const { JSDOM, VirtualConsole } = require("jsdom"); const fs = require("fs");
const html = fs.readFileSync(require("path").join(__dirname, "..", "..", "pulpit-binder.html"), "utf8");
const store = new Map(); const subs = [];
function mkDb(){ const notify=()=>subs.forEach(f=>f());
 const doc = path => ({ async get(){ const d=store.get(path); return {id:path.split("/").pop(), exists:!!d, data:()=>d&&JSON.parse(d), metadata:{hasPendingWrites:false}}; },
   async set(v){ store.set(path, JSON.stringify(v)); notify(); }, async delete(){ store.delete(path); notify(); },
   onSnapshot(cb){ const f=async()=>cb(await doc(path).get()); subs.push(f); f(); return ()=>{}; } });
 const collection = path => ({ onSnapshot(cb){ let prev=new Map(); const f=()=>{ const docs=[...store.keys()].filter(k=>k.startsWith(path+"/")&&k.split("/").length===path.split("/").length+1).map(k=>({id:k.split("/").pop(),exists:true,data:()=>JSON.parse(store.get(k))})); const ch=docs.map(d=>({type:"added",doc:d})); cb({docs,docChanges:()=>ch,metadata:{}}); }; subs.push(f); setTimeout(f,10); return ()=>{}; } });
 return { doc, collection }; }
let up=0;
function boot(name){ return new Promise(res => {
 const vc = new VirtualConsole(); const errs=[]; vc.on("jsdomError", e => errs.push(e.message)); vc.on("warn", (...a)=>errs.push("warn "+a.join(" ")));
 const dom = new JSDOM("<!doctype html><html><head></head><body>" + html + "</body></html>", { runScripts: "dangerously", virtualConsole: vc, url: "https://x.test/#edit", beforeParse(w) {
  w.matchMedia = () => ({ matches: false }); w.ResizeObserver = class { observe() {} }; w.requestAnimationFrame = f => setTimeout(f, 0);
  w.URL.createObjectURL = () => "blob:x"; w.document.execCommand = () => true; w.Element.prototype.scrollIntoView = () => {};
  const db = mkDb();
  w.claude = { use: async n => n==="db"?db : n==="user"?{id:async()=>"u1"} : n==="assets"?{upload:async b=>({id:"a"+(++up)})} : null };
 }});
 setTimeout(()=>res({w:dom.window, errs}), 500); }); }
(async()=>{
 const A = await boot("A"); const d=A.w.document;
 console.log("A pill:", d.querySelector("#sync").textContent);
 // user edits example
 const ed=d.querySelector("#editor"); ed.querySelector("p").append(" EDITED-ON-A"); ed.dispatchEvent(new A.w.Event("input"));
 await new Promise(r=>setTimeout(r,3500));
 console.log("A pill after edit:", d.querySelector("#sync").textContent, "cloud keys:", [...store.keys()].length, A.errs);
 const B = await boot("B"); await new Promise(r=>setTimeout(r,800));
 const db=B.w.document;
 console.log("B editor has edit:", db.querySelector("#editor").textContent.includes("EDITED-ON-A"), "B pill:", db.querySelector("#sync").textContent, "library:", [...db.querySelectorAll("#library option")].map(o=>o.textContent));
 console.log("B errs", B.errs);
 process.exit(0);
})();
