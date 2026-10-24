import asyncio, pathlib, base64, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); window.__ed = ed; window.__writeSc = writeSc; window.__setView = setView; Object.defineProperty(window, 'S', { get: () => S });\n})();")   # the served copy only
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__saved = []; window.__copied = ''; window.claude = { use: async n => n === 'downloads' ? { save: async o => { window.__saved.push({ name: o.filename, size: o.data.size, b64: await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(o.data); }) }); } } : null }; navigator.clipboard.writeText = async t => { window.__copied = t; };"""
LONG = " ".join("{{%d}} %s" % (i, "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon.") for i in range(1, 15))
SHORT = "{{1}} Alpha beta gamma delta. {{2}} Epsilon _zeta_ eta theta iota kappa.\n{{3}} Lambda mu nu xi omicron."
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, scheme in [(1400, "light"), (390, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
      for sid, ref, texts in [("a1", "Test 1:1-3", {"ESV": {"t": SHORT, "s": "typed"}, "NKJV": {"t": "{{1}} Other words here.", "s": "typed"}}), ("a2", "Test 2:1-14", {"ESV": {"t": LONG, "s": "typed"}})]:
        await page.evaluate("""([id, ref, texts]) => { const d = document.createElement('div'); window.__writeSc(d, { id, ref, ver: 'ESV', texts }); window.__ed.prepend(d); }""", [sid, ref, texts])
      await page.evaluate("window.__setView('materials')"); await page.wait_for_timeout(1500)
      print(w, "sections", await page.evaluate("[...document.querySelectorAll('#mr-sec option')].map(o => o.textContent)"), "vers", await page.evaluate("[...document.querySelectorAll('#mr-ver option')].map(o => o.value)"), "picked", await page.evaluate("document.querySelector('#mr-sec').value"))
      await page.evaluate("document.querySelector('#mat-reading').scrollIntoView()"); await page.wait_for_timeout(300)
      await page.screenshot(path=str(OUT / f"reading_{w}.png"))
      await page.fill("#mr-note", "Please stand for the reading of God's word"); await page.wait_for_timeout(500)
      await page.select_option("#mr-sec", "a2"); await page.wait_for_timeout(700)   # a long passage shrinks to fit
      await page.evaluate("document.querySelector('#mr-prev').scrollIntoView()"); await page.screenshot(path=str(OUT / f"reading_long_{w}.png"))
      await page.select_option("#mr-sec", "a1"); await page.select_option("#mr-size", "half"); await page.wait_for_timeout(700)
      await page.screenshot(path=str(OUT / f"reading_half_{w}.png"))
      await page.select_option("#mr-ver", "NKJV"); await page.wait_for_timeout(500)
      await page.click("#mr-copy"); print(w, "copied", json.dumps(await page.evaluate("window.__copied")))
      await page.select_option("#mr-ver", "ESV"); await page.select_option("#mr-size", "full"); await page.wait_for_timeout(500)
      await page.click("#mr-copy"); print(w, "copied ESV", json.dumps(await page.evaluate("window.__copied")))
      await page.click("#mr-pdf"); await page.wait_for_function("window.__saved.length >= 1", timeout=20000)
      sv = await page.evaluate("window.__saved[0]"); print(w, "saved", sv["name"], sv["size"])
      if w == 1400: open(OUT / "reading.pdf", "wb").write(base64.b64decode(sv["b64"]))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
