"""Materials tab: bulletin notes page, social invitation, quote cards, and Branding in Settings.
Claude and downloads are mocked. Screenshots and the drawn pictures go to tests/out/mat_*.png."""
import asyncio, base64, io, pathlib, zipfile
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"\n       got  {got!r}\n       want {want!r}")
    if not ok: fails.append(name)
INIT = r"""
const smp = async () => ({text:''});
smp.json = async (p) => { await new Promise(r => setTimeout(r, 60));
  if (p.includes("sermon-notes page")) return { bigIdea: "God's word gives enough light for the next faithful step.", outline: [{level:1,text:"God's word is a [[lamp]], not a floodlight"},{level:2,text:"It lights the [[next]] step"},{level:1,text:"A lamp only helps if you [[carry]] it"},{level:1,text:"The lamp is for the [[dark]]"},{level:1,text:"So take the [[next]] faithful step this week"}], questions: ["What is the next faithful step this light shows you?","Where will you open your Bible this week?"] };
  if (p.includes("three short social media posts")) return { captions: [{label:"Warm and simple",text:"You are invited to worship with us this Sunday."},{label:"Short",text:"Join us Sunday."},{label:"About the message",text:"This week we look at Psalm 119."}] };
  if (p.includes("most worth sharing")) return { quotes: [{text:"God rarely shows us the whole road. He gives us enough light for the next faithful step.",why:"x"},{text:"This sentence is not anywhere in the manuscript.",why:"x"}] };
  return {}; };
smp.limits = async () => ({});
window.__saved = [];
const dl = { save: async ({filename, data}) => { const buf = data instanceof Blob ? await data.arrayBuffer() : new TextEncoder().encode(String(data)).buffer; const u = new Uint8Array(buf); let bin = ""; for (let i = 0; i < u.length; i += 8192) bin += String.fromCharCode.apply(null, u.subarray(i, i + 8192)); window.__saved.push({filename, size: u.length, b64: btoa(bin)}); return {status: "saved"}; } };
window.claude = { use: async n => n === "sample" ? smp : n === "downloads" ? dl : null };
"""
INK = """(id) => { const c = document.querySelector(id), x = c.getContext('2d'), d = x.getImageData(0, 0, c.width, c.height).data; const seen = new Set(); let ink = 0; const bg = [d[0], d[1], d[2]].join(); for (let i = 0; i < d.length; i += 4 * 97) { const k = d[i] + ',' + d[i+1] + ',' + d[i+2]; seen.add(k); if (k !== bg) ink++; } return [c.width, c.height, seen.size > 12, ink > 40]; }"""
async def open_page(b, **kw):
    ctx = await b.new_context(**kw); await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.goto("https://x.test/"); await page.wait_for_timeout(800)
    return ctx, page, errs
async def pic(page, sel, name):
    d = await page.evaluate(f"document.querySelector('{sel}').toDataURL('image/png')")
    (OUT / name).write_bytes(base64.b64decode(d.split(",")[1]))
async def main():
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx, page, errs = await open_page(b, viewport={"width": 1300, "height": 950}, color_scheme="light")
        await page.click("#tab-materials"); await page.wait_for_timeout(700)
        check("the tab opens its view", await page.is_visible("#view-materials"), True)
        check("bulletin page is drawn at 200 dpi, letter size", (await page.evaluate(INK, "#mb-canvas"))[:2], [1700, 2200])
        check("bulletin has more than a blank page", (await page.evaluate(INK, "#mb-canvas"))[2:], [True, True])
        check("invitation is drawn", (await page.evaluate(INK, "#ms-canvas"))[2:], [True, True])
        check("quote picture is drawn", (await page.evaluate(INK, "#mq-canvas"))[2:], [True, True])
        outline = await page.input_value("#mb-outline")
        check("the outline starts from the manuscript, with blanks", ("[[" in outline, outline.count("\n") >= 2), (True, True))
        n_q = await page.evaluate("document.querySelectorAll('#mq-list .mat-q').length")
        check("quotable lines are found", n_q >= 3, True)
        brand = await page.inner_text("#mat-brand-name"); check("branding strip names the church", brand, "Bridge Creek church of Christ")
        # Claude drafts
        await page.click("#mb-ai"); await page.wait_for_timeout(700)
        check("Claude's outline replaces the text", "[[lamp]]" in await page.input_value("#mb-outline"), True)
        check("big idea and questions are filled", ((await page.input_value("#mb-idea")).startswith("God's word"), (await page.input_value("#mb-q")).count("\n")), (True, 1))
        await page.click("#mq-ai"); await page.wait_for_timeout(700)
        texts = await page.evaluate("[...document.querySelectorAll('#mq-list textarea')].map(t => t.value)")
        check("a quote that is in the manuscript is added", any(t.startswith("God rarely shows us") for t in texts), True)
        check("a quote that is not in the manuscript is refused", any("not anywhere" in t for t in texts), False)
        check("the refusal is explained", "left out" in await page.inner_text("#mq-status"), True)
        await page.click("#ms-ai"); await page.wait_for_timeout(700)
        check("three captions arrive", await page.evaluate("document.querySelectorAll('#ms-caps .mat-cap').length"), 3)
        # editing redraws
        before = await page.evaluate("document.querySelector('#mb-canvas').toDataURL().length")
        await page.fill("#mb-outline", "Short point with a [[blank]]"); await page.wait_for_timeout(500)
        after = await page.evaluate("document.querySelector('#mb-canvas').toDataURL().length")
        check("editing the outline redraws the page", before != after, True)
        await page.click("#mb-local"); await page.wait_for_timeout(300)
        # branding
        await page.click("#mat-edit-brand"); await page.wait_for_timeout(300)
        check("Branding opens in Settings", await page.get_attribute("#set-tab-brand", "aria-selected"), "true")
        await page.evaluate("""async () => { const c = document.createElement('canvas'); c.width = 300; c.height = 120; const x = c.getContext('2d'); x.fillStyle = '#2f5d8a'; x.fillRect(0, 0, 300, 120); x.fillStyle = '#fff'; x.font = '700 44px serif'; x.fillText('BCC', 24, 74);
          const blob = await new Promise(r => c.toBlob(r, 'image/png')); const dt = new DataTransfer(); dt.items.add(new File([blob], 'logo.png', {type: 'image/png'})); const i = document.querySelector('#set-logo-file'); i.files = dt.files; i.dispatchEvent(new Event('change')); }""")
        await page.wait_for_timeout(500)
        check("the logo shows in the dialog", await page.evaluate("!!document.querySelector('#set-logo-box img')"), True)
        await page.fill("#set-baddr", "100 Example Road, Anytown"); await page.fill("#set-bweb", "example.org")
        await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(700)
        check("the logo shows in the branding strip", await page.evaluate("!!document.querySelector('#mat-brand-logo img')"), True)
        check("settings keep the logo", await page.evaluate("JSON.parse(localStorage.getItem('pb-settings')).brand.logo.startsWith('data:image/png')"), True)
        await pic(page, "#mb-canvas", "mat_bulletin.png"); await pic(page, "#ms-canvas", "mat_invite.png"); await pic(page, "#mq-canvas", "mat_quote.png")
        await page.screenshot(path=str(OUT / "mat_desktop.png"), full_page=True)
        # files
        await page.click("#mb-pdf"); await page.wait_for_timeout(1200)
        await page.click("#ms-png"); await page.wait_for_timeout(800)
        await page.click("#mq-png"); await page.wait_for_timeout(800)
        await page.click("#mq-zip"); await page.wait_for_timeout(1500)
        await page.click("#mat-all"); await page.wait_for_timeout(2500)
        saved = await page.evaluate("window.__saved")
        names = [s["filename"] for s in saved]
        print("saved:", names)
        pdf = base64.b64decode(next(s["b64"] for s in saved if s["filename"].endswith("bulletin-notes.pdf")))
        check("the PDF is a PDF with one letter-size page", (pdf[:5], b"/MediaBox [0 0 612.00 792.00]" in pdf, pdf.count(b"/Type /Page ")), (b"%PDF-", True, 1))
        (OUT / "mat_bulletin.pdf").write_bytes(pdf)
        png = base64.b64decode(next(s["b64"] for s in saved if "invitation" in s["filename"] and s["filename"].endswith(".png")))
        check("the invitation is a PNG", png[:8], b"\x89PNG\r\n\x1a\n")
        z1 = zipfile.ZipFile(io.BytesIO(base64.b64decode(next(s["b64"] for s in saved if s["filename"].endswith("quotes.zip")))))
        check("the quotes zip holds PNGs", all(n.endswith(".png") for n in z1.namelist()) and len(z1.namelist()) >= 1, True)
        z2 = zipfile.ZipFile(io.BytesIO(base64.b64decode(next(s["b64"] for s in saved if s["filename"].endswith("materials.zip")))))
        check("everything zip holds the PDF, the invitation, and the quotes", (any(n.endswith(".pdf") for n in z2.namelist()), any("invitation" in n for n in z2.namelist()), any("quote" in n for n in z2.namelist())), (True, True, True))
        # answer key and half page
        await page.check("#mb-ans"); await page.select_option("#mb-size", "half"); await page.wait_for_timeout(600)
        check("half page is 5.5 by 8.5", (await page.evaluate(INK, "#mb-canvas"))[:2], [1100, 1700])
        await pic(page, "#mb-canvas", "mat_bulletin_half_answers.png")
        check("no errors on desktop", errs, [])
        await ctx.close()
        # phone, light and dark
        for scheme in ["light", "dark"]:
            ctx, page, errs = await open_page(b, **p.devices["iPhone 13"], color_scheme=scheme)
            await page.click("#tab-materials"); await page.wait_for_timeout(900)
            sw = await page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"); check(f"phone {scheme}: no sideways scroll", sw, 0)
            tabs = await page.evaluate("[...document.querySelectorAll('.tab')].map(t => { const r = t.getBoundingClientRect(), s = t.querySelector('.tab-tx'); return [Math.round(r.width), s.scrollWidth <= Math.ceil(r.width)]; })")
            check(f"phone {scheme}: seven tabs each wide enough for their label", (len(tabs), all(w >= 44 and fit for w, fit in tabs)), (7, True))
            small = await page.evaluate("""() => [...document.querySelectorAll('#view-materials button, #view-materials select, #view-materials input, #view-materials textarea')].filter(e => e.checkVisibility && e.checkVisibility() && Math.min(e.getBoundingClientRect().width, e.getBoundingClientRect().height) < 32 && e.type !== 'checkbox').map(e => (e.id || e.className) + ' ' + Math.round(e.getBoundingClientRect().width) + 'x' + Math.round(e.getBoundingClientRect().height))""")
            check(f"phone {scheme}: no tiny controls", small, [])
            zoom = await page.evaluate("""() => [...document.querySelectorAll('#view-materials input, #view-materials select, #view-materials textarea')].filter(e => e.checkVisibility() && e.type !== 'checkbox' && parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.id)""")
            check(f"phone {scheme}: fields are 16px", zoom, [])
            await page.screenshot(path=str(OUT / f"mat_phone_{scheme}.png"), full_page=True)
            check(f"phone {scheme}: no errors", errs, [])
            await ctx.close()
        await b.close()
    print("\nall passed" if not fails else "\nFAILED: " + "; ".join(fails))
    raise SystemExit(1 if fails else 0)
asyncio.run(main())
