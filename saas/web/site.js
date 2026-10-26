/* The account pages of sermon.freely.church: sign in and up, password and sign-in links, Account (profile, Anthropic
   key, picture service keys, usage, giving), the owner's admin page, and giving. One small page; the address picks what it shows. */
(() => {
  "use strict";
  const view = document.getElementById("view");
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const params = new URLSearchParams(location.search);

  // ---------- Helpers ----------
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (k === "text") e.textContent = v;
      else if (k === "class") e.className = v;
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : String(k));
    return e;
  }
  async function api(method, url, body) {
    const r = await fetch(url, { method, credentials: "same-origin", headers: body !== undefined ? { "content-type": "application/json" } : {}, body: body !== undefined ? JSON.stringify(body) : undefined });
    let j = null; try { j = await r.json(); } catch {}
    if (!r.ok) throw Object.assign(new Error((j && j.error) || "Something went wrong. Please try again."), { status: r.status, code: j && j.code });
    return j || {};
  }
  const msg = (text, kind = "err") => h("div", { class: "msg " + kind, role: kind === "err" ? "alert" : "status", text });
  function field(label, attrs, hint) {
    const id = attrs.id || "f-" + Math.random().toString(36).slice(2, 8);
    return h("div", { class: "field" }, h("label", { for: id, text: label }), h("input", { ...attrs, id }), hint ? h("div", { class: "hint", text: hint }) : null);
  }
  /** A form whose submit runs `fn` with its values, showing what went wrong above the fields. */
  function form(children, button, fn) {
    const out = h("div");
    const btn = h("button", { class: "btn primary block", type: "submit", text: button });
    const f = h("form", { novalidate: true }, out, children, btn);
    f.addEventListener("submit", async ev => {
      ev.preventDefault();
      out.replaceChildren();
      const vals = Object.fromEntries(new FormData(f));
      btn.disabled = true;
      try { await fn(vals, out); } catch (e) { out.replaceChildren(msg(e.message)); } finally { btn.disabled = false; }
    });
    return f;
  }
  const fill = (el, ...kids) => el.replaceChildren(...kids.flat().filter(k => k != null && k !== false));
  const page = (...kids) => fill(view, ...kids);
  const card = (...kids) => h("div", { class: "card" }, ...kids);
  const next = () => { const n = params.get("next"); return n && /^\/(?![/\\])/.test(n) ? n : "/app"; };
  const money = (cents, cur = "usd") => new Intl.NumberFormat("en-US", { style: "currency", currency: cur.toUpperCase(), minimumFractionDigits: cents % 100 ? 2 : 0 }).format(cents / 100);
  const day = iso => iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "";
  const bytes = n => !n ? "none" : n < 1048576 ? `${Math.max(1, Math.round(n / 1024))} KB` : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1073741824).toFixed(2)} GB`;
  const title = t => { document.title = t ? `${t} · Pulpit Binder` : "Pulpit Binder"; };
  const googleIcon = () => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true"); s.innerHTML = '<path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.2 14.6 2.2 12 2.2 6.6 2.2 2.2 6.6 2.2 12S6.6 21.8 12 21.8c5.8 0 9.6-4 9.6-9.7 0-.7-.1-1.2-.2-1.7H12z"/>'; return s; };

  let me = { user: null, features: {} };

  // ---------- Signing up and in ----------
  const ERRORS = {
    google: "Google sign-in didn't finish. Please try again.",
    "google-email": "Google hasn't confirmed that email address yet. Confirm it with Google, or sign up with email.",
    "google-off": "Google sign-in isn't set up on this server yet.",
    disabled: "This account has been turned off."
  };
  function googleButton(label) {
    if (!me.features.google) return null;
    return h("div", {}, h("a", { class: "btn block", href: "/api/auth/google?next=" + encodeURIComponent(next()) }, googleIcon(), label), h("div", { class: "or", text: "or" }));
  }
  function login() {
    title("Sign in");
    const err = ERRORS[params.get("error")];
    const pw = form([field("Email", { type: "email", name: "email", autocomplete: "email", required: true, value: params.get("email") || null }), field("Password", { type: "password", name: "password", autocomplete: "current-password", required: true })], "Sign in", async v => {
      await api("POST", "/api/auth/login", { email: v.email, password: v.password });
      location.href = next();
    });
    const magic = me.features.email ? h("button", { class: "btn ghost block", type: "button", style: "margin-top:8px", text: "Email me a sign-in link instead", onclick: () => magicLink() }) : null;
    page(h("div", { class: "narrow" }, card(
      h("h1", { text: "Welcome back" }), h("p", { class: "muted", style: "margin-bottom:20px", text: "Sign in to open your binder." }),
      err ? msg(err) : null, googleButton("Continue with Google"), pw, magic,
      h("div", { class: "links" }, h("a", { href: "/register" + location.search, text: "Create an account" }), me.features.email ? h("a", { href: "/forgot", text: "Forgot password?" }) : null)
    )));
  }
  function magicLink() {
    title("Sign-in link");
    const box = h("div");
    const f = form([field("Email", { type: "email", name: "email", autocomplete: "email", required: true })], "Send the link", async v => {
      await api("POST", "/api/auth/magic", { email: v.email });
      box.replaceChildren(msg(`If ${v.email} has an account, a sign-in link is on its way. It works for 20 minutes.`, "ok"));
    });
    page(h("div", { class: "narrow" }, card(h("h1", { text: "Email a sign-in link" }), h("p", { class: "muted", style: "margin-bottom:20px", text: "No password needed: we'll email you a link that signs you in." }), box, f, h("div", { class: "links" }, h("a", { href: "/login", text: "Back to sign in" })))));
  }
  function register() {
    title("Start free");
    const f = form([
      field("Your name", { type: "text", name: "name", autocomplete: "name", required: true }),
      field("Email", { type: "email", name: "email", autocomplete: "email", required: true, value: params.get("email") || null }),
      field("Password", { type: "password", name: "password", autocomplete: "new-password", required: true, minlength: "8" }, "At least 8 characters.")
    ], "Create my binder", async v => {
      await api("POST", "/api/auth/register", { name: v.name, email: v.email, password: v.password });
      location.href = next();
    });
    page(h("div", { class: "narrow" }, card(
      h("h1", { text: "Start your binder" }), h("p", { class: "muted", style: "margin-bottom:20px", text: "Free for every preacher. No card needed." }),
      googleButton("Sign up with Google"), f,
      h("div", { class: "links" }, h("span", {}, "Have an account? ", h("a", { href: "/login" + location.search, text: "Sign in" })))
    )));
  }
  function forgot() {
    title("Forgot password");
    const box = h("div");
    const f = form([field("Email", { type: "email", name: "email", autocomplete: "email", required: true })], "Send a reset link", async v => {
      await api("POST", "/api/auth/forgot", { email: v.email });
      box.replaceChildren(msg(`If ${v.email} has an account, a link to choose a new password is on its way. It works for an hour.`, "ok"));
    });
    page(h("div", { class: "narrow" }, card(h("h1", { text: "Forgot your password?" }), h("p", { class: "muted", style: "margin-bottom:20px", text: "We'll email you a link to choose a new one." }), box, f, h("div", { class: "links" }, h("a", { href: "/login", text: "Back to sign in" })))));
  }
  async function reset(token) {
    title("New password");
    const ok = await api("GET", "/api/auth/reset/" + encodeURIComponent(token)).then(r => r.valid, () => false);
    if (!ok) return page(h("div", { class: "narrow" }, card(h("h1", { text: "This link has expired" }), h("p", { class: "muted", style: "margin-bottom:16px", text: "Reset links work for an hour and only once." }), h("a", { class: "btn primary", href: "/forgot", text: "Send a new link" }))));
    const f = form([field("New password", { type: "password", name: "password", autocomplete: "new-password", required: true, minlength: "8" }, "At least 8 characters.")], "Save and sign in", async v => {
      await api("POST", "/api/auth/reset", { token, password: v.password });
      location.href = "/app";
    });
    page(h("div", { class: "narrow" }, card(h("h1", { text: "Choose a new password" }), f)));
  }
  async function magic(token) {
    title("Sign in");
    const r = await api("GET", `/api/auth/magic/${encodeURIComponent(token)}/peek`).catch(() => ({ valid: false }));
    if (!r.valid) return page(h("div", { class: "narrow" }, card(h("h1", { text: "This link has expired" }), h("p", { class: "muted", style: "margin-bottom:16px", text: "Sign-in links work for 20 minutes and only once." }), h("a", { class: "btn primary", href: "/login", text: "Sign in" }))));
    const f = form([], "Sign in", async () => {
      await api("POST", "/api/auth/magic/" + encodeURIComponent(token));
      location.href = "/app";
    });
    page(h("div", { class: "narrow" }, card(h("h1", { text: "Sign in to Pulpit Binder" }), h("p", { class: "muted", style: "margin-bottom:20px", text: `You're signing in as ${r.email}.` }), f)));
  }
  async function confirmEmail(token) {
    title("Confirm email");
    if (!me.user) return location.replace("/login?next=" + encodeURIComponent(location.pathname));
    try {
      await api("POST", "/api/auth/confirm/" + encodeURIComponent(token));
      page(h("div", { class: "narrow" }, card(h("h1", { text: "Email confirmed" }), h("p", { class: "muted", style: "margin-bottom:16px", text: `${me.user.email} is confirmed.` }), h("a", { class: "btn primary", href: "/account", text: "Back to Account" }))));
    } catch (e) {
      page(h("div", { class: "narrow" }, card(h("h1", { text: "That link didn't work" }), msg(e.message), h("a", { class: "btn", href: "/account", text: "Back to Account" }))));
    }
  }

  // ---------- Account ----------
  async function account() {
    title("Account");
    if (!me.user) return location.replace("/login?next=/account");
    const u = me.user;
    const usage = await api("GET", "/api/account/usage").catch(() => null);

    // Claude
    const claudeBox = h("div");
    const drawClaude = () => {
      const status = u.claude === "own" ? h("span", { class: "status ok", text: `Your key is in (${u.keyHint})` })
        : u.claude === "shared" ? h("span", { class: "status ok", text: "Using the key the site owner shares with you" })
        : h("span", { class: "status warn", text: "No key yet" });
      const keyForm = form([field(u.keyHint ? "Replace your key" : "Your Anthropic API key", { type: "password", name: "key", autocomplete: "off", spellcheck: "false", placeholder: "sk-ant-...", required: true }, "Kept encrypted, and used only for your own requests.")], u.keyHint ? "Save the new key" : "Save my key", async (v, out) => {
        const r = await api("PUT", "/api/account/key", { key: v.key.trim() });
        u.keyHint = r.keyHint; u.claude = "own"; drawClaude();
        claudeBox.prepend(msg("Your key is saved. Claude's help is ready in your binder.", "ok"));
      });
      const remove = u.keyHint ? h("button", { class: "btn danger", type: "button", text: "Remove my key", onclick: async () => {
        if (!confirm("Remove your Anthropic key from Pulpit Binder?")) return;
        await api("DELETE", "/api/account/key"); u.keyHint = null; u.claude = u.sharedKey ? "shared" : null; drawClaude();
      } }) : null;
      fill(claudeBox,
        h("div", { class: "row", style: "margin-bottom:14px" }, status),
        u.claude === "shared" && !u.keyHint ? h("p", { class: "muted small", style: "margin-bottom:14px", text: "Your requests use the site owner's key for now. Add your own key any time; yours is used whenever it is in." }) : null,
        !u.keyHint ? h("ol", { class: "steps" },
          h("li", {}, "Open the ", h("a", { href: "https://console.anthropic.com/settings/keys", target: "_blank", rel: "noopener", text: "Anthropic Console" }), " and sign up or sign in."),
          h("li", { text: "Add a little credit under Billing (five dollars lasts most preachers months)." }),
          h("li", { text: "Create a key under API keys, copy it, and paste it here." })) : null,
        keyForm, remove ? h("div", { style: "margin-top:10px" }, remove) : null
      );
    };
    drawClaude();
    const usageTable = usage && usage.claude.length ? h("div", { class: "table-wrap", style: "margin-top:18px" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", { text: "Model" }), h("th", { text: "Key" }), h("th", { class: "num", text: "Requests" }), h("th", { class: "num", text: "Tokens in" }), h("th", { class: "num", text: "Tokens out" }))),
      h("tbody", {}, usage.claude.map(r => h("tr", {}, h("td", { text: r.model }), h("td", { text: r.source === "own" ? "Yours" : "Shared" }), h("td", { class: "num", text: r.requests }), h("td", { class: "num", text: (r.input || 0).toLocaleString() }), h("td", { class: "num", text: (r.output || 0).toLocaleString() })))))) : null;

    // Pictures: a key for any of these paints Illustration slides and slide theme header pictures.
    const PICTURES = [
      { id: "openai", name: "OpenAI", fields: [["key", "OpenAI API key", "sk-..."]], link: "https://platform.openai.com/api-keys", where: "the OpenAI Platform", steps: "Create a key under API keys, and add a little credit under Billing." },
      { id: "google", name: "Google Gemini (Nano Banana)", fields: [["key", "Gemini API key", "AIza..."]], link: "https://aistudio.google.com/apikey", where: "Google AI Studio", steps: "Create an API key and copy it." },
      { id: "stability", name: "Stability AI", fields: [["key", "Stability AI API key", "sk-..."]], link: "https://platform.stability.ai/dashboard/api-keys", where: "the Stability AI Platform", steps: "Copy your API key, and buy a few credits under Billing." },
      { id: "firefly", name: "Adobe Firefly", fields: [["clientId", "Client ID", ""], ["clientSecret", "Client secret", "p8e-..."]], link: "https://developer.adobe.com/console", where: "the Adobe Developer Console", steps: "Create a project, add the Firefly API with OAuth Server-to-Server, and copy its client ID and secret. Firefly's API comes with Adobe Firefly Services, which a regular Creative Cloud plan may not include." }
    ];
    const keys = { ...(u.imageKeys || {}) };
    const picBox = h("div");
    const drawPictures = () => fill(picBox, PICTURES.map((p, i) => {
      const hint = keys[p.id];
      const keyForm = form(p.fields.map(([name, label, ph]) => field(label, { type: "password", name, autocomplete: "off", spellcheck: "false", placeholder: ph || null, required: true })), hint ? "Save the new key" : "Save", async (v) => {
        const r = await api("PUT", "/api/account/image-key/" + p.id, Object.fromEntries(p.fields.map(([name]) => [name, (v[name] || "").trim()])));
        keys[p.id] = r.hint; drawPictures();
        document.getElementById("pic-" + p.id).append(msg(`Your ${p.name} key is saved. Choose ${p.name} under Pictures in your binder's Settings, AI and images.`, "ok"));
      });
      const remove = hint ? h("button", { class: "btn danger", type: "button", text: "Remove", onclick: async () => {
        if (!confirm(`Remove your ${p.name} key from Pulpit Binder?`)) return;
        await api("DELETE", "/api/account/image-key/" + p.id); delete keys[p.id]; drawPictures();
      } }) : null;
      return h("div", { id: "pic-" + p.id, style: i ? "border-top:1px solid var(--line);padding-top:18px;margin-top:18px" : null },
        h("div", { class: "row", style: "justify-content:space-between;margin-bottom:10px" }, h("b", { text: p.name }),
          hint ? h("span", { class: "status ok", text: `Key in (${hint})` }) : h("span", { class: "status", text: "No key" })),
        hint ? h("details", {}, h("summary", { class: "muted small", style: "cursor:pointer", text: "Replace or remove this key" }), h("div", { style: "margin-top:12px" }, keyForm, h("div", { style: "margin-top:10px" }, remove)))
          : h("div", {}, h("p", { class: "muted small", style: "margin-bottom:12px" }, "Open ", h("a", { href: p.link, target: "_blank", rel: "noopener", text: p.where }), ". " + p.steps), keyForm));
    }));
    drawPictures();
    const picCount = usage && usage.pictures ? usage.pictures.reduce((a, r) => a + r.requests, 0) : 0;

    // Profile
    const profile = form([
      field("Name", { type: "text", name: "name", value: u.name, autocomplete: "name", required: true }, "Used as the speaker on new sermons."),
      field("Email", { type: "email", name: "email", value: u.email, autocomplete: "email", required: true })
    ], "Save", async (v, out) => {
      await api("PATCH", "/api/auth/profile", { name: v.name, email: v.email });
      out.replaceChildren(msg("Saved.", "ok"));
      if (v.email.toLowerCase() !== u.email.toLowerCase()) setTimeout(() => location.reload(), 600);
    });
    const confirmBtn = !u.emailVerified && me.features.email ? h("button", { class: "btn", type: "button", text: "Confirm my email", onclick: async ev => {
      ev.target.disabled = true;
      try { await api("POST", "/api/auth/confirm"); ev.target.replaceWith(msg(`A link is on its way to ${u.email}.`, "ok")); } catch (e) { ev.target.replaceWith(msg(e.message)); }
    } }) : null;

    // Password
    const pwForm = form([
      u.hasPassword ? field("Current password", { type: "password", name: "currentPassword", autocomplete: "current-password" }) : null,
      field(u.hasPassword ? "New password" : "Set a password", { type: "password", name: "newPassword", autocomplete: "new-password", minlength: "8" }, u.hasPassword ? null : "You sign in with Google or emailed links now. A password is optional.")
    ], u.hasPassword ? "Change password" : "Set password", async (v, out) => {
      await api("POST", "/api/auth/password", { currentPassword: v.currentPassword || undefined, newPassword: v.newPassword });
      out.replaceChildren(msg("Password saved. Other devices were signed out.", "ok"));
    });

    // Giving
    const giving = h("div");
    if (me.features.support) {
      api("GET", "/api/support/mine").then(r => {
        const subs = (r.subscriptions || []).filter(s => s.status !== "canceled");
        giving.replaceChildren(card(h("h2", { text: "Giving" }),
          subs.length ? h("div", {}, h("p", { class: "muted", style: "margin-bottom:12px", text: "Thank you for supporting Pulpit Binder." }), ...subs.map(s => h("div", { class: "row", style: "justify-content:space-between;margin-bottom:8px" },
            h("span", {}, h("b", { text: `${money(s.amount, s.currency)} a month` }), s.cancelAtPeriodEnd ? h("span", { class: "muted", text: ` · ends ${day(s.currentPeriodEnd)}` }) : null),
            h("button", { class: "btn", type: "button", text: "Change or cancel", onclick: async () => { location.href = (await api("POST", "/api/support/mine/portal", { subscriptionId: s.id })).url; } }))))
            : h("p", { class: "muted", style: "margin-bottom:14px", text: "Pulpit Binder is free. If you are able, a gift helps keep it that way for every preacher." }),
          h("a", { class: "btn primary", href: "/support", text: subs.length ? "Give again" : "Give" })));
      }).catch(() => {});
    }

    // Delete
    const delForm = form([u.hasPassword ? field("Password", { type: "password", name: "password", autocomplete: "current-password" }) : field("Type your email address to confirm", { type: "email", name: "confirm", autocomplete: "off" })], "Delete my account and sermons", async v => {
      if (!confirm("This deletes your account, every sermon, slide, and recording kept here. It can't be undone.")) return;
      await api("DELETE", "/api/auth/account", v);
      try { indexedDB.deleteDatabase("pulpit-binder"); for (const k of Object.keys(localStorage)) if (k.startsWith("pb-")) localStorage.removeItem(k); } catch {}
      location.href = "/";
    });
    delForm.querySelector("button[type=submit]").className = "btn danger block";

    page(h("div", { class: "page" },
      h("div", { class: "row", style: "justify-content:space-between" }, h("h1", { style: "font-size:32px", text: "Account" }), h("div", { class: "row" },
        u.isOwner ? h("a", { class: "btn", href: "/admin", text: "Site admin" }) : null,
        h("button", { class: "btn", type: "button", text: "Sign out", onclick: signOut }))),
      u.ownerNeedsConfirmation ? msg("This is the site owner's address. Confirm it below to open the admin page.", "ok") : null,
      card(h("h2", { id: "claude", text: "Claude" }), h("p", { class: "muted", style: "margin-bottom:16px", text: "Claude's help in your binder (analysis, suggestions, outlines, slide drafts, passage text) runs on your own Anthropic API key. Anthropic bills you directly for what you use." }), claudeBox,
        usage ? h("p", { class: "muted small", style: "margin-top:18px", text: `Last 30 days: ${usage.claude.reduce((a, r) => a + r.requests, 0)} Claude requests.` }) : null, usageTable),
      card(h("h2", { id: "pictures", text: "Pictures" }), h("p", { class: "muted", style: "margin-bottom:16px", text: "Add a key for any of these to paint Illustration slides and slide theme header pictures with it, then choose it under Pictures in your binder's Settings. Each company bills you directly. Keys are kept encrypted and used only for your own pictures." }), picBox,
        picCount ? h("p", { class: "muted small", style: "margin-top:18px", text: `Last 30 days: ${picCount} picture${picCount === 1 ? "" : "s"}.` }) : null),
      card(h("h2", { text: "Your binder" }), usage ? h("p", { class: "muted", text: `${usage.sermons} sermon${usage.sermons === 1 ? "" : "s"} synced. Files: ${bytes(usage.storage.used)} of ${bytes(usage.storage.limit)}.` }) : null,
        h("div", { class: "row", style: "margin-top:14px" }, h("a", { class: "btn primary", href: "/app", text: "Open my binder" }))),
      card(h("h2", { text: "Profile" }), profile, confirmBtn ? h("div", { style: "margin-top:12px" }, confirmBtn) : null),
      card(h("h2", { text: "Password" }), pwForm),
      giving,
      card(h("h2", { text: "Delete account" }), h("p", { class: "muted", style: "margin-bottom:16px", text: "Removes your account and everything kept here. Copies already saved on your own devices stay there." }), delForm)
    ));
    if (location.hash) document.querySelector(location.hash)?.scrollIntoView();
  }

  // ---------- Site admin (the owner) ----------
  async function admin() {
    title("Site admin");
    if (!me.user) return location.replace("/login?next=/admin");
    if (!me.user.isOwner) return page(h("div", { class: "narrow" }, card(h("h1", { text: "Site admin" }), msg(me.user.ownerNeedsConfirmation ? "Confirm your email in Account first." : "Only the site owner can open this page."), h("a", { class: "btn", href: "/account", text: "Account" }))));
    let data;
    const box = h("div");
    const filter = h("input", { type: "search", placeholder: "Find by name or email", "aria-label": "Find a preacher", oninput: () => draw() });
    const load = async () => { data = await api("GET", "/api/admin/users"); draw(); };
    const toggle = (u, key, label) => h("label", { class: "switch" }, h("input", { type: "checkbox", checked: u[key], disabled: key === "sharedKey" && !data.sharedKeyConfigured, onchange: async ev => {
      try { await api("PATCH", "/api/admin/users/" + u.id, { [key]: ev.target.checked }); u[key] = ev.target.checked; draw(); } catch (e) { ev.target.checked = !ev.target.checked; alert(e.message); }
    } }), label);
    const draw = () => {
      const q = filter.value.trim().toLowerCase();
      const rows = data.users.filter(u => !q || u.email.toLowerCase().includes(q) || (u.name || "").toLowerCase().includes(q));
      const shared = data.users.filter(u => u.sharedKey);
      fill(box,
        h("div", { class: "row", style: "gap:24px;margin-bottom:16px" },
          h("span", {}, h("b", { text: data.users.length }), " preachers"),
          h("span", {}, h("b", { text: shared.length }), " on the shared key"),
          h("span", {}, h("b", { text: `$${shared.reduce((a, u) => a + u.sharedCost30, 0).toFixed(2)}` }), " shared key, last 30 days"),
          h("span", {}, h("b", { text: money(data.giving30.total) }), ` given, last 30 days (${data.giving30.payments})`)),
        data.sharedKeyConfigured ? null : msg("No shared key is set. Add ANTHROPIC_API_KEY to the server's environment to lend Claude to preachers you choose.", "ok"),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", { text: "Preacher" }), h("th", { text: "Joined" }), h("th", { class: "num", text: "Sermons" }), h("th", { class: "num", text: "Files" }), h("th", { text: "Claude" }), h("th", { class: "num", text: "Requests (30 days)" }), h("th", { text: "Shared key" }), h("th", { text: "Turned off" }))),
          h("tbody", {}, rows.map(u => h("tr", {},
            h("td", {}, h("b", { text: u.name || "(no name)" }), h("div", { class: "muted", text: u.email + (u.verified ? "" : " (unconfirmed)") }), u.supporter ? h("div", { class: "status ok", style: "margin-top:4px", text: "Gives monthly" }) : null),
            h("td", { text: day(u.createdAt) }),
            h("td", { class: "num", text: u.sermons }),
            h("td", { class: "num", text: u.storage ? bytes(u.storage) : "" }),
            h("td", { text: u.ownKey ? "Own key" : u.sharedKey ? "Shared" : "None" }),
            h("td", { class: "num", text: u.requests30 ? `${u.requests30}${u.sharedRequests30 ? ` (${u.sharedRequests30} shared, $${u.sharedCost30.toFixed(2)})` : ""}` : "" }),
            h("td", {}, toggle(u, "sharedKey", "Lend")),
            h("td", {}, u.id === me.user.id ? null : toggle(u, "disabled", "Off")))))))
      );
    };
    page(h("div", { class: "page wide" }, h("h1", { style: "font-size:32px", text: "Site admin" }),
      card(h("h2", { text: "Preachers" }), h("p", { class: "muted", style: "margin-bottom:14px", text: "Lend your Anthropic key to the preachers you choose. Their own key, when they add one, is always used first. Costs are estimates at list prices." }), h("div", { class: "field" }, filter), box)));
    await load();
  }

  // ---------- Giving ----------
  async function support() {
    title("Give");
    const cfg = await api("GET", "/api/support/config").catch(() => ({ enabled: false }));
    if (!cfg.enabled) return page(h("div", { class: "narrow" }, card(h("h1", { text: "Giving" }), h("p", { class: "muted", text: "Online giving isn't set up yet. Thank you for thinking of it." }))));
    let amount = 2500, monthly = false;
    const presets = [1000, 2500, 5000, 10000];
    const other = h("input", { type: "text", inputmode: "decimal", placeholder: "Other amount", "aria-label": "Other amount in dollars", oninput: () => { amounts.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", "false")); } });
    const amounts = h("div", { class: "amounts" }, presets.map(c => h("button", { type: "button", "aria-pressed": String(c === amount), text: money(c), onclick: ev => { amount = c; other.value = ""; amounts.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b === ev.target))); } })));
    const seg = h("div", { class: "seg", role: "group", "aria-label": "How often" }, [["Once", false], ["Monthly", true]].map(([t, m]) => h("button", { type: "button", "aria-pressed": String(m === monthly), text: t, onclick: ev => { monthly = m; seg.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b === ev.target))); } })));
    const out = h("div");
    const go = h("button", { class: "btn primary block big", type: "button", text: "Continue to payment", onclick: async () => {
      out.replaceChildren();
      let cents = amount;
      if (other.value.trim()) { const s = other.value.replace(/[$,\s]/g, ""); if (!/^\d+(\.\d{1,2})?$/.test(s)) { out.append(msg("Enter an amount in dollars, like 20 or 12.50.")); return; } cents = Math.round(Number(s) * 100); }
      go.disabled = true;
      try { location.href = (await api("POST", "/api/support/checkout", { amount: cents, frequency: monthly ? "monthly" : "once" })).url; } catch (e) { out.append(msg(e.message)); go.disabled = false; }
    } });
    page(h("div", { class: "narrow" }, card(
      h("h1", { text: "Give to Pulpit Binder" }),
      h("p", { class: "muted", style: "margin-bottom:20px", text: "Pulpit Binder is free for every preacher. Gifts pay for the server, storage, and backups, and the time to keep improving it." }),
      cfg.sandbox ? msg("Test mode: no real money moves.", "ok") : null,
      seg, amounts, h("div", { class: "field" }, other), out, go,
      h("p", { class: "hint", style: "margin-top:14px", text: "Payments are handled securely by Stripe." }),
      h("div", { class: "links" }, h("a", { href: "/support/manage", text: "Change or cancel monthly giving" }))
    )));
  }
  async function supportThanks() {
    title("Thank you");
    const id = params.get("session_id") || "";
    const s = await api("GET", "/api/support/session/" + encodeURIComponent(id)).catch(() => null);
    page(h("div", { class: "narrow" }, card(h("h1", { text: "Thank you" }),
      h("p", { class: "muted", style: "margin-bottom:16px", text: s ? (s.monthly ? `Your ${money(s.amount, s.currency)} a month helps keep Pulpit Binder free for every preacher.` : `Your gift of ${money(s.amount, s.currency)} helps keep Pulpit Binder free for every preacher.`) + (s.paid ? "" : " Your bank payment is on its way; Stripe will email when it clears.") : "Your gift helps keep Pulpit Binder free for every preacher." }),
      h("a", { class: "btn primary", href: me.user ? "/app" : "/", text: me.user ? "Back to my binder" : "Back home" }))));
  }
  async function supportManage(token) {
    title("Monthly giving");
    if (!token) {
      const box = h("div");
      const f = form([field("Email you give from", { type: "email", name: "email", autocomplete: "email", required: true })], "Email me a link", async v => {
        await api("POST", "/api/support/manage", { email: v.email });
        box.replaceChildren(msg(`If ${v.email} gives monthly, a link to manage it is on its way.`, "ok"));
      });
      return page(h("div", { class: "narrow" }, card(h("h1", { text: "Change or cancel monthly giving" }), h("p", { class: "muted", style: "margin-bottom:20px", text: "We'll email a link to the address your giving was set up with." }), box, f)));
    }
    const r = await api("GET", "/api/support/manage/" + encodeURIComponent(token)).catch(() => ({ valid: false }));
    if (!r.valid) return page(h("div", { class: "narrow" }, card(h("h1", { text: "This link has expired" }), h("a", { class: "btn primary", href: "/support/manage", text: "Ask for a new link" }))));
    const subs = r.subscriptions.filter(s => s.status !== "canceled");
    page(h("div", { class: "narrow" }, card(h("h1", { text: "Monthly giving" }), h("p", { class: "muted", style: "margin-bottom:16px", text: r.email }),
      subs.length ? subs.map(s => h("div", { class: "row", style: "justify-content:space-between;margin-bottom:8px" }, h("b", { text: `${money(s.amount, s.currency)} a month` }),
        h("button", { class: "btn", type: "button", text: "Change or cancel", onclick: async () => { location.href = (await api("POST", `/api/support/manage/${encodeURIComponent(token)}/portal`, { subscriptionId: s.id })).url; } })))
        : h("p", { text: "There is no monthly giving on this address now." }))));
  }

  function notFoundPage() {
    title("Not found");
    page(h("div", { class: "narrow" }, card(h("h1", { text: "Page not found" }), h("p", { class: "muted", style: "margin-bottom:16px", text: "That address isn't part of Pulpit Binder." }), h("a", { class: "btn primary", href: "/", text: "Go home" }))));
  }

  async function signOut() {
    await api("POST", "/api/auth/logout").catch(() => {});
    try { indexedDB.deleteDatabase("pulpit-binder"); for (const k of Object.keys(localStorage)) if (k.startsWith("pb-") && !["pb-theme", "pb-read", "pb-follow"].includes(k)) localStorage.removeItem(k); } catch {}
    location.href = "/";
  }
  document.getElementById("signout")?.addEventListener("click", signOut);

  // ---------- Route ----------
  (async () => {
    me = await api("GET", "/api/auth/me").catch(() => ({ user: null, features: {} }));
    const seg = path.split("/");
    if ((path === "/login" || path === "/register") && me.user) return location.replace(next());
    if (path === "/login") return login();
    if (path === "/register") return register();
    if (path === "/forgot") return forgot();
    if (seg[1] === "reset" && seg[2]) return reset(seg[2]);
    if (seg[1] === "magic" && seg[2]) return magic(seg[2]);
    if (seg[1] === "confirm" && seg[2]) return confirmEmail(seg[2]);
    if (path === "/account") return account();
    if (path === "/admin") return admin();
    if (path === "/support") return support();
    if (path === "/support/thanks") return supportThanks();
    if (path === "/support/manage") return supportManage(null);
    if (seg[1] === "support" && seg[2] === "manage" && seg[3]) return supportManage(seg[3]);
    notFoundPage();
  })();
})();
