import asyncio, pathlib, json, random, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
random.seed(4)
texts = ["Psalm 119:105","John 3:16","Romans 12:1-2","Ephesians 2:8-10","Acts 2:38","Matthew 5:3-12","James 1:22","Hebrews 11:1","Genesis 12:1-3","Isaiah 40:31","1 Corinthians 13:4-7","Philippians 4:6-7","Luke 15:11-32","Exodus 20:1-17","2 Timothy 3:16","Galatians 5:22","Mark 10:45","1 Peter 2:9","Revelation 21:1-4","Micah 6:8","John 15:1-8","Proverbs 3:5-6"]
themes = ["grace","faith","obedience","prayer","the church","baptism","hope","discipleship","love","worship","suffering","holiness","evangelism","family"]
docs = ["salvation by grace","the Lordship of Christ","the church","baptism","resurrection","the Holy Spirit","sin","scripture"]
appr = ["Expository","Expository","Topical","Textual","Narrative","Doctrinal"]
svc = ["Sunday AM","Sunday AM","Sunday PM","Wednesday Bible Study"]
recs=[]
for i in range(26):
  m = 1 + i*0.7
  y, mo = 2025 + (int(m)+3)//12, (int(m)+3)%12+1
  t = texts[i % len(texts)]
  body = " ".join(["We read in %s that God is faithful and you can trust Him. Do we believe it? Consider also %s." % (t, random.choice(texts))]*random.randint(30,80))
  ai = None if i % 7 == 3 else {"bigIdea":"God gives enough light for the next faithful step in "+t+".","approach":random.choice(appr),"tone":random.sample(["hopeful","urgent","pastoral","challenging","warm"],2),"themes":random.sample(themes,4),"doctrines":random.sample(docs,2),"gaps":["The transition into the application could be clearer."],"scriptures":[{"ref":t,"use":"main text"}],"at":1}
  recs.append({"id":"s%02d"%i,"updatedAt":1700000000000+i,"meta":{"title":"Sermon %d on %s"%(i+1,t.split(' ')[0]),"text":t,"when":"%d-%02d-%02dT10:30"%(y,mo,random.randint(1,27)),"service":random.choice(svc),"place":"Bridge Creek church of Christ","speaker":"Jarred Pettijohn","wpm":140,"series":"Faith series" if i%5==0 else ""},"html":"<p>"+body+"</p>","slides":[],"manual":{},"ai":ai,"media":{"link":"https://youtu.be/x" if i%3==0 else ""}})
INIT = """const smp = async () => ({text:''}); smp.json = async (p) => { window.__p = p; await new Promise(r=>setTimeout(r,300)); if (p.includes('whole body of preaching')) return {overview:'Mostly expository, strongly New Testament, with a steady call to obedience.',patterns:['Applications land on personal obedience','Sermons run about 30 minutes'],wellCovered:['Grace','Faith','The church'],underrepresented:['Minor prophets','The Lord\\'s Supper','Eschatology'],recurringGaps:['Transitions into application'],ideas:[{title:'What Does the Lord Require?',text:'Micah 6:6-8',why:'Brings the minor prophets back into view.'},{title:'Do This in Remembrance',text:'1 Corinthians 11:23-26',why:'Teaches the Supper.'}]}; return {}; }; window.claude = { use: async n => n === 'sample' ? smp : null };"""
async def main():
  dark = "dark" in sys.argv; w = 390 if "mobile" in sys.argv else 1400
  async with async_playwright() as p:
    b = await p.chromium.launch()
    ctx = await b.new_context(viewport={"width": w, "height": 900}, color_scheme="dark" if dark else "light"); await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs=[]; page.on("pageerror", lambda e: errs.append(str(e))); page.on("console", lambda m: m.type=="error" and errs.append(m.text))
    async def route(r):
      if r.request.url.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
      else: await r.abort()
    await page.route("**/*", route)
    await page.goto("https://x.test/#build"); await page.wait_for_timeout(700)
    await page.evaluate("""recs => new Promise(res => { const q = indexedDB.open('pulpit-binder'); q.onsuccess = () => { const tx = q.result.transaction('sermons','readwrite'); const st = tx.objectStore('sermons'); st.clear(); recs.forEach(r => st.put(r)); tx.oncomplete = res; }; })""", recs)
    await page.goto("https://x.test/#dash"); await page.reload(); await page.wait_for_timeout(1500)
    await page.screenshot(path=str(ROOT / "tests" / "out" / "dash_top.png"))
    await page.screenshot(path=str(ROOT / "tests" / "out" / "dash_full.png"), full_page=True)
    print("kpi", await page.evaluate("[...document.querySelectorAll('#dash-kpi .stat')].map(s=>s.innerText.replace(/\\n/g,' '))"))
    print("sub", await page.text_content("#dash-sub"))
    await page.hover("#dash-months rect.hit >> nth=3"); await page.wait_for_timeout(100); print("tip", await page.text_content("#dash-tip"))
    await page.click("#btn-dash-ai"); await page.wait_for_timeout(900)
    await page.click("#dash-themes .bar-row >> nth=0"); await page.wait_for_timeout(600); print("count", await page.text_content("#dash-count"))
    await page.select_option("#dash-range","12m"); await page.wait_for_timeout(300); print("sub12", await page.text_content("#dash-sub"))
    await page.screenshot(path=str(ROOT / "tests" / "out" / "dash_full2.png"), full_page=True)
    await page.click("#dash-table tbody tr >> nth=0"); await page.wait_for_timeout(800)
    print("after open view", await page.evaluate("document.body.dataset.view"), await page.input_value("#m-title") if await page.query_selector("#m-title") else "")
    print("scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
    print("errors", errs)
asyncio.run(main())
