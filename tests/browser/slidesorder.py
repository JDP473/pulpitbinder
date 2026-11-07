# The Slides tab under Write: thumbnails in deck order, reordered by mouse drag, a finger's long press and drag, the arrow
# buttons, and Alt with an arrow key. A numbered slide cue in the manuscript must follow its slide, and Undo puts the order back.
import asyncio, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = "window.claude = { use: async n => null };"
TITLES = "[...document.querySelectorAll('#sl-grid .sl-card .sl-t')].map(e => e.textContent)"
CUE = "(() => { const c = document.querySelector('#editor .pb-slide[data-n]'); return c ? +c.dataset.n : null; })()"
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch(); bad = 0
    def check(tag, what, ok, extra=""):
      nonlocal bad; bad += not ok; print(tag, what, "OK" if ok else "FAIL", extra)
    for w, h, scheme in [(1400, 900, "light"), (1100, 800, "dark"), (390, 800, "light")]:
      phone = w < 500
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, has_touch=phone, is_mobile=phone); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(1000)
      await page.set_input_files("#file-pptx", str(FIX / "deck.pptx")); await page.wait_for_timeout(2500)
      # a numbered cue for slide 5 at the top of the manuscript
      await page.evaluate("""(() => { const ed = document.querySelector('#editor'); ed.insertAdjacentHTML('afterbegin', '<div class="pb-slide" contenteditable="false" data-n="5">SLIDE 5</div>'); ed.dispatchEvent(new Event('input')); })()""")
      await page.wait_for_timeout(600)
      await page.click("#sub-slides"); await page.wait_for_timeout(900)
      tag = f"{w}{'d' if scheme == 'dark' else ''}"
      t0 = await page.evaluate(TITLES); n = len(t0)
      check(tag, f"{n} thumbnails in order", n == 12 and t0[0] != t0[4], str(t0[:5]))
      await page.screenshot(path=str(OUT / f"slidesorder_{tag}.png"))
      cards = page.locator("#sl-grid .sl-card")
      if not phone:   # mouse: drag slide 5 in front of slide 1
        a = await cards.nth(4).bounding_box(); z = await cards.nth(0).bounding_box()
        await page.mouse.move(a["x"] + a["width"] / 2, a["y"] + 40); await page.mouse.down()
        await page.mouse.move(a["x"] + a["width"] / 2 - 20, a["y"] + 40, steps=4)
        await page.mouse.move(z["x"] + 10, z["y"] + 40, steps=12); await page.wait_for_timeout(150)
        await page.screenshot(path=str(OUT / f"slidesorder_drag_{tag}.png"))
        await page.mouse.up(); await page.wait_for_timeout(500)
      else:
        # a quick swipe over the slides scrolls the page and moves nothing
        cdp0 = await ctx.new_cdp_session(page); a = await cards.nth(2).bounding_box(); y0s = await page.evaluate("scrollY")
        await cdp0.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 200, "y": a["y"] + 60}]})
        for k in range(1, 12): await cdp0.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": 200, "y": a["y"] + 60 - k * 25}]}); await page.wait_for_timeout(16)
        await cdp0.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); await page.wait_for_timeout(500)
        check(tag, "a swipe scrolls instead of dragging", await page.evaluate("scrollY") > y0s and await page.evaluate(TITLES) == t0)
        # finger: hold slide 5, then drag it up to the first slide (the page scrolls along the way)
        await cards.nth(4).scroll_into_view_if_needed(); a = await cards.nth(4).bounding_box()
        cdp = await ctx.new_cdp_session(page); x, y = a["x"] + a["width"] / 2, a["y"] + 40
        await cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]}); await page.wait_for_timeout(450)
        for k in range(60):
          y2 = max(90, y - k * 25); await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y2}]}); await page.wait_for_timeout(30)
        for k in range(40):   # hold near the top while the page scrolls up to the first slide
          await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": 60 + (k % 2)}]}); await page.wait_for_timeout(40)
        z = await cards.nth(0).bounding_box()
        await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": z["y"] + 20}]}); await page.wait_for_timeout(100)
        await page.screenshot(path=str(OUT / f"slidesorder_drag_{tag}.png"))
        await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); await page.wait_for_timeout(500)
      t1 = await page.evaluate(TITLES); cue = await page.evaluate(CUE)
      check(tag, "drag moved slide 5 to the front", t1[0] == t0[4] and t1[1] == t0[0] and len(t1) == n, str(t1[:3]))
      check(tag, "the slide 5 cue follows it", cue == 1, f"cue now {cue}")
      # arrows: the first slide one place later
      await cards.nth(0).locator("button[aria-label='Move later']").click(); await page.wait_for_timeout(400)
      t2 = await page.evaluate(TITLES); cue = await page.evaluate(CUE)
      check(tag, "arrow moves it later", t2[1] == t0[4] and t2[0] == t0[0] and cue == 2, f"cue {cue}")
      # keyboard: Alt and Left puts it back first
      await cards.nth(1).focus(); await page.keyboard.press("Alt+ArrowLeft"); await page.wait_for_timeout(1800)   # past the background redraw
      t3 = await page.evaluate(TITLES); focused = await page.evaluate("document.activeElement.dataset.i")
      check(tag, "Alt+Left moves it back, focus follows", t3[0] == t0[4] and focused == "0")
      # undo three times: the original order and cue
      for _ in range(3): await page.click("#sl-undo"); await page.wait_for_timeout(300)
      t4 = await page.evaluate(TITLES); cue = await page.evaluate(CUE)
      check(tag, "Undo restores order and cue", t4 == t0 and cue == 5, f"cue {cue}")
      # the manuscript's slide column agrees
      await page.click("#sub-edit"); await page.wait_for_timeout(800)
      lbl = await page.evaluate("document.querySelector('#editor .pb-slide[data-n]').textContent")
      check(tag, "cue label in the editor", lbl.startswith("SLIDE 5"), lbl[:40])
      sw = await page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
      check(tag, "no sideways scroll", sw[0] <= sw[1], str(sw))
      check(tag, "no errors", not errs, str(errs[:2]))
      await ctx.close()
    sys.exit(1 if bad else 0)
asyncio.run(main())
