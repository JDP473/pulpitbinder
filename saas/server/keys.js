// Each preacher's own Anthropic key, encrypted at rest (AES-256-GCM). The encryption key comes from KEY_SECRET, or is
// made once and kept beside the database, so a copy of the database alone doesn't give the keys away.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { env } from './env.js';

let secret = null;
function key() {
  if (secret) return secret;
  let raw = env.keySecret;
  if (!raw) {
    const file = path.join(env.dataDir, 'key-secret');
    if (!fs.existsSync(file)) fs.writeFileSync(file, crypto.randomBytes(32).toString('base64'), { mode: 0o600 });
    raw = fs.readFileSync(file, 'utf8').trim();
  }
  secret = crypto.createHash('sha256').update(raw).digest();
  return secret;
}

export function sealKey(plain) {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv('aes-256-gcm', key(), iv);
  const body = Buffer.concat([c.update(plain, 'utf8'), c.final()]);
  return `v1.${iv.toString('base64')}.${c.getAuthTag().toString('base64')}.${body.toString('base64')}`;
}

export function openKey(sealed) {
  if (!sealed) return null;
  try {
    const [v, iv, tag, body] = sealed.split('.');
    if (v !== 'v1') return null;
    const d = crypto.createDecipheriv('aes-256-gcm', key(), Buffer.from(iv, 'base64'));
    d.setAuthTag(Buffer.from(tag, 'base64'));
    return Buffer.concat([d.update(Buffer.from(body, 'base64')), d.final()]).toString('utf8');
  } catch {
    return null;
  }
}

/** "sk-ant-...wxyz": enough to recognize a key without showing it. */
export const keyHint = (k) => `${k.slice(0, 7)}...${k.slice(-4)}`;
