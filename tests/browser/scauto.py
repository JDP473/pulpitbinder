import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); Object.defineProperty(window, 'S', { get: () => S });\n})();")   # the served copy only, so the test can reach the open sermon
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
# Firecrawl answers with generic print-view markdown, numbered from the reference's first verse; a reference with "Jude" fails to load
INIT = """window.__fail = false; window.claude = { use: async n => n === 'mcp' ? { callTool: async (srv, tool, input) => {
  await new Promise(r => setTimeout(r, 300));
  const ref = decodeURIComponent((input.url.match(/search=([^&]+)/) || [])[1] || '');
  if (window.__fail || /Jude/.test(ref)) throw { code: 'parse' };
  const m = ref.match(/:(\\d+)-(\\d+)$/) || ref.match(/:(\\d+)()$/), a = +m[1], z = +(m[2] || m[1]), w = ['Alpha beta gamma.', 'Delta epsilon zeta.', 'Eta theta iota.', 'Kappa lambda mu.', 'Nu xi omicron.', 'Pi rho sigma.'];
  let md = ''; for (let v = a; v <= z; v++) md += v + ' ' + w[(v - a) % w.length] + ' ';
  return { payload: { markdown: md.trim() } }; } } : null };"""
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
      made = "(id => S.slides.map((s, i) => [i + 1, s.sc && s.sc.id === id ? s.ref : null]).filter(x => x[1]))"
      before = await page.evaluate("S.slides.length")
      cues = "[...document.querySelectorAll('#editor .pb-slide')].filter(c => +c.dataset.n).every(c => +c.dataset.n + (+c.dataset.k || 1) - 1 <= S.slides.length)"
      print(w, "cues in range at the start", await page.evaluate(cues))
      # 1. type a reference at the end of a paragraph and press Tab
      await page.evaluate("""() => { const p = [...document.querySelectorAll('#editor p')].find(p => p.textContent.trim().length > 40); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); }""")
      await page.keyboard.type(" John 3:16-19"); await page.keyboard.press("Tab")
      await page.wait_for_function("document.querySelector('#editor .pb-scripture') && JSON.parse(document.querySelector('#editor .pb-scripture').dataset.texts).ESV", timeout=5000); await page.wait_for_timeout(300)
      id1 = await page.evaluate("document.querySelector('#editor .pb-scripture').dataset.id")
      print(w, "tab: slides", await page.evaluate(made, id1), "deck", before, "->", await page.evaluate("S.slides.length"))
      print(w, "tab: cue right before the section", await page.evaluate("(id => { const e = document.querySelector(`#editor .pb-scripture[data-id='${id}']`); const c = e.previousElementSibling; return c && c.classList.contains('pb-slide') ? [c.dataset.n, c.dataset.k || '1'] : null; })", id1))
      print(w, "tab: slide text", await page.evaluate("(id => S.slides.filter(s => s.sc && s.sc.id === id).map(s => s.text))", id1))
      await page.evaluate("(id => document.querySelector(`#editor .pb-scripture[data-id='${id}']`).scrollIntoView({ block: 'center' }))", id1); await page.wait_for_timeout(500)
      await page.screenshot(path=str(OUT / f"scauto_tab_{w}_{scheme}.png"))
      # undo takes the new slides back off, and leaves the section
      await page.keyboard.press("Control+z"); await page.wait_for_timeout(400)
      print(w, "undo: slides", await page.evaluate(made, id1), "section kept", await page.evaluate("(id => !!document.querySelector(`#editor .pb-scripture[data-id='${id}']`))", id1))
      await page.keyboard.press("Control+Shift+z"); await page.wait_for_timeout(400)
      print(w, "redo: slides", await page.evaluate(made, id1))
      # 2. the + Scripture button on the toolbar
      if w >= 900:
        await page.click("#tb-scripture"); await page.fill("#sc-pop-ref", "Romans 8:28-30"); await page.press("#sc-pop-ref", "Enter")
        await page.wait_for_function("[...document.querySelectorAll('#editor .pb-scripture')].some(e => e.dataset.ref === 'Romans 8:28-30' && JSON.parse(e.dataset.texts).ESV)", timeout=5000); await page.wait_for_timeout(300)
        id2 = await page.evaluate("[...document.querySelectorAll('#editor .pb-scripture')].find(e => e.dataset.ref === 'Romans 8:28-30').dataset.id")
        print(w, "toolbar: slides", await page.evaluate(made, id2))
      # 3. a passage that fails to load gets its slides once the text is pasted
      await page.evaluate("""() => { const p = [...document.querySelectorAll('#editor p')].filter(p => p.textContent.trim().length > 40).pop(); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); }""")
      await page.keyboard.type(" Jude 1:20-21"); await page.keyboard.press("Tab")
      await page.wait_for_selector("#editor .pb-scripture[data-ref='Jude 1:20-21'] .pb-sc-err", timeout=5000)
      id3 = await page.evaluate("document.querySelector(\"#editor .pb-scripture[data-ref='Jude 1:20-21']\").dataset.id")
      print(w, "failed load: slides", await page.evaluate(made, id3))
      await page.click("#editor .pb-scripture[data-ref='Jude 1:20-21'] [data-act=paste]")
      await page.fill("#editor .pb-scripture[data-ref='Jude 1:20-21'] textarea", "20 Generic words for the test. 21 More generic words here.")
      await page.click("#editor .pb-scripture[data-ref='Jude 1:20-21'] .pb-sc-paste + p button"); await page.wait_for_timeout(400)
      print(w, "pasted: slides", await page.evaluate(made, id3))
      # 4. making slides by hand still works beside the automatic ones
      await page.click("#editor .pb-scripture[data-ref='Jude 1:20-21'] [data-act=slides]"); await page.wait_for_timeout(300)
      await page.click("#mk-kinds button:has-text('Key verse')"); await page.wait_for_timeout(200); await page.click("#mk-add"); await page.wait_for_timeout(300)
      print(w, "key verse too", await page.evaluate("(id => S.slides.filter(s => s.sc && s.sc.id === id).map(s => s.made))", id3))
      await page.evaluate("document.querySelector(\"#editor .pb-scripture[data-ref='Jude 1:20-21']\").scrollIntoView({ block: 'center' })"); await page.wait_for_timeout(500)
      await page.screenshot(path=str(OUT / f"scauto_paste_{w}_{scheme}.png"))
      # cue numbers still match the deck: every cue points at a slide that exists
      print(w, "cues in range", await page.evaluate(cues))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
    # without Firecrawl or Claude: the section says why, no slides, no errors
    ctx = await b.new_context(viewport={"width": 1400, "height": 900}); await ctx.add_init_script("window.claude = { use: async () => null };")
    page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    async def route2(r):
      u = r.request.url
      if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
      elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
      else: await r.abort()
    await page.route("**/*", route2)
    await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
    n0 = await page.evaluate("S.slides.length")
    await page.evaluate("""() => { const p = [...document.querySelectorAll('#editor p')].find(p => p.textContent.trim().length > 40); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); }""")
    await page.keyboard.type(" John 3:16-19"); await page.keyboard.press("Tab"); await page.wait_for_selector("#editor .pb-scripture .pb-sc-err", timeout=5000)
    print("offline: deck", n0, "->", await page.evaluate("S.slides.length"), "errors", errs)
    await b.close()
asyncio.run(main())
