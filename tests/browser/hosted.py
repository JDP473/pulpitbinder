"""sermon.freely.church: the real server (saas/) with a stand-in for Anthropic's API, driven in Chromium.
Signs up, opens the app, checks it syncs between two devices, asks Claude through the shim, and shows the account,
admin, and public pages in light, dark, and on a phone. Screenshots go to tests/out/hosted_*."""
import asyncio, json, os, pathlib, shutil, socket, sqlite3, subprocess, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
JSZIP = (ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read_text()
SHOTS = ROOT / "saas" / "web" / "shots"

class Anthropic(BaseHTTPRequestHandler):
    """Answers every prompt with a little generic JSON, the way the app asks for it."""
    calls = []
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"id": "claude-haiku-5-5", "type": "model"}).encode())
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Anthropic.calls.append(body)
        text = json.dumps({"ok": True, "bigIdea": "Walk by the light you have.", "text": "Walk by the light you have."})
        out = {"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn", "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 50, "output_tokens": 20}}
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

async def main():
    mock = ThreadingHTTPServer(("127.0.0.1", 0), Anthropic); threading.Thread(target=mock.serve_forever, daemon=True).start()
    data = tempfile.mkdtemp(prefix="pb-hosted-")
    port = free_port(); base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PORT": str(port), "DATA_DIR": data, "APP_URL": base, "PLATFORM_OWNER_EMAIL": "owner@example.com",
           "ANTHROPIC_API_KEY": "sk-ant-shared-key-0000000000", "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{mock.server_address[1]}", "SMTP_HOST": "", "STRIPE_SECRET_KEY": ""}
    srv = subprocess.Popen(["node", "server/index.js"], cwd=ROOT / "saas", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(100):
        try: urllib.request.urlopen(base + "/api/health"); break
        except Exception: time.sleep(0.1)
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            async def route(r):
                u = r.request.url
                if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
                elif u.startswith(base): await r.continue_()
                else: await r.abort()
            async def new_page(w=1400, scheme="light", ctx=None):
                ctx = ctx or await b.new_context(viewport={"width": w, "height": 900 if w > 600 else 844}, color_scheme=scheme)
                pg = await ctx.new_page(); pg.errs = []
                pg.on("pageerror", lambda e: pg.errs.append(str(e)))
                await pg.route("**/*", route)
                return ctx, pg

            # 1. The public page, signed out
            for w, scheme in [(1400, "light"), (1400, "dark"), (390, "light")]:
                ctx, pg = await new_page(w, scheme)
                await pg.goto(base + "/"); await pg.wait_for_timeout(300)
                await pg.screenshot(path=str(OUT / f"hosted_landing_{w}_{scheme}.png"), full_page=(w == 390))
                print("landing", w, scheme, "scrollW", await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"), "errors", pg.errs)
                await ctx.close()

            # 2. Sign up and open the binder
            ctx, pg = await new_page()
            await pg.goto(base + "/register"); await pg.wait_for_selector("form")
            await pg.screenshot(path=str(OUT / "hosted_register_1400_light.png"))
            await pg.fill("input[name=name]", "Pat Preacher"); await pg.fill("input[name=email]", "pat@example.com"); await pg.fill("input[name=password]", "correct horse battery")
            await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app"); await pg.wait_for_timeout(2500)
            print("app: title", await pg.title(), "sync", await pg.text_content("#sync"), "speaker default", await pg.evaluate("JSON.parse(localStorage.getItem('pb-settings') || '{}').speaker || null"))
            print("app: no-key notice", await pg.evaluate("[...document.querySelectorAll('[role=status]')].map(e => e.textContent).find(t => t.includes('Anthropic API key')) || null"))
            print("app: live view button hidden", await pg.evaluate("document.querySelector('#btn-live').hidden"))
            await pg.click("#btn-sermon"); await pg.wait_for_timeout(200)
            print("app: More menu has", await pg.evaluate("[...document.querySelectorAll('#sermon-menu .menu-item')].map(b => b.textContent).slice(-2)"))
            await pg.screenshot(path=str(OUT / "hosted_app_menu_1400_light.png"))
            await pg.keyboard.press("Escape")

            # Claude without a key: the shim says where to add one
            r = await pg.evaluate("window.claude.use('sample').then(s => s.json('Return ONLY JSON {\"a\":1}', { modelTier: 'quick' })).then(v => ['ok', v], e => ['err', e.code])")
            print("claude without key", r)

            # 3. Make a sermon of our own, then see it on a second device
            await pg.evaluate("document.querySelector('#btn-new-top').click()"); await pg.wait_for_timeout(600)
            await pg.fill("#m-title", "Walking in the Light"); await pg.wait_for_timeout(300)
            await pg.evaluate("document.querySelector('#sub-edit').click()"); await pg.wait_for_timeout(600)
            await pg.evaluate("""() => { const ed = document.querySelector('#editor'); ed.focus(); const r = document.createRange(); r.selectNodeContents(ed); r.collapse(false); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""")
            await pg.keyboard.type("Walking in the light is a daily choice. ")
            uid = await pg.evaluate("window.__PB__.id")
            for _ in range(60):
                if sqlite3.connect(os.path.join(data, "pulpit.db")).execute("SELECT COUNT(*) FROM docs WHERE user_id = ? AND data LIKE '%daily choice%'", (uid,)).fetchone()[0]: break
                await pg.wait_for_timeout(250)
            uid = await pg.evaluate("window.__PB__.id")
            rows = sqlite3.connect(os.path.join(data, "pulpit.db")).execute("SELECT path FROM docs WHERE user_id = ? AND data IS NOT NULL", (uid,)).fetchall()
            print("server has", len(rows), "documents, sermons:", len([r for r in rows if r[0].count('/') == 3 and not r[0].split('/')[3].startswith('_')]))
            cookies = await ctx.cookies()
            ctx2 = await b.new_context(viewport={"width": 1400, "height": 900}); await ctx2.add_cookies(cookies)
            _, pg2 = await new_page(ctx=ctx2)
            await pg2.goto(base + "/app"); await pg2.wait_for_timeout(3000)
            await pg2.evaluate("document.querySelector('#sub-edit').click()"); await pg2.wait_for_timeout(600)
            await pg2.screenshot(path=str(OUT / "hosted_device2_1400_light.png"))
            print("second device: sync", await pg2.text_content("#sync"), "title", await pg2.text_content("#sc-title"), "sees the words", await pg2.evaluate("document.querySelector('#editor').textContent.includes('Walking in the light is a daily choice')"))
            # an edit on the first device reaches the second through the live feed
            await pg.keyboard.type("Second sentence from the first device. ")
            for _ in range(60):
                if sqlite3.connect(os.path.join(data, "pulpit.db")).execute("SELECT COUNT(*) FROM docs WHERE user_id = ? AND data LIKE '%first device%'", (uid,)).fetchone()[0]: break
                await pg.wait_for_timeout(250)
            await pg2.evaluate("document.activeElement && document.activeElement.blur()")
            await pg2.wait_for_timeout(7000)
            print("second device: live update", await pg2.evaluate("document.querySelector('#editor').textContent.includes('Second sentence from the first device')"))
            print("errors", pg.errs, pg2.errs)
            await ctx2.close()

            # 4. Account: add a key, then Claude answers through the shim
            await pg.goto(base + "/account"); await pg.wait_for_selector("#claude")
            await pg.screenshot(path=str(OUT / "hosted_account_nokey_1400_light.png"), full_page=True)
            await pg.fill("input[name=key]", "sk-ant-own-key-1111111111111"); await pg.click("#claude ~ div button[type=submit], form:has(input[name=key]) button[type=submit]"); await pg.wait_for_timeout(800)
            print("account: key status", await pg.text_content(".status"))
            await pg.goto(base + "/app"); await pg.wait_for_timeout(1500)
            Anthropic.calls.clear()
            r = await pg.evaluate("window.claude.use('sample').then(s => s.json('Return ONLY JSON {\"text\":\"\"}', { modelTier: 'default' })).then(v => ['ok', v], e => ['err', e.code])")
            print("claude with key", r, "model", Anthropic.calls and Anthropic.calls[-1]["model"])

            # 4b. Share "Walking in the Light" by email from the More menu
            await pg.click("#sc-title"); await pg.wait_for_timeout(300)
            await pg.click("#sp-modal .sp-item:has-text('Walking in the Light')"); await pg.wait_for_timeout(800)
            await pg.click("#btn-sermon"); await pg.wait_for_timeout(200)
            await pg.click("#sermon-menu .menu-item:has-text('Share this sermon')"); await pg.wait_for_selector("#sh-email")
            await pg.fill("#sh-email", "ivy@example.com"); await pg.fill("#sh-note", "For Sunday night, if it helps.")
            await pg.click(".sh-modal button[type=submit]"); await pg.wait_for_selector(".sh-row"); await pg.wait_for_timeout(300)
            print("share: dialog says", await pg.evaluate("document.querySelector('.sh-modal [role=status]').textContent"), "| list", await pg.evaluate("[...document.querySelectorAll('.sh-row')].map(r => r.textContent)"))
            await pg.screenshot(path=str(OUT / "hosted_share_dialog_1400_light.png"))
            await pg.keyboard.press("Escape"); await pg.wait_for_timeout(200)
            print("share: Escape closes", await pg.evaluate("!document.querySelector('.sh-modal')"))
            await ctx.close()

            for w, scheme in [(1400, "light"), (390, "dark")]:
                ctx, pg = await new_page(w, scheme)
                email = f"ivy{w}@example.com"
                await pg.goto(base + "/register"); await pg.fill("input[name=name]", "Ivy Receiver"); await pg.fill("input[name=email]", email); await pg.fill("input[name=password]", "correct horse battery")
                await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app"); await pg.wait_for_timeout(1500)
                db = sqlite3.connect(os.path.join(data, "pulpit.db"))
                db.execute("UPDATE shares SET to_email = ? WHERE to_email = 'ivy@example.com'", (email,)); db.commit()
                await pg.reload(); await pg.wait_for_timeout(2500)
                print(w, "share: unconfirmed sees", await pg.evaluate("[document.querySelectorAll('.sh-card').length, [...document.querySelectorAll('[role=status]')].some(e => e.textContent.includes('Confirm your email'))]"))
                db.execute("UPDATE users SET email_verified_at = '2026-10-25T00:00:00Z' WHERE email = ?", (email,)); db.commit(); db.close()
                await pg.reload(); await pg.wait_for_selector(".sh-card"); await pg.wait_for_timeout(500)
                await pg.screenshot(path=str(OUT / f"hosted_share_card_{w}_{scheme}.png"))
                print(w, "share: card", await pg.text_content(".sh-card"))
                await pg.click(".sh-card button:has-text('Add to my binder')"); await pg.wait_for_timeout(2500)
                print(w, "share: opened", await pg.text_content("#sc-title"), "cards left", await pg.evaluate("document.querySelectorAll('.sh-card').length"), "errors", pg.errs)
                await pg.evaluate("document.querySelector('#sub-edit').click()"); await pg.wait_for_timeout(800)
                print(w, "share: words came along", await pg.evaluate("document.querySelector('#editor').textContent.includes('Walking in the light is a daily choice')"), "scrollW", await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
                await pg.screenshot(path=str(OUT / f"hosted_share_added_{w}_{scheme}.png"))
                # put the share back for the next size
                db = sqlite3.connect(os.path.join(data, "pulpit.db")); db.execute("UPDATE shares SET to_email = 'ivy@example.com', accepted_at = NULL, accepted_by = NULL, copy_id = NULL WHERE to_email = ?", (email,)); db.commit(); db.close()
                await ctx.close()

            # 5. Another account on the same browser starts with an empty binder
            ctx, pg = await new_page()
            await pg.goto(base + "/register"); await pg.wait_for_selector("form")
            await pg.fill("input[name=name]", "Pat Preacher"); await pg.fill("input[name=email]", "pat2@example.com"); await pg.fill("input[name=password]", "correct horse battery")
            await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app"); await pg.wait_for_timeout(2500)
            await pg.evaluate("document.querySelector('#btn-new-top').click()"); await pg.wait_for_timeout(600)
            await pg.fill("#m-title", "Pat two's sermon"); await pg.wait_for_timeout(1500)
            IDB = """new Promise(ok => { const q = indexedDB.open('pulpit-binder'); q.onsuccess = () => { const d = q.result; if (!d.objectStoreNames.contains('sermons')) return ok([]); const g = d.transaction('sermons').objectStore('sermons').getAll(); g.onsuccess = () => ok(g.result.map(r => r.meta && r.meta.title)); }; q.onerror = () => ok([]); })"""
            print("pat2's browser holds", await pg.evaluate(IDB))
            # The session ends without signing out (cookies cleared), and someone else signs in on this browser
            await ctx.clear_cookies()
            await pg.goto(base + "/register"); await pg.fill("input[name=name]", "Sam Preacher"); await pg.fill("input[name=email]", "owner@example.com"); await pg.fill("input[name=password]", "correct horse battery")
            await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app"); await pg.wait_for_timeout(2500)
            print("next account on the same browser holds", await pg.evaluate(IDB))
            # The Sign out button beside Settings clears this browser's copy too
            await pg.screenshot(path=str(OUT / "hosted_signout_1400_light.png"))
            print("sign out button", await pg.evaluate("(b => b && [b.textContent, b.getAttribute('aria-label'), b.getBoundingClientRect().width > 0])(document.querySelector('#btn-signout'))"))
            await pg.click("#btn-signout"); await pg.wait_for_url(base + "/"); await pg.wait_for_timeout(500)
            print("after sign out", await pg.evaluate(IDB), "signed-in data attr", await pg.evaluate("document.documentElement.dataset.auth"))
            await ctx.close()

            # On a phone, Sign out sits in the header beside Settings and Light or dark
            ctx, pg = await new_page(390, "dark")
            await pg.goto(base + "/login"); await pg.fill("input[name=email]", "pat2@example.com"); await pg.fill("input[name=password]", "correct horse battery")
            await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app"); await pg.wait_for_timeout(2500)
            await pg.screenshot(path=str(OUT / "hosted_signout_390_dark.png"))
            print("phone sign out visible", await pg.is_visible("#btn-signout"), "scrollW", await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
            await pg.click("#btn-signout"); await pg.wait_for_url(base + "/"); await pg.wait_for_timeout(300)
            print("phone signed out", await pg.evaluate("document.documentElement.dataset.auth"), "errors", pg.errs)
            # The account pages' header has one too
            await pg.goto(base + "/login"); await pg.fill("input[name=email]", "pat2@example.com"); await pg.fill("input[name=password]", "correct horse battery")
            await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app")
            await pg.goto(base + "/account"); await pg.wait_for_selector("#claude")
            await pg.screenshot(path=str(OUT / "hosted_account_header_390_dark.png"))
            print("header sign out hidden on phone", not await pg.is_visible("header #signout")); await pg.set_viewport_size({"width": 1000, "height": 800}); await pg.click("header #signout"); await pg.wait_for_url(base + "/"); await pg.wait_for_timeout(300)
            print("account header sign out", await pg.evaluate("document.documentElement.dataset.auth"))
            await ctx.close()

            # 6. The owner's admin page (address confirmed, as the emailed link would)
            db = sqlite3.connect(os.path.join(data, "pulpit.db")); db.execute("UPDATE users SET email_verified_at = '2026-10-25T00:00:00Z' WHERE email = 'owner@example.com'"); db.commit(); db.close()
            for w, scheme in [(1400, "light"), (1400, "dark"), (390, "dark")]:
                ctx, pg = await new_page(w, scheme)
                await pg.goto(base + "/login"); await pg.fill("input[name=email]", "owner@example.com"); await pg.fill("input[name=password]", "correct horse battery")
                await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app")
                await pg.goto(base + "/admin"); await pg.wait_for_selector("table"); await pg.wait_for_timeout(300)
                if w == 1400 and scheme == "light":
                    await pg.click("tr:has-text('pat2@example.com') input[type=checkbox] >> nth=0"); await pg.wait_for_timeout(300)
                await pg.screenshot(path=str(OUT / f"hosted_admin_{w}_{scheme}.png"), full_page=True)
                await pg.goto(base + "/account"); await pg.wait_for_selector("#claude"); await pg.wait_for_timeout(300)
                await pg.screenshot(path=str(OUT / f"hosted_account_{w}_{scheme}.png"), full_page=True)
                print("owner pages", w, scheme, "scrollW", await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"), "errors", pg.errs)
                await ctx.close()
            print("pat2 lent the shared key", sqlite3.connect(os.path.join(data, "pulpit.db")).execute("SELECT shared_key FROM users WHERE email = 'pat2@example.com'").fetchone()[0] == 1)

            # 7. Screens for the public page: the example sermon in the binder, on a computer and a phone
            if os.environ.get("SHOTS"):
                SHOTS.mkdir(exist_ok=True)
                for w, name in [(1400, "desktop"), (390, "phone")]:
                    ctx, pg = await new_page(w, "light")
                    await pg.goto(base + "/login"); await pg.fill("input[name=email]", "owner@example.com"); await pg.fill("input[name=password]", "correct horse battery")
                    await pg.click("button[type=submit]"); await pg.wait_for_url(base + "/app")
                    await pg.unroute("**/*"); await pg.route("**/*", lambda r: r.abort() if not (r.request.url.startswith(base) or "fonts.g" in r.request.url or "jszip" in r.request.url) else (r.fulfill(body=JSZIP, content_type="application/javascript") if "jszip" in r.request.url else r.continue_()))
                    await pg.goto(base + "/app"); await pg.wait_for_timeout(2500)
                    await pg.evaluate("document.querySelector('#sub-edit').click()" if w > 600 else "document.querySelector('#tab-present').click()")
                    await pg.wait_for_timeout(2500)
                    await pg.evaluate("document.querySelectorAll('[role=status]').forEach(e => { if (e.textContent.includes('Anthropic')) e.remove(); })")
                    await pg.screenshot(path=str(SHOTS / f"{name}.png"))
                    await ctx.close()
            await b.close()
    finally:
        srv.terminate(); log = srv.stdout.read().decode()
        if "[error]" in log: print("server log:\n" + log)
        mock.shutdown(); shutil.rmtree(data, ignore_errors=True)

asyncio.run(main())
