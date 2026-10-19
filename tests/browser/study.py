"""Text Study, with Firecrawl and Claude mocked. The "translations" below are made-up sentences, not any real Bible text.
Every outside request is counted in localStorage so the test can show that a second visit pulls nothing again."""
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

INIT = r"""
const bump = k => localStorage.setItem(k, (+localStorage.getItem(k) || 0) + 1);
const TEXT = {
  ESV:  "1 The lamp gives light to every path. 2 Walk in its light and be glad. 3 Keep the word close to your heart, for it lights the way.",
  NASB: "1 The lamp gives light to every trail. 2 Walk in its light and rejoice. 3 Keep the word near to your heart, for it lights the way.",
  NKJV: "1 A lamp gives light to every path. 2 Walk in the light and be glad. 3 Keep the word close to your heart, for it lights the way.",
  LSB:  "1 The lamp gives light to every path. 2 Walk in its light and be glad. 3 Keep the word close to your own heart, for it lights the way."
};
const sef = { 'Rashi_on_Psalms.7.1': { en: ['A made-up comment from the first commentator.'], he: ['הערה לדוגמה'] }, 'Ibn_Ezra_on_Psalms.7.1': { en: ['A made-up comment from the second commentator.'], he: [] } };
const smp = async () => ({ text: '' });
smp.json = async (p) => {
  bump('__smp'); await new Promise(r => setTimeout(r, 120));
  if (p.includes('Task: background and word study')) return { author: 'A made-up author', audience: 'Made-up first hearers', date: 'About a thousand years before Christ', genre: 'Song', setting: 'A made-up setting for the song.', mainIdea: 'The word gives light for the next step.', structure: [{ range: 'v. 1', label: 'The lamp gives light' }, { range: 'v. 2-3', label: 'Walk in it and keep it close' }], keyWords: [{ word: 'lamp', original: 'נר', translit: 'ner', gloss: 'lamp, light', note: 'A small oil lamp.' }], observations: ['The word light repeats.', 'The command is plain.'] };
  if (p.includes('Task: manuscript variants')) return { summary: 'No significant variant readings.', variants: [] };
  if (p.includes('Task: how Christians have read')) return { eras: [{ era: 'Early church (to about AD 500)', voices: ['A Made-Up Father'], summary: 'Read the lamp as the guiding word.', emphasis: 'Guidance.' }, { era: 'Medieval (about 500 to 1500)', voices: [], summary: 'Read it in four senses.' }, { era: 'Reformation and after (1500 to 1800)', voices: [], summary: 'Stressed Scripture alone.' }, { era: 'Restoration Movement and the modern era (1800 to now)', voices: [], summary: 'Stressed the plain sense.' }], differences: [{ topic: 'What the path is', views: [{ tradition: 'Reformed', view: 'The whole of life.' }, { tradition: 'Restoration Movement and churches of Christ', view: 'The walk of obedience.' }] }], caution: 'A short summary of a long history.' };
  if (p.includes('Task: Hebrew and Jewish understanding')) return { hebrew: [{ word: 'lamp', original: 'נר', translit: 'ner', meaning: 'lamp', note: 'Also a figure for a household.' }], eras: [{ era: 'Second Temple period and the Septuagint', voices: [], summary: 'Light as instruction.' }, { era: 'Targums, Talmud, and Midrash', voices: [], summary: 'Torah as a lamp.' }, { era: 'Medieval commentators (for example Rashi, Ibn Ezra, Radak, Maimonides)', voices: ['Rashi'], summary: 'Guidance in decisions of law.' }, { era: 'Early modern and modern Jewish readings', voices: [], summary: 'Light in daily life.' }], howItChanged: 'From instruction to daily guidance.', caution: 'A summary only.' };
  if (p.includes('Task: group cross references')) return { themes: [{ label: 'Light and lamp', why: 'The word as light.', refs: ['Proverbs 6:23'] }] };
  if (p.includes('Task: answer a question')) return { answer: 'A short, made-up, pastoral answer.', refs: ['Proverbs 6:23'], alternatives: 'Some read it narrowly.', uncertainty: '' };
  if (p.includes('Task: mind map')) return { center: 'Psalm 7:1-3', branches: [{ label: 'Main idea', children: [{ label: 'Light for the next step' }] }, { label: 'Key words', children: [{ label: 'lamp' }, { label: 'path' }] }, { label: 'Application', children: [{ label: 'Walk in the light' }] }] };
  return {};
};
smp.limits = async () => ({});
const mcp = { callTool: async (srv, tool, input) => {
  bump('__mcp'); const u = input.url || '';
  if (u.includes('biblegateway.com')) { const v = (u.match(/version=([A-Z0-9]+)/) || [])[1]; return { payload: { markdown: TEXT[v] || '' } }; }
  if (u.includes('openbible.info')) return { payload: { markdown: 'Psalm 7 Cross References\n====\n\n### Psalm 7:1\n\nThe lamp gives light.\n\n### [Proverbs 6:23](https://x/search?q=Proverbs+6%3A23)\n Helpful? [Yes](https://x/#u)\n [No](https://x/#d)\n\nA made-up cross reference text about a lamp.\n\n### [John 8:12](https://x/search?q=John+8%3A12)\n Helpful? [Yes](https://x/#u)\n [No](https://x/#d)\n\nAnother made-up cross reference text.\n\nUnless otherwise indicated, all content is licensed.' } };
  if (u.includes('sefaria.org')) { const key = decodeURIComponent(u.split('/api/texts/')[1].split('?')[0]); const j = sef[key]; return { payload: { markdown: '```json\n' + JSON.stringify(j ? { ref: key.replace(/_/g, ' '), text: j.en, he: j.he } : { error: 'No text found' }) + '\n```' } }; }
  return { payload: { markdown: '' } };
} };
window.__saved = null;
window.claude = { use: async n => n === 'sample' ? smp : n === 'mcp' ? mcp : n === 'downloads' ? { save: async o => { window.__saved = o; } } : null };
"""
CALLS = "() => [+localStorage.getItem('__mcp') || 0, +localStorage.getItem('__smp') || 0]"

async def open_page(b, scheme="light", viewport=(1400, 900), mobile=False, clear=True):
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
    await page.clock.set_system_time(NOW)
    await page.goto("https://x.test/#study"); await page.wait_for_timeout(900)
    return ctx, page, errs

async def settle(page, ms=500): await page.wait_for_timeout(ms)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx, page, errs = await open_page(b)
        check("the Study tab is there", await page.is_visible("#tab-study"), True)
        chips = await page.evaluate("[...document.querySelectorAll('#st-vers .st-vchip')].map(c => c.textContent + (c.classList.contains('on') ? '*' : ''))")
        check("favorite translations start selected", chips[:4], ["ESV*", "LSB*", "NASB*", "NKJV*"])

        await page.fill("#st-ref", "Psalm 7:1-3"); await page.click("#st-form button[type=submit]"); await settle(page, 1500)
        check("three verses load", await page.evaluate("document.querySelectorAll('#st-compare .st-verse').length"), 3)
        check("differences are marked", await page.evaluate("document.querySelectorAll('#st-compare .st-var').length") >= 4, True)
        check("the strip shows each verse", await page.evaluate("document.querySelectorAll('#st-compare .st-strip .bk').length"), 3)

        # hover shows what each translation chose
        await page.hover("#stv-7-1 .st-var >> nth=0"); await settle(page, 200)
        tip = await page.text_content("#st-tip")
        check("hovering shows the other readings", all(x in tip for x in ["ESV", "NKJV", "LSB", "The", "A"]), True)
        await page.mouse.move(5, 5); await settle(page, 100)
        check("moving away hides it", await page.is_visible("#st-tip"), False)
        vw = await page.evaluate("[...document.querySelectorAll('#stv-7-1 .st-var')].map(v => v.textContent)")
        check("the places that differ in verse 1", vw, ["The", "path"])
        await page.click("#stv-7-2 .st-var >> nth=0"); await settle(page, 150)
        check("tapping pins it", (await page.is_visible("#st-tip"), "NASB" in await page.text_content("#st-tip") or "NKJV" in await page.text_content("#st-tip")), (True, True))
        await page.keyboard.press("Escape"); await settle(page, 100)
        check("Escape closes it", await page.is_visible("#st-tip"), False)
        await page.screenshot(path=str(OUT / "study_compare.png"))

        await page.click("#st-compare .st-seg button >> text=Stacked"); await settle(page, 200)
        check("stacked view layers the readings", (await page.evaluate("document.querySelectorAll('#st-compare .st-var.stack').length") > 0, await page.evaluate("document.querySelectorAll('#st-compare .st-va').length") > 0), (True, True))
        await page.screenshot(path=str(OUT / "study_stacked.png"))
        await page.click("#st-compare .st-seg button >> text=Hover"); await settle(page, 150)
        await page.select_option("#st-base", "NASB"); await settle(page, 200)
        check("the reading text can change", await page.evaluate("document.querySelector('#stv-7-1').textContent.includes('trail')"), True)
        await page.select_option("#st-base", "ESV"); await settle(page, 150)
        await page.check("#st-logic"); await settle(page, 150)
        check("connecting words are marked", await page.evaluate("[...document.querySelectorAll('#st-compare .lg')].map(x => x.textContent.toLowerCase())"), ["for"])
        await page.uncheck("#st-logic")
        await page.click("#st-compare .st-kws .chip >> nth=0"); await settle(page, 150)
        check("a repeated word can be marked", await page.evaluate("document.querySelectorAll('#st-compare .kw').length") >= 2, True)

        # cross references
        await page.click("#st-xref .btn >> text=Find cross references"); await settle(page, 1500)
        check("cross references appear for each verse", await page.evaluate("document.querySelectorAll('#st-xref details.st-xr').length"), 3)
        check("with their text", await page.evaluate("[...document.querySelectorAll('#st-xref .st-xi')].length >= 6 && document.querySelector('#st-xref .st-xt').textContent.length > 10"), True)
        check("and a map of where they land", await page.evaluate("document.querySelectorAll('#st-xref .bk.l1, #st-xref .bk.l2, #st-xref .bk.l3, #st-xref .bk.l4').length > 0"), True)
        await page.click("#st-xref button >> text=Group by theme"); await settle(page, 400)
        check("grouping by theme", "Light and lamp" in await page.text_content("#st-xref"), True)
        await page.click("#st-xref .st-xi >> nth=0 >> text=Add to notes"); await settle(page, 100)
        check("a cross reference can go to the notes", "Proverbs 6:23" in await page.input_value("#st-notes textarea >> nth=0"), True)

        # background and history
        await page.click("#st-context .btn >> text=Study the background"); await settle(page, 700)
        check("background and word study", (lambda tx: all(x in tx for x in ["The word gives light for the next step", "A made-up author", "ner", "How it is built"]))(await page.text_content("#st-context")), True)
        await page.click("#st-history .st-hist >> nth=0 >> text=Trace it"); await settle(page, 500)
        await page.click("#st-history .st-hist >> nth=1 >> text=Trace it"); await settle(page, 500)
        h = await page.text_content("#st-history")
        check("Christian and Jewish readings through history", all(x in h for x in ["Early church", "Where traditions differ", "Reformed", "Targums, Talmud", "From instruction to daily guidance"]), True)
        await page.click("#st-history button >> text=/Read Rashi/"); await settle(page, 1500)
        h = await page.text_content("#st-history")
        check("Sefaria sources, and the ones with nothing", all(x in h for x in ["A made-up comment from the first commentator", "A made-up comment from the second commentator", "Radak: no comment", "Metzudat David: no comment"]), True)
        check("Hebrew shown right to left", await page.evaluate("[...document.querySelectorAll('#st-history .st-hebtext')].every(e => e.dir === 'rtl')"), True)

        # questions
        await page.locator("#stv-7-2 .st-vn").scroll_into_view_if_needed(); await settle(page, 300)   # scrolling closes the tip, so scroll first
        await page.click("#stv-7-2 .st-vn"); await settle(page, 150)
        await page.click("#st-tip .btn >> text=Ask a question about this verse"); await settle(page, 300)
        check("a verse's question form is set to it", await page.input_value("#st-q-v"), "2")
        await page.fill("#st-q-text", "What does it mean to walk in the light?"); await page.click("#st-questions button[type=submit]"); await settle(page, 200)
        check("the question is kept", (await page.evaluate("document.querySelectorAll('#st-questions .st-q').length"), "Verse 2" in await page.text_content("#st-questions .st-qm")), (1, True))
        await page.click("#st-questions .st-q .btn >> text=Ask Claude"); await settle(page, 600)
        check("Claude's answer is kept with it", ("A short, made-up, pastoral answer." in await page.text_content("#st-questions"), await page.is_checked("#st-questions .st-q input[type=checkbox]")), (True, True))
        await page.fill("#st-notes textarea >> nth=0", "My own note."); await settle(page, 800)

        # pictures
        await page.click("#st-viz button >> text=Mind map from this study"); await settle(page, 300)
        check("a mind map from the study", (await page.evaluate("document.querySelectorAll('#st-viz svg').length"), await page.evaluate("document.querySelectorAll('#st-viz svg g').length") >= 6), (1, True))
        mm = await page.inner_text("#st-viz") if False else await page.evaluate("[...document.querySelectorAll('#st-viz svg text')].map(t => t.textContent).join(' | ')")
        check("it gathers what was found", all(x in mm for x in ["Psalm 7:1-3", "Cross references", "Questions", "Through history"]), True)
        await page.screenshot(path=str(OUT / "study_map.png"), full_page=True)
        await page.click("#st-viz button >> text=Mind map with Claude"); await settle(page, 700)
        check("a mind map drawn by Claude", "Light for the next step" in await page.evaluate("[...document.querySelectorAll('#st-viz svg text')].map(t => t.textContent).join(' | ')"), True)
        await page.click("#st-viz button >> text=How it is built"); await settle(page, 300)
        check("how it is built", await page.evaluate("document.querySelectorAll('#st-viz .st-sb').length"), 2)
        await page.click("#st-viz button >> text=Through the centuries"); await settle(page, 300)
        check("the centuries side by side", (await page.evaluate("document.querySelectorAll('#st-viz .st-tc.ch .st-te').length"), await page.evaluate("document.querySelectorAll('#st-viz .st-tc.jw .st-te').length")), (4, 4))
        await page.screenshot(path=str(OUT / "study_full.png"), full_page=True)

        # export
        await page.click("#st-save"); await settle(page, 200)
        saved = await page.evaluate("window.__saved")
        check("the study saves as Markdown", (saved["filename"], all(x in saved["data"] for x in ["# Text study: Psalm 7:1-3", "## Where the translations differ", "## Cross references", "## Background", "## Questions", "My own note."])), ("psalm-7-1-3-study.md", True))

        # everything is kept: a second visit pulls nothing again
        calls = await page.evaluate(CALLS); await page.wait_for_timeout(900)
        await page.reload(); await page.wait_for_timeout(2500)
        check("the passage and what was found come back", (await page.input_value("#st-ref"), await page.evaluate("document.querySelectorAll('#st-compare .st-verse').length"), await page.evaluate("document.querySelectorAll('#st-xref details.st-xr').length"), "The word gives light" in await page.text_content("#st-context"), await page.evaluate("document.querySelectorAll('#st-questions .st-q').length")), ("Psalm 7:1-3", 3, 3, True, 1))
        check("with no new requests", await page.evaluate(CALLS), calls)
        check("page errors", [e for e in errs if "ERR_FAILED" not in e], [])
        await ctx.close()

        for name, scheme, vp, mob in [("study_phone", "light", (390, 844), True), ("study_dark", "dark", (1400, 900), False)]:
            ctx, page, errs = await open_page(b, scheme, vp, mob)
            await page.fill("#st-ref", "Psalm 7:1-3"); await page.click("#st-form button[type=submit]"); await settle(page, 1500)
            await page.click("#st-xref .btn >> text=Find cross references"); await settle(page, 1200)
            await page.screenshot(path=str(OUT / (name + ".png")), full_page=mob)
            if mob: check("phone: no sideways scroll", await page.evaluate("document.documentElement.scrollWidth"), 390)
            await ctx.close()
        await b.close()
    print("FAILED: " + ", ".join(fails) if fails else "all passed")
asyncio.run(main())
