import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__prompts = []; let n = 0; const smp = async () => ({ text: '' });
smp.json = async (p, o) => { window.__prompts.push(p); await new Promise(r => setTimeout(r, 200)); if (!p.includes('rework part of his sermon manuscript')) return {};
  n++; return { text: n === 1 ? 'A lamp left on the shelf does nothing for your feet.\\n\\nIt has to be carried, one step at a time, into the dark places of your week.' : 'Carry the lamp ' + n + '.' }; };
smp.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? smp : n === 'downloads' ? { save: async () => {} } : null };"""
SEL = """(([start, end]) => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let a, b, n;
  while ((n = w.nextNode())) { if (n.parentElement.closest('.pb-slide,.pb-scripture')) continue; if (!a && n.textContent.includes(start)) a = [n, n.textContent.indexOf(start)]; if (n.textContent.includes(end)) b = [n, n.textContent.indexOf(end) + end.length]; }
  const r = document.createRange(); r.setStart(...a); r.setEnd(...b); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.dispatchEvent(new Event('selectionchange')); })"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, h, scheme in [(1440, 900, "light"), (390, 844, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1200)
      text0 = await page.evaluate("document.querySelector('#editor').innerText")
      # highlight part of one paragraph
      await page.evaluate(SEL, ["A lamp left on the shelf", "feet."]); await page.wait_for_timeout(300)
      print(w, "button", await page.evaluate("[!document.querySelector('#btn-edit-sel').hidden, !document.querySelector('#sel-pop').hidden]"))
      await page.screenshot(path=str(OUT / f"editsel_pop_{w}.png"))
      await page.evaluate("document.querySelector('#btn-edit-sel').click()"); await page.wait_for_timeout(300)
      print(w, "open", await page.evaluate("[!document.querySelector('#es-modal').hidden, document.querySelector('#es-orig').textContent.slice(0, 60), [...document.querySelectorAll('#es-len option')].map(o => o.textContent).length, document.querySelector('#es-lenhint').textContent]"))
      await page.click("#es-go"); await page.wait_for_timeout(200); print(w, "needs a request", await page.evaluate("document.querySelector('#es-msg').textContent"))
      await page.click("#es-chips .chip >> nth=1"); await page.select_option("#es-len", "4")
      print(w, "chip filled", await page.evaluate("[document.querySelector('#es-ask').value, document.querySelector('#es-lenhint').textContent]"))
      await page.screenshot(path=str(OUT / f"editsel_form_{w}.png"))
      await page.click("#es-go"); await page.wait_for_function("!document.querySelector('#es-step2').hidden", timeout=10000)
      print(w, "preview", await page.evaluate("[document.querySelector('#es-n0').textContent, document.querySelector('#es-n1').textContent, document.querySelector('#es-out').value.slice(0, 50)]"))
      pr = await page.evaluate("window.__prompts[0]"); print(w, "prompt has", [k in pr for k in ["much longer", "His request: Add a short illustration", "Just before the highlighted words", "Do not invent facts"]])
      await page.screenshot(path=str(OUT / f"editsel_preview_{w}.png"))
      await page.fill("#es-out", "A lamp left on the shelf does nothing for your feet.\n\nIt has to be carried, one step at a time, into the dark places of your week. Edited.")
      await page.click("#es-accept"); await page.wait_for_timeout(300)
      html = await page.evaluate("[...document.querySelectorAll('#editor > p')].map(p => p.textContent).filter(t => t.includes('lamp left on the shelf') || t.includes('carried, one step'))")
      print(w, "replaced", json.dumps(html)[:420]); print(w, "closed", await page.evaluate("document.querySelector('#es-modal').hidden"))
      # undo brings it back
      await page.evaluate("document.querySelector('#sg-undo').click()"); await page.wait_for_timeout(300)
      print(w, "undo restored", await page.evaluate("document.querySelector('#editor').innerText") == text0)
      # try again then accept
      await page.evaluate(SEL, ["Second, a lamp only helps", "not only on Sunday."]); await page.wait_for_timeout(250)
      await page.evaluate("document.querySelector('#btn-edit-sel').click()"); await page.fill("#es-ask", "Shorter"); await page.select_option("#es-len", "0"); await page.click("#es-go")
      await page.wait_for_function("!document.querySelector('#es-step2').hidden", timeout=10000); first = await page.evaluate("document.querySelector('#es-out').value")
      await page.click("#es-again"); await page.wait_for_function("first => document.querySelector('#es-out').value !== first", arg=first, timeout=10000)
      print(w, "try again", await page.evaluate("[window.__prompts.length, document.querySelector('#es-out').value]"))
      await page.click("#es-back"); print(w, "back to request", await page.evaluate("[!document.querySelector('#es-step1').hidden, document.querySelector('#es-ask').value]"))
      await page.keyboard.press("Escape"); print(w, "escape closes", await page.evaluate("document.querySelector('#es-modal').hidden"))
      # a highlight that crosses a slide cue is refused
      await page.evaluate(SEL, ["Notice first what the psalmist", "Second, a lamp only helps"]); await page.wait_for_timeout(250)
      await page.evaluate("document.querySelector('#btn-edit-sel').click()"); await page.wait_for_timeout(250)
      print(w, "across a cue", await page.evaluate("[document.querySelector('#es-modal').hidden, document.querySelector('#toast').textContent]"))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
asyncio.run(main())
