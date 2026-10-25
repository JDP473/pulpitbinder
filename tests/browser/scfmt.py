import asyncio, pathlib, base64, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); Object.defineProperty(window, 'S', { get: () => S }); window.__ed = ed; window.__writeSc = writeSc;\n})();")   # the served copy only, so the test can reach the open sermon
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__saved = null; window.claude = { use: async n => n === 'downloads' ? { save: async o => { window.__saved = { name: o.filename, b64: await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(o.data); }) }; } } : null };"""
TEXT = "{{1}} Alpha beta gamma delta. {{2}} Epsilon _zeta_ eta theta iota. {{3}} Kappa lambda mu nu."
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
      # a generic Scripture section in the manuscript, and a passage slide linked to it
      await page.evaluate("""(t => { const ed = window.__ed; const d = document.createElement('div'); window.__writeSc(d, { id: 'sctest', ref: 'Test 1:1-3', ver: 'ESV', texts: { ESV: { t, s: 'typed' } } }); ed.prepend(d); })(%s)""" % json.dumps(TEXT))
      await page.evaluate("document.querySelector('#editor').dispatchEvent(new Event('input'))"); await page.wait_for_timeout(600)
      print(w, "section", await page.evaluate("document.querySelectorAll('#editor .pb-scripture').length"))
      # a section drawn from its text, then select words in verse 1 and 2 and bold them
      await page.click("#editor .pb-scripture[data-id=sctest] .pb-sc-mk"); await page.wait_for_timeout(500)
      await page.click("#mk-kinds button:has-text('Passage')"); await page.wait_for_timeout(300)
      await page.select_option("#mk-f-per", "2"); await page.wait_for_timeout(200); await page.click("#mk-add"); await page.wait_for_timeout(500)
      print(w, "slides", await page.evaluate("S.slides.filter(s => s.made === 'scripture').map(s => [s.text, JSON.stringify(s.sc)])"))
      sel = """(([a, z]) => { const body = document.querySelector('#editor .pb-scripture[data-id=sctest] .pb-sc-body'); const tn = []; const w = document.createTreeWalker(body, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) if (!n.parentElement.closest('.vn')) tn.push(n);
        const find = (needle, from) => { for (const t of tn) { const i = t.textContent.indexOf(needle); if (i >= 0) return [t, i]; } };
        const [t1, i1] = find(a), [t2, i2] = find(z); const r = document.createRange(); r.setStart(t1, i1); r.setEnd(t2, i2 + z.length); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.dispatchEvent(new Event('selectionchange')); })"""
      await page.evaluate(sel, ["beta", "Epsilon"]); await page.wait_for_timeout(300)
      print(w, "toolbar", await page.evaluate("[!document.querySelector('#sc-fmt').hidden, document.querySelector('#sc-fmt').getBoundingClientRect().top > 0]"))
      await page.screenshot(path=str(OUT / f"scfmt_bar_{w}.png"))
      await page.click("#sc-fmt [data-f=b]"); await page.wait_for_timeout(300)
      print(w, "tokens", await page.evaluate("JSON.parse(document.querySelector('#editor .pb-scripture[data-id=sctest]').dataset.texts).ESV.t.replace(/[\\uE000-\\uE0FF]/g, c => '<' + (c.charCodeAt(0) - 0xE000).toString(16) + '>')"))
      print(w, "selection kept", await page.evaluate("getSelection().toString()"), "bar still", await page.evaluate("!document.querySelector('#sc-fmt').hidden"))
      await page.click("#sc-fmt [data-h=yellow]"); await page.wait_for_timeout(200); await page.click("#sc-fmt [data-f=u]"); await page.wait_for_timeout(300)
      print(w, "html", await page.evaluate("document.querySelector('#editor .pb-scripture[data-id=sctest] .pb-sc-body').innerHTML"))
      print(w, "slide now", await page.evaluate("S.slides.filter(s => s.made === 'scripture').map(s => JSON.stringify(s.text))"))
      await page.evaluate("document.querySelector('#editor .pb-scripture[data-id=sctest]').scrollIntoView({block:'center'})"); await page.wait_for_timeout(200)
      await page.screenshot(path=str(OUT / f"scfmt_done_{w}.png"))
      # toggle off bold, then clear
      await page.click("#sc-fmt [data-f=b]"); await page.wait_for_timeout(300)
      print(w, "bold off", await page.evaluate("JSON.stringify(JSON.parse(document.querySelector('#editor .pb-scripture[data-id=sctest]').dataset.texts).ESV.t)"))
      await page.click("#sc-fmt [data-f=clear]"); await page.wait_for_timeout(300)
      print(w, "cleared", await page.evaluate("JSON.parse(document.querySelector('#editor .pb-scripture[data-id=sctest]').dataset.texts).ESV.t === %s" % json.dumps(TEXT)))
      # undo puts it back
      await page.click("#sc-fmt [data-h=pink]"); await page.wait_for_timeout(300)
      # the present view and the slide column show the formatting
      if w == 1400:
        await page.evaluate("document.querySelector('#btn-save-pptx').click()"); await page.wait_for_function("window.__saved", timeout=60000); open(OUT / "scfmt.pptx", "wb").write(base64.b64decode(await page.evaluate("__saved.b64")))
      saved = await page.evaluate("S.slides.find(s => s.made === 'scripture').text"); print(w, "slide text", json.dumps(saved))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
