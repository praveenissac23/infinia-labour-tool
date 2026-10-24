// Estimation > a project > Previous records - bringing in what happened before the app: certified client bills,
// subcontractor payment certificates, contracts and variations.
// Each file is opened on this computer (portal/est/agreement.js: Excel, PDF, a scanned PDF or a photo - text
// recognition runs here); only its words go to the server, which reads the figures (app/est_prevread.py) and checks
// them against the certificate's own arithmetic. The QS checks every figure on the form and saves; nothing is saved
// unread and nothing of the file is kept - its name goes on the record so the original can always be found.
const PREV = { q: [], busy: false };
const PREV_KINDS = {
  clientpc: { label: "Client bills (IPAs)", sub: "certified by the consultant / client", accept: ".xlsx,.xlsm,.xls,.pdf,.jpg,.jpeg,.png,image/*" },
  subpc: { label: "Subcontractor PCs", sub: "payment certificates issued to subcontractors", accept: ".xlsx,.xlsm,.xls,.pdf,.jpg,.jpeg,.png,image/*" },
  contract: { label: "Contracts", sub: "main contract, subcontract agreements, LPOs", accept: ".pdf,.docx,.xlsx,.xlsm,.jpg,.jpeg,.png,image/*" },
  variation: { label: "Variations", sub: "variation log, cost proposals, approvals", accept: ".xlsx,.xlsm,.pdf,.docx,.jpg,.jpeg,.png,image/*" },
};
const PREV_ST = { wait: ["Waiting", ""], reading: ["Reading", "b"], check: ["Check and save", "a"], saved: ["Saved", "g"], skipped: ["Skipped", ""], error: ["Could not read", "r"] };

SECTIONS["prev.rec"] = el => {
  const b = ST.b;
  const nPc = b.subs.reduce((n, s) => n + s.pcs.length, 0);
  const counts = { clientpc: b.clientpcs.length, subpc: nPc, contract: b.subs.length, variation: b.variations.length };
  const q = PREV.q.filter(x => x.pid === ST.pid);
  el.innerHTML = `<div class="prev-wrap"><h3>Previous records - ${esc(b.project.code)}<span class="spacer"></span><span class="small muted">for going live: bring in what happened before the app</span></h3>
      <div class="small muted" style="margin:-4px 0 12px">Pick the files (many at once is fine) - Excel, PDF, a scanned PDF or a photo, any size. Each is read on this computer and opened on its form with every figure filled in and checked against the certificate's own sums. Check it and Save; the next one opens. Nothing of the file is kept: its name goes on the record.
        ${tip("Bring the certificates in the order they were made (PC 01, 02, 03 ...) - each one's previous figures are checked against the ones already brought in. A figure the certificate's arithmetic does not agree with is shown in red before you save.")}</div>
      <div class="prev-cards">${Object.entries(PREV_KINDS).map(([k, x]) => `<div class="prev-card"><b>${esc(x.label)}</b><span class="small muted">${esc(x.sub)}</span>
        <div class="n">${counts[k]}<span class="small muted"> in the app</span></div>
        <button type="button" class="btn btn-primary" data-pup="${k}">+ Upload</button><input type="file" id="pf-${k}" accept="${x.accept}" multiple hidden></div>`).join("")}</div>
      ${q.length ? `<div class="tw" style="margin-top:12px"><table class="t"><thead><tr><th>File</th><th>Type</th><th>Read as</th><th class="r">To date</th><th class="r">Amount due</th><th>Status</th><th></th></tr></thead><tbody>
        ${q.map((x, i) => { const [sl, sc] = PREV_ST[x.st]; return `<tr><td>${esc(x.file.name)} <span class="small muted">${prevSize(x.file.size)}</span></td><td>${esc(PREV_KINDS[x.kind].label.replace(/ \(.*/, ""))}</td>
          <td>${esc(x.as || "")}</td><td class="r">${x.todate != null ? money(x.todate, false) : ""}</td><td class="r">${x.due != null ? money(x.due, false) : ""}</td>
          <td><span class="st ${sc}">${esc(x.note && x.st === "reading" ? x.note : sl)}</span>${x.bad ? ` <span class="small" style="color:var(--red)">${x.bad} check${x.bad > 1 ? "s" : ""} not agreeing</span>` : ""}${x.st === "error" ? `<div class="small" style="color:var(--red)">${esc(x.err || "")}</div>` : ""}</td>
          <td class="nowrap">${["check", "error", "skipped"].includes(x.st) ? `<button class="btn btn-ghost" data-popen="${PREV.q.indexOf(x)}">${x.st === "check" ? "Open" : "Try again"}</button>` : ""}${["wait", "check"].includes(x.st) ? ` <button class="btn btn-plain" data-pskip="${PREV.q.indexOf(x)}">Skip</button>` : ""}</td></tr>`; }).join("")}
      </tbody></table></div>` : ""}
    </div>`;
  $$("[data-pup]", el).forEach(btn => { const k = btn.dataset.pup, fi = $("#pf-" + k, el); btn.onclick = () => fi.click();
    fi.onchange = () => { const files = [...fi.files]; fi.value = ""; if (!files.length) return;
      files.sort((a, b2) => a.name.localeCompare(b2.name, undefined, { numeric: true }));            // PC 01, PC 02 ... in order
      files.forEach(f => PREV.q.push({ pid: ST.pid, kind: k, file: f, st: "wait" })); prevDraw(); prevRun(); }; });
  $$("[data-popen]", el).forEach(btn => btn.onclick = () => { const x = PREV.q[+btn.dataset.popen]; if (x.st === "check" && x.read) prevOpen(x); else { x.st = "wait"; x.read = null; prevDraw(); prevRun(); } });
  $$("[data-pskip]", el).forEach(btn => btn.onclick = () => { PREV.q[+btn.dataset.pskip].st = "skipped"; prevDraw(); prevRun(); });
};
function prevSize(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }
function prevDraw() { if (key() === "prev.rec" && $("#sec")) SECTIONS["prev.rec"]($("#sec")); }

// One file at a time: read it, open its form; the next starts when that form is saved, skipped or closed.
async function prevRun() {
  if (PREV.busy || !$("#modal").classList.contains("hide")) return;
  const x = PREV.q.find(y => y.st === "wait" && y.pid === ST.pid); if (!x) return;
  PREV.busy = true;
  try {
    if (x.kind === "clientpc" || x.kind === "subpc") {
      x.st = "reading"; x.note = "Opening the file ..."; prevDraw();
      const d = await readAgreement(x.file, m => { x.note = m; prevDraw(); });
      const subs = ST.b.subs.map(s => ({ id: s.id, name: s.name }));
      x.read = await POST(`/store/est/read/${x.kind === "clientpc" ? "ipa" : "subpc"}`, { lines: d.lines, subs });
      const f = x.read.fields || {};
      x.bad = (x.read.checks || []).filter(c => !c.ok).length;
      if (x.kind === "clientpc") { x.as = `Bill ${f.bill_label || f.seq || "?"}${f.submitted ? " · " + dt(f.submitted) : ""}`; x.todate = f.claimed_cum; x.due = f.total; }
      else { x.as = `${f.sub_name || "?"} · PC ${f.seq != null ? pad(f.seq, 2) : "?"}`; x.todate = (f.work_cum || 0) + (f.var_cum || 0); x.due = f.total; }
      x.st = "check"; prevDraw(); prevOpen(x);
    } else { x.st = "check"; prevDraw(); prevOpen(x); }
  } catch (e) { x.st = "error"; x.err = e.message || String(e); prevDraw(); }
  finally { PREV.busy = false; }
  if (x.st === "error") prevRun();
}

// Watch the form that opens: closed by its Save -> saved; by Cancel -> left to open again. Then the next file.
function prevWatch(x) {
  let saving = false;
  const save = $("#m-save"), cancel = $("#m-cancel");
  if (save) save.addEventListener("click", () => { saving = true; }, true);
  if (cancel) cancel.addEventListener("click", () => { saving = false; }, true);
  const mo = new MutationObserver(() => {
    if (!$("#modal").classList.contains("hide")) return;
    mo.disconnect();
    if (saving) x.st = "saved";
    setTimeout(() => { window.PREV_NO_OPEN = false; }, 2000);
    prevDraw();
    setTimeout(prevRun, 150);
  });
  mo.observe($("#modal"), { attributes: true, attributeFilter: ["class"] });
}
// A file handed to a form's own "Read from ..." box, as if picked there - the form's own reader fills it.
function prevHand(input, file) {
  const el = $(input); if (!el) return;
  const dt_ = new DataTransfer(); dt_.items.add(file); el.files = dt_.files; el.dispatchEvent(new Event("change", { bubbles: true }));
}
function prevOpen(x) {
  if (x.kind === "clientpc") prevCpcForm(x);
  else if (x.kind === "subpc") prevPcForm(x);
  else if (x.kind === "contract") prevContract(x);
  else prevVariation(x);
}
function prevChecks(r) {
  const cs = r.checks || [];
  const rows = cs.map(c => `<div class="${c.ok ? "ok" : "bad"}">${c.ok ? "&#10003;" : "&#10007;"} ${esc(c.name)} <span class="muted">- ${esc(c.detail)}</span></div>`).join("");
  const notes = (r.notes || []).map(n => `<div class="warn-t">${esc(n)}</div>`).join("");
  return `<div class="prev-chk">${rows || '<div class="warn-t">The certificate\'s figures could not all be checked - compare every figure with the file.</div>'}${notes}</div>`;
}
const prevN = v => Number(String(v ?? "").replace(/,/g, "")) || 0;

// ---- a client bill -------------------------------------------------------------------------------------------
function prevCpcForm(x) {
  const f = x.read.fields || {}, b = ST.b;
  const dup = f.seq != null && b.clientpcs.find(c => +c.seq === +f.seq);
  const xl = /\.xls[xm]?$/i.test(x.file.name);
  const extra = (f.extra || []).map(e => `${e.label} ${money(e.v, false)}`).join("; ");
  const remarks = [`Previous record: ${x.file.name}`, f.bill_label ? `bill ${f.bill_label}` : "", f.previous != null ? `previous payments ${money(f.previous, false)}` : "",
                   f.vat != null ? `VAT ${money(f.vat, false)}` : "", f.authority ? `authority fees ${money(f.authority, false)}` : "", extra, f.total != null ? `amount due ${money(f.total, false)}` : ""].filter(Boolean).join(" · ");
  modal(`Previous bill - ${x.file.name}`, [
    { k: "seq", label: "Bill / certificate no.", type: "num", value: f.seq ?? "", tip: "The bill's own number - the bills are kept in this order." },
    { k: "pc_type", label: "Type", type: "select", options: ["Interim", "Advance", "Final"], value: f.pc_type || "Interim" },
    { k: "submitted", label: "Submitted on", type: "date", value: f.submitted || "" },
    { k: "period_to", label: "Period up to", type: "date", value: f.period_to || f.submitted || "" },
    { k: "claimed_cum", label: "Work done to date - claimed (AED)", type: "money", value: f.claimed_cum ?? "", tip: "Total value of work done on the bill, with the approved variations on it." },
    { k: "certified_cum", label: "Certified to date (AED)", type: "money", value: f.claimed_cum ?? "", tip: "What the consultant certified - the same as claimed unless the certified copy says less." },
    { k: "certified_on", label: "Certified on", type: "date", value: "" },
    { k: "adv_rec_cum", label: "Advance recovered to date", type: "money", value: f.adv_rec_cum ?? "" },
    { k: "ret_cum", label: "Retention to date", type: "money", value: f.ret_cum ?? "" },
    { k: "ret_rel_cum", label: "Retention released to date", type: "money", value: f.ret_rel_cum ?? "" },
    { k: "mos_cum", label: "Material on site to date", type: "money", value: "" },
    { k: "status", label: "Status", type: "select", options: ["Certified", "Invoiced", "Paid"], value: "Paid", tip: "Where this bill stands now - most previous bills are paid." },
    { k: "invoice_no", label: "Our invoice no.", value: "" },
    { k: "remarks", label: "Remarks", type: "area", value: remarks, full: true },
  ], async v => {
    if (!v.claimed_cum) throw new Error("Type the work done to date from the bill.");
    const d = Object.assign({}, v, { project_id: ST.pid, adv_auto: false, ret_auto: false });
    ["submitted", "period_to", "certified_on"].forEach(k => { if (!d[k]) d[k] = null; });
    if (!d.seq) delete d.seq;
    await POST("/store/est/clientpcs", d);
    if (xl && $("#pv-fmt") && $("#pv-fmt").checked) await prevAsFormat(x.file);
    await reload(); toast(`Bill ${v.seq || ""} saved`);
  }, { wide: true, save: "Save bill",
       top: `${dup ? `<div class="warn">Bill ${esc(String(f.seq))} is already in the app - saving adds it again. Skip it if it is the same bill.</div>` : ""}${prevChecks(x.read)}`,
       bottom: xl ? `<label class="chk" style="margin-top:8px"><input type="checkbox" id="pv-fmt" ${prevLatest(x, "clientpc") ? "checked" : ""}> Also use this workbook as the bill format - the next bill (in Bills) is made from it, line by line ${tip("Tick it for the LAST bill: the whole workbook is kept on the server and next month's bill starts from it, with every % line, the layout, logo and formulas.")}</label>` : "" });
  prevWatch(x);
}
function prevLatest(x, kind) {           // the highest bill no. among the files picked of this kind
  const n = y => +((y.read && y.read.fields && y.read.fields.seq) || 0);
  const all = PREV.q.filter(y => y.pid === x.pid && y.kind === kind && y.st !== "skipped");
  return all.every(y => n(y) <= n(x) || !y.read);
}
async function prevAsFormat(file) {
  const fd = new FormData(); fd.append("project_id", ST.pid); fd.append("name", file.name.replace(/\.xls[xm]?$/i, ""));
  const PART = 700 * 1024;
  if (file.size > PART) {
    const id = [...crypto.getRandomValues(new Uint8Array(12))].map(b => b.toString(16).padStart(2, "0")).join(""), n = Math.ceil(file.size / PART);
    for (let i = 0; i < n; i++) { const pf = new FormData(); pf.append("upload_id", id); pf.append("index", i); pf.append("file", file.slice(i * PART, (i + 1) * PART), "part"); await api("/store/est/ipa/format/part", { method: "POST", body: pf }); }
    fd.append("upload_id", id); fd.append("parts", n); fd.append("filename", file.name);
  } else fd.append("file", file);
  const r = await api("/store/est/ipa/format", { method: "POST", body: fd });
  toast(`Bill format kept: ${r.lines} lines - the next bill starts from it (Bills tab)`, { ms: 5000 });
}

// ---- a subcontractor payment certificate ----------------------------------------------------------------------
function prevPcForm(x, keepSub) {
  const f = x.read.fields || {}, b = ST.b;
  const subs = b.subs.filter(s => s.status !== "Cancelled");
  const sid = keepSub || f.sub_id || "";
  const fields = [
    { k: "sub_id", label: "Subcontractor", type: "select", noseg: true, full: true, value: sid,
      options: [["", subs.length ? "- Pick the subcontractor -" : "- None on this project yet: add it below -"], ...subs.map(s => [s.id, `${s.name}${s.scope ? " - " + s.scope : ""}`])] },
    { k: "seq", label: "PC no.", type: "num", value: f.seq ?? "" },
    { k: "pc_type", label: "Type", type: "select", options: ["Interim", "Advance", "Final", "Retention release"], value: "Interim" },
    { k: "inv_ref", label: "Invoice no.", value: f.inv_ref || "" },
    { k: "inv_date", label: "Invoice date", type: "date", value: f.inv_date || "" },
    { k: "received", label: "Invoice received", type: "date", value: f.received || "" },
    { k: "measured_on", label: "Measurement date", type: "date", value: f.measured_on || "" },
    { k: "issued", label: "IPC issued on", type: "date", value: f.issued || "" },
    { k: "work_cum", label: "Value of work executed to date", type: "money", value: f.work_cum ?? "" },
    { k: "var_cum", label: "Variations executed to date", type: "money", value: f.var_cum ?? "" },
    { k: "mos_cum", label: "Material on site to date", type: "money", value: "" },
    { k: "adv_cum", label: "Advance paid to date", type: "money", value: f.adv_cum ?? "", tip: "The advance on the certificate (B). The part not already on the earlier PCs is put on this one." },
    { k: "adv_rec_cum", label: "Advance recovered to date", type: "money", value: f.adv_rec_cum ?? "" },
    { k: "ret_cum", label: "Retention to date", type: "money", value: f.ret_cum ?? "" },
    { k: "ret_rel_cum", label: "Retention released to date", type: "money", value: f.ret_rel_cum ?? "" },
    { k: "other_cum", label: "Deductions to date (material, manpower, plant, other)", type: "money", value: f.other_cum ?? "" },
    { k: "other_note", label: "Deduction details", value: f.other_note || "", full: true },
    { k: "status", label: "Status now", type: "select", options: ["Paid", "With Accounts", "PC issued"], value: "Paid" },
    { k: "paid_on", label: "Paid on", type: "date", value: "" },
    { k: "paid_amount", label: "Amount paid (AED)", type: "money", value: f.total ?? "", tip: "The total amount due on the certificate (with VAT) - change it if a different amount was paid." },
    { k: "remarks", label: "Remarks", type: "area", full: true, value: `Previous record: ${x.file.name}${f.agreement ? " · agreement " + f.agreement : ""}` },
  ];
  // what the app works out from this and the earlier PCs of the same subcontractor, against the certificate
  let calc = null;
  const live = () => {
    const v = readForm(fields), s = b.subs.find(y => y.id === +v.sub_id), box = $("#pv-calc"); if (!box) return;
    if (!s) { box.innerHTML = `<div class="warn-t">Pick the subcontractor to compare with the PCs already in the app.</div>`; return; }
    const seq = prevN(v.seq), earlier = prevEarlier(s, seq, f);
    const advBefore = earlier.reduce((a, p) => a + Number(p.adv_amount || 0), 0);
    const me = { seq, work_cum: prevN(v.work_cum), var_cum: prevN(v.var_cum), mos_cum: prevN(v.mos_cum), adv_amount: r2(prevN(v.adv_cum) - advBefore),
                 adv_rec_cum: prevN(v.adv_rec_cum), ret_cum: prevN(v.ret_cum), ret_rel_cum: prevN(v.ret_rel_cum), other_cum: prevN(v.other_cum) };
    const c = chainCalc([...earlier, me], s.adv_pct, s.ret_pct, s.vat_pct);
    const mine = c[c.length - 1], prevNet = c.length > 1 ? c[c.length - 2].net : 0;
    calc = mine;
    const row = (l, a, cert, ok) => `<tr><td>${l}</td><td class="r">${money(a, false)}</td><td class="r">${cert == null ? "" : money(cert, false)}</td><td>${cert == null ? "" : ok ? '<span class="ok">&#10003;</span>' : '<span class="bad">&#10007;</span>'}</td></tr>`;
    const near = (a, bb, t = 0.05) => bb == null || Math.abs(a - bb) <= t;
    box.innerHTML = `<table class="t prev-calc"><thead><tr><th></th><th class="r">The app</th><th class="r">Certificate</th><th></th></tr></thead><tbody>
      ${row(prevCanOpen(s, seq, f) && prevOpenOn() ? "Previously certified (the opening line)" : `Previously certified (${earlier.length} earlier PC${earlier.length === 1 ? "" : "s"} in the app)`, prevNet, f.prev_cert, near(prevNet, f.prev_cert))}
      ${row("This certificate (net)", mine.this, f.net, near(mine.this, f.net))}
      ${row(`VAT ${s.vat_pct}%`, mine.vat, f.vat, near(mine.vat, f.vat))}
      ${row("Amount due", mine.payable, f.total, near(mine.payable, f.total, 1.0))}</tbody></table>
      ${me.adv_amount < -0.005 ? `<div class="warn-t">The advance on this PC (${money(prevN(v.adv_cum), false)}) is less than the earlier PCs already paid - check it.</div>` : ""}
      ${f.prev_cert != null && !near(prevNet, f.prev_cert) ? `<div class="warn-t">The earlier PCs in the app add up to ${money(prevNet, false)}, the certificate says ${money(f.prev_cert, false)} - bring in the missing earlier PCs first (or check the figures).</div>` : ""}
      ${prevCanOpen(s, seq, f) ? `<label class="chk" style="margin-top:8px;color:var(--ink)"><input type="checkbox" id="pv-open" ${prevOpenOn(s) ? "checked" : ""}> Put PC 01${seq > 2 ? " to PC " + pad(seq - 1, 2) : ""} in as one opening line - previously certified ${money(f.prev_cert, false)}, paid (with VAT)
        ${tip("When the earlier certificates are not being brought in one by one: they go in as one line, so this certificate, the totals certified and paid, and what is left to pay all come out right. Untick it to bring the earlier PCs in yourself.")}</label>` : ""}
      ${s.pcs.some(p => +p.seq === seq) ? `<div class="warn">PC ${pad(seq, 2)} of ${esc(s.name)} is already in the app - saving adds it again. Skip it if it is the same certificate.</div>` : ""}`;
  };
  modal(`Previous PC - ${x.file.name}`, fields, async v => {
    const s = b.subs.find(y => y.id === +v.sub_id);
    if (!s) throw new Error("Pick the subcontractor (or add it as a new one).");
    if (!v.work_cum && v.pc_type !== "Advance") throw new Error("Type the value of work executed to date from the certificate.");
    const seq = prevN(v.seq), opening = prevCanOpen(s, seq, f) && $("#pv-open") && $("#pv-open").checked;
    const earlier = opening ? [] : s.pcs.filter(p => +p.seq < seq);
    const advBefore = earlier.reduce((a, p) => a + Number(p.adv_amount || 0), 0);
    if (opening) {           // the earlier certificates as one opening line: previously certified, paid with VAT
      const pv = r2(f.prev_cert), vat = r2(pv * (s.vat_pct || 0) / 100);
      await POST("/store/est/subpcs", { sub_id: s.id, seq: Math.max(1, seq - 1), pc_type: "Interim", work_cum: pv, var_cum: 0, mos_cum: 0, adv_amount: 0, adv_rec_cum: 0,
        ret_cum: 0, ret_rel_cum: 0, other_cum: 0, adv_auto: false, ret_auto: false, status: "Paid", paid_amount: r2(pv + vat), received: null,
        certified_on: v.issued || null, issued: v.issued || null, to_accounts: v.issued || null, paid_on: v.issued || null,
        remarks: `Opening line: PC 01${seq > 2 ? " to PC " + pad(seq - 1, 2) : ""} certified before the app (${money(pv, false)} + VAT), taken from ${x.file.name}` });
    }
    const d = Object.assign({}, v, { sub_id: s.id, adv_amount: r2(prevN(v.adv_cum) - advBefore), adv_auto: false, ret_auto: false });
    delete d.adv_cum;
    if (d.adv_amount < 0) d.adv_amount = 0;
    if (!d.seq) delete d.seq;
    d.certified_on = d.issued || null;
    if (d.status !== "PC issued") d.to_accounts = d.issued || null;
    if (d.status !== "Paid") { d.paid_on = null; d.paid_amount = 0; }
    // the certificate rounds its total to the dirham (10,225.69 -> 10,226.00): paid as the app works it out, so nothing
    // is left over or overpaid by the fils of the rounding; the certificate's own total is kept in the remarks
    else if (calc && f.total != null && Math.abs(prevN(d.paid_amount) - f.total) < 0.005 && Math.abs(calc.payable - f.total) > 0.004 && Math.abs(calc.payable - f.total) <= 1) {
      d.paid_amount = calc.payable; d.remarks = `${d.remarks} · certificate total ${money(f.total, false)} (rounded)`;
    }
    ["inv_date", "received", "measured_on", "issued", "paid_on"].forEach(k => { if (!d[k]) d[k] = null; });
    d.inv_amount = f.total || 0;
    await POST("/store/est/subpcs", d);
    await reload(); toast(`PC ${pad(seq, 2)} of ${s.name} saved`);
  }, { wide: true, live, save: "Save certificate",
       top: `${prevChecks(keepSub ? Object.assign({}, x.read, { notes: (x.read.notes || []).filter(n => !/not a subcontractor on this project/.test(n)) }) : x.read)}${f.new_sub && !keepSub ? `<div class="agrow" style="margin:6px 0"><button type="button" class="btn btn-primary" id="pv-newsub">+ Add ${esc(f.new_sub)} as a new subcontractor</button>
         <span class="small muted">with the TRN, agreement and work read from the certificate - check the contract value on Subcontracts after.</span></div>` : ""}<div id="pv-calc" style="margin:8px 0 12px"></div>` });
  const nb = $("#pv-newsub");
  if (nb) nb.onclick = async () => {
    nb.disabled = true;
    try {
      const sup = (ST.meta.suppliers || []).find(y => y.name.toLowerCase() === f.new_sub.toLowerCase());
      const r = await POST("/store/est/subs", { project_id: ST.pid, name: f.new_sub, trn: f.trn || "", agreement: f.agreement || "", scope: f.scope_hint || "",
                                                supplier_id: sup ? sup.id : null, status: "Active", ret_pct: f.ret_cum && f.work_cum ? Math.round(1000 * f.ret_cum / ((f.work_cum || 0) + (f.var_cum || 0))) / 10 : 0 });
      await reload(); toast(`${f.new_sub} added to this project`);
      closeModal(); prevPcForm(x, r.id);
    } catch (e) { nb.disabled = false; fail(e); }
  };
  live();
  $("#m-body").addEventListener("change", e => { if (e.target && e.target.id === "pv-open") live(); });
  prevWatch(x);
}

// The earlier PCs of this subcontractor to work this one out from: those in the app, or (ticked) one opening line.
function prevCanOpen(s, seq, f) { return s && f.prev_cert > 0 && !s.pcs.some(p => +p.seq < seq); }
function prevOpenOn() { const el = $("#pv-open"); return el ? el.checked : true; }
function prevEarlier(s, seq, f) {
  if (prevCanOpen(s, seq, f) && prevOpenOn()) return [{ seq: Math.max(1, seq - 1), work_cum: f.prev_cert, var_cum: 0, mos_cum: 0, adv_amount: 0, adv_rec_cum: 0, ret_cum: 0, ret_rel_cum: 0, other_cum: 0 }];
  return s.pcs.filter(p => +p.seq < seq);
}

// ---- a contract: the subcontract form (or the project's) with the agreement read into it -----------------------
function prevContract(x) {
  modal(`Contract - ${x.file.name}`, [], async () => {}, { save: "-", top: `<div class="small" style="margin-bottom:10px">What is <b>${esc(x.file.name)}</b>?</div>
    <div class="agrow"><button type="button" class="btn btn-primary" id="pv-sca">A subcontract agreement / LPO</button><button type="button" class="btn btn-ghost" id="pv-main">The main contract with the client</button></div>` });
  $("#m-save").style.display = "none";
  let picked = false;
  $("#pv-sca").onclick = () => { picked = true; x.as = "Subcontract agreement"; closeModal(); window.PREV_NO_OPEN = true; subForm(); prevHand("#ag-file", x.file); prevWatch(x); };
  $("#pv-main").onclick = () => { picked = true; x.as = "Main contract"; closeModal(); editProject(); prevHand("#doc-file", x.file); prevWatch(x); };
  const mo = new MutationObserver(() => { if ($("#modal").classList.contains("hide") && !picked) { mo.disconnect(); prevDraw(); setTimeout(prevRun, 150); } else if (picked) mo.disconnect(); });
  mo.observe($("#modal"), { attributes: true, attributeFilter: ["class"] });
}
// ---- variations: a log (Excel) through the log import; a letter / cost proposal on the variation form ----------
function prevVariation(x) {
  x.as = /\.xls[xm]?$/i.test(x.file.name) ? "Variation log" : "Variation";
  if (/\.xls[xm]?$/i.test(x.file.name)) { voImport(x.file).then(() => { if (!$("#modal").classList.contains("hide")) prevWatch(x); else { x.st = "error"; x.err = "Nothing could be read from it as a variation log."; prevDraw(); prevRun(); } }); return; }
  voForm(); prevHand("#doc-file", x.file); prevWatch(x);
}
