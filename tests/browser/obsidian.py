"""Saving sermons to Obsidian through a stand-in Obsidian connector: turning it on in Settings, the sermon note with Logos
links and slide embeds, one picture note per slide, only changed slides written again, a rename cleaning up after itself,
and a title another sermon already uses. The written notes go to tests/out/obsidian/, screenshots to tests/out/obs_*."""
import asyncio, json, pathlib, re
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
HTML = open(ROOT / "pulpit-binder.html").read()
assert HTML.count("setSideTab(sideTab);\n})();") == 1
# the served copy only, so the test can reach the open sermon and the Obsidian queue
HTML = HTML.replace("setSideTab(sideTab);\n})();", "setSideTab(sideTab); window.__pb = { get S() { return S; }, save, obsSave, obsFlush, obsQueue, get settings() { return settings; }, get busy() { return obsBusy; }, get last() { return obsLast; }, get queued() { return !!obsT && obsFor === S.id; } };\n})();")
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
H2C = (ROOT / "tests" / "node" / "node_modules" / "html2canvas" / "dist" / "html2canvas.min.js")
OUT = ROOT / "tests" / "out"; OUT.mkdir(exist_ok=True); (OUT / "obsidian").mkdir(exist_ok=True)
INIT = """window.__calls = []; window.__vault = {};
const smp = async () => ({ text: '' }); smp.json = async () => ({}); smp.limits = async () => ({});
const text = t => ({ content: [{ type: 'text', text: t }] });
const mcp = { callTool: async (srv, tool, input) => {
  window.__calls.push({ srv, tool, path: input && input.path, size: input && input.content ? input.content.length : 0 });
  if (srv !== 'Obsidian') throw { code: 'server_not_connected' };
  const p = input.path;
  if (!p.startsWith('AIOS/')) throw { code: 'tool_error', message: 'Writes are only allowed inside: AIOS/.' };
  if (tool === 'read_note') { if (!(p in window.__vault)) throw { code: 'tool_error' }; return text('[Open in Obsidian](obsidian://open)\\n\\n---\\n\\n' + window.__vault[p]); }
  if (tool === 'write_note') { window.__vault[p] = input.content; return text('Wrote ' + p); }
  if (tool === 'delete_note') { delete window.__vault[p]; return text('Deleted ' + p); }
  throw { code: 'tool_error' };
} };
window.claude = { use: async n => n === 'sample' ? smp : n === 'downloads' ? { save: async () => {} } : n === 'mcp' ? mcp : null };"""

async def main():
  h2c = H2C.read_text() if H2C.exists() else None
  async with async_playwright() as p:
    b = await p.chromium.launch()
    for w, h, scheme in [(1440, 900, "light"), (390, 844, "dark")]:
      ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme); await ctx.add_init_script(INIT)
      page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
      async def route(r):
        u = r.request.url
        if "jszip" in u: await r.fulfill(body=JSZIP, content_type="application/javascript")
        elif "html2canvas" in u and h2c: await r.fulfill(body=h2c, content_type="application/javascript")
        elif u.startswith("https://x.test/"): await r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}[hidden]{display:none!important}</style></head><body>" + HTML + "</body></html>", content_type="text/html")
        else: await r.abort()
      await page.route("**/*", route)
      await page.goto("https://x.test/#build"); await page.wait_for_timeout(1500)
      # the example sermon is never saved; make it one of the preacher's own
      await page.evaluate("__pb.S.example = false; __pb.S.meta.title = 'A Lamp to My Feet'; __pb.save()")
      await page.click("#btn-sermon"); await page.wait_for_timeout(150)
      print(w, "menu item", await page.evaluate("!document.querySelector('#btn-obs').hidden"), await page.inner_text("#btn-obs"))
      await page.keyboard.press("Escape")

      # Settings: turn it on; the first save happens right away
      await page.click("#btn-settings"); await page.wait_for_timeout(300); await page.click("#set-tab-obsidian"); await page.wait_for_timeout(200)
      print(w, "defaults", await page.evaluate("[document.querySelector('#set-obs-on').checked, document.querySelector('#set-obs-folder').value]"), "|", await page.inner_text("#set-obs-st"))
      await page.check("#set-obs-on")
      await page.locator("#set-pane-obsidian").screenshot(path=str(OUT / f"obs_settings_{w}_{scheme}.png"))
      await page.click("#settings-form button[type=submit]")
      await page.wait_for_function("() => !__pb.busy && __pb.last.at", timeout=60000)
      calls = await page.evaluate("window.__calls.filter(c => c.srv === 'Obsidian')")
      vault = await page.evaluate("window.__vault")
      n = await page.evaluate("__pb.S.slides.length")
      slide_notes = sorted(k for k in vault if k.startswith("AIOS/Sermons/A Lamp to My Feet slides/"))
      note = vault.get("AIOS/Sermons/A Lamp to My Feet.md", "")
      print(w, "first save:", len(slide_notes), "slide notes for", n, "slides; main note", bool(note), "| largest call", max(c["size"] for c in calls), "| order ok", calls[-1]["path"].endswith("A Lamp to My Feet.md"))
      print(w, "slide note", vault[slide_notes[0]][:40] if slide_notes else None)
      sid = await page.evaluate("__pb.S.id")
      print(w, "front matter", f"pulpit-binder: {sid}" in note, "tags sermon" , "  - sermon" in note, "| embeds", len(re.findall(r"!\[\[AIOS/Sermons/A Lamp to My Feet slides/Slide \d\d\]\]", note)),
            "| logos links", len(re.findall(r"\]\(https://ref\.ly/logosres/esv\?ref=BibleESV\.[1-3]?[A-Za-z]+\d", note)), "| app syntax left", bool(re.search(r"::: scripture|\[slide|==\{", note)))
      (OUT / "obsidian" / f"sermon_{w}.md").write_text(note)
      if slide_notes: (OUT / "obsidian" / "slide_note_start.txt").write_text(vault[slide_notes[0]][:200])
      # write the first slide out as a picture to look at
      if slide_notes:
        import base64
        d = vault[slide_notes[0]]; b64 = d[d.index("base64,") + 7:d.rindex(")")]
        (OUT / "obsidian" / f"slide01_{w}.jpg").write_bytes(base64.b64decode(b64))

      # A Scripture section comes out as a Logos link, the version, and numbered verses (placeholder text, not Scripture)
      await page.evaluate("""__pb.S.html = '<div class="pb-scripture" data-id="t1" data-ref="John 3:16-17" data-ver="ESV" data-texts=\\'{"ESV":{"t":"{{16}} First placeholder verse. {{17}} Second placeholder verse.","s":"typed"}}\\'></div>' + __pb.S.html; __pb.obsSave(true)""")
      await page.wait_for_function("() => !__pb.busy", timeout=30000)
      note2 = await page.evaluate("window.__vault['AIOS/Sermons/A Lamp to My Feet.md']")
      print(w, "scripture block", "[John 3:16–17](https://ref.ly/logosres/esv?ref=BibleESV.Jn3.16-17)\n\nESV\n\n16 First placeholder verse. 17 Second placeholder verse." in note2)

      # Saving again with nothing changed writes only the sermon note
      await page.evaluate("window.__calls = []; __pb.obsSave(true)"); await page.wait_for_function("() => !__pb.busy", timeout=30000)
      print(w, "unchanged save writes", await page.evaluate("window.__calls.filter(c => c.tool === 'write_note').map(c => c.path.split('/').pop())"))

      # Automatic: an edit queues a save; switching sermons sends it first
      await page.evaluate("window.__calls = []; __pb.S.meta.text = 'Psalm 119:105-112'; __pb.save()"); await page.wait_for_timeout(800)
      print(w, "queued after edit", await page.evaluate("__pb.queued"))
      await page.evaluate("__pb.obsFlush()"); await page.wait_for_function("() => !__pb.busy", timeout=30000)
      print(w, "auto save wrote", await page.evaluate("window.__calls.filter(c => c.tool === 'write_note').length"), "notes")

      # A rename moves everything and leaves nothing behind
      await page.evaluate("window.__calls = []; __pb.S.meta.title = 'Light for the Next Step'; __pb.obsSave(true)"); await page.wait_for_function("() => !__pb.busy", timeout=60000)
      vault = await page.evaluate("window.__vault")
      print(w, "after rename", sorted(set(k.split('/')[2] if k.count('/') > 2 else k.split('/')[-1] for k in vault)))

      # A title another sermon already uses: this one adds its date
      await page.evaluate("window.__vault['AIOS/Sermons/Clash.md'] = '---\\npulpit-binder: someone-else\\n---\\nTheirs'; __pb.S.meta.title = 'Clash'; localStorage.removeItem('pb-obs-' + __pb.S.id); __pb.obsSave(true)")
      await page.wait_for_function("() => !__pb.busy", timeout=60000)
      vault = await page.evaluate("window.__vault")
      print(w, "clash kept theirs", vault.get("AIOS/Sermons/Clash.md", "").endswith("Theirs"), "| ours", [k for k in vault if k.startswith("AIOS/Sermons/Clash (")][:1])

      # A folder the connector refuses says so
      await page.evaluate("__pb.settings.obsidian.folder = 'Christ/Sermons'; __pb.obsSave(false)"); await page.wait_for_function("() => !__pb.busy", timeout=30000)
      await page.click("#btn-settings"); await page.wait_for_timeout(300); await page.click("#set-tab-obsidian"); await page.wait_for_timeout(200)
      print(w, "refused folder", await page.inner_text("#set-obs-st"))
      await page.locator("#set-pane-obsidian").screenshot(path=str(OUT / f"obs_settings_err_{w}_{scheme}.png"))
      print(w, "errors", errs, "scrollW", await page.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
      await ctx.close()
    await b.close()

asyncio.run(main())
