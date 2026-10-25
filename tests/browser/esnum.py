# Edit with suggestions: type the number of words wanted, instead of (or after) choosing a size.
import asyncio, pathlib, re
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__prompts = []; const smp = async () => ({ text: '' });
smp.json = async (p, o) => { window.__prompts.push(p); await new Promise(r => setTimeout(r, 150)); return p.includes('rework part of his sermon manuscript') ? { text: 'Carry the lamp into the week ' + window.__prompts.length + '.' } : {}; };
smp.limits = async () => ({});
window.claude = { use: async n => n === 'sample' ? smp : null };"""
SEL = """(([start, end]) => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let a, b, n;
  while ((n = w.nextNode())) { if (n.parentElement.closest('.pb-slide,.pb-scripture')) continue; if (!a && n.textContent.includes(start)) a = [n, n.textContent.indexOf(start)]; if (n.textContent.includes(end)) b = [n, n.textContent.indexOf(end) + end.length]; }
  const r = document.createRange(); r.setStart(...a); r.setEnd(...b); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.dispatchEvent(new Event('selectionchange')); })"""
ST = "[document.querySelector('#es-len').value, document.querySelector('#es-words').value, document.querySelector('#es-lenhint').textContent]"
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch(); bad = 0
    def check(c, msg):
      nonlocal bad
      print("ok  " if c else "FAIL", msg); bad += 0 if c else 1
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
      await page.evaluate(SEL, ["Notice first what the psalmist", "next faithful step."]); await page.wait_for_timeout(300)
      await page.evaluate("document.querySelector('#btn-edit-sel').click()"); await page.wait_for_timeout(300)
      n = await page.evaluate("(document.querySelector('#es-orig').textContent.match(/\\S+/g) || []).length")
      s0 = await page.evaluate(ST); print(w, "opened", s0, "highlight words", n)
      check(s0[0] == "2" and int(s0[1]) == n, f"{w} starts at about the same length, number filled in")
      await page.select_option("#es-len", "4"); s1 = await page.evaluate(ST)
      check(int(s1[1]) == round(n * 2), f"{w} choosing Much longer fills in {s1[1]}")
      await page.fill("#es-words", "150"); s2 = await page.evaluate(ST)
      check(s2[0] == "x" and "About 150 words" in s2[2], f"{w} typing 150 picks Exact number: {s2}")
      await page.fill("#es-words", str(round(n * 0.5))); s3 = await page.evaluate(ST)
      check(s3[0] == "0", f"{w} typing the much-shorter count picks that size: {s3[0]}")
      await page.fill("#es-words", "3"); s4 = await page.evaluate(ST)
      check("at least 5" in s4[2], f"{w} too few words is explained: {s4[2]}")
      await page.fill("#es-words", "150"); await page.fill("#es-ask", "Say it more simply")
      await page.screenshot(path=str(OUT / f"esnum_form_{w}.png"))
      await page.focus("#es-words"); await page.keyboard.press("Enter")   # Enter in the number field creates
      await page.wait_for_function("!document.querySelector('#es-step2').hidden", timeout=10000)
      pr = await page.evaluate("window.__prompts.filter(p => p.includes('rework part')).pop()")
      line = [l for l in pr.split("\n") if l.startswith("Length:")][0]; print(w, line)
      check("about 150 words" in line and "within a few words of 150" in line, f"{w} the request to Claude asks for 150 words")
      n1 = await page.evaluate("document.querySelector('#es-n1').textContent"); check("asked for 150" in n1, f"{w} preview shows the target: {n1}")
      await page.screenshot(path=str(OUT / f"esnum_preview_{w}.png"))
      # back, choose a size again: the number follows and the prompt uses the size
      await page.click("#es-back"); await page.select_option("#es-len", "1"); s5 = await page.evaluate(ST)
      check(s5[0] == "1" and int(s5[1]) == round(n * 0.75), f"{w} choosing a size again resets the number: {s5[1]}")
      await page.click("#es-go"); await page.wait_for_function("!document.querySelector('#es-step2').hidden", timeout=10000)
      line = [l for l in (await page.evaluate("window.__prompts.filter(p => p.includes('rework part')).pop()")).split("\n") if l.startswith("Length:")][0]; print(w, line)
      check("a bit shorter" in line and "within a few words" not in line, f"{w} a chosen size is sent as a size")
      await page.click("#es-accept"); await page.wait_for_timeout(300)
      check("Carry the lamp" in await page.evaluate("document.querySelector('#editor').innerText"), f"{w} accept still replaces")
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]")); bad += len(errs)
      await ctx.close()
    print("RESULT", "all passed" if not bad else f"{bad} failures"); await b.close()
asyncio.run(main())
