/* Estimation > Trello - core: sign-in, calls, state, routing, home page, header. */
"use strict";
const S = { me: null, boards: [], board: null, cards: {}, lists: [], filter: null, view: "board", poll: null,
            labelColors: [], canAdmin: false, openCard: null, side: null };
try { if (!sessionStorage.getItem("infinia_token") && localStorage.getItem("infinia_keep")) sessionStorage.setItem("infinia_token", localStorage.getItem("infinia_keep")); } catch (e) {}   // "Keep me signed in"
let TOKEN = sessionStorage.getItem("infinia_token") || null;

// ---------- tiny helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
function esc(s) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
function tip(t) { return `<span class="help-i in-label" tabindex="0" data-tip="${esc(t)}">i</span>`; }
function ic(name, cls = "") { return `<svg class="i ${cls}"><use href="#i-${name}"/></svg>`; }
function h(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function pad2(n) { return String(n).padStart(2, "0"); }
function isoDay(d) { return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; }      // never toISOString (Dubai)
function nowLocal() { return new Date(); }
function parseDue(s) { if (!s) return null; const [d, t] = s.split("T"); const [y, m, dd] = d.split("-").map(Number); const [hh, mm] = (t || "00:00").split(":").map(Number); return new Date(y, m - 1, dd, hh || 0, mm || 0); }
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// Every date on screen reads dd/mm/yyyy (30/10/2026); with a time, dd/mm/yyyy HH:mm (24h).
function dmy(d) { return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`; }
function fmtDue(s, withTime = true) {
  const d = parseDue(s); if (!d) return "";
  const t = withTime && s.includes("T") ? ` ${pad2(d.getHours())}:${pad2(d.getMinutes())}` : "";
  return `${dmy(d)}${t}`;
}
function ago(iso) {
  if (!iso) return ""; const d = new Date(iso), s = (Date.now() - d) / 1000;
  if (s < 60) return "just now"; if (s < 3600) return `${Math.floor(s / 60)} minute${s < 120 ? "" : "s"} ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} hour${s < 7200 ? "" : "s"} ago`;
  if (s < 86400 * 2) return `yesterday at ${((d.getHours() + 11) % 12) + 1}:${pad2(d.getMinutes())} ${d.getHours() < 12 ? "AM" : "PM"}`;
  return `${dmy(d)} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
function dueState(c) {
  if (!c.due) return "";
  if (c.due_complete) return "done";
  const d = parseDue(c.due), n = new Date(), diff = d - n;
  if (diff < 0) return Math.abs(diff) > 86400000 ? "past" : "over";
  if (diff < 86400000) return "soon";
  return "";
}
const AV_COLORS = ["#0C66E4", "#1F845A", "#C25100", "#AE2E24", "#6E5DC6", "#227D9B", "#5B7F24", "#AE4787", "#626F86", "#943D73", "#216E4E", "#A54800"];
function avColor(id) { return AV_COLORS[Math.abs(Number(id) || 0) % AV_COLORS.length]; }
function person(id) { return (S.board && (S.board.people || []).find(p => p.id === id)) || (S.me && S.me.id === id ? S.me : null); }
function av(p, cls = "") { if (!p) return ""; return `<span class="av ${cls}" style="background:${avColor(p.id)}" title="${esc(p.name)} (${esc(p.username)})">${esc(p.initials)}</span>`; }
function labColor(c) { return c ? `var(--l-${c})` : "#DCDFE4"; }
function labDark(c) { return /_dark$/.test(c || "") || ["green_dark", "red_dark", "purple_dark", "blue_dark", "sky_dark", "lime_dark", "pink_dark", "black_dark", "orange_dark", "yellow_dark"].includes(c); }
function labHtml(l, cls = "") { return `<span class="lab ${labDark(l.color) ? "dk" : ""} ${cls}" style="background:${labColor(l.color)}" title="${esc((l.color || "no colour").replace("_", " ") + (l.name ? ': "' + l.name + '"' : ""))}">${esc(l.name || "")}</span>`; }

// Board backgrounds: Trello's colours and gradients.
const BG = {
  blue: "#0079BF", orange: "#D29034", green: "#519839", red: "#B04632", purple: "#89609E", pink: "#CD5A91", lime: "#4BBF6B", sky: "#00AEFF", grey: "#838C91",
  g_snow: "linear-gradient(135deg,#E2E8F0 0%,#CBD5E1 100%)", g_ocean: "linear-gradient(135deg,#0C66E4 0%,#37B4C3 100%)",
  g_crystal: "linear-gradient(135deg,#09326C 0%,#0C66E4 100%)", g_rainbow: "linear-gradient(135deg,#6F5ED3 0%,#E774BB 50%,#F5CD47 100%)",
  g_peach: "linear-gradient(135deg,#F87168 0%,#FCA700 100%)", g_flower: "linear-gradient(135deg,#E774BB 0%,#943D73 100%)",
  g_earth: "linear-gradient(135deg,#1F845A 0%,#5B7F24 100%)", g_alien: "linear-gradient(135deg,#22A06B 0%,#6CC3E0 100%)",
  g_volcano: "linear-gradient(135deg,#5D1F1A 0%,#C9372C 100%)", g_night: "linear-gradient(135deg,#1D2125 0%,#44546F 100%)",
  g_dusk: "linear-gradient(135deg,#352C63 0%,#AE4787 100%)", g_mint: "linear-gradient(135deg,#B3DF72 0%,#4BCE97 100%)",
};
function bgCss(bg, url) {
  if (url) return `#334 url("${url}") center/cover`;
  if (!bg) return BG.blue;
  if (bg.startsWith("c:")) return bg.slice(2);
  if (bg.startsWith("img:")) return `#334 url("${bg.slice(4)}") center/cover`;
  if (window.ANIM_BG && ANIM_BG[bg]) return ANIM_BG[bg].thumb;      // a live wallpaper: its colours, under the moving layer
  return BG[bg] || BG.blue;
}
function bgBase(bg) {   // a flat colour close to the background, for the header and the logo
  if (!bg) return "#0079BF"; if (bg.startsWith("c:")) return bg.slice(2);
  const v = BG[bg] || (window.ANIM_BG && ANIM_BG[bg] ? ANIM_BG[bg].thumb : ""); const m = v.match(/#[0-9A-Fa-f]{6}/); return m ? m[0] : "#1D2125";
}
function shade(hex, f) { // darken (f<0) / lighten
  const n = parseInt(hex.slice(1), 16); let r = n >> 16, g = (n >> 8) & 255, b = n & 255;
  const t = f < 0 ? 0 : 255, p = Math.abs(f);
  r = Math.round((t - r) * p + r); g = Math.round((t - g) * p + g); b = Math.round((t - b) * p + b);
  return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}

// ---------- calls ----------
async function api(path, opt = {}) {
  const headers = Object.assign({}, opt.headers || {});
  if (TOKEN) headers.Authorization = "Bearer " + TOKEN;
  let body = opt.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") { body = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, { method: opt.method || (body ? "POST" : "GET"), headers, body });
  if (res.status === 401) { signIn(); throw new Error("Please sign in again."); }
  if (!res.ok) {
    let msg = "Something went wrong.";
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : msg; } catch (e) { if (res.status === 413) msg = "That file is too big for the server."; }
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}
const GET = p => api(p), POST = (p, b) => api(p, { method: "POST", body: b || {} }), PATCH = (p, b) => api(p, { method: "PATCH", body: b }),
      DEL = p => api(p, { method: "DELETE" }), PUT = (p, b) => api(p, { method: "PUT", body: b });
function toast(msg, opts = {}) {
  $$(".toast").forEach(t => t.remove());
  const t = h(`<div class="toast ${opts.err ? "err" : ""}"><span></span>${opts.undo ? '<a data-u>Undo</a>' : ""}</div>`);
  t.querySelector("span").textContent = msg; document.body.appendChild(t);
  if (opts.undo) t.querySelector("[data-u]").onclick = () => { t.remove(); opts.undo(); };
  setTimeout(() => t.remove(), opts.ms || (opts.undo ? 6000 : 3000));
}
function fail(e) { toast(e && e.message ? e.message : String(e), { err: true }); }
async function copyText(t, what = "Copied") { try { await navigator.clipboard.writeText(t); toast(what + " to clipboard"); } catch (e) { const ta = h("<textarea></textarea>"); ta.value = t; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); toast(what + " to clipboard"); } }
function cardUrl(bid, cid) { return location.origin + "/portal/boards.html#/b/" + bid + (cid ? "/c/" + cid : ""); }
function appLink(bid, cid) { return location.origin + "/?p=estimation#boards" + (bid ? ":b" + bid + (cid ? "c" + cid : "") : ""); }

// ---------- sign in ----------
function signIn() {
  TOKEN = null; sessionStorage.removeItem("infinia_token");
  if (window.PG_EMBED) { try { parent.postMessage("pg-signin", location.origin); } catch (e) {} return; }
  $("#login").classList.remove("hide"); $("#lg-u").focus();
}
async function doLogin() {
  $("#lg-e").textContent = "";
  try {
    const r = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: $("#lg-u").value.trim(), password: $("#lg-p").value }) });
    if (!r.ok) { $("#lg-e").textContent = "Wrong username or password."; return; }
    TOKEN = (await r.json()).access_token; sessionStorage.setItem("infinia_token", TOKEN);
    $("#login").classList.add("hide"); start();
  } catch (e) { $("#lg-e").textContent = "Could not reach the server."; }
}

// ---------- routing ----------
function route() {
  const m = location.hash.match(/^#\/b\/(\d+)(?:\/c\/(\d+))?(?:\?view=(\w+))?/);
  closePops(); { const qe = $("#qe"); if (qe) qe.remove(); }
  if (m) {
    const bid = +m[1];
    const v = m[3] || (m[2] ? S.view : "board");
    if (!S.board || S.board.id !== bid) { closeCardModal(true); S.view = v; openBoard(bid, m[2] ? +m[2] : null); }
    else {
      if (m[2]) openCardModal(+m[2]); else closeCardModal(true);
      if (v !== S.view) { S.view = v; renderHeader(); renderView(); }
    }
  } else {
    const t = (location.hash.match(/^#\/(templates|home)/) || [])[1] || "boards";
    closeCardModal(true);
    showHome(t);
  }
}
function go(hash) { if (location.hash !== hash) location.hash = hash; else route(); }
window.addEventListener("hashchange", route);
// The app (parent frame) can send us somewhere: "b12c40" from a bell click.
window.addEventListener("message", e => {
  if (e.origin === location.origin && e.data && e.data.kb === "full") { document.body.classList.toggle("kb-full", !!e.data.on); if (S.board) renderHeader(); return; }
  if (e.origin !== location.origin || typeof e.data !== "object" || !e.data || e.data.kb !== "go") return;
  const m = String(e.data.target || "").match(/b(\d+)(?:c(\d+))?/);
  if (m) go(`#/b/${m[1]}${m[2] ? "/c/" + m[2] : ""}`);
});

// ---------- start ----------
async function BOOT() {
  $("#lg-go").onclick = doLogin; $("#lg-p").onkeydown = e => { if (e.key === "Enter") doLogin(); };
  if (!TOKEN) { signIn(); return; }
  start();
}
async function start() {
  try {
    const d = await GET("/store/kb/boards");
    S.me = d.me; S.boards = d.boards; S.labelColors = d.label_colors; S.canAdmin = d.can_admin;
  } catch (e) {
    if (/sign in/i.test(e.message)) return;
    document.body.innerHTML = `<div class="empty" style="margin-top:80px"><b>Trello is not open to this login</b>${esc(e.message)}<br><br>Ask an admin to tick <b>Estimation &gt; Trello</b> on Settings &gt; Access.</div>`;
    return;
  }
  $("#hdr").classList.remove("hide"); $("#dock").classList.remove("hide");
  buildHeader();
  route();
  setInterval(pollNotes, 30000); pollNotes();
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollNotes(); });
  document.addEventListener("keydown", keys);
}

// ---------- header ----------
function buildHeader() {
  $("#hb-me").innerHTML = av(S.me, "lg").replace('class="av lg"', 'class="av"');
  $("#go-home").onclick = () => go("#/");
  $("#hb-boards").onclick = e => boardsPop(e.currentTarget, "all");
  $("#hb-recent").onclick = e => boardsPop(e.currentTarget, "recent");
  $("#hb-starred").onclick = e => boardsPop(e.currentTarget, "starred");
  $("#hb-templates").onclick = e => boardsPop(e.currentTarget, "templates");
  $("#hb-create").onclick = e => createPop(e.currentTarget);
  $("#hb-notes").onclick = e => notesPop(e.currentTarget);
  $("#hb-help").onclick = () => shortcutsDlg();
  $("#hb-me").onclick = e => mePop(e.currentTarget);
  const q = $("#q"), res = $("#srch-res");
  const run = debounce(async () => {
    const v = q.value.trim(); if (!v) { res.classList.add("hide"); return; }
    try {
      const d = await GET("/store/kb/search?q=" + encodeURIComponent(v));
      res.innerHTML = (d.cards.length ? "<h4>Cards</h4>" + d.cards.map(c => `<div class="r" data-c="${c.id}" data-b="${c.board_id}"><span class="bgsw" style="background:var(--neutral);display:flex;align-items:center;justify-content:center">${ic("board", "s14")}</span><div><b>${esc(c.title)}</b><small>#${c.no} · ${esc(c.board)}: ${esc(c.list)}${c.closed ? " · archived" : ""}</small></div></div>`).join("") : "")
        + (d.boards.length ? "<h4>Boards</h4>" + d.boards.map(b => `<div class="r" data-b="${b.id}"><span class="bgsw" style="background:${bgCss(b.bg)}"></span><div><b>${esc(b.title)}</b></div></div>`).join("") : "")
        || `<div class="empty" style="padding:16px">Nothing found for "${esc(v)}"</div>`;
      res.classList.remove("hide");
      $$(".r", res).forEach(r => r.onclick = () => { res.classList.add("hide"); q.value = ""; go(`#/b/${r.dataset.b}${r.dataset.c ? "/c/" + r.dataset.c : ""}`); });
    } catch (e) { fail(e); }
  }, 180);
  q.oninput = run; q.onfocus = run;
  q.onkeydown = e => {
    const rows = $$(".r", res); let i = rows.findIndex(r => r.classList.contains("sel"));
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); rows.forEach(r => r.classList.remove("sel")); i = e.key === "ArrowDown" ? Math.min(rows.length - 1, i + 1) : Math.max(0, i - 1); if (rows[i]) rows[i].classList.add("sel"); }
    if (e.key === "Enter" && rows.length) (rows[i] || rows[0]).click();
    if (e.key === "Escape") { res.classList.add("hide"); q.blur(); }
  };
  document.addEventListener("mousedown", e => { if (!e.target.closest(".srch")) res.classList.add("hide"); });
  $("#dk-inbox").onclick = () => sidePanel("inbox");
  $("#dk-planner").onclick = () => sidePanel("planner");
  $("#dk-board").onclick = () => sidePanel(null);
  $("#dk-switch").onclick = e => boardsPop(e.currentTarget, "switch");
}
async function pollNotes() {
  if (document.hidden) return;                 // a tab in the background does not ask
  try {
    const d = await GET("/store/kb/notes");
    const btn = $("#hb-notes"); let dot = btn.querySelector(".badge-dot");
    if (d.unread) { if (!dot) { dot = h('<span class="badge-dot"></span>'); btn.appendChild(dot); } dot.textContent = d.unread > 9 ? "9+" : d.unread; }
    else if (dot) dot.remove();
    S.notes = d;
  } catch (e) {}
}

// ---------- home ----------
async function refreshBoards() { const d = await GET("/store/kb/boards"); S.boards = d.boards; return d; }
async function showHome(tab = "boards") {
  stopPoll(); S.board = null; document.body.classList.remove("on-board"); document.body.style.removeProperty("--hdr-bg");
  $("#board").classList.add("hide"); const home = $("#home"); home.classList.remove("hide");
  $("#dk-board").classList.toggle("on", !S.side);
  try { await refreshBoards(); } catch (e) { fail(e); }
  const open = S.boards.filter(b => !b.closed && !b.is_template), tpls = S.boards.filter(b => b.is_template && !b.closed);
  const starred = open.filter(b => b.starred), recent = [...open].filter(b => b.seen).sort((a, b) => b.seen.localeCompare(a.seen)).slice(0, 4);
  const closed = S.boards.filter(b => b.closed);
  const tile = b => `<div class="tile" data-b="${b.id}"><div class="tb" style="background:${bgCss(b.bg, b.bg_url)}">${b.visibility === "private" ? `<span class="tag">${ic("lock", "s12")} Private</span>` : ""}</div><div class="tt">${esc(b.title)}</div><button class="st ${b.starred ? "on" : ""}" data-star="${b.id}" title="${b.starred ? "Unstar" : "Star"} this board"><svg class="i ${b.starred ? "f" : ""}"><use href="#i-star"/></svg></button></div>`;
  const nav = `<nav class="home-nav">
      <div class="ni ${tab === "boards" ? "on" : ""}" data-go="#/">${ic("board")} Boards</div>
      <div class="ni ${tab === "templates" ? "on" : ""}" data-go="#/templates">${ic("tpl")} Templates</div>
      <div class="ni ${tab === "home" ? "on" : ""}" data-go="#/home">${ic("act")} Home</div>
      <hr><div class="muted" style="padding:0 8px 6px;font-weight:600">Workspaces</div>
      <div class="ws"><span class="wl">I</span> Infinia Estimation</div>
      <div class="sub" data-go="#/">Boards</div><div class="sub" data-act="members">Members</div><div class="sub" data-act="import">Import from Trello</div>
    </nav>`;
  let main = "";
  if (tab === "templates") {
    main = `<section><h3>${ic("tpl", "s20")} Board templates</h3><p class="muted" style="margin:-6px 0 14px">Start a new board from one of these. Make any board a template from its menu (… &gt; Settings &gt; Make template).</p>
      <div class="tiles">${tpls.map(tile).join("") || ""}${TEMPLATES.map((t, i) => `<div class="tile" data-tpl="${i}"><div class="tb" style="background:${bgCss(t.bg)}"><span class="tag">Template</span></div><div class="tt">${esc(t.title)}</div></div>`).join("")}</div></section>`;
  } else if (tab === "home") {
    const due = (S.notes && S.notes.due) || [];
    main = `<section><h3>${ic("clock", "s20")} Up next</h3>${due.length ? due.map(d => `<div class="pl-card" data-gob="${d.board_id}" data-goc="${d.card_id}"><b>${esc(d.title)}</b><small>${esc(d.board)} · due ${fmtDue(d.due)} ${d.overdue ? "· overdue" : ""}</small></div>`).join("") : '<div class="muted">Nothing due in the next day on cards you are on.</div>'}</section>
      <section><h3>${ic("bell", "s20")} Activity for you</h3>${((S.notes && S.notes.notes) || []).slice(0, 20).map(n => `<div class="pl-card" data-gob="${n.board_id}" data-goc="${n.card_id || ""}"><b>${esc(n.who)}</b> ${esc(n.text)}<small>${esc(n.board)} · ${ago(n.at)}</small></div>`).join("") || '<div class="muted">Nothing yet.</div>'}</section>`;
  } else {
    main = (starred.length ? `<section><h3>${ic("star", "s20")} Starred boards</h3><div class="tiles">${starred.map(tile).join("")}</div></section>` : "")
      + (recent.length ? `<section><h3>${ic("clock", "s20")} Recently viewed</h3><div class="tiles">${recent.map(tile).join("")}</div></section>` : "")
      + `<section><h3><span class="wl" style="width:24px;height:24px;border-radius:4px;background:linear-gradient(#C0392B,#E74C3C);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:13px">I</span> YOUR BOARDS</h3>
          <div class="tiles">${open.map(tile).join("")}<div class="tile new" data-new="1">Create new board<small>Unlimited</small></div></div></section>`
      + (closed.length ? `<button class="b" data-closed="1">${ic("archive")} View closed boards (${closed.length})</button>` : "");
  }
  home.innerHTML = `<div class="home-wrap">${nav}<div class="home-main">${main}</div></div>`;
  $$("[data-go]", home).forEach(e => e.onclick = () => go(e.dataset.go));
  $$(".tile[data-b]", home).forEach(t => t.onclick = e => { if (e.target.closest("[data-star]")) return; go("#/b/" + t.dataset.b); });
  $$("[data-star]", home).forEach(s => s.onclick = async e => { e.stopPropagation(); try { await POST(`/store/kb/boards/${s.dataset.star}/star`); showHome(tab); } catch (er) { fail(er); } });
  $$("[data-new]", home).forEach(t => t.onclick = () => createBoardPop(t));
  $$("[data-tpl]", home).forEach(t => t.onclick = () => createBoardPop(t, TEMPLATES[+t.dataset.tpl]));
  $$("[data-gob]", home).forEach(t => t.onclick = () => go(`#/b/${t.dataset.gob}${t.dataset.goc ? "/c/" + t.dataset.goc : ""}`));
  const cl = $("[data-closed]", home); if (cl) cl.onclick = () => closedBoardsDlg();
  const im = $('[data-act="import"]', home); if (im) im.onclick = () => importDlg();
  const mb = $('[data-act="members"]', home); if (mb) mb.onclick = () => toast("Everyone with Estimation > Trello is in this workspace - no limit on members.");
}
// Ready-made board templates (Trello's most used ones, set for Infinia).
const TEMPLATES = [
  { title: "Project tracker (villa)", bg: "g_ocean", lists: ["Permits & NOCs", "Shoring & Excavation", "Structure", "MEP", "Finishes", "Snags", "Handover"] },
  { title: "Tenders & estimation", bg: "g_peach", lists: ["Enquiries", "Site visit", "BOQ in progress", "Submitted", "Negotiation", "Won", "Lost"] },
  { title: "Kanban", bg: "green", lists: ["Backlog", "To do", "Doing", "Review", "Done"] },
  { title: "Weekly planning", bg: "g_dusk", lists: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Next week"] },
  { title: "Procurement", bg: "g_earth", lists: ["Requested", "Quotes", "LPO issued", "Delivered", "Paid"] },
];

// ---------- polling (two people on one board) ----------
function startPoll() {
  stopPoll();
  S.poll = setInterval(async () => {
    if (!S.board || document.hidden || window.DRAG || pageBusy()) return;
    try {
      const v = await GET(`/store/kb/boards/${S.board.id}/version`);
      if (v.version !== S.board.version) {
        await reloadBoard(true);
        if (S.openCard) await loadFullCard(S.openCard, true);    // the open card follows too (not while typing on it)
      }
    } catch (e) {}
  }, 4000);
}
// Someone is typing or has a menu open: the board is not redrawn under them (Trello never does).
function pageBusy() {
  const a = document.activeElement;
  if (a && a !== document.body && (a.tagName === "TEXTAREA" || a.tagName === "SELECT" || a.isContentEditable || (a.tagName === "INPUT" && !["checkbox", "radio", "button"].includes(a.type)))) {
    if (!(a.closest && a.closest("#cm-ov"))) return true;      // typing on the open card is handled by the card itself
  }
  return !!$(".pop, .composer textarea, .lhd textarea, #qe, .bname-in");
}
function stopPoll() { if (S.poll) clearInterval(S.poll); S.poll = null; }

// ---------- keyboard shortcuts (Trello's) ----------
let HOVER_CARD = null, HOVER_LIST = null;
function keys(e) {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) {
    if (e.key === "Escape") { if (e.target.closest(".pop")) closePops(); else if (e.target.closest(".dlg")) e.target.closest(".dlg").remove(); else e.target.blur(); }
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === "Escape" && document.body.classList.contains("kb-full") && !$(".dlg") && !$(".pop") && !$("#qe") && !S.openCard && !$("#bmenu")) { try { parent.postMessage({ kb: "fullscreen" }, location.origin); } catch (er) {} return; }
  if (k === "Escape") { if ($(".dlg")) { $$(".dlg").forEach(d => d.remove()); return; } if ($(".pop")) closePops(); else if ($("#qe")) $("#qe").remove(); else if (S.openCard) go(`#/b/${S.board.id}`); else if ($("#bmenu")) $("#bmenu").remove(); else if (S.side) sidePanel(null); return; }
  if (k === "?") { shortcutsDlg(); return; }
  if (k === "/") { e.preventDefault(); $("#q").focus(); return; }
  if (k === "b") { e.preventDefault(); boardsPop($("#hb-boards"), "all"); return; }
  if (!S.board) return;
  if (k === "f") { e.preventDefault(); filterPop($("#bh-filter")); return; }
  if (k === "q") { toggleMyCards(); return; }
  if (k === "x") { clearFilter(); return; }
  if (k === "w") { boardMenu(); return; }
  if (k === ";") { document.body.classList.toggle("lab-open"); try { localStorage.setItem("kb_lab_open", document.body.classList.contains("lab-open") ? "1" : ""); } catch (er) {} return; }
  if (k === "n" && HOVER_LIST) { e.preventDefault(); openComposer(HOVER_LIST, HOVER_CARD); return; }
  const cid = S.openCard || HOVER_CARD; if (!cid) return;
  const anchor = S.openCard ? $(".cm .acts") : document.querySelector(`.card[data-c="${cid}"]`);
  if (k === "e" && !S.openCard && HOVER_CARD) { e.preventDefault(); quickEdit(HOVER_CARD); }
  else if (k === "l") { e.preventDefault(); labelsPop(anchor, cid); }
  else if (k === "m") { e.preventDefault(); membersPop(anchor, cid); }
  else if (k === "d") { e.preventDefault(); datesPop(anchor, cid); }
  else if (k === " ") { e.preventDefault(); toggleJoin(cid); }
  else if (k === "c") { archiveCard(cid); }
  else if (k === "t") { e.preventDefault(); if (!S.openCard) quickEdit(cid); }
  else if (k === "Enter" && !S.openCard) go(`#/b/${S.board.id}/c/${cid}`);
}
function shortcutsDlg() {
  const rows = [["b", "Open boards"], ["/", "Search"], ["f", "Filter cards"], ["q", "My cards"], ["x", "Clear filters"], ["w", "Board menu"],
    [";", "Show label text"], ["n", "Add card (under the mouse)"], ["e", "Quick edit card"], ["Enter", "Open card"], ["l", "Labels"], ["m", "Members"], ["d", "Dates"],
    ["Space", "Join / leave card"], ["c", "Archive card"], ["Esc", "Close"], ["?", "This list"]];
  dlg(`<h2><span>Keyboard shortcuts</span><button class="x" data-close>${ic("x")}</button></h2><div class="shortcut-grid">${rows.map(r => `<div><span class="kbd">${esc(r[0])}</span>${esc(r[1])}</div>`).join("")}</div>`);
}
function dlg(inner, width) {
  const d = h(`<div class="dlg"><div class="box" ${width ? `style="width:${width}px"` : ""}>${inner}</div></div>`);
  d.addEventListener("mousedown", e => { if (e.target === d) d.remove(); });
  $$("[data-close]", d).forEach(b => b.onclick = () => d.remove());
  document.body.appendChild(d); return d;
}
function confirmPop(anchor, title, text, okLabel, cb) {
  const p = pop(anchor, title, `<p style="margin:0 0 12px">${esc(text)}</p><button class="b dng" style="width:100%">${esc(okLabel)}</button>`);
  p.querySelector(".b.dng").onclick = () => { closePops(); cb(); };
}
