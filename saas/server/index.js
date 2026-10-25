import { serve } from '@hono/node-server';
import { migrate, one } from './db.js';
import { createAuthToken } from './auth.js';
import { createApp } from './app.js';
import { env, emailEnabled, googleEnabled, stripeEnabled, stripeLive } from './env.js';
import { checkMailLogin } from './mailer.js';
import { pruneTombstones } from './store.js';

migrate();

// Account recovery without email: RESET_PASSWORD_FOR=<email> writes a one-time, 24-hour reset link to the log on start.
const resetFor = process.env.RESET_PASSWORD_FOR?.trim().toLowerCase();
if (resetFor) {
  const user = one('SELECT id FROM users WHERE email = ?', resetFor);
  if (user) console.log(`[admin] One-time password reset link for ${resetFor} (valid 24h): ${env.appUrl}/reset/${createAuthToken(user.id, 'reset', 60 * 24)}`);
  else console.log(`[admin] RESET_PASSWORD_FOR: no account found for ${resetFor}`);
}

const app = createApp();
const server = serve({ fetch: app.fetch, port: env.port, hostname: '0.0.0.0' }, (info) => {
  console.log(`[server] Pulpit Binder listening on http://0.0.0.0:${info.port} (public URL ${env.appUrl})`);
  console.log(`[server] data dir ${env.dataDir}; email ${emailEnabled() ? 'on' : 'off'}; Google sign-in ${googleEnabled() ? 'on' : 'off'}; shared Anthropic key ${env.sharedAnthropicKey ? 'set' : 'not set'}`);
  void checkMailLogin();
  if (stripeEnabled()) console.log(`[stripe] giving on (${stripeLive() ? 'live' : 'sandbox'} keys); webhook at ${env.appUrl}/api/stripe/webhook`);
  else if (env.stripe.secretKey || env.stripe.webhookSecret) console.warn('[stripe] giving off: set both STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET');
});

setInterval(() => {
  try {
    pruneTombstones();
  } catch (e) {
    console.error('[cleanup]', e);
  }
}, 6 * 3600_000).unref();

const shutdown = () => {
  server.close();
  process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
