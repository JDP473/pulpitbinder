// Each preacher's synced documents and files. The app addresses documents by path, as it does on Claude
// (data/users/<user id>/<sermon>, .../parts/html.0, _prefs, _cache/ai/<key>); a preacher reaches only their own.
import fs from 'node:fs';
import path from 'node:path';
import { all, one, run, tx } from './db.js';
import { env } from './env.js';
import { HttpError, newId, nowIso } from './util.js';

const MAX_DOC = 1_500_000;
export const MAX_ASSET = 25 * 1048576;

/** A path inside this preacher's own space, split into segments; anything else is refused. */
export function ownPath(userId, p) {
  if (typeof p !== 'string' || p.length > 700) throw new HttpError(400, 'Bad path');
  const segs = p.split('/');
  if (segs.length < 4 || segs[0] !== 'data' || segs[1] !== 'users' || segs[2] !== userId) throw new HttpError(403, 'That is not your data.', 'forbidden');
  if (segs.some((s) => !s || s === '.' || s === '..' || s.length > 300)) throw new HttpError(400, 'Bad path');
  return segs;
}

const parentOf = (p) => p.slice(0, p.lastIndexOf('/'));

// Listeners per preacher (the change feed), told the newest seq after every write.
const listeners = new Map();
export function listen(userId, fn) {
  let set = listeners.get(userId);
  if (!set) listeners.set(userId, (set = new Set()));
  set.add(fn);
  return () => {
    set.delete(fn);
    if (!set.size) listeners.delete(userId);
  };
}
const notify = (userId, seq) => listeners.get(userId)?.forEach((fn) => fn(seq));

const nextSeq = (userId) => (one('SELECT MAX(seq) AS m FROM docs WHERE user_id = ?', userId)?.m || 0) + 1;
export const currentSeq = (userId) => one('SELECT MAX(seq) AS m FROM docs WHERE user_id = ?', userId)?.m || 0;

export function getDoc(userId, p) {
  ownPath(userId, p);
  const row = one('SELECT data FROM docs WHERE user_id = ? AND path = ?', userId, p);
  return row && row.data != null ? JSON.parse(row.data) : null;
}

export function setDoc(userId, p, data) {
  ownPath(userId, p);
  if (data == null || typeof data !== 'object' || Array.isArray(data)) throw new HttpError(400, 'A document is an object.');
  const json = JSON.stringify(data);
  if (json.length > MAX_DOC) throw new HttpError(413, 'That document is too large.', 'quota_or_state');
  const seq = tx(() => {
    const s = nextSeq(userId);
    run(
      `INSERT INTO docs (user_id, path, parent, data, seq, updated_at) VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(user_id, path) DO UPDATE SET data = excluded.data, seq = excluded.seq, updated_at = excluded.updated_at`,
      userId, p, parentOf(p), json, s, nowIso(),
    );
    return s;
  });
  notify(userId, seq);
  return seq;
}

export function deleteDoc(userId, p) {
  ownPath(userId, p);
  const seq = tx(() => {
    if (!one('SELECT 1 FROM docs WHERE user_id = ? AND path = ? AND data IS NOT NULL', userId, p)) return 0;
    const s = nextSeq(userId);
    run('UPDATE docs SET data = NULL, seq = ?, updated_at = ? WHERE user_id = ? AND path = ?', s, nowIso(), userId, p);
    return s;
  });
  if (seq) notify(userId, seq);
  return seq;
}

/** The documents directly in a collection, optionally ordered by one field and limited. */
export function listDocs(userId, collection, { orderBy, dir, limit } = {}) {
  if (typeof collection !== 'string') throw new HttpError(400, 'Bad path');
  ownPath(userId, collection + '/x');
  const field = orderBy && /^[A-Za-z0-9_]{1,40}$/.test(orderBy) ? orderBy : null;
  const order = field ? `ORDER BY json_extract(data, '$.${field}') ${dir === 'desc' ? 'DESC' : 'ASC'}` : 'ORDER BY path';
  const n = Math.min(Math.max(Number(limit) || 5000, 1), 5000);
  const rows = all(`SELECT path, data FROM docs WHERE user_id = ? AND parent = ? AND data IS NOT NULL ${order} LIMIT ?`, userId, collection, n);
  return rows.map((r) => ({ id: r.path.slice(collection.length + 1), data: JSON.parse(r.data) }));
}

/** What changed after `since` in the given collections, oldest first (deletes have data null). */
export function changesSince(userId, since, parents, limit = 500) {
  const list = (Array.isArray(parents) ? parents : [parents]).filter((p) => typeof p === 'string').slice(0, 20);
  for (const p of list) ownPath(userId, p + '/x');
  if (!list.length) return { changes: [], more: false };
  const rows = all(
    `SELECT path, parent, data, seq FROM docs WHERE user_id = ? AND seq > ? AND parent IN (${list.map(() => '?').join(', ')}) ORDER BY seq LIMIT ?`,
    userId, Number(since) || 0, ...list, limit + 1,
  );
  const more = rows.length > limit;
  return {
    changes: rows.slice(0, limit).map((r) => ({ path: r.path, parent: r.parent, data: r.data == null ? null : JSON.parse(r.data), seq: r.seq })),
    more,
    // With more to come, the next page starts after the last change here; otherwise the reader is up to date.
    seq: more ? rows[limit - 1].seq : currentSeq(userId),
  };
}

// ---------- Files ----------

const assetDir = (userId) => path.join(env.dataDir, 'assets', userId);
const assetFile = (userId, id) => path.join(assetDir(userId), id);

export const storageUsed = (userId) => one('SELECT COALESCE(SUM(size), 0) AS n FROM assets WHERE user_id = ?', userId).n;

export function saveAsset(userId, buf, type) {
  if (!buf.length) throw new HttpError(400, 'That file is empty.');
  if (buf.length > MAX_ASSET) throw new HttpError(413, 'That file is larger than 25 MB.', 'quota_or_state');
  if (storageUsed(userId) + buf.length > env.storageMb * 1048576) throw new HttpError(413, 'Your file storage is full.', 'quota_or_state');
  const id = newId().replace(/-/g, '');
  fs.mkdirSync(assetDir(userId), { recursive: true });
  fs.writeFileSync(assetFile(userId, id), buf);
  const safeType = /^[\w.+-]+\/[\w.+-]+$/.test(type || '') ? type : 'application/octet-stream';
  run('INSERT INTO assets (id, user_id, type, size, created_at) VALUES (?, ?, ?, ?, ?)', id, userId, safeType, buf.length, nowIso());
  return id;
}

export function findAsset(userId, id) {
  if (!/^[0-9a-f]{32}$/.test(id)) return null;
  const row = one('SELECT id, type, size FROM assets WHERE id = ? AND user_id = ?', id, userId);
  if (!row) return null;
  const file = assetFile(userId, id);
  return fs.existsSync(file) ? { ...row, file } : null;
}

/** Removes everything a preacher kept here (their account is being deleted). */
export function removeUserFiles(userId) {
  fs.rmSync(assetDir(userId), { recursive: true, force: true });
}

/** Deleted documents are remembered for 60 days, long enough for every device to hear about them. */
export function pruneTombstones() {
  run('DELETE FROM docs WHERE data IS NULL AND updated_at < ?', new Date(Date.now() - 60 * 86400000).toISOString());
}
