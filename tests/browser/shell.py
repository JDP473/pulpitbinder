import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900"><circle cx="800" cy="420" r="160" fill="#e2b55e"/><rect x="700" y="600" width="200" height="40" fill="#f5f2ea"/></svg>'
INIT = """window.__tiers = []; const smp = async () => ({ text: '' });
smp.json = async (p, o) => { window.__tiers.push(o && o.modelTier); await new Promise(r => setTimeout(r, 150)); if (p.includes('Draw one simple illustration')) return { svg: %s, caption: 'Enough light for one step' }; if (p.includes('Describe one picture')) return { prompt: 'An oil lamp on a path', caption: 'Light for the next step' }; return {}; };
smp.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? smp : n === 'downloads' ? { save: async () => {} } : n === 'mcp' ? { callTool: async () => { throw { code: 'server_not_connected' }; } } : null };""" % json.dumps(SVG)
SEL = """() => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const t = n.textContent; if (t.length > 40 && !n.parentElement.closest('.pb-slide,.pb-scripture')) { const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 30); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""
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
      print(w, "title", await page.evaluate("[document.querySelector('#sb-title').textContent, getComputedStyle(document.querySelector('.sb-head')).display]"))
      # every section from the navigation
      for v in ["dash", "study", "present", "materials", "analysis", "build"]:
        await page.click(f"#tab-{v}"); await page.wait_for_timeout(250)
      print(w, "back on", await page.evaluate("document.body.dataset.view"), "edit side panel width", await page.evaluate("Math.round(document.querySelector('#view-edit .sg-col, .sg-col') ? 0 : 0)"))
      if w == 1440:
        await page.click("#btn-collapse"); await page.wait_for_timeout(150); print(w, "chips hidden", await page.evaluate("getComputedStyle(document.querySelector('#tagbar')).display === 'none'")); await page.click("#btn-collapse")
      # settings: open from the navigation, AI pane, choose Claude drawing and the most careful setting
      await page.click("#btn-settings"); await page.wait_for_timeout(300)
      print(w, "settings open", await page.evaluate("[!document.querySelector('#settings').hidden, document.body.classList.contains('set-open')]"))
      await page.click("#set-tab-ai"); await page.wait_for_timeout(200)
      print(w, "picture options", await page.evaluate("[...document.querySelectorAll('#set-img .ai-opt b')].map(b => b.textContent)"), "claude", await page.evaluate("document.querySelector('#ai-claude-st').textContent"))
      await page.screenshot(path=str(OUT / f"shell_ai_{w}.png"))
      await page.check("#set-img-claude-draw"); await page.select_option("#set-tier", "careful"); await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(300)
      print(w, "saved", await page.evaluate("[document.querySelector('#settings').hidden, JSON.parse(localStorage.getItem('pb-settings')).imgService, JSON.parse(localStorage.getItem('pb-settings')).aiTier]"))
      # an Illustration slide now drawn by Claude, at the most careful setting
      await page.click("#tab-build"); await page.wait_for_timeout(200)
      await page.evaluate("document.querySelector('#sub-edit').click()"); await page.wait_for_timeout(500)
      if await page.evaluate(SEL):
        await page.wait_for_timeout(250); await page.evaluate("document.querySelector('#btn-make-slide').click()"); await page.wait_for_timeout(300)
        print(w, "art label", await page.evaluate("[...document.querySelectorAll('#mk-kinds .mk-kind')].filter(k => k.textContent.includes('Illustration')).map(k => k.querySelector('.mk-ai').textContent)"))
        await page.click("#mk-kinds button:has-text('Illustration')"); await page.wait_for_function("document.querySelector('#mk-preview img.mk-img')", timeout=10000)
        print(w, "drawn", await page.evaluate("document.querySelector('#mk-preview img.mk-img').src.slice(0, 26)"), "tiers", await page.evaluate("window.__tiers"))
        await page.screenshot(path=str(OUT / f"shell_draw_{w}.png"))
        await page.click("#mk-add"); await page.wait_for_timeout(300)
      # Escape closes settings; switching sections closes it too
      await page.click("#btn-settings"); await page.wait_for_timeout(200); await page.keyboard.press("Escape"); await page.wait_for_timeout(150)
      print(w, "escape closes", await page.evaluate("document.querySelector('#settings').hidden"))
      await page.click("#btn-settings"); await page.wait_for_timeout(200); await page.click("#tab-present"); await page.wait_for_timeout(250)
      print(w, "nav closes", await page.evaluate("[document.querySelector('#settings').hidden, document.body.dataset.view]"))
      await page.screenshot(path=str(OUT / f"shell_present_{w}.png"))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
