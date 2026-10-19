"""Importing a folder of files as sermons. The folder is built on disk for the test with made-up content, with known
modification dates so the dates the app falls back on can be checked. The clock starts on Tuesday, October 20, 2026."""
import asyncio, pathlib, datetime, os, shutil, tempfile, io, zipfile, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
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

def docx_bytes(paragraphs):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join('<w:p><w:r><w:t>%s</w:t></w:r></w:p>' % t for t in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {ns}><w:body>{body}</w:body></w:document>')
    return buf.getvalue()

def build(root):
    def w(rel, data, when=None):
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
        if when: ts = datetime.datetime.fromisoformat(when).timestamp(); os.utime(p, (ts, ts))
    body = "This is the made-up body of a test sermon. " * 12
    w("Psalm 23.md", f"---\ntitle: The Lord Is My Shepherd\ntext: Psalm 23\ndate: 2026-10-11 10:00\nservice: Sunday AM\nplace: Oak Grove church of Christ\nspeaker: Guest Speaker\n---\n\n## Shepherd\n\n{body}\n", "2026-01-01T09:00")
    shutil.copy(FIX / "deck.pptx", root / "Psalm 23.pptx")
    w("Psalm 23.docx", docx_bytes(["A second copy of the same sermon in Word."]))
    w("2026-10-18 Walking in Light.txt", f"Place: Oak Grove church of Christ\n\n{body}\n", "2026-01-02T09:00")
    w("Romans/Romans 12.md", f"{body}\n", "2026-10-21T15:30")
    w("Romans/2025/Old Talk.md", f"{body}\n", "2025-03-02T09:00")
    shutil.copy(FIX / "deck.pptx", root / "Lonely Deck.pptx"); ts = datetime.datetime.fromisoformat("2026-10-25T12:00").timestamp(); os.utime(root / "Lonely Deck.pptx", (ts, ts))
    w("Sunday Talk.md", f"---\ntitle: Sunday Talk\ndate: 2026-10-04 18:00\nservice: Sunday PM\n---\n\n{body}\n")
    w("Sunday Talk.mp3", b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 200)
    w("Broken.pdf", b"this is not really a pdf")
    w("photo.jpg", b"\xff\xd8\xff")
    w("notes.xyz", "unknown type")
    w(".DS_Store", b"junk")
    w("~$temp.docx", b"lock file")

INIT = "const smp = async () => ({text:''}); smp.json = async () => ({}); smp.limits = async () => ({}); window.claude = { use: async n => n === 'sample' ? smp : null };"
READ = """() => new Promise(res => { const q = indexedDB.open('pulpit-binder'); q.onsuccess = () => { const g = q.result.transaction('sermons').objectStore('sermons').getAll();
  g.onsuccess = () => res(g.result.map(r => ({ title: r.meta.title, text: r.meta.text, when: r.meta.when, service: r.meta.service, place: r.meta.place, speaker: r.meta.speaker, series: r.meta.series, slides: (r.slides || []).length, media: !!(r.media && r.media.file && r.media.file.name), words: (r.transcript || '').split(/\\s+/).filter(Boolean).length, example: !!r.example }))); }; })"""

async def open_page(b, scheme="light", viewport=(1400, 900), mobile=False):
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, color_scheme=scheme, timezone_id="America/Chicago", is_mobile=mobile, has_touch=mobile)
    await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.clock.set_system_time(NOW)
    await page.goto("https://x.test/#build"); await page.wait_for_timeout(800)
    return ctx, page, errs

async def main():
    tmp = pathlib.Path(tempfile.mkdtemp()); root = tmp / "Sermons"; root.mkdir(); build(root)
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            ctx, page, errs = await open_page(b)
            await page.click("#btn-sermon"); check("import is in the Sermon menu", await page.is_visible("#btn-import"), True); await page.keyboard.press("Escape")
            await page.click("#btn-sermon"); await page.click("#btn-import"); await page.wait_for_timeout(200)
            await page.screenshot(path=str(OUT / "folder_pick.png"))
            await page.set_input_files("#imp-in-folder", str(root)); await page.wait_for_selector("#imp-done:not([hidden])", timeout=60000); await page.wait_for_timeout(300)
            head = await page.text_content("#imp-done .imp-head")
            check("summary counts the sermons", head.strip(), "6 sermons imported")
            await page.screenshot(path=str(OUT / "folder_done.png"))
            recs = {r["title"]: r for r in await page.evaluate(READ)}
            check("one sermon per name, none from junk", sorted(recs), sorted(["The Lord Is My Shepherd", "Walking in Light", "Romans 12", "Old Talk", "Lonely Deck", "Sunday Talk"]))
            r = recs["The Lord Is My Shepherd"]
            check("details from the file, deck matched by name", (r["text"], r["when"], r["service"], r["place"], r["speaker"], r["slides"] > 0), ("Psalm 23", "2026-10-11T10:00", "Sunday AM", "Oak Grove church of Christ", "Guest Speaker", True))
            deck = r["slides"]
            r = recs["Walking in Light"]
            check("a date in the file name, service guessed from the day", (r["when"], r["service"], r["place"]), ("2026-10-18T10:00", "Sunday AM", "Oak Grove church of Christ"))
            r = recs["Romans 12"]
            check("no details: the file's date, the day's service, the subfolder as a tag", (r["when"], r["service"], r["series"]), ("2026-10-21T19:00", "Wednesday Bible Study", "Romans"))
            check("a year folder is not a tag", (recs["Old Talk"]["series"], recs["Old Talk"]["when"]), ("Romans", "2025-03-02T10:00"))
            r = recs["Lonely Deck"]
            check("a deck alone becomes a sermon", (r["slides"], r["words"], r["when"], r["service"]), (deck, 0, "2026-10-25T10:00", "Sunday AM"))
            r = recs["Sunday Talk"]
            check("a recording with the same name is attached", (r["media"], r["service"], r["when"]), (True, "Sunday PM", "2026-10-04T18:00"))
            check("the example sermon is gone", [x for x in recs.values() if x["example"]], [])
            summary = await page.inner_text("#imp-done")
            check("summary mentions slides and recordings", ("2 with slides" in summary, "1 with a recording" in summary), (True, True))
            check("guessed dates are called out", "4 had no date in the file" in summary, True)
            check("the broken PDF is reported, not saved", ("1 could not be imported" in summary, "Broken" in summary, "Broken" in recs), (True, True, False))
            skipped = await page.evaluate("[...document.querySelectorAll('#imp-done .imp-more')].find(d => /skipped/.test(d.textContent)).textContent")
            check("skipped files are listed with why", all(x in skipped for x in ["photo.jpg", "notes.xyz", "Psalm 23.docx: same name as Psalm 23.md"]) and ".DS_Store" not in skipped and "~$temp" not in skipped, True)
            check("the library lists them", await page.evaluate("document.querySelectorAll('#library option').length"), 6)

            # open one from the summary
            await page.click("#imp-done .imp-item >> text=Romans 12"); await page.wait_for_timeout(400)
            check("clicking one opens it", (await page.input_value("#m-title"), await page.is_visible("#import-modal")), ("Romans 12", False))

            # the same folder again adds nothing
            await page.click("#btn-sermon"); await page.click("#btn-import"); await page.wait_for_timeout(150)
            await page.set_input_files("#imp-in-folder", str(root)); await page.wait_for_selector("#imp-done:not([hidden])", timeout=60000); await page.wait_for_timeout(300)
            again = await page.inner_text("#imp-done")
            check("importing again skips what is already in", ("Nothing new was imported" in again, "6 already imported" in again), (True, True))
            check("and the library is unchanged", len(await page.evaluate(READ)), 6)
            await page.click("#imp-ok")

            # a dropped folder, with a subfolder
            await page.click("#btn-sermon"); await page.click("#btn-import"); await page.wait_for_timeout(150)
            await page.evaluate("""() => {
              const file = (name, text) => ({ isFile: true, isDirectory: false, name, file: ok => ok(new File([text], name, { lastModified: Date.parse('2026-10-18T12:00:00') })) });
              const dir = (name, kids) => ({ isFile: false, isDirectory: true, name, createReader: () => { let done = false; return { readEntries: ok => { if (done) ok([]); else { done = true; ok(kids); } } }; } });
              const dt = { items: [{ webkitGetAsEntry: () => dir('Dropped', [file('Drop One.md', 'Plain made-up body text for the first dropped sermon.'), dir('Series A', [file('Drop Two.txt', 'Plain made-up body text for the second dropped sermon.')])]) }], files: [] };
              const ev = new Event('drop', { bubbles: true, cancelable: true }); ev.dataTransfer = dt; document.querySelector('#imp-drop').dispatchEvent(ev); }""")
            await page.wait_for_selector("#imp-done:not([hidden])", timeout=30000); await page.wait_for_timeout(300)
            recs = {r["title"]: r for r in await page.evaluate(READ)}
            check("a dropped folder imports, its subfolder becomes a tag", (recs["Drop One"]["series"], recs["Drop Two"]["series"], recs["Drop Two"]["when"]), ("", "Series A", "2026-10-18T10:00"))
            await page.click("#imp-ok")
            check("page errors", [e for e in errs if "ERR_FAILED" not in e], [])
            await ctx.close()

            for name, scheme, vp, mob in [("folder_phone", "light", (390, 844), True), ("folder_dark", "dark", (1400, 900), False)]:
                ctx, page, errs = await open_page(b, scheme, vp, mob)
                await page.click("#btn-sermon"); await page.click("#btn-import"); await page.wait_for_timeout(200)
                await page.screenshot(path=str(OUT / (name + "_pick.png")))
                await page.set_input_files("#imp-in-folder", str(root)); await page.wait_for_selector("#imp-done:not([hidden])", timeout=60000); await page.wait_for_timeout(300)
                await page.screenshot(path=str(OUT / (name + "_done.png")))
                if mob: check("phone: no sideways scroll", await page.evaluate("document.documentElement.scrollWidth"), 390)
                await ctx.close()
            await b.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
asyncio.run(main())
