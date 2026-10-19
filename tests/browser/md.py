"""Markdown in the editor: import with details auto-filled, typing shortcuts, paste, and the Markdown view.
The clock is fixed on Tuesday, October 20, 2026 at 9:00 AM Central. Fixtures here are generic, made-up text."""
import asyncio, pathlib, datetime, zipfile, io
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
NOW = datetime.datetime(2026, 10, 20, 14, 0, tzinfo=datetime.timezone.utc)
fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"\n       got  {got!r}\n       want {want!r}")
    if not ok: fails.append(name)

FRONT = """---
title: Walking in the Light
text: Psalm 119:105-112
date: 2026-10-18 18:00
service: Sunday PM
place: Oak Grove church of Christ
speaker: Guest Speaker
tags: [lamp, faith]
pace: 150
---

# Introduction

Good evening. This is a **generic** test paragraph with *italic*, ++underline++, ==highlight==,
and a soft wrapped second line.

## First point

> A short quotation for the test.

- one thing
- another thing

1. first
2. second

[slide 2]

Second paragraph with a [pause] in it.

::: scripture John 3:16 ESV
{{16}} Generic test verse text for the fixture.
:::
"""
APP_EXPORT = """# Exported Sermon

- **When:** Sun, Oct 18, 2026, 10:00 AM
- **Where:** Bridge Creek church of Christ
- **Service:** Sunday AM
- **Text:** Romans 8:28-30
- **Speaker:** Jarred Pettijohn
- **Tags:** hope, trust
- **Length:** 900 words, about 6 minutes

## Substance analysis

**Big idea:** Not part of the manuscript.

## Manuscript with slide cues

**[Slide 1: Opening]**

First paragraph of the manuscript.

**[Slide 2: Point]**

Second paragraph.
"""
PLAIN = """A Plain Text Sermon
Sunday, October 25, 2026 at 6:00 PM
Romans 12:1-2
Preached by Visiting Brother

Brothers and sisters, this is where the manuscript begins and it is a long enough line to be body text for sure.

Another paragraph.
"""
LOOSE = """Untitled Loose Header
Wednesday, October 21, 2026 · 7:00 PM
Some Other Church

The body starts here, with a sentence that is clearly not a header line at all, so it stays.
"""

def docx_bytes():
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    def p(text, style=None):
        ppr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
        return '<w:p>%s<w:r><w:t>%s</w:t></w:r></w:p>' % (ppr, text)
    body = p("Docx Test Sermon", "Title") + p("Date: October 21, 2026") + p("Time: 7:00 PM") + p("Place: Docx Congregation") + p("The manuscript text begins right here in a normal paragraph of the document.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {ns}><w:body>{body}</w:body></w:document>')
    return buf.getvalue()

META = "() => ({ title: document.querySelector('#m-title').value, text: document.querySelector('#m-text').value, when: document.querySelector('#m-when').value, service: document.querySelector('#m-service').value, place: document.querySelector('#m-place').value, speaker: document.querySelector('#m-speaker').value, series: document.querySelector('#m-series').value, wpm: document.querySelector('#m-wpm').value })"
BODY = "() => document.querySelector('#editor').innerHTML"

async def open_page(b, scheme="light", viewport=(1400, 900), mobile=False):
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, color_scheme=scheme, timezone_id="America/Chicago", is_mobile=mobile, has_touch=mobile)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.clock.set_fixed_time(NOW)
    await page.goto("https://x.test/#edit"); await page.wait_for_timeout(800)
    return ctx, page, errs

async def load(page, name, data, mime="text/plain"):
    await page.set_input_files("#file-text", files=[{"name": name, "mimeType": mime, "buffer": data if isinstance(data, bytes) else data.encode()}])
    await page.wait_for_timeout(500)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx, page, errs = await open_page(b)

        # 1. Markdown file with a details block
        await page.click("#btn-sermon"); await page.click("#btn-new"); await page.click("#tab-edit"); await page.wait_for_timeout(300)
        await load(page, "walking.md", FRONT, "text/markdown")
        m = await page.evaluate(META)
        check("front matter: title, text", (m["title"], m["text"]), ("Walking in the Light", "Psalm 119:105-112"))
        check("front matter: date and time", m["when"], "2026-10-18T18:00")
        check("front matter: service, place", (m["service"], m["place"]), ("Sunday PM", "Oak Grove church of Christ"))
        check("front matter: speaker, tags, pace", (m["speaker"], m["series"], m["wpm"]), ("Guest Speaker", "lamp, faith", "150"))
        check("toast names what was filled", "Filled in title, primary text, date and time, service, place, speaker, tags, pace" in await page.text_content("#toast"), True)
        h = await page.evaluate(BODY)
        for name, frag in [("h1", "<h1>Introduction</h1>"), ("h2", "<h2>First point</h2>"), ("bold", "<strong>generic</strong>"), ("italic", "<em>italic</em>"),
                           ("underline", "<u>underline</u>"), ("highlight", '<mark class="hl-yellow">highlight</mark>'), ("quote", "<blockquote>A short quotation for the test.</blockquote>"),
                           ("bullets", "<ul><li>one thing</li><li>another thing</li></ul>"), ("numbers", "<ol><li>first</li><li>second</li></ol>"), ("slide cue", 'data-n="2"'), ("pause", "pb-cue"),
                           ("scripture", 'data-ref="John 3:16"')]:
            check("body has " + name, frag in h, True)
        check("soft wrap joined into one paragraph", "highlight</mark>, and a soft wrapped second line" in h.replace("\n", " "), True)
        check("details block is not in the manuscript", "title:" in h or "pace:" in h, False)
        await page.screenshot(path=str(OUT / "md_import.png"))

        # undo restores details too
        await page.click("#sg-undo"); await page.wait_for_timeout(300)
        m = await page.evaluate(META)
        check("undo puts the old details back", (m["title"], m["place"]), ("", "Bridge Creek church of Christ"))

        # 2. a file this app exported
        await load(page, "exported.md", APP_EXPORT, "text/markdown")
        m = await page.evaluate(META)
        check("export format: details", (m["title"], m["when"], m["service"], m["place"], m["text"], m["speaker"], m["series"]),
              ("Exported Sermon", "2026-10-18T10:00", "Sunday AM", "Bridge Creek church of Christ", "Romans 8:28-30", "Jarred Pettijohn", "hope, trust"))
        h = await page.evaluate(BODY)
        check("export format: only the manuscript, with cues", ("Big idea" in h, 'data-n="1"' in h, 'data-n="2"' in h, "First paragraph" in h), (False, True, True, True))

        # 3. plain text: title line, date, reference, by-line
        await load(page, "plain.txt", PLAIN)
        m = await page.evaluate(META)
        check("plain text: title, date, text, speaker", (m["title"], m["when"], m["text"], m["speaker"]), ("A Plain Text Sermon", "2026-10-25T18:00", "Romans 12:1-2", "Visiting Brother"))
        check("plain text: service inferred from day and time", m["service"], "Sunday PM")
        h = await page.evaluate(BODY)
        check("plain text: header lines left the manuscript", ("Brothers and sisters" in h, "Preached by" in h, "A Plain Text Sermon" in h), (True, False, False))

        # 4. loose lines: unknown place is kept, Wednesday inferred
        await load(page, "loose.txt", LOOSE)
        m = await page.evaluate(META)
        check("loose header: title, when, service, place", (m["title"], m["when"], m["service"], m["place"]), ("Untitled Loose Header", "2026-10-21T19:00", "Wednesday Bible Study", m["place"]))
        check("loose header: body stays", "The body starts here" in await page.evaluate(BODY), True)
        check("unknown place offers to be saved", await page.is_visible("#m-place-save"), False if m["place"] == "Bridge Creek church of Christ" else True)

        # 5. docx
        await load(page, "docx-sermon.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        m = await page.evaluate(META)
        check("docx: title, when, place", (m["title"], m["when"], m["place"]), ("Docx Test Sermon", "2026-10-21T19:00", "Docx Congregation"))
        check("docx: service inferred", m["service"], "Wednesday Bible Study")
        check("docx: only the manuscript left", await page.evaluate("document.querySelector('#editor').textContent.trim()"), "The manuscript text begins right here in a normal paragraph of the document.")

        # 6. typing shortcuts
        await page.click("#btn-sermon"); await page.click("#btn-new"); await page.click("#tab-edit"); await page.wait_for_timeout(300)
        await page.evaluate("document.querySelector('#editor').innerHTML = '<p><br></p>'")
        await page.click("#editor"); await page.keyboard.press("Control+End")
        async def line(txt, enter=True):
            await page.keyboard.type(txt)
            if enter: await page.keyboard.press("Enter")
        await line("## A heading"); await line("> A quotation"); await page.keyboard.press("Enter")
        await line("- bullet one"); await page.keyboard.press("Enter"); await page.keyboard.press("Enter")
        await line("1. step one"); await page.keyboard.press("Enter"); await page.keyboard.press("Enter")
        await line("Plain with **bold** and *slanted* and ==marked== and ++under++ words.")
        await line("[slide 3]"); await line("After the cue [pause]", False)
        await page.wait_for_timeout(500)
        h = (await page.evaluate(BODY)).replace("&nbsp;", " ")   # Chrome holds a typed space as a non-breaking one
        for name, frag in [("heading", "<h2>A heading</h2>"), ("quote", "<blockquote>A quotation</blockquote>"), ("bullet", "<ul><li>bullet one</li></ul>"), ("number", "<ol><li>step one</li></ol>"),
                           ("bold", "<strong>bold</strong> and"), ("italic", "<em>slanted</em> and"), ("mark", '<mark class="hl-yellow">marked</mark> and'), ("underline", "<u>under</u> words."),
                           ("slide cue", 'data-n="3"'), ("pause", "pb-cue")]:
            check("typing: " + name, frag in h, True)
        check("typing: no stray markers", any(x in h for x in ["**", "==", "++", "[slide", "[pause"]), False)
        if any(x in h for x in ["**", "==", "++", "[slide", "[pause"]) or "<ul><li>bullet one</li></ul>" not in h: print("DOM:", h)
        await page.screenshot(path=str(OUT / "md_typing.png"))

        # 7. paste Markdown (plain text only, and as a code editor would send it)
        await page.evaluate("document.querySelector('#editor').innerHTML = '<p>Start</p>'")
        await page.click("#editor"); await page.keyboard.press("Control+End")
        await page.evaluate("""() => { const dt = new DataTransfer(); dt.setData('text/plain', '## Pasted heading\\n\\n- pasted item\\n- second item\\n\\nWith **bold** text.');
          dt.setData('text/html', '<div style="font-family: Consolas, monospace"><div>## Pasted heading</div></div>');
          document.querySelector('#editor').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }""")
        await page.wait_for_timeout(400)
        h = await page.evaluate(BODY)
        check("paste: markdown from a code editor becomes structure", all(x in h for x in ["<h2>Pasted heading</h2>", "<ul><li>pasted item</li><li>second item</li></ul>", "<strong>bold</strong>"]), True)

        # 8. the Markdown view
        await page.evaluate("document.querySelector('#editor').innerHTML = ''")
        await page.click("#btn-md"); await page.wait_for_timeout(300)
        src = await page.input_value("#md-src")
        check("view: toolbar collapses to Markdown controls", await page.evaluate("[...document.querySelectorAll('#ed-toolbar > *')].filter(e => getComputedStyle(e).display !== 'none').map(e => e.id || e.className).length <= 4"), True)
        await page.click("#btn-md")  # back
        await page.evaluate("document.querySelector('#editor').innerHTML = ''")
        await page.click("#btn-md"); await page.wait_for_timeout(200)
        await page.fill("#md-src", FRONT + "\nAn added closing paragraph.\n"); await page.wait_for_timeout(1100)
        m = await page.evaluate(META)
        check("view: editing the details block updates the sermon", (m["title"], m["service"], m["place"]), ("Walking in the Light", "Sunday PM", "Oak Grove church of Christ"))
        check("view: edits apply to the manuscript as you type", "An added closing paragraph." in await page.evaluate(BODY), True)
        await page.screenshot(path=str(OUT / "md_view.png"))
        sid = await page.evaluate("document.querySelector('#editor .pb-scripture').getAttribute('data-id')")
        await page.click("#btn-md"); await page.wait_for_timeout(300)   # back to editor
        before = await page.evaluate(BODY)
        await page.click("#btn-md"); await page.wait_for_timeout(300)   # to source and back, untouched
        src2 = await page.input_value("#md-src")
        await page.click("#btn-md"); await page.wait_for_timeout(300)
        check("round trip: the manuscript is unchanged", await page.evaluate(BODY), before)
        check("round trip: the Scripture section keeps its id", f"#{sid}" in src2, True)
        check("round trip: source holds details and structure", all(x in src2 for x in ["title: Walking in the Light", "# Introduction", "> A short quotation", "- one thing", "1. first", "[slide 2]", "[pause]", "::: scripture John 3:16 ESV"]), True)
        check("round trip: the verse text stays", "{{16}} Generic test verse text" in src2, True)

        # 9. awkward content survives a trip through Markdown and back, and a second trip changes nothing
        TRICKY = ('<p>2 * 3 * 4 and a_b_c and #hashtag and a * b</p><p>1. Not a list</p><p># not a heading</p><p>&gt; not a quote</p><p>- not a bullet</p>'
                  '<p>[slide] literal text and [pause] too</p><p>Line one<br>Line two</p><p><mark class="hl-green">green words</mark> and <strong>bold <em>and italic</em></strong></p>'
                  '<p>a ==b== c and ++d++ e and back\\slash and `tick` and C# and 5 &lt; 6</p><h3>Heading *with* stars</h3><blockquote>Quote with **marks** inside</blockquote>')
        await page.evaluate("(h) => { document.querySelector('#editor').innerHTML = h; }", TRICKY)
        text0 = (await page.evaluate("document.querySelector('#editor').textContent")).replace("\u00a0", " ")
        for _ in range(2):
            await page.click("#btn-md"); await page.wait_for_timeout(250); await page.click("#btn-md"); await page.wait_for_timeout(250)
        html1 = await page.evaluate(BODY)
        for _ in range(2):
            await page.click("#btn-md"); await page.wait_for_timeout(250); await page.click("#btn-md"); await page.wait_for_timeout(250)
        check("tricky: text is exactly preserved", (await page.evaluate("document.querySelector('#editor').textContent")).replace("\u00a0", " "), text0)
        check("tricky: a further trip changes nothing", await page.evaluate(BODY), html1)
        for name, frag in [("colored highlight", '<mark class="hl-green">green words</mark>'), ("nested bold and italic", "<strong>bold <em>and italic</em></strong>"), ("hard break", "Line one<br>Line two"),
                           ("literal not a list", "<p>1. Not a list</p>"), ("literal not a heading", "<p># not a heading</p>"), ("literal not a quote", "<p>&gt; not a quote</p>"), ("literal not a bullet", "<p>- not a bullet</p>"),
                           ("heading keeps stars", "<h3>Heading *with* stars</h3>"), ("quote keeps marks", "<blockquote>Quote with **marks** inside</blockquote>")]:
            check("tricky: " + name, frag in html1, True)
        check("page errors", errs, [])
        await ctx.close()

        # dark and phone looks
        ctx, page, errs = await open_page(b, "dark")
        await page.click("#btn-md"); await page.wait_for_timeout(300)
        await page.screenshot(path=str(OUT / "md_view_dark.png"))
        await ctx.close()
        ctx, page, errs = await open_page(b, "light", (390, 844), True)
        await page.click("#btn-md"); await page.wait_for_timeout(300)
        await page.screenshot(path=str(OUT / "md_view_phone.png"))
        check("phone: no sideways scroll", await page.evaluate("document.documentElement.scrollWidth"), 390)
        check("phone page errors", errs, [])
        await ctx.close()
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
asyncio.run(main())
