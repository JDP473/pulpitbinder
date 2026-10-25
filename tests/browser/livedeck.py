# End to end: Present > Share live view against the real relay (live.pettijohn.me), then open the viewer, alone and in an iframe.
# Needs the connector token in PULPIT_LIVE_TOKEN (never committed); skips otherwise.
import asyncio, pathlib, json, os, urllib.request, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
from playwright.async_api import async_playwright
TOKEN = os.environ.get("PULPIT_LIVE_TOKEN", "")
if not TOKEN: print("PULPIT_LIVE_TOKEN not set, skipping"); sys.exit(0)
HOST = "https://live.pettijohn.me"
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); Object.defineProperty(window, 'S', { get: () => S });\n})();")
JSZIP = open(ROOT / "tests/node/node_modules/jszip/dist/jszip.min.js").read()
H2C = open(ROOT / "tests/node/node_modules/html2canvas/dist/html2canvas.min.js").read()
INIT = """const smp = async () => ({text:''}); smp.json = async () => ({}); smp.limits = async () => ({});
window.__calls = [];
window.claude = { use: async name => name === 'sample' ? smp : name === 'downloads' ? { save: async () => {} } : name === 'mcp' ? { callTool: async (srv, tool, input) => {
  window.__calls.push(tool); if (srv !== 'Pulpit Live') throw { code: 'not_in_manifest' };
  return await window.relay(tool, JSON.stringify(input)); } } : null };"""
def relay(tool, args):
  body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": json.loads(args)}}).encode()
  r = urllib.request.Request(f"{HOST}/mcp/{TOKEN}", body, {"content-type": "application/json", "User-Agent": "pulpit-test"})
  return json.loads(urllib.request.urlopen(r, timeout=30).read())["result"]
def state(code): return json.loads(urllib.request.urlopen(urllib.request.Request(f"{HOST}/v/{code}/state", headers={"User-Agent": "pulpit-test"}), timeout=20).read())
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, scheme in [(1400, "light"), (390, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      loop = asyncio.get_running_loop()
      await page.expose_function("relay", lambda t, a: relay(t, a))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif "html2canvas" in u: await r.fulfill(body=H2C, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
      await page.set_input_files("#file-pptx", str(FIX / "deck.pptx")); await page.wait_for_timeout(2500)
      n = await page.evaluate("S.slides.length"); print(w, "slides", n)
      await page.evaluate("document.querySelector('#tab-present').click()"); await page.wait_for_timeout(800)
      await page.click("#btn-live", force=True); await page.wait_for_timeout(300)
      print(w, "before", await page.inner_text("#lv-state"))
      await page.screenshot(path=str(OUT / f"live_modal_before_{w}.png"))
      await page.click("#lv-toggle")
      await page.wait_for_function("document.querySelector('#lv-state').textContent.includes('All')", timeout=120000)
      print(w, "ready", await page.inner_text("#lv-state"))
      code = await page.evaluate("S.meta.live.code"); url = await page.input_value("#lv-url"); print(w, "url", url.replace(code, "<code>"))
      assert url == f"{HOST}/v/{code}"
      st = state(code); print(w, "relay", {k: st[k] for k in ("live", "count", "cur")}, "ready images", sum(1 for h in st["hashes"] if h)); assert st["count"] == n and all(st["hashes"])
      await page.screenshot(path=str(OUT / f"live_modal_on_{w}.png"))
      await page.click("#lv-close"); await page.click("#btn-next", force=True); await page.wait_for_timeout(3500)
      st2 = state(code); print(w, "after Next", st2["cur"]); assert st2["cur"] == 1
      print(w, "calls", await page.evaluate("[...new Set(window.__calls)]"))
      # viewer, alone and framed by another page
      vctx = await b.new_context(viewport={"width": 1280 if w > 500 else 390, "height": 720 if w > 500 else 700})
      v = await vctx.new_page(); await v.goto(url); await v.wait_for_function("document.querySelector('#im') && !document.querySelector('#im').hidden && document.querySelector('#im').naturalWidth > 0", timeout=20000)
      print(w, "viewer image", await v.evaluate("[im.naturalWidth, im.naturalHeight]")); await v.screenshot(path=str(OUT / f"live_viewer_{w}.png"))
      await page.click("#btn-next", force=True); await page.wait_for_timeout(3500)
      cur = state(code)["cur"]; src = await v.evaluate("document.querySelector('#im').src"); print(w, "viewer follows", cur, src.split("/img/")[1][:3]); assert f"/img/{cur}?" in src
      host = await vctx.new_page()
      async def hroute(r):
        if r.request.url.startswith("https://host.test/"): await r.fulfill(body=f'<body style="margin:0;background:#222"><iframe src="{url}" style="border:0;width:640px;aspect-ratio:16/9"></iframe></body>', content_type="text/html")
        else: await r.continue_()
      await host.route("**/*", hroute); await host.goto("https://host.test/")
      fr = host.frames[1]; await fr.wait_for_function("document.querySelector('#im') && document.querySelector('#im').naturalWidth > 0", timeout=20000); print(w, "iframe ok"); await host.screenshot(path=str(OUT / f"live_embed_{w}.png"))
      await vctx.close()
      # stop: the link goes dark
      await page.click("#btn-live", force=True); await page.click("#lv-toggle"); await page.wait_for_function("document.querySelector('#lv-state').textContent.trim() === 'Not live'", timeout=20000)
      print(w, "after stop", {k: state(code)[k] for k in ("live", "count")})
      print(w, "errors", errs); await ctx.close()
  await b.close()
asyncio.run(main())
