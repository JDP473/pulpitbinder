import asyncio, pathlib, json, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
async def run(mobile):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(**(p.devices["iPhone 13"] if mobile else {"viewport": {"width": 1400, "height": 900}}))
        page = await ctx.new_page()
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'></head><body>"+HTML+"</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.goto("https://x.test/#build")
        await page.wait_for_timeout(800)
        await page.set_input_files("#file-pptx", str(FIX / "deck.pptx"))
        await page.wait_for_timeout(1500)
        await page.set_input_files("#file-text", "long.txt")
        await page.wait_for_timeout(800)
        await page.click("#tab-present"); await page.wait_for_timeout(800)
        await page.evaluate("""() => { window.__gaps=[]; window.__lt=[]; let last=performance.now(); const f=t=>{ __gaps.push(t-last); last=t; requestAnimationFrame(f)}; requestAnimationFrame(f);
           new PerformanceObserver(l=>l.getEntries().forEach(e=>__lt.push(Math.round(e.duration)))).observe({type:'longtask',buffered:true});
           window.__st=[]; const ms=document.querySelector('#manuscript'); ms.addEventListener('scroll',()=>__st.push([Math.round(performance.now()), ms.scrollTop]),{passive:true}); }""")
        await page.evaluate("() => { __lt.length = 0; __gaps.length = 0; }")
        dims = await page.evaluate("() => [document.documentElement.scrollHeight, innerHeight, document.querySelector('#manuscript').clientHeight]")
        print("page/viewport/manuscript heights", dims)
        box = await page.eval_on_selector("#manuscript", "e => { const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2] }")
        await page.mouse.move(*box)
        if mobile:
            cdp = await ctx.new_cdp_session(page)
            print("at point:", await page.evaluate(f"() => {{ const e = document.elementFromPoint({int(box[0])}, {int(box[1])}); return e && (e.id || e.className || e.tagName); }}"), box)
            for i in range(12):
                await cdp.send("Input.synthesizeScrollGesture", {"x": int(box[0]), "y": int(box[1]), "yDistance": -600, "speed": 1600, "gestureSourceType": "touch"})
        else:
            for i in range(120):
                await page.mouse.wheel(0, 60); await page.wait_for_timeout(16)
        await page.wait_for_timeout(500)
        r = await page.evaluate("() => { const g=__gaps.slice(5); g.sort((a,b)=>b-a); const st=__st; let back=0; for(let i=1;i<st.length;i++) if(st[i][1]<st[i-1][1]-1) back++; return {worst:g.slice(0,8).map(Math.round), over50:g.filter(x=>x>50).length, frames:g.length, longtasks:__lt, backjumps:back, pos:document.querySelector('#pos').textContent, scrollTop:document.querySelector('#manuscript').scrollTop, pageScrollY: scrollY} }")
        print("mobile" if mobile else "desktop", json.dumps(r))
        await page.screenshot(path=("m" if mobile else "d")+".png")
        await b.close()
asyncio.run(run(False)); asyncio.run(run(True))
