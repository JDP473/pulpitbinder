import asyncio, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
S = json.load(open(FIX / "samples.json"))
INIT = """const SAMPLES = %s;
const smp = async () => ({text:''});
smp.json = async (p, o) => { await new Promise(r=>setTimeout(r,250));
  if (p.includes('Describe one picture')) return { prompt: 'A small oil lamp glowing on a rocky path at night, lighting only the next step', caption: 'Enough light for the next step' }; if (p.includes('Draw a simple')) return { svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900"><script>alert(1)</script><g onload="x()"><path d="M700 650 Q800 400 900 650 Z" fill="none" stroke="rgb(226,181,94)" stroke-width="14"/><circle cx="800" cy="380" r="60" fill="rgb(226,181,94)" opacity=".6"/><rect x="760" y="650" width="80" height="40" fill="rgb(245,242,234)"/></g><image href="http://evil/x.png"/></svg>', caption: 'Enough light for the next step' };
  if (p.includes('one short, memorable')) return { text: 'Walk by the light you have.' };
  if (p.includes('2 to 4 parallel points')) return { title: 'Walking by faith', points: ['Light for one step', 'Trust the One who sees', 'Take the next step'] };
  if (p.includes('reflection question')) return { text: 'What is the next faithful step this light shows you today?' };
  if (p.includes('double square brackets')) return { text: 'Faith is [[walking]] by the [[light]] you have.' };
  return {}; };
smp.limits = async () => ({});
let polls = 0; window.__canva = [];
window.claude = { use: async n => n === 'sample' ? smp : n === 'mcp' ? { callTool: async (srv, tool, input) => { window.__canva.push([srv, tool, input.prompt || input.jobId]);
  if (srv === 'Canva' && tool === 'generate-image') return { content: [{type:'text', text: JSON.stringify({jobId:'j1'})}], payload: { jobId: 'j1' } };
  if (srv === 'Canva' && tool === 'get-generate-image-job') { polls++; if (polls < 2) return { payload: { status: 'PENDING' }, content: [] };
     return { payload: { status: 'SUCCESS', link: 'https://media.canva.com/v2/image-resize/format:PNG/width:2560/x.png?exp=1 https://www.canva.com/design/abc/view' }, content: [{type:'text', text:'{"status":"SUCCESS"}'}, {type:'image', data: 'iVBORw0KGgoAAAANSUhEUgAAAgAAAAEgCAIAAABNXlwGAAAF8ElEQVR4nO3by00dSxRAUbBeCB4zJgRHQEQOw4E5GAfhgSULiQcCc7t+e60xg64zOLu7rrh/eHy6A6Dny+wHAGAOAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAICo/2Y/AAzy88fX9//xt++/rnsSWMT9w+PT7GeAS3xo479NDziSAHCUGy7914gBxxAATjBg77+kBOxOANjblNX/nAywLwFgS9P3/ktKwHYEgM0suPqfkwE24v8A2Mni2/9uhyeEv3wBsIftFqtPAdYnAKxuu9X/nAywMldALG3r7X+3//NzNgFgXWdszzNOwZFcAbGiI5em6yBW4wuA5Ry5/e/OPRf7EgDWcvaWPPt0bEcAWEhhPxbOyC4EgFV0NmPnpCxOAFhCbSfWzsuaBID5mtuweWqWIgBMVt6D5bOzAgFgJhvQBJhIAJjG7vvDHJhFAACiBIA5vPY+ZxpMIQBMYN+9ZCaMJwCMZtO9xmQYTAAAogSAobzkvs18GEkAAKIEgHG83r6HKTGMADCIvfZ+ZsUYAgAQJQCM4JX2o0yMAQQAIEoAAKIEgMu5zfg35sbVBAAgSgC4ltfYzzA9LiUAAFECABAlAFzIDcbnmSHXEQCAKAEAiBIAgCgB4Cour2/FJLmIAABECQBAlAAARAkAQJQAcAm/W96WeXIFAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAEAiBIAgCgBAIgSAIAoAQCIEgCAKAHgEt++/5r9CEcxT64gAABRAgAQJQAAUQIAECUAXMXvlrdiklxEAACiBAAgSgAAogSAC7m8/jwz5DoCABAlAABRAsC13GB8hulxKQEAiBIALuc19t+YG1cTAIAoAQCIEgBGcJvxUSbGAAIAECUADOKV9v3MijEEgHHstfcwJYYRAIAoAWAor7dvMx9GEgCAKAFgNC+5rzEZBhMAJrDpXjITxhMA5rDvnjMNphAAgCgBYBqvvX+YA7MIADPZfSbARALAZOUNWD47KxAA5mvuweapWYoAsITaNqydlzUJAKvo7MTOSVmcALCQwmYsnJFdCABrOXs/nn06tiMALOfULXnqudjX/cPj0+xngP/388fX2Y9wG1Y/a/IFwLrO2JtnnIIjCQBL23177v78nM0VEHvY7jrI6md9AsBOtsiA1c8uXAGxk/V36/pPCH/5AmBLC34KWP1sRwDY2/QS2PvsSwA4wZQMWP3sTgA4yoAS2PscQwA41g1jYOlzJAGg4kM9sPEpEACAKP8HABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUQIAECUAAFECABAlAABRAgAQJQAAUb8By2jWHyg+pJkAAAAASUVORK5CYII=', mimeType:'image/png'}] }; }
  return { payload: { markdown: SAMPLES.esv } }; } } : null };""" % json.dumps(S)
SEL = """() => { const ed = document.querySelector('#editor'); const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const i = n.textContent.indexOf('Faith is walking'); if (i >= 0 && !n.parentElement.closest('.pb-slide')) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, n.textContent.indexOf('path.', i) + 5); ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; }"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1400, "height": 900}); await ctx.add_init_script(INIT)
        page = await ctx.new_page(); errs=[]; page.on("pageerror", lambda e: errs.append(str(e))); page.on("dialog", lambda d: errs.append("DIALOG "+d.message))
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.goto("https://x.test/#edit"); await page.wait_for_timeout(900)
        deck = "() => document.querySelectorAll('#editor .pb-slide').length"
        async def make(kind, shot=None, setup=None):
            assert await page.evaluate(SEL)
            await page.wait_for_timeout(250)
            if not await page.is_visible("#sel-pop"):
                print("  pop hidden; sel=", await page.evaluate("getSelection().toString().slice(0,40)"), "active=", await page.evaluate("document.activeElement.id"), "view hidden edit?", await page.evaluate("document.querySelector('#view-edit').hidden"), "modal", await page.evaluate("document.querySelector('#mk-modal').hidden"))
                await page.screenshot(path=str(ROOT / "tests" / "out" / "pk_dbg.png"))
            await page.click("#btn-make-slide"); await page.wait_for_timeout(200)
            if shot == "kinds": await page.screenshot(path=str(ROOT / "tests" / "out" / "pk_kinds.png"))
            await page.click(f"#mk-kinds button:has-text('{kind}')"); await page.wait_for_timeout(500)
            if setup: await setup()
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(ROOT / "tests" / "out") + "/" + f"pk_{kind.split()[0].lower()}.png")
            label = await page.text_content("#mk-add")
            await page.click("#mk-add"); await page.wait_for_timeout(300)
            return label
        print("quote:", await make("Quote", "kinds"))
        print("big idea:", await make("Big idea"))
        print("blank:", await make("Fill in the blank"))
        print("points:", await make("Summary points"))
        print("question:", await make("Reflection question"))
        print("point:", await make("Main point"))
        async def waitpaint():
            await page.wait_for_timeout(8000); await page.screenshot(path=str(ROOT / "tests" / "out" / "pk_art_small.png")); print("links:", await page.evaluate("[...document.querySelectorAll('.hd-links a')].map(a => a.textContent + ' -> ' + a.href.slice(0,60))"))
            await page.set_input_files("#mk-f-hd", str(FIX / "art.png")); await page.wait_for_timeout(500)
        print("art:", await make("Illustration", setup=waitpaint))
        async def photo(): await page.set_input_files("#mk-f-img", str(FIX / "photo.jpg")); await page.wait_for_timeout(500)
        print("photo:", await make("Photo", setup=photo))
        print("canva calls:", await page.evaluate("__canva.map(c => c[1] + ':' + String(c[2]).slice(0,50))"))
        print("art slide img:", await page.evaluate("[...document.querySelectorAll('#gutter img.mk-img.cover')].length"))
        if False: print("svg sanitized:", await page.evaluate("(() => { const s = document.querySelector('img.mk-img.contain') || [...document.querySelectorAll('#mk-preview img')][0]; if (!s) return 'no art img in DOM'; const d = decodeURIComponent(s.src.split(',')[1]); return [d.includes('script'), d.includes('onload'), d.includes('evil')]; })()"))
        # scripture
        await page.evaluate("""() => { const p = [...document.querySelectorAll('#editor p')].find(p => p.textContent.includes('Matthew 4:4')); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); document.querySelector('#editor').focus(); }""")
        await page.keyboard.type(" John 3:16-18"); await page.keyboard.press("Tab"); await page.wait_for_timeout(500)
        await page.click("#editor .pb-scripture .pb-sc-mk"); await page.wait_for_timeout(200)
        print("scripture kinds:", await page.evaluate("[...document.querySelectorAll('#mk-kinds button')].map(b=>b.querySelector('b').textContent)"))
        await page.click("#mk-kinds button:has-text('Passage')"); await page.wait_for_timeout(200)
        await page.select_option("#mk-f-per", "1"); await page.wait_for_timeout(200)
        await page.screenshot(path=str(ROOT / "tests" / "out" / "pk_passage.png"))
        print("passage:", await page.text_content("#mk-add")); await page.click("#mk-add"); await page.wait_for_timeout(300)
        await page.click("#editor .pb-scripture .pb-sc-mk"); await page.wait_for_timeout(200)
        await page.click("#mk-kinds button:has-text('Key verse')"); await page.wait_for_timeout(200)
        await page.select_option("#mk-f-vi", "1"); await page.wait_for_timeout(200)
        await page.screenshot(path=str(ROOT / "tests" / "out" / "pk_key.png")); await page.click("#mk-add"); await page.wait_for_timeout(300)
        print("cues:", await page.evaluate("[...document.querySelectorAll('#editor .pb-slide')].map(c => c.textContent.slice(0,30))"))
        await page.click("#tab-present"); await page.wait_for_timeout(500)
        print("present pos:", await page.text_content("#pos"))
        print("errors", errs)
        await b.close()
asyncio.run(main())
