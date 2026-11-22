"""A browser a tester can drive one step at a time, for usability walk-throughs by people or by smaller Claude models.

    python3 tests/usability/serve.py PORT desktop|phone light|dark OUTDIR [first]

"first" opens the app as a new preacher sees it, with only the example sermon; without it, 26 generic sermons are saved.
Each action is sent with tests/usability/do and answers with the path of a fresh screenshot. Every step is written to
OUTDIR/log.jsonl, so the path a tester took can be read back afterwards. See tests/usability/README.md."""
import sys, json, time, pathlib, random
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parents[2]
JSZIP = open(ROOT / "tests" / "node" / "node_modules" / "jszip" / "dist" / "jszip.min.js").read()
def records():
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
        recs.append({"id":"s%02d"%i,"updatedAt":1700000000000+i,"meta":{"title":"Sermon %d on %s"%(i+1,t.split(' ')[0]),"text":t,"when":"%d-%02d-%02dT10:30"%(y,mo,random.randint(1,27)),"service":random.choice(svc),"place":"Bridge Creek church of Christ","speaker":"Jarred Pettijohn","wpm":140,"series":"Faith series" if i%5==0 else ""},"html":"<h2>Introduction</h2><p>"+body[:600]+"</p><h2>The text</h2><p>"+body[600:]+"</p>","slides":[],"manual":{},"ai":ai,"media":{"link":"https://youtu.be/x" if i%3==0 else ""}})
    return recs
SEED = """recs => new Promise(res => { const q = indexedDB.open('pulpit-binder', 2); q.onsuccess = () => { const tx = q.result.transaction('sermons','readwrite'); const st = tx.objectStore('sermons'); recs.forEach(r => st.put(r)); tx.oncomplete = res; }; })"""
port, form, scheme, out = int(sys.argv[1]), sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4]); out.mkdir(parents=True, exist_ok=True)
first = len(sys.argv) > 5 and sys.argv[5] == "first"   # first run: no saved sermons, only the example
HTML = open(ROOT / "pulpit-binder.html").read(); MOCK = open(pathlib.Path(__file__).parent / "mock.js").read()
vp = (390, 844) if form == "phone" else (1366, 800)
pw = sync_playwright().start(); b = pw.chromium.launch()
ctx = b.new_context(viewport={"width": vp[0], "height": vp[1]}, color_scheme=scheme, timezone_id="America/Chicago", is_mobile=form == "phone", has_touch=form == "phone")
ctx.add_init_script(MOCK); page = ctx.new_page(); notes = []
page.on("pageerror", lambda e: notes.append("PAGE ERROR: " + str(e)[:200]))
def on_dialog(d): notes.append(f"A browser {d.type} box appeared saying: {d.message!r}. It was accepted."); d.accept()
page.on("dialog", on_dialog)
def route(r):
    u = r.request.url
    if "jszip" in u: r.fulfill(body=JSZIP, content_type="application/javascript")
    elif u.startswith("https://x.test/"): r.fulfill(body="<!doctype html><html><head><meta charset=utf8><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:0}</style></head><body>" + HTML + "</body></html>", content_type="text/html")
    else: r.abort()
page.route("**/*", route); page.goto("https://x.test/"); page.wait_for_timeout(900)
if not first:
    page.evaluate(SEED, records()); page.reload(); page.wait_for_timeout(1300)
n = [0]; log = open(out / "log.jsonl", "a")
def shot():
    n[0] += 1; f = out / f"step-{n[0]:03d}.png"; page.screenshot(path=str(f)); return str(f)
CONTROLS = """() => { const out = []; const seen = new Set();
  const name = e => (e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].textContent) || e.innerText || e.value || e.getAttribute('placeholder') || e.getAttribute('title') || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
  for (const e of document.querySelectorAll('button, a[href], input, select, textarea, [role=button], [role=tab], [role=menuitem], [role=option], [contenteditable=true], summary, [tabindex="0"]')) {
    const r = e.getBoundingClientRect(); if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const cs = getComputedStyle(e); if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
    const x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2); const top = document.elementFromPoint(x, y); if (!top || !(e === top || e.contains(top) || top.contains(e))) continue;
    const kind = e.tagName === 'INPUT' ? 'input:' + (e.type || 'text') : e.tagName === 'SELECT' ? 'dropdown' : e.tagName === 'TEXTAREA' ? 'textbox' : e.isContentEditable ? 'editable text' : (e.getAttribute('role') || e.tagName.toLowerCase());
    const k = x + ',' + y; if (seen.has(k)) continue; seen.add(k);
    out.push(`${kind} "${name(e)}" at ${x},${y}` + (e.disabled ? ' (disabled)' : '') + (e.tagName === 'SELECT' ? ' options: ' + [...e.options].slice(0, 12).map(o => o.textContent.trim()).join(' | ') : '')); }
  return out; }"""
def act(cmd, a):
    if cmd == "look": return ""
    if cmd == "controls": return "\n".join(page.evaluate(CONTROLS))
    if cmd == "click": page.mouse.click(float(a[0]), float(a[1])); return ""
    if cmd == "dblclick": page.mouse.dblclick(float(a[0]), float(a[1])); return ""
    if cmd == "hover": page.mouse.move(float(a[0]), float(a[1])); return ""
    if cmd == "type": page.keyboard.type(a[0], delay=5); return ""
    if cmd == "key": page.keyboard.press(a[0]); return ""
    if cmd == "scroll":
        x, y = (float(a[1]), float(a[2])) if len(a) > 2 else (vp[0] / 2, vp[1] / 2)
        page.mouse.move(x, y); page.mouse.wheel(0, float(a[0])); return ""
    if cmd == "choose":
        el = page.evaluate_handle("([x, y]) => { const e = document.elementFromPoint(x, y); return e && (e.closest('select') || e); }", [float(a[0]), float(a[1])]).as_element()
        if not el or el.evaluate("e => e.tagName") != "SELECT": return "There is no dropdown at that point."
        el.select_option(label=a[2]); return ""
    if cmd == "drag": page.mouse.move(float(a[0]), float(a[1])); page.mouse.down(); page.mouse.move(float(a[2]), float(a[3]), steps=8); page.mouse.up(); return ""
    if cmd == "select-text":
        ok = page.evaluate("""t => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const i = n.textContent.indexOf(t); if (i >= 0 && n.parentElement.offsetParent) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + t.length); const ed = n.parentElement.closest('[contenteditable=true]'); if (ed) ed.focus(); const s = getSelection(); s.removeAllRanges(); s.addRange(r); n.parentElement.scrollIntoView({ block: 'center' }); document.dispatchEvent(new Event('selectionchange')); (ed || document).dispatchEvent(new MouseEvent('mouseup', { bubbles: true })); return true; } } return false; }""", a[0])
        return "" if ok else "Those words were not found on the page."
    if cmd == "upload":
        with page.expect_file_chooser(timeout=4000) as fc: page.mouse.click(float(a[0]), float(a[1]))
        fc.value.set_files(a[2]); return ""
    return "Unknown command."
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); cmd, a = body["cmd"], body.get("args", [])
        try:
            msg = act(cmd, a); page.wait_for_timeout(1500 if cmd in ("click", "key", "choose", "upload") else 400)
        except Exception as e: msg = "That did not work: " + str(e).split("\n")[0][:200]
        f = "" if cmd == "controls" else shot()
        extra = list(notes); notes.clear()
        log.write(json.dumps({"t": time.time(), "cmd": cmd, "args": a, "shot": f, "msg": msg[:300], "notes": extra, "view": page.evaluate("document.body.dataset.view || ''"), "scrollW": page.evaluate("document.documentElement.scrollWidth - innerWidth")}) + "\n"); log.flush()
        res = "\n".join(x for x in [msg, *extra, ("Screenshot: " + f) if f else ""] if x)
        self.send_response(200); self.end_headers(); self.wfile.write(res.encode())
print("ready", port, flush=True)
HTTPServer(("127.0.0.1", port), H).serve_forever()
