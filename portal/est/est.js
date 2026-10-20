/* Estimation > Dashboard / Projects / Tenders.
   One page, three views (?view=dash | projects | tenders), held in a frame by the app.
   Typing is kept to the numbers that cannot be picked: everything else is a pick,
   a click, or filled in from what is already known. */
"use strict";
try { if (!sessionStorage.getItem("infinia_token") && localStorage.getItem("infinia_keep")) sessionStorage.setItem("infinia_token", localStorage.getItem("infinia_keep")); } catch (e) {}
let TOKEN = sessionStorage.getItem("infinia_token") || null;
const VIEW = (location.search.match(/[?&]view=(\w+)/) || [])[1] || "dash";
const ST = { meta: null, pid: null, b: null, group: "subs", sec: "reg", q: {}, filt: {}, dash: null, tenders: null };
if (window.PG_EMBED) document.body.classList.add("embed");

// ---------- small helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
function esc(s) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
function tip(t) { return `<span class="help-i in-label" tabindex="0" data-tip="${esc(t)}">i</span>`; }
function money(v, dash = true) { const n = Number(v || 0); if (!n && dash) return '<span class="muted">-</span>'; return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function m0(v) { const n = Number(v || 0); return n.toLocaleString("en-US", { maximumFractionDigits: 0 }); }
function aed(v) { const n = Number(v || 0); const a = Math.abs(n); return (n < 0 ? "-" : "") + (a >= 1e6 ? (a / 1e6).toFixed(2) + "M" : a >= 1e4 ? (a / 1e3).toFixed(0) + "K" : a.toLocaleString("en-US", { maximumFractionDigits: 0 })); }
function r2(x) { return Math.round((Number(x || 0) + Number.EPSILON) * 100) / 100; }
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dt(s) { if (!s) return ""; const [y, m, d] = s.slice(0, 10).split("-"); return `${+d}-${MON[+m - 1]}-${y.slice(2)}`; }
function today() { return (ST.meta && ST.meta.today) || new Date().toISOString().slice(0, 10); }
function pad(n, w = 3) { return String(n).padStart(w, "0"); }
function h(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }
function st(s) {
  const g = ["Paid", "Approved", "Closed", "Answered", "Won", "Completed", "Current", "Certified", "Approved as noted", "✔"];
  const a = ["Submitted", "At site", "Back from site", "With Accounts", "PC issued", "Pricing", "Invoiced", "Preparing", "Running"];
  const r = ["Rejected", "Lost", "Revise & resubmit", "Cancelled", "Overdue"];
  const b = ["Received", "Open", "Draft", "Identified", "Not started"];
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
$("#lg-go").onclick = doLogin;
$("#lg-p").onkeydown = e => { if (e.key === "Enter") doLogin(); };

// ---------- modal: a form built from a list of fields ----------
// field: {k, label, type: text|money|num|pct|date|select|combo|area|check, options, value, tip, full, hint, quick}
function fieldHtml(f) {
  const v = f.value ?? "";
  const lab = `<label for="f-${f.k}">${esc(f.label)}${f.tip ? " " + tip(f.tip) : ""}</label>`;
  let inp;
  if (f.type === "select") inp = `<select id="f-${f.k}">${(f.options || []).map(o => { const [val, txt] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(val)}" ${String(val) === String(v) ? "selected" : ""}>${esc(txt)}</option>`; }).join("")}</select>`;
  else if (f.type === "combo") inp = `<input id="f-${f.k}" list="dl-${f.k}" value="${esc(v)}" autocomplete="off" placeholder="${esc(f.ph || "Pick or type")}"><datalist id="dl-${f.k}">${(f.options || []).map(o => `<option value="${esc(o)}">`).join("")}</datalist>`;
  else if (f.type === "area") inp = `<textarea id="f-${f.k}" placeholder="${esc(f.ph || "")}">${esc(v)}</textarea>`;
  else if (f.type === "check") inp = `<label class="chk"><input type="checkbox" id="f-${f.k}" ${v ? "checked" : ""}> ${esc(f.text || "")}</label>`;
  else if (f.type === "date") inp = `<input id="f-${f.k}" type="date" value="${esc(v)}">`;
  else if (["money", "num", "pct"].includes(f.type)) inp = `<input id="f-${f.k}" class="money" inputmode="decimal" value="${v === "" || v === null ? "" : esc(v)}" placeholder="${f.type === "pct" ? "%" : "0.00"}">`;
  else inp = `<input id="f-${f.k}" value="${esc(v)}" placeholder="${esc(f.ph || "")}" autocomplete="off">`;
  const q = f.quick ? `<div class="quick">${f.quick.map((x, i) => `<button type="button" data-q="${f.k}:${i}">${esc(x[0])}</button>`).join("")}</div>` : "";
  return `<div class="f ${f.full || f.type === "area" ? "full" : ""}">${lab}${inp}${q}${f.hint ? `<div class="hint">${f.hint}</div>` : ""}</div>`;
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
function modal(title, fields, onSave, opts = {}) {
  $("#m-title").textContent = title;
  $("#m-body").innerHTML = (opts.top || "") + `<div class="frm">${fields.map(fieldHtml).join("")}</div>` + (opts.bottom || "");
  $("#m-foot").innerHTML = (opts.del ? `<button class="btn btn-ghost left" id="m-del">Remove</button>` : "") +
    (opts.extra || "") + `<button class="btn btn-plain" id="m-cancel">Cancel</button><button class="btn btn-primary" id="m-save">${esc(opts.save || "Save")}</button>`;
  $(".mbox").classList.toggle("wide", !!opts.wide);
  $("#modal").classList.remove("hide");
  fields.forEach(f => (f.quick || []).forEach((x, i) => { const b = $(`[data-q="${f.k}:${i}"]`); if (b) b.onclick = () => { x[1]($("#f-" + f.k)); if (opts.live) opts.live(); }; }));
  if (opts.live) { $$("#m-body input, #m-body select").forEach(el => el.addEventListener("input", opts.live)); opts.live(); }
  const first = fields.find(f => f.focus) || fields.find(f => ["money", "num"].includes(f.type) && !f.value) || null;
  setTimeout(() => { const el = first && $("#f-" + first.k); if (el) { el.focus(); el.select && el.select(); } }, 30);
  const save = async () => {
    const btn = $("#m-save"); btn.disabled = true;
    try { await onSave(readForm(fields)); closeModal(); } catch (e) { fail(e); } finally { btn.disabled = false; }
  };
  $("#m-save").onclick = save;
  $("#m-cancel").onclick = closeModal;
  if (opts.del) $("#m-del").onclick = async () => { if (!confirmInline($("#m-del"))) return; try { await opts.del(); closeModal(); } catch (e) { fail(e); } };
  if (opts.after) opts.after();
  $$("#m-body input").forEach(el => el.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } }));
}
// A remove button asks once by changing its words, not with a browser box.
function confirmInline(btn) {
  if (btn.dataset.sure) return true;
  btn.dataset.sure = "1"; const t = btn.textContent; btn.textContent = "Press again to remove"; btn.classList.add("btn-primary");
  setTimeout(() => { if (btn.isConnected) { btn.dataset.sure = ""; btn.textContent = t; btn.classList.remove("btn-primary"); } }, 3500);
  return false;
}
function closeModal() { $("#modal").classList.add("hide"); }
$("#m-x").onclick = closeModal;
$("#modal").addEventListener("mousedown", e => { if (e.target.id === "modal") closeModal(); });
function drawer(title, html) { $("#d-title").innerHTML = title; $("#d-body").innerHTML = html; $("#drawer").classList.remove("hide"); }
function closeDrawer() { $("#drawer").classList.add("hide"); ST.drawer = null; }
$("#d-x").onclick = closeDrawer;
$("#drawer").addEventListener("mousedown", e => { if (e.target.id === "drawer") closeDrawer(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") { if (!$("#modal").classList.contains("hide")) closeModal(); else if (!$("#drawer").classList.contains("hide")) closeDrawer(); } });

// ---------- Preview / PDF / Excel / Share ----------
function xpButtons(what, extra = {}) {
  const k = JSON.stringify({ what, extra }).replace(/"/g, "&quot;");
  return `<span class="xp"><button class="btn btn-plain btn-sm" data-xp="preview" data-k="${k}">Preview</button><button class="btn btn-plain btn-sm" data-xp="pdf" data-k="${k}">PDF</button><button class="btn btn-plain btn-sm" data-xp="excel" data-k="${k}">Excel</button><button class="btn btn-plain btn-sm" data-xp="share" data-k="${k}">Share</button></span>`;
}
async function exportGo(fmt, what, extra) {
  try {
    const t = await POST("/auth/download-token"); const tok = t.token || t.download_token;
    const p = new URLSearchParams(Object.assign({ token: tok, format: fmt === "share" ? "pdf" : fmt }, extra));
    const url = what === "pc" ? `/export/est/pc/${extra.id}?token=${encodeURIComponent(tok)}&format=${fmt === "share" ? "pdf" : fmt}` : `/export/est/${what}?${p}`;
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
    shown = items.filter(x => !q || (x.label + " " + (x.sub || "")).toLowerCase().includes(q) || inp.dataset.picked === inp.value);
    if (inp.dataset.picked === inp.value) shown = items;
    list.innerHTML = shown.length ? shown.map((x, i) => `<div class="opt ${i === cur ? "on" : ""}" data-i="${i}"><b>${esc(x.code)}</b><span>${esc(x.name || "")}</span><small>${esc(x.sub || "")}</small></div>`).join("") : '<div class="none">No project matches</div>';
    list.classList.remove("hide");
  };
  inp.onfocus = () => { inp.select(); cur = -1; draw(); };
  inp.oninput = () => { cur = 0; draw(); };
  inp.onkeydown = e => {
    if (e.key === "ArrowDown") { cur = Math.min(shown.length - 1, cur + 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { cur = Math.max(0, cur - 1); draw(); e.preventDefault(); }
    else if (e.key === "Enter" && shown[Math.max(cur, 0)]) { pick(shown[Math.max(cur, 0)]); }
    else if (e.key === "Escape") { list.classList.add("hide"); inp.blur(); }
  };
  const pick = x => { inp.value = x.code + "  " + (x.name || ""); inp.dataset.picked = inp.value; list.classList.add("hide"); inp.blur(); onPick(x); };
  list.onmousedown = e => { const o = e.target.closest(".opt"); if (o) { e.preventDefault(); pick(shown[+o.dataset.i]); } };
  inp.onblur = () => setTimeout(() => list.classList.add("hide"), 120);
  return { set(x) { if (x) { inp.value = x.code + "  " + (x.name || ""); inp.dataset.picked = inp.value; } } };
}

// ---------- the same money as the server, for the live figures in a form ----------
function chainCalc(pcs, advPct, retPct, vatPct, workKey = "work_cum") {
  let prev = 0, advPaid = 0; const out = [];
  for (const p of pcs) {
    advPaid = r2(advPaid + Number(p.adv_amount || 0));
    const work = r2(p[workKey]), gross = r2(work + Number(p.mos_cum || 0));
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
    if (s[1]) { ST.group = s[1]; ST.sec = s[2]; }
    else { try { const k = localStorage.getItem("est_sec"); if (k) [ST.group, ST.sec] = k.split("."); } catch (e) {} }
    renderProjectShell();
    if (!(pid && ST.meta.projects.some(p => p.id === pid))) pid = (ST.meta.projects.find(p => p.status === "Running") || ST.meta.projects[0] || {}).id;
    if (pid) openProject(pid);   // the first project opens by itself
  } else if (VIEW === "tenders") loadTenders();
  else loadDash();
}
window.addEventListener("message", e => {
  if (e.origin !== location.origin || !e.data) return;
  if (e.data.est === "open" && VIEW === "projects") {
    if (e.data.group) { ST.group = e.data.group; ST.sec = e.data.sec; }
    if (e.data.pid) openProject(+e.data.pid, true); else if (ST.pid) openProject(ST.pid, true);
  }
  if (e.data.est === "refresh") { if (VIEW === "dash") loadDash(); else if (VIEW === "tenders") loadTenders(); else if (ST.pid) openProject(ST.pid, true); }
});
window.pgRefresh = () => { if (VIEW === "dash") loadDash(); else if (VIEW === "tenders") loadTenders(); else if (ST.pid) openProject(ST.pid, true); };
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
  const d = ST.dash, t = d.totals, k = d.kpi;
  const fig = (l, v, s, cls = "", click = "") => `<div class="fig ${cls} ${click ? "click" : ""}" ${click ? `data-go="${click}"` : ""}><div class="l">${l}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`;
  const rows = d.projects;
  app.innerHTML = `<div class="wrap">
    <div class="tools"><b style="font-size:16px">All projects at a glance</b> ${tip("Every figure here is worked out from the projects - nothing is typed on this page. Click a project to open it.")}<span class="spacer"></span>${xpButtons("dash")}</div>
    <div class="strip">
      ${fig("Projects", rows.length, rows.filter(r => r.status === "Running").length + " running")}
      ${fig("Contract value", aed(t.revised), "with approved variations")}
      ${fig("Certified by client", aed(t.client_certified), t.revised ? Math.round(100 * t.client_certified / t.revised) + "% of contract" : "")}
      ${fig("Received", aed(t.received), "from Accounts > Project payments", "green")}
      ${fig("Subcontracts", aed(t.committed), "committed")}
      ${fig("Sub certified", aed(t.sub_certified), aed(t.sub_paid) + " paid")}
      ${fig("Waiting payment", k.with_accounts, aed(k.with_accounts_amount) + " with Accounts", k.with_accounts ? "amber" : "", "subs.pcs")}
      ${fig("Invoices at site", k.at_site, k.site_delays + " late back", k.site_delays ? "red" : "", "subs.inv")}
      ${fig("PCs being prepared", k.preparing, k.pc_delays + " past PC due date", k.pc_delays ? "red" : "", "subs.inv")}
      ${fig("Overdue RFIs / submittals", d.late.length, "", d.late.length ? "red" : "")}
    </div>
    <div class="card"><h3>Projects ${tip("Progress = work certified by the client against the revised contract. Margin = revised contract less subcontracts committed.")}</h3>
      ${rows.length ? `<div class="tw"><table class="t"><thead><tr><th>Project</th><th>Client</th><th>Status</th><th class="r">Contract</th><th class="r">Certified</th><th>Progress</th><th class="r">Received</th><th class="r">Subcontracts</th><th class="r">Sub certified</th><th class="r">Sub to pay</th><th class="r">Margin</th><th class="c">RFIs</th><th class="c">Approvals</th><th class="c">Overdue</th></tr></thead><tbody>
      ${rows.map(r => `<tr class="rowc" data-pid="${r.id}"><td class="nowrap"><b>${esc(r.code)}</b> <span class="muted">${esc(r.name)}</span></td><td>${esc(r.client)}</td><td>${st(r.status)}</td>
        <td class="r">${money(r.revised)}</td><td class="r">${money(r.client_certified)}</td><td><div class="bar"><i style="width:${Math.min(100, r.progress)}%"></i></div><span class="small muted">${r.progress}%</span></td>
        <td class="r">${money(r.received)}</td><td class="r">${money(r.committed)}</td><td class="r">${money(r.sub_certified)}</td><td class="r">${money(r.sub_to_pay)}</td><td class="r ${r.margin < 0 ? "neg" : ""}">${money(r.margin)}</td>
        <td class="c">${r.open_rfi || ""}</td><td class="c small">${r.approvals_total ? r.approvals_done + "/" + r.approvals_total : ""}</td><td class="c ${r.overdue ? "late" : ""}">${r.overdue || ""}</td></tr>`).join("")}
      <tr class="tot"><td>Total</td><td></td><td></td><td class="r">${money(t.revised)}</td><td class="r">${money(t.client_certified)}</td><td></td><td class="r">${money(t.received)}</td><td class="r">${money(t.committed)}</td><td class="r">${money(t.sub_certified)}</td><td class="r">${money(t.sub_to_pay)}</td><td></td><td></td><td></td><td></td></tr>
      </tbody></table></div>` : `<div class="empty">No projects yet.<br><button class="btn btn-primary" onclick="goProject(0)">Add the first project</button></div>`}
    </div>
    <div class="grid2">
      <div class="card"><h3>Subcontractor invoices in hand ${tip("Every invoice not yet paid, oldest PC due date first. Site return is due " + d.rules.site_days + " days after it goes to site; the PC is due " + d.rules.pc_days + " days after the invoice arrives.")}<span class="spacer"></span><span class="small muted">${d.queue.length}</span></h3>
        ${d.queue.length ? `<div class="tw" style="max-height:380px"><table class="t"><thead><tr><th>Project</th><th>Subcontractor</th><th>PC</th><th>Status</th><th>PC due</th><th class="r">Payable</th></tr></thead><tbody>
        ${d.queue.map(x => `<tr class="rowc" data-pid="${x.project_id}" data-sec="subs.inv"><td><b>${esc(x.code)}</b></td><td>${esc(x.sub)}<div class="small muted">${esc(x.scope)}${x.inv_ref ? " · " + esc(x.inv_ref) : ""}</div></td><td>${pad(x.seq, 2)}</td><td>${st(x.status)}${x.site_delay ? `<div class="small late">site ${x.site_delay}d late</div>` : ""}</td><td class="nowrap ${x.pc_delay ? "late" : ""}">${dt(x.pc_due)}${x.pc_delay ? ` (+${x.pc_delay}d)` : ""}</td><td class="r">${money(x.payable)}</td></tr>`).join("")}
        </tbody></table></div>` : '<div class="empty">Nothing in hand.</div>'}
      </div>
      <div class="card"><h3>Overdue RFIs & submittals</h3>
        ${d.late.length ? `<div class="tw" style="max-height:180px"><table class="t"><thead><tr><th>Project</th><th>No.</th><th>Subject</th><th>With</th><th>Due</th></tr></thead><tbody>
        ${d.late.map(x => `<tr class="rowc" data-pid="${x.project_id}" data-sec="site.${x.kind === "rfi" ? "rfi" : "submittal"}"><td><b>${esc(x.code)}</b></td><td class="nowrap">${esc(x.no)}</td><td>${esc(x.title)}</td><td>${esc(x.party)}</td><td class="late nowrap">${dt(x.due)}</td></tr>`).join("")}
        </tbody></table></div>` : '<div class="empty" style="padding:14px">Nothing overdue.</div>'}
        <h3 style="margin-top:14px">Tenders being priced</h3>
        ${d.tenders.length ? `<div class="tw" style="max-height:170px"><table class="t"><thead><tr><th>Tender</th><th>Client</th><th>Due</th><th>Status</th></tr></thead><tbody>
        ${d.tenders.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.client)}</td><td class="nowrap ${x.due && x.due < d.today ? "late" : ""}">${dt(x.due)}</td><td>${st(x.status)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty" style="padding:14px">No open tenders.</div>'}
      </div>
    </div>
    <div class="card"><h3>Finalization - all projects ${tip("The final status of each trade on each project, from each project's finalization log. ✔ finalized, X not yet, C main contractor's scope, E employer's, PS provisional sum. Click a project's column heading to open its log.")}</h3>${finalMatrix(d)}</div>
  </div>`;
  $$("[data-pid]", app).forEach(r => r.onclick = () => { const s = (r.dataset.sec || "").split("."); goProject(+r.dataset.pid, s[0], s[1]); });
  $$("[data-go]", app).forEach(f => f.onclick = () => { const s = f.dataset.go.split("."); const first = rows[0]; if (first) goProject(first.id, s[0], s[1]); });
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
  client: { label: "Client side", secs: [["boq", "BOQ & budget"], ["cpc", "Payment certificates"], ["vo", "Variations"], ["inv", "Invoices"]] },
  subs: { label: "Subcontractors", secs: [["reg", "Subcontract register"], ["inv", "Invoice tracker"], ["pcs", "Payment certificates"], ["final", "Finalization log"]] },
  site: { label: "Site & technical", secs: [["rfi", "RFI log"], ["approval", "NOCs & approvals"], ["submittal", "Submittals"], ["doc", "Documents"]] },
};
function renderProjectShell() {
  $("#app").innerHTML = `<div class="wrap"><div class="pbar"><div id="pick"></div><button class="btn btn-ghost" id="p-new">+ New project</button><button class="btn btn-plain hide" id="p-edit">Project details</button><span class="spacer"></span></div><div id="pbody"></div></div>`;
  const items = ST.meta.projects.map(p => ({ ...p, label: p.code + " " + p.name, sub: [p.client, p.status].filter(Boolean).join(" · ") }));
  ST.combo = combo($("#pick"), items, x => openProject(x.id), "Search a project - code, name or client");
  $("#p-new").onclick = newProject;
  $("#p-edit").onclick = editProject;
  if (!ST.meta.projects.length) $("#pbody").innerHTML = `<div class="card empty">No projects yet. Press <b>+ New project</b> and pick the site - the rest is filled in for you.</div>`;
  else $("#pbody").innerHTML = `<div class="card empty">Pick a project above.<br><span class="small">Type a few letters of the code, name or client.</span></div>`;
}
async function openProject(pid, keep) {
  ST.pid = pid;
  try { localStorage.setItem("est_pid", pid); } catch (e) {}
  const p = ST.meta.projects.find(x => x.id === pid);
  if (p && ST.combo) ST.combo.set(p);
  $("#p-edit").classList.remove("hide");
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
    { k: "client", label: "Client", type: "combo", options: [...new Set(ST.meta.projects.map(p => p.client).filter(Boolean))] },
    { k: "consultant", label: "Consultant", type: "combo", options: [...new Set(ST.meta.projects.map(p => p.consultant).filter(Boolean))] },
    { k: "contract_value", label: "Contract value (AED)", type: "money", tip: "Left empty, it is taken from Accounts > Project payments." },
    { k: "ret_pct", label: "Retention held by client %", type: "pct", value: 10, quick: [["5%", el => el.value = 5], ["10%", el => el.value = 10]] },
    { k: "adv_pct", label: "Advance from client %", type: "pct", value: 0, quick: [["0", el => el.value = 0], ["10%", el => el.value = 10], ["20%", el => el.value = 20]] },
    { k: "qs", label: "QS in charge", type: "combo", options: ST.meta.users.map(u => u.name) },
  ], async v => {
    const r = await POST("/store/est/projects", v);
    ST.meta = await GET("/store/est/meta"); renderProjectShell(); openProject(r.id); toast("Project added");
  }, {
    after: () => {
      const fill = () => { const s = ST.meta.sites.find(x => x.code === $("#f-code").value.trim()); if (s && !$("#f-name").value) $("#f-name").value = s.name; };
      $("#f-code").addEventListener("change", fill); $("#f-code").addEventListener("input", fill);
      $$("[data-site]").forEach(a => a.onclick = e => { e.preventDefault(); $("#f-code").value = a.dataset.site; $("#f-name").value = ""; fill(); });
    }
  });
}
function editProject() {
  const p = ST.b.project;
  modal(`Project ${p.code} - details`, [
    { k: "name", label: "Project name", value: p.name, full: true },
    { k: "client", label: "Client", value: p.client }, { k: "consultant", label: "Consultant", value: p.consultant },
    { k: "location", label: "Location / plot", value: p.location },
    { k: "status", label: "Status", type: "select", options: ["Running", "Tender", "On hold", "Handed over", "Closed"], value: p.status },
    { k: "contract_value", label: "Contract value (AED)", type: "money", value: p.contract_value },
    { k: "ret_pct", label: "Retention %", type: "pct", value: p.ret_pct }, { k: "adv_pct", label: "Advance %", type: "pct", value: p.adv_pct },
    { k: "vat_pct", label: "VAT %", type: "pct", value: p.vat_pct },
    { k: "start_date", label: "Start", type: "date", value: p.start_date }, { k: "end_date", label: "Completion", type: "date", value: p.end_date },
    { k: "qs", label: "QS in charge", type: "combo", options: ST.meta.users.map(u => u.name), value: p.qs },
    { k: "notes", label: "Notes", type: "area", value: p.notes },
  ], async v => { await PATCH(`/store/est/projects/${p.id}`, v); ST.meta = await GET("/store/est/meta"); reload(); toast("Saved"); },
  { del: ST.meta.me.admin ? async () => { await DEL(`/store/est/projects/${p.id}`); ST.meta = await GET("/store/est/meta"); ST.pid = null; try { localStorage.removeItem("est_pid"); } catch (e) {} renderProjectShell(); } : null });
}
function renderProject() {
  const b = ST.b, s = b.summary;
  const fig = (l, v, sub, cls = "") => `<div class="fig ${cls}"><div class="l">${l}</div><div class="v">${v}</div>${sub ? `<div class="s">${sub}</div>` : ""}</div>`;
  const count = { "subs.reg": b.subs.length, "subs.inv": b.subs.reduce((n, x) => n + x.pcs.filter(p => p.status !== "Paid").length, 0),
                  "subs.pcs": b.subs.reduce((n, x) => n + x.pcs.filter(p => p.status === "With Accounts").length, 0),
                  "client.cpc": b.clientpcs.length, "client.vo": b.variations.length, "client.inv": b.invoices.length, "client.boq": b.boq.length,
                  "site.rfi": s.open_rfi, "site.submittal": s.open_submittals, "site.doc": b.files.length,
                  "site.approval": s.approvals_total ? `${s.approvals_done}/${s.approvals_total}` : 0, "subs.final": s.finals_total ? `${s.finals_done}/${s.finals_total}` : 0 };
  if (!GROUPS[ST.group] || !GROUPS[ST.group].secs.some(x => x[0] === ST.sec)) { ST.group = "subs"; ST.sec = "reg"; }
  $("#pbody").innerHTML = `
    <div class="strip">
      ${fig("Contract", aed(s.revised), s.approved_vo ? `incl. VOs ${aed(s.approved_vo)}` : "revised")}
      ${fig("Certified by client", aed(s.client_certified), s.revised ? Math.round(100 * s.client_work / s.revised) + "% done" : "")}
      ${fig("Received", aed(s.received), "Accounts", "green")}
      ${fig("Subcontracts", aed(s.committed), b.subs.length + " subcontractors")}
      ${fig("Sub certified", aed(s.sub_certified), aed(s.sub_paid) + " paid")}
      ${fig("Sub to pay", aed(s.sub_to_pay), "certified, not paid", s.sub_to_pay > 0 ? "amber" : "")}
      ${fig("Margin", aed(s.margin), "contract - subcontracts", s.margin < 0 ? "red" : "")}
      ${fig("Overdue", s.overdue, "RFIs / submittals", s.overdue ? "red" : "")}
    </div>
    <div class="groups">${Object.entries(GROUPS).map(([k, g]) => `<div class="group ${k === ST.group ? "on" : ""}" data-g="${k}">${g.label}</div>`).join("")}</div>
    <div class="subtabs">${GROUPS[ST.group].secs.map(([k, l]) => { const n = count[ST.group + "." + k]; return `<div class="tab ${k === ST.sec ? "on" : ""}" data-s="${k}">${l}${n ? `<span class="n">${n}</span>` : ""}</div>`; }).join("")}</div>
    <div class="panel" id="sec"></div>`;
  $$("[data-g]").forEach(x => x.onclick = () => { ST.group = x.dataset.g; ST.sec = GROUPS[ST.group].secs[0][0]; saveSec(); renderProject(); });
  $$("[data-s]").forEach(x => x.onclick = () => { ST.sec = x.dataset.s; saveSec(); renderProject(); });
  const fn = SECTIONS[ST.group + "." + ST.sec];
  try { fn($("#sec")); } catch (e) { console.error(e); $("#sec").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
function saveSec() { try { localStorage.setItem("est_sec", ST.group + "." + ST.sec); } catch (e) {} }
function key() { return ST.group + "." + ST.sec; }
function tools(what, opts = {}) {
  const k = key(), q = ST.q[k] || "", f = ST.filt[k] || "";
  return `<div class="tools">${opts.add || ""}<input class="q" placeholder="Search" value="${esc(q)}" data-q>${opts.chips ? `<div class="chips">${opts.chips.map(([v, n]) => `<span class="chip ${f === v ? "on" : ""}" data-f="${esc(v)}">${esc(v || "All")}${n !== undefined ? `<span class="n">${n}</span>` : ""}</span>`).join("")}</div>` : ""}<span class="spacer"></span>${opts.right || ""}${what ? xpButtons(what, Object.assign({ pid: ST.pid, q, status: f }, opts.xp || {})) : ""}</div>`;
}
function bindTools(el, redraw) {
  const k = key();
  const qi = $("[data-q]", el); if (qi) qi.oninput = debounce(() => { ST.q[k] = qi.value; redraw(); setTimeout(() => { const n = $("[data-q]", el); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }, 0); }, 250);
  $$("[data-f]", el).forEach(c => c.onclick = () => { ST.filt[k] = ST.filt[k] === c.dataset.f ? "" : c.dataset.f; redraw(); });
}
function match(row) { const q = (ST.q[key()] || "").toLowerCase(); return !q || JSON.stringify(row).toLowerCase().includes(q); }
function filt() { return ST.filt[key()] || ""; }

const SECTIONS = {};

// ---------------- Subcontractors > register ----------------
SECTIONS["subs.reg"] = el => {
  const b = ST.b, f = filt();
  const subs = b.subs.filter(s => (!f || s.status === f) && match(s));
  const stc = s => b.subs.filter(x => x.status === s).length;
  const tot = k => r2(subs.reduce((n, s) => n + s[k], 0));
  el.innerHTML = tools("subs", { add: `<button class="btn btn-primary" id="add-sub">+ Subcontract / LPO</button>`, chips: [["", b.subs.length], ["Active", stc("Active")], ["Completed", stc("Completed")], ["Closed", stc("Closed")], ["Cancelled", stc("Cancelled")]] }) +
    (subs.length ? `<div class="tw"><table class="t"><thead><tr><th>#</th><th>Subcontractor</th><th>Work</th><th>Agreement / LPO</th><th class="r">Value</th><th class="r">VOs</th><th class="r">Revised</th><th>Done</th><th class="r">Certified</th><th class="r">Paid</th><th class="r">To pay</th><th class="r">Retention held</th><th class="c">PCs</th><th>Status</th></tr></thead><tbody>
    ${subs.map((s, i) => `<tr class="rowc" data-sub="${s.id}"><td class="muted">${i + 1}</td><td><b>${esc(s.name)}</b><div class="small muted">${esc(s.kind)} · ${esc(s.trade)}</div></td><td>${esc(s.scope)}</td><td class="small">${esc([s.agreement, s.lpo].filter(Boolean).join(" / "))}</td>
      <td class="r">${money(s.value)}</td><td class="r">${money(s.vo_total)}</td><td class="r"><b>${money(s.revised)}</b></td><td><div class="bar ${s.done_pct > 100 ? "over" : ""}"><i style="width:${Math.min(100, s.done_pct)}%"></i></div><span class="small muted">${s.done_pct}%</span></td>
      <td class="r">${money(s.certified)}</td><td class="r">${money(s.paid)}</td><td class="r ${s.to_pay > 0.005 ? "late" : ""}">${money(s.to_pay)}</td><td class="r">${money(s.ret_left)}</td><td class="c">${s.pc_count}</td><td>${st(s.status)}</td></tr>`).join("")}
    <tr class="tot"><td></td><td>Total</td><td></td><td></td><td class="r">${money(tot("value"))}</td><td class="r">${money(tot("vo_total"))}</td><td class="r">${money(tot("revised"))}</td><td></td><td class="r">${money(tot("certified"))}</td><td class="r">${money(tot("paid"))}</td><td class="r">${money(tot("to_pay"))}</td><td class="r">${money(tot("ret_left"))}</td><td></td><td></td></tr>
    </tbody></table></div>` : `<div class="empty">No subcontracts${f ? " with this status" : ""} yet.<br><button class="btn btn-primary" onclick="subForm()">+ Add the first subcontract</button></div>`);
  bindTools(el, () => SECTIONS["subs.reg"](el));
  const a = $("#add-sub", el); if (a) a.onclick = () => subForm();
  $$("[data-sub]", el).forEach(r => r.onclick = () => openSub(+r.dataset.sub));
};
function subForm(s) {
  const m = ST.meta, edit = !!s; s = s || {};
  const names = [...new Set([...m.suppliers.map(x => x.name), ...m.sub_names])];
  modal(edit ? "Subcontract - " + s.name : "New subcontract / LPO", [
    { k: "name", label: "Subcontractor", type: "combo", options: names, value: s.name || "", full: true, focus: !edit, ph: "Start typing - suppliers from Store & Purchasing", tip: "The list is every supplier in Store & Purchasing. A new name can be typed." },
    { k: "scope", label: "Work", type: "combo", options: m.scopes, value: s.scope || "" },
    { k: "trade", label: "Trade", type: "select", options: m.trades, value: s.trade || "Civil" },
    { k: "kind", label: "Type", type: "select", options: ["Subcontract", "LPO", "Manpower"], value: s.kind || "Subcontract" },
    { k: "status", label: "Status", type: "select", options: ["Active", "Completed", "Closed", "Cancelled"], value: s.status || "Active" },
    { k: "agreement", label: "Agreement no.", value: s.agreement || "", ph: `IC/${ST.b.project.code}/SCA/01/26` },
    { k: "lpo", label: "LPO no.", value: s.lpo || "" },
    { k: "value", label: "Subcontract / LPO amount (AED)", type: "money", value: s.value ?? "", tip: "Before VAT. Variations are added later on the subcontract." },
    { k: "cancelled", label: "LPO cancellation (AED)", type: "money", value: s.cancelled || "" },
    { k: "adv_pct", label: "Advance %", type: "pct", value: s.adv_pct ?? 0, quick: [["0", el => el.value = 0], ["10%", el => el.value = 10], ["20%", el => el.value = 20]], tip: "Recovered from each certificate by the same % of the work done, until it is all back." },
    { k: "ret_pct", label: "Retention %", type: "pct", value: s.ret_pct ?? 0, quick: [["0", el => el.value = 0], ["5%", el => el.value = 5], ["10%", el => el.value = 10]] },
    { k: "vat_pct", label: "VAT %", type: "pct", value: s.vat_pct ?? 5, quick: [["5%", el => el.value = 5], ["0", el => el.value = 0]] },
    { k: "start_date", label: "Start date", type: "date", value: s.start_date || today() },
    { k: "notes", label: "Notes", type: "area", value: s.notes || "" },
  ], async v => {
    const sup = m.suppliers.find(x => x.name.toLowerCase() === v.name.toLowerCase());
    if (sup) v.supplier_id = sup.id;
    if (edit) await PATCH(`/store/est/subs/${s.id}`, v); else { v.project_id = ST.pid; const r = await POST("/store/est/subs", v); ST.openAfter = r.id; }
    await reload(); toast(edit ? "Saved" : "Subcontract added");
    if (ST.openAfter) { openSub(ST.openAfter); ST.openAfter = null; }
  }, { del: edit ? async () => { await DEL(`/store/est/subs/${s.id}`); closeDrawer(); reload(); toast("Removed"); } : null, wide: true });
}
// The subcontract's own page: its figures, variations and every certificate (the Excel sheet per subcontractor).
function openSub(sid) {
  ST.drawer = () => {
    const s = ST.b.subs.find(x => x.id === sid); if (!s) { closeDrawer(); return; }
    const fig = (l, v, cls = "") => `<div class="fig ${cls}"><div class="l">${l}</div><div class="v">${v}</div></div>`;
    drawer(`${esc(s.name)} <span class="muted small">${esc(s.scope)}</span>`, `
      <div class="tools"><button class="btn btn-primary" id="s-inv">+ Invoice received</button><button class="btn btn-ghost" id="s-adv" ${s.adv_pct ? "" : "disabled"} title="${s.adv_pct ? "" : "No advance % on this subcontract"}">+ Advance PC</button><button class="btn btn-plain" id="s-vo">+ Variation</button><button class="btn btn-plain" id="s-edit">Edit subcontract</button><span class="spacer"></span>${xpButtons("subpcs", { pid: ST.pid, sub_id: s.id, name: s.name })}</div>
      <div class="strip">
        ${fig("Value", money(s.value, false))}${fig("Variations", money(s.vo_total, false))}${fig("Revised", money(s.revised, false))}
        ${fig("Work done", money(s.work_done, false) + `<div class="s">${s.done_pct}%</div>`)}${fig("Certified", money(s.certified, false))}${fig("Paid", money(s.paid, false), "green")}
        ${fig("To pay", money(s.to_pay, false), s.to_pay > 0.005 ? "amber" : "")}${fig("Advance left", money(s.adv_left, false))}${fig("Retention held", money(s.ret_left, false))}${fig("Balance work", money(s.balance, false), s.balance < 0 ? "red" : "")}
      </div>
      <div class="card"><h3>Payment certificates ${tip("Figures to date. 'This PC' = net to date now less net to date at the last PC, so the certificates always add up to the total. Click a row to certify or change it.")}</h3>
      ${s.pcs.length ? `<div class="tw"><table class="t"><thead><tr><th>PC</th><th>Invoice</th><th class="r">Inv. amount</th><th class="r">Work done to date</th><th class="r">Adv. recovery</th><th class="r">Retention</th><th class="r">Other ded.</th><th class="r">Ret. release</th><th class="r">Net to date</th><th class="r">This PC</th><th class="r">Payable</th><th class="r">Paid</th><th>Status</th><th></th></tr></thead><tbody>
      ${s.pcs.map(p => `<tr class="rowc" data-pc="${p.id}"><td class="nowrap"><b>PC ${pad(p.seq, 2)}</b>${p.pc_type !== "Interim" ? `<div class="small muted">${esc(p.pc_type)}</div>` : ""}</td><td class="small">${esc(p.inv_ref)}<div class="muted">${dt(p.inv_date || p.received)}</div></td><td class="r">${money(p.inv_amount)}</td>
        <td class="r">${money(p.work_cum)}${p.adv_amount ? `<div class="small muted">adv. ${money(p.adv_amount)}</div>` : ""}</td><td class="r neg">${p.adv_rec_cum ? "-" + money(p.adv_rec_cum) : money(0)}</td><td class="r neg">${p.ret_cum ? "-" + money(p.ret_cum) : money(0)}</td><td class="r neg">${p.other_cum ? "-" + money(p.other_cum) : money(0)}</td><td class="r">${money(p.ret_rel_cum)}</td>
        <td class="r">${money(p.net_cum)}</td><td class="r"><b>${money(p.this, false)}</b></td><td class="r">${money(p.payable, false)}</td><td class="r">${money(p.paid_amount)}</td><td>${st(p.status)}</td>
        <td class="nowrap"><button class="btn btn-plain btn-sm" data-print="${p.id}">Print</button></td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">No certificates yet. Press <b>+ Invoice received</b> when the first invoice comes in.</div>`}</div>
      <div class="card"><h3>Variations to this subcontract</h3>
      ${s.vos.length ? `<div class="tw"><table class="t"><thead><tr><th>Date</th><th>Ref.</th><th>Description</th><th class="r">Amount</th></tr></thead><tbody>${s.vos.map(v => `<tr class="rowc" data-vo="${v.id}"><td>${dt(v.on_date)}</td><td>${esc(v.ref)}</td><td>${esc(v.title)}</td><td class="r">${money(v.amount, false)}</td></tr>`).join("")}<tr class="tot"><td colspan="3">Total</td><td class="r">${money(s.vo_total, false)}</td></tr></tbody></table></div>` : '<div class="muted small">None.</div>'}</div>
      <div class="card"><h3>Details</h3><div class="small">${esc(s.kind)} · ${esc(s.trade)} · Agreement ${esc(s.agreement || "-")} · LPO ${esc(s.lpo || "-")} · Advance ${s.adv_pct}% · Retention ${s.ret_pct}% · VAT ${s.vat_pct}%${s.notes ? "<br>" + esc(s.notes) : ""}</div></div>`);
    $("#s-inv").onclick = () => invoiceForm(s.id);
    $("#s-adv").onclick = async () => { try { await POST("/store/est/subpcs", { sub_id: s.id, pc_type: "Advance", inv_ref: "Advance" }); await reload(); toast("Advance PC made - " + s.adv_pct + "% of the value"); } catch (e) { fail(e); } };
    $("#s-vo").onclick = () => voSubForm(s);
    $("#s-edit").onclick = () => subForm(s);
    $$("[data-pc]").forEach(r => r.onclick = e => { if (e.target.closest("[data-print]")) return; certifyForm(s.id, +r.dataset.pc); });
    $$("[data-print]").forEach(b => b.onclick = () => exportGo("preview", "pc", { id: +b.dataset.print }));
    $$("[data-vo]").forEach(r => r.onclick = () => voSubForm(s, s.vos.find(v => v.id === +r.dataset.vo)));
  };
  ST.drawer();
}
function voSubForm(s, v) {
  v = v || {};
  modal(v.id ? "Variation" : "Variation to " + s.name, [
    { k: "title", label: "Description", value: v.title || "", full: true, focus: true },
    { k: "amount", label: "Amount (AED)", type: "money", value: v.amount ?? "", tip: "Negative for an omission." },
    { k: "on_date", label: "Date", type: "date", value: v.on_date || today() }, { k: "ref", label: "Ref.", value: v.ref || "" },
  ], async x => { if (v.id) await PATCH(`/store/est/subvos/${v.id}`, x); else await POST("/store/est/subvos", Object.assign(x, { sub_id: s.id })); await reload(); toast("Saved"); },
  { del: v.id ? async () => { await DEL(`/store/est/subvos/${v.id}`); reload(); } : null });
}
// Invoice received: the first step. Only the reference and amount are typed.
function invoiceForm(sid) {
  const subs = ST.b.subs.filter(x => x.status !== "Cancelled");
  if (!subs.length) { toast("Add the subcontract first", { err: true }); return; }
  modal("Invoice received", [
    { k: "sub_id", label: "Subcontractor", type: "select", options: subs.map(x => [x.id, `${x.name} - ${x.scope}`]), value: sid || subs[0].id, full: true },
    { k: "inv_ref", label: "Invoice no.", focus: true }, { k: "inv_amount", label: "Invoice amount (AED)", type: "money" },
    { k: "inv_date", label: "Invoice date", type: "date", value: today() }, { k: "received", label: "Received in office", type: "date", value: today() },
    { k: "to_site", label: "Sent to site for checking", type: "check", value: true, text: "Send to site today" },
  ], async v => {
    const send = v.to_site; delete v.to_site;
    const r = await POST("/store/est/subpcs", v);
    if (send) await POST(`/store/est/subpcs/${r.id}/step`, { step: "At site" });
    await reload(); toast(send ? "Invoice logged and sent to site" : "Invoice logged");
  });
}
// Certify: the one number to type is the work done to date.
function certifyForm(sid, pcid) {
  const s = ST.b.subs.find(x => x.id === sid), p = s.pcs.find(x => x.id === pcid);
  const idx = s.pcs.indexOf(p), prev = s.pcs[idx - 1] || null;
  const locked = p.status === "Paid" && !ST.meta.me.admin;
  const fields = [
    { k: "work_cum", label: "Value of work done to date (AED)", type: "money", value: p.work_cum, focus: true, tip: "Everything done up to now, not just this month. The earlier PCs are taken off automatically.",
      quick: [["Same as last", el => el.value = prev ? prev.work_cum : 0], ...[25, 50, 75, 90, 100].map(n => [n + "%", el => el.value = r2(s.revised * n / 100)])],
      hint: `Revised value ${money(s.revised, false)}${prev ? ` · last PC ${money(prev.work_cum, false)}` : ""}` },
    { k: "mos_cum", label: "Material on site to date", type: "money", value: p.mos_cum || "" },
    { k: "other_cum", label: "Other deductions to date", type: "money", value: p.other_cum || "", tip: "Back-charges, manpower supplied by us, damages ... to date." },
    { k: "other_note", label: "Deduction reason", type: "combo", value: p.other_note, options: ["Manpower supplied by main contractor", "Back-charge", "Material supplied", "Damages", "Rectification"] },
    { k: "adv_rec_cum", label: `Advance recovered to date ${s.adv_pct ? "(" + s.adv_pct + "%)" : ""}`, type: "money", value: p.adv_rec_cum || "" },
    { k: "adv_auto", label: " ", type: "check", value: p.adv_auto, text: "Work it out from the %" },
    { k: "ret_cum", label: `Retention to date ${s.ret_pct ? "(" + s.ret_pct + "%)" : ""}`, type: "money", value: p.ret_cum || "" },
    { k: "ret_auto", label: " ", type: "check", value: p.ret_auto, text: "Work it out from the %" },
    { k: "ret_rel_cum", label: "Retention released to date", type: "money", value: p.ret_rel_cum || "", quick: [["Release half", el => el.value = r2(Number($("#f-ret_cum").value || 0) / 2)], ["Release all", el => el.value = $("#f-ret_cum").value || 0], ["None", el => el.value = 0]] },
    { k: "adv_amount", label: "Advance paid on this PC", type: "money", value: p.adv_amount || "" },
    { k: "pc_type", label: "Type", type: "select", options: ["Interim", "Advance", "Final", "Retention release"], value: p.pc_type || "Interim" },
    { k: "inv_ref", label: "Invoice no.", value: p.inv_ref }, { k: "inv_amount", label: "Invoice amount", type: "money", value: p.inv_amount || "" },
    { k: "remarks", label: "Remarks", type: "area", value: p.remarks },
  ];
  const live = () => {
    const v = readForm(fields);
    const n = x => Number(String(x || 0).replace(/,/g, "")) || 0;
    const advPaidBefore = prev ? prev.adv_paid_cum : 0, advPaid = advPaidBefore + n(v.adv_amount), work = n(v.work_cum);
    if (v.adv_auto) { const pct = s.adv_pct || (s.revised ? 100 * advPaid / s.revised : 0); const a = pct ? Math.min(advPaid, work * pct / 100) : Math.min(advPaid, n(v.adv_rec_cum)); $("#f-adv_rec_cum").value = r2(a); }
    if (v.ret_auto) $("#f-ret_cum").value = r2(work * s.ret_pct / 100);
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
    if (["Received", "At site", "Back from site"].includes(p.status) && Number(v.work_cum || 0) > 0) await POST(`/store/est/subpcs/${p.id}/step`, { step: "Certified" });
    await reload(); toast("Certificate saved");
  }, { wide: true, live, top: '<div class="calc" id="calc" style="margin:0 0 12px"></div>', save: locked ? "Locked (paid)" : "Save certificate",
       extra: `<button class="btn btn-plain" id="m-print">Print PC</button>`,
       del: p.status !== "Paid" ? async () => { await DEL(`/store/est/subpcs/${p.id}`); reload(); toast("Removed"); } : null,
       after: () => { $("#m-print").onclick = () => exportGo("preview", "pc", { id: p.id }); if (locked) $("#m-save").disabled = true; } });
}

// ---------------- Subcontractors > invoice tracker ----------------
const STEPS = ["Received", "At site", "Back from site", "Certified", "PC issued", "With Accounts", "Paid"];
const NEXT = { "Received": "At site", "At site": "Back from site", "Back from site": "Certified", "Certified": "PC issued", "PC issued": "With Accounts", "With Accounts": "Paid" };
const NEXT_LABEL = { "At site": "Sent to site", "Back from site": "Back from site", "Certified": "Certify", "PC issued": "PC issued", "With Accounts": "Send to Accounts", "Paid": "Mark paid" };
function allPcs() { return ST.b.subs.flatMap(s => s.pcs.map(p => Object.assign({ sub: s }, p))); }
SECTIONS["subs.inv"] = el => {
  const f = filt(), all = allPcs();
  const list = all.filter(p => (!f || p.status === f) && match({ a: p.sub.name, b: p.inv_ref, c: p.status, d: p.sub.scope })).sort((a, b) => (a.status === "Paid") - (b.status === "Paid") || (a.pc_due || "").localeCompare(b.pc_due || ""));
  const n = s => all.filter(p => p.status === s).length;
  const r = ST.b.rules;
  el.innerHTML = tools("invoices", { add: `<button class="btn btn-primary" id="add-inv">+ Invoice received</button>`, chips: [["", all.length], ...STEPS.map(s => [s, n(s)])],
      right: `<button class="btn btn-plain btn-sm" id="rules">Days: site ${r.site_days} · PC ${r.pc_days}</button>` }) +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>Subcontractor</th><th>PC</th><th>Invoice</th><th class="r">Amount</th><th>Received</th><th>Site</th><th>PC due</th><th>Progress</th><th>Status</th><th class="r">Payable</th><th>Next step</th></tr></thead><tbody>
    ${list.map(p => { const i = STEPS.indexOf(p.status), nx = NEXT[p.status];
      return `<tr><td><b>${esc(p.sub.name)}</b><div class="small muted">${esc(p.sub.scope)}</div></td><td class="nowrap">PC ${pad(p.seq, 2)}</td><td class="small">${esc(p.inv_ref)}</td><td class="r">${money(p.inv_amount)}</td><td class="nowrap">${dt(p.received)}</td>
      <td class="small nowrap">${p.to_site ? "out " + dt(p.to_site) : ""}${p.site_back ? "<br>back " + dt(p.site_back) : p.to_site ? `<br><span class="${p.site_delay ? "late" : "muted"}">due ${dt(p.site_due)}</span>` : ""}${p.site_delay ? `<div class="late">${p.site_delay}d late</div>` : ""}</td>
      <td class="nowrap ${p.pc_delay ? "late" : ""}">${dt(p.pc_due)}${p.issued ? `<div class="small muted">issued ${dt(p.issued)}</div>` : ""}${p.pc_delay ? `<div class="small">${p.pc_delay}d late</div>` : ""}</td>
      <td><span class="flow">${STEPS.map((s, j) => `<i class="${j < i ? "on" : j === i ? (p.status === "Paid" ? "on" : "cur") : ""}" title="${s}"></i>`).join("")}</span></td><td>${st(p.status)}</td>
      <td class="r">${p.work_cum || p.adv_amount ? money(p.payable, false) : '<span class="muted">-</span>'}</td>
      <td class="nowrap">${nx ? `<button class="btn ${nx === "Paid" ? "btn-ok" : "btn-ghost"} btn-sm" data-next="${p.id}" data-sub="${p.sub.id}" data-to="${nx}">${NEXT_LABEL[nx]}</button>` : ""}${i > 0 ? ` <button class="btn btn-plain btn-sm" data-undo="${p.id}" data-st="${p.status}" title="Back one step">&#8630;</button>` : ""} <button class="btn btn-plain btn-sm" data-open="${p.id}" data-sub="${p.sub.id}">Open</button></td></tr>`; }).join("")}
    </tbody></table></div>` : `<div class="empty">No invoices${f ? " at this step" : ""}.</div>`);
  bindTools(el, () => SECTIONS["subs.inv"](el));
  $("#add-inv", el).onclick = () => invoiceForm();
  $("#rules", el).onclick = rulesForm;
  $$("[data-next]", el).forEach(b => b.onclick = () => step(+b.dataset.next, b.dataset.to, +b.dataset.sub));
  $$("[data-undo]", el).forEach(b => b.onclick = async () => { try { await POST(`/store/est/subpcs/${b.dataset.undo}/step`, { step: b.dataset.st, undo: true }); await reload(); toast("Moved back one step"); } catch (e) { fail(e); } });
  $$("[data-open]", el).forEach(b => b.onclick = () => certifyForm(+b.dataset.sub, +b.dataset.open));
};
async function step(pcid, to, sid) {
  if (to === "Certified") { certifyForm(sid, pcid); return; }
  if (to === "Paid") { payForm(sid, pcid); return; }
  try {
    await POST(`/store/est/subpcs/${pcid}/step`, { step: to }); await reload();
    toast(`${NEXT_LABEL[to] || to} - ${dt(today())}`, { undo: async () => { await POST(`/store/est/subpcs/${pcid}/step`, { step: to, undo: true }); reload(); } });
  } catch (e) { fail(e); }
}
function payForm(sid, pcid) {
  const s = ST.b.subs.find(x => x.id === sid), p = s.pcs.find(x => x.id === pcid);
  modal(`Paid - PC ${pad(p.seq, 2)} ${s.name}`, [
    { k: "amount", label: "Amount paid (AED)", type: "money", value: p.payable, tip: "Filled in with the amount payable (incl. VAT)." },
    { k: "date", label: "Paid on", type: "date", value: today() },
    { k: "ref", label: "Cheque / transfer ref.", focus: true },
  ], async v => { await POST(`/store/est/subpcs/${pcid}/step`, Object.assign({ step: "Paid" }, v)); await reload(); toast("Marked paid"); });
}
function rulesForm() {
  const r = ST.b.rules;
  modal("Days allowed", [
    { k: "site_days", label: "Site to check an invoice (days)", type: "num", value: r.site_days },
    { k: "pc_days", label: "PC to be issued after the invoice arrives (days)", type: "num", value: r.pc_days },
    { k: "rfi_days", label: "Reply to an RFI (days)", type: "num", value: r.rfi_days },
    { k: "submittal_days", label: "Reply to a submittal (days)", type: "num", value: r.submittal_days },
  ], async v => { await PUT("/store/est/rules", v); await reload(); toast("Saved - delays recounted"); });
}

// ---------------- Subcontractors > payment certificates (to Accounts) ----------------
SECTIONS["subs.pcs"] = el => {
  const f = filt() || "", all = allPcs().filter(p => ["Certified", "PC issued", "With Accounts", "Paid"].includes(p.status));
  const list = all.filter(p => (!f || p.status === f) && match({ a: p.sub.name, b: p.inv_ref, c: p.status }));
  const n = s => all.filter(p => p.status === s).length;
  const tot = k => r2(list.reduce((a, p) => a + (p[k] || 0), 0));
  el.innerHTML = tools("invoices", { chips: [["", all.length], ["Certified", n("Certified")], ["PC issued", n("PC issued")], ["With Accounts", n("With Accounts")], ["Paid", n("Paid")]],
      add: `<span class="muted small">Certified PCs go to Accounts from here; Accounts marks them paid ${tip("Accounts staff with the Bank right can mark a certificate paid and print it, without seeing the rest of Estimation.")}</span>` }) +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>Subcontractor</th><th>PC</th><th class="r">This PC</th><th class="r">VAT</th><th class="r">Payable</th><th>Issued</th><th>To Accounts</th><th>Paid</th><th class="r">Paid amount</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map(p => `<tr><td><b>${esc(p.sub.name)}</b><div class="small muted">${esc(p.sub.scope)}</div></td><td class="nowrap">PC ${pad(p.seq, 2)}${p.pc_type !== "Interim" ? ` <span class="small muted">${esc(p.pc_type)}</span>` : ""}</td><td class="r">${money(p.this, false)}</td><td class="r">${money(p.vat)}</td><td class="r"><b>${money(p.payable, false)}</b></td>
      <td>${dt(p.issued)}</td><td>${dt(p.to_accounts)}</td><td>${dt(p.paid_on)}<div class="small muted">${esc(p.paid_ref)}</div></td><td class="r">${money(p.paid_amount)}</td><td>${st(p.status)}</td>
      <td class="nowrap"><button class="btn btn-plain btn-sm" data-print="${p.id}">Print</button> ${p.status === "Certified" ? `<button class="btn btn-ghost btn-sm" data-next="${p.id}" data-sub="${p.sub.id}" data-to="PC issued">PC issued</button>` : p.status === "PC issued" ? `<button class="btn btn-ghost btn-sm" data-next="${p.id}" data-sub="${p.sub.id}" data-to="With Accounts">Send to Accounts</button>` : p.status === "With Accounts" ? `<button class="btn btn-ok btn-sm" data-next="${p.id}" data-sub="${p.sub.id}" data-to="Paid">Mark paid</button>` : ""}</td></tr>`).join("")}
    <tr class="tot"><td>Total</td><td></td><td class="r">${money(tot("this"))}</td><td class="r">${money(tot("vat"))}</td><td class="r">${money(tot("payable"))}</td><td></td><td></td><td></td><td class="r">${money(tot("paid_amount"))}</td><td></td><td></td></tr>
    </tbody></table></div>` : '<div class="empty">No certificates here yet. They appear once an invoice is certified.</div>');
  bindTools(el, () => SECTIONS["subs.pcs"](el));
  $$("[data-print]", el).forEach(b => b.onclick = () => exportGo("preview", "pc", { id: +b.dataset.print }));
  $$("[data-next]", el).forEach(b => b.onclick = () => step(+b.dataset.next, b.dataset.to, +b.dataset.sub));
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
  html += `<div class="tw"><table class="t fg"><thead><tr><th>Item</th>${FCOLS.map(c => `<th class="c">${c[1]}</th>`).join("")}<th>Subcontractor</th></tr></thead><tbody>`;
  let sec = "";
  for (const x of rows) {
    if (x.section !== sec) { sec = x.section; html += `<tr class="sec"><td colspan="${FCOLS.length + 2}">${esc(sec)}</td></tr>`; }
    html += `<tr><td>${esc(x.item)}</td>${FCOLS.map(c => `<td class="cell ${cls(x[c[0]])}" data-fc="${x.id}:${c[0]}">${esc(x[c[0]] || "")}</td>`).join("")}<td><select data-fsub="${x.id}" style="max-width:220px;border:1px solid #E0DCD6;border-radius:6px;height:28px"><option value="">-</option>${b.subs.map(s => `<option value="${s.id}" ${s.id === x.sub_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></td></tr>`;
  }
  el.innerHTML = html + "</tbody></table></div>";
  bindTools(el, () => SECTIONS["subs.final"](el));
  $$("[data-fc]", el).forEach(td => td.onclick = async () => {
    const [id, k] = td.dataset.fc.split(":"); const col = FCOLS.find(c => c[0] === k)[2]; const row = b.finals.find(x => x.id === +id);
    const nv = col[(col.indexOf(row[k] || "") + 1) % col.length];
    row[k] = nv; td.textContent = nv; td.className = "cell " + cls(nv);
    try { await PATCH(`/store/est/finals/${id}`, { [k]: nv }); } catch (e) { fail(e); }
  });
  $$("[data-fsub]", el).forEach(s => s.onchange = async () => { try { await PATCH(`/store/est/finals/${s.dataset.fsub}`, { sub_id: s.value || null }); b.finals.find(x => x.id === +s.dataset.fsub).sub_id = +s.value || null; toast("Saved"); } catch (e) { fail(e); } });
  $("#add-final", el).onclick = () => modal("Finalization item", [
    { k: "section", label: "Section", type: "select", options: ["CIVIL", "MEP", "EXTERNAL", "OTHER"] }, { k: "item", label: "Item", focus: true }],
    async v => { await POST("/store/est/finals", Object.assign(v, { project_id: ST.pid })); reload(); });
};

// ---------------- Client side > BOQ & budget ----------------
SECTIONS["client.boq"] = el => {
  const b = ST.b, rows = b.boq.filter(match);
  const tot = rows.reduce((a, x) => a + x.amount, 0), cost = rows.reduce((a, x) => a + x.cost, 0);
  let html = tools("boq", { add: `<button class="btn btn-primary" id="boq-paste">Paste from Excel</button><button class="btn btn-ghost" id="boq-add">+ Line</button>` });
  if (!rows.length) html += `<div class="empty">No BOQ yet. Copy the lines out of the Excel BOQ (description, unit, qty, rate) and press <b>Paste from Excel</b> - one step for the whole BOQ.</div>`;
  else {
    html += `<div class="strip">${[["BOQ value", tot], ["Budget cost", cost], ["Budget margin", tot - cost]].map(([l, v]) => `<div class="fig"><div class="l">${l}</div><div class="v">${aed(v)}</div></div>`).join("")}<div class="fig"><div class="l">Margin %</div><div class="v">${tot ? (100 * (tot - cost) / tot).toFixed(1) : 0}%</div></div></div>`;
    html += `<div class="tw"><table class="t"><thead><tr><th>Item</th><th>Description</th><th>Unit</th><th class="r">Qty</th><th class="r">Rate</th><th class="r">Amount</th><th class="r">Cost rate ${tip("Your budget cost per unit. Click any figure to change it.")}</th><th class="r">Budget</th><th class="r">Done %</th></tr></thead><tbody>`;
    let sec = null;
    for (const x of rows) {
      if (x.section !== sec) { sec = x.section; const st2 = rows.filter(y => y.section === sec); html += `<tr class="sec"><td colspan="5">${esc(sec || "General")}</td><td class="r">${money(st2.reduce((a, y) => a + y.amount, 0))}</td><td></td><td class="r">${money(st2.reduce((a, y) => a + y.cost, 0))}</td><td></td></tr>`; }
      html += `<tr><td class="small">${esc(x.code)}</td><td class="rowc" data-boq="${x.id}">${esc(x.description)}</td><td>${esc(x.unit)}</td>${["qty", "rate"].map(k => `<td class="r rowc" data-ed="${x.id}:${k}">${money(x[k])}</td>`).join("")}<td class="r">${money(x.amount)}</td><td class="r rowc" data-ed="${x.id}:cost_rate">${money(x.cost_rate)}</td><td class="r">${money(x.cost)}</td><td class="r rowc" data-ed="${x.id}:done_pct">${x.done_pct ? x.done_pct + "%" : '<span class="muted">-</span>'}</td></tr>`;
    }
    html += `<tr class="tot"><td></td><td>Total</td><td></td><td></td><td></td><td class="r">${money(tot)}</td><td></td><td class="r">${money(cost)}</td><td></td></tr></tbody></table></div>`;
  }
  el.innerHTML = html;
  bindTools(el, () => SECTIONS["client.boq"](el));
  $("#boq-paste", el).onclick = () => modal("Paste the BOQ from Excel", [
    { k: "section", label: "Section for lines before the first heading", ph: "e.g. SUBSTRUCTURE" },
    { k: "text", label: "Lines copied from Excel", type: "area", ph: "Select the rows in Excel (item, description, unit, qty, rate), copy, and paste here.", focus: true }],
    async v => { const r = await POST(`/store/est/projects/${ST.pid}/boq-paste`, v); await reload(); toast(r.added + " lines added"); },
    { after: () => { $("#f-text").style.height = "220px"; } });
  $("#boq-add", el).onclick = () => boqForm();
  $$("[data-boq]", el).forEach(td => td.onclick = () => boqForm(b.boq.find(x => x.id === +td.dataset.boq)));
  $$("[data-ed]", el).forEach(td => td.onclick = () => inlineEdit(td, "boq"));
};
function boqForm(x) {
  x = x || {};
  modal(x.id ? "BOQ line" : "New BOQ line", [
    { k: "section", label: "Section", type: "combo", options: [...new Set(ST.b.boq.map(y => y.section).filter(Boolean))], value: x.section || "" },
    { k: "code", label: "Item no.", value: x.code || "" }, { k: "description", label: "Description", value: x.description || "", full: true, focus: true },
    { k: "unit", label: "Unit", type: "combo", options: ["m3", "m2", "m", "nos", "kg", "ton", "LS", "set", "lot"], value: x.unit || "" },
    { k: "qty", label: "Qty", type: "num", value: x.qty ?? "" }, { k: "rate", label: "Rate (AED)", type: "money", value: x.rate ?? "" },
    { k: "cost_rate", label: "Budget cost rate (AED)", type: "money", value: x.cost_rate ?? "" }, { k: "done_pct", label: "Done %", type: "pct", value: x.done_pct ?? "" },
  ], async v => { if (x.id) await PATCH(`/store/est/boq/${x.id}`, v); else await POST("/store/est/boq", Object.assign(v, { project_id: ST.pid })); reload(); },
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

// ---------------- Client side > payment certificates ----------------
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
    { k: "claimed_cum", label: "Work done to date - claimed (AED)", type: "money", value: edit ? c.claimed_cum : (last ? last.claimed_cum : ""), focus: true,
      quick: [25, 50, 75, 100].map(n => [n + "%", el => el.value = r2(b.summary.revised * n / 100)]), hint: `Revised contract ${money(b.summary.revised, false)}${last && !edit ? " · last claim " + money(last.claimed_cum, false) : ""}` },
    { k: "certified_cum", label: "Certified to date (AED)", type: "money", value: c.certified_cum || "" },
    { k: "period_to", label: "Period up to", type: "date", value: c.period_to || today() }, { k: "submitted", label: "Submitted on", type: "date", value: c.submitted || "" },
    { k: "mos_cum", label: "Material on site to date", type: "money", value: c.mos_cum || "" }, { k: "other_cum", label: "Other deductions to date", type: "money", value: c.other_cum || "" },
    { k: "ret_rel_cum", label: "Retention released to date", type: "money", value: c.ret_rel_cum || "" },
    { k: "status", label: "Status", type: "select", options: ["Draft", "Submitted", "Certified", "Invoiced", "Paid"], value: c.status || "Draft" },
    { k: "invoice_no", label: "Our invoice no.", value: c.invoice_no || "", tip: "The tax invoice from Accounts > Invoices for this certificate." },
    { k: "remarks", label: "Remarks", type: "area", value: c.remarks || "" },
  ], async v => { if (edit) await PATCH(`/store/est/clientpcs/${c.id}`, v); else await POST("/store/est/clientpcs", Object.assign(v, { project_id: ST.pid })); await reload(); toast("Saved"); },
  { wide: true, del: edit ? async () => { await DEL(`/store/est/clientpcs/${c.id}`); reload(); } : null });
}

// ---------------- Client side > variations ----------------
SECTIONS["client.vo"] = el => {
  const b = ST.b, f = filt();
  const list = b.variations.filter(v => (!f || v.status === f) && match(v));
  const n = s => b.variations.filter(v => v.status === s).length;
  const sum = (k, s) => r2(b.variations.filter(v => !s || v.status === s).reduce((a, v) => a + (v[k] || 0), 0));
  el.innerHTML = tools("variations", { add: `<button class="btn btn-primary" id="add-vo">+ Variation</button>`, chips: [["", b.variations.length], ...["Identified", "Submitted", "Approved", "Rejected"].map(s => [s, n(s)])] }) +
    `<div class="strip"><div class="fig"><div class="l">Submitted</div><div class="v">${aed(sum("submitted_amount"))}</div></div><div class="fig green"><div class="l">Approved</div><div class="v">${aed(sum("approved_amount", "Approved"))}</div></div><div class="fig amber"><div class="l">Waiting approval</div><div class="v">${aed(sum("submitted_amount", "Submitted"))}</div></div></div>` +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>VO</th><th>Description</th><th>Source</th><th>Date</th><th class="r">Submitted</th><th class="r">Approved</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map(v => `<tr class="rowc" data-vo="${v.id}"><td class="nowrap"><b>VO-${pad(v.seq)}</b></td><td>${esc(v.title)}<div class="small muted">${esc(v.kind)}${v.ref ? " · " + esc(v.ref) : ""}</div></td><td class="small">${esc(v.source)}</td><td class="nowrap">${dt(v.on_date)}</td><td class="r">${money(v.submitted_amount)}</td><td class="r">${money(v.approved_amount)}</td><td>${st(v.status)}</td>
      <td class="nowrap">${v.status === "Identified" ? `<button class="btn btn-ghost btn-sm" data-vst="${v.id}:Submitted">Submitted</button>` : v.status === "Submitted" ? `<button class="btn btn-ok btn-sm" data-vapp="${v.id}">Approved</button> <button class="btn btn-plain btn-sm" data-vst="${v.id}:Rejected">Rejected</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>` : '<div class="empty">No variations yet.</div>');
  bindTools(el, () => SECTIONS["client.vo"](el));
  $("#add-vo", el).onclick = () => voForm();
  $$("[data-vo]", el).forEach(r => r.onclick = e => { if (e.target.closest("button")) return; voForm(b.variations.find(v => v.id === +r.dataset.vo)); });
  $$("[data-vst]", el).forEach(x => x.onclick = async () => { const [id, s] = x.dataset.vst.split(":"); const d = { status: s }; if (s === "Submitted") d.submitted = today(); try { await PATCH(`/store/est/variations/${id}`, d); await reload(); toast(s); } catch (e) { fail(e); } });
  $$("[data-vapp]", el).forEach(x => x.onclick = () => { const v = b.variations.find(y => y.id === +x.dataset.vapp);
    modal(`VO-${pad(v.seq)} approved`, [{ k: "approved_amount", label: "Approved amount (AED)", type: "money", value: v.submitted_amount, quick: [["As submitted", el2 => el2.value = v.submitted_amount]], focus: true }, { k: "approved_on", label: "Approved on", type: "date", value: today() }],
      async d => { await PATCH(`/store/est/variations/${v.id}`, Object.assign(d, { status: "Approved" })); await reload(); toast("Approved - added to the contract"); }); });
};
function voForm(v) {
  v = v || {};
  modal(v.id ? `VO-${pad(v.seq)}` : "New variation", [
    { k: "title", label: "Description", value: v.title || "", full: true, focus: true },
    { k: "kind", label: "Type", type: "select", options: ["Addition", "Omission"], value: v.kind || "Addition" },
    { k: "source", label: "Source", type: "select", options: ["Client instruction", "Consultant instruction", "Site condition", "Design change", "Authority requirement"], value: v.source || "Client instruction" },
    { k: "ref", label: "Instruction ref.", value: v.ref || "" }, { k: "on_date", label: "Date", type: "date", value: v.on_date || today() },
    { k: "submitted_amount", label: "Submitted amount (AED)", type: "money", value: v.submitted_amount ?? "" },
    { k: "approved_amount", label: "Approved amount (AED)", type: "money", value: v.approved_amount || "" },
    { k: "status", label: "Status", type: "select", options: ["Identified", "Submitted", "Approved", "Rejected"], value: v.status || "Identified" },
    { k: "sub_id", label: "Passed to subcontractor", type: "select", options: [["", "-"], ...ST.b.subs.map(s => [s.id, s.name])], value: v.sub_id || "" },
    { k: "notes", label: "Notes", type: "area", value: v.notes || "" },
  ], async d => { if (v.id) await PATCH(`/store/est/variations/${v.id}`, d); else await POST("/store/est/variations", Object.assign(d, { project_id: ST.pid })); await reload(); toast("Saved"); },
  { wide: true, del: v.id ? async () => { await DEL(`/store/est/variations/${v.id}`); reload(); } : null });
}

// ---------------- Client side > invoices (from Accounts) ----------------
SECTIONS["client.inv"] = el => {
  const b = ST.b, list = b.invoices.filter(match);
  const tax = list.filter(i => i.kind === "tax" && i.status !== "cancelled");
  el.innerHTML = `<div class="tools"><input class="q" placeholder="Search" value="${esc(ST.q[key()] || "")}" data-q><span class="spacer"></span><span class="small muted">Read from Accounts > Invoices (project ${esc(b.project.code)}) ${tip("Invoices are made in Accounts > Invoices. Any invoice with this project number shows here by itself.")}</span>${ST.meta.me.accounts && window.PG_EMBED ? `<button class="btn btn-ghost btn-sm" id="go-inv">Open Accounts > Invoices</button>` : ""}</div>
    <div class="strip"><div class="fig"><div class="l">Invoiced (tax)</div><div class="v">${aed(tax.reduce((a, i) => a + i.total, 0))}</div><div class="s">${tax.length} invoices</div></div><div class="fig green"><div class="l">Received</div><div class="v">${aed(b.summary.received)}</div><div class="s">Accounts > Project payments</div></div><div class="fig amber"><div class="l">Certified, not invoiced</div><div class="v">${aed(Math.max(0, b.summary.client_certified * (1 + b.project.vat_pct / 100) - tax.reduce((a, i) => a + i.total, 0)))}</div></div></div>` +
    (list.length ? `<div class="tw"><table class="t"><thead><tr><th>Type</th><th>Number</th><th>Date</th><th>Work</th><th class="r">Amount</th><th class="r">VAT</th><th class="r">Total</th><th>Status</th></tr></thead><tbody>${list.map(i => `<tr><td>${i.kind === "tax" ? "Tax invoice" : "Proforma"}</td><td><b>${esc(i.number)}</b></td><td>${dt(i.date)}</td><td>${esc(i.work)}</td><td class="r">${money(i.subtotal)}</td><td class="r">${money(i.vat)}</td><td class="r">${money(i.total)}</td><td>${st(i.status === "cancelled" ? "Cancelled" : "Issued")}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">No invoices for project ${esc(b.project.code)} in Accounts yet.</div>`);
  bindTools(el, () => SECTIONS["client.inv"](el));
  const g = $("#go-inv", el); if (g) g.onclick = () => parent.postMessage({ est: "app", page: "accounts", tab: "invoices" }, location.origin);
};

// ---------------- Site & technical: RFIs, submittals ----------------
const LOGCFG = {
  rfi: { name: "RFI", title: "Subject", party: "To", reply: "Answered", btn: "Answer received" },
  submittal: { name: "Submittal", title: "Item submitted", party: "To", reply: "Approved", btn: "Reply received" },
};
function logSection(kind) {
  return el => {
    const b = ST.b, cfg = LOGCFG[kind], f = filt(), sts = ST.meta.log_status[kind], t = today();
    const all = b.logs.filter(l => l.kind === kind);
    const list = all.filter(l => (!f || l.status === f || (f === "Overdue" && l.due && l.due < t && !l.replied)) && match(l));
    const late = all.filter(l => l.due && l.due < t && !l.replied && !["Closed", "Approved", "Answered", "Rejected"].includes(l.status)).length;
    el.innerHTML = tools(kind, { add: `<button class="btn btn-primary" id="add-log">+ ${cfg.name}</button>`, chips: [["", all.length], ...sts.map(s => [s, all.filter(l => l.status === s).length]), ["Overdue", late]],
      right: `<button class="btn btn-plain btn-sm" id="rules">Reply in ${kind === "rfi" ? b.rules.rfi_days : b.rules.submittal_days} days</button>` }) +
      (list.length ? `<div class="tw"><table class="t"><thead><tr><th>No.</th><th>${cfg.title}</th><th>${cfg.party}</th><th>Discipline</th><th>Ref.</th>${kind === "submittal" ? "<th>Rev.</th>" : ""}<th>Sent</th><th>Due</th><th>Reply</th><th>Status</th><th></th></tr></thead><tbody>
      ${list.map(l => { const od = l.due && l.due < t && !l.replied && !["Closed", "Approved", "Answered", "Rejected"].includes(l.status);
        return `<tr class="rowc" data-log="${l.id}"><td class="nowrap"><b>${kind === "rfi" ? "RFI" : "SUB"}-${pad(l.seq)}</b></td><td>${esc(l.title)}${l.note ? `<div class="small muted">${esc(l.note.slice(0, 120))}</div>` : ""}</td><td>${esc(l.party)}</td><td class="small">${esc(l.discipline)}</td><td class="small">${esc(l.ref)}</td>${kind === "submittal" ? `<td>${esc(l.rev)}</td>` : ""}
        <td class="nowrap">${dt(l.sent)}</td><td class="nowrap ${od ? "late" : ""}">${dt(l.due)}${od ? " !" : ""}</td><td class="nowrap">${dt(l.replied)}</td><td>${st(l.status)}</td>
        <td class="nowrap">${!l.replied ? `<button class="btn btn-ghost btn-sm" data-reply="${l.id}">${cfg.btn}</button>` : kind === "rfi" && l.status !== "Closed" ? `<button class="btn btn-plain btn-sm" data-close="${l.id}">Close</button>` : ""}</td></tr>`; }).join("")}
      </tbody></table></div>` : `<div class="empty">No ${cfg.name}s${f ? " here" : " yet"}.</div>`);
    bindTools(el, () => logSection(kind)(el));
    $("#add-log", el).onclick = () => logForm(kind);
    $("#rules", el).onclick = rulesForm;
    $$("[data-log]", el).forEach(r => r.onclick = e => { if (e.target.closest("button")) return; logForm(kind, all.find(l => l.id === +r.dataset.log)); });
    $$("[data-reply]", el).forEach(x => x.onclick = () => {
      const l = all.find(y => y.id === +x.dataset.reply);
      if (kind === "rfi") return quickLog(l.id, { replied: today(), status: "Answered" }, "Answer received");
      modal(`SUB-${pad(l.seq)} reply`, [{ k: "status", label: "Reply", type: "select", options: ["Approved", "Approved as noted", "Revise & resubmit", "Rejected"] }, { k: "replied", label: "Reply date", type: "date", value: today() }, { k: "note", label: "Comments", type: "area", value: l.note }],
        async v => { await PATCH(`/store/est/logs/${l.id}`, v); await reload(); toast("Saved"); });
    });
    $$("[data-close]", el).forEach(x => x.onclick = () => quickLog(+x.dataset.close, { status: "Closed" }, "Closed"));
  };
}
async function quickLog(id, d, msg) { try { await PATCH(`/store/est/logs/${id}`, d); await reload(); toast(msg); } catch (e) { fail(e); } }
function logForm(kind, l) {
  l = l || {}; const cfg = LOGCFG[kind], m = ST.meta;
  const fields = [
    { k: "title", label: cfg.title, value: l.title || "", full: true, focus: true },
    { k: "party", label: cfg.party, type: "select", options: m.parties, value: l.party || "Consultant" },
    { k: "discipline", label: "Discipline", type: "select", options: ["", ...m.disciplines], value: l.discipline || "" },
    { k: "ref", label: "Ref. / letter no.", value: l.ref || "" },
    { k: "sent", label: "Sent on", type: "date", value: l.sent || today() }, { k: "due", label: "Reply due", type: "date", value: l.due || "", hint: l.id ? "" : "Left empty, it is set from the days allowed." },
    { k: "replied", label: "Reply received", type: "date", value: l.replied || "" },
    { k: "status", label: "Status", type: "select", options: m.log_status[kind], value: l.status || m.log_status[kind][0] },
    { k: "note", label: kind === "rfi" ? "Question / answer" : "Comments", type: "area", value: l.note || "" },
  ];
  if (kind === "submittal") fields.splice(4, 0, { k: "rev", label: "Revision", type: "select", options: ["0", "1", "2", "3", "4", "5"], value: l.rev || "0" });
  modal(l.id ? `${kind === "rfi" ? "RFI" : "SUB"}-${pad(l.seq)}` : `New ${cfg.name}`, fields,
    async v => { if (l.id) await PATCH(`/store/est/logs/${l.id}`, v); else { v.kind = kind; v.project_id = ST.pid; await POST("/store/est/logs", v); } await reload(); toast("Saved"); },
    { wide: true, del: l.id ? async () => { await DEL(`/store/est/logs/${l.id}`); reload(); } : null });
}
SECTIONS["site.rfi"] = logSection("rfi");
SECTIONS["site.submittal"] = logSection("submittal");

// ---------------- Site & technical > NOCs & approvals (the project tracker) ----------------
SECTIONS["site.approval"] = el => {
  const b = ST.b, f = filt();
  const all = b.logs.filter(l => l.kind === "approval");
  const list = all.filter(l => (!f || l.status === f) && match(l));
  let html = tools("approval", { add: `<button class="btn btn-ghost" id="add-ap">+ Item</button>`, chips: [["", all.length], ...ST.meta.log_status.approval.map(s => [s, all.filter(l => l.status === s).length])],
      right: `<span class="small muted">One click stamps today's date ${tip("Submitted / Approved put today's date in. Click the item to change a date.")}</span>` });
  html += `<div class="tw"><table class="t"><thead><tr><th>Item</th><th>Authority</th><th>Submitted</th><th>Approved</th><th>Status</th><th>Ref.</th><th></th></tr></thead><tbody>`;
  let g = null;
  for (const l of list) {
    if (l.group !== g) { g = l.group; html += `<tr class="sec"><td colspan="7">${esc(g || "Other")}</td></tr>`; }
    html += `<tr class="rowc" data-ap="${l.id}"><td>${esc(l.title)}</td><td class="small">${esc(l.party)}</td><td class="nowrap">${dt(l.sent)}</td><td class="nowrap">${dt(l.replied)}</td><td>${st(l.status)}</td><td class="small">${esc(l.ref)}</td>
      <td class="nowrap">${l.status === "Not started" || l.status === "Rejected" ? `<button class="btn btn-ghost btn-sm" data-aq="${l.id}:Submitted">Submitted</button> <button class="btn btn-plain btn-sm" data-aq="${l.id}:N/A">N/A</button>` : l.status === "Submitted" ? `<button class="btn btn-ok btn-sm" data-aq="${l.id}:Approved">Approved</button> <button class="btn btn-plain btn-sm" data-aq="${l.id}:Rejected">Rejected</button>` : ""}</td></tr>`;
  }
  el.innerHTML = html + "</tbody></table></div>";
  bindTools(el, () => SECTIONS["site.approval"](el));
  $$("[data-aq]", el).forEach(x => x.onclick = e => { e.stopPropagation(); const [id, s] = x.dataset.aq.split(":"); const d = { status: s }; if (s === "Submitted") d.sent = today(); if (s === "Approved") d.replied = today(); quickLog(+id, d, s); });
  $$("[data-ap]", el).forEach(r => r.onclick = e => { if (e.target.closest("button")) return; apForm(all.find(l => l.id === +r.dataset.ap)); });
  $("#add-ap", el).onclick = () => apForm();
};
function apForm(l) {
  l = l || {};
  modal(l.id ? l.title : "New approval item", [
    { k: "group", label: "Stage", type: "combo", options: [...new Set(ST.b.logs.filter(x => x.kind === "approval").map(x => x.group))], value: l.group || "" },
    { k: "title", label: "Item", value: l.title || "", focus: !l.id }, { k: "party", label: "Authority", type: "select", options: ST.meta.parties, value: l.party || "DM (Dubai Municipality)" },
    { k: "sent", label: "Submitted", type: "date", value: l.sent || "" }, { k: "replied", label: "Approved", type: "date", value: l.replied || "" },
    { k: "status", label: "Status", type: "select", options: ST.meta.log_status.approval, value: l.status || "Not started" },
    { k: "ref", label: "Ref. / permit no.", value: l.ref || "" }, { k: "note", label: "Note", type: "area", value: l.note || "" },
  ], async v => { if (l.id) await PATCH(`/store/est/logs/${l.id}`, v); else await POST("/store/est/logs", Object.assign(v, { kind: "approval", project_id: ST.pid })); await reload(); toast("Saved"); },
  { del: l.id ? async () => { await DEL(`/store/est/logs/${l.id}`); reload(); } : null });
}

// ---------------- Site & technical > documents ----------------
SECTIONS["site.doc"] = el => {
  const b = ST.b, f = filt();
  const files = b.files.filter(x => (!f || x.category === f) && match(x));
  const cats = ST.meta.doc_categories;
  el.innerHTML = tools("", { chips: [["", b.files.length], ...cats.filter(c => b.files.some(x => x.category === c)).map(c => [c, b.files.filter(x => x.category === c).length])] }) +
    `<div class="drop" id="drop"><b>Drop files here</b> or <label style="color:var(--red);cursor:pointer;font-weight:700">choose files<input type="file" multiple id="up" class="hide"></label> &nbsp;·&nbsp; filed under <select id="up-cat" style="height:28px;border:1px solid #D9DCE0;border-radius:6px">${cats.map(c => `<option>${esc(c)}</option>`).join("")}</select><div class="small" style="margin-top:4px">Up to 25 MB each. Drawings, letters, permits, photos ...</div></div>` +
    (files.length ? `<div class="tw" style="margin-top:12px"><table class="t"><thead><tr><th>File</th><th>Filed under</th><th>Added by</th><th>When</th><th class="r">Size</th><th></th></tr></thead><tbody>${files.map(x => `<tr><td><a href="${x.url}" target="_blank" rel="noopener"><b>${esc(x.name)}</b></a></td><td><select data-fcat="${x.id}" style="height:26px;border:1px solid #E0DCD6;border-radius:6px">${cats.map(c => `<option ${c === x.category ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></td><td>${esc(x.by)}</td><td class="nowrap">${dt(x.at)}</td><td class="r small">${(x.size / 1024 / 1024).toFixed(2)} MB</td><td><button class="btn btn-plain btn-sm" data-fdel="${x.id}">Remove</button></td></tr>`).join("")}</tbody></table></div>` : "");
  bindTools(el, () => SECTIONS["site.doc"](el));
  const up = async list => {
    let n = 0;
    for (const file of list) {
      const fd = new FormData(); fd.append("project_id", ST.pid); fd.append("kind", "doc"); fd.append("category", $("#up-cat").value); fd.append("file", file);
      try { await api("/store/est/files/upload", { method: "POST", body: fd }); n++; } catch (e) { fail(e); }
    }
    if (n) { await reload(); toast(n + " file" + (n > 1 ? "s" : "") + " added"); }
  };
  $("#up", el).onchange = e => up([...e.target.files]);
  const d = $("#drop", el);
  d.ondragover = e => { e.preventDefault(); d.classList.add("over"); }; d.ondragleave = () => d.classList.remove("over");
  d.ondrop = e => { e.preventDefault(); d.classList.remove("over"); up([...e.dataTransfer.files]); };
  $$("[data-fdel]", el).forEach(x => x.onclick = async () => { if (!confirmInline(x)) return; try { await DEL(`/store/est/files/${x.dataset.fdel}`); reload(); } catch (e) { fail(e); } });
  $$("[data-fcat]", el).forEach(s => s.onchange = async () => { try { await PATCH(`/store/est/files/${s.dataset.fcat}`, { category: s.value }); toast("Saved"); } catch (e) { fail(e); } });
};

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
  { wide: true, del: x.id ? async () => { await DEL(`/store/est/tenders/${x.id}`); loadTenders(); } : null });
}
function addDays(n) { const d = new Date(today() + "T00:00:00"); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }

start();
