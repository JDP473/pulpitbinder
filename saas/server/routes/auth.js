// Signing up and in: email and password, a sign-in link by email, or Google. Adapted from freely.church.
import { Hono } from 'hono';
import { z } from 'zod';
import { getCookie, setCookie, deleteCookie } from 'hono/cookie';
import {
  assertUnderLimit, clearAttempts, clientIp, consumeAuthToken, createAuthToken, createSession, destroySession, hashPassword,
  peekAuthTokenUser, rateLimit, recordAttempt, requireUser, validatePassword, verifyPassword,
} from '../auth.js';
import { one, run, tx } from '../db.js';
import { env, emailEnabled, googleEnabled, stripeEnabled } from '../env.js';
import { exchangeGoogleCode, googleAuthUrl, newGoogleRequest, safeNext } from '../google.js';
import { sendConfirmEmail, sendLoginEmail, sendResetEmail } from '../mailer.js';
import { removeUserFiles } from '../store.js';
import { HttpError, bad, newId, nowIso } from '../util.js';
import { keyFor } from '../ai.js';
import { imageKeyHints } from '../images.js';

export const authRoutes = new Hono();

export const emailSchema = z
  .string()
  .trim()
  .toLowerCase()
  .regex(/^[^\s@]+@[^\s@]+\.[^\s@]+$/, 'Please enter a valid email address.')
  .max(200);

export const features = () => ({ email: emailEnabled(), google: googleEnabled(), support: stripeEnabled(), sharedKey: !!env.sharedAnthropicKey });

/** Who is signed in, and whether Claude is ready for them (their own key, or the shared one). */
export function meResponse(user) {
  if (!user) return { user: null, features: features() };
  const row = one('SELECT anthropic_key_hint, anthropic_key, shared_key, password_hash, google_sub FROM users WHERE id = ?', user.id);
  const k = keyFor(row);
  return {
    user: {
      ...user,
      keyHint: row.anthropic_key ? row.anthropic_key_hint : null,
      sharedKey: !!row.shared_key && !!env.sharedAnthropicKey,
      claude: k ? k.source : null,
      imageKeys: imageKeyHints(user.id),
      hasPassword: !!row.password_hash,
      google: !!row.google_sub,
    },
    features: features(),
  };
}

authRoutes.get('/me', (c) => c.json(meResponse(c.get('user'))));

authRoutes.post('/register', async (c) => {
  rateLimit(`register:${clientIp(c)}`, 10, 15 * 60000);
  const body = z.object({ name: z.string().trim().min(1, 'Please enter your name.').max(120), email: emailSchema, password: z.string() }).parse(await c.req.json());
  validatePassword(body.password);
  if (one('SELECT 1 FROM users WHERE email = ?', body.email)) throw new HttpError(409, 'An account with this email already exists. Please sign in instead.');
  const id = newId();
  run('INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)', id, body.email, body.name, await hashPassword(body.password), nowIso());
  createSession(c, id);
  return c.json({ ok: true });
});

authRoutes.post('/login', async (c) => {
  const body = z.object({ email: emailSchema, password: z.string().max(200) }).parse(await c.req.json());
  // Only failures count: per email and address, so someone guessing elsewhere can't lock the real person out, and
  // a looser per-address bucket slows guessing across many accounts.
  const ip = clientIp(c);
  const ipKey = `login-fail:${ip}`;
  const accountKey = `login-fail:${body.email}:${ip}`;
  assertUnderLimit(ipKey, 50);
  assertUnderLimit(accountKey, 10);
  const user = one('SELECT id, password_hash, disabled FROM users WHERE email = ?', body.email);
  const ok = await verifyPassword(body.password, user?.password_hash);
  if (!user || !ok) {
    recordAttempt(ipKey, 15 * 60000);
    recordAttempt(accountKey, 15 * 60000);
    throw new HttpError(401, user && !user.password_hash ? 'This account signs in with Google or an emailed link. Use one of those, or set a password with "Forgot password".' : 'That email and password do not match.');
  }
  if (user.disabled) throw new HttpError(403, 'This account has been turned off.');
  clearAttempts(accountKey);
  createSession(c, user.id);
  return c.json({ ok: true });
});

// ---------- Sign in with Google ----------

const GOOGLE_COOKIE = 'pb_google';
const googleCookieOpts = { httpOnly: true, secure: env.secureCookies, sameSite: 'Lax', path: '/api/auth/google' };

authRoutes.get('/google', (c) => {
  if (!googleEnabled()) return c.redirect('/login?error=google-off');
  rateLimit(`google:${clientIp(c)}`, 30, 15 * 60000);
  const { state, verifier, challenge } = newGoogleRequest();
  const next = safeNext(c.req.query('next'));
  setCookie(c, GOOGLE_COOKIE, Buffer.from(JSON.stringify({ state, verifier, next })).toString('base64url'), { ...googleCookieOpts, maxAge: 600 });
  return c.redirect(googleAuthUrl(state, challenge));
});

/** Back from Google: the account this Google account used before, else the one with its (verified) email, else a new one. */
authRoutes.get('/google/callback', async (c) => {
  const fail = (why) => {
    console.warn('[google] sign-in failed:', why);
    return c.redirect(`/login?error=${why === 'email not verified' ? 'google-email' : 'google'}`);
  };
  const raw = getCookie(c, GOOGLE_COOKIE);
  deleteCookie(c, GOOGLE_COOKIE, googleCookieOpts);
  if (!googleEnabled()) return c.redirect('/login?error=google-off');
  if (c.req.query('error')) return c.redirect('/login');
  let saved;
  try {
    saved = JSON.parse(Buffer.from(raw ?? '', 'base64url').toString('utf8'));
  } catch {
    return fail('no saved state');
  }
  const code = c.req.query('code');
  if (!code || !saved.state || !saved.verifier || c.req.query('state') !== saved.state) return fail('state mismatch');
  rateLimit(`google-callback:${clientIp(c)}`, 30, 15 * 60000);
  let who;
  try {
    who = await exchangeGoogleCode(code, saved.verifier);
  } catch (e) {
    return fail(e instanceof Error ? e.message : 'exchange failed');
  }
  const now = nowIso();
  const userId = tx(() => {
    const bySub = one('SELECT id FROM users WHERE google_sub = ?', who.sub);
    if (bySub) return bySub.id;
    const byEmail = one('SELECT id FROM users WHERE email = ?', who.email);
    if (byEmail) {
      run('UPDATE users SET google_sub = ? WHERE id = ?', who.sub, byEmail.id);
      return byEmail.id;
    }
    const id = newId();
    run('INSERT INTO users (id, email, name, created_at, email_verified_at, google_sub) VALUES (?, ?, ?, ?, ?, ?)', id, who.email, who.name.slice(0, 120), now, now, who.sub);
    return id;
  });
  if (one('SELECT disabled FROM users WHERE id = ?', userId)?.disabled) return c.redirect('/login?error=disabled');
  run('UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ? AND email = ?', now, userId, who.email);
  createSession(c, userId);
  return c.redirect(safeNext(saved.next));
});

authRoutes.post('/logout', (c) => {
  destroySession(c);
  return c.json({ ok: true });
});

// ---------- Password reset and sign-in links ----------

authRoutes.post('/forgot', async (c) => {
  const body = z.object({ email: emailSchema }).parse(await c.req.json());
  rateLimit(`forgot:${clientIp(c)}`, 10, 15 * 60000);
  if (!emailEnabled()) throw bad('Email is not set up on this server yet.');
  const user = one('SELECT id FROM users WHERE email = ? AND disabled = 0', body.email);
  if (user) {
    const token = createAuthToken(user.id, 'reset', 60);
    await sendResetEmail(body.email, `${env.appUrl}/reset/${token}`).catch((e) => console.error('[mail] reset failed', e));
  }
  return c.json({ ok: true });
});

authRoutes.get('/reset/:token', (c) => c.json({ valid: !!peekAuthTokenUser(c.req.param('token'), 'reset') }));

authRoutes.post('/reset', async (c) => {
  const body = z.object({ token: z.string().max(200), password: z.string() }).parse(await c.req.json());
  validatePassword(body.password);
  const userId = consumeAuthToken(body.token, 'reset');
  if (!userId) throw bad('This reset link is invalid or has expired.');
  // A reset link only goes out by email, so using one also confirms the address.
  run('UPDATE users SET password_hash = ?, email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?', await hashPassword(body.password), nowIso(), userId);
  run('DELETE FROM sessions WHERE user_id = ?', userId);
  createSession(c, userId);
  return c.json({ ok: true });
});

authRoutes.post('/magic', async (c) => {
  const body = z.object({ email: emailSchema }).parse(await c.req.json());
  rateLimit(`magic:${clientIp(c)}`, 10, 15 * 60000);
  if (!emailEnabled()) throw bad('Email sign-in is not available on this server yet.');
  const user = one('SELECT id FROM users WHERE email = ? AND disabled = 0', body.email);
  if (user) {
    const token = createAuthToken(user.id, 'login', 20);
    await sendLoginEmail(body.email, `${env.appUrl}/magic/${token}`).catch((e) => console.error('[mail] sign-in link failed', e));
  }
  return c.json({ ok: true });
});

// Email scanners open links, so opening one doesn't use it up: the page shows who is signing in and posts to sign in.
authRoutes.get('/magic/:token/peek', (c) => {
  const userId = peekAuthTokenUser(c.req.param('token'), 'login');
  const user = userId ? one('SELECT email FROM users WHERE id = ?', userId) : undefined;
  return c.json({ valid: !!user, email: user?.email ?? null });
});

authRoutes.post('/magic/:token', (c) => {
  rateLimit(`magic-use:${clientIp(c)}`, 30, 15 * 60000);
  const userId = consumeAuthToken(c.req.param('token'), 'login');
  if (!userId) throw bad('That sign-in link has expired or was already used. Please ask for a new one.');
  run('UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?', nowIso(), userId);
  createSession(c, userId);
  return c.json({ ok: true });
});

/** Confirming the address: needed before the owner's address counts as the owner. */
authRoutes.post('/confirm', requireUser, async (c) => {
  const user = c.get('user');
  rateLimit(`confirm:${user.id}`, 5, 60 * 60000);
  if (!emailEnabled()) throw bad('Email is not set up on this server yet.');
  const token = createAuthToken(user.id, 'confirm', 30);
  await sendConfirmEmail(user.email, `${env.appUrl}/confirm/${token}`);
  return c.json({ ok: true });
});

authRoutes.post('/confirm/:token', requireUser, (c) => {
  const user = c.get('user');
  const userId = consumeAuthToken(c.req.param('token'), 'confirm');
  if (!userId || userId !== user.id) throw bad('That link has expired, was already used, or belongs to another account.');
  run('UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?', nowIso(), userId);
  return c.json({ ok: true });
});

// ---------- The signed-in account ----------

authRoutes.post('/password', requireUser, async (c) => {
  const user = c.get('user');
  const body = z.object({ currentPassword: z.string().max(200).optional(), newPassword: z.string() }).parse(await c.req.json());
  validatePassword(body.newPassword);
  const row = one('SELECT password_hash FROM users WHERE id = ?', user.id);
  if (row.password_hash && !(await verifyPassword(body.currentPassword ?? '', row.password_hash))) throw bad('Your current password is incorrect.');
  run('UPDATE users SET password_hash = ? WHERE id = ?', await hashPassword(body.newPassword), user.id);
  run('DELETE FROM sessions WHERE user_id = ? AND id != ?', user.id, c.get('sessionId'));
  return c.json({ ok: true });
});

authRoutes.patch('/profile', requireUser, async (c) => {
  const user = c.get('user');
  const body = z.object({ name: z.string().trim().min(1).max(120).optional(), email: emailSchema.optional() }).parse(await c.req.json());
  if (body.email && body.email !== user.email.toLowerCase()) {
    if (one('SELECT 1 FROM users WHERE email = ? AND id != ?', body.email, user.id)) throw bad('That email is already in use.');
    // A new address starts unconfirmed, and links already emailed to the old one stop working.
    run('UPDATE users SET email = ?, email_verified_at = NULL WHERE id = ?', body.email, user.id);
    run('DELETE FROM auth_tokens WHERE user_id = ? AND used_at IS NULL', user.id);
  }
  if (body.name) run('UPDATE users SET name = ? WHERE id = ?', body.name, user.id);
  return c.json({ ok: true });
});

authRoutes.delete('/account', requireUser, async (c) => {
  const user = c.get('user');
  const body = z.object({ password: z.string().max(200).optional(), confirm: z.string().max(200).optional() }).parse(await c.req.json().catch(() => ({})));
  const row = one('SELECT password_hash FROM users WHERE id = ?', user.id);
  if (row.password_hash ? !(await verifyPassword(body.password ?? '', row.password_hash)) : (body.confirm || '').trim().toLowerCase() !== user.email.toLowerCase()) {
    throw bad(row.password_hash ? 'Password is incorrect.' : 'Type your email address to confirm.');
  }
  run('DELETE FROM users WHERE id = ?', user.id);
  removeUserFiles(user.id);
  destroySession(c);
  return c.json({ ok: true });
});
