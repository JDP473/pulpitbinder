const { JSDOM, VirtualConsole } = require("jsdom"); const fs = require("fs");
const html = fs.readFileSync(require("path").join(__dirname, "..", "..", "pulpit-binder.html"), "utf8");
const vc = new VirtualConsole(); const errs = [];
vc.on("jsdomError", e => errs.push(e.message + (e.detail ? " " + e.detail : ""))); vc.on("error", e => errs.push(String(e)));
const dom = new JSDOM("<!doctype html><html><head></head><body>" + html + "</body></html>", { runScripts: "dangerously", virtualConsole: vc, url: "https://x.test/#edit", beforeParse(w) {
  w.matchMedia = () => ({ matches: false, addEventListener() {} });
  w.ResizeObserver = class { observe() {} }; w.requestAnimationFrame = f => setTimeout(f, 0);
  w.URL.createObjectURL = () => "blob:x";
  w.document.execCommand = () => true;
  w.Element.prototype.scrollIntoView = () => {}; w.Element.prototype.scrollTo = () => {}; w.cancelAnimationFrame = clearTimeout;
}});
const w = dom.window;
setTimeout(() => {
  const d = w.document;
  console.log("errors:", errs);
  console.log("editor blocks:", d.querySelector("#editor").children.length, "cues:", d.querySelectorAll("#editor .pb-slide").length);
  console.log("gutter thumbs:", d.querySelectorAll("#gutter .g-thumb").length, "rails:", d.querySelectorAll("#gutter .g-rail").length, [...d.querySelectorAll(".g-lbl")].map(x=>x.textContent).join(" | ")); console.log("stats:", d.querySelector("#ed-stats").textContent);
  console.log("sugg cards:", d.querySelectorAll(".sg").length, d.querySelector(".sg .sg-reason")?.textContent);
  // apply first quick check
  const btn = [...d.querySelectorAll(".sg .btn.primary")][0]; if (btn) btn.click();
  setTimeout(() => {
    console.log("marks after apply:", d.querySelectorAll("#editor mark").length, errs.slice(-2));
    d.querySelector("#tab-present").click();
    console.log("present secs:", d.querySelectorAll(".sec").length, "cues:", d.querySelectorAll(".sec .cue").length, "pos:", d.querySelector("#pos").textContent);
    d.querySelector("#tab-analysis").click();
    console.log("preached panel:", d.querySelector("#preached-out").textContent.slice(0, 80));
    // as-preached sample with timestamps
    d.querySelector("#tab-build").click();
    const ta = d.querySelector("#rec-preached");
    ta.value = "0:00\nGood morning. Open your Bibles with me to Psalm 119, and we will read verse 105 together.\n2:10\nNotice first what the psalmist does not say. He does not say God's word is a floodlight\n6:40\nSecond, a lamp only helps if you carry it. A lamp left on the shelf does nothing for your feet.\n11:05\nThird, the lamp is for the dark. Verse 107 says I am severely afflicted.\n16:00\nIf you have never begun walking with Christ, the first step is clear.";
    ta.dispatchEvent(new w.Event("input"));
    d.querySelector("#rec-link").value = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"; d.querySelector("#rec-link").dispatchEvent(new w.Event("input"));
    setTimeout(() => {
      d.querySelector("#tab-analysis").click();
      console.log("preached:", d.querySelector("#preached-out").textContent.slice(0, 300));
      console.log("share:\n" + d.querySelector("#share-text").textContent);
      console.log("final errors:", errs);
    }, 600);
  }, 500);
}, 800);
