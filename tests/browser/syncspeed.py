"""How long a save takes to reach the account, and how much it sends. The mock account adds network delay to every
call and counts writes and uploads. A sermon with a 30-slide deck is synced once, then the page is reloaded (a new
session, as when the page is opened again later) and one word is typed: only the changed text should go up."""
import asyncio, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
LAT, UP = 120, 400   # ms per database call, ms per file upload

INIT = """
const LAT = %d, UP = %d, wait = ms => new Promise(r => setTimeout(r, ms));
const store = new Map(Object.entries(JSON.parse(localStorage.getItem('__db') || '{}')));
const persist = () => localStorage.setItem('__db', JSON.stringify(Object.fromEntries(store)));
const count = k => localStorage.setItem(k, +(localStorage.getItem(k) || 0) + 1);
const subs = [];
const snap = path => ({ id: path.split('/').pop(), exists: store.has(path), data: () => store.has(path) ? JSON.parse(store.get(path)) : undefined, metadata: { hasPendingWrites: false } });
const notify = () => setTimeout(() => subs.forEach(f => f()), 0);
const doc = path => ({ async get() { await wait(LAT); count('__gets'); return snap(path); },
  async set(v) { await wait(LAT); count('__sets'); store.set(path, JSON.stringify(v)); persist(); notify(); },
  async delete() { await wait(LAT); count('__dels'); store.delete(path); persist(); notify(); },
  onSnapshot(cb) { setTimeout(() => cb(snap(path)), 0); return () => {}; } });
const collection = path => ({ doc: id => doc(path + '/' + id), orderBy() { return this; }, limit() { return this; }, async get() { return { docs: [] }; },
  onSnapshot(cb) { let sent = new Set(); const f = () => { const n = path.split('/').length + 1;
    const now = [...store.keys()].filter(k => k.startsWith(path + '/') && k.split('/').length === n);
    const ch = now.map(k => ({ type: sent.has(k) ? 'modified' : 'added', doc: snap(k) })).concat([...sent].filter(k => !store.has(k)).map(k => ({ type: 'removed', doc: snap(k) })));
    sent = new Set(now); cb({ docChanges: () => ch }); }; subs.push(f); setTimeout(f, LAT); return () => {}; } });
let aid = +(localStorage.getItem('__aid') || 0);
const assets = { async upload(b) { await wait(UP); count('__ups'); aid++; localStorage.setItem('__aid', aid); return { id: 'a' + aid, url: '/_blob/a' + aid, sizeBytes: b.size }; } };
window.claude = { use: async n => n === 'db' ? { doc, collection } : n === 'user' ? { id: async () => 'u1' } : n === 'assets' ? assets : null };
""" % (LAT, UP)

SEED = """async () => {
  const blobs = [];
  for (let i = 0; i < 30; i++) { const c = document.createElement('canvas'); c.width = 320; c.height = 180; const x = c.getContext('2d'); x.fillStyle = `hsl(${i * 12},50%%,40%%)`; x.fillRect(0, 0, 320, 180); x.fillStyle = '#fff'; x.font = '40px sans-serif'; x.fillText('Slide ' + (i + 1), 40, 100); blobs.push(await new Promise(r => c.toBlob(r, 'image/jpeg', 0.8))); }
  const paras = Array.from({ length: 40 }, (_, i) => `<p>Generic paragraph ${i + 1} for testing how long a save takes to reach the account. ${'Words to give it some length. '.repeat(12)}</p>`).join('');
  const rec = { id: 'big', updatedAt: Date.now(), deckVer: 1, meta: { title: 'Thirty slide test', text: 'Psalm 23', when: '2026-10-18T10:00', service: 'Sunday AM', place: 'Test congregation', speaker: 'Test speaker', wpm: 140, series: '' },
    html: paras, slides: blobs.map((b, i) => ({ title: 'Slide ' + (i + 1), body: [], notes: '', exact: b, hidden: false })), pdfName: 'deck.pdf', pdfPages: blobs.map((b, i) => ({ blob: b, text: 'Slide ' + (i + 1) })), slidesFromPdf: true, manual: {}, ai: null };
  await new Promise(res => { const q = indexedDB.open('pulpit-binder', 2); q.onupgradeneeded = () => { q.result.createObjectStore('sermons', { keyPath: 'id' }); q.result.createObjectStore('kv', { keyPath: 'k' }); }; q.onsuccess = () => { const tx = q.result.transaction('sermons', 'readwrite'); tx.objectStore('sermons').put(rec); tx.oncomplete = () => { q.result.close(); res(); }; }; });
}"""
COUNTS = "['__sets','__dels','__gets','__ups'].map(k => +(localStorage.getItem(k) || 0))"
RESET = "['__sets','__dels','__gets','__ups'].forEach(k => localStorage.removeItem(k))"

fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"got {got!r} want {want!r}")
    if not ok: fails.append(name)

async def until_synced(page, timeout=180, started=False):
    t0 = time.time()
    if started:   # wait for the save to begin, so an old "Synced" doesn't count
        while await page.evaluate("document.querySelector('#sync').dataset.state") == "synced" and time.time() - t0 < 5: await page.wait_for_timeout(20)
    while time.time() - t0 < timeout:
        if await page.evaluate("document.querySelector('#sync').dataset.state") == "synced": return time.time() - t0
        await page.wait_for_timeout(50)
    return None

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1400, "height": 900})
        await ctx.add_init_script(INIT)
        page = await ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8></head><body>" + HTML + "</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.goto("https://x.test/#build"); await page.wait_for_timeout(300)
        await page.evaluate("localStorage.clear(); new Promise(r => { const q = indexedDB.deleteDatabase('pulpit-binder'); q.onsuccess = q.onerror = q.onblocked = () => r(); })")
        await page.goto("https://x.test/#build")   # page closed so the seed owns the database
        await page.evaluate(SEED)
        await page.reload(); t = await until_synced(page)
        check("first sync uploads each picture once", (await page.evaluate(COUNTS))[3], 30)
        print(f"first upload of the 30-slide sermon: {t:.1f}s  sets, deletes, gets, uploads = {await page.evaluate(COUNTS)}")

        async def edit(label):
            await page.evaluate(RESET)
            await page.goto("https://x.test/#edit"); await page.wait_for_timeout(200); await page.reload(); await until_synced(page); await page.wait_for_timeout(500)
            await page.evaluate(RESET)
            await page.click("#editor p >> nth=3"); await page.keyboard.press("End"); await page.keyboard.type(" amen")
            t = await until_synced(page, started=True)
            c = await page.evaluate(COUNTS); print(f"{label}: typed a word, synced after {t:.1f}s  sets, deletes, gets, uploads = {c}")
            check(f"{label}: only the text and the sermon's record are written", c, [2, 0, 0, 0])
            check(f"{label}: under 3 seconds", t < 3, True)
            await page.evaluate(RESET)
            await page.click("#editor p >> nth=5"); await page.keyboard.press("End"); await page.keyboard.type(" again")
            t = await until_synced(page, started=True)
            print(f"{label}: second edit in the same session, synced after {t:.1f}s  sets, deletes, gets, uploads = {await page.evaluate(COUNTS)}")
        await edit("after reopening the page")

        # the deck changes after reopening: a slide is made from highlighted words. Slide text goes up; no picture is uploaded again.
        await page.reload(); await until_synced(page); await page.wait_for_timeout(500); await page.evaluate(RESET)
        await page.evaluate("""() => { const p = document.querySelectorAll('#editor p')[8]; const r = document.createRange(); r.selectNodeContents(p.firstChild); r.setEnd(p.firstChild, 30); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""")
        await page.wait_for_timeout(200); await page.click("#btn-make-slide"); await page.wait_for_timeout(200)
        await page.click("#mk-kinds .mk-kind >> nth=0"); await page.wait_for_timeout(300); await page.click("#mk-add")
        t = await until_synced(page, started=True); c = await page.evaluate(COUNTS)
        print(f"after reopening, a slide added: synced after {t:.1f}s  sets, deletes, gets, uploads = {c}")
        check("adding a slide uploads no picture again", c[3], 0)
        check("the deck now has 31 slides in the account", await page.evaluate("JSON.parse(JSON.parse(window.localStorage.getItem('__db'))['data/users/u1/big']).slideCount"), 31)

        # a second device: nothing on it yet, so the sermon comes down from the account; an edit there sends only the text
        await page.goto("https://x.test/#build"); await page.evaluate("new Promise(r => { const q = indexedDB.deleteDatabase('pulpit-binder'); q.onsuccess = q.onerror = q.onblocked = () => r(); })")
        await page.goto("https://x.test/#edit"); await page.reload(); await until_synced(page); await page.wait_for_timeout(1500)
        check("second device opens the sermon from the account", await page.input_value("#m-title"), "Thirty slide test")
        check("with all 31 slides", await page.evaluate("document.querySelectorAll('#ed-slide option').length - 2"), 31)
        await page.evaluate(RESET)
        await page.click("#editor p >> nth=2"); await page.keyboard.press("End"); await page.keyboard.type(" here")
        t = await until_synced(page, started=True); c = await page.evaluate(COUNTS)
        print(f"second device, typed a word: synced after {t:.1f}s  sets, deletes, gets, uploads = {c}")
        check("second device: only the text and the record are written", (c[0], c[3]), (2, 0))
        print("errors", errs); check("no page errors", errs, [])
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
    sys.exit(1 if fails else 0)
asyncio.run(main())
