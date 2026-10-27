/* Estimation > Dashboard / Projects.
   One page, three views (?view=dash | projects | tenders), held in a frame by the app.
   Typing is kept to the numbers that cannot be picked: everything else is a pick,
   a click, or filled in from what is already known. */
"use strict";
try { if (!sessionStorage.getItem("infinia_token") && localStorage.getItem("infinia_keep")) sessionStorage.setItem("infinia_token", localStorage.getItem("infinia_keep")); } catch (e) {}
let TOKEN = sessionStorage.getItem("infinia_token") || null;
const VIEW = (location.search.match(/[?&]view=(\w+)/) || [])[1] || "dash";
const ST = { meta: null, pid: null, b: null, group: "home", sec: "dash", q: {}, filt: {}, dash: null, tenders: null };
if (window.PG_EMBED) document.body.classList.add("embed");

// ---------- small helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
function esc(s) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
function tip(t) { return `<span class="help-i in-label" tabindex="0" data-tip="${esc(t)}">i</span>`; }
function money(v, dash = true) { const n = Number(v || 0); if (!n && dash) return '<span class="muted">-</span>'; return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function m0(v) { const n = Number(v || 0); return n.toLocaleString("en-US", { maximumFractionDigits: 0 }); }
function aed(v) { return money(v, false); }      // full figures, as everywhere else in the app
function r2(x) { return Math.round((Number(x || 0) + Number.EPSILON) * 100) / 100; }
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dt(s) { if (!s) return ""; const [y, m, d] = s.slice(0, 10).split("-"); return `${+d}-${MON[+m - 1]}-${y.slice(2)}`; }
function today() { return (ST.meta && ST.meta.today) || new Date().toISOString().slice(0, 10); }
function pad(n, w = 3) { return String(n).padStart(w, "0"); }
function h(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }
function st(s) {
  const g = ["Paid", "Approved", "Claimed", "Closed", "Answered", "Won", "Completed", "Current", "Certified", "Certified at site", "Approved as noted", "✔"];
  const a = ["Submitted", "At site", "Pricing", "Invoiced", "Preparing", "Running", "MD approved"];
  const r = ["Rejected", "Lost", "Revise & resubmit", "Cancelled", "Overdue"];
  const b = ["Received", "Open", "Draft", "Identified", "Not started", "Absorbed", "Prepared", "CM approved", "Verified"];
  const k = g.includes(s) ? "g" : a.includes(s) ? "a" : r.includes(s) ? "r" : b.includes(s) ? "b" : "";
  return `<span class="st ${k}">${esc(s || "-")}</span>`;
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ---------- calls ----------
async function api(path, opt = {}) {
  const headers = {};
  if (TOKEN) headers.Authorization = "Bearer " + TOKEN;
  let body = opt.body;
  if (body && !(body instanceof FormData)) { body = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, { method: opt.method || (body ? "POST" : "GET"), headers, body });
  if (res.status === 401) { signIn(); throw new Error("Please sign in again."); }
  if (!res.ok) {
    let msg = "Something went wrong.";
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : msg; } catch (e) { if (res.status === 413) msg = "That file is too big."; }
    throw new Error(msg);
  }
  return res.json();
}
const GET = p => api(p), POST = (p, b) => api(p, { method: "POST", body: b || {} }), PATCH = (p, b) => api(p, { method: "PATCH", body: b }),
      DEL = p => api(p, { method: "DELETE" }), PUT = (p, b) => api(p, { method: "PUT", body: b });
function toast(msg, opts = {}) {
  $$(".toast").forEach(t => t.remove());
  const t = h(`<div class="toast ${opts.err ? "err" : ""}"><span></span>${opts.undo ? "<a data-u>Undo</a>" : ""}</div>`);
  t.querySelector("span").textContent = msg; document.body.appendChild(t);
  if (opts.undo) t.querySelector("[data-u]").onclick = () => { t.remove(); opts.undo(); };
  setTimeout(() => t.remove(), opts.ms || (opts.undo ? 6000 : 2600));
}
function fail(e) { toast(e && e.message ? e.message : String(e), { err: true }); }

// ---------- sign in ----------
function signIn() {
  TOKEN = null; sessionStorage.removeItem("infinia_token"); try { localStorage.removeItem("infinia_keep"); } catch (e) {}
  if (window.PG_EMBED) { try { parent.postMessage("pg-signin", location.origin); } catch (e) {} return; }
  $("#login").classList.remove("hide"); $("#lg-u").focus();
}
async function doLogin() {
  $("#lg-e").textContent = "";
  try {
    const r = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: $("#lg-u").value.trim(), password: $("#lg-p").value, remember: $("#lg-keep").checked ? "1" : "0" }) });
    if (!r.ok) { $("#lg-e").textContent = "Wrong username or password."; return; }
    TOKEN = (await r.json()).access_token; sessionStorage.setItem("infinia_token", TOKEN);
    try { const k = $("#lg-keep").checked; if (k) localStorage.setItem("infinia_keep", TOKEN); else localStorage.removeItem("infinia_keep"); localStorage.setItem("infinia_keep_tick", k ? "1" : "0"); } catch (e) {}
    $("#login").classList.add("hide"); start();
  } catch (e) { $("#lg-e").textContent = "Could not reach the server."; }
}
$("#lg-go").onclick = doLogin;
try { const t = localStorage.getItem("infinia_keep_tick"); if (t !== null) $("#lg-keep").checked = t === "1"; } catch (e) {}
$("#lg-p").onkeydown = e => { if (e.key === "Enter") doLogin(); };

// ---------- modal: a form built from a list of fields ----------
// field: {k, label, type: text|money|num|pct|date|select|combo|area|check, options, value, tip, full, hint, quick}
function fieldHtml(f) {
  const v = f.value ?? "";
  const lab = `<label for="f-${f.k}">${esc(f.label)}${f.tip ? " " + tip(f.tip) : ""}</label>`;
  let inp;
  const opts = (f.options || []).map(o => Array.isArray(o) ? o : [o, o]);
  if ((f.type === "seg" || (f.type === "select" && !f.noseg && opts.length >= 2 && opts.length <= 6 && opts.every(o => String(o[1]).length <= 24 && String(o[0]) !== "")))) {
    const cur = opts.some(o => String(o[0]) === String(v)) ? v : opts[0][0];
    inp = `<input type="hidden" id="f-${f.k}" value="${esc(cur)}"><div class="seg" data-segfor="${f.k}">${opts.map(([val, txt]) => `<button type="button" data-v="${esc(val)}" class="${String(val) === String(cur) ? "on" : ""}">${esc(txt)}</button>`).join("")}</div>`;
  }
  else if (f.type === "select") inp = `<select id="f-${f.k}">${(f.options || []).map(o => { const [val, txt] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(val)}" ${String(val) === String(v) ? "selected" : ""}>${esc(txt)}</option>`; }).join("")}</select>`;
  else if (f.type === "combo") inp = `<input id="f-${f.k}" list="dl-${f.k}" value="${esc(v)}" autocomplete="off" placeholder="${esc(f.ph || "Pick or type")}"><datalist id="dl-${f.k}">${(f.options || []).map(o => `<option value="${esc(o)}">`).join("")}</datalist>`;
  else if (f.type === "area") inp = `<textarea id="f-${f.k}" placeholder="${esc(f.ph || "")}">${esc(v)}</textarea>`;
  else if (f.type === "check") inp = `<label class="chk"><input type="checkbox" id="f-${f.k}" ${v ? "checked" : ""}> ${esc(f.text || "")}</label>`;
  else if (f.type === "date") inp = `<input id="f-${f.k}" type="date" value="${esc(v)}">`;
  else if (["money", "num", "pct"].includes(f.type)) inp = `<input id="f-${f.k}" class="money" inputmode="decimal" value="${v === "" || v === null ? "" : esc(v)}" placeholder="${f.ph || (f.type === "pct" ? "%" : "0.00")}">`;
  else inp = `<input id="f-${f.k}" value="${esc(v)}" placeholder="${esc(f.ph || "")}" autocomplete="off"${f.ro ? ' readonly tabindex="-1" style="background:#f3f4f6;color:#374151"' : ""}>`;
  const q = f.quick ? `<div class="quick">${f.quick.map((x, i) => `<button type="button" data-q="${f.k}:${i}">${esc(x[0])}</button>`).join("")}</div>` : "";
  return `<div class="f ${f.full || f.type === "area" ? "full" : ""}">${lab}${inp}${q}${f.hint ? `<div class="hint">${f.hint}</div>` : ""}</div>`;
}
// A click on a choice: it is the value; anything listening to the form hears it like typing.
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest(".seg button"); if (!b) return;
  const box = b.parentElement, inp = document.getElementById("f-" + box.dataset.segfor); if (!inp) return;
  e.preventDefault(); setField(box.dataset.segfor, b.dataset.v);
});
// Put a value in a form box - a text box, a list or a row of choices - and let the form know.
function setField(k, v) {
  const el = document.getElementById("f-" + k); if (!el) return;
  if (el.type === "checkbox") el.checked = !!v;
  else if (el.tagName === "SELECT" && v && ![...el.options].some(o => o.value === String(v))) { el.add(new Option(v, v)); el.value = v; }   // a value used before, not in the list
  else el.value = v ?? "";
  const box = document.querySelector(`.seg[data-segfor="${k}"]`);
  if (box) box.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === String(v)));
  el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
}
function readForm(fields) {
  const out = {};
  for (const f of fields) {
    const el = $("#f-" + f.k); if (!el) continue;
    if (f.type === "check") out[f.k] = el.checked;
    else if (["money", "num", "pct"].includes(f.type)) out[f.k] = el.value.replace(/,/g, "").trim();
    else out[f.k] = el.value.trim();
  }
  return out;
}
// ---------- one standard for leaving a screen with changes not saved ----------
// Pop-up forms, full pages with a Save: on Back / x / Cancel / Esc / clicking outside / phone Back,
// if anything typed differs from when the screen opened, ask: Stay / Leave without saving / Save & exit.
const GUARD = {};
function guardSnap(el) {
  if (!el) return "";
  return [...el.querySelectorAll("input,select,textarea")].filter(x => x.type !== "file" && x.type !== "search" && !x.closest("[data-noguard]"))
    .map(x => (x.type === "checkbox" || x.type === "radio") ? (x.checked ? "1" : "0") : x.value).join("\u0001");
}
function guardOn(layer, el, save) {
  const g = GUARD[layer] = { el, save, base: guardSnap(el), touched: false };
  // figures filled in by the screen itself just after it opens are not the person's changes
  if (!el._guardT) { el._guardT = 1; const t = e => { const c = GUARD[layer]; if (e.isTrusted && c && c.el === el) c.touched = true; };
    el.addEventListener("input", t, true); el.addEventListener("change", t, true); }
  [300, 900, 1800].forEach(ms => setTimeout(() => { if (GUARD[layer] === g && !g.touched) g.base = guardSnap(el); }, ms));
}
function guardBase(layer) { const g = GUARD[layer]; if (g) g.base = guardSnap(g.el); }
function guardOff(layer) { delete GUARD[layer]; }
function guardDirty(layer) { const g = GUARD[layer]; return !!g && g.el && g.el.isConnected && guardSnap(g.el) !== g.base; }
function askLeave() {
  return new Promise(res => {
    let el = document.getElementById("leave");
    if (!el) {
      el = document.createElement("div"); el.id = "leave"; el.className = "hide";
      el.innerHTML = `<div class="lbox" role="dialog" aria-modal="true" aria-labelledby="lv-t"><h3 id="lv-t">Unsaved changes</h3>
        <p>You have changes on this screen that are not saved yet. Do you want to save them before leaving?</p>
        <div class="lfoot"><button class="btn btn-ghost left" id="lv-drop">Leave without saving</button><button class="btn btn-plain" id="lv-stay">Stay</button><button class="btn btn-primary" id="lv-save">Save &amp; exit</button></div></div>`;
      document.body.appendChild(el);
    }
    const done = v => { el.classList.add("hide"); document.removeEventListener("keydown", key, true); res(v); };
    const key = e => { if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); done("stay"); } };
    $("#lv-drop").onclick = () => done("drop"); $("#lv-stay").onclick = () => done("stay"); $("#lv-save").onclick = () => done("save");
    el.onmousedown = e => { if (e.target === el) done("stay"); };
    document.addEventListener("keydown", key, true);
    el.classList.remove("hide"); setTimeout(() => $("#lv-save").focus(), 20);
  });
}
// go() leaves the screen; it runs straight away when nothing was changed.
async function guardLeave(layer, go) {
  if (guardDirty(layer)) {
    const a = await askLeave();
    if (a === "stay") return false;
    if (a === "save") { const g = GUARD[layer]; const ok = g && g.save ? await g.save(true) : true; if (ok === false) return false; if (layer === "modal") { guardOff(layer); return true; } }
  }
  guardOff(layer); go(); return true;
}
// the phone / browser closes or reloads with something not saved
addEventListener("beforeunload", e => { if (Object.keys(GUARD).some(guardDirty)) { e.preventDefault(); e.returnValue = ""; } });
// the main app asks before moving to another page or tab while something here is not saved
window.estHasUnsaved = () => Object.keys(GUARD).some(guardDirty);
window.estLeaveAll = async () => {
  if (guardDirty("modal") && !(await closeModal())) return false;
  if (guardDirty("big") && typeof leaveBig === "function" && !(await leaveBig())) return false;
  return true;
};

function modal(title, fields, onSave, opts = {}) {
  $("#m-title").textContent = title;
  $("#m-body").innerHTML = (opts.top || "") + `<div class="frm">${fields.map(fieldHtml).join("")}</div>` + (opts.bottom || "");
  $("#m-foot").innerHTML = (opts.del ? `<button class="btn btn-ghost left" id="m-del">Delete</button>` : "") +
    (opts.extra || "") + `<button class="btn btn-plain" id="m-cancel">Cancel</button><button class="btn btn-primary" id="m-save">${esc(opts.save || "Save")}</button>`;
  $(".mbox").classList.toggle("wide", !!opts.wide);
  $("#modal").classList.remove("hide");
  fields.forEach(f => (f.quick || []).forEach((x, i) => { const b = $(`[data-q="${f.k}:${i}"]`); if (b) b.onclick = () => { x[1]($("#f-" + f.k)); if (opts.live) opts.live(); }; }));
  if (opts.live) { $$("#m-body input, #m-body select").forEach(el => el.addEventListener("input", opts.live)); opts.live(); }
  const first = fields.find(f => f.focus) || fields.find(f => ["money", "num"].includes(f.type) && !f.value) || null;
  setTimeout(() => { const el = first && $("#f-" + first.k); if (el) { el.focus(); el.select && el.select(); } }, 30);
  const save = async () => {
    const btn = $("#m-save"); btn.disabled = true;
    try { await onSave(readForm(fields)); guardOff("modal"); closeModal(true); return true; } catch (e) { fail(e); return false; } finally { btn.disabled = false; }
  };
  $("#m-save").onclick = save;
  $("#m-cancel").onclick = () => closeModal();
  if (opts.del) $("#m-del").onclick = async () => { if (!(await confirmDelete(`Delete - ${title}?`, opts.delWhat || ""))) return; try { await opts.del(); guardOff("modal"); closeModal(true); toast("Deleted"); } catch (e) { fail(e); } };
  if (opts.after) opts.after();
  if (opts.doc) docBar(opts.doc);
  // a form with nothing to save (save: "-") never asks
  if (opts.save === "-" || $("#m-save").disabled) guardOff("modal"); else guardOn("modal", $("#m-body"), save);
  $$("#m-body input").forEach(el => el.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } }));
}
// The one confirmation box for every delete in Estimation: says what goes, Cancel / Delete (red).
function confirmDelete(title, detail = "", ok = "Delete") {
  return new Promise(res => {
    let el = document.getElementById("cfm");
    if (!el) {
      el = document.createElement("div"); el.id = "cfm"; el.className = "hide";
      el.innerHTML = `<div class="lbox" role="alertdialog" aria-modal="true" aria-labelledby="cfm-t"><h3 id="cfm-t"></h3><p id="cfm-d"></p>
        <div class="lfoot"><button class="btn btn-plain" id="cfm-no">Cancel</button><button class="btn btn-danger" id="cfm-ok"></button></div></div>`;
      document.body.appendChild(el);
    }
    $("#cfm-t").textContent = title;
    $("#cfm-d").innerHTML = (detail ? detail + "<br>" : "") + '<span class="muted">This cannot be undone.</span>';
    $("#cfm-ok").textContent = ok;
    const done = v => { el.classList.add("hide"); document.removeEventListener("keydown", key, true); res(v); };
    const key = e => { if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); done(false); } };
    $("#cfm-no").onclick = () => done(false); $("#cfm-ok").onclick = () => done(true);
    el.onmousedown = e => { if (e.target === el) done(false); };
    document.addEventListener("keydown", key, true);
    el.classList.remove("hide"); setTimeout(() => $("#cfm-no").focus(), 20);
  });
}
// (old) A remove button asks once by changing its words - kept only for anything not moved over yet.
function confirmInline(btn) {
  if (btn.dataset.sure) return true;
  btn.dataset.sure = "1"; const t = btn.textContent; btn.textContent = "Press again to remove"; btn.classList.add("btn-primary");
  setTimeout(() => { if (btn.isConnected) { btn.dataset.sure = ""; btn.textContent = t; btn.classList.remove("btn-primary"); } }, 3500);
  return false;
}
// closeModal(true) = closed by the code after a save; closeModal() = the person closing it - asks if anything is unsaved
function closeModal(force) {
  if (force === true) { guardOff("modal"); $("#modal").classList.add("hide"); return; }
  return guardLeave("modal", () => $("#modal").classList.add("hide"));
}
$("#m-x").onclick = () => closeModal();
$("#modal").addEventListener("mousedown", e => { if (e.target.id === "modal") closeModal(); });
function drawer(title, html) {
  const was = !$("#drawer").classList.contains("hide");
  $("#drawer").dataset.ctx = "est.sub"; $("#d-title").innerHTML = title; $("#d-body").innerHTML = html; $("#drawer").classList.remove("hide");
  document.body.style.overflow = "hidden";
  if (!was) { try { history.pushState({ estDrawer: 1 }, ""); } catch (e) {} $("#drawer .dbox").scrollTop = 0; }
}
function closeDrawer(fromHistory) {
  $("#drawer").classList.add("hide"); ST.drawer = null; document.body.style.overflow = "";
  if (!fromHistory && history.state && history.state.estDrawer) { try { history.back(); } catch (e) {} }
}
$("#d-back").onclick = () => closeDrawer();
// the browser / phone Back button closes the page and returns to the list
addEventListener("popstate", () => {
  if (ST.skipPop) { ST.skipPop = false; return; }                          // a full page closing itself
  const bg = document.getElementById("big"); if (bg && !bg.classList.contains("hide")) return;   // the full page's own Back
  // Back with a pop-up form open over a page closes the form only (asking first if it has changes)
  if (!$("#modal").classList.contains("hide") && !$("#drawer").classList.contains("hide")) { try { history.pushState({ estDrawer: 1 }, ""); } catch (e) {} closeModal(); return; }
  if (!$("#drawer").classList.contains("hide")) closeDrawer(true);
});

document.addEventListener("keydown", e => { if (e.key === "Escape") { const lv = document.getElementById("leave"); if (lv && !lv.classList.contains("hide")) return;
  const bg = document.getElementById("big"); if (!$("#modal").classList.contains("hide")) closeModal(); else if (bg && !bg.classList.contains("hide")) return; else if (!$("#drawer").classList.contains("hide")) closeDrawer(); } });

// ---------- Preview / PDF / Excel / Share ----------
function xpButtons(what, extra = {}) {
  const k = JSON.stringify({ what, extra }).replace(/"/g, "&quot;");
  return `<span class="xp"><button class="btn btn-ghost" data-xp="preview" data-k="${k}">Preview</button><button class="btn btn-ghost" data-xp="pdf" data-k="${k}">Export PDF</button><button class="btn btn-ghost" data-xp="excel" data-k="${k}">Export Excel</button><button class="btn btn-ghost" data-xp="share" data-k="${k}">Share</button></span>`;
}
async function exportGo(fmt, what, extra) {
  try {
    const t = await POST("/auth/download-token"); const tok = t.token || t.download_token;
    const p = new URLSearchParams(Object.assign({ token: tok, format: fmt === "share" ? "pdf" : fmt }, extra));
    const url = what === "ipa" ? `/export/est/ipa/${extra.id}?token=${encodeURIComponent(tok)}&format=${fmt === "share" ? "pdf" : fmt}` :
                what === "ipafmt" ? `/export/est/ipa/format/${extra.id}?token=${encodeURIComponent(tok)}&format=${fmt === "share" ? "pdf" : fmt}` :
                what === "pc" ? `/export/est/pc/${extra.id}?token=${encodeURIComponent(tok)}&format=${fmt === "share" ? "pdf" : fmt}` : `/export/est/${what}?${p}`;
    if (fmt === "share") {
      const r = await fetch(url); const blob = await r.blob(); const file = new File([blob], (extra.name || what).replace(/[^\w]+/g, "_") + ".pdf", { type: "application/pdf" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: extra.name || what });
      else { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = file.name; a.click(); toast("Sharing isn't available here - the PDF was downloaded"); }
      return;
    }
    window.open(url, "_blank");
  } catch (e) { if (e && e.name !== "AbortError") fail(e); }
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-xp]"); if (!b) return;
  const k = JSON.parse(b.dataset.k); exportGo(b.dataset.xp, k.what, k.extra);
});

// ---------- the searchable project picker ----------
function combo(el, items, onPick, placeholder) {
  el.innerHTML = `<div class="combo"><input placeholder="${esc(placeholder)}" autocomplete="off"><span class="caret">&#9662;</span><div class="list hide"></div></div>`;
  const inp = $("input", el), list = $(".list", el);
  let cur = -1, shown = [];
  const draw = () => {
    const q = inp.value.trim().toLowerCase();
    shown = items.filter(x => !q || x.label.toLowerCase().includes(q) || inp.dataset.picked === inp.value);
    if (inp.dataset.picked === inp.value) shown = items;
    list.innerHTML = shown.length ? shown.map((x, i) => `<div class="opt ${i === cur ? "on" : ""}" data-i="${i}"><b>${esc(x.code)}</b></div>`).join("") : '<div class="none">No project matches</div>';
    list.classList.remove("hide");
  };
  inp.onfocus = () => { inp.select(); cur = -1; draw(); };
  inp.oninput = () => { cur = 0; draw(); };
  inp.onkeydown = e => {
    if (e.key === "ArrowDown") { cur = Math.min(shown.length - 1, cur + 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { cur = Math.max(0, cur - 1); draw(); e.preventDefault(); }
    else if (e.key === "Enter" && shown[Math.max(cur, 0)]) { pick(shown[Math.max(cur, 0)]); }
    else if (e.key === "Escape") { list.classList.add("hide"); if (inp.dataset.picked) inp.value = inp.dataset.picked; inp.blur(); }
  };
  const pick = x => { inp.value = String(x.code); inp.dataset.picked = inp.value; list.classList.add("hide"); inp.blur(); onPick(x); };
  list.onmousedown = e => { const o = e.target.closest(".opt"); if (o) { e.preventDefault(); pick(shown[+o.dataset.i]); } };
  inp.onblur = () => setTimeout(() => { list.classList.add("hide"); if (inp.dataset.picked && !items.some(x => String(x.code) === inp.value)) inp.value = inp.dataset.picked; }, 150);
  return { set(x) { if (x) { inp.value = String(x.code); inp.dataset.picked = inp.value; } } };
}

// ---------- the same money as the server, for the live figures in a form ----------
function chainCalc(pcs, advPct, retPct, vatPct, workKey = "work_cum") {
  let prev = 0, advPaid = 0; const out = [];
  for (const p of pcs) {
    advPaid = r2(advPaid + Number(p.adv_amount || 0));
    const work = r2(p[workKey]), gross = r2(work + Number(p.var_cum || 0) + Number(p.mos_cum || 0));
    const net = r2(gross + advPaid - (p.adv_rec_cum || 0) - (p.ret_cum || 0) + Number(p.ret_rel_cum || 0) - (p.other_cum || 0));
    const th = r2(net - prev), vat = r2(th * (vatPct || 0) / 100);
    out.push({ net, this: th, vat, payable: r2(th + vat), advPaid }); prev = net;
  }
  return out;
}

// =====================================================================
// start
// =====================================================================
async function start() {
  if (!TOKEN) { signIn(); return; }
  document.body.dataset.ctx = "est." + VIEW;          // est.dash / est.projects / est.pay - for the (i) notes
  if (VIEW === "pay") { $("#app").classList.remove("hide"); return loadPay(); }      // Accounts: needs only the Bank right
  // The page's own data is asked for at the same time as the lists, not after them.
  let early = null;
  if (VIEW === "dash") early = GET("/store/est/dash").catch(() => null);
  else if (VIEW === "projects") {
    let ep = +((location.hash.match(/p(\d+)/) || [])[1] || 0);
    try { ep = ep || +(localStorage.getItem("est_pid") || 0); } catch (e) {}
    if (ep) early = GET(`/store/est/projects/${ep}`).then(d => { (ST.cache = ST.cache || {})[ep] = d; ST.earlyPid = ep; return d; }).catch(() => null);
  } else if (VIEW === "tenders") early = GET("/store/est/tenders").catch(() => null);
  ST.early = early;
  try { ST.meta = await GET("/store/est/meta"); } catch (e) { $("#app").innerHTML = `<div class="wrap"><div class="empty">${esc(e.message)}</div></div>`; $("#app").classList.remove("hide"); return; }
  $("#app").classList.remove("hide");
  if (VIEW === "projects") {
    let pid = +((location.hash.match(/p(\d+)/) || [])[1] || 0);
    try { pid = pid || +(localStorage.getItem("est_pid") || 0); } catch (e) {}
    const s = (location.hash.match(/s=(\w+)\.(\w+)/) || []);
    const hb = +((location.hash.match(/bill=(\d+)/) || [])[1] || 0);
    if (hb) ST.pendingOpen = { est: "open", pid: pid, group: "bills", sec: "ipa", bill: hb };
    if (s[1]) { ST.group = s[1]; ST.sec = s[2]; }
    else { try { const k = localStorage.getItem("est_sec"); if (k) [ST.group, ST.sec] = k.split("."); } catch (e) {} }
    renderProjectShell();
    if (ST.pendingOpen) { const d = ST.pendingOpen; ST.pendingOpen = null; ST.early = null; ST.earlyPid = null; return openFromMessage(d); }
    if (!(pid && ST.meta.projects.some(p => p.id === pid))) pid = (ST.meta.projects.find(p => p.status === "Running") || ST.meta.projects[0] || {}).id;
    if (pid) openProject(pid);   // the first project opens by itself
  } else if (VIEW === "tenders") loadTenders();
  else loadDash();
}
window.addEventListener("message", e => {
  if (e.origin !== location.origin || !e.data) return;
  if (e.data.est === "open" && VIEW === "projects") {
    if (!ST.meta || !ST.picker) { ST.pendingOpen = e.data; return; }      // the page is still starting: it opens this when ready
    openFromMessage(e.data);
  }
  if (e.data.est === "refresh") { if (VIEW === "pay") loadPay(); else if (VIEW === "dash") loadDash(); else if (VIEW === "tenders") loadTenders(); else if (ST.pid) openProject(ST.pid, true); }
});
async function openFromMessage(d) {
  if (d.group) { ST.group = d.group; ST.sec = d.sec; }
  if (d.pid && !ST.meta.projects.some(p => p.id === +d.pid)) {         // made a moment ago (a won tender): fetch the list again
    try { ST.meta = await GET("/store/est/meta"); renderProjectShell(); } catch (e) {}
  }
  if (d.pid) await openProject(+d.pid, true); else if (ST.pid) await openProject(ST.pid, true);
  if (d.bill && typeof openBill === "function") openBill(+d.bill, "review");       // a bill waiting for this person's signature
}
window.pgRefresh = () => { if (VIEW === "pay") loadPay(); else if (VIEW === "dash") loadDash(); else if (VIEW === "tenders") loadTenders(); else if (ST.pid) openProject(ST.pid, true); };
function goProject(pid, group, sec) {
  if (window.PG_EMBED) { try { parent.postMessage({ est: "go", view: "projects", pid, group, sec }, location.origin); return; } catch (e) {} }
  location.href = `/portal/est-app.html?view=projects#p${pid}` + (group ? `&s=${group}.${sec}` : "");
}

// =====================================================================
// DASHBOARD
// =====================================================================
async function loadDash() {
  const app = $("#app");
  if (!ST.dash) app.innerHTML = '<div class="wrap"><div class="empty">Loading...</div></div>';
  const early = ST.early; ST.early = null;
  try { ST.dash = (early && await early) || await GET("/store/est/dash"); } catch (e) { return fail(e); }
  const d = ST.dash, t = d.totals, k = d.kpi, A = v => "AED " + money(v, false);
  const rows = d.projects;
  const coll = t.revised ? Math.round(100 * t.received / t.revised) : 0;
  app.innerHTML = `<div class="wrap">
    <div class="card"><h3>All projects ${tip("Every figure is worked out from the projects - nothing is typed here. Click a project to open its dashboard.")}<span class="spacer"></span>${xpButtons("dash")}</h3>
      <div class="kpis">
        ${kpi("Contract value", A(t.revised), rows.length + " projects · " + rows.filter(r => r.status === "Running").length + " running")}
        ${kpi("Certified by client", A(t.client_certified), t.revised ? Math.round(100 * t.client_certified / t.revised) + "% of contract" : "")}
        ${kpi("Received", A(t.received), `<div class="bar"><i style="width:${Math.min(100, coll)}%"></i></div>${coll}% collected`, "green")}
        ${kpi("Subcontracts", A(t.committed), A(t.sub_certified) + " certified")}
        ${kpi("Waiting payment", A(k.with_accounts_amount), k.with_accounts + " PCs with Accounts", k.with_accounts ? "amber click" : "", 'data-go="subs.pcs"')}
        ${kpi("Invoices at site", k.at_site, k.site_delays ? k.site_delays + " late back" : "none late", k.site_delays ? "red click" : "click", 'data-go="subs.inv"')}
        ${kpi("PCs being prepared", k.preparing, k.pc_delays ? k.pc_delays + " past due date" : "none late", k.pc_delays ? "red click" : "click", 'data-go="subs.inv"')}
      </div></div>
    <div class="card"><h3>Projects</h3>
      ${rows.length ? `<div class="tw"><table class="t"><thead><tr><th>Project</th><th>Client</th><th>Status</th><th class="r">Contract</th><th class="r">Certified</th><th>Progress</th><th class="r">Received</th><th class="r">Subcontracts</th><th class="r">Sub to pay</th>${ST.meta.me.admin ? `<th class="r">Margin</th>` : ""}</tr></thead><tbody>
      ${rows.map(r => `<tr class="rowc" data-pid="${r.id}" data-sec="home.dash"><td class="nowrap"><b>${esc(r.code)}</b></td><td>${esc(r.client)}</td><td>${st(r.status)}</td>
        <td class="r">${money(r.revised)}</td><td class="r">${money(r.client_certified)}</td><td><div class="bar"><i style="width:${Math.min(100, r.progress)}%"></i></div><span class="small muted">${r.progress}%</span></td>
        <td class="r">${money(r.received)}</td><td class="r">${money(r.committed)}</td><td class="r">${money(r.sub_to_pay)}</td>${ST.meta.me.admin ? `<td class="r ${r.margin < 0 ? "neg" : ""}">${money(r.margin)}</td>` : ""}</tr>`).join("")}
      <tr class="tot"><td>Total</td><td></td><td></td><td class="r">${money(t.revised)}</td><td class="r">${money(t.client_certified)}</td><td></td><td class="r">${money(t.received)}</td><td class="r">${money(t.committed)}</td><td class="r">${money(t.sub_to_pay)}</td>${ST.meta.me.admin ? "<td></td>" : ""}</tr>
      </tbody></table></div>` : `<div class="empty">No projects yet.<br><button class="btn btn-primary" onclick="goProject(0)">Add the first project</button></div>`}
    </div>
    <div class="card"><h3>Subcontractor invoices in hand ${tip("Every invoice not yet paid, oldest PC due date first. Site return is due " + d.rules.site_days + " days after it goes to site; the PC is due " + d.rules.pc_days + " days after the invoice arrives.")}<span class="spacer"></span><span class="small muted">${d.queue.length}</span></h3>
      ${d.queue.length ? `<div class="tw" style="max-height:420px"><table class="t"><thead><tr><th>Project</th><th>Subcontractor</th><th>PC</th><th>Status</th><th>PC due</th><th class="r">Payable</th></tr></thead><tbody>
      ${d.queue.map(x => `<tr class="rowc" data-pid="${x.project_id}" data-sec="subs.inv"><td><b>${esc(x.code)}</b></td><td>${esc(x.sub)}<div class="small muted">${esc(x.scope)}${x.inv_ref ? " · " + esc(x.inv_ref) : ""}</div></td><td>${pad(x.seq, 2)}</td><td>${st(x.status)}${x.site_delay ? `<div class="small late">site ${x.site_delay}d late</div>` : ""}</td><td class="nowrap ${x.pc_delay ? "late" : ""}">${dt(x.pc_due)}${x.pc_delay ? ` (+${x.pc_delay}d)` : ""}</td><td class="r">${money(x.payable)}</td></tr>`).join("")}
      </tbody></table></div>` : '<div class="empty">Nothing in hand.</div>'}
    </div>
  </div>`;
  $$("[data-pid]", app).forEach(r => r.onclick = () => { const s = (r.dataset.sec || "").split("."); goProject(+r.dataset.pid, s[0], s[1]); });
  $$("[data-go]", app).forEach(f => f.onclick = () => {
    const s = f.dataset.go.split("."), want = s[1] === "pcs" ? ["Prepared", "CM approved", "Verified", "MD approved"] : ["At site", "Received", "Certified"];
    const n = {}; d.queue.filter(x => want.includes(x.status)).forEach(x => n[x.project_id] = (n[x.project_id] || 0) + 1);
    const best = Object.entries(n).sort((a, b) => b[1] - a[1])[0];
    if (best) goProject(+best[0], s[0], s[1]); else toast("Nothing waiting there just now");
  });
}
function finalMatrix(d) {
  if (!d.matrix.length) return '<div class="empty">No projects yet.</div>';
  const cell = f => { if (!f) return '<td class="cell"></td>'; const sc = f.sc, s = f.st; if (sc === "N/A" || s === "N/A") return '<td class="cell na">N/A</td>'; if (sc === "E") return `<td class="cell sc" title="Employer's scope">E${s === "✔" ? " ✔" : ""}</td>`; return `<td class="cell ${s === "✔" ? "ok" : s === "X" ? "no" : ""}">${esc(s || (sc ? sc : ""))}</td>`; };
  let html = `<div class="tw" style="max-height:460px"><table class="t fg mx"><thead><tr><th>Item</th>${d.matrix.map(p => `<th class="c rowc" data-pid="${p.id}" data-sec="subs.final" style="cursor:pointer">${esc(p.code)}</th>`).join("")}</tr></thead><tbody>`;
  for (const [sec, items] of Object.entries(d.final_items)) {
    html += `<tr class="sec"><td colspan="${d.matrix.length + 1}">${esc(sec)}</td></tr>`;
    for (const it of items) html += `<tr><td>${esc(it)}</td>${d.matrix.map(p => cell(p.finals[it])).join("")}</tr>`;
  }
  return html + "</tbody></table></div>";
}

// =====================================================================
// PROJECTS
// =====================================================================
const GROUPS = {
  home: { label: "", secs: [["dash", "Dashboard"]] },
  client: { label: "Overview", secs: [["boq", "BOQ & budget"]] },       // variations are under Site & technical
  subs: { label: "Subcontractors", secs: [["reg", "Subcontract register"], ["inv", "Invoice tracker"], ["pcs", "Payment certificates"], ["final", "Finalization log"]] },
  site: { label: "Site & technical", secs: [["rfi", "RFI log"], ["approval", "NOCs & approvals"], ["submittal", "Submittals"], ["vo", "Variations"]] },
  bills: { label: "Bills", secs: [["ipa", "Bills to client"]] },      // portal/est/bills.js
  prev: { label: "Previous records", secs: [["rec", "Bring in old records"]] },   // portal/est/prev.js - for going live
};
function renderProjectShell() {
  const list = ST.meta.projects.slice().sort((a, b) => String(a.code).localeCompare(String(b.code), "en", { numeric: true }));
  // The app's own pattern: one row of main tabs (pill group), the sub-tabs under it (underlined), the page below at full width.
  $("#app").innerHTML = `<div class="wrap">
    <div class="ptop"><select class="pick" id="pick" title="Project">${list.map(p => `<option value="${p.id}">${esc(p.code)}</option>`).join("")}</select>
      <div class="pills" id="pnav"></div><span class="pname" id="pname"></span><span class="spacer"></span><button class="btn btn-ghost" id="p-new">+ New project</button></div>
    <div class="utabs" id="psub"></div>
    <div id="pbody"></div></div>`;
  ST.picker = true;
  $("#pick").onchange = () => openProject(+$("#pick").value);
  $("#p-new").onclick = newProject;
  if (!list.length) $("#pbody").innerHTML = `<div class="card empty">No projects yet. Press <b>+ New project</b> and pick the site - the rest is filled in for you.</div>`;
}
async function openProject(pid, keep) {
  ST.pid = pid;
  try { localStorage.setItem("est_pid", pid); } catch (e) {}
  const p = ST.meta.projects.find(x => x.id === pid);
  if (p && $("#pick")) { $("#pick").value = String(pid); $("#pname").textContent = [p.name, p.client].filter(Boolean).join(" · "); }
  // A project opened before shows at once from memory, then catches up.
  ST.cache = ST.cache || {};
  if (ST.early) { const e = ST.early; ST.early = null; await e; }       // the first project was already on its way
  if (ST.earlyPid === pid && ST.cache[pid]) { ST.earlyPid = null; ST.b = ST.cache[pid]; renderProject(); if (ST.drawer) ST.drawer(); return; }
  ST.earlyPid = null;
  if (ST.cache[pid] && !keep) { ST.b = ST.cache[pid]; renderProject(); }
  let fresh;
  try { fresh = await GET(`/store/est/projects/${pid}`); } catch (e) { return fail(e); }
  if (ST.pid !== pid) return;                       // another project was picked meanwhile
  const changed = !ST.b || JSON.stringify(ST.b) !== JSON.stringify(fresh) || ST.b.project.id !== pid;
  ST.b = fresh; ST.cache[pid] = fresh;
  if (changed || keep) renderProject();
  if (ST.drawer) ST.drawer();
}
async function reload() { try { ST.b = await GET(`/store/est/projects/${ST.pid}`); (ST.cache = ST.cache || {})[ST.pid] = ST.b; renderProject(); if (ST.drawer) ST.drawer(); } catch (e) { fail(e); } }
function newProject() {
  const used = new Set(ST.meta.projects.map(p => p.code));
  const sites = ST.meta.sites.filter(s => !used.has(s.code));
  modal("New project", [
    { k: "code", label: "Project (site)", type: "combo", options: sites.map(s => s.code), ph: "Pick the site code", tip: "Projects come from Settings > Companies & sites. A code not in the list can be typed.", focus: true,
      hint: sites.length ? sites.slice(0, 12).map(s => `<a href="#" data-site="${esc(s.code)}">${esc(s.code)}</a>`).join(" · ") : "" },
    { k: "name", label: "Project name", value: "", ph: "Filled in from the site" },
    { k: "plot_no", label: "Plot no.", value: "", ph: "Filled in from the site" },
    { k: "location", label: "Location", value: "" },
    { k: "client", label: "Client", type: "combo", options: [...new Set(ST.meta.projects.map(p => p.client).filter(Boolean))] },
    { k: "consultant", label: "Consultant", type: "combo", options: [...new Set(ST.meta.projects.map(p => p.consultant).filter(Boolean))] },
    { k: "contract_value", label: "Contract value (AED)", type: "money", tip: "Left empty, it is taken from Accounts > Project payments." },
    { k: "ret_pct", label: "Retention held by client %", type: "pct", value: 10, quick: [["5%", el => el.value = 5], ["10%", el => el.value = 10]] },
    { k: "adv_pct", label: "Advance from client %", type: "pct", value: 0, quick: [["0", el => el.value = 0], ["10%", el => el.value = 10], ["20%", el => el.value = 20]] },
    { k: "qs", label: "QS in charge", type: "combo", options: ST.meta.users.map(u => u.name) },
  ], async v => {
    const f = ($("#np-boq") || {}).files; const file = f && f[0];
    const r = await POST("/store/est/projects", v);
    ST.meta = await GET("/store/est/meta"); renderProjectShell(); await openProject(r.id); toast("Project added");
    if (file) { go("client.boq"); setTimeout(() => boqImport(file, r.id), 60); }     // after this form has closed
  }, {
    doc: { kind: "project", what: "letter of award or main contract", want: [["name", "Project name"], ["client", "Client"], ["contract_value", "Contract value"]] },
    bottom: `<div class="frm" style="margin-top:4px"><div class="f full"><label for="np-boq">Internal BOQ (optional) ${tip("Pick the internal BOQ Excel and every line goes into Overview > BOQ & budget, grouped by trade, with excluded / phase 2 bills kept aside. Only the lines are kept - the file is not stored. It can also be uploaded later from Overview > BOQ & budget.")}</label><input type="file" id="np-boq" accept=".xlsx,.xlsm,.pdf,.docx,.jpg,.jpeg,.png"></div></div>`,
    after: () => {
      const fill = () => { const s = ST.meta.sites.find(x => x.code === $("#f-code").value.trim()); if (s && !$("#f-name").value) $("#f-name").value = s.name; if (s && s.plot && !$("#f-plot_no").value) $("#f-plot_no").value = s.plot; };
      $("#f-code").addEventListener("change", fill); $("#f-code").addEventListener("input", fill);
      $$("[data-site]").forEach(a => a.onclick = e => { e.preventDefault(); $("#f-code").value = a.dataset.site; $("#f-name").value = ""; $("#f-plot_no").value = ""; fill(); });
    }
  });
}
// Details: every figure of the project in one place (they used to fill the top of the screen), and its details.
function projectInfo() {
  const b = ST.b, s = b.summary, p = b.project;
  const fig = (l, v, sub, cls = "") => `<div class="fig ${cls}"><div class="l">${l}</div><div class="v">${v}</div>${sub ? `<div class="s">${sub}</div>` : ""}</div>`;
  const row = (l, v) => v ? `<tr><th>${l}</th><td>${v}</td></tr>` : "";
  ST.drawer = null;
  drawer(`Project ${esc(p.code)} <span class="muted small">${esc(p.name || "")}</span>`, `
    <div class="strip">
      ${fig("Contract", money(s.revised, false), s.approved_vo ? `original ${money(s.contract, false)} + VOs ${money(s.approved_vo, false)}` : "revised")}
      ${fig("Certified by client", money(s.client_certified, false), s.revised ? Math.round(100 * s.client_work / s.revised) + "% done" : "")}
      ${fig("Received", money(s.received, false), "Accounts", "green")}
      ${fig("Subcontracts", money(s.committed, false), b.subs.length + " subcontractors")}
      ${fig("Sub certified", money(s.sub_certified, false), money(s.sub_paid, false) + " paid")}
      ${fig("Sub to pay", money(s.sub_to_pay, false), "certified, not paid", s.sub_to_pay > 0 ? "amber" : "")}
      ${ST.meta.me.admin ? fig("Margin", money(s.margin, false), "contract - subcontracts", s.margin < 0 ? "red" : "") : ""}
      ${fig("Overdue", s.overdue, "RFIs / submittals", s.overdue ? "red" : "")}
    </div>
    <div class="card"><h3>Details</h3><table class="kv">${row("Name", esc(p.name))}${row("Client", esc(p.client))}${row("Consultant", esc(p.consultant))}${row("Location", esc(p.location))}
      ${row("Status", esc(p.status))}${row("QS", esc(p.qs))}${row("Advance from client", p.adv_pct ? p.adv_pct + "%" : "")}${row("Retention held by client", p.ret_pct ? p.ret_pct + "%" : "")}${row("VAT", p.vat_pct + "%")}
      ${row("Start", dt(p.start_date))}${row("Completion", dt(p.end_date))}${row("Notes", esc(p.notes))}</table>
      <div style="margin-top:10px"><button class="btn btn-primary btn-sm" id="pi-edit">Edit details</button></div></div>`);
  $("#pi-edit").onclick = editProject;
}
function editProject() {
  const p = ST.b.project;
  modal(`Project ${p.code} - details`, [
    { k: "name", label: "Project name", value: p.name, full: true },
    { k: "client", label: "Client", value: p.client }, { k: "consultant", label: "Consultant", value: p.consultant },
    { k: "location", label: "Location", value: p.location },
    { k: "plot_no", label: "Plot no.", value: p.plot_no || "", ph: "Printed on the payment certificates" },
    { k: "status", label: "Status", type: "select", options: ["Running", "Tender", "On hold", "Handed over", "Closed"], value: p.status },
    { k: "contract_value", label: "Contract value (AED)", type: "money", value: p.contract_value },
    { k: "ret_pct", label: "Retention %", type: "pct", value: p.ret_pct }, { k: "adv_pct", label: "Advance %", type: "pct", value: p.adv_pct },
    { k: "vat_pct", label: "VAT %", type: "pct", value: p.vat_pct },
    { k: "start_date", label: "Start", type: "date", value: p.start_date }, { k: "end_date", label: "Completion", type: "date", value: p.end_date },
    { k: "qs", label: "QS in charge", type: "combo", options: ST.meta.users.map(u => u.name), value: p.qs },
    { k: "notes", label: "Notes", type: "area", value: p.notes },
  ], async v => { await PATCH(`/store/est/projects/${p.id}`, v); ST.meta = await GET("/store/est/meta"); reload(); toast("Saved"); },
  { doc: { kind: "project", what: "letter of award or main contract", want: [["name", "Project name"], ["client", "Client"], ["contract_value", "Contract value"], ["start_date", "Start"], ["end_date", "Completion"]] } },
  { del: ST.meta.me.admin ? async () => { await DEL(`/store/est/projects/${p.id}`); ST.meta = await GET("/store/est/meta"); ST.pid = null; try { localStorage.removeItem("est_pid"); } catch (e) {} renderProjectShell(); const nx = ST.meta.projects.find(x => x.status === "Running") || ST.meta.projects[0]; if (nx) openProject(nx.id); } : null });
}
function renderProject() {
  const b = ST.b, s = b.summary;
  document.body.dataset.ctx = "est." + key();          // which (i) notes apply (heads.js)
  const count = { "subs.reg": b.subs.length, "subs.inv": b.subs.reduce((n, x) => n + x.pcs.filter(p => p.status !== "Paid").length, 0),
                  "subs.pcs": b.subs.reduce((n, x) => n + x.pcs.filter(p => pcMine(Object.assign({ sub: x }, p)) && STEPS.indexOf(p.status) >= 3).length, 0),
                  "client.cpc": b.clientpcs.length, "client.vo": b.variations.filter(v => v.status !== "Cancelled").length, "site.vo": b.variations.filter(v => v.status !== "Cancelled").length, "client.inv": b.invoices.length, "client.boq": b.boq.length,
                  "site.rfi": s.open_rfi, "site.submittal": s.open_submittals,
                  "site.approval": s.approvals_total ? `${s.approvals_done}/${s.approvals_total}` : 0, "subs.final": s.finals_total ? `${s.finals_done}/${s.finals_total}` : 0 };
  if (!GROUPS[ST.group] || !GROUPS[ST.group].secs.some(x => x[0] === ST.sec)) { ST.group = "home"; ST.sec = "dash"; }
  const lbl = g => g === "home" ? "Dashboard" : GROUPS[g].label;
  $("#pnav").innerHTML = Object.keys(GROUPS).map(g => `<button class="${g === ST.group ? "on" : ""}" data-g="${g}">${lbl(g)}</button>`).join("");
  $("#psub").innerHTML = ST.group === "home" ? "" : GROUPS[ST.group].secs.map(([k, l]) => { const n = count[ST.group + "." + k]; return `<button class="${k === ST.sec ? "on" : ""}" data-s="${k}">${l}${n ? `<span class="n">${n}</span>` : ""}</button>`; }).join("");
  $("#psub").classList.toggle("hide", ST.group === "home");
  $("#pbody").innerHTML = `<div class="panel ${ST.group === "home" ? "bare" : ""}" id="sec"></div>`;
  $$("#pnav [data-g]").forEach(x => x.onclick = () => { ST.group = x.dataset.g; ST.sec = GROUPS[ST.group].secs[0][0]; saveSec(); renderProject(); });
  $$("#psub [data-s]").forEach(x => x.onclick = () => { ST.sec = x.dataset.s; saveSec(); renderProject(); });
  const fn = SECTIONS[ST.group + "." + ST.sec];
  try { fn($("#sec")); } catch (e) { console.error(e); $("#sec").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
// ---------------- the project's own dashboard ----------------
function kpi(l, v, sub, cls = "", extra = "") { return `<div class="kpi ${cls}" ${extra}><div class="l">${l}</div><div class="v">${v}</div>${sub ? `<div class="s">${sub}</div>` : ""}</div>`; }
function go(gs) { [ST.group, ST.sec] = gs.split("."); saveSec(); renderProject(); window.scrollTo(0, 0); }
function homeDash(el) {
  const b = ST.b, s = b.summary, p = b.project, A = v => "AED " + money(v, false);
  const coll = s.revised ? Math.min(100, Math.round(100 * s.received / s.revised)) : 0;
  const vs = st_ => b.variations.filter(v => v.status === st_);
  const sum = (arr, k) => r2(arr.reduce((a, v) => a + (v[k] || 0), 0));
  const waiting = b.subs.flatMap(x => x.pcs.filter(q => q.status !== "Paid").map(q => Object.assign({ sub: x }, q)));
  const row = (l, v) => v ? `<tr><th>${l}</th><td>${v}</td></tr>` : "";
  el.innerHTML = `
    <div class="card"><div class="kpis k4">
      ${kpi("Contract value", A(s.revised), s.approved_vo ? `original ${money(s.contract, false)} + VOs ${money(s.approved_vo, false)}` : "original contract")}
      ${kpi("Certified by client", A(s.client_certified), s.revised ? Math.round(100 * s.client_work / s.revised) + "% of the work" : "")}
      ${kpi("Received", A(s.received), `<div class="bar"><i style="width:${coll}%"></i></div>${coll}% collected`, "green")}
      ${kpi("To receive", A(r2(s.revised - s.received)), "contract less received", s.revised - s.received > 0 ? "red" : "")}
      ${kpi("Subcontracts", A(s.committed), b.subs.length + " subcontractors")}
      ${kpi("Sub certified", A(s.sub_certified), money(s.sub_paid, false) + " paid")}
      ${kpi("Sub to pay", A(s.sub_to_pay), "certified, not paid", s.sub_to_pay > 0 ? "amber" : "")}
      ${ST.meta.me.admin ? kpi("Margin", A(s.margin), "contract less subcontracts", s.margin < 0 ? "red" : "") : ""}
    </div></div>
    <div class="dgrid">
      ${contractsCard()}
      <div class="card"><h3>Project details<span class="go" id="pd-edit">Edit</span></h3><table class="kv">${row("Name", esc(p.name))}${row("Client", esc(p.client))}${row("Consultant", esc(p.consultant))}${row("Location", esc(p.location))}${row("Plot no.", esc(p.plot_no || ""))}${row("Status", st(p.status))}${row("QS", esc(p.qs))}${CTRS().length ? row("Contracts", CTRS().length + " - see above") : row("Retention by client", p.ret_pct ? p.ret_pct + "%" : "") + row("Advance from client", p.adv_pct ? p.adv_pct + "%" : "")}${row("Start", dt(p.start_date))}${row("Completion", dt(p.end_date))}</table></div>
      <div class="card"><h3>Variations<span class="go" data-go="site.vo">Open</span></h3>
        <div class="vs"><div><span>Approved</span><b class="ok">${money(sum(vs("Approved"), "approved_amount"), false)}</b><small class="muted">${vs("Approved").length} lines</small></div>
          <div><span>Waiting</span><b>${money(sum(vs("Submitted"), "submitted_amount"), false)}</b><small class="muted">${vs("Submitted").length} submitted</small></div>
          <div><span>Absorbed</span><b>${money(sum(b.variations.filter(v => v.status !== "Cancelled"), "absorbed_amount"), false)}</b><small class="muted">${vs("Absorbed").length} lines</small></div>
          <div><span>To price</span><b>${vs("Identified").length}</b><small class="muted">identified</small></div></div>
        <h3 style="margin-top:16px">Client payment certificates</h3>
        ${b.clientpcs.length ? `<div id="dash-cpc">${dashCpcTable()}</div>` : '<div class="muted small">None yet.</div>'}
      </div>
      <div class="card full"><h3>Subcontractors<span class="go" data-go="subs.reg">Open register</span></h3>
        ${b.subs.length ? `<div class="tw"><table class="t"><thead><tr><th>Subcontractor</th><th>Work</th><th class="r">Revised value</th><th>Done</th><th class="r">Certified</th><th class="r">Paid</th><th class="r">To pay</th><th>Status</th></tr></thead><tbody>
        ${b.subs.map(x => `<tr class="rowc" data-sub="${x.id}"><td><b>${esc(x.name)}</b></td><td>${esc(x.scope)}</td><td class="r">${money(x.revised)}</td><td>${x.remeasure ? '<span class="small muted">re-measured</span>' : `<div class="bar"><i style="width:${Math.min(100, x.done_pct)}%"></i></div><span class="small muted">${x.done_pct}%</span>`}</td><td class="r">${money(x.certified)}</td><td class="r">${money(x.paid)}</td><td class="r">${money(x.to_pay)}</td><td>${st(x.status)}</td></tr>`).join("")}
        </tbody></table></div>` : '<div class="muted small">No subcontracts yet.</div>'}
      </div>
      <div class="card full"><h3>Invoices in hand<span class="go" data-go="subs.inv">Open tracker</span></h3>
        ${waiting.length ? `<div class="tw"><table class="t"><thead><tr><th>Subcontractor</th><th>PC</th><th>Invoice</th><th>Status</th><th>PC due</th><th class="r">Payable</th></tr></thead><tbody>
        ${waiting.map(q => `<tr><td>${esc(q.sub.name)}</td><td>PC ${pad(q.seq, 2)}</td><td>${esc(q.inv_ref)}</td><td>${st(q.status)}</td><td class="${q.pc_delay ? "late" : ""}">${dt(q.pc_due)}${q.pc_delay ? ` (+${q.pc_delay}d)` : ""}</td><td class="r">${q.work_cum || q.adv_amount ? money(q.payable) : ""}</td></tr>`).join("")}
        </tbody></table></div>` : '<div class="muted small">Nothing waiting.</div>'}
      </div>
    </div>`;
  $("#pd-edit", el).onclick = editProject;
  const ca = $("#ctr-add", el); if (ca) ca.onclick = () => contractForm();
  $$("[data-ctr]", el).forEach(r => r.onclick = () => { ctrSet(+r.dataset.ctr); go("bills.ipa"); });
  $$("[data-go]", el).forEach(x => x.onclick = () => go(x.dataset.go));
  $$("[data-sub]", el).forEach(r => r.onclick = () => openSub(+r.dataset.sub));
}
function saveSec() { try { localStorage.setItem("est_sec", ST.group + "." + ST.sec); } catch (e) {} }
function key() { return ST.group + "." + ST.sec; }
function tools(what, opts = {}) {
  const k = key(), q = ST.q[k] || "", f = ST.filt[k] || "";
  return `<div class="tools">${opts.add || ""}<input class="q" placeholder="Search" value="${esc(q)}" data-q><span class="spacer"></span>${opts.right || ""}${what ? xpButtons(what, Object.assign({ pid: ST.pid, q, status: f }, opts.xp || {})) : ""}</div>` +
    (opts.chips ? `<div class="chips crow">${opts.chips.map(([v, n]) => `<span class="chip ${f === v ? "on" : ""}" data-f="${esc(v)}">${esc(v || "All")}${n !== undefined ? `<span class="n">${n}</span>` : ""}</span>`).join("")}</div>` : "");
}
function bindTools(el, redraw) {
  const k = key();
  const qi = $("[data-q]", el); if (qi) qi.oninput = debounce(() => { ST.q[k] = qi.value; redraw(); setTimeout(() => { const n = $("[data-q]", el); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }, 0); }, 250);
  $$("[data-f]", el).forEach(c => c.onclick = () => { ST.filt[k] = ST.filt[k] === c.dataset.f ? "" : c.dataset.f; redraw(); });
}
function match(row) { const q = (ST.q[key()] || "").toLowerCase(); return !q || JSON.stringify(row).toLowerCase().includes(q); }
function filt() { return ST.filt[key()] || ""; }

// ---------------- contracts: a project built under several agreements with the client ----------------
// (shell & core, MEP, swimming pool ...). One agreement needs none: the project's own figures are the contract.
function CTRS() { return (ST.b && ST.b.contracts) || []; }
function ctrName(id) { const k = CTRS().find(c => c.id === +id); return k ? k.name : ""; }
function ctrPick() {                     // the contract shown on the Bills tab (remembered per project)
  const ks = CTRS(); if (!ks.length) return null;
  let id = null; try { id = +localStorage.getItem("est_ctr_" + ST.pid); } catch (e) {}
  return (ks.find(k => k.id === id) || ks[0]).id;
}
function ctrSet(id) { try { localStorage.setItem("est_ctr_" + ST.pid, id); } catch (e) {} }
function ctrField(value, label = "Contract") {   // the "which contract" box on a form - only when there are several
  const ks = CTRS(); if (!ks.length) return null;
  return { k: "contract_id", label, type: "select", noseg: true, value: value || (ks.length === 1 ? ks[0].id : ctrPick() || ""),
           options: [["", "- Pick the contract -"], ...ks.map(k => [k.id, k.name + (k.ref ? " · " + k.ref : "")])],
           tip: "This project is under several agreements with the client - each has its own bills, certificates and variations." };
}
let CTR_TYPED = "";
function contractForm(k) {
  const p = ST.b.project, edit = !!k, first = !CTRS().length; k = k || {};
  modal(edit ? `Contract - ${k.name}` : `Add contract to ${p.code}`, [
    ...(first ? [{ k: "first_name", label: `Name of the contract already on ${p.code}`, value: "Main contract", full: true, ph: "e.g. Shell & Core",
                   tip: `Project ${p.code} has one contract now (AED ${money(p.contract_value, false)}). It becomes the first of the contracts with this name - its bills, certificates and variations stay with it.` }] : []),
    { k: "name", label: first ? "New contract name" : "Contract name", value: k.name || "", full: true, focus: true, ph: "e.g. MEP works, Swimming pool works" },
    { k: "ref", label: "Agreement / LOA no.", value: k.ref || "", ph: `IC/${p.code}/...` },
    { k: "value", label: "Contract value (AED, excl. VAT)", type: "money", value: k.value ?? "" },
    { k: "adv_pct", label: "Advance %", type: "pct", value: k.adv_pct ?? 0, quick: [["0", el => el.value = 0], ["10%", el => el.value = 10], ["20%", el => el.value = 20]] },
    { k: "ret_pct", label: "Retention %", type: "pct", value: k.ret_pct ?? 10, quick: [["0", el => el.value = 0], ["5%", el => el.value = 5], ["10%", el => el.value = 10]] },
    { k: "vat_pct", label: "VAT %", type: "pct", value: k.vat_pct ?? 5, quick: [["5%", el => el.value = 5], ["0", el => el.value = 0]] },
    { k: "notes", label: "Notes", type: "area", value: k.notes || "" },
  ], async v => {
    if (!String(v.name || "").trim()) throw new Error("Name the contract (e.g. MEP works).");
    if (edit) await PATCH(`/store/est/contracts/${k.id}`, v);
    else { const r = await POST("/store/est/contracts", Object.assign(v, { project_id: ST.pid })); ctrSet(r.id); }
    ST.meta = await GET("/store/est/meta"); await reload(); toast(edit ? "Saved" : `Contract ${v.name} added - it has its own bills from now on`);
  }, { wide: true, save: edit ? "Save" : "Add contract",
       doc: { kind: "project", what: "agreement or letter of award", want: [["value", "Contract value"]], extra: () => { CTR_TYPED = $("#f-name") ? $("#f-name").value : ""; return {}; },
              keep: r => { const f = (r && r.fields) || {}; if (f.contract_value && $("#f-value")) setField("value", f.contract_value); if (CTR_TYPED && $("#f-name")) $("#f-name").value = CTR_TYPED; } },
       del: edit ? async () => { await DEL(`/store/est/contracts/${k.id}`); ST.meta = await GET("/store/est/meta"); await reload(); toast("Contract removed"); } : null });
}
function contractsCard() {                 // the project dashboard: one line per contract and the project total
  const ks = CTRS(); if (!ks.length) return "";
  const t = f => r2(ks.reduce((a, k) => a + (k[f] || 0), 0));
  const pc = (a, b) => b ? (Math.round(1000 * a / b) / 10).toFixed(1) + "%" : "-";
  return `<div class="card full"><h3>Contracts with the client<span class="go" id="ctr-add">+ Add contract</span></h3><div class="tw"><table class="t">
    <thead><tr><th>Contract</th><th>Agreement</th><th class="r">Value</th><th class="r">Variations</th><th class="r">Revised</th><th class="r">Work done (last bill)</th><th class="r">%</th><th class="r">Certified</th><th class="r">Retention held</th><th>Last bill</th></tr></thead><tbody>
    ${ks.map(k => `<tr class="rowc" data-ctr="${k.id}"><td><b>${esc(k.name)}</b></td><td class="small">${esc(k.ref || "")}</td><td class="r">${money(k.value)}</td><td class="r">${money(k.approved_vo)}</td><td class="r"><b>${money(k.revised)}</b></td>
      <td class="r">${money(k.work_done)}</td><td class="r">${pc(k.work_done, k.revised)}</td><td class="r">${money(k.certified)}</td><td class="r">${money(k.retention)}</td>
      <td class="small">${k.last_bill ? `IPA ${esc(k.last_bill.label)} ${st(k.last_bill.status)}` : '<span class="muted">none yet</span>'}</td></tr>`).join("")}
    <tr class="tot"><td>Project ${esc(ST.b.project.code)} total</td><td></td><td class="r">${money(t("value"))}</td><td class="r">${money(t("approved_vo"))}</td><td class="r">${money(t("revised"))}</td><td class="r">${money(t("work_done"))}</td><td class="r">${pc(t("work_done"), t("revised"))}</td><td class="r">${money(t("certified"))}</td><td class="r">${money(t("retention"))}</td><td></td></tr>
    </tbody></table></div></div>`;
}

const SECTIONS = {};
SECTIONS["home.dash"] = homeDash;

// ---------------- Subcontractors > register ----------------
SECTIONS["subs.reg"] = el => {
  const b = ST.b, f = filt();
  const subs = b.subs.filter(s => (!f || s.status === f) && match(s));
  const stc = s => b.subs.filter(x => x.status === s).length;
  const tot = k => r2(subs.reduce((n, s) => n + s[k], 0));
  el.innerHTML = tools("subs", { add: `<button class="btn btn-primary" id="add-sub">+ Subcontract / LPO</button>`, chips: [["", b.subs.length], ["Active", stc("Active")], ["Completed", stc("Completed")], ["Closed", stc("Closed")], ["Cancelled", stc("Cancelled")]] }) +
    (subs.length ? `<div class="tw"><table class="t"><thead><tr><th>#</th><th>Subcontractor</th><th>Work</th><th>Agreement / LPO</th><th class="r">Value</th><th class="r">VOs</th><th class="r">Revised</th><th>Done</th><th class="r">Certified</th><th class="r">Paid</th><th class="r">To pay</th><th class="r">Retention held</th><th class="c">PCs</th><th>Status</th></tr></thead><tbody>
    ${subs.map((s, i) => `<tr class="rowc" data-sub="${s.id}"><td class="muted">${i + 1}</td><td><b>${esc(s.name)}</b><div class="small muted">${esc(s.kind)} · ${esc(s.trade)}</div></td><td>${esc(s.scope)}</td><td class="small">${esc([s.agreement, s.lpo].filter(Boolean).join(" / "))}</td>
      <td class="r">${money(s.value)}</td><td class="r">${money(s.vo_total)}</td><td class="r"><b>${money(s.revised)}</b></td><td>${s.remeasure ? '<span class="small muted" title="Re-measurable: the revised value is the work measured on the certificates so far">re-measured</span>' : `<div class="bar ${s.done_pct > 100 ? "over" : ""}"><i style="width:${Math.min(100, s.done_pct)}%"></i></div><span class="small muted">${s.done_pct}%</span>`}</td>
      <td class="r">${money(s.certified)}</td><td class="r">${money(s.paid)}</td><td class="r ${s.to_pay > 0.005 ? "late" : ""}">${money(s.to_pay)}</td><td class="r">${money(s.ret_left)}</td><td class="c">${s.pc_count}</td><td>${st(s.status)}</td></tr>`).join("")}
    <tr class="tot"><td></td><td>Total</td><td></td><td></td><td class="r">${money(tot("value"))}</td><td class="r">${money(tot("vo_total"))}</td><td class="r">${money(tot("revised"))}</td><td></td><td class="r">${money(tot("certified"))}</td><td class="r">${money(tot("paid"))}</td><td class="r">${money(tot("to_pay"))}</td><td class="r">${money(tot("ret_left"))}</td><td></td><td></td></tr>
    </tbody></table></div>` : `<div class="empty">No subcontracts${f ? " with this status" : ""} yet.<br><button class="btn btn-primary" onclick="subForm()">+ Add the first subcontract</button></div>`);
  bindTools(el, () => SECTIONS["subs.reg"](el));
  const a = $("#add-sub", el); if (a) a.onclick = () => subForm();
  $$("[data-sub]", el).forEach(r => r.onclick = () => openSub(+r.dataset.sub));
};
function recMode(s) { return s.adv_rec_mode || (s.adv_rec_pct === 0 ? "none" : s.adv_rec_pct != null && s.adv_rec_pct !== undefined ? "pct" : ""); }
function recShow() { const m = $("#f-adv_rec_mode"); if (!m) return; const f = $("#f-adv_rec_pct"); const box = f && (f.closest(".f") || f.parentElement); if (box) box.style.display = m.value === "pct" ? "" : "none";
  const fr = $("#f-adv_rec_from"); const fb = fr && (fr.closest(".f") || fr.parentElement); if (fb) fb.style.display = m.value === "none" || m.value === "manual" ? "none" : ""; }
function subForm(s, pre) {
  const m = ST.meta, edit = !!s; s = s || Object.assign({}, pre || {});
  let ag = null;                 // what was read from the agreement file (nothing of the file is kept)
  const names = [...new Set([...m.suppliers.map(x => x.name), ...m.sub_names])];
  modal(edit ? "Subcontract - " + s.name : "New subcontract / LPO", [
    { k: "name", label: "Subcontractor", type: "combo", options: names, value: s.name || "", full: true, focus: !edit, ph: "Start typing - suppliers from Store & Purchasing", tip: "The list is every supplier in Store & Purchasing. A new name can be typed." },
    { k: "address", label: "Address", type: "area", value: s.address || "", ph: "Office address - printed on his payment certificates", tip: "Printed under his name on every payment certificate. Filled from Store & Purchasing > Suppliers when he is there." },
    { k: "phone", label: "Telephone", value: s.phone || "", ph: "04 ..." }, { k: "mobile", label: "Mobile", value: s.mobile || "", ph: "05 ..." },
    { k: "trn", label: "TRN", value: s.trn || "", ph: "15 digits", tip: "His VAT number - printed on the payment certificates. Leave blank if he is not VAT registered." },
    { k: "scope", label: "Work", type: "combo", options: m.scopes, value: s.scope || "" },
    { k: "trade", label: "Trade", type: "select", options: m.trades, value: s.trade || "Civil" },
    { k: "kind", label: "Type", type: "select", options: ["Subcontract", "LPO", "Manpower"], value: s.kind || "Subcontract" },
    { k: "status", label: "Status", type: "select", options: ["Active", "Completed", "Closed", "Cancelled"], value: s.status || "Active" },
    { k: "agreement", label: "Agreement no.", value: s.agreement || (edit ? "" : nextAgreement()), ph: `IC/${ST.b.project.code}/SCA/01/26`, tip: "Filled with the next number for this project (IC/project/SCA/serial/year). Change it if the agreement says otherwise." },
    { k: "lpo", label: "LPO no.", value: s.lpo || "" },
    { k: "value", label: "Subcontract / LPO amount (AED)", type: "money", value: s.value ?? "", tip: "Before VAT. Variations are added later on the subcontract." },
    { k: "cancelled", label: "LPO cancellation (AED)", type: "money", value: s.cancelled || "" },
    { k: "adv_pct", label: "Advance %", type: "pct", value: s.adv_pct ?? 0, quick: [["0", el => el.value = 0], ["10%", el => el.value = 10], ["20%", el => el.value = 20]], tip: "The advance paid on this subcontract, as a % of its value." },
    { k: "adv_rec_mode", label: "How the advance is recovered", type: "select", noseg: true, value: recMode(s),
      options: [["", "In step with the work done"], ["pct", "A fixed % of the work done"], ["none", "Not recovered"], ["manual", "Typed on each certificate"]],
      tip: "In step with the work done: each certificate takes back the same share of the advance as the share of the work done (work done x advance %). A fixed %: that % of the work done, whatever the advance. Not recovered: nothing taken back (0% on the certificates). Typed: the QS types the amount on each certificate." },
    { k: "adv_rec_pct", label: "Recovery % of the work done", type: "pct", value: s.adv_rec_pct ?? "", ph: "e.g. 20" },
    { k: "adv_rec_from", label: "Start recovering from PC no.", type: "num", value: s.adv_rec_from || 1,
      tip: "1 = from the first certificate. 2 = the first certificate takes nothing back, recovery starts with the second (catching up with the work done so far)." },
    { k: "ret_pct", label: "Retention % (required)", type: "pct", value: edit ? (s.ret_pct ?? 0) : (s.ret_pct ?? ""), ph: "Pick 0, 5% or 10%", quick: [["None (0)", el => el.value = 0], ["5%", el => el.value = 5], ["10%", el => el.value = 10]], tip: "Held from each certificate as the agreement says - printed on the certificate. No retention: press None (0)." },
    { k: "vat_pct", label: "VAT %", type: "pct", value: s.vat_pct ?? 5, quick: [["5%", el => el.value = 5], ["0", el => el.value = 0]] },
    { k: "start_date", label: "Commencement date", type: "date", value: s.start_date || today() },
    { k: "agreement_date", label: "Agreement date", type: "date", value: s.agreement_date || "" },
    { k: "contract_type", label: "Contract type", type: "combo", options: ["Lump sum contract", "Contract progressive payment", "Unit rate re-measurement contract", "Manpower rates"], value: s.contract_type || "" },
    { k: "pay_terms", label: "Payment terms (printed on the certificate)", type: "area", full: true, value: s.pay_terms || "", tip: "Written for you from the advance and retention % while you leave it as it is. Type over it if the agreement words it differently.", ph: "10% advance against security cheque\n100% progressive payment after certification\n10% retention" },
    { k: "notes", label: "Notes", type: "area", value: s.notes || "" },
  ], async v => {
    if (v.ret_pct === "" || v.ret_pct === null || v.ret_pct === undefined || isNaN(Number(v.ret_pct))) throw new Error("Retention: pick None (0), 5% or 10%, or type the % the agreement says.");
    const trn = String(v.trn || "").replace(/\D/g, "");
    if (trn && trn.length !== 15) throw new Error("A TRN has 15 digits.");
    v.trn = trn;
    const sup = m.suppliers.find(x => x.name.toLowerCase() === v.name.toLowerCase());
    if (!v.contract_type && v.kind === "Manpower") v.contract_type = "Manpower rates";
    if (sup) v.supplier_id = sup.id;
    let sid = edit ? s.id : null;
    if (edit) await PATCH(`/store/est/subs/${s.id}`, v);
    else {
      v.project_id = ST.pid; const r = await POST("/store/est/subs", v); sid = r.id;
      if (pre && pre.final_id) await PATCH(`/store/est/finals/${pre.final_id}`, { sub_id: r.id });      // made from the finalization log: linked to its line
      else if (!window.PREV_NO_OPEN) ST.openAfter = r.id;        // not while bringing in previous records: the next file opens instead
    }
    // the priced schedule read from the agreement becomes the item schedule (certified line by line)
    let n = 0;
    if (ag && ag.items.length && $("#ag-items") && $("#ag-items").checked) {
      const remeasure = /re-?measure|unit rate/i.test(v.contract_type || "");
      await PUT(`/store/est/subs/${sid}/items`, { items: ag.items.map(x => ({ bill: x.bill, bill_title: x.bill_title, section: x.section || "", no: x.no, description: x.description,
        qty: x.qty || "", unit: x.unit || "", rate: x.rate || "", amount: x.amount, measure: remeasure && x.qty && x.rate ? "qty" : "pct" })) });
      n = ag.items.length;
    }
    await reload(); toast((edit ? "Saved" : "Subcontract added") + (n ? ` with its ${n}-line schedule` : ""));
    if (ST.openAfter) { openSub(ST.openAfter); ST.openAfter = null; }
  }, { del: edit ? async () => { await DEL(`/store/est/subs/${s.id}`); closeDrawer(); reload(); toast("Removed"); } : null, wide: true,
    after: () => { subAutoFill(edit, s); agreementBar(edit, s, r => { ag = r; }); recShow(); const m = $("#f-adv_rec_mode"); if (m) m.addEventListener("change", recShow); } });
}
// Read from a document - on any Estimation form. The file is opened on this computer (portal/est/agreement.js);
// only its words go to /store/est/read/<kind>, which finds the form's details. Nothing is uploaded or kept.
//   doc = { kind, what: "tender invitation", extra: () => ({...}), keep: r => {...} }
function docBar(doc) {
  const body = $("#m-body"); if (!body || !window.readAgreement) return;
  const bar = h(`<div class="agbar"><div class="agrow"><button type="button" class="btn btn-ghost" id="doc-pick">Read from document</button>
      <span class="small muted">Read from the ${esc(doc.what)} - the form fills in for you to check. ${tip("The file is opened on this computer only: it is not uploaded or kept anywhere. Its words are read for the details of this form; check them, then Save.")}</span>
      <input type="file" id="doc-file" accept=".pdf,.docx,.xlsx,.xlsm,.xls,.jpg,.jpeg,.png,image/*" hidden></div><div id="doc-out"></div></div>`);
  body.insertBefore(bar, body.firstChild);
  $("#doc-pick").onclick = () => $("#doc-file").click();
  $("#doc-file").onchange = async e => {
    const file = e.target.files[0]; e.target.value = ""; if (!file) return;
    const out = $("#doc-out"); out.innerHTML = `<div class="agnote">Reading ${esc(file.name)} ...</div>`;
    try {
      const d = await readAgreement(file, m => { out.innerHTML = `<div class="agnote">${esc(m)}</div>`; });
      const r = await POST(`/store/est/read/${doc.kind}`, Object.assign({ lines: d.lines }, doc.extra ? doc.extra() : {}));
      const filled = docFill(r.fields || {});
      if (doc.keep) doc.keep(r);
      const miss = (doc.want || []).filter(w => !filled.includes(w[0])).map(w => w[1]);
      out.innerHTML = `<div class="agres"><div><b>Read from ${esc(file.name)}</b></div>
        <div class="small">${r.found && r.found.length ? "Filled in: " + r.found.map(esc).join(", ") : "Nothing on this form could be found in the file - type it in."}${miss.length && r.found && r.found.length ? `<br><span class="warn-t">Not found - type it: ${miss.map(esc).join(", ")}</span>` : ""}</div>
        ${(r.notes || []).map(n => `<div class="small warn-t">${esc(n)}</div>`).join("")}${doc.more ? doc.more(r) : ""}</div>`;
    } catch (er) { out.innerHTML = `<div class="agnote bad">${esc(er.message || String(er))}</div>`; }
  };
}
// Put what was read into the form's boxes; a list picks the choice that matches; notes are added to, not replaced.
function docFill(f) {
  const done = [];
  Object.entries(f).forEach(([k, v]) => {
    const el = document.getElementById("f-" + k); if (!el || v === null || v === undefined || v === "") return;
    if (el.tagName === "SELECT") {
      const t = String(v).toLowerCase(), opt = [...el.options].find(o => o.value.toLowerCase() === t || o.text.toLowerCase() === t)
        || [...el.options].find(o => o.value && (o.text.toLowerCase().includes(t) || t.includes(o.text.toLowerCase().split(" (")[0])));
      setField(k, opt ? opt.value : v);
    } else if (el.tagName === "TEXTAREA" && el.value.trim() && !el.value.includes(String(v))) setField(k, el.value.trim() + "\n" + v);
    else setField(k, v);
    done.push(k);
  });
  return done;
}
// Read the agreement: the file is opened on this computer (portal/est/agreement.js); only its words go to
// the server, which finds the details and the priced schedule. The form is filled to check, then Save.
function agreementBar(edit, s, keep) {
  const body = $("#m-body"); if (!body || !window.readAgreement) return;
  const has = edit && (s.items || 0) > 0;
  const bar = h(`<div class="agbar"><div class="agrow"><button type="button" class="btn btn-ghost" id="ag-pick">Read from agreement</button>
      <span class="small muted">The details and the priced schedule are filled in for you to check. ${tip("The file is opened on this computer only: it is not uploaded or kept anywhere. Its text is read for the subcontractor, agreement no. and date, contract value and type, advance, retention, payment terms and every priced line of the schedule. Check what is filled in, then Save.")}</span>
      <input type="file" id="ag-file" accept=".pdf,.docx,.xlsx,.xlsm,.xls,.jpg,.jpeg,.png,image/*" hidden></div><div id="ag-out"></div></div>`);
  body.insertBefore(bar, body.firstChild);
  $("#ag-pick").onclick = () => $("#ag-file").click();
  $("#ag-file").onchange = async e => {
    const file = e.target.files[0]; e.target.value = ""; if (!file) return;
    const out = $("#ag-out"); out.innerHTML = `<div class="agnote">Reading ${esc(file.name)} ...</div>`;
    try {
      const doc = await readAgreement(file, m => { out.innerHTML = `<div class="agnote">${esc(m)}</div>`; });
      const r = await POST("/store/est/subs/agreement/read", { lines: doc.lines, trades: ST.meta.trades });
      keep(r); agreementFill(r, file.name, has, out);
    } catch (er) { out.innerHTML = `<div class="agnote bad">${esc(er.message || String(er))}</div>`; }
  };
}
function agreementFill(r, fname, has, out) {
  const f = r.fields, set = (k, v) => { if (v !== undefined && v !== null && v !== "") setField(k, v); };
  const pt = $("#f-pay_terms"); if (pt) pt.dataset.ag = "1";              // the agreement's own words - not rewritten from the %
  const nm = $("#f-name"); if (nm) nm.dataset.ag = "1";
  set("name", f.name); set("kind", f.kind || "Subcontract"); set("scope", f.scope); set("trade", f.trade);
  set("agreement", f.agreement); set("lpo", f.lpo); set("value", f.value);
  set("adv_pct", f.adv_pct ?? 0); set("ret_pct", f.ret_pct ?? 0); set("vat_pct", f.vat_pct);
  set("agreement_date", f.agreement_date); set("start_date", f.start_date || f.agreement_date);
  set("contract_type", f.contract_type); set("pay_terms", f.pay_terms);
  const nt = $("#f-notes");
  if (nt && !nt.value.trim()) nt.value = [f.works ? "Scope: " + f.works : "", f.quote ? "Quotation: " + f.quote : "", f.address ? "Address: " + f.address : "", f.trn ? "TRN: " + f.trn : ""].filter(Boolean).join("\n");
  const want = [["Subcontractor", f.name], ["Agreement no.", f.agreement], ["Agreement date", f.agreement_date], ["Contract value", f.value], ["Contract type", f.contract_type],
                ["Advance %", f.adv_pct], ["Retention %", f.ret_pct], ["Payment terms", f.pay_terms], ["Work", f.scope]];
  const miss = want.filter(w => w[1] === undefined || w[1] === null || w[1] === "").map(w => w[0]);
  const c = r.checks || {}, it = r.items || [];
  const secs = (c.sections || []).map(x => `<span class="${x.ok ? "ok" : "bad"}">${esc(x.bill)} ${money(x.total)}${x.ok ? " &#10003;" : ` (agreement says ${money(x.in_doc)})`}</span>`).join(" ");
  out.innerHTML = `<div class="agres">
    <div><b>Read from ${esc(fname)}</b>${r.known ? ` <span class="small muted">- ${esc(f.name)} is already known (Store & Purchasing)</span>` : ""}</div>
    <div class="small">Filled in: ${r.found.map(esc).join(", ") || "nothing"}${miss.length ? `<br><span class="warn-t">Not found - type it: ${miss.map(esc).join(", ")}</span>` : ""}</div>
    ${it.length ? `<div class="agsched"><label class="chk"><input type="checkbox" id="ag-items" ${has ? "" : "checked"} ${has ? "disabled" : ""}> Save the ${it.length} priced line${it.length > 1 ? "s" : ""} as the item schedule</label>
      <span class="${c.match ? "ok" : "bad"}">${money(c.items_total)} ${c.match ? "= contract value &#10003;" : c.contract_value != null ? `&ne; contract value ${money(c.contract_value)}` : ""}</span> ${secs}
      ${has ? `<div class="small warn-t">This subcontract already has an item schedule - change it in Item schedule.</div>` : ""}
      <details><summary>See the lines</summary><div class="tw"><table class="t"><thead><tr><th>Bill</th><th>No</th><th>Description</th><th class="r">Qty</th><th>Unit</th><th class="r">Rate</th><th class="r">Amount</th></tr></thead><tbody>
      ${it.map(x => `<tr><td>${esc(x.bill)}</td><td>${esc(x.no)}</td><td class="d">${esc(x.description)}</td><td class="r">${x.qty ?? ""}</td><td>${esc(x.unit)}</td><td class="r">${x.rate ? money(x.rate) : ""}</td><td class="r">${money(x.amount)}</td></tr>`).join("")}
      </tbody></table></div></details></div>` : ""}
    ${(r.notes || []).map(n => `<div class="small warn-t">${esc(n)}</div>`).join("")}</div>`;
}
// The next agreement number on this project: IC/912/SCA/03/26 after .../02/...
function nextAgreement() {
  const code = ST.b.project.code, yy = String(today()).slice(2, 4);
  const n = Math.max(0, ...ST.b.subs.map(x => { const m = String(x.agreement || "").match(/SCA\/(\d+)\//i); return m ? +m[1] : 0; }));
  return `IC/${code}/SCA/${pad(n + 1, 2)}/${yy}`;
}
// Payment terms in the words the certificates use, from the advance and retention %.
function payTermsText(adv, ret, kind) {
  const L = [];
  if (+adv) L.push(`${+adv}% advance against security cheque`);
  L.push(kind === "Manpower" ? "Monthly payment against certified timesheets" : "100% progressive payment after certification");
  if (+ret) L.push(`${+ret}% retention`);
  return L.join("\n");
}
function subAutoFill(edit, s) {
  const m = ST.meta, g = k => ($("#f-" + k) || {}).value || "";
  const typed = {};                                     // what the user typed himself is never overwritten
  ["trade", "kind", "adv_pct", "ret_pct", "vat_pct", "contract_type", "pay_terms", "scope", "agreement"].forEach(k => {
    const el = $("#f-" + k); if (el) el.addEventListener("keydown", () => { typed[k] = true; });
  });
  let autoTerms = !edit || !s.pay_terms || s.pay_terms === payTermsText(s.adv_pct, s.ret_pct, s.kind);
  const pt = $("#f-pay_terms"); if (pt) pt.addEventListener("input", e => { if (e.isTrusted) autoTerms = false; });
  const terms = () => { if (autoTerms && pt && !pt.dataset.ag) pt.value = payTermsText(g("adv_pct"), g("ret_pct"), g("kind")); };
  const set = (k, v) => { if (!typed[k] && v !== undefined && v !== null && v !== "") setField(k, v); };
  const nm = $("#f-name");
  const fromName = () => {
    // his address, phone and TRN from Store & Purchasing > Suppliers, into boxes still empty
    const sp = (m.suppliers || []).find(x => x.name.toLowerCase() === g("name").trim().toLowerCase());
    if (sp) { ["address", "phone", "trn"].forEach(k => { if (sp[k] && !g(k)) setField(k, sp[k]); }); }
    if (edit || (nm && nm.dataset.ag)) return;           // filled from the agreement itself: its own terms stand
    const t = m.sub_terms && m.sub_terms[g("name").trim().toLowerCase()]; if (!t) return;
    set("kind", t.kind); set("trade", t.trade); set("adv_pct", t.adv_pct); set("ret_pct", t.ret_pct); set("vat_pct", t.vat_pct);
    set("contract_type", t.contract_type); if (!g("scope")) set("scope", t.scope);
    if (t.pay_terms && pt) { pt.value = t.pay_terms; autoTerms = false; } else terms();
    toast("Filled in from the last subcontract with " + g("name") + " - check and change anything");
  };
  if (nm) { nm.addEventListener("change", fromName); }
  const sc = $("#f-scope");
  if (sc) sc.addEventListener("change", () => { const t = m.scope_trade && m.scope_trade[g("scope").trim().toLowerCase()]; if (t) set("trade", t); });
  const kd = $("#f-kind");
  if (kd) kd.addEventListener("input", () => {
    const k = g("kind");
    if (k === "Manpower") { if (g("trade") !== "Manpower") kd._trade = g("trade"); set("trade", "Manpower"); if (!g("contract_type")) setField("contract_type", "Manpower rates"); }
    else if (g("trade") === "Manpower" && kd._trade) { set("trade", kd._trade); if (g("contract_type") === "Manpower rates") setField("contract_type", ""); }
    if (k === "LPO" && !g("contract_type")) setField("contract_type", "Lump sum contract");
    const ag = $("#f-agreement");
    if (!edit && ag && !typed.agreement) ag.value = k === "LPO" ? "" : (ag.value || nextAgreement());
    terms();
  });
  ["adv_pct", "ret_pct"].forEach(k => { const el = $("#f-" + k); if (el) el.addEventListener("input", terms); });
  $$('[data-q^="adv_pct:"], [data-q^="ret_pct:"]').forEach(b => b.addEventListener("click", () => setTimeout(terms, 0)));
  if (!edit && pt && !pt.value) terms();
}
// The subcontract's own page: its figures, variations and every certificate (the Excel sheet per subcontractor).
function openSub(sid) {
  ST.drawer = () => {
    const s = ST.b.subs.find(x => x.id === sid); if (!s) { closeDrawer(); return; }
    const fig = (l, v, cls = "") => `<div class="fig ${cls}"><div class="l">${l}</div><div class="v">${v}</div></div>`;
    drawer(`${esc(s.name)} <span class="muted small">${esc(s.scope)}</span>`, `
      <div class="tools"><button class="btn btn-primary" id="s-inv">+ Invoice received</button>${s.pcs.some(p => p.pc_type === "Advance") ? "" : `<button class="btn btn-ghost" id="s-adv">+ Advance PC</button>`}<button class="btn btn-plain" id="s-vo">+ Variation</button><button class="btn btn-plain" id="s-edit">Edit subcontract</button><span class="spacer"></span>${xpButtons("subpcs", { pid: ST.pid, sub_id: s.id, name: s.name })}</div>
      <div class="strip">
        ${fig("Value", s.remeasure ? '<span style="font-size:15px">Re-measurable</span>' : money(s.value, false))}${fig("Variations", money(s.vo_total, false))}${fig("Revised", money(s.revised, false))}
        ${fig("Work done", money(s.work_done, false) + `<div class="s">${s.remeasure ? "re-measured" : s.done_pct + "%"}</div>`)}${fig("Certified", money(s.certified, false))}${fig("Paid", money(s.paid, false), "green")}
        ${fig("To pay", money(s.to_pay, false), s.to_pay > 0.005 ? "amber" : "")}${fig("Advance left", money(s.adv_left, false))}${fig("Retention held", money(s.ret_left, false))}${fig("Balance work", money(s.balance, false), s.balance < 0 ? "red" : "")}
      </div>
      <div class="card"><h3>Payment certificates ${tip("Figures to date. 'This PC' = net to date now less net to date at the last PC, so the certificates always add up to the total. Click a row to certify or change it.")}</h3>
      ${s.pcs.length ? `<div class="tw"><table class="t"><thead><tr><th>PC</th><th>Invoice</th><th class="r">Inv. amount</th><th class="r">Work done to date</th><th class="r">Adv. recovery</th><th class="r">Retention</th><th class="r">Other ded.</th><th class="r">Ret. release</th><th class="r">Net to date</th><th class="r">This PC</th><th class="r">Payable</th><th class="r">Paid</th><th>Status</th><th></th></tr></thead><tbody>
      ${s.pcs.map(p => `<tr class="rowc" data-pc="${p.id}"><td class="nowrap"><b>PC ${pad(p.seq, 2)}</b>${p.pc_type !== "Interim" ? `<div class="small muted">${esc(p.pc_type)}</div>` : ""}</td><td class="small">${esc(p.inv_ref)}<div class="muted">${dt(p.inv_date || p.received)}</div></td><td class="r">${money(p.inv_amount)}</td>
        <td class="r">${money(p.work_cum)}${p.adv_amount ? `<div class="small muted">adv. ${money(p.adv_amount)}</div>` : ""}</td><td class="r neg">${p.adv_rec_cum ? "-" + money(p.adv_rec_cum) : money(0)}</td><td class="r neg">${p.ret_cum ? "-" + money(p.ret_cum) : money(0)}</td><td class="r neg">${p.other_cum ? "-" + money(p.other_cum) : money(0)}</td><td class="r">${money(p.ret_rel_cum)}</td>
        <td class="r">${money(p.net_cum)}</td><td class="r"><b>${money(p.this, false)}</b></td><td class="r">${money(p.payable, false)}</td><td class="r">${money(p.paid_amount)}</td><td>${st(p.status)}</td>
        <td class="nowrap"><button class="btn btn-plain btn-sm" data-print="${p.id}">Print</button>${p.status !== "Paid" || ST.meta.me.admin ? `<button class="btn btn-ghost btn-sm" data-pcdel="${p.id}" title="Delete this certificate (an invoice entered twice, or by mistake). The later certificates are numbered down.">Delete</button>` : ""}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">No certificates yet. Press <b>+ Invoice received</b> when the first invoice comes in.</div>`}</div>
      <div class="card"><h3>Item schedule (Appendix A) ${tip("The agreement's BOQ lines, set up once. Each certificate is then made line by line on the sheet: % done, measured size or quantity to date - the rest is worked out and printed as Appendix A.")}<span class="spacer"></span><button class="btn btn-primary btn-sm" id="s-up" title="The agreement BOQ or any payment certificate (Appendix A / Bill sheets). Every line comes in, checked against the sheet's totals - the file is not stored.">Upload</button><input type="file" id="s-up-f" accept=".xlsx,.xlsm,.pdf,.docx,.jpg,.jpeg,.png" hidden><button class="btn btn-ghost btn-sm" id="s-paste">Paste from Excel</button><button class="btn btn-ghost btn-sm" id="s-items">${s.items ? "Edit schedule" : "Set up"}</button></h3>
        <div class="small muted">${s.items ? `${s.items} lines - certificates are made on the sheet, line by line.` : "None yet - certificates use the quick form (one figure for the work done). Upload the agreement BOQ or a payment certificate Excel to certify line by line."}</div></div>
      <div class="card"><h3>Variations to this subcontract</h3>
      ${s.vos.length ? `<div class="tw"><table class="t"><thead><tr><th>Date</th><th>Ref.</th><th>Description</th><th class="r">Amount</th></tr></thead><tbody>${s.vos.map(v => `<tr class="rowc" data-vo="${v.id}"><td>${dt(v.on_date)}</td><td>${esc(v.ref)}</td><td>${esc(v.title)}</td><td class="r">${money(v.amount, false)}</td></tr>`).join("")}<tr class="tot"><td colspan="3">Total</td><td class="r">${money(s.vo_total, false)}</td></tr></tbody></table></div>` : '<div class="muted small">None.</div>'}</div>
      <div class="card"><h3>Details</h3><div class="small">${esc(s.kind)} · ${esc(s.trade)} · Agreement ${esc(s.agreement || "-")} · LPO ${esc(s.lpo || "-")} · Advance ${s.adv_pct}%${({ none: " (not recovered)", manual: " (recovery typed on each PC)", pct: ` (recovered at ${s.adv_rec_pct}% of the work)` })[recMode(s)] || ""}${(s.adv_rec_from || 1) > 1 && !["none", "manual"].includes(recMode(s)) ? ` from PC ${s.adv_rec_from}` : ""} · Retention ${s.ret_pct}% · VAT ${s.vat_pct}%${s.notes ? "<br>" + esc(s.notes) : ""}</div></div>`);
    $("#s-inv").onclick = () => invoiceForm(s.id);
    const sa = $("#s-adv"); if (sa) sa.onclick = () => modal("Advance payment certificate", [
      { k: "adv_amount", label: "Advance amount (AED)", type: "money", value: s.adv_pct ? r2(s.value * s.adv_pct / 100) : "", focus: true,
        hint: s.adv_pct ? `${s.adv_pct}% of ${money(s.value, false)} - change it if the agreement says another figure` : "No advance % on the subcontract: type the amount",
        quick: [[`${s.adv_pct || 10}%`, el => el.value = r2(s.value * (s.adv_pct || 10) / 100)]] },
      { k: "inv_ref", label: "Invoice / request ref.", value: "Advance" }],
      async v => { await POST("/store/est/subpcs", { sub_id: s.id, pc_type: "Advance", adv_amount: v.adv_amount, inv_ref: v.inv_ref }); await reload(); toast("Advance certificate made - recovered from the next certificates"); });
    $("#s-vo").onclick = () => voSubForm(s);
    $("#s-edit").onclick = () => subForm(s);
    $$("[data-pc]").forEach(r => r.onclick = e => { if (e.target.closest("[data-print],[data-pcdel]")) return; openCert(s.id, +r.dataset.pc); });
    // Remove a certificate: pressed twice (the button asks once), never a browser box.
    $$("[data-pcdel]").forEach(b => b.onclick = async e => {
      e.stopPropagation();
      const p = s.pcs.find(x => x.id === +b.dataset.pcdel);
      if (!(await confirmDelete(`Delete PC ${pad(p.seq, 2)} of ${s.name}?`, `Invoice ${esc(p.inv_ref || "-")} · AED ${money(p.payable, false)}. The later certificates are numbered down.`))) return;
      try { await DEL(`/store/est/subpcs/${p.id}`); await reload(); toast(`PC ${pad(p.seq, 2)} removed (${p.inv_ref || "no invoice no."})`); }
      catch (er) { fail(er); }
    });
    $("#s-items").onclick = () => scheduleEditor(s.id);
    $("#s-paste").onclick = () => pasteItems(s.id, s, () => reload());
    const sf = $("#s-up-f"); $("#s-up").onclick = () => sf.click();
    sf.onchange = () => { const f = sf.files[0]; sf.value = ""; if (f) importItems(s.id, f, async () => { await reload(); scheduleEditor(s.id); }); };
    $$("[data-print]").forEach(b => b.onclick = () => exportGo("preview", "pc", { id: +b.dataset.print }));
    $$("[data-vo]").forEach(r => r.onclick = () => voSubForm(s, s.vos.find(v => v.id === +r.dataset.vo)));
  };
  ST.drawer();
}
function voSubForm(s, v) {
  v = v || {};
  modal(v.id ? "Variation" : "Variation to " + s.name, [
    { k: "title", label: "Description", value: v.title || "", full: true, focus: true },
    { k: "sign", label: "Type", type: "seg", options: ["Addition", "Omission"], value: (v.amount || 0) < 0 ? "Omission" : "Addition", tip: "Omission takes the amount off the subcontract - type the amount without a minus." },
    { k: "amount", label: "Amount (AED)", type: "money", value: v.amount ? Math.abs(v.amount) : "" },
    { k: "on_date", label: "Date", type: "date", value: v.on_date || today() }, { k: "ref", label: "Variation no.", value: v.ref || nextSubVoRef(s), ro: true, tip: "Numbered for you, in order: V01, V02, V03 ... The subcontractor's own reference can go in the description." },
  ], async x => { const a = Math.abs(Number(String(x.amount || 0).replace(/,/g, "")) || 0); x.amount = x.sign === "Omission" ? -a : a; delete x.sign; if (v.id) await PATCH(`/store/est/subvos/${v.id}`, x); else await POST("/store/est/subvos", Object.assign(x, { sub_id: s.id })); await reload(); toast("Saved"); },
  { doc: { kind: "subvo", what: "variation letter or the subcontractor's quotation", want: [["title", "Description"], ["amount", "Amount"]] },
    del: v.id ? async () => { await DEL(`/store/est/subvos/${v.id}`); reload(); } : null });
}
// Invoice received: the first step. Only the reference and amount are typed.
function invoiceForm(sid, keep) {
  const subs = ST.b.subs.filter(x => x.status !== "Cancelled");
  let read = null;
  // No subcontractor is picked for you: chosen by hand, or found from the invoice (a new one can be added from it).
  modal("Invoice received", [
    { k: "sub_id", label: "Subcontractor", type: "select", noseg: true, options: [["", subs.length ? "- Pick the subcontractor -" : "- None on this project yet: read the invoice to add it -"], ...subs.map(x => [x.id, x.name])], value: sid || "", full: true },
    { k: "inv_ref", label: "Invoice no.", focus: true }, { k: "inv_amount", label: "Invoice amount (AED)", type: "money" },
    { k: "inv_date", label: "Invoice date", type: "date", value: today() }, { k: "received", label: "Received in office", type: "date", value: today() },
    { k: "to_site", label: "Sent to site for checking", type: "check", value: true, text: "Send to site today" },
  ], async v => {
    if (!v.sub_id) throw new Error("Pick the subcontractor (or read the invoice and add it as a new one).");
    const send = v.to_site; delete v.to_site;
    if (read && read.inv_lines) v.inv_lines = read.inv_lines;          // the bill's own lines, read from the invoice
    else if (keep && keep.inv_lines) v.inv_lines = keep.inv_lines;
    const r = await POST("/store/est/subpcs", v);
    if (send) await POST(`/store/est/subpcs/${r.id}/step`, { step: "At site" });
    await reload(); toast(send ? "Invoice logged and sent to site" : "Invoice logged");
  }, { doc: { kind: "invoice", what: "subcontractor's invoice", want: [["sub_id", "Subcontractor"], ["inv_ref", "Invoice no."], ["inv_amount", "Invoice amount"]],
    extra: () => ({ subs: subs.map(x => ({ id: x.id, name: x.name })) }), keep: r => { read = r.fields; setTimeout(() => newSubButton(r.fields), 0); },
    more: r => (r.fields.new_sub ? `<div class="agrow" style="margin-top:6px"><button type="button" class="btn btn-primary" id="inv-newsub">+ Add ${esc(r.fields.new_sub)} as a new subcontractor</button></div>` : "")
      + (r.fields.inv_lines ? `<div class="small muted">${JSON.parse(r.fields.inv_lines).length} line(s) of the bill kept with the invoice - they show on its payment certificate.</div>` : "") } });
  if (keep) Object.entries(keep).forEach(([k, val]) => { const el = $("#f-" + k); if (el && val !== undefined && val !== null && val !== "") el.value = val; });
}
// The invoice is from a subcontractor not on this project: add it (name and scope from the invoice) and pick it.
function newSubButton(f) {
  const btn = $("#inv-newsub"); if (!btn || !f.new_sub) return;
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const sup = (ST.meta.suppliers || []).find(x => x.name.toLowerCase() === f.new_sub.toLowerCase());
      const r = await POST("/store/est/subs", { project_id: ST.pid, name: f.new_sub, scope: f.scope_hint || "", supplier_id: sup ? sup.id : null, status: "Active" });
      const keep = { inv_lines: f.inv_lines || "" }; ["inv_ref", "inv_amount", "inv_date", "received"].forEach(k => { const el = $("#f-" + k); if (el) keep[k] = el.value; });
      await reload();
      invoiceForm(r.id, keep);
      toast(`${f.new_sub} added to this project - check the contract value on Subcontracts later`);
    } catch (e) { btn.disabled = false; toast(e.message || String(e), { err: true }); }
  };
}
// Certify: the one number to type is the work done to date.
function certifyForm(sid, pcid) {
  const s = ST.b.subs.find(x => x.id === sid), p = s.pcs.find(x => x.id === pcid);
  const idx = s.pcs.indexOf(p), prev = s.pcs[idx - 1] || null;
  const locked = (p.status === "Paid" || s.pcs.some(x => x.seq > p.seq && x.status === "Paid")) && !ST.meta.me.admin;     // paid, or history of a paid one
  const fields = [
    { k: "work_cum", label: "Value of work done to date (AED)", type: "money", value: p.work_cum, focus: true, tip: "Everything done up to now, not just this month. The earlier PCs are taken off automatically.",
      quick: [["Same as last", el => el.value = prev ? prev.work_cum : 0], ...[25, 50, 75, 90, 100].map(n => [n + "%", el => el.value = r2(s.revised * n / 100)])],
      hint: `Revised value ${money(s.revised, false)}${prev ? ` · last PC ${money(prev.work_cum, false)}` : ""}` },
    { k: "mos_cum", label: "Material on site to date", type: "money", value: p.mos_cum || "" },
    { k: "other_cum", label: "Other deductions to date", type: "money", value: p.other_cum || "", tip: "Back-charges, manpower supplied by us, damages ... to date." },
    { k: "other_note", label: "Deduction reason", type: "combo", value: p.other_note, options: ["Manpower supplied by main contractor", "Back-charge", "Material supplied", "Damages", "Rectification"] },
    { k: "adv_rec_cum", label: `Advance recovered to date ${({ none: "(not recovered)", manual: "(type it)", pct: "(" + s.adv_rec_pct + "% of the work)" })[recMode(s)] || (s.adv_pct ? "(" + s.adv_pct + "%)" : "")}`, type: "money", value: p.adv_rec_cum || "",
      tip: "Worked out from how the advance is recovered on the subcontract. Typing a figure here fixes it for this certificate." },
    { k: "adv_auto", label: " ", type: "check", value: p.adv_auto, text: "Work it out from the %" },
    { k: "ret_cum", label: `Retention to date ${s.ret_pct ? "(" + s.ret_pct + "%)" : ""}`, type: "money", value: p.ret_cum || "" },
    { k: "ret_auto", label: " ", type: "check", value: p.ret_auto, text: "Work it out from the %" },
    { k: "ret_rel_cum", label: "Retention released to date", type: "money", value: p.ret_rel_cum || "", quick: [["Release half", el => el.value = r2(Number($("#f-ret_cum").value || 0) / 2)], ["Release all", el => el.value = $("#f-ret_cum").value || 0], ["None", el => el.value = 0]] },
    { k: "adv_amount", label: "Advance paid on this PC", type: "money", value: p.adv_amount || "" },
    { k: "pc_type", label: "Type", type: "select", options: ["Interim", "Advance", "Final", "Retention release"], value: p.pc_type || "Interim" },
    { k: "inv_ref", label: "Invoice no.", value: p.inv_ref }, { k: "inv_amount", label: "Invoice amount", type: "money", value: p.inv_amount || "" },
    { k: "issued", label: "IPC issued date", type: "date", value: p.issued || today(), tip: "Printed on the certificate. Today unless changed." },
    { k: "remarks", label: "Remarks", type: "area", value: p.remarks },
  ];
  const live = () => {
    const v = readForm(fields);
    const n = x => Number(String(x || 0).replace(/,/g, "")) || 0;
    const advPaidBefore = prev ? prev.adv_paid_cum : 0, advPaid = advPaidBefore + n(v.adv_amount), work = n(v.work_cum);
    if (v.adv_auto) { const pct = s.adv_pct || (s.revised ? 100 * advPaid / s.revised : 0); const a = pct ? Math.min(advPaid, work * pct / 100) : Math.min(advPaid, n(v.adv_rec_cum)); $("#f-adv_rec_cum").value = r2(a); }
    if (v.ret_auto) $("#f-ret_cum").value = r2((work + Number(p.var_cum || 0)) * s.ret_pct / 100);
    $("#f-adv_rec_cum").disabled = v.adv_auto; $("#f-ret_cum").disabled = v.ret_auto;
    const now = { work_cum: work, mos_cum: n(v.mos_cum), adv_amount: n(v.adv_amount), adv_rec_cum: n($("#f-adv_rec_cum").value), ret_cum: n($("#f-ret_cum").value), ret_rel_cum: n(v.ret_rel_cum), other_cum: n(v.other_cum) };
    const list = s.pcs.map(x => x.id === p.id ? Object.assign({}, x, now) : x);
    const c = chainCalc(list, s.adv_pct, s.ret_pct, s.vat_pct)[idx];
    const pn = idx ? chainCalc(list, s.adv_pct, s.ret_pct, s.vat_pct)[idx - 1].net : 0;
    const row = (l, a, cls = "") => `<tr class="${cls}"><td>${l}</td><td class="r">${money(a, false)}</td></tr>`;
    $("#calc").innerHTML = `<table>${row("Work done to date", work)}${now.mos_cum ? row("Material on site", now.mos_cum) : ""}${c.advPaid ? row("Advance paid", c.advPaid) : ""}${now.adv_rec_cum ? row("Less advance recovered", -now.adv_rec_cum) : ""}${now.ret_cum ? row("Less retention", -now.ret_cum) : ""}${now.ret_rel_cum ? row("Add retention released", now.ret_rel_cum) : ""}${now.other_cum ? row("Less other deductions", -now.other_cum) : ""}
      ${row("Net to date", c.net, "b")}${row("Less previous certificates", -pn)}${row("This certificate", c.this, "b")}${row("VAT " + s.vat_pct + "%", c.vat)}${row("Amount payable", c.payable, "p")}</table>
      ${work > s.revised + 0.01 ? `<div class="warn">Work done is above the revised value (${money(s.revised, false)}). Add a variation if this is right.</div>` : ""}${c.this < 0 ? '<div class="warn">This certificate is negative - it takes money back.</div>' : ""}`;
  };
  modal(`PC ${pad(p.seq, 2)} - ${s.name}`, fields, async v => {
    if (locked) throw new Error("This certificate is paid - its figures are locked.");
    delete v.adv_rec_cum_x;
    if (v.adv_auto) delete v.adv_rec_cum; if (v.ret_auto) delete v.ret_cum;
    await PATCH(`/store/est/subpcs/${p.id}`, v);
    if (p.status === "At site" && Number(v.work_cum || 0) > 0) await POST(`/store/est/subpcs/${p.id}/step`, { step: "Certified" }).catch(() => {});
    await reload(); toast("Certificate saved");
  }, { wide: true, live, top: '<div class="calc" id="calc" style="margin:0 0 12px"></div>', save: locked ? "Locked - paid" : "Save certificate",
       extra: `<button class="btn btn-plain" id="m-sheet" title="Line by line from the item schedule, deductions with their details, the subcontractor's bill and the sign-off">Full sheet</button><button class="btn btn-plain" id="m-print">Print PC</button>`,
       del: p.status !== "Paid" ? async () => { await DEL(`/store/est/subpcs/${p.id}`); reload(); toast("Removed"); } : null,
       after: () => { $("#m-print").onclick = () => exportGo("preview", "pc", { id: p.id }); $("#m-sheet").onclick = async () => { if (await closeModal()) pcSheet(p.id); }; if (locked) $("#m-save").disabled = true; } });
}

// ---------------- Subcontractors > invoice tracker ----------------
// A certificate's way: invoice received -> site -> certified -> prepared (QS) -> approved (contracts manager) ->
// verified (Accounts) -> approved (Managing Director) -> paid (Accounts). Each step is a click by the person whose
// turn it is: their name and the time go on it, the next person is told. Where it waits, and for how long, shows.
const STEPS = ["Received", "At site", "Certified", "Prepared", "CM approved", "Verified", "MD approved", "Paid"];
const STEP_LABEL = { "Received": "Received", "At site": "At site", "Certified": "Certified at site", "Prepared": "Prepared", "CM approved": "CM approved",
                     "Verified": "Verified", "MD approved": "MD approved", "Paid": "Paid" };
const STAGE_CHIP = [["At site", "At site"], ["Certified", "To prepare"], ["Prepared", "CM approval"], ["CM approved", "Accounts verify"], ["Verified", "MD approval"], ["MD approved", "To pay"], ["Paid", "Paid"]];
const STEP_DONE = { "At site": "Sent to site", "Certified": "Certified", "Prepared": "Prepared", "CM approved": "Approved", "Verified": "Verified", "MD approved": "MD approved", "Paid": "Paid", "Received": "Received" };
function allPcs() { return ST.b.subs.flatMap(s => s.pcs.map(p => Object.assign({ sub: s }, p))); }
function pcCan(role) { const m = (ST.meta && ST.meta.me) || {}; return (m.pc_can || []).includes(role); }
function pcMine(p) { const m = (ST.meta && ST.meta.me) || {}; return !!(p.flow && p.flow.turn && (m.pc_mine || []).includes(p.flow.turn)); }
function ageTxt(h) { return h < 1 ? "just now" : h < 24 ? `${h} h` : `${Math.floor(h / 24)} day${h >= 48 ? "s" : ""}`; }
function stampTxt(l) { if (!l) return ""; const t = l.at ? `${dt(l.at.slice(0, 10))} ${l.at.slice(11, 16)}` : ""; return `${l.back ? "&#8630; Sent back" : "&#10003; " + esc(STEP_DONE[l.s] || l.s)} - ${esc(l.by || "")}${t ? ", " + t : ""}`; }
// a verified certificate waits with Accounts until "Send to MD"; then it is with the MD
function pcStage(status, fl) { return status === "Verified" ? (fl && fl.md_sent === false ? "Verified - send to MD" : "With the MD") : status === "MD approved" ? "MD approved - to pay" : (STEP_LABEL[status] || status); }
function nextBtns(p) {
  // the buttons for the person whose turn it is (an admin may press any step)
  const st = p.status, t = p.flow && p.flow.turn, mine = pcMine(p), can = t && pcCan(t);
  if (!t || !can) return "";
  const cls = mine ? "btn-ok" : "btn-plain", d = `data-pc="${p.id}" data-sub="${p.sub.id}"`;
  const b = (to, label, c = cls) => `<button class="btn ${c} btn-sm" ${d} data-to="${to}">${label}</button>`;
  const back = ["Prepared", "CM approved", "Verified"].includes(st) && mine ? ` <button class="btn btn-plain btn-sm" ${d} data-back="1" title="Send it back with a note">&#8630; Send back</button>` : "";
  if (st === "Received") return (p.pc_type !== "Interim" ? b("Prepared", "Prepared &#10003;") + " " : b("At site", "Send to site") + " ") + b("Certified", "Certify in office", "btn-plain");
  if (st === "At site") return b("Certified", "Certified &#10003;");
  if (st === "Certified") return b("open", "Open PC", "btn-plain") + " " + b("Prepared", "Prepared &#10003;");
  if (st === "Prepared") return b("CM approved", "Approve &#10003;") + back;
  if (st === "CM approved") return b("Verified", "Verified &#10003;") + back;
  if (st === "Verified") return p.flow && p.flow.md_sent === false ? b("sendmd", "Send to MD &rarr;") + back : b("MD approved", "Approve &#10003;") + back;
  if (st === "MD approved") return b("Paid", "Mark paid");
  return "";
}
SECTIONS["subs.inv"] = el => {
  const f = filt(), all = allPcs();
  const list = all.filter(p => (!f || (f === "__mine" ? pcMine(p) : f === "__stuck" ? p.flow && p.flow.stuck : p.status === f)) && match({ a: p.sub.name, b: p.inv_ref, c: p.status, d: p.sub.scope }))
    .sort((a, b) => (a.status === "Paid") - (b.status === "Paid") || pcMine(b) - pcMine(a) || (b.flow ? b.flow.hours : 0) - (a.flow ? a.flow.hours : 0));
  const n = s => all.filter(p => p.status === s).length, mineN = all.filter(pcMine).length, stuckN = all.filter(p => p.flow && p.flow.stuck).length;
  const r = ST.b.rules;
  const chip = (v, label, c, extra = "") => `<span class="chip ${f === v ? "on" : ""}" data-f="${esc(v)}" ${extra}>${label}<span class="n">${c}</span></span>`;
  el.innerHTML = tools("invoices", { add: `<button class="btn btn-primary" id="add-inv">+ Invoice received</button>`,
      right: `<button class="btn btn-plain btn-sm" id="rules">Days: site ${r.site_days} · PC ${r.pc_days} · stuck after ${r.stuck_days || 2}</button>` }) +
    `<div class="chips crow">${chip("__mine", "Waiting for me", mineN, mineN ? 'style="border-color:#C0392B;font-weight:700"' : "")}${chip("__stuck", "Stuck &gt; " + (r.stuck_days || 2) + " days", stuckN, stuckN ? 'style="color:#B42318;border-color:#E8B4AE;font-weight:700"' : "")}${chip("", "All", all.length)}${n("Received") ? chip("Received", "Received", n("Received")) : ""}${STAGE_CHIP.map(([v, l]) => chip(v, l, n(v))).join("")}</div>` +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>Subcontractor</th><th>PC</th><th>Invoice</th><th class="r">Amount</th><th>Progress &middot; last stamp</th><th>Stage</th><th>Waiting on</th><th>Days here</th><th class="r">Payable</th><th>Next step</th></tr></thead><tbody>
    ${list.map(p => { const i = STEPS.indexOf(p.status), fl = p.flow || {}, mine = pcMine(p);
      return `<tr class="${fl.stuck ? "late-row" : ""}" style="${mine ? "background:#FFF8E6" : ""}" data-row="${p.id}"><td><b>${esc(p.sub.name)}</b><div class="small muted">${esc(p.sub.scope)}</div></td><td class="nowrap">PC ${pad(p.seq, 2)}${p.pc_type !== "Interim" ? ` <span class="small muted">${esc(p.pc_type)}</span>` : ""}</td><td class="small">${esc(p.inv_ref)}</td><td class="r">${money(p.inv_amount)}</td>
      <td><span class="flow">${STEPS.map((s, j) => `<i class="${j < i ? "on" : j === i ? (p.status === "Paid" ? "on" : "cur") : ""}" title="${STEP_LABEL[s]}"></i>`).join("")}</span><div class="small muted" style="margin-top:3px">${stampTxt(fl.last)}</div>${fl.note ? `<div class="small late">&ldquo;${esc(fl.note)}&rdquo;</div>` : ""}</td>
      <td>${st(pcStage(p.status, fl))}</td>
      <td>${fl.turn ? (mine ? `<b style="color:#C0392B">You</b>` : `<b>${esc(fl.waiting)}</b>`) + `<div class="small muted">${esc(fl.task)}</div>` : '<span class="muted">-</span>'}</td>
      <td class="nowrap ${fl.stuck ? "late" : ""}">${fl.turn ? ageTxt(fl.hours) + (fl.stuck ? '<div class="small">stuck</div>' : "") : ""}</td>
      <td class="r">${p.work_cum || p.adv_amount ? money(p.payable, false) : '<span class="muted">-</span>'}</td>
      <td class="nowrap">${nextBtns(p) || (fl.turn ? `<span class="small muted">${esc(fl.waiting)}'s turn</span>` : "")}${p.status === "Verified" && fl.md_sent ? ` <button class="btn btn-plain btn-sm" data-wa="${p.id}" title="Tell the Managing Director on WhatsApp - the link opens this certificate">WhatsApp</button>` : ""}${i > 0 && pcCan(TURN_OF[STEPS[i - 1]]) ? ` <button class="btn btn-plain btn-sm" data-undo="${p.id}" data-st="${p.status}" title="Back one step">&#8630;</button>` : ""} <button class="btn btn-plain btn-sm" data-open="${p.id}" data-sub="${p.sub.id}">Open</button></td></tr>`; }).join("")}
    </tbody></table></div>` : `<div class="empty">${f === "__mine" ? "Nothing waiting for you." : f === "__stuck" ? "Nothing stuck." : "No invoices" + (f ? " at this step" : "") + "."}</div>`);
  bindTools(el, () => SECTIONS["subs.inv"](el));
  $("#add-inv", el).onclick = () => invoiceForm();
  $("#rules", el).onclick = rulesForm;
  bindPcButtons(el, () => reload());
  $$("[data-undo]", el).forEach(b => b.onclick = async () => { try { await POST(`/store/est/subpcs/${b.dataset.undo}/step`, { step: b.dataset.st, undo: true }); await reload(); toast("Moved back one step"); } catch (e) { fail(e); } });
  $$("[data-open]", el).forEach(b => b.onclick = () => openCert(+b.dataset.sub, +b.dataset.open));
  $$("[data-wa]", el).forEach(b => b.onclick = () => { const p = all.find(x => x.id === +b.dataset.wa); waShare([p]); });
};
const TURN_OF = { "Received": "qs", "At site": "site", "Certified": "qs", "Prepared": "cm", "CM approved": "acc", "Verified": "md", "MD approved": "acc" };
function bindPcButtons(el, after) {
  $$("[data-pc]", el).forEach(b => b.onclick = () => {
    const pcid = +b.dataset.pc, sid = +b.dataset.sub;
    if (b.dataset.back) return sendBack(pcid, after);
    if (b.dataset.to === "open") return openCert(sid, pcid);
    step(pcid, b.dataset.to, sid, after);
  });
}
function pcOf(pcid) { return allPcs().find(x => x.id === pcid); }
async function step(pcid, to, sid, after) {
  after = after || reload;
  const p = pcOf(pcid);
  if (to === "Paid") { payForm(sid, pcid, after); return; }
  if (to === "Certified" && p && p.status === "At site") {
    modal(`Certified at site - PC ${pad(p.seq, 2)} ${p.sub.name}`, [{ k: "by", label: "Certified by (site engineer)", value: p.verified_by || "", focus: true, tip: "The name goes on the certificate. Leave blank if you certify it yourself." },
      { k: "date", label: "On", type: "date", value: today() }], async v => { await POST(`/store/est/subpcs/${pcid}/step`, { step: "Certified", by: v.by, date: v.date }); await after(); toast("Certified at site"); });
    return;
  }
  if (to === "sendmd") {
    try { await POST(`/store/est/subpcs/${pcid}/step`, { step: "Sent to MD" }); await after();
      toast("Sent to the Managing Director", { undo: async () => { await POST(`/store/est/subpcs/${pcid}/step`, { step: "Sent to MD", undo: true }); after(); } });
      if (p) waAsk([p]); } catch (e) { fail(e); }
    return;
  }
  try {
    await POST(`/store/est/subpcs/${pcid}/step`, { step: to }); await after();
    toast(`${STEP_DONE[to] || to} - ${dt(today())}`, { undo: async () => { await POST(`/store/est/subpcs/${pcid}/step`, { step: to, undo: true }); after(); } });
    if (to === "Verified") toast("Verified - press Send to MD when it is ready to go", { ms: 4500 });
  } catch (e) { fail(e); }
}
function sendBack(pcid, after) {
  const p = pcOf(pcid) || { seq: 0, sub: { name: "" }, status: "" };
  const i = STEPS.indexOf(p.status);
  const opts = [["Certified", "QS - to prepare again"], ["Prepared", "Contracts manager"], ["CM approved", "Accounts - to verify again"]].filter(([k]) => STEPS.indexOf(k) < i);
  modal(`Send back - PC ${pad(p.seq, 2)} ${p.sub.name}`, [{ k: "note", label: "Why (one line)", focus: true, full: true },
    { k: "to", label: "Back to", type: "select", options: opts, value: "Certified" }],
    async v => { if (!v.note) throw new Error("Say why it goes back."); await POST(`/store/est/subpcs/${pcid}/step`, { back: true, to: v.to, note: v.note }); await (after || reload)(); toast("Sent back with your note"); });
}
function approveLink(ps) { return `${location.origin}/portal/approve.html?pc=${ps.map(p => p.id || p.pc_id).join(",")}`; }
function waText(ps) {
  const one = ps.length === 1, p = ps[0], name = x => x.sub && x.sub.name ? x.sub.name : x.sub;
  const tot = ps.reduce((a, x) => a + (x.payable || 0), 0);
  return one ? `Payment certificate for approval: ${name(p)} PC ${pad(p.seq, 2)} - AED ${money(p.payable, false)}\n${approveLink(ps)}`
             : `${ps.length} payment certificates for approval - AED ${money(tot, false)} in total\n${approveLink(ps)}`;
}
function waShare(ps) { window.open("https://wa.me/?text=" + encodeURIComponent(waText(ps)), "_blank"); }
function waAsk(ps) {
  modal("Sent to the Managing Director", [], async () => { waShare(ps); }, { top: `<div style="font-size:14px;line-height:1.5">The managers have a notification.<br>Also tell them on WhatsApp? It opens with the message and the link already typed - the link opens the certificate (the PDF) with Approve / Reject.</div>
    <div class="small muted" style="margin-top:8px;white-space:pre-wrap;background:#F7F5F1;border-radius:8px;padding:8px">${esc(waText(ps))}</div>`, save: "WhatsApp" });
}
function payForm(sid, pcid, after) {
  const s = ST.b.subs.find(x => x.id === sid), p = s.pcs.find(x => x.id === pcid);
  modal(`Paid - PC ${pad(p.seq, 2)} ${s.name}`, [
    { k: "amount", label: "Amount paid (AED)", type: "money", value: p.payable, tip: "Filled in with the amount payable (incl. VAT)." },
    { k: "date", label: "Paid on", type: "date", value: today() },
    { k: "ref", label: "Cheque / transfer ref.", focus: true },
  ], async v => { await POST(`/store/est/subpcs/${pcid}/step`, Object.assign({ step: "Paid" }, v)); await (after || reload)(); toast("Marked paid - Estimation can see it"); });
}
function rulesForm() {
  const r = ST.b.rules;
  modal("Days allowed", [
    { k: "site_days", label: "Site to check an invoice (days)", type: "num", value: r.site_days },
    { k: "pc_days", label: "PC to be issued after the invoice arrives (days)", type: "num", value: r.pc_days },
    { k: "rfi_days", label: "Reply to an RFI (days)", type: "num", value: r.rfi_days },
    { k: "submittal_days", label: "Reply to a submittal (days)", type: "num", value: r.submittal_days },
    { k: "stuck_days", label: "A certificate is 'stuck' after (days at one step)", type: "num", value: r.stuck_days || 2 },
    { k: "pc_cm", label: "Contracts manager(s) who approve certificates", value: r.pc_cm || "", tip: "Names, comma between. They get the Approve button and the notification. Accounts verifies and pays; the Managing Director is the admin login." },
  ], async v => { await PUT("/store/est/rules", v); ST.meta = await GET("/store/est/meta"); await reload(); toast("Saved"); });
}

// ---------------- Subcontractors > payment certificates ----------------
SECTIONS["subs.pcs"] = el => {
  const f = filt() || "", all = allPcs().filter(p => STEPS.indexOf(p.status) >= STEPS.indexOf("Prepared"));
  const list = all.filter(p => (!f || p.status === f) && match({ a: p.sub.name, b: p.inv_ref, c: p.status }));
  const n = s => all.filter(p => p.status === s).length;
  const tot = k => r2(list.reduce((a, p) => a + (p[k] || 0), 0));
  el.innerHTML = tools("invoices", { chips: [["", all.length], ...["Prepared", "CM approved", "Verified", "MD approved", "Paid"].map(s => [s, n(s)])],
      add: `<span class="muted small">Prepared &rarr; Contracts manager &rarr; Accounts verify &rarr; Managing Director &rarr; Accounts pay ${tip("Each step is a click by the person whose turn it is - their name and the time go on the certificate. Accounts (with the Bank right) verifies and pays from Accounts > Subcontractor payments.")}</span>` }) +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>Subcontractor</th><th>PC</th><th class="r">This PC</th><th class="r">VAT</th><th class="r">Payable</th><th>Last stamp</th><th>Waiting on</th><th>Paid</th><th class="r">Paid amount</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map(p => { const fl = p.flow || {}; return `<tr class="${fl.stuck ? "late-row" : ""}"><td><b>${esc(p.sub.name)}</b><div class="small muted">${esc(p.sub.scope)}</div></td><td class="nowrap">PC ${pad(p.seq, 2)}${p.pc_type !== "Interim" ? ` <span class="small muted">${esc(p.pc_type)}</span>` : ""}</td><td class="r">${money(p.this, false)}</td><td class="r">${money(p.vat)}</td><td class="r"><b>${money(p.payable, false)}</b></td>
      <td class="small">${stampTxt(fl.last)}</td><td>${fl.turn ? (pcMine(p) ? '<b style="color:#C0392B">You</b>' : esc(fl.waiting)) + ` <span class="small ${fl.stuck ? "late" : "muted"}">${ageTxt(fl.hours)}</span>` : ""}</td>
      <td>${dt(p.paid_on)}<div class="small muted">${esc(p.paid_ref)}</div></td><td class="r">${money(p.paid_amount)}</td><td>${st(STEP_LABEL[p.status] || p.status)}</td>
      <td class="nowrap"><button class="btn btn-plain btn-sm" data-print="${p.id}">Print</button> ${nextBtns(p)}</td></tr>`; }).join("")}
    <tr class="tot"><td>Total</td><td></td><td class="r">${money(tot("this"))}</td><td class="r">${money(tot("vat"))}</td><td class="r">${money(tot("payable"))}</td><td></td><td></td><td></td><td class="r">${money(tot("paid_amount"))}</td><td></td><td></td></tr>
    </tbody></table></div>` : '<div class="empty">No certificates here yet. They appear once the QS presses Prepared.</div>');
  bindTools(el, () => SECTIONS["subs.pcs"](el));
  $$("[data-print]", el).forEach(b => b.onclick = () => exportGo("preview", "pc", { id: +b.dataset.print }));
  bindPcButtons(el, () => reload());
};

// ---------------- Subcontractors > finalization log ----------------
const FCOLS = [["sc", "Scope", ["C", "E", "PS", "N/A", ""]], ["rt", "Rate finalized", ["✔", "X", "N/A", ""]], ["sd", "Shop drawing", ["✔", "X", "N/A", ""]],
               ["ma", "Material approval", ["✔", "X", "N/A", ""]], ["aa", "Authority approval", ["✔", "X", "N/A", ""]], ["st", "Final status", ["✔", "X", "N/A", ""]]];
SECTIONS["subs.final"] = el => {
  const b = ST.b, f = filt();
  const rows = b.finals.filter(x => (!f || (f === "Pending" ? x.st !== "✔" && x.sc !== "N/A" : x.st === "✔")) && match(x));
  const cls = v => v === "✔" ? "ok" : v === "X" ? "no" : v === "N/A" ? "na" : ["C", "E", "PS"].includes(v) ? "sc" : "";
  let html = tools("finals", { add: `<button class="btn btn-ghost" id="add-final">+ Item</button>`, chips: [["", b.finals.length], ["Pending", b.finals.filter(x => x.st !== "✔" && x.sc !== "N/A").length], ["✔", b.finals.filter(x => x.st === "✔").length]],
      right: `<span class="small muted">Click a box to change it ${tip("Scope: C main contractor · E employer · PS provisional sum. Other boxes: ✔ done · X not yet · N/A. Each click moves to the next.")}</span>` });
  html += `<div class="tw"><table class="t fg"><thead><tr><th>Item</th><th>Subcontractor</th>${FCOLS.map(c => `<th class="c">${c[1]}</th>`).join("")}</tr></thead><tbody>`;
  let sec = "";
  for (const x of rows) {
    if (x.section !== sec) { sec = x.section; html += `<tr class="sec"><td colspan="${FCOLS.length + 2}">${esc(sec)}</td></tr>`; }
    html += `<tr><td>${esc(x.item)}</td><td><select class="fsub" data-fsub="${x.id}"><option value="">-</option>${b.subs.map(s => `<option value="${s.id}" ${s.id === x.sub_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}<option value="new">+ New subcontract...</option></select></td>${FCOLS.map(c => `<td class="cell ${cls(x[c[0]])}" data-fc="${x.id}:${c[0]}">${esc(x[c[0]] || "")}</td>`).join("")}</tr>`;
  }
  el.innerHTML = html + "</tbody></table></div>";
  bindTools(el, () => SECTIONS["subs.final"](el));
  $$("[data-fc]", el).forEach(td => td.onclick = async () => {
    const [id, k] = td.dataset.fc.split(":"); const col = FCOLS.find(c => c[0] === k)[2]; const row = b.finals.find(x => x.id === +id);
    const nv = col[(col.indexOf(row[k] || "") + 1) % col.length];
    row[k] = nv; td.textContent = nv; td.className = "cell " + cls(nv);
    // the counts on the chips and the tab follow at once
    const pend = b.finals.filter(x => x.st !== "✔" && x.sc !== "N/A").length, done = b.finals.filter(x => x.st === "✔").length, tot = b.finals.filter(x => x.sc !== "N/A").length;
    const setN = (sel, v) => { const n = document.querySelector(sel); if (n) n.textContent = v; };
    setN('.chip[data-f="Pending"] .n', pend); setN('.chip[data-f="✔"] .n', done); setN('#psub [data-s="final"] .n', `${done}/${tot}`);
    b.summary.finals_done = done; b.summary.finals_total = tot;
    try { await PATCH(`/store/est/finals/${id}`, { [k]: nv }); } catch (e) { fail(e); }
  });
  $$("[data-fsub]", el).forEach(s => s.onchange = async () => {
    const row = b.finals.find(x => x.id === +s.dataset.fsub);
    if (s.value === "new") { s.value = row.sub_id || ""; subForm(null, { scope: row.item, final_id: row.id }); return; }
    try { await PATCH(`/store/est/finals/${s.dataset.fsub}`, { sub_id: s.value || null }); b.finals.find(x => x.id === +s.dataset.fsub).sub_id = +s.value || null; toast("Saved"); } catch (e) { fail(e); } });
  $("#add-final", el).onclick = () => modal("Finalization item", [
    { k: "section", label: "Section", type: "select", options: ["CIVIL", "MEP", "EXTERNAL", "OTHER"] }, { k: "item", label: "Item", focus: true }],
    async v => { await POST("/store/est/finals", Object.assign(v, { project_id: ST.pid })); reload(); });
};

// ---------------- Overview > BOQ & budget ----------------
// Hundreds of lines from the internal BOQ: one row per bill (trade), opened with a click.
// Lines out of the awarded scope (Excluded, Phase 02 ...) stay for reference but are not counted.
SECTIONS["client.boq"] = el => {
  const b = ST.b, q = (ST.q[key()] || "").trim(), rows = b.boq.filter(match);
  const all = b.boq, inScope = all.filter(x => !x.scope);
  const tot = inScope.reduce((a, x) => a + x.counted, 0), cost = inScope.reduce((a, x) => a + x.cost, 0);
  const out = all.filter(x => x.scope).reduce((a, x) => a + x.amount, 0);
  const open = ST.boqOpen = ST.boqOpen || {};
  let html = tools("boq", { add: `<button class="btn btn-primary" id="boq-up" title="The estimation team's internal BOQ workbook (1.PRELIM, 2.SUBSTR ... 20. SPECIALIZED ITEMS). Only the lines are kept - the file is not stored.">Upload BOQ</button><input type="file" id="boq-up-f" accept=".xlsx,.xlsm,.pdf,.docx,.jpg,.jpeg,.png" hidden><button class="btn btn-plain" id="boq-paste">Paste from Excel</button><button class="btn btn-ghost" id="boq-add">+ Line</button>` });
  if (!all.length) html += `<div class="empty">No BOQ yet. Press <b>Upload internal BOQ</b> and pick the internal BOQ Excel - every line comes in, grouped by trade, with what is excluded or phase 2 kept aside. ${tip("The workbook is read once and only its lines are kept; the Excel file itself is not stored. Upload a newer revision any time - the cost rates and done % you typed stay on the lines that come back.")}</div>`;
  else {
    html += `<div class="strip">${[["BOQ value", tot, "In the awarded scope"], ["Budget cost", cost, "Qty x your cost rate"], ["Budget margin", tot - cost, ""]].map(([l, v, t]) => `<div class="fig"><div class="l">${l}${t ? " " + tip(t) : ""}</div><div class="v">${aed(v)}</div></div>`).join("")}<div class="fig"><div class="l">Margin %</div><div class="v">${tot && cost ? (100 * (tot - cost) / tot).toFixed(1) + "%" : '<span class="muted">-</span>'}</div></div>${out ? `<div class="fig"><div class="l">Not in scope ${tip("Bills and sections the internal BOQ leaves out (Excluded, Phase 02, N/A ...). Kept for reference, not counted. Click the tag on a bill to bring it into scope when it is awarded.")}</div><div class="v muted">${aed(out)}</div></div>` : ""}</div>`;
    const bills = [...new Set(rows.map(x => x.bill || ""))];
    const many = bills.length > 1;
    html += `<div class="tw"><table class="t boq"><thead><tr><th style="width:62px">Item</th><th>Description</th><th>Unit</th><th class="r">Qty</th><th class="r">Rate</th><th class="r">Amount</th><th class="r">Cost rate ${tip("Your budget cost per unit. Click any figure to change it.")}</th><th class="r">Budget</th><th class="r">Done %</th></tr></thead><tbody>`;
    for (const bl of bills) {
      const L = rows.filter(x => (x.bill || "") === bl), cnt = L.reduce((a, x) => a + x.counted, 0), bc = L.reduce((a, x) => a + x.cost, 0);
      const scopes = [...new Set(L.map(x => x.scope))], whole = scopes.length === 1 && scopes[0];
      const isOpen = !many || q || open[bl];
      if (many) html += `<tr class="bill ${isOpen ? "open" : ""} ${whole ? "out" : ""}" data-bill="${esc(bl)}"><td colspan="5"><span class="caret">${isOpen ? "▾" : "▸"}</span> ${esc(bl || "Other lines")} <span class="small muted">${L.length} line${L.length === 1 ? "" : "s"}</span>${whole ? ` <span class="st b scopetag" data-scope="${esc(bl)}" title="Not counted - click to change">${esc(whole)}</span>` : (scopes.some(x => x) ? ` <span class="small muted">· part left out</span>` : "")}</td><td class="r">${whole ? `<span class="muted">${money(L.reduce((a, x) => a + x.amount, 0))}</span>` : money(cnt)}</td><td></td><td class="r">${money(bc)}</td><td></td></tr>`;
      if (!isOpen) continue;
      let sec = null;
      for (const x of L) {
        if (x.section !== sec) {
          sec = x.section;
          if (sec || !many) { const S = L.filter(y => y.section === sec), so = S.every(y => y.scope) && !whole ? S[0].scope : "";
            html += `<tr class="sec ${so ? "out" : ""}"><td colspan="5">${esc(sec || "General")}${so ? ` <span class="st b scopetag" data-scope="${esc(bl)}" data-ssec="${esc(sec)}" title="Not counted - click to change">${esc(so)}</span>` : ""}</td><td class="r">${so ? `<span class="muted">${money(S.reduce((a, y) => a + y.amount, 0))}</span>` : money(S.reduce((a, y) => a + y.counted, 0))}</td><td></td><td class="r">${money(S.reduce((a, y) => a + y.cost, 0))}</td><td></td></tr>`; }
        }
        const amt = x.scope ? `<span class="muted" title="${esc(x.scope)} - not counted">${money(x.amount)}</span>` : money(x.amount);
        html += `<tr class="${x.scope ? "out" : ""}"><td class="small">${esc(x.code)}</td><td class="rowc" data-boq="${x.id}">${esc(x.description)}${x.remark ? ` <span class="small muted">· ${esc(x.remark)}</span>` : ""}</td><td>${esc(x.unit)}</td>${["qty", "rate"].map(k => `<td class="r rowc" data-ed="${x.id}:${k}">${money(x[k])}</td>`).join("")}<td class="r">${amt}</td><td class="r rowc" data-ed="${x.id}:cost_rate">${money(x.cost_rate)}</td><td class="r">${money(x.cost)}</td><td class="r rowc" data-ed="${x.id}:done_pct">${x.done_pct ? x.done_pct + "%" : '<span class="muted">-</span>'}</td></tr>`;
      }
    }
    const shownT = rows.reduce((a, x) => a + x.counted, 0), shownC = rows.reduce((a, x) => a + x.cost, 0);
    html += `<tr class="tot"><td></td><td colspan="4">Total${q ? " (lines found)" : ""}${many && !q ? ` <a href="#" class="small" id="boq-all">${bills.every(x => open[x]) ? "close all" : "open all"}</a>` : ""}</td><td class="r">${money(shownT)}</td><td></td><td class="r">${money(shownC)}</td><td></td></tr></tbody></table></div>`;
  }
  el.innerHTML = html;
  bindTools(el, () => SECTIONS["client.boq"](el));
  const fi = $("#boq-up-f", el);
  $("#boq-up", el).onclick = () => fi.click();
  fi.onchange = () => { if (fi.files[0]) boqImport(fi.files[0]); fi.value = ""; };
  $("#boq-paste", el).onclick = () => modal("Paste the BOQ from Excel", [
    { k: "section", label: "Section for lines before the first heading", ph: "e.g. SUBSTRUCTURE" },
    { k: "text", label: "Lines copied from Excel", type: "area", ph: "Select the rows in Excel (item, description, unit, qty, rate), copy, and paste here.", focus: true }],
    async v => { const r = await POST(`/store/est/projects/${ST.pid}/boq-paste`, v); await reload(); toast(r.added + " lines added"); },
    { after: () => { $("#f-text").style.height = "220px"; } });
  $("#boq-add", el).onclick = () => boqForm();
  $$("tr.bill", el).forEach(tr => tr.onclick = e => { if (e.target.closest("[data-scope]")) return; open[tr.dataset.bill] = !open[tr.dataset.bill]; SECTIONS["client.boq"](el); });
  const ab = $("#boq-all", el); if (ab) ab.onclick = e => { e.preventDefault(); const bl = [...new Set(b.boq.map(x => x.bill || ""))], all2 = bl.every(x => open[x]); bl.forEach(x => open[x] = !all2); SECTIONS["client.boq"](el); };
  $$("[data-scope]", el).forEach(t => t.onclick = e => { e.stopPropagation(); boqScope(t.dataset.scope, t.dataset.ssec, t.textContent); });
  $$("[data-boq]", el).forEach(td => td.onclick = () => boqForm(b.boq.find(x => x.id === +td.dataset.boq)));
  $$("[data-ed]", el).forEach(td => td.onclick = () => inlineEdit(td, "boq"));
};
// A bill or section left out (Excluded, Phase 02 ...) brought into scope once awarded - or left out again.
function boqScope(bill, section, now) {
  const what = section ? `${section} (${bill})` : bill;
  modal(what, [{ k: "scope", label: "Left out because", type: "combo", options: ["Excluded", "Phase 02", "N/A", "By Client"], value: now || "", tip: "Clear it to count these lines in the BOQ value." }],
    async v => { await POST(`/store/est/projects/${ST.pid}/boq-scope`, { bill, section: section ?? null, scope: v.scope }); await reload(); toast(v.scope ? "Left out: " + v.scope : "Now counted in the BOQ value"); },
    { save: "Save", extra: now ? `<button class="btn btn-ghost left" id="m-count">Bring into scope</button>` : "",
      after: () => { const c = $("#m-count"); if (c) c.onclick = async () => { try { await POST(`/store/est/projects/${ST.pid}/boq-scope`, { bill, section: section ?? null, scope: "" }); closeModal(true); await reload(); toast("Now counted in the BOQ value"); } catch (e) { fail(e); } }; } });
}
// The internal BOQ workbook: read, shown bill by bill against the workbook's own summary, then saved.
// A document to read in the browser (not an Excel workbook the server reads as it always has).
function isDoc(file) { return /\.(pdf|docx|jpe?g|png|webp)$/i.test(file.name || "") || /^image\//.test(file.type || ""); }
async function boqImport(file, pid) {
  pid = pid || ST.pid;
  let send = async (save, mode) => { const fd = new FormData(); fd.append("file", file); fd.append("save", save ? "1" : "0"); fd.append("mode", mode || "replace"); return api(`/store/est/projects/${pid}/boq-import`, { method: "POST", body: fd }); };
  if (isDoc(file)) {                     // a PDF, Word file or scan: read here, only its words are sent
    let d; try { d = await readAgreement(file, m => toast(m)); } catch (e) { return fail(e); }
    send = (save, mode) => POST(`/store/est/projects/${pid}/boq-import-text`, { lines: d.lines, save: save ? 1 : 0, mode: mode || "replace", name: file.name });
  }
  let r; try { toast("Reading " + file.name + " ..."); r = await send(false); } catch (e) { return fail(e); }
  const ok = r.summary_total === null || r.summary_total === undefined ? "" : Math.abs(r.total - r.summary_total) < 0.01 ? `<span class="st g">matches the ${esc(r.summary_sheet)} sheet</span>` : `<span class="st r">${esc(r.summary_sheet)} sheet says ${money(r.summary_total, false)}</span>`;
  modal(`Internal BOQ - ${file.name}`, [], async () => {
    const mode = ($("input[name=boqmode]:checked") || {}).value || "replace";
    const x = await send(true, mode); ST.boqOpen = {};
    if (pid === ST.pid) await reload();
    toast(`${x.saved} BOQ lines ${mode === "replace" ? "in" : "added"}${x.kept_budget ? ` - cost rate / done % kept on ${x.kept_budget}` : ""}`);
  }, {
    wide: true, save: `Bring in ${r.lines} lines`,
    top: `<div class="strip"><div class="fig"><div class="l">Lines</div><div class="v">${r.lines}</div></div><div class="fig green"><div class="l">BOQ value (in scope)</div><div class="v">${money(r.total, false)}</div><div class="s">${ok}</div></div>${r.left_out ? `<div class="fig"><div class="l">Not in scope</div><div class="v muted">${money(r.left_out, false)}</div><div class="s">kept for reference</div></div>` : ""}</div>
      ${r.existing ? `<div class="warn" style="margin:8px 0">This project already has ${r.existing} BOQ line(s).
        <label class="chk" style="display:flex;gap:8px;margin-top:6px"><input type="radio" name="boqmode" value="replace" checked><span><b>Replace them</b> with this workbook - cost rates and done % already typed stay on the lines that come back</span></label>
        <label class="chk" style="display:flex;gap:8px;margin-top:4px"><input type="radio" name="boqmode" value="add"><span><b>Add</b> these lines after them</span></label></div>` : ""}
      ${r.notes.length ? `<div class="small" style="margin:6px 0">${r.notes.map(n => "• " + esc(n)).join("<br>")}</div>` : ""}
      <div class="tw" style="max-height:360px;overflow:auto"><table class="t"><thead><tr><th>Bill</th><th class="r">Lines</th><th class="r">Counted</th><th>Left out</th></tr></thead><tbody>${r.bills.map(x => `<tr><td>${esc(x.bill)}</td><td class="r">${x.lines}</td><td class="r">${money(x.counted)}</td><td>${x.scope ? `<span class="st b">${esc(x.scope)}</span> <span class="small muted">${money(x.left_out, false)}</span>` : x.sections_out.length ? `<span class="small">${x.sections_out.map(esc).join("<br>")}</span> <span class="small muted">${money(x.left_out, false)}</span>` : ""}</td></tr>`).join("")}
      <tr class="tot"><td>Total</td><td class="r">${r.lines}</td><td class="r">${money(r.total)}</td><td>${r.left_out ? `<span class="small muted">${money(r.left_out, false)} not counted</span>` : ""}</td></tr></tbody></table></div>
      <div class="small muted" style="margin-top:6px">Only the lines are kept - the file itself is not stored.</div>` });
}
function boqForm(x) {
  x = x || {};
  modal(x.id ? "BOQ line" : "New BOQ line", [
    { k: "section", label: "Section", type: "combo", options: [...new Set(ST.b.boq.map(y => y.section).filter(Boolean))], value: x.section || "" },
    { k: "code", label: "Item no.", value: x.code || "" }, { k: "description", label: "Description", value: x.description || "", full: true, focus: true },
    { k: "unit", label: "Unit", type: "combo", options: ["m3", "m2", "m", "nos", "kg", "ton", "LS", "set", "lot"], value: x.unit || "" },
    { k: "qty", label: "Qty", type: "num", value: x.qty ?? "" }, { k: "rate", label: "Rate (AED)", type: "money", value: x.rate ?? "" },
    { k: "amount", label: "Amount (AED)", type: "money", value: x.given ? x.amount : "", ph: "Qty x rate", tip: "Leave empty to work it out from qty x rate. A lump sum or a figure from the internal BOQ is kept as typed." },
    { k: "cost_rate", label: "Budget cost rate (AED)", type: "money", value: x.cost_rate ?? "" }, { k: "done_pct", label: "Done %", type: "pct", value: x.done_pct ?? "" },
    { k: "bill", label: "Bill (trade)", type: "combo", options: [...new Set(ST.b.boq.map(y => y.bill).filter(Boolean))], value: x.bill || "" },
    { k: "remark", label: "Remark", value: x.remark || "" },
    { k: "scope", label: "Left out because", type: "combo", options: ["", "Excluded", "Phase 02", "N/A", "By Client"], value: x.scope || "", tip: "Empty = in the awarded scope and counted. Anything here keeps the line for reference without counting it." },
  ], async v => {
    const n = k => Number(String(v[k] ?? "").replace(/,/g, "")) || 0;
    if (x.given && (n("qty") !== (x.qty || 0) || n("rate") !== (x.rate || 0)) && n("amount") === r2(x.amount)) v.amount = "";   // qty / rate changed: amount worked out again
    if (x.id) await PATCH(`/store/est/boq/${x.id}`, v); else await POST("/store/est/boq", Object.assign(v, { project_id: ST.pid })); reload(); },
  { del: x.id ? async () => { await DEL(`/store/est/boq/${x.id}`); reload(); } : null });
}
// Click a figure, type, Enter. No form.
function inlineEdit(td, kind) {
  if (td.querySelector("input")) return;
  const [id, k] = td.dataset.ed.split(":");
  const row = (kind === "boq" ? ST.b.boq : []).find(x => x.id === +id);
  const old = row[k];
  td.innerHTML = `<input class="money" style="width:100px;height:28px;border:1px solid var(--red);border-radius:5px;text-align:right;padding:0 6px" value="${old || ""}">`;
  const inp = td.querySelector("input"); inp.focus(); inp.select();
  let done = false;
  const save = async ok => {
    if (done) return; done = true;
    const v = inp.value.replace(/,/g, "").trim();
    if (!ok || v === String(old || "")) { renderProject(); return; }
    try { await PATCH(`/store/est/${kind}/${id}`, { [k]: v }); await reload(); } catch (e) { fail(e); renderProject(); }
  };
  inp.onkeydown = e => { if (e.key === "Enter") save(true); if (e.key === "Escape") save(false); };
  inp.onblur = () => save(true);
}

// ---------------- Overview > payment certificates ----------------
SECTIONS["client.cpc"] = el => {
  const b = ST.b, p = b.project, f = filt();
  const list = b.clientpcs.filter(c => (!f || c.status === f) && match(c));
  const n = s => b.clientpcs.filter(c => c.status === s).length;
  el.innerHTML = tools("clientpcs", { add: `<button class="btn btn-primary" id="add-cpc">+ New certificate</button>${p.adv_pct ? `<button class="btn btn-ghost" id="add-cadv">+ Advance</button>` : ""}`,
      chips: [["", b.clientpcs.length], ...["Draft", "Submitted", "Certified", "Invoiced", "Paid"].map(s => [s, n(s)])],
      right: `<span class="small muted">Retention ${p.ret_pct}% · Advance ${p.adv_pct}% · VAT ${p.vat_pct}%</span>` }) +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>PC</th><th>Period to</th><th>Submitted</th><th class="r">Claimed to date</th><th class="r">Certified to date</th><th class="r">Adv. recovery</th><th class="r">Retention</th><th class="r">Net to date</th><th class="r">This PC</th><th class="r">With VAT</th><th>Invoice</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map(c => `<tr class="rowc" data-cpc="${c.id}"><td><b>${pad(c.seq, 2)}</b>${c.pc_type !== "Interim" ? ` <span class="small muted">${esc(c.pc_type)}</span>` : ""}</td><td>${dt(c.period_to)}</td><td>${dt(c.submitted)}</td><td class="r">${money(c.claimed_cum)}</td><td class="r">${money(c.certified_cum)}</td>
      <td class="r neg">${c.adv_rec_cum ? "-" + money(c.adv_rec_cum) : money(0)}</td><td class="r neg">${c.ret_cum ? "-" + money(c.ret_cum) : money(0)}</td><td class="r">${money(c.net_cum)}</td><td class="r"><b>${money(c.this, false)}</b></td><td class="r">${money(c.payable, false)}</td><td>${esc(c.invoice_no)}</td><td>${st(c.status)}</td>
      <td class="nowrap">${c.status === "Draft" ? `<button class="btn btn-ghost btn-sm" data-cst="${c.id}:Submitted">Submitted</button>` : c.status === "Submitted" ? `<button class="btn btn-ghost btn-sm" data-cert="${c.id}">Certified</button>` : c.status === "Certified" ? `<button class="btn btn-ghost btn-sm" data-cst="${c.id}:Invoiced">Invoiced</button>` : c.status === "Invoiced" ? `<button class="btn btn-ok btn-sm" data-cst="${c.id}:Paid">Paid</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>` : `<div class="empty">No certificates to the consultant yet.</div>`);
  bindTools(el, () => SECTIONS["client.cpc"](el));
  $("#add-cpc", el).onclick = () => cpcForm();
  const ca = $("#add-cadv", el); if (ca) ca.onclick = async () => { try { await POST("/store/est/clientpcs", { project_id: ST.pid, pc_type: "Advance" }); await reload(); toast("Advance certificate made"); } catch (e) { fail(e); } };
  $$("[data-cpc]", el).forEach(r => r.onclick = e => { if (e.target.closest("button")) return; cpcForm(b.clientpcs.find(c => c.id === +r.dataset.cpc)); });
  $$("[data-cst]", el).forEach(x => x.onclick = async () => { const [id, s] = x.dataset.cst.split(":"); const d = { status: s }; if (s === "Submitted") d.submitted = today(); try { await PATCH(`/store/est/clientpcs/${id}`, d); await reload(); toast(s); } catch (e) { fail(e); } });
  $$("[data-cert]", el).forEach(x => x.onclick = () => { const c = b.clientpcs.find(y => y.id === +x.dataset.cert);
    modal(`PC ${pad(c.seq, 2)} - certified by the consultant`, [
      { k: "certified_cum", label: "Certified work done to date (AED)", type: "money", value: c.claimed_cum, quick: [["Same as claimed", el2 => el2.value = c.claimed_cum]], focus: true },
      { k: "certified_on", label: "Certified on", type: "date", value: today() }],
      async v => { await PATCH(`/store/est/clientpcs/${c.id}`, Object.assign(v, { status: "Certified" })); await reload(); toast("Certified"); }); });
};
function cpcForm(c) {
  const b = ST.b, p = b.project, edit = !!c; c = c || {};
  const last = b.clientpcs[b.clientpcs.length - 1];
  modal(edit ? `Payment certificate ${pad(c.seq, 2)}` : "New payment certificate", [
    ...[ctrField(c.contract_id)].filter(Boolean),
    { k: "claimed_cum", label: "Work done to date - claimed (AED)", type: "money", value: edit ? c.claimed_cum : (last ? last.claimed_cum : ""), focus: true,
      quick: [25, 50, 75, 100].map(n => [n + "%", el => el.value = r2(b.summary.revised * n / 100)]), hint: `Revised contract ${money(b.summary.revised, false)}${last && !edit ? " · last claim " + money(last.claimed_cum, false) : ""}` },
    { k: "certified_cum", label: "Certified to date (AED)", type: "money", value: c.certified_cum || "" },
    { k: "period_to", label: "Period up to", type: "date", value: c.period_to || today() }, { k: "submitted", label: "Submitted on", type: "date", value: c.submitted || "" },
    { k: "mos_cum", label: "Material on site to date", type: "money", value: c.mos_cum || "" }, { k: "other_cum", label: "Other deductions to date", type: "money", value: c.other_cum || "" },
    { k: "ret_rel_cum", label: "Retention released to date", type: "money", value: c.ret_rel_cum || "" },
    { k: "authority", label: "Authority payments (this bill)", type: "money", value: c.authority || "", tip: "Authority fees paid for the client and claimed on this bill (DEWA, Municipality, Civil Defence ...) - this bill's amount, not to date." },
    { k: "status", label: "Status", type: "select", options: ["Draft", "Submitted", "Certified", "Invoiced", "Paid"], value: c.status || "Draft" },
    { k: "invoice_no", label: "Our invoice no.", type: "combo", options: (b.invoices || []).filter(i => i.kind === "tax" && i.status !== "cancelled").map(i => i.number), value: c.invoice_no || "", ph: "Pick from Accounts > Invoices", tip: "The tax invoice from Accounts > Invoices for this certificate - pick it from the list." },
    { k: "remarks", label: "Remarks", type: "area", value: c.remarks || "" },
  ], async v => { if (edit) await PATCH(`/store/est/clientpcs/${c.id}`, v); else await POST("/store/est/clientpcs", Object.assign(v, { project_id: ST.pid })); await reload(); toast("Saved"); },
  { wide: true, doc: { kind: "clientpc", what: "payment certificate (ours or the consultant's)", want: [["claimed_cum", "Work done to date"], ["period_to", "Period up to"]] }, del: edit ? async () => { await DEL(`/store/est/clientpcs/${c.id}`); reload(); } : null });
}

// ---------------- Dashboard > client payment certificates ----------------
// Every IPA, oldest first, in a box that scrolls (header stays); a column heading sorts it - again turns it round.
const DASH_CPC = { k: "seq", dir: 1 };
const DASH_CPC_COLS = [["seq", "IPA", ""], ["period_to", "Period to", ""], ["net_cum", "Certified to date", "r"], ["authority", "Authority payments", "r"], ["status", "Status", ""]];
function dashCpcTable() {
  const b = ST.b, { k, dir } = DASH_CPC;
  const val = c => k === "status" ? STEPS_CPC.indexOf(c.status) : k === "period_to" ? (c.period_to || "") : (Number(c[k]) || 0);
  const rows = b.clientpcs.slice().sort((x, y) => { const a = val(x), z = val(y); return (a < z ? -1 : a > z ? 1 : (x.seq - y.seq) || (x.id - y.id)) * dir; });
  const tot = r2(b.clientpcs.reduce((n, c) => n + (Number(c.authority) || 0), 0));
  return `<div class="tw dcpc"><table class="t"><thead><tr>${DASH_CPC_COLS.map(([ck, l, cl]) => `<th class="${cl} sortable" data-dsort="${ck}" title="Sort by ${l.toLowerCase()} - again to turn it round">${l}${ck === k ? (dir > 0 ? " &#9650;" : " &#9660;") : ""}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(c => `<tr><td>${pad(c.seq, 2)}</td><td>${dt(c.period_to)}</td><td class="r">${money(c.net_cum)}</td><td class="r">${c.authority ? money(c.authority) : '<span class="muted">-</span>'}</td><td>${st(c.status)}</td></tr>`).join("")}</tbody>
    <tfoot><tr class="tot"><td colspan="3">${b.clientpcs.length} IPA${b.clientpcs.length === 1 ? "" : "s"}</td><td class="r">${money(tot, false)}</td><td></td></tr></tfoot></table></div>`;
}
const STEPS_CPC = ["Draft", "Submitted", "Certified", "Invoiced", "Paid"];
document.addEventListener("click", e => {
  const th = e.target.closest("#dash-cpc [data-dsort]"); if (!th) return;
  const k = th.dataset.dsort; DASH_CPC.dir = DASH_CPC.k === k ? -DASH_CPC.dir : 1; DASH_CPC.k = k;
  const box = $("#dash-cpc"); const sc = box.querySelector(".tw") ? box.querySelector(".tw").scrollTop : 0;
  box.innerHTML = dashCpcTable(); box.querySelector(".tw").scrollTop = sc;
});

// ---------------- Overview > variations ----------------
const VO_ST = ["Identified", "Submitted", "Approved", "Rejected", "Absorbed", "Claimed", "Cancelled"];
SECTIONS["client.vo"] = el => {
  const b = ST.b, f = filt();
  const list = b.variations.filter(v => (!f || v.status === f) && match(v));
  const n = s => b.variations.filter(v => v.status === s).length;
  const sum = (k, s) => r2(b.variations.filter(v => v.status !== "Cancelled" && (!s || v.status === s) && (k !== "submitted_amount" || v.kind !== "Coordination")).reduce((a, v) => a + (v[k] || 0), 0));
  const absorbed = sum("absorbed_amount");
  const fig = (l, v, c, tip) => `<div class="fig ${c || ""}" ${tip ? `title="${esc(tip)}"` : ""}><div class="l">${l}</div><div class="v">${aed(v)}</div></div>`;
  el.innerHTML = tools("variations", { add: `<button class="btn btn-primary" id="add-vo">+ Variation</button><button class="btn btn-plain" id="imp-vo" title="Bring in the QS variation log Excel (Ref.No, Description, Submitted / Revised / Accepted / Absorbed amount, dates, Claimed in PC, Remarks). The OHP sheet comes in too.">Import log</button><input type="file" id="imp-vo-f" accept=".xlsx,.xlsm,.pdf,.docx,.jpg,.jpeg,.png" hidden>`,
      chips: [["", b.variations.length], ...VO_ST.filter(s => n(s) || ["Identified", "Submitted", "Approved", "Rejected"].includes(s)).map(s => [s, n(s)])] }) +
    `<div class="strip">${fig("Submitted", sum("submitted_amount"), "", "Every variation sent to the client (coordination lines left out)")}${fig("Approved", sum("approved_amount", "Approved"), "green", "Added to the contract value")}${fig("Waiting approval", sum("submitted_amount", "Submitted"), "amber", "Submitted, not yet accepted or rejected")}${absorbed ? fig("Absorbed", absorbed, "", "Cost Infinia carries itself - not added to the contract") : ""}</div>` +
    (list.length ? voTable(list) : '<div class="empty">No variations yet. Press + Variation, or Import log to bring in the QS variation log.</div>');
  bindTools(el, () => SECTIONS[key()](el));
  $("#add-vo", el).onclick = () => voForm();
  const fi = $("#imp-vo-f", el);
  $("#imp-vo", el).onclick = () => fi.click();
  fi.onchange = () => { if (fi.files[0]) voImport(fi.files[0]); fi.value = ""; };
  $$("[data-vo]", el).forEach(r => r.onclick = e => { if (e.target.closest("button")) return; voForm(b.variations.find(v => v.id === +r.dataset.vo)); });
  $$("[data-vrestore]", el).forEach(x => x.onclick = async () => { try { const r = await POST(`/store/est/variations/${x.dataset.vrestore}/cancel`, { restore: true }); await reload(); toast(`Restored as ${r.ref} - the numbers after it moved down`); } catch (e) { fail(e); } });
  $$("[data-vst]", el).forEach(x => x.onclick = async () => { const [id, s] = x.dataset.vst.split(":"); const d = { status: s }; if (s === "Submitted") d.submitted = today(); try { await PATCH(`/store/est/variations/${id}`, d); await reload(); toast(s); } catch (e) { fail(e); } });
  $$("[data-vapp]", el).forEach(x => x.onclick = () => { const v = b.variations.find(y => y.id === +x.dataset.vapp);
    const base = v.revised_amount || v.submitted_amount;
    modal(`${v.ref || vref(v.seq)} approved`, [{ k: "approved_amount", label: "Approved amount (AED)", type: "money", value: base, quick: [["As submitted", el2 => el2.value = v.submitted_amount], ...(v.revised_amount ? [["As revised", el2 => el2.value = v.revised_amount]] : [])], focus: true }, { k: "approved_on", label: "Approved on", type: "date", value: today() }, { k: "pc_ref", label: "Claimed in PC", value: v.pc_ref || "" }],
      async d => { await PATCH(`/store/est/variations/${v.id}`, Object.assign(d, { status: "Approved" })); await reload(); toast("Approved - added to the contract"); }); });
};
// The variation log as the QS keeps it: grouped (variations / absorbed / coordination),
// fixed columns, every figure lined up, a subtotal per group and the grand total.
function voTable(list) {
  const m = v => v ? money(v, false) : '<span class="dash">-</span>';
  const live = list.filter(v => v.status !== "Cancelled");
  const groups = [["Variations", live.filter(v => v.kind !== "Coordination" && v.status !== "Absorbed")],
                  ["Absorbed by Infinia - not added to the contract", live.filter(v => v.kind !== "Coordination" && v.status === "Absorbed")],
                  ["Coordination, builders' work & attendance (OHP)", live.filter(v => v.kind === "Coordination")],
                  ["Cancelled - not counted, no number", list.filter(v => v.status === "Cancelled")]].filter(g => g[1].length);
  const tot = rows => ({ sub: r2(rows.reduce((a, v) => a + (v.submitted_amount || 0), 0)), rev: r2(rows.reduce((a, v) => a + (v.revised_amount || 0), 0)),
                         app: r2(rows.filter(v => v.status === "Approved").reduce((a, v) => a + (v.approved_amount || 0), 0)), abs: r2(rows.reduce((a, v) => a + (v.absorbed_amount || 0), 0)) });
  const cols = 8;
  const row = v => { const rem = (v.notes || "").split("\n").filter(Boolean)[0] || "";
    if (v.status === "Cancelled") return `<tr class="rowc vcan" data-vo="${v.id}" style="opacity:.75"><td class="ref small muted">Cancelled</td>
      <td class="desc"><div class="t1" style="text-decoration:line-through">${esc(v.title)}</div><div class="t2" style="color:#9B2C20">${dt(v.cancelled_on)}: ${esc(v.cancel_note)}</div>${rem ? `<div class="t2" title="${esc(v.notes)}">${esc(rem)}</div>` : ""}</td>
      <td class="r muted" style="text-decoration:line-through">${v.submitted_amount ? money(v.submitted_amount, false) : ""}</td><td></td><td></td><td></td><td></td>
      <td>${st("Cancelled")}<div class="va"><button class="btn btn-plain btn-sm" data-vrestore="${v.id}" title="Bring it back on the log (it takes its number again)">Restore</button></div></td></tr>`;
    return `<tr class="rowc" data-vo="${v.id}"><td class="ref">${v.ref ? esc(v.ref) : '<span class="dash">-</span>'}</td>
      <td class="desc"><div class="t1">${esc(v.title)}${v.kind === "Omission" ? ' <span class="om">omission</span>' : ""}${v.contract_id && CTRS().length ? ` <span class="ctag">${esc(ctrName(v.contract_id))}</span>` : ""}</div>${rem ? `<div class="t2" title="${esc(v.notes)}">${esc(rem)}</div>` : ""}</td>
      <td class="r">${m(v.submitted_amount)}${v.submitted ? `<div class="dd">${dt(v.submitted)}</div>` : ""}</td><td class="r">${m(v.revised_amount)}</td>
      <td class="r ${v.status === "Approved" ? "ok" : ""}">${m(v.approved_amount)}${v.approved_on ? `<div class="dd">${dt(v.approved_on)}</div>` : ""}</td><td class="r">${m(v.absorbed_amount)}</td>
      <td class="c small">${v.pc_ref ? esc(v.pc_ref) : '<span class="dash">-</span>'}</td>
      <td>${st(v.status)}${v.status === "Identified" ? `<div class="va"><button class="btn btn-ghost btn-sm" data-vst="${v.id}:Submitted" title="Sent to the client today">Mark submitted</button></div>` : v.status === "Submitted" ? `<div class="va"><button class="btn btn-ok btn-sm" data-vapp="${v.id}">Approved</button><button class="btn btn-plain btn-sm" data-vst="${v.id}:Rejected">Rejected</button></div>` : ""}</td></tr>`; };
  const z = v => v ? money(v, false) : "";
  const sumRow = (label, t, cls) => `<tr class="${cls}"><td></td><td>${label}</td><td class="r">${z(t.sub)}</td><td class="r">${z(t.rev)}</td><td class="r">${z(t.app)}</td><td class="r">${z(t.abs)}</td><td></td><td></td></tr>`;
  const all = tot(live.filter(v => v.kind !== "Coordination"));
  return `<div class="tw"><table class="t vlog"><colgroup><col style="width:74px"><col><col style="width:120px"><col style="width:112px"><col style="width:120px"><col style="width:104px"><col style="width:84px"><col style="width:178px"></colgroup>
    <thead><tr><th>Ref.</th><th>Description</th><th class="r">Submitted</th><th class="r">Revised</th><th class="r">Approved</th><th class="r">Absorbed</th><th class="c">PC ref.</th><th>Status</th></tr></thead><tbody>
    ${groups.map(([title, rows]) => `<tr class="grp"><td colspan="${cols}">${esc(title)} <span>${rows.length}</span></td></tr>${rows.map(row).join("")}${groups.length > 1 && !title.startsWith("Cancelled") ? sumRow("Subtotal", tot(rows), "sub") : ""}`).join("")}
    ${sumRow("Total" + (groups.some(g => g[0].startsWith("Coord")) ? " (coordination left out)" : ""), all, "tot")}
    </tbody></table></div>`;
}
// The QS variation log Excel: shows what will come in, then puts it in.
async function voImport(file) {
  const cid = () => ($("#vo-ctr") && $("#vo-ctr").value) || "";
  let send = async (save, off) => { const fd = new FormData(); fd.append("file", file); fd.append("save", save ? "1" : "0"); fd.append("take_off_contract", off ? "1" : "0"); fd.append("contract_id", cid()); return api(`/store/est/projects/${ST.pid}/variations/import`, { method: "POST", body: fd }); };
  if (isDoc(file)) {                     // a PDF, Word file or scan: read here, only its words are sent
    let d; try { d = await readAgreement(file, m => toast(m)); } catch (e) { return fail(e); }
    send = (save, off) => POST(`/store/est/projects/${ST.pid}/variations/import-text`, { lines: d.lines, save: save ? 1 : 0, take_off_contract: off ? 1 : 0, contract_id: cid() || null });
  }
  let r; try { r = await send(false); } catch (e) { return fail(e); }
  const by = Object.entries(r.by_status).map(([k, n]) => `${st(k)} ${n}`).join(" ");
  const orig = r2(r.contract - r.approved);
  modal(`Import ${file.name}`, [], async () => { const off = $("#vo-off") && $("#vo-off").checked; const x = await send(true, off); await reload(); toast(`${x.rows} variations added${off ? " - contract set to " + money(x.contract, false) : ""}`); }, {
    wide: true, save: `Add ${r.rows} variations`,
    top: `${CTRS().length ? `<div class="frm"><div class="f full"><label for="vo-ctr">These variations are for the contract</label><select id="vo-ctr"><option value="">- Pick the contract -</option>${CTRS().map(k => `<option value="${k.id}" ${k.id === ctrPick() ? "selected" : ""}>${esc(k.name)}</option>`).join("")}</select></div></div>` : ""}${r.have ? `<div class="warn">This project already has ${r.have} variation(s). These are added after them - nothing is replaced.</div>` : ""}
      <div class="strip"><div class="fig"><div class="l">Lines</div><div class="v">${r.rows}</div></div><div class="fig green"><div class="l">Approved</div><div class="v">${money(r.approved, false)}</div></div><div class="fig"><div class="l">Submitted</div><div class="v">${money(r.submitted, false)}</div></div>${r.absorbed ? `<div class="fig"><div class="l">Absorbed</div><div class="v">${money(r.absorbed, false)}</div></div>` : ""}</div>
      <div class="small" style="margin:6px 0">${by}</div>
      ${r.approved ? `<label class="chk" style="display:flex;gap:8px;align-items:flex-start;margin:8px 0"><input type="checkbox" id="vo-off"><span>The contract value (${money(r.contract, false)}) already includes these approved variations - set it to the original ${money(orig, false)} so they aren't counted twice.</span></label>` : ""}
      <div class="tw" style="max-height:340px;overflow:auto"><table class="t"><thead><tr><th>Ref.</th><th>Description</th><th class="r">Submitted</th><th class="r">Approved</th><th class="r">Absorbed</th><th>Status</th></tr></thead><tbody>${r.lines.map(x => `<tr><td class="nowrap">${esc(x.ref)}</td><td>${esc(x.title)}</td><td class="r">${x.submitted_amount ? money(x.submitted_amount) : ""}</td><td class="r">${x.approved_amount ? money(x.approved_amount) : ""}</td><td class="r">${x.absorbed_amount ? money(x.absorbed_amount) : ""}</td><td>${st(x.status)}</td></tr>`).join("")}</tbody></table></div>` });
}
function voForm(v) {
  v = v || {};
  modal(v.id ? (v.ref || vref(v.seq)) : "New variation", [
    { k: "title", label: "Description", value: v.title || "", full: true, focus: true },
    ...[ctrField(v.contract_id)].filter(Boolean),
    { k: "ref", label: "Variation no.", value: v.ref || (v.id ? vref(v.seq) : nextVoRef()), ro: true, tip: "Every variation is numbered for you in the order it is made: V01, V02, V03 ... (cost proposals and OHP claims too). The client's or QS's own reference can go in the remarks." },
    { k: "kind", label: "Type", type: "select", options: ["Addition", "Omission", "Coordination"], value: v.kind || "Addition" },
    { k: "source", label: "Source", type: "select", options: ["Client instruction", "Consultant instruction", "Site condition", "Design change", "Authority requirement", "Coordination & attendance"], value: v.source || "Client instruction" },
    { k: "submitted", label: "Submitted on", type: "date", value: v.submitted || "" },
    { k: "submitted_amount", label: "Submitted amount (AED)", type: "money", value: v.submitted_amount ?? "" },
    { k: "revised_amount", label: "Revised amount (AED)", type: "money", value: v.revised_amount || "" },
    { k: "approved_on", label: "Approved on", type: "date", value: v.approved_on || "" },
    { k: "approved_amount", label: "Approved amount (AED)", type: "money", value: v.approved_amount || "" },
    { k: "absorbed_amount", label: "Absorbed amount (AED)", type: "money", value: v.absorbed_amount || "" },
    { k: "pc_ref", label: "Claimed in PC", type: "combo", options: [...new Set([...ST.b.clientpcs.map(c => `PC ${pad(c.seq, 2)}`), ...ST.b.variations.map(x => x.pc_ref).filter(Boolean)])], value: v.pc_ref || "", ph: "Pick the PC" },
    { k: "status", label: "Status", type: "select", options: v.status === "Cancelled" ? VO_ST : VO_ST.filter(x => x !== "Cancelled"), value: v.status || "Identified", tip: "Submitted / Approved fill today's date in their box when it is empty." },
    { k: "sub_id", label: "Passed to subcontractor", type: "select", options: [["", "-"], ...ST.b.subs.map(s => [s.id, s.name])], value: v.sub_id || "" },
    { k: "notes", label: "Remarks", type: "area", value: v.notes || "" },
  ], async d => { if (!d.submitted) d.submitted = null; if (!d.approved_on) d.approved_on = null; d.on_date = d.submitted || v.on_date || today(); if (v.id) await PATCH(`/store/est/variations/${v.id}`, d); else await POST("/store/est/variations", Object.assign(d, { project_id: ST.pid })); await reload(); toast("Saved"); },
  { wide: true, doc: { kind: "variation", what: "cost proposal or variation letter", want: [["title", "Description"], ["submitted_amount", "Submitted amount"]] }, del: v.id ? async () => { await DEL(`/store/est/variations/${v.id}`); reload(); } : null,
    extra: v.id && v.status !== "Cancelled" ? `<button class="btn btn-plain" id="m-vcancel" title="Keep it on the log with a note, struck out - not counted and not numbered; the ones after it move up">Cancel variation</button>` : "",
    after: () => { const cb = $("#m-vcancel"); if (cb) cb.onclick = () => voCancel(v);
      const st_ = $("#f-status"); if (st_) st_.addEventListener("input", () => {
      if (st_.value === "Submitted" && !$("#f-submitted").value) $("#f-submitted").value = today();
      if (st_.value === "Approved") { if (!$("#f-approved_on").value) $("#f-approved_on").value = today(); if (!$("#f-approved_amount").value) $("#f-approved_amount").value = $("#f-revised_amount").value || $("#f-submitted_amount").value; } }); } });
}
// Cancel a variation: kept on the log with its note, not counted, no number - the ones after it move up.
function voCancel(v) {
  modal(`Cancel ${v.ref || vref(v.seq)} - ${v.title}`, [
    { k: "note", label: "Why it is cancelled (kept on the log)", value: "", focus: true, full: true, quick: [["Implemented before the portal", el => el.value = "Implemented before the portal"], ["Submitted twice", el => el.value = "Submitted twice"], ["Withdrawn", el => el.value = "Withdrawn"]] },
  ], async d => { if (!d.note) throw new Error("Say why it is cancelled (one line)."); await POST(`/store/est/variations/${v.id}/cancel`, { note: d.note }); await reload(); toast(`${v.ref || "Variation"} cancelled - the ones after it are renumbered`); },
  { save: "Cancel variation", top: `<div class="small muted" style="margin-bottom:8px">It stays on the log, struck out with your note. It counts in no total and takes no number - ${esc(v.ref || "")} goes, and the variations after it move up (e.g. V05 becomes V04).</div>` });
}
// Variation numbers: V01, V02 ... in the order they are made (the server gives the same number).
function vref(n) { return "V" + String(+n || 0).padStart(2, "0"); }
function nextVoRef() { return vref(Math.max(0, ...ST.b.variations.map(x => +x.seq || 0)) + 1); }
function nextSubVoRef(s) {
  const nums = (s.vos || []).map(x => { const m = String(x.ref || "").trim().match(/^V(\d+)$/i); return m ? +m[1] : 0; });
  return vref(Math.max((s.vos || []).length, ...nums) + 1);
}

// ---------------- Overview > invoices (from Accounts) ----------------
SECTIONS["client.inv"] = el => {
  const b = ST.b, list = b.invoices.filter(match);
  const tax = list.filter(i => i.kind === "tax" && i.status !== "cancelled");
  el.innerHTML = `<div class="tools"><input class="q" placeholder="Search" value="${esc(ST.q[key()] || "")}" data-q><span class="spacer"></span><span class="small muted">Read from Accounts > Invoices (project ${esc(b.project.code)}) ${tip("Invoices are made in Accounts > Invoices. Any invoice with this project number shows here by itself.")}</span>${ST.meta.me.accounts && window.PG_EMBED ? `<button class="btn btn-ghost btn-sm" id="go-inv">Open Accounts > Invoices</button>` : ""}</div>
    <div class="strip"><div class="fig"><div class="l">Invoiced (tax)</div><div class="v">${aed(tax.reduce((a, i) => a + i.total, 0))}</div><div class="s">${tax.length} invoices</div></div><div class="fig green"><div class="l">Received</div><div class="v">${aed(b.summary.received)}</div><div class="s">Accounts > Project payments</div></div><div class="fig amber"><div class="l">Certified, not invoiced</div><div class="v">${aed(Math.max(0, b.summary.client_certified * (1 + b.project.vat_pct / 100) - tax.reduce((a, i) => a + i.total, 0)))}</div></div></div>` +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>Type</th><th>Number</th><th>Date</th><th>Work</th><th class="r">Amount</th><th class="r">VAT</th><th class="r">Total</th><th>Status</th></tr></thead><tbody>${list.map(i => `<tr><td>${i.kind === "tax" ? "Tax invoice" : "Proforma"}</td><td><b>${esc(i.number)}</b></td><td>${dt(i.date)}</td><td>${esc(i.work)}</td><td class="r">${money(i.subtotal)}</td><td class="r">${money(i.vat)}</td><td class="r">${money(i.total)}</td><td>${st(i.status === "cancelled" ? "Cancelled" : "Issued")}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">No invoices for project ${esc(b.project.code)} in Accounts yet.</div>`);
  bindTools(el, () => SECTIONS["client.inv"](el));
  const g = $("#go-inv", el); if (g) g.onclick = () => parent.postMessage({ est: "app", page: "accounts", tab: "invoices" }, location.origin);
};

SECTIONS["site.vo"] = el => SECTIONS["client.vo"](el);      // the same variations, from Site & technical too
// ---------------- Site & technical: RFIs, submittals, NOCs & approvals ----------------
// One line per item. The status is one click (the dates stamp themselves), remarks are typed straight
// into the line - for anything stuck, so everyone sees why. The pencil opens the few details there are.
const LOGCFG = {
  rfi: { name: "RFI", pre: "RFI", title: "Subject", add: "New RFI - type the subject and press Enter", days: "rfi_days",
         steps: [["Open", "Open"], ["Answered", "Answered"], ["Closed", "Closed"]] },
  submittal: { name: "Submittal", pre: "SUB", title: "Item submitted", add: "New submittal - type what is being submitted and press Enter", days: "submittal_days",
         steps: [["Preparing", "Preparing"], ["Submitted", "Sent"], ["Approved", "Approved"], ["Approved as noted", "As noted"], ["Revise & resubmit", "Revise"], ["Rejected", "Rejected"]] },
  approval: { name: "Item", pre: "AP", title: "Item",
         steps: [["Not started", "Not started"], ["Submitted", "Submitted"], ["Approved", "Approved"], ["Rejected", "Rejected"], ["N/A", "N/A"]] },
};
const LOG_DONE = ["Closed", "Approved", "Approved as noted", "Answered", "Rejected", "N/A"];
const STEP_TONE = { "Not started": "z", "Preparing": "z", "Approved": "g", "Approved as noted": "g", "Answered": "g", "Closed": "g", "Submitted": "b", "Open": "b", "Revise & resubmit": "a", "Rejected": "r", "N/A": "n" };
// What one click on a status writes: the status, and the date it happened (today) where that date is still empty.
function stepData(kind, l, s) {
  const t = today(), d = { status: s };
  const sentAt = () => { if (!l.sent) d.sent = t; if (kind !== "approval" && !l.due) d.due = addDays(ST.b.rules[LOGCFG[kind].days] || 14); };
  if (kind === "approval") {
    if (s === "Not started") { d.sent = null; d.replied = null; }
    else if (s === "Submitted") { sentAt(); d.replied = null; }
    else if (s === "Approved" || s === "Rejected") { if (!l.sent) d.sent = t; d.replied = t; }
  } else if (kind === "submittal") {
    if (s === "Preparing") { d.sent = null; d.replied = null; d.due = null; }
    else if (s === "Submitted") { sentAt(); d.replied = null; }
    else { if (!l.sent) d.sent = t; d.replied = t; }
  } else {
    if (s === "Open") d.replied = null;
    else { if (!l.replied) d.replied = t; }
  }
  return d;
}
function dueTag(l) {
  if (!l.due || LOG_DONE.includes(l.status) || l.replied) return l.due ? `<span class="muted">${dt(l.due)}</span>` : "";
  const n = Math.round((new Date(l.due) - new Date(today())) / 864e5);
  return n < 0 ? `<span class="due late">${-n} day${n === -1 ? "" : "s"} late</span>` : n === 0 ? `<span class="due soon">due today</span>` : `<span class="due ${n <= 3 ? "soon" : ""}">in ${n} day${n === 1 ? "" : "s"}</span>`;
}
function stampLine(kind, l) {
  const a = kind === "approval" ? ["Submitted", "Approved"] : kind === "rfi" ? ["Sent", "Answered"] : ["Sent", "Reply"];
  const bits = [l.sent ? `${a[0]} ${dt(l.sent)}` : "", l.replied ? `${l.status === "Rejected" ? "Rejected" : a[1]} ${dt(l.replied)}` : ""].filter(Boolean);
  return bits.length ? `<div class="stamp">${bits.join(" · ")}</div>` : "";
}
function stepsHtml(kind, l) {
  return `<div class="steps">${LOGCFG[kind].steps.map(([v, lab]) => `<button class="${l.status === v ? "on " + (STEP_TONE[v] || "") : ""}" data-step="${l.id}" data-v="${esc(v)}" title="${esc(v)}${l.status === v ? "" : " - one click, today's date goes in"}">${esc(lab)}</button>`).join("")}</div>${stampLine(kind, l)}`;
}
const dIn = (l, k) => `<input type="date" class="cell-d" data-cell="${l.id}" data-k="${k}" value="${l[k] || ""}" title="Change the date">`;
const tIn = (l, k, ph, cls = "") => `<input class="cell-t ${cls}" data-cell="${l.id}" data-k="${k}" value="${esc(l[k] || "")}" placeholder="${esc(ph)}" data-spell="off">`;
function logRemarks(l) { return `<input class="cell-t rm ${l.note ? "has" : ""}" data-cell="${l.id}" data-k="note" value="${esc((l.note || "").replace(/\n/g, " · "))}" placeholder="Add a remark..." data-spell="off" title="${esc(l.note || "Anything stuck or to remember - everyone on the project sees it")}">`; }
// Saving a typed cell: no reload, the line keeps its place and the cursor moves on.
function bindLogCells(el, redraw) {
  $$("[data-step]", el).forEach(x => x.onclick = async () => {
    const l = ST.b.logs.find(y => y.id === +x.dataset.step); if (!l || l.status === x.dataset.v) return;
    try { await PATCH(`/store/est/logs/${l.id}`, stepData(l.kind, l, x.dataset.v)); await reload(); toast(`${l.title.slice(0, 40)}: ${x.dataset.v}`); } catch (e) { fail(e); }
  });
  $$("[data-cell]", el).forEach(x => {
    const save = async () => {
      const l = ST.b.logs.find(y => y.id === +x.dataset.cell); const k = x.dataset.k; if (!l) return;
      const v = x.value.trim(), old = k === "note" ? (l.note || "").replace(/\n/g, " · ") : (l[k] || "");
      if (v === old) return;
      try { await PATCH(`/store/est/logs/${l.id}`, { [k]: v || (x.type === "date" ? null : "") }); l[k] = v; x.classList.toggle("has", !!v); x.classList.add("saved"); setTimeout(() => x.classList.remove("saved"), 900); }
      catch (e) { fail(e); x.value = old; }
    };
    x.onchange = save;
    x.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); x.blur(); } if (e.key === "Escape") { x.value = x.dataset.k === "note" ? "" : x.value; x.blur(); } };
  });
  $$("[data-resub]", el).forEach(x => x.onclick = () => { const l = ST.b.logs.find(y => y.id === +x.dataset.resub);
    quickLog(l.id, { rev: String((+l.rev || 0) + 1), status: "Submitted", sent: today(), replied: null, due: addDays(ST.b.rules.submittal_days) }, "Resubmitted - rev " + ((+l.rev || 0) + 1)); });
}
function logSection(kind) {
  return el => {
    const b = ST.b, cfg = LOGCFG[kind], f = filt(), sts = ST.meta.log_status[kind], t = today();
    const all = b.logs.filter(l => l.kind === kind);
    const isLate = l => l.due && l.due < t && !l.replied && !LOG_DONE.includes(l.status);
    const list = all.filter(l => (!f || l.status === f || (f === "Overdue" && isLate(l)) || (f === "With remarks" && l.note)) && match(l));
    const late = all.filter(isLate).length, noted = all.filter(l => l.note).length;
    el.innerHTML = tools(kind, { chips: [["", all.length], ...sts.map(s => [s, all.filter(l => l.status === s).length]).filter(([s, n]) => n || ["Submitted", "Open"].includes(s)), ["Overdue", late], ["With remarks", noted]],
        right: `<button class="btn btn-plain btn-sm" id="rules" title="Days allowed for a reply - the due date is set from it">Reply in ${b.rules[cfg.days]} days</button>` }) +
      `<div class="qadd"><input id="qa-title" placeholder="${esc(cfg.add)}"><select id="qa-party" title="Sent to">${ST.meta.parties.map(x => `<option ${x === (lastLog(kind, "party") || "Consultant") ? "selected" : ""}>${esc(x)}</option>`).join("")}</select><button class="btn btn-primary" id="qa-go">Add</button></div>` +
      (list.length ? `<div class="tw"><table class="t lg"><colgroup><col style="width:76px"><col>${kind === "submittal" ? '<col style="width:46px">' : ""}<col style="width:104px"><col style="width:${kind === "submittal" ? 410 : 250}px"><col style="width:26%"><col style="width:36px"></colgroup>
        <thead><tr><th>No.</th><th>${cfg.title}</th>${kind === "submittal" ? '<th class="c">Rev</th>' : ""}<th>Reply due</th><th>Status - one click</th><th>Remarks</th><th></th></tr></thead><tbody>
        ${list.map(l => `<tr class="${isLate(l) ? "late-row" : ""}"><td class="nowrap"><b>${cfg.pre}-${pad(l.seq)}</b></td>
          <td><div class="t1">${esc(l.title)}</div><div class="small muted">to ${esc(l.party || "-")}${l.ref ? " · Ref. " + esc(l.ref) : ""}</div></td>${kind === "submittal" ? `<td class="c">${esc(l.rev || "0")}</td>` : ""}
          <td class="nowrap small">${dueTag(l)}</td>
          <td>${stepsHtml(kind, l)}${l.status === "Revise & resubmit" ? `<button class="btn btn-ghost btn-sm resub" data-resub="${l.id}">Resubmit as rev ${(+l.rev || 0) + 1}</button>` : ""}</td>
          <td>${logRemarks(l)}</td><td><button class="ico" data-edit="${l.id}" title="Details">&#9998;</button></td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">No ${cfg.name}s${f ? " here" : " yet"} - type one in the box above.</div>`);
    bindTools(el, () => logSection(kind)(el));
    $("#rules", el).onclick = rulesForm;
    const add = async () => {
      const title = $("#qa-title").value.trim(); if (!title) { $("#qa-title").focus(); return; }
      try { await POST("/store/est/logs", { kind, project_id: ST.pid, title, party: $("#qa-party").value, status: kind === "rfi" ? "Open" : "Submitted", sent: t }); await reload(); toast(`${cfg.name} added - sent today, reply due in ${b.rules[cfg.days]} days`); setTimeout(() => { const q = $("#qa-title"); if (q) q.focus(); }, 50); }
      catch (e) { fail(e); }
    };
    $("#qa-go", el).onclick = add; $("#qa-title", el).onkeydown = e => { if (e.key === "Enter") add(); };
    bindLogCells(el);
    $$("[data-edit]", el).forEach(x => x.onclick = () => logForm(kind, all.find(l => l.id === +x.dataset.edit)));
  };
}
async function quickLog(id, d, msg) { try { await PATCH(`/store/est/logs/${id}`, d); await reload(); toast(msg); } catch (e) { fail(e); } }
function lastLog(kind, k) { const L = ST.b.logs.filter(x => x.kind === kind && x[k]); return L.length ? L[L.length - 1][k] : ""; }
function logForm(kind, l) {
  l = l || {}; const cfg = LOGCFG[kind], m = ST.meta;
  const fields = [
    { k: "title", label: cfg.title, value: l.title || "", full: true, focus: true },
    { k: "party", label: "Sent to", type: "select", options: m.parties, value: l.party || lastLog(kind, "party") || "Consultant" },
    { k: "ref", label: "Ref. / letter no.", value: l.ref || "" },
    ...(kind === "submittal" ? [{ k: "rev", label: "Revision", type: "select", options: ["0", "1", "2", "3", "4", "5"], value: l.rev || "0" }] : []),
    { k: "discipline", label: "Discipline", type: "select", options: ["", ...m.disciplines], value: l.discipline || (l.id ? "" : lastLog(kind, "discipline")) },
    { k: "note", label: "Remarks", type: "area", full: true, value: l.note || "", ph: "Anything stuck or to remember - everyone on the project sees it" },
    { k: "sent", label: "Sent on", type: "date", value: l.sent || (l.id ? "" : today()), tip: "Put in by the status click - change it only if it went on another day." },
    { k: "due", label: "Reply due", type: "date", value: l.due || "", tip: `Set for you: ${ST.b.rules[cfg.days]} days after it is sent.` },
    ...(l.id ? [{ k: "replied", label: "Reply received", type: "date", value: l.replied || "" }] : []),
  ];
  modal(l.id ? `${cfg.pre}-${pad(l.seq)}` : `New ${cfg.name}`, fields,
    async v => { if (l.id) await PATCH(`/store/est/logs/${l.id}`, v); else { v.kind = kind; v.project_id = ST.pid; v.status = kind === "rfi" ? "Open" : v.sent ? "Submitted" : "Preparing"; await POST("/store/est/logs", v); } await reload(); toast("Saved"); },
    { wide: true, doc: { kind: "log", what: kind === "rfi" ? "RFI or its letter" : "submittal transmittal or its letter", want: [["title", "Subject"], ["ref", "Ref. / letter no."]] },
      del: l.id ? async () => { await DEL(`/store/est/logs/${l.id}`); reload(); } : null });
}
SECTIONS["site.rfi"] = logSection("rfi");
SECTIONS["site.submittal"] = el => submittalSection(el);

// ---------------- Site & technical > Submittals - the material submittal log, as it is kept ----------------
// Grouped by discipline (CIVIL, ELECTRICAL, PLUMBING, HVAC, SHOP DRAWINGS ...): Sr. No, material, specification,
// manufacturer / supplier, rev, submitted, reviewed and the consultant's status code. Another supplier for an item
// sits under it. The status is picked from the codes (the date stamps itself); a row opens its form; remarks are typed in.
const SUBST = [["Not submitted", "NS", "n", "To submit"], ["Under review", "UR", "b", "Under review"], ["Approved", "A", "g", "Approved"], ["Approved as noted", "AAN", "g", "As noted"], ["Revise & resubmit", "R&R", "a", "Revise"], ["Rejected", "R", "r", "Rejected"]];
const subCode = s => (SUBST.find(x => x[0] === s) || [s, "", ""])[1];
function subStatusData(l, s) {
  const t = today(), d = { status: s };
  if (s === "Not submitted") { d.sent = null; d.replied = null; d.due = null; }
  else if (s === "Under review") { if (!l.sent) d.sent = t; d.replied = null; if (!l.due) d.due = addDays(ST.b.rules.submittal_days || 14); }
  else { if (!l.sent) d.sent = t; if (!l.replied) d.replied = t; }
  return d;
}
function submittalSection(el) {
  const b = ST.b, f = filt(), t = today();
  const all = b.logs.filter(l => l.kind === "submittal").sort((x, y) => (x.sort - y.sort) || (x.id - y.id));
  const isLate = l => l.status === "Under review" && l.due && l.due < t && !l.replied;
  const list = all.filter(l => (!f || l.status === f || (f === "Overdue" && isLate(l))) && match(l));
  const groups = [...new Set(all.map(l => l.group || "GENERAL"))];
  const chips = [["", all.length], ...SUBST.map(([s]) => [s, all.filter(l => l.status === s).length]).filter(([s, n]) => n || s === "Under review"), ["Overdue", all.filter(isLate).length]];
  el.innerHTML = tools("submittal", { add: `<button class="btn btn-primary" id="sb-add">+ New submittal</button>`,
      right: `<span class="sb-legend">${SUBST.map(([s, c, tone]) => `<span class="sb-code ${tone}" title="${esc(s)}">${esc(c)}</span>`).join("")}</span><button class="btn btn-plain btn-sm" id="rules" title="Days allowed for the consultant's review - the reply due date is set from it">Review in ${b.rules.submittal_days} days</button>`,
      chips }) +
    (list.length ? `<div class="tw sb-wrap"><table class="t sb"><colgroup><col style="width:52px"><col style="width:23%"><col style="width:15%"><col style="width:22%"><col style="width:42px"><col style="width:96px"><col style="width:92px"><col style="width:166px"><col style="width:34px"></colgroup>
      <thead><tr><th class="c">Sr. No</th><th>Material description</th><th>Specification</th><th>Manufacturer / supplier</th><th class="c">Rev</th><th>Submitted</th><th>Reviewed</th><th>Consultant status</th><th></th></tr></thead>
      ${groups.map(g => { const rows = list.filter(l => (l.group || "GENERAL") === g); if (!rows.length) return "";
        let prev = null;
        return `<tbody><tr class="sb-grp"><td colspan="9"><b>${esc(g)}</b><span class="muted small"> ${rows.length} line${rows.length === 1 ? "" : "s"}</span><button class="btn btn-ghost btn-sm" data-sbadd="${esc(g)}">+ Add to ${esc(g.toLowerCase())}</button></td></tr>
          ${rows.map(l => { const alt = prev && l.item_no && l.item_no !== "*" && prev.item_no === l.item_no && prev.title === l.title; prev = l;
            const tone = (SUBST.find(x => x[0] === l.status) || [])[2] || "";
            return `<tr class="sb-row ${isLate(l) ? "late-row" : ""} ${alt ? "alt" : ""} ${l.item_no === "*" ? "part" : ""}" data-sbrow="${l.id}">
              <td class="c"><b>${alt ? "" : esc(l.item_no || "")}</b></td>
              <td>${alt ? `<span class="muted small">&#8627; another supplier</span>` : `<span class="t1">${esc(l.title)}</span>`}${l.note ? `<div class="sb-note" title="${esc(l.note)}">${esc(l.note)}</div>` : ""}</td>
              <td>${esc(l.spec || "")}</td><td>${esc(l.supplier || "")}</td><td class="c">${esc(l.rev || "")}</td>
              <td class="nowrap">${l.sent ? dt(l.sent) : '<span class="muted">-</span>'}${isLate(l) ? `<div class="due late">${Math.round((new Date(t) - new Date(l.due)) / 864e5)} days late</div>` : ""}</td>
              <td class="nowrap">${l.replied ? dt(l.replied) : '<span class="muted">-</span>'}</td>
              <td>${l.status || (l.item_no !== "*" && !l.sent) ? `<select class="sb-st ${tone}" data-sbst="${l.id}" title="The consultant's status - picking it puts today's date in where it is still empty">
                ${SUBST.map(([s, c, , sh]) => `<option value="${esc(s)}" ${l.status === s ? "selected" : ""} title="${esc(s)}">${esc(c)} · ${esc(sh)}</option>`).join("")}${l.status ? "" : '<option value="" selected>- (heading)</option>'}</select>` : ""}
                ${l.status === "Revise & resubmit" ? `<button class="btn btn-ghost btn-sm" data-resub="${l.id}">Resubmit as rev ${(+l.rev || 0) + 1}</button>` : ""}</td>
              <td class="r"><button class="ico" data-sbedit="${l.id}" title="Open">&#9998;</button></td></tr>`; }).join("")}</tbody>`; }).join("")}
      </table></div>` : `<div class="empty">No submittals${f ? " here" : " yet"}. Press <b>+ New submittal</b>.</div>`);
  bindTools(el, () => submittalSection(el));
  $("#rules", el).onclick = rulesForm;
  $("#sb-add", el).onclick = () => submittalForm(null, groups[groups.length - 1] || "CIVIL");
  $$("[data-sbadd]", el).forEach(x => x.onclick = e => { e.stopPropagation(); submittalForm(null, x.dataset.sbadd); });
  $$("[data-sbst]", el).forEach(x => { x.onclick = e => e.stopPropagation(); x.onchange = async () => {
    const l = all.find(y => y.id === +x.dataset.sbst); if (!l || !x.value) return;
    try { await PATCH(`/store/est/logs/${l.id}`, subStatusData(l, x.value)); await reload(); toast(`${l.title.slice(0, 40)}: ${subCode(x.value)} - ${x.value}`); } catch (e2) { fail(e2); } }; });
  $$("[data-resub]", el).forEach(x => x.onclick = e => { e.stopPropagation(); const l = all.find(y => y.id === +x.dataset.resub);
    quickLog(l.id, { rev: String((+l.rev || 0) + 1), status: "Under review", sent: today(), replied: null, due: addDays(b.rules.submittal_days) }, `Resubmitted - rev ${(+l.rev || 0) + 1}, under review`); });
  bindLogCells(el);
  $$("[data-sbedit]", el).forEach(x => x.onclick = e => { e.stopPropagation(); submittalForm(all.find(l => l.id === +x.dataset.sbedit)); });
  $$("[data-sbrow]", el).forEach(r => r.onclick = e => { if (e.target.closest("input,select,button,a")) return; submittalForm(all.find(l => l.id === +r.dataset.sbrow)); });
}
function submittalForm(l, group) {
  const b = ST.b, all = b.logs.filter(x => x.kind === "submittal"), edit = !!(l && l.id); l = l || {};
  const groups = [...new Set(all.map(x => x.group).filter(Boolean))];
  const g = l.group || group || groups[groups.length - 1] || "CIVIL";
  const nums = all.map(x => parseInt(x.item_no, 10)).filter(n => !isNaN(n));
  const fields = [
    { k: "group", label: "Discipline", type: "combo", options: groups.length ? groups : ["CIVIL", "ELECTRICAL", "PLUMBING", "HVAC", "SHOP DRAWINGS"], value: g, tip: "The heading it sits under on the log - pick one, or type a new one." },
    { k: "item_no", label: "Sr. No", value: edit ? (l.item_no || "") : String((nums.length ? Math.max(...nums) : 0) + 1), tip: "As on the log. Another supplier for the same item: give it the same Sr. No. A part of an item (e.g. the MEP drawings): *." },
    { k: "title", label: "Material description", value: l.title || "", full: true, focus: true },
    { k: "spec", label: "Specification", value: l.spec || "", ph: "e.g. C45/20, Jindal FY460, Ducab" },
    { k: "supplier", label: "Manufacturer / supplier", type: "combo", options: [...new Set(all.map(x => x.supplier).filter(Boolean))].sort(), value: l.supplier || "" },
    { k: "rev", label: "Rev", type: "select", options: ["", "0", "1", "2", "3", "4", "5", "6"], value: l.rev ?? (edit ? "" : "0") },
    { k: "status", label: "Consultant status", type: "select", options: SUBST.map(x => x[0]), value: l.status || (edit ? "" : "Under review") },
    { k: "sent", label: "Submitted", type: "date", value: l.sent || (edit ? "" : today()) },
    { k: "replied", label: "Reviewed", type: "date", value: l.replied || "" },
    { k: "ref", label: "Transmittal / ref. no.", value: l.ref || "" },
    { k: "note", label: "Remarks", type: "area", full: true, value: l.note || "", ph: "Consultant's comments, what is pending - everyone on the project sees it" },
  ];
  modal(edit ? `${l.item_no ? "Sr. No " + l.item_no + " - " : ""}${l.title}` : "New submittal", fields, async v => {
    v.group = (v.group || "").trim().toUpperCase();
    if (!v.title.trim()) throw new Error("Type the material.");
    if (v.status === "Not submitted") { v.sent = v.sent || null; v.replied = null; }
    if (v.sent && !v.replied && v.status === "Under review" && !(l.due)) v.due = addDays(b.rules.submittal_days || 14, v.sent);
    if (edit) await PATCH(`/store/est/logs/${l.id}`, v);
    else {
      // it goes in its place on the log: under its item (another supplier), else at the end of its discipline
      const same = all.filter(x => (x.group || "") === v.group).sort((a, c) => a.sort - c.sort);
      const item = v.item_no ? same.filter(x => x.item_no === v.item_no) : [];
      const after = (item.length ? item[item.length - 1] : same[same.length - 1]) || null;
      await POST("/store/est/logs", Object.assign(v, { kind: "submittal", project_id: ST.pid, party: "Consultant", discipline: v.group }, after ? { after: after.id } : {}));
    }
    await reload(); toast(edit ? "Saved" : "Submittal added");
  }, { wide: true, save: edit ? "Save" : "Add submittal",
       extra: edit ? `<button class="btn btn-plain" id="sb-alt" title="The same item with another manufacturer / supplier - added under it">+ Another supplier</button>` : "",
       after: () => { const a = $("#sb-alt"); if (a) a.onclick = async () => { if (!(await closeModal())) return;
         submittalForm({ group: l.group, item_no: l.item_no, title: l.title, spec: l.spec, rev: "0", status: "Under review", sent: today() }); }; },
       del: edit ? async () => { await DEL(`/store/est/logs/${l.id}`); await reload(); } : null });
}

// ---------------- Site & technical > NOCs & approvals (the project tracker) ----------------
SECTIONS["site.approval"] = el => {
  const b = ST.b, f = filt();
  const all = b.logs.filter(l => l.kind === "approval");
  const list = all.filter(l => (!f || l.status === f || (f === "With remarks" && l.note)) && match(l));
  const done = all.filter(l => ["Approved", "N/A"].includes(l.status)).length, pct = all.length ? Math.round(100 * done / all.length) : 0;
  let html = tools("approval", { add: `<button class="btn btn-ghost" id="add-ap">+ Item</button>`,
      chips: [["", all.length], ...ST.meta.log_status.approval.map(s => [s, all.filter(l => l.status === s).length]), ["With remarks", all.filter(l => l.note).length]],
      right: `<div class="prog" title="Approved or not needed"><div class="bar"><i style="width:${pct}%"></i></div><span>${done} of ${all.length} done</span></div>` });
  html += `<div class="tw"><table class="t lg"><colgroup><col><col style="width:160px"><col style="width:350px"><col style="width:140px"><col style="width:26%"><col style="width:36px"></colgroup>
    <thead><tr><th>Item</th><th>Authority</th><th>Status - one click</th><th>Ref. / permit no.</th><th>Remarks</th><th></th></tr></thead><tbody>`;
  let g = null;
  for (const l of list) {
    if (l.group !== g) { g = l.group; html += `<tr class="sec"><td colspan="6">${esc(g || "Other")}</td></tr>`; }
    html += `<tr><td><div class="t1">${esc(l.title)}</div></td><td class="small">${esc(l.party)}</td><td>${stepsHtml("approval", l)}</td>
      <td>${tIn(l, "ref", "Type it")}</td><td>${logRemarks(l)}</td><td><button class="ico" data-edit="${l.id}" title="Details">&#9998;</button></td></tr>`;
  }
  el.innerHTML = html + "</tbody></table></div>";
  bindTools(el, () => SECTIONS["site.approval"](el));
  bindLogCells(el);
  $$("[data-edit]", el).forEach(x => x.onclick = () => apForm(all.find(l => l.id === +x.dataset.edit)));
  $("#add-ap", el).onclick = () => apForm();
};
function apForm(l) {
  l = l || {};
  modal(l.id ? l.title : "New approval item", [
    { k: "title", label: "Item", value: l.title || "", focus: !l.id, full: true, ph: "e.g. Civil Defence NOC" },
    { k: "party", label: "Authority", type: "select", options: ST.meta.parties, value: l.party || "DM (Dubai Municipality)" },
    { k: "group", label: "Stage", type: "combo", options: [...new Set(ST.b.logs.filter(x => x.kind === "approval").map(x => x.group))], value: l.group || "NOCs", tip: "The heading it sits under in the list." },
    { k: "ref", label: "Ref. / permit no.", value: l.ref || "" },
    { k: "note", label: "Remarks", type: "area", full: true, value: l.note || "", ph: "Anything stuck or to remember - everyone on the project sees it" },
    ...(l.id ? [{ k: "sent", label: "Submitted on", type: "date", value: l.sent || "", tip: "Put in by the Submitted click - change it only if it went on another day." },
                { k: "replied", label: "Approved on", type: "date", value: l.replied || "", tip: "Put in by the Approved click - change it only if it came on another day." }] : []),
  ], async v => { if ("sent" in v && !v.sent) v.sent = null; if ("replied" in v && !v.replied) v.replied = null; if (l.id) await PATCH(`/store/est/logs/${l.id}`, v); else await POST("/store/est/logs", Object.assign(v, { kind: "approval", project_id: ST.pid, status: "Not started" })); await reload(); toast("Saved"); },
  { save: l.id ? "Save" : "Add item", doc: { kind: "approval", what: "NOC, permit or authority letter", want: [["title", "Item"], ["ref", "Ref. / permit no."]] }, del: l.id ? async () => { await DEL(`/store/est/logs/${l.id}`); reload(); } : null });
}

// =====================================================================
// TENDERS
// =====================================================================
async function loadTenders() {
  const early = ST.early; ST.early = null;
  try { ST.tenders = (early && await early) || await GET("/store/est/tenders"); } catch (e) { return fail(e); }
  drawTenders();
}
function drawTenders() {
  const all = ST.tenders.tenders, f = ST.filt.tenders || "", q = (ST.q.tenders || "").toLowerCase(), t = ST.tenders.today;
  const list = all.filter(x => (!f || x.status === f) && (!q || JSON.stringify(x).toLowerCase().includes(q)));
  const sts = ["Received", "Pricing", "Submitted", "Won", "Lost", "Dropped"];
  const won = all.filter(x => x.status === "Won"), dec = all.filter(x => ["Won", "Lost"].includes(x.status));
  const sum = s => all.filter(x => s.includes(x.status)).reduce((a, x) => a + x.value, 0);
  $("#app").innerHTML = `<div class="wrap">
    <div class="strip"><div class="fig"><div class="l">Being priced</div><div class="v">${all.filter(x => ["Received", "Pricing"].includes(x.status)).length}</div><div class="s">${all.filter(x => ["Received", "Pricing"].includes(x.status) && x.due && x.due < t).length} past due</div></div>
      <div class="fig amber"><div class="l">Submitted, waiting</div><div class="v">${aed(sum(["Submitted"]))}</div></div><div class="fig green"><div class="l">Won</div><div class="v">${aed(sum(["Won"]))}</div><div class="s">${won.length} tenders</div></div>
      <div class="fig"><div class="l">Hit rate</div><div class="v">${dec.length ? Math.round(100 * won.length / dec.length) : 0}%</div><div class="s">won of decided</div></div></div>
    <div class="tools"><button class="btn btn-primary" id="add-t">+ Tender</button><input class="q" placeholder="Search" value="${esc(ST.q.tenders || "")}" id="tq"><div class="chips">${[["", all.length], ...sts.map(s => [s, all.filter(x => x.status === s).length])].map(([v, n]) => `<span class="chip ${f === v ? "on" : ""}" data-tf="${v}">${v || "All"}<span class="n">${n}</span></span>`).join("")}</div><span class="spacer"></span>${xpButtons("tenders", { q: ST.q.tenders || "", status: f })}</div>
    ${list.length ? `<div class="tw"><table class="t"><thead><tr><th>No.</th><th>Tender</th><th>Client</th><th>Consultant</th><th>Received</th><th>Due</th><th>Submitted</th><th class="r">Value</th><th>Estimator</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map(x => `<tr class="rowc" data-t="${x.id}"><td class="nowrap"><b>T-${pad(x.seq)}</b></td><td>${esc(x.name)}<div class="small muted">${esc([x.kind, x.location].filter(Boolean).join(" · "))}</div></td><td>${esc(x.client)}</td><td class="small">${esc(x.consultant)}</td><td class="nowrap">${dt(x.received)}</td><td class="nowrap ${x.due && x.due < t && ["Received", "Pricing"].includes(x.status) ? "late" : ""}">${dt(x.due)}</td><td class="nowrap">${dt(x.submitted)}</td><td class="r">${money(x.value)}</td><td>${esc(x.estimator)}</td><td>${st(x.status)}</td>
      <td class="nowrap">${x.status === "Received" ? `<button class="btn btn-ghost btn-sm" data-ts="${x.id}:Pricing">Start pricing</button>` : x.status === "Pricing" ? `<button class="btn btn-ghost btn-sm" data-ts="${x.id}:Submitted">Submitted</button>` : x.status === "Submitted" ? `<button class="btn btn-ok btn-sm" data-won="${x.id}">Won</button> <button class="btn btn-plain btn-sm" data-ts="${x.id}:Lost">Lost</button>` : x.status === "Won" && x.project_id ? `<button class="btn btn-plain btn-sm" data-openp="${x.project_id}">Open project</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>` : `<div class="card empty">No tenders${f ? " here" : " yet"}.</div>`}
  </div>`;
  $("#add-t").onclick = () => tenderForm();
  $("#tq").oninput = debounce(e => { ST.q.tenders = $("#tq").value; drawTenders(); const n = $("#tq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 250);
  $$("[data-tf]").forEach(c => c.onclick = () => { ST.filt.tenders = ST.filt.tenders === c.dataset.tf ? "" : c.dataset.tf; drawTenders(); });
  $$("[data-t]").forEach(r => r.onclick = e => { if (e.target.closest("button")) return; tenderForm(all.find(x => x.id === +r.dataset.t)); });
  $$("[data-ts]").forEach(b => b.onclick = async () => { const [id, s] = b.dataset.ts.split(":"); const d = { status: s }; if (s === "Submitted") d.submitted = t; try { await PATCH(`/store/est/tenders/${id}`, d); await loadTenders(); toast(s); } catch (e) { fail(e); } });
  $$("[data-openp]").forEach(b => b.onclick = () => goProject(+b.dataset.openp));
  $$("[data-won]").forEach(b => b.onclick = () => {
    const x = all.find(y => y.id === +b.dataset.won), used = new Set(ST.meta.projects.map(p => p.code));
    modal(`Won - ${x.name}`, [{ k: "code", label: "It becomes project", type: "combo", options: ST.meta.sites.filter(s => !used.has(s.code)).map(s => s.code), focus: true, tip: "Pick the site code. The project is made with the tender's client, consultant and value." }],
      async v => { const r = await POST(`/store/est/tenders/${x.id}/won`, v); ST.meta = await GET("/store/est/meta"); await loadTenders(); toast("Project " + v.code + " made"); goProject(r.project_id); }, { save: "Make the project" });
  });
}
function tenderForm(x) {
  x = x || {}; const all = ST.tenders.tenders;
  modal(x.id ? `T-${pad(x.seq)}` : "New tender", [
    { k: "name", label: "Tender / project", value: x.name || "", full: true, focus: true },
    { k: "client", label: "Client", type: "combo", options: [...new Set(all.map(y => y.client).filter(Boolean))], value: x.client || "" },
    { k: "consultant", label: "Consultant", type: "combo", options: [...new Set(all.map(y => y.consultant).filter(Boolean))], value: x.consultant || "" },
    { k: "kind", label: "Type", type: "select", options: ["Villa", "Building", "Fit-out", "Renovation", "Infrastructure", "Other"], value: x.kind || "Villa" },
    { k: "location", label: "Location", type: "combo", options: [...new Set(all.map(y => y.location).filter(Boolean))], value: x.location || "" },
    { k: "received", label: "Received", type: "date", value: x.received || today() },
    { k: "due", label: "Submission due", type: "date", value: x.due || "", quick: [["+1 week", el => el.value = addDays(7)], ["+2 weeks", el => el.value = addDays(14)], ["+3 weeks", el => el.value = addDays(21)]] },
    { k: "value", label: "Our price (AED)", type: "money", value: x.value || "" },
    { k: "estimator", label: "Estimator", type: "select", options: ["", ...ST.meta.users.map(u => u.name)], value: x.estimator || "" },
    { k: "status", label: "Status", type: "select", options: ["Received", "Pricing", "Submitted", "Won", "Lost", "Dropped"], value: x.status || "Received" },
    { k: "note", label: "Notes", type: "area", value: x.note || "" },
  ], async v => { if (x.id) await PATCH(`/store/est/tenders/${x.id}`, v); else await POST("/store/est/tenders", v); await loadTenders(); toast("Saved"); },
  { wide: true, doc: { kind: "tender", what: "tender invitation or enquiry", want: [["name", "Tender / project"], ["client", "Client"], ["due", "Submission due"]] }, del: x.id ? async () => { await DEL(`/store/est/tenders/${x.id}`); loadTenders(); } : null });
}
// =====================================================================
// ACCOUNTS > SUBCONTRACTOR PAYMENTS (the certificates Estimation sends for payment)
// =====================================================================
async function loadPay() {
  let d; try { d = await GET("/store/est/payqueue"); } catch (e) { $("#app").innerHTML = `<div class="wrap"><div class="empty">${esc(e.message)}</div></div>`; return; }
  ST.pay = d; ST.meta = ST.meta || { today: d.today };
  drawPay();
}
function drawPay() {
  // Accounts: verify what the contracts manager approved (it then goes to the Managing Director), and pay what the MD approved.
  const d = ST.pay, mineAcc = (d.mine || []).includes("acc") || (d.can || []).includes("acc");
  const f = ST.filt.pay ?? "__mine", q = (ST.q.pay || "").toLowerCase();
  const toSend = r => r.status === "Verified" && r.flow && r.flow.md_sent === false, withMd = r => r.status === "Verified" && !toSend(r);
  const isMine = r => r.status === "CM approved" || r.status === "MD approved" || toSend(r);
  const stOf = r => toSend(r) ? "__send" : withMd(r) ? "Verified" : r.status;
  const rows = d.rows.filter(r => (!f || (f === "__mine" ? isMine(r) : stOf(r) === f)) && (!q || JSON.stringify(r).toLowerCase().includes(q)));
  const n = s => d.rows.filter(r => stOf(r) === s).length;
  const sum = s => d.rows.filter(r => stOf(r) === s).reduce((a, r) => a + r.payable, 0);
  const age = h => h < 1 ? "just now" : h < 24 ? `${h} h` : `${Math.floor(h / 24)} day${h >= 48 ? "s" : ""}`;
  const fl = i => '<span class="flow">' + [0, 1, 2, 3, 4, 5, 6, 7].map(j => `<i class="${j < i ? "on" : j === i ? "cur" : ""}"></i>`).join("") + "</span>";
  const IDX = { "CM approved": 4, "Verified": 5, "MD approved": 6, "Paid": 7 };
  const LBL = { "CM approved": "To verify", "__send": "Verified - send to MD", "Verified": "With the MD", "MD approved": "MD approved - to pay", "Paid": "Paid" };
  const checks = r => { const c = r.checks || {}; const ok = t => `<span style="color:#1E6B2A">&#10003; ${t}</span>`, bad = t => `<span class="late">&#9888; ${t}</span>`;
    return [c.agreement ? ok("Agreement on file") : bad("No agreement ref. on the subcontract"),
            c.prev_n ? (c.unpaid.length ? bad(`Not paid yet: ${c.unpaid.join(", ")}`) : ok(`Previous ${c.prev_n} PC${c.prev_n > 1 ? "s" : ""} paid: ${money(c.prev_paid, false)}`)) : ok("First certificate"),
            c.adv_paid ? ok(`Advance ${money(c.adv_paid, false)} - recovered so far ${money(c.adv_rec, false)}`) : ""].filter(Boolean).join(" &middot; "); };
  const chip = (v, l, c) => `<span class="chip ${f === v ? "on" : ""}" data-pf="${v}">${l}<span class="n">${c}</span></span>`;
  $("#app").innerHTML = `<div class="wrap">
    <div class="strip"><div class="fig"><div class="l">To verify</div><div class="v">${n("CM approved")}</div><div class="s">${aed(sum("CM approved"))} approved by the contracts manager</div></div>
      <div class="fig amber"><div class="l">To pay now</div><div class="v">${aed(sum("MD approved"))}</div><div class="s">${n("MD approved")} approved by the MD</div></div>
      <div class="fig ${n("__send") ? "amber" : ""}"><div class="l">To send to MD</div><div class="v">${n("__send")}</div><div class="s">${aed(sum("__send"))} verified</div></div>
      <div class="fig"><div class="l">With the MD</div><div class="v">${n("Verified")}</div><div class="s">${aed(sum("Verified"))}</div></div>
      <div class="fig green"><div class="l">Paid (last 60 days)</div><div class="v">${aed(d.rows.filter(r => r.status === "Paid").reduce((a, r) => a + r.paid_amount, 0))}</div></div></div>
    <div class="tools"><input class="q" placeholder="Search" value="${esc(ST.q.pay || "")}" id="pq"><div class="chips">${chip("__mine", "Waiting for me", n("CM approved") + n("__send") + n("MD approved"))}${chip("CM approved", "To verify", n("CM approved"))}${chip("__send", "To send to MD", n("__send"))}${chip("MD approved", "To pay", n("MD approved"))}${chip("Verified", "With the MD", n("Verified"))}${chip("Paid", "Paid", n("Paid"))}${chip("", "All", d.rows.length)}</div>
      <span class="spacer"></span>${n("Verified") ? `<button class="btn btn-plain btn-sm" id="wa-all" title="One WhatsApp message to the managers with one link for all of them">WhatsApp the MD (${n("Verified")})</button>` : ""}<span class="small muted">Verify &rarr; Send to MD &rarr; MD approves &rarr; Mark paid ${tip("Verified keeps it with Accounts; Send to MD hands it over - the MD is told (bell and phone) and approves from the link: the PDF opens with Approve / Reject. It comes back here as MD approved - to pay.")}</span></div>
    ${rows.length ? `<div class="tw"><table class="t"><thead><tr><th>Project</th><th>Subcontractor</th><th>PC</th><th class="r">Payable</th><th>Progress &middot; last stamp</th><th>Stage</th><th>Days here</th><th>Paid</th><th></th></tr></thead><tbody>
    ${rows.map(r => { const w = r.flow || {}, mine = isMine(r) && mineAcc; return `<tr class="${w.stuck && r.status !== "Paid" ? "late-row" : ""}" style="${mine ? "background:#FFF8E6" : ""}"><td><b>${esc(r.project)}</b><div class="small muted">${esc(r.project_name)}</div></td><td><b>${esc(r.sub)}</b><div class="small muted">${esc(r.scope)}${r.inv_ref ? " · " + esc(r.inv_ref) : ""}</div></td><td class="nowrap">PC ${pad(r.seq, 2)}${r.pc_type !== "Interim" ? ` <span class="small muted">${esc(r.pc_type)}</span>` : ""}</td>
      <td class="r"><b>${money(r.payable, false)}</b><div class="small muted">VAT ${money(r.vat)}</div></td>
      <td>${fl(IDX[r.status] || 0)}<div class="small muted" style="margin-top:3px">${stampTxt(w.last)}</div>${w.note ? `<div class="small late">&ldquo;${esc(w.note)}&rdquo;</div>` : ""}${r.status === "CM approved" ? `<div class="small" style="margin-top:3px">${checks(r)}</div>` : ""}</td>
      <td>${st(LBL[stOf(r)] || r.status)}${withMd(r) && r.flow.md_sent_at ? `<div class="small muted">sent ${dt(r.flow.md_sent_at.slice(0, 10))} ${r.flow.md_sent_at.slice(11, 16)}</div>` : ""}</td><td class="nowrap ${w.stuck && r.status !== "Paid" ? "late" : ""}">${r.status !== "Paid" ? age(w.hours || 0) + (w.stuck ? '<div class="small">stuck</div>' : "") : ""}</td>
      <td class="nowrap">${dt(r.paid_on)}${r.paid_ref ? `<div class="small muted">${esc(r.paid_ref)}</div>` : ""}</td>
      <td class="nowrap"><button class="btn btn-plain btn-sm" data-pp="${r.pc_id}">Print</button> ${r.status === "CM approved" && mineAcc ? `<button class="btn btn-ok btn-sm" data-pver="${r.pc_id}">Verified &#10003;</button> <button class="btn btn-plain btn-sm" data-pback="${r.pc_id}">&#8630; Send back</button>` :
        r.status === "MD approved" && mineAcc ? `<button class="btn btn-ok btn-sm" data-ppay="${r.pc_id}">Mark paid</button>` :
        toSend(r) && mineAcc ? `<button class="btn btn-ok btn-sm" data-psend="${r.pc_id}">Send to MD &rarr;</button> <button class="btn btn-plain btn-sm" data-pback="${r.pc_id}">&#8630; Send back</button>` :
        withMd(r) ? `<button class="btn btn-plain btn-sm" data-pwa="${r.pc_id}">WhatsApp the MD</button>${mineAcc ? ` <button class="btn btn-plain btn-sm" data-precall="${r.pc_id}" title="Take it back from the MD (not approved yet)">&#8630;</button>` : ""}` :
        r.status === "Paid" && mineAcc ? `<button class="btn btn-plain btn-sm" data-pundo="${r.pc_id}" title="Not paid after all">&#8630;</button>` : ""}</td></tr>`; }).join("")}
    <tr class="tot"><td>Total</td><td></td><td></td><td class="r">${money(rows.reduce((a, r) => a + r.payable, 0))}</td><td></td><td></td><td></td><td></td><td></td></tr></tbody></table></div>`
    : `<div class="card empty">${f === "__mine" ? "Nothing waiting for you." : "Nothing " + (f === "Paid" ? "paid in the last 60 days" : "here") + "."}</div>`}</div>`;
  $("#pq").oninput = debounce(() => { ST.q.pay = $("#pq").value; drawPay(); const n2 = $("#pq"); n2.focus(); n2.setSelectionRange(n2.value.length, n2.value.length); }, 250);
  $$("[data-pf]").forEach(c => c.onclick = () => { ST.filt.pay = c.dataset.pf; drawPay(); });
  $$("[data-pp]").forEach(b => b.onclick = () => exportGo("preview", "pc", { id: +b.dataset.pp }));
  const row = id => d.rows.find(x => x.pc_id === +id);
  $$("[data-pver]").forEach(b => b.onclick = async () => { const r = row(b.dataset.pver);
    try { b.disabled = true; await POST(`/store/est/subpcs/${r.pc_id}/step`, { step: "Verified" }); await loadPay(); toast("Verified - now Send to MD", { ms: 4000 }); } catch (e) { b.disabled = false; fail(e); } });
  $$("[data-psend]").forEach(b => b.onclick = async () => { const r = row(b.dataset.psend);
    try { b.disabled = true; await POST(`/store/est/subpcs/${r.pc_id}/step`, { step: "Sent to MD" }); await loadPay(); toast("Sent to the Managing Director"); waAsk([{ id: r.pc_id, sub: r.sub, seq: r.seq, payable: r.payable }]); } catch (e) { b.disabled = false; fail(e); } });
  $$("[data-precall]").forEach(b => b.onclick = async () => { try { await POST(`/store/est/subpcs/${b.dataset.precall}/step`, { step: "Sent to MD", undo: true }); await loadPay(); toast("Taken back from the MD"); } catch (e) { fail(e); } });
  $$("[data-pback]").forEach(b => b.onclick = () => { const r = row(b.dataset.pback);
    modal(`Send back - ${r.sub}, PC ${pad(r.seq, 2)}`, [{ k: "note", label: "Why (one line)", focus: true, full: true }, { k: "to", label: "Back to", type: "select", options: [["Prepared", "Contracts manager"], ["Certified", "QS - to prepare again"]], value: "Prepared" }],
      async v => { if (!v.note) throw new Error("Say why it goes back."); await POST(`/store/est/subpcs/${r.pc_id}/step`, { back: true, to: v.to, note: v.note }); await loadPay(); toast("Sent back with your note"); }); });
  $$("[data-pwa]").forEach(b => b.onclick = () => { const r = row(b.dataset.pwa); waShare([{ id: r.pc_id, sub: r.sub, seq: r.seq, payable: r.payable }]); });
  if ($("#wa-all")) $("#wa-all").onclick = () => waShare(d.rows.filter(withMd).map(r => ({ id: r.pc_id, sub: r.sub, seq: r.seq, payable: r.payable })));
  $$("[data-ppay]").forEach(b => b.onclick = () => { const r = row(b.dataset.ppay);
    modal(`Paid - ${r.sub}, PC ${pad(r.seq, 2)}`, [
      { k: "amount", label: "Amount paid (AED)", type: "money", value: r.payable, tip: "Filled in with the amount payable (incl. VAT)." },
      { k: "date", label: "Paid on", type: "date", value: d.today }, { k: "ref", label: "Cheque / transfer ref.", focus: true }],
      async v => { await POST(`/store/est/subpcs/${r.pc_id}/step`, Object.assign({ step: "Paid" }, v)); await loadPay(); toast("Marked paid - Estimation is told"); }); });
  $$("[data-pundo]").forEach(b => b.onclick = async () => { try { await POST(`/store/est/subpcs/${b.dataset.pundo}/step`, { step: "Paid", undo: true }); await loadPay(); toast("Back to pay"); } catch (e) { fail(e); } });
}
function addDays(n, from) { const d = new Date((from || today()) + "T00:00:00"); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }

start();
