import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
def rec(i, title, tags, when, body):
  return {"id": f"s{i}", "updatedAt": 1700000000000 + i, "meta": {"title": title, "text": "Psalm 23", "when": when, "service": "Sunday AM", "place": "Bridge Creek church of Christ", "speaker": "Jarred Pettijohn", "wpm": 140, "series": tags}, "html": body, "slides": [], "manual": {}, "ai": {"bigIdea": f"Big idea of {title}."} if i == 1 else None, "media": {}}
recs = [rec(1, "The Lord Is My Shepherd", "Psalms series", "2026-09-06T10:00", "<h2>He leads</h2><p>The shepherd goes before the sheep.</p><p>[slide]</p><p>He restores my soul.</p>"),
        rec(2, "Still Waters", "Psalms series, Comfort", "2026-09-13T10:00", "<h2>Rest</h2><p>He makes me lie down in green pastures.</p>"),
        rec(3, "A Table Before Me", "Psalms series", "2026-09-20T10:00", "<p>You prepare a table before me.</p>"),
        rec(4, "Unrelated", "", "2026-09-27T10:00", "<p>Other.</p>"),
        rec(5, "Comfort Ye", "Comfort", "2026-10-04T10:00", "<p>Comfort, comfort my people.</p>")]
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
      # open sermon 2 (Psalms series, Comfort)
      await page.select_option("#library", "s2"); await page.wait_for_timeout(500)
      vis = lambda: page.evaluate("!document.querySelector('#sub-series').hidden")
      print(w, "tab visible", await vis())
      await page.click("#sub-series"); await page.wait_for_timeout(500)
      st = lambda: page.evaluate("[location.hash, [...document.querySelectorAll('#ser-list .ser-item b')].map(b=>b.textContent), document.querySelector('#ser-count').textContent, (document.querySelector('#ser-read .ser-head h3')||{}).textContent, (document.querySelector('.ser-doc')||{}).innerText]")
      print(w, "all", await st())
      await page.click("#ser-tags .chip:has-text('Comfort')"); await page.wait_for_timeout(300); print(w, "comfort", await st())
      await page.click("#ser-tags .chip:has-text('All')"); await page.click("#ser-list .ser-item:has-text('Table')"); await page.wait_for_timeout(300); print(w, "pick", await st())
      await page.screenshot(path=str(OUT / f"series_{w}.png"), full_page=w < 500)
      await page.click("#ser-read .btn:has-text('Open this sermon')"); await page.wait_for_timeout(500)
      print(w, "opened", await page.evaluate("[document.body.dataset.view, location.hash, document.querySelector('#editor').innerText.slice(0,40), document.querySelector('#library').selectedOptions[0].text]"))
      await page.select_option("#library", "s4"); await page.wait_for_timeout(400); print(w, "untagged hides tab", not await vis())
      await page.select_option("#library", "s1"); await page.wait_for_timeout(300); await page.click("#sub-series"); await page.wait_for_timeout(300)
      # remove the tag while on the series tab -> goes back to details
      await page.click("#sub-details"); await page.wait_for_timeout(200)
      await page.click("#tag-pills .tag-x"); await page.wait_for_timeout(200); print(w, "removed tag, tab hidden", not await vis())
      print(w, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"), "errors", errs)
      await ctx.close()
asyncio.run(main())
