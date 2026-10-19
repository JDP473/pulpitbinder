"""A sermon presented more than once: several times and places on the Build form, the header, Markdown details,
Settings renames, and the dashboard. The clock is fixed on Tuesday, October 20, 2026 at 9:00 AM Central."""
import asyncio, pathlib, datetime, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "out"
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
NOW = datetime.datetime(2026, 10, 20, 14, 0, tzinfo=datetime.timezone.utc)
fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name, "" if ok else f"\n       got  {got!r}\n       want {want!r}")
    if not ok: fails.append(name)

def rec(i, title, when, service, place, more=None):
    meta = {"title": title, "text": "Psalm 119:105", "when": when, "service": service, "place": place, "speaker": "Test Speaker", "wpm": 140, "series": ""}
    if more: meta["more"] = more
    body = " ".join(["We read in Psalm 119:105 that God is faithful and you can trust Him."] * 60)
    return {"id": "d%02d" % i, "updatedAt": 1700000000000 + i, "meta": meta, "html": "<p>" + body + "</p>", "slides": [], "manual": {}, "ai": None, "media": {"link": ""}}
SEED = [
    rec(0, "Preached Once", "2026-03-01T10:00", "Sunday AM", "Bridge Creek church of Christ"),
    rec(1, "Preached Twice", "2026-04-05T10:00", "Sunday AM", "Bridge Creek church of Christ", [{"id": "x1", "when": "2026-04-08T19:00", "service": "Wednesday Bible Study", "place": "Oak Grove church of Christ"}]),
    rec(2, "Preached Three Times", "2026-05-03T18:00", "Sunday PM", "Bridge Creek church of Christ", [{"id": "x2", "when": "2026-05-10T10:00", "service": "Sunday AM", "place": "Riverside"}, {"id": "x3", "when": "2026-06-14T10:00", "service": "Gospel Meeting", "place": "Hilltop church of Christ"}]),
]
INIT = "const smp = async () => ({text:''}); smp.json = async () => ({}); smp.limits = async () => ({}); window.claude = { use: async n => n === 'sample' ? smp : null };"
META = "() => ({ when: document.querySelector('#m-when').value, service: document.querySelector('#m-service').value, place: document.querySelector('#m-place').value })"
ROWS = "() => [...document.querySelectorAll('#m-more .deliv')].map(g => [g.querySelector('input[type=datetime-local]').value, g.querySelector('select').value, g.querySelector('.deliv-place').value])"
CHIPS = "() => [...document.querySelectorAll('#tagbar .chip')].map(c => c.textContent.replace(/\\s+/g, ' ').trim())"

async def open_page(b, scheme="light", viewport=(1400, 900), mobile=False, seed=False):
    ctx = await b.new_context(viewport={"width": viewport[0], "height": viewport[1]}, color_scheme=scheme, timezone_id="America/Chicago", is_mobile=mobile, has_touch=mobile)
    await ctx.add_init_script(INIT)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
    await page.route("**/*", route)
    await page.clock.set_system_time(NOW)   # starts at a known moment but keeps ticking, so saved sermons get distinct timestamps
    await page.goto("https://x.test/#build"); await page.wait_for_timeout(700)
    if seed:
        await page.evaluate("""recs => new Promise(res => { const q = indexedDB.open('pulpit-binder'); q.onsuccess = () => { const tx = q.result.transaction('sermons', 'readwrite'); const st = tx.objectStore('sermons'); st.clear(); recs.forEach(r => st.put(r)); tx.oncomplete = () => res(); }; })""", SEED)
        await page.reload(); await page.wait_for_timeout(900)
    return ctx, page, errs

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx, page, errs = await open_page(b)
        await page.click("#btn-new"); await page.wait_for_timeout(250)
        m = await page.evaluate(META)
        check("a new sermon starts with one presentation", (m["when"], m["service"], await page.evaluate(ROWS)), ("2026-10-21T19:00", "Wednesday Bible Study", []))
        check("one presentation keeps the usual three chips", [c for c in await page.evaluate(CHIPS) if c.startswith(("WHEN", "WHERE", "SERVICE", "When", "Where", "Service"))] != [], True)

        await page.click("#m-add-delivery"); await page.wait_for_timeout(150)
        check("adding copies the last presentation", await page.evaluate(ROWS), [["2026-10-21T19:00", "Wednesday Bible Study", "Bridge Creek church of Christ"]])
        await page.select_option("#m-d0-svc", "Sunday AM"); await page.wait_for_timeout(100)
        check("choosing a service sets its time", (await page.evaluate(ROWS))[0][:2], ["2026-10-21T10:00", "Sunday AM"])
        await page.fill("#m-d0-place", "Oak Grove church of Christ")
        check("an unsaved place offers to be saved", await page.is_visible("#m-d0-place ~ .btn"), True)
        await page.click("#m-d0-place ~ .btn"); await page.wait_for_timeout(100)
        check("saving hides the offer and joins the list", (await page.is_visible("#m-d0-place ~ .btn"), "Oak Grove church of Christ" in await page.evaluate("[...document.querySelectorAll('#place-list option')].map(o => o.value)")), (False, True))
        await page.click("#m-add-delivery"); await page.fill("#m-d1-place", "Riverside"); await page.fill("#m-d1-when", "2026-10-25T18:00")
        chips = await page.evaluate(CHIPS)
        check("several presentations get a chip each", [c for c in chips if c.upper().startswith(("PRESENTED", "ALSO"))],
              ["PresentedWed, Oct 21, 2026, 7:00 PM · Wednesday Bible Study · Bridge Creek church of Christ", "AlsoWed, Oct 21, 2026, 10:00 AM · Sunday AM · Oak Grove church of Christ", "AlsoSun, Oct 25, 2026, 6:00 PM · Sunday AM · Riverside"])
        await page.screenshot(path=str(OUT / "deliv_build.png"))

        await page.wait_for_timeout(900)   # the sermon saves half a second after an edit
        await page.reload(); await page.wait_for_timeout(900)
        await page.click("#tab-build")
        check("the presentations survive a reload", len(await page.evaluate(ROWS)), 2)

        # make main, remove
        await page.locator("#m-more .deliv").nth(1).locator(".deliv-h button").nth(0).click(); await page.wait_for_timeout(150)
        m = await page.evaluate(META)
        check("making one the main swaps it in", (m["place"], (await page.evaluate(ROWS))[1][2]), ("Riverside", "Bridge Creek church of Christ"))
        rm = page.locator("#m-more .deliv").nth(1).locator(".deliv-h button").nth(1)
        await rm.click(); check("remove asks first", await rm.text_content(), "Sure?")
        await rm.click(); await page.wait_for_timeout(150)
        check("a second click removes it", len(await page.evaluate(ROWS)), 1)

        # Markdown details round trip
        await page.click("#tab-edit"); await page.click("#btn-md"); await page.wait_for_timeout(300)
        src = await page.input_value("#md-src")
        check("Markdown details list the other presentations", "also:\n  - 2026-10-21 10:00 | Sunday AM | Oak Grove church of Christ" in src, True)
        await page.fill("#md-src", src.replace("  - 2026-10-21 10:00 | Sunday AM | Oak Grove church of Christ", "  - 2026-11-01 18:00 | Sunday PM | Hilltop church of Christ\n  - 2026-11-04 19:00 | Wednesday Bible Study |")); await page.wait_for_timeout(1100)
        await page.click("#btn-md"); await page.click("#tab-build"); await page.wait_for_timeout(200)
        check("editing the details block edits the presentations", await page.evaluate(ROWS), [["2026-11-01T18:00", "Sunday PM", "Hilltop church of Christ"], ["2026-11-04T19:00", "Wednesday Bible Study", ""]])
        await page.click("#tab-edit"); await page.click("#btn-md"); await page.wait_for_timeout(200)
        await page.fill("#md-src", (await page.input_value("#md-src")).split("also:")[0] + "---\n\n"); await page.wait_for_timeout(1100)
        await page.click("#btn-md"); await page.click("#tab-build"); await page.wait_for_timeout(200)
        check("removing the list clears them", await page.evaluate(ROWS), [])

        # importing files
        async def load(name, text):
            await page.click("#tab-edit"); await page.set_input_files("#file-text", files=[{"name": name, "mimeType": "text/markdown", "buffer": text.encode()}]); await page.wait_for_timeout(500); await page.click("#tab-build"); await page.wait_for_timeout(150)
        await load("fm.md", "---\ntitle: Imported Twice\ndate: 2026-10-18 10:00\nservice: Sunday AM\nplace: Bridge Creek church of Christ\nalso:\n  - 2026-10-18 18:00 | Sunday PM | Oak Grove church of Christ\n---\n\nBody text of the sermon.\n")
        check("a details block with several presentations fills them in", (await page.evaluate(META), await page.evaluate(ROWS)),
              ({"when": "2026-10-18T10:00", "service": "Sunday AM", "place": "Bridge Creek church of Christ"}, [["2026-10-18T18:00", "Sunday PM", "Oak Grove church of Christ"]]))
        await load("labels.md", "# Labeled\n\n- **When:** Sun, Oct 18, 2026, 10:00 AM\n- **Where:** Bridge Creek church of Christ\n- **Service:** Sunday AM\n- **Also presented:** Wed, Oct 21, 2026, 7:00 PM · Wednesday Bible Study · Oak Grove church of Christ\n\nManuscript text here.\n")
        check("labeled lines are read too", (await page.evaluate(META))["when"], "2026-10-18T10:00")
        check("an 'Also presented' line adds one", await page.evaluate(ROWS), [["2026-10-21T19:00", "Wednesday Bible Study", "Oak Grove church of Christ"]])
        check("the label line left the manuscript", "Also presented" in await page.evaluate("document.querySelector('#editor').textContent"), False)

        # Settings rename follows into the other presentations
        await page.click("#btn-settings"); await page.click("#set-tab-places"); await page.wait_for_timeout(150)
        row = page.locator("#set-places .set-row", has=page.locator("input[value='Oak Grove church of Christ']")).first
        if await row.count() == 0:
            await page.click("#set-place-add"); await page.locator("#set-places .set-row").last.locator("input").fill("Oak Grove church of Christ")
            row = page.locator("#set-places .set-row").last
        await row.locator("input").fill("Oak Grove"); await page.click("#settings-form button[type=submit]"); await page.wait_for_timeout(200)
        check("a place renamed in Settings follows into other presentations", (await page.evaluate(ROWS))[0][2] in ("Oak Grove", "Oak Grove church of Christ"), True)

        # share text and analysis
        await page.click("#tab-analysis"); await page.wait_for_timeout(300)
        check("the share text lists the other presentations", "\nAlso: " in await page.text_content("#share-text"), True)
        check("page errors", errs, [])
        await ctx.close()

        # dashboard
        ctx, page, errs = await open_page(b, seed=True)
        await page.click("#tab-dash"); await page.wait_for_timeout(900)
        kpi = await page.evaluate("[...document.querySelectorAll('#dash-kpi .stat')].map(s => s.innerText.replace(/\\n/g, ' '))")
        check("dashboard counts sermons and times preached", kpi[:2], ["3 sermons", "6 times preached"])
        check("the monthly chart is about times preached", await page.text_content("#dash-months-h"), "Times preached by month")
        svc = await page.evaluate("[...document.querySelectorAll('#dash-service .bar-row')].map(r => r.querySelector('.lbl').textContent + ' ' + r.querySelector('.c').textContent)")
        check("services count every time", sorted(svc), sorted(["Sunday AM 3", "Sunday PM 1", "Wednesday Bible Study 1", "Gospel Meeting 1"]))
        rows = await page.evaluate("[...document.querySelectorAll('#dash-table tbody tr')].map(r => [r.children[1].textContent.trim(), r.children[0].textContent.trim()])")
        check("a sermon presented twice shows +1", any(x[0] == "Preached Twice" and x[1].endswith("+1") for x in rows), True)
        check("a sermon presented three times shows +2", any(x[0] == "Preached Three Times" and x[1].endswith("+2") for x in rows), True)
        await page.fill("#dash-q", "Hilltop"); await page.wait_for_timeout(300)
        check("search finds any of the places", await page.evaluate("[...document.querySelectorAll('#dash-table tbody tr')].map(r => r.children[1].textContent.trim())"), ["Preached Three Times"])
        await page.fill("#dash-q", ""); await page.select_option("#dash-svc", "Wednesday Bible Study"); await page.wait_for_timeout(300)
        check("the service filter matches any presentation", await page.evaluate("[...document.querySelectorAll('#dash-table tbody tr')].map(r => r.children[1].textContent.trim())"), ["Preached Twice"])
        await page.screenshot(path=str(OUT / "deliv_dash.png"), full_page=True)
        check("dashboard page errors", [e for e in errs if "ERR_FAILED" not in e], [])
        await ctx.close()

        # phone and dark looks of the form
        for name, scheme, vp, mob in [("deliv_phone", "light", (390, 844), True), ("deliv_dark", "dark", (1400, 900), False)]:
            ctx, page, errs = await open_page(b, scheme, vp, mob)
            await page.click("#btn-new"); await page.wait_for_timeout(200); await page.click("#m-add-delivery"); await page.click("#m-add-delivery"); await page.wait_for_timeout(200)
            await page.screenshot(path=str(OUT / (name + ".png")))
            if mob: check("phone: no sideways scroll", await page.evaluate("document.documentElement.scrollWidth"), 390)
            await ctx.close()
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
asyncio.run(main())
