"""The shared interface: one control size, the header and its Sermon menu, keyboard use of the section tabs, the skip link,
dialog focus, and on a phone the bottom section bar. Screenshots go to tests/out/ui_*.png."""
import asyncio, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"\n       got  {got!r}\n       want {want!r}")
    if not ok: fails.append(name)

INIT = "const smp = async () => ({text:''}); smp.json = async () => ({}); smp.limits = async () => ({}); window.claude = { use: async n => n === 'sample' ? smp : null };"
VIEWS = ["dash", "build", "study", "edit", "present", "materials", "analysis"]
# heights of the ordinary controls on screen; compact ones (.sm, the editor toolbar, suggestion actions) are checked apart
SIZES = """() => { const vis = e => e.offsetParent !== null && e.getBoundingClientRect().height > 0;
  const q = sel => [...document.querySelectorAll(sel)].filter(vis);
  const h = els => [...new Set(els.map(e => Math.round(e.getBoundingClientRect().height)))].sort((a, b) => a - b);
  const view = '.view:not([hidden]) ';
  return { regular: h([...q('header .btn, header select, header .icon-btn'), ...q(view + '.btn:not(.sm):not(.link-btn):not(.ghost)'), ...q(view + 'select:not(.sm)'), ...q(view + 'input[type=text],' + view + 'input[type=number],' + view + 'input[type=datetime-local]')].filter(e => !e.closest('.ed-toolbar,.sg-act,.sel-pop,.st-vn'))),
           compact: h(q('.ed-toolbar select, .ed-toolbar .btn, .sg-act .btn')) }; }"""

async def open_page(b, scheme="light", viewport=(1400, 900), mobile=False):
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, color_scheme=scheme, timezone_id="America/Chicago", is_mobile=mobile, has_touch=mobile)
    await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}</style></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.goto("https://x.test/#build"); await page.wait_for_timeout(800)
    return ctx, page, errs

async def active(page): return await page.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.className || document.activeElement.tagName)")

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        # ---------- desktop ----------
        ctx, page, errs = await open_page(b)
        await page.keyboard.press("Tab")
        check("the first Tab stop is the skip link", await active(page), "skip-link")
        await page.screenshot(path=str(OUT / "ui_skip.png"))
        await page.keyboard.press("Enter"); await page.wait_for_timeout(100)
        check("it moves focus to the content", await active(page), "main")
        top = await page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect(); return { brand: r('.brand').top, tabs: r('.tabs').top, lib: r('#library').top, menu: r('#btn-sermon').top, settings: r('#btn-settings').top, theme: r('#btn-theme').top }; }""")
        check("one row: brand, tabs, picker, menu and tools line up", max(top.values()) - min(top.values()) < 16, True)
        check("the Sermon menu starts closed", (await page.is_visible("#sermon-menu"), await page.get_attribute("#btn-sermon", "aria-expanded")), (False, "false"))
        for v in VIEWS:
            await page.click(f"#tab-{v}"); await page.wait_for_timeout(250)
            sz = await page.evaluate(SIZES)
            check(f"{v}: ordinary controls share one height", sz["regular"], [36])
            check(f"{v}: compact controls share one height", sz["compact"] in ([], [30]), True)
        await page.click("#tab-build"); await page.wait_for_timeout(200)

        # the Sermon menu
        await page.click("#btn-sermon"); await page.wait_for_timeout(100)
        check("menu opens with its three actions", (await page.is_visible("#sermon-menu"), await page.get_attribute("#btn-sermon", "aria-expanded"), await page.locator("#sermon-menu .menu-item").count()), (True, "true", 3))
        check("focus lands on the first action", await active(page), "btn-new")
        await page.keyboard.press("ArrowDown"); check("arrow down moves to Import", await active(page), "btn-import")
        await page.keyboard.press("ArrowDown"); check("and then to Delete", await active(page), "btn-del")
        await page.keyboard.press("ArrowDown"); check("and wraps around", await active(page), "btn-new")
        await page.screenshot(path=str(OUT / "ui_menu.png"))
        await page.keyboard.press("Escape")
        check("Escape closes the menu and returns to its button", (await page.is_visible("#sermon-menu"), await active(page)), (False, "btn-sermon"))
        await page.click("#btn-sermon"); await page.mouse.click(700, 600); await page.wait_for_timeout(100)
        check("clicking elsewhere closes it", await page.is_visible("#sermon-menu"), False)
        n0 = await page.locator("#library option").count()
        await page.click("#btn-sermon"); await page.click("#btn-new"); await page.wait_for_timeout(300)
        check("New sermon closes the menu and adds one", (await page.is_visible("#sermon-menu"), await page.locator("#library option").count()), (False, n0 + 1))

        # tabs from the keyboard
        await page.focus("#tab-build")
        await page.keyboard.press("ArrowRight"); await page.wait_for_timeout(200)
        check("arrow right opens the next section", (await page.get_attribute("#tab-study", "aria-selected"), await page.is_visible("#view-study"), await active(page)), ("true", True, "tab-study"))
        check("only the open section is in the tab order", await page.evaluate("[...document.querySelectorAll('.tab')].map(t => t.tabIndex).join()"), "-1,-1,0,-1,-1,-1,-1")
        await page.keyboard.press("Home"); await page.wait_for_timeout(200)
        check("Home goes to the first", (await page.get_attribute("#tab-dash", "aria-selected"), await page.is_visible("#view-dash")), ("true", True))
        await page.keyboard.press("End"); await page.wait_for_timeout(200)
        check("End goes to the last", (await page.get_attribute("#tab-analysis", "aria-selected"), await page.is_visible("#view-analysis")), ("true", True))
        check("each section names its tab", await page.evaluate("[...document.querySelectorAll('section.view')].every(s => s.getAttribute('role') === 'tabpanel' && document.getElementById(s.getAttribute('aria-labelledby')))"), True)
        await page.click("#tab-build")

        # dialog focus
        await page.click("#btn-settings"); await page.wait_for_timeout(250)
        check("opening Settings moves focus inside it", await page.evaluate("document.querySelector('#settings').contains(document.activeElement)"), True)
        for _ in range(60): await page.keyboard.press("Tab")
        check("Tab stays inside the dialog", await page.evaluate("document.querySelector('#settings').contains(document.activeElement)"), True)
        await page.keyboard.press("Shift+Tab")
        check("and so does Shift+Tab", await page.evaluate("document.querySelector('#settings').contains(document.activeElement)"), True)
        await page.keyboard.press("Escape"); await page.wait_for_timeout(150)
        check("closing returns focus to the button that opened it", await active(page), "btn-settings")
        await page.click("#btn-sermon"); await page.click("#btn-import"); await page.wait_for_timeout(250)
        check("a dialog opened from the menu also takes focus", await page.evaluate("document.querySelector('#import-modal').contains(document.activeElement)"), True)
        await page.keyboard.press("Escape"); await page.wait_for_timeout(150)
        check("and gives it back to the Sermon button", await active(page), "btn-sermon")
        check("page errors", [e for e in errs if "ERR_FAILED" not in e], [])
        for v in VIEWS:
            await page.click(f"#tab-{v}"); await page.wait_for_timeout(300)
            await page.screenshot(path=str(OUT / f"ui_{v}.png"))
        await ctx.close()

        # ---------- dark ----------
        ctx, page, errs = await open_page(b, "dark")
        await page.screenshot(path=str(OUT / "ui_dark_build.png"))
        await page.click("#btn-sermon"); await page.wait_for_timeout(100)
        await page.screenshot(path=str(OUT / "ui_dark_menu.png"))
        check("dark: menu text is readable against its panel", await page.evaluate("""() => { const c = getComputedStyle(document.querySelector('#sermon-menu .menu-item')), m = getComputedStyle(document.querySelector('#sermon-menu')); return c.color !== m.backgroundColor; }"""), True)
        await ctx.close()

        # ---------- a narrow laptop: the picker moves to its own row, nothing is lost ----------
        ctx, page, errs = await open_page(b, viewport=(1100, 800))
        vis = await page.evaluate("['#library','#sync','#btn-sermon','#btn-settings','#btn-theme','#btn-collapse'].map(s => { const r = document.querySelector(s).getBoundingClientRect(); return r.width > 0 && r.right <= innerWidth; })")
        check("1100px: every header control is on screen", vis, [True] * 6)
        await page.screenshot(path=str(OUT / "ui_1100.png"))
        await ctx.close()

        # ---------- phone ----------
        ctx, page, errs = await open_page(b, viewport=(390, 844), mobile=True)
        bar = await page.evaluate("""() => { const r = document.querySelector('.tabs').getBoundingClientRect(); return { bottom: Math.round(r.bottom), top: Math.round(r.top), vh: innerHeight, fixed: getComputedStyle(document.querySelector('.tabs')).position, tabs: [...document.querySelectorAll('.tab')].map(t => { const b = t.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height), getComputedStyle(t.querySelector('.tab-ic')).display]; }) }; }""")
        check("phone: sections are a fixed bar at the bottom", (bar["fixed"], bar["bottom"]), ("fixed", bar["vh"]))
        check("phone: each section button is a full touch target with an icon", all(w >= 44 and h >= 44 and d == "block" for w, h, d in bar["tabs"]), True)
        for v in VIEWS:
            await page.click(f"#tab-{v}"); await page.wait_for_timeout(350)
            sw = await page.evaluate("document.documentElement.scrollWidth")
            check(f"phone {v}: no sideways scroll", sw, 390)
            sz = await page.evaluate(SIZES)
            check(f"phone {v}: ordinary controls are 44px", sz["regular"], [44])
            await page.screenshot(path=str(OUT / f"ui_phone_{v}.png"))
        await page.click("#tab-build"); await page.wait_for_timeout(300)
        await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)"); await page.wait_for_timeout(200)
        gap = await page.evaluate("""() => { const last = [...document.querySelectorAll('#view-build .panel')].pop().getBoundingClientRect().bottom; return Math.round(document.querySelector('.tabs').getBoundingClientRect().top - last); }""")
        check("phone: the end of a page is not hidden behind the bar", gap >= 0, True)
        await page.click("#tab-edit"); await page.wait_for_timeout(400)
        sheet = await page.evaluate("""() => ({ sheet: Math.round(document.querySelector('.sg-col').getBoundingClientRect().bottom), bar: Math.round(document.querySelector('.tabs').getBoundingClientRect().top) })""")
        check("phone: the suggestions sheet rests on top of the bar", abs(sheet["sheet"] - sheet["bar"]) <= 2, True)
        await page.click("#tab-build"); await page.click("#btn-sermon"); await page.wait_for_timeout(150)
        menu = await page.evaluate("(() => { const r = document.querySelector('#sermon-menu').getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight; })()")
        check("phone: the Sermon menu stays on screen", menu, True)
        await page.screenshot(path=str(OUT / "ui_phone_menu.png"))
        await page.keyboard.press("Escape")
        await page.click("#tab-present"); await page.wait_for_timeout(500)
        pr = await page.evaluate("""() => ({ scroll: document.documentElement.scrollHeight, view: innerHeight, manu: Math.round(document.querySelector('#manuscript').getBoundingClientRect().bottom), bar: Math.round(document.querySelector('.tabs').getBoundingClientRect().top) })""")
        check("phone: Present fits the screen above the bar", (pr["scroll"] <= pr["view"], pr["manu"] <= pr["bar"]), (True, True))
        check("page errors", [e for e in errs if "ERR_FAILED" not in e], [])
        await ctx.close()
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
asyncio.run(main())
