import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { Hono } from 'hono';
import { compress } from 'hono/compress';
import { bodyLimit } from 'hono/body-limit';
import { secureHeaders } from 'hono/secure-headers';
import { ZodError } from 'zod';
import { hasLiveSession, sessionMiddleware } from './auth.js';
import { env, stripeEnabled } from './env.js';
import { one } from './db.js';
import { HttpError } from './util.js';
import { authRoutes, meResponse } from './routes/auth.js';
import { accountRoutes } from './routes/account.js';
import { adminRoutes } from './routes/admin.js';
import { blobRoute, dataRoutes } from './routes/data.js';
import { stripeWebhook, supportRoutes } from './routes/support.js';
import { keyFor } from './ai.js';

// The site's own pages: scripts from this site only.
const SITE_CSP = {
  defaultSrc: ["'self'"],
  scriptSrc: ["'self'", 'https://static.cloudflareinsights.com'],
  styleSrc: ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
  fontSrc: ["'self'", 'https://fonts.gstatic.com'],
  imgSrc: ["'self'", 'data:'],
  connectSrc: ["'self'", 'https://cloudflareinsights.com'],
  objectSrc: ["'none'"],
  frameAncestors: ["'none'"],
  baseUri: ["'self'"],
  formAction: ["'self'"],
};

// Pulpit Binder itself is one file with its script inline, and loads JSZip and pdf.js from cdnjs, as on Claude.
const APP_CSP = {
  ...SITE_CSP,
  scriptSrc: ["'self'", "'unsafe-inline'", 'https://cdnjs.cloudflare.com', 'https://static.cloudflareinsights.com'],
  imgSrc: ["'self'", 'data:', 'blob:'],
  mediaSrc: ["'self'", 'data:', 'blob:'],
  connectSrc: ["'self'", 'data:', 'blob:', 'https://cdnjs.cloudflare.com', 'https://cloudflareinsights.com'],
  workerSrc: ["'self'", 'blob:', 'https://cdnjs.cloudflare.com'],
  frameSrc: ["'self'", 'https:'],
};

const esc = (s) => String(s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
/** JSON safe to put inside a <script> element. */
const scriptJson = (v) => JSON.stringify(v).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');

export function createApp() {
  const app = new Hono();

  // ---- API ----
  const api = new Hono();
  api.use('*', secureHeaders({ crossOriginResourcePolicy: 'same-origin', contentSecurityPolicy: { defaultSrc: ["'none'"], frameAncestors: ["'none'"] } }));
  api.use('*', async (c, next) => (c.req.path === '/api/db/events' ? next() : compress()(c, next)));
  api.use('*', sessionMiddleware);

  // CSRF defence: state-changing requests must come from our own pages (Stripe's webhook is signed instead).
  api.use('*', async (c, next) => {
    const method = c.req.method;
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS' && c.req.path !== '/api/stripe/webhook') {
      const site = c.req.header('sec-fetch-site');
      if (site && site !== 'same-origin' && site !== 'none') throw new HttpError(403, 'Cross-site request blocked.');
      const origin = c.req.header('origin');
      if (origin) {
        const host = c.req.header('x-forwarded-host') || c.req.header('host');
        let ok = false;
        try {
          ok = new URL(origin).host === host || origin === env.appUrl;
        } catch {}
        if (!ok) throw new HttpError(403, 'Cross-site request blocked.');
      }
    }
    await next();
  });

  const MB = 1024 * 1024;
  api.use('*', bodyLimit({ maxSize: 26 * MB, onError: (c) => c.json({ error: 'That upload is too large.', code: 'quota_or_state' }, 413) }));

  api.get('/health', (c) => c.json({ ok: true }));
  api.route('/auth', authRoutes);
  api.route('/account', accountRoutes);
  api.route('/admin', adminRoutes);
  api.route('/support', supportRoutes);
  api.post('/stripe/webhook', stripeWebhook);
  api.route('/', dataRoutes);
  api.all('*', (c) => c.json({ error: 'Not found' }, 404));
  app.route('/api', api);

  app.onError((err, c) => {
    if (err instanceof HttpError) return c.json(err.code ? { error: err.message, code: err.code } : { error: err.message }, err.status);
    if (err instanceof ZodError) {
      const first = err.issues[0];
      const msg = first?.message && !/^Invalid input/.test(first.message) ? first.message : 'Please check what you entered.';
      return c.json({ error: msg }, 400);
    }
    if (err instanceof SyntaxError) return c.json({ error: 'Malformed request.' }, 400);
    console.error('[error]', c.req.method, c.req.path, err);
    return c.json({ error: 'Something went wrong. Please try again.' }, 500);
  });

  // ---- Files kept by the app ----
  app.get('/_blob/:id', sessionMiddleware, blobRoute);

  // ---- Pages ----
  // Scripts and styles are linked with their content's hash (/shim.js?v=...), so a deploy reaches every browser at
  // once even though Cloudflare tells browsers to keep them for hours.
  const versions = new Map();
  const version = (f) => {
    if (!versions.has(f) || !env.isProd) versions.set(f, crypto.createHash('sha256').update(fs.readFileSync(path.join(env.webDir, f))).digest('hex').slice(0, 12));
    return versions.get(f);
  };
  const stamp = (html) => html.replace(/(src|href)="\/(shim\.js|site\.js|site\.css)"/g, (_, attr, f) => `${attr}="/${f}?v=${version(f)}"`);
  const read = (f) => stamp(fs.readFileSync(path.join(env.webDir, f), 'utf8'));
  const site = (c, html, csp = SITE_CSP) => {
    c.header('Cache-Control', 'no-cache');
    return c.html(html);
  };
  const pages = new Hono();
  pages.use('/app', secureHeaders({ crossOriginEmbedderPolicy: false, contentSecurityPolicy: APP_CSP, referrerPolicy: 'same-origin' }));
  pages.use('*', async (c, next) => (c.req.path === '/app' ? next() : secureHeaders({ crossOriginEmbedderPolicy: false, contentSecurityPolicy: SITE_CSP })(c, next)));
  pages.use('*', sessionMiddleware);

  const landing = () => read('landing.html').replaceAll('__APP_URL__', esc(env.appUrl));
  const withAuth = (html, c) => html.replace('<html lang="en"', `<html lang="en" data-auth="${c.get('user') ? 'in' : 'out'}" data-support="${stripeEnabled() ? 'yes' : 'no'}"`);

  pages.get('/', (c) => site(c, withAuth(landing(), c)));
  pages.get('/about', (c) => c.redirect('/', 301));

  // Pulpit Binder, signed in. The shim (shim.js) gives it the platform it expects on Claude, backed by this server.
  let appHtml = null;
  pages.get('/app', (c) => {
    const user = c.get('user');
    if (!user) return c.redirect('/login?next=/app');
    if (!appHtml || !env.isProd) appHtml = fs.readFileSync(env.appFile, 'utf8');
    const row = one('SELECT anthropic_key, shared_key FROM users WHERE id = ?', user.id);
    const boot = { id: user.id, name: user.name, email: user.email, claude: keyFor(row)?.source ?? null, owner: user.isOwner };
    const head = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><meta name="robots" content="noindex">
<style>body{margin:0}[hidden]{display:none!important}</style>
<script>window.__PB__=${scriptJson(boot)};</script><script src="/shim.js?v=${version('shim.js')}"></script>
</head><body>
`;
    c.header('Cache-Control', 'no-store');
    return c.html(head + appHtml + '\n</body></html>');
  });

  // Account pages share one small page (site.html), which shows the right form for the address.
  const SITE_PAGES = ['/login', '/register', '/forgot', '/reset/:token', '/magic/:token', '/confirm/:token', '/account', '/admin', '/support', '/support/thanks', '/support/manage', '/support/manage/:token'];
  for (const p of SITE_PAGES) pages.get(p, (c) => site(c, withAuth(read('site.html'), c)));

  const STATIC = { '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.txt': 'text/plain; charset=utf-8', '.ico': 'image/x-icon' };
  pages.get('/:file{[a-z0-9][a-z0-9._-]*\\.(js|css|svg|png|webp|txt|ico)}', (c) => {
    const file = path.join(env.webDir, c.req.param('file'));
    if (!fs.existsSync(file) || path.basename(file) === 'site.html') return c.text('Not found', 404);
    c.header('Content-Type', STATIC[path.extname(file)]);
    // A stamped link is that exact content forever; an unstamped one is checked each time.
    c.header('Cache-Control', c.req.query('v') ? 'public, max-age=31536000, immutable' : 'no-cache');
    return c.body(fs.readFileSync(file));
  });
  pages.get('/shots/:file{[a-z0-9_-]+\\.(png|webp)}', (c) => {
    const file = path.join(env.webDir, 'shots', c.req.param('file'));
    if (!fs.existsSync(file)) return c.text('Not found', 404);
    c.header('Content-Type', STATIC[path.extname(file)]);
    c.header('Cache-Control', 'public, max-age=86400');
    return c.body(fs.readFileSync(file));
  });
  pages.get('*', (c) => {
    c.status(404);
    return site(c, withAuth(read('site.html'), c));
  });
  app.route('/', pages);
  return app;
}

export { hasLiveSession, meResponse };
