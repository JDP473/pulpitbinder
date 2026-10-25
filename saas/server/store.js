// Each preacher's synced documents and files. The app addresses documents by path, as it does on Claude
// (data/users/<user id>/<sermon>, .../parts/html.0, _prefs, _cache/ai/<key>); a preacher reaches only their own.
import crypto from 'node:crypto';
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

// ---------- Copying a sermon to another preacher (sharing) ----------

const CHUNK = 60000; // the app's part size (pulpit-binder.html, CHUNK)
const newSermonId = () => crypto.randomBytes(6).toString('base64url').toLowerCase().replace(/[^a-z0-9]/g, '').padEnd(8, '0').slice(0, 8);

/** The sermon's meta document, or null when it isn't (or is no longer) in this preacher's binder. */
export function sermonMeta(userId, sermonId) {
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(sermonId) || sermonId.startsWith('_')) return null;
  return getDoc(userId, `data/users/${userId}/${sermonId}`);
}

/**
 * Copies a sermon from one preacher's binder into another's, as a new sermon of their own: the meta document, every
 * part (manuscript, slides, PDF pages, recording transcript), and the files those parts name (pictures, slide images),
 * which get new ids in the recipient's storage. Returns the new sermon's id.
 */
export function copySermon(fromUser, sermonId, toUser) {
  const meta = sermonMeta(fromUser, sermonId);
  if (!meta) throw new HttpError(410, 'That sermon is no longer available. Ask them to share it again.', 'gone');
  const base = `data/users/${fromUser}/${sermonId}`;
  const chunks = meta.chunks || {};
  // Each part whole again (an asset id can straddle two chunks), with the files it names copied over.
  const parts = {};
  const assetMap = new Map();
  let bytes = 0;
  for (const [name, n] of Object.entries(chunks)) {
    let str = '';
    for (let k = 0; k < n; k++) str += getDoc(fromUser, `${base}/parts/${name}.${k}`)?.s || '';
    str = str.replace(/"asset":"([0-9a-f]{32})"/g, (m, id) => {
      if (!assetMap.has(id)) {
        const a = findAsset(fromUser, id);
        if (!a) return m;
        assetMap.set(id, { ...a, to: newId().replace(/-/g, '') });
        bytes += a.size;
      }
      return `"asset":"${assetMap.get(id).to}"`;
    });
    parts[name] = str;
  }
  if (storageUsed(toUser) + bytes > env.storageMb * 1048576) throw new HttpError(413, 'Your file storage is too full for this sermon\'s slides and pictures.', 'quota_or_state');
  const id = newSermonId();
  const now = Date.now();
  fs.mkdirSync(assetDir(toUser), { recursive: true });
  for (const a of assetMap.values()) {
    fs.copyFileSync(a.file, assetFile(toUser, a.to));
    run('INSERT INTO assets (id, user_id, type, size, created_at) VALUES (?, ?, ?, ?, ?)', a.to, toUser, a.type, a.size, nowIso());
  }
  const toBase = `data/users/${toUser}/${id}`;
  const newChunks = {};
  for (const [name, str] of Object.entries(parts)) {
    const n = Math.max(1, Math.ceil(str.length / CHUNK));
    for (let k = 0; k < n; k++) setDoc(toUser, `${toBase}/parts/${name}.${k}`, { s: str.slice(k * CHUNK, (k + 1) * CHUNK) });
    newChunks[name] = n;
  }
  // Content hashes are dropped so the recipient's app treats every part as its own; the device is not theirs.
  setDoc(toUser, toBase, { ...meta, id, updatedAt: now, device: 'shared', chunks: newChunks, hashes: {}, fileLocal: false });
  return id;
}
