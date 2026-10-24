import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
PNG = __import__("base64").b64encode(open(FIX / "preview.png", "rb").read()).decode()
INIT = """const smp = async () => ({text:''}); smp.json = async (p) => { await new Promise(r=>setTimeout(r,300)); if (p.includes('three distinct slide themes')) return {themes:[{name:'Lamp on the Path',mood:'Warm dusk light on stone.',why:'Psalm 119 is about light for the next step.',bg:'#1a1510',bg2:'#4a3218',fg:'#f6efe2',accent:'#e8b45a',head:'Cormorant Garamond',body:'Lora',tex:'vignette',imagery:'An oil lamp on a stone path at dusk'},{name:'Morning Word',mood:'Clean and bright.',bg:'#f4efe4',bg2:'#ffffff',fg:'#222222',accent:'#2f5d8a',head:'DM Serif Display',body:'Source Serif 4',tex:'dots',imagery:'Sunrise over hills'},{name:'Night Watch',mood:'Deep blue and quiet.',bg:'#0f1a2b',fg:'#20242c',accent:'#123456',head:'Oswald',body:'Inter',tex:'lines',imagery:'Stars over a dark valley'}]}; return {}; };
let polls = 0; window.claude = { use: async n => n === 'sample' ? smp : n === 'mcp' ? { callTool: async (srv, tool) => { if (tool === 'generate-image') return { payload: { jobId: 'j1' }, content: [] }; polls++; return { payload: { status: 'SUCCESS', link: 'https://www.canva.com/design/abc/view', url: 'https://media.canva.com/v2/image-resize/format:PNG/width:2560/x.png?exp=1' }, content: [{ type: 'image', data: '%s', mimeType: 'image/png' }] }; } } : n === 'downloads' ? { save: async o => { window.__saved = o.filename; } } : null };""" % PNG
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
      await page.goto("https://x.test/#materials"); await page.wait_for_timeout(1200)
      cards = lambda: page.evaluate("[...document.querySelectorAll('#th-list .th-card b')].map(b=>b.textContent)")
      print(w, "local", await cards(), "previews", await page.evaluate("document.querySelectorAll('#th-prev .slide').length"))
      await page.click("#th-ai"); await page.wait_for_timeout(700)
      print(w, "claude", await cards())
      print(w, "night watch fixed fg", await page.evaluate("JSON.stringify(S_th = null) && [...document.querySelectorAll('#th-list .th-card')].length"))
      await page.click("#th-paint"); await page.wait_for_timeout(3800)
      print(w, "header img", await page.evaluate("!!document.querySelector('#th-prev .mk-hdr')"))
      print(w, "hd box", await page.evaluate("[...document.querySelectorAll('#th-edit .hd-box a')].map(a=>a.textContent+' '+a.href.slice(0,40))"), await page.evaluate("(document.querySelector('#th-edit .hd-box b')||{}).textContent"))
      await page.set_input_files("#th-hd", str(FIX / "photo.jpg")); await page.wait_for_timeout(600)
      print(w, "after swap", await page.evaluate("[!!document.querySelector('#th-edit .hd-box'), (document.querySelector('#th-edit .th-pic .hint:last-of-type')||{}).textContent]"))
      await page.screenshot(path=str(OUT / f"theme_{w}.png"), full_page=False)
      await page.evaluate("document.querySelector('#mat-theme').scrollIntoView()"); await page.wait_for_timeout(200)
      await page.screenshot(path=str(OUT / f"theme_panel_{w}.png"))
      await page.click("#th-use"); await page.click("#th-add-title"); await page.wait_for_timeout(300)
      print(w, "title added", await page.evaluate("document.querySelectorAll('.slide').length >= 0 && JSON.stringify(document.querySelector('#th-restyle').textContent)"))
      await page.click("#th-save"); await page.wait_for_timeout(1500); print(w, "saved", await page.evaluate("window.__saved"))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
