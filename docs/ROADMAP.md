# Roadmap

## Now: runs inside Claude

The published page uses Jarred's Claude account for AI, sync, file storage, and Canva. No API billing.

## Now also: sermon.freely.church

The same file runs for any preacher on a Node server (`saas/`): accounts with Google, email, and passwords, sync and files on the server, Claude on each preacher's own Anthropic key (or the owner's, lent from the admin page), and giving through Stripe. A shim supplies the platform calls. Bible text there comes from Claude or pasting until a licensed source is added, and Canva and Pulpit Live are not offered.

## Next: split platform code from the app

Route every platform call through one module so the rest of the app never touches `window.claude` directly:

- `ai.json(prompt, opts)`
- `store` (list, get, save, delete, watch)
- `files.put(blob)` / `files.url(id)`
- `images.paint(prompt)`
- `bible.passage(ref, version)`

Two implementations: the Claude one (today's behavior) and a server one. The app picks at startup.

## Later: standalone server version

- Backend in his stack (Laravel and MySQL) deployed on Coolify. Holds the Anthropic API key server-side, adds accounts, and exposes routes for analyze, suggest, outline, slide drafts, and the dashboard read. The prompts move from the page to the server.
- Replace before delivering to others:
  - Bible text through licensed sources (publisher APIs), not Bible Gateway.
  - Images through a contracted image service instead of the personal Canva connection.
  - Speech-to-text for recordings.
  - Accounts per church, and billing.

## Cost notes (October 2026 API prices)

Sonnet 5.5 is about $0.25 per sermon worked through end to end, roughly $1.50 per preacher per month. Opus 5.5 is about double that, and Haiku 5.5 is about a twentieth. Prompt caching (the same manuscript is sent to analyze, suggest, and outline) and the Batch API (half price) lower it further.

## Open items

- Confirm a real Canva job result includes a direct full-size image URL (only tested with a mock).
- Firecrawl and Canva calls are built against their documented inputs but have not been observed live from the page in a development session.
