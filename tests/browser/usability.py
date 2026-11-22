"""What the usability walk-throughs turned up, kept fixed: the selection bar stays in the editor, a slide made from quoted
words keeps its quotation mark, a deck dropped by mistake can be undone, notices carry Undo, the long pages have jump
links, the phone's buttons have names, nothing floats over the text, and each section opens at its top.
Screenshots go to tests/out/usability_*.png."""
import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
fails = []
def check(name, got, want=True):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"\n       got  {got!r}\n       want {want!r}")
    if not ok: fails.append(name)

INIT = """const smp = async () => ({text:''}); smp.json = async p => { await new Promise(r => setTimeout(r, 150));
  if (p.includes('"sure": true')) return { sure: true, verses: [{ c: 119, v: 105, t: 'Placeholder verse wording for the test.' }] };
  if (p.includes('"bigIdea": one sentence')) return { bigIdea: 'A plain big idea.', summary: 'A summary.', approach: 'Expository', tone: ['warm'], themes: ['trust'], doctrines: [], scriptures: [] };
  return {}; };
smp.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? smp : n === 'downloads' ? { save: async () => ({}) } : null };"""
SELECT = """t => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { const i = n.textContent.indexOf(t); if (i >= 0 && !n.parentElement.closest('.pb-slide,.pb-scripture')) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + t.length); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""

async def open_page(b, scheme="light", viewport=(1400, 900), mobile=False, hash="build"):
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, color_scheme=scheme, timezone_id="America/Chicago", is_mobile=mobile, has_touch=mobile)
    await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}</style></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.goto("https://x.test/#" + hash); await page.wait_for_timeout(900)
    return ctx, page, errs

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        # ---------- desktop ----------
        ctx, page, errs = await open_page(b)
        js = page.evaluate
        check("the open sermon comes before the sections for the keyboard", await js("!!(document.querySelector('#sermon-card').compareDocumentPosition(document.querySelector('#tab-dash')) & Node.DOCUMENT_POSITION_FOLLOWING)"))
        await page.focus("#tab-build"); await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(200)
        check("the down arrow moves to the next section", await js("document.body.dataset.view"), "study")
        await page.keyboard.press("ArrowUp"); await page.wait_for_timeout(200)
        check("the up arrow moves back", await js("document.body.dataset.view"), "build")
        check("the sidebar says the sermon is saved", await page.text_content("#sync"), "Saved on this device")
        check("the time to preach is named", " ".join((await page.inner_text("#est-pill")).split()), "3 min to preach")
        await page.click("#est-pill"); await page.wait_for_timeout(150)
        check("pressing it explains the estimate", "words a minute" in await page.text_content("#toast"))
        check("light or dark says what it will do", await page.inner_text("#btn-theme"), "Switch to dark")
        await page.click("#btn-theme"); check("and flips its label", await page.inner_text("#btn-theme"), "Switch to light"); await page.click("#btn-theme")

        # a slide from quoted words keeps its opening mark; the selection bar stays in the editor
        await page.click("#sub-edit"); await page.wait_for_timeout(500)
        check("the heading list shows its whole label", await js("(() => { const s = document.querySelector('#ed-block'); return s.offsetWidth >= 180; })()"))
        assert await js(SELECT, "Your word is a lamp to my feet and a light to my path.")
        await page.wait_for_timeout(300)
        check("highlighting shows the selection bar", await page.is_visible("#sel-pop"))
        await page.click("#tab-analysis"); await page.wait_for_timeout(300)
        check("the selection bar does not follow to another section", await page.is_visible("#sel-pop"), False)
        stat = await js("[...document.querySelectorAll('#stats .stat')].map(s => s.innerText.replace(/\\n/g, ' '))")
        check("Analysis names the time to preach", any("to preach (min:sec)" in s for s in stat))
        await page.click("#tab-build"); await page.click("#sub-edit"); await page.wait_for_timeout(400)
        assert await js(SELECT, "Your word is a lamp to my feet and a light to my path.")
        await page.wait_for_timeout(300); await page.click("#btn-make-slide"); await page.wait_for_timeout(250)
        await page.click("#mk-kinds button:has-text('Quote')"); await page.wait_for_timeout(400); await page.click("#mk-add"); await page.wait_for_timeout(400)
        check("no quotation mark is left stranded before the new slide", await js("(() => { const cue = [...document.querySelectorAll('#editor .pb-slide')].find(c => c.nextElementSibling && c.nextElementSibling.textContent.includes('Your word is a lamp')); if (!cue) return 'no cue'; return [/[\"“]\\s*$/.test(cue.previousElementSibling.textContent), /^[\"“]Your word/.test(cue.nextElementSibling.textContent)]; })()"), [False, True])
        await page.screenshot(path=str(OUT / "usability_quote.png"))

        # a deck dropped onto a sermon that has slides can be taken back
        before = await js("document.querySelectorAll('#editor .pb-slide').length")
        await page.click("#sub-details"); await page.wait_for_timeout(300)
        n0 = await js("document.querySelector('#deck-status').innerText")
        await page.set_input_files("#file-pptx", str(FIX / "deck.pptx")); await page.wait_for_function("document.querySelector('#deck-status').innerText.includes('deck.pptx')", timeout=20000); await page.wait_for_timeout(300)
        t = await page.text_content("#toast")
        check("loading a deck says what it replaced", "took the place of" in t and "Undo" in t, True)
        check("the notice carries an Undo button", await page.is_visible("#toast .toast-act"))
        await page.screenshot(path=str(OUT / "usability_deck_toast.png"))
        await page.click("#toast .toast-act"); await page.wait_for_timeout(500)
        check("Undo brings the earlier slides back", (await js("document.querySelector('#deck-status').innerText")) == n0 and await js("document.querySelectorAll('#editor .pb-slide').length") == before)
        check("the Slides card has no empty gap", await js("getComputedStyle(document.querySelector('#deck-progress')).display"), "none")

        # sections open at their top; long pages have jump links
        await page.click("#tab-materials"); await page.wait_for_timeout(500)
        chips = await js("[...document.querySelectorAll('#mat-jump .jump-b')].map(b => b.textContent)")
        check("Materials has jump links to its parts", chips, ["Slide theme", "Back of the bulletin", "Scripture reading", "Social media invitations", "Quotes to share"])
        await page.click("#mat-jump .jump-b:has-text('Quotes to share')"); await page.wait_for_timeout(900)
        check("a jump link brings its part to the top", await js("(() => { const r = document.querySelector('#mat-quotes').getBoundingClientRect(); return r.top >= 0 && r.top < 200; })()"))
        await page.screenshot(path=str(OUT / "usability_jump.png"))
        await page.click("#tab-analysis"); await page.wait_for_timeout(300)
        check("the next section opens at its top", await js("scrollY"), 0)
        await page.click("#tab-study"); await page.wait_for_timeout(300)
        check("Study shows no jump links before a study", await page.is_visible("#st-jump"), False)
        await page.click("#st-form button[type=submit]"); await page.wait_for_timeout(1500)
        check("and shows them once there is one", (await js("document.querySelectorAll('#st-jump .jump-b').length")) >= 5)

        # Overview: coverage in words, the way in for old sermons, and deleting the open sermon
        await page.click("#tab-dash"); await page.wait_for_timeout(700)
        check("Import sermons is on the Overview", await page.is_visible("#dash-import"))
        await page.click("#dash-import"); await page.wait_for_timeout(250)
        check("and opens the import dialog", await page.is_visible("#import-modal")); await page.keyboard.press("Escape"); await page.wait_for_timeout(150)
        await page.click("#btn-sermon"); await page.wait_for_timeout(200)
        check("Delete this sermon is offered on the Overview", await page.is_visible("#btn-del")); await page.keyboard.press("Escape")
        await page.screenshot(path=str(OUT / "usability_dash.png"))

        # Present: the folded sidebar keeps its names
        await page.click("#tab-present"); await page.wait_for_timeout(500)
        check("Present's rail names each section", await js("[...document.querySelectorAll('.tab .tab-tx')].every(t => { const r = t.getBoundingClientRect(); return r.width > 20 && r.height > 8; })"))
        check("and nothing in the rail is cut off", await js("[...document.querySelectorAll('.tab, .hdr-tools > *')].every(e => e.scrollWidth <= e.clientWidth + 1)"))
        await page.screenshot(path=str(OUT / "usability_present.png"))
        check("no errors on desktop", errs, [])
        await ctx.close()

        # ---------- dark ----------
        ctx, page, errs = await open_page(b, scheme="dark", hash="materials")
        await page.wait_for_timeout(300); await page.screenshot(path=str(OUT / "usability_dark.png"))
        check("dark: dropdowns draw their own arrow", "data:image/svg+xml" in await page.evaluate("getComputedStyle(document.querySelector('#mb-size, select')).backgroundImage"))
        check("no errors in dark", errs, []); await ctx.close()

        # ---------- phone ----------
        ctx, page, errs = await open_page(b, viewport=(390, 844), mobile=True)
        js = page.evaluate
        names = await js("[...document.querySelectorAll('header.top button, .tabs .tab')].filter(e => e.offsetParent !== null || getComputedStyle(e).position === 'fixed').map(e => (e.getAttribute('aria-label') || e.innerText || '').trim()).filter(n => !n).length")
        check("phone: every button in the top and bottom bars has a name", names, 0)
        check("phone: the time to preach sits in the top bar, not over the text", await js("getComputedStyle(document.querySelector('#est-pill')).position"), "static")
        check("phone: the saved mark can be seen and pressed", await js("(() => { const r = document.querySelector('#sync').getBoundingClientRect(); return r.width >= 40 && r.height >= 40; })()"))
        await page.tap("#sync"); await page.wait_for_timeout(150)
        check("phone: pressing it says where the sermon is saved", "saved in this browser" in await page.text_content("#toast"))
        check("phone: the chip row fades where it runs on", await js("document.querySelector('#tagbar').dataset.more"), "r")
        await page.screenshot(path=str(OUT / "usability_phone.png"))
        await page.tap("#tab-present"); await page.wait_for_timeout(500)
        check("phone: Present says which slide is up", await page.inner_text("#pos-s"), "Slide 1 of 6")
        check("phone: none of Present's controls run off the screen", await js("[...document.querySelectorAll('#view-present .controls > *')].filter(e => e.offsetParent).every(e => e.getBoundingClientRect().right <= innerWidth)"))
        await page.screenshot(path=str(OUT / "usability_phone_present.png"))
        check("phone: no sideways scroll", await js("document.documentElement.scrollWidth <= innerWidth"))
        check("no errors on a phone", errs, []); await ctx.close()
        await b.close()
    print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
asyncio.run(main())
