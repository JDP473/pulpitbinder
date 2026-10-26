"""The sermon card, New sermon, sync, and More menu at the top of the side column, with the More menu open:
on a computer, a narrower window, and a phone, in light and dark. Screenshots go to tests/out/libmenu_*."""
import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = "window.claude = { use: async n => null };"
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, h, scheme in [(1400, 900, "light"), (1400, 900, "dark"), (1180, 820, "light"), (390, 844, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/"); await page.wait_for_timeout(1000)
      await page.screenshot(path=str(OUT / f"libmenu_closed_{w}_{scheme}.png"))
      await page.click("#btn-sermon"); await page.wait_for_timeout(250)
      box = await page.evaluate("(m => { const r = m.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.width), innerWidth]; })(document.querySelector('#sermon-menu'))")
      print(w, scheme, "menu left/right/width/viewport", box, "inside", box[0] >= 0 and box[1] <= box[3])
      await page.screenshot(path=str(OUT / f"libmenu_open_{w}_{scheme}.png"))
      await page.keyboard.press("Escape"); await page.wait_for_timeout(150)
      print(w, scheme, "closed by Escape", await page.evaluate("document.querySelector('#sermon-menu').hidden"), "focus back", await page.evaluate("document.activeElement && document.activeElement.id"))
      print(w, scheme, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
    await b.close()
asyncio.run(main())
