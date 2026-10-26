// The owner's page: every account, who may use the shared Anthropic key, and how much Claude each has used.
import { Hono } from 'hono';
import { z } from 'zod';
import { requireUser, requireOwner } from '../auth.js';
import { all, one, run } from '../db.js';
import { env } from '../env.js';
import { supportingUsers } from '../stripe.js';
import { MODELS } from '../ai.js';
import { notFound, bad } from '../util.js';

export const adminRoutes = new Hono();
adminRoutes.use('*', requireUser, requireOwner);

// List prices per million tokens (October 2026), for a rough cost beside each account.
const PRICE = { [MODELS.quick]: [0.1, 0.5], [MODELS.default]: [2, 10], [MODELS.complex]: [4, 20] };
const cost = (model, input, output) => {
  const p = PRICE[model] || PRICE[MODELS.default];
  return (input / 1e6) * p[0] + (output / 1e6) * p[1];
};

adminRoutes.get('/users', (c) => {
  const since = new Date(Date.now() - 30 * 86400000).toISOString();
  const users = all(
    `SELECT u.id, u.email, u.name, u.created_at, u.last_login_at, u.shared_key, u.disabled, u.email_verified_at,
       (u.anthropic_key IS NOT NULL) AS own_key,
       (SELECT COUNT(*) FROM docs d WHERE d.user_id = u.id AND d.parent = 'data/users/' || u.id AND d.data IS NOT NULL AND d.path NOT LIKE '%/\\_%' ESCAPE '\\') AS sermons,
       (SELECT COALESCE(SUM(size), 0) FROM assets a WHERE a.user_id = u.id) AS storage
     FROM users u ORDER BY u.created_at DESC`,
  );
  const usage = all(
    `SELECT user_id, model, key_source, COUNT(*) AS requests, SUM(input_tokens) AS input, SUM(output_tokens) AS output
     FROM ai_usage WHERE at > ? GROUP BY user_id, model, key_source`,
    since,
  );
  const givers = supportingUsers(users.map((u) => u.id));
  const out = users.map((u) => {
    const mine = usage.filter((r) => r.user_id === u.id && r.key_source !== 'image');   // Claude only; pictures are on the preacher's own keys
    const shared = mine.filter((r) => r.key_source === 'shared');
    return {
      id: u.id,
      email: u.email,
      name: u.name,
      createdAt: u.created_at,
      lastLoginAt: u.last_login_at,
      verified: !!u.email_verified_at,
      ownKey: !!u.own_key,
      sharedKey: !!u.shared_key,
      disabled: !!u.disabled,
      sermons: u.sermons,
      storage: u.storage,
      supporter: givers.has(u.id),
      requests30: mine.reduce((a, r) => a + r.requests, 0),
      sharedRequests30: shared.reduce((a, r) => a + r.requests, 0),
      sharedCost30: Math.round(shared.reduce((a, r) => a + cost(r.model, r.input, r.output), 0) * 100) / 100,
    };
  });
  const payments = one("SELECT COUNT(*) AS n, COALESCE(SUM(amount - amount_refunded), 0) AS total FROM support_payments WHERE status IN ('paid', 'partially_refunded') AND created_at > ?", since);
  return c.json({ users: out, sharedKeyConfigured: !!env.sharedAnthropicKey, giving30: { payments: payments.n, total: payments.total } });
});

adminRoutes.patch('/users/:id', async (c) => {
  const id = c.req.param('id');
  const body = z.object({ sharedKey: z.boolean().optional(), disabled: z.boolean().optional() }).parse(await c.req.json());
  const target = one('SELECT id, email FROM users WHERE id = ?', id);
  if (!target) throw notFound();
  if (body.disabled && id === c.get('user').id) throw bad("You can't turn off your own account.");
  if (body.sharedKey !== undefined) run('UPDATE users SET shared_key = ? WHERE id = ?', body.sharedKey ? 1 : 0, id);
  if (body.disabled !== undefined) {
    run('UPDATE users SET disabled = ? WHERE id = ?', body.disabled ? 1 : 0, id);
    if (body.disabled) run('DELETE FROM sessions WHERE user_id = ?', id);
  }
  return c.json({ ok: true });
});
