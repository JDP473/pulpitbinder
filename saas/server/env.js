// Settings from the environment. The names match freely.church's, so the same Google client, mail server, and Stripe
// account serve both sites.
import path from 'node:path';

function bool(v, def) {
  if (v == null || v === '') return def;
  return /^(1|true|yes|on)$/i.test(v);
}

const appUrl = (process.env.APP_URL || 'http://localhost:3000').replace(/\/+$/, '');

export const env = {
  port: Number(process.env.PORT || 3000),
  isProd: process.env.NODE_ENV === 'production',
  dataDir: path.resolve(process.env.DATA_DIR || './data'),
  appUrl,
  /** Secure cookies when the public URL is https. */
  secureCookies: bool(process.env.SECURE_COOKIES, appUrl.startsWith('https://')),
  sessionDays: Number(process.env.SESSION_DAYS || 90),
  /** The site owner: runs the admin page and chooses who may use the shared Anthropic key. */
  ownerEmail: (process.env.PLATFORM_OWNER_EMAIL || '').trim().toLowerCase(),
  smtp: {
    host: process.env.SMTP_HOST || '',
    port: Number(process.env.SMTP_PORT || 587),
    secure: bool(process.env.SMTP_SECURE, Number(process.env.SMTP_PORT) === 465),
    user: process.env.SMTP_USER || '',
    pass: process.env.SMTP_PASS || '',
    from: process.env.MAIL_FROM || process.env.SMTP_FROM || '',
  },
  /** Where the page files live: the site pages (web/) and the app itself (pulpit-binder.html). */
  webDir: path.resolve(process.env.WEB_DIR || new URL('../web', import.meta.url).pathname),
  appFile: path.resolve(process.env.APP_FILE || new URL('../../pulpit-binder.html', import.meta.url).pathname),
  stripe: {
    secretKey: (process.env.STRIPE_SECRET_KEY || '').trim(),
    /** The signing secret of the webhook endpoint at APP_URL/api/stripe/webhook (its own endpoint, not freely.church's). */
    webhookSecret: (process.env.STRIPE_WEBHOOK_SECRET || '').trim(),
    apiUrl: (process.env.STRIPE_API_URL || '').trim(),
  },
  google: {
    clientId: (process.env.GOOGLE_CLIENT_ID || '').trim(),
    clientSecret: (process.env.GOOGLE_CLIENT_SECRET || '').trim(),
  },
  /** The owner's Anthropic key, lent to the preachers the owner picks on the admin page. Optional. */
  sharedAnthropicKey: (process.env.ANTHROPIC_API_KEY || '').trim(),
  /** Send Claude calls somewhere else (tests). Leave unset in production. */
  anthropicBaseUrl: (process.env.ANTHROPIC_BASE_URL || '').trim(),
  /** Encrypts preachers' own Anthropic keys at rest. When unset, a key is made once and kept in DATA_DIR. */
  keySecret: (process.env.KEY_SECRET || '').trim(),
  /** File storage per preacher, in megabytes (slides, pictures, recordings). */
  storageMb: Number(process.env.STORAGE_MB || 2048),
};

export const emailEnabled = () => !!(env.smtp.host && env.smtp.from);
export const googleEnabled = () => !!(env.google.clientId && env.google.clientSecret);
export const stripeEnabled = () => !!(env.stripe.secretKey && env.stripe.webhookSecret);
export const stripeLive = () => /^(sk|rk)_live_/.test(env.stripe.secretKey);
