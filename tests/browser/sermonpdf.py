# "Save sermon PDF with slides beside": the example sermon and its deck, saved as a PDF in light and dark mode and on a phone.
# Each page of the PDF is one JPEG; they are written to tests/out/spdf_<width>_<page>.jpg to look at.
import asyncio, pathlib, base64, re
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); Object.defineProperty(window, 'S', { get: () => S });\n})();")   # the served copy only, so the test can reach the open sermon
NM = ROOT / "tests" / "node" / "node_modules"
JSZIP = open(NM / "jszip" / "dist" / "jszip.min.js").read()
H2C = open(NM / "html2canvas" / "dist" / "html2canvas.min.js").read()   # npm install --no-save html2canvas@1.4.1 in tests/node
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__saved = null;
window.claude = { use: async n => n === 'downloads' ? { save: async o => { const b = o.data; window.__saved = { name: o.filename, size: b.size, b64: await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(b); }) }; } } : null };"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, scheme in [(1400, "light"), (1400, "dark"), (390, "light")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e))); page.on("console", lambda m: m.type == "error" and errs.append(m.text))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif "html2canvas" in u: await r.fulfill(body=H2C, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(1200)
      await page.set_input_files("#file-pptx", str(FIX / "deck.pptx")); await page.wait_for_timeout(2500)
      tag = f"{w}{'d' if scheme == 'dark' else ''}"
      if scheme == "dark":   # a long sermon: paragraphs and a Scripture section that run past the bottom of a page
        await page.evaluate("""(() => { const long = 'Generic filler sentence number one for layout testing only. '.repeat(70);
          const sc = '<div class="pb-scripture" data-id="t1" data-ref="Psalm 1:1-3" data-ver="ESV" data-texts=\\'' + JSON.stringify({ESV: {t: Array.from({length: 40}, (_, i) => '{{' + (i + 1) + '}}Placeholder verse words for testing the cut. ').join(''), s: 'typed'}}).replace(/'/g, '&#39;') + '\\'></div>';
          S.html = S.html + '<h2>A long heading</h2><p><strong>Bold start</strong> ' + long + '<em>italic end</em></p>' + sc + '<p>' + long + '</p>'; })()""")
      btn = page.locator("#btn-save-spdf"); await btn.scroll_into_view_if_needed()
      await page.screenshot(path=str(OUT / f"spdf_btn_{tag}.png"))
      await btn.click(); await page.wait_for_function("window.__saved", timeout=120000)
      info = await page.evaluate("({name: __saved.name, size: __saved.size})")
      pdf = base64.b64decode(await page.evaluate("__saved.b64"))
      assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
      n = int(re.search(rb"/Count (\d+)", pdf).group(1))
      jpgs = re.findall(rb"/DCTDecode /Length (\d+) >>\nstream\n", pdf)
      pos = 0; k = 0
      for m in re.finditer(rb"/DCTDecode /Length (\d+) >>\nstream\n", pdf):
        L = int(m.group(1)); k += 1; open(OUT / f"spdf_{tag}_{k}.jpg", "wb").write(pdf[m.end():m.end() + L])
      # xref offsets must point at their objects
      xr = int(re.search(rb"startxref\n(\d+)", pdf).group(1)); assert pdf[xr:xr+4] == b"xref"
      offs = [int(x) for x in re.findall(rb"(\d{10}) 00000 n", pdf)]
      bad = [i + 1 for i, o in enumerate(offs) if not pdf[o:].startswith(f"{i+1} 0 obj".encode())]
      print(tag, info, "pages", n, "images", len(jpgs), "bad xref", bad, "button:", await btn.text_content())
      print(tag, "errors", errs)
      await ctx.close()
asyncio.run(main())
