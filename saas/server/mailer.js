// Email through the same mail server as freely.church (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM).
import nodemailer from 'nodemailer';
import { env, emailEnabled } from './env.js';

const SITE = 'Pulpit Binder';
let transporter = null;

function getTransport() {
  if (!transporter) {
    transporter = nodemailer.createTransport({
      host: env.smtp.host,
      port: env.smtp.port,
      secure: env.smtp.secure,
      auth: env.smtp.user ? { user: env.smtp.user, pass: env.smtp.pass } : undefined,
    });
  }
  return transporter;
}

const esc = (s) => String(s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);

function layout({ heading, body, cta }) {
  const btn = cta
    ? `<p style="margin:28px 0"><a href="${esc(cta.url)}" style="background:#8a5d0b;color:#fff;text-decoration:none;padding:12px 22px;border-radius:10px;font-weight:600;display:inline-block">${esc(cta.label)}</a></p>
       <p style="color:#6b7280;font-size:13px">Or paste this link into your browser:<br><a href="${esc(cta.url)}" style="color:#8a5d0b;word-break:break-all">${esc(cta.url)}</a></p>`
    : '';
  return `<!doctype html><html><body style="margin:0;background:#f3f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1a2130">
  <div style="max-width:560px;margin:0 auto;padding:32px 20px">
    <div style="background:#fff;border-radius:16px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <h1 style="font-size:22px;margin:0 0 16px">${esc(heading)}</h1>
      <div style="font-size:15px;line-height:1.6">${body}</div>
      ${btn}
    </div>
    <p style="text-align:center;color:#9ca3af;font-size:12px;margin-top:20px">${SITE} · sermon.freely.church</p>
  </div></body></html>`;
}

const fromAddress = (from) => (from.match(/<([^>]+)>/) || [null, from])[1];

export async function sendMail(to, subject, html, text) {
  if (!emailEnabled()) throw new Error('Email is not configured on this server.');
  await getTransport().sendMail({ from: `"${SITE}" <${fromAddress(env.smtp.from)}>`, to, subject, html, text });
}

export async function checkMailLogin() {
  if (!emailEnabled()) return;
  try {
    await getTransport().verify();
    console.log(`[mail] SMTP login OK (${env.smtp.host}:${env.smtp.port})`);
  } catch (e) {
    console.error(`[mail] SMTP login FAILED (${env.smtp.host}:${env.smtp.port}): ${e?.message ?? e}`);
  }
}

export async function sendResetEmail(to, url) {
  const html = layout({
    heading: 'Reset your password',
    body: '<p>We received a request to reset your Pulpit Binder password. This link expires in 1 hour. If you did not ask for this, you can ignore this email.</p>',
    cta: { label: 'Choose a new password', url },
  });
  await sendMail(to, 'Reset your Pulpit Binder password', html, `Reset your password: ${url}\n\nThis link expires in 1 hour.`);
}

export async function sendLoginEmail(to, url) {
  const html = layout({
    heading: 'Your sign-in link',
    body: '<p>Tap the button below to sign in to Pulpit Binder. This link expires in 20 minutes and can only be used once.</p>',
    cta: { label: 'Sign in', url },
  });
  await sendMail(to, 'Your Pulpit Binder sign-in link', html, `Sign in: ${url}\n\nThis link expires in 20 minutes.`);
}

export async function sendConfirmEmail(to, url) {
  const html = layout({
    heading: 'Confirm your email address',
    body: "<p>Tap the button to confirm this is your email address. This link expires in 30 minutes and can only be used once.</p><p>If you didn't ask for this, you can ignore this email.</p>",
    cta: { label: 'Confirm my email', url },
  });
  await sendMail(to, 'Confirm your email for Pulpit Binder', html, `Confirm your email address: ${url}\n\nThis link expires in 30 minutes.`);
}

export async function sendSupportThanksEmail(to, { name, amount, monthly }) {
  const first = name?.trim().split(/\s+/)[0];
  const manageUrl = `${env.appUrl}/support/manage`;
  const html = layout({
    heading: 'Thank you',
    body: `<p>${first ? `Hi ${esc(first)},` : 'Hello,'}</p><p>Thank you for ${
      monthly ? `supporting Pulpit Binder with <strong>${esc(amount)} a month</strong>` : `your gift of <strong>${esc(amount)}</strong> to Pulpit Binder`
    }. It pays for the server, storage, and backups, and the time to keep improving it, so any preacher can keep using it at no cost.</p>${
      monthly ? '<p>You can change the amount, update your card, or cancel at any time from the link below, using this email address.</p>' : ''
    }`,
    cta: monthly ? { label: 'Manage monthly support', url: manageUrl } : undefined,
  });
  const text = `Thank you for ${monthly ? `supporting Pulpit Binder with ${amount} a month` : `your gift of ${amount} to Pulpit Binder`}.${
    monthly ? `\n\nChange the amount, update your card, or cancel at any time: ${manageUrl}` : ''
  }\n`;
  await sendMail(to, monthly ? 'Thank you for supporting Pulpit Binder' : 'Thank you for your gift to Pulpit Binder', html, text);
}

export async function sendSupportManageEmail(to, url) {
  const html = layout({
    heading: 'Manage your monthly support',
    body: "<p>Tap the button to see your monthly support for Pulpit Binder, change the amount or card, or cancel. This link works for 60 minutes.</p><p>If you didn't ask for this, you can ignore this email.</p>",
    cta: { label: 'Manage monthly support', url },
  });
  await sendMail(to, 'Manage your monthly support for Pulpit Binder', html, `Manage your monthly support: ${url}\n\nThis link works for 60 minutes.`);
}

export async function sendShareEmail(to, { from, title, note, url, hasAccount }) {
  const html = layout({
    heading: `${from} shared a sermon with you`,
    body: `<p>${esc(from)} shared <strong>${esc(title)}</strong> with you on Pulpit Binder. Add it to your binder to get your own copy, with its manuscript, Scripture, and slides, to read or adapt.</p>${
      note ? `<p style="border-left:3px solid #e6d3ad;padding-left:12px;color:#374151">${esc(note)}</p>` : ''
    }${hasAccount ? '' : '<p>Pulpit Binder is a free sermon workspace for preachers. Sign up with this email address and the sermon will be waiting.</p>'}`,
    cta: { label: hasAccount ? 'Open Pulpit Binder' : 'Sign up and see it', url },
  });
  const text = `${from} shared "${title}" with you on Pulpit Binder.${note ? `\n\n${note}` : ''}\n\n${hasAccount ? 'Open Pulpit Binder' : 'Sign up with this email address to see it'}: ${url}\n`;
  await sendMail(to, `${from} shared "${title}" with you`, html, text);
}
