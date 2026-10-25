# The estimated sermon time stays in the header in every view, at desktop, tablet, and phone widths, and follows edits and pace changes.
import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
GO = "v => { const t = document.querySelector(`.tab[data-view='${v === 'edit' ? 'build' : v}']`); if (t) t.click(); if (v === 'edit') document.querySelector('#sub-edit').click(); }"
INIT = "window.claude = { use: async () => null };"
VIS = """() => { const p = document.querySelector('#est-pill'); const r = p.getBoundingClientRect(); const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const top = document.elementFromPoint(x, y); return { text: p.textContent.trim(), shown: r.width > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && !!top && p.contains(top) }; }"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch(); bad = 0
    for w, scheme in [(1440, "light"), (1024, "dark"), (390, "dark"), (390, "light")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
      for v in ["dash", "build", "edit", "study", "present", "materials", "analysis"]:
        await page.evaluate(GO, v); await page.wait_for_timeout(400)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)"); await page.wait_for_timeout(150)
        r = await page.evaluate(VIS); print(w, scheme, v, r)
        if not r["shown"] or not r["text"]: bad += 1
        if v in ("edit", "present"): await page.screenshot(path=str(OUT / f"esttime_{v}_{w}_{scheme}.png"))
      # edits and pace move it
      await page.evaluate(GO, "edit"); await page.wait_for_timeout(300)
      before = (await page.evaluate(VIS))["text"]
      await page.evaluate("() => { const ed = document.querySelector('#editor'); const p = document.createElement('p'); p.textContent = 'word '.repeat(1400); ed.append(p); ed.dispatchEvent(new Event('input')); }"); await page.wait_for_timeout(600)
      after = (await page.evaluate(VIS))["text"]
      await page.evaluate("() => { const x = document.querySelector('#m-wpm'); x.value = '100'; x.dispatchEvent(new Event('input')); }"); await page.wait_for_timeout(300)
      slower = (await page.evaluate(VIS))["text"]
      print(w, scheme, "edit", before, "->", after, "| pace 100 ->", slower)
      if before == after or after == slower: bad += 1
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]")); bad += len(errs)
      await ctx.close()
    print("RESULT", "all passed" if not bad else f"{bad} failures"); await b.close()
asyncio.run(main())
