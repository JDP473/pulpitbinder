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
- `data/users/<userId>/_cache/ai/<fingerprint>`: saved Claude answers, one per exact request (see Claude answers below).
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

## Claude answers

Every request to Claude goes through `askJson`, which fingerprints the exact prompt and tier. The answer is kept in the `kv` store in IndexedDB (key `ai-<fingerprint>`, newest 500 kept) and in the account under `_cache/ai`, so the same request on another device is answered without spending usage. Changing the manuscript or passage changes the prompt, so a stale answer is never shown. When a saved answer is used, the next press of the same button asks fresh (`refresh`), and the platform cache is set to 24 hours. Test: `tests/browser/cache.py`.

## Markdown

The manuscript is stored as sanitized HTML (`S.html`) but reads and writes Markdown. `mdToHtml` and `htmlToMd` are the two directions; they round-trip, which `tests/browser/md.py` checks with awkward text (literal `*`, `#`, `1.`, brackets, nested marks).

| Markdown | Manuscript |
|---|---|
| `#` to `####` | Headings 1 to 4 (more `#` are Heading 4) |
| `>` | Quotation |
| `-`, `*`, `+`, `1.` | Bulleted and numbered lists |
| `**x**`, `*x*`, `++x++` | Bold, italic, underline |
| `==x==`, `=={green}x==` | Highlights (yellow, or green, blue, pink) |
| `[slide]`, `[slide 3]`, `[slides 3-5]`, `[pause]` | Slide cues and pause cues |
| `::: scripture John 3:16 ESV #id` ... `:::` | A Scripture section; the id keeps its other loaded translations |
| `\` or two spaces at a line end | Hard line break |

A file may begin with a `---` details block (`title`, `text`, `date`, `service`, `place`, `speaker`, `tags`, `pace`). When a file is opened, `detectDetails` also reads labeled lines (`Date: ...`, `- **Where:** ...`) and short header lines that hold only a date, time, service, place, "by" name, or Scripture reference, and `applyDetails` puts what it found into the sermon. A service not named in the file is inferred from the date and time against the service days and times in Settings. Header lines that held nothing else leave the manuscript; undo restores the details too. A file this app exported (with a "Manuscript with slide cues" section) imports as just the manuscript, with its details.

The Markdown view (`#btn-md`) shows the details block and the manuscript as text. Edits apply as you type, and Scripture directives reuse the existing block by id, else by reference.
