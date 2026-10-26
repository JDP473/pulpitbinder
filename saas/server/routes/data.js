// What the app's shim calls in place of Claude's platform: documents (db), files (assets), and Claude (sample).
import fs from 'node:fs';
import { Hono } from 'hono';
import { streamSSE } from 'hono/streaming';
import { z } from 'zod';
import { rateLimit, requireUser } from '../auth.js';
import { one } from '../db.js';
import { askClaude } from '../ai.js';
import { changesSince, currentSeq, deleteDoc, findAsset, getDoc, listDocs, listen, saveAsset, setDoc, MAX_ASSET } from '../store.js';
import { HttpError, notFound } from '../util.js';

export const dataRoutes = new Hono();
dataRoutes.use('*', requireUser);

dataRoutes.get('/db/doc', (c) => {
  const id = c.get('user').id;
  const seq = currentSeq(id);
  const data = getDoc(id, c.req.query('path'));
  return c.json({ exists: data != null, data, seq });
});

dataRoutes.put('/db/doc', async (c) => {
  const body = await c.req.json();
  return c.json({ seq: setDoc(c.get('user').id, body?.path, body?.data) });
});

dataRoutes.delete('/db/doc', (c) => c.json({ seq: deleteDoc(c.get('user').id, c.req.query('path')) }));

dataRoutes.get('/db/list', (c) => {
  const id = c.get('user').id;
  const seq = currentSeq(id);
  const docs = listDocs(id, c.req.query('collection'), { orderBy: c.req.query('orderBy'), dir: c.req.query('dir'), limit: c.req.query('limit') });
  return c.json({ docs, seq });
});

dataRoutes.get('/db/changes', (c) => {
  return c.json(changesSince(c.get('user').id, c.req.query('since'), c.req.queries('parent') || []));
});

/** Tells an open page when anything of this preacher's changes (the page then asks for the changes). */
dataRoutes.get('/db/events', (c) => {
  const id = c.get('user').id;
  c.header('X-Accel-Buffering', 'no');
  c.header('Cache-Control', 'no-cache, no-transform');
  return streamSSE(c, async (stream) => {
    let wake = null;
    let latest = currentSeq(id);
    const stop = listen(id, (seq) => {
      latest = seq;
      wake?.();
    });
    stream.onAbort(() => {
      stop();
      wake?.();
    });
    await stream.writeSSE({ event: 'seq', data: String(latest) });
    let sent = latest;
    while (!stream.aborted && !stream.closed) {
      await new Promise((r) => {
        wake = r;
        setTimeout(r, 25_000);
      });
      wake = null;
      if (stream.aborted || stream.closed) break;
      if (latest !== sent) {
        sent = latest;
        await stream.writeSSE({ event: 'seq', data: String(latest) });
      } else await stream.writeSSE({ event: 'ping', data: '' });
    }
    stop();
  });
});

dataRoutes.post('/assets', async (c) => {
  const user = c.get('user');
  rateLimit(`asset:${user.id}`, 600, 60 * 60000);
  const len = Number(c.req.header('content-length') || 0);
  if (len > MAX_ASSET) throw new HttpError(413, 'That file is larger than 25 MB.', 'quota_or_state');
  const buf = Buffer.from(await c.req.arrayBuffer());
  return c.json({ id: saveAsset(user.id, buf, c.req.header('content-type')) });
});

dataRoutes.post('/ai', async (c) => {
  const user = c.get('user');
  rateLimit(`ai:${user.id}`, 120, 10 * 60000);
  const body = z.object({ prompt: z.string().min(1).max(400_000), tier: z.enum(['quick', 'default', 'complex']).default('default') }).parse(await c.req.json());
  const row = one('SELECT id, anthropic_key, shared_key FROM users WHERE id = ?', user.id);
  return c.json({ value: await askClaude(row, body) });
});

/** GET /_blob/:id: a preacher's own file, as the app shows pictures and plays recordings (with ranges for seeking). */
export function blobRoute(c) {
  const user = c.get('user');
  if (!user) return c.text('Please sign in.', 401);
  const a = findAsset(user.id, c.req.param('id'));
  if (!a) throw notFound();
  c.header('Content-Type', a.type);
  c.header('Cache-Control', 'private, max-age=31536000, immutable');
  c.header('Accept-Ranges', 'bytes');
  c.header('X-Content-Type-Options', 'nosniff');
  c.header('Content-Security-Policy', "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; sandbox");
  const m = /^bytes=(\d*)-(\d*)$/.exec(c.req.header('range') || '');
  if (m && (m[1] || m[2])) {
    let start = m[1] ? Number(m[1]) : a.size - Number(m[2]);
    let end = m[1] && m[2] ? Math.min(Number(m[2]), a.size - 1) : a.size - 1;
    if (start < 0) start = 0;
    if (start > end || start >= a.size) {
      c.header('Content-Range', `bytes */${a.size}`);
      return c.body(null, 416);
    }
    c.header('Content-Range', `bytes ${start}-${end}/${a.size}`);
    c.header('Content-Length', String(end - start + 1));
    return c.body(fs.readFileSync(a.file).subarray(start, end + 1), 206);
  }
  c.header('Content-Length', String(a.size));
  return c.body(fs.readFileSync(a.file));
}
