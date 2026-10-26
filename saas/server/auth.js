// Accounts and sessions, adapted from freely.church: scrypt passwords, a session cookie holding a random token (its
// sha256 is what the database keeps), one-time tokens for password resets and sign-in links, and a small rate limiter.
import crypto from 'node:crypto';
import { promisify } from 'node:util';
import { getCookie, setCookie, deleteCookie } from 'hono/cookie';
import { env } from './env.js';
import { one, run } from './db.js';
import { HttpError, nowIso, randomToken, sha256 } from './util.js';

const scrypt = promisify(crypto.scrypt);
const SCRYPT = { N: 16384, r: 8, p: 1 };

export async function hashPassword(password) {
  const salt = crypto.randomBytes(16);
  const hash = await scrypt(password, salt, 64, { ...SCRYPT, maxmem: 64 * 1024 * 1024 });
  return `scrypt$${SCRYPT.N}$${SCRYPT.r}$${SCRYPT.p}$${salt.toString('base64')}$${hash.toString('base64')}`;
}

export async function verifyPassword(password, stored) {
  if (!stored) {
    // Same work either way, so a missing account takes as long as a wrong password.
    await scrypt(password, Buffer.alloc(16), 64, { ...SCRYPT, maxmem: 64 * 1024 * 1024 });
    return false;
  }
  const [algo, N, r, p, saltB64, hashB64] = stored.split('$');
  if (algo !== 'scrypt' || !saltB64 || !hashB64) return false;
  const expected = Buffer.from(hashB64, 'base64');
  const actual = await scrypt(password, Buffer.from(saltB64, 'base64'), expected.length, { N: Number(N), r: Number(r), p: Number(p), maxmem: 64 * 1024 * 1024 });
  return actual.length === expected.length && crypto.timingSafeEqual(actual, expected);
}

export function validatePassword(pw) {
  if (typeof pw !== 'string' || pw.length < 8) throw new HttpError(400, 'Your password needs at least 8 characters.');
  if (pw.length > 200) throw new HttpError(400, 'That password is too long.');
  return pw;
}

const COOKIE = 'pb_session';
const cookieOpts = (expires) => ({ httpOnly: true, secure: env.secureCookies, sameSite: 'Lax', path: '/', expires });

/** The owner (PLATFORM_OWNER_EMAIL) counts only once the account has shown it reads that inbox: anyone can sign up with any address. */
export const isOwner = (u) => !!env.ownerEmail && u.email.toLowerCase() === env.ownerEmail && !!u.email_verified_at;

export function toUser(row) {
  return {
    id: row.id,
    email: row.email,
    name: row.name,
    emailVerified: !!row.email_verified_at,
    isOwner: isOwner(row),
    ownerNeedsConfirmation: !!env.ownerEmail && row.email.toLowerCase() === env.ownerEmail && !row.email_verified_at,
  };
}

export function createSession(c, userId) {
  const token = randomToken(32);
  const now = new Date();
  const expires = new Date(now.getTime() + env.sessionDays * 86400000);
  run(
    'INSERT INTO sessions (id, user_id, created_at, expires_at, last_seen_at, user_agent) VALUES (?, ?, ?, ?, ?, ?)',
    sha256(token), userId, now.toISOString(), expires.toISOString(), now.toISOString(), (c.req.header('user-agent') || '').slice(0, 300),
  );
  run('UPDATE users SET last_login_at = ? WHERE id = ?', now.toISOString(), userId);
  setCookie(c, COOKIE, token, cookieOpts(expires));
}

export function destroySession(c) {
  const token = getCookie(c, COOKIE);
  if (token) run('DELETE FROM sessions WHERE id = ?', sha256(token));
  deleteCookie(c, COOKIE, { path: '/' });
}

/** Resolve the session cookie into c.var.user (or null). */
export async function sessionMiddleware(c, next) {
  c.set('user', null);
  c.set('sessionId', null);
  const token = getCookie(c, COOKIE);
  if (token) {
    const sid = sha256(token);
    const row = one(
      `SELECT u.*, s.expires_at AS s_expires, s.last_seen_at AS s_seen FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?`,
      sid,
    );
    if (row && row.s_expires > nowIso() && !row.disabled) {
      c.set('user', toUser(row));
      c.set('sessionId', sid);
      // Sliding expiry, refreshed at most once a day.
      if (Date.now() - (row.s_seen ? Date.parse(row.s_seen) : 0) > 86400000) {
        const expires = new Date(Date.now() + env.sessionDays * 86400000);
        run('UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE id = ?', nowIso(), expires.toISOString(), sid);
        setCookie(c, COOKIE, token, cookieOpts(expires));
      }
    } else if (row) {
      run('DELETE FROM sessions WHERE id = ?', sid);
    }
  }
  await next();
}

export function hasLiveSession(c) {
  const token = getCookie(c, COOKIE);
  if (!token) return false;
  const row = one('SELECT s.expires_at, u.disabled FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?', sha256(token));
  return !!row && row.expires_at > nowIso() && !row.disabled;
}

export async function requireUser(c, next) {
  if (!c.get('user')) throw new HttpError(401, 'Please sign in.', 'signed_out');
  await next();
}

export async function requireOwner(c, next) {
  if (!c.get('user')?.isOwner) throw new HttpError(403, 'Only the site owner can open this page.');
  await next();
}

// ---------- One-time tokens (password reset, sign-in links, owner confirmation) ----------

export function createAuthToken(userId, kind, minutes) {
  const token = randomToken(32);
  run('INSERT INTO auth_tokens (id, user_id, kind, created_at, expires_at) VALUES (?, ?, ?, ?, ?)', sha256(token), userId, kind, nowIso(), new Date(Date.now() + minutes * 60000).toISOString());
  return token;
}

export function peekAuthTokenUser(token, kind) {
  const row = one('SELECT user_id, expires_at, used_at FROM auth_tokens WHERE id = ? AND kind = ?', sha256(token), kind);
  return row && !row.used_at && row.expires_at >= nowIso() ? row.user_id : null;
}

export function consumeAuthToken(token, kind) {
  const row = one('SELECT id, user_id, expires_at, used_at FROM auth_tokens WHERE id = ? AND kind = ?', sha256(token), kind);
  if (!row || row.used_at || row.expires_at < nowIso()) return null;
  run('UPDATE auth_tokens SET used_at = ? WHERE id = ?', nowIso(), row.id);
  return row.user_id;
}

// ---------- In-memory rate limiter ----------

const buckets = new Map();
const tooMany = () => new HttpError(429, 'Too many attempts. Please wait a few minutes and try again.', 'rate_limited');

export function recordAttempt(key, windowMs) {
  const now = Date.now();
  const b = buckets.get(key);
  if (!b || b.reset < now) {
    buckets.set(key, { count: 1, reset: now + windowMs });
    return 1;
  }
  return ++b.count;
}

export function assertUnderLimit(key, limit) {
  const b = buckets.get(key);
  if (b && b.reset >= Date.now() && b.count >= limit) throw tooMany();
}

export const clearAttempts = (key) => buckets.delete(key);

export function rateLimit(key, limit, windowMs) {
  if (recordAttempt(key, windowMs) > limit) throw tooMany();
}

setInterval(() => {
  const now = Date.now();
  for (const [k, b] of buckets) if (b.reset < now) buckets.delete(k);
  run('DELETE FROM sessions WHERE expires_at < ?', nowIso());
  run('DELETE FROM auth_tokens WHERE expires_at < ?', new Date(Date.now() - 86400000).toISOString());
}, 10 * 60000).unref();

export function clientIp(c) {
  return c.req.header('cf-connecting-ip') || c.req.header('x-forwarded-for')?.split(',')[0]?.trim() || c.req.header('x-real-ip') || 'local';
}
