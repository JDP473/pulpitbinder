import asyncio, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
recs = [{"id": f"t{i}", "updatedAt": 1700000000000 + i, "meta": {"title": f"Sermon {i}", "text": "John 3:16", "when": f"2026-0{i%9+1}-05T10:00", "service": "Sunday AM", "place": "Bridge Creek church of Christ", "speaker": "Jarred Pettijohn", "wpm": 140, "series": s}, "html": "<p>Words.</p>", "slides": [], "manual": {}, "ai": None, "media": {}} for i, s in enumerate(["Faith series", "Faith series, Psalms", "Family", "Faith series", "Psalms, Prayer"])]
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
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(700)
      await page.evaluate("""recs => new Promise(res => { const q = indexedDB.open('pulpit-binder', 2); q.onupgradeneeded = () => { const d = q.result; if (!d.objectStoreNames.contains('sermons')) d.createObjectStore('sermons', { keyPath: 'id' }); if (!d.objectStoreNames.contains('kv')) d.createObjectStore('kv', { keyPath: 'k' }); }; q.onsuccess = () => { const tx = q.result.transaction('sermons','readwrite'); const st = tx.objectStore('sermons'); st.clear(); recs.forEach(r => st.put(r)); tx.oncomplete = res; }; })""", recs)
      await page.reload(); await page.wait_for_timeout(900)
      await page.evaluate("try{localStorage.setItem('pb-build-sub','details')}catch{}"); await page.goto("https://x.test/#build"); await page.reload(); await page.wait_for_timeout(800)
      pills = lambda: page.evaluate("[...document.querySelectorAll('#tag-pills .tag-pill')].map(p=>p.firstChild.textContent)")
      print(w, "start", await pills(), await page.evaluate("document.querySelector('#library').selectedOptions[0].text"))
      await page.click("#m-series"); await page.keyboard.type("fa"); await page.wait_for_timeout(150)
      print(w, "sugg", await page.evaluate("[...document.querySelectorAll('#tag-sugg .tag-opt')].map(o=>o.textContent)"))
      await page.screenshot(path=str(OUT / f"tags_sugg_{w}.png"))
      await page.keyboard.press("Tab"); await page.wait_for_timeout(100); print(w, "after tab", await pills(), "focus", await page.evaluate("document.activeElement.id"))
      await page.keyboard.type("Advent"); await page.keyboard.press("Enter"); await page.keyboard.type("hope, joy,"); await page.wait_for_timeout(100); print(w, "typed", await pills())
      await page.keyboard.press("Backspace"); print(w, "backspace", await pills())
      await page.click("#m-series"); await page.wait_for_timeout(100)
      opts = await page.query_selector_all("#tag-sugg .tag-opt"); 
      if opts: await opts[0].click(); await page.wait_for_timeout(100)
      print(w, "clicked", await pills(), "stored", await page.evaluate("document.querySelector('#tagbar').innerText.replace(/\\n/g,' | ')"))
      await page.click("#tag-pills .tag-pill >> nth=0 >> .tag-x"); print(w, "removed first", await pills())
      await page.keyboard.press("Tab"); print(w, "empty tab moves focus to", await page.evaluate("document.activeElement.id || document.activeElement.className"))
      await page.screenshot(path=str(OUT / f"tags_done_{w}.png"))
      print(w, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"), "errors", errs)
      await ctx.close()
asyncio.run(main())
