import asyncio, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, scheme in [(1400, "light"), (390, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        if r.request.url.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/"); await page.wait_for_timeout(800)
      tabs = await page.evaluate("[...document.querySelectorAll('.tab')].map(t=>t.textContent)")
      st = lambda: page.evaluate("[document.body.dataset.view, location.hash, [...document.querySelectorAll('#subtabs .subtab')].filter(b=>b.getAttribute('aria-selected')==='true').map(b=>b.textContent)[0], document.querySelector('.tab[aria-selected=true]').textContent, !document.querySelector('#subtabs').hidden]")
      print(w, "tabs", tabs, await st())
      await page.screenshot(path=str(OUT / f"sub_details_{w}.png"))
      await page.click("#subtabs .subtab[data-sub=edit]"); await page.wait_for_timeout(400); print(w, "edit", await st(), "editor visible", await page.is_visible("#editor"), "gutter", await page.evaluate("document.querySelectorAll('#gutter .g-item, #gutter > *').length"))
      await page.screenshot(path=str(OUT / f"sub_edit_{w}.png"))
      await page.click("#subtabs .subtab[data-sub=bindings]"); await page.wait_for_timeout(300); print(w, "bind", await st(), await page.is_visible("#bind-list"))
      await page.screenshot(path=str(OUT / f"sub_bind_{w}.png"))
      await page.click(".tab[data-view=present]"); await page.wait_for_timeout(300)
      await page.click(".tab[data-view=build]"); await page.wait_for_timeout(300); print(w, "back to build remembers", await st())
      await page.reload(); await page.wait_for_timeout(800); print(w, "after reload", await st())
      await page.goto("https://x.test/#edit"); await page.reload(); await page.wait_for_timeout(800); print(w, "#edit link", await st())
      print(w, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"), "errors", errs)
      await ctx.close()
asyncio.run(main())
