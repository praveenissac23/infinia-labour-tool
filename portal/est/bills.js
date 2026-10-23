/* Estimation > Bills: the bills (interim payment applications) sent to the client each month.
   The consultant's own Excel bill is uploaded once as the format; each month's bill starts from the last one
   (Previous % = last Total %, bill no. + 1, dated today, last bill put on the previous payments), staff type
   this month's Total % and payments, and it comes out as the same workbook, a preview and a PDF.
   Uses est.js (ST, api, modal, money, ...) and pcsheet.js (big). */

const IPA = { list: null, bill: null, view: "progress", q: "", only: false };
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
      ${d.formats.map(f => `<tr><td><b>${esc(f.name)}</b></td><td class="small">${esc(f.filename)}</td><td class="small">${esc(f.sheets.join(", "))}</td><td class="c">${f.lines}</td>
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

// ---------------------------------------------------------------- one bill
async function openBill(id) {
  try { IPA.bill = await GET(`/store/est/ipa/bill/${id}`); } catch (e) { return fail(e); }
  IPA.view = "progress"; IPA.q = ""; IPA.only = false;
  big("", "", billsRedraw, "est.ipa");
  drawBill();
}
function billThisMonth(b) {
  let n = 0;
  b.progress.forEach(t => t.lines.forEach(l => { if (l.amount && l.total !== null) n += l.amount * ((l.total || 0) - (l.prev || 0)); }));
  return r2(n);
}
function drawBill(focusKey) {
  const b = IPA.bill, paid = b.status === "Paid" && !ST.meta.me.admin;
  $("#b-title").innerHTML = `IPA ${esc(b.label || b.seq)} <span class="muted small">${esc(ST.b.project.code)} · ${esc(b.format)}</span>`;
  $("#b-tools").innerHTML = `<select id="ipa-st" title="Status">${IPA.list.statuses.map(s => `<option ${s === b.status ? "selected" : ""}>${s}</option>`).join("")}</select>` +
    xpButtons("ipa", { id: b.id, name: `${ST.b.project.code} IPA ${b.label || b.seq}` }) + `<button class="btn btn-ghost" id="ipa-del">Remove</button>`;
  const views = [["progress", "Progress"], ["payments", "Payments"]].concat(b.sheets.map(s => ["sheet:" + s.i, s.name]));
  const changed = b.progress.reduce((n, t) => n + t.lines.filter(l => l.changed).length, 0);
  $("#b-body").innerHTML = `
    <div class="strip">
      <div class="fig"><div class="l">Total due this bill</div><div class="v">${money(b.total_due, false)}</div><div class="s">as worked out on the consultant's sheet</div></div>
      <div class="fig"><div class="l">Work this month</div><div class="v">${money(billThisMonth(b), false)}</div><div class="s">${changed} line${changed === 1 ? "" : "s"} moved on since the last bill</div></div>
      <div class="fig"><div class="l">Issue date</div><div class="v">${dt(b.issue_date) || "-"}</div><div class="s">change it on the sheet</div></div>
      <div class="fig"><div class="l">Status</div><div class="v" style="font-size:15px">${st(b.status)}</div><div class="s">${esc(b.by)}</div></div>
    </div>
    <div class="tools"><span class="seg" id="ipa-views">${views.map(([k, l]) => `<button class="${IPA.view === k ? "on" : ""}" data-v="${k}">${esc(l)}</button>`).join("")}</span></div>
    ${paid ? `<div class="card small muted">This bill is paid - it can no longer be changed.</div>` : ""}
    <div id="ipa-view"></div>
    <div class="card" style="margin-top:14px"><h3>Notes</h3><textarea id="ipa-notes" rows="2" style="width:100%" placeholder="Anything to remember about this bill (not printed)">${esc(b.notes)}</textarea></div>`;
  $$("#ipa-views [data-v]").forEach(x => x.onclick = () => { IPA.view = x.dataset.v; drawBill(); });
  $("#ipa-st").onchange = async e => {
    try { await POST(`/store/est/ipa/bill/${b.id}/status`, { status: e.target.value }); b.status = e.target.value; toast("Status: " + b.status); drawBill(); } catch (x) { fail(x); }
  };
  $("#ipa-del").onclick = async () => {
    if (!confirmInline($("#ipa-del"))) return;
    try { await DEL(`/store/est/ipa/bill/${b.id}`); toast("Bill removed"); closeBig(billsRedraw); } catch (x) { fail(x); }
  };
  $("#ipa-notes").onchange = e => saveBill({}, e.target.value);
  const v = $("#ipa-view");
  if (IPA.view === "progress") drawProgress(v, paid, focusKey);
  else if (IPA.view === "payments") drawPayments(v, paid);
  else drawSheet(v, +IPA.view.split(":")[1], paid);
}
async function saveBill(set, notes, focusKey) {
  const body = { set };
  if (notes !== undefined) body.notes = notes;
  try { IPA.bill = await PUT(`/store/est/ipa/bill/${IPA.bill.id}`, body); } catch (e) { fail(e); drawBill(focusKey); return false; }
  if (notes === undefined) drawBill(focusKey); else toast("Notes saved");
  return true;
}

// The lines staff update each month: only Total % is typed; Previous % comes from the last bill.
function drawProgress(v, paid, focusKey) {
  const b = IPA.bill, q = IPA.q.toLowerCase();
  v.innerHTML = `<div class="tools"><input class="q" id="ipa-q" placeholder="Search the lines" value="${esc(IPA.q)}">
      <label class="small"><input type="checkbox" id="ipa-only" ${IPA.only ? "checked" : ""}> Only lines not yet 100%</label><span class="spacer"></span>
      <span class="small muted">Type this month's <b>Total %</b> - the rest is worked out by the consultant's own formulas.</span></div>` +
    b.progress.map(t => {
      const lines = t.lines.filter(l => (!q || (l.item + " " + l.desc).toLowerCase().includes(q)) && (!IPA.only || (l.tot_typed && (l.total || 0) < 0.99995)));
      const sum = k => r2(t.lines.reduce((n, l) => n + (l.amount && l.total !== null ? l.amount * (k === "prev" ? (l.prev || 0) : k === "tot" ? (l.total || 0) : (l.total || 0) - (l.prev || 0)) : 0), 0));
      return `<div class="card"><h3>${esc(t.sheet)}<span class="muted small" style="margin-left:8px">${t.lines.length} lines · to date ${money(sum("tot"), false)} · this month ${money(sum("now"), false)}</span></h3>
        ${lines.length ? `<div class="tw"><table class="t ipa-t"><thead><tr><th>Item</th><th>Description</th><th class="r">Amount</th><th class="r">Previous %</th><th class="r" style="width:110px">Total %</th><th class="r">This month %</th><th class="r">This month</th><th class="r">To date</th></tr></thead><tbody>
        ${lines.map(l => {
          const now = l.total !== null ? (l.total || 0) - (l.prev || 0) : null;
          const inp = l.tot_typed && !paid ? `<input class="ipa-pct ${l.changed ? "ch" : ""}" data-sh="${esc(t.sheet)}" data-k="${l.tot_key}" value="${pct(l.total)}" inputmode="decimal">` : `<span class="muted">${l.total !== null ? pct(l.total) + "%" : ""}</span>`;
          return `<tr${now < 0 ? ' class="neg"' : ""}><td class="small">${esc(l.item)}</td><td>${esc(l.desc)}</td><td class="r">${money(l.amount)}</td><td class="r">${l.prev !== null ? pct(l.prev) + "%" : ""}</td>
            <td class="r">${inp}</td><td class="r ${now < 0 ? "red" : ""}">${now ? pct(now) + "%" : '<span class="muted">-</span>'}</td>
            <td class="r">${l.amount && now ? money(l.amount * now) : '<span class="muted">-</span>'}</td><td class="r">${l.amount && l.total ? money(l.amount * l.total) : '<span class="muted">-</span>'}</td></tr>`;
        }).join("")}</tbody></table></div>` : `<div class="empty small">No lines match.</div>`}</div>`;
    }).join("");
  const qi = $("#ipa-q", v);
  qi.oninput = debounce(() => { IPA.q = qi.value; drawProgress(v, paid); const n = $("#ipa-q", v); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 250);
  $("#ipa-only", v).onchange = e => { IPA.only = e.target.checked; drawProgress(v, paid); };
  const all = $$(".ipa-pct", v);
  all.forEach((inp, i) => {
    const was = inp.value;
    const commit = async next => {
      let s = inp.value.trim().replace(/%$/, "").replace(/,/g, "");
      if (s === was) { if (next && all[i + 1]) all[i + 1].focus(); return; }
      if (s === "") { await saveBill({ [inp.dataset.sh]: { [inp.dataset.k]: null } }, undefined, next ? (all[i + 1] || {}).dataset?.k : null); return; }
      const n = Number(s);
      if (isNaN(n)) { toast("Type the Total % as a number, e.g. 45", { err: true }); inp.value = was; return; }
      if (n < 0 || n > 100) { toast("Total % must be between 0 and 100", { err: true }); inp.value = was; inp.focus(); return; }
      await saveBill({ [inp.dataset.sh]: { [inp.dataset.k]: Math.round(n * 1e4) / 1e6 } }, undefined, next ? (all[i + 1] || {}).dataset?.k : null);
    };
    inp.onkeydown = e => { if (e.key === "Enter" || (e.key === "Tab" && !e.shiftKey)) { e.preventDefault(); inp.onblur = null; commit(true); } else if (e.key === "Escape") { e.stopPropagation(); inp.value = was; inp.blur(); } };
    inp.onblur = () => commit(false);
    inp.onfocus = () => inp.select();
  });
  if (focusKey) { const f = all.find(x => x.dataset.k === focusKey); if (f) { f.focus(); f.select(); } }
}

// Payments received for earlier bills, as on the consultant's sheet ("Payment Application No N").
function drawPayments(v, paid) {
  const b = IPA.bill;
  if (!b.payments.length) { v.innerHTML = `<div class="card empty">This format has no table of previous payments. Payments can be typed on the sheet itself.</div>`; return; }
  const head = { desc: "Description", submitted: "Submitted", certified: "Certified", received: "Received on", amount: "Amount" };
  const shown = c => {
    if (!c) return "";
    const val = c.value;
    if (typeof val === "number" && /[dmy]{2}/i.test(c.nf) && val > 20000 && val < 80000) { const d = new Date(Date.UTC(1899, 11, 30) + val * 864e5); return dt(d.toISOString()); }
    if (typeof val === "number") return money(val);
    return esc(val ?? "");
  };
  v.innerHTML = b.payments.map(p => {
    const rows = p.rows.filter(r => p.cols.some(c => r[c] && r[c].raw !== null && r[c].raw !== "" && !String(r[c].raw).startsWith("=")) || r === p.rows.find(x => !(x.desc && x.desc.raw)));
    return `<div class="card"><h3>${esc(p.sheet)} - previous payments<span class="muted small" style="margin-left:8px">total ${money(p.total, false)}</span></h3>
      <div class="small muted" style="margin-bottom:8px">Type the amount received for each bill (a formula like <b>=(989148-280)/1.05</b> works, as in Excel). The next empty row can be used for a new line.</div>
      <div class="tw"><table class="t"><thead><tr>${p.cols.map(c => `<th class="${c === "amount" ? "r" : ""}">${head[c] || c}</th>`).join("")}</tr></thead><tbody>
      ${rows.map(r => `<tr>${p.cols.map(c => {
        const x = r[c]; if (!x) return "<td></td>";
        const raw = x.raw === null || x.raw === undefined ? "" : (typeof x.raw === "number" && /[dmy]{2}/i.test(x.nf) ? shown(x).replace(/<[^>]+>/g, "") : String(x.raw));
        const isF = String(x.raw || "").startsWith("=");
        return `<td class="${c === "amount" ? "r" : ""}">${paid ? shown(x) : `<input class="ipa-pay" data-sh="${esc(p.sheet)}" data-k="${x.key}" data-c="${c}" ${/[dmy]{2}/i.test(x.nf) ? 'data-date="1"' : ""} value="${esc(raw)}" style="width:${c === "desc" ? 260 : c === "amount" ? 210 : 130}px">`}${isF || (c === "amount" && typeof x.value === "number" && String(x.raw) !== String(x.value)) ? `<div class="small muted">${shown(x)}</div>` : ""}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table></div></div>`;
  }).join("");
  $$(".ipa-pay", v).forEach(inp => {
    const was = inp.value;
    inp.onchange = async () => {
      let s = inp.value.trim();
      let val = s === "" ? null : (inp.dataset.c === "amount" && /^-?[\d,]+(\.\d+)?$/.test(s) ? Number(s.replace(/,/g, "")) : s);
      if (val !== null && inp.dataset.date) { const n = excelDate(s); if (n) val = n; }
      if (s === was) return;
      await saveBill({ [inp.dataset.sh]: { [inp.dataset.k]: val } });
    };
  });
}

// "20.10.2026", "20/10/26", "20-Oct-26", "2026-10-20" -> Excel's day number (for date cells), or 0.
function excelDate(s) {
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/), y, mo, d;
  if (m) [y, mo, d] = [+m[1], +m[2], +m[3]];
  else if ((m = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$/))) [d, mo, y] = [+m[1], +m[2], +m[3]];
  else if ((m = s.match(/^(\d{1,2})[ .\/-]([A-Za-z]{3})[a-z]*[ .\/-](\d{2,4})$/))) { mo = MON.findIndex(x => x.toLowerCase() === m[2].toLowerCase()) + 1; [d, y] = [+m[1], +m[3]]; }
  else return 0;
  if (y < 100) y += 2000;
  if (!(mo >= 1 && mo <= 12 && d >= 1 && d <= 31)) return 0;
  return Math.round((Date.UTC(y, mo - 1, d) - Date.UTC(1899, 11, 30)) / 864e5);
}

// One sheet as the consultant laid it out; the cells that can be typed in are marked and open on a click.
async function drawSheet(v, i, paid) {
  v.innerHTML = `<div class="empty">Loading the sheet...</div>`;
  let d; try { d = await GET(`/store/est/ipa/bill/${IPA.bill.id}/sheet/${i}`); } catch (e) { v.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!document.getElementById("ipa-css")) document.head.appendChild(h(`<style id="ipa-css">${d.css}
    .ipa-sheet{background:#fff;border:1px solid var(--line2);border-radius:9px;overflow:auto;padding:12px;max-height:calc(100vh - 290px)}
    .ipa-sheet .xt td.ed{cursor:text}
    .ipa-sheet .xt td.ed.n,.ipa-sheet .xt td.ed.tot{box-shadow:inset 0 0 0 1px #9DB8E0;background-color:#F3F8FF}
    .ipa-sheet .xt td.ed.ch{background-color:#FFF6D6}
    .ipa-sheet .xt td.ed:hover{box-shadow:inset 0 0 0 2px #2F6FD0}
    .ipa-sheet .xt td.ed.ch{box-shadow:inset 0 0 0 1px #E5C66A}
    .ipa-cell{position:absolute;z-index:5;border:2px solid #2F6FD0;font:inherit;padding:0 3px;background:#fff;box-sizing:border-box}
    </style>`));
  v.innerHTML = `<div class="small muted" style="margin-bottom:6px">${paid ? "" : `Blue cells are the figures that can be typed in (yellow = changed this month); any text without a formula can be changed too. Click one, type, press Enter. Clearing a cell puts back last month's figure. % cells take the percentage (45 = 45%). A formula starting with = works as in Excel.`}</div>
    <div class="ipa-sheet"><div style="position:relative;display:inline-block">${d.html}</div></div>`;
  if (paid) return;
  const host = $(".ipa-sheet > div", v);
  const sh = d.name;
  $$("td.ed", v).forEach(td => td.onclick = () => {
    if ($(".ipa-cell", host)) return;
    const nf = td.dataset.nf, raw = td.dataset.raw, pc = isPctNf(nf) && raw !== "" && !raw.startsWith("=") && !isNaN(Number(raw));
    const inp = document.createElement("input");
    inp.className = "ipa-cell";
    inp.value = pc ? pct(Number(raw)) : raw;
    const hr = host.getBoundingClientRect(), r = td.getBoundingClientRect();
    Object.assign(inp.style, { left: (r.left - hr.left) + "px", top: (r.top - hr.top) + "px", width: Math.max(r.width, 90) + "px", height: Math.max(r.height, 22) + "px", fontSize: getComputedStyle(td).fontSize });
    host.appendChild(inp); inp.focus(); inp.select();
    let done = false;
    const commit = async keep => {
      if (done) return; done = true;
      if (!keep) { inp.remove(); return; }
      let s = inp.value.trim();
      if (s === (pc ? pct(Number(raw)) : raw)) { inp.remove(); return; }
      let val = s === "" ? null : s;
      if (val !== null && !s.startsWith("=")) {
        const n = Number(s.replace(/,/g, "").replace(/%$/, ""));
        if (!isNaN(n) && /^-?[\d,]*\.?\d+%?$/.test(s)) val = isPctNf(nf) || s.endsWith("%") ? Math.round(n * 1e4) / 1e6 : n;
      }
      inp.disabled = true;
      const ok = await saveBillQuiet({ [sh]: { [td.dataset.k]: val } });
      if (ok) drawBill(); else inp.remove();
    };
    inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); commit(true); } else if (e.key === "Escape") { e.stopPropagation(); commit(false); } };
    inp.onblur = () => commit(true);
  });
}
async function saveBillQuiet(set) {
  try { IPA.bill = await PUT(`/store/est/ipa/bill/${IPA.bill.id}`, { set }); return true; } catch (e) { fail(e); return false; }
}
