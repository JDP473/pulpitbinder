"""Deleting sermons: one or many at once from the Sermon menu, from this device and the account, including sermons
that are only in the account, the sermon that is open, a failed account delete, and a page with no account at all.
Run with "phone" or "dark" for those screenshots too."""
import asyncio, pathlib, json, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()

TEXTS = ["Psalm 23", "Romans 12:1-2", "John 15:1-8", "Romans 5:1-5", "Micah 6:8", "James 1:22", "Acts 2:38", "Hebrews 11:1"]
RECS = [{"id": "s%02d" % i, "updatedAt": 1700000000000 + i * 1000, "meta": {"title": "Sample sermon %d" % (i + 1), "text": t,
         "when": "2026-%02d-%02dT10:00" % (1 + i, 4 + i), "service": "Sunday AM", "place": "Test congregation", "speaker": "Test speaker", "wpm": 140, "series": ""},
         "html": "<p>A generic paragraph about %s for testing.</p>" % t, "slides": [], "manual": {}, "ai": None} for i, t in enumerate(TEXTS)]
# two sermons only in the account, with their parts
CLOUD = {}
for i, cid in enumerate(["c1", "c2"]):
    base = "data/users/u1/" + cid
    CLOUD[base] = {"id": cid, "updatedAt": 1600000000000 + i, "title": "Account sermon %d" % (i + 1), "when": "2025-0%d-01T10:00" % (i + 3),
                   "meta": {"title": "Account sermon %d" % (i + 1), "text": "Luke 15", "when": "2025-0%d-01T10:00" % (i + 3), "service": "Sunday PM"},
                   "chunks": {"core": 1, "html": 1, "preached": 1, "pdf": 1}, "slideCount": 0, "deckVer": 0}
    for name in ["core", "html", "preached", "pdf"]: CLOUD[base + "/parts/%s.0" % name] = {"s": "{}" if name in ("core", "pdf") else "<p>Generic.</p>" if name == "html" else ""}

INIT = """
const store = new Map(Object.entries(%s).map(([k, v]) => [k, JSON.stringify(v)]));
window.__store = store; window.__failDelete = null;
const subs = [];
const snap = path => ({ id: path.split('/').pop(), exists: store.has(path), data: () => store.has(path) ? JSON.parse(store.get(path)) : undefined, metadata: { hasPendingWrites: false } });
const notify = () => setTimeout(() => subs.forEach(f => f()), 0);
const doc = path => ({ async get() { return snap(path); }, async set(v) { store.set(path, JSON.stringify(v)); notify(); },
  async delete() { await new Promise(r => setTimeout(r, 5)); if (window.__failDelete && path.includes(window.__failDelete)) throw { code: 'invalid_argument' }; store.delete(path); notify(); },
  onSnapshot(cb) { cb(snap(path)); return () => {}; } });
const collection = path => ({ doc: id => doc(path + '/' + id), orderBy() { return this; }, limit() { return this; }, async get() { return { docs: [] }; },
  onSnapshot(cb) { let sent = new Set(); const f = () => { const n = path.split('/').length + 1;
    const now = [...store.keys()].filter(k => k.startsWith(path + '/') && k.split('/').length === n);
    const ch = now.map(k => ({ type: sent.has(k) ? 'modified' : 'added', doc: snap(k) })).concat([...sent].filter(k => !store.has(k)).map(k => ({ type: 'removed', doc: snap(k) })));
    sent = new Set(now); cb({ docChanges: () => ch }); }; subs.push(f); setTimeout(f, 0); return () => {}; } });
const db = { doc, collection };
window.claude = %s;
"""
WITH_ACCOUNT = "{ use: async n => n === 'db' ? db : n === 'user' ? { id: async () => 'u1' } : null }"
NO_ACCOUNT = "undefined"

fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"got {got!r} want {want!r}")
    if not ok: fails.append(name)

async def open_page(b, claude, w=1400, dark=False):
    ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme="dark" if dark else "light")
    await ctx.add_init_script(INIT % (json.dumps(CLOUD), claude))
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.goto("https://x.test/#build"); await page.wait_for_timeout(600)
    await page.evaluate("""recs => new Promise(res => { const q = indexedDB.open('pulpit-binder', 2); q.onsuccess = () => { const tx = q.result.transaction('sermons','readwrite'); const st = tx.objectStore('sermons'); st.clear(); recs.forEach(r => st.put(r)); tx.oncomplete = () => { q.result.close(); res(); }; }; })""", RECS)
    await page.reload(); await page.wait_for_timeout(1500)
    return page, errs

LOCAL_IDS = "new Promise(res => { const q = indexedDB.open('pulpit-binder', 2); q.onsuccess = () => { const g = q.result.transaction('sermons').objectStore('sermons').getAllKeys(); g.onsuccess = () => res(g.result.sort()); }; })"
CLOUD_KEYS = "[...window.__store.keys()].filter(k => !k.includes('/_')).sort()"

async def menu(page, item):
    await page.click("#btn-sermon"); await page.click(item); await page.wait_for_timeout(300)

async def main():
    phone, dark = "phone" in sys.argv, "dark" in sys.argv
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page, errs = await open_page(b, WITH_ACCOUNT, 390 if phone else 1400, dark)
        sfx = "_phone" if phone else "_dark" if dark else ""
        check("all 8 local sermons synced to the account", len([k for k in await page.evaluate(CLOUD_KEYS) if k.count("/") == 3]), 10)
        check("library lists 10", await page.evaluate("document.querySelectorAll('#library option').length"), 10)

        check("Sample sermon 8 is open", await page.input_value("#m-title"), "Sample sermon 8")
        await menu(page, "#btn-del-many")
        check("dialog open", await page.is_visible("#del-modal"), True)
        check("10 rows, newest first", await page.evaluate("[...document.querySelectorAll('#del-list .del-row b')].map(x => x.textContent).slice(0, 2)"), ["Sample sermon 8", "Sample sermon 7"])
        check("nothing selected, delete disabled", await page.is_disabled("#del-go"), True)
        await page.screenshot(path=str(OUT / f"delete_dialog{sfx}.png"))

        await page.fill("#del-q", "romans"); await page.wait_for_timeout(100)
        check("search narrows to the two Romans sermons", await page.evaluate("document.querySelectorAll('#del-list .del-row').length"), 2)
        await page.check("#del-all")
        check("select all shown picks both", await page.text_content("#del-go"), "Delete 2 sermons")
        await page.fill("#del-q", ""); await page.wait_for_timeout(100)
        check("selection survives clearing the search", await page.evaluate("document.querySelectorAll('#del-list .del-row.on').length"), 2)
        check("select-all shows partly checked", await page.evaluate("document.querySelector('#del-all').indeterminate"), True)
        await page.click("label[for='del-c-c1']"); await page.click("label[for='del-c-s07']")
        check("four selected", await page.text_content("#del-go"), "Delete 4 sermons")
        await page.screenshot(path=str(OUT / f"delete_selected{sfx}.png"))
        await page.click("#del-go")
        check("first press asks again", await page.text_content("#del-go"), "Yes, delete all 4")
        check("nothing deleted yet", len(await page.evaluate(LOCAL_IDS)), 8)
        await page.screenshot(path=str(OUT / f"delete_confirm{sfx}.png"))
        await page.click("#del-go"); await page.wait_for_timeout(1500)
        check("dialog closed", await page.is_visible("#del-modal"), False)
        check("toast", await page.text_content("#toast"), "4 sermons deleted")
        local = await page.evaluate(LOCAL_IDS)
        check("removed from this device", [x for x in ["s01", "s03", "s07"] if x in local], [])
        keys = await page.evaluate(CLOUD_KEYS)
        check("removed from the account, parts and all", [k for k in keys if any(f"/{x}" in k for x in ["s01", "s03", "s07", "c1"])], [])
        check("others untouched in the account", len([k for k in keys if k.count("/") == 3]), 6)
        await page.wait_for_timeout(400)
        check("library lists 6", await page.evaluate("document.querySelectorAll('#library option').length"), 6)
        check("the open sermon (Sample sermon 8) was deleted, so another is open", (await page.input_value("#m-title")) in ["Sample sermon 2", "Sample sermon 4", "Sample sermon 8"], False)
        check("library shows the sermon now open", await page.evaluate("document.querySelector('#library').value"), await page.evaluate("[...document.querySelectorAll('#library option')].find(o => o.selected).value"))

        # Delete this sermon: preselects the open one
        title = await page.input_value("#m-title")
        await menu(page, "#btn-del")
        check("open sermon preselected", await page.evaluate("[...document.querySelectorAll('#del-list .del-row.on b')].map(x => x.textContent)"), [title])
        check("one-sermon label", await page.text_content("#del-go"), "Delete 1 sermon")
        await page.click("#del-go"); check("asks again", await page.text_content("#del-go"), "Yes, delete it")
        await page.click("#del-go"); await page.wait_for_timeout(1200)
        check("single delete toast", await page.text_content("#toast"), "Sermon deleted")
        check("another sermon opened", await page.input_value("#m-title") != title, True)

        # Escape cancels, and an arm times out back to the normal label
        await menu(page, "#btn-del-many")
        await page.keyboard.press("Escape"); check("Escape closes", await page.is_visible("#del-modal"), False)

        # a failed account delete is reported and the sermon stays listed as in the account
        await page.evaluate("window.__failDelete = 'c2'")
        await menu(page, "#btn-del-many")
        await page.click("label[for='del-c-c2']"); await page.click("#del-go"); await page.click("#del-go"); await page.wait_for_timeout(1200)
        check("failure reported", "couldn't be removed from your account" in await page.text_content("#toast"), True)
        check("still listed", await page.evaluate("[...document.querySelectorAll('#library option')].some(o => o.value === 'c2')"), True)
        await page.screenshot(path=str(OUT / f"delete_after{sfx}.png"))

        # delete everything that's left: the page falls back to the example sermon
        await page.evaluate("window.__failDelete = null")
        await menu(page, "#btn-del-many"); await page.check("#del-all"); await page.click("#del-go"); await page.click("#del-go"); await page.wait_for_timeout(2000)
        check("account empty of sermons", [k for k in await page.evaluate(CLOUD_KEYS) if k.startswith("data/users/u1/")], [])
        check("example sermon shown", (await page.input_value("#m-title")).endswith("(example)"), True)
        check("no horizontal scroll", await page.evaluate("document.documentElement.scrollWidth <= innerWidth"), True)
        check("no page errors", errs, [])

        # no account: deletes from this browser only
        page2, errs2 = await open_page(b, NO_ACCOUNT)
        await menu(page2, "#btn-del-many")
        check("intro says this browser", "removed from this browser" in await page2.text_content("#del-intro"), True)
        await page2.click("label[for='del-c-s00']"); await page2.click("label[for='del-c-s02']"); await page2.click("#del-go"); await page2.click("#del-go"); await page2.wait_for_timeout(800)
        check("no account: removed locally", len(await page2.evaluate(LOCAL_IDS)), 6)
        check("no account: no errors", errs2, [])
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
    sys.exit(1 if fails else 0)
asyncio.run(main())
