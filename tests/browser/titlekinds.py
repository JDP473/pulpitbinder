import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
SEL = """() => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const i = n.textContent.indexOf('Faith is walking'); if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 30); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w in [1400, 390]:
      ctx = await b.new_context(viewport={"width": w, "height": 900})
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        if r.request.url.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(900)
      # an H2 above the selection, so the section header picks it up
      await page.evaluate("(() => { const p = [...document.querySelectorAll('#editor p')].find(x => x.textContent.includes('That is frustrating')); const h = document.createElement('h2'); h.textContent = 'Enough Light for One Step'; p.before(h); document.querySelector('#editor').dispatchEvent(new Event('input')); })()"); await page.wait_for_timeout(500)
      for kind in ["Sermon title", "Section header"]:
        assert await page.evaluate(SEL); await page.wait_for_timeout(250)
        await page.click("#btn-make-slide"); await page.wait_for_timeout(200)
        print(w, "kinds", await page.evaluate("[...document.querySelectorAll('#mk-kinds .mk-kind b')].map(b=>b.textContent).join(', ')")) if kind == "Sermon title" else None
        await page.click(f"#mk-kinds button:has-text('{kind}')"); await page.wait_for_timeout(300)
        print(w, kind, await page.evaluate("[document.querySelector('#mk-f-kick').value, document.querySelector('#mk-f-ttl').value, document.querySelector('#mk-f-ref').value, [...document.querySelector('#mk-f-pic').options].map(o=>o.value).join('/')]"))
        if kind == "Section header":
          await page.select_option("#mk-f-pic", "own"); await page.wait_for_timeout(150); await page.set_input_files("#mk-f-img", str(FIX / "photo.jpg")); await page.wait_for_timeout(500)
          print(w, "own pic in preview", await page.evaluate("!!document.querySelector('#mk-preview .mk-hdr')"))
        await page.screenshot(path=str(OUT / f"tk_{kind.split()[0].lower()}_{w}.png"))
        await page.click("#mk-add"); await page.wait_for_timeout(400)
      print(w, "made", await page.evaluate("JSON.stringify(document.querySelectorAll('#editor .pb-slide').length)"), "errors", errs)
      await ctx.close()
asyncio.run(main())
