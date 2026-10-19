import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
async def run(mobile):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(**(p.devices["iPhone 13"] if mobile else {"viewport": {"width": 1400, "height": 900}}))
        page = await ctx.new_page(); errs=[]
        page.on("pageerror", lambda e: errs.append(str(e)))
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.goto("https://x.test/#build"); await page.wait_for_timeout(700)
        await page.set_input_files("#file-pptx", str(FIX / "deck.pptx")); await page.wait_for_timeout(1200)
        await page.set_input_files("#file-text", "outline.md"); await page.wait_for_timeout(600)
        await page.click("#tab-edit"); await page.wait_for_timeout(400)
        if mobile:
            print("sheet box", await page.evaluate("JSON.stringify([document.querySelector('.sg-col').getBoundingClientRect(), document.querySelector('#side-tab-ol').getBoundingClientRect(), innerHeight, getComputedStyle(document.querySelector('.sg-col')).zIndex, getComputedStyle(document.querySelector('.sg-col')).position])"))
            await page.screenshot(path=str(ROOT / "tests" / "out" / "olm0.png"))
        await page.click("#side-tab-ol"); await page.wait_for_timeout(400)
        items = await page.evaluate("[...document.querySelectorAll('#ol-list .ol-item')].map(r => r.querySelector('.ol-num').textContent + ' ' + r.querySelector('.ol-txt').textContent + ' | ' + r.querySelector('.ol-meta').textContent)")
        print("mobile" if mobile else "desktop", json.dumps(items, indent=0))
        print("summary:", await page.text_content("#ol-summary"))
        await page.screenshot(path=("olm" if mobile else "old")+".png")
        if not mobile:
            # move "A lamp only helps" (k index) up
            k = await page.evaluate("[...document.querySelectorAll('#ol-list .ol-item')].findIndex(r => r.textContent.includes('only helps'))")
            await page.hover(f"#ol-list .ol-item:nth-child({k+1})")
            await page.click(f"#ol-list .ol-item:nth-child({k+1}) .ol-act button:nth-child(1)"); await page.wait_for_timeout(300)
            print("after move up:", await page.evaluate("[...document.querySelectorAll('#ol-list .ol-item')].map(r => r.querySelector('.ol-num').textContent + ' ' + r.querySelector('.ol-txt').textContent)"))
            hs = await page.evaluate("[...document.querySelectorAll('#editor > h1, #editor > h2, #editor > h3, #editor > h4')].map(h=>h.tagName+':'+h.textContent)")
            print("editor headings:", hs)
            await page.click("#sg-undo"); await page.wait_for_timeout(300)
            print("after undo:", await page.evaluate("[...document.querySelectorAll('#editor > h2')].map(h=>h.textContent)"))
            # jump
            await page.click("#ol-list .ol-item.lv1:last-child .ol-link") if False else None
            last = await page.evaluate("document.querySelectorAll('#ol-list .ol-item').length")
            await page.click(f"#ol-list .ol-item:nth-child({last}) .ol-link"); await page.wait_for_timeout(900)
            print("on:", await page.evaluate("document.querySelector('#ol-list .ol-item.on .ol-txt')?.textContent"), "scrollY", await page.evaluate("scrollY"))
            await page.screenshot(path=str(ROOT / "tests" / "out" / "old2.png"))
        else:
            await page.click("#side-tab-sg"); await page.wait_for_timeout(300)
            await page.screenshot(path=str(ROOT / "tests" / "out" / "olm1.png"))
            await page.click("#side-tab-ol"); await page.wait_for_timeout(300)
            print("sheet open after switching tabs?", await page.evaluate("document.querySelector('.sg-col').classList.contains('open')"))
            await page.wait_for_timeout(400)
            await page.screenshot(path=str(ROOT / "tests" / "out" / "olm2.png"))
        print("errors", errs)
        await b.close()
asyncio.run(run(False)); asyncio.run(run(True))
