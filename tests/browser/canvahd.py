import asyncio, pathlib, json, base64, datetime
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
PNG = base64.b64encode(open(FIX / "preview.png", "rb").read()).decode()
# Canva's design tools, mocked with the shapes the real connector returns. FAIL_EXPORT makes every export fail.
INIT = """const smp = async () => ({text:''}); smp.json = async () => ({}); smp.limits = async () => ({});
window.__calls = []; window.FAIL_EXPORT = false; let n = 0, jobs = 0;
const exportUrl = () => 'https://export-download.canva.com/test/DAtest00001/-1/0/0001-' + (++n) + '.png?X-Amz-Date=' + new Date(Date.now()).toISOString().replace(/[-:]|\.\d+/g, '') + '&X-Amz-Expires=68000&X-Amz-Signature=test';
window.claude = { use: async name => name === 'sample' ? smp : name === 'downloads' ? { save: async () => {} } : name === 'mcp' ? { callTool: async (srv, tool, input) => {
  window.__calls.push(tool); await new Promise(r => setTimeout(r, 120));
  if (tool === 'generate-image') return { payload: { jobId: 'j' + (++jobs) }, content: [] };
  if (tool === 'get-generate-image-job') return { payload: { status: 'SUCCESS', result: { results: [{ type: 'MEDIA', id: 'MAtest' + jobs + 'abcd', version: '1' }] } },
    content: [{ type: 'resource_link', uri: 'https://www.canva.com/M/MAtest' + jobs + 'abcd', name: 'MAtest' + jobs + 'abcd' }, { type: 'image', data: '%s', mimeType: 'image/png' }, { type: 'text', text: '{"status":"SUCCESS"}' }] };
  if (tool === 'search-designs') return { payload: { items: [{ id: 'DAother00001', title: 'Any Presentation Photo' }] } };
  if (tool === 'create-design') return { payload: { job_id: 'cj1', status: 'pending', continuation_token: 'c1', polling_policy: { wait_seconds: 5 } } };
  if (tool === 'get-create-design-async-job') return { payload: { job_id: 'cj1', status: 'completed', design: { id: 'DAtest00001' } } };
  if (tool === 'read-design') { if (input.design_id !== 'DAtest00001') throw { code: 'tool_error', message: 'not found' }; return { payload: { page_metadata: [{ id: 'PBtestpage1', index: 1 }], transaction: { transaction_id: 'tx' + n } } }; }
  if (tool === 'edit-design') { window.__calls.push('edit:' + input.finalize + (input.operations ? ':' + input.operations[0].type + ':' + input.operations[0].asset_id : '')); return { payload: input.finalize === 'commit' ? { status: 'committed' } : { status: 'edits_unverified', edit_operation_results: [{ status: 'applied_unverified' }] } }; }
  if (tool === 'export-design') { if (window.FAIL_EXPORT) throw { code: 'tool_error', message: 'export failed' }; return { payload: { job: { status: 'success', urls: [exportUrl()] } } }; }
  throw { code: 'not_in_manifest' };
} } : null };""" % PNG
SEL = """() => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const t = n.textContent; if (t.length > 40 && !n.parentElement.closest('.pb-slide,.pb-scripture')) { const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 30); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""
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
      calls = lambda: page.evaluate("window.__calls.splice(0)")
      hd = "(() => { const b = document.querySelector('#mk-hd'); return b ? [b.querySelector('b').textContent, [...b.querySelectorAll('.hd-links a, .hd-links button')].map(a => a.textContent + (a.href ? ' ' + a.href.split('?')[0].slice(-12) : ''))] : null; })()"
      # 1. Illustration: paint, then the full-size export starts on its own (first time: no kept design yet, so one is made)
      assert await page.evaluate(SEL); await page.wait_for_timeout(250)
      await page.click("#btn-make-slide"); await page.wait_for_timeout(200)
      await page.click("#mk-kinds button:has-text('Illustration')"); await page.wait_for_timeout(300)
      if await page.evaluate("!document.querySelector('#mk-f-prompt').value.trim()"): await page.fill("#mk-f-prompt", "An oil lamp on a stone path at dusk")
      await page.wait_for_function("document.querySelector('#mk-hd b') && document.querySelector('#mk-hd b').textContent.startsWith('Getting')", timeout=15000)
      print(w, "while exporting", await page.evaluate(hd))
      await page.screenshot(path=str(OUT / f"canvahd_busy_{w}.png"))
      # typing while the export runs keeps focus
      await page.click("#mk-f-cap"); await page.keyboard.type("Enough light"); await page.wait_for_function("document.querySelector('#mk-hd b').textContent.includes('ready')", timeout=20000); await page.keyboard.type(" for the next step")
      print(w, "caption kept focus", await page.evaluate("[document.activeElement.id, document.querySelector('#mk-f-cap').value]"))
      print(w, "ready", await page.evaluate(hd))
      print(w, "calls", await calls())
      await page.evaluate("document.querySelector('#mk-hd').scrollIntoView({block:'center'})"); await page.screenshot(path=str(OUT / f"canvahd_ready_{w}.png"))
      # Paint another: the kept design is reused, no search or create
      await page.click("#mk-again"); await page.wait_for_function("[...document.querySelectorAll('#mk-hd a')].some(a => a.href.includes('0001-2.png'))", timeout=20000)
      c = await calls(); print(w, "second paint calls", c); assert "search-designs" not in c and "create-design" not in c
      print(w, "second ready", await page.evaluate(hd))
      await page.click("#mk-add"); await page.wait_for_timeout(400)
      # 2. a saved slide: the popup links the full-size picture, and once the link expires (two days on) offers to export again
      openpop = "(() => { const t = [...document.querySelectorAll('.g-thumb')].find(b => b.querySelector('.slide.made-art')); if (!t || !t.offsetParent) return false; t.click(); return true; })()"
      pop = "[...document.querySelectorAll('.g-pop .hd-links a, .g-pop .hd-links button')].map(a => a.textContent)"
      if await page.evaluate(openpop):
        await page.wait_for_timeout(300); print(w, "popup fresh", await page.evaluate(pop)); await page.keyboard.press("Escape"); await page.mouse.click(5, 5); await page.wait_for_timeout(200)
        await page.evaluate("(() => { const real = Date.now; Date.now = () => real() + 2 * 86400000; })()")
        await page.evaluate(openpop); await page.wait_for_timeout(300)
        print(w, "popup expired", await page.evaluate(pop))
        await page.click(".g-pop .hd-links button"); await page.wait_for_timeout(1500)
        print(w, "popup after", await page.evaluate(pop))
        await page.screenshot(path=str(OUT / f"canvahd_pop_{w}.png"))
        await page.mouse.click(5, 5); await page.wait_for_timeout(200)
      else: print(w, "popup: no gutter on this width")
      await calls()
      # 3. export fails: a plain message and Try again
      await page.evaluate("window.FAIL_EXPORT = true")
      assert await page.evaluate(SEL); await page.wait_for_timeout(250)
      await page.click("#btn-make-slide"); await page.wait_for_timeout(200)
      await page.click("#mk-kinds button:has-text('Illustration')"); await page.wait_for_timeout(300)
      if await page.evaluate("!document.querySelector('#mk-f-prompt').value.trim()"): await page.fill("#mk-f-prompt", "A path at dusk")
      await page.wait_for_selector("#mk-hd button:has-text('Try again')", timeout=20000)
      print(w, "failed", await page.evaluate(hd), await page.evaluate("(document.querySelector('#mk-hd .hint')||{}).textContent"))
      print(w, "failed calls", await calls())
      await page.evaluate("document.querySelector('#mk-hd').scrollIntoView({block:'center'})"); await page.screenshot(path=str(OUT / f"canvahd_fail_{w}.png"))
      await page.evaluate("window.FAIL_EXPORT = false"); await page.click("#mk-hd button:has-text('Try again')"); await page.wait_for_timeout(1500)
      print(w, "retried", await page.evaluate(hd))
      await page.keyboard.press("Escape"); await page.evaluate("document.querySelector('#mk-modal').hidden = true")
      # 4. theme header picture
      await page.goto("https://x.test/#materials"); await page.reload(); await page.wait_for_timeout(1200); await calls()
      await page.click("#th-paint"); await page.wait_for_function("(document.querySelector('#th-hd-box b')||{}).textContent?.startsWith('Getting')", timeout=15000)
      th = "(() => { const b = document.querySelector('#th-hd-box'); return b ? [(b.querySelector('b')||{}).textContent, [...b.querySelectorAll('.hd-links a, .hd-links button')].map(a => a.textContent)] : null; })()"
      print(w, "theme busy", await page.evaluate(th))
      await page.wait_for_function("(document.querySelector('#th-hd-box b')||{}).textContent?.includes('ready')", timeout=15000)
      print(w, "theme ready", await page.evaluate(th))
      print(w, "theme calls", await calls())
      await page.evaluate("document.querySelector('#th-hd-box').scrollIntoView({block:'center'})"); await page.screenshot(path=str(OUT / f"canvahd_theme_{w}.png"))
      await page.set_input_files("#th-hd", str(FIX / "photo.jpg")); await page.wait_for_timeout(600)
      print(w, "theme after swap", await page.evaluate(th))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
