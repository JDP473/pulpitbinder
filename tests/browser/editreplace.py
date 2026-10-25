import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
INIT = """const smp = async () => ({ text: '' }); smp.json = async () => { await new Promise(r => setTimeout(r, 80)); return { text: window.__reply }; }; smp.limits = async () => ({});
window.claude = { use: async k => k === 'sample' ? smp : null };"""
ONE = "NEW SENTENCE ONE."; TWO = "NEW SENTENCE ONE.\n\nNEW SENTENCE TWO."
# [name, how the highlight is made, the reply, expected paragraphs 1..: a function of the original paragraph texts p1..p3 is checked in python]
CASES = [
 ("middle of a paragraph", "(() => { const t = P(1).firstChild; const r = document.createRange(); r.setStart(t, 10); r.setEnd(t, 60); return r; })()", ONE),
 ("middle of a paragraph, two paragraphs back", "(() => { const t = P(1).firstChild; const r = document.createRange(); r.setStart(t, 10); r.setEnd(t, 60); return r; })()", TWO),
 ("whole paragraph by triple click", "(() => { const r = document.createRange(); r.setStart(P(1), 0); r.setEnd(P(2), 0); return r; })()", ONE),
 ("whole paragraph by triple click, two back", "(() => { const r = document.createRange(); r.setStart(P(1), 0); r.setEnd(P(2), 0); return r; })()", TWO),
 ("whole paragraph contents", "(() => { const r = document.createRange(); r.selectNodeContents(P(1)); return r; })()", TWO),
 ("end of one paragraph to middle of the next (no cue between)", "(() => { const r = document.createRange(); r.setStart(P(1).firstChild, 120); r.setEnd(P(2).firstChild, 40); return r; })()", TWO),
 ("three paragraphs (no cues)", "(() => { const r = document.createRange(); r.setStart(P(1).firstChild, 20); r.setEnd(P(3).firstChild, 40); return r; })()", ONE),
]
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch(); ctx = await b.new_context(viewport={"width": 1400, "height": 900}); await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
      u = r.request.url
      if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
      elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
      else: await r.abort()
    await page.route("**/*", route)
    bad = 0
    for k, (name, expr, reply) in enumerate(CASES):
      await page.goto("https://x.test/#edit"); await page.reload(); await page.wait_for_timeout(1200)
      # three plain paragraphs with no slide cues between them, so any highlight can cross them
      await page.evaluate("""() => { const ed = document.querySelector('#editor'); ed.innerHTML = '<p>' + ['Alpha one begins here and it runs on for quite a while so that there is plenty of text to select from inside it, ending with ZEBRA.', 'Bravo two is the middle paragraph and it also runs on for a good while, with enough words to select partway through it, ending with YAK.', 'Charlie three comes last and keeps going for some time too, with its own ending, which is XRAY.'].join('</p><p>') + '</p><p>Delta four stays untouched.</p>'; ed.dispatchEvent(new Event('input')); }""")
      await page.wait_for_timeout(500)
      await page.evaluate("r => { window.__reply = r; }", reply)
      pre = await page.evaluate("[...document.querySelectorAll('#editor > p')].map(p => p.textContent)")
      sel = await page.evaluate("(e) => { const P = i => document.querySelectorAll('#editor > p')[i - 1]; const r = eval(e); const ed = document.querySelector('#editor'); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.dispatchEvent(new Event('selectionchange')); return r.toString(); }", expr)
      await page.wait_for_timeout(300)
      await page.evaluate("document.querySelector('#btn-edit-sel').click()"); await page.wait_for_timeout(250)
      if await page.evaluate("document.querySelector('#es-modal').hidden"): print("FAIL", name, "dialog did not open", await page.evaluate("document.querySelector('#toast').textContent")); bad += 1; continue
      await page.fill("#es-ask", f"change number {k}"); await page.click("#es-go"); await page.wait_for_function("!document.querySelector('#es-step2').hidden")
      await page.click("#es-accept"); await page.wait_for_timeout(300)
      post = await page.evaluate("[...document.querySelectorAll('#editor > p')].map(p => p.textContent)")
      joined_pre, joined_post = "\n\n".join(pre), "\n\n".join(post)
      # expected: the highlighted text is gone, the new paragraphs sit where it was, and every other character is unchanged
      i0 = joined_pre.find(sel.strip()) if "\n" not in sel else -1
      flat_sel = sel.replace("\n", "")
      ok = True; why = []
      for must in ["NEW SENTENCE ONE."] + (["NEW SENTENCE TWO."] if "TWO" in reply else []):
        if must not in joined_post: ok = False; why.append("missing " + must)
      if "TWO" in reply and joined_post.find("NEW SENTENCE ONE.") > joined_post.find("NEW SENTENCE TWO."): ok = False; why.append("replacement paragraphs out of order")
      for chunk in [c for c in flat_sel.split(". ") if len(c) > 12]:
        if chunk.strip(". ") in joined_post: ok = False; why.append("old words remain: " + chunk[:30])
      if "Delta four stays untouched." not in post: ok = False; why.append("later paragraph changed")
      first_prefix = pre[0 if name.startswith("three") or name.startswith("end of one") else 1][:10] if True else ""
      print(("ok  " if ok else "FAIL"), name, "|", len(pre), "->", len(post), "paragraphs", why)
      for i, t in enumerate(post[:5]): print("      ", i + 1, t[:90].replace("\n", " "), "…" if len(t) > 90 else "")
      if not ok: bad += 1
      # undo, then redo
      await page.click('#ed-toolbar [data-cmd="undo"]'); await page.wait_for_timeout(300)
      back = await page.evaluate("[...document.querySelectorAll('#editor > p')].map(p => p.textContent)")
      if back != pre: print("FAIL undo did not restore:", len(back), "paragraphs"); bad += 1
      await page.click('#ed-toolbar [data-cmd="redo"]'); await page.wait_for_timeout(300)
      again = await page.evaluate("[...document.querySelectorAll('#editor > p')].map(p => p.textContent)")
      if again != post: print("FAIL redo did not restore"); bad += 1
    print("failures:", bad, "errors:", errs)
    await b.close()
asyncio.run(main())
