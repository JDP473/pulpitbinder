import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
exec(open("ol.py").read().split("async def run")[0])
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(**p.devices["iPhone 13"])
        page = await ctx.new_page()
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'><style>body{margin:0}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        for v in ["build","edit","present","analysis"]:
            await page.goto("https://x.test/#"+v); await page.wait_for_timeout(900)
            r = await page.evaluate("""() => { const W = document.documentElement.clientWidth; const out=[]; document.querySelectorAll('body *').forEach(e => { const r=e.getBoundingClientRect(); if (r.right > W + 1 && r.width>0) { let p=e.parentElement, clipped=false; while(p){ const o=getComputedStyle(p).overflowX; if(o!=='visible'){ if(p.getBoundingClientRect().right<=W+1){clipped=true;} break;} p=p.parentElement;} if(!clipped) out.push((e.id?'#'+e.id:e.tagName.toLowerCase()+'.'+e.className)+' '+Math.round(r.right)); } }); return [W, document.documentElement.scrollWidth, innerWidth, out.slice(0,8)]; }""")
            print(v, r)
        await b.close()
asyncio.run(main())
