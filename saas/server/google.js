// Sign in with Google: OpenID Connect's authorization code flow with PKCE, the same as freely.church. Turned on by
// GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET; the redirect URI to add to the Google client is APP_URL/api/auth/google/callback.
import { createHash, randomBytes } from 'node:crypto';
import { env } from './env.js';

export const GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth';
export const GOOGLE_TOKEN_URL = process.env.GOOGLE_TOKEN_URL || 'https://oauth2.googleapis.com/token';
const ISSUERS = new Set(['https://accounts.google.com', 'accounts.google.com']);

export const googleRedirectUri = () => `${env.appUrl}/api/auth/google/callback`;

export function newGoogleRequest() {
  const state = randomBytes(24).toString('base64url');
  const verifier = randomBytes(48).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest().toString('base64url');
  return { state, verifier, challenge };
}

export function googleAuthUrl(state, challenge) {
  const q = new URLSearchParams({
    client_id: env.google.clientId,
    redirect_uri: googleRedirectUri(),
    response_type: 'code',
    scope: 'openid email profile',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
    prompt: 'select_account',
  });
  return `${GOOGLE_AUTH_URL}?${q}`;
}

/**
 * Trade the code for Google's ID token and read who signed in. The token comes straight from Google's token endpoint
 * over TLS, so (as OpenID Connect allows for this flow) its claims are checked rather than its signature.
 */
export async function exchangeGoogleCode(code, verifier, now = Date.now()) {
  const res = await fetch(GOOGLE_TOKEN_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      code_verifier: verifier,
      client_id: env.google.clientId,
      client_secret: env.google.clientSecret,
      redirect_uri: googleRedirectUri(),
      grant_type: 'authorization_code',
    }),
    signal: AbortSignal.timeout(15_000),
  });
  if (!res.ok) throw new Error(`token endpoint ${res.status}`);
  const idToken = (await res.json()).id_token;
  if (typeof idToken !== 'string') throw new Error('no id_token');
  let claims;
  try {
    claims = JSON.parse(Buffer.from(idToken.split('.')[1] ?? '', 'base64url').toString('utf8'));
  } catch {
    throw new Error('unreadable id_token');
  }
  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!ISSUERS.has(String(claims.iss))) throw new Error('wrong issuer');
  if (!aud.includes(env.google.clientId)) throw new Error('wrong audience');
  if (typeof claims.exp !== 'number' || claims.exp * 1000 < now) throw new Error('expired');
  if (typeof claims.sub !== 'string' || !claims.sub) throw new Error('no subject');
  if (typeof claims.email !== 'string' || !claims.email.includes('@')) throw new Error('no email');
  if (claims.email_verified !== true && claims.email_verified !== 'true') throw new Error('email not verified');
  return {
    sub: claims.sub,
    email: claims.email.trim().toLowerCase(),
    name: (typeof claims.name === 'string' && claims.name.trim()) || claims.email.split('@')[0],
  };
}

/** Only a path on this site: anything else (another site, "//evil", a backslash trick) goes to the app. */
export function safeNext(next) {
  return typeof next === 'string' && /^\/(?![/\\])/.test(next) && !next.includes('\\') && next.length <= 500 ? next : '/app';
}
