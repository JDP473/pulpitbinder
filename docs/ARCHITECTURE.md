# Architecture

Everything lives in `pulpit-binder.html`: CSS tokens and styles at the top, the markup for each tab, then one script wrapped in an IIFE. There is no build step.

## Views

| Tab | Section id | Render entry |
|---|---|---|
| Dashboard | `#view-dash` | `renderDash()` gathers every sermon, `drawDash()` draws |
| Build: Details, Bindings | `#view-build` (`#build-details`, `#build-bind`) | `renderBindings()`, `renderMediaPanel()` |
| Build: Edit manuscript | `#view-edit` | `renderGutter()`, `renderSuggestions()`, `renderOutline()` |
| Present | `#view-present` | `renderPresent()` |
| Analysis | `#view-analysis` | `renderAnalysis()`, `renderAI()` |

`setView(v)` switches views and remembers the place in the URL hash. Build's sections use the `#subtabs` bar and `goBuild(sub)`; the editor is still its own view internally (`edit`), shown under the Build tab.

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
- The sermon document records `hashes` of each part. A push compares against them and writes only parts that changed, so a new session or another device does not resend everything. Slides are sent only when `deckVer` or the slide count differs from the account's copy.
- Each uploaded file is remembered on the device by its SHA-256 (`kv` key `asset-<hash>`), so the same picture is never uploaded twice.
- Writes go a few at a time. A save waits 0.5 s after typing stops, then about 0.6 s more before pushing (at most 4 s during steady typing).
- `data/users/<userId>/_prefs`: settings (default translation, favorites).
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
- Canva: `generate-image`, polled with `get-generate-image-job`. Only a small preview (about 200 pixels wide) comes back inline, plus the picture's Canva media id.
- Scripture formatting: bold, italic, underline, and four highlight colors are applied from a floating toolbar (`#sc-fmt`) over a selection in a Scripture section. They are stored in the section's text as invisible private-use marks (U+E001 to U+E014) around runs of words, never across a verse number or line break (`scPieces`, `scFromPieces`); `scPlainText` strips them. A slide made from a section keeps `sc: {id, a, z}` (section id and first and last verse) and `syncScSlides` rewrites its text whenever the section changes; older slides link themselves by matching their words the first time their section is touched.
- PowerPoint export (`deckPptx`, "Save slides as PowerPoint" in Details): writes the .pptx by hand with JSZip (blank layout, plain theme, notes master). Made slides are the theme background as a picture plus one editable text box; slides read from a .pptx are rebuilt from the parsed model; PDF pages go in as pictures. Notes hold the slide's own notes, then the manuscript paragraphs that bring it up, so Presenter View shows the manuscript. Saved through `downloads` (pptx is on its allowlist). Checked with python-pptx, not yet opened in PowerPoint itself.
- Full-size pictures: the page can't download from Canva, so it places the media on the one 1920 x 1080 page of a design in the viewer's Canva titled "Pulpit Binder full-size pictures" (`read-design` with a transaction, `edit-design` `update_fill` on the page background, then commit) and exports that page with `export-design` as a PNG. The export link is signed and expires within about a day; the viewer opens it, saves the file, and chooses it to swap in. The design is found with `search-designs` (its id cached in `localStorage` as `pb-canva-holder`) or made once with `create-design` and `get-create-design-async-job`. Exports run one at a time because they share that page. Slides and themes keep `media`, `hdUrl`, and `canva`; a saved slide's popup exports again once the link has expired.

## Dashboard

`dashSummary(rec)` reduces a sermon to word count, references, reading grade, voice counts, and the key analysis fields. Summaries are cached, saved with each sermon's sync metadata, and pulled from `core` and `html` parts for older sermons that lack one.
