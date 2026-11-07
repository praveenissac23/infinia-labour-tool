/* Estimation > Bills: the bills (interim payment applications) sent to the client each month.
   The consultant's own Excel bill is uploaded once as the format; each month's bill starts from the last one
   (Previous % = last Total %, bill no. + 1, dated today, last bill put on the previous payments), staff type
   this month's Total % and payments, and it comes out as the same workbook, a preview and a PDF.
   Uses est.js (ST, api, modal, money, ...) and pcsheet.js (big). */

const IPA = { list: null, bill: null, step: "work", q: "", filter: "", sheet: undefined, addRow: null };
const pct = v => v === null || v === undefined ? "" : String(Math.round(v * 1e6) / 1e4);       // 0.45 -> "45"
const isPctNf = nf => /%/.test(String(nf || "").replace(/"[^"]*"/g, ""));

SECTIONS["bills.ipa"] = async el => {
  el.innerHTML = `<div class="empty">Loading the bills...</div>`;
  let d;
  try { d = await GET(`/store/est/ipa/list?project_id=${ST.pid}`); } catch (e) { el.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (key() !== "bills.ipa") return;
  // A project under several contracts: one contract at a time, each with its own formats and bills.
  const ks = CTRS(), cur = ctrPick(), K = ks.find(k => k.id === cur);
  const formats = K ? d.formats.filter(f => f.contract_id === cur) : d.formats;
  IPA.list = Object.assign({}, d, { formats, contract_id: cur });
  const fm = id => d.formats.find(f => f.id === id);
  const q = (ST.q[key()] || "").toLowerCase();
  const bills = d.bills.filter(b => (!K || b.contract_id === cur) && (!q || JSON.stringify(b).toLowerCase().includes(q)));
  const pc = (a, b) => b ? (Math.round(1000 * a / b) / 10).toFixed(1) + "%" : "-";
  const ctrRow = K ? `<div class="ctrs"><span class="lbl">Contract</span>${ks.map(k => `<button class="ctr ${k.id === cur ? "on" : ""}" data-ctrpick="${k.id}"><b>${esc(k.name)}</b><small>${esc([k.ref, "AED " + money(k.value, false), k.bills ? k.bills + " bill" + (k.bills === 1 ? "" : "s") : "no bills yet"].filter(Boolean).join(" · "))}</small></button>`).join("")}
      <button class="ctr add" id="ctr-add">+ Add contract</button><span class="spacer"></span><button class="btn btn-ghost" id="ctr-edit">Edit contract</button></div>
    <div class="kpis k5 ctrk">${kpi("Contract value (with variations)", money(K.revised, false), K.approved_vo ? `original ${money(K.value, false)} + VOs ${money(K.approved_vo, false)}` : "original contract")}
      ${kpi("Work done to date (last bill)", money(K.work_done, false), pc(K.work_done, K.revised) + " of the contract")}
      ${kpi("Certified by client", money(K.certified, false), K.pcs + " certificate" + (K.pcs === 1 ? "" : "s"))}
      ${kpi("Retention held", money(K.retention, false), K.ret_pct + "% retention")}
      ${kpi("Advance recovered", K.adv_paid ? `${money(K.adv_recovered, false)} <span class="muted small">of ${money(K.adv_paid, false)}</span>` : "-", K.adv_pct ? K.adv_pct + "% advance" : "no advance")}</div>` : "";
  el.innerHTML = ctrRow + tools(null, { add: (formats.length ? `<button class="btn btn-primary" id="ipa-new">+ New bill${K ? " - " + esc(K.name) : ""}</button>` : "") + `<button class="btn btn-ghost" id="ipa-up">Upload bill format${K ? " - " + esc(K.name) : ""}</button>`,
      right: K ? "" : `<button class="btn btn-plain" id="ctr-add" title="This project is under more than one agreement with the client (e.g. shell & core, MEP, swimming pool): each gets its own bills, certificates and variations.">+ Another contract</button>` }) +
    (!formats.length ? `<div class="card empty" style="text-align:left;line-height:1.6"><b>No bill format for ${K ? "the " + esc(K.name) + " contract" : "this project"} yet.</b><br>
        Upload the last bill exactly as it was sent to the consultant (the Excel workbook with the cover, summary and the sheets with Previous % / Total %).
        Each new bill starts from it: last month's Total % becomes Previous %, the bill number goes up by one and the date is today.
        The workbook comes back out with the same layout, logo, stamps and formulas.</div>` :
     bills.length ? `<div class="tw"><table class="t"><thead><tr><th>Bill</th><th>Issue date</th><th>Format</th><th class="r">Total due</th><th>Status</th><th>Last change</th><th></th></tr></thead><tbody>
      ${bills.map(b => `<tr class="rowc" data-ipa="${b.id}"><td><b>IPA ${esc(b.label || b.seq)}</b></td><td>${dt(b.issue_date)}</td><td class="small">${esc((fm(b.format_id) || {}).name || "")}</td>
        <td class="r"><b>${money(b.total_due)}</b></td><td>${st(b.status)}</td><td class="small muted">${esc(b.by)}${b.updated ? " · " + dt(b.updated) : ""}</td>
        <td class="r nowrap"><button class="btn btn-ghost btn-sm" data-ipaopen="${b.id}">Open</button>${b.status === "Draft" || ST.meta.me.admin ? ` <button class="btn btn-plain btn-sm" data-ipadel="${b.id}">Delete</button>` : ""}</td></tr>`).join("")}</tbody></table></div>` :
     `<div class="card empty">No bills yet. Press <b>+ New bill</b> - it starts from the uploaded format.</div>`) +
    (formats.length ? fmtCards(formats, ks, K) : "");
  bindTools(el, () => SECTIONS["bills.ipa"](el));
  $$("[data-ctrpick]", el).forEach(b => b.onclick = () => { ctrSet(+b.dataset.ctrpick); SECTIONS["bills.ipa"](el); });
  const ca = $("#ctr-add", el); if (ca) ca.onclick = () => contractForm();
  const ce = $("#ctr-edit", el); if (ce) ce.onclick = () => contractForm(K);
  $$("[data-fmmove]", el).forEach(x => x.onchange = async () => { try { await PATCH(`/store/est/ipa/format/${x.dataset.fmmove}`, { contract_id: +x.value }); await reload(); toast(`Moved to ${ctrName(x.value)}`); } catch (e) { fail(e); } });
  $("#ipa-up", el).onclick = uploadFormat;
  const nb = $("#ipa-new", el); if (nb) nb.onclick = newBill;
  $$("[data-ipa]", el).forEach(r => r.onclick = e => { if (e.target.closest("[data-ipadel]")) return; openBill(+r.dataset.ipa); });
  $$("[data-ipadel]", el).forEach(x => x.onclick = async e => {
    e.stopPropagation();
    const b = bills.find(y => y.id === +x.dataset.ipadel);
    if (!(await confirmDelete(`Delete bill ${b.label || b.seq}?`, `${esc(b.status)} · total due AED ${money(b.total_due, false)}`))) return;
    try { await DEL(`/store/est/ipa/bill/${b.id}`); toast(`Bill ${b.label || b.seq} deleted`); SECTIONS["bills.ipa"](el); } catch (y) { fail(y); }
  });
  $$("[data-fmdel]", el).forEach(b => b.onclick = async e => {
    e.stopPropagation();
    const f = formats.find(x => x.id === +b.dataset.fmdel);
    if (!(await confirmDelete(`Delete uploaded bill ${f ? f.no[1] || f.no[0] : ""}?`,
        `${esc(f ? f.filename : "")}${f && f.bills ? `<br><b>${f.bills} bill${f.bills === 1 ? "" : "s"} made on it go with it.</b>` : ""}`))) return;
    try { await DEL(`/store/est/ipa/format/${b.dataset.fmdel}`); toast("Deleted"); SECTIONS["bills.ipa"](el); } catch (x) { fail(x); }
  });
  $$("[data-fmview]", el).forEach(r => r.onclick = e => { if (e.target.closest("[data-fmdel],select")) return; viewFormat(+r.dataset.fmview); });
};
// Every bill uploaded as a workbook (Previous records or Upload), in bill order - click one to read it sheet by sheet,
// print or export it. (The latest of them is what the next bill is made from until a bill has been made here.)
function fmtCards(formats, ks, K) {
  const list = formats.slice().sort((a, b) => (a.no[0] - b.no[0]) || (a.id - b.id));
  const ctrSel = f => ks.length > 1 ? `<td><select class="sel-sm" data-fmmove="${f.id}" title="Move this workbook (and bills made on it) to another contract">${ks.map(k => `<option value="${k.id}" ${k.id === f.contract_id ? "selected" : ""}>${esc(k.name)}</option>`).join("")}</select></td>` : "";
  return `<div class="card" style="margin-top:14px"><h3>Previous bills (uploaded)${K ? " - " + esc(K.name) : ""} ${tip("Bills uploaded as workbooks - from Previous records or Upload bill. Click one to read it sheet by sheet, preview, print, or export it as PDF or the Excel as uploaded. A new bill is made from the latest bill - the last one made here, with whatever was added on it, or the latest uploaded one until then.")}<span class="spacer"></span><span class="small muted">${list.length} workbook${list.length === 1 ? "" : "s"}</span></h3>
    <div class="tw"><table class="t"><thead><tr><th>Bill no.</th><th>File</th><th>Sheets</th><th class="c">Bills made on it</th><th>Uploaded</th>${ks.length > 1 ? "<th>Contract</th>" : ""}<th></th></tr></thead><tbody>
    ${list.map(f => `<tr class="rowc" data-fmview="${f.id}" title="Open to read"><td><b>${esc(f.no[1] || String(f.no[0] || "-"))}</b></td><td>${esc(f.filename)}</td><td class="small" title="${esc(f.sheets.join(", "))}">${f.sheets.length} sheets</td>
      <td class="c">${f.bills || '<span class="muted">-</span>'}</td><td class="small muted">${esc(f.by)} · ${dt(f.on)}</td>${ctrSel(f)}<td class="r nowrap"><button class="btn btn-ghost btn-sm" data-fmview="${f.id}">Open</button> <button class="btn btn-plain btn-sm" data-fmdel="${f.id}">Delete</button></td></tr>`).join("")}
    </tbody></table></div></div>`;
}
// ---- one sheet viewer for every sheet shown (a previous bill to read, the bill's own Sheets step) ----------------
// A bar: the sheet picker (< sheet >, "2 of 12") on the left; zoom - / % / + / Fit width / 100% on the right. The sheet
// fills the window down to the bottom and scrolls inside it (bars always shown). Opens fitted to the width; the zoom
// chosen is kept for next time. Ctrl / Cmd + and -, and pinching the trackpad, zoom too.
const SV = { z: null, w: 0 };
function svZoomPref() { try { return localStorage.getItem("est_sheet_zoom") || "fit"; } catch (e) { return "fit"; } }
function svSave(v) { try { localStorage.setItem("est_sheet_zoom", String(v)); } catch (e) {} }
function sheetFrame(el, d, opts = {}) {
  const sheets = opts.sheets || [], k = sheets.findIndex(x => x.i === d.i);
  el.innerHTML = `<div class="sv"><div class="sv-bar">
      ${sheets.length ? `<button class="btn btn-plain btn-sm" data-sv="prev" title="Previous sheet" ${k <= 0 ? "disabled" : ""}>&lsaquo;</button>
        <select class="sv-pick" title="Go to a sheet">${sheets.map(x => `<option value="${x.i}" ${x.i === d.i ? "selected" : ""}>${esc(x.name)}${x.added ? " (added)" : ""}</option>`).join("")}</select>
        <button class="btn btn-plain btn-sm" data-sv="next" title="Next sheet" ${k >= sheets.length - 1 ? "disabled" : ""}>&rsaquo;</button>
        <span class="muted small sv-n">${k + 1} of ${sheets.length}</span>` : ""}
      ${opts.tools || ""}
      <span class="spacer"></span>
      <span class="sv-zoom"><button class="btn btn-plain btn-sm" data-sv="out" title="Zoom out (Ctrl -)">&minus;</button><span class="sv-pc" title="Zoom">100%</span><button class="btn btn-plain btn-sm" data-sv="in" title="Zoom in (Ctrl +)">+</button>
        <button class="btn btn-plain btn-sm" data-sv="fit" title="The whole width of the sheet in the window">Fit width</button><button class="btn btn-plain btn-sm" data-sv="page" title="The whole sheet in the window">Fit page</button><button class="btn btn-plain btn-sm" data-sv="one" title="Actual size">100%</button></span></div>
    ${opts.below || ""}
    <div class="sv-box"><div class="sv-sz"><div class="sv-in ipa-sheet-in">${d.html}</div></div></div></div>`;
  const box = $(".sv-box", el), inner = $(".sv-in", el), sz = $(".sv-sz", el);
  SV.w = d.width || inner.scrollWidth;
  // the box: down to the bottom of the window - or only as tall as the sheet, so no empty band is left under it
  const avail = () => Math.max(260, window.innerHeight - box.getBoundingClientRect().top - 14);
  const size = () => { box.style.height = Math.min(avail(), Math.ceil(inner.offsetHeight * (SV.z || 1)) + 26 + (box.offsetHeight - box.clientHeight)) + "px"; };
  // scaled as a picture (transform), not with CSS zoom: Safari (iPhone / iPad / Mac) will not draw text below its
  // smallest size, so a zoomed-out sheet came out with its words too big for their cells - cut off and run together
  const set = z => { z = Math.max(0.3, Math.min(2.5, z)); SV.z = z; inner.style.transform = `scale(${z})`;
    sz.style.width = Math.ceil(inner.offsetWidth * z) + "px"; sz.style.height = Math.ceil(inner.offsetHeight * z) + "px";
    $(".sv-pc", el).textContent = Math.round(z * 100) + "%"; size(); };
  const fit = () => set(Math.min(1.25, (box.clientWidth - 26) / Math.max(1, SV.w)));     // a small sheet is not blown up
  const fitPage = () => { box.style.height = avail() + "px"; set(Math.min((box.clientWidth - 26) / Math.max(1, SV.w), (avail() - 26) / Math.max(1, inner.offsetHeight))); };
  box.style.height = avail() + "px";
  const pref = svZoomPref(); if (pref === "fit") fit(); else if (pref === "page") fitPage(); else set(Number(pref) || 1);
  const step = dir => { const z = Math.round(((SV.z || 1) + dir * 0.1) * 10) / 10; set(z); svSave(SV.z); };
  $$("[data-sv]", el).forEach(b => b.onclick = () => { const a = b.dataset.sv;
    if (a === "in") step(1); else if (a === "out") step(-1); else if (a === "fit") { fit(); svSave("fit"); } else if (a === "page") { fitPage(); svSave("page"); } else if (a === "one") { set(1); svSave(1); }
    else if (a === "prev" && k > 0) opts.go(sheets[k - 1].i); else if (a === "next" && k < sheets.length - 1) opts.go(sheets[k + 1].i); });
  const pick = $(".sv-pick", el); if (pick) pick.onchange = () => opts.go(+pick.value);
  box.addEventListener("wheel", e => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); set((SV.z || 1) * (e.deltaY < 0 ? 1.08 : 1 / 1.08)); svSave(SV.z); } }, { passive: false });
  if (!SV.bound) { SV.bound = true;
    document.addEventListener("keydown", e => { const fr = document.querySelector(".sv .sv-zoom"); if (!fr || !(e.ctrlKey || e.metaKey)) return;
      if (e.key === "+" || e.key === "=") { e.preventDefault(); fr.querySelector('[data-sv="in"]').click(); } else if (e.key === "-") { e.preventDefault(); fr.querySelector('[data-sv="out"]').click(); }
      else if (e.key === "0") { e.preventDefault(); fr.querySelector('[data-sv="fit"]').click(); } });
    window.addEventListener("resize", () => { const f = document.querySelector(".sv [data-sv=fit]"), pg = document.querySelector(".sv [data-sv=page]"), p_ = svZoomPref();
      if (p_ === "fit" && f) f.click(); else if (p_ === "page" && pg) pg.click(); }); }
  return { box, inner, zoom: () => SV.z || 1 };
}

// A previous bill (or the format) to read: its sheets as sent, one at a time.
async function viewFormat(fid, i = 0) {
  let d; try { d = await GET(`/store/est/ipa/format/${fid}/sheet/${i}`); } catch (e) { return fail(e); }
  const el = document.getElementById("big"), open = el && !el.classList.contains("hide") && el.dataset.ctx === "est.fmview";
  if (!open) big(`Bill ${esc(d.no[1] || String(d.no[0] || ""))} <span class="muted small">${esc(d.file)} - as uploaded, to read</span>`, "", null, "est.fmview");
  if (!document.getElementById("ipa-css")) document.head.appendChild(h(`<style id="ipa-css">${d.css}</style>`));
  $("#b-tools").innerHTML = xpButtons("ipafmt", { id: fid, name: (d.file || "bill").replace(/\.xls[xm]?$/i, "") });
  $("#b-body").classList.add("sv-body");
  sheetFrame($("#b-body"), d, { sheets: d.sheets, go: j => viewFormat(fid, j) });
}
function billsRedraw() { if (key() === "bills.ipa" && $("#sec")) SECTIONS["bills.ipa"]($("#sec")); }

// Upload a bill workbook as a format (Bills > Upload, and Previous records > "use as the bill format"). A bigger file
// goes in pieces (the web server takes about 1 MB a request). When some of its formulas do not give Excel's own
// figure here, the server stops and says which: the person sees them and chooses - upload anyway, or cancel.
async function sendBillFormat(file, fields, progress, force) {
  const fd = new FormData(); fd.append("project_id", ST.pid); fd.append("name", fields.name || file.name.replace(/\.xls[xm]?$/i, ""));
  if (fields.contract_id) fd.append("contract_id", fields.contract_id);
  if (force) fd.append("force", "1");
  const PART = 700 * 1024;
  if (file.size > PART) {
    const id = [...crypto.getRandomValues(new Uint8Array(12))].map(b => b.toString(16).padStart(2, "0")).join("");
    const n = Math.ceil(file.size / PART);
    for (let i = 0; i < n; i++) {
      if (progress) progress(`Uploading ${Math.round(100 * i / n)}%...`);
      const pf = new FormData(); pf.append("upload_id", id); pf.append("index", i); pf.append("file", file.slice(i * PART, (i + 1) * PART), "part");
      await api("/store/est/ipa/format/part", { method: "POST", body: pf });
    }
    fd.append("upload_id", id); fd.append("parts", n); fd.append("filename", file.name);
  } else fd.append("file", file);
  if (progress) progress("Reading the workbook...");
  try {
    return await api("/store/est/ipa/format", { method: "POST", body: fd });
  } catch (e) {
    if (e.status !== 409 || !e.data || force) throw e;
    const rows = (e.data.different || []).map(d => `<tr><td>${esc(d.sheet)} ${esc(d.cell)}</td><td class="r">${esc(String(d.excel ?? ""))}</td><td class="r">${esc(String(d.here ?? ""))}</td></tr>`).join("");
    const nm = e.data.mismatch || (e.data.formulas - e.data.same);
    const go = await confirmDelete(`${nm} formula${nm === 1 ? " does" : "s do"} not match Excel`,
      `${esc(e.message)}<div class="tw" style="margin:10px 0;max-height:220px;overflow:auto"><table class="t"><thead><tr><th>Cell</th><th class="r">Excel</th><th class="r">Here</th></tr></thead><tbody>${rows}</tbody></table></div>
       Check these cells in the workbook first. Upload it anyway only if you are sure the figures are right.`, "Upload anyway", "");
    if (!go) return null;
    return sendBillFormat(file, fields, progress, true);
  }
}

// What a workbook upload could not find - said, not left for a wrong bill to show later.
function formatGaps(r) {
  const miss = [["bill_no", "the bill no. (it will not go up by itself)"], ["issue_date", "the issue date (it will not be dated today by itself)"],
                ["total_due", "the total amount due"], ["payments", "a previous-payments table"]].filter(([k]) => r[k] === false).map(x => x[1]);
  return miss.length ? ` Not found in it: ${miss.join("; ")} - check the bill before sending.` : "";
}

function uploadFormat() {
  const p = ST.b.project, K = CTRS().find(k => IPA.list && k.id === IPA.list.contract_id);
  modal("Upload bill format" + (K ? " - " + K.name : ""), [
    { k: "name", label: "Name", value: [p.consultant || p.client, K ? K.name : "", "bill"].filter(Boolean).join(" - "), ph: "e.g. Consultant's IPA format", full: true },
  ], async v => {
    const f = ($("#fm-file") || {}).files; const file = f && f[0];
    if (!file) throw new Error("Pick the Excel bill.");
    const r = await sendBillFormat(file, { name: v.name, contract_id: IPA.list && IPA.list.contract_id }, t => { $("#m-save").textContent = t; });
    if (!r) return;
    const ok = r.same === r.formulas;
    const gaps = formatGaps(r);
    toast(`Format read: ${r.lines} lines with Previous % / Total % on ${r.sheets.join(", ")}. ${ok ? `All ${r.formulas} formulas give Excel's own figures.` : `${r.same} of ${r.formulas} formulas match Excel - check the bill before sending.`}${gaps}`, { ms: gaps || !ok ? 15000 : 7000, err: !ok || !!gaps });
    billsRedraw();
  }, { save: "Upload", bottom: `<div class="frm" style="margin-top:4px"><div class="f full"><label for="fm-file">The last bill as sent (Excel .xlsx or .xls) ${tip("The whole workbook: cover / summary and the sheets with the % of work done. It is kept on the server - every new bill is made from it, with the same layout, logo, stamps and formulas.")}</label><input type="file" id="fm-file" accept=".xlsx,.xlsm,.xls"></div></div>` });
}

// A new bill is made from the latest bill - the last one made here (with every line, section and page added on it),
// or the uploaded workbook when that is later - nothing to pick.
async function newBill() {
  const nf = nextFrom();
  try {
    const r = await POST("/store/est/ipa/new", { project_id: ST.pid, contract_id: IPA.list.contract_id || null });
    toast(`New bill started from bill ${nf.label || ""}${nf.kind === "bill" ? " (with everything added on it)" : ""}`); billsRedraw(); openBill(r.id);
  } catch (e) { fail(e); }
}
function nextFrom() { return ((IPA.list.next_from || {})[String(IPA.list.contract_id || 0)]) || {}; }


// =====================================================================================================
// ONE BILL - four steps: Cover & details, Work done, Payments received, Review & send.
// The consultant's sheets are never re-laid out; these screens only gather what changes each month.
// =====================================================================================================
const IPA_ALL_STEPS = [["cover", "Cover & details"], ["work", "Work done"], ["pay", "Payments received"], ["fees", "Authority fees"], ["sheets", "Sheets"], ["review", "Approve & send"]];
let IPA_STEPS = IPA_ALL_STEPS;
const pctTxt = v => v === null || v === undefined ? "" : (Math.round(v * 1e6) / 1e4).toLocaleString("en-US", { maximumFractionDigits: 2 }) + "%";
const amt = v => v === null || v === undefined || v === "" ? '<span class="muted">-</span>' : money(v, true);
let SAVING = Promise.resolve();

async function openBill(id, step) {
  try { IPA.bill = await GET(`/store/est/ipa/bill/${id}`); } catch (e) { return fail(e); }
  try { IPA.people = (await GET("/store/est/ipa/signatures")).people; } catch (e) { IPA.people = []; }
  try { IPA.staff = (await GET("/store/est/ipa/people")).people; } catch (e) { IPA.staff = []; }
  IPA.step = step || "work"; IPA.q = ""; IPA.filter = "";
  big("", `<div class="ipa"><nav class="ipa-nav" id="ipa-nav"></nav><div class="ipa-main" id="ipa-main"></div></div>`, billsRedraw, "est.ipa");
  $("#big .bbody").classList.add("ipa-body");
  drawBill();
}
function billNo(b) { return b.bill_no_raw || b.label || b.seq; }
function lines(b) { return b.progress.flatMap(t => t.lines.map(l => Object.assign({ sheet: t.sheet }, l))); }
function nowPct(l) { return l.total === null ? null : (l.total || 0) - (l.prev || 0); }
function billFigs(b) {
  const L = lines(b);
  const sum = f => r2(L.reduce((n, l) => n + (l.amount ? l.amount * (f(l) || 0) : 0), 0));
  return { value: r2(L.reduce((n, l) => n + (l.amount || 0), 0)), prev: sum(l => l.prev), now: sum(nowPct), todate: sum(l => l.total),
           moved: L.filter(l => Math.abs(nowPct(l) || 0) > 1e-9).length, entry: L.filter(l => l.how).length,
           bad: L.filter(l => (l.total || 0) > 1.00005 || (nowPct(l) || 0) < -1e-9) };
}
function checks(b) {
  const f = billFigs(b), out = [];
  const pay = b.payments[0];
  out.push(b.has_no ? [true, `Bill number ${esc(billNo(b))}`] : [null, "This format has no bill number cell"]);
  out.push(b.has_date ? [true, `Issue date ${dt(b.issue_date)}`] : [null, "This format has no issue date cell"]);
  if (b.total_due < 0) out.push([false, `The total due is below zero (AED ${money(b.total_due, false)}) - check the % typed and the payments received`]);
  out.push(f.moved ? [true, `${f.moved} line${f.moved === 1 ? "" : "s"} moved on this month - ${money(f.now, false)} of work`] : [false, "No line has moved on since the last bill - type this month's % on Work done"]);
  if (f.bad.length) out.push([false, `${f.bad.length} line${f.bad.length === 1 ? " is" : "s are"} over 100% or below last month: ${f.bad.slice(0, 3).map(l => esc(l.item || l.desc.slice(0, 30))).join(", ")}`]);
  if (pay) {
    const open = pay.rows.filter(r => r.desc && /\d/.test(String(r.desc.value || "")) && !(r.amount && r.amount.value));
    out.push(open.length ? [false, `No amount yet for ${open.map(r => esc(r.desc.value)).join(", ")} - type it on Payments received once the money is in`] : [true, "Every earlier bill on the payments list has its amount"]);
  }
  (b.signers || []).forEach(x => { const lab = x.labels.find(l => l !== "Signature") || x.labels[0]; out.push(x.signed_at ? (x.sig ? [true, `${esc(lab)}: ${esc(x.name)} signed on ${dt(x.signed_at)}`] : [false, `${esc(lab)}: ${esc(x.name)} signed on ${dt(x.signed_at)} but has no signature picture - upload it on Cover & details`]) : [false, `${esc(lab)}: ${esc(x.name)} has not signed yet${x.turn ? " - it is their turn" : ""}`]); });
  return out;
}

function drawBill() {
  const b = IPA.bill, f = billFigs(b), ck = checks(b);
  const p = ST.b.project;
  $("#b-title").innerHTML = `<span class="ipa-ttl">Interim Bill ${esc(billNo(b))}</span> <span class="muted small">${esc(p.code)}${p.name ? " · " + esc(p.name) : ""}</span> ${st(b.status)}`;
  $("#b-tools").innerHTML = xpButtons("ipa", { id: b.id, name: `${p.code} IPA ${billNo(b)}` });
  IPA_STEPS = IPA_ALL_STEPS.filter(([k]) => k !== "fees" || (b.fees && b.fees.length));
  if (!IPA_STEPS.some(x => x[0] === IPA.step)) IPA.step = "work";
  const signed = (b.signers || []).filter(x => x.signed_at).length, nsign = (b.signers || []).length;
  const sub = { cover: `${dt(b.issue_date) || "no date"}`, work: `${f.moved} of ${f.entry} lines moved`,
                pay: b.payments.length ? `total ${money(b.payments[0].total, false)}` : "none on this format",
                fees: b.fees && b.fees.length ? `this bill ${money(b.fees[0].total, false)}` : "",
                sheets: `${b.sheets.length} sheets`,
                review: nsign ? (signed === nsign ? "approved" : `${signed} of ${nsign} signed`) : (ck.some(c => c[0] === false) ? `${ck.filter(c => c[0] === false).length} to look at` : "ready") };
  $("#ipa-nav").innerHTML = IPA_STEPS.map(([k, l], i) => `<button class="ipa-step ${IPA.step === k ? "on" : ""} ${k === "review" && ck.some(c => c[0] === false) ? "warn" : ""}" data-step="${k}">
      <span class="no">${i + 1}</span><span class="tx"><b>${l}</b><small>${sub[k]}</small></span></button>`).join("") +
    `<div class="ipa-due"><small>Total due this bill</small><b>AED ${money(b.total_due, false)}</b><small>work this month ${money(f.now, false)}</small></div>`;
  $$("#ipa-nav [data-step]").forEach(x => x.onclick = () => { IPA.step = x.dataset.step; drawBill(); $("#big .bbody").scrollTop = 0; });
  const m = $("#ipa-main");
  ({ cover: drawCover, work: drawWork, pay: ipaDrawPay, fees: drawFees, sheets: drawSheets, review: drawReview })[IPA.step](m);
}
function nextBtn(k) {
  const i = IPA_STEPS.findIndex(s => s[0] === k), n = IPA_STEPS[i + 1], pv = IPA_STEPS[i - 1];
  return `<div class="ipa-next">${pv ? `<button class="btn btn-plain" data-go="${pv[0]}">&larr; ${pv[1]}</button>` : "<span></span>"}${n ? `<button class="btn btn-primary" data-go="${n[0]}">Next: ${n[1]} &rarr;</button>` : ""}</div>`;
}
function bindNext(m) { $$("[data-go]", m).forEach(x => x.onclick = () => { IPA.step = x.dataset.go; drawBill(); $("#big .bbody").scrollTop = 0; }); }

// saving: one at a time, in the order typed
function save(body) {
  const job = SAVING.then(async () => {
    try { IPA.bill = await PUT(`/store/est/ipa/bill/${IPA.bill.id}`, body); return true; }
    catch (e) { fail(e); return false; }
  });
  SAVING = job.catch(() => {});
  return job;
}
function refreshNav() {           // the side panel's figures, without touching what is being typed
  const b = IPA.bill, f = billFigs(b);
  const due = $("#ipa-nav .ipa-due"); if (due) due.innerHTML = `<small>Total due this bill</small><b>AED ${money(b.total_due, false)}</b><small>work this month ${money(f.now, false)}</small>`;
  const w = $('#ipa-nav [data-step="work"] small'); if (w) w.textContent = `${f.moved} of ${f.entry} lines moved`;
}

// ---------------------------------------------------------------- 1. cover & details
function drawCover(m) {
  const b = IPA.bill, c = b.cover, p = ST.b.project, fx = (c && c.facts) || {};
  m.innerHTML = `<div class="ipa-card ipa-cover">
      <div class="ipa-cv-head"><div class="k">Interim payment application</div><div class="t">${esc(fx.project || p.name || p.code)}</div>${fx.location ? `<div class="s">${esc(fx.location)}</div>` : ""}</div>
      <div class="ipa-cv-grid">
        <label>Interim bill no.<input id="cv-no" value="${esc(billNo(b))}" ${b.has_no ? "" : "disabled"}></label>
        <label>Issue date<input id="cv-date" type="date" value="${esc(b.issue_date || "")}" ${b.has_date ? "" : "disabled"}></label>
        <label>Client<div class="ro">${esc(fx.client || p.client || "-")}</div></label>
        <label>Consultant<div class="ro">${esc(fx.consultant || p.consultant || "-")}</div></label>
      </div>
      ${c && c.rows.length ? `<table class="ipa-sum" data-nofreeze><thead><tr><th>Payment summary</th><th class="r">Amount (AED)</th></tr></thead><tbody>
        ${c.rows.map(r => `<tr class="${r.total ? "tot" : ""}"><td>${esc(r.label)}${r.detail ? `<div class="d">${esc(r.detail)}</div>` : ""}</td><td class="r">${r.amount === null ? "" : money(r.amount, false)}</td></tr>`).join("")}
      </tbody></table>${c.words ? `<div class="ipa-words">${esc(c.words)}</div>` : ""}` : `<div class="muted">The cover's payment summary could not be found on this format.</div>`}
      <div class="ipa-cv-note muted small">Worked out by the consultant's own formulas from Work done and Payments received. The printed cover keeps the consultant's layout, logo and stamps.</div>
    </div>
    ${signersCard(b)}
    <div class="ipa-card"><h3>Notes <span class="muted small">(for the office - not printed)</span></h3><textarea id="cv-notes" rows="2" placeholder="e.g. sent to consultant by email, waiting for site measurement">${esc(b.notes)}</textarea></div>
    ${nextBtn("cover")}`;
  bindNext(m);
  bindSigners(m);
  const no = $("#cv-no"), d = $("#cv-date");
  no.onchange = async () => { if (no.value.trim() && await save({ bill_no: no.value.trim() })) { toast("Bill number saved"); drawBill(); } };
  d.onchange = async () => { if (d.value && await save({ issue_date: d.value })) { toast("Issue date saved"); drawBill(); } };
  $("#cv-notes").onchange = async e => { if (await save({ notes: e.target.value })) toast("Notes saved"); };
}

// the same person written two ways ("Anoop S" / "ANOOP SUBRAMANIAN", "Shafiq" / "Shafeeq") - as the server decides
function samePerson(a, b) {
  const toks = x => String(x || "").toLowerCase().split(/[^a-z]+/).filter(t => t && !["mr", "mrs", "ms", "miss", "dr", "eng", "engr"].includes(t));
  const skel = t => { t = t.replace(/k/g, "q").replace(/ph/g, "f"); return (t[0] + t.slice(1).replace(/[aeiouy]/g, "")).replace(/(.)\1+/g, "$1"); };
  const ta = toks(a), tb = toks(b);
  if (!ta.length || !tb.length) return false;
  if (ta.join(" ") === tb.join(" ")) return true;
  const [sh, lg] = ta.length <= tb.length ? [ta, tb] : [tb, ta];
  const pool = lg.slice(); let whole = false;
  for (const t of sh) {
    let hit = -1;
    for (let i = 0; i < pool.length; i++) {
      const u = pool[i];
      if (t === u || (t.length > 2 && u.length > 2 && skel(t) === skel(u))) { hit = i; whole = true; break; }
      if ((t.length === 1 && u.startsWith(t)) || (u.length === 1 && t.startsWith(u))) { hit = i; break; }
    }
    if (hit < 0) return false;
    pool.splice(hit, 1);
  }
  return whole;
}

// who prepares / checks / approves: the full name and designation printed on the bill, and the person's signature
function signersCard(b) {
  if (!b.signers || !b.signers.length) return "";
  const staff = IPA.staff || [];
  const names = [...new Set(staff.map(x => x.name).concat((IPA.people || []).map(x => x.name)).filter(Boolean))];
  const who = n => staff.find(p => samePerson(p.name, n));
  return `<div class="ipa-card"><h3>Prepared, checked and approved by</h3>
    <div class="muted small" style="margin-bottom:10px">Who prepares, checks and approves this bill - the names and designations printed on it. Pick or type the full name; a signature uploaded once is kept for that person. It is printed only after they sign on Approve &amp; send, each in turn. Next month's bill keeps the same people.</div>
    <datalist id="ipa-people">${names.map(n => { const p = staff.find(x => x.name === n); return `<option value="${esc(n)}">${p ? esc(p.designation) : ""}</option>`; }).join("")}</datalist>
    <div class="ipa-tw"><table class="ipa-sg" data-nofreeze><thead><tr><th>Signs as</th><th>Full name</th><th>Designation</th><th>Signature</th><th></th></tr></thead><tbody>
    ${b.signers.map(g => `<tr data-sg="${esc(g.key)}"><td><b>${esc(g.labels.join(" / "))}</b><div class="muted small">${esc(g.sheets.join(", "))}</div></td>
      <td><input class="ipa-sgn" list="ipa-people" value="${esc(g.name)}" data-noclear data-spell="off" autocomplete="off" placeholder="Pick from the staff register">${(() => { const p = who(g.name);
        return p ? `<div class="small ${p.login ? "muted" : "ipa-warn"}">Staff register: ${esc(p.name)} - ${esc(p.short || p.designation)}${p.login ? ` · login <b>${esc(p.login)}</b>` : " · no login, cannot sign"}</div>` : `<div class="small ipa-warn">Not in the staff register${g.step === 0 ? "" : " - cannot sign"}</div>`; })()}</td>
      <td><input class="ipa-sgt" value="${esc(g.title || "")}" data-noclear></td>
      <td class="sig">${g.sig ? `<img src="${g.sig}" alt="signature">` : `<span class="muted small">${g.format_has ? "none for this person" : "none"}</span>`}${g.sig && !g.own ? `<div class="muted small">from the format</div>` : ""}</td>
      <td class="r"><label class="btn btn-plain btn-sm">${g.own ? "Change signature" : "Upload signature"}<input type="file" accept="image/*" class="ipa-sgf" hidden></label></td></tr>`).join("")}
    </tbody></table></div></div>`;
}
function bindSigners(m) {
  $$("tr[data-sg]", m).forEach(tr => {
    const k = tr.dataset.sg, n = $(".ipa-sgn", tr), t = $(".ipa-sgt", tr), f = $(".ipa-sgf", tr);
    const push = async () => {
      if (!n.value.trim()) { toast("Type the full name", { err: true }); return; }
      if (await save({ signs: { [k]: { name: n.value.trim(), title: t.value.trim() } } })) { toast("Saved - printed on the bill"); drawBill(); }
    };
    n.onchange = () => {
      const was = (IPA.bill.signers.find(x => x.key === k) || {}).name || "";
      const sp = (IPA.staff || []).find(x => samePerson(x.name, n.value.trim()));
      const pp = (IPA.people || []).find(x => samePerson(x.name, n.value.trim()));
      if (!samePerson(was, n.value.trim())) {          // another person: their designation from the staff register
        if (pp && pp.title) t.value = pp.title; else if (sp && sp.designation) t.value = sp.designation;
      }
      push();
    };
    t.onchange = push;
    f.onchange = async () => {
      const file = f.files[0]; if (!file) return;
      if (!n.value.trim()) { toast("Type the full name first", { err: true }); return; }
      const fd = new FormData(); fd.append("name", n.value.trim()); fd.append("title", t.value.trim()); fd.append("file", file);
      try {
        toast("Uploading the signature...");
        await api("/store/est/ipa/signature", { method: "POST", body: fd });
        IPA.people = (await GET("/store/est/ipa/signatures")).people;
        await save({ signs: { [k]: { name: n.value.trim(), title: t.value.trim() } } });
        toast("Signature saved - the paper's white is taken out"); drawBill();
      } catch (e) { fail(e); }
    };
  });
}

// ---------------------------------------------------------------- 2. work done
function drawWork(m) {
  const b = IPA.bill;
  const secSum = t => {
    const s = f => r2(t.lines.reduce((n, l) => n + (l.amount ? l.amount * (f(l) || 0) : 0), 0));
    const v = r2(t.lines.reduce((n, l) => n + (l.amount || 0), 0));
    return { v, prev: s(l => l.prev), now: s(nowPct), td: s(l => l.total) };
  };
  m.innerHTML = `
    <div class="ipa-card ipa-intro"><b>Type this month's progress.</b> For each line type either <b>This month %</b> or the new <b>Total %</b> - the other works itself out.
      <span class="muted">Enter or &darr; goes to the next line, &uarr; back. Previous % is last bill's Total %. Amounts are worked out by the consultant's formulas.</span></div>
    <div class="ipa-card"><div class="ipa-tw"><table class="ipa-secs" data-nofreeze><thead><tr><th>Section</th><th class="r">Value</th><th class="r">Previous</th><th class="r">This month</th><th class="r">To date</th><th class="r">Done</th></tr></thead><tbody>
      ${b.progress.map((t, i) => { const s = secSum(t); return `<tr data-jump="${i}"><td><a>${esc(t.sheet)}</a> <span class="muted small">${t.lines.length} lines${t.hidden ? " · hidden, not printed" : ""}</span></td><td class="r">${money(s.v, false)}</td><td class="r">${money(s.prev, false)}</td><td class="r ${s.now ? "b" : ""}">${amt(s.now)}</td><td class="r">${money(s.td, false)}</td><td class="r">${s.v ? Math.round(100 * s.td / s.v) + "%" : "-"}</td></tr>`; }).join("")}
      ${(() => { const f = billFigs(b); return `<tr class="tot"><td>All sections</td><td class="r">${money(f.value, false)}</td><td class="r">${money(f.prev, false)}</td><td class="r">${money(f.now, false)}</td><td class="r">${money(f.todate, false)}</td><td class="r">${f.value ? Math.round(100 * f.todate / f.value) + "%" : "-"}</td></tr>`; })()}
    </tbody></table></div></div>
    <div class="ipa-bar"><input class="q" id="ipa-q" placeholder="Search item or description" value="${esc(IPA.q)}">
      <span class="chips">${[["", "All lines"], ["open", "Not yet 100%"], ["moved", "Moved this month"]].map(([k, l]) => `<span class="chip ${IPA.filter === k ? "on" : ""}" data-flt="${k}">${l}</span>`).join("")}</span></div>
    <div id="ipa-secs">${b.progress.map((t, i) => workSection(t, i)).join("")}</div>
    ${nextBtn("work")}`;
  bindNext(m);
  $$("[data-jump]", m).forEach(r => r.onclick = () => { const s = $(`#ipa-sec-${r.dataset.jump}`); if (s) s.scrollIntoView({ behavior: "smooth", block: "start" }); });
  const qi = $("#ipa-q", m);
  qi.oninput = debounce(() => { IPA.q = qi.value; $("#ipa-secs").innerHTML = b.progress.map((t, i) => workSection(t, i)).join(""); bindWork(m); }, 200);
  $$("[data-flt]", m).forEach(c => c.onclick = () => { IPA.filter = c.dataset.flt; drawWork(m); });
  bindWork(m);
}
function lineShown(l) {
  const q = IPA.q.trim().toLowerCase();
  if (q && !(`${l.item} ${l.desc}`).toLowerCase().includes(q)) return false;
  if (IPA.filter === "open") return l.how && (l.total || 0) < 0.99995;
  if (IPA.filter === "moved") return Math.abs(nowPct(l) || 0) > 1e-9;
  return true;
}
function canEditBill() { return !(IPA.bill.status === "Paid" && !ST.meta.me.admin); }
function workSection(t, i) {
  const shown = t.lines.filter(l => (l.item || l.desc || l.amount || l.added) && lineShown(l));
  if (!shown.length && (IPA.q || IPA.filter)) return "";
  const ed = t.editable && canEditBill();
  // the section's headings in between (3.1.1 Concrete ..., a section added on the bill) - not while searching
  const heads = IPA.q || IPA.filter ? [] : (t.heads || []);
  // a heading with only one line under it is shown as that one line, under the heading's own item and name
  // ("D  BLOCK WORKS 269,013.00"), as the bill itself reads - not the heading and then "33 200mm thick Solid blocks"
  const all = shown.map(l => ({ r: l.r, l })).concat(heads.map(h => ({ r: h.r, hd: h }))).sort((a, b) => a.r - b.r);
  const rows = [];
  for (let k = 0; k < all.length; k++) {
    const x = all[k];
    if (x.hd) {
      let n = 0, j = k + 1; while (j < all.length && !all[j].hd) { n++; j++; }
      // not for a cost proposal / variation order: its heading is only a number ("COST PROPOSAL - 01"), the line says what it is
      const generic = /\b(cost\s*proposal|variation|v\.?\s*o\.?\b|change\s*order|c\.?\s*p\.?\s*-?\s*\d|addendum|additional\s+work|extra\s+work)/i.test(x.hd.desc || "");
      const lettered = n === 1 && /^[A-Za-z][.)]?$/.test(String(all[k + 1].l.item || "").trim());
      if (n === 1 && !x.hd.added && !generic && !lettered) { const l = all[k + 1].l; rows.push({ r: x.r, h: lineRow(t.sheet, l, ed, x.hd) }); k++; continue; }
      rows.push({ r: x.r, h: headRow(t.sheet, x.hd, ed) });
    } else rows.push({ r: x.r, h: lineRow(t.sheet, x.l, ed) });
  }
  return `<div class="ipa-card ipa-sec ${t.hidden ? "hid" : ""}" id="ipa-sec-${i}"><div class="ipa-sec-h"><h3>${esc(t.sheet)}${t.hidden ? ` <span class="st">hidden sheet - not printed</span>` : ""}</h3>
      ${ed ? `<span class="ipa-sec-add"><button class="btn btn-ghost btn-sm" data-addln="${esc(t.sheet)}" title="A new item or variation at the end of ${esc(t.sheet)}">+ Line</button><button class="btn btn-ghost btn-sm" data-addsec="${esc(t.sheet)}" title="A heading at the end of ${esc(t.sheet)}, to put new lines under">+ Section</button></span>` : ""}</div>
    <div class="ipa-tw"><table class="ipa-lines"><colgroup><col style="width:72px"><col><col style="width:124px"><col style="width:112px"><col style="width:142px"><col style="width:118px"><col style="width:132px"><col style="width:124px">${ed ? '<col style="width:40px">' : ""}</colgroup>
    <thead><tr><th>Item</th><th>Description</th><th class="r">Amount</th><th class="c">Previous</th><th class="c in">This month %</th><th class="c in">Total %</th><th class="r">This month</th><th class="r">To date</th>${ed ? "<th></th>" : ""}</tr></thead>
    <tbody>${rows.map(x => x.h).join("") || `<tr><td colspan="${ed ? 9 : 8}" class="muted c">No lines match.</td></tr>`}</tbody></table></div></div>`;
}
function headRow(sh, h, ed) {
  return `<tr class="hd" data-head="${esc(sh + "|" + h.r)}"><td class="it">${esc(h.item)}</td><td class="ds" colspan="7"><span class="hd-t">${esc(h.desc)}${h.added ? ' <span class="new-tag">added</span>' : ""}</span></td>
    ${ed ? `<td class="act"><button class="ln-menu" data-menu="${esc(sh + "|" + h.r)}" data-kind="head" title="Section: edit, add a line under it">&#8942;</button></td>` : ""}</tr>`;
}
function lineCells(l) {
  const now = nowPct(l);
  return { prev: l.prev === null ? "" : pctTxt(l.prev), nowAmt: l.amount && now ? money(l.amount * now) : '<span class="muted">-</span>',
           td: l.amount && l.total ? money(l.amount * l.total) : '<span class="muted">-</span>', now, cls: (l.total || 0) > 1.00005 || (now || 0) < -1e-9 ? "bad" : (Math.abs(now || 0) > 1e-9 ? "moved" : "") };
}
const pnum = v => v === null || v === undefined ? "" : String(Math.round(v * 1e6) / 1e4);
const pnow = v => v === null || v === undefined || Math.abs(v) < 1e-9 ? "" : pnum(v);          // nothing this month: left empty
function lineRow(sh, l, ed, hd) {
  const c = lineCells(l), id = `${sh}|${l.r}`, paid = IPA.bill.status === "Paid" && !ST.meta.me.admin;
  const edit = l.how && !paid;
  const inp = (k, v) => edit ? `<input class="ipa-in" data-noclear data-row="${esc(id)}" data-w="${k}" value="${k === "now" ? pnow(v) : pnum(v)}" placeholder="0" inputmode="decimal" autocomplete="off"><span class="pc">%</span>` : `<span class="ro">${v === null ? "" : pctTxt(v)}</span>`;
  if (hd) return `<tr class="${c.cls} one" data-line="${esc(id)}" data-head="${esc(sh + "|" + hd.r)}"><td class="it"><b>${esc(hd.item)}</b></td>
    <td class="ds" title="${esc([l.item, l.desc].filter(Boolean).join(" "))}"><b>${esc(hd.desc)}</b>${l.added ? ' <span class="new-tag">added</span>' : ""}${!l.how && l.follows ? followsLink(sh, l) : ""}${brkBtn(id, l, hd)}</td>
    <td class="r" data-l="Amount">${l.amount !== null ? money(l.amount, false) : `<span class="muted small">${esc(l.amount_text || "-")}</span>`}</td>
    <td class="c muted" data-c="prev" data-l="Previous">${c.prev}</td>
    <td class="c in" data-c="now" data-l="This month %">${inp("now", c.now)}</td>
    <td class="c in" data-c="tot" data-l="Total %">${inp("tot", l.total)}</td>
    <td class="r" data-c="nowAmt" data-l="This month">${c.nowAmt}</td><td class="r" data-c="td" data-l="To date">${c.td}</td>
    ${ed ? `<td class="act"><button class="ln-menu" data-menu="${esc(id)}" data-kind="line" title="Line: edit its details, add a line or section below">&#8942;</button></td>` : ""}</tr>${brkRow(id, l, hd, ed)}`;
  return `<tr class="${c.cls}" data-line="${esc(id)}"><td class="it">${esc(l.item)}</td>
    <td class="ds">${esc(l.desc) || '<span class="muted">(no description)</span>'}${l.added ? ' <span class="new-tag">added</span>' : ""}${l.unit && !/^(item|ls|l\.s\.?|lump ?sum)$/i.test(l.unit.trim()) ? ` <span class="muted small">(${esc(l.unit)})</span>` : ""}${!l.how && l.follows ? followsLink(sh, l) : ""}${brkBtn(id, l)}</td>
    <td class="r" data-l="Amount">${l.amount !== null ? money(l.amount, false) : `<span class="muted small">${esc(l.amount_text || "-")}</span>`}</td>
    <td class="c muted" data-c="prev" data-l="Previous">${c.prev}</td>
    <td class="c in" data-c="now" data-l="This month %">${inp("now", c.now)}</td><td class="c in" data-c="tot" data-l="Total %">${inp("tot", l.total)}</td>
    <td class="r" data-c="nowAmt" data-l="This month">${c.nowAmt}</td><td class="r" data-c="td" data-l="To date">${c.td}</td>
    ${ed ? `<td class="act"><button class="ln-menu" data-menu="${esc(id)}" data-kind="line" title="Line: edit its details, add a line or section below">&#8942;</button></td>` : ""}</tr>${brkRow(id, l, null, ed)}`;
}
// the break-up the consultant lists under a lump-sum line without pricing it (SITE WORKS = 1 Clearance of site,
// 2 Density test ...): shown on a click, for reading only - the line is still billed by its own %
function brkList(l, hd) {
  const own = hd && (l.item || l.desc) ? [{ item: l.item, desc: l.desc, sub: false }] : [];
  const p = own.concat(l.parts || []);
  return (l.parts || []).length >= (hd ? 1 : 2) ? p : [];
}
function brkBtn(id, l, hd) {
  const p = brkList(l, hd); if (!p.length) return "";
  const n = p.filter(x => !x.sub).length || p.length;
  return `<button type="button" class="brk-btn" data-brk="${esc(id)}" aria-expanded="false"><span class="ar">&#9656;</span> Break-up &middot; ${n} item${n === 1 ? "" : "s"}</button>`;
}
function brkRow(id, l, hd, ed) {
  const p = brkList(l, hd); if (!p.length) return "";
  return `<tr class="brk-row" data-brkof="${esc(id)}" hidden><td colspan="${ed ? 9 : 8}"><table class="brk-t">${p.map(x => x.sub
    ? `<tr class="sub"><td></td><td>${esc(x.desc)}</td></tr>` : `<tr><td>${esc(x.item)}</td><td>${esc(x.desc)}</td></tr>`).join("")}</table></td></tr>`;
}
function followsLink(sh, l) {     // "follows the line on row 21" -> a link that takes you to that line
  const m = l.follows.match(/row (\d+)$/), o = l.follows.match(/^set on the (.+) sheet$/);
  if (m) {
    const t = IPA.bill.progress.find(x => x.sheet === sh), tl = t && t.lines.find(x => x.r === +m[1]);
    const txt = tl && tl.item ? `follows item ${tl.item} (row ${m[1]})` : l.follows;
    return `<a class="fl" href="#" data-goto="${esc(sh + "|" + m[1])}" title="Go to row ${m[1]}">${esc(txt)} &rarr;</a>`;
  }
  if (o && IPA.bill.progress.some(x => x.sheet === o[1])) return `<a class="fl" href="#" data-gosec="${esc(o[1])}" title="Go to the ${esc(o[1])} sheet">${esc(l.follows)} &rarr;</a>`;
  return `<div class="fl">${esc(l.follows)}</div>`;
}
function gotoLine(id) {
  let tr = $(`#ipa-secs tr[data-line="${CSS.escape(id)}"]`);
  if (!tr && (IPA.q || IPA.filter)) {          // hidden by the search or a filter: clear them first
    IPA.q = ""; IPA.filter = ""; drawWork($("#ipa-secs").parentElement);
    tr = $(`#ipa-secs tr[data-line="${CSS.escape(id)}"]`);
  }
  if (!tr) { toast(`Row ${id.slice(id.lastIndexOf("|") + 1)} is a heading or total in the sheet, not a line you type`, { ms: 3500 }); return; }
  tr.scrollIntoView({ behavior: "smooth", block: "center" });
  tr.classList.remove("flash"); void tr.offsetWidth; tr.classList.add("flash");
  setTimeout(() => tr.classList.remove("flash"), 2200);
  const inp = $("input.ipa-in", tr); if (inp) setTimeout(() => inp.focus({ preventScroll: true }), 450);
}
function findLine(id) { const [sh, r] = [id.slice(0, id.lastIndexOf("|")), +id.slice(id.lastIndexOf("|") + 1)]; const t = IPA.bill.progress.find(x => x.sheet === sh); return t && { sh, l: t.lines.find(x => x.r === r) }; }
function patchWork() {           // new figures in place: no redraw, so typing carries on
  $$("#ipa-secs tr[data-line]").forEach(tr => {
    const f = findLine(tr.dataset.line); if (!f || !f.l) return;
    const c = lineCells(f.l);
    tr.className = c.cls;
    $('[data-c="prev"]', tr).innerHTML = c.prev; $('[data-c="nowAmt"]', tr).innerHTML = c.nowAmt; $('[data-c="td"]', tr).innerHTML = c.td;
    $$("input.ipa-in", tr).forEach(i => { if (i !== document.activeElement) i.value = i.dataset.w === "now" ? pnow(c.now) : pnum(f.l.total); });
  });
  refreshNav();
}
function bindWork(m) {
  const secs = $("#ipa-secs", m);
  if (secs) secs.onclick = e => {
    const mb = e.target.closest("[data-menu]"); if (mb) { e.stopPropagation(); return lineMenu(mb); }
    const al = e.target.closest("[data-addln]"); if (al) return lineForm(al.dataset.addln, { kind: "line" });
    const as = e.target.closest("[data-addsec]"); if (as) return lineForm(as.dataset.addsec, { kind: "head" });
    const bk = e.target.closest("[data-brk]");
    if (bk) { const r = secs.querySelector(`tr[data-brkof="${CSS.escape(bk.dataset.brk)}"]`); if (r) { r.hidden = !r.hidden; bk.setAttribute("aria-expanded", String(!r.hidden)); } return; }
    const a = e.target.closest("a[data-goto], a[data-gosec]"); if (!a) return;
    e.preventDefault();
    if (a.dataset.goto) return gotoLine(a.dataset.goto);
    const i = IPA.bill.progress.findIndex(x => x.sheet === a.dataset.gosec), sec = $(`#ipa-sec-${i}`);
    if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const all = () => $$("input.ipa-in", m);
  all().forEach(inp => {
    inp.dataset.was = inp.value;
    inp.onfocus = () => { inp.dataset.was = inp.value; setTimeout(() => inp.select(), 0); };
    const move = d => { const a = all(), i = a.indexOf(inp); const col = a.filter(x => x.dataset.w === inp.dataset.w); const j = col.indexOf(inp) + d; if (col[j]) col[j].focus(); else inp.blur(); };          // the last line: Enter saves it
    inp.onkeydown = e => {
      if (e.key === "Enter" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Escape") { e.stopPropagation(); inp.value = inp.dataset.was; inp.blur(); }
    };
    inp.onblur = () => commitLine(inp);
  });
}
// ---- a line's own details, and lines / sections put in on the bill
function closeLineMenu() { const x = document.getElementById("ln-pop"); if (x) x.remove(); document.removeEventListener("mousedown", lineMenuOut, true); }
function lineMenuOut(e) { if (!e.target.closest("#ln-pop") && !e.target.closest("[data-menu]")) closeLineMenu(); }
function lineMenu(btn) {
  const open = document.getElementById("ln-pop"), same = open && open.dataset.for === btn.dataset.menu;
  closeLineMenu(); if (same) return;
  const id = btn.dataset.menu, sh = id.slice(0, id.lastIndexOf("|")), r = +id.slice(id.lastIndexOf("|") + 1), head = btn.dataset.kind === "head";
  const t = IPA.bill.progress.find(x => x.sheet === sh); if (!t) return;
  const it = head ? (t.heads || []).find(h => h.r === r) : t.lines.find(l => l.r === r); if (!it) return;
  const pop = document.createElement("div"); pop.id = "ln-pop"; pop.className = "ln-pop"; pop.dataset.for = id;
  pop.innerHTML = `<button data-do="edit">${head ? "Edit section" : "Edit line details"}</button>
    <button data-do="line">Add line below</button><button data-do="head">Add section below</button>
    ${it.can_remove ? `<hr><button data-do="del" class="danger">${head ? "Remove section" : "Remove line"}</button>` : ""}`;
  document.body.appendChild(pop);
  const rc = btn.getBoundingClientRect(), pw = pop.offsetWidth, ph = pop.offsetHeight;
  pop.style.left = Math.max(8, Math.min(innerWidth - pw - 8, rc.right - pw)) + "px";
  pop.style.top = (rc.bottom + ph + 6 > innerHeight ? rc.top - ph - 4 : rc.bottom + 4) + "px";
  setTimeout(() => document.addEventListener("mousedown", lineMenuOut, true), 0);
  pop.onclick = async e => {
    const d = e.target.closest("[data-do]"); if (!d) return;
    closeLineMenu();
    if (d.dataset.do === "edit") return lineForm(sh, { kind: head ? "head" : "line", edit: it });
    if (d.dataset.do === "line" || d.dataset.do === "head") return lineForm(sh, { kind: d.dataset.do, after: r });
    const what = head ? `the section ${it.item || ""} ${it.desc || ""}` : `the line ${it.item || ""} ${it.desc || ""}`;
    if (!(await confirmDelete(`Remove ${what.replace(/\s+/g, " ").trim()}?`, "It was added on this bill and has not been billed - it comes out of the bill and its totals."))) return;
    try { IPA.bill = await POST(`/store/est/ipa/bill/${IPA.bill.id}/line/remove`, { sheet: sh, r }); redrawWork(); toast(head ? "Section removed" : "Line removed"); } catch (er) { fail(er); }
  };
}
function redrawWork(focus) {
  const m = $("#ipa-main"), sc = $("#big .bbody"), y = sc ? sc.scrollTop : 0;
  drawBill(); if (sc) sc.scrollTop = y;
  if (focus && IPA.step === "work") setTimeout(() => gotoLine(focus), 60);
}
// one form for a new line / section and for a line's own details. The fields are the table's own columns:
// Item, Description, Unit, and the Amount - or QTY and RATE where the sheet works the amount out from them.
function lineForm(sh, o) {
  const t = IPA.bill.progress.find(x => x.sheet === sh); if (!t) return;
  const head = o.kind === "head", ed = o.edit;
  const after = o.after || Math.max(0, ...t.lines.map(l => l.r), ...(t.heads || []).map(h => h.r));
  const model = ed ? ed : (t.lines.filter(l => l.r <= after).pop() || t.lines[0]);        // the line a new one is modelled on
  const src = (model && model.fields) || [];
  let fl = head ? src.filter(f => f.f === "item" || f.f === "desc") : src;
  if (head && !fl.length) fl = [{ f: "desc", label: "Section name", value: "", edit: true }];
  const worked = !head && src.some(f => f.f === "amount" && !f.edit);
  const label = f => head && f.f === "desc" ? "Section name" : (f.f === "item" ? (head ? "Ref. (optional)" : "Item / ref.") : f.label);
  const fields = fl.filter(f => f.edit || (ed && f.f === "amount")).map(f => ({
    k: f.f, label: label(f) + (f.f === "amount" && worked ? " (worked out)" : ""), value: ed ? (f.value ?? "") : "",
    type: f.num && f.edit ? "num" : undefined, ro: !f.edit, full: f.f === "desc", focus: f.f === "desc",
    ph: f.f === "item" ? (head ? "e.g. 3.3" : "e.g. V07 or 3.2.2.3") : f.f === "desc" ? (head ? "e.g. Additional works" : "What the work is") : f.f === "unit" ? "M3, M2, Nos..." : (f.f === "amount" && worked ? "" : "0.00") }));
  if (!fields.length) { toast("This sheet's lines have nothing that can be typed here - use Sheets", { err: true }); return; }
  const ttl = ed ? (head ? "Edit section" : `Edit line ${ed.item || ""}`.trim()) : (head ? `New section - ${sh}` : `New line - ${sh}`);
  const nearTxt = !ed && model ? `<div class="muted small" style="margin-bottom:10px">${head ? "A heading" : "A new line"} after ${esc((t.lines.concat(t.heads || []).find(x => x.r === after) || {}).item || ("row " + after))}${head ? " - add lines under it next." : ` - it works like ${esc(model.item || "the line above")} (${worked ? "amount = " + fl.filter(f => /^c\d+$/.test(f.f)).map(f => f.label).join(" x ") + ", " : ""}starts at 0%). The totals take it in.`}</div>` : "";
  modal(ttl, fields, async x => {
    const vals = {};
    fl.forEach(f => { if (!f.edit) return; const v = x[f.f]; vals[f.f] = typeof v === "string" ? v.trim() : v; });
    if (ed) {
      const set = {};
      fl.forEach(f => {
        if (!f.edit) return;
        let v = vals[f.f];
        if (String(v ?? "") === String(f.value ?? "")) return;
        if (f.num) { v = v === "" || v === null || v === undefined ? null : (String(v).trim().startsWith("=") ? String(v).trim() : Number(String(v).replace(/,/g, ""))); if (typeof v === "number" && isNaN(v)) throw new Error(`${f.label}: type a number`); }
        set[f.k] = v;
      });
      if (!Object.keys(set).length) return;
      IPA.bill = await PUT(`/store/est/ipa/bill/${IPA.bill.id}`, { set: { [sh]: set } });
      redrawWork(head ? null : `${sh}|${ed.r}`); toast("Saved");
      return;
    }
    if (!vals.desc && !vals.item) throw new Error(head ? "Type the section's name" : "Type the description");
    const res = await POST(`/store/est/ipa/bill/${IPA.bill.id}/line`, { sheet: sh, kind: head ? "head" : "line", after, values: vals });
    IPA.bill = res; IPA.q = ""; IPA.filter = "";
    redrawWork(head ? null : `${sh}|${res.added_row}`);
    if (head && IPA.step === "work") setTimeout(() => { const tr = $(`tr[data-head="${CSS.escape(sh + "|" + res.added_row)}"]`); if (tr) { tr.scrollIntoView({ behavior: "smooth", block: "center" }); tr.classList.add("flash"); } }, 60);
    toast(head ? "Section added - add its lines with the ⋮ next to it" : "Line added - type its % now");
  }, { save: ed ? "Save" : (head ? "Add section" : "Add line"), top: nearTxt });
}

async function commitLine(inp) {
  const s = inp.value.trim().replace(/%$/, "").replace(/,/g, "");
  if (s === inp.dataset.was) return;
  const f = findLine(inp.dataset.row); if (!f) return;
  const l = f.l, prev = l.prev || 0;
  let n = s === "" ? 0 : Number(s);
  if (isNaN(n)) { toast("Type a number, e.g. 15", { err: true }); inp.value = inp.dataset.was; return; }
  let total = inp.dataset.w === "now" ? prev + n / 100 : n / 100;
  total = Math.round(total * 1e8) / 1e8;
  if (total > 1.00005) { toast(`That takes ${l.item || "the line"} to ${pctTxt(total)} - the total cannot go over 100%`, { err: true }); inp.value = inp.dataset.was; inp.focus(); return; }
  if (total < -1e-9) { toast("The total cannot be below 0%", { err: true }); inp.value = inp.dataset.was; return; }
  if (total < prev - 1e-9 && !inp.dataset.ok) toast(`Less than last bill's ${pctTxt(prev)} - saved as a reduction`, { ms: 3500 });
  inp.dataset.was = inp.value;
  // optimistic: show at once, then the consultant's own figures when they come back
  l.total = total; patchWork();
  const t = IPA.bill.progress.find(x => x.sheet === f.sh);
  const val = l.how === "cur" ? Math.round((total - prev) * 1e8) / 1e8 : total;
  const key = l.how === "cur" ? l.cur_key : l.tot_key;
  inp.closest("tr").classList.add("saving");
  const ok = await save({ set: { [f.sh]: { [key]: val } } });
  const tr = $(`tr[data-line="${CSS.escape(inp.dataset.row)}"]`);
  if (tr) tr.classList.remove("saving");
  if (ok) patchWork(); else { IPA.bill = await GET(`/store/est/ipa/bill/${IPA.bill.id}`); patchWork(); }
}

// ---------------------------------------------------------------- 3. payments received
function serialToIso(v) { return new Date(Date.UTC(1899, 11, 30) + Math.round(v) * 864e5).toISOString().slice(0, 10); }
function isoToSerial(s) { const [y, mo, d] = s.split("-").map(Number); return Math.round((Date.UTC(y, mo - 1, d) - Date.UTC(1899, 11, 30)) / 864e5); }
function textToIso(s) {
  const m = String(s || "").trim().match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$/);
  if (!m) return "";
  const y = +m[3] < 100 ? 2000 + +m[3] : +m[3];
  return `${y}-${String(m[2]).padStart(2, "0")}-${String(m[1]).padStart(2, "0")}`;
}
function cellIso(x) {
  if (!x) return "";
  if (typeof x.value === "number" && x.value > 20000 && x.value < 80000) return serialToIso(x.value);
  return textToIso(x.value) || textToIso(x.raw);
}
function ipaDrawPay(m) {
  const b = IPA.bill;
  if (!b.payments.length) { m.innerHTML = `<div class="ipa-card empty">This format has no table of previous payments.</div>${nextBtn("pay")}`; bindNext(m); return; }
  const head = { desc: "Bill", submitted: "Submitted on", certified: "Certified on", received: "Received on", amount: "Amount (AED)" };
  m.innerHTML = `<div class="ipa-card ipa-intro"><b>Money received for earlier bills.</b> When a payment comes in, type the amount as the consultant counts it (usually without VAT and authority fees).
      You can type a sum such as <b>(989148-280)/1.05</b> - it is worked out and shown as money.</div>` +
    b.payments.map((p, pi) => {
      const filled = p.rows.filter(r => p.cols.some(c => r[c] && r[c].value !== null && r[c].value !== "" && r[c].value !== 0));
      const spare = p.rows.filter(r => !filled.includes(r));
      const show = filled.concat(IPA.addRow === pi && spare[0] ? [spare[0]] : []);
      const canDel = !(IPA.bill.status === "Paid" && !ST.meta.me.admin);
      return `<div class="ipa-card"><h3>${esc(p.sheet)}</h3><div class="ipa-tw"><table class="ipa-pay"><thead><tr><th style="width:34px">#</th>${p.cols.map(c => `<th class="${c === "amount" ? "r" : ""}">${head[c] || c}</th>`).join("")}${canDel ? '<th style="width:40px"></th>' : ""}</tr></thead><tbody>
        ${show.map((r, i) => `<tr>${`<td class="muted">${i + 1}</td>`}${p.cols.map(c => payCell(p, r, c)).join("")}${canDel ? `<td class="r"><button class="btn btn-ghost btn-sm" data-paydel="${pi}:${r.r}" title="Delete this line from the payment summary">&#10005;</button></td>` : ""}</tr>`).join("")}
        <tr class="tot"><td></td><td colspan="${p.cols.length - 1}">Total of previous payments</td><td class="r">${money(p.total, false)}</td>${canDel ? "<td></td>" : ""}</tr>
        </tbody></table></div>
        ${spare.length && IPA.addRow !== pi ? `<button class="btn btn-plain btn-sm" data-addpay="${pi}" style="margin-top:10px">+ Add a payment line</button>` : ""}</div>`;
    }).join("") + nextBtn("pay");
  bindNext(m);
  $$("[data-addpay]", m).forEach(x => x.onclick = () => { IPA.addRow = +x.dataset.addpay; ipaDrawPay(m); const e = $$(".ipa-pay tr:not(.tot)", m).pop(); const i = e && $("input", e); if (i) i.focus(); });
  $$("[data-pk]", m).forEach(bindPayInput);
  // Delete a line: its bill name, dates and amount are cleared on this bill (the format is not changed), so it
  // drops off the summary and out of the total; + Add a payment line brings an empty one back.
  $$("[data-paydel]", m).forEach(x => x.onclick = async () => {
    const [pi, rr] = x.dataset.paydel.split(":").map(Number), p = IPA.bill.payments[pi], r = p && p.rows.find(y => y.r === rr);
    if (!r) return;
    const name = (r.desc && r.desc.value) || "this line";
    if (!(await confirmDelete(`Delete ${esc(String(name))}?`, "It comes off this bill's payment summary and out of the total of previous payments.", "Delete"))) return;
    const set = {}; p.cols.forEach(c => { if (r[c]) set[r[c].key] = ""; });
    if (await save({ set: { [p.sheet]: set } })) {
      const sn = `${rr},1`;                         // the line's number in the first column, when it is typed
      if (!p.cols.some(c => r[c] && r[c].key === sn)) { try { await PUT(`/store/est/ipa/bill/${IPA.bill.id}`, { set: { [p.sheet]: { [sn]: "" } } }); } catch (e) {} }
      IPA.bill = await GET(`/store/est/ipa/bill/${IPA.bill.id}`);
      toast("Line deleted"); drawBill();
    }
  });
}
function payCell(p, r, c) {
  const x = r[c]; if (!x) return "<td></td>";
  const paid = IPA.bill.status === "Paid" && !ST.meta.me.admin;
  const at = `data-sh="${esc(p.sheet)}" data-pk="${x.key}" data-c="${c}"`;
  if (c === "desc") return `<td>${paid ? esc(x.value || "") : `<input class="ipa-pin wide" data-spell="off" ${at} value="${esc(x.value ?? "")}" placeholder="e.g. Payment Application No 9">`}</td>`;
  if (c === "amount") {
    const raw = x.raw === null || x.raw === undefined ? "" : String(x.raw).replace(/^=/, "");
    return `<td class="r">${paid ? money(x.value) : `<input class="ipa-pin amt" data-noclear ${at} data-raw="${esc(raw)}" value="${typeof x.value === "number" && x.value ? money(x.value, false) : ""}" placeholder="">`}</td>`;
  }
  const iso = cellIso(x);
  const asText = typeof x.raw === "string" && !String(x.raw).startsWith("=") ? (String(x.raw).match(/[./-]/) || ["."])[0] : "";
  return `<td>${paid ? (iso ? dt(iso) : esc(x.value || "")) : `<input class="ipa-pin" type="date" ${at} data-text="${esc(asText)}" value="${iso}">`}</td>`;
}
function bindPayInput(inp) {
  const c = inp.dataset.c;
  if (c === "amount") {
    inp.onfocus = () => { inp.value = inp.dataset.raw; inp.dataset.was = inp.value; setTimeout(() => inp.select(), 0); };
    inp.onblur = async () => {
      const s = inp.value.trim().replace(/^=/, "");
      if (s === inp.dataset.was) { refill(); return; }
      let v = null;
      if (s !== "") {
        const plain = s.replace(/,/g, "");
        v = /^-?\d+(\.\d+)?$/.test(plain) ? Number(plain) : "=" + plain;
      }
      const ok = await save({ set: { [inp.dataset.sh]: { [inp.dataset.pk]: v } } });
      if (ok) { toast("Payment saved"); drawBill(); } else refill();
    };
    const refill = () => { const p = IPA.bill.payments.concat(IPA.bill.fees || []).find(x => x.sheet === inp.dataset.sh && x.rows.some(rr => rr.amount && rr.amount.key === inp.dataset.pk)); const r = p && p.rows.find(rr => rr.amount && rr.amount.key === inp.dataset.pk); inp.value = r && typeof r.amount.value === "number" && r.amount.value ? money(r.amount.value, false) : ""; };
  } else if (c === "desc" || c === "ref" || c === "sn") {
    inp.onchange = async () => { const v = inp.value.trim(); const n = c === "sn" && /^\d+$/.test(v) ? Number(v) : (v || null); if (await save({ set: { [inp.dataset.sh]: { [inp.dataset.pk]: n } } })) { toast("Saved"); drawBill(); } };
  } else {
    inp.onchange = async () => {
      let v = null;
      if (inp.value) { const sep = inp.dataset.text; if (sep) { const [y, mo, d] = inp.value.split("-"); v = `${d}${sep}${mo}${sep}${y}`; } else v = isoToSerial(inp.value); }
      if (await save({ set: { [inp.dataset.sh]: { [inp.dataset.pk]: v } } })) { toast("Date saved"); refreshNav(); }
    };
  }
  inp.addEventListener("keydown", e => { if (e.key === "Escape") e.stopPropagation(); if (e.key === "Enter") inp.blur(); });
}

// ---------------------------------------------------------------- 4. review & send
// the chain: Prepared by signs first, then Checked by, then Approved by - each person on their own turn; a
// signature prints only once its owner has signed
function chainCard(b) {
  if (!b.signers || !b.signers.length) return "";
  const meName = ST.meta.me.name || "", meUser = ST.meta.me.username || "";
  return `<div class="ipa-card"><h3>Approval <span class="muted small">- each person signs in turn; the bill goes out once everyone has</span></h3>
    <ol class="ipa-chain">${b.signers.map(x => {
      const mine = ST.meta.me.admin || samePerson(meName, x.name) || samePerson(meUser, x.name);
      const state = x.signed_at ? "done" : x.turn ? "turn" : "wait";
      return `<li class="${state}"><span class="dot">${x.signed_at ? "&#10003;" : x.turn ? "&rarr;" : "&middot;"}</span>
        <div class="who"><b>${esc(x.labels.find(l => l !== "Signature") || x.labels[0])}</b><div>${esc(x.name)}${x.title ? ` <span class="muted">- ${esc(x.title)}</span>` : ""}</div>
          <div class="small muted">${x.signed_at ? `Signed on ${dt(x.signed_at)}` : x.turn ? (mine ? "Your turn to sign" : `Waiting for ${esc(x.name)} to sign`) : "After the one before"}</div></div>
        <div class="act">${x.signed_at ? (mine ? `<button class="btn btn-plain btn-sm" data-unsign="${esc(x.key)}">Take back</button>` : "")
          : x.turn && mine ? `<button class="btn btn-primary" data-sign="${esc(x.key)}">${x.step === 0 ? "Sign as prepared" : x.step >= 3 ? "Approve & sign" : "Check & sign"}</button>` : ""}</div></li>`; }).join("")}</ol>
    ${b.signers.some(x => x.turn && !(ST.meta.me.admin || samePerson(meName, x.name) || samePerson(meUser, x.name))) ? `<div class="small muted">Only the person named can sign - matched to their login through the staff register - or an admin on their behalf. They see it on their bell.</div>` : ""}</div>`;
}
function bindChain(m) {
  $$("[data-sign]", m).forEach(bt => bt.onclick = async () => {
    bt.disabled = true;
    try {
      const r = await POST(`/store/est/ipa/bill/${IPA.bill.id}/sign`, { key: bt.dataset.sign });
      IPA.bill = r;
      if (r.warn) toast(r.warn, { err: true, ms: 7000 });
      else toast(r.next ? `Signed. Now with ${r.next.name} to ${r.next.label.toLowerCase().replace(" by", "")}${r.next.has_login ? " - they see it on their bell" : " - they have no login with that name"}` : "Signed - the bill is approved", { ms: 5000 });
      drawBill();
    } catch (e) { fail(e); bt.disabled = false; }
  });
  $$("[data-unsign]", m).forEach(bt => bt.onclick = async () => {
    if (!(await confirmDelete("Take back this signature?", "The bill goes back to waiting for this person.", "Take back"))) return;
    try { IPA.bill = await POST(`/store/est/ipa/bill/${IPA.bill.id}/sign`, { key: bt.dataset.unsign, undo: true }); toast("Signing taken back"); drawBill(); } catch (e) { fail(e); }
  });
}

// ---------------------------------------------------------------- authority fees (Appendix B)
const feeCols = t => ["sn", "desc", "ref", "amount"].filter(c => t.cols.includes(c));
function drawFees(m) {
  const b = IPA.bill;
  const head = { sn: "SN", desc: "Description", ref: "Invoice reference", amount: "Amount (AED)" };
  m.innerHTML = `<div class="ipa-card ipa-intro"><b>Fees paid to the authorities in this bill</b> (DM, DEWA, permits ...). Type each receipt: what it was for, the invoice reference and the amount.
      What was claimed in earlier bills is shown above it (grey, not changed here) so you can see what is claimed and what is not; the sub-total counts this bill's lines.</div>` +
    b.fees.map((t, ti) => `<div class="ipa-card"><h3>${esc(t.sheet)}${(t.earlier || []).length ? ` <span class="muted small">- claimed in earlier bills: ${money(t.earlier_total, false)}</span>` : ""}</h3>
      <div class="ipa-tw"><table class="ipa-pay"><thead><tr>${feeCols(t).map(c => `<th class="${c === "amount" ? "r" : ""}" style="${c === "sn" ? "width:60px" : ""}">${head[c] || c}</th>`).join("")}<th style="width:40px"></th></tr></thead><tbody>
      ${(t.earlier || []).map(e => e.head ? `<tr class="hd old"><td colspan="${t.cols.length + 1}">${esc(e.desc ?? "")} <span class="muted small">earlier bill</span></td></tr>`
          : `<tr class="old">${feeCols(t).map(c => `<td class="${c === "amount" ? "r" : ""}">${c === "amount" ? (e.amount ? money(e.amount, false) : "") : esc(e[c] ?? "")}</td>`).join("")}<td></td></tr>`).join("")}
      ${(t.earlier || []).length ? `<tr class="tot old"><td colspan="${t.cols.length - 1}">Claimed in earlier bills</td><td class="r">${money(t.earlier_total, false)}</td><td></td></tr>` : ""}
      ${t.rows.map(r => r.head ? `<tr class="hd"><td colspan="${t.cols.length + 1}"><input class="ipa-pin" data-sh="${esc(t.sheet)}" data-pk="${r.desc.key}" data-c="desc" value="${esc(r.desc.value ?? "")}" style="width:200px;font-weight:700"></td></tr>` :
        `<tr>${feeCols(t).map(c => { const x = r[c]; if (!x) return "<td></td>";
          const at = `data-sh="${esc(t.sheet)}" data-pk="${x.key}" data-c="${c}"`;
          if (c === "amount") return `<td class="r"><input class="ipa-pin amt" data-noclear ${at} data-raw="${esc(x.raw === null || x.raw === undefined ? "" : String(x.raw).replace(/^=/, ""))}" value="${typeof x.value === "number" && x.value ? money(x.value, false) : ""}"></td>`;
          if (c === "sn") return `<td><input class="ipa-pin" ${at} value="${esc(x.value ?? "")}" style="width:50px"></td>`;
          return `<td><input class="ipa-pin ${c === "desc" ? "wide" : ""}" data-spell="off" ${at} value="${esc(x.value ?? "")}" ${c === "desc" ? 'placeholder="e.g. DM: Building permit fee"' : 'placeholder="e.g. WIFBP2017904 dtd 14.09.2026"'} style="${c === "ref" ? "width:230px" : ""}"></td>`; }).join("")}
          <td class="r"><button class="btn btn-plain btn-sm" title="Clear this line" data-clear="${r.r}" data-sh="${esc(t.sheet)}" data-ti="${ti}">&times;</button></td></tr>`).join("")}
      <tr class="tot"><td colspan="${t.cols.length - 1}">Sub-total this bill</td><td class="r">${money(t.total, false)}</td><td></td></tr>
      </tbody></table></div>
      <button class="btn btn-plain btn-sm" data-addfee="${ti}" style="margin-top:10px">+ Add a line</button></div>`).join("") + nextBtn("fees");
  bindNext(m);
  $$("[data-pk]", m).forEach(bindPayInput);
  $$("[data-addfee]", m).forEach(x => x.onclick = async () => {
    const t = b.fees[+x.dataset.addfee];
    const data = t.rows.filter(r => !r.head);
    const filled = data.filter(r => r.desc.value || r.ref.value || r.amount.value);
    const empty = data.filter(r => !(r.desc.value || r.ref.value || r.amount.value));
    if (empty.length) { const i = $(`.ipa-pin[data-pk="${empty[0].desc.key}"]`, m); if (i) i.focus(); return; }   // an empty line is there already
    const last = filled.length ? filled[filled.length - 1] : t.rows[0];
    try {
      IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/rows`, { sheet: t.sheet, at: last.r + 1, n: 1, like: filled.length ? last.r : null });
      drawBill(); const nt = IPA.bill.fees[+x.dataset.addfee]; const nr = nt.rows.find(r => r.r === last.r + 1);
      if (nr) { const i = $(`.ipa-pin[data-pk="${nr.desc.key}"]`); if (i) i.focus(); }
    } catch (e) { fail(e); }
  });
  $$("[data-clear]", m).forEach(x => x.onclick = async () => {
    const t = b.fees[+x.dataset.ti], r = t.rows.find(rr => rr.r === +x.dataset.clear); if (!r) return;
    const set = {}; t.cols.forEach(c => { if (r[c]) set[r[c].key] = null; });
    if (await save({ set: { [t.sheet]: set } })) { toast("Line cleared"); drawBill(); }
  });
}

// ---------------------------------------------------------------- the sheets themselves
function drawSheets(m) {
  const b = IPA.bill;
  if (IPA.sheet === undefined || !b.sheets.some(s => s.i === IPA.sheet)) IPA.sheet = (b.sheets[0] || {}).i;
  m.innerHTML = `<div class="ipa-card ipa-intro"><b>Every sheet of the bill, as the consultant laid it out - and anything this bill needs added.</b>
      <span class="muted">Blue cells can be typed in; yellow = changed this month. Click a cell, type, press Enter (= works as in Excel). Click a row to put a line or a section next to it, or to hide it. <b>+ Add page</b> copies a sheet (e.g. a second variations page); the next bill keeps it.</span></div>
    <div id="ipa-sheet"></div>${nextBtn("sheets")}`;
  bindNext(m);
  drawSheet($("#ipa-sheet"), IPA.sheet);
}
async function drawReview(m) {
  const b = IPA.bill, ck = checks(b), c = b.cover;
  const allSigned = !(b.signers || []).some(x => !x.signed_at);
  m.innerHTML = `<div class="ipa-card ipa-rev">
      <div class="ipa-rev-top"><div><small>Total amount due for payment</small><div class="big">AED ${money(b.total_due, false)}</div>${c && c.words ? `<div class="muted small">${esc(c.words)}</div>` : ""}</div>
        <div class="ipa-rev-st"><label class="small muted">Status</label><select id="ipa-st" ${ST.meta.me.admin ? "" : "disabled"}>${IPA.list.statuses.map(s => `<option ${s === b.status ? "selected" : ""}>${s}</option>`).join("")}</select>
          ${allSigned && ["Draft", "Awaiting approval", "Approved"].includes(b.status) ? `<button class="btn btn-primary" id="ipa-submit">Mark as submitted</button>` : ""}</div></div>
      <ul class="ipa-checks">${ck.map(([ok, t]) => `<li class="${ok === true ? "ok" : ok === false ? "no" : "na"}"><span>${ok === true ? "&#10003;" : ok === false ? "!" : "&ndash;"}</span>${t}</li>`).join("")}</ul>
      <div class="ipa-rev-x">${xpButtons("ipa", { id: b.id, name: `${ST.b.project.code} IPA ${billNo(b)}` })}</div>
    </div>
    ${chainCard(b)}
    <div class="ipa-card"><h3>The bill as it will print <span class="muted small">- the consultant's own sheets, this month's figures${allSigned ? "" : ", signatures once each person has signed"}</span></h3><div id="ipa-pv" class="ipa-pv"><div class="empty">Loading...</div></div></div>
    <div class="ipa-card"><button class="btn btn-ghost" id="ipa-del">Delete this bill</button></div>
    ${nextBtn("review")}`;
  bindNext(m);
  $("#ipa-st").onchange = e => setStatus(e.target.value);
  const sb = $("#ipa-submit"); if (sb) sb.onclick = () => setStatus("Submitted");
  $("#ipa-del").onclick = async () => { if (!(await confirmDelete(`Delete bill ${billNo(b)}?`, `${esc(b.status)} · total due AED ${money(b.total_due, false)}`))) return; try { await DEL(`/store/est/ipa/bill/${b.id}`); toast("Bill removed"); closeBig(billsRedraw); } catch (x) { fail(x); } };
  bindChain(m);
  try {
    const t = await POST("/auth/download-token"); const tok = t.token || t.download_token;
    const pv = $("#ipa-pv"); if (!pv) return;
    pv.innerHTML = `<iframe src="/export/est/ipa/${b.id}?token=${encodeURIComponent(tok)}&format=preview&embed=1" title="Bill preview"></iframe>`;
  } catch (e) { const pv = $("#ipa-pv"); if (pv) pv.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
async function setStatus(s) {
  try { await POST(`/store/est/ipa/bill/${IPA.bill.id}/status`, { status: s }); IPA.bill.status = s; toast("Status: " + s); drawBill(); } catch (x) { fail(x); }
}

// ---- Sheets step formatting: what is picked stays picked across a redraw of the same sheet
const FSZ = [6, 7, 8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24];
// number formats (real Excel formats - the value itself never changes, only how it shows)
const NF = { general: "General", num: "#,##0.00", num0: "#,##0", pct: "0%", pct2: "0.00%",
  acc: '_("AED "* #,##0.00_);_("AED "* (#,##0.00);_("AED "* "-"??_);_(@_)', neg: "#,##0.00;[Red](#,##0.00)", date: "dd/mm/yyyy", date2: "dd-mmm-yyyy" };
const NFS = [["general", "General 1318577.14"], ["num", "Number 1,318,577.14"], ["num0", "Number (0 dp) 1,318,577"], ["pct", "Percentage 45%"], ["pct2", "Percentage 45.00%"],
  ["acc", "Accounting AED 1,318,577.14"], ["neg", "Negative in ( ) (1,234.56)"], ["date", "Date 08/05/2026"], ["date2", "Date 08-May-2026"]];
// dates are read day first, always (05/06/2026 = 5 June), whatever the computer is set to: -> an Excel date number
const MONS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
function parseDMY(t) {
  t = String(t || "").trim(); let d, m, y, x;
  if ((x = t.match(/^(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2}|\d{4})$/))) { d = +x[1]; m = +x[2]; y = +x[3]; }
  else if ((x = t.match(/^(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})\.?,?[\s\-]+(\d{2}|\d{4})$/))) { d = +x[1]; m = MONS.indexOf(x[2].slice(0, 3).toLowerCase()) + 1; y = +x[3]; }
  else return null;
  if (y < 100) y += 2000;
  if (!m || m > 12 || d < 1 || d > new Date(Date.UTC(y, m, 0)).getUTCDate()) return NaN;     // 31/02/2026: not a date
  return Math.round((Date.UTC(y, m - 1, d) - Date.UTC(1899, 11, 30)) / 864e5);
}
const isDateNf = nf => { const t = String(nf || "").replace(/"[^"]*"|\[[^\]]*\]/g, ""); return /[dy]/i.test(t) && !/[0#?]/.test(t) && !/general/i.test(t); };
// one section of a format at a time: commas on / off, decimals 0-4 (text sections and dates left alone)
function nfEach(nf, f) { const out = [], parts = []; let cur = "", q = false;
  for (const ch of nf || "General") { if (ch === '"') q = !q; if (ch === ";" && !q) { parts.push(cur); cur = ""; } else cur += ch; } parts.push(cur);
  for (const p of parts) out.push(/@/.test(p.replace(/"[^"]*"/g, "")) ? p : f(p)); return out.join(";"); }
function nfSec(p, comma, dec) {             // comma: true / false / null (keep); dec: number / null (keep)
  if (/^\s*general\s*$/i.test(p)) p = "0.00";
  let done = false;
  return p.replace(/(?:"[^"]*")|(?:_.)|([#0][#0?,]*(?:\.[0#?]*)?)/g, (m, num) => { if (!num || done) return m; done = true;
    const [ip, dp = ""] = num.split("."); const hasC = ip.includes(",");
    const nI = (comma === null ? hasC : comma) ? "#,##0" : "0"; const nD = dec === null ? dp.length : dec;
    return nI + (nD > 0 ? "." + "0".repeat(nD) : ""); }); }
function nfDec(nf) { const m = (nf || "").replace(/"[^"]*"/g, "").match(/[#0?][#0?,]*(?:\.([0#?]*))?/); return m && m[1] ? m[1].length : 0; }
function fmtTools(v, host, b, sh, redraw) {
  const bar = $("#sv-fmt", v); if (!bar) return;
  if (!IPA.fsel || IPA.fsel.sh !== sh) IPA.fsel = { sh, a: null, z: null, rows: null, cols: null, add: [] };
  const S = IPA.fsel; S.add = S.add || [];
  // row numbers down the left and column letters along the top, as in Excel; the corner box picks the whole sheet
  host.style.position = "relative"; host.style.paddingLeft = "30px"; host.style.paddingTop = "18px";
  const gut = document.createElement("div"); gut.className = "sv-gut"; host.appendChild(gut);
  const ctop = document.createElement("div"); ctop.className = "sv-cgut"; host.appendChild(ctop);
  const corner = document.createElement("div"); corner.className = "sv-corner"; corner.title = "The whole sheet (Ctrl+A)"; host.appendChild(corner);
  const colL = n => { let t = ""; while (n > 0) { const m = (n - 1) % 26; t = String.fromCharCode(65 + m) + t; n = Math.floor((n - 1) / 26); } return t; };
  const place = () => { gut.innerHTML = ""; const hr = host.getBoundingClientRect(), z = SV.z || 1;
    $$("tr[data-r]", host).forEach(tr => { const r = tr.getBoundingClientRect(); const d = document.createElement("div"); d.className = "sv-rn"; d.dataset.r = tr.dataset.r; d.textContent = tr.dataset.r;
      Object.assign(d.style, { top: (r.top - hr.top) / z + "px", height: Math.max(r.height / z, 10) + "px" }); gut.appendChild(d); }); };
  const placeCols = () => { ctop.innerHTML = ""; const hr = host.getBoundingClientRect(), z = SV.z || 1, span = {};
    $$("td[data-c]", host).forEach(td => { if (td.colSpan > 1) return; const c = +td.dataset.c, r = td.getBoundingClientRect(); if (!span[c]) span[c] = [r.left, r.right]; });
    Object.keys(span).forEach(c => { const d = document.createElement("div"); d.className = "sv-cn"; d.dataset.c = c; d.textContent = colL(+c);
      Object.assign(d.style, { left: (span[c][0] - hr.left) / z + "px", width: Math.max((span[c][1] - span[c][0]) / z, 8) + "px" }); ctop.appendChild(d); }); };
  placeCols(); place();
  const allRows = () => $$("tr[data-r]", host).map(t => +t.dataset.r);
  const rangeCells = () => { if (!S.a) return [];
    const [r1, r2] = [Math.min(S.a[0], (S.z || S.a)[0]), Math.max(S.a[0], (S.z || S.a)[0])], [c1, c2] = [Math.min(S.a[1], (S.z || S.a)[1]), Math.max(S.a[1], (S.z || S.a)[1])];
    const out = []; for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) out.push([r, c]); return out; };
  const cellsOf = () => { if (S.rows || S.cols) return []; const seen = new Set(), out = [];
    for (const x of rangeCells().concat(S.add)) { const k = x.join(","); if (!seen.has(k)) { seen.add(k); out.push(x); } } return out; };
  const tdsOf = () => { if (S.rows) { const set = new Set(S.rows); return $$("tr[data-r] td[data-c]", host).filter(td => set.has(+td.parentElement.dataset.r)); }
    if (S.cols) return $$("td[data-c]", host).filter(td => S.cols.includes(+td.dataset.c));
    const set = new Set(cellsOf().map(x => x.join(","))); return $$("tr[data-r] td[data-c]", host).filter(td => set.has(td.parentElement.dataset.r + "," + td.dataset.c)); };
  const st = td => td ? (td.getAttribute("style") || "") : "";
  const paint = () => { $$(".xsel", host).forEach(x => x.classList.remove("xsel")); $$(".sv-rn.on, .sv-cn.on", host).forEach(x => x.classList.remove("on"));
    const tds = tdsOf(); tds.forEach(td => td.classList.add("xsel"));
    (S.rows || []).forEach(r => { const d = $(`.sv-rn[data-r="${r}"]`, gut); if (d) d.classList.add("on"); });
    (S.cols || []).forEach(c => { const d = $(`.sv-cn[data-c="${c}"]`, ctop); if (d) d.classList.add("on"); });
    corner.classList.toggle("on", !!S.all);
    const on = tds.length > 0; $$("[data-fx]", bar).forEach(x => x.disabled = !on);
    const f = tds.find(td => td.textContent.trim()) || tds[0], fs = getComputedStyle(f || document.body);
    const szm = st(f).match(/font-size:\s*([\d.]+)pt/);
    const sz = szm ? Math.round(+szm[1] * 2) / 2 : (f ? Math.round(parseFloat(fs.fontSize) * 0.75 * 2) / 2 : "");
    const sel = $('[data-fx="sz"]', bar);
    if (sz && !$(`option[value="${sz}"]`, sel)) sel.insertAdjacentHTML("beforeend", `<option value="${sz}">${sz}</option>`);
    sel.value = on && sz ? String(sz) : "";
    const fam = (st(f).match(/font-family:\s*'([^']+)'/) || [])[1] || "";
    const fsel = $('[data-fx="font"]', bar); if (fam && !$(`option[value="${CSS.escape(fam)}"]`, fsel)) fsel.insertAdjacentHTML("beforeend", `<option value="${esc(fam)}">${esc(fam)}</option>`);
    fsel.value = on ? fam : "";
    const txt = tds.filter(td => td.textContent.trim());
    const has = re => on && txt.length > 0 && txt.every(td => re.test(st(td)));
    $('[data-fx="b"]', bar).classList.toggle("on", has(/font-weight:\s*(700|bold)/));
    $('[data-fx="i"]', bar).classList.toggle("on", has(/font-style:\s*italic/));
    $('[data-fx="u"]', bar).classList.toggle("on", has(/text-decoration:[^;]*underline/));
    $('[data-fx="wrap"]', bar).classList.toggle("on", has(/white-space:\s*pre-wrap/));
    const fcm = st(f).match(/(?:^|;)\s*color:\s*#([0-9A-Fa-f]{6})/); const fci = $('[data-fx="fc"]', bar); fci.value = "#" + (fcm ? fcm[1] : "000000");
    fci.parentElement.style.setProperty("--fc", fci.value);
    const nt = tds.find(td => td.dataset.num) || f, nf = nt ? nt.dataset.nf || "General" : "";
    const key = Object.keys(NF).find(k => NF[k] === nf) || (isDateNf(nf) ? "date" : "");
    $('[data-fx="nf"]', bar).value = on ? key : "";
    $('[data-fx="comma"]', bar).classList.toggle("on", on && /#,##0/.test(nf));
    const ha = nt ? (nt.dataset.ha || "") : "";
    $$('[data-fx="al"]', bar).forEach(x => x.classList.toggle("on", on && x.dataset.v === ha));
    const va = (st(f).match(/vertical-align:\s*(\w+)/) || [])[1]; const vam = { top: "top", middle: "center", bottom: "bottom" }[va] || "";
    $$('[data-fx="va"]', bar).forEach(x => x.classList.toggle("on", on && x.dataset.v === vam));
    const ind = +((st(f).match(/padding-left:\s*(\d+)px/) || [])[1] || 3); S.cur = { sz, tds, nf, ind: Math.max(0, Math.round((ind - 3) / 9)) }; };
  const clearAll = () => { S.a = null; S.z = null; S.rows = null; S.cols = null; S.add = []; S.all = false; };
  host.addEventListener("click", e => { const td = e.target.closest("td[data-c]"); if (!td || !host.contains(td)) return;
    const rc = [+td.parentElement.dataset.r, +td.dataset.c];
    if ((e.ctrlKey || e.metaKey) && !S.rows && !S.cols) { const k = rc.join(","), i = S.add.findIndex(x => x.join(",") === k);
      if (i >= 0) S.add.splice(i, 1); else S.add.push(rc); e.preventDefault(); e.stopPropagation(); }
    else if (e.shiftKey && S.a && !S.rows && !S.cols) { S.z = rc; e.preventDefault(); window.getSelection && window.getSelection().removeAllRanges(); }
    else { clearAll(); S.a = rc; }
    paint(); }, true);
  gut.addEventListener("click", e => { const d = e.target.closest(".sv-rn"); if (!d) return; e.stopPropagation(); const r = +d.dataset.r;
    if (e.shiftKey && S.rows && S.rows.length) { const a = S.rows[0], lo = Math.min(a, r), hi = Math.max(a, r); S.rows = [a].concat(allRows().filter(x => x >= lo && x <= hi && x !== a)); }
    else if ((e.ctrlKey || e.metaKey) && S.rows) S.rows = S.rows.includes(r) ? S.rows.filter(x => x !== r) : S.rows.concat([r]);
    else { clearAll(); S.rows = [r]; }
    paint(); const tr = $(`tr[data-r="${r}"]`, host); if (tr && S.rows.length === 1) tr.click(); });
  ctop.addEventListener("click", e => { const d = e.target.closest(".sv-cn"); if (!d) return; e.stopPropagation(); const c = +d.dataset.c;
    if (e.shiftKey && S.cols && S.cols.length) { const a = S.cols[0], lo = Math.min(a, c), hi = Math.max(a, c); S.cols = $$(".sv-cn", ctop).map(x => +x.dataset.c).filter(x => x >= lo && x <= hi); }
    else if ((e.ctrlKey || e.metaKey) && S.cols) S.cols = S.cols.includes(c) ? S.cols.filter(x => x !== c) : S.cols.concat([c]);
    else { clearAll(); S.cols = [c]; }
    paint(); });
  const pickAll = () => { clearAll(); S.rows = allRows(); S.all = true; paint(); };
  corner.addEventListener("click", e => { e.stopPropagation(); pickAll(); });
  const send = async body => { const p = Object.assign({ sheet: sh }, (body.rows || body.cols || body.cells) ? {} : S.rows ? { rows: S.rows } : S.cols ? { cols: S.cols } : { cells: cellsOf() }, body);
    if (!(p.rows || p.cols || p.cells).length) return toast("Pick cells first");
    try { IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/fmt`, p); redraw(); } catch (e) { fail(e); } };
  // Delete: the contents go, the look stays (only cells that can be typed in; formulas that work things out are kept)
  const clearCells = async () => { const tds = tdsOf().filter(td => td.classList.contains("ed") && td.dataset.k && (td.dataset.raw || "") !== "");
    if (!tds.length) return toast("Nothing to clear here");
    const set = {}; tds.forEach(td => set[td.dataset.k] = ""); if (await save({ set: { [sh]: set } })) { toast(tds.length === 1 ? "Cleared" : `${tds.length} cells cleared`); redraw(); } };
  const act = (a, x) => { const cur = (S.cur || {}).sz || 11;
    if (a === "up" || a === "dn") { const nxt = a === "up" ? (FSZ.find(z => z > cur) || Math.min(24, cur + 2)) : ([...FSZ].reverse().find(z => z < cur) || Math.max(6, cur - 1)); send({ set: { sz: nxt } }); }
    else if (a === "b" || a === "i" || a === "u" || a === "wrap") send({ set: { [a]: !x.classList.contains("on") } });
    else if (a === "al") send({ set: { ha: x.dataset.v } });
    else if (a === "va") send({ set: { va: x.dataset.v } });
    else if (a === "ind") send({ set: { ind: Math.max(0, Math.min(10, ((S.cur || {}).ind || 0) + +x.dataset.v)) } });
    else if (a === "comma") { const on = !x.classList.contains("on"); send({ set: { nf: nfEach(S.cur.nf, p => nfSec(p, on, null)) } }); }
    else if (a === "dless" || a === "dmore") { const d = Math.max(0, Math.min(4, nfDec(S.cur.nf) + (a === "dmore" ? 1 : -1))); send({ set: { nf: nfEach(S.cur.nf, p => nfSec(p, null, d)) } }); }
    else if (a === "like") send({ like_above: true });
    else if (a === "menu") openMenu(x.dataset.v, x);
    else if (a === "clear") clearCells();
    else if (a === "reset") send({ reset: true }); };
  bar.onclick = e => { const x = e.target.closest("button[data-fx]"); if (!x || x.disabled) return; act(x.dataset.fx, x); };
  $('[data-fx="sz"]', bar).onchange = e => { if (e.target.value) send({ set: { sz: +e.target.value } }); };
  $('[data-fx="font"]', bar).onchange = e => { if (e.target.value) send({ set: { font: e.target.value } }); };
  $('[data-fx="fc"]', bar).onchange = e => send({ set: { fc: e.target.value.replace("#", "") } });
  $('[data-fx="nf"]', bar).onchange = e => { if (e.target.value) send({ set: { nf: NF[e.target.value] } }); };
  // right-click: the same tools by the cell
  host.addEventListener("contextmenu", e => { const td = e.target.closest("td[data-c]"); if (!td) return; e.preventDefault();
    if (!td.classList.contains("xsel")) { clearAll(); S.a = [+td.parentElement.dataset.r, +td.dataset.c]; paint(); }
    $$(".sv-ctx").forEach(x => x.remove());
    const items = [["b", "Bold", "Ctrl+B"], ["i", "Italic", "Ctrl+I"], ["u", "Underline", "Ctrl+U"], ["wrap", "Wrap text"], ["-"], ["al:left", "Align left"], ["al:center", "Centre"], ["al:right", "Align right"], ["al:dec", "Align on decimal"],
      ["-"], ["nf:num", "Number 1,318,577.14"], ["nf:pct", "Percentage 45%"], ["nf:date", "Date 08/05/2026"], ["nf:general", "General"], ["-"], ["like", "Match row above"], ["clear", "Clear contents", "Delete"], ["reset", "Reset to the consultant's look"]];
    const m = document.createElement("div"); m.className = "sv-ctx";
    m.innerHTML = items.map(([k, l, h]) => k === "-" ? "<hr>" : `<button type="button" data-k="${k}">${l}${h ? `<small>${h}</small>` : ""}</button>`).join("");
    document.body.appendChild(m);
    m.style.left = Math.min(e.clientX, innerWidth - m.offsetWidth - 8) + "px"; m.style.top = Math.min(e.clientY, innerHeight - m.offsetHeight - 8) + "px";
    m.onclick = ev => { const x = ev.target.closest("button[data-k]"); if (!x) return; m.remove(); const [a, val] = x.dataset.k.split(":");
      if (a === "nf") send({ set: { nf: NF[val] } }); else if (a === "al") send({ set: { ha: val } });
      else { const btn = $(`[data-fx="${a}"]`, bar); act(a, btn || x); } };
    setTimeout(() => document.addEventListener("click", () => m.remove(), { once: true }), 0); });
  // ---- the box picked: rows / columns covered (a merged cell counts all its columns)
  const boxOf = () => { const tds = tdsOf(); if (!tds.length) return null; let r1 = 1e9, c1 = 1e9, r2 = 0, c2 = 0;
    tds.forEach(td => { const r = +td.parentElement.dataset.r, c = +td.dataset.c, ce = c + (td.colSpan || 1) - 1;
      r1 = Math.min(r1, r); r2 = Math.max(r2, r); c1 = Math.min(c1, c); c2 = Math.max(c2, ce); }); return [r1, c1, r2, c2]; };
  const rowsIn = (r1, r2) => allRows().filter(r => r >= r1 && r <= r2);
  const borders = (how, stl, col) => { const bx = boxOf(); if (!bx) return toast("Pick cells first"); const [r1, c1, r2, c2] = bx, rows = rowsIn(r1, r2), out = {};
    const put = (r, c, side, v) => { const k = r + "," + c; (out[k] = out[k] || {})[side] = v; };
    const thick = how === "thickout" ? "thick" : stl;
    for (const r of rows) for (let c = c1; c <= c2; c++) {
      const top = r === rows[0], bot = r === rows[rows.length - 1], lf = c === c1, rt = c === c2;
      if (how === "all") ["l", "r", "t", "b"].forEach(sd => put(r, c, sd, stl));
      else if (how === "outside" || how === "thickout") { if (top) put(r, c, "t", thick); if (bot) put(r, c, "b", thick); if (lf) put(r, c, "l", thick); if (rt) put(r, c, "r", thick); }
      else if (how === "inside") { if (!bot) put(r, c, "b", stl); if (!rt) put(r, c, "r", stl); }
      else if (how === "top" && top) put(r, c, "t", stl); else if (how === "bottom" && bot) put(r, c, "b", stl);
      else if (how === "left" && lf) put(r, c, "l", stl); else if (how === "right" && rt) put(r, c, "r", stl);
      else if (how === "thickbot" && bot) put(r, c, "b", "thick"); else if (how === "dblbot" && bot) put(r, c, "b", "double");
      else if (how === "none") ["l", "r", "t", "b"].forEach(sd => put(r, c, sd, "")); }
    if (how === "none") {                                // the cells around share those lines: theirs go too
      const all = allRows(), ia = all.indexOf(rows[0]), ib = all.indexOf(rows[rows.length - 1]);
      for (let c = c1; c <= c2; c++) { if (ia > 0) put(all[ia - 1], c, "b", ""); if (ib >= 0 && ib < all.length - 1) put(all[ib + 1], c, "t", ""); }
      for (const r of rows) { if (c1 > 1) put(r, c1 - 1, "r", ""); put(r, c2 + 1, "l", ""); } }
    send({ borders: out, bdc: (col || "#000000").replace("#", ""), cells: [[r1, c1]] }); };
  const menu = (btn, html, bind) => { $$(".sv-ddm").forEach(x => x.remove()); const m = document.createElement("div"); m.className = "sv-ddm"; m.innerHTML = html;
    document.body.appendChild(m); const r = btn.getBoundingClientRect(); m.style.left = Math.min(r.left, innerWidth - m.offsetWidth - 8) + "px"; m.style.top = (r.bottom + 4) + "px";
    m.addEventListener("click", e => e.stopPropagation()); bind(m); setTimeout(() => document.addEventListener("click", () => m.remove(), { once: true }), 0); return m; };
  const BDS = [["all", "All borders"], ["outside", "Outside"], ["inside", "Inside"], ["top", "Top"], ["bottom", "Bottom"], ["left", "Left"], ["right", "Right"], ["thickout", "Thick outside"], ["thickbot", "Thick bottom"], ["dblbot", "Double bottom (totals)"], ["none", "No border"]];
  const openMenu = (kind, btn) => {
    if (kind === "bd") menu(btn, `<div class="sv-ddrow"><label>Line <select id="bd-st"><option value="thin">Thin</option><option value="medium">Medium</option><option value="thick">Thick</option><option value="dashed">Dashed</option><option value="double">Double</option></select></label>
        <label>Colour <input type="color" id="bd-c" value="${SV.bdc || "#000000"}"></label></div>${BDS.map(([k, l]) => `<button type="button" data-b="${k}">${l}</button>`).join("")}`,
      m => { const st_ = $("#bd-st", m); st_.value = SV.bds || "thin"; m.onclick = e => { const x = e.target.closest("[data-b]"); if (!x) return; SV.bds = st_.value; SV.bdc = $("#bd-c", m).value; m.remove(); borders(x.dataset.b, st_.value, SV.bdc); }; });
    else if (kind === "mg") menu(btn, `<button type="button" data-m="center">Merge &amp; centre</button><button type="button" data-m="across">Merge across (each row)</button><button type="button" data-m="merge">Merge cells</button><button type="button" data-m="unmerge">Unmerge</button>`,
      m => { m.onclick = async e => { const x = e.target.closest("[data-m]"); if (!x) return; m.remove(); const how = x.dataset.m;
        if (how !== "unmerge") { const full = tdsOf().filter(td => td.textContent.trim()); const bx = boxOf();
          const many = how === "across" ? rowsIn(bx[0], bx[2]).some(r => full.filter(td => +td.parentElement.dataset.r === r).length > 1) : full.length > 1;
          if (many && !(await confirmDelete("Merge these cells?", "Merging keeps only the top-left value - the others are hidden.", "Merge", "Unmerge brings the cells back."))) return; }
        const bx = boxOf(); send({ merge: how, cells: [[bx[0], bx[1]], [bx[2], bx[3]]] }); }; });
    else if (kind === "fm") menu(btn, `<button type="button" data-f="rowh">Row height…</button><button type="button" data-f="colw">Column width…</button><hr>
        <button type="button" data-f="fitr">Autofit rows picked</button><button type="button" data-f="fitc">Autofit columns picked</button><button type="button" data-f="fitall">Autofit all rows - this sheet</button><button type="button" data-f="fitbook">Autofit all rows - all sheets</button><hr>
        <button type="button" data-f="brkon">Insert page break above</button><button type="button" data-f="brkoff">Remove page break above</button><hr><button type="button" data-f="resetall">Reset the whole sheet to the consultant's look</button>`,
      m => { m.onclick = async e => { const x = e.target.closest("[data-f]"); if (!x) return; m.remove(); const a = x.dataset.f, bx = boxOf();
        if (a === "rowh" || a === "colw") { const tr = $(`tr[data-r="${bx[0]}"]`, host), z = SV.z || 1;
          const cur = a === "rowh" ? Math.round(tr.getBoundingClientRect().height / z * 0.75 * 4) / 4 : Math.round(((($(`.sv-cn[data-c="${bx[1]}"]`, ctop) || {}).offsetWidth || 64) - 5) / 7 * 100) / 100;
          modal(a === "rowh" ? "Row height" : "Column width", [{ k: "v", label: a === "rowh" ? `Height in points (rows ${bx[0]}-${bx[2]})` : `Width in characters (columns ${colL(bx[1])}-${colL(bx[3])})`, type: "num", value: cur, focus: true }],
            async v => { send({ [a]: +v.v }); }, { save: "Set" }); }
        else if (a === "fitr") send({ autofit: "rows" }); else if (a === "fitc") send({ autofit: "cols" });
        else if (a === "fitall") send({ autofit: "rows", whole: true });
        else if (a === "fitbook") { if (await confirmDelete("Autofit every row on every sheet?", "Each row takes the height its text needs.", "Autofit", "Reset brings a sheet back.")) send({ autofit: "rows", all_sheets: true }); }
        else if (a === "brkon" || a === "brkoff") send({ brk: { above: bx[0], on: a === "brkon" } });
        else if (a === "resetall") { if (await confirmDelete("Reset the whole sheet?", "Every change of look made on this bill goes; the figures and words stay.", "Reset", "")) send({ reset: true, whole: true, rows: allRows() }); } }; });
  };
  // ---- page breaks on the screen: the printed A4 pages (grey) and the breaks put in (dashed blue)
  const lines = document.createElement("div"); lines.className = "sv-pgl"; host.appendChild(lines);
  const placeLines = () => { lines.innerHTML = ""; const hr = host.getBoundingClientRect(), z = SV.z || 1, man = new Set(SV.manual || []);
    (SV.pages || []).concat([...man]).forEach(r => { const tr = $(`tr[data-r="${r}"]`, host); if (!tr) return; const y = (tr.getBoundingClientRect().top - hr.top) / z;
      const d = document.createElement("div"); d.className = "sv-pg" + (man.has(r) ? " man" : ""); d.style.top = y + "px"; d.title = man.has(r) ? "Page break put in above row " + r : "A4 page " + ((SV.pages || []).indexOf(r) + 2) + " starts here"; lines.appendChild(d); }); };
  placeLines();
  // ---- drag a row's bottom edge / a column's right edge to resize; double-click it to autofit
  const tip = document.createElement("div"); tip.className = "sv-tip"; document.body.appendChild(tip);
  const drag = (el, axis, id) => { const hd = document.createElement("div"); hd.className = "sv-rz " + axis; el.appendChild(hd);
    hd.addEventListener("dblclick", e => { e.stopPropagation(); send(axis === "y" ? { autofit: "rows", rows: [id] } : { autofit: "cols", cols: [id] }); });
    hd.addEventListener("mousedown", e => { e.preventDefault(); e.stopPropagation(); const z = SV.z || 1, start = axis === "y" ? e.clientY : e.clientX;
      const base = axis === "y" ? $(`tr[data-r="${id}"]`, host).getBoundingClientRect().height / z : el.offsetWidth;
      const mv = ev => { const px = Math.max(4, base + ((axis === "y" ? ev.clientY : ev.clientX) - start) / z);
        tip.textContent = axis === "y" ? `Height: ${(px * 0.75).toFixed(2)} pt (${Math.round(px)} px)` : `Width: ${Math.max(0.5, (px - 5) / 7).toFixed(2)} (${Math.round(px)} px)`;
        Object.assign(tip.style, { display: "block", left: ev.clientX + 14 + "px", top: ev.clientY + 14 + "px" });
        if (axis === "y") { const tr = $(`tr[data-r="${id}"]`, host); if (tr) tr.style.height = px + "px"; } else el.style.width = px + "px"; };
      const up = ev => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); tip.style.display = "none";
        const px = Math.max(4, base + ((axis === "y" ? ev.clientY : ev.clientX) - start) / z); if (Math.abs(px - base) < 1) return;
        if (axis === "y") send({ rowh: Math.round(px * 0.75 * 4) / 4, rows: [id] }); else send({ colw: Math.round(Math.max(0.5, (px - 5) / 7) * 100) / 100, cols: [id] }); };
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up); }); };
  $$(".sv-rn", gut).forEach(d => drag(d, "y", +d.dataset.r));
  $$(".sv-cn", ctop).forEach(d => drag(d, "x", +d.dataset.c));
  SV.fx = { paint, pickAll, clearCells, act, bar };
  if (!SV.fkeys) { SV.fkeys = true;
    document.addEventListener("keydown", e => { const fb = document.querySelector("#sv-fmt"); if (!fb || !SV.fx) return;
      if (/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || "") || document.querySelector(".ipa-cell")) return;
      if (document.querySelector(".modal-bg, .modal.open")) return;
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && !e.altKey && k === "a" && document.querySelector(".sv-in")) { e.preventDefault(); SV.fx.pickAll(); return; }
      if ((e.ctrlKey || e.metaKey) && !e.altKey && ["b", "i", "u"].includes(k)) { const btn = fb.querySelector(`[data-fx="${k}"]`); if (!btn || btn.disabled) return; e.preventDefault(); btn.click(); return; }
      if ((e.key === "Delete" || e.key === "Backspace") && document.querySelector(".sv-in td.xsel")) { e.preventDefault(); SV.fx.clearCells(); } }); }
  paint();
}

// one sheet as the consultant laid it out; typed figures open on a click
async function drawSheet(v, i, keep) {
  const was = keep && $(".sv-box", v) ? [$(".sv-box", v).scrollLeft, $(".sv-box", v).scrollTop] : null;
  if (!was) v.innerHTML = `<div class="empty">Loading the sheet...</div>`;
  let d; try { d = await GET(`/store/est/ipa/bill/${IPA.bill.id}/sheet/${i}`); } catch (e) { v.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!document.getElementById("ipa-css")) document.head.appendChild(h(`<style id="ipa-css">${d.css}</style>`));
  d.i = i;
  const b = IPA.bill, cur = b.sheets.find(x => x.i === i) || {};
  const locked = b.status !== "Draft";                  // the sheets are changed only while the bill is a Draft
  const FS = [6, 7, 8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24];
  const FONTS = ["Calibri", "Arial", "Arial Narrow", "Times New Roman", "Cambria", "Tahoma", "Verdana", "Century Gothic", "Book Antiqua"];
  const B_ = (fx, t, h, v) => `<button class="btn btn-plain btn-sm" data-fx="${fx}"${v !== undefined ? ` data-v="${v}"` : ""} title="${t}" disabled>${h}</button>`;
  const fmtBar = locked ? "" : `<span class="sv-sep"></span><span class="sv-fmt" id="sv-fmt" title="Pick cells first: click a cell, Shift+click a range, Ctrl+click to add cells, a row number / column letter for a whole row / column, Ctrl+A for the sheet. Right-click for the same tools.">
      <select data-fx="font" title="Font" disabled><option value="">Font</option>${FONTS.map(x => `<option value="${x}">${x}</option>`).join("")}</select>
      <select data-fx="sz" title="Font size" disabled><option value="">Size</option>${FS.map(x => `<option value="${x}">${x}</option>`).join("")}</select>
      ${B_("dn", "Smaller", "A&minus;")}${B_("up", "Bigger", "A+")}
      ${B_("b", "Bold (Ctrl+B)", "<b>B</b>")}${B_("i", "Italic (Ctrl+I)", "<i>I</i>")}${B_("u", "Underline (Ctrl+U)", "<u>U</u>")}
      <label class="btn btn-plain btn-sm sv-fc" title="Text colour"><span>A</span><input type="color" data-fx="fc" value="#000000" disabled></label>
      <span class="sv-sep"></span>
      ${B_("al", "Align left", "&#8676;", "left")}${B_("al", "Centre", "&#8596;", "center")}${B_("al", "Align right", "&#8677;", "right")}${B_("al", "Align on decimal: the points line up under each other", ".00", "dec")}
      ${B_("va", "Top", "&#8868;", "top")}${B_("va", "Middle", "&#8801;", "center")}${B_("va", "Bottom", "&#8869;", "bottom")}
      ${B_("ind", "Outdent", "&#8676;&#8676;", "-1")}${B_("ind", "Indent (B1, B2, B3)", "&#8677;&#8677;", "1")}${B_("wrap", "Wrap text: onto several lines, the row grows", "Wrap")}
      <span class="sv-sep"></span>
      <select data-fx="nf" title="Number format" disabled><option value="">Format</option>${NFS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select>
      ${B_("comma", "Thousands separator: 1,318,577.14", ",")}${B_("dless", "Fewer decimals", ".0&larr;")}${B_("dmore", "More decimals", ".00&rarr;")}
      <span class="sv-sep"></span>
      <span class="sv-dd"><button class="btn btn-plain btn-sm" data-fx="menu" data-v="bd" title="Borders" disabled>&#9638; Borders &#9662;</button></span>
      <span class="sv-dd"><button class="btn btn-plain btn-sm" data-fx="menu" data-v="mg" title="Merge cells" disabled>&#8862; Merge &#9662;</button></span>
      <span class="sv-dd"><button class="btn btn-plain btn-sm" data-fx="menu" data-v="fm" title="Row height, column width, autofit, page breaks" disabled>Format &#9662;</button></span>
      <span class="sv-sep"></span>
      ${B_("like", "Font, size, bold, alignment and borders of the row above", "Match row above")}${B_("clear", "Clear contents (Delete) - the look stays", "Clear")}${B_("reset", "Back to the consultant's look", "Reset")}</span>`;
  const tools = locked ? "" : fmtBar + `<span class="sv-sep"></span><button class="btn btn-ghost btn-sm" data-pg="add" title="A copy of one of the sheets, added after the last one - e.g. a second variations or authority fees page">+ Add page</button>${cur.added ? `<button class="btn btn-plain btn-sm" data-pg="del" title="Take this added page off the bill">Delete page</button>` : ""}`;
  const below = locked ? `<div class="sv-locked">Read only - this bill is ${esc(b.status)}. The sheets can be changed while the bill is a Draft.</div>` : `<div class="sv-rows" id="sv-rows"><span class="muted">Click a row of the sheet to add a line or a section next to it, or to hide it.</span>${cur.hidden ? ` <button class="btn btn-plain btn-sm" data-rw="show">Show ${cur.hidden} hidden line${cur.hidden === 1 ? "" : "s"}</button>` : ""}</div>`;
  const fr = sheetFrame(v, d, { sheets: b.sheets, go: j => { IPA.sheet = j; drawSheet(v, j); }, tools, below });
  if (was) { fr.box.scrollLeft = was[0]; fr.box.scrollTop = was[1]; }
  if (locked) return;
  const host = fr.inner, sh = d.name, redraw = () => { refreshNav(); drawSheet(v, i, true); };
  // ---- pages
  const pa = $('[data-pg="add"]', v); if (pa) pa.onclick = () => modal("Add a page", [
    { k: "from", label: "Copy of", type: "select", options: b.sheets.map(x => x.name), value: sh, full: true, tip: "The new page starts as this sheet looks (its headings, columns and look). Clear or change its lines after." },
    { k: "name", label: "Name of the new page", value: "", ph: "e.g. Variations 2", full: true, focus: true }],
    async x => { IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/pages`, { from: x.from, name: x.name }); const n = IPA.bill.sheets.find(y => y.name === x.name.trim().replace(/\s+/g, " "));
      IPA.sheet = n ? n.i : IPA.sheet; drawBill(); toast(`Page ${x.name} added`); }, { save: "Add page" });
  const pd = $('[data-pg="del"]', v); if (pd) pd.onclick = async () => {
    if (!(await confirmDelete(`Delete the page ${sh}?`, "It is taken off this bill, with what was typed on it."))) return;
    try { IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/pages`, { remove: sh }); IPA.sheet = undefined; drawBill(); toast("Page deleted"); } catch (e) { fail(e); } };
  const sw = $('[data-rw="show"]', v); if (sw) sw.onclick = async () => {
    try { IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/hide`, { sheet: sh, rows: [], show: true, all: true }); redraw(); toast("Hidden lines shown"); } catch (e) { fail(e); } };
  // ---- rows: click one -> put a line / a section next to it, or hide it
  const rowBar = $("#sv-rows", v);
  const pickRow = tr => {
    $$("tr.sel", host).forEach(x => x.classList.remove("sel")); tr.classList.add("sel");
    const r = +tr.dataset.r;
    rowBar.innerHTML = `<b>Row ${r}</b><button class="btn btn-ghost btn-sm" data-rw="above">+ Line above</button><button class="btn btn-ghost btn-sm" data-rw="below">+ Line below</button>
      <button class="btn btn-ghost btn-sm" data-rw="section" title="A heading line (in the look of the table's headings) and a line under it">+ Section below</button><button class="btn btn-plain btn-sm" data-rw="hide" title="Kept in the file, not printed">Hide line</button>
      <button class="btn btn-plain btn-sm" data-rw="clear" title="Done">&times;</button>`;
    const heading = () => { let p = tr.previousElementSibling;                       // the nearest heading above: a bold row
      while (p) { if ([...p.cells].some(c => /font-weight:700/.test(c.getAttribute("style") || "") && c.textContent.trim())) return +p.dataset.r; p = p.previousElementSibling; } return r; };
    const add = async (at, n, like) => { try { IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/rows`, { sheet: sh, at, n, like }); redraw(); toast(n > 1 ? "Section added - type its heading in the first new line" : "Line added - click its cells to type"); } catch (e) { fail(e); } };
    // a row of a table of lines: the same form as on Work done - the new line works like the ones around it
    const tb = b.progress.find(x => x.sheet === sh), lastR = tb ? Math.max(...tb.lines.map(l => l.r), ...(tb.heads || []).map(h => h.r)) : 0;
    const inTable = tb && tb.editable && canEditBill() && r > (tb.lines.length ? Math.min(...tb.lines.map(l => l.r)) - 4 : 1e9) && r <= lastR + 1;
    // a new line looks like the row above it (Match row above) - never like a bold heading: then the first plain row under it
    const isHead = t => t && [...t.cells].some(c => /font-weight:\s*(700|bold)/.test(c.getAttribute("style") || "") && c.textContent.trim());
    const likeAbove = above => { if (!above) return r; if (!isHead(above)) return +above.dataset.r;
      let n = above.nextElementSibling, k = 0; while (n && k++ < 8) { if (!isHead(n) && [...n.cells].some(c => c.textContent.trim())) return +n.dataset.r; n = n.nextElementSibling; } return +above.dataset.r; };
    $('[data-rw="above"]', rowBar).onclick = () => inTable ? lineForm(sh, { kind: "line", after: r - 1 }) : add(r, 1, [likeAbove(tr.previousElementSibling)]);
    $('[data-rw="below"]', rowBar).onclick = () => inTable ? lineForm(sh, { kind: "line", after: r }) : add(r + 1, 1, [likeAbove(tr)]);
    $('[data-rw="section"]', rowBar).onclick = () => inTable ? lineForm(sh, { kind: "head", after: r }) : add(r + 1, 2, [heading(), r]);
    $('[data-rw="hide"]', rowBar).onclick = async () => { try { IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/hide`, { sheet: sh, rows: [r] }); redraw(); toast("Line hidden"); } catch (e) { fail(e); } };
    $('[data-rw="clear"]', rowBar).onclick = () => { tr.classList.remove("sel"); rowBar.innerHTML = '<span class="muted">Click a row of the sheet to add a line or a section next to it, or to hide it.</span>'; };
  };
  $$("tr[data-r]", host).forEach(tr => tr.addEventListener("click", e => { if (!e.shiftKey) pickRow(tr); }));
  // ---- the formatting toolbar: pick cells (click, Shift+click a range, a row number = the whole row), then size / B / I / U
  SV.pages = d.pages || []; SV.manual = d.manual || [];
  fmtTools(v, host, b, sh, () => drawSheet(v, i, true));
  // ---- typing in a cell (the sheet may be zoomed: the box is placed in the sheet's own size)
  // Remarks: click picks the cell; double-click or start typing to write; Enter saves, Esc cancels, Alt+Enter = a new
  // line in the cell, Tab saves and goes to the next Remarks cell down. Plain text - never a figure, never a total.
  const openEd = (td, first) => {
    if ($(".ipa-cell", host)) return;
    const z = fr.zoom(), rm = td.classList.contains("rm");
    const nf = td.dataset.nf, raw = td.dataset.raw, pc = !rm && isPctNf(nf) && raw !== "" && !raw.startsWith("=") && !isNaN(Number(raw));
    const inp = document.createElement(rm ? "textarea" : "input");
    inp.className = "ipa-cell" + (rm ? " rm" : "");
    inp.value = first !== undefined ? first : (pc ? pct(Number(raw)) : raw);
    const hr = host.getBoundingClientRect(), r = td.getBoundingClientRect();
    Object.assign(inp.style, { left: (r.left - hr.left) / z + "px", top: (r.top - hr.top) / z + "px", width: Math.max(r.width / z, rm ? 160 : 90) + "px",
      height: Math.max(r.height / z, rm ? 44 : 24) + "px", fontSize: getComputedStyle(td).fontSize });
    host.appendChild(inp); inp.focus();
    if (first === undefined) inp.select(); else inp.setSelectionRange(inp.value.length, inp.value.length);
    let done = false;
    const commit = async (keep, next) => {
      if (done) return; done = true;
      const s = rm ? inp.value.replace(/\s+$/, "") : inp.value.trim();
      if (!keep || s === (pc ? pct(Number(raw)) : raw)) { inp.remove(); if (keep && next) goNext(td); return; }
      let val = s === "" ? (rm ? "" : null) : s;
      let asDate = false;
      if (!rm && val !== null && !s.startsWith("=") && (isDateNf(nf) || /^\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{2,4}$|^\d{1,2}(st|nd|rd|th)?[\s\-]+[A-Za-z]{3,9}\.?,?[\s\-]+\d{2,4}$/.test(s))) {
        const dn = parseDMY(s);                          // day first, always: 05/06/2026 = 5 June 2026
        if (Number.isNaN(dn)) { done = false; inp.classList.add("bad"); inp.title = "Invalid date - use DD/MM/YYYY"; toast("Invalid date - use DD/MM/YYYY"); inp.focus(); return; }
        if (dn !== null) { val = dn; asDate = true; }
      }
      if (!rm && !asDate && val !== null && !s.startsWith("=")) {
        // a figure typed or pasted with commas, AED, or in brackets for a minus is still a figure: 145,841.90 -> 145841.9
        let t = s.replace(/^AED\s*/i, "").replace(/\s+/g, ""); const neg = /^\(.*\)$/.test(t); if (neg) t = t.slice(1, -1);
        const n = Number(t.replace(/,/g, "").replace(/%$/, ""));
        if (!isNaN(n) && /^-?[\d,]*\.?\d+%?$/.test(t)) { const x = neg ? -n : n; val = isPctNf(nf) || t.endsWith("%") ? Math.round(x * 1e4) / 1e6 : x; }
      }
      if (rm && /^=/.test(val)) val = "\u200B" + val;     // a remark is words: "= done" is not worked out as a formula
      inp.disabled = true;
      if (next) IPA.rmNext = nextRm(td);
      if (await save({ set: { [sh]: { [td.dataset.k]: val } } })) {
        if (asDate && !isDateNf(nf)) { const [r_, c_] = td.dataset.k.split(",").map(Number);     // a date typed in a figure cell: shown as a date
          try { IPA.bill = await POST(`/store/est/ipa/bill/${b.id}/fmt`, { sheet: sh, cells: [[r_, c_]], set: { nf: NF.date } }); } catch (e) { /* the date is saved either way */ } }
        toast("Saved"); redraw(); } else { inp.remove(); IPA.rmNext = null; }
    };
    inp.onkeydown = e => {
      if (e.key === "Enter" && rm && e.altKey) { e.preventDefault(); const a = inp.selectionStart; inp.value = inp.value.slice(0, a) + "\n" + inp.value.slice(inp.selectionEnd); inp.setSelectionRange(a + 1, a + 1); }
      else if (e.key === "Enter") { e.preventDefault(); commit(true); }
      else if (e.key === "Tab" && rm) { e.preventDefault(); commit(true, true); }
      else if (e.key === "Escape") { e.stopPropagation(); commit(false); } };
    inp.onblur = () => commit(true);
  };
  const rms = () => $$("td.ed.rm", host);
  const nextRm = td => { const all = rms(), c = td.dataset.c; const k = all.indexOf(td);
    const n = all.slice(k + 1).find(x => x.dataset.c === c) || all[k + 1]; return n ? n.dataset.k : null; };
  const goNext = td => { const k = nextRm(td); const n = k && $(`td.ed[data-k="${k}"]`, host); if (n) { n.click(); openEd(n); } };
  $$("td.ed", host).forEach(td => {
    td.addEventListener("click", e => { if (e.shiftKey || td.classList.contains("rm")) return; openEd(td); });
    if (td.classList.contains("rm")) td.addEventListener("dblclick", e => { e.preventDefault(); openEd(td); });
  });
  // typing on a picked Remarks cell starts writing in it, as in Excel
  host.tabIndex = -1;
  if (!SV.rmkeys) { SV.rmkeys = true;
    document.addEventListener("keydown", e => {
      if (e.ctrlKey || e.metaKey || e.altKey || /INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || "")) return;
      const sel = document.querySelectorAll(".sv-in td.xsel"); if (sel.length !== 1 || !sel[0].classList.contains("rm")) return;
      if (e.key === "Enter" || e.key === "F2") { e.preventDefault(); sel[0].dispatchEvent(new MouseEvent("dblclick", { bubbles: true })); return; }
      if (e.key.length === 1) { e.preventDefault(); SV.rmOpen && SV.rmOpen(sel[0], e.key); } }); }
  SV.rmOpen = openEd;
  if (IPA.rmNext) { const k = IPA.rmNext; IPA.rmNext = null; const n = $(`td.ed[data-k="${k}"]`, host); if (n) { n.scrollIntoView({ block: "nearest" }); n.click(); openEd(n); } }
  // ---- Remarks: kept for the next bill unless asked
  if (d.remarks) { const rb = $("#sv-rows", v);
    if (rb) rb.insertAdjacentHTML("afterend", `<label class="sv-clr"><input type="checkbox" id="sv-clr" ${d.clear_remarks ? "checked" : ""}> Clear remarks for next bill <span class="muted small">- off: the next bill starts with these remarks</span></label>`);
    const cb = $("#sv-clr", v); if (cb) cb.onchange = async () => { try { const x = await POST(`/store/est/ipa/bill/${b.id}/opts`, { clear_remarks: cb.checked }); toast(x.clear_remarks ? "The next bill starts with empty remarks" : "The next bill keeps these remarks"); } catch (e) { fail(e); cb.checked = !cb.checked; } }; }
}
