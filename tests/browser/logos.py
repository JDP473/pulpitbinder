import asyncio, pathlib, json, os
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
S = {"esv": "16 Placeholder words for the first verse of the test passage. 17 Placeholder words for the second verse. 18 Placeholder words for the third verse."}
INIT = """
const SAMPLES = %s;
window.claude = { use: async n => {
  if (n === 'mcp') return { callTool: async () => ({ payload: { markdown: SAMPLES.esv } }) };
  return null; } };
""" % json.dumps(S)
def cut(a, b): i = HTML.index(a); return HTML[i:HTML.index(b, i)]
# the page script is one closure, so lift the pure reference code out of it to check the link format directly
PURE = cut("const BOOKS = [", "/* sectioning */") + cut("function normalizeRef(s) {", "function refAtCaret()") + cut("const LOGOS_NUM", "const logosA")
CASES = {
  "John 3:16": "bible.64.3.16", "John 3:16-18": "bible.64.3.16-64.3.18", "Jn 3:16-4:2": "bible.64.3.16-64.4.2",
  "Psalm 23": "bible.19.23", "Psalms 1-2": "bible.19.1-19.2", "Genesis 1:1": "bible.1.1.1", "Malachi 3:10": "bible.39.3.10",
  "Matthew 5:3": "bible.61.5.3", "Romans 11:33-36": "bible.66.11.33-66.11.36", "1 Cor 13:4-7": "bible.67.13.4-67.13.7",
  "Jude 3": "bible.86.1.3", "Philemon 4-7": "bible.78.1.4-78.1.7", "3 John 1:4": "bible.85.1.4", "Revelation 22:20": "bible.87.22.20",
  "Acts 2:38; Romans 6:3-4": "bible.65.2.38", "not a passage": "",
}
async def run(name, mobile=False, dark=False):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("PB_CHROME"))
        ctx = await b.new_context(color_scheme="dark" if dark else "light", **({"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2} if mobile else {"viewport": {"width": 1400, "height": 900}}))
        await ctx.add_init_script(INIT)
        page = await ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        async def route(r):
            u = r.request.url
            if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
            elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
            else: await r.abort()
        await page.route("**/*", route)
        await page.goto("https://x.test/#edit"); await page.wait_for_timeout(900)
        if not mobile and not dark:
            got = await page.evaluate("cs => { %s; return Object.fromEntries(cs.map(c => [c, logosLink(c)])); }" % PURE, list(CASES))
            for k, v in CASES.items():
                want = "https://ref.ly/logosref/" + v if v else ""
                print("ok  " if got[k] == want else "FAIL", k, "->", got[k])
        await page.evaluate("""() => { const p = document.createElement('p'); p.textContent = 'John 3:16-18'; const e = document.querySelector('#editor'); e.append(p); const r = document.createRange(); r.selectNodeContents(p); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); e.focus(); }""")
        await page.wait_for_timeout(150)
        if mobile: await page.click("#sc-hint-btn")
        else: await page.keyboard.press("Tab")
        await page.wait_for_timeout(700)
        links = await page.evaluate("[...document.querySelectorAll('#editor .pb-scripture .pb-sc-foot a')].map(a => a.textContent + ' ' + a.href)")
        print(name, "block links:", links)
        await page.evaluate("document.querySelector('#editor .pb-scripture').scrollIntoView({block:'center'})")
        await page.wait_for_timeout(200)
        await page.screenshot(path=str(OUT / f"logos-{name}-block.png"))
        await page.click("[data-view=analysis]:visible"); await page.wait_for_timeout(700)
        chips = await page.evaluate("[...document.querySelectorAll('#refs .refchip')].map(c => [...c.querySelectorAll('a')].map(a => a.textContent + ' ' + a.href))")
        print(name, "chips:", chips[:2])
        el = await page.query_selector("#refs")
        if el and await el.is_visible():
            await el.evaluate("e => e.scrollIntoView({block: 'center'})"); await page.wait_for_timeout(200); await page.screenshot(path=str(OUT / f"logos-{name}-chips.png"))
        print(name, "errors:", errs)
        await b.close()
async def main():
    await run("light"); await run("dark", dark=True); await run("phone", mobile=True)
asyncio.run(main())
