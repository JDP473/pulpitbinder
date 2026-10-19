"""Settings: services with days and times, places preached, and new sermon defaults.
Runs with the clock fixed on Tuesday, October 20, 2026 at 9:00 AM Central, so the next service is Wednesday."""
import asyncio, pathlib, datetime
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
NOW = datetime.datetime(2026, 10, 20, 14, 0, tzinfo=datetime.timezone.utc)  # 9:00 AM in Chicago
fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"got {got!r} want {want!r}")
    if not ok: fails.append(name)

async def open_page(b, scheme="light", viewport=(1400, 900), mobile=False):
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, color_scheme=scheme, timezone_id="America/Chicago", is_mobile=mobile, has_touch=mobile)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.clock.set_fixed_time(NOW)
    await page.goto("https://x.test/#build"); await page.wait_for_timeout(700)
    return ctx, page, errs

meta = "() => ({ when: document.querySelector('#m-when').value, service: document.querySelector('#m-service').value, place: document.querySelector('#m-place').value, speaker: document.querySelector('#m-speaker').value, wpm: document.querySelector('#m-wpm').value })"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx, page, errs = await open_page(b)
        opts = await page.evaluate("[...document.querySelectorAll('#m-service option')].map(o => o.textContent)")
        check("service options from settings", opts[:3] + opts[-1:], ["Sunday AM", "Sunday PM", "Wednesday Bible Study", "Add a service…"])

        await page.click("#btn-new"); await page.wait_for_timeout(200)
        m = await page.evaluate(meta)
        check("new sermon starts on next service", (m["when"], m["service"]), ("2026-10-21T19:00", "Wednesday Bible Study"))
        check("new sermon default place", m["place"], "Bridge Creek church of Christ")

        await page.select_option("#m-service", "Sunday PM"); await page.wait_for_timeout(100)
        check("choosing a service sets its time", (await page.evaluate(meta))["when"], "2026-10-21T18:00")

        await page.fill("#m-place", "Oak Grove church of Christ"); await page.wait_for_timeout(100)
        check("save-to-places shows for a new place", await page.is_visible("#m-place-save"), True)
        await page.click("#m-place-save"); await page.wait_for_timeout(100)
        check("save-to-places hides once saved", await page.is_visible("#m-place-save"), False)
        check("place suggestions", await page.evaluate("[...document.querySelectorAll('#place-list option')].map(o => o.value)"), ["Bridge Creek church of Christ", "Oak Grove church of Christ"])

        # Add a service from the sermon's own Service list
        await page.select_option("#m-service", "__add"); await page.wait_for_timeout(200)
        check("add a service opens Settings on Services", (await page.is_visible("#settings"), await page.is_visible("#set-pane-services")), (True, True))
        check("new row is focused", await page.evaluate("document.activeElement.classList.contains('sv-name')"), True)
        await page.keyboard.type("Thursday Devotional")
        rows = page.locator("#set-svcs .set-row")
        last = rows.nth(await rows.count() - 1)
        await last.locator(".sv-day").select_option("4"); await last.locator(".sv-time").fill("19:30")
        await page.screenshot(path=str(OUT / "set_services.png"))
        await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(200)
        m = await page.evaluate(meta)
        check("added service is picked with its time", (m["service"], m["when"]), ("Thursday Devotional", "2026-10-21T19:30"))

        # Places: star Oak Grove and rename it; the open sermon follows the rename
        await page.click("[data-set-tab=places]"); await page.wait_for_timeout(150)
        await page.locator("#set-places .set-row").nth(1).locator(".set-star").click()
        await page.locator("#set-places .set-row").nth(1).locator("input").fill("Oak Grove")
        await page.screenshot(path=str(OUT / "set_places.png"))
        await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(200)
        check("rename follows to open sermon", (await page.evaluate(meta))["place"], "Oak Grove")

        # New sermon defaults
        await page.click("#btn-settings"); await page.click("#set-tab-defaults")
        await page.fill("#set-speaker", "Guest Speaker"); await page.fill("#set-wpm", "150")
        await page.screenshot(path=str(OUT / "set_defaults.png"))
        await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(200)
        await page.click("#btn-new"); await page.wait_for_timeout(200)
        m = await page.evaluate(meta)
        check("new sermon uses defaults", (m["place"], m["speaker"], m["wpm"]), ("Oak Grove", "Guest Speaker", "150"))

        # Validation
        await page.click("#btn-settings"); await page.click("#set-tab-services"); await page.click("#set-svc-add")
        await page.locator("#set-svcs .set-row").last.locator(".sv-time").fill("08:00")
        await page.click("#set-tab-scripture")
        await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(100)
        check("unnamed service is refused", (await page.text_content("#set-msg"), await page.is_visible("#set-pane-services")), ("Give each service a name, or remove the empty row.", True))
        await page.locator("#set-svcs .set-row").last.locator("button[aria-label^=Remove]").click()
        await page.click("#set-cancel")

        # Survives a reload
        await page.reload(); await page.wait_for_timeout(700)
        check("settings kept after reload", "Thursday Devotional" in await page.evaluate("[...document.querySelectorAll('#m-service option')].map(o => o.textContent)"), True)
        await page.screenshot(path=str(OUT / "set_build.png"), clip={"x": 0, "y": 0, "width": 1400, "height": 700})
        check("page errors", errs, [])
        await ctx.close()

        # Dark and phone
        ctx, page, errs = await open_page(b, "dark")
        await page.click("[data-set-tab=services]"); await page.wait_for_timeout(200)
        await page.screenshot(path=str(OUT / "set_services_dark.png"))
        await ctx.close()
        ctx, page, errs = await open_page(b, "light", (390, 844), True)
        await page.click("[data-set-tab=services]"); await page.wait_for_timeout(200)
        await page.screenshot(path=str(OUT / "set_services_phone.png"))
        check("phone: no sideways scroll in dialog", await page.evaluate("(() => { const c = document.querySelector('#settings-form'); return c.scrollWidth <= c.clientWidth; })()"), True)
        await page.click("#set-tab-places"); await page.wait_for_timeout(100)
        await page.screenshot(path=str(OUT / "set_places_phone.png"))
        await page.click("#set-cancel"); await page.wait_for_timeout(100)
        await page.screenshot(path=str(OUT / "set_build_phone.png"))
        check("phone: page width", await page.evaluate("document.documentElement.scrollWidth"), 390)
        check("phone page errors", errs, [])
        await ctx.close()
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
asyncio.run(main())
