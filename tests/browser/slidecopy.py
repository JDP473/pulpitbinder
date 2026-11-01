# Click a slide to copy it as a full-size picture: from Bindings and from the editor's slide popup, with the clipboard
# allowed, then with it refused (the picture is saved through downloads instead). The copied picture goes to tests/out/slidecopy.png.
import asyncio, pathlib, base64
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
NM = ROOT / "tests" / "node" / "node_modules"
JSZIP = open(NM / "jszip" / "dist" / "jszip.min.js").read()
H2C = open(NM / "html2canvas" / "dist" / "html2canvas.min.js").read()   # npm install --no-save html2canvas@1.4.1 in tests/node
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__saved = null;
window.claude = { use: async n => n === 'downloads' ? { save: async o => { window.__saved = { name: o.filename, size: o.data.size }; } } : null };"""
READ = """async () => { const items = await navigator.clipboard.read(); const b = await items[0].getType('image/png'); const bm = await createImageBitmap(b);
  const d = await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(b); }); return { w: bm.width, h: bm.height, b64: d }; }"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for allow, w, scheme in [(True, 1400, "light"), (True, 390, "dark"), (False, 1400, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme, permissions=["clipboard-read", "clipboard-write"] if allow else [])
      await ctx.add_init_script(INIT + ("" if allow else "navigator.clipboard.write = async () => { throw new DOMException('blocked', 'NotAllowedError'); };"))
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif "html2canvas" in u: await r.fulfill(body=H2C, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(1200)
      await page.set_input_files("#file-pptx", str(FIX / "deck.pptx")); await page.wait_for_timeout(2500)
      tag = f"{w}{'d' if scheme == 'dark' else ''}{'' if allow else '_blocked'}"
      await page.click("#sub-bindings"); await page.wait_for_timeout(800)
      sl = page.locator("#bind-list .slide.copyable").nth(1); await sl.scroll_into_view_if_needed(); await sl.hover()
      await page.screenshot(path=str(OUT / f"slidecopy_bind_{tag}.png"))
      await sl.click(); await page.wait_for_timeout(2500)
      toast = await page.text_content("#toast")
      if allow:
        r = await page.evaluate(READ); print(tag, "bindings copy", r["w"], "x", r["h"], "|", toast)
        if w == 1400: open(OUT / "slidecopy.png", "wb").write(base64.b64decode(r["b64"]))
      else: print(tag, "bindings fallback", await page.evaluate("__saved"), "|", toast)
      # the editor's slide popup (the gutter is hidden on phones)
      if w > 640:
        await page.click("#sub-edit"); await page.wait_for_timeout(1000)
        await page.locator("#gutter .g-chip, #gutter button").first.click(); await page.wait_for_timeout(400)
        await page.screenshot(path=str(OUT / f"slidecopy_pop_{tag}.png"))
        await page.click(".g-pop button:has-text('Copy picture')"); await page.wait_for_timeout(2500)
        print(tag, "popup copy:", await page.text_content("#toast"), "| popup still open:", await page.is_visible(".g-pop"))
      print(tag, "errors", errs)
      await ctx.close()
asyncio.run(main())
