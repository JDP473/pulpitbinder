# Pulpit Binder

A sermon workspace for preachers: write the manuscript, bind it to the PowerPoint, preach from a unified view, and see the whole body of preaching on a dashboard.

Today it runs inside Claude as a published page on Jarred Pettijohn's account, which supplies the Claude analysis, sync across devices, file storage, and the Canva connection. The long-term plan is a standalone app with its own server (see [docs/ROADMAP.md](docs/ROADMAP.md)).

## What it does

- **Dashboard:** every sermon at once: frequency, length, Bible coverage by book and section, themes, doctrines, approach, tone, themes over time, and Claude's read across all of it.
- **Build**, in three sections:
  - **Details:** sermon details (date, time, place, service, text, tags), the slide deck (.pptx rendered to match PowerPoint, or a PDF export), and a recording link or file with an as-preached transcript.
  - **Bindings:** which slide goes with which part of the text.
  - **Edit manuscript:** rich text manuscript with headings H1 to H4, highlights, pauses, slide cues, and Scripture sections (type a reference, press Tab, choose among favorite translations). Slides sit in a column beside the text and stay in sync. Side panel with Claude's suggestions and an outline view with auto outline. Highlight text or use a Scripture section to make new slides (quote, key verse, big idea, summary points, fill in the blank, question, Canva illustration, photo).
- **Present:** the manuscript scrolls and the matching slide follows along. Works on phones, with smaller slides so the text leads.
- **Analysis:** word count, timing, passages cited, recurring words, voice, as-preached comparison, share text and chapters, and Claude's substance analysis.

## Repository layout

| Path | What it is |
|---|---|
| `pulpit-binder.html` | The whole app: markup, styles, and script in one file. This is what gets published. |
| `docs/ARCHITECTURE.md` | How the file is organized, the data model, sync layout, and integrations. |
| `docs/ROADMAP.md` | The path from the Claude-hosted version to a standalone product. |
| `tests/browser/` | Playwright scripts that load the page with mocked Claude, Canva, and Firecrawl. |
| `tests/node/` | jsdom checks for boot and sync. |
| `tests/fixtures/` | A generic 12-slide deck and placeholder images for tests. |

## Running the tests

```bash
cd tests/node && npm install && cd ../..
pip install playwright        # uses an installed Chromium
python3 tests/browser/dash.py # dashboard with 26 seeded sermons
python3 tests/browser/pk.py   # slide picker, Canva mock, Scripture slides
```

`pk.py` and `sc.py` also need `tests/fixtures/samples.json` (Bible Gateway print-view markdown for ESV, LSB, and NKJV). It is not committed because the Bible text is copyrighted; capture it locally if you need those tests.

Screenshots go to `tests/out/`.

## Your sermons are not in this repo

Manuscripts, slides, recordings, and analyses sync to the Claude account under the published page. This repository holds code only.
