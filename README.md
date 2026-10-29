# Pulpit Binder

A sermon workspace for preachers: write the manuscript, bind it to the PowerPoint, preach from a unified view, and see the whole body of preaching on a dashboard.

Today it runs inside Claude as a published page on Jarred Pettijohn's account, which supplies the Claude analysis, sync across devices, file storage, and the Canva connection. The same file also runs for any preacher at sermon.freely.church, with accounts, sync, and Claude on each preacher's own Anthropic key (see [saas/README.md](saas/README.md)).

## What it does

- **Overview:** every sermon at once: frequency, length, Bible coverage by book and section, themes, doctrines, approach, tone, themes over time, and Claude's read across all of it.
- **Write** (once called Build), in three sections:
  - **Details:** sermon details (date, time, place, service, text, tags), the slide deck (.pptx rendered to match PowerPoint, or a PDF export), and a recording link or file with an as-preached transcript.
  - **Series documents:** shown when a sermon has a series or tag; the other sermons that share it, readable in place, with a button to open one, and **Next sermon in the series**, which recommends the next text (the next passage in order, plus Claude's options) and creates the sermon with the series, text, title, and date filled in.
  - **Bindings:** which slide goes with which part of the text.
  - **Edit manuscript:** rich text manuscript with headings H1 to H4, highlights, pauses, slide cues, and Scripture sections (type a reference, press Tab, choose among favorite translations). Every Scripture section you add makes its own passage slides, two verses a slide, as soon as its text loads or is pasted. Any slide can be edited or turned into another kind from the slide column, from Bindings, or (on a phone) by tapping its slide cue; a slide read from a PowerPoint can be remade as a slide made here. Slides sit in a column beside the text and stay in sync. Side panel, which you can drag wider, with Claude's suggestions, an outline view (auto outline, add headings, and Write, which drafts a section's text with Claude from your prompt and places it under that heading), and the Text Study. Highlight text or use a Scripture section to make new slides (quote, key verse, big idea, summary points, fill in the blank, question, Canva illustration, photo).
- **Present:** the manuscript scrolls and the matching slide follows along. Works on phones, with smaller slides so the text leads.
- **Materials:** slide themes (Claude proposes colors, typefaces, a texture, and a Canva header picture from the sermon's text; previews on the sermon's own words; styles new slides, restyles made slides, adds title and Scripture slides, saves backgrounds), the bulletin notes page, a Scripture reading page (sermon name and the passage for whoever reads it), social invitations, and quote cards.
- **Obsidian:** with Settings, Obsidian turned on, each sermon is kept as a Markdown note in the vault through the Obsidian connector (`AIOS/Sermons` by default): front matter, Logos links for Scripture, and every slide as a picture note embedded where it comes up. It saves about a minute after writing stops, only changed slides are written again, and Save to Obsidian in the sermon menu saves right away.
- **Analysis:** word count, timing, passages cited, recurring words, voice, as-preached comparison, share text and chapters, and Claude's substance analysis.

## Repository layout

| Path | What it is |
|---|---|
| `pulpit-binder.html` | The whole app: markup, styles, and script in one file. This is what gets published. |
| `docs/ARCHITECTURE.md` | How the file is organized, the data model, sync layout, and integrations. |
| `saas/` | sermon.freely.church: the server, public page, account pages, and the shim that runs this file outside Claude. |
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
python3 tests/browser/shell.py   # sidebar, Settings page, AI and images
python3 tests/browser/reading.py   # Scripture reading page on Materials
python3 tests/browser/scfmt.py   # formatting Scripture and slides following it
python3 tests/browser/pptxout.py   # saves the deck as .pptx (open tests/out/export.pptx to check it)
python3 tests/browser/canvahd.py   # full-size Canva pictures through the export flow
python3 tests/browser/scauto.py   # passage slides made when a Scripture section is added
python3 tests/browser/slideedit.py   # editing slides and changing their kind
python3 tests/browser/hosted.py   # sermon.freely.church: sign up, sync, Claude, sharing, account and admin pages
python3 tests/browser/obsidian.py   # saving to Obsidian through a stand-in connector (notes go to tests/out/obsidian/)
python3 tests/browser/hosted_pictures.py   # sermon.freely.church: picture keys in Account, painting a slide with them
python3 tests/browser/libmenu.py   # the open-sermon card and More menu at every width
```

`pk.py` and `sc.py` also need `tests/fixtures/samples.json` (Bible Gateway print-view markdown for ESV, LSB, and NKJV). It is not committed because the Bible text is copyrighted; capture it locally if you need those tests.

Screenshots go to `tests/out/`.

## Your sermons are not in this repo

Manuscripts, slides, recordings, and analyses sync to the Claude account under the published page, or to the sermon.freely.church server for preachers there. This repository holds code only.
