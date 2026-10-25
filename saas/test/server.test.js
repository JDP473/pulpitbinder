// Starts the server with a fresh data folder and a stand-in for Anthropic's API, then checks accounts, each
// preacher's data staying their own, files, Claude, and the owner's shared key.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pb-saas-'));
const PORT = 3900 + Math.floor(Math.random() * 90);
const BASE = `http://127.0.0.1:${PORT}`;
let server, mock;
const seen = [];

before(async () => {
  // The stand-in Anthropic API: a key named sk-ant-bad is refused; anything else gets JSON back.
  mock = http.createServer((req, res) => {
    let body = '';
    req.on('data', (d) => (body += d));
    req.on('end', () => {
      const key = req.headers['x-api-key'] || (req.headers.authorization || '').replace(/^Bearer /, '');
      seen.push({ url: req.url, key, body: body ? JSON.parse(body) : null, beta: req.headers['anthropic-beta'] });
      res.setHeader('content-type', 'application/json');
      if (key === 'sk-ant-bad-key-000000000000') {
        res.statusCode = 401;
        return res.end(JSON.stringify({ type: 'error', error: { type: 'authentication_error', message: 'invalid x-api-key' } }));
      }
      if (req.url.startsWith('/v1/models/')) return res.end(JSON.stringify({ id: 'claude-haiku-5-5', type: 'model' }));
      res.end(JSON.stringify({
        id: 'msg_1', type: 'message', role: 'assistant', model: JSON.parse(body).model, stop_reason: 'end_turn',
        content: [{ type: 'text', text: '```json\n{"bigIdea":"Walk in the light."}\n```' }],
        usage: { input_tokens: 120, output_tokens: 30 },
      }));
    });
  }).listen(0);
  await new Promise((r) => mock.once('listening', r));
  server = spawn(process.execPath, ['server/index.js'], {
    cwd: new URL('..', import.meta.url).pathname,
    env: { ...process.env, PORT: String(PORT), DATA_DIR: dir, APP_URL: BASE, PLATFORM_OWNER_EMAIL: 'owner@example.com', ANTHROPIC_API_KEY: 'sk-ant-shared-key-0000000000', ANTHROPIC_BASE_URL: `http://127.0.0.1:${mock.address().port}`, SMTP_HOST: '', STRIPE_SECRET_KEY: '' },
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

/** A browser-like client that keeps its own cookie. */
function client() {
  let cookie = '';
  const call = async (method, url, body, headers = {}) => {
    const raw = body instanceof Uint8Array;
    const res = await fetch(BASE + url, {
      method,
      redirect: 'manual',
      headers: { origin: BASE, ...(cookie && { cookie }), ...(body !== undefined && !raw && { 'content-type': 'application/json' }), ...headers },
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    });
    const set = res.headers.getSetCookie?.() || [];
    for (const s of set) if (s.startsWith('pb_session=')) cookie = s.split(';')[0];
    const type = res.headers.get('content-type') || '';
    return { status: res.status, headers: res.headers, json: type.includes('json') ? await res.json() : null, text: type.includes('json') ? null : await res.text() };
  };
  return { call, get cookie() { return cookie; } };
}

async function signUp(name, email) {
  const c = client();
  const r = await c.call('POST', '/api/auth/register', { name, email, password: 'correct horse battery' });
  assert.equal(r.status, 200, JSON.stringify(r.json));
  const me = await c.call('GET', '/api/auth/me');
  return { c, id: me.json.user.id, me: me.json };
}

test('public page, sign up, and the app page', async () => {
  const anon = client();
  const home = await anon.call('GET', '/');
  assert.equal(home.status, 200);
  assert.match(home.text, /data-auth="out"/);
  assert.match(home.text, /Write it, bind it/);
  assert.equal((await anon.call('GET', '/app')).headers.get('location'), '/login?next=/app');
  assert.equal((await anon.call('GET', '/api/db/doc?path=data/users/x/y')).status, 401);

  const { c, me } = await signUp('Pat Preacher', 'pat@example.com');
  assert.equal(me.user.name, 'Pat Preacher');
  assert.equal(me.user.claude, null);
  const app = await c.call('GET', '/app');
  assert.equal(app.status, 200);
  assert.match(app.text, /window\.__PB__=\{"id":"[0-9a-f-]+","name":"Pat Preacher"/);
  assert.match(app.text, /<script src="\/shim\.js"><\/script>/);
  assert.match(app.text, /<title>Pulpit Binder<\/title>/);
  assert.match(app.headers.get('content-security-policy'), /script-src 'self' 'unsafe-inline' https:\/\/cdnjs\.cloudflare\.com/);
  assert.equal((await c.call('POST', '/api/auth/register', { name: 'X', email: 'pat@example.com', password: 'another password' })).status, 409);
  const bad = client();
  assert.equal((await bad.call('POST', '/api/auth/login', { email: 'pat@example.com', password: 'wrong password' })).status, 401);
  assert.equal((await bad.call('POST', '/api/auth/login', { email: 'pat@example.com', password: 'correct horse battery' })).status, 200);
});

test('documents: set, get, list, change feed, and each preacher only reaches their own', async () => {
  const a = await signUp('Alice', 'alice@example.com');
  const b = await signUp('Bob', 'bob@example.com');
  const root = `data/users/${a.id}`;
  const put = (p, data) => a.c.call('PUT', '/api/db/doc', { path: `${root}/${p}`, data });
  const start = (await a.c.call('GET', `/api/db/list?collection=${root}`)).json.seq;
  assert.equal((await put('s1', { title: 'Grace', updatedAt: 2 })).status, 200);
  await put('s2', { title: 'Faith', updatedAt: 1 });
  await put('_prefs', { defVer: 'ESV' });
  await put('s1/parts/html.0', { s: '<p>Hello</p>' });
  await put('_cache/ai/k1', { v: '{}', at: 5 });
  await put('_cache/ai/k2', { v: '{}', at: 9 });

  const got = await a.c.call('GET', `/api/db/doc?path=${root}/s1/parts/html.0`);
  assert.deepEqual(got.json.data, { s: '<p>Hello</p>' });
  assert.equal((await a.c.call('GET', `/api/db/doc?path=${root}/nope`)).json.exists, false);

  const list = await a.c.call('GET', `/api/db/list?collection=${root}`);
  assert.deepEqual(list.json.docs.map((d) => d.id).sort(), ['_prefs', 's1', 's2']);
  const recent = await a.c.call('GET', `/api/db/list?collection=${root}/_cache/ai&orderBy=at&dir=desc&limit=1`);
  assert.deepEqual(recent.json.docs.map((d) => d.id), ['k2']);

  // The feed for the sermons collection carries only its own documents, with deletes as data null.
  await a.c.call('DELETE', `/api/db/doc?path=${root}/s2`);
  const feed = await a.c.call('GET', `/api/db/changes?since=${start}&parent=${encodeURIComponent(root)}`);
  assert.deepEqual(feed.json.changes.map((ch) => [ch.path.slice(root.length + 1), ch.data === null]), [['s1', false], ['_prefs', false], ['s2', true]]);
  assert.ok(feed.json.seq >= feed.json.changes.at(-1).seq);

  // Bob can't read, write, list, or follow Alice's documents.
  assert.equal((await b.c.call('GET', `/api/db/doc?path=${root}/s1`)).status, 403);
  assert.equal((await b.c.call('PUT', '/api/db/doc', { path: `${root}/s9`, data: { x: 1 } })).status, 403);
  assert.equal((await b.c.call('GET', `/api/db/list?collection=${root}`)).status, 403);
  assert.equal((await b.c.call('GET', `/api/db/changes?since=0&parent=${encodeURIComponent(root)}`)).status, 403);
  assert.equal((await a.c.call('PUT', '/api/db/doc', { path: `${root}/../${b.id}/x`, data: { x: 1 } })).status, 400);
  assert.equal((await a.c.call('GET', `/api/db/list?collection=data/users/${b.id}`)).status, 403);

  // Cross-site writes are refused.
  assert.equal((await a.c.call('PUT', '/api/db/doc', { path: `${root}/s3`, data: { x: 1 } }, { origin: 'https://evil.example' })).status, 403);
});

test('files: upload, read back with ranges, and only by their owner', async () => {
  const a = await signUp('Carol', 'carol@example.com');
  const b = await signUp('Dan', 'dan@example.com');
  const bytes = new TextEncoder().encode('generic test picture bytes');
  const up = await a.c.call('POST', '/api/assets', bytes, { 'content-type': 'image/png' });
  assert.equal(up.status, 200);
  const id = up.json.id;
  const got = await a.c.call('GET', `/_blob/${id}`);
  assert.equal(got.status, 200);
  assert.equal(got.headers.get('content-type'), 'image/png');
  assert.equal(got.text, 'generic test picture bytes');
  const part = await a.c.call('GET', `/_blob/${id}`, undefined, { range: 'bytes=0-6' });
  assert.equal(part.status, 206);
  assert.equal(part.text, 'generic');
  assert.equal((await b.c.call('GET', `/_blob/${id}`)).status, 404);
  assert.equal((await client().call('GET', `/_blob/${id}`)).status, 401);
});

test('Claude: no key, a refused key, an own key, and the shared key the owner lends', async () => {
  const p = await signUp('Eve', 'eve@example.com');
  const ask = () => p.c.call('POST', '/api/ai', { prompt: 'Return ONLY JSON {"bigIdea":""}', tier: 'default' });
  const none = await ask();
  assert.equal(none.status, 402);
  assert.equal(none.json.code, 'no_key');

  assert.equal((await p.c.call('PUT', '/api/account/key', { key: 'not a key at all, really' })).status, 400);
  assert.equal((await p.c.call('PUT', '/api/account/key', { key: 'sk-ant-bad-key-000000000000' })).status, 400);
  const saved = await p.c.call('PUT', '/api/account/key', { key: 'sk-ant-own-key-1111111111111' });
  assert.equal(saved.status, 200);
  assert.equal(saved.json.keyHint, 'sk-ant-...1111');
  const stored = (await p.c.call('GET', '/api/auth/me')).json.user;
  assert.equal(stored.claude, 'own');

  seen.length = 0;
  const r = await ask();
  assert.equal(r.status, 200, JSON.stringify(r.json));
  assert.deepEqual(r.json.value, { bigIdea: 'Walk in the light.' });
  const sent = seen.find((s) => s.url.startsWith('/v1/messages'));
  assert.equal(sent.key, 'sk-ant-own-key-1111111111111');
  assert.equal(sent.body.model, 'claude-sonnet-5-5');
  assert.equal(sent.body.fallbacks, 'default');
  assert.match(sent.beta, /server-side-fallback-2026-07-01/);
  assert.equal(sent.body.output_config.effort, 'medium');

  seen.length = 0;
  await p.c.call('POST', '/api/ai', { prompt: 'Return ONLY JSON {}', tier: 'quick' });
  const quick = seen.find((s) => s.url.startsWith('/v1/messages'));
  assert.equal(quick.body.model, 'claude-haiku-5-5');
  assert.equal(quick.body.fallbacks, undefined);

  const usage = await p.c.call('GET', '/api/account/usage');
  assert.equal(usage.json.claude.reduce((a, r) => a + r.requests, 0), 2);

  // The key is not stored in plain text.
  const dbFile = fs.readFileSync(path.join(dir, 'pulpit.db'));
  assert.equal(dbFile.includes('sk-ant-own-key-1111111111111'), false);

  // The owner lends the shared key to a preacher without one.
  const f = await signUp('Frank', 'frank@example.com');
  assert.equal((await f.c.call('GET', '/api/admin/users')).status, 403);
  const owner = await signUp('Owner', 'owner@example.com');
  assert.equal(owner.me.user.isOwner, false, 'an unconfirmed address is not the owner yet');
  assert.equal(owner.me.user.ownerNeedsConfirmation, true);
});

test('the owner, once confirmed, lends the shared key and can turn an account off', async () => {
  const { DatabaseSync } = await import('node:sqlite').catch(() => ({}));
  const owner = client();
  assert.equal((await owner.call('POST', '/api/auth/login', { email: 'owner@example.com', password: 'correct horse battery' })).status, 200);
  // Stand in for clicking the emailed confirmation link.
  if (DatabaseSync) {
    const db = new DatabaseSync(path.join(dir, 'pulpit.db'));
    db.prepare("UPDATE users SET email_verified_at = '2026-10-25T00:00:00Z' WHERE email = 'owner@example.com'").run();
    db.close();
  } else assert.fail('node:sqlite is needed for this test');
  const users = await owner.call('GET', '/api/admin/users');
  assert.equal(users.status, 200);
  assert.equal(users.json.sharedKeyConfigured, true);
  const frank = users.json.users.find((u) => u.email === 'frank@example.com');
  assert.equal((await owner.call('PATCH', `/api/admin/users/${frank.id}`, { sharedKey: true })).status, 200);

  const f = client();
  await f.call('POST', '/api/auth/login', { email: 'frank@example.com', password: 'correct horse battery' });
  assert.equal((await f.call('GET', '/api/auth/me')).json.user.claude, 'shared');
  seen.length = 0;
  const r = await f.call('POST', '/api/ai', { prompt: 'Return ONLY JSON {}', tier: 'complex' });
  assert.equal(r.status, 200);
  const sent = seen.find((s) => s.url.startsWith('/v1/messages'));
  assert.equal(sent.key, 'sk-ant-shared-key-0000000000');
  assert.equal(sent.body.model, 'claude-opus-5-5');
  const after = (await owner.call('GET', '/api/admin/users')).json.users.find((u) => u.email === 'frank@example.com');
  assert.equal(after.sharedRequests30, 1);

  assert.equal((await owner.call('PATCH', `/api/admin/users/${frank.id}`, { disabled: true })).status, 200);
  assert.equal((await f.call('GET', '/api/auth/me')).json.user, null);
  assert.equal((await f.call('POST', '/api/auth/login', { email: 'frank@example.com', password: 'correct horse battery' })).status, 403);
});

test('deleting an account removes its documents and files', async () => {
  const g = await signUp('Gail', 'gail@example.com');
  await g.c.call('PUT', '/api/db/doc', { path: `data/users/${g.id}/s1`, data: { title: 'x' } });
  await g.c.call('POST', '/api/assets', new TextEncoder().encode('abc'), { 'content-type': 'text/plain' });
  assert.ok(fs.existsSync(path.join(dir, 'assets', g.id)));
  assert.equal((await g.c.call('DELETE', '/api/auth/account', { password: 'correct horse battery' })).status, 200);
  assert.equal(fs.existsSync(path.join(dir, 'assets', g.id)), false);
  assert.equal((await g.c.call('GET', '/api/auth/me')).json.user, null);
});
