import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
def rec(i, title, text, when):
  return {"id": f"j{i}", "updatedAt": 1700000000000 + i, "meta": {"title": title, "text": text, "when": when, "service": "Sunday AM", "place": "Bridge Creek church of Christ", "speaker": "Jarred Pettijohn", "wpm": 140, "series": "1 John"}, "html": f"<p>{title}.</p>", "slides": [], "manual": {}, "ai": None, "media": {}}
recs = [rec(1, "That You May Have Fellowship", "1 John 1:1-4", "2026-09-27T10:00"), rec(2, "Walking in the Light", "1 John 1:5-10", "2026-10-04T10:00"), rec(3, "Our Advocate", "1 John 2:1-6", "2026-10-11T10:00"), rec(4, "An Old and New Commandment", "1 John 2:7-11", "2026-10-18T10:00")]
INIT = """const smp = async () => ({text:''}); smp.json = async (p) => { window.__p = p; await new Promise(r=>setTimeout(r,400)); if (p.includes('next sermon in a series')) return {options:[{text:'1 John 2:12-14',title:'I Am Writing to You',why:'The next paragraph after 2:7-11.',bigIdea:'God speaks to every stage of faith.'},{text:'1 John 2:12-17',title:'Do Not Love the World',why:'Takes the address and the warning together.',bigIdea:'Love for the Father leaves no room for love of the world.'},{text:'1 John 2:15-17',title:'The World Is Passing Away',why:'A shorter unit on the warning alone.',bigIdea:'What we love shows whom we belong to.'}]}; return {}; }; window.claude = { use: async n => n === 'sample' ? smp : null };"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, scheme in [(1400, "light"), (390, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        if r.request.url.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(700)
      await page.evaluate("""recs => new Promise(res => { const q = indexedDB.open('pulpit-binder', 2); q.onupgradeneeded = () => { const d = q.result; if (!d.objectStoreNames.contains('sermons')) d.createObjectStore('sermons', { keyPath: 'id' }); if (!d.objectStoreNames.contains('kv')) d.createObjectStore('kv', { keyPath: 'k' }); }; q.onsuccess = () => { const tx = q.result.transaction('sermons','readwrite'); const st = tx.objectStore('sermons'); st.clear(); recs.forEach(r => st.put(r)); tx.oncomplete = res; }; })""", recs)
      await page.goto("https://x.test/#series"); await page.reload(); await page.wait_for_timeout(900)
      print(w, "view", await page.evaluate("[location.hash, document.querySelector('#ser-count').textContent, document.querySelector('#btn-ser-next').textContent]"))
      await page.click("#btn-ser-next"); await page.wait_for_timeout(100)
      opts = lambda: page.evaluate("[...document.querySelectorAll('#nx-opts .nx-opt')].map(o=>o.innerText.replace(/\\n/g,' / '))")
      print(w, "local", await opts(), await page.input_value("#nx-text"), await page.input_value("#nx-when"))
      await page.wait_for_timeout(700)
      print(w, "claude", await opts(), await page.input_value("#nx-text"), "|", await page.input_value("#nx-name"))
      await page.screenshot(path=str(OUT / f"next_{w}.png"))
      await page.click("#nx-opts .nx-opt >> nth=1"); print(w, "picked", await page.input_value("#nx-text"), "|", await page.input_value("#nx-name"))
      await page.click("#nx-go"); await page.wait_for_timeout(700)
      print(w, "created", await page.evaluate("[document.body.dataset.view, document.querySelector('#library').selectedOptions[0].text, document.querySelector('#tagbar').innerText.replace(/\\n/g,' '), !!document.querySelector('#editor .pb-scripture'), document.querySelector('#editor .pb-scripture') && document.querySelector('#editor .pb-scripture').dataset.ref]"))
      await page.click("#sub-series"); await page.wait_for_timeout(300); print(w, "series now", await page.evaluate("document.querySelector('#ser-count').textContent"))
      print(w, "errors", errs)
      await ctx.close()
asyncio.run(main())
