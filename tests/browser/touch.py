"""Phone touch-comfort check: iPhone 13 viewport, light and dark, tap target size and 16px fields."""
import asyncio, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"
CHECK = """() => { const small=[], zoom=[]; document.querySelectorAll('button,a[href],select,input,textarea,[role=tab]').forEach(e=>{
  const r=e.getBoundingClientRect(), cs=getComputedStyle(e); if(!r.width||!r.height||!e.checkVisibility({checkVisibilityCSS:true})) return;
  const n=(e.id?'#'+e.id:e.tagName.toLowerCase()+'.'+(e.className||'').toString().split(' ')[0])+' '+Math.round(r.width)+'x'+Math.round(r.height);
  if(Math.min(r.width,r.height)<32) small.push(n);
  if(['INPUT','SELECT','TEXTAREA'].includes(e.tagName)&&parseFloat(cs.fontSize)<16&&!['checkbox','radio','range','color','file'].includes(e.type)) zoom.push(n); });
  return {small, zoom, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth}; }"""
async def main():
    bad = 0
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for scheme in ["light", "dark"]:
            ctx = await b.new_context(**p.devices["iPhone 13"], color_scheme=scheme)
            page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            async def route(r):
                u = r.request.url
                if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
                elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>" + HTML + "</body></html>", content_type="text/html")
                else: await r.abort()
            await page.route("**/*", route)
            await page.goto("https://x.test/"); await page.wait_for_timeout(700)
            for v in ["dash", "build", "study", "edit", "present", "analysis"]:
                await page.click("#tab-" + v); await page.wait_for_timeout(450)
                r = await page.evaluate(CHECK)
                print(scheme, v, "overflow", r["overflow"], "small", r["small"][:6], "zoom", r["zoom"][:4])
                bad += r["overflow"] > 0 or len(r["zoom"])
                if v in ("build", "present", "study"): await page.screenshot(path=str(OUT / f"touch_{v}_{scheme}.png"))
            print(scheme, "errors", errs); bad += len(errs)
            await ctx.close()
        await b.close()
    sys.exit(1 if bad else 0)
asyncio.run(main())
