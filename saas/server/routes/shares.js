// Sharing a sermon with another preacher by email. They get their own copy when they add it to their binder.
// Shares are matched by email, so a recipient sees them only once their address is confirmed: anyone can sign up
// with any address.
import { Hono } from 'hono';
import { z } from 'zod';
import { rateLimit, requireUser } from '../auth.js';
import { all, one, run, tx } from '../db.js';
import { env, emailEnabled } from '../env.js';
import { sendShareEmail } from '../mailer.js';
import { copySermon, sermonMeta } from '../store.js';
import { bad, forbidden, newId, notFound, nowIso, randomToken, sha256 } from '../util.js';
import { emailSchema } from './auth.js';

export const shareRoutes = new Hono();
shareRoutes.use('*', requireUser);

const verified = (userId) => !!one('SELECT email_verified_at FROM users WHERE id = ?', userId)?.email_verified_at;

shareRoutes.post('/', async (c) => {
  const user = c.get('user');
  rateLimit(`share:${user.id}`, 30, 60 * 60000);
  const body = z.object({ sermonId: z.string().max(40), email: emailSchema, note: z.string().trim().max(1000).optional() }).parse(await c.req.json());
  if (body.email === user.email.toLowerCase()) throw bad("That's your own address. Share it with someone else.");
  const meta = sermonMeta(user.id, body.sermonId);
  if (!meta) throw bad("This sermon hasn't finished saving yet. Try again in a moment.");
  const title = String(meta.title || meta.meta?.title || 'Untitled sermon').slice(0, 200);
  if (one('SELECT 1 FROM shares WHERE from_user = ? AND sermon_id = ? AND to_email = ? AND accepted_at IS NULL AND declined_at IS NULL', user.id, body.sermonId, body.email)) {
    throw bad(`It's already waiting for ${body.email}.`);
  }
  const id = newId();
  // The emailed link carries a token: opening it signed in with that address shows the person reads that inbox.
  const token = randomToken(24);
  run('INSERT INTO shares (id, from_user, sermon_id, title, to_email, note, created_at, token_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', id, user.id, body.sermonId, title, body.email, body.note || null, nowIso(), sha256(token));
  const hasAccount = !!one('SELECT 1 FROM users WHERE email = ? AND disabled = 0', body.email);
  let emailed = false;
  if (emailEnabled()) {
    const url = `${env.appUrl}/s/${token}`;
    emailed = await sendShareEmail(body.email, { from: user.name || user.email, title, note: body.note, url, hasAccount }).then(() => true, (e) => {
      console.error('[mail] share email failed', e);
      return false;
    });
  }
  return c.json({ ok: true, id, emailed, hasAccount });
});

/** Shares waiting for me (when my address is confirmed), and the ones I sent. */
shareRoutes.get('/', (c) => {
  const user = c.get('user');
  const ok = verified(user.id);
  const waiting = all(
    `SELECT s.id, s.title, s.note, s.created_at, u.name AS from_name, u.email AS from_email FROM shares s JOIN users u ON u.id = s.from_user
     WHERE s.to_email = ? AND s.accepted_at IS NULL AND s.declined_at IS NULL AND s.from_user != ? ORDER BY s.created_at`,
    user.email,
    user.id,
  );
  const sent = all(
    `SELECT id, sermon_id, title, to_email, created_at, accepted_at, declined_at FROM shares WHERE from_user = ? ORDER BY created_at DESC LIMIT 200`,
    user.id,
  );
  return c.json({
    incoming: ok ? waiting.map((s) => ({ id: s.id, title: s.title, note: s.note, from: s.from_name || s.from_email, fromEmail: s.from_email, at: s.created_at })) : [],
    needsConfirm: !ok && waiting.length ? waiting.length : 0,
    sent: sent.map((s) => ({ id: s.id, sermonId: s.sermon_id, title: s.title, to: s.to_email, at: s.created_at, status: s.accepted_at ? 'added' : s.declined_at ? 'declined' : 'waiting' })),
  });
});

const incoming = (user, id) => {
  const s = one('SELECT * FROM shares WHERE id = ?', id);
  if (!s || s.to_email.toLowerCase() !== user.email.toLowerCase()) throw notFound();
  if (!verified(user.id)) throw forbidden('Confirm your email address in Account first.');
  if (s.accepted_at || s.declined_at) throw bad('That share was already answered.');
  return s;
};

shareRoutes.post('/:id/accept', (c) => {
  const user = c.get('user');
  rateLimit(`share-accept:${user.id}`, 60, 60 * 60000);
  const s = incoming(user, c.req.param('id'));
  const copyId = tx(() => {
    const id = copySermon(s.from_user, s.sermon_id, user.id);
    run('UPDATE shares SET accepted_at = ?, accepted_by = ?, copy_id = ? WHERE id = ?', nowIso(), user.id, id, s.id);
    return id;
  });
  return c.json({ ok: true, sermonId: copyId });
});

shareRoutes.post('/:id/decline', (c) => {
  const s = incoming(c.get('user'), c.req.param('id'));
  run('UPDATE shares SET declined_at = ? WHERE id = ?', nowIso(), s.id);
  return c.json({ ok: true });
});

/** The sender takes back a share that hasn't been added yet. */
shareRoutes.delete('/:id', (c) => {
  const user = c.get('user');
  const s = one('SELECT id, accepted_at FROM shares WHERE id = ? AND from_user = ?', c.req.param('id'), user.id);
  if (!s) throw notFound();
  if (s.accepted_at) throw bad('They already added it to their binder, so their copy stays with them.');
  run('DELETE FROM shares WHERE id = ?', s.id);
  return c.json({ ok: true });
});

/**
 * GET /s/:token, the link in a share email. Signed in with the address it was sent to: that address counts as
 * confirmed (the link only went there), and on to the binder where the share waits. Not signed in: sign up or in with
 * that address first. Opening it signed out changes nothing, so mail scanners that follow links do no harm.
 */
export function shareLink(c) {
  const s = one('SELECT to_email FROM shares WHERE token_hash = ?', sha256(c.req.param('token')));
  if (!s) return c.redirect('/app');
  const user = c.get('user');
  const here = encodeURIComponent(c.req.path);
  if (!user) {
    const has = !!one('SELECT 1 FROM users WHERE email = ?', s.to_email);
    return c.redirect(`/${has ? 'login' : 'register'}?email=${encodeURIComponent(s.to_email)}&next=${here}`);
  }
  if (user.email.toLowerCase() !== s.to_email.toLowerCase()) return c.redirect(`/app?share=other`);
  run('UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?', nowIso(), user.id);
  return c.redirect('/app');
}
