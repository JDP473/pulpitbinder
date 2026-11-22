# Adding a slide from highlighted words must leave the editor where it was: the page does not jump to the top,
# and the slide column and Bindings catch up on their own. Also checks the slide popup's Edit and Delete.
import asyncio, pathlib, json, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = "window.claude = { use: async n => null };"
# the paragraph to highlight, far enough down that the page must scroll to reach it
SEL = """(needle) => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { const i = n.textContent.indexOf(needle); if (i >= 0) { n.parentElement.scrollIntoView({ block: 'center' }); const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + needle.length); ed.focus({ preventScroll: true }); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch(); bad = 0
    for w, h, scheme in [(1400, 700, "light"), (1100, 700, "dark"), (390, 760, "light")]:
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, has_touch=w < 500); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
      tag = f"{w}{'d' if scheme == 'dark' else ''}"
      await page.evaluate("document.querySelector('#editor').dispatchEvent(new Event('input'))"); await page.wait_for_timeout(500)   # an edit makes the example sermon your own
      for k, needle in enumerate(["The word was given for exactly that night", "Ask one question: what is the next faithful step"]):
        assert await page.evaluate(SEL, needle)
        await page.wait_for_timeout(300)
        y0 = await page.evaluate("scrollY"); top0 = await page.evaluate("(n) => { const w = document.createTreeWalker(document.querySelector('#editor'), NodeFilter.SHOW_TEXT); let x; while ((x = w.nextNode())) { const i = x.textContent.indexOf(n); if (i >= 0) { const r = document.createRange(); r.setStart(x, i); r.setEnd(x, i + 3); return Math.round(r.getClientRects()[0].top); } } }", needle)
        await page.click("#btn-make-slide"); await page.wait_for_timeout(250)
        await page.click("#mk-kinds button:has-text('Quote')"); await page.wait_for_timeout(250)
        n0 = await page.evaluate("document.querySelectorAll('#editor .pb-slide').length")
        await page.click("#mk-add"); await page.wait_for_timeout(900)
        y1 = await page.evaluate("scrollY"); top1 = await page.evaluate("(n) => { const w = document.createTreeWalker(document.querySelector('#editor'), NodeFilter.SHOW_TEXT); let x; while ((x = w.nextNode())) { const i = x.textContent.indexOf(n); if (i >= 0) { const r = document.createRange(); r.setStart(x, i); r.setEnd(x, i + 3); return Math.round(r.getClientRects()[0].top); } } }", needle)
        n1 = await page.evaluate("document.querySelectorAll('#editor .pb-slide').length")
        thumbs = await page.evaluate("document.querySelectorAll('#gutter .g-thumb').length")
        caret = await page.evaluate("(n) => { const s = getSelection(); if (!s.rangeCount) return false; let e = s.anchorNode; e = e.nodeType === 1 ? e : e.parentElement; return document.activeElement.id === 'editor' && !!e.closest('#editor') && e.closest('#editor > *').textContent.includes(n); }", needle)
        moved = abs(top1 - top0)
        ok = y0 > 200 and moved < 60 and n1 == n0 + 1 and caret
        bad += not ok
        print(tag, f"slide {k+1}: scrollY {y0} -> {y1}, words' top {top0} -> {top1}, cues {n0} -> {n1}, gutter thumbs {thumbs}, caret in that paragraph {caret}", "OK" if ok else "JUMPED")
        await page.screenshot(path=str(OUT / f"keepscroll_{tag}_{k+1}.png"))
      if w > 640:   # editing a slide from the slide column's popup keeps the place too
        thumb = page.locator("#gutter .g-thumb").last; await thumb.click(); await page.wait_for_timeout(300)
        await page.click(".g-pop .btn.primary"); await page.wait_for_timeout(300)   # the test scrolls to reach the button; measure from here
        if await page.is_visible("#mk-step1"): await page.click("#mk-kinds button:has-text('Quote')"); await page.wait_for_timeout(300)
        y0 = await page.evaluate("scrollY")
        await page.click("#mk-add"); await page.wait_for_timeout(900)
        y1 = await page.evaluate("scrollY"); ok = abs(y1 - y0) < 60; bad += not ok
        print(tag, f"edit from popup: scrollY {y0} -> {y1}", "OK" if ok else "JUMPED")
      # the views out of sight while writing catch up on their own
      await page.click("#sub-details" if w > 700 else "#tab-build"); await page.wait_for_timeout(400)
      if w <= 700: await page.click("#sub-details"); await page.wait_for_timeout(400)
      made = await page.evaluate("[...document.querySelectorAll('#deck-status .deck-row')].map(r => r.textContent).find(t => t.includes('Made in Pulpit Binder')) || ''")
      await page.click("#sub-bindings"); await page.wait_for_timeout(400)
      nb = await page.evaluate("document.querySelectorAll('#bind-list .bind').length")
      ok = ("3 slides" if w > 640 else "2 slides") in made and nb > 0   # two added, plus one PowerPoint slide turned into a quote from the popup; bad += not ok
      print(tag, "details:", made[:60], "| bindings rows", nb, "OK" if ok else "STALE")
      print(tag, "errors", errs); bad += bool(errs)
      await ctx.close()
    sys.exit(1 if bad else 0)
if __name__ == "__main__": asyncio.run(main())
