import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); window.__lib = { store, blank, refreshLibrary }; Object.defineProperty(window, 'S', { get: () => S });\n})();")   # the served copy only
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = "window.claude = { use: async n => n === 'downloads' ? { save: async () => {} } : null };"
SEED = """async (n) => { const L = window.__lib; const topics = [['Walking by Faith', 'Hebrews 11:1-6', 'Faith, Hebrews'], ['The Lamp and the Path', 'Psalm 119:105-112', 'Psalms'], ['A Sower Went Out', 'Matthew 13:1-9', 'Parables'], ['Love One Another', '1 John 4:7-12', 'Epistles'], ['Born Again', 'John 3:1-8', 'Gospel of John'], ['The Good Shepherd', 'John 10:1-18', 'Gospel of John']];
  for (let i = 0; i < n; i++) { const r = L.blank(), t = topics[i % topics.length]; r.meta.title = t[0] + (i >= topics.length ? ' ' + (Math.floor(i / topics.length) + 1) : ''); r.meta.text = t[1]; r.meta.series = t[2]; r.meta.when = new Date(2026, 9 - (i % 9), 4 + (i % 20), 10, 0).toISOString().slice(0, 16); r.updatedAt = Date.now() - i * 86400000;
    r.transcript = 'Good morning. ' + (i % 4 === 0 ? 'The ancient lantern is a picture of patience. ' : 'We begin with a simple thought. ') + 'Let us read together and think about ' + t[0].toLowerCase() + '.'; r.html = '<p>' + r.transcript + '</p>'; await L.store.put(r); }
  await L.refreshLibrary(); }"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, h, scheme in [(1440, 900, "light"), (1024, 768, "light"), (390, 844, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(1200)
      await page.evaluate(SEED, 30); await page.wait_for_timeout(300)
      vis = lambda sel: page.evaluate("s => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; }", sel)
      print(w, "visible: card", await vis("#sermon-card"), "new button", await vis("#btn-new-top"), "title", await page.evaluate("document.querySelector('#sc-title').textContent"))
      await page.screenshot(path=str(OUT / f"sermons_side_{w}.png"))
      await page.click("#sermon-card"); await page.wait_for_timeout(300)
      print(w, "panel", await page.evaluate("[!document.querySelector('#sp-modal').hidden, document.activeElement.id, document.querySelectorAll('#sp-list .sp-item').length, document.querySelector('#sp-count').textContent, document.querySelectorAll('#sp-filters .chip').length]"))
      await page.screenshot(path=str(OUT / f"sermons_panel_{w}.png"))
      await page.keyboard.type("shepherd"); await page.wait_for_timeout(250)
      print(w, "search title", await page.evaluate("[...document.querySelectorAll('#sp-list .sp-t')].slice(0, 3).map(t => t.textContent)"), await page.evaluate("document.querySelector('#sp-count').textContent"))
      await page.fill("#sp-q", "john 3"); await page.wait_for_timeout(200)
      print(w, "search text", await page.evaluate("[...document.querySelectorAll('#sp-list .sp-t')].slice(0, 2).map(t => t.textContent)"))
      await page.fill("#sp-q", "lantern"); await page.wait_for_timeout(200)
      print(w, "search manuscript", await page.evaluate("document.querySelectorAll('#sp-list .sp-snip').length > 0"), await page.evaluate("document.querySelector('#sp-list .sp-snip') && document.querySelector('#sp-list .sp-snip').textContent.slice(0, 60)"))
      await page.screenshot(path=str(OUT / f"sermons_search_{w}.png"))
      await page.fill("#sp-q", "october faith"); await page.wait_for_timeout(200)
      print(w, "date and tag", await page.evaluate("[...document.querySelectorAll('#sp-list .sp-t')].length"))
      await page.fill("#sp-q", "shepherd"); await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter"); await page.wait_for_timeout(500)
      print(w, "opened second", await page.evaluate("[document.querySelector('#sp-modal').hidden, S.meta.title, document.querySelector('#sc-title').textContent]"))
      # keyboard shortcut and tag filter
      await page.keyboard.press("Control+k"); await page.wait_for_timeout(200)
      await page.click("#sp-filters .chip >> nth=0"); await page.wait_for_timeout(200)
      print(w, "tag filter", await page.evaluate("[document.querySelector('#sp-count').textContent, document.querySelector('#sp-filters .chip[aria-pressed=true]').textContent]"))
      await page.click("#sp-filters .chip[aria-pressed=true]"); await page.keyboard.press("Escape"); print(w, "esc", await page.evaluate("document.querySelector('#sp-modal').hidden"))
      # nothing matches: create from what was typed
      await page.click("#sermon-card"); await page.fill("#sp-q", "Romans 8:28-30"); await page.wait_for_timeout(200)
      print(w, "no match", await page.evaluate("document.querySelector('#sp-list .sp-none button').textContent")); await page.screenshot(path=str(OUT / f"sermons_none_{w}.png"))
      await page.keyboard.press("Enter"); await page.wait_for_timeout(500)
      print(w, "created from passage", await page.evaluate("[S.meta.title, S.meta.text, document.querySelector('#sp-modal').hidden, document.activeElement.id, document.querySelector('#sc-title').textContent]"))
      await page.click("#sermon-card"); await page.fill("#sp-q", "Gratitude in hard times"); await page.keyboard.press("Control+Enter"); await page.wait_for_timeout(500)
      print(w, "created from title", await page.evaluate("[S.meta.title, S.meta.text, window.__lib && 1]"))
      await page.click("#btn-new-top"); await page.wait_for_timeout(400)
      print(w, "new button", await page.evaluate("[S.meta.title, document.activeElement.id, document.querySelector('#view-build').hidden]"))
      await page.screenshot(path=str(OUT / f"sermons_new_{w}.png"))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
