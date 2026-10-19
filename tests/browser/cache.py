"""Saved Claude answers: the same request is answered from the saved copy on this device, then from the
account on a device that has never seen it, and the next press of the same button asks fresh."""
import asyncio, pathlib, datetime
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
NOW = datetime.datetime(2026, 10, 20, 14, 0, tzinfo=datetime.timezone.utc)
# A mock account database kept in localStorage, so it outlives a wiped IndexedDB (a second device).
INIT = """
const LS = k => JSON.parse(localStorage.getItem(k) || 'null');
const store = new Map(Object.entries(LS('__db') || {}));
const persist = () => localStorage.setItem('__db', JSON.stringify(Object.fromEntries(store)));
const subs = [];
const snap = path => ({ id: path.split('/').pop(), exists: store.has(path), data: () => store.has(path) ? JSON.parse(store.get(path)) : undefined, metadata: { hasPendingWrites: false } });
const doc = path => ({ async get() { return snap(path); }, async set(v) { store.set(path, JSON.stringify(v)); persist(); subs.forEach(f => f()); },
  async delete() { store.delete(path); persist(); }, onSnapshot(cb) { cb(snap(path)); return () => {}; }, collection: sub => collection(path + '/' + sub) });
const collection = path => ({ doc: id => doc(path + '/' + id), onSnapshot(cb) { const f = () => { const n = path.split('/').length + 1;
  const docs = [...store.keys()].filter(k => k.startsWith(path + '/') && k.split('/').length === n).map(snap);
  cb({ docChanges: () => docs.map(d => ({ type: 'added', doc: d })) }); }; subs.push(f); setTimeout(f, 0); return () => {}; } });
const db = { doc, collection };
const calls = () => +(localStorage.getItem('__calls') || 0);
const smp = async () => ({ text: '' });
smp.json = async (p, o) => { localStorage.setItem('__calls', calls() + 1); window.__opts = o; await new Promise(r => setTimeout(r, 150));
  return { bigIdea: 'Walk by the light you have, run ' + calls(), summary: 'A short summary.', approach: 'Textual', themes: ['Faith'], doctrines: [], strengths: ['Clear'], gaps: [] }; };
smp.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? smp : n === 'db' ? db : n === 'user' ? { id: async () => 'u1' } : null };
"""
fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"got {got!r} want {want!r}")
    if not ok: fails.append(name)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1400, "height": 900}, timezone_id="America/Chicago")
        await ctx.add_init_script(INIT)
        page = await ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8></head><body>" + HTML + "</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.clock.set_fixed_time(NOW)
        await page.goto("https://x.test/#analysis"); await page.wait_for_timeout(900)
        calls = "+(localStorage.getItem('__calls') || 0)"
        big = "document.querySelector('.big-idea') ? document.querySelector('.big-idea').textContent : ''"

        await page.click("#btn-ai"); await page.wait_for_timeout(500)
        check("first press asks Claude", await page.evaluate(calls), 1)
        check("asks with the 24-hour platform cache", await page.evaluate("JSON.stringify(window.__opts.cache)"), '{"gcTime":86400000}')
        await page.click("#btn-ai"); await page.wait_for_timeout(400)
        check("same request uses the saved answer", await page.evaluate(calls), 1)
        check("viewer is told no usage was spent", "no usage was spent" in await page.text_content("#toast"), True)
        await page.screenshot(path=str(OUT / "cache_toast.png"), clip={"x": 0, "y": 500, "width": 1400, "height": 400})
        await page.click("#btn-ai"); await page.wait_for_timeout(500)
        check("next press asks fresh", (await page.evaluate(calls), await page.evaluate("!!window.__opts.cache.refresh")), (2, True))
        check("fresh answer shown", "run 2" in await page.evaluate(big), True)

        await page.reload(); await page.wait_for_timeout(900)
        await page.click("#btn-ai"); await page.wait_for_timeout(400)
        check("after reload, answered from this device", await page.evaluate(calls), 2)
        check("saved answer is the latest one", "run 2" in await page.evaluate(big), True)
        check("answer saved to the account", await page.evaluate("Object.keys(JSON.parse(localStorage.getItem('__db'))).filter(k => k.startsWith('data/users/u1/_cache/ai/')).length"), 1)

        # a second device: nothing in IndexedDB, same account
        await page.evaluate("new Promise(r => { const q = indexedDB.deleteDatabase('pulpit-binder'); q.onsuccess = q.onerror = q.onblocked = () => r(); })")
        await page.reload(); await page.wait_for_timeout(1200)
        check("this device has no saved answers", await page.evaluate("new Promise(r => { const q = indexedDB.open('pulpit-binder'); q.onsuccess = () => { try { const g = q.result.transaction('kv').objectStore('kv').getAll(); g.onsuccess = () => r(g.result.filter(x => x.k.startsWith('ai-')).length); } catch (e) { r(-1); } }; })"), 0)
        await page.click("#btn-ai"); await page.wait_for_timeout(400)
        check("other device answered from the account", await page.evaluate(calls), 2)
        check("page errors", errs, [])
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
asyncio.run(main())
