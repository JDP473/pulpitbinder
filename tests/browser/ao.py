import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
INIT = """
window.__prompt = null;
const s = async () => ({text:''}); s.json = async (p) => { window.__prompt = p; await new Promise(r=>setTimeout(r,200));
  return {outline:[{before:1,level:1,text:'Introduction'},{before:2,level:1,text:'The Lamp We Carry'},{before:2,level:2,text:'Enough light for the next step'},{before:4,level:2,text:'A lamp only helps if you carry it'},{before:5,level:2,text:'The lamp is for the dark'},{before:6,level:1,text:'Invitation'},{before:99,level:2,text:'bogus'}]}; };
s.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? s : null };
"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1400, "height": 900}); await ctx.add_init_script(INIT)
        page = await ctx.new_page(); errs=[]; page.on("pageerror", lambda e: errs.append(str(e)))
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.goto("https://x.test/#edit"); await page.wait_for_timeout(900)
        await page.click("#side-tab-ol"); await page.wait_for_timeout(200)
        await page.click("#btn-ao"); await page.wait_for_timeout(700)
        print("prompt has paragraphs:", (await page.evaluate("__prompt"))[-300:].replace("\n"," | ")[:200])
        print("preview rows:", await page.evaluate("[...document.querySelectorAll('.ao-row')].map(r=>r.querySelector('.ol-num').textContent+' '+r.querySelector('.ao-txt').value+' ['+r.querySelector('.ao-snip').textContent.slice(0,30)+']')"))
        await page.screenshot(path=str(ROOT / "tests" / "out" / "ao1.png"))
        await page.fill("#ao-tx-2", "Enough light for the next faithful step")
        await page.click(".ao-preview .btn.primary"); await page.wait_for_timeout(400)
        print("editor headings:", await page.evaluate("[...document.querySelectorAll('#editor > h1, #editor > h2')].map(h=>h.tagName+':'+h.textContent+' -> '+h.nextElementSibling.textContent.slice(0,25))"))
        print("outline:", await page.evaluate("[...document.querySelectorAll('#ol-list .ol-item')].map(r=>r.querySelector('.ol-num').textContent+' '+r.querySelector('.ol-txt').textContent)"))
        await page.screenshot(path=str(ROOT / "tests" / "out" / "ao2.png"))
        await page.click("#sg-undo"); await page.wait_for_timeout(300)
        print("after undo headings:", await page.evaluate("document.querySelectorAll('#editor > h1, #editor > h2').length"))
        await page.click("#btn-ao-slides"); await page.wait_for_timeout(300)
        print("slides rows:", await page.evaluate("[...document.querySelectorAll('.ao-row')].map(r=>r.querySelector('.ao-txt').value)"))
        print("errors", errs)
        await b.close()
asyncio.run(main())
