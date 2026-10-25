import asyncio, pathlib, json, base64
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); Object.defineProperty(window, 'S', { get: () => S });\n})();")   # the served copy only
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__prompts = []; const smp = async () => ({ text: '' });
smp.json = async (p, o) => { window.__prompts.push(p); await new Promise(r => setTimeout(r, 150));
  if (p.includes('infographic slide')) return window.__reply || { layout: 'steps', title: 'Walking by the light', items: [{ label: 'Hear', detail: 'Let the word be read aloud' }, { label: 'Trust', detail: 'Believe the One who sees the whole path' }, { label: 'Step', detail: 'Take the next faithful step' }] };
  return {}; };
smp.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? smp : n === 'downloads' ? { save: async o => { window.__saved = { name: o.filename, b64: await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(o.data); }) }; } } : null };"""
SEL = """(k) => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n, i = 0; while ((n = w.nextNode())) { const t = n.textContent; if (t.length > 40 && !n.parentElement.closest('.pb-slide,.pb-scripture') && i++ === k) { const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 30); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.dispatchEvent(new Event('selectionchange')); return true; } } return false; }"""
REPLIES = {
  "steps": None,
  "timeline": { "layout": "timeline", "title": "Abraham's road", "items": [{ "label": "Called", "detail": "Go to the land I will show you" }, { "label": "Went out", "detail": "Not knowing where he was going" }, { "label": "Waited", "detail": "By faith he lived as a stranger" }, { "label": "Received", "detail": "The promise kept in God's time" }] },
  "stats": { "layout": "stats", "title": "", "items": [{ "label": "1", "detail": "lamp for the next step" }, { "label": "8", "detail": "verses in this section" }, { "label": "0", "detail": "need to see the whole road" }] },
  "compare": { "layout": "compare", "title": "Two builders", "left": { "head": "Wise", "points": ["Hears the word", "Does the word", "Stands in the storm"] }, "right": { "head": "Foolish", "points": ["Hears the word", "Ignores it", "Falls when the rain comes"] } },
}
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, h, scheme in [(1440, 900, "light"), (390, 844, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
      for k, (lay, reply) in enumerate(REPLIES.items()):
        await page.evaluate("r => { window.__reply = r; }", reply)
        assert await page.evaluate(SEL, k); await page.wait_for_timeout(250)
        await page.evaluate("document.querySelector('#btn-make-slide').click()"); await page.wait_for_timeout(250)
        if lay == "steps": print(w, "kind listed", await page.evaluate("[...document.querySelectorAll('#mk-kinds .mk-kind b')].map(b => b.textContent).includes('Infographic')"))
        await page.click("#mk-kinds button:has-text('Infographic')"); await page.wait_for_function("document.querySelector('#mk-f-info') && document.querySelector('#mk-f-info').value.length > 0", timeout=8000)
        print(w, lay, "layout", await page.evaluate("document.querySelector('#mk-f-lay').value"), "text", json.dumps(await page.evaluate("document.querySelector('#mk-f-info').value"))[:110], "slides", await page.evaluate("document.querySelectorAll('#mk-preview .slide').length"))
        if lay == "steps":
          await page.fill("#mk-f-info", "Hear | Let the word be read\nTrust | Believe the One who sees\nStep | Take the next step\nRepeat | Every morning\nShare | Tell someone else\nSixth | Extra one that is dropped"); await page.wait_for_timeout(200)
          print(w, "steps cap", await page.evaluate("document.querySelectorAll('#mk-preview .ig-cell').length"))
        await page.evaluate("document.querySelector('#mk-preview').scrollIntoView({block:'center'})"); await page.wait_for_timeout(150)
        await page.screenshot(path=str(OUT / f"ig_{lay}_{w}.png"))
        await page.click("#mk-add"); await page.wait_for_timeout(300)
      print(w, "slides added", await page.evaluate("S.slides.filter(s => s.made === 'infographic').map(s => [s.layout, s.items.length])"))
      if w == 1440:
        await page.evaluate("document.querySelector('#btn-save-pptx').click()"); await page.wait_for_function("window.__saved", timeout=60000)
        open(OUT / "infographic.pptx", "wb").write(base64.b64decode(await page.evaluate("__saved.b64")))
      # layout switch in the form and Claude failing leaves a usable form
      await page.evaluate("window.__reply = { layout: 'steps', items: [] }"); assert await page.evaluate(SEL, 5); await page.wait_for_timeout(200)
      await page.evaluate("document.querySelector('#btn-make-slide').click()"); await page.wait_for_timeout(200); await page.click("#mk-kinds button:has-text('Infographic')"); await page.wait_for_timeout(900)
      print(w, "empty reply", await page.evaluate("[document.querySelector('#mk-add').disabled, document.querySelector('#mk-f-info').value.length, document.querySelectorAll('#mk-preview .slide').length]"))
      await page.select_option("#mk-f-lay", "stats"); await page.fill("#mk-f-info", "3 | days in the tomb"); await page.wait_for_timeout(200)
      print(w, "typed by hand", await page.evaluate("document.querySelectorAll('#mk-preview .ig-big').length"))
      await page.evaluate("document.querySelector('#mk-cancel2').click()")
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
