/* Pulpit Binder on sermon.freely.church. The app is the same file published on Claude; on Claude it reaches the
   platform through window.claude.use(...). This gives it the same calls, backed by this site's server:
     sample     Claude, with the preacher's own Anthropic key (or the owner's, when lent)
     db         the preacher's synced documents, with live updates
     user       the signed-in account
     assets     files (slides, pictures, recordings), shown at /_blob/<id>
     downloads  saving a file from the browser
   mcp (Canva, Firecrawl, Pulpit Live) is not offered here; the app already works without it. */
(() => {
  "use strict";
  const boot = window.__PB__ || {};

  /* This browser's local copy belongs to one account. Another account signing in here starts clean, so one
     preacher's sermons never show up (or sync up) under another's. */
  const KEEP = new Set(["pb-theme", "pb-read", "pb-follow", "pb-hosted-user"]);
  function forgetLocal() {
    try { indexedDB.deleteDatabase("pulpit-binder"); } catch {}
    try { for (const k of Object.keys(localStorage)) if (k.startsWith("pb-") && !KEEP.has(k)) localStorage.removeItem(k); } catch {}
    try { sessionStorage.clear(); } catch {}
  }
  try {
    const last = localStorage.getItem("pb-hosted-user");
    if (last && last !== boot.id) forgetLocal();
    localStorage.setItem("pb-hosted-user", boot.id);
  } catch {}

  // ---------- Talking to the server ----------
  const fail = (code, message, status) => Object.assign(new Error(message || code), { code, status });
  async function api(method, url, body, raw) {
    let r;
    try {
      r = await fetch(url, {
        method, credentials: "same-origin",
        headers: raw ? { "content-type": raw.type || "application/octet-stream" } : body !== undefined ? { "content-type": "application/json" } : {},
        body: raw || (body !== undefined ? JSON.stringify(body) : undefined)
      });
    } catch { throw fail("unavailable", "Couldn't reach the server."); }
    let j = null; try { j = await r.json(); } catch {}
    if (r.status === 401) signedOut();
    if (!r.ok) throw fail((j && j.code) || (r.status === 429 ? "rate_limited" : r.status === 401 ? "signed_out" : r.status >= 500 ? "unavailable" : "failed"), j && j.error, r.status);
    return j;
  }

  // ---------- A small notice at the bottom of the page ----------
  let noteEl = null;
  function notice(text, link, label) {
    const show = () => {
      if (!noteEl) {
        noteEl = document.createElement("div");
        noteEl.setAttribute("role", "status");
        noteEl.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:2147483000;max-width:min(560px,calc(100vw - 32px));box-sizing:border-box;display:flex;gap:12px;align-items:center;padding:12px 14px;border-radius:12px;background:#1a2130;color:#fff;font:500 14px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.25)";
        document.body.append(noteEl);
      }
      noteEl.replaceChildren();
      const t = document.createElement("span"); t.textContent = text; t.style.flex = "1"; noteEl.append(t);
      if (link) { const a = document.createElement("a"); a.href = link; a.textContent = label; a.style.cssText = "color:#f4ead6;font-weight:700;white-space:nowrap"; noteEl.append(a); }
      const x = document.createElement("button"); x.type = "button"; x.textContent = "Close"; x.style.cssText = "background:none;border:0;color:#c9cbd2;font:inherit;cursor:pointer;padding:4px";
      x.onclick = () => { noteEl.remove(); noteEl = null; }; noteEl.append(x);
    };
    document.body ? show() : addEventListener("DOMContentLoaded", show, { once: true });
  }
  let toldSignedOut = false;
  function signedOut() {
    if (toldSignedOut) return; toldSignedOut = true;
    notice("You have been signed out. Your work is kept in this browser until you sign in again.", "/login?next=/app", "Sign in");
  }

  // ---------- Claude ----------
  const KEY_HELP = { no_key: "Claude needs an Anthropic API key. Add yours in Account.", bad_key: null, no_credit: null };
  const sample = async () => { throw fail("unsupported", "Use sample.json"); };
  sample.json = async (prompt, opts = {}) => {
    const tier = ["quick", "default", "complex"].includes(opts.modelTier) ? opts.modelTier : "default";
    try {
      const r = await api("POST", "/api/ai", { prompt: String(prompt), tier });
      return r.value;
    } catch (e) {
      if (e.code in KEY_HELP) notice(KEY_HELP[e.code] || e.message, "/account#claude", "Open Account");
      throw e;
    }
  };
  sample.limits = async () => ({});

  // ---------- Documents ----------
  const clone = v => v == null ? v : JSON.parse(JSON.stringify(v));
  const lastSeg = p => p.slice(p.lastIndexOf("/") + 1);
  const parentOf = p => p.slice(0, p.lastIndexOf("/"));
  const docSnap = (path, data) => ({
    id: lastSeg(path), ref: { path, id: lastSeg(path) }, exists: data != null,
    data: () => data == null ? undefined : clone(data), get: f => data == null ? undefined : clone(data[f]),
    metadata: { hasPendingWrites: false, fromCache: false }
  });
  const querySnap = (docs, changes) => ({
    docs, size: docs.length, empty: !docs.length, forEach: fn => docs.forEach(fn),
    docChanges: () => changes, metadata: { hasPendingWrites: false, fromCache: false }
  });

  // One feed for the page: the server says when anything changed, then the changes in watched collections come down.
  const watchers = new Set();   // { parent, onChange(change) }
  let cursor = 0, pulling = null, again = false, source = null, pollT = null;
  function watchedParents() { return [...new Set([...watchers].map(w => w.parent))]; }
  async function pull() {
    if (pulling) { again = true; return pulling; }
    pulling = (async () => {
      do {
        again = false;
        const parents = watchedParents(); if (!parents.length) return;
        let more = true;
        while (more) {
          const q = new URLSearchParams({ since: String(cursor) }); parents.forEach(p => q.append("parent", p));
          const r = await api("GET", "/api/db/changes?" + q);
          for (const ch of r.changes) for (const w of [...watchers]) if (w.parent === ch.parent) { try { w.onChange(ch); } catch (e) { console.warn("db listener", e); } }
          cursor = Math.max(cursor, r.seq || 0); more = r.more;
        }
      } while (again);
    })().catch(e => { if (e.code !== "signed_out") console.warn("db feed", e); }).finally(() => { pulling = null; });
    return pulling;
  }
  function startFeed() {
    if (source || typeof EventSource === "undefined") return;
    source = new EventSource("/api/db/events");
    source.addEventListener("seq", ev => { if (+ev.data > cursor) pull(); });
    source.onerror = () => { if (source && source.readyState === 2) { source = null; setTimeout(startFeed, 10000); } };
    clearInterval(pollT); pollT = setInterval(pull, 60000);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") pull(); });
    addEventListener("online", pull);
  }
  function addWatcher(w, seq) {
    if (!watchers.size) cursor = seq; else if (seq < cursor) pull();
    watchers.add(w); startFeed();
    return () => watchers.delete(w);
  }

  const docRef = path => ({
    path, id: lastSeg(path),
    async get() { const r = await api("GET", "/api/db/doc?path=" + encodeURIComponent(path)); return docSnap(path, r.exists ? r.data : null); },
    async set(data) { await api("PUT", "/api/db/doc", { path, data: clone(data) }); },
    async delete() { await api("DELETE", "/api/db/doc?path=" + encodeURIComponent(path)); },
    onSnapshot(next, error) {
      let stop = null, closed = false;
      api("GET", "/api/db/doc?path=" + encodeURIComponent(path)).then(r => {
        if (closed) return;
        next(docSnap(path, r.exists ? r.data : null));
        stop = addWatcher({ parent: parentOf(path), onChange: ch => { if (ch.path === path) next(docSnap(path, ch.data)); } }, r.seq || 0);
      }).catch(e => { if (error) error(e); });
      return () => { closed = true; if (stop) stop(); };
    }
  });

  function query(path, order, lim) {
    const params = () => { const q = new URLSearchParams({ collection: path }); if (order) { q.set("orderBy", order.field); q.set("dir", order.dir); } if (lim) q.set("limit", String(lim)); return q; };
    const list = () => api("GET", "/api/db/list?" + params());
    return {
      path, id: lastSeg(path),
      doc: id => docRef(path + "/" + id),
      orderBy: (field, dir = "asc") => query(path, { field, dir }, lim),
      limit: n => query(path, order, n),
      async get() { const r = await list(); return querySnap(r.docs.map(d => docSnap(path + "/" + d.id, d.data)), r.docs.map(d => ({ type: "added", doc: docSnap(path + "/" + d.id, d.data) }))); },
      onSnapshot(next, error) {
        let stop = null, closed = false;
        const known = new Map();
        list().then(r => {
          if (closed) return;
          for (const d of r.docs) known.set(d.id, d.data);
          const docs = () => [...known].map(([id, data]) => docSnap(path + "/" + id, data));
          next(querySnap(docs(), r.docs.map(d => ({ type: "added", doc: docSnap(path + "/" + d.id, d.data) }))));
          stop = addWatcher({
            parent: path,
            onChange: ch => {
              const id = lastSeg(ch.path);
              let type;
              if (ch.data == null) { if (!known.has(id)) return; known.delete(id); type = "removed"; }
              else { type = known.has(id) ? "modified" : "added"; known.set(id, ch.data); }
              next(querySnap(docs(), [{ type, doc: docSnap(ch.path, ch.data) }]));
            }
          }, r.seq || 0);
        }).catch(e => { if (error) error(e); });
        return () => { closed = true; if (stop) stop(); };
      }
    };
  }
  const db = { doc: docRef, collection: path => query(path, null, 0) };

  // ---------- Files and downloads ----------
  const assets = {
    async upload(blob) {
      if (!(blob instanceof Blob)) blob = new Blob([blob]);
      const r = await api("POST", "/api/assets", undefined, blob);
      return { id: r.id, url: "/_blob/" + r.id };
    }
  };
  const downloads = {
    async save({ filename, data, mimeType }) {
      const blob = data instanceof Blob ? data : new Blob([data], { type: mimeType || (typeof data === "string" ? "text/plain;charset=utf-8" : "application/octet-stream") });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = filename || "download"; a.style.display = "none";
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      return { ok: true };
    }
  };
  const user = { id: async () => boot.id, name: async () => boot.name, email: async () => boot.email };

  const services = { sample, db, user, assets, downloads, mcp: null };
  window.claude = {
    use: async name => (name in services ? services[name] : null),
    hosted: { name: boot.name || "", email: boot.email || "", claude: boot.claude, owner: !!boot.owner }
  };

  // ---------- Account and sign out, in the app's More menu ----------
  addEventListener("DOMContentLoaded", () => {
    const menu = document.getElementById("sermon-menu"); if (!menu) return;
    const item = (text, fn) => { const b = document.createElement("button"); b.type = "button"; b.className = "menu-item"; b.setAttribute("role", "menuitem"); b.textContent = text; b.onclick = fn; return b; };
    const sep = document.createElement("div"); sep.className = "menu-sep"; sep.setAttribute("role", "separator");
    menu.append(sep, item("Account and Claude key", () => { location.href = "/account"; }));
    if (boot.owner) menu.append(item("Site admin", () => { location.href = "/admin"; }));
    menu.append(item("Sign out", async () => {
      try { await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }); } catch {}
      forgetLocal();
      try { localStorage.removeItem("pb-hosted-user"); } catch {}
      location.href = "/";
    }));
    if (!boot.claude) notice("Claude's help (analysis, suggestions, outlines, slides) needs an Anthropic API key. Add yours in Account.", "/account#claude", "Add a key");
  });
})();
