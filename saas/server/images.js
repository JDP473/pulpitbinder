// Pictures for the app, on each preacher's own keys with the image services they choose: OpenAI, Google (Nano Banana),
// Stability AI, and Adobe Firefly. Every picture is wide (16:9) for a slide, and comes back as image bytes.
import { env } from './env.js';
import { openKey, sealKey } from './keys.js';
import { all, run } from './db.js';
import { HttpError, nowIso, sha256 } from './util.js';

export const PROVIDERS = {
  openai: { name: 'OpenAI', model: 'gpt-image-2.5-flare' },
  google: { name: 'Google Gemini', model: 'gemini-nano-banana-2.1' },
  stability: { name: 'Stability AI', model: 'stable-image-core' },
  firefly: { name: 'Adobe Firefly', model: 'firefly-image4' },
};

// Where each service lives. IMAGE_API_BASE sends all of them to one stand-in server (tests), under its own path.
const base = (p) => (env.imageApiBase ? `${env.imageApiBase}/${p}` : null);
const URLS = {
  openai: () => base('openai') || 'https://api.openai.com',
  google: () => base('google') || 'https://generativelanguage.googleapis.com',
  stability: () => base('stability') || 'https://api.stability.ai',
  firefly: () => base('firefly') || 'https://firefly-api.adobe.io',
  ims: () => base('ims') || 'https://ims-na1.adobelogin.com',
};
const FIREFLY_SCOPE = 'openid,AdobeID,session,additional_info,read_organizations,firefly_api,ff_apis';
const PAINT_MS = 3 * 60_000;

/** What a preacher types for each service: one key, or (Firefly) a client ID and secret. Returns the credential or a message. */
export function readCredential(provider, body) {
  const s = (v) => (typeof v === 'string' ? v.trim() : '');
  if (provider === 'firefly') {
    const clientId = s(body.clientId), clientSecret = s(body.clientSecret);
    if (!/^[\w-]{16,100}$/.test(clientId)) return { error: 'That does not look like a Firefly client ID. Copy it from your project in the Adobe Developer Console.' };
    if (!/^[\w.-]{16,200}$/.test(clientSecret)) return { error: 'That does not look like a Firefly client secret. Copy it from your project in the Adobe Developer Console.' };
    return { cred: { clientId, clientSecret }, hint: `${clientId.slice(0, 6)}...${clientId.slice(-4)}` };
  }
  const key = s(body.key);
  const shape = { openai: /^sk-[\w-]{20,300}$/, stability: /^sk-[\w-]{20,300}$/, google: /^[\w.-]{30,300}$/ }[provider];   // Google's newer auth keys start with AQ. and carry dots
  if (!shape.test(key)) {
    return { error: { openai: 'That does not look like an OpenAI API key. It starts with sk-.', stability: 'That does not look like a Stability AI API key. It starts with sk-.', google: 'That does not look like a Gemini API key. Copy it from Google AI Studio.' }[provider] };
  }
  return { cred: { key }, hint: `${key.slice(0, 6)}...${key.slice(-4)}` };
}

export function saveImageKey(userId, provider, cred, hint) {
  run(
    `INSERT INTO image_keys (user_id, provider, sealed, hint, created_at) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT (user_id, provider) DO UPDATE SET sealed = excluded.sealed, hint = excluded.hint, created_at = excluded.created_at`,
    userId, provider, sealKey(JSON.stringify(cred)), hint, nowIso(),
  );
}
export const removeImageKey = (userId, provider) => run('DELETE FROM image_keys WHERE user_id = ? AND provider = ?', userId, provider);

/** { openai: "sk-pro...wxyz", ... } for the services this preacher has a key in for. */
export function imageKeyHints(userId) {
  return Object.fromEntries(all('SELECT provider, hint FROM image_keys WHERE user_id = ?', userId).filter((r) => PROVIDERS[r.provider]).map((r) => [r.provider, r.hint]));
}
function credentialFor(userId, provider) {
  const row = all('SELECT sealed FROM image_keys WHERE user_id = ? AND provider = ?', userId, provider)[0];
  try {
    return row ? JSON.parse(openKey(row.sealed)) : null;
  } catch {
    return null;
  }
}

async function call(url, opts, ms = 30_000) {
  try {
    return await fetch(url, { ...opts, signal: AbortSignal.timeout(ms) });
  } catch (e) {
    if (e && e.name === 'TimeoutError') return { timeout: true };
    return { unreachable: true };
  }
}
const readJson = async (r) => {
  try {
    return await r.json();
  } catch {
    return null;
  }
};

/** Checks a credential before it's saved. Null when it's fine (or the service is only busy), else what to tell them. */
export async function testImageKey(provider, cred) {
  const name = PROVIDERS[provider].name;
  const refused = `${name} did not accept that key. Copy it again and paste it here.`;
  if (provider === 'firefly') {
    const t = await fireflyToken(cred, true).catch((e) => e);
    return t instanceof HttpError && t.code === 'bad_key' ? 'Adobe did not accept that client ID and secret. Check that the project has the Firefly API added.' : null;
  }
  const r =
    provider === 'openai' ? await call(`${URLS.openai()}/v1/models`, { headers: { authorization: `Bearer ${cred.key}` } })
    : provider === 'google' ? await call(`${URLS.google()}/v1beta/models?pageSize=1`, { headers: { 'x-goog-api-key': cred.key } })
    : await call(`${URLS.stability()}/v1/user/account`, { headers: { authorization: `Bearer ${cred.key}` } });
  if (r.timeout || r.unreachable) return null;
  if (r.status === 401 || r.status === 403) return refused;
  if (provider === 'google' && r.status === 400) {
    const j = await readJson(r);
    if (/API key|API_KEY/i.test(JSON.stringify(j || ''))) return refused;
  }
  return null;
}

// Adobe hands out a token for a client ID and secret that lasts about a day; keep one per client.
const tokens = new Map();
async function fireflyToken({ clientId, clientSecret }, fresh) {
  const kept = tokens.get(clientId);
  if (!fresh && kept && kept.secret === sha256(clientSecret) && kept.until > Date.now()) return kept.token;
  const body = new URLSearchParams({ grant_type: 'client_credentials', client_id: clientId, client_secret: clientSecret, scope: FIREFLY_SCOPE });
  const r = await call(`${URLS.ims()}/ims/token/v3`, { method: 'POST', body });
  if (r.timeout || r.unreachable) throw new HttpError(503, "Couldn't reach Adobe. Try again in a minute.", 'unavailable');
  const j = await readJson(r);
  if (!r.ok || !j || !j.access_token) {
    if (r.status === 400 || r.status === 401 || r.status === 403) throw new HttpError(400, 'Adobe did not accept your Firefly client ID and secret. Check them in Account.', 'bad_key');
    throw new HttpError(503, 'Adobe is busy right now. Try again in a minute.', 'busy');
  }
  if (tokens.size > 200) tokens.clear();
  tokens.set(clientId, { token: j.access_token, secret: sha256(clientSecret), until: Date.now() + Math.max(60, (j.expires_in || 3600) - 600) * 1000 });
  return j.access_token;
}

/** What a failed request means, the same way for every service. */
function failure(provider, status, detail) {
  const name = PROVIDERS[provider].name;
  const d = String(detail || '');
  if (status === 401 || (status === 403 && provider !== 'stability')) return new HttpError(400, `${name} did not accept your key. Check it in Account.`, 'bad_key');
  if (status === 402 || /insufficient_quota|billing|credit|balance/i.test(d)) return new HttpError(400, `Your ${name} account is out of credit. Add credit with ${name}, then try again.`, 'no_credit');
  if ((status === 403 && provider === 'stability') || /moderation|content_policy|safety|blocked|CONTENT_FILTERED/i.test(d)) return new HttpError(422, `${name} declined to paint that. Try different words.`, 'refused');
  if (status === 429) return new HttpError(429, `${name} has had too many requests right now. Try again in a minute.`, 'rate_limited');
  if (status >= 400 && status < 500) {
    console.warn('[images]', provider, status, d.slice(0, 300));
    return new HttpError(400, `${name} couldn't take that request. Try different words.`, 'bad_request');
  }
  console.warn('[images]', provider, status, d.slice(0, 300));
  return new HttpError(503, `${name} is busy right now. Try again in a minute.`, 'busy');
}
const unreachable = (provider, r) => new HttpError(503, r.timeout ? `${PROVIDERS[provider].name} took too long. Try again.` : `Couldn't reach ${PROVIDERS[provider].name}. Try again in a minute.`, 'unavailable');

/** The picture type from its first bytes, or null when it isn't a picture. */
function sniff(buf) {
  if (buf.length > 8 && buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return 'image/png';
  if (buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return 'image/jpeg';
  if (buf.length > 12 && buf.toString('ascii', 0, 4) === 'RIFF' && buf.toString('ascii', 8, 12) === 'WEBP') return 'image/webp';
  return null;
}
function picture(provider, buf) {
  const mime = buf && sniff(buf);
  if (!mime) throw new HttpError(502, `${PROVIDERS[provider].name} didn't send back a picture. Try again.`, 'empty');
  return { buf, mime };
}

/** The last image block anywhere in a Gemini interaction (its execution steps hold the model's output). */
function lastImage(v) {
  let found = null;
  const walk = (x) => {
    if (Array.isArray(x)) return x.forEach(walk);
    if (!x || typeof x !== 'object') return;
    if (x.type === 'image' && typeof x.data === 'string' && x.data.length > 100) found = x.data;
    Object.values(x).forEach(walk);
  };
  walk(v);
  return found;
}

const painters = {
  async openai(cred, prompt, userId) {
    const r = await call(`${URLS.openai()}/v1/images/generations`, {
      method: 'POST',
      headers: { authorization: `Bearer ${cred.key}`, 'content-type': 'application/json' },
      body: JSON.stringify({ model: PROVIDERS.openai.model, prompt, n: 1, size: '2048x1152', quality: 'medium', output_format: 'png', safety_identifier: sha256(userId).slice(0, 32) }),
    }, PAINT_MS);
    if (r.timeout || r.unreachable) throw unreachable('openai', r);
    const j = await readJson(r);
    if (!r.ok) throw failure('openai', r.status, j && j.error && `${j.error.code || ''} ${j.error.type || ''} ${j.error.message || ''}`);
    const b64 = j && j.data && j.data[0] && j.data[0].b64_json;
    return picture('openai', b64 ? Buffer.from(b64, 'base64') : null);
  },

  async google(cred, prompt) {
    const r = await call(`${URLS.google()}/v1beta/interactions`, {
      method: 'POST',
      headers: { 'x-goog-api-key': cred.key, 'content-type': 'application/json' },
      body: JSON.stringify({
        model: PROVIDERS.google.model,
        input: [{ type: 'text', text: prompt }],
        response_format: { type: 'image', mime_type: 'image/png', aspect_ratio: '16:9', image_size: '2K' },
        store: false,
      }),
    }, PAINT_MS);
    if (r.timeout || r.unreachable) throw unreachable('google', r);
    const j = await readJson(r);
    if (!r.ok) {
      const e = (j && j.error) || {};
      const detail = `${e.status || ''} ${e.message || ''}`;
      // Google answers a bad key with 400, and a project without billing with FAILED_PRECONDITION.
      throw failure('google', /API key not valid|API_KEY_INVALID/i.test(detail) ? 401 : /billing/i.test(detail) ? 402 : r.status, detail);
    }
    const b64 = lastImage(j);
    if (!b64) throw new HttpError(422, 'Google answered without a picture. Try different words.', 'refused');
    return picture('google', Buffer.from(b64, 'base64'));
  },

  async stability(cred, prompt) {
    const form = new FormData();
    form.set('prompt', prompt);
    form.set('aspect_ratio', '16:9');
    form.set('output_format', 'png');
    const r = await call(`${URLS.stability()}/v2beta/stable-image/generate/core`, {
      method: 'POST',
      headers: { authorization: `Bearer ${cred.key}`, accept: 'image/*', 'stability-client-id': 'pulpit-binder' },
      body: form,
    }, PAINT_MS);
    if (r.timeout || r.unreachable) throw unreachable('stability', r);
    if (!r.ok) {
      const j = await readJson(r);
      throw failure('stability', r.status, j && `${j.name || ''} ${(j.errors || []).join(' ')}`);
    }
    if (r.headers.get('finish-reason') === 'CONTENT_FILTERED') throw failure('stability', 403, 'CONTENT_FILTERED');
    return picture('stability', Buffer.from(await r.arrayBuffer()));
  },

  async firefly(cred, prompt) {
    const token = await fireflyToken(cred);
    const headers = { authorization: `Bearer ${token}`, 'x-api-key': cred.clientId };
    const r = await call(`${URLS.firefly()}/v3/images/generate-async`, {
      method: 'POST',
      headers: { ...headers, 'content-type': 'application/json', 'x-model-version': 'image4_standard' },
      body: JSON.stringify({ prompt, numVariations: 1, size: { width: 2688, height: 1536 } }),
    });
    if (r.timeout || r.unreachable) throw unreachable('firefly', r);
    const job = await readJson(r);
    if (!r.ok || !job || !job.statusUrl) {
      if (r.status === 401 || r.status === 403) tokens.delete(cred.clientId);
      throw failure('firefly', r.ok ? 502 : r.status, job && `${job.error_code || ''} ${job.message || ''}`);
    }
    // Only follow a status link on Adobe's own service.
    if (!job.statusUrl.startsWith(URLS.firefly() + '/')) throw failure('firefly', 502, 'unexpected status link');
    const t0 = Date.now();
    let done = null;
    while (Date.now() - t0 < PAINT_MS) {
      await new Promise((res) => setTimeout(res, env.imageApiBase ? 50 : 2000));
      const s = await call(job.statusUrl, { headers });
      if (s.timeout || s.unreachable) continue;
      const st = await readJson(s);
      if (!s.ok) throw failure('firefly', s.status, st && `${st.error_code || ''} ${st.message || ''}`);
      if (st.status === 'succeeded') { done = st; break; }
      if (st.status === 'failed' || st.status === 'timeout' || st.status === 'cancelled') throw failure('firefly', 400, `${st.error_code || ''} ${st.message || st.status}`);
    }
    if (!done) throw unreachable('firefly', { timeout: true });
    const url = done.result && done.result.outputs && done.result.outputs[0] && done.result.outputs[0].image && done.result.outputs[0].image.url;
    if (!url || !/^https?:\/\//.test(url)) picture('firefly', null);
    const img = await call(url, {}, 60_000);
    if (img.timeout || img.unreachable || !img.ok) throw new HttpError(503, "Couldn't fetch the picture from Adobe. Try again.", 'unavailable');
    const buf = Buffer.from(await img.arrayBuffer());
    if (buf.length > 40 * 1024 * 1024) throw new HttpError(502, 'That picture was too large to keep.', 'empty');
    return picture('firefly', buf);
  },
};

/** One picture for the app, on the preacher's own key for that service. Logs the request against the account. */
export async function paint(userId, provider, prompt) {
  const cred = credentialFor(userId, provider);
  if (!cred) throw new HttpError(402, `Add your ${PROVIDERS[provider].name} key in Account to paint pictures with it.`, 'no_key');
  try {
    const out = await painters[provider](cred, prompt, userId);
    run('INSERT INTO ai_usage (user_id, at, model, key_source, ok) VALUES (?, ?, ?, ?, 1)', userId, nowIso(), PROVIDERS[provider].model, 'image');
    return out;
  } catch (e) {
    run('INSERT INTO ai_usage (user_id, at, model, key_source, ok) VALUES (?, ?, ?, ?, 0)', userId, nowIso(), PROVIDERS[provider].model, 'image');
    if (e instanceof HttpError) throw e;
    console.error('[images] paint failed', provider, e);
    throw new HttpError(503, `Couldn't reach ${PROVIDERS[provider].name}. Try again in a minute.`, 'unavailable');
  }
}
