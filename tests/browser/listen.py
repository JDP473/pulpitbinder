# The Listen tab: the sermon read aloud with a preacher's delivery. The browser's speech engine is replaced by a recorder
# that keeps every sentence with its speed, pitch, loudness, and timing, so the delivery can be checked without sound.
import asyncio, pathlib, sys, json
ROOT = pathlib.Path(__file__).resolve().parents[2]
from playwright.async_api import async_playwright
HTML = open(ROOT / "pulpit-binder.html").read()
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True)
SPEECH = """window.__said = [];
class FakeUtterance { constructor(t) { this.text = t; this.rate = 1; this.pitch = 1; this.volume = 1; this.voice = null; } }
let live = null;
const fake = { speaking: false,
  getVoices: () => [{ name: 'Alex', lang: 'en-US', localService: true }, { name: 'Microsoft Andrew Online (Natural) - English (United States)', lang: 'en-US', localService: false }, { name: 'Thomas', lang: 'fr-FR', localService: true }],
  speak(u) { const rec = { text: u.text, rate: u.rate, pitch: u.pitch, volume: u.volume, voice: u.voice && u.voice.name, at: performance.now() }; window.__said.push(rec); const ms = 25 + u.text.length * 0.6;
    live = { u, t: setTimeout(() => { live = null; rec.end = performance.now(); u.onend && u.onend({}); }, ms) }; u.onstart && setTimeout(() => u.onstart({}), 2); },
  cancel() { if (live) { clearTimeout(live.t); const u = live.u; live = null; u.onerror && u.onerror({ error: 'interrupted' }); } },
  addEventListener() {} };
window.__noSpeech ? Object.defineProperty(window, 'speechSynthesis', { value: undefined, configurable: true }) : Object.defineProperty(window, 'speechSynthesis', { value: fake, configurable: true });
window.SpeechSynthesisUtterance = FakeUtterance;"""
COACH = """window.claude = { use: async n => { if (n !== 'sample') return null; const s = async () => ({}); s.json = async (p) => { await new Promise(r => setTimeout(r, 100));
  const lines = (p.split('Lines:\\n')[1] || '').split('\\n\\nReturn')[0].split('\\n').filter(Boolean);
  return { lines: lines.map((l, k) => ({ n: k + 1, tone: k === 1 ? 'strong' : k === 2 ? 'tender' : 'plain', pause: k === 1 ? 1.8 : 0.3 })) }; }; s.limits = async () => ({}); return s; } };"""
# a manuscript with an introduction, two main points (one with a sub-point), a Scripture section, a PAUSE cue, and a bold key line
MS = """(() => { const ed = document.querySelector('#editor'); ed.innerHTML = `
<p>Good morning. Open your Bibles with me to Psalm 119:105. Is the road dark for you this morning?</p>
<h2>A lamp, not a floodlight</h2>
<p>God rarely shows us the whole road. <strong>He gives us enough light for the next faithful step.</strong> That is enough.</p>
<div class="pb-scripture" contenteditable="false" data-id="t1" data-ref="Psalm 119:105-106" data-ver="ESV" data-texts='{"ESV":{"t":"{{105}} Placeholder words for the first verse. {{106}} Placeholder words for the second verse.","s":"typed"}}'></div>
<h3>Faith walks anyway</h3>
<p>Abraham went out not knowing where he was going. <span class="pb-cue" contenteditable="false">PAUSE</span> He walked by the light he had.</p>
<h2>Carry the lamp</h2>
<p>A lamp only helps if you carry it. A lamp on the shelf does nothing for your feet. A lamp in your hand lights the way. Take it with you this week!</p>`;
  ed.dispatchEvent(new Event('input')); })()"""
SAID = "__said.map(x => x.text)"
async def main():
  async with async_playwright() as p:
    b = await p.chromium.launch(); bad = 0
    def check(tag, what, ok, extra=""):
      nonlocal bad; bad += not ok; print(tag, what, "OK" if ok else "FAIL", extra)
    for w, h, scheme in [(1400, 900, "light"), (1100, 800, "dark"), (390, 800, "light")]:
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, has_touch=w < 500); await ctx.add_init_script(SPEECH + COACH)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>"+HTML+"</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#edit"); await page.wait_for_timeout(1000)
      await page.evaluate(MS); await page.wait_for_timeout(800)
      await page.click("#sub-listen"); await page.wait_for_timeout(600)
      tag = f"{w}{'d' if scheme == 'dark' else ''}"
      parts = await page.evaluate("[...document.querySelectorAll('#ls-list .ls-part')].map(r => r.textContent)")
      check(tag, "parts by heading", len(parts) == 4 and "Before the first heading" in parts[0] and parts[1].startswith("I.") and parts[2].startswith("A.") and parts[3].startswith("II."), str(parts))
      voice = await page.evaluate("document.querySelector('#ls-voice').value")
      check(tag, "a natural voice is chosen first, other languages left out", "Natural" in voice and await page.evaluate("[...document.querySelectorAll('#ls-voice option')].every(o => !o.value.includes('Thomas'))"), voice[:40])
      # choose only point I: its sub-point A comes with it
      await page.click("#ls-none"); await page.click("#ls-list .ls-part:nth-child(2) input"); await page.wait_for_timeout(200)
      on = await page.evaluate("[...document.querySelectorAll('#ls-list input')].map(i => i.checked)")
      check(tag, "a point brings its sub-point", on == [False, True, True, False], str(on))
      await page.click("#ls-play"); await page.wait_for_timeout(200); y0 = await page.evaluate("scrollY")
      await page.wait_for_function("document.querySelector('#ls-play').textContent === 'Play'", timeout=60000)
      said = await page.evaluate("__said")
      texts = [x["text"] for x in said]
      check(tag, "reads only point I, heading first", texts and texts[0] == "A lamp, not a floodlight" and not any("Good morning" in t or "Carry the lamp" in t or "shelf" in t for t in texts), str(texts[:3]))
      check(tag, "Scripture reference read as words", any("Psalm 119, verses 105 through 106" in t for t in texts), str([t for t in texts if "Psalm" in t]))
      key = next((x for x in said if x["text"].startswith("He gives us enough light")), None); plain = next((x for x in said if x["text"].startswith("God rarely")), None)
      check(tag, "the bold key line slows down", key and plain and key["rate"] < plain["rate"], str((key or {}).get("rate")) + " vs " + str((plain or {}).get("rate")))
      verse = next((x for x in said if "first verse" in x["text"]), None)
      check(tag, "Scripture is slower", verse and verse["rate"] < 0.95, str((verse or {}).get("rate")))
      a = next((k for k, x in enumerate(said) if x["text"].startswith("Abraham")), None)
      gap = said[a + 1]["at"] - said[a]["end"] if a is not None and a + 1 < len(said) and said[a].get("end") else 0
      check(tag, "a PAUSE cue is a real silence", gap > 1300, f"{gap:.0f} ms")
      check(tag, "the page did not move", await page.evaluate("scrollY") == y0)
      check(tag, "finished and reset", await page.evaluate("document.querySelector('#ls-play').textContent") == "Play")
      # the whole sermon: the opening question lifts; "A lamp..." lines build
      await page.click("#ls-all"); await page.evaluate("__said = []"); await page.click("#ls-play"); await page.wait_for_timeout(1200)
      await page.screenshot(path=str(OUT / f"listen_{tag}.png"))
      await page.click("#ls-play"); await page.wait_for_timeout(300)   # pause
      n1 = await page.evaluate("__said.length"); await page.wait_for_timeout(700); n2 = await page.evaluate("__said.length")
      check(tag, "Pause stops the reading", n1 == n2 and await page.evaluate("document.querySelector('#ls-play').textContent") == "Resume")
      lastsaid = await page.evaluate("__said[__said.length-1].text")
      await page.click("#ls-play"); await page.wait_for_timeout(300)
      await page.wait_for_function(f"__said.length > {n2}", timeout=5000)
      resumed = await page.evaluate(f"__said[{n2}].text"); texts = await page.evaluate(SAID)
      check(tag, "Resume picks up where it stopped", resumed == lastsaid or (lastsaid in texts and texts.index(lastsaid) == texts.index(resumed) - 1), f"{resumed!r} after {lastsaid!r}")
      await page.wait_for_function("document.querySelector('#ls-play').textContent === 'Play'", timeout=90000)
      said = await page.evaluate("__said")
      q = next((x for x in said if x["text"].startswith("Is the road dark")), None)
      check(tag, "a question lifts", q and q["pitch"] > 1.05, str((q or {}).get("pitch")))
      lamps = [x for x in said if x["text"].startswith("A lamp")]
      check(tag, "repeated openings build", len(lamps) >= 3 and lamps[2]["rate"] > lamps[0]["rate"], str([round(x["rate"], 2) for x in lamps]))
      # click a sentence to start there
      await page.evaluate("__said = []"); await page.click("#ls-read .ls-s:has-text('Take it with you')"); await page.wait_for_timeout(400)
      check(tag, "clicking a sentence starts there", await page.evaluate("__said[0] && __said[0].text.startsWith('Take it with you')"))
      await page.wait_for_timeout(600)
      # plain reading: no variation
      await page.select_option("#ls-style", "plain"); await page.evaluate("__said = []"); await page.click("#ls-play"); await page.wait_for_timeout(2500); await page.click("#ls-stop")
      said = await page.evaluate("__said")
      check(tag, "plain reading is even", said and all(abs(x["rate"] - 1) < .001 and abs(x["pitch"] - 1) < .001 for x in said))
      # Claude directs the delivery
      await page.select_option("#ls-style", "preach"); await page.click("#ls-coach"); await page.wait_for_timeout(800)
      st = await page.evaluate("document.querySelector('#ls-coach-st').textContent")
      await page.evaluate("__said = []"); await page.click("#ls-play"); await page.wait_for_timeout(2500); await page.click("#ls-stop")
      said = await page.evaluate("__said")
      check(tag, "Claude's directions are used", "Claude directed" in st and len(said) >= 3 and said[1]["rate"] < 0.95 and said[2]["volume"] < 0.9 and said[2]["at"] - said[1]["end"] > 1500, st + " " + str([(x["text"][:20], round(x["rate"], 2), round(x["volume"], 2), round(x["at"]), round(x.get("end") or 0)) for x in said[:3]]))
      sw = await page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
      check(tag, "no sideways scroll", sw[0] <= sw[1], str(sw))
      check(tag, "no errors", not errs, str(errs[:2]))
      await ctx.close()
    # a browser that can't speak
    ctx = await b.new_context(viewport={"width": 1100, "height": 800}); await ctx.add_init_script("window.__noSpeech = true;" + SPEECH)
    page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    async def route2(r):
      u = r.request.url
      if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
      elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8></head><body>"+HTML+"</body></html>", content_type="text/html")
      else: await r.abort()
    await page.route("**/*", route2); await page.goto("https://x.test/#listen"); await page.wait_for_timeout(1000)
    note = await page.evaluate("document.querySelector('#ls-note').textContent"); dis = await page.evaluate("document.querySelector('#ls-play').disabled")
    check("nospeech", "says it can't read aloud", "can't read aloud" in note and dis and not errs, note[:50] + str(errs[:1]))
    sys.exit(1 if bad else 0)
asyncio.run(main())
