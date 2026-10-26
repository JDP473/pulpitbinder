# sermon.freely.church

Pulpit Binder for any preacher: a public page, accounts, sync and file storage on this server, Claude on each preacher's own Anthropic key, and giving through Stripe. Like freely.church, it is free to use with the option to give.

The app is the same `pulpit-binder.html` that is published on Claude. The server wraps it in a page with `web/shim.js`, which supplies the `window.claude.use(...)` calls the app makes on Claude (sample, db, user, assets, downloads) from this server instead. Connectors (Canva, Firecrawl, Pulpit Live) are not offered here, and the app's wording changes where it would mention them (`HOSTED` in the page).

## Pages

| Address | What it is |
|---|---|
| `/` | The public page (`web/landing.html`) |
| `/register`, `/login`, `/forgot`, `/reset/:token`, `/magic/:token` | Signing up and in: email and password, an emailed sign-in link, or Google |
| `/app` | Pulpit Binder itself, signed in |
| `/account` | Name and email, the Anthropic key, Claude usage, storage, password, giving, deleting the account |
| `/admin` | The owner only: every preacher, lending the shared key, turning an account off |
| `/support` | Giving once or monthly through Stripe Checkout |

## Sharing a sermon

From the More menu, "Share this sermon…" sends a sermon to another preacher by email, with an optional note. They get an email (an invitation to sign up, if they have no account), and a card in their binder to add it or decline. Adding it gives them their own copy, with the manuscript, Scripture, slides, and the pictures those slides use copied into their storage; later changes stay with each copy. The sender sees who has added it and can cancel a share that is still waiting.

Shares are matched by email address, so a preacher sees one only once their address is confirmed (Google sign-in, an emailed sign-in link, or "Confirm my email"). The link in the share email counts: opening it signed in with that address confirms it.

## Claude

Each preacher pastes an Anthropic API key in Account. It is encrypted at rest (AES-256-GCM, with `KEY_SECRET` or a key made once in `DATA_DIR`). The owner can set `ANTHROPIC_API_KEY` and lend it from `/admin` to the preachers they choose; a preacher's own key is always used first. Every request is logged by model and key, so the admin page shows what the shared key costs.

The app asks at three tiers: quick (Claude Haiku 5.5), default (Claude Sonnet 5.5), and complex (Claude Opus 5.5). Sonnet and Opus requests carry the API's server-side fallback, so a request a safety check declines is retried on a suitable model.

## Settings

The same names as freely.church, so its Google client, mail server, and Stripe account serve both.

| Variable | Needed | What it is |
|---|---|---|
| `APP_URL` | yes | `https://sermon.freely.church` |
| `DATA_DIR` | yes | Where the database and files live (a persistent volume, `/data` in the image) |
| `PLATFORM_OWNER_EMAIL` | yes | The owner; counts once that address is confirmed |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | for Google | Add `https://sermon.freely.church/api/auth/google/callback` to the client's redirect URIs |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM` | for email | Sign-in links, password resets, thank-you notes |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | for giving | The webhook secret is for this site's own endpoint, `https://sermon.freely.church/api/stripe/webhook` |
| `ANTHROPIC_API_KEY` | optional | The key the owner lends |
| `KEY_SECRET` | optional | Encrypts preachers' keys; otherwise one is made in `DATA_DIR` |
| `STORAGE_MB` | optional | File storage per preacher, 2048 by default |
| `RESET_PASSWORD_FOR` | rarely | Writes a one-time reset link for that address to the log on start |

The Stripe webhook should send `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `customer.subscription.*`, `invoice.paid`, `invoice.payment_failed`, `charge.refunded`, and `charge.dispute.created`. Objects made here are tagged `pulpit: support`, so it can share a Stripe account with freely.church without either site touching the other's.

## Running it

```bash
cd saas && npm install
APP_URL=http://localhost:3000 PLATFORM_OWNER_EMAIL=you@example.com npm start
npm test                                  # the server, against a stand-in Anthropic API
python3 ../tests/browser/hosted.py        # the whole site in Chromium
```

The image builds from the repository root: `docker build -f saas/Dockerfile .`
