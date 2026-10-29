"""sermon.freely.church pictures on the preacher's own keys: the real server (saas/) with stand-ins for Anthropic and the
picture services, driven in Chromium. Adds an OpenAI key in Account, chooses OpenAI in Settings, and paints an
Illustration slide with it. Screenshots go to tests/out/hosted_pic_*."""
import asyncio, json, os, pathlib, shutil, socket, subprocess, tempfile, threading, time, urllib.request, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
JSZIP = (ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read_text()
PICTURE = (ROOT / "saas" / "web" / "shots" / "desktop.png").read_bytes()
SEL = """() => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const t = n.textContent; if (t.length > 40 && !n.parentElement.closest('.pb-slide,.pb-scripture')) { const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 30); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""

class Stand(BaseHTTPRequestHandler):
    """Anthropic at /v1, OpenAI at /openai. Any key is accepted; every picture is the same PNG."""
    calls = []
    def log_message(self, *a): pass
    def send(self, status, body, kind="application/json"):
        self.send_response(status); self.send_header("content-type", kind); self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())
    def do_GET(self):
        if self.path.startswith("/openai/v1/models"): return self.send(200, {"data": []})
        self.send(200, {"id": "claude-haiku-5-5", "type": "model"})
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length") or 0))
        body = json.loads(raw) if raw else {}
        Stand.calls.append((self.path, body))
        if self.path == "/openai/v1/images/generations":
            return self.send(200, {"created": 1, "data": [{"b64_json": base64.b64encode(PICTURE).decode()}]})
        prompt = body["messages"][0]["content"] if "messages" in body else ""
        value = {"prompt": "A single oil lamp on a stone path at dusk", "caption": "Light for the next step"} if "picture" in prompt.lower() else {"ok": True}
        self.send(200, {"id": "msg_1", "type": "message", "role": "assistant", "model": body.get("model", ""), "stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(value)}], "usage": {"input_tokens": 50, "output_tokens": 20}})

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

async def main():
    mock = ThreadingHTTPServer(("127.0.0.1", 0), Stand); threading.Thread(target=mock.serve_forever, daemon=True).start()
    mb = f"http://127.0.0.1:{mock.server_address[1]}"
    data = tempfile.mkdtemp(prefix="pb-pics-")
    port = free_port(); base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PORT": str(port), "DATA_DIR": data, "APP_URL": base, "PLATFORM_OWNER_EMAIL": "owner@example.com",
           "ANTHROPIC_API_KEY": "", "ANTHROPIC_BASE_URL": mb, "IMAGE_API_BASE": mb, "SMTP_HOST": "", "STRIPE_SECRET_KEY": ""}
    srv = subprocess.Popen(["node", "server/index.js"], cwd=ROOT / "saas", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(100):
        try: urllib.request.urlopen(base + "/api/health"); break
        except Exception: time.sleep(0.1)
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            ctx = await b.new_context(viewport={"width": 1400, "height": 900}, color_scheme="light")
            pg = await ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            async def route(r):
                u = r.request.url
                if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
                elif u.startswith(base): await r.continue_()
                else: await r.abort()
            await pg.route("**/*", route)

            await pg.goto(base + "/register"); await pg.wait_for_selector("form")
            await pg.fill("input[name=name]", "Pat Preacher"); await pg.fill("input[name=email]", "pat@example.com"); await pg.fill("input[name=password]", "correct horse battery")
            await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app"); await pg.wait_for_timeout(1500)

            # Account: the Pictures card, then an Anthropic key and an OpenAI key
            await pg.goto(base + "/account"); await pg.wait_for_selector("#pictures")
            card = pg.locator(".card:has(#pictures)")
            print("account pictures", await card.locator("#pic-openai .status, #pic-google .status, #pic-stability .status, #pic-firefly .status").all_inner_texts())
            print("firefly fields", await pg.eval_on_selector_all("#pic-firefly input", "els => els.map(e => e.name)"))
            await card.screenshot(path=str(OUT / "hosted_pic_account_1400_light.png"))
            await pg.fill("form:has(input[placeholder='sk-ant-...']) input[name=key]", "sk-ant-own-key-1111111111111")
            await pg.click("form:has(input[placeholder='sk-ant-...']) button[type=submit]"); await pg.wait_for_timeout(600)
            await pg.fill("#pic-openai input[name=key]", "sk-proj-good-111111111111111111")
            await pg.click("#pic-openai button[type=submit]"); await pg.wait_for_selector("#pic-openai .status.ok")
            print("openai saved", await pg.inner_text("#pic-openai .status"), "|", await pg.inner_text("#pic-openai .msg"))
            await card.screenshot(path=str(OUT / "hosted_pic_account_saved_1400_light.png"))
            await pg.emulate_media(color_scheme="dark"); await card.screenshot(path=str(OUT / "hosted_pic_account_saved_1400_dark.png"))
            await pg.set_viewport_size({"width": 390, "height": 844}); await pg.wait_for_timeout(200)
            await card.screenshot(path=str(OUT / "hosted_pic_account_saved_390_dark.png"))
            print("account phone scrollW", await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
            await pg.emulate_media(color_scheme="light"); await pg.set_viewport_size({"width": 1400, "height": 900})

            # Settings: OpenAI ready, the others ask for a key; choose OpenAI
            await pg.goto(base + "/app"); await pg.wait_for_timeout(2000)
            await pg.click("#btn-settings"); await pg.wait_for_timeout(300); await pg.click("#set-tab-ai"); await pg.wait_for_timeout(200)
            opts = await pg.evaluate("[...document.querySelectorAll('#set-img .ai-opt')].map(o => [o.querySelector('b').textContent, (o.querySelector('.chip') || {}).textContent || 'ready'])")
            print("picture options", opts)
            print("keys card", await pg.inner_text(".ai-later .ai-card-h"), "|", await pg.inner_text("#set-keys-hint"), "| planned", await pg.eval_on_selector_all("#set-later li > span:first-child", "els => els.map(e => e.textContent)"))
            await pg.check("#set-img-openai-image"); await pg.locator("#set-img").screenshot(path=str(OUT / "hosted_pic_settings_1400_light.png"))
            await pg.click("#settings-form button[type=submit]"); await pg.wait_for_timeout(300)
            await pg.reload(); await pg.wait_for_timeout(2000)
            await pg.click("#btn-settings"); await pg.wait_for_timeout(300); await pg.click("#set-tab-ai"); await pg.wait_for_timeout(200)
            print("after reload, chosen", await pg.evaluate("(document.querySelector('#set-img input:checked') || {}).value"))
            await pg.click("#set-cancel"); await pg.wait_for_timeout(200)

            # An Illustration slide painted by OpenAI through the server
            await pg.click("#tab-build"); await pg.wait_for_timeout(200)
            await pg.evaluate("document.querySelector('#sub-edit').click()"); await pg.wait_for_timeout(600)
            assert await pg.evaluate(SEL), "no text to highlight"
            await pg.wait_for_timeout(250); await pg.evaluate("document.querySelector('#btn-make-slide').click()"); await pg.wait_for_timeout(300)
            print("art label", await pg.evaluate("[...document.querySelectorAll('#mk-kinds .mk-kind')].filter(k => k.textContent.includes('Illustration')).map(k => k.querySelector('.mk-ai').textContent)"))
            Stand.calls.clear()
            await pg.click("#mk-kinds button:has-text('Illustration')"); await pg.wait_for_selector("#mk-preview img.mk-img", timeout=15000)
            sent = [c for c in Stand.calls if c[0] == "/openai/v1/images/generations"]
            print("painted", await pg.evaluate("document.querySelector('#mk-preview img.mk-img').src.slice(0, 5)"), "requests", len(sent), "size", sent[0][1]["size"] if sent else None,
                  "prompt ok", bool(sent) and "oil lamp" in sent[0][1]["prompt"] and "worship slide" in sent[0][1]["prompt"])
            print("quality box", await pg.evaluate("(document.querySelector('#mk-hd b') || {}).textContent"))
            await pg.screenshot(path=str(OUT / "hosted_pic_art_1400_light.png"))
            await pg.click("#mk-add"); await pg.wait_for_timeout(500)
            print("slide added", await pg.evaluate("document.querySelectorAll('#editor .pb-slide').length > 0"))

            # Removing the key: the option asks for a key again, and painting tells them where to add it
            await pg.goto(base + "/account"); await pg.wait_for_selector("#pic-openai")
            pg.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await pg.click("#pic-openai summary"); await pg.click("#pic-openai button.danger"); await pg.wait_for_timeout(600)
            print("after remove", await pg.inner_text("#pic-openai .status"))
            await pg.goto(base + "/app"); await pg.wait_for_timeout(1500)
            await pg.click("#btn-settings"); await pg.wait_for_timeout(300); await pg.click("#set-tab-ai"); await pg.wait_for_timeout(200)
            print("openai option now", await pg.evaluate("(document.querySelector('label[for=set-img-openai-image] .chip') || {}).textContent"))
            print("errors", errs)
            await b.close()
    finally:
        srv.terminate(); mock.shutdown(); shutil.rmtree(data, ignore_errors=True)

asyncio.run(main())
