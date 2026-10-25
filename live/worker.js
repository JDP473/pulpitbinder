// Pulpit Live relay: one Cloudflare Worker plus one Durable Object per live link.
// Pulpit Binder (a Claude page, which cannot fetch) pushes slide pictures through the MCP endpoint;
// projector screens and OBS open the viewer link. Nothing from a sermon is stored in this repo.
const CODE = /^[a-z0-9]{8,24}$/;
const J = (o, s = 200, h = {}) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json", "cache-control": "no-store", ...h } });
const sha = async t => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t)))].map(b => b.toString(16).padStart(2, "0")).join("");
const same = (a, b) => { a = String(a); b = String(b); let d = a.length ^ b.length; for (let i = 0; i < Math.max(a.length, b.length); i++) d |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0); return d === 0; };

const TOOLS = [
  { name: "live_open", description: "Start or refresh a live link. Returns which slide numbers still need a picture.", inputSchema: { type: "object", properties: { code: { type: "string" }, secret: { type: "string" }, title: { type: "string" }, hashes: { type: "array", items: { type: "string" }, description: "One fingerprint per slide" } }, required: ["code", "secret", "hashes"] } },
  { name: "live_slide", description: "Store one slide picture (base64 JPEG).", inputSchema: { type: "object", properties: { code: { type: "string" }, secret: { type: "string" }, index: { type: "integer" }, hash: { type: "string" }, image: { type: "string" } }, required: ["code", "secret", "index", "hash", "image"] } },
  { name: "live_show", description: "Show this slide on every viewer.", inputSchema: { type: "object", properties: { code: { type: "string" }, secret: { type: "string" }, index: { type: "integer" } }, required: ["code", "secret", "index"] } },
  { name: "live_close", description: "End the link and delete its pictures.", inputSchema: { type: "object", properties: { code: { type: "string" }, secret: { type: "string" } }, required: ["code", "secret"] } },
];

export default {
  async fetch(req, env) {
    const u = new URL(req.url); const p = u.pathname.split("/").filter(Boolean);
    if (!p.length) return new Response("Pulpit Live", { headers: { "content-type": "text/plain" } });
    if (p[0] === "mcp") return mcp(req, env, p[1] || "");
    if (p[0] === "v" && CODE.test(p[1] || "")) {
      const stub = env.ROOM.get(env.ROOM.idFromName(p[1]));
      if (!p[2]) return new Response(VIEWER, { headers: { "content-type": "text/html; charset=utf-8", "content-security-policy": "frame-ancestors *", "cache-control": "no-store", "referrer-policy": "no-referrer" } });
      return stub.fetch(new Request("https://room/" + p.slice(2).join("/") + u.search, { method: "GET" }));
    }
    return new Response("Not found", { status: 404 });
  },
};

async function mcp(req, env, token) {
  if (!env.MCP_TOKEN || !same(token, env.MCP_TOKEN)) return new Response("Not found", { status: 404 });
  if (req.method !== "POST") return new Response("POST only", { status: 405 });
  let body; try { body = await req.json(); } catch { return J({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, 400); }
  const one = async m => {
    const id = m.id; const ok = result => ({ jsonrpc: "2.0", id, result }); const bad = (code, message) => ({ jsonrpc: "2.0", id, error: { code, message } });
    if (id === undefined) return null;
    switch (m.method) {
      case "initialize": return ok({ protocolVersion: (m.params && m.params.protocolVersion) || "2025-03-26", capabilities: { tools: {} }, serverInfo: { name: "Pulpit Live", version: "1.0.0" } });
      case "ping": return ok({});
      case "tools/list": return ok({ tools: TOOLS });
      case "tools/call": {
        const name = m.params && m.params.name, a = (m.params && m.params.arguments) || {};
        if (!TOOLS.some(t => t.name === name)) return bad(-32602, "Unknown tool");
        if (!CODE.test(a.code || "") || typeof a.secret !== "string" || a.secret.length < 16) return ok({ isError: true, content: [{ type: "text", text: JSON.stringify({ error: "bad_code_or_secret" }) }] });
        const r = await env.ROOM.get(env.ROOM.idFromName(a.code)).fetch("https://room/rpc", { method: "POST", body: JSON.stringify({ op: name.slice(5), ...a }) });
        const out = await r.json();
        return ok({ isError: !r.ok, content: [{ type: "text", text: JSON.stringify(out) }] });
      }
      default: return bad(-32601, "Method not found");
    }
  };
  if (Array.isArray(body)) { const rs = (await Promise.all(body.map(one))).filter(Boolean); return rs.length ? J(rs) : new Response(null, { status: 202 }); }
  const r = await one(body); return r ? J(r) : new Response(null, { status: 202 });
}

export class Room {
  constructor(state, env) {
    this.sql = state.storage.sql; this.clients = new Set(); this.ping = null;
    this.sql.exec("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS slides (idx INTEGER PRIMARY KEY, hash TEXT, img BLOB)");
  }
  get(k, d = null) { const r = this.sql.exec("SELECT v FROM meta WHERE k=?", k).toArray(); return r.length ? JSON.parse(r[0].v) : d; }
  set(k, v) { this.sql.exec("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", k, JSON.stringify(v)); }
  view() {
    const hashes = this.get("hashes", []); const have = new Set(this.sql.exec("SELECT idx FROM slides").toArray().map(r => r.idx));
    return { live: !!this.get("secret"), title: this.get("title", ""), cur: this.get("cur", 0), count: hashes.length, hashes: hashes.map((h, i) => have.has(i) ? h : ""), ver: this.get("ver", 0) };
  }
  push() { this.set("ver", this.get("ver", 0) + 1); const s = "data: " + JSON.stringify(this.view()) + "\n\n"; for (const w of this.clients) { try { w.write(new TextEncoder().encode(s)); } catch { this.clients.delete(w); } } }
  async fetch(req) {
    const u = new URL(req.url); const p = u.pathname.split("/").filter(Boolean);
    if (p[0] === "rpc") return this.rpc(await req.json());
    if (p[0] === "state") return J(this.view());
    if (p[0] === "img") {
      const r = this.sql.exec("SELECT hash, img FROM slides WHERE idx=?", parseInt(p[1], 10)).toArray();
      if (!r.length) return new Response("Not found", { status: 404 });
      return new Response(r[0].img, { headers: { "content-type": "image/jpeg", "cache-control": "public, max-age=31536000, immutable", etag: '"' + r[0].hash + '"' } });
    }
    if (p[0] === "events") {
      const { readable, writable } = new TransformStream(); const w = writable.getWriter(); const enc = new TextEncoder();
      this.clients.add(w); w.write(enc.encode("retry: 2000\ndata: " + JSON.stringify(this.view()) + "\n\n"));
      if (!this.ping) this.ping = setInterval(() => { for (const c of this.clients) { c.write(enc.encode(": ping\n\n")).catch(() => this.clients.delete(c)); } if (!this.clients.size) { clearInterval(this.ping); this.ping = null; } }, 15000);
      req.signal && req.signal.addEventListener("abort", () => { this.clients.delete(w); w.close().catch(() => {}); });
      return new Response(readable, { headers: { "content-type": "text/event-stream", "cache-control": "no-store", "x-accel-buffering": "no" } });
    }
    return new Response("Not found", { status: 404 });
  }
  async rpc(m) {
    const h = await sha(m.secret); const have = this.get("secret");
    if (m.op === "open") { if (have && !same(have, h)) return J({ error: "link_taken" }, 403); if (!have) this.set("secret", h); }
    else if (!have || !same(have, h)) return J({ error: "not_open_or_wrong_secret" }, 403);
    if (m.op === "open") {
      const hashes = (Array.isArray(m.hashes) ? m.hashes : []).slice(0, 400).map(x => String(x).slice(0, 40));
      this.set("hashes", hashes); this.set("title", String(m.title || "").slice(0, 120)); this.set("cur", Math.min(this.get("cur", 0), Math.max(0, hashes.length - 1)));
      this.sql.exec("DELETE FROM slides WHERE idx >= ?", hashes.length);
      const stored = new Map(this.sql.exec("SELECT idx, hash FROM slides").toArray().map(r => [r.idx, r.hash]));
      const needs = []; hashes.forEach((x, i) => { if (stored.get(i) !== x) needs.push(i); });
      this.push(); return J({ ok: true, needs, count: hashes.length });
    }
    if (m.op === "slide") {
      const hashes = this.get("hashes", []); const i = m.index | 0;
      if (i < 0 || i >= hashes.length || String(m.hash) !== hashes[i]) return J({ error: "stale_slide" }, 409);
      if (typeof m.image !== "string" || m.image.length > 1500000) return J({ error: "image_too_large" }, 413);
      let bin; try { bin = Uint8Array.from(atob(m.image), c => c.charCodeAt(0)); } catch { return J({ error: "bad_image" }, 400); }
      this.sql.exec("INSERT OR REPLACE INTO slides (idx, hash, img) VALUES (?, ?, ?)", i, hashes[i], bin);
      this.push(); return J({ ok: true });
    }
    if (m.op === "show") { this.set("cur", Math.max(0, m.index | 0)); this.push(); return J({ ok: true }); }
    if (m.op === "close") {
      this.sql.exec("DELETE FROM slides"); this.sql.exec("DELETE FROM meta"); this.push();
      for (const w of this.clients) w.close().catch(() => {}); this.clients.clear(); return J({ ok: true });
    }
    return J({ error: "unknown_op" }, 400);
  }
}

const VIEWER = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Live slides</title>
<style>html,body{margin:0;height:100%;overflow:hidden;background:var(--bg,#000);cursor:none}#st{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;font:20px/1.4 system-ui,sans-serif;color:#8b8478;text-align:center;padding:24px}
img{position:fixed;inset:0;width:100%;height:100%;object-fit:contain;display:block}img[hidden],#st[hidden]{display:none}</style></head><body>
<div id="st">Waiting for the service to begin</div><img id="im" alt="" hidden>
<script>
const q=new URLSearchParams(location.search),code=location.pathname.split("/")[2],B="/v/"+code+"/";
const bg=q.get("bg");if(bg==="transparent")document.documentElement.style.setProperty("--bg","transparent");else if(/^[0-9a-f]{3,8}$/i.test(bg||""))document.documentElement.style.setProperty("--bg","#"+bg);
if(q.get("fit")==="cover")document.getElementById("im").style.objectFit="cover";
const im=document.getElementById("im"),st=document.getElementById("st");let last=null,seen=new Set();
function show(v){
  last=v;const h=v.hashes[v.cur];
  if(!v.live||!v.count){st.hidden=false;im.hidden=true;st.textContent=v.live?"Waiting for the service to begin":"This link is not live";return}
  if(!h){st.hidden=false;im.hidden=true;st.textContent="Loading";return}
  im.src=B+"img/"+v.cur+"?h="+h;im.hidden=false;st.hidden=true;
  for(const j of[v.cur+1,v.cur+2,v.cur-1])if(v.hashes[j]&&!seen.has(j+v.hashes[j])){seen.add(j+v.hashes[j]);new Image().src=B+"img/"+j+"?h="+v.hashes[j]}
}
let poll=null;
function startPoll(){if(poll)return;poll=setInterval(()=>fetch(B+"state").then(r=>r.json()).then(v=>{if(!last||v.ver!==last.ver)show(v)}).catch(()=>{}),1500)}
function connect(){
  if(!window.EventSource){startPoll();return}
  const es=new EventSource(B+"events");
  es.onmessage=e=>{if(poll){clearInterval(poll);poll=null}try{show(JSON.parse(e.data))}catch{}};
  es.onerror=()=>startPoll();
}
connect();
</script></body></html>`;
