import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
S = json.load(open(FIX / "samples.json"))
INIT = """
window.__calls = [];
const SAMPLES = %s;
window.claude = { use: async n => {
  if (n === 'mcp') return { callTool: async (srv, tool, input) => { window.__calls.push([srv, tool, input.url]); await new Promise(r => setTimeout(r, 150));
      const u = input.url; const md = u.includes('version=LSB') && u.includes('Romans') ? SAMPLES.lsb : u.includes('version=LSB') ? SAMPLES.esv.replace('his only Son', 'His only begotten Son') : u.includes('Psalm') ? SAMPLES.nkjv : SAMPLES.esv;
      return { content: [{type:'text', text: JSON.stringify({markdown: md})}], payload: { markdown: md } }; } };
  return null; } };
""" % json.dumps(S)
async def run(mobile):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(**(p.devices["iPhone 13"] if mobile else {"viewport": {"width": 1400, "height": 900}}))
        await ctx.add_init_script(INIT)
        page = await ctx.new_page(); errs=[]
        page.on("pageerror", lambda e: errs.append(str(e)))
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.goto("https://x.test/#edit"); await page.wait_for_timeout(900)
        # put caret at end of first paragraph and type a sentence with a reference
        await page.evaluate("""() => { const p = document.querySelector('#editor p'); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); }""")
        await page.keyboard.type(" As Jesus said in John 3:16-18")
        await page.wait_for_timeout(200)
        print("hint visible:", await page.is_visible("#sc-hint"), await page.text_content("#sc-hint"))
        await page.screenshot(path=("scm" if mobile else "sc")+"0.png")
        if mobile:
            await page.click("#sc-hint-btn")
        else:
            await page.keyboard.press("Tab")
        await page.wait_for_timeout(600)
        info = await page.evaluate("""() => { const b = document.querySelector('#editor .pb-scripture'); return b && { ref: b.dataset.ref, ver: b.dataset.ver, tabs: [...b.querySelectorAll('.pb-sc-tab')].map(t=>t.textContent+(t.getAttribute('aria-pressed')==='true'?'*':'')), body: b.querySelector('.pb-sc-body').textContent.slice(0,80), prev: b.previousElementSibling.textContent.slice(-40), next: b.nextElementSibling && b.nextElementSibling.outerHTML.slice(0,40) } }""")
        print("block:", info)
        print("calls:", await page.evaluate("__calls"))
        # type continues in next paragraph
        await page.keyboard.type("That is the gospel.")
        await page.wait_for_timeout(400)
        print("after type next:", await page.evaluate("document.querySelector('#editor .pb-scripture').nextElementSibling.textContent"))
        # switch to LSB tab
        await page.click("#editor .pb-scripture .pb-sc-tab[data-v=LSB]"); await page.wait_for_timeout(600)
        print("LSB body:", await page.evaluate("document.querySelector('#editor .pb-scripture .pb-sc-body').textContent.slice(0,60)"), await page.evaluate("Object.keys(JSON.parse(document.querySelector('#editor .pb-scripture').dataset.texts))"))
        # back to ESV: no new call
        n0 = len(await page.evaluate("__calls"))
        await page.click("#editor .pb-scripture .pb-sc-tab[data-v=ESV]"); await page.wait_for_timeout(300)
        print("calls after back to ESV:", len(await page.evaluate("__calls")) - n0)
        await page.screenshot(path=("scm" if mobile else "sc")+"1.png", full_page=False)
        # whole-paragraph reference
        await page.evaluate("""() => { const p = document.createElement('p'); p.textContent = 'Psalm 23:1-2'; document.querySelector('#editor').append(p); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); }""")
        await page.wait_for_timeout(100)
        if not mobile:
            await page.keyboard.press("Tab"); await page.wait_for_timeout(500)
            print("psalm blocks:", await page.evaluate("[...document.querySelectorAll('#editor .pb-scripture')].map(b => b.dataset.ref + ' prev=' + (b.previousElementSibling && b.previousElementSibling.textContent.slice(-20)))"))
            # present
            await page.click("#tab-present"); await page.wait_for_timeout(500)
            print("present scripture:", await page.evaluate("[...document.querySelectorAll('#manuscript .pb-scripture')].map(b => b.dataset.ref + ' | ' + b.querySelector('.pb-sc-body').textContent.slice(0,40))"))
            await page.click("#manuscript .pb-scripture .pb-sc-tab[data-v=LSB]"); await page.wait_for_timeout(300)
            print("present after LSB:", await page.evaluate("document.querySelector('#manuscript .pb-scripture .pb-sc-body').textContent.slice(0,40)"), "editor ver:", await page.evaluate("document.querySelector('#editor .pb-scripture').dataset.ver"))
            await page.screenshot(path=str(ROOT / "tests" / "out" / "sc2.png"))
            # settings
            await page.click("#btn-settings"); await page.wait_for_timeout(200)
            await page.screenshot(path=str(ROOT / "tests" / "out" / "sc3.png"))
            await page.check("#fav-KJV"); await page.uncheck("#fav-NASB"); await page.select_option("#set-def", "NKJV")
            await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(200)
            print("tabs after settings:", await page.evaluate("[...document.querySelector('#manuscript .pb-scripture').querySelectorAll('.pb-sc-tab')].map(t=>t.textContent)"))
            # analysis / sections sanity
            print("sections:", await page.evaluate("JSON.stringify(document.querySelector('#pos').textContent)"))
        print("errors", errs)
        await b.close()
asyncio.run(run(False)); asyncio.run(run(True))
