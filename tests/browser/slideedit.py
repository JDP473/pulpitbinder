import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); Object.defineProperty(window, 'S', { get: () => S });\n})();")   # the served copy only, so the test can reach the open sermon
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
# Claude answers the slide kinds; Firecrawl answers Bible Gateway with generic words
INIT = """const smp = async () => ({ text: '' });
smp.json = async p => { await new Promise(r => setTimeout(r, 150));
  if (p.includes('one short, memorable')) return { text: 'Walk by the light you have.' };
  if (p.includes('double square brackets')) return { text: 'Faith is [[walking]] by the light you have.' };
  return {}; };
smp.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? smp : n === 'mcp' ? { callTool: async (srv, tool, input) => {
  const ref = decodeURIComponent((input.url.match(/search=([^&]+)/) || [])[1] || ''), m = ref.match(/:(\\d+)-(\\d+)$/), a = +m[1], z = +m[2], w = ['Alpha beta gamma.', 'Delta epsilon zeta.', 'Eta theta iota.', 'Kappa lambda mu.'];
  let md = ''; for (let v = a; v <= z; v++) md += v + ' ' + w[(v - a) % w.length] + ' ';
  return { payload: { markdown: md.trim() } }; } } : null };"""
SEL = """() => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const i = n.textContent.indexOf('Faith is walking'); if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, n.textContent.indexOf('path.', i) + 5); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""
DECK = "S.slides.map((s, i) => (i + 1) + ':' + (s.made || 'pptx'))"
CUES = "[...document.querySelectorAll('#editor .pb-slide')].filter(c => +c.dataset.n).every(c => +c.dataset.n >= 1 && +c.dataset.n + (+c.dataset.k || 1) - 1 <= S.slides.length)"
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
      shot = lambda name: page.screenshot(path=str(OUT / f"slideedit_{name}_{w}_{scheme}.png"))
      async def open_edit(n):   # slide n (1-based): the slide column beside the text on a computer, Bindings on a phone
        if w >= 900:
          await page.evaluate("document.querySelector('#sub-edit').click()"); await page.wait_for_timeout(400)
          await page.click(f"#gutter .g-thumb[aria-label^='Slide {n},']"); await page.wait_for_timeout(200)
          await page.click("#gutter .g-pop button.btn.primary"); await page.wait_for_timeout(300)
        else:
          await page.evaluate("document.querySelector('#sub-bindings').click()"); await page.wait_for_timeout(400)
          await page.evaluate(f"[...document.querySelectorAll('#bind-list .bind')].find(b => b.querySelector('select').value === '{n - 1}').querySelector('.side button.btn:not(.ghost)').click()"); await page.wait_for_timeout(300)
      async def save():
        label = await page.text_content("#mk-add"); await page.click("#mk-add"); await page.wait_for_timeout(400); return label
      # a quote slide from highlighted words
      assert await page.evaluate(SEL); await page.wait_for_timeout(250)
      await page.click("#btn-make-slide"); await page.wait_for_timeout(200)
      await page.click("#mk-kinds button:has-text('Quote')"); await page.wait_for_timeout(200); await page.click("#mk-add"); await page.wait_for_timeout(400)
      q = await page.evaluate("S.slides.findIndex(s => s.made === 'quote') + 1")
      print(w, "deck", await page.evaluate(DECK), "quote is slide", q)
      if w < 900:
        await page.evaluate("document.querySelector('#sub-bindings').click()"); await page.wait_for_timeout(400)
        await page.evaluate("[...document.querySelectorAll('#bind-list .bind')].find(b => b.querySelector('select').value === '2').scrollIntoView({ block: 'center' })"); await page.wait_for_timeout(300)
        await shot("bindings")
        # tapping a slide cue in Edit manuscript opens that slide
        await page.evaluate("document.querySelector('#sub-edit').click()"); await page.wait_for_timeout(400)
        await page.evaluate("[...document.querySelectorAll('#editor .pb-slide')].find(c => c.dataset.n === '3').scrollIntoView({ block: 'center' })"); await page.wait_for_timeout(200)
        await page.click("#editor .pb-slide[data-n='3']"); await page.wait_for_timeout(300)
        print(w, "cue tap opens", await page.evaluate("[document.querySelector('#mk-modal').hidden, document.querySelector('#mk-kind-title').textContent]"))
        await page.click("#mk-cancel2"); await page.wait_for_timeout(200)
      # 1. edit its words
      await open_edit(q)
      print(w, "edit opens", await page.evaluate("[document.querySelector('#mk-step2').hidden, document.querySelector('#mk-kind-title').textContent, document.querySelector('#mk-f-text').value.slice(0, 30), document.querySelector('#mk-add').textContent]"))
      await page.fill("#mk-f-text", "Faith takes the next step in the light it has."); await page.wait_for_timeout(200)
      await shot("edit")
      print(w, "saved", await save(), await page.evaluate(f"[S.slides.length, S.slides[{q} - 1].made, S.slides[{q} - 1].text]"))
      # 2. change the kind: Big idea, with Claude
      await open_edit(q); await page.click("#mk-back"); await page.wait_for_timeout(200)
      print(w, "kinds", await page.evaluate("[document.querySelector('#mk-title').textContent, document.querySelector('#mk-kinds .last b') && document.querySelector('#mk-kinds .last b').textContent, document.querySelector('#mk-note').textContent]"))
      await shot("kinds")
      await page.click("#mk-kinds button:has-text('Big idea')"); await page.wait_for_timeout(600)
      print(w, "to big idea", await save(), await page.evaluate(f"[S.slides.length, S.slides[{q} - 1].made, S.slides[{q} - 1].text]"))
      # 3. to Fill in the blank (two slides), then the answers slide back to a quote (one slide)
      n0 = await page.evaluate("S.slides.length")
      await open_edit(q); await page.click("#mk-back"); await page.wait_for_timeout(200)
      await page.click("#mk-kinds button:has-text('Fill in the blank')"); await page.wait_for_timeout(600)
      print(w, "to blanks", await save(), "deck", n0, "->", await page.evaluate("S.slides.length"), "cues ok", await page.evaluate(CUES))
      if w >= 900:
        await open_edit(q + 1)   # the answers slide opens the pair
        print(w, "pair opens as", await page.evaluate("[document.querySelector('#mk-kind-title').textContent, document.querySelector('#mk-add').textContent]"))
        await page.click("#mk-back"); await page.wait_for_timeout(200); await page.click("#mk-kinds button:has-text('Quote')"); await page.wait_for_timeout(300)
        print(w, "pair to quote", await save(), "deck", await page.evaluate("S.slides.length"), "cues ok", await page.evaluate(CUES))
      # 4. undo puts the last change back
      before = await page.evaluate(DECK)
      await page.evaluate("document.querySelector('#sg-undo').click()"); await page.wait_for_timeout(400)
      print(w, "undo", before, "->", await page.evaluate(DECK))
      # 5. a slide read from the PowerPoint becomes a main point slide, keeping its speaker notes
      await open_edit(1)
      print(w, "pptx slide", await page.evaluate("[document.querySelector('#mk-step1').hidden, document.querySelector('#mk-title').textContent, document.querySelector('#mk-src').textContent.slice(0, 40)]"))
      await page.click("#mk-kinds button:has-text('Quote')"); await page.wait_for_timeout(300)
      print(w, "pptx to quote", await save(), await page.evaluate("[S.slides[0].made, S.slides[0].text, S.slides[0].notes]"))
      # 6. a passage slide: two verses become one each, then one becomes a key verse
      if w >= 900:
        await page.evaluate("document.querySelector('#sub-edit').click()"); await page.wait_for_timeout(300)
        await page.evaluate("""() => { const p = [...document.querySelectorAll('#editor p')].filter(p => p.textContent.trim().length > 40).pop(); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); }""")
        await page.keyboard.type(" John 3:16-19"); await page.keyboard.press("Tab")
        await page.wait_for_function("S.slides.filter(s => s.made === 'scripture').length === 2", timeout=5000); await page.wait_for_timeout(400)
        sc = await page.evaluate("S.slides.findIndex(s => s.made === 'scripture') + 1")
        await open_edit(sc)
        print(w, "passage opens", await page.evaluate("[document.querySelector('#mk-kind-title').textContent, document.querySelector('#mk-f-per').value]"))
        await page.select_option("#mk-f-per", "1"); await page.wait_for_timeout(200)
        print(w, "one verse each", await save(), await page.evaluate("S.slides.filter(s => s.made === 'scripture').map(s => s.ref)"))
        await open_edit(sc + 1); await page.click("#mk-back"); await page.wait_for_timeout(200); await page.click("#mk-kinds button:has-text('Key verse')"); await page.wait_for_timeout(300)
        print(w, "key verse", await save(), await page.evaluate(f"(s => [s.made, s.ref, s.text, s.sc && s.sc.a])(S.slides[{sc}])"), "linked", await page.evaluate(f"!!document.querySelector(`#editor .pb-scripture[data-id='${{S.slides[{sc}].sc.id}}']`)"))
        await page.evaluate("document.querySelector('#editor .pb-scripture').scrollIntoView({ block: 'center' })"); await page.wait_for_timeout(400)
        await shot("column")
      print(w, "deck", await page.evaluate(DECK), "cues ok", await page.evaluate(CUES))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
    await b.close()
asyncio.run(main())
