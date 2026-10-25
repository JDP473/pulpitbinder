import asyncio, pathlib, base64, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); Object.defineProperty(window, 'S', { get: () => S });\n})();")   # the served copy only, so the test can reach the open sermon
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
DECK = base64.b64encode(open(FIX / "deck.pptx", "rb").read()).decode()
INIT = """window.__saved = null;
window.claude = { use: async n => n === 'downloads' ? { save: async o => { const b = o.data; window.__saved = { name: o.filename, size: b.size, b64: await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(b); }) }; } } : null };"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, scheme in [(1400, "light"), (390, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e))); page.on("console", lambda m: m.type == "error" and errs.append(m.text))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(1200)
      # the example deck, then a real .pptx read in and a made slide of each kind added
      await page.set_input_files("#file-pptx", str(FIX / "deck.pptx")); await page.wait_for_timeout(2500)
      await page.evaluate("""(() => { const th = { bg:'#1a1510', bg2:'#4a3218', fg:'#f6efe2', accent:'#e8b45a', head:'Lora', body:'Lora', tex:'vignette' };
        const mk = o => ({ theme: th, notes: '', ...o });
        addSlides && 0; })()""") if False else None
      n0 = await page.evaluate("S.slides.length")
      await page.evaluate("""(() => { const th = { bg:'#1a1510', bg2:'#4a3218', fg:'#f6efe2', accent:'#e8b45a', head:'Lora', body:'Lora', tex:'vignette' };
        const base = { theme: th, notes: 'Made note', title: 'x', body: [] };
        [{made:'statement',text:'Walk by the light you have.'},{made:'quote',text:'Your word is a lamp to my feet.',ref:'Psalm 119:105',ver:'ESV'},
         {made:'points',title:'Three steps',points:['Light','Trust','Step'],ref:'Psalm 119'},{made:'blanks',text:'Faith is [[walking]] by the [[light]].'},
         {made:'title',title:'Enough Light',kicker:'A sermon on',ref:'Psalm 119:105-112'},{made:'point',num:'II.',text:'Light for one step'},
         {made:'question',text:'What is the next faithful step?'},{made:'scripture',text:'{{105}}Your word is a lamp to my feet\\nand a light to my path.',ref:'Psalm 119:105'}]
         .forEach(o => S.slides.push({ ...base, ...o })); S.slides[S.slides.length-1].hidden = true; })()""")
      await page.click("#btn-save-pptx"); await page.wait_for_function("window.__saved", timeout=60000)
      info = await page.evaluate("({name: __saved.name, size: __saved.size})"); print(w, "saved", info, "from", n0, "->", await page.evaluate("S.slides.length"))
      if w == 1400:
        open(OUT / "export.pptx", "wb").write(base64.b64decode(await page.evaluate("__saved.b64")))
      print(w, "errors", errs)
      await ctx.close()
asyncio.run(main())
