import Database from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';
import { env } from './env.js';

fs.mkdirSync(env.dataDir, { recursive: true });

export const db = new Database(path.join(env.dataDir, 'pulpit.db'));
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('foreign_keys = ON');
db.pragma('busy_timeout = 5000');

const MIGRATIONS = [
  // 1: accounts, sign-in, each preacher's synced documents and files, Claude usage, and giving through Stripe.
  `
  CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL DEFAULT '',
    password_hash TEXT,
    google_sub TEXT UNIQUE,
    email_verified_at TEXT,
    anthropic_key TEXT,
    anthropic_key_hint TEXT,
    shared_key INTEGER NOT NULL DEFAULT 0,
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login_at TEXT
  );
  CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    user_agent TEXT
  );
  CREATE INDEX sessions_user ON sessions(user_id);
  CREATE TABLE auth_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
  );

  -- The app's documents, by path (data/users/<user id>/...). A delete leaves a row with data NULL, so other devices
  -- hear about it; seq orders every change for the change feed.
  CREATE TABLE docs (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    parent TEXT NOT NULL,
    data TEXT,
    seq INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, path)
  );
  CREATE INDEX docs_parent ON docs(user_id, parent);
  CREATE INDEX docs_seq ON docs(user_id, seq);
  CREATE TABLE assets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
  );
  CREATE INDEX assets_user ON assets(user_id);
  CREATE TABLE ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    model TEXT NOT NULL,
    key_source TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 1
  );
  CREATE INDEX ai_usage_user ON ai_usage(user_id, at);

  CREATE TABLE support_customers (
    id TEXT PRIMARY KEY,
    livemode INTEGER NOT NULL,
    email TEXT COLLATE NOCASE,
    name TEXT,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
  CREATE INDEX support_customers_email ON support_customers(email);
  CREATE TABLE support_subscriptions (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    livemode INTEGER NOT NULL,
    status TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
    current_period_end TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
  CREATE INDEX support_subscriptions_customer ON support_subscriptions(customer_id);
  CREATE TABLE support_payments (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    livemode INTEGER NOT NULL,
    customer_id TEXT,
    subscription_id TEXT,
    payment_intent_id TEXT,
    amount INTEGER NOT NULL,
    amount_refunded INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    email TEXT,
    name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
  CREATE INDEX support_payments_created ON support_payments(created_at);
  CREATE INDEX support_payments_intent ON support_payments(payment_intent_id);
  CREATE TABLE support_links (
    token_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE,
    livemode INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
  );
  CREATE TABLE stripe_events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    received_at TEXT NOT NULL
  );
  CREATE TABLE app_values (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );
  `,
  // 2: sermons shared by email. The recipient gets their own copy when they add it; until then it waits here.
  `
  CREATE TABLE shares (
    id TEXT PRIMARY KEY,
    from_user TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sermon_id TEXT NOT NULL,
    title TEXT NOT NULL,
    to_email TEXT NOT NULL COLLATE NOCASE,
    note TEXT,
    created_at TEXT NOT NULL,
    accepted_at TEXT,
    accepted_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    copy_id TEXT,
    declined_at TEXT,
    token_hash TEXT UNIQUE
  );
  CREATE INDEX shares_to ON shares(to_email);
  CREATE INDEX shares_from ON shares(from_user);
  `,
  // 3: each preacher's own keys for picture services (OpenAI, Google, Stability AI, Adobe Firefly), encrypted.
  `
  CREATE TABLE image_keys (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    sealed TEXT NOT NULL,
    hint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, provider)
  );
  `,
];

export function migrate() {
  db.exec('CREATE TABLE IF NOT EXISTS _migrations (id INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)');
  const done = new Set(db.prepare('SELECT id FROM _migrations').all().map((r) => r.id));
  MIGRATIONS.forEach((sql, i) => {
    const id = i + 1;
    if (done.has(id)) return;
    db.transaction(() => {
      db.exec(sql);
      db.prepare('INSERT INTO _migrations (id, applied_at) VALUES (?, ?)').run(id, new Date().toISOString());
    })();
    console.log(`[db] applied migration ${id}`);
  });
}

export const one = (sql, ...params) => db.prepare(sql).get(...params);
export const all = (sql, ...params) => db.prepare(sql).all(...params);
export const run = (sql, ...params) => db.prepare(sql).run(...params);
export const tx = (fn) => db.transaction(fn)();
