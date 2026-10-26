// Claude for the app. Each preacher brings an Anthropic API key; the owner can lend the site's own key
// (ANTHROPIC_API_KEY) to the preachers they choose. The app asks for JSON at one of three tiers.
import Anthropic from '@anthropic-ai/sdk';
import { env } from './env.js';
import { openKey } from './keys.js';
import { run } from './db.js';
import { HttpError, nowIso } from './util.js';

export const MODELS = { quick: 'claude-haiku-5-5', default: 'claude-sonnet-5-5', complex: 'claude-opus-5-5' };
const EFFORT = { quick: 'low', default: 'medium', complex: 'high' };

const SYSTEM =
  'You are the assistant inside Pulpit Binder, a sermon workspace for preachers in the churches of Christ. ' +
  'Every request asks for JSON. Reply with that JSON alone: no prose before or after it, and no code fences.';

/** The key a preacher's requests use, and whose it is, or null when they have none. */
export function keyFor(row) {
  const own = openKey(row.anthropic_key);
  if (own) return { key: own, source: 'own' };
  if (row.shared_key && env.sharedAnthropicKey) return { key: env.sharedAnthropicKey, source: 'shared' };
  return null;
}

const clients = new Map();
function client(key) {
  let c = clients.get(key);
  if (!c) {
    c = new Anthropic({ apiKey: key, timeout: 5 * 60_000, maxRetries: 2, ...(env.anthropicBaseUrl && { baseURL: env.anthropicBaseUrl }) });
    if (clients.size > 200) clients.clear();
    clients.set(key, c);
  }
  return c;
}

/** The JSON in Claude's reply: the whole text, or the outermost object or array inside it. */
export function parseJsonReply(text) {
  const t = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  try {
    return JSON.parse(t);
  } catch {}
  const starts = [t.indexOf('{'), t.indexOf('[')].filter((i) => i >= 0);
  if (!starts.length) throw new HttpError(502, "Claude's answer wasn't in the expected form. Try again.", 'parse');
  const start = Math.min(...starts);
  const end = Math.max(t.lastIndexOf('}'), t.lastIndexOf(']'));
  try {
    return JSON.parse(t.slice(start, end + 1));
  } catch {
    throw new HttpError(502, "Claude's answer wasn't in the expected form. Try again.", 'parse');
  }
}

/** One request from the app: a prompt that asks for JSON, at a tier. Logs the tokens used against the account. */
export async function askClaude(user, { prompt, tier }) {
  const k = keyFor(user);
  if (!k) throw new HttpError(402, 'Add your Anthropic API key in Account to use Claude here.', 'no_key');
  const model = MODELS[tier] || MODELS.default;
  const params = {
    model,
    max_tokens: 16000,
    output_config: { effort: EFFORT[tier] || EFFORT.default },
    system: SYSTEM,
    messages: [{ role: 'user', content: prompt }],
  };
  // When a safety check declines a request, the API runs it again on a model suited to it (not offered on Haiku).
  if (model !== MODELS.quick) Object.assign(params, { betas: ['server-side-fallback-2026-07-01'], fallbacks: 'default' });
  let res;
  try {
    res = await client(k.key).beta.messages.create(params);
  } catch (e) {
    run('INSERT INTO ai_usage (user_id, at, model, key_source, ok) VALUES (?, ?, ?, ?, 0)', user.id, nowIso(), model, k.source);
    if (e instanceof Anthropic.AuthenticationError || e instanceof Anthropic.PermissionDeniedError) {
      throw new HttpError(400, k.source === 'own' ? 'Your Anthropic key was not accepted. Check it in Account.' : 'The shared key was not accepted. Let the site owner know.', 'bad_key');
    }
    if (e instanceof Anthropic.RateLimitError) throw new HttpError(429, 'Too many requests right now. Try again in a minute.', 'rate_limited');
    if (e instanceof Anthropic.BadRequestError) {
      console.warn('[ai] bad request', e.message);
      const credit = /credit|billing|balance/i.test(e.message);
      throw new HttpError(400, credit ? 'Your Anthropic account is out of credit. Add credit in the Anthropic Console.' : "Claude couldn't take that request.", credit ? 'no_credit' : 'bad_request');
    }
    if (e instanceof Anthropic.APIError) {
      console.warn('[ai] api error', e.status, e.message);
      throw new HttpError(503, 'Claude is busy right now. Try again in a minute.', 'busy');
    }
    console.error('[ai] request failed', e);
    throw new HttpError(503, "Couldn't reach Claude. Try again in a minute.", 'unavailable');
  }
  const u = res.usage || {};
  run(
    'INSERT INTO ai_usage (user_id, at, model, key_source, input_tokens, output_tokens, ok) VALUES (?, ?, ?, ?, ?, ?, ?)',
    user.id,
    nowIso(),
    res.model || model,
    k.source,
    (u.input_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0),
    u.output_tokens || 0,
    res.stop_reason === 'refusal' ? 0 : 1,
  );
  if (res.stop_reason === 'refusal') throw new HttpError(422, "Claude declined that request. Try different wording.", 'refused');
  const text = res.content.filter((b) => b.type === 'text').map((b) => b.text).join('');
  if (!text.trim()) throw new HttpError(502, res.stop_reason === 'max_tokens' ? 'That answer ran too long. Try a smaller request.' : "Claude didn't return an answer. Try again.", 'empty');
  return parseJsonReply(text);
}

/** Checks a key before it's saved: a tiny request on the quickest model. */
export async function testKey(key) {
  try {
    await client(key).models.retrieve(MODELS.quick);
    return null;
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError || e instanceof Anthropic.PermissionDeniedError) return 'Anthropic did not accept that key. Copy it again from the Anthropic Console.';
    if (e instanceof Anthropic.APIError) return null; // a busy or rate-limited moment isn't the key's fault
    return null;
  }
}
