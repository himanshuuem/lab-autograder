"use strict";
/* Lab Grader dashboard: plain JS, no build step. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 1) => (n === null || n === undefined ? "–" : (+n).toFixed(d).replace(/\.0+$/, ""));
const view = () => $("#view");

let state = { courses: [], poll: null, me: null };

// ------------------------------------------------------------------ api
async function api(path, opts = {}) {
  const init = { credentials: "same-origin", ...opts, headers: { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) } };
  if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
  const r = await fetch("/api" + path, init);
  if (r.status === 401 && path !== "/login") { showLogin(); throw new Error("Sign in to continue"); }
  if (r.status === 403 && state.me && state.me.status !== "active") { showPending(); throw new Error("Waiting for approval"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const d = data && data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : `Request failed (${r.status})`);
  }
  return data;
}

let toastTimer;
function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), bad ? 7000 : 3500);
}

// ------------------------------------------------------------------ motion
const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
// staggered entrance for a freshly rendered view; the class is dropped afterwards so sticky/fixed children behave
function enter(root) {
  const items = $$(":scope > *:not(#job):not(#tab):not(#programs), #tab > *:not(.summary), .summary > *, #programs > *", root);
  items.forEach((el, i) => {
    el.style.setProperty("--i", Math.min(i, 10));
    el.classList.add("enter");
    el.addEventListener("animationend", (e) => { if (e.target === el) el.classList.remove("enter"); });
  });
}
// numbers in [data-count] roll up to their value
function countUp(root) {
  $$("[data-count]", root).forEach((el) => {
    const to = +el.dataset.count, dec = +(el.dataset.dec || 0);
    if (calm() || !isFinite(to) || to === 0) return;
    const t0 = performance.now(), dur = 750;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(to * e, dec);
      if (k < 1) requestAnimationFrame(step);
    };
    el.textContent = fmt(0, dec);
    requestAnimationFrame(step);
  });
}
// the highlight in the sidebar slides from the last assignment to the current one
function placePill() {
  const nav = $("#courses"), on = $(".nav-a.on", nav);
  if (!on) { nav.classList.remove("has-pill"); state.pill = null; return; }
  const pill = document.createElement("span");
  pill.className = "nav-pill";
  pill.setAttribute("aria-hidden", "true");
  nav.prepend(pill);
  nav.classList.add("has-pill");
  const put = (p) => { pill.style.transform = `translateY(${p.top}px)`; pill.style.height = p.height + "px"; };
  const to = { top: on.offsetTop, height: on.offsetHeight };
  if (state.pill && !calm()) {
    pill.style.transition = "none";
    put(state.pill);
    pill.getBoundingClientRect();
    pill.style.transition = "";
  }
  put(to);
  state.pill = to;
}

async function act(btn, fn) {
  const label = btn ? btn.innerHTML : "";    // the button may hold an icon
  if (btn) { btn.disabled = true; }
  try { return await fn(); }
  catch (e) { toast(e.message, true); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = label; } }
}

// ------------------------------------------------------------------ icons
const svg = (d, n = 16) => `<svg width="${n}" height="${n}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICON = {
  search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
  chevron: svg('<path d="m9 18 6-6-6-6"/>'),
  updown: svg('<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>', 14),
  calendar: svg('<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>', 13),
  users: svg('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>', 13),
  book: svg('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M8 7h8M8 11h6"/>', 20),
  file: svg('<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'),
  home: svg('<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>'),
  pulse: svg('<path d="M3 12h4l3-8 4 16 3-8h4"/>'),
  shield: svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'),
  refresh: svg('<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/>'),
  panel: svg('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>'),
  out: svg('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>'),
  inbox: svg('<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>', 14),
  check: svg('<path d="M20 6 9 17l-5-5"/>', 14),
  sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
  moon: svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
};

// ------------------------------------------------------------------ vocabulary
const FLAGS = {
  NOT_SUBMITTED: ["Not submitted", ""],
  LATE: ["Late", "blue"],
  MISSING_QUESTION: ["missing", "red"],
  COMPILE_ERROR: ["doesn't compile", "red"],
  POSSIBLE_FABRICATED_OUTPUT: ["shown output not produced by code", "mark"],
  OCR_USED: ["Scanned PDF", "mark"],
  EXTRACTION_REVIEW: ["check extracted code", "mark"],
  UNKNOWN_LANGUAGE: ["language unknown", "mark"],
  NO_TESTS: ["no tests", ""],
  SIMILAR_CODE: ["similar code", "mark"],
  SANDBOX_ERROR: ["Sandbox error", "red"],
  NOT_PDF: ["Not a PDF", "red"],
  UNREADABLE_FILE: ["File can't be read", "red"],
  FILE_SKIPPED: ["A file was skipped", "mark"],
  EARLIER_COPY: ["Earlier download used", "blue"],
  UNREADABLE_PDF: ["Unreadable PDF", "red"],
  NO_CODE: ["No code found", "red"],
};
function flagChip(f) {
  const [text, cls] = FLAGS[f.code] || [f.code, ""];
  const label = f.q && !["NO_TESTS"].includes(f.code) ? `Q${f.q} ${text}` : f.q && f.code === "NO_TESTS" ? `Q${f.q} has no tests` : text;
  return `<span class="flag ${cls}" title="${esc(f.msg)}">${esc(label)}</span>`;
}
const REPAIRS = {
  smart_quote: "curly quotes straightened", dash: "dashes fixed", special_space: "special spaces fixed",
  ligature: "ligatures expanded", symbol: "symbols converted", zero_width_char: "invisible characters removed",
  header_footer_removed: "page headers/footers removed", line_number_removed: "line numbers removed",
  auto_capital_fixed: "auto-capitalised keywords fixed", indentation_rebuilt: "indentation rebuilt",
  wrapped_line_joined: "lines broken by the page width rejoined", imports_moved: "imports moved to the top",
  outside_class_removed: "text outside any class removed",
};
const repairText = (r) => Object.entries(r || {}).map(([k, v]) => `${REPAIRS[k] || k} (${v})`).join(", ");
const STATUS_TEXT = { OK: "Wrong answer", TLE: "Time limit exceeded", MLE: "Memory limit exceeded", RUNTIME_ERROR: "Crashed",
  OUTPUT_LIMIT: "Too much output", NOT_RUN: "Not run", SANDBOX_ERROR: "Sandbox error" };
const LANG = { python: "Python", c: "C", cpp: "C++", java: "Java" };
const KIND = { pdf: "PDF", office: "Office document", image: "image", text: "text file", notebook: "Jupyter notebook", zip: "ZIP archive" };

// ------------------------------------------------------------------ auth
async function showLogin(err = "") {
  $("#app").classList.add("hidden");
  $("#pending").classList.add("hidden");
  $("#login").classList.remove("hidden");
  let cfg = { google: false, local: true, domain: "" };
  try { cfg = await (await fetch("/api/auth/config")).json(); } catch { /* offline: show the form */ }
  $("#google-signin").classList.toggle("hidden", !cfg.google);
  $("#local-login").classList.toggle("hidden", !cfg.local);
  $("#local-login").open = cfg.local && !cfg.google;
  $("#login-lede").textContent = cfg.google
    ? `Sign in with your ${cfg.domain ? "@" + cfg.domain : "college"} Google account to grade your Classroom assignments.`
    : "Sign in to grade your Classroom assignments.";
  $("#login-err").textContent = err;
}
function showPending() {
  $("#app").classList.add("hidden");
  $("#login").classList.add("hidden");
  $("#pending").classList.remove("hidden");
  $("#pending-email").textContent = state.me ? state.me.email : "";
}
async function signOut(e) {
  e && e.preventDefault();
  await api("/logout", { method: "POST" });
  state.me = null;
  showLogin();
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/login", { method: "POST", body: { username: f.get("username"), password: f.get("password") } });
    $("#login").classList.add("hidden");
    boot();
  } catch (err) { $("#login-err").textContent = err.message; }
});
$("#logout").addEventListener("click", signOut);
$("#pending-out").addEventListener("click", signOut);
$("#pending-reload").addEventListener("click", () => location.reload());
function renderMe() {
  const m = state.me;
  $("#me").innerHTML = `<span class="av">${m.picture ? `<img src="${esc(m.picture)}" alt="" referrerpolicy="no-referrer">`
    : `<span class="avatar">${esc((m.name || m.email)[0].toUpperCase())}</span>`}</span>
    <span class="who"><b title="${esc(m.email)}">${esc(m.name || m.email)}${m.role === "admin" ? ` <span class="role">admin</span>` : ""}</b>
    <span id="me-status">${esc(state.svc || "Checking services")}</span></span>${ICON.updown}`;
  $("#me").setAttribute("aria-label", `Account: ${m.name || m.email}`);
  $("#me-mail").textContent = m.email;
  $("#admin-link").classList.toggle("hidden", m.role !== "admin");
}
// the account popover above the profile card
function setMenu(open) {
  $("#menu").classList.toggle("open", open);
  $("#me").setAttribute("aria-expanded", String(open));
}
$("#me").addEventListener("click", (e) => { e.stopPropagation(); setMenu(!$("#menu").classList.contains("open")); });
document.addEventListener("click", (e) => { if (!e.target.closest("#menu")) setMenu(false); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#menu").classList.contains("open")) { setMenu(false); $("#me").focus(); } });
$("#menu").addEventListener("click", (e) => { if (e.target.closest(".mi")) setMenu(false); });
async function refreshAdminCount() {
  if (!state.me || state.me.role !== "admin") return;
  try {
    const n = (await api("/admin/users")).filter((u) => u.status === "pending").length;
    $("#admin-count").textContent = n;
    $("#admin-count").classList.toggle("hidden", !n);
  } catch { /* not fatal */ }
}

// ------------------------------------------------------------------ sidebar
async function loadCourses() {
  state.courses = await api("/courses");
  renderSidebar();
}
function renderSidebar() {
  const cur = location.hash;
  $("#courses").innerHTML = state.courses.length ? state.courses.map((c) => `
    <div class="course-name ${c.assignments.some((a) => cur.startsWith(`#/a/${a.id}`)) ? "on" : ""}">${esc(c.name)}</div>
    ${c.section ? `<div class="course-sec">${esc(c.section)}</div>` : ""}
    ${c.assignments.map((a) => `<a class="nav-a ${cur.startsWith(`#/a/${a.id}`) ? "on" : ""}" href="#/a/${a.id}">
      ${esc(a.title)}<span class="due">${a.due ? "Due " + esc(dueText(a.due)) : "No due date"}${a.graded ? "" : ", not graded yet"}</span></a>`).join("")
      || `<div class="course-sec">No assignments</div>`}`).join("")
    : `<p class="muted small" style="padding:10px">No courses yet. Refresh from Classroom to load them.</p>`;
  placePill();
}
$("#sync").addEventListener("click", (e) => act(e.currentTarget, async () => {
  const b = $("#sync");
  b.classList.add("busy");
  $("span", b).textContent = "Refreshing…";
  try { await api("/courses/sync", { method: "POST" }); } finally { b.classList.remove("busy"); }
  await loadCourses();
  toast("Courses and assignments updated from Classroom.");
  if (!location.hash || location.hash === "#/") render();
}));

async function checkServices() {
  const el = $("#svc");
  let ok = false;
  try {
    const s = await api("/status");
    ok = s.classroom.ok && s.sandbox.ok;
    state.svc = ok ? `Connected${s.classroom.mode === "demo" ? " (demo classroom)" : ""}` : "A service needs attention";
  } catch { state.svc = "Status unavailable"; }
  el.innerHTML = `<span class="dot ${ok ? "ok" : "bad"}"></span>${esc(state.svc)}`;
  $("#profile").dataset.ok = ok ? "1" : "0";
  const st = $("#me-status");
  if (st) st.textContent = state.svc;
}

// ------------------------------------------------------------------ collapsible sidebar
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode: not remembered */ } },
};
const wide = matchMedia("(min-width: 981px)");
function applyCollapse() {
  const on = wide.matches && store.get("lg-collapsed") === "1";
  $("#app").classList.toggle("collapsed", on);
  const b = $("#collapse");
  b.setAttribute("aria-pressed", String(on));
  b.dataset.tip = on ? "Expand sidebar" : "Collapse sidebar";
  b.setAttribute("aria-label", b.dataset.tip);
}
$("#collapse").addEventListener("click", () => {
  store.set("lg-collapsed", store.get("lg-collapsed") === "1" ? "0" : "1");
  applyCollapse();
  placePill();
});
wide.addEventListener("change", applyCollapse);
applyCollapse();

// ------------------------------------------------------------------ theme: system / light / dark
function setTheme(t) {
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  store.set("lg-theme", t);
  $$("[data-theme-pick]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.themePick === t)));
}
setTheme(store.get("lg-theme") || "system");
$$("[data-theme-pick]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); setTheme(b.dataset.themePick); }));

// ------------------------------------------------------------------ command palette (⌘K / Ctrl+K)
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
$("#cmdk-key").textContent = isMac ? "⌘K" : "Ctrl K";
$("#open-cmdk").dataset.tip = `Search (${isMac ? "⌘K" : "Ctrl K"})`;
const cmdk = { items: [], shown: [], at: 0, back: null };
function cmdkItems() {
  const go = (h) => () => (location.hash = h);
  const items = [];
  state.courses.forEach((c) => c.assignments.forEach((a) => items.push({
    group: "Assignments", icon: ICON.file, title: a.title, sub: c.name,
    hint: a.to_review ? `${a.to_review} to review` : "", run: go(`#/a/${a.id}`) })));
  items.push({ group: "Pages", icon: ICON.home, title: "Assignments overview", run: go("#/") });
  items.push({ group: "Pages", icon: ICON.pulse, title: "Service status", run: go("#/status") });
  if (state.me && state.me.role === "admin") items.push({ group: "Pages", icon: ICON.shield, title: "Admin", run: go("#/admin") });
  items.push({ group: "Actions", icon: ICON.refresh, title: "Refresh from Classroom", run: () => $("#sync").click() });
  items.push({ group: "Actions", icon: ICON.panel, title: "Collapse or expand the sidebar", run: () => $("#collapse").click() });
  const dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  items.push({ group: "Actions", icon: dark ? ICON.sun : ICON.moon, title: dark ? "Switch to light theme" : "Switch to dark theme", run: () => setTheme(dark ? "light" : "dark") });
  if (document.documentElement.dataset.theme) items.push({ group: "Actions", icon: ICON.panel, title: "Use the system theme", run: () => setTheme("system") });
  items.push({ group: "Actions", icon: ICON.out, title: "Sign out", run: () => signOut() });
  return items;
}
function cmdkDraw() {
  const words = $("#cmdk-q").value.toLowerCase().split(/\s+/).filter(Boolean);
  const hay = (it) => `${it.title} ${it.sub || ""} ${it.group}`.toLowerCase();
  cmdk.shown = cmdk.items.filter((it) => words.every((w) => hay(it).includes(w)));
  if (words.length) cmdk.shown.sort((x, y) => (y.title.toLowerCase().startsWith(words[0]) - x.title.toLowerCase().startsWith(words[0])));
  cmdk.at = Math.min(cmdk.at, Math.max(0, cmdk.shown.length - 1));
  let last = "";
  $("#cmdk-list").innerHTML = cmdk.shown.map((it, i) => {
    const head = !words.length && it.group !== last ? `<div class="cmdk-group" role="presentation">${it.group}</div>` : "";
    last = it.group;
    return `${head}<div class="cmdk-item ${i === cmdk.at ? "on" : ""}" role="option" id="ck-${i}" data-i="${i}" aria-selected="${i === cmdk.at}">
      ${it.icon}<span class="ct">${esc(it.title)}</span>${it.hint ? `<span class="flag mark">${esc(it.hint)}</span>` : ""}${it.sub ? `<span class="cs">${esc(it.sub)}</span>` : ""}</div>`;
  }).join("") || `<div class="cmdk-empty">Nothing matches “${esc($("#cmdk-q").value)}”.</div>`;
  $("#cmdk-q").setAttribute("aria-activedescendant", cmdk.shown.length ? `ck-${cmdk.at}` : "");
  const on = $(".cmdk-item.on");
  if (on) on.scrollIntoView({ block: "nearest" });
}
function openCmdk() {
  if (!state.me || $("#app").classList.contains("hidden")) return;
  cmdk.back = document.activeElement;
  cmdk.items = cmdkItems();
  cmdk.at = 0;
  $("#cmdk-q").value = "";
  $("#cmdk").classList.remove("hidden");
  cmdkDraw();
  $("#cmdk-q").focus();
}
function closeCmdk() {
  $("#cmdk").classList.add("hidden");
  if (cmdk.back && document.contains(cmdk.back)) cmdk.back.focus();
}
function runCmdk(i) {
  const it = cmdk.shown[i];
  if (!it) return;
  closeCmdk();
  it.run();
}
$("#open-cmdk").addEventListener("click", openCmdk);
$("#cmdk-q").addEventListener("input", () => { cmdk.at = 0; cmdkDraw(); });
$("#cmdk-q").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const n = cmdk.shown.length;
    if (n) { cmdk.at = (cmdk.at + (e.key === "ArrowDown" ? 1 : -1) + n) % n; cmdkDraw(); }
  } else if (e.key === "Enter") { e.preventDefault(); runCmdk(cmdk.at); }
});
$("#cmdk-list").addEventListener("click", (e) => { const it = e.target.closest(".cmdk-item"); if (it) runCmdk(+it.dataset.i); });
$("#cmdk-list").addEventListener("mousemove", (e) => {
  const it = e.target.closest(".cmdk-item");
  if (it && +it.dataset.i !== cmdk.at) { cmdk.at = +it.dataset.i; $$(".cmdk-item").forEach((x) => { x.classList.toggle("on", x === it); x.setAttribute("aria-selected", x === it); }); }
});
$("#cmdk").addEventListener("mousedown", (e) => { if (e.target.id === "cmdk") closeCmdk(); });
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#cmdk").classList.contains("hidden") ? openCmdk() : closeCmdk(); }
  else if (e.key === "Escape" && !$("#cmdk").classList.contains("hidden")) { e.preventDefault(); closeCmdk(); }
});

// ------------------------------------------------------------------ router
function stopPoll() { if (state.poll) { clearInterval(state.poll); state.poll = null; } }
async function render() {
  stopPoll();
  renderSidebar();
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const v = view();
  const moved = state.shown !== location.hash;
  state.shown = location.hash;
  state.moved = moved;
  if (moved) v.innerHTML = `<div class="skeleton" aria-busy="true"><span class="sr">Loading…</span><i></i><i></i><i></i><i></i></div>`;
  try {
    if (parts[0] === "a") await viewAssignment(+parts[1], parts[2] || "results");
    else if (parts[0] === "s") await viewSubmission(+parts[1], parts[2]);
    else if (parts[0] === "p") await viewPair(+parts[1]);
    else if (parts[0] === "st") await viewStudent(+parts[1]);
    else if (parts[0] === "status") await viewStatus();
    else if (parts[0] === "admin") await viewAdmin();
    else viewHome();
  } catch (e) {
    v.innerHTML = `<div class="sheet empty"><h2>That didn't load</h2><p>${esc(e.message)}</p><a class="btn" href="#/">Go to overview</a></div>`;
  }
  if (moved) enter(v);
  else { v.classList.remove("refresh"); void v.offsetWidth; v.classList.add("refresh"); }
  countUp(v);
  v.focus({ preventScroll: true });
}
window.addEventListener("hashchange", () => { setMenu(false); render(); });

// ------------------------------------------------------------------ home
function viewHome() {
  if (!state.courses.length) {
    view().innerHTML = `<div class="sheet empty">
      <h2>Load your Classroom courses</h2>
      <p>Lab Grader reads your courses, assignments and the PDFs students turned in. Nothing is changed in Classroom until you choose to publish grades.</p>
      <button class="btn primary" id="first-sync">Refresh from Classroom</button></div>`;
    $("#first-sync").onclick = (e) => $("#sync").click();
    return;
  }
  const f = state.home || (state.home = { q: "", status: "all", sort: "due-desc" });
  const opt = (v, t, cur) => `<option value="${v}" ${v === cur ? "selected" : ""}>${t}</option>`;
  view().innerHTML = `<div class="topline"><div class="grow"><h1>Assignments</h1>
      <p class="lede">Pick an assignment to grade, review, or publish.</p></div>
      <div class="toolbar">
        <label class="searchbox">${ICON.search}<span class="sr">Search assignments</span>
          <input type="text" id="h-q" placeholder="Search assignments" value="${esc(f.q)}" autocomplete="off"><kbd>/</kbd></label>
        <label><span class="sr">Filter by status</span><select id="h-status">${opt("all", "All statuses", f.status)}${opt("todo", "Not graded", f.status)}
          ${opt("graded", "Graded", f.status)}${opt("review", "Needs review", f.status)}</select></label>
        <label><span class="sr">Sort</span><select id="h-sort">${opt("due-desc", "Newest due date", f.sort)}${opt("due-asc", "Oldest due date", f.sort)}
          ${opt("title", "Title A–Z", f.sort)}${opt("review", "Most to review", f.sort)}</select></label>
      </div></div>
    ${bento()}
    ${state.courses.map((c) => {
      const graded = c.assignments.filter((a) => a.graded).length, n = c.assignments.length;
      const pct = n ? Math.round((100 * graded) / n) : 0;
      return `<section class="sheet course-card">
      <div class="course-head">
        <div class="course-icon">${ICON.book}</div>
        <div class="course-title"><h2>${esc(c.name)}</h2>
          <div class="sub">${c.section ? `<span>${esc(c.section)}</span>` : ""}
            <span class="badge">${ICON.users}${c.students} student${c.students === 1 ? "" : "s"}</span>
            <span class="badge">${n} assignment${n === 1 ? "" : "s"}</span></div></div>
        <div class="progress ${n && graded === n ? "full" : ""}" role="progressbar" aria-valuemin="0" aria-valuemax="${n}" aria-valuenow="${graded}" aria-label="Assignments graded">
          <div class="lbl"><span>Graded</span><b>${graded}/${n}</b></div><div class="track"><i style="width:${pct}%"></i></div></div>
      </div>
      <div class="arows" data-course="${c.id}"></div></section>`;
    }).join("")}`;
  const draw = () => {
    const q = f.q.trim().toLowerCase();
    const keep = (a) => (!q || a.title.toLowerCase().includes(q)) && (f.status === "all"
      || (f.status === "todo" && !a.graded) || (f.status === "graded" && a.graded) || (f.status === "review" && a.to_review > 0));
    const by = { "due-desc": (x, y) => (y.due || "").localeCompare(x.due || ""), "due-asc": (x, y) => (x.due || "~").localeCompare(y.due || "~"),
      title: (x, y) => x.title.localeCompare(y.title, undefined, { numeric: true }), review: (x, y) => y.to_review - x.to_review }[f.sort];
    state.courses.forEach((c) => {
      const rows = c.assignments.filter(keep).sort(by);
      $(`.arows[data-course="${c.id}"]`).innerHTML = rows.map((a) => `<a class="arow" href="#/a/${a.id}">
        <span class="t"><b>${esc(a.title)}</b><span class="meta"><span class="tag">${ICON.calendar}${a.due ? "Due " + esc(dueText(a.due)) : "No due date"}</span></span></span>
        <span class="slot review">${a.to_review ? `<span class="flag mark">${a.to_review} to review</span>` : ""}</span>
        <span class="counter"><b>${a.turned_in}</b>/${a.submissions} submissions</span>
        <span class="slot">${a.graded ? `<span class="flag green">Graded</span>` : `<span class="flag slate">Not graded</span>`}</span>
        <span class="chev">${ICON.chevron}</span></a>`).join("")
        || (c.assignments.length ? `<div class="none-found">No assignments in this course match your search or filter.<br>
              <button class="btn small" data-clear>Clear search and filters</button></div>`
            : `<div class="none-found">No assignments in this course yet. New ones appear when you refresh from Classroom.</div>`);
    });
    $$("[data-clear]").forEach((b) => (b.onclick = () => {
      Object.assign(f, { q: "", status: "all" });
      $("#h-q").value = ""; $("#h-status").value = "all";
      draw();
    }));
  };
  draw();
  $("#h-q").oninput = (e) => { f.q = e.target.value; draw(); };
  $("#h-status").onchange = (e) => { f.status = e.target.value; draw(); };
  $("#h-sort").onchange = (e) => { f.sort = e.target.value; draw(); };
}
// the bento row: what needs attention first, then the totals
function bento() {
  const all = state.courses.flatMap((c) => c.assignments.map((a) => ({ ...a, course: c.name })));
  const review = all.reduce((n, a) => n + a.to_review, 0);
  const subs = all.reduce((n, a) => n + a.submissions, 0), turned = all.reduce((n, a) => n + a.turned_in, 0);
  const graded = all.filter((a) => a.graded).length;
  const students = state.courses.reduce((n, c) => n + c.students, 0);
  const queue = all.filter((a) => a.to_review).sort((x, y) => y.to_review - x.to_review).slice(0, 4);
  const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
  return `<div class="bento">
    <section class="sheet tile wide ${review ? "review" : ""}">
      <div class="k">${ICON.inbox}Waiting for your review</div>
      <div class="v" data-count="${review}">${review}</div>
      ${queue.length ? `<div class="queue">${queue.map((a) => `<a href="#/a/${a.id}/results"><span class="qt"><b>${esc(a.title)}</b><span>${esc(a.course)}</span></span>
          <span class="flag mark">${a.to_review}</span>${ICON.chevron}</a>`).join("")}</div>`
        : `<div class="hint">Nothing flagged. Every graded submission has been checked.</div>`}
    </section>
    <section class="sheet tile accent">
      <div class="k">${ICON.check}Assignments graded</div>
      <div class="v"><span data-count="${graded}">${graded}</span><small> / ${all.length}</small></div>
      <div class="meter-sm"><i style="width:${pct(graded, all.length)}%"></i></div>
    </section>
    <section class="sheet tile">
      <div class="k">${ICON.file}Submissions turned in</div>
      <div class="v"><span data-count="${turned}">${turned}</span><small> / ${subs}</small></div>
      <div class="hint">${pct(turned, subs)}% of all expected work</div>
    </section>
    <section class="sheet tile">
      <div class="k">${ICON.users}Students</div>
      <div class="v" data-count="${students}">${students}</div>
      <div class="hint">across ${state.courses.length} course${state.courses.length === 1 ? "" : "s"}</div>
    </section>
    <section class="sheet tile">
      <div class="k">${ICON.search}Find anything</div>
      <div class="hint" style="margin-top:0">Jump to an assignment or action from anywhere.</div>
      <button class="btn small" style="margin-top:auto;align-self:flex-start" onclick="openCmdk()">Open search <kbd>${isMac ? "⌘K" : "Ctrl K"}</kbd></button>
    </section>
  </div>`;
}
// "2026-10-17" or "2026-10-17 23:59" -> "17 Oct 2026"
function dueText(d) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : d;
}
// "/" jumps to the search box on the overview
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !e.target.closest("input, textarea, select, [contenteditable]") && $("#h-q")) { e.preventDefault(); $("#h-q").focus(); }
});
function rowLinks() { $$("tr[data-href]").forEach((tr) => tr.addEventListener("click", () => (location.hash = tr.dataset.href))); }

// ------------------------------------------------------------------ assignment
async function viewAssignment(id, tab) {
  const a = await api(`/assignments/${id}`);
  const subs = tab === "results" ? await api(`/assignments/${id}/submissions`) : null;
  const pairs = tab === "similarity" ? await api(`/assignments/${id}/similarity`) : null;
  const total = Object.values(a.counts).reduce((x, y) => x + y, 0);
  const tabs = [["results", "Results", total], ["tests", "Questions and tests", a.n_tests], ["similarity", "Similarity", a.similar_open || null], ["settings", "Settings", null]];
  view().innerHTML = `
    <div class="topline">
      <div class="grow">
        <div class="crumb">${esc(a.course.name)}</div>
        <h1>${esc(a.title)}</h1>
        <div class="muted small" style="margin-top:6px">${fmt(a.max_points)} points${a.due ? `, due ${esc(dueText(a.due))}` : ""}${a.last_graded_at ? `, last graded ${new Date(a.last_graded_at).toLocaleString()}` : ""}</div>
      </div>
      <div class="actions">
        <button class="btn primary" id="grade">${a.last_graded_at ? "Grade again" : "Grade all submissions"}</button>
        <a class="btn" href="/api/assignments/${id}/export.csv">Export CSV</a>
        <button class="btn" id="publish">Publish grades</button>
      </div>
    </div>
    <div id="job"></div>
    <div class="tabs" role="tablist">${tabs.map(([k, t, n]) => `<button class="tab ${k === tab ? "on" : ""}" role="tab" aria-selected="${k === tab}" data-tab="${k}">${t}${n !== null ? `<span class="n">${n}</span>` : ""}</button>`).join("")}</div>
    <div id="tab"></div>`;
  $$(".tab").forEach((b) => (b.onclick = () => (location.hash = `#/a/${id}/${b.dataset.tab}`)));
  $("#grade").onclick = (e) => act(e.target, async () => {
    if (!a.n_tests && a.tests_imported) toast("No test cases yet: code will be extracted but not scored. Add tests under Questions and tests.");
    const j = await api(`/assignments/${id}/grade`, { method: "POST" });
    showJob(j, id);
  });
  $("#publish").onclick = () => publishDialog(a);
  if (a.job) showJob(a.job, id, true);
  const t = $("#tab");
  if (tab === "results") renderResults(t, a, subs);
  else if (tab === "tests") renderTests(t, a);
  else if (tab === "similarity") renderSimilarity(t, a, pairs);
  else renderSettings(t, a);
}

function showJob(j, aid, initial = false) {
  const box = $("#job");
  if (!box) return;
  const draw = (j) => {
    const pct = j.total ? Math.round((100 * j.progress) / j.total) : 0;
    const running = j.status === "queued" || j.status === "running";
    if (initial && !running && j.status === "done") { box.innerHTML = ""; return; }
    const cur = box.firstElementChild;
    if (running && cur && cur.dataset.status === j.status) {   // update in place so the bar glides
      $(".bar i", cur).style.width = pct + "%";
      $(".job-n", cur).textContent = `${j.progress}/${j.total || "?"}`;
      $(".job-msg", cur).textContent = j.message;
      return running;
    }
    box.innerHTML = `<div class="sheet job ${j.status} ${cur ? "" : "enter"}" data-status="${j.status}">
      <div style="min-width:0;flex:2"><b>${running ? "Grading in progress" : j.status === "failed" ? "Grading stopped" : "Grading finished"}</b>
      <div class="muted small job-msg">${esc(j.message)}</div></div>
      ${running ? `<div class="bar" aria-label="progress"><i style="width:${pct}%"></i></div><span class="small muted job-n">${j.progress}/${j.total || "?"}</span>` : `<button class="btn small ghost" id="job-x">Dismiss</button>`}</div>`;
    const x = $("#job-x");
    if (x) x.onclick = () => (box.innerHTML = "");
    return running;
  };
  if (!draw(j)) return;
  stopPoll();
  state.poll = setInterval(async () => {
    try {
      const nj = await api(`/jobs/${j.id}`);
      if (!draw(nj)) {
        stopPoll();
        initial = false;
        await loadCourses();
        if (location.hash.startsWith(`#/a/${aid}`)) { await render(); showJob(nj, aid); }
        toast(nj.status === "done" ? "Grading finished." : "Grading stopped: " + nj.message, nj.status !== "done");
      }
    } catch { stopPoll(); }
  }, 1200);
}

function histogram(scores, max) {
  const bins = new Array(10).fill(0);
  scores.forEach((s) => bins[Math.min(9, Math.floor((s / max) * 10))]++);
  const top = Math.max(1, ...bins);
  const w = 30, gap = 4, base = 54, tall = 36;   // room above the tallest bar for its count
  const h = (b) => Math.max(b ? 2 : 0, (b / top) * tall);
  return `<div class="hist-head"><span>Score distribution</span><span>${scores.length} student${scores.length === 1 ? "" : "s"}</span></div>
    <svg viewBox="0 0 ${10 * (w + gap) - gap} 72" role="img" aria-label="Score distribution: ${bins.map((b, i) => `${b} between ${fmt((i * max) / 10)} and ${fmt(((i + 1) * max) / 10)}`).join(", ")}">
    <defs><linearGradient id="hist-g" x1="0" y1="0" x2="0" y2="1"><stop offset="0"/><stop offset="1"/></linearGradient></defs>
    ${bins.map((b, i) => `<rect style="--i:${i}" x="${i * (w + gap)}" y="${base - h(b)}" width="${w}" height="${h(b)}" rx="2"><title>${b} student(s) between ${fmt((i * max) / 10)} and ${fmt(((i + 1) * max) / 10)}</title></rect>
      ${b ? `<text class="cnt" x="${i * (w + gap) + w / 2}" y="${base - h(b) - 4}" text-anchor="middle">${b}</text>` : ""}`).join("")}
    <line x1="0" x2="${10 * (w + gap) - gap}" y1="${base + 0.5}" y2="${base + 0.5}"/>
    <text x="0" y="70">0</text><text x="${(10 * (w + gap) - gap) / 2}" y="70" text-anchor="middle">${fmt(max / 2)}</text>
    <text x="${10 * (w + gap) - gap}" y="70" text-anchor="end">${fmt(max)}</text></svg>`;
}

// one question's result as a single short value: "11/13", "Doesn't compile", "—"
function qResult(st) {
  if (st.compile === "MISSING") return `<span class="qres none" title="No code for this question">—</span>`;
  if (st.compile === "COMPILE_ERROR") return `<span class="qres bad">Doesn't compile</span>`;
  if (!st.runs.length) {
    const why = st.compile === "NO_TESTS" ? "No tests" : st.compile === "UNKNOWN_LANGUAGE" ? "Language unknown" : "Not run";
    return `<span class="qres none">${why}</span>`;
  }
  const ok = st.runs.filter(Boolean).length, n = st.runs.length;
  const cls = ok === n ? "ok" : ok === 0 ? "bad" : "part";
  const tip = st.runs.map((p, i) => `Test ${i + 1}: ${p ? "passed" : STATUS_TEXT[st.statuses[i]] || st.statuses[i]}`).join("\n");
  return `<span class="qres ${cls}" title="${esc(tip)}"><b>${ok}</b>/${n}</span>`;
}
// what the row needs from you, in one place; the reasons stay small
function rowStatus(r) {
  const late = r.late ? `<span class="flag blue">Late</span>` : "";
  if (r.status === "NO_SUBMISSION") return `<span class="flag">Not submitted</span>`;
  if (r.status === "ERROR" && r.override_score === null) return `<span class="flag red">Couldn't grade</span>${late}`;
  if (r.needs_review && !r.reviewed) {
    const why = [...new Set(r.flags.filter((f) => !["LATE", "NOT_SUBMITTED", "COMPILE_ERROR", "MISSING_QUESTION", "SIMILAR_CODE", "EARLIER_COPY"].includes(f.code))
      .map((f) => (FLAGS[f.code] || [f.code])[0].toLowerCase()))];
    return `<span class="flag mark">Needs review</span>${late}${why.length ? `<span class="why" title="${esc(r.flags.map((f) => f.msg).join("\n"))}">${esc(why.join(", "))}</span>` : ""}`;
  }
  if (r.reviewed) return `<span class="flag green">Reviewed</span>${late}`;
  return late;
}

function renderResults(el, a, data) {
  const rows = data.rows;
  if (!rows.length) {
    el.innerHTML = `<div class="sheet empty"><h2>No submissions loaded yet</h2>
      <p>Grading fetches every student's PDF from Classroom, pulls out the code, runs it against your tests in an isolated sandbox, and checks for copied code.</p>
      <button class="btn primary" onclick="document.getElementById('grade').click()">Grade all submissions</button></div>`;
    return;
  }
  const graded = rows.filter((r) => r.final_score !== null && r.status !== "NO_SUBMISSION");
  const avg = graded.length ? graded.reduce((s, r) => s + r.final_score, 0) / graded.length : null;
  const isReview = (r) => r.needs_review && !r.reviewed;
  const isMissing = (r) => r.status === "NO_SUBMISSION";
  const toReview = rows.filter(isReview).length;
  const missing = rows.filter(isMissing).length;
  const filters = [["all", "Everyone", rows.length], ["review", "Needs review", toReview], ["done", "Reviewed", rows.filter((r) => r.reviewed).length], ["missing", "Not submitted", missing]];
  el.innerHTML = `
    <div class="sheet summary">
      <div><div class="v"><span data-count="${graded.length}">${graded.length}</span><span class="muted" style="font-size:15px;font-weight:500"> / ${rows.length}</span></div><div class="k">graded</div></div>
      <div><div class="v">${avg === null ? "–" : `<span data-count="${avg}" data-dec="1">${fmt(avg)}</span>`}</div><div class="k">average of ${fmt(a.max_points)}</div></div>
      <div class="review"><div class="v" data-count="${toReview}">${toReview}</div><div class="k">need your review</div></div>
      <div><div class="v" data-count="${missing}">${missing}</div><div class="k">not submitted</div></div>
      <div class="hist">${histogram(a.scores, a.max_points)}</div>
    </div>
    <div class="chips" role="group" aria-label="Filter">
      ${filters.map(([k, t, n], i) => `<button class="chip ${i ? "" : "on"}" data-f="${k}">${t}<span class="n">${n}</span></button>`).join("")}
      <input class="search" type="text" placeholder="Find a student" aria-label="Find a student">
    </div>
    <div class="sheet table-wrap"><table class="register results">
      <thead><tr><th><button class="sort" data-sort="name">Student</button></th>${data.labels.map((l) => `<th class="q">Q${esc(l)}</th>`).join("")}
        <th class="num"><button class="sort" data-sort="score">Score</button></th><th class="hide-sm">Status</th></tr></thead>
      <tbody id="reg"></tbody></table></div>`;
  let filter = "all", q = "", sort = { by: "name", dir: 1 }, first = state.moved;
  const keyOf = { name: (r) => person(r.student.name).name.toLowerCase(), score: (r) => (isMissing(r) ? -1 : r.final_score ?? -1) };
  const draw = () => {
    const shown = rows.filter((r) => {
      if (q && !(r.student.name + r.student.email).toLowerCase().includes(q)) return false;
      if (filter === "review") return isReview(r);
      if (filter === "done") return r.reviewed;
      if (filter === "missing") return isMissing(r);
      return true;
    }).sort((x, y) => { const kx = keyOf[sort.by](x), ky = keyOf[sort.by](y); return (kx < ky ? -1 : kx > ky ? 1 : 0) * sort.dir; });
    $$(".sort").forEach((b) => b.setAttribute("aria-sort", b.dataset.sort === sort.by ? (sort.dir > 0 ? "ascending" : "descending") : "none"));
    $("#reg").innerHTML = shown.map((r) => {
      const who = person(r.student.name);
      return `<tr class="row ${isReview(r) ? "review" : ""}" data-href="#/s/${r.id}">
      <td title="${esc(r.student.email)}"><div class="name">${esc(who.name)}</div>${who.roll ? `<div class="email">${esc(who.roll)}</div>` : ""}</td>
      ${r.strip.map((st) => `<td class="q">${isMissing(r) ? `<span class="qres none">—</span>` : qResult(st)}</td>`).join("")}
      <td class="num">${isMissing(r) ? `<span class="qres none">—</span>` : `<span class="score ${r.override_score !== null ? "over" : ""}" ${r.override_score !== null ? `title="Changed by you (automatic: ${fmt(r.auto_score)})"` : ""}>${fmt(r.final_score)}</span><span class="score"><span class="of"> / ${fmt(a.max_points)}</span></span>`}</td>
      <td class="hide-sm"><span class="status">${rowStatus(r)}</span></td></tr>`;
    }).join("")
      || `<tr><td colspan="${3 + data.labels.length}" class="muted" style="padding:24px;text-align:center">Nobody matches this filter.</td></tr>`;
    if (first && !calm()) $$("#reg tr").forEach((tr, i) => { if (i < 16) { tr.style.setProperty("--i", i); tr.classList.add("enter"); } });
    first = false;
    rowLinks();
  };
  $$(".chip", el).forEach((c) => (c.onclick = () => { $$(".chip", el).forEach((x) => x.classList.remove("on")); c.classList.add("on"); filter = c.dataset.f; draw(); }));
  $$(".sort", el).forEach((b) => (b.onclick = () => {
    sort = sort.by === b.dataset.sort ? { by: sort.by, dir: -sort.dir } : { by: b.dataset.sort, dir: b.dataset.sort === "score" ? -1 : 1 };
    draw();
  }));
  $(".search", el).oninput = (e) => { q = e.target.value.toLowerCase(); draw(); };
  draw();
}

// ------------------------------------------------------------------ tests editor
function renderTests(el, a) {
  el.innerHTML = `
    <div class="note">Tests run against every student's program. Sample tests are read from the assignment PDF; add hidden tests to check edge cases students haven't seen. Changes save as you go and apply the next time you grade.</div>
    <div class="actions" style="margin-bottom:16px">
      <button class="btn" id="import">${a.tests_imported ? "Read tests from the PDF again" : "Read tests from the assignment PDF"}</button>
    </div>
    <div id="qs"></div>
    <form class="sheet pad" id="addq" style="margin-top:16px">
      <h3 style="margin-bottom:12px">Add a question</h3>
      <div style="display:grid;grid-template-columns:120px 1fr 100px auto;gap:10px;align-items:end">
        <label class="field" style="margin:0"><span>Number</span><input type="text" name="label" required placeholder="3"></label>
        <label class="field" style="margin:0"><span>Title</span><input type="text" name="title" placeholder="Reverse a linked list"></label>
        <label class="field" style="margin:0"><span>Weight</span><input type="number" name="weight" value="1" min="0.1" step="0.1"></label>
        <button class="btn" type="submit">Add question</button>
      </div>
      <p class="muted small" style="margin:8px 0 0">The number must match how students label the question in their PDF (Q3, Question 3, Program 3…).</p>
    </form>`;
  const qs = $("#qs");
  const drawQ = (q) => `<section class="sheet qblock" data-q="${q.id}">
    <div class="qhead"><h3>Question ${esc(q.label)}${q.title ? `: ${esc(q.title)}` : ""}</h3>
      <label class="small">Weight <input type="number" class="qw" value="${q.weight}" min="0.1" step="0.1" style="width:70px"></label>
      <button class="btn small ghost danger qdel">Remove question</button></div>
    <div class="pad">
      ${q.statement ? `<p class="muted small" style="margin:0 0 12px;white-space:pre-wrap">${esc(q.statement)}</p>` : ""}
      <table class="tests-table"><thead><tr><th>Input</th><th>Expected output</th><th class="narrow">Hidden</th><th class="narrow">Weight</th><th></th></tr></thead>
      <tbody>${q.tests.map((t, i) => t.rule ? `<tr data-t="${t.id}">
        <td colspan="2"><div class="note" style="margin:0"><b>Requirement check:</b> ${esc(t.expected)}</div><div class="src">Test ${i + 1}, checks the program's behaviour (${esc(t.rule)})</div></td>
        <td></td>
        <td><input type="number" class="t-w" value="${t.weight}" min="0.1" step="0.1" style="width:70px" aria-label="Weight"></td>
        <td><button class="btn small ghost danger t-del" aria-label="Delete test ${i + 1}">Delete</button></td></tr>` : `<tr data-t="${t.id}">
        <td><textarea class="t-in" aria-label="Input for test ${i + 1}">${esc(t.stdin)}</textarea><div class="src">Test ${i + 1}${t.source === "pdf" ? ", from the PDF" : ""}</div></td>
        <td><textarea class="t-out" aria-label="Expected output for test ${i + 1}">${esc(t.expected)}</textarea></td>
        <td><input type="checkbox" class="t-hid" ${t.hidden ? "checked" : ""} aria-label="Hidden"></td>
        <td><input type="number" class="t-w" value="${t.weight}" min="0.1" step="0.1" style="width:70px" aria-label="Weight"></td>
        <td><button class="btn small ghost danger t-del" aria-label="Delete test ${i + 1}">Delete</button></td></tr>`).join("")
        || `<tr><td colspan="5" class="muted small">No tests yet. This question can't be scored until it has at least one.</td></tr>`}</tbody></table>
      <button class="btn small t-add" style="margin-top:10px">Add test</button>
    </div></section>`;
  const draw = () => {
    qs.innerHTML = a.questions.length ? a.questions.map(drawQ).join("")
      : `<div class="sheet empty"><h2>No questions yet</h2><p>Read them from the assignment PDF, or add them below.</p></div>`;
    $$(".qblock").forEach(bindQ);
  };
  const replaceQ = (nq) => { a.questions = a.questions.map((q) => (q.id === nq.id ? nq : q)); draw(); };
  function bindQ(sec) {
    const qid = +sec.dataset.q;
    $(".qw", sec).onchange = (e) => act(null, async () => { await api(`/questions/${qid}`, { method: "PATCH", body: { weight: +e.target.value } }); toast("Weight saved."); });
    $(".qdel", sec).onclick = () => act(null, async () => {
      if (!confirm("Remove this question and its tests?")) return;
      await api(`/questions/${qid}`, { method: "DELETE" });
      a.questions = a.questions.filter((q) => q.id !== qid); draw();
    });
    $(".t-add", sec).onclick = (e) => act(e.target, async () => replaceQ(await api(`/questions/${qid}/tests`, { method: "POST", body: { stdin: "", expected: "" } })));
    $$("tr[data-t]", sec).forEach((tr) => {
      const tid = +tr.dataset.t;
      const save = (body) => act(null, async () => { await api(`/tests/${tid}`, { method: "PATCH", body }); toast("Test saved."); });
      if ($(".t-in", tr)) $(".t-in", tr).onchange = (e) => save({ stdin: e.target.value });
      if ($(".t-out", tr)) $(".t-out", tr).onchange = (e) => save({ expected: e.target.value });
      if ($(".t-hid", tr)) $(".t-hid", tr).onchange = (e) => save({ hidden: e.target.checked });
      $(".t-w", tr).onchange = (e) => save({ weight: +e.target.value });
      $(".t-del", tr).onclick = () => act(null, async () => {
        await api(`/tests/${tid}`, { method: "DELETE" });
        const q = a.questions.find((q) => q.id === qid); q.tests = q.tests.filter((t) => t.id !== tid); draw();
      });
    });
  }
  $("#import").onclick = (e) => act(e.target, async () => {
    e.target.textContent = "Reading…";
    const r = await api(`/assignments/${a.id}/import-tests`, { method: "POST" });
    toast(r.message, !r.questions);
    render();
  });
  $("#addq").onsubmit = (e) => { e.preventDefault(); act(null, async () => {
    const f = new FormData(e.target);
    const q = await api(`/assignments/${a.id}/questions`, { method: "POST", body: { label: f.get("label").trim(), title: f.get("title"), weight: +f.get("weight") || 1 } });
    a.questions.push(q); e.target.reset(); draw();
  }); };
  draw();
}

// ------------------------------------------------------------------ similarity
// "2025ITB065 SATYAM_KUMAR" -> { name: "Satyam Kumar", roll: "2025ITB065" }
function person(raw) {
  const m = /^(\S*\d\S*)\s+(.+)$/.exec((raw || "").trim());
  let name = (m ? m[2] : raw || "").replace(/_+/g, " ").replace(/\s+/g, " ").trim();
  if (name === name.toUpperCase()) name = name.toLowerCase().replace(/\b\p{L}/gu, (c) => c.toUpperCase());
  return { name, roll: m ? m[1] : "" };
}
const pct = (x) => `${Math.round(x * 100)}%`;
function who(s) {
  const p = person(s.name);
  return `<span class="who2"><b>${esc(p.name)}</b>${p.roll ? `<span>${esc(p.roll)}</span>` : ""}</span>`;
}

// students who share code on one question: every pair of them linked, at any strength
function simClusters(pairs) {
  const parent = new Map();
  const find = (k) => { while (parent.get(k) !== k) { parent.set(k, parent.get(parent.get(k))); k = parent.get(k); } return k; };
  const key = (p, s) => `${p.question}|${s.id}`;
  pairs.forEach((p) => {
    [key(p, p.a), key(p, p.b)].forEach((k) => parent.has(k) || parent.set(k, k));
    parent.set(find(key(p, p.a)), find(key(p, p.b)));
  });
  const by = new Map();
  pairs.forEach((p) => {
    const r = find(key(p, p.a));
    if (!by.has(r)) by.set(r, { q: p.question, members: new Map(), items: [] });
    const g = by.get(r);
    g.items.push(p); g.members.set(p.a.id, p.a); g.members.set(p.b.id, p.b);
  });
  return [...by.values()].map((g) => {
    g.items.sort((x, y) => y.score - x.score);
    g.score = g.items[0].score;
    g.open = g.items.filter((p) => !p.verdict).length;
    g.state = g.open ? "open" : g.items.some((p) => p.verdict === "confirmed") ? "confirmed" : "cleared";
    g.short = g.items.every((p) => p.low_confidence);
    g.people = [...g.members.values()].sort((x, y) => person(x.name).name.localeCompare(person(y.name).name));
    return g;
  }).sort((x, y) => (y.state === "open") - (x.state === "open") || y.score - x.score
    || String(x.q).localeCompare(String(y.q), undefined, { numeric: true }));
}

function renderSimilarity(el, a, pairs) {
  const groups = simClusters(pairs);
  const n = { open: 0, cleared: 0, confirmed: 0 };
  groups.forEach((g) => n[g.state]++);
  const f = state.simFilter && state.simFilter.aid === a.id ? state.simFilter : (state.simFilter = { aid: a.id, v: n.open ? "open" : "all" });
  const chip = (v, t, c) => `<button class="chip ${f.v === v ? "on" : ""}" data-f="${v}">${t}<span class="n">${c}</span></button>`;
  if (!pairs.length) {
    el.innerHTML = `<div class="sheet empty"><h2>No similar code</h2><p>${a.last_graded_at ? `No two students share more than ${pct(a.similarity_threshold)} of their code on any question.` : "Similarity is checked when you grade."}</p></div>`;
    return;
  }
  el.innerHTML = `
    <div class="sim-head">
      <p class="sim-lede"><b>${groups.length}</b> group${groups.length === 1 ? "" : "s"} of students wrote similar code${n.open ? `, <b>${n.open}</b> still to decide` : ", all decided"}. Similar code doesn't put students in "Needs review": decide here, a whole group at a time.</p>
      <details class="how"><summary>How is this measured?</summary>
        <p>Code is compared question by question, after renaming variables and removing comments, so copied work still matches when it has been reworded. A group is every student linked to another by similar code on the same question. Patterns most of the class shares, and any starter code set in Settings, are ignored. Short programs match more easily, so they are marked "short". A high score is a reason to look, not proof: talk to the students before acting.</p></details>
    </div>
    <div class="chips">${chip("open", "To decide", n.open)}${chip("cleared", "Marked fine", n.cleared)}${chip("confirmed", "Copying confirmed", n.confirmed)}${chip("all", "All", groups.length)}</div>
    <div class="sheet sim-list" id="sim-list"></div>`;
  const names = (g) => g.people.slice(0, 4).map((s) => esc(person(s.name).name)).join(", ") + (g.people.length > 4 ? ` and ${g.people.length - 4} more` : "");
  const draw = () => {
    const rows = groups.map((g, i) => [g, i]).filter(([g]) => f.v === "all" || g.state === f.v);
    $("#sim-list").innerHTML = rows.map(([g, i]) => `<div class="sim-group" data-g="${i}">
      <button class="sim-row" aria-expanded="false">
        <span class="sim-pct ${g.score >= 0.9 ? "hi" : ""}">${pct(g.score)}</span>
        <span class="sim-who"><span class="who2"><b>Question ${esc(g.q)}: ${g.people.length} students</b><span>${names(g)}</span></span></span>
        <span class="sim-qs"><span class="qchip">${g.items.length} pair${g.items.length === 1 ? "" : "s"}</span>${g.short ? `<span class="short">short</span>` : ""}</span>
        <span class="sim-state">${g.state === "cleared" ? `<span class="flag green">Marked fine</span>` : g.state === "confirmed" ? `<span class="flag red">Copying</span>` : ""}</span>
        <span class="chev">${ICON.chevron}</span></button>
      <div class="sim-pairs hidden">
        ${g.items.map((p) => `<a class="sim-pair" href="#/p/${p.id}"><span class="sim-pct sm ${p.score >= 0.9 ? "hi" : ""}">${pct(p.score)}</span>${who(p.a)}<span class="amp" aria-hidden="true">&amp;</span>${who(p.b)}${p.verdict ? `<span class="flag ${p.verdict === "cleared" ? "green" : "red"}">${p.verdict === "cleared" ? "Fine" : "Copying"}</span>` : ""}</a>`).join("")}
        <div class="sim-acts">${g.state === "open" || g.open
          ? `<button class="btn small" data-v="cleared">Mark the group as fine</button><button class="btn small danger" data-v="confirmed">Confirm copying for the group</button>`
          : `<button class="btn small ghost" data-v="">Undo the decision</button>`}
          <span class="muted small">Open a pair to compare the code side by side.</span></div>
      </div></div>`).join("")
      || `<div class="none-found">${f.v === "open" ? "Every group has been decided." : "No groups here."}</div>`;
    $$(".sim-group", el).forEach((box) => {
      const g = groups[+box.dataset.g];
      const head = $(".sim-row", box);
      head.onclick = () => { const open = head.getAttribute("aria-expanded") !== "true"; head.setAttribute("aria-expanded", open); $(".sim-pairs", box).classList.toggle("hidden", !open); };
      $$("[data-v]", box).forEach((b) => (b.onclick = () => act(b, async () => {
        await api(`/assignments/${a.id}/similarity/verdict`, { method: "POST", body: { ids: g.items.map((p) => p.id), verdict: b.dataset.v } });
        toast(b.dataset.v === "cleared" ? `Marked ${g.people.length} students as fine on question ${g.q}.` : b.dataset.v === "confirmed" ? `Copying confirmed for ${g.people.length} students.` : "Decision undone.");
        render();
      })));
    });
  };
  draw();
  $$(".chips [data-f]", el).forEach((b) => (b.onclick = () => {
    f.v = b.dataset.f;
    $$(".chips [data-f]", el).forEach((x) => x.classList.toggle("on", x === b));
    draw();
  }));
}

async function viewPair(id) {
  const p = await api(`/similarity/${id}`);
  const all = await api(`/assignments/${p.assignment_id}/similarity`);
  const key = (x, y) => [x, y].sort((m, n) => m - n).join("-");
  const siblings = all.filter((x) => key(x.a.id, x.b.id) === key(p.a.id, p.b.id)).sort((x, y) => String(x.question).localeCompare(String(y.question), undefined, { numeric: true }));
  const A = person(p.a.name), B = person(p.b.name);
  const vd = (v, t, cls = "") => `<button class="btn ${cls}" data-v="${v}">${t}</button>`;
  const decided = p.verdict === "cleared" ? `<span class="flag green">Marked fine</span>` : p.verdict === "confirmed" ? `<span class="flag red">Copying confirmed</span>` : "";
  view().innerHTML = `
    <div class="crumb"><a href="#/a/${p.assignment_id}/similarity">Similar code</a></div>
    <div class="topline"><div class="grow"><h1>${esc(A.name)} &amp; ${esc(B.name)}</h1>
      <div class="muted small" style="margin-top:8px">${esc([A.roll, B.roll].filter(Boolean).join(" · "))}${A.roll ? " · " : ""}Question ${esc(p.question)}: ${pct(p.score)} of the shorter program matches${p.low_confidence ? " (short program, less certain)" : ""}</div></div>
      <div class="actions">${decided}${p.verdict ? vd("", "Undo", "ghost") : `${vd("cleared", "Mark as fine")}${vd("confirmed", "Confirm copying", "danger")}`}</div></div>
    ${siblings.length > 1 ? `<div class="tabs" role="tablist">${siblings.map((x) => `<button class="tab ${x.id === p.id ? "on" : ""}" role="tab" aria-selected="${x.id === p.id}" data-pair="${x.id}">Q${esc(x.question)}<span class="n">${pct(x.score)}</span></button>`).join("")}</div>` : ""}
    <div class="side-by-side">${[[p.a, A], [p.b, B]].map(([s, who]) => `<div class="sheet"><div class="qhead"><h3><a href="#/s/${s.id}">${esc(who.name)}</a></h3><span class="lang">${esc(LANG[s.language] || s.language || "")}</span></div>
      <div style="padding:12px">${codeTable(s.code, s.lines, true)}</div></div>`).join("")}</div>
    <p class="muted small" style="margin-top:12px"><span class="hit-key"></span>Marked lines share their structure with the other student's program.</p>`;
  $$("[data-pair]").forEach((b) => (b.onclick = () => (location.hash = `#/p/${b.dataset.pair}`)));
  $$("[data-v]").forEach((b) => (b.onclick = () => act(b, async () => {
    await api(`/similarity/${id}`, { method: "PATCH", body: { verdict: b.dataset.v } });
    toast(b.dataset.v === "cleared" ? "Marked as fine. The flag is removed from both students." : b.dataset.v === "confirmed" ? "Copying confirmed." : "Decision undone.");
    render();
  })));
}

function codeTable(code, hits = [], wrap = false) {
  const hit = new Set();
  (hits || []).forEach(([a, b]) => { for (let i = a; i <= b; i++) hit.add(i); });
  const lines = (code || "").replace(/\n$/, "").split("\n");
  return `<div class="code${wrap ? " wrap" : ""}"><table>${lines.map((l, i) => `<tr class="${hit.has(i + 1) ? "hit" : ""}"><td class="ln">${i + 1}</td><td>${esc(l) || " "}</td></tr>`).join("")}</table></div>`;
}

// ------------------------------------------------------------------ settings
function renderSettings(el, a) {
  el.innerHTML = `<form class="sheet pad" id="settings" style="max-width:720px">
    <label class="field"><span>Maximum points</span><input type="number" name="max_points" value="${a.max_points}" min="1" step="0.5" style="max-width:160px"><em>Scores are scaled to this. Taken from Classroom when the assignment has points.</em></label>
    <label class="field"><span>Time limit per test (seconds)</span><input type="number" name="time_limit_s" value="${a.time_limit_s}" min="0.2" max="20" step="0.1" style="max-width:160px"><em>Java starts slower; 2 to 3 seconds suits most lab programs.</em></label>
    <label class="field"><span>How outputs are compared</span>
      <select name="compare_mode" style="max-width:380px">
        <option value="tokens" ${a.compare_mode === "tokens" ? "selected" : ""}>Ignore spacing and line breaks (recommended)</option>
        <option value="lines" ${a.compare_mode === "lines" ? "selected" : ""}>Same lines, ignore extra spaces</option>
        <option value="exact" ${a.compare_mode === "exact" ? "selected" : ""}>Exact, apart from trailing spaces</option>
      </select><em>Numbers within 0.000001 of each other count as equal.</em></label>
    <label class="field"><span>Flag code as similar from</span><input type="number" name="similarity_threshold" value="${a.similarity_threshold}" min="0.2" max="1" step="0.05" style="max-width:160px"><em>0.6 means 60% of the shorter program matches. Lower finds more pairs and more false alarms.</em></label>
    <label class="field"><span>Starter code you gave students</span><textarea name="starter_code" rows="6" placeholder="Paste any template code here so it isn't counted as copying">${esc(a.starter_code)}</textarea></label>
    <button class="btn primary" type="submit">Save settings</button>
    <span class="muted small" style="margin-left:10px">Settings apply the next time you grade.</span>
  </form>
  <div class="sheet pad" style="max-width:720px;margin-top:16px">
    <b>Download every file again</b>
    <p class="muted small" style="margin:6px 0 12px">Grading again only downloads what students changed in Classroom since the last time. Use this if a file was edited in Drive without the student turning it in again.</p>
    <button class="btn" id="fresh">Download and grade everything</button>
  </div>`;
  $("#fresh").onclick = (e) => act(e.target, async () => {
    const j = await api(`/assignments/${a.id}/grade?fresh=true`, { method: "POST" });
    location.hash = `#/a/${a.id}/results`;
    setTimeout(() => showJob(j, a.id), 300);
  });
  $("#settings").onsubmit = (e) => { e.preventDefault(); act(null, async () => {
    const f = new FormData(e.target);
    await api(`/assignments/${a.id}`, { method: "PATCH", body: {
      max_points: +f.get("max_points"), time_limit_s: +f.get("time_limit_s"), compare_mode: f.get("compare_mode"),
      similarity_threshold: +f.get("similarity_threshold"), starter_code: f.get("starter_code") } });
    toast("Settings saved.");
  }); };
}

// ------------------------------------------------------------------ publish
async function publishDialog(a) {
  const assign = confirm(`Publish scores to Google Classroom for "${a.title}"?\n\nOK: set them as returned grades students can see.\nCancel: choose draft grades instead.`);
  if (!assign && !confirm("Save the scores as draft grades in Classroom? Students won't see drafts until you return the work.")) return;
  act($("#publish"), async () => {
    $("#publish").textContent = "Publishing…";
    const r = await api(`/assignments/${a.id}/publish`, { method: "POST", body: { assign } });
    if (r.errors.length) toast(`Published ${r.published}. ${r.errors[0].student}: ${r.errors[0].error}`, true);
    else toast(`Published ${r.published} grade(s)${r.skipped ? `, skipped ${r.skipped} without a score` : ""}.`);
  });
}

// ------------------------------------------------------------------ submission
function diffOut(actual, expected) {
  const a = (actual || "").replace(/\s+$/, "").split("\n");
  const e = (expected || "").replace(/\s+$/, "").split("\n");
  return a.map((l, i) => (l.trimEnd() === (e[i] ?? "").trimEnd() ? esc(l) : `<span class="bad">${esc(l) || " "}</span>`)).join("\n");
}
// a requirement check (see checks.py): what it verifies, and what it found
function checkRow(r, i) {
  const showsOutput = r.rule === "run" || r.rule.startsWith("out:") || r.rule.startsWith("py:");
  return `<tr><td>
    <div class="run-head" data-run><span class="cell ${r.status === "NOT_RUN" ? "x" : r.passed ? "p" : "f"}"></span>
      <b>Check ${i + 1}</b> <span class="small">${esc(r.expected)}</span>
      <span class="verdict ${r.passed ? "p" : "f"}" style="margin-left:auto">${r.passed ? "Passed" : "Failed"}</span></div>
    <div class="run-body ${r.passed ? "hidden" : ""}">
      <div style="grid-column:1/-1"><div class="k">Result</div><pre class="out">${esc(r.note) || "<span class='muted'>(nothing)</span>"}</pre></div>
      ${showsOutput && r.status !== "NOT_RUN" ? `<div style="grid-column:1/-1"><div class="k">Program printed (run with no input)</div><pre class="out">${esc(r.stdout) || "<span class='muted'>(nothing)</span>"}</pre></div>` : ""}
      ${r.stderr ? `<div style="grid-column:1/-1"><div class="k">Errors</div><pre class="out">${esc(r.stderr)}</pre></div>` : ""}
    </div></td></tr>`;
}
const CLAIM = {
  MATCHES_ACTUAL: ["The output the student showed matches what this code prints.", false],
  MATCHES_EXPECTED_ONLY: ["The student showed the correct output, but this code doesn't print it. The output may have been copied or edited.", true],
  NO_MATCH: ["The output the student showed doesn't match any test. They may have used different input.", false],
  NONE: ["The submission has no output for this question.", false],
};

async function viewSubmission(id) {
  const s = await api(`/submissions/${id}`);
  const a = s.assignment;
  const ex = s.extraction || {};
  view().innerHTML = `
    <div class="crumb"><a href="#/a/${a.id}">${esc(a.title)}</a></div>
    <div class="subhead">
      <div>
        <h1><a class="plain" href="#/st/${s.student.id}" title="Every assignment of this student">${esc(s.student.name)}</a></h1>
        <div class="muted small" style="margin-top:6px">${esc(s.student.email)}${s.late ? `, turned in late` : ""}${s.published_grade !== null ? `, ${fmt(s.published_grade)} published to Classroom` : ""}</div>
        <div class="actions" style="margin-top:14px">
          ${s.has_pdf ? `<a class="btn" href="/api/submissions/${s.id}/pdf" target="_blank" rel="noopener">Open PDF</a>` : ""}
          <button class="btn" id="regrade">Grade again</button>
          <button class="btn ${s.reviewed ? "" : "primary"}" id="reviewed">${s.reviewed ? "Mark as not reviewed" : "Mark as reviewed"}</button>
          <span class="pager">${s.prev_id ? `<a class="btn" href="#/s/${s.prev_id}" aria-label="Previous student">Previous</a>` : ""}${s.next_id ? `<a class="btn" href="#/s/${s.next_id}" aria-label="Next student">Next</a>` : ""}</span>
        </div>
      </div>
      <div class="bigscore">
        <div class="v">${s.status === "ERROR" || s.final_score === null ? "–" : `<span data-count="${s.final_score}" data-dec="1">${fmt(s.final_score)}</span>`}<small> / ${fmt(a.max_points)}</small></div>
        <div class="sub">${s.override_score !== null ? `Changed by you. Automatic score was ${fmt(s.auto_score)}.` : s.status === "GRADED" ? "Automatic score" : s.status === "NO_SUBMISSION" ? "Nothing turned in" : esc(s.status)}</div>
        <form class="override" id="ovr">
          <input type="number" name="score" min="0" max="${a.max_points}" step="0.5" placeholder="Score" value="${s.override_score ?? ""}" aria-label="Your score">
          <button class="btn small" type="submit">Set score</button>
          ${s.override_score !== null ? `<button class="btn small ghost" type="button" id="clr">Use automatic</button>` : ""}
        </form>
      </div>
    </div>
    ${s.flags.length || s.error ? `<div class="sheet pad flags-box"><h3>Things to check</h3><ul>
      ${s.error ? `<li><span class="flag red">Error</span> ${esc(s.error)}</li>` : ""}
      ${s.flags.map((f) => `<li>${flagChip(f)} <span class="small muted">${esc(f.msg)}</span></li>`).join("")}
      ${s.similar.map((p) => `<li><a href="#/p/${p.id}">Compare with ${esc(p.other)}</a> <span class="small muted">Question ${esc(p.question)}, ${Math.round(p.score * 100)}%${p.verdict ? `, ${p.verdict === "cleared" ? "marked fine" : "copying confirmed"}` : ""}</span></li>`).join("")}
    </ul></div>` : ""}
    ${(s.files || []).filter((f) => f.note).map((f) => `<p class="small" style="color:var(--mark-ink)">${esc(f.note)}</p>`).join("")}
    ${(s.files || []).filter((f) => f.title).length ? `<p class="muted small">Submitted: ${s.files.filter((f) => f.title).map((f) => `${esc(f.title)}${f.kind ? ` (${esc(KIND[f.kind] || f.kind)})` : ""}`).join(", ")}${ex.images_read ? `. Read ${ex.images_read} screenshot${ex.images_read > 1 ? "s" : ""} by OCR` : ""}.${s.has_pdf && s.files.some((f) => f.kind && f.kind !== "pdf") ? " Open PDF shows the files converted and merged." : ""}</p>` : ""}
    ${ex.repairs && Object.keys(ex.repairs).length ? `<p class="muted small">While reading the submission: ${esc(repairText(ex.repairs))}.</p>` : ""}
    ${(ex.warnings || []).length ? `<p class="muted small">${ex.warnings.map(esc).join(" ")}</p>` : ""}
    <div id="programs"></div>
    <section class="sheet qblock" style="margin-top:8px">
      <div class="qhead"><h3>Feedback for the student</h3><button class="btn small primary" id="copyfb">Copy</button></div>
      <div class="pad">
        <p class="muted small" style="margin-top:0">Paste it into the student's private comment in Classroom. Hidden tests show only passed or failed; review flags and your note are left out. You can edit it before copying; edits aren't saved.</p>
        <textarea id="fb" rows="12" aria-label="Feedback for the student">${esc(s.feedback)}</textarea>
      </div>
    </section>
    <label class="field sheet pad" style="margin-top:8px"><span>Note for yourself</span>
      <textarea id="note" rows="3" placeholder="Why you changed the score, what you discussed with the student…">${esc(s.override_note)}</textarea></label>`;

  $("#programs").innerHTML = s.programs.length ? s.programs.map((p) => {
    const graded = p.tests_total > 0;
    const verdict = !graded ? "" : `<span class="verdict ${p.tests_passed === p.tests_total ? "p" : "f"}">${p.tests_passed} of ${p.tests_total} tests passed</span>`;
    const claim = CLAIM[p.claimed_status] || CLAIM.NONE;
    return `<section class="sheet qblock">
      <div class="qhead"><h3>Question ${esc(p.question)}</h3>
        <span class="lang" style="font-size:12px">${esc(LANG[p.language] || p.language || "Unknown language")}</span>
        ${p.compile_status === "COMPILE_ERROR" ? `<span class="flag red">Doesn't compile</span>` : ""}${p.fixed ? `<span class="flag blue">Corrected by you</span>` : p.ocr ? `<span class="flag mark">Read by OCR</span>` : ""}${verdict}
        <button class="btn small ghost" style="margin-left:auto" data-fix="${esc(p.question)}">${p.fixed ? "Edit your code" : "Fix code"}</button></div>
      <div class="qgrid">
        <div data-code="${esc(p.question)}">${codeTable(p.code)}
          ${Object.keys(p.repairs || {}).length ? `<p class="muted small">Fixed: ${esc(repairText(p.repairs))}.</p>` : ""}
          ${(p.warnings || []).length ? `<p class="small" style="color:var(--ink-2)">${p.warnings.map(esc).join("<br>")}</p>` : ""}</div>
        <div>
          ${p.compile_status === "COMPILE_ERROR" ? `<div class="k small" style="font-weight:600">Compiler output</div><pre class="out">${esc(p.compile_output)}</pre>` : ""}
          ${p.compile_status === "NO_TESTS" ? `<p class="muted small">This question has no tests yet. Add some under Questions and tests, then grade again.</p>` : ""}
          ${p.compile_status === "NOT_GRADED" ? `<p class="muted small">This program doesn't match any question in the assignment, so it wasn't graded.</p>` : ""}
          ${p.runs.length ? `<table class="runs"><tbody>${p.runs.map((r, i) => r.rule ? checkRow(r, i) : `<tr><td>
            <div class="run-head" data-run><span class="cell ${r.status === "NOT_RUN" ? "x" : r.passed ? "p" : "f"}"></span>
              <b>Test ${i + 1}</b>${r.hidden ? ` <span class="flag">Hidden</span>` : ""}
              <span class="verdict ${r.passed ? "p" : "f"}">${r.passed ? "Passed" : esc(STATUS_TEXT[r.status] || r.status)}</span>
              <span class="muted small" style="margin-left:auto">${r.status !== "NOT_RUN" ? r.runtime_ms + " ms" : ""}</span></div>
            <div class="run-body ${r.passed ? "hidden" : ""}">
              <div><div class="k">Input</div><pre class="out">${esc(r.stdin) || "<span class='muted'>(none)</span>"}</pre></div>
              <div><div class="k">Expected</div><pre class="out">${esc(r.expected)}</pre></div>
              ${r.status !== "NOT_RUN" ? `<div style="grid-column:1/-1"><div class="k">Program printed</div><pre class="out">${diffOut(r.stdout, r.expected) || "<span class='muted'>(nothing)</span>"}</pre></div>` : ""}
              ${r.stderr ? `<div style="grid-column:1/-1"><div class="k">Errors</div><pre class="out">${esc(r.stderr)}</pre></div>` : ""}
            </div></td></tr>`).join("")}</tbody></table>` : ""}
          ${p.claimed_output !== null || p.claimed_status !== "NONE" ? `<div class="claim ${claim[1] ? "bad" : ""}"><b>${esc(claim[0])}</b>
            ${p.claimed_output ? `<div class="k small" style="margin-top:8px;font-weight:600">${p.claimed_from_image ? "Output read from the student's screenshot (OCR, may contain small misreadings)" : "Output shown in the submission"}</div><pre class="out">${esc(p.claimed_output)}</pre>` : ""}</div>` : ""}
        </div>
      </div></section>`;
  }).join("") : (s.status === "NO_SUBMISSION" ? `<div class="sheet empty"><h2>Nothing turned in</h2><p>This student hasn't attached a file in Classroom. The score is 0 until they submit and you grade again.</p></div>`
    : `<div class="sheet empty"><h2>No code found</h2><p>Open the PDF to check what was submitted. You can set a score by hand above.</p></div>`);

  if ((s.missing || []).length && s.status !== "NO_SUBMISSION") {
    $("#programs").insertAdjacentHTML("beforeend", `<section class="sheet qblock"><div class="qhead"><h3>No code found</h3>
      <span class="muted small">for question ${s.missing.map(esc).join(", ")}. If it is in the PDF (a screenshot the reader missed), type it in to grade it.</span></div>
      <div class="pad" style="display:flex;gap:8px;flex-wrap:wrap">${s.missing.map((q) => `<button class="btn small" data-fix="${esc(q)}" data-new>Add code for question ${esc(q)}</button>`).join("")}</div>
      <div data-code-new></div></section>`);
  }
  // the teacher's own copy of a question's code: typed over an OCR misreading, graded instead
  const waitJob = async (j, btn) => {
    if (btn) btn.textContent = "Grading…";
    for (let i = 0; i < 300; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const nj = await api(`/jobs/${j.id}`);
      if (nj.status === "done" || nj.status === "failed") { toast(nj.status === "done" ? "Graded again." : nj.message, nj.status !== "done"); break; }
    }
    render();
  };
  $$("[data-fix]").forEach((b) => (b.onclick = () => {
    const q = b.dataset.fix;
    const prog = s.programs.find((p) => p.question === q);
    const box = b.hasAttribute("data-new") ? $("[data-code-new]") : $(`[data-code="${CSS.escape(q)}"]`);
    const code = prog ? prog.code : "";
    box.innerHTML = `<div class="fix">${b.hasAttribute("data-new") ? `<div class="k small" style="font-weight:600;margin:12px 0 6px">Question ${esc(q)}</div>` : ""}
      <textarea class="code-edit" rows="${Math.min(30, Math.max(8, code.split("\n").length + 2))}" spellcheck="false" aria-label="Code for question ${esc(q)}">${esc(code)}</textarea>
      <p class="muted small">Correct what was misread (compare with Open PDF), then grade again. Your version is kept for every later grading.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn small primary" data-save>Save and grade again</button>
        <button class="btn small ghost" data-cancel>Cancel</button>
        ${prog && prog.fixed ? `<button class="btn small ghost" data-undo>Use the code from the PDF</button>` : ""}</div></div>`;
    const ta = $("textarea", box);
    ta.focus();
    ta.addEventListener("keydown", (e) => {          // Tab indents instead of leaving the box
      if (e.key !== "Tab") return;
      e.preventDefault();
      ta.setRangeText("    ", ta.selectionStart, ta.selectionEnd, "end");
    });
    const send = (code, btn) => act(btn, async () => waitJob(await api(`/submissions/${id}/code`, { method: "PUT", body: { question: q, code } }), btn));
    $("[data-save]", box).onclick = (e) => { if (!ta.value.trim()) return toast("Type the code first.", true); send(ta.value, e.target); };
    $("[data-cancel]", box).onclick = () => render();
    const undo = $("[data-undo]", box);
    if (undo) undo.onclick = (e) => send(null, e.target);
  }));
  $$("[data-run]").forEach((h) => (h.onclick = () => h.nextElementSibling.classList.toggle("hidden")));
  $("#regrade").onclick = (e) => act(e.target, async () => waitJob(await api(`/submissions/${id}/regrade`, { method: "POST" }), e.target));
  $("#reviewed").onclick = (e) => act(e.target, async () => { await api(`/submissions/${id}`, { method: "PATCH", body: { reviewed: !s.reviewed } }); render(); });
  $("#ovr").onsubmit = (e) => { e.preventDefault(); act(null, async () => {
    const v = e.target.score.value;
    if (v === "") return toast("Type a score first.", true);
    await api(`/submissions/${id}`, { method: "PATCH", body: { override_score: +v, reviewed: true } });
    toast("Score saved."); render();
  }); };
  const clr = $("#clr");
  if (clr) clr.onclick = () => act(clr, async () => { await api(`/submissions/${id}`, { method: "PATCH", body: { clear_override: true } }); render(); });
  $("#copyfb").onclick = async () => {
    const box = $("#fb");
    try { await navigator.clipboard.writeText(box.value); }
    catch { box.select(); document.execCommand("copy"); }
    toast("Feedback copied. Paste it into the private comment in Classroom.");
  };
  $("#note").onchange = (e) => act(null, async () => { await api(`/submissions/${id}`, { method: "PATCH", body: { override_note: e.target.value } }); toast("Note saved."); });
}

// ------------------------------------------------------------------ student
// one student across every assignment: who is slipping, who jumped suddenly
async function viewStudent(id) {
  const d = await api(`/students/${id}`);
  const who = person(d.student.name);
  const rows = d.rows;
  const pct = (v, max) => (v === null || v === undefined || !max ? null : Math.max(0, Math.min(100, (100 * v) / max)));
  const scored = rows.filter((r) => r.status !== "ERROR" && r.final_score !== null);
  const mine = scored.map((r) => pct(r.final_score, r.assignment.max_points));
  const theirs = scored.filter((r) => r.class_avg !== null).map((r) => pct(r.class_avg, r.assignment.max_points));
  const mean = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);
  const missed = rows.filter((r) => r.status === "NO_SUBMISSION").length;
  const review = rows.filter((r) => r.needs_review).length;
  const status = (r) => r.status === "NO_SUBMISSION" ? `<span class="flag">Not submitted</span>`
    : r.status === "ERROR" && r.final_score === null ? `<span class="flag red">Couldn't grade</span>`
    : r.needs_review ? `<span class="flag mark">Needs review</span>` : "";
  view().innerHTML = `
    <div class="topline"><div class="grow">
      <div class="crumb">Student</div>
      <h1>${esc(who.name)}</h1>
      <div class="muted small" style="margin-top:6px">${who.roll ? `${esc(who.roll)}, ` : ""}${esc(d.student.email)}</div>
    </div></div>
    <div class="sheet summary">
      <div><div class="v">${mean(mine) === null ? "–" : `<span data-count="${mean(mine)}" data-dec="0">${Math.round(mean(mine))}</span>%`}</div><div class="k">average score</div></div>
      <div><div class="v">${mean(theirs) === null ? "–" : `${Math.round(mean(theirs))}%`}</div><div class="k">class average, same assignments</div></div>
      <div><div class="v">${rows.length - missed}<span class="muted" style="font-size:15px;font-weight:500"> / ${rows.length}</span></div><div class="k">turned in</div></div>
      <div class="${review ? "review" : ""}"><div class="v">${review}</div><div class="k">need your review</div></div>
    </div>
    <div class="sheet table-wrap"><table class="register student-rows">
      <thead><tr><th>Assignment</th><th class="num">Score</th><th class="hide-sm">Against the class</th><th class="hide-sm">Status</th></tr></thead>
      <tbody>${rows.map((r) => {
        const p = pct(r.final_score, r.assignment.max_points), c = pct(r.class_avg, r.assignment.max_points);
        const none = r.status === "NO_SUBMISSION" || p === null;
        return `<tr class="row" data-href="#/s/${r.submission_id}">
          <td><div class="name">${esc(r.assignment.title)}</div><div class="email">${esc(r.course)}</div></td>
          <td class="num">${none ? `<span class="qres none">—</span>` : `<span class="score">${fmt(r.final_score)}</span><span class="score"><span class="of"> / ${fmt(r.assignment.max_points)}</span></span>`}</td>
          <td class="hide-sm">${none ? "" : `<div class="vs" title="${Math.round(p)}%${c !== null ? `; class average ${Math.round(c)}%` : ""}"><i class="${c !== null && p < c - 15 ? "low" : ""}" style="width:${p}%"></i>${c !== null ? `<b style="left:${c}%"></b>` : ""}</div>`}</td>
          <td class="hide-sm"><span class="status">${status(r)}${r.late ? `<span class="flag blue">Late</span>` : ""}</span></td></tr>`;
      }).join("")}</tbody></table></div>
    <p class="muted small">The bar is this student's score; the white mark is the class average. A red bar is 15 points or more below the class.</p>`;
  rowLinks();
}

// ------------------------------------------------------------------ status
async function viewStatus() {
  const s = await api("/status");
  const h = await api("/health");
  const row = (name, ok, detail) => `<tr><td class="name">${name}</td><td><span class="dot ${ok ? "ok" : "bad"}"></span>${ok ? "Working" : "Not working"}</td><td class="muted small">${detail}</td></tr>`;
  const imgs = s.sandbox.images ? Object.entries(s.sandbox.images).map(([k, v]) => `${LANG[k] || k} ${v ? "ready" : "<b style='color:var(--fail)'>image missing, run make images</b>"}`).join(", ") : esc(s.sandbox.error || "");
  view().innerHTML = `<h1 style="margin-bottom:16px">Services</h1>
    <div class="sheet table-wrap"><table class="register"><tbody>
      ${row("Google Classroom", s.classroom.ok, s.classroom.ok ? (s.classroom.mode === "demo" ? "Demo classroom with sample students. Set CLASSROOM_MODE=google to use your real courses." : "Connected to your Google account.") : esc(s.classroom.error))}
      ${row("Code sandbox", !!s.sandbox.ok, s.sandbox.ok ? `${s.sandbox.backend === "docker" ? "Isolated Docker containers" : "<b style='color:var(--fail)'>Unsafe local mode, for development only</b>"}. ${imgs}` : esc(s.sandbox.error))}
      ${row("Database", h.database === "ok", h.database === "ok" ? "Connected." : esc(h.database))}
    </tbody></table></div>`;
}

// ------------------------------------------------------------------ admin
const ago = (iso) => {
  if (!iso) return "never";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 2 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`;
};
async function viewAdmin() {
  const [users, courses] = await Promise.all([api("/admin/users"), api("/admin/courses")]);
  const pending = users.filter((u) => u.status === "pending").length;
  const status = (u) => u.status === "pending" ? `<span class="flag mark">Waiting for you</span>`
    : u.status === "disabled" ? `<span class="flag red">Switched off</span>` : `<span class="flag green">Active</span>`;
  const actions = (u) => {
    if (u.id === state.me.id) return `<span class="muted small">You</span>`;
    const b = [];
    if (u.status !== "active") b.push(`<button class="btn small primary" data-u="${u.id}" data-set='{"status":"active"}'>${u.status === "pending" ? "Approve" : "Switch on"}</button>`);
    if (u.status !== "disabled") b.push(`<button class="btn small ghost danger" data-u="${u.id}" data-set='{"status":"disabled"}'>${u.status === "pending" ? "Refuse" : "Switch off"}</button>`);
    if (u.status === "active" && !u.fixed_admin) b.push(u.role === "admin"
      ? `<button class="btn small ghost" data-u="${u.id}" data-set='{"role":"teacher"}'>Remove admin</button>`
      : `<button class="btn small ghost" data-u="${u.id}" data-set='{"role":"admin"}'>Make admin</button>`);
    return `<div class="admin-actions">${b.join("")}</div>`;
  };
  view().innerHTML = `<div class="topline"><div class="grow"><h1>Admin</h1>
      <p class="muted" style="margin:6px 0 0">${users.length} teacher(s)${pending ? `, <b>${pending} waiting for your approval</b>` : ""}, ${courses.length} course(s).</p></div></div>
    <section class="sheet" style="margin-bottom:16px">
      <div class="pad" style="border-bottom:1px solid var(--rule-2)"><h2>Teachers</h2>
        <div class="muted small">Colleagues appear here after they sign in with Google. Each one sees only the courses they teach.</div></div>
      <div class="table-wrap"><table class="register"><thead><tr><th>Teacher</th><th>Status</th><th class="num">Courses</th><th class="num">Grading runs</th><th>Last seen</th><th></th></tr></thead><tbody>
      ${users.map((u) => `<tr><td class="name">${esc(u.name || u.email)} ${u.role === "admin" ? `<span class="role">admin</span>` : ""}
          <div class="muted small">${esc(u.email)}${u.google ? "" : (u.email.endsWith("@local") ? " (password sign-in)" : " · Google not connected")}</div></td>
        <td>${status(u)}</td><td class="num">${u.courses}</td><td class="num">${u.grading_runs}</td>
        <td class="muted small">${ago(u.last_seen_at)}</td><td>${actions(u)}</td></tr>`).join("")}
      </tbody></table></div></section>
    <section class="sheet">
      <div class="pad" style="border-bottom:1px solid var(--rule-2)"><h2>All courses</h2>
        <div class="muted small">You can open any assignment to help out. Grades can be published only by the course's own teachers.</div></div>
      <div class="table-wrap"><table class="register"><thead><tr><th>Course</th><th>Teachers</th><th>Assignments</th></tr></thead><tbody>
      ${courses.map((c) => `<tr><td class="name">${esc(c.name)}${c.section ? `<div class="muted small">${esc(c.section)}</div>` : ""}</td>
        <td class="small">${c.teachers.map((t) => esc(t.name || t.email)).join(", ") || `<span class="muted">nobody</span>`}</td>
        <td class="small">${c.assignments.map((a) => `<a href="#/a/${a.id}">${esc(a.title)}</a>`).join(" · ") || `<span class="muted">none</span>`}</td></tr>`).join("")}
      </tbody></table></div></section>`;
  $$("[data-set]").forEach((btn) => (btn.onclick = () => act(btn, async () => {
    await api(`/admin/users/${btn.dataset.u}`, { method: "PATCH", body: JSON.parse(btn.dataset.set) });
    await render();
    refreshAdminCount();
  })));
}

// ------------------------------------------------------------------ boot
async function boot() {
  const err = location.hash.match(/^#\/signin-error\/(.*)$/);
  if (err) { history.replaceState(null, "", "#/"); return showLogin(decodeURIComponent(err[1])); }
  try { state.me = await api("/me"); } catch { return; }
  if (state.me.status !== "active") return showPending();
  $("#login").classList.add("hidden");
  $("#pending").classList.add("hidden");
  $("#app").classList.remove("hidden");
  renderMe();
  refreshAdminCount();
  await loadCourses();
  if (!state.courses.length) {   // first visit: load from Classroom automatically
    try { await api("/courses/sync", { method: "POST" }); await loadCourses(); } catch (e) { toast(e.message, true); }
  }
  checkServices();
  render();
}
boot();
