import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """const smp = async () => ({text:''}); smp.json = async (p) => { window.__p = p; await new Promise(r=>setTimeout(r,300)); if (p.includes('write part of his sermon manuscript')) return {markdown:'The psalmist does not promise a floodlight.\\n\\nHe promises enough light for the next faithful step, and that is grace.'}; return {}; }; window.claude = { use: async n => n === 'sample' ? smp : null };"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w in [1400, 390]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        if r.request.url.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(900)
      sw = lambda: page.evaluate("Math.round(document.querySelector('.sg-col').getBoundingClientRect().width)")
      if w > 1200:
        before = await sw(); box = await page.query_selector("#sg-drag"); bb = await box.bounding_box()
        await page.mouse.move(bb["x"] + 5, bb["y"] + 200); await page.mouse.down(); await page.mouse.move(bb["x"] - 200, bb["y"] + 200, steps=8); await page.mouse.up(); await page.wait_for_timeout(200)
        print("drag", before, "->", await sw()); await page.reload(); await page.wait_for_timeout(800); print("after reload", await sw())
      # outline: add heading at end, then write
      await page.click("#side-tab-ol"); await page.wait_for_timeout(200)
      await page.fill("#ol-add-text", "Introduction"); await page.select_option("#ol-add-lv", "1"); await page.select_option("#ol-add-at", "end"); await page.click("#ol-add button[type=submit]"); await page.wait_for_timeout(300)
      print(w, "headings", await page.evaluate("[...document.querySelectorAll('#editor h1,#editor h2')].map(h=>h.tagName+':'+h.textContent)"))
      if w < 900: await page.evaluate("document.querySelector('.sg-col').classList.add('open')"); await page.wait_for_timeout(200)
      await page.click("#ol-list .ol-item.lv1 .ol-w"); await page.wait_for_timeout(200)
      await page.fill("#ol-gen-p", "Explain the lamp"); await page.click("#ol-gen-go"); await page.wait_for_timeout(700)
      print(w, "preview", await page.evaluate("document.querySelector('.ol-gen-prev') && document.querySelector('.ol-gen-prev').innerText"))
      await page.screenshot(path=str(OUT / f"side_gen_{w}.png"))
      await page.click("#ol-gen .btn.primary:has-text('Put it under')"); await page.wait_for_timeout(300)
      print(w, "after place", await page.evaluate("(() => { const h=[...document.querySelectorAll('#editor h1')].find(x=>x.textContent==='Introduction'); return [h.nextElementSibling.textContent.slice(0,40), h.nextElementSibling.nextElementSibling && h.nextElementSibling.nextElementSibling.textContent.slice(0,30)] })()"))
      await page.click("#sg-undo"); await page.wait_for_timeout(200); print(w, "undo ok", await page.evaluate("(() => { const h=[...document.querySelectorAll('#editor h1')].find(x=>x.textContent==='Introduction'); return !!h && (!h.nextElementSibling || !h.nextElementSibling.textContent.includes('floodlight')) })()"))
      # study tab
      await page.click("#side-tab-st"); await page.wait_for_timeout(400)
      if w < 900: await page.evaluate("document.querySelector('.sg-col').classList.add('open')"); await page.wait_for_timeout(300)
      print(w, "study in side", await page.evaluate("[document.querySelector('#study-box').parentElement.id, !document.querySelector('#side-st').hidden, document.querySelector('#st-ref').value]"))
      await page.screenshot(path=str(OUT / f"side_study_{w}.png"))
      await page.click(".tab[data-view=study]"); await page.wait_for_timeout(300)
      print(w, "study tab", await page.evaluate("[document.querySelector('#study-box').parentElement.id, document.body.dataset.view]"))
      await page.click(".tab[data-view=build]"); await page.wait_for_timeout(300)
      print(w, "back", await page.evaluate("[document.body.dataset.view, document.querySelector('#study-box').parentElement.id]"))
      print(w, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"), "errors", errs)
      await ctx.close()
asyncio.run(main())
