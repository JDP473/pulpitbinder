"""Stack translations: tick translations, highlighted differences, tap to stack, slides follow. Generic invented text only."""
import asyncio, pathlib, json, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"
TEXTS = {"ESV": {"t": "{{1}}The river runs to the sea and the people rest.\n{{2}}Every hill gives its light to the valley.", "s": "bg"},
         "LSB": {"t": "{{1}}The stream runs to the sea and the people sleep.\n{{2}}Every hill gives its light to the valley below.", "s": "bg"},
         "NASB": {"t": "{{1}}The river flows to the sea and the folk rest.\n{{2}}Each hill gives its light to the valley.", "s": "bg"}}
INIT = "window.claude = { use: async n => null };"
async def main():
    bad = 0
    def chk(name, ok, extra=""):
        nonlocal bad; print(("ok  " if ok else "FAIL"), name, extra); bad += not ok
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for label, kw in [("light", dict(viewport={"width": 1300, "height": 900})), ("dark", dict(viewport={"width": 1300, "height": 900}, color_scheme="dark")), ("phone", dict(**p.devices["iPhone 13"]))]:
            ctx = await b.new_context(**kw); await ctx.add_init_script(INIT)
            page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            async def route(r):
                u = r.request.url
                if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
                elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>" + HTML + "</body></html>", content_type="text/html")
                else: await r.abort()
            await page.route("**/*", route)
            await page.goto("https://x.test/#edit"); await page.wait_for_timeout(800)
            await page.evaluate("""(T) => { const ed = document.querySelector('#editor'); const d = document.createElement('div'); d.className = 'pb-scripture'; d.setAttribute('contenteditable','false');
              d.dataset.id = 'tst1'; d.dataset.ref = 'John 3:1-2'; d.dataset.ver = 'ESV'; d.dataset.texts = JSON.stringify(T);
              d.innerHTML = '<div class="pb-sc-head"><button type="button" data-act="stackmenu">Stack translations</button><button type="button" data-act="slides">+ Slides</button></div><div class="pb-sc-body"></div>'; ed.prepend(d); }""", TEXTS)
            sec = "#editor .pb-scripture[data-id=tst1]"
            await page.click(sec + " [data-act=stackmenu]"); await page.wait_for_timeout(200)
            chk(label + " panel open", await page.is_visible(sec + " .pb-sc-stk-panel"))
            chk(label + " button in header", await page.is_visible(sec + " [data-act=stackmenu]"))
            await page.click(sec + " [data-act=stackver][data-v=LSB]"); await page.wait_for_timeout(150)
            n = await page.locator(sec + " .sc-var").count()
            chk(label + " differences highlighted", n >= 2, str(n))
            await page.screenshot(path=str(OUT / f"stack_{label}_1.png"))
            await page.click(sec + " .sc-var >> nth=0"); await page.wait_for_timeout(150)
            sel = await page.locator(sec + " .sc-var.sel").count()
            alts = await page.locator(sec + " .sc-stk-a").all_inner_texts()
            chk(label + " tap stacks", sel == 1 and len(alts) == 1 and "LSB" in alts[0], str(alts))
            await page.click(sec + " .sc-var.sel"); await page.wait_for_timeout(150)
            chk(label + " tap again removes", await page.locator(sec + " .sc-var.sel").count() == 0)
            await page.click(sec + " .sc-var >> nth=0"); await page.wait_for_timeout(100); await page.click(sec + " .sc-var:not(.sel) >> nth=0"); await page.wait_for_timeout(150)
            await page.click(sec + " [data-act=stackver][data-v=NASB]"); await page.wait_for_timeout(150)
            chk(label + " keeps choices after adding translation", await page.locator(sec + " .sc-var.sel").count() == 2)
            plain = await page.evaluate("document.querySelector('#editor .pb-scripture[data-id=tst1]').dataset.stack")
            chk(label + " stack saved on section", "LSB" in plain and "sel" in plain, plain[:90])
            # slides
            await page.click(sec + " [data-act=slides]"); await page.wait_for_timeout(300)
            print("kinds:", await page.locator(".mk-kind").all_inner_texts())
            await page.locator(".mk-kind:not([disabled])").first.click(); await page.wait_for_timeout(500)
            await page.screenshot(path=str(OUT / f"stack_{label}_picker.png"))
            await page.click("#mk-add"); await page.wait_for_timeout(500)
            await page.click("#tab-build"); await page.wait_for_timeout(600)
            CNT = "document.querySelectorAll('.slide .sc-stk').length"
            st = await page.evaluate(CNT)

            chk(label + " slides carry stack", st >= 2, str(st))
            pass
            await page.click("#tab-present"); await page.wait_for_timeout(500); await page.screenshot(path=str(OUT / f"stack_{label}_present.png")); await page.click("#tab-build"); await page.wait_for_timeout(400)
            await page.click(sec + " .sc-var.sel >> nth=0"); await page.wait_for_timeout(400)
            await page.click("#tab-build"); await page.wait_for_timeout(500)
            st2 = await page.evaluate(CNT)
            chk(label + " slides follow unselect", 0 < st2 < st, str(st2))
            await page.click("#tab-build"); await page.wait_for_timeout(500)
            await page.screenshot(path=str(OUT / f"stack_{label}_2.png"))
            await page.click("#tab-present"); await page.wait_for_timeout(400)
            chk(label + " no controls in present", not await page.locator("#manuscript .pb-sc-stk-btn").first.is_visible() if await page.locator("#manuscript .pb-sc-stk-btn").count() else True)
            chk(label + " no errors", not errs, str(errs)); await ctx.close()
        await b.close()
    sys.exit(1 if bad else 0)
asyncio.run(main())
