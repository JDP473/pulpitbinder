"""Sermons are never lost between the editor and the account. The mock account keeps its documents in localStorage,
so every tab in the test sees the same account, and each tab can be cut off (window.__fail) or have its picture
uploads refused (localStorage __upfail). Covers:
  1. switching sermons right after typing keeps the last words of the sermon being left, here and in the account
  2. a failed save is tried again on its own, without another edit, and the status says so meanwhile
  3. closing the page right after typing keeps the words for next time, and they then go up
  4. the same sermon changed in two tabs while one was cut off: both versions are kept
  5. a tab with nothing unsent picks up a change made in another tab on the same device
  7. a connection that drops just as a save checks the account never writes over another tab's newer version
  6. a slide picture that won't upload never holds back the text, and goes up once there is room"""
import asyncio, json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()

INIT = """
const wait = ms => new Promise(r => setTimeout(r, ms));
const all = () => JSON.parse(localStorage.getItem('__db') || '{}');
const put = (k, v) => { const d = all(); if (v === undefined) delete d[k]; else d[k] = v; localStorage.setItem('__db', JSON.stringify(d)); };
const has = k => k in all();
const fail = what => { if (window.__fail || (what === 'get' && window.__failget)) { const e = new Error('offline ' + what); e.code = 'unavailable'; throw e; } };
const subs = new Set();
const notify = () => setTimeout(() => subs.forEach(f => f()), 0);
addEventListener('storage', e => { if (e.key === '__db') notify(); });   // another tab wrote to the account
const snap = path => { const d = all(); return { id: path.split('/').pop(), exists: path in d, data: () => path in d ? JSON.parse(d[path]) : undefined, metadata: { hasPendingWrites: false } }; };
const doc = path => ({
  async get() { await wait(30); fail('get'); return snap(path); },
  async set(v) { await wait(30); fail('set'); put(path, JSON.stringify(v)); notify(); },
  async delete() { await wait(30); fail('delete'); put(path); notify(); },
  onSnapshot(cb) { let last = null; const f = () => { const v = all()[path] || null; if (v !== last) { last = v; cb(snap(path)); } }; subs.add(f); setTimeout(f, 0); return () => subs.delete(f); } });
const collection = path => ({ doc: id => doc(path + '/' + id), orderBy() { return this; }, limit() { return this; }, async get() { return { docs: [] }; },
  onSnapshot(cb) { let sent = new Map(); const f = () => { const n = path.split('/').length + 1, d = all();
    const now = Object.keys(d).filter(k => k.startsWith(path + '/') && k.split('/').length === n);
    const ch = now.filter(k => sent.get(k) !== d[k]).map(k => ({ type: sent.has(k) ? 'modified' : 'added', doc: snap(k) })).concat([...sent.keys()].filter(k => !(k in d)).map(k => ({ type: 'removed', doc: snap(k) })));
    sent = new Map(now.map(k => [k, d[k]])); if (ch.length || !f.done) { f.done = true; cb({ docChanges: () => ch }); } }; subs.add(f); setTimeout(f, 30); return () => subs.delete(f); } });
const assets = { async upload(b) { await wait(30); if (localStorage.getItem('__upfail')) { const e = new Error('full'); e.code = 'quota_or_state'; throw e; }
  const id = 'a' + (+(localStorage.getItem('__aid') || 0) + 1); localStorage.setItem('__aid', id.slice(1)); return { id, url: '/_blob/' + id, sizeBytes: b.size }; } };
window.claude = { use: async n => n === 'db' ? { doc, collection } : n === 'user' ? { id: async () => 'u1' } : n === 'assets' ? assets : null };
"""

fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"got {got!r} want {want!r}")
    if not ok: fails.append(name)

ACCOUNT_HTML = """id => { const d = JSON.parse(localStorage.getItem('__db') || '{}'), m = d['data/users/u1/' + id]; if (!m) return null;
  const n = JSON.parse(m).chunks.html || 0; let s = ''; for (let k = 0; k < n; k++) s += JSON.parse(d[`data/users/u1/${id}/parts/html.${k}`] || '{"s":""}').s; return s; }"""
ACCOUNT_TITLES = """() => Object.entries(JSON.parse(localStorage.getItem('__db') || '{}')).filter(([k]) => k.split('/').length === 4).map(([, v]) => JSON.parse(v).title).sort()"""
LOCAL_HTML = """id => new Promise(res => { const q = indexedDB.open('pulpit-binder'); q.onsuccess = () => { const g = q.result.transaction('sermons').objectStore('sermons').get(id); g.onsuccess = () => { res(g.result ? g.result.html : null); q.result.close(); }; }; })"""
SEED = """async recs => { await new Promise(res => { const q = indexedDB.open('pulpit-binder', 2); q.onupgradeneeded = () => { q.result.createObjectStore('sermons', { keyPath: 'id' }); q.result.createObjectStore('kv', { keyPath: 'k' }); };
  q.onsuccess = () => { const tx = q.result.transaction('sermons', 'readwrite'); recs.forEach((r, i) => tx.objectStore('sermons').put({ updatedAt: Date.now() - i * 1000, deckVer: 0, slides: [], manual: {}, ai: null, ...r })); tx.oncomplete = () => { q.result.close(); res(); }; }; }); }"""
def rec(id, title, words):
    return {"id": id, "meta": {"title": title, "text": "", "when": "", "service": "", "place": "", "speaker": "", "wpm": 140, "series": ""}, "html": f"<p>{words}</p>"}

async def is_state(page, st): return await page.evaluate("s => document.querySelector('#sync').dataset.state === s", st)
async def until(page, fn, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if await fn(): return True
        await page.wait_for_timeout(100)
    return False

async def saved(page):   # a save that has started, then finished, so an earlier "Synced" doesn't count
    await until(page, lambda: page.evaluate("document.querySelector('#sync').dataset.state !== 'synced'"), 6)
    return await until(page, lambda: is_state(page, 'synced'), 30)

async def _has(page, id, words, timeout=20):
    return await until(page, lambda: page.evaluate("([f, id, w]) => (eval(f))(id).includes(w)", [ACCOUNT_HTML.replace("return null", "return ''"), id, words]), timeout)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1300, "height": 850})
        await ctx.add_init_script(INIT)
        errs = []
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8></head><body>" + HTML + "</body></html>", content_type="text/html")
            else: await r.abort()
        await ctx.route("**/*", route)
        async def tab(hash="#edit"):
            pg = await ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
            await pg.goto("https://x.test/" + hash); return pg
        page = await tab()
        await page.evaluate("localStorage.clear(); new Promise(r => { const q = indexedDB.deleteDatabase('pulpit-binder'); q.onsuccess = q.onerror = q.onblocked = () => r(); })")
        await page.close(); page = await tab("#build")
        await page.evaluate(SEED, [rec("one", "First generic sermon", "Opening words of the first."), rec("two", "Second generic sermon", "Opening words of the second.")])
        await page.goto("https://x.test/#edit"); await page.reload()
        await until(page, lambda: is_state(page, 'synced'))
        check("both seeded sermons reach the account", await page.evaluate(ACCOUNT_TITLES), ["First generic sermon", "Second generic sermon"])

        # 1. type, then switch sermons within a fraction of a second
        check("the newest sermon is open", await page.input_value("#m-title"), "First generic sermon")
        await page.click("#editor p"); await page.keyboard.press("End"); await page.keyboard.type(" Last words before switching.")
        await page.evaluate("() => { const s = document.querySelector('#library'); s.value = 'two'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(150)
        check("switched to the second sermon", await page.input_value("#m-title"), "Second generic sermon")
        check("1. the words typed just before switching are saved on this device", "Last words before switching." in (await page.evaluate(LOCAL_HTML, "one") or ""), True)
        await until(page, lambda: is_state(page, 'synced'))
        check("1. and reach the account", "Last words before switching." in (await page.evaluate(ACCOUNT_HTML, "one") or ""), True)

        # 2. cut off, type, see the status, come back: it goes up without another edit
        await page.evaluate("window.__fail = true")
        await page.click("#editor p"); await page.keyboard.press("End"); await page.keyboard.type(" Typed while offline.")
        await until(page, lambda: is_state(page, 'error'))
        check("2. a failed save shows Not synced yet", await page.evaluate("document.querySelector('#sync').textContent"), "Not synced yet")
        check("2. the words are kept on this device meanwhile", "Typed while offline." in (await page.evaluate(LOCAL_HTML, "two") or ""), True)
        await page.screenshot(path=str(ROOT / "tests/out/syncsafe-offline.png"))
        await page.evaluate("window.__fail = false")
        ok = await until(page, lambda: is_state(page, 'synced'), 30)
        check("2. it is tried again on its own and syncs", ok, True)
        check("2. the offline words reach the account", "Typed while offline." in (await page.evaluate(ACCOUNT_HTML, "two") or ""), True)

        # 3. type and close the page straight away; the next visit sends it
        await page.click("#editor p"); await page.keyboard.press("End"); await page.keyboard.type(" Typed just before closing.")
        await page.wait_for_timeout(50); await page.close(run_before_unload=True)
        page = await tab()
        check("3. the words typed just before closing are on this device", "Typed just before closing." in (await page.evaluate(LOCAL_HTML, "two") or ""), True)
        ok = await _has(page, "two", "Typed just before closing.")
        check("3. and go up on the next visit", ok, True)

        # 5. a second tab with nothing unsent follows a change made in the first
        other = await tab()
        await until(other, lambda: is_state(other, 'synced'))
        check("second tab opens the same sermon", await other.input_value("#m-title"), "Second generic sermon")
        await page.click("#editor p"); await page.keyboard.press("End"); await page.keyboard.type(" From the first tab.")
        await saved(page)
        await page.evaluate("document.activeElement.blur()")   # leave the editor so the second tab is free to update
        ok = await until(other, lambda: other.evaluate("document.querySelector('#editor').textContent.includes('From the first tab.')"), 20)
        check("5. the second tab picks up the change from the first", ok, True)

        # 4. the second tab is cut off and edits; the first edits too and syncs; when the second comes back both are kept
        await other.evaluate("window.__fail = true")
        await other.click("#editor p"); await other.keyboard.press("End"); await other.keyboard.type(" Only in the second tab.")
        await until(other, lambda: is_state(other, 'error'))
        await page.click("#editor p"); await page.keyboard.press("End"); await page.keyboard.type(" Only in the first tab.")
        check("4. the first tab's change reaches the account", await _has(page, "two", "Only in the first tab.", 30), True)
        await page.evaluate("document.activeElement.blur()")
        await other.evaluate("window.__fail = false; dispatchEvent(new Event('online'))")
        await until(other, lambda: is_state(other, 'synced'), 30)
        await other.wait_for_timeout(800)
        titles = await other.evaluate(ACCOUNT_TITLES)
        copy = [t for t in titles if t.startswith("Second generic sermon (other device")]
        check("4. the other version is kept as its own sermon", len(copy), 1)
        main_html = await other.evaluate(ACCOUNT_HTML, "two") or ""
        check("4. the sermon keeps the version from the tab that was cut off", "Only in the second tab." in main_html, True)
        ids = await other.evaluate("() => Object.keys(JSON.parse(localStorage.getItem('__db'))).filter(k => k.split('/').length === 4).map(k => k.split('/')[3])")
        cid = [i for i in ids if i not in ("one", "two")]
        copy_html = (await other.evaluate(ACCOUNT_HTML, cid[0]) or "") if cid else ""
        check("4. the copy holds the first tab's words", "Only in the first tab." in copy_html and "Only in the second tab." not in copy_html, True)
        await other.screenshot(path=str(ROOT / "tests/out/syncsafe-both.png"))

        # 7. the second tab can write but not read the account's copy; the first tab's newer words must survive
        ok = await until(page, lambda: page.evaluate("document.querySelector('#editor').textContent.includes('Only in the second tab.')"), 20)
        check("7. the first tab has caught up with the second", ok, True)
        await other.evaluate("window.__failget = true")
        await other.click("#editor p"); await other.keyboard.press("End"); await other.keyboard.type(" Second tab, shaky line.")
        await until(other, lambda: is_state(other, 'error'))
        await page.click("#editor p"); await page.keyboard.press("End"); await page.keyboard.type(" First tab, steady line.")
        check("7. the first tab's words reach the account", await _has(page, "two", "First tab, steady line.", 30), True)
        await page.evaluate("document.activeElement.blur()")
        await other.wait_for_timeout(5000)   # the second tab keeps retrying meanwhile
        check("7. while it can't check, the second tab writes nothing over them", await _has(other, "two", "First tab, steady line.", 1), True)
        await other.evaluate("window.__failget = false; dispatchEvent(new Event('online'))")
        await until(other, lambda: is_state(other, 'synced'), 30); await other.wait_for_timeout(800)
        titles = await other.evaluate(ACCOUNT_TITLES)
        check("7. then both versions are kept", len([t for t in titles if t.startswith("Second generic sermon (other device")]), 2)
        check("7. the sermon has the second tab's words", await _has(other, "two", "Second tab, shaky line.", 1), True)
        await other.close()

        # 6. a sermon with a slide picture, opened while uploads are refused: the text goes up at once, the picture once there is room
        await page.evaluate("""async () => { localStorage.setItem('__upfail', '1');
          const c = document.createElement('canvas'); c.width = 64; c.height = 36; c.getContext('2d').fillRect(0, 0, 64, 36);
          const b = await new Promise(r => c.toBlob(r, 'image/png'));
          await new Promise(res => { const q = indexedDB.open('pulpit-binder'); q.onsuccess = () => { const tx = q.result.transaction('sermons', 'readwrite');
            tx.objectStore('sermons').put({ id: 'pics', updatedAt: Date.now() + 60000, deckVer: 1, manual: {}, ai: null, html: '<p>Words of the picture sermon.</p>', slides: [{ title: 'One', body: [], notes: '', exact: b }],
              meta: { title: 'Picture sermon', text: '', when: '', service: '', place: '', speaker: '', wpm: 140, series: '' } });
            tx.oncomplete = () => { q.result.close(); res(); }; }; }); }""")
        await page.reload()
        await until(page, lambda: is_state(page, 'error'))
        check("6. the picture sermon is open", await page.input_value("#m-title"), "Picture sermon")
        check("6. its text is in the account although the picture was refused", await _has(page, "pics", "Words of the picture sermon."), True)
        check("6. the status says the pictures are waiting", "storage is full" in await page.evaluate("document.querySelector('#sync').title"), True)
        await page.evaluate("localStorage.removeItem('__upfail'); dispatchEvent(new Event('online'))")
        await until(page, lambda: is_state(page, 'synced'), 30)
        print("   status after room:", await page.evaluate("[document.querySelector('#sync').dataset.state, document.querySelector('#sync').title]"))
        slide = await page.evaluate("() => { const d = JSON.parse(localStorage.getItem('__db')); return [JSON.parse(d['data/users/u1/pics']).picsPending, JSON.parse(JSON.parse(d['data/users/u1/pics/parts/s0.0']).s).exact]; }")
        check("6. once there is room the picture goes up", slide, [False, {"asset": slide[1]["asset"] if isinstance(slide[1], dict) else None}])
        check("6. as a stored file", isinstance(slide[1], dict) and str(slide[1].get("asset", "")).startswith("a"), True)

        print("errors", errs); check("no page errors", errs, [])
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
    sys.exit(1 if fails else 0)
asyncio.run(main())
