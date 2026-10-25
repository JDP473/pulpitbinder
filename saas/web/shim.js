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
        noteEl.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:2147483000;width:min(560px,calc(100vw - 32px));box-sizing:border-box;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;padding:12px 14px;border-radius:12px;background:#1a2130;color:#fff;font:500 14px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.25)";
        document.body.append(noteEl);
      }
      noteEl.replaceChildren();
      const t = document.createElement("span"); t.textContent = text; t.style.flex = "1 1 240px"; noteEl.append(t);
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

  // ---------- Sharing a sermon by email ----------
  const el = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (k === "text") e.textContent = v; else if (k === "class") e.className = v; else e.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) e.append(k);
    return e;
  };
  const when = iso => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  let shareEl = null, shareBack = null;
  // Escape closes the dialog before the app's own Escape handling sees it.
  document.addEventListener("keydown", ev => { if (shareEl && ev.key === "Escape") { ev.preventDefault(); ev.stopImmediatePropagation(); closeShare(); } }, true);
  function closeShare() { if (!shareEl) return; shareEl.remove(); shareEl = null; if (shareBack) shareBack.focus(); }
  async function openShare() {
    const hosted = window.claude.hosted, cur = hosted.current && hosted.current();
    if (!cur) { notice("Open one of your own sermons to share it. The example sermon can't be shared."); return; }
    shareBack = document.activeElement;
    // Let a burst of typing reach the server first, so they get what is on screen.
    for (let i = 0; i < 24 && document.getElementById("sync")?.dataset.state === "saving"; i++) await new Promise(r => setTimeout(r, 250));
    const email = el("input", { type: "email", id: "sh-email", autocomplete: "email", placeholder: "name@example.com", required: true });
    const note = el("textarea", { id: "sh-note", rows: "3", maxlength: "1000", placeholder: "Optional: a word about why you're sending it" });
    const out = el("div", { role: "status", "aria-live": "polite" });
    const send = el("button", { class: "btn primary", type: "submit", text: "Send" });
    const list = el("div", { class: "sh-list" });
    const drawSent = async () => {
      const r = await api("GET", "/api/shares").catch(() => null); if (!r) return;
      const mine = r.sent.filter(x => x.sermonId === cur.id);
      list.replaceChildren(...(mine.length ? [el("div", { class: "set-h", text: "Shared so far" }), ...mine.map(x => el("div", { class: "sh-row" },
        el("span", { class: "sh-to", text: x.to }),
        el("span", { class: "hint", text: x.status === "added" ? `Added ${when(x.at)}` : x.status === "declined" ? "Declined" : `Waiting since ${when(x.at)}` }),
        x.status === "waiting" ? el("button", { class: "btn ghost sm", type: "button", text: "Cancel", onclick: async () => { await api("DELETE", "/api/shares/" + x.id).catch(e => out.replaceChildren(msgEl(e.message))); drawSent(); } }) : null))] : []));
    };
    const msgEl = (t, ok) => el("p", { class: "hint", style: `margin:0;color:var(${ok ? "--ok" : "--warn"})`, text: t });
    const form = el("form", { class: "modal-card", role: "dialog", "aria-modal": "true", "aria-labelledby": "sh-title", novalidate: true, onsubmit: async ev => {
      ev.preventDefault(); out.replaceChildren();
      const to = email.value.trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) { out.append(msgEl("Enter their email address.")); email.focus(); return; }
      send.disabled = true;
      try {
        const r = await api("POST", "/api/shares", { sermonId: cur.id, email: to, note: note.value.trim() || undefined });
        out.append(msgEl(r.emailed ? `Sent. ${to} will get an email${r.hasAccount ? "" : " inviting them to sign up"}, and the sermon waits in their binder until they add it.` : `Shared. It waits in ${to}'s binder until they add it${r.hasAccount ? "" : " (they need to sign up with that address first)"}.`, true));
        email.value = ""; note.value = ""; drawSent();
      } catch (e) { out.append(msgEl(e.message)); }
      send.disabled = false;
    } },
      el("h2", { id: "sh-title", text: "Share this sermon" }),
      el("p", { class: "hint", style: "margin:0;font-size:14px", text: `They get their own copy of “${cur.title}”, with its manuscript, Scripture, and slides, to read or adapt. Later changes stay with each copy.` }),
      el("div", { class: "field" }, el("label", { for: "sh-email", text: "Their email" }), email),
      el("div", { class: "field" }, el("label", { for: "sh-note", text: "Note" }), note),
      out,
      el("div", { style: "display:flex;gap:8px;justify-content:flex-end" }, el("button", { class: "btn", type: "button", text: "Close", onclick: closeShare }), send),
      list);
    shareEl = el("div", { class: "modal sh-modal", onclick: ev => { if (ev.target === shareEl) closeShare(); } }, form);
    document.body.append(shareEl);
    email.focus();
    drawSent();
  }

  // Sermons shared with this preacher: a card for each, to add it to the binder or decline it.
  let inboxEl = null;
  async function checkInbox() {
    const r = await api("GET", "/api/shares").catch(() => null); if (!r) return;
    if (r.needsConfirm) notice(`${r.needsConfirm === 1 ? "A sermon has" : r.needsConfirm + " sermons have"} been shared with you. Confirm your email address in Account to see ${r.needsConfirm === 1 ? "it" : "them"}.`, "/account", "Open Account");
    if (!inboxEl) { inboxEl = el("div", { class: "sh-inbox", role: "region", "aria-label": "Sermons shared with you" }); document.body.append(inboxEl); }
    inboxEl.replaceChildren(...r.incoming.map(x => {
      const status = el("p", { class: "hint", style: "margin:0" });
      const add = el("button", { class: "btn primary sm", type: "button", text: "Add to my binder" });
      const no = el("button", { class: "btn ghost sm", type: "button", text: "No thanks" });
      const card = el("div", { class: "sh-card" },
        el("div", { class: "sh-k", text: "Shared with you" }),
        el("div", {}, el("b", { text: x.from }), ` shared “${x.title}”.`),
        x.note ? el("p", { class: "sh-note", text: x.note }) : null,
        status, el("div", { class: "sh-btns" }, no, add));
      add.onclick = async () => {
        add.disabled = no.disabled = true; status.textContent = "Adding…";
        try {
          const r = await api("POST", `/api/shares/${x.id}/accept`);
          card.remove();
          const opened = window.claude.hosted.open ? await window.claude.hosted.open(r.sermonId).catch(() => false) : false;
          if (!opened) notice(`“${x.title}” is in your binder. Find it under Open sermon.`);
        } catch (e) { status.textContent = e.message; add.disabled = no.disabled = false; }
      };
      no.onclick = async () => { no.disabled = true; await api("POST", `/api/shares/${x.id}/decline`).catch(() => {}); card.remove(); };
      return card;
    }));
  }

  async function signOut() {
    try { await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }); } catch {}
    forgetLocal();
    try { localStorage.removeItem("pb-hosted-user"); } catch {}
    location.href = "/";
  }

  // ---------- Account and sign out ----------
  addEventListener("DOMContentLoaded", () => {
    const menu = document.getElementById("sermon-menu"); if (!menu) return;
    const icon = d => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
    const ICONS = {
      "Share this sermon…": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/>',
      "Account": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
      "Site admin": '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/>',
      "Sign out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>'
    };
    const item = (text, fn) => { const b = document.createElement("button"); b.type = "button"; b.className = "menu-item"; b.setAttribute("role", "menuitem"); b.innerHTML = icon(ICONS[text] || ""); const t = document.createElement("span"); t.textContent = text; b.append(t); b.onclick = fn; return b; };
    const sep = document.createElement("div"); sep.className = "menu-sep"; sep.setAttribute("role", "separator");
    menu.append(sep, item("Share this sermon…", openShare), item("Account", () => { location.href = "/account"; }));
    if (boot.owner) menu.append(item("Site admin", () => { location.href = "/admin"; }));
    menu.append(item("Sign out", signOut));
    // Sign out beside Settings and Light or dark: in the side column on a computer, in the header on a phone.
    const tools = document.querySelector(".hdr-tools");
    if (tools) {
      const b = document.createElement("button");
      b.className = "icon-btn"; b.id = "btn-signout"; b.type = "button";
      b.setAttribute("aria-label", "Sign out" + (boot.email ? ` (${boot.email})` : "")); b.title = "Sign out" + (boot.email ? ` of ${boot.email}` : "");
      b.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg><span class="tool-l">Sign out</span>';
      b.onclick = signOut;
      tools.append(b);
    }
    const css = document.createElement("style");
    css.textContent = `.sh-modal .modal-card{width:min(520px,100%)}
.sh-modal textarea{width:100%;font:15px/1.45 var(--f-ui)}
.sh-modal input[type=email]{width:100%;height:var(--ctl);background:var(--surface);border:1px solid var(--line);border-radius:var(--r-sm);padding:0 10px;font-size:15px}
.sh-list{display:flex;flex-direction:column;gap:6px;border-top:1px solid var(--line);padding-top:12px}
.sh-list:empty{display:none}
.sh-row{display:flex;gap:6px 12px;align-items:center;flex-wrap:wrap}
.sh-to{font-weight:600;overflow-wrap:anywhere;flex:1 1 12em}
.sh-inbox{position:fixed;right:16px;bottom:16px;z-index:29;display:flex;flex-direction:column;gap:10px;width:min(360px,calc(100vw - 32px))}
.sh-inbox:empty{display:none}
@media (max-width:700px){.sh-inbox{bottom:calc(var(--nav-h,0px) + 76px);right:16px}}
.sh-card{background:var(--surface);color:var(--ink);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:12px;box-shadow:0 12px 32px rgba(0,0,0,.2);padding:14px;display:flex;flex-direction:column;gap:8px;font-size:14.5px}
.sh-k{font:700 11px var(--f-ui);letter-spacing:.09em;text-transform:uppercase;color:var(--accent)}
.sh-note{margin:0;font-family:var(--f-read);color:var(--muted);border-left:2px solid var(--line);padding-left:10px}
.sh-btns{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}`;
    document.head.append(css);
    checkInbox();
    setInterval(checkInbox, 5 * 60000);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") checkInbox(); });
    if (!boot.claude) notice("Claude's help (analysis, suggestions, outlines, slides) needs an Anthropic API key. Add yours in Account.", "/account#claude", "Add a key");
  });
})();
