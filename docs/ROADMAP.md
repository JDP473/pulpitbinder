# Roadmap

## Now: runs inside Claude

The published page uses Jarred's Claude account for AI, sync, file storage, and Canva. No API billing.

## Next: split platform code from the app

Route every platform call through one module so the rest of the app never touches `window.claude` directly:

- `ai.json(prompt, opts)`
- `store` (list, get, save, delete, watch)
- `files.put(blob)` / `files.url(id)`
- `images.paint(prompt)`
- `bible.passage(ref, version)`

Two implementations: the Claude one (today's behavior) and a server one. The app picks at startup.

## Preparing for a product (started October 2026)

Done in the page so far:
- AI services are a registry (`AI_SERVICES`): each has a kind (writing or pictures) and where it runs (here, or hosted). Every Claude request goes through `askJson`, and every picture through the Illustration and theme painters, so a new provider is one entry and one branch.
- Settings has an AI and images page: how much care Claude takes (mapped to model tiers), and which picture service to use (Canva, Claude drawing, or none). Hosted-only providers are listed so the shape of the product is visible.
- No API keys are stored in the page. The Claude-hosted page cannot reach other AI companies, so keys would only be a liability here. In the hosted version they live on the server, per church, never in the browser.

Still to do before selling it:
- The platform module below, so the app runs on Claude or on its own server unchanged.
- Accounts, churches as tenants, roles (preacher, reader, media volunteer), and billing.
- A key vault on the server, and per-church usage limits and logs for AI calls.
- Licensed Bible text, a contracted image service, and terms and privacy pages.
- An export of everything a church owns, so it is never locked in.
- The local-first Sunday mode (booth helper, iPad present screen) tabled in October 2026; its first test passed on the booth computer.

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

- The full-size export flow (search, place on the kept design, export) was checked by hand against the live Canva connector in a session; from the page it is tested with a mock.
- Firecrawl and Canva calls are built against their documented inputs but have not been observed live from the page in a development session.
