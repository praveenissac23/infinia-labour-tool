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
  IPA.list = d;
  const fm = id => d.formats.find(f => f.id === id);
  const q = (ST.q[key()] || "").toLowerCase();
  const bills = d.bills.filter(b => !q || JSON.stringify(b).toLowerCase().includes(q));
  el.innerHTML = tools(null, { add: (d.formats.length ? `<button class="btn btn-primary" id="ipa-new">+ New bill</button>` : "") + `<button class="btn btn-ghost" id="ipa-up">Upload bill format</button>` }) +
    (!d.formats.length ? `<div class="card empty" style="text-align:left;line-height:1.6"><b>No bill format for this project yet.</b><br>
        Upload the last bill exactly as it was sent to the consultant (the Excel workbook with the cover, summary and the sheets with Previous % / Total %).
        Each new bill starts from it: last month's Total % becomes Previous %, the bill number goes up by one and the date is today.
        The workbook comes back out with the same layout, logo, stamps and formulas.<br><span class="muted small">An old .xls file must first be saved as .xlsx in Excel (File &gt; Save As).</span></div>` :
     bills.length ? `<div class="tw"><table class="t"><thead><tr><th>Bill</th><th>Issue date</th><th>Format</th><th class="r">Total due</th><th>Status</th><th>Last change</th><th></th></tr></thead><tbody>
      ${bills.map(b => `<tr class="rowc" data-ipa="${b.id}"><td><b>IPA ${esc(b.label || b.seq)}</b></td><td>${dt(b.issue_date)}</td><td class="small">${esc((fm(b.format_id) || {}).name || "")}</td>
        <td class="r"><b>${money(b.total_due)}</b></td><td>${st(b.status)}</td><td class="small muted">${esc(b.by)}${b.updated ? " · " + dt(b.updated) : ""}</td>
        <td class="r"><button class="btn btn-ghost btn-sm" data-ipaopen="${b.id}">Open</button></td></tr>`).join("")}</tbody></table></div>` :
     `<div class="card empty">No bills yet. Press <b>+ New bill</b> - it starts from the uploaded format.</div>`) +
    (d.formats.length ? `<div class="card" style="margin-top:14px"><h3>Bill formats</h3><div class="tw"><table class="t"><thead><tr><th>Format</th><th>File</th><th>Sheets</th><th class="c">% lines</th><th>Checked against Excel</th><th class="c">Bills</th><th>Uploaded</th><th></th></tr></thead><tbody>
      ${d.formats.map(f => `<tr><td><b>${esc(f.name)}</b></td><td class="small">${esc(f.filename)}</td><td class="small" title="${esc(f.sheets.join(", "))}">${f.sheets.length} sheets</td><td class="c">${f.lines}</td>
        <td class="small">${f.same === f.formulas ? `<span class="st g">all ${f.formulas} formulas match</span>` : `<span class="st a">${f.same} of ${f.formulas} formulas match</span>`}</td>
        <td class="c">${f.bills}</td><td class="small muted">${esc(f.by)} · ${dt(f.on)}</td><td class="r"><button class="btn btn-ghost btn-sm" data-fmdel="${f.id}">Remove</button></td></tr>`).join("")}</tbody></table></div></div>` : "");
  bindTools(el, () => SECTIONS["bills.ipa"](el));
  $("#ipa-up", el).onclick = uploadFormat;
  const nb = $("#ipa-new", el); if (nb) nb.onclick = newBill;
  $$("[data-ipa]", el).forEach(r => r.onclick = () => openBill(+r.dataset.ipa));
  $$("[data-fmdel]", el).forEach(b => b.onclick = async e => {
    e.stopPropagation();
    if (!confirmInline(b)) return;
    try { await DEL(`/store/est/ipa/format/${b.dataset.fmdel}`); toast("Format removed"); SECTIONS["bills.ipa"](el); } catch (x) { fail(x); }
  });
};
function billsRedraw() { if (key() === "bills.ipa" && $("#sec")) SECTIONS["bills.ipa"]($("#sec")); }

function uploadFormat() {
  const p = ST.b.project;
  modal("Upload bill format", [
    { k: "name", label: "Name", value: [p.consultant || p.client, "bill"].filter(Boolean).join(" - "), ph: "e.g. Consultant's IPA format", full: true },
  ], async v => {
    const f = ($("#fm-file") || {}).files; const file = f && f[0];
    if (!file) throw new Error("Pick the Excel bill.");
    if (/\.xls$/i.test(file.name)) throw new Error("This is an old .xls file. Open it in Excel, File > Save As > Excel Workbook (.xlsx), and upload that.");
    const fd = new FormData(); fd.append("project_id", ST.pid); fd.append("name", v.name); fd.append("file", file);
    $("#m-save").textContent = "Reading the workbook...";
    const r = await api("/store/est/ipa/format", { method: "POST", body: fd });
    const ok = r.same === r.formulas;
    toast(`Format read: ${r.lines} lines with Previous % / Total % on ${r.sheets.join(", ")}. ${ok ? `All ${r.formulas} formulas give Excel's own figures.` : `${r.same} of ${r.formulas} formulas match Excel - check the bill before sending.`}`, { ms: 7000, err: !ok });
    billsRedraw();
  }, { save: "Upload", bottom: `<div class="frm" style="margin-top:4px"><div class="f full"><label for="fm-file">The last bill as sent (Excel .xlsx) ${tip("The whole workbook: cover / summary and the sheets with the % of work done. It is kept on the server - every new bill is made from it, with the same layout, logo, stamps and formulas.")}</label><input type="file" id="fm-file" accept=".xlsx,.xlsm,.xls"></div></div>` });
}

async function newBill() {
  const fs = IPA.list.formats;
  const make = async fid => {
    const r = await POST("/store/est/ipa/new", { project_id: ST.pid, format_id: fid });
    toast("New bill started from the last one"); billsRedraw(); openBill(r.id);
  };
  if (fs.length === 1) { try { await make(fs[0].id); } catch (e) { fail(e); } return; }
  modal("New bill", [{ k: "fid", label: "Format", type: "select", options: fs.map(f => f.name), value: fs[fs.length - 1].name, full: true }],
    async v => { const f = fs.find(x => x.name === v.fid) || fs[fs.length - 1]; await make(f.id); }, { save: "Start the bill" });
}


// =====================================================================================================
// ONE BILL - four steps: Cover & details, Work done, Payments received, Review & send.
// The consultant's sheets are never re-laid out; these screens only gather what changes each month.
// =====================================================================================================
const IPA_STEPS = [["cover", "Cover & details"], ["work", "Work done"], ["pay", "Payments received"], ["review", "Review & send"]];
const pctTxt = v => v === null || v === undefined ? "" : (Math.round(v * 1e6) / 1e4).toLocaleString("en-US", { maximumFractionDigits: 2 }) + "%";
const amt = v => v === null || v === undefined || v === "" ? '<span class="muted">-</span>' : money(v, true);
let SAVING = Promise.resolve();

async function openBill(id, step) {
  try { IPA.bill = await GET(`/store/est/ipa/bill/${id}`); } catch (e) { return fail(e); }
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
  out.push(f.moved ? [true, `${f.moved} line${f.moved === 1 ? "" : "s"} moved on this month - ${money(f.now, false)} of work`] : [false, "No line has moved on since the last bill - type this month's % on Work done"]);
  if (f.bad.length) out.push([false, `${f.bad.length} line${f.bad.length === 1 ? " is" : "s are"} over 100% or below last month: ${f.bad.slice(0, 3).map(l => esc(l.item || l.desc.slice(0, 30))).join(", ")}`]);
  if (pay) {
    const open = pay.rows.filter(r => r.desc && /\d/.test(String(r.desc.value || "")) && !(r.amount && r.amount.value));
    out.push(open.length ? [false, `No amount yet for ${open.map(r => esc(r.desc.value)).join(", ")} - type it on Payments received once the money is in`] : [true, "Every earlier bill on the payments list has its amount"]);
  }
  return out;
}

function drawBill() {
  const b = IPA.bill, f = billFigs(b), ck = checks(b);
  const p = ST.b.project;
  $("#b-title").innerHTML = `<span class="ipa-ttl">Interim Bill ${esc(billNo(b))}</span> <span class="muted small">${esc(p.code)}${p.name ? " · " + esc(p.name) : ""}</span> ${st(b.status)}`;
  $("#b-tools").innerHTML = xpButtons("ipa", { id: b.id, name: `${p.code} IPA ${billNo(b)}` });
  const sub = { cover: `${dt(b.issue_date) || "no date"}`, work: `${f.moved} of ${f.entry} lines moved`,
                pay: b.payments.length ? `total ${money(b.payments[0].total, false)}` : "none on this format",
                review: ck.some(c => c[0] === false) ? `${ck.filter(c => c[0] === false).length} to look at` : "ready" };
  $("#ipa-nav").innerHTML = IPA_STEPS.map(([k, l], i) => `<button class="ipa-step ${IPA.step === k ? "on" : ""} ${k === "review" && ck.some(c => c[0] === false) ? "warn" : ""}" data-step="${k}">
      <span class="no">${i + 1}</span><span class="tx"><b>${l}</b><small>${sub[k]}</small></span></button>`).join("") +
    `<div class="ipa-due"><small>Total due this bill</small><b>AED ${money(b.total_due, false)}</b><small>work this month ${money(f.now, false)}</small></div>`;
  $$("#ipa-nav [data-step]").forEach(x => x.onclick = () => { IPA.step = x.dataset.step; drawBill(); $("#big .bbody").scrollTop = 0; });
  const m = $("#ipa-main");
  ({ cover: drawCover, work: drawWork, pay: ipaDrawPay, review: drawReview })[IPA.step](m);
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
    <div class="ipa-card"><h3>Notes <span class="muted small">(for the office - not printed)</span></h3><textarea id="cv-notes" rows="2" placeholder="e.g. sent to consultant by email, waiting for site measurement">${esc(b.notes)}</textarea></div>
    ${nextBtn("cover")}`;
  bindNext(m);
  const no = $("#cv-no"), d = $("#cv-date");
  no.onchange = async () => { if (no.value.trim() && await save({ bill_no: no.value.trim() })) { toast("Bill number saved"); drawBill(); } };
  d.onchange = async () => { if (d.value && await save({ issue_date: d.value })) { toast("Issue date saved"); drawBill(); } };
  $("#cv-notes").onchange = async e => { if (await save({ notes: e.target.value })) toast("Notes saved"); };
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
function workSection(t, i) {
  const shown = t.lines.filter(l => (l.item || l.desc || l.amount) && lineShown(l));
  if (!shown.length && (IPA.q || IPA.filter)) return "";
  return `<div class="ipa-card ipa-sec ${t.hidden ? "hid" : ""}" id="ipa-sec-${i}"><h3>${esc(t.sheet)}${t.hidden ? ` <span class="st">hidden sheet - not printed</span>` : ""}</h3>
    <div class="ipa-tw"><table class="ipa-lines"><colgroup><col style="width:64px"><col><col style="width:118px"><col style="width:86px"><col style="width:104px"><col style="width:104px"><col style="width:118px"><col style="width:118px"></colgroup>
    <thead><tr><th>Item</th><th>Description</th><th class="r">Amount</th><th class="r">Previous</th><th class="r in">This month %</th><th class="r in">Total %</th><th class="r">This month</th><th class="r">To date</th></tr></thead>
    <tbody>${shown.map(l => lineRow(t.sheet, l)).join("") || `<tr><td colspan="8" class="muted c">No lines match.</td></tr>`}</tbody></table></div></div>`;
}
function lineCells(l) {
  const now = nowPct(l);
  return { prev: l.prev === null ? "" : pctTxt(l.prev), nowAmt: l.amount && now ? money(l.amount * now) : '<span class="muted">-</span>',
           td: l.amount && l.total ? money(l.amount * l.total) : '<span class="muted">-</span>', now, cls: (l.total || 0) > 1.00005 || (now || 0) < -1e-9 ? "bad" : (Math.abs(now || 0) > 1e-9 ? "moved" : "") };
}
const pnum = v => v === null || v === undefined ? "" : String(Math.round(v * 1e6) / 1e4);
const pnow = v => v === null || v === undefined || Math.abs(v) < 1e-9 ? "" : pnum(v);          // nothing this month: left empty
function lineRow(sh, l) {
  const c = lineCells(l), id = `${sh}|${l.r}`, paid = IPA.bill.status === "Paid" && !ST.meta.me.admin;
  const edit = l.how && !paid;
  const inp = (k, v) => edit ? `<input class="ipa-in" data-noclear data-row="${esc(id)}" data-w="${k}" value="${k === "now" ? pnow(v) : pnum(v)}" placeholder="0" inputmode="decimal" autocomplete="off"><span class="pc">%</span>` : `<span class="ro">${v === null ? "" : pctTxt(v)}</span>`;
  return `<tr class="${c.cls}" data-line="${esc(id)}"><td class="it">${esc(l.item)}</td>
    <td class="ds">${esc(l.desc)}${l.unit && !/^(item|ls|l\.s\.?|lump ?sum)$/i.test(l.unit.trim()) ? ` <span class="muted small">(${esc(l.unit)})</span>` : ""}${!l.how && l.follows ? `<div class="fl">${esc(l.follows)}</div>` : ""}</td>
    <td class="r" data-l="Amount">${l.amount !== null ? money(l.amount, false) : `<span class="muted small">${esc(l.amount_text || "-")}</span>`}</td>
    <td class="r muted" data-c="prev" data-l="Previous">${c.prev}</td>
    <td class="r in" data-c="now" data-l="This month %">${inp("now", c.now)}</td><td class="r in" data-c="tot" data-l="Total %">${inp("tot", l.total)}</td>
    <td class="r" data-c="nowAmt" data-l="This month">${c.nowAmt}</td><td class="r" data-c="td" data-l="To date">${c.td}</td></tr>`;
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
  const all = () => $$("input.ipa-in", m);
  all().forEach(inp => {
    inp.dataset.was = inp.value;
    inp.onfocus = () => { inp.dataset.was = inp.value; setTimeout(() => inp.select(), 0); };
    const move = d => { const a = all(), i = a.indexOf(inp); const col = a.filter(x => x.dataset.w === inp.dataset.w); const j = col.indexOf(inp) + d; if (col[j]) col[j].focus(); };
    inp.onkeydown = e => {
      if (e.key === "Enter" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Escape") { e.stopPropagation(); inp.value = inp.dataset.was; inp.blur(); }
    };
    inp.onblur = () => commitLine(inp);
  });
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
      return `<div class="ipa-card"><h3>${esc(p.sheet)}</h3><div class="ipa-tw"><table class="ipa-pay"><thead><tr><th style="width:34px">#</th>${p.cols.map(c => `<th class="${c === "amount" ? "r" : ""}">${head[c] || c}</th>`).join("")}</tr></thead><tbody>
        ${show.map((r, i) => `<tr>${`<td class="muted">${i + 1}</td>`}${p.cols.map(c => payCell(p, r, c)).join("")}</tr>`).join("")}
        <tr class="tot"><td></td><td colspan="${p.cols.length - 1}">Total of previous payments</td><td class="r">${money(p.total, false)}</td></tr>
        </tbody></table></div>
        ${spare.length && IPA.addRow !== pi ? `<button class="btn btn-plain btn-sm" data-addpay="${pi}" style="margin-top:10px">+ Add a payment line</button>` : ""}</div>`;
    }).join("") + nextBtn("pay");
  bindNext(m);
  $$("[data-addpay]", m).forEach(x => x.onclick = () => { IPA.addRow = +x.dataset.addpay; ipaDrawPay(m); const e = $$(".ipa-pay tr:not(.tot)", m).pop(); const i = e && $("input", e); if (i) i.focus(); });
  $$("[data-pk]", m).forEach(bindPayInput);
}
function payCell(p, r, c) {
  const x = r[c]; if (!x) return "<td></td>";
  const paid = IPA.bill.status === "Paid" && !ST.meta.me.admin;
  const at = `data-sh="${esc(p.sheet)}" data-pk="${x.key}" data-c="${c}"`;
  if (c === "desc") return `<td>${paid ? esc(x.value || "") : `<input class="ipa-pin wide" ${at} value="${esc(x.value ?? "")}" placeholder="e.g. Payment Application No 9">`}</td>`;
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
    const refill = () => { const p = IPA.bill.payments.find(x => x.sheet === inp.dataset.sh); const r = p && p.rows.find(rr => rr.amount && rr.amount.key === inp.dataset.pk); inp.value = r && typeof r.amount.value === "number" && r.amount.value ? money(r.amount.value, false) : ""; };
  } else if (c === "desc") {
    inp.onchange = async () => { if (await save({ set: { [inp.dataset.sh]: { [inp.dataset.pk]: inp.value.trim() || null } } })) { toast("Saved"); drawBill(); } };
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
async function drawReview(m) {
  const b = IPA.bill, ck = checks(b), c = b.cover;
  m.innerHTML = `<div class="ipa-card ipa-rev">
      <div class="ipa-rev-top"><div><small>Total amount due for payment</small><div class="big">AED ${money(b.total_due, false)}</div>${c && c.words ? `<div class="muted small">${esc(c.words)}</div>` : ""}</div>
        <div class="ipa-rev-st"><label class="small muted">Status</label><select id="ipa-st">${IPA.list.statuses.map(s => `<option ${s === b.status ? "selected" : ""}>${s}</option>`).join("")}</select>
          ${b.status === "Draft" ? `<button class="btn btn-primary" id="ipa-submit">Mark as submitted</button>` : ""}</div></div>
      <ul class="ipa-checks">${ck.map(([ok, t]) => `<li class="${ok === true ? "ok" : ok === false ? "no" : "na"}"><span>${ok === true ? "&#10003;" : ok === false ? "!" : "&ndash;"}</span>${t}</li>`).join("")}</ul>
      <div class="ipa-rev-x">${xpButtons("ipa", { id: b.id, name: `${ST.b.project.code} IPA ${billNo(b)}` })}</div>
    </div>
    <div class="ipa-card"><h3>The bill as it will print <span class="muted small">- the consultant's own sheets, this month's figures</span></h3><div id="ipa-pv" class="ipa-pv"><div class="empty">Loading...</div></div></div>
    <div class="ipa-card"><details id="ipa-adv"><summary><b>Change a figure on a sheet</b> <span class="muted small">- for anything not on the steps before (e.g. a milestone % on a breakdown sheet)</span></summary>
      <div class="ipa-shbar"><button class="btn btn-plain btn-sm" id="sh-prev">&lsaquo;</button><select id="sh-pick">${b.sheets.map(s => `<option value="${s.i}" ${s.i === IPA.sheet ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select><button class="btn btn-plain btn-sm" id="sh-next">&rsaquo;</button>
        <span class="muted small">Blue figures can be typed over; yellow = changed this month. Click, type, Enter. Clearing a figure puts back last month's.</span></div>
      <div id="ipa-sheet"></div></details></div>
    <div class="ipa-card"><button class="btn btn-ghost" id="ipa-del">Remove this bill</button></div>
    ${nextBtn("review")}`;
  bindNext(m);
  $("#ipa-st").onchange = e => setStatus(e.target.value);
  const sb = $("#ipa-submit"); if (sb) sb.onclick = () => setStatus("Submitted");
  $("#ipa-del").onclick = async () => { if (!confirmInline($("#ipa-del"))) return; try { await DEL(`/store/est/ipa/bill/${b.id}`); toast("Bill removed"); closeBig(billsRedraw); } catch (x) { fail(x); } };
  if (IPA.sheet === undefined || !b.sheets.some(s => s.i === IPA.sheet)) IPA.sheet = (b.sheets[0] || {}).i;
  const pick = $("#sh-pick");
  const go = d => { const opts = [...pick.options]; const i = opts.findIndex(o => o.selected) + d; if (opts[i]) { pick.value = opts[i].value; pick.onchange(); } };
  pick.onchange = () => { IPA.sheet = +pick.value; drawSheet($("#ipa-sheet"), IPA.sheet); };
  $("#sh-prev").onclick = () => go(-1); $("#sh-next").onclick = () => go(1);
  $("#ipa-adv").ontoggle = () => { if ($("#ipa-adv").open && !$("#ipa-sheet").innerHTML) drawSheet($("#ipa-sheet"), IPA.sheet); };
  try {
    const t = await POST("/auth/download-token"); const tok = t.token || t.download_token;
    const pv = $("#ipa-pv"); if (!pv) return;
    pv.innerHTML = `<iframe src="/export/est/ipa/${b.id}?token=${encodeURIComponent(tok)}&format=preview&embed=1" title="Bill preview"></iframe>`;
  } catch (e) { const pv = $("#ipa-pv"); if (pv) pv.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
async function setStatus(s) {
  try { await POST(`/store/est/ipa/bill/${IPA.bill.id}/status`, { status: s }); IPA.bill.status = s; toast("Status: " + s); drawBill(); } catch (x) { fail(x); }
}

// one sheet as the consultant laid it out; typed figures open on a click
async function drawSheet(v, i) {
  v.innerHTML = `<div class="empty">Loading the sheet...</div>`;
  let d; try { d = await GET(`/store/est/ipa/bill/${IPA.bill.id}/sheet/${i}`); } catch (e) { v.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!document.getElementById("ipa-css")) document.head.appendChild(h(`<style id="ipa-css">${d.css}</style>`));
  v.innerHTML = `<div class="ipa-sheet"><div class="ipa-sheet-in">${d.html}</div></div>`;
  const paid = IPA.bill.status === "Paid" && !ST.meta.me.admin;
  if (paid) return;
  const host = $(".ipa-sheet-in", v), sh = d.name;
  $$("td.ed", v).forEach(td => td.onclick = () => {
    if ($(".ipa-cell", host)) return;
    const nf = td.dataset.nf, raw = td.dataset.raw, pc = isPctNf(nf) && raw !== "" && !raw.startsWith("=") && !isNaN(Number(raw));
    const inp = document.createElement("input");
    inp.className = "ipa-cell";
    inp.value = pc ? pct(Number(raw)) : raw;
    const hr = host.getBoundingClientRect(), r = td.getBoundingClientRect();
    Object.assign(inp.style, { left: (r.left - hr.left) + "px", top: (r.top - hr.top) + "px", width: Math.max(r.width, 90) + "px", height: Math.max(r.height, 24) + "px", fontSize: getComputedStyle(td).fontSize });
    host.appendChild(inp); inp.focus(); inp.select();
    let done = false;
    const commit = async keep => {
      if (done) return; done = true;
      const s = inp.value.trim();
      if (!keep || s === (pc ? pct(Number(raw)) : raw)) { inp.remove(); return; }
      let val = s === "" ? null : s;
      if (val !== null && !s.startsWith("=")) {
        const n = Number(s.replace(/,/g, "").replace(/%$/, ""));
        if (!isNaN(n) && /^-?[\d,]*\.?\d+%?$/.test(s)) val = isPctNf(nf) || s.endsWith("%") ? Math.round(n * 1e4) / 1e6 : n;
      }
      inp.disabled = true;
      if (await save({ set: { [sh]: { [td.dataset.k]: val } } })) { toast("Saved"); refreshNav(); drawSheet(v, i); } else inp.remove();
    };
    inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); commit(true); } else if (e.key === "Escape") { e.stopPropagation(); commit(false); } };
    inp.onblur = () => commit(true);
  });
}
