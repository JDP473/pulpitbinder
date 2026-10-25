// Giving through Stripe, adapted from freely.church. The Stripe account can be the same one freely.church uses: every
// object made here is tagged { pulpit: 'support' }, and each site handles only its own.
import Stripe from 'stripe';
import { all, one, run } from './db.js';
import { env, emailEnabled, stripeLive } from './env.js';
import { sendSupportThanksEmail } from './mailer.js';
import { HttpError, formatMoney, nowIso } from './util.js';

/** Pinned, so a change to the account's default API version can't change what the code below receives. */
export const STRIPE_API_VERSION = '2026-09-30.endive';
/** Tags the Checkout Sessions this site creates, to tell them apart in the Stripe Dashboard. */
export const INTEGRATION_ID = 'pulpit-support';
/** Marks the Stripe objects that are support for Pulpit Binder, so anything else on the same account is left alone. */
const TAG = { pulpit: 'support' };
const ours = (metadata) => metadata?.pulpit === TAG.pulpit;

let client = null;

export function stripe() {
  if (!client) {
    const api = env.stripe.apiUrl ? new URL(env.stripe.apiUrl) : null;
    client = new Stripe(env.stripe.secretKey, {
      apiVersion: STRIPE_API_VERSION,
      appInfo: { name: 'Pulpit Binder', url: 'https://sermon.freely.church' },
      // Retried requests reuse their idempotency key, so a retry never creates a second Checkout Session.
      maxNetworkRetries: 2,
      timeout: 20_000,
      ...(api && { protocol: api.protocol === 'http:' ? 'http' : 'https', host: api.hostname, port: api.port || (api.protocol === 'http:' ? 80 : 443) }),
    });
  }
  return client;
}

const idOf = (v) => (typeof v === 'string' ? v : (v?.id ?? null));
const iso = (seconds) => (seconds ? new Date(seconds * 1000).toISOString() : null);
const liveFlag = () => (stripeLive() ? 1 : 0);

/** A Stripe failure as something to show the visitor, with the details (a missing key permission, say) in the log. */
export function stripeFailure(e, what) {
  if (e instanceof HttpError) return e;
  if (e instanceof Stripe.errors.StripeError) console.error(`[stripe] ${what} failed: ${e.type}${e.code ? ` (${e.code})` : ''}: ${e.message}`);
  else console.error(`[stripe] ${what} failed`, e);
  return new HttpError(502, "We couldn't reach our payment processor. Please try again in a few minutes.");
}

// ---- Checkout ----

/** One product holds every gift and monthly amount; created on first use and remembered per mode (sandbox or live). */
async function supportProduct() {
  const key = `stripe-product:${stripeLive() ? 'live' : 'test'}`;
  const saved = one('SELECT value FROM app_values WHERE key = ?', key)?.value;
  if (saved) return saved;
  const product = await stripe().products.create({
    name: 'Support Pulpit Binder',
    description: 'Keeps Pulpit Binder running at no cost to preachers.',
    metadata: TAG,
  });
  run('INSERT OR REPLACE INTO app_values (key, value) VALUES (?, ?)', key, product.id);
  return product.id;
}

/** Starts Stripe Checkout for a one-time gift or monthly support and returns its address. */
export async function createSupportCheckout(opts) {
  const page = `${env.appUrl}/support`;
  const create = (product) =>
    stripe().checkout.sessions.create({
      mode: opts.monthly ? 'subscription' : 'payment',
      line_items: [
        {
          quantity: 1,
          price_data: { currency: 'usd', unit_amount: opts.amount, product, ...(opts.monthly && { recurring: { interval: 'month' } }) },
        },
      ],
      success_url: `${page}/thanks?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: page,
      // Set here, never by the visitor: ties the gift to the signed-in account for the platform dashboard.
      client_reference_id: opts.userId ?? undefined,
      metadata: TAG,
      integration_identifier: INTEGRATION_ID,
      custom_text: { submit: { message: 'Thank you for helping keep Pulpit Binder free for every preacher.' } },
      ...(opts.monthly
        ? { subscription_data: { description: 'Monthly support for Pulpit Binder', metadata: TAG } }
        : { customer_creation: 'always', payment_intent_data: { description: 'Gift to Pulpit Binder', metadata: TAG } }),
    });
  let session;
  try {
    session = await create(await supportProduct());
  } catch (e) {
    // The remembered product is from other keys (another sandbox or account): make a new one.
    if (!(e instanceof Stripe.errors.StripeInvalidRequestError && e.code === 'resource_missing' && e.param?.includes('product'))) throw e;
    run("DELETE FROM app_values WHERE key LIKE 'stripe-product:%'");
    session = await create(await supportProduct());
  }
  if (!session.url) throw new Error('Checkout Session has no url');
  return session.url;
}

/** What the thank-you page shows. Null for sessions that aren't support for freely.church. */
export async function supportSessionStatus(id) {
  const s = await stripe().checkout.sessions.retrieve(id);
  if (!ours(s.metadata)) return null;
  return {
    monthly: s.mode === 'subscription',
    complete: s.status === 'complete',
    // Bank debits finish days later; cards are paid at once.
    paid: s.payment_status !== 'unpaid',
    amount: s.amount_total ?? 0,
    currency: s.currency ?? 'usd',
  };
}

/** A Stripe customer portal visit, where people change their monthly amount, card, or cancel. */
export async function portalUrl(customerId, returnUrl) {
  const session = await stripe().billingPortal.sessions.create({ customer: customerId, return_url: returnUrl });
  return session.url;
}

/** Monthly support set up from this email address (current mode only), newest first. */
export function subscriptionsFor(email) {
  return all(
    `SELECT s.id, s.customer_id, s.status, s.amount, s.currency, s.cancel_at_period_end, s.current_period_end, s.created_at
     FROM support_subscriptions s JOIN support_customers c ON c.id = s.customer_id
     WHERE c.email = ? AND s.livemode = ? AND s.status NOT IN ('incomplete', 'incomplete_expired')
     ORDER BY s.created_at DESC`,
    email,
    liveFlag(),
  );
}

/** Support customers that are this account (`u`): it gave while signed in, or from its confirmed email address. */
const GIVEN_BY = '(c.user_id = u.id OR (u.email_verified_at IS NOT NULL AND c.email = u.email))';

/** Monthly support given from this account (current mode only), newest first. */
export function subscriptionsForUser(userId) {
  return all(
    `SELECT DISTINCT s.id, s.customer_id, s.status, s.amount, s.currency, s.cancel_at_period_end, s.current_period_end, s.created_at
     FROM users u JOIN support_customers c ON ${GIVEN_BY} JOIN support_subscriptions s ON s.customer_id = c.id
     WHERE u.id = ? AND s.livemode = ? AND s.status NOT IN ('incomplete', 'incomplete_expired')
     ORDER BY s.created_at DESC`,
    userId,
    liveFlag(),
  );
}

/** Monthly support that's still going: paying, or a payment being retried. */
const SUPPORTING = "('active', 'trialing', 'past_due')";

/** Accounts (of `ids`) that give monthly, from their account or their confirmed email address. */
export function supportingUsers(ids) {
  if (!ids.length || !env.stripe.secretKey) return new Set();
  const rows = all(
    `SELECT DISTINCT u.id FROM users u JOIN support_customers c ON ${GIVEN_BY} JOIN support_subscriptions s ON s.customer_id = c.id
     WHERE u.id IN (${ids.map(() => '?').join(', ')}) AND s.livemode = ? AND s.status IN ${SUPPORTING}`,
    ...ids,
    liveFlag(),
  );
  return new Set(rows.map((r) => r.id));
}

// ---- Webhooks ----

/** Checks the signature and handles the event. Throws on a bad signature. */
export function verifyStripeEvent(payload, signature) {
  return stripe().webhooks.constructEvent(payload, signature, env.stripe.webhookSecret);
}

/** Handles each event once (Stripe can deliver one more than once). A failure lets Stripe retry it. */
export async function handleStripeEvent(event) {
  const fresh = run('INSERT OR IGNORE INTO stripe_events (id, type, received_at) VALUES (?, ?, ?)', event.id, event.type, nowIso()).changes > 0;
  if (!fresh) return;
  try {
    await dispatch(event);
  } catch (e) {
    run('DELETE FROM stripe_events WHERE id = ?', event.id);
    throw e;
  }
}

async function dispatch(event) {
  switch (event.type) {
    case 'checkout.session.completed':
    case 'checkout.session.async_payment_succeeded':
    case 'checkout.session.async_payment_failed':
      return checkoutSession(event.data.object, event.type === 'checkout.session.async_payment_failed');
    case 'customer.subscription.created':
    case 'customer.subscription.updated':
    case 'customer.subscription.deleted':
    case 'customer.subscription.paused':
    case 'customer.subscription.resumed':
      if (ours(event.data.object.metadata)) await syncSubscription(event.data.object.id);
      return;
    case 'invoice.paid':
      return invoicePaid(event.data.object);
    case 'invoice.payment_failed': {
      const inv = event.data.object;
      // Stripe retries the card and emails the supporter (Dashboard → Billing → Revenue recovery).
      if (ours(inv.parent?.subscription_details?.metadata)) console.warn(`[stripe] a monthly support payment failed (${inv.id}); Stripe will retry it`);
      return;
    }
    case 'charge.refunded': {
      const ch = event.data.object;
      const pi = idOf(ch.payment_intent);
      if (pi) {
        run(
          "UPDATE support_payments SET status = ?, amount_refunded = ?, updated_at = ? WHERE payment_intent_id = ? AND status != 'disputed'",
          ch.refunded ? 'refunded' : 'partially_refunded',
          ch.amount_refunded,
          nowIso(),
          pi,
        );
      }
      return;
    }
    case 'charge.dispute.created': {
      const d = event.data.object;
      const pi = idOf(d.payment_intent);
      const hit = pi ? run("UPDATE support_payments SET status = 'disputed', updated_at = ? WHERE payment_intent_id = ?", nowIso(), pi).changes : 0;
      if (hit) console.warn(`[stripe] a support payment was disputed (${d.id}, ${d.reason}); respond in the Stripe Dashboard by ${iso(d.evidence_details?.due_by) ?? 'the deadline shown there'}`);
      return;
    }
    case 'radar.early_fraud_warning.created': {
      const pi = idOf(event.data.object.payment_intent);
      if (pi && one('SELECT 1 FROM support_payments WHERE payment_intent_id = ?', pi)) {
        console.warn(`[stripe] early fraud warning on support payment ${pi}: refunding it in the Stripe Dashboard avoids a dispute fee`);
      }
      return;
    }
    default:
      return;
  }
}

function saveCustomer(id, livemode, email, name, userId) {
  const user = userId && one('SELECT 1 FROM users WHERE id = ?', userId) ? userId : null;
  const now = nowIso();
  run(
    `INSERT INTO support_customers (id, livemode, email, name, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET email = COALESCE(excluded.email, email), name = COALESCE(excluded.name, name),
       user_id = COALESCE(excluded.user_id, user_id), updated_at = excluded.updated_at`,
    id,
    livemode ? 1 : 0,
    email?.toLowerCase() ?? null,
    name,
    user,
    now,
    now,
  );
}

async function checkoutSession(s, failed) {
  if (!ours(s.metadata)) return;
  const customerId = idOf(s.customer);
  const email = s.customer_details?.email ?? null;
  const name = s.customer_details?.name ?? null;
  if (customerId) saveCustomer(customerId, s.livemode, email, name, s.client_reference_id);
  if (s.mode === 'subscription') {
    // The payments themselves arrive as invoice.paid.
    const sub = idOf(s.subscription);
    if (sub) await syncSubscription(sub);
    return;
  }
  if (s.mode !== 'payment') return;

  const status = failed ? 'failed' : s.payment_status === 'paid' ? 'paid' : 'pending';
  const before = one('SELECT status FROM support_payments WHERE id = ?', s.id);
  const now = nowIso();
  if (!before) {
    run(
      `INSERT INTO support_payments (id, kind, livemode, customer_id, payment_intent_id, amount, currency, status, email, name, created_at, updated_at)
       VALUES (?, 'once', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      s.id,
      s.livemode ? 1 : 0,
      customerId,
      idOf(s.payment_intent),
      s.amount_total ?? 0,
      s.currency ?? 'usd',
      status,
      email,
      name,
      iso(s.created) ?? now,
      now,
    );
  } else if (before.status === 'pending' && status !== 'pending') {
    // Only a pending bank payment moves on (events can arrive out of order; refunds and disputes are newer news).
    run('UPDATE support_payments SET status = ?, updated_at = ? WHERE id = ?', status, now, s.id);
  } else {
    return;
  }
  if (status === 'paid') thank(email, name, s.amount_total ?? 0, s.currency ?? 'usd', false);
}

async function syncSubscription(id) {
  // Events can arrive out of order, so record the subscription as Stripe has it now rather than as the event had it.
  const sub = await stripe().subscriptions.retrieve(id);
  if (!ours(sub.metadata)) return;
  const item = sub.items.data[0];
  const customerId = idOf(sub.customer);
  const now = nowIso();
  run(
    'INSERT OR IGNORE INTO support_customers (id, livemode, created_at, updated_at) VALUES (?, ?, ?, ?)',
    customerId,
    sub.livemode ? 1 : 0,
    now,
    now,
  );
  run(
    `INSERT INTO support_subscriptions (id, customer_id, livemode, status, amount, currency, cancel_at_period_end, current_period_end, ended_at, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET status = excluded.status, amount = excluded.amount, currency = excluded.currency,
       cancel_at_period_end = excluded.cancel_at_period_end, current_period_end = excluded.current_period_end,
       ended_at = excluded.ended_at, updated_at = excluded.updated_at`,
    sub.id,
    customerId,
    sub.livemode ? 1 : 0,
    sub.status,
    (item?.price.unit_amount ?? 0) * (item?.quantity ?? 1),
    sub.currency,
    sub.cancel_at_period_end || sub.cancel_at ? 1 : 0,
    iso(item?.current_period_end),
    iso(sub.ended_at),
    iso(sub.created) ?? now,
    now,
  );
}

async function invoicePaid(inv) {
  const details = inv.parent?.subscription_details;
  if (!ours(details?.metadata) || !inv.amount_paid || !inv.id) return;
  if (one('SELECT 1 FROM support_payments WHERE id = ?', inv.id)) return;
  // Kept so a later refund or dispute (which name the payment, not the invoice) finds this row.
  const payments = await stripe().invoicePayments.list({ invoice: inv.id, status: 'paid', limit: 1 });
  const customerId = idOf(inv.customer);
  const now = nowIso();
  if (customerId) saveCustomer(customerId, inv.livemode, inv.customer_email, inv.customer_name, null);
  run(
    `INSERT OR IGNORE INTO support_payments (id, kind, livemode, customer_id, subscription_id, payment_intent_id, amount, currency, status, email, name, created_at, updated_at)
     VALUES (?, 'monthly', ?, ?, ?, ?, ?, ?, 'paid', ?, ?, ?, ?)`,
    inv.id,
    inv.livemode ? 1 : 0,
    customerId,
    idOf(details?.subscription),
    idOf(payments.data[0]?.payment.payment_intent),
    inv.amount_paid,
    inv.currency,
    inv.customer_email,
    inv.customer_name,
    iso(inv.status_transitions?.paid_at) ?? iso(inv.created) ?? now,
    now,
  );
  if (inv.billing_reason === 'subscription_create') thank(inv.customer_email, inv.customer_name, inv.amount_paid, inv.currency, true);
}

/** A thank-you note from us (Stripe sends the receipt, when receipts are switched on in its settings). */
function thank(email, name, amount, currency, monthly) {
  if (!email || !emailEnabled()) return;
  sendSupportThanksEmail(email, { name, amount: formatMoney(amount, currency), monthly }).catch((e) => console.error('[mail] support thank-you failed', e));
}
