import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
INIT = "window.claude = { use: async n => n === 'downloads' ? { save: async () => {} } : null };"
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch(); ctx = await b.new_context(viewport={"width": 1400, "height": 900}); await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
      u = r.request.url
      if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
      elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
      else: await r.abort()
    await page.route("**/*", route)
    await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
    txt = lambda: page.evaluate("document.querySelector('#editor > p').textContent")
    btn = lambda c: page.evaluate("c => { const b = document.querySelector('#ed-toolbar [data-cmd=' + c + ']'); return b.disabled; }", c)
    ok = True
    def check(name, cond, extra=""):
      nonlocal ok; ok = ok and cond; print("ok  " if cond else "FAIL", name, extra)
    base = await txt()
    check("buttons start disabled", await btn("undo") and await btn("redo"))
    # typing at the start of the first paragraph, in two bursts
    await page.evaluate("(() => { const p = document.querySelector('#editor > p'); const r = document.createRange(); r.setStart(p.firstChild, 0); r.collapse(true); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); })()")
    await page.keyboard.type("ABC"); await page.wait_for_timeout(1100); await page.keyboard.type("DEF"); await page.wait_for_timeout(500)
    check("typed", (await txt()).startswith("ABCDEF"), (await txt())[:12])
    check("undo enabled", not await btn("undo"))
    await page.click('#ed-toolbar [data-cmd="undo"]'); await page.wait_for_timeout(200)
    check("undo one burst", (await txt()).startswith("ABC") and not (await txt()).startswith("ABCDEF"), (await txt())[:12])
    check("redo enabled", not await btn("redo"))
    await page.click('#ed-toolbar [data-cmd="undo"]'); await page.wait_for_timeout(200)
    check("undo second burst", await txt() == base)
    await page.click('#ed-toolbar [data-cmd="redo"]'); await page.click('#ed-toolbar [data-cmd="redo"]'); await page.wait_for_timeout(200)
    check("redo twice", (await txt()).startswith("ABCDEF"))
    # keyboard
    await page.evaluate("document.querySelector('#editor').focus()")
    await page.keyboard.press("Control+z"); await page.wait_for_timeout(200); check("Ctrl+Z", not (await txt()).startswith("ABCDEF"))
    await page.keyboard.press("Control+y"); await page.wait_for_timeout(200); check("Ctrl+Y", (await txt()).startswith("ABCDEF"))
    await page.keyboard.press("Control+z"); await page.keyboard.press("Control+Shift+z"); await page.wait_for_timeout(200); check("Ctrl+Shift+Z", (await txt()).startswith("ABCDEF"))
    # a new edit clears redo
    await page.keyboard.press("Control+z"); await page.wait_for_timeout(200); await page.keyboard.type("Q"); await page.wait_for_timeout(300)
    check("new edit clears redo", await btn("redo"))
    # bold from the toolbar, then undo
    await page.evaluate("(() => { const p = document.querySelector('#editor > p'); const r = document.createRange(); r.setStart(p.firstChild, 3); r.setEnd(p.firstChild, 9); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); document.dispatchEvent(new Event('selectionchange')); })()")
    await page.wait_for_timeout(200); await page.click('#ed-toolbar [data-cmd="bold"]'); await page.wait_for_timeout(300)
    check("bold applied", await page.evaluate("!!document.querySelector('#editor > p b, #editor > p strong')"))
    await page.click('#ed-toolbar [data-cmd="undo"]'); await page.wait_for_timeout(300)
    check("undo bold", await page.evaluate("!document.querySelector('#editor > p b, #editor > p strong')"))
    await page.click('#ed-toolbar [data-cmd="redo"]'); await page.wait_for_timeout(300)
    check("redo bold", await page.evaluate("!!document.querySelector('#editor > p b, #editor > p strong')"))
    # a change the app makes in code (a slide cue), undone and redone from the same buttons
    cues = await page.evaluate("document.querySelectorAll('#editor .pb-slide').length")
    await page.evaluate("(() => { const sel = document.querySelector('#ed-slide'); sel.value = 'next'; sel.dispatchEvent(new Event('change')); })()"); await page.wait_for_timeout(300)
    check("cue added", await page.evaluate("document.querySelectorAll('#editor .pb-slide').length") == cues + 1)
    await page.click('#ed-toolbar [data-cmd="undo"]'); await page.wait_for_timeout(300); check("undo cue", await page.evaluate("document.querySelectorAll('#editor .pb-slide').length") == cues)
    await page.click('#ed-toolbar [data-cmd="redo"]'); await page.wait_for_timeout(300); check("redo cue", await page.evaluate("document.querySelectorAll('#editor .pb-slide').length") == cues + 1)
    # the side panel Undo is the same history
    await page.click("#sg-undo"); await page.wait_for_timeout(300); check("side panel Undo", await page.evaluate("document.querySelectorAll('#editor .pb-slide').length") == cues)
    # switching sermon starts fresh
    await page.click("#btn-new-top"); await page.wait_for_timeout(500)
    await page.evaluate("document.querySelector('#sub-edit').click()"); await page.wait_for_timeout(300)
    check("new sermon starts with no history", await btn("undo") and await btn("redo") and await page.evaluate("document.querySelector('#sg-undo').disabled"))
    print("errors", errs, "RESULT", "all passed" if ok else "FAILURES")
    await b.close()
asyncio.run(main())
