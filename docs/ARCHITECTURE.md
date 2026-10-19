# Architecture

Everything lives in `pulpit-binder.html`: CSS tokens and styles at the top, the markup for each tab, then one script wrapped in an IIFE. There is no build step.

## Views

| Tab | Section id | Render entry |
|---|---|---|
| Dashboard | `#view-dash` | `renderDash()` gathers every sermon, `drawDash()` draws |
| Build | `#view-build` | `renderBindings()`, `renderMediaPanel()` |
| Edit | `#view-edit` | `renderGutter()`, `renderSuggestions()`, `renderOutline()` |
| Present | `#view-present` | `renderPresent()` |
| Analysis | `#view-analysis` | `renderAnalysis()`, `renderAI()` |

`setView(v)` switches tabs and remembers the tab in the URL hash.

## Sermon record

```
{ id, updatedAt, example,
  meta: { title, text, when, service, place, speaker, wpm, series },
  html,                 // the manuscript (rich text)
  transcript,           // plain text derived from html
  slides: [ ... ],      // rendered PowerPoint models, PDF pages, or made slides
  manual: { sec: slideIndex },   // pinned bindings
  ai,                   // Claude substance analysis
  suggestions, dismissed,
  media: { link, file, preached } }
```

Kept in IndexedDB (`pulpit-binder` / `sermons`) and synced to the account.

## Sync layout (Claude db capability)

- `data/users/<userId>/<sermonId>`: metadata, part counts, and `dash` (a compact summary used by the Dashboard).
- `data/users/<userId>/<sermonId>/parts/<name>.<k>`: chunks of 60,000 characters (`core`, `html`, `preached`, `pdf`, `s<i>` per slide).
- Large binaries go to the assets store and are referenced as `{asset: id}`.
- `data/users/<userId>/_prefs`: settings (default translation, favorites, services with day and time, places preached with a default, and the speaker and pace for new sermons).
- `data/users/<userId>/_dash`: the latest Claude read across all sermons.
- Ids starting with `_` are not sermons and are skipped in the library.

## Manuscript building blocks

- Slide cue: `<div class="pb-slide" data-n data-k>`; `data-k` spans several slides.
- Pause: `<span class="pb-cue">PAUSE</span>`.
- Scripture section: `<div class="pb-scripture" data-ref data-ver data-texts='{"ESV":{"t":tokens,"s":"bg|claude|typed"}}'>`. Tokens: `{{16}}` verse number, `_italic_`, `\n` line, `\n\n` paragraph.

## Binding text to slides

`rebuild()` splits the manuscript into sections, treats cues and pins as fixed points, and aligns the rest with a dynamic-programming match on words between them. `buildSteps()` produces the Present sequence so every slide is shown, including slides with no matching text.

## Slides

- PowerPoint: parsed with JSZip into a model (boxes, images, lines, tables, placeholders inherited from layout and master, theme colors) and drawn as HTML.
- PDF export: rendered page images via pdf.js, for exact appearance.
- Made slides: `made` is quote, scripture, keyverse, statement, points, point, blanks, question, art, or photo, styled from `deckTheme()`.

## Integrations

- Claude (sample): substance analysis, suggestions, auto outline, slide drafts, picture descriptions, Scripture fallback, dashboard read.
- Firecrawl: Bible Gateway print view for Scripture text, parsed by `parseBG()`.
- Canva: `generate-image`, polled with `get-generate-image-job`. Only a preview comes back inline; the full-size link and Canva link are kept on the slide (`hdUrl`, `canva`).

## Dashboard

`dashSummary(rec)` reduces a sermon to word count, references, reading grade, voice counts, and the key analysis fields. Summaries are cached, saved with each sermon's sync metadata, and pulled from `core` and `html` parts for older sermons that lack one.
