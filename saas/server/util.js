import crypto from 'node:crypto';

export const nowIso = () => new Date().toISOString();
export const newId = () => crypto.randomUUID();
export const randomToken = (bytes = 32) => crypto.randomBytes(bytes).toString('base64url');
export const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');

export class HttpError extends Error {
  constructor(status, message, code) {
    super(message);
    this.status = status;
    /** Machine-readable reason, sent as `code` (the app shim reads it). */
    this.code = code;
  }
}

export const bad = (msg) => new HttpError(400, msg);
export const forbidden = (msg = 'You do not have permission to do that.') => new HttpError(403, msg);
export const notFound = (msg = 'Not found') => new HttpError(404, msg);

/** "$25" for whole dollars, "$12.50" otherwise. */
export function formatMoney(cents, currency = 'usd') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency.toUpperCase(),
    minimumFractionDigits: cents % 100 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

export const SUPPORT_MIN = 100;
export const SUPPORT_MAX = 1_000_000;
