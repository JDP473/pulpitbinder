# Study questions as a conversation: ask now, follow-ups, quick "Go deeper" prompts, and Tell me more on a highlighted phrase.
import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
INIT = """window.__ps = [];
const smp = async () => ({text:''});
smp.json = async (p) => { window.__ps.push(p); await new Promise(r=>setTimeout(r,250));
  if (p.includes('Task: continue a conversation')) return {answer:'A follow-up answer that builds on the first.\\n\\nA second paragraph with more detail.', refs:['John 1:5'], alternatives:'', uncertainty:''};
  if (p.includes('Task: answer a question')) return {answer:'A first answer about the lamp and the path, kept short.', refs:['Psalm 18:28'], alternatives:'Some read it as wisdom literature.', uncertainty:''};
  if (p.includes('Task: background')) return {mainIdea:'God guides by his word.', author:'Unknown', keyWords:[{word:'lamp', original:'נֵר', translit:'ner', gloss:'a small oil lamp', note:'light for one step'}], observations:['The light is for the feet, not the horizon.']};
  return {}; };
window.claude = { use: async n => n === 'sample' ? smp : null };"""
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, scheme in [(1400, "light"), (1400, "dark"), (390, "light")]:
      ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        if r.request.url.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#study"); await page.wait_for_timeout(900)
      await page.fill("#st-ref", "Psalm 119:105"); await page.press("#st-ref", "Enter"); await page.wait_for_timeout(900)
      tag = f"{w}_{scheme}"
      print(tag, "buttons", await page.evaluate("[!!document.querySelector('#st-q-ask'), !!document.querySelector('#st-q-keep')]"))
      await page.fill("#st-q-text", "Why a lamp and not the sun?"); await page.click("#st-q-ask"); await page.wait_for_timeout(700)
      print(tag, "first answer", await page.evaluate("document.querySelector('.st-q .st-ans p') && document.querySelector('.st-q .st-ans p').textContent"))
      await page.click(".st-q .st-chips .chip:has-text('Go deeper')"); await page.wait_for_timeout(100)
      print(tag, "spinner", await page.evaluate("!!document.querySelector('.st-turn .mk-wait')"))
      await page.wait_for_timeout(600)
      print(tag, "turns", await page.evaluate("[...document.querySelectorAll('.st-turn')].map(t => [t.querySelector('.st-tq').textContent.slice(0,20), t.querySelectorAll('.st-ans p').length])"))
      print(tag, "prompt has convo", await page.evaluate("window.__ps.at(-1).includes('The conversation so far') && window.__ps.at(-1).includes('Why a lamp')"))
      await page.fill(".st-fu textarea", "What about the feet?"); await page.press(".st-fu textarea", "Enter"); await page.wait_for_timeout(700)
      print(tag, "turns after typed", await page.evaluate("document.querySelectorAll('.st-turn').length"), await page.evaluate("window.__ps.at(-1).includes('Go deeper on this')"))
      # save for later does not call Claude
      n = await page.evaluate("window.__ps.length"); await page.fill("#st-q-text", "Keep this one"); await page.click("#st-q-keep"); await page.wait_for_timeout(400)
      print(tag, "kept without asking", await page.evaluate("window.__ps.length") == n, await page.evaluate("document.querySelector('.st-q .st-qt').textContent"))
      # highlight text outside any question: it becomes a new "Tell me more" question, asked right away
      await page.evaluate("""(() => { const h=document.querySelector('#st-questions .bind-head h2'); const r=document.createRange(); r.selectNodeContents(h); const s=getSelection(); s.removeAllRanges(); s.addRange(r); })()""")
      await page.wait_for_timeout(500); await page.click("#st-selbtn"); await page.wait_for_timeout(700)
      print(tag, "tell me more", await page.evaluate("document.querySelector('.st-q .st-qt').textContent"), await page.evaluate("!!document.querySelector('.st-q .st-ans')"))
      # highlight a phrase in the first answer of the lamp question
      await page.evaluate("""(() => { const q=[...document.querySelectorAll('.st-q')].find(c=>c.querySelector('.st-qt').textContent.startsWith('Why a lamp')); const pEl=q.querySelector('.st-ans p'); const r=document.createRange(); r.setStart(pEl.firstChild, 2); r.setEnd(pEl.firstChild, 20); const s=getSelection(); s.removeAllRanges(); s.addRange(r); })()""")
      await page.wait_for_timeout(500)
      print(tag, "sel button", await page.evaluate("!document.querySelector('#st-selbtn').hidden"))
      await page.screenshot(path=str(OUT / f"studyask_sel_{tag}.png"))
      await page.click("#st-selbtn"); await page.wait_for_timeout(700)
      print(tag, "selection became follow-up", await page.evaluate("[...document.querySelectorAll('.st-q')].find(c=>c.querySelector('.st-qt').textContent.startsWith('Why a lamp')).querySelectorAll('.st-turn').length"))
      await page.evaluate("document.querySelector('#st-questions').scrollIntoView()"); await page.wait_for_timeout(300)
      await page.screenshot(path=str(OUT / f"studyask_{tag}.png"))
      card = await page.query_selector("xpath=//div[contains(@class,'st-q ')][.//label[starts-with(normalize-space(.),'Why a lamp')]]")
      await card.screenshot(path=str(OUT / f"studyask_card_{tag}.png"))
      el = await page.query_selector("#st-questions"); await el.screenshot(path=str(OUT / f"studyask_panel_{tag}.png"))
      print(tag, "hscroll", await page.evaluate("document.documentElement.scrollWidth > innerWidth"), "errors", errs)
      await ctx.close()
    await b.close()
asyncio.run(main())
