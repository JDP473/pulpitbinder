// Giving to Pulpit Binder: one-time gifts and monthly support through Stripe Checkout. Adapted from freely.church.
import { Hono } from 'hono';
import { z } from 'zod';
import Stripe from 'stripe';
import { clientIp, rateLimit } from '../auth.js';
import { one, run } from '../db.js';
import { env, emailEnabled, stripeEnabled, stripeLive } from '../env.js';
import { sendSupportManageEmail } from '../mailer.js';
import { createSupportCheckout, handleStripeEvent, portalUrl, stripeFailure, subscriptionsFor, subscriptionsForUser, supportSessionStatus, verifyStripeEvent } from '../stripe.js';
import { HttpError, SUPPORT_MAX, SUPPORT_MIN, bad, notFound, nowIso, randomToken, sha256 } from '../util.js';

const LINK_MINUTES = 60;

export const supportRoutes = new Hono();

const requireStripe = () => {
  if (!stripeEnabled()) throw notFound("Online giving isn't set up yet.");
};

supportRoutes.get('/config', (c) => c.json({ enabled: stripeEnabled(), sandbox: stripeEnabled() && !stripeLive() }));

supportRoutes.post('/checkout', async (c) => {
  requireStripe();
  rateLimit(`support-checkout:${clientIp(c)}`, 20, 60 * 60000);
  const body = z
    .object({
      amount: z.number().int().min(SUPPORT_MIN, 'The smallest gift is $1.').max(SUPPORT_MAX, 'For gifts over $10,000, please get in touch.'),
      frequency: z.enum(['once', 'monthly']),
    })
    .parse(await c.req.json());
  try {
    return c.json({ url: await createSupportCheckout({ amount: body.amount, monthly: body.frequency === 'monthly', userId: c.get('user')?.id ?? null }) });
  } catch (e) {
    throw stripeFailure(e, 'starting Checkout');
  }
});

supportRoutes.get('/session/:id', async (c) => {
  requireStripe();
  const id = c.req.param('id');
  if (!/^cs_(test|live)_[A-Za-z0-9]+$/.test(id)) throw notFound();
  rateLimit(`support-session:${clientIp(c)}`, 60, 60 * 60000);
  let status;
  try {
    status = await supportSessionStatus(id);
  } catch (e) {
    if (e instanceof Stripe.errors.StripeInvalidRequestError && e.code === 'resource_missing') throw notFound();
    throw stripeFailure(e, 'looking up a Checkout Session');
  }
  if (!status) throw notFound();
  return c.json(status);
});

// Changing or cancelling monthly support: a link goes to the address the support was set up with.
supportRoutes.post('/manage', async (c) => {
  requireStripe();
  if (!emailEnabled()) throw bad("Email isn't set up on this server yet, so we can't send the link.");
  const { email } = z.object({ email: z.string().trim().toLowerCase().email('Please enter a valid email address.').max(200) }).parse(await c.req.json());
  rateLimit(`support-manage:${clientIp(c)}`, 10, 60 * 60000);
  rateLimit(`support-manage:${email}`, 3, 60 * 60000);
  // The same answer either way, so nobody can find out who gives.
  if (subscriptionsFor(email).length) {
    const token = randomToken(32);
    const now = new Date();
    run('DELETE FROM support_links WHERE expires_at < ?', now.toISOString());
    run('INSERT INTO support_links (token_hash, email, livemode, created_at, expires_at) VALUES (?, ?, ?, ?, ?)', sha256(token), email, stripeLive() ? 1 : 0, now.toISOString(), new Date(now.getTime() + LINK_MINUTES * 60000).toISOString());
    sendSupportManageEmail(email, `${env.appUrl}/support/manage/${token}`).catch((e) => console.error('[mail] support manage link failed', e));
  }
  return c.json({ ok: true });
});

const toSubscription = (s) => ({
  id: s.id,
  status: s.status,
  amount: s.amount,
  currency: s.currency,
  cancelAtPeriodEnd: !!s.cancel_at_period_end,
  currentPeriodEnd: s.current_period_end,
  createdAt: s.created_at,
});

const signedInUser = (c) => {
  const user = c.get('user');
  if (!user) throw new HttpError(401, 'Please sign in.');
  return user;
};

supportRoutes.get('/mine', (c) => {
  if (!stripeEnabled()) return c.json({ subscriptions: [] });
  return c.json({ subscriptions: subscriptionsForUser(signedInUser(c).id).map(toSubscription) });
});

supportRoutes.post('/mine/portal', async (c) => {
  requireStripe();
  const user = signedInUser(c);
  const { subscriptionId } = z.object({ subscriptionId: z.string().max(100) }).parse(await c.req.json());
  const sub = subscriptionsForUser(user.id).find((s) => s.id === subscriptionId);
  if (!sub) throw notFound();
  try {
    return c.json({ url: await portalUrl(sub.customer_id, `${env.appUrl}/account`) });
  } catch (e) {
    throw stripeFailure(e, 'opening the customer portal');
  }
});

const linkEmail = (token) => one('SELECT email FROM support_links WHERE token_hash = ? AND expires_at > ? AND livemode = ?', sha256(token), nowIso(), stripeLive() ? 1 : 0)?.email ?? null;

supportRoutes.get('/manage/:token', (c) => {
  requireStripe();
  const email = linkEmail(c.req.param('token'));
  if (!email) return c.json({ valid: false });
  return c.json({ valid: true, email, subscriptions: subscriptionsFor(email).map(toSubscription) });
});

supportRoutes.post('/manage/:token/portal', async (c) => {
  requireStripe();
  const token = c.req.param('token');
  const email = linkEmail(token);
  if (!email) throw new HttpError(410, 'This link has expired. Ask for a new one below.');
  const { subscriptionId } = z.object({ subscriptionId: z.string().max(100) }).parse(await c.req.json());
  const sub = subscriptionsFor(email).find((s) => s.id === subscriptionId);
  if (!sub) throw notFound();
  try {
    return c.json({ url: await portalUrl(sub.customer_id, `${env.appUrl}/support/manage/${token}`) });
  } catch (e) {
    throw stripeFailure(e, 'opening the customer portal');
  }
});

/** POST /api/stripe/webhook: Stripe tells us about payments here. Only signed requests are accepted. */
export async function stripeWebhook(c) {
  if (!stripeEnabled()) return c.json({ error: 'Not found' }, 404);
  const signature = c.req.header('stripe-signature');
  if (!signature) return c.json({ error: 'Missing signature' }, 400);
  const payload = Buffer.from(await c.req.arrayBuffer());
  let event;
  try {
    event = verifyStripeEvent(payload, signature);
  } catch {
    console.warn('[stripe] webhook with a bad signature ignored (check STRIPE_WEBHOOK_SECRET matches this endpoint)');
    return c.json({ error: 'Bad signature' }, 400);
  }
  try {
    await handleStripeEvent(event);
  } catch (e) {
    console.error(`[stripe] handling ${event.type} (${event.id}) failed; Stripe will retry`, e);
    return c.json({ error: 'Not handled' }, 500);
  }
  return c.json({ received: true });
}
