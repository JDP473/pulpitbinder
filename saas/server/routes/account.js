// The preacher's own settings: their Anthropic key, their picture service keys, and what Claude, pictures, and storage
// they have used.
import { Hono } from 'hono';
import { z } from 'zod';
import { requireUser, rateLimit } from '../auth.js';
import { all, one, run } from '../db.js';
import { env } from '../env.js';
import { keyHint, sealKey } from '../keys.js';
import { testKey } from '../ai.js';
import { PROVIDERS, readCredential, removeImageKey, saveImageKey, testImageKey } from '../images.js';
import { storageUsed } from '../store.js';
import { bad } from '../util.js';

export const accountRoutes = new Hono();
accountRoutes.use('*', requireUser);

accountRoutes.put('/key', async (c) => {
  const user = c.get('user');
  rateLimit(`key:${user.id}`, 10, 60 * 60000);
  const { key } = z.object({ key: z.string().trim().min(20).max(300) }).parse(await c.req.json());
  if (!/^sk-ant-[\w-]+$/.test(key)) throw bad('That does not look like an Anthropic API key. It starts with sk-ant-.');
  const problem = await testKey(key);
  if (problem) throw bad(problem);
  run('UPDATE users SET anthropic_key = ?, anthropic_key_hint = ? WHERE id = ?', sealKey(key), keyHint(key), user.id);
  return c.json({ ok: true, keyHint: keyHint(key) });
});

accountRoutes.delete('/key', (c) => {
  run('UPDATE users SET anthropic_key = NULL, anthropic_key_hint = NULL WHERE id = ?', c.get('user').id);
  return c.json({ ok: true });
});

/** A key for a picture service: tried with the service first, then kept encrypted. */
accountRoutes.put('/image-key/:provider', async (c) => {
  const user = c.get('user');
  const provider = c.req.param('provider');
  if (!PROVIDERS[provider]) throw bad('That picture service is not offered here.');
  rateLimit(`imgkey:${user.id}`, 20, 60 * 60000);
  const r = readCredential(provider, (await c.req.json()) || {});
  if (r.error) throw bad(r.error);
  const problem = await testImageKey(provider, r.cred);
  if (problem) throw bad(problem);
  saveImageKey(user.id, provider, r.cred, r.hint);
  return c.json({ ok: true, hint: r.hint });
});

accountRoutes.delete('/image-key/:provider', (c) => {
  removeImageKey(c.get('user').id, c.req.param('provider'));
  return c.json({ ok: true });
});

/** Claude requests and pictures over the last 30 days by model and key, and the files kept here. */
accountRoutes.get('/usage', (c) => {
  const user = c.get('user');
  const since = new Date(Date.now() - 30 * 86400000).toISOString();
  const rows = all(
    `SELECT model, key_source AS source, COUNT(*) AS requests, SUM(input_tokens) AS input, SUM(output_tokens) AS output
     FROM ai_usage WHERE user_id = ? AND at > ? GROUP BY model, key_source ORDER BY requests DESC`,
    user.id,
    since,
  );
  const claude = rows.filter((r) => r.source !== 'image');
  const pictures = rows.filter((r) => r.source === 'image').map((r) => ({ model: r.model, requests: r.requests }));
  const sermons = one("SELECT COUNT(*) AS n FROM docs WHERE user_id = ? AND parent = ? AND data IS NOT NULL AND path NOT LIKE '%/\\_%' ESCAPE '\\'", user.id, `data/users/${user.id}`).n;
  return c.json({ claude, pictures, storage: { used: storageUsed(user.id), limit: env.storageMb * 1048576 }, sermons });
});
