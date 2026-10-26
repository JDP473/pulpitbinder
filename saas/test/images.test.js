// Pictures on each preacher's own keys: the server against stand-ins for OpenAI, Google, Stability AI, and Adobe
// Firefly. Keys are tried before they're kept, every picture is asked for wide (16:9), and failures say what to do.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pb-img-'));
const PORT = 3990 + Math.floor(Math.random() * 9);
const BASE = `http://127.0.0.1:${PORT}`;
const PNG = fs.readFileSync(new URL('../../tests/fixtures/preview.png', import.meta.url));
let server, mock, MOCK;
const seen = [];
let imsCalls = 0, polls = 0;

before(async () => {
  // Keys with "bad" in them are refused; "broke" is out of credit. A prompt with "forbidden" is declined.
  mock = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (d) => chunks.push(d));
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      const auth = req.headers.authorization || '';
      const key = req.headers['x-goog-api-key'] || auth.replace(/^Bearer /, '');
      const type = req.headers['content-type'] || '';
      const body = type.includes('json') && raw ? JSON.parse(raw) : raw;
      seen.push({ url: req.url, key, body, headers: req.headers });
      const json = (status, v) => { res.statusCode = status; res.setHeader('content-type', 'application/json'); res.end(JSON.stringify(v)); };
      const u = req.url;
      // OpenAI
      if (u === '/openai/v1/models') return /bad/.test(key) ? json(401, { error: { message: 'Incorrect API key', type: 'invalid_request_error', code: 'invalid_api_key' } }) : json(200, { data: [] });
      if (u === '/openai/v1/images/generations') {
        if (/broke/.test(key)) return json(429, { error: { message: 'You exceeded your current quota', type: 'insufficient_quota', code: 'insufficient_quota' } });
        if (/forbidden/.test(body.prompt)) return json(400, { error: { message: 'Your request was rejected by the safety system.', code: 'moderation_blocked' } });
        return json(200, { created: 1, data: [{ b64_json: PNG.toString('base64') }] });
      }
      // Google
      if (u.startsWith('/google/v1beta/models')) return /bad/.test(key) ? json(400, { error: { code: 400, message: 'API key not valid. Please pass a valid API key.', status: 'INVALID_ARGUMENT' } }) : json(200, { models: [] });
      if (u === '/google/v1beta/interactions') {
        if (/forbidden/.test(body.input[0].text)) return json(200, { id: 'i1', steps: [{ type: 'model_output', content: [{ type: 'text', text: 'I can not make that.' }] }] });
        return json(200, { id: 'i2', status: 'completed', steps: [{ type: 'thought', content: [] }, { type: 'model_output', content: [{ type: 'text', text: 'Here it is.' }, { type: 'image', mime_type: 'image/png', data: PNG.toString('base64') }] }] });
      }
      // Stability AI
      if (u === '/stability/v1/user/account') return /bad/.test(key) ? json(401, { name: 'unauthorized', errors: ['invalid key'] }) : json(200, { id: 'acct' });
      if (u === '/stability/v2beta/stable-image/generate/core') {
        if (/broke/.test(key)) return json(402, { name: 'payment_required', errors: ['not enough credits'] });
        res.setHeader('content-type', 'image/png');
        res.setHeader('finish-reason', /forbidden/.test(raw) ? 'CONTENT_FILTERED' : 'SUCCESS');
        return res.end(PNG);
      }
      // Adobe
      if (u === '/ims/ims/token/v3') {
        imsCalls++;
        const f = new URLSearchParams(raw);
        if (/bad/.test(f.get('client_secret') || '')) return json(400, { error: 'invalid_client', error_description: 'invalid client_secret parameter' });
        return json(200, { access_token: 'adobe-token-1', token_type: 'bearer', expires_in: 86399 });
      }
      if (u === '/firefly/v3/images/generate-async') {
        if (auth !== 'Bearer adobe-token-1') return json(401, { error_code: 'unauthorized', message: 'bad token' });
        polls = 0;
        return json(202, { jobId: 'urn:ff:jobs:1', statusUrl: `${MOCK}/firefly/v3/status/urn:ff:jobs:1`, cancelUrl: `${MOCK}/firefly/v3/cancel/urn:ff:jobs:1` });
      }
      if (u.startsWith('/firefly/v3/status/')) {
        polls++;
        if (polls < 2) return json(200, { status: 'running', jobId: 'urn:ff:jobs:1' });
        return json(200, { status: 'succeeded', jobId: 'urn:ff:jobs:1', result: { size: { width: 2688, height: 1536 }, outputs: [{ seed: 1, image: { url: `${MOCK}/files/out.png` } }] } });
      }
      if (u === '/files/out.png') { res.setHeader('content-type', 'image/png'); return res.end(PNG); }
      json(404, { error: 'not found' });
    });
  }).listen(0);
  await new Promise((r) => mock.once('listening', r));
  MOCK = `http://127.0.0.1:${mock.address().port}`;
  server = spawn(process.execPath, ['server/index.js'], {
    cwd: new URL('..', import.meta.url).pathname,
    env: { ...process.env, PORT: String(PORT), DATA_DIR: dir, APP_URL: BASE, PLATFORM_OWNER_EMAIL: 'owner@example.com', ANTHROPIC_API_KEY: '', IMAGE_API_BASE: MOCK, SMTP_HOST: '', STRIPE_SECRET_KEY: '' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  server.stdout.on('data', (d) => (log += d));
  server.stderr.on('data', (d) => (log += d));
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(`${BASE}/api/health`)).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('server did not start\n' + log);
});

after(() => {
  server?.kill();
  mock?.close();
  fs.rmSync(dir, { recursive: true, force: true });
});

let ipSeq = 0;
async function signUp(name, email) {
  let cookie = '';
  const call = async (method, url, body, headers = {}) => {
    const res = await fetch(BASE + url, {
      method,
      redirect: 'manual',
      headers: { origin: BASE, ...(cookie && { cookie }), ...(body !== undefined && { 'content-type': 'application/json' }), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    for (const s of res.headers.getSetCookie?.() || []) if (s.startsWith('pb_session=')) cookie = s.split(';')[0];
    const type = res.headers.get('content-type') || '';
    return { status: res.status, type, json: type.includes('json') ? await res.json() : null, bytes: type.includes('json') ? null : Buffer.from(await res.arrayBuffer()) };
  };
  const r = await call('POST', '/api/auth/register', { name, email, password: 'correct horse battery' }, { 'cf-connecting-ip': `10.1.0.${++ipSeq}` });
  assert.equal(r.status, 200, JSON.stringify(r.json));
  return call;
}
const paint = (call, provider, prompt = 'An oil lamp on a stone path at dusk') => call('POST', '/api/image', { provider, prompt });

test('no key, then an OpenAI key tried, kept encrypted, and used for a wide picture', async () => {
  const call = await signUp('Gail', 'gail@example.com');
  const none = await paint(call, 'openai');
  assert.equal(none.status, 402);
  assert.equal(none.json.code, 'no_key');
  assert.equal((await call('POST', '/api/image', { provider: 'midjourney', prompt: 'a lamp' })).status, 400);

  assert.match((await call('PUT', '/api/account/image-key/openai', { key: 'not a key' })).json.error, /starts with sk-/);
  assert.match((await call('PUT', '/api/account/image-key/openai', { key: 'sk-bad-0000000000000000000000' })).json.error, /OpenAI did not accept/);
  const saved = await call('PUT', '/api/account/image-key/openai', { key: 'sk-proj-good-111111111111111111' });
  assert.equal(saved.status, 200, JSON.stringify(saved.json));
  assert.equal(saved.json.hint, 'sk-pro...1111');
  assert.deepEqual((await call('GET', '/api/auth/me')).json.user.imageKeys, { openai: 'sk-pro...1111' });

  seen.length = 0;
  const pic = await paint(call, 'openai');
  assert.equal(pic.status, 200);
  assert.equal(pic.type, 'image/png');
  assert.ok(pic.bytes.equals(PNG));
  const sent = seen.find((s) => s.url === '/openai/v1/images/generations');
  assert.equal(sent.key, 'sk-proj-good-111111111111111111');
  assert.equal(sent.body.model, 'gpt-image-2.5-flare');
  assert.equal(sent.body.size, '2048x1152');
  assert.equal(sent.body.response_format, undefined);

  const declined = await paint(call, 'openai', 'something forbidden');
  assert.equal(declined.status, 422);
  assert.equal(declined.json.code, 'refused');

  const db = fs.readFileSync(path.join(dir, 'pulpit.db'));
  assert.equal(db.includes('sk-proj-good-111111111111111111'), false);

  // Another preacher can't paint on Gail's key.
  const other = await signUp('Hal', 'hal@example.com');
  assert.equal((await paint(other, 'openai')).json.code, 'no_key');

  const usage = (await call('GET', '/api/account/usage')).json;
  assert.deepEqual(usage.claude, []);
  assert.deepEqual(usage.pictures, [{ model: 'gpt-image-2.5-flare', requests: 2 }]);

  assert.equal((await call('DELETE', '/api/account/image-key/openai')).status, 200);
  assert.equal((await paint(call, 'openai')).json.code, 'no_key');
  assert.deepEqual((await call('GET', '/api/auth/me')).json.user.imageKeys, {});
});

test('the app learns which picture keys are in', async () => {
  const call = await signUp('Ida', 'ida@example.com');
  await call('PUT', '/api/account/image-key/stability', { key: 'sk-stab-good-2222222222222222' });
  const app = await call('GET', '/app');
  assert.match(app.bytes.toString('utf8'), /"images":\["stability"\]/);
});

test('Google: a refused key, then Nano Banana at 16:9, and an answer with no picture', async () => {
  const call = await signUp('Jo', 'jo@example.com');
  assert.match((await call('PUT', '/api/account/image-key/google', { key: 'AIzaSy-bad-00000000000000000000000000' })).json.error, /Google Gemini did not accept/);
  assert.equal((await call('PUT', '/api/account/image-key/google', { key: 'AIzaSyGood11111111111111111111111111111' })).status, 200);
  seen.length = 0;
  const pic = await paint(call, 'google');
  assert.equal(pic.status, 200, JSON.stringify(pic.json));
  assert.ok(pic.bytes.equals(PNG));
  const sent = seen.find((s) => s.url === '/google/v1beta/interactions');
  assert.equal(sent.key, 'AIzaSyGood11111111111111111111111111111');
  assert.equal(sent.body.model, 'gemini-nano-banana-2.1');
  assert.deepEqual(sent.body.response_format, { type: 'image', mime_type: 'image/png', aspect_ratio: '16:9', image_size: '2K' });
  assert.equal(sent.body.store, false);
  const none = await paint(call, 'google', 'something forbidden');
  assert.equal(none.status, 422);
  assert.match(none.json.error, /without a picture/);
});

test('Stability AI: Core at 16:9, filtered pictures, and an empty account', async () => {
  const call = await signUp('Kit', 'kit@example.com');
  assert.match((await call('PUT', '/api/account/image-key/stability', { key: 'sk-bad-stab-000000000000000' })).json.error, /Stability AI did not accept/);
  assert.equal((await call('PUT', '/api/account/image-key/stability', { key: 'sk-stab-good-3333333333333333' })).status, 200);
  seen.length = 0;
  const pic = await paint(call, 'stability');
  assert.equal(pic.status, 200, JSON.stringify(pic.json));
  const sent = seen.find((s) => s.url === '/stability/v2beta/stable-image/generate/core');
  assert.match(sent.headers['content-type'], /multipart\/form-data/);
  assert.match(sent.body, /name="aspect_ratio"\r\n\r\n16:9/);
  assert.equal(sent.headers.accept, 'image/*');
  assert.equal((await paint(call, 'stability', 'something forbidden')).json.code, 'refused');

  assert.equal((await call('PUT', '/api/account/image-key/stability', { key: 'sk-stab-broke-444444444444444' })).status, 200);
  const broke = await paint(call, 'stability');
  assert.equal(broke.json.code, 'no_credit');
  assert.match(broke.json.error, /out of credit/);
});

test('Adobe Firefly: client ID and secret, a token kept between pictures, and the job followed to its picture', async () => {
  const call = await signUp('Lee', 'lee@example.com');
  assert.match((await call('PUT', '/api/account/image-key/firefly', { clientId: 'short', clientSecret: 'x' })).json.error, /client ID/);
  assert.match((await call('PUT', '/api/account/image-key/firefly', { clientId: 'a1b2c3d4e5f6a7b8c9d0', clientSecret: 'p8e-bad-secret-000000000' })).json.error, /Adobe did not accept/);
  imsCalls = 0;
  const saved = await call('PUT', '/api/account/image-key/firefly', { clientId: 'a1b2c3d4e5f6a7b8c9d0', clientSecret: 'p8e-good-secret-11111111' });
  assert.equal(saved.status, 200, JSON.stringify(saved.json));
  assert.equal(saved.json.hint, 'a1b2c3...c9d0');

  seen.length = 0;
  const pic = await paint(call, 'firefly');
  assert.equal(pic.status, 200, JSON.stringify(pic.json));
  assert.ok(pic.bytes.equals(PNG));
  const sent = seen.find((s) => s.url === '/firefly/v3/images/generate-async');
  assert.equal(sent.headers['x-api-key'], 'a1b2c3d4e5f6a7b8c9d0');
  assert.equal(sent.headers['x-model-version'], 'image4_standard');
  assert.deepEqual(sent.body.size, { width: 2688, height: 1536 });
  assert.ok(seen.filter((s) => s.url.startsWith('/firefly/v3/status/')).length >= 2, 'polled until done');
  assert.equal((await paint(call, 'firefly')).status, 200);
  assert.equal(imsCalls, 1, 'the token from checking the key serves both pictures');
});
