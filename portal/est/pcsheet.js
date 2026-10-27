/* Estimation > subcontractor payment certificates made in the portal - no attachments.
   The item schedule of a subcontract (Appendix A), the monthly sheet of a certificate
   (figures to date per line, deductions, the subcontractor's bill, sign-off) and its print.
   Uses est.js (ST, api, modal, money, ...). */

// ---------- a full-screen page over the project ----------
function big(title, html, onClose, ctx) {
  let el = document.getElementById("big");
  if (!el) {
    el = h(`<div id="big" class="hide"><div class="bbox"><div class="mhead"><b id="b-title"></b><span class="spacer"></span><span id="b-tools"></span><button class="x" id="b-x" aria-label="Close">&times;</button></div><div class="bbody" id="b-body"></div></div></div>`);
    document.body.appendChild(el);
  }
  el.dataset.ctx = ctx || "est.big";             // which (i) notes apply on this page (heads.js)
  $("#b-title").innerHTML = title; $("#b-body").innerHTML = html; $("#b-tools").innerHTML = "";
  el.classList.remove("hide"); document.body.style.overflow = "hidden";
  $("#b-x").onclick = () => closeBig(onClose);
  return el;
}
function closeBig(cb) { const el = document.getElementById("big"); if (el) el.classList.add("hide"); document.body.style.overflow = ""; if (cb) cb(); }
const MEAS = [["pct", "% done"], ["size", "Measured W x H + % done"], ["qty", "Quantity x rate"]];
const DCATS = ["Material", "Manpower", "Plant & Equipment", "Other"];
const num = v => Number(String(v ?? "").replace(/,/g, "").replace("%", "")) || 0;

// ---------- the item schedule (Appendix A), set up once per subcontract ----------
async function scheduleEditor(sid) {
  let d; try { d = await GET(`/store/est/subs/${sid}/items`); } catch (e) { return fail(e); }
  let rows = d.items.map(x => Object.assign({}, x));
  const draw = () => {
    const tot = r2(rows.filter(x => !x.is_var).reduce((a, x) => a + num(x.amount || (num(x.qty) * num(x.rate))), 0));
    const vt = r2(rows.filter(x => x.is_var).reduce((a, x) => a + num(x.amount || (num(x.qty) * num(x.rate))), 0));
    $("#b-body").innerHTML = `
      <div class="card"><div class="tools"><button class="btn btn-primary" id="it-up" title="The agreement BOQ or any payment certificate (Appendix A / Bill sheets) - every line comes in, checked against the sheet's own totals. The file is not stored.">Upload</button><input type="file" id="it-up-f" accept=".xlsx,.xlsm,.pdf,.docx,.jpg,.jpeg,.png" hidden><button class="btn btn-ghost" id="it-paste">Paste from Excel</button><button class="btn btn-ghost" id="it-add">+ Line</button><button class="btn btn-ghost" id="it-addv">+ Variation line</button>
        <span class="spacer"></span><span class="muted">Contract lines <b>${money(tot, false)}</b>${d.sub.value ? ` of ${money(d.sub.value, false)}` : ""} · Variations <b>${money(vt, false)}</b></span></div>
        ${d.sub.value && Math.abs(tot - d.sub.value) > 0.5 && rows.some(x => !x.is_var) ? `<div class="warn" style="margin:0 0 10px">The contract lines add up to ${money(tot, false)}, the subcontract value is ${money(d.sub.value, false)}.</div>` : ""}
        ${rows.length ? `<div class="tw"><table class="t ed sched"><colgroup><col style="width:50px"><col style="width:110px"><col style="width:110px"><col style="width:50px"><col><col style="width:80px"><col style="width:78px"><col style="width:88px"><col style="width:64px"><col style="width:84px"><col style="width:100px"><col style="width:140px"><col style="width:118px"><col style="width:38px"></colgroup>
        <thead><tr><th>Bill</th><th>Bill name</th><th>Heading</th><th>No</th><th>Description</th><th>Type / mark</th><th class="r">Qty</th><th class="r">Claimed qty</th><th>Unit</th><th class="r">Rate</th><th class="r">Amount</th><th>Measured by</th><th>Variation</th><th></th></tr></thead><tbody>
        ${rows.map((x, i) => `<tr data-i="${i}" class="${x.is_var ? "var" : ""}"><td><input data-k="bill" value="${esc(x.bill)}" placeholder="B1"></td><td><input data-k="bill_title" value="${esc(x.bill_title)}" placeholder="Bill name"></td><td><input data-k="section" value="${esc(x.section)}" placeholder="Heading"></td>
          <td><input data-k="no" value="${esc(x.no)}" placeholder="1.1"></td><td><textarea data-k="description" rows="1" placeholder="Description of the item">${esc(x.description)}</textarea></td><td><input data-k="ref" value="${esc(x.ref)}" placeholder="e.g. W3"></td>
          <td><input data-k="qty" class="n" value="${x.qty || ""}" placeholder="0.00" inputmode="decimal"></td><td><input data-k="claimed_qty" class="n" value="${x.claimed_qty || ""}" placeholder="0.00" inputmode="decimal" title="The quantity the subcontractor claims"></td><td><input data-k="unit" value="${esc(x.unit)}" placeholder="m3"></td><td><input data-k="rate" class="n" value="${x.rate || ""}" placeholder="0.00" inputmode="decimal"></td>
          <td><input data-k="amount" class="n" value="${x.amount || ""}" placeholder="qty x rate" inputmode="decimal"></td>
          <td><select data-k="measure">${MEAS.map(([k, l]) => `<option value="${k}" ${x.measure === k ? "selected" : ""}>${l}</option>`).join("")}</select></td>
          <td><div class="vcell"><input type="checkbox" data-k="is_var" ${x.is_var ? "checked" : ""} title="A variation / additional scope"><input data-k="var_ref" value="${esc(x.var_ref)}" placeholder="V01 / LPO"></div></td>
          <td class="c"><button class="btn btn-plain btn-sm" data-del="${i}" ${x.used ? 'title="On a certificate - removing it takes it off the open certificates"' : 'title="Remove the line"'}>&times;</button></td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">No lines yet. Copy the lines of the agreement's BOQ in Excel (item, description, qty, unit, rate, amount) and press <b>Paste from Excel</b>.</div>`}
      </div>`;
    $$("#b-body [data-i]").forEach(tr => { const x = rows[+tr.dataset.i];
      $$("[data-k]", tr).forEach(inp => inp.oninput = inp.onchange = () => { const k = inp.dataset.k; x[k] = inp.type === "checkbox" ? inp.checked : inp.value;
        if ((k === "qty" || k === "rate") && !x._amt_typed) { const a = r2(num(x.qty) * num(x.rate)); if (a) { x.amount = a; $('[data-k="amount"]', tr).value = a; } }
        if (k === "amount") x._amt_typed = true; if (k === "is_var") tr.classList.toggle("var", inp.checked); });
      const ta = $("textarea", tr); ta.style.height = "auto"; ta.style.height = Math.max(32, ta.scrollHeight) + "px"; });
    $$("#b-body [data-del]").forEach(b => b.onclick = () => { rows.splice(+b.dataset.del, 1); draw(); });
    const last = rows[rows.length - 1] || {};
    $("#it-add").onclick = () => { rows.push({ bill: last.bill || "", bill_title: last.bill_title || "", section: last.section || "", measure: last.measure || (d.sub.contract_type.match(/measur|rate/i) ? "qty" : "pct"), is_var: false }); draw(); };
    $("#it-addv").onclick = () => { rows.push({ measure: last.measure || "pct", is_var: true, var_ref: "" }); draw(); };
    const fi = $("#it-up-f"); $("#it-up").onclick = () => fi.click();
    fi.onchange = () => { const f = fi.files[0]; fi.value = ""; if (f) importItems(sid, f, async () => { const n = await GET(`/store/est/subs/${sid}/items`); d = n; rows = n.items.map(x => Object.assign({}, x)); draw(); }); };
    $("#it-paste").onclick = () => pasteItems(sid, d.sub, async () => { const n = await GET(`/store/est/subs/${sid}/items`); d = n; rows = n.items.map(x => Object.assign({}, x)); draw(); });
  };
  big(`Item schedule - ${esc(d.sub.name)} <span class="muted small">${esc(d.sub.scope)}</span>`, "", () => reload(), "est.schedule");
  $("#b-tools").innerHTML = `<button class="btn btn-primary" id="it-save">Save schedule</button>`;
  $("#it-save").onclick = async () => {
    try { const r = await PUT(`/store/est/subs/${sid}/items`, { items: rows.map(x => { const y = Object.assign({}, x); delete y._amt_typed; return y; }) }); d = r; rows = r.items.map(x => Object.assign({}, x)); draw(); toast("Schedule saved"); }
    catch (e) { fail(e); }
  };
  draw();
}
// The schedule out of Excel (agreement BOQ or a payment certificate): every line shown, each sheet
// checked against its own total row, then saved - and opened in the editor for any change.
async function importItems(sid, file, after) {
  if (/\.(pdf|docx|jpe?g|png)$/i.test(file.name)) return importItemsDoc(sid, file, after);
  const send = async (save, mode) => { const fd = new FormData(); fd.append("file", file); fd.append("save", save ? "1" : "0"); fd.append("mode", mode || "replace"); return api(`/store/est/subs/${sid}/items/import`, { method: "POST", body: fd }); };
  let r; try { toast("Reading " + file.name + " ..."); r = await send(false); } catch (e) { return fail(e); }
  const ok = c => c ? (c.ok ? `<span class="st g">= sheet total</span>` : `<span class="st r">sheet says ${money(c.sheet, false)}</span>`) : `<span class="small muted">no total row</span>`;
  const ML = { pct: "% done", size: "size", qty: "quantity" };
  let bill = null;
  const rowsHtml = r.items.map(x => { let h = ""; const b = (x.bill || "") + (x.bill_title ? " " + x.bill_title : "");
    if (b !== bill) { bill = b; if (b.trim()) h += `<tr class="sec"><td colspan="8">${esc(b)}</td></tr>`; }
    return h + `<tr class="${x.rate_missing ? "warnrow" : ""}"><td class="small">${esc(x.no)}</td><td>${x.section ? `<span class="small muted">${esc(x.section)} · </span>` : ""}${esc(x.description)}${x.words ? ` <span class="small muted">· ${esc(x.words)}</span>` : ""}</td><td class="r">${x.qty ? money(x.qty) : ""}</td><td>${esc(x.unit)}</td><td class="r">${x.rate ? money(x.rate) : (x.rate_missing ? '<span class="st r">no rate</span>' : "")}</td><td class="r">${money(x.amount)}</td><td class="small">${ML[x.measure]}</td><td class="r small muted">${x.certified !== null ? money(x.certified) : ""}</td></tr>`; }).join("");
  modal(`Item schedule - ${file.name}`, [], async () => {
    const mode = ($("input[name=itmode]:checked") || {}).value || "replace";
    const x = await send(true, mode); toast(`${x.saved} lines ${mode === "replace" ? "in" : "added"} - ${money(r.contract, false)}`);
    if (after) await after(); else scheduleEditor(sid);
  }, {
    wide: true, save: `Bring in ${r.lines} lines`,
    top: `<div class="strip"><div class="fig"><div class="l">Lines</div><div class="v">${r.lines}</div></div><div class="fig green"><div class="l">Contract lines</div><div class="v">${money(r.contract, false)}</div>${r.value ? `<div class="s">${Math.abs(r.contract - r.value) < 0.01 ? '<span class="st g">= subcontract value</span>' : `subcontract value ${money(r.value, false)}`}</div>` : ""}</div>${r.certified ? `<div class="fig"><div class="l">Certified to date in this file ${tip("Read from the certificate's Certified Amount column - shown here to prove every line was read right. Only the schedule is brought in.")}</div><div class="v">${money(r.certified, false)}</div></div>` : ""}<div class="fig"><div class="l">Checked</div><div class="v">${r.all_checked ? '<span class="st g">every sheet = its total</span>' : '<span class="st a">see notes</span>'}</div></div></div>
      <div class="tw" style="margin:8px 0"><table class="t"><thead><tr><th>Sheet</th><th>Bill</th><th class="r">Lines</th><th class="r">Contract</th><th></th><th class="r">Certified</th><th></th></tr></thead><tbody>${r.sheets.map(x => `<tr><td>${esc(x.sheet)}</td><td>${esc((x.bill + " " + x.title).trim())}</td><td class="r">${x.lines}</td><td class="r">${money(x.contract)}</td><td>${x.check.contract ? ok(x.check.contract) : ""}</td><td class="r">${x.certified ? money(x.certified) : ""}</td><td>${x.check.certified ? ok(x.check.certified) : (x.check.contract ? "" : ok(null))}</td></tr>`).join("")}</tbody></table></div>
      ${r.notes.length ? `<div class="warn" style="margin:0 0 8px">${r.notes.map(esc).join("<br>")}</div>` : ""}
      ${r.existing ? `<div class="warn" style="margin:0 0 8px">This subcontract already has ${r.existing} schedule line(s)${r.used ? `, ${r.used} of them on certificates` : ""}.
        <label class="chk" style="display:flex;gap:8px;margin-top:6px"><input type="radio" name="itmode" value="replace" ${r.used ? "disabled" : "checked"}><span><b>Replace them</b>${r.used ? " - not possible, lines are on certificates" : ""}</span></label>
        <label class="chk" style="display:flex;gap:8px;margin-top:4px"><input type="radio" name="itmode" value="add" ${r.used ? "checked" : ""}><span><b>Add</b> these lines after them</span></label></div>` : ""}
      <div class="tw" style="max-height:340px;overflow:auto"><table class="t"><thead><tr><th>No</th><th>Description</th><th class="r">Qty</th><th>Unit</th><th class="r">Rate</th><th class="r">Amount</th><th>Measured by</th><th class="r">Certified</th></tr></thead><tbody>${rowsHtml}</tbody></table></div>
      <div class="small muted" style="margin-top:6px">After bringing them in, the schedule opens so any line can be changed. The Excel file is not stored.</div>` });
}
function pasteItems(sid, sub, after) {
  modal("Paste lines from Excel", [
    { k: "text", label: "Lines copied from Excel", type: "area", full: true, focus: true, tip: "Select the rows in Excel (item no., description, type, qty, unit, rate, amount) and paste here. A line in capitals with no figures becomes a heading." },
    { k: "bill", label: "Bill (B1, B2 ...)", value: "", ph: "optional" }, { k: "bill_title", label: "Bill name", value: "", ph: "e.g. Electrical Works" },
    { k: "measure", label: "Measured by", type: "select", options: MEAS, value: (sub.contract_type || "").match(/measur|rate/i) ? "qty" : "pct" },
    { k: "is_var", label: " ", type: "check", text: "These are variation lines", value: false }, { k: "var_ref", label: "Variation ref.", value: "", ph: "V01 / LPO no." },
  ], async v => { const r = await POST(`/store/est/subs/${sid}/items/paste`, v); toast(`${r.added} lines added - ${money(r.total, false)}`); if (after) await after(); }, { wide: true, save: "Add lines",
    after: () => { const t = $("#f-text"); if (t) t.style.height = "180px"; } });
}

// ---------- the monthly sheet of one certificate ----------
async function pcSheet(pcid) {
  let d; try { d = await GET(`/store/est/subpcs/${pcid}/sheet`); } catch (e) { return fail(e); }
  const S = { d, lines: {}, deds: [], f: {} };
  const init = () => {
    S.lines = {}; d.items.forEach(it => { const l = d.lines[it.id] || {}; S.lines[it.id] = { pct: l.pct || 0, qty: l.qty || 0, claimed_qty: l.claimed_qty || 0, w: l.w || 0, h: l.h || 0, deduct: l.deduct || 0, remark: l.remark || "" }; });
    S.deds = d.deds.filter(x => x.mine).map(x => Object.assign({}, x));
    const p = d.pc; let inv = []; try { inv = JSON.parse(p.inv_lines || "[]") || []; } catch (e) {}
    S.f = { measured_on: p.measured_on || today(), inv_ref: p.inv_ref, inv_date: p.inv_date, inv_amount: p.inv_amount || "", received: p.received, remarks: p.remarks, mos_cum: p.mos_cum || "",
            adv_amount: p.adv_amount || "", ret_rel_cum: p.ret_rel_cum || "", adv_auto: p.adv_auto, ret_auto: p.ret_auto, adv_rec_cum: p.adv_rec_cum || "", ret_cum: p.ret_cum || "",
            work_cum: p.work_cum || "", var_cum: p.var_cum || "", other_cum: p.other_cum || "", other_note: p.other_note || "", inv_lines: inv };
  };
  init();
  const lineAmt = (it, l) => !l ? 0 : it.measure === "qty" ? r2(num(l.qty) * it.rate * (num(l.pct) ? num(l.pct) / 100 : 1) - num(l.deduct)) : r2((it.amount - num(l.deduct)) * num(l.pct) / 100);
  const s = d.sub, locked = d.locked && !(d.me && d.me.admin);
  // the money, as the server works it out
  const figures = () => {
    let work = 0, vr = 0;
    if (d.items.length) d.items.forEach(it => { const a = lineAmt(it, S.lines[it.id]); if (it.is_var) vr += a; else work += a; });
    else { work = num(S.f.work_cum); vr = num(S.f.var_cum); }
    work = r2(work); vr = r2(vr);
    const earlier = d.deds.filter(x => !x.mine && x.counted).reduce((a, x) => a + x.amount, 0);
    const mine = S.deds.filter(x => x.counted !== false).reduce((a, x) => a + (num(x.qty) && num(x.rate) ? r2(num(x.qty) * num(x.rate)) : num(x.amount)), 0);
    const other = (d.deds.length || S.deds.length) ? r2(earlier + mine) : num(S.f.other_cum);
    const i = d.pcs.findIndex(x => x.id === d.pc.id), prev = d.pcs[i - 1];
    const advPaid = r2((prev ? prev.adv_paid_cum : 0) + num(S.f.adv_amount));
    const advRec = S.f.adv_auto ? r2(Math.min(advPaid, work * ((s.adv_pct || (s.revised ? 100 * advPaid / s.revised : 0))) / 100)) : num(S.f.adv_rec_cum);
    const ret = S.f.ret_auto ? r2((work + vr) * (s.ret_pct || 0) / 100) : num(S.f.ret_cum);
    const net = r2(work + vr + num(S.f.mos_cum) + advPaid - advRec - ret + num(S.f.ret_rel_cum) - other);
    const prevNet = prev ? prev.net_cum : 0, th = r2(net - prevNet), vat = r2(th * (s.vat_pct || 0) / 100);
    return { work, vr, other, advPaid, advRec, ret, net, prevNet, th, vat, pay: r2(th + vat) };
  };
  const signBox = (role, label, by, on) => `<div class="sg ${by ? "on" : ""}"><span>${label}</span>${by ? `<b>${esc(by)}</b><small>${dt(on)}</small>${d.me && (d.me.admin || d.me.name === by) ? `<button class="btn btn-plain btn-sm" data-unsign="${role}">Undo</button>` : ""}` : (d.me && d.me.can[role] ? `<button class="btn btn-ghost btn-sm" data-sign="${role}">${role === "prep" ? "Prepared" : role === "rev" ? "Verified" : role === "site" ? "Certified" : "Approve"}</button>` : `<small class="muted">waiting</small>`)}</div>`;
  const calcHtml = F => { const p = d.pc; return `<div class="card calc2"><h3>Certificate ${pad(p.seq, 2)}<span class="spacer"></span>${st(p.status)}</h3><table>
          <tr><td>Work executed to date</td><td class="r">${money(F.work, false)}</td></tr><tr><td>Variations executed to date</td><td class="r">${money(F.vr, false)}</td></tr>
          ${num(S.f.mos_cum) ? `<tr><td>Material on site</td><td class="r">${money(S.f.mos_cum, false)}</td></tr>` : ""}
          <tr class="b"><td>Total work executed</td><td class="r">${money(r2(F.work + F.vr + num(S.f.mos_cum)), false)}</td></tr>
          ${F.advPaid ? `<tr><td>Add advance paid</td><td class="r">${money(F.advPaid, false)}</td></tr>` : ""}
          ${F.advRec ? `<tr><td>Less advance recovery</td><td class="r">-${money(F.advRec, false)}</td></tr>` : ""}
          ${F.ret ? `<tr><td>Less retention</td><td class="r">-${money(F.ret, false)}</td></tr>` : ""}
          ${F.other ? `<tr><td>Less deductions</td><td class="r">-${money(F.other, false)}</td></tr>` : ""}
          ${num(S.f.ret_rel_cum) ? `<tr><td>Add retention released</td><td class="r">${money(S.f.ret_rel_cum, false)}</td></tr>` : ""}
          <tr><td>Less previously certified</td><td class="r">-${money(F.prevNet, false)}</td></tr>
          <tr class="b"><td>Net amount due</td><td class="r">${money(F.th, false)}</td></tr><tr><td>VAT ${s.vat_pct}%</td><td class="r">${money(F.vat, false)}</td></tr>
          <tr class="p"><td>Total due for payment</td><td class="r">AED ${money(F.pay, false)}</td></tr></table>
          ${num(S.f.inv_amount) && Math.abs(num(S.f.inv_amount) - F.pay) > 0.005 ? `<div class="warn">Invoice ${money(S.f.inv_amount, false)} - certified ${money(F.pay, false)} (difference ${money(r2(num(S.f.inv_amount) - F.pay), false)}).</div>` : ""}
          ${F.th < 0 ? '<div class="warn">This certificate is negative - it takes money back.</div>' : ""}
          ${s.revised && F.work + F.vr > s.revised + 0.5 ? `<div class="warn">Work done is above the revised value (${money(s.revised, false)}).</div>` : ""}
        </div>`; };
  // A line that moved since the last certificate (what the subcontractor claimed this time) - a pale shade.
  const moved = it => { const a = S.lines[it.id] || {}, b = d.prev[it.id] || {}, g = (o, k) => num(o[k]) || 0;
    return ["qty", "claimed_qty", "w", "h", "pct", "deduct"].some(k => Math.abs(g(a, k) - g(b, k)) > 1e-9) || String(a.remark || "").trim() !== String(b.remark || "").trim()
      || Math.abs(lineAmt(it, S.lines[it.id]) - (b.amount || 0)) > 0.004; };
  const draw = () => {
    const F = figures(), p = d.pc;
    const bills = []; d.items.forEach(it => { const key = it.is_var ? "VAR" : it.bill; if (!bills.length || bills[bills.length - 1].key !== key) bills.push({ key, title: it.is_var ? "Variations / additional scope" : ((it.bill ? it.bill + " - " : "") + (it.bill_title || "Contract works")), items: [] }); bills[bills.length - 1].items.push(it); });
    const lineRow = it => { const l = S.lines[it.id], pv = d.prev[it.id] ? d.prev[it.id].amount : 0, a = lineAmt(it, l), m = it.measure;
      const inp = (k, w, ph = "") => `<input class="n" data-l="${it.id}" data-k="${k}" value="${l[k] || ""}" style="width:${w}px" placeholder="${ph}" ${locked ? "disabled" : ""}>`;
      return `<tr data-row="${it.id}" class="${moved(it) ? "mv" : ""}" title="${moved(it) ? "Changed since the last certificate - claimed this time" : ""}"><td>${esc(it.no)}</td><td class="d">${esc(it.description)}${it.ref ? `<div class="small muted">${esc(it.ref)}</div>` : ""}</td><td class="r">${it.qty ? it.qty : ""} ${esc(it.unit)}</td><td class="r">${it.rate ? money(it.rate) : ""}</td><td class="r">${money(it.amount)}</td>
        <td class="nowrap">${m === "size" ? inp("w", 54, "W") + " x " + inp("h", 54, "H") : m === "qty" ? `<span class="small muted">claimed</span> ${inp("claimed_qty", 64)}` : ""}</td>
        <td class="nowrap">${m === "qty" ? inp("qty", 70, "qty") + ` <span class="small muted">${esc(it.unit)}</span> ` + `<span title="Optional: a stage % of the measured quantity (e.g. 70% = first coat done). Empty = 100%.">${inp("pct", 44, "100")}<span class="small muted">%</span></span>` : inp("pct", 58, "%") + " %"}</td>
        <td>${inp("deduct", 80, "0.00")}</td><td class="r muted">${money(pv)}</td><td class="r" data-this="${it.id}">${money(r2(a - pv))}</td><td class="r"><b data-amt="${it.id}">${money(a, false)}</b></td>
        <td><input data-l="${it.id}" data-k="remark" value="${esc(l.remark)}" style="width:150px" ${locked ? "disabled" : ""}></td></tr>`; };
    const sumBill = b => r2(b.items.reduce((x, it) => x + lineAmt(it, S.lines[it.id]), 0));
    $("#b-body").innerHTML = `
      <div class="sheet">
      <div class="sh-main">
        ${locked ? '<div class="warn" style="margin:0 0 12px">This certificate is paid (or a later one is) - its figures are locked.</div>' : ""}
        <div class="card"><h3>Invoice & dates</h3><div class="frm f4">
          <div class="f"><label>Measurement date</label><input type="date" data-f="measured_on" value="${S.f.measured_on || ""}"></div>
          <div class="f"><label>Subcontractor invoice no.</label><input data-f="inv_ref" value="${esc(S.f.inv_ref)}"></div>
          <div class="f"><label>Invoice date</label><input type="date" data-f="inv_date" value="${S.f.inv_date || ""}"></div>
          <div class="f"><label>Invoice amount (AED)</label><input class="money" data-f="inv_amount" value="${S.f.inv_amount}"></div>
          <div class="f"><label>Received in office</label><input type="date" data-f="received" value="${S.f.received || ""}"></div>
          <div class="f full"><label>Remarks (printed)</label><input data-f="remarks" value="${esc(S.f.remarks)}" placeholder="Nil"></div></div>
          <details class="inv" ${S.f.inv_lines.length ? "open" : ""}><summary>Lines of the subcontractor's bill (optional - instead of attaching it)</summary>
            <div id="invl">${S.f.inv_lines.map((x, i) => `<div class="il"><input data-il="${i}" data-k="d" value="${esc(x.d)}" placeholder="Description"><input class="money" data-il="${i}" data-k="a" value="${x.a || ""}" placeholder="Amount"><button class="btn btn-plain btn-sm" data-ildel="${i}">&times;</button></div>`).join("")}</div>
            <button class="btn btn-ghost btn-sm" id="il-add">+ Bill line</button></details>
        </div>
        ${d.items.length ? bills.map((b, bi) => `<div class="card"><h3>${esc(b.title)}<span class="spacer"></span><span class="small muted">to date <b data-bill="${bi}">${money(sumBill(b), false)}</b></span></h3>
          <div class="tw"><table class="t sl"><thead><tr><th>No</th><th>Description</th><th class="r">Qty</th><th class="r">Rate</th><th class="r">Contract amt</th><th>Measured</th><th>Done to date</th><th>Deduction</th><th class="r">Previous</th><th class="r">This PC</th><th class="r">To date</th><th>Remark</th></tr></thead>
          <tbody>${(() => { let sec = null; return b.items.map(it => { let x = ""; if (it.section && it.section !== sec) { sec = it.section; x = `<tr class="sec"><td></td><td colspan="11">${esc(sec)}</td></tr>`; } return x + lineRow(it); }).join(""); })()}</tbody></table></div></div>`).join("")
        : `<div class="card"><h3>Work done to date</h3><div class="muted small" style="margin-bottom:8px">No item schedule on this subcontract - type the totals, or <a href="#" id="sh-sched">set up the item schedule</a> to certify line by line.</div><div class="frm f4">
            <div class="f"><label>Value of work to date</label><input class="money" data-f="work_cum" value="${S.f.work_cum}"></div><div class="f"><label>Variations to date</label><input class="money" data-f="var_cum" value="${S.f.var_cum}"></div></div></div>`}
        <div class="card"><h3>Deductions ${tip("Material, manpower or plant supplied by Infinia, back-charges, damages. A deduction is entered once, on the certificate where it arises, and counts on every later certificate (the certificate works on figures to date).")}<span class="spacer"></span><span class="small muted">to date <b id="dedtot">${money(F.other, false)}</b></span></h3>
          ${d.deds.filter(x => !x.mine).length ? `<div class="tw" style="margin-bottom:8px"><table class="t"><thead><tr><th>PC</th><th>Type</th><th>Date</th><th>Description</th><th class="r">Qty</th><th>Unit</th><th class="r">Rate</th><th class="r">Amount</th></tr></thead><tbody>${d.deds.filter(x => !x.mine).map(x => `<tr class="${x.counted ? "" : "muted"}"><td>${pad(x.pc_seq, 2)}</td><td>${esc(x.cat)}</td><td>${dt(x.on_date)}</td><td>${esc(x.description)}${x.counted ? "" : " <i>(not deducted)</i>"}</td><td class="r">${x.qty || ""}</td><td>${esc(x.unit)}</td><td class="r">${x.rate ? money(x.rate) : ""}</td><td class="r">${money(x.amount)}</td></tr>`).join("")}</tbody></table></div>` : ""}
          <div class="tw"><table class="t de"><thead><tr><th>Type</th><th>Date</th><th>Description</th><th>Qty</th><th>Unit</th><th>Rate</th><th>Amount</th><th>Taken</th><th></th></tr></thead><tbody>
          ${S.deds.map((x, i) => `<tr><td><select data-d="${i}" data-k="cat">${DCATS.map(c => `<option ${x.cat === c ? "selected" : ""}>${c}</option>`).join("")}</select></td><td><input type="date" data-d="${i}" data-k="on_date" value="${x.on_date || ""}"></td>
            <td><input data-d="${i}" data-k="description" value="${esc(x.description)}" style="min-width:220px"></td><td><input class="n" data-d="${i}" data-k="qty" value="${x.qty || ""}" style="width:60px"></td><td><input data-d="${i}" data-k="unit" value="${esc(x.unit)}" style="width:50px"></td>
            <td><input class="n" data-d="${i}" data-k="rate" value="${x.rate || ""}" style="width:80px"></td><td><input class="n" data-d="${i}" data-k="amount" value="${num(x.qty) && num(x.rate) ? r2(num(x.qty) * num(x.rate)) : (x.amount || "")}" style="width:90px" ${num(x.qty) && num(x.rate) ? "disabled" : ""}></td>
            <td class="c"><input type="checkbox" data-d="${i}" data-k="counted" ${x.counted !== false ? "checked" : ""}></td><td><button class="btn btn-plain btn-sm" data-ddel="${i}">&times;</button></td></tr>`).join("") || `<tr><td colspan="9" class="muted small">None on this certificate.</td></tr>`}
          </tbody></table></div><button class="btn btn-ghost btn-sm" id="de-add" style="margin-top:8px" ${locked ? "disabled" : ""}>+ Deduction</button></div>
        <div class="card"><h3>Advance, retention & material on site</h3><div class="frm f4">
          <div class="f"><label>Advance paid on this PC</label><input class="money" data-f="adv_amount" value="${S.f.adv_amount}"></div>
          <div class="f"><label>Advance recovered to date ${s.adv_pct ? `(${s.adv_pct}% of the work)` : ""}</label><input class="money" data-f="adv_rec_cum" value="${S.f.adv_auto ? F.advRec : S.f.adv_rec_cum}" ${S.f.adv_auto ? "disabled" : ""}><label class="chk"><input type="checkbox" data-f="adv_auto" ${S.f.adv_auto ? "checked" : ""}> work it out</label></div>
          <div class="f"><label>Retention to date ${s.ret_pct ? `(${s.ret_pct}% of work + variations)` : ""}</label><input class="money" data-f="ret_cum" value="${S.f.ret_auto ? F.ret : S.f.ret_cum}" ${S.f.ret_auto ? "disabled" : ""}><label class="chk"><input type="checkbox" data-f="ret_auto" ${S.f.ret_auto ? "checked" : ""}> work it out</label></div>
          <div class="f"><label>Retention released to date</label><input class="money" data-f="ret_rel_cum" value="${S.f.ret_rel_cum}"><div class="quick"><button data-rel="half">Half</button><button data-rel="all">All</button><button data-rel="0">None</button></div></div>
          <div class="f"><label>Material on site to date</label><input class="money" data-f="mos_cum" value="${S.f.mos_cum}"></div></div></div>
      </div>
      <aside class="sh-side">
        <div id="calcbox">${calcHtml(F)}</div>
        <div class="card"><h3>Sign-off ${tip("Each click puts the name and today's date on the certificate. Reviewed is for Accounts, Approved for the manager.")}</h3><div class="sgs">
          ${signBox("site", "Certified at site", p.verified_by, p.verified_on)}${signBox("prep", "Prepared (QS)", p.prep_by, p.prep_on)}${signBox("chk", "Approved (contracts manager)", p.chk_by, p.chk_on)}${signBox("rev", "Verified (Accounts)", p.rev_by, p.rev_on)}${signBox("app", "Approved (Managing Director)", p.app_by ? "Managing Director" : "", p.app_on)}</div></div>
      </aside></div>`;
    bind();
  };
  const refreshFigures = () => { const y = $("#b-body").scrollTop; draw(); $("#b-body").scrollTop = y; };
  // a typed figure moves only the figures - the cursor stays where it is
  const update = () => {
    const B = $("#b-body"), F = figures();
    d.items.forEach(it => { const a = lineAmt(it, S.lines[it.id]), pv = d.prev[it.id] ? d.prev[it.id].amount : 0;
      const x = $(`[data-amt="${it.id}"]`, B); if (x) x.textContent = money(a, false);
      const tr = $(`tr[data-row="${it.id}"]`, B); if (tr) { const m = moved(it); tr.classList.toggle("mv", m); tr.title = m ? "Changed since the last certificate - claimed this time" : ""; } const t = $(`[data-this="${it.id}"]`, B); if (t) t.innerHTML = money(r2(a - pv)); });
    const bills = []; d.items.forEach(it => { const key = it.is_var ? "VAR" : it.bill; if (!bills.length || bills[bills.length - 1].key !== key) bills.push({ key, items: [] }); bills[bills.length - 1].items.push(it); });
    bills.forEach((b, bi) => { const x = $(`[data-bill="${bi}"]`, B); if (x) x.textContent = money(r2(b.items.reduce((q, it) => q + lineAmt(it, S.lines[it.id]), 0)), false); });
    S.deds.forEach((x, i) => { const auto = num(x.qty) && num(x.rate); const inp = $(`[data-d="${i}"][data-k="amount"]`, B); if (inp) { inp.disabled = !!auto; if (auto) inp.value = r2(num(x.qty) * num(x.rate)); } });
    const dt_ = $("#dedtot", B); if (dt_) dt_.textContent = money(F.other, false);
    const ar = $('[data-f="adv_rec_cum"]', B); if (ar && S.f.adv_auto) ar.value = F.advRec;
    const rt = $('[data-f="ret_cum"]', B); if (rt && S.f.ret_auto) rt.value = F.ret;
    $("#calcbox", B).innerHTML = calcHtml(F);
  };
  const bind = () => {
    const B = $("#b-body");
    $$("[data-l]", B).forEach(inp => inp.oninput = () => { S.lines[inp.dataset.l][inp.dataset.k] = inp.dataset.k === "remark" ? inp.value : num(inp.value); update(); });
    $$("[data-l]", B).forEach(inp => inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); const all = $$(`[data-k="${inp.dataset.k}"][data-l]`, B); const m = all[all.indexOf(inp) + 1]; if (m) { m.focus(); m.select(); } } });
    $$("[data-f]", B).forEach(inp => { inp.oninput = inp.onchange = () => { const k = inp.dataset.f; S.f[k] = inp.type === "checkbox" ? inp.checked : inp.value;
      if (k === "adv_auto" || k === "ret_auto") refreshFigures(); else update(); }; });
    $$("[data-rel]", B).forEach(b => b.onclick = e => { e.preventDefault(); const F = figures(); S.f.ret_rel_cum = b.dataset.rel === "all" ? F.ret : b.dataset.rel === "half" ? r2(F.ret / 2) : 0; $('[data-f="ret_rel_cum"]', B).value = S.f.ret_rel_cum; update(); });
    $$("[data-d]", B).forEach(inp => { inp.oninput = inp.onchange = () => { const x = S.deds[+inp.dataset.d], k = inp.dataset.k; x[k] = inp.type === "checkbox" ? inp.checked : inp.value; update(); }; });
    $$("[data-ddel]", B).forEach(b => b.onclick = () => { S.deds.splice(+b.dataset.ddel, 1); refreshFigures(); });
    const da = $("#de-add"); if (da) da.onclick = () => { const last = S.deds[S.deds.length - 1]; S.deds.push({ cat: last ? last.cat : "Manpower", on_date: today(), description: "", qty: "", unit: last ? last.unit : "", rate: last ? last.rate : "", amount: "", counted: true }); refreshFigures(); };
    $$("[data-il]", B).forEach(inp => inp.onchange = () => { S.f.inv_lines[+inp.dataset.il][inp.dataset.k] = inp.value; });
    $$("[data-ildel]", B).forEach(b => b.onclick = () => { S.f.inv_lines.splice(+b.dataset.ildel, 1); refreshFigures(); });
    const ia = $("#il-add"); if (ia) ia.onclick = () => { S.f.inv_lines.push({ d: "", a: "" }); refreshFigures(); };
    const sc = $("#sh-sched"); if (sc) sc.onclick = e => { e.preventDefault(); closeBig(); scheduleEditor(s.id); };
    $$("[data-sign]", B).forEach(b => b.onclick = () => sign(b.dataset.sign, false));
    $$("[data-unsign]", B).forEach(b => b.onclick = () => sign(b.dataset.unsign, true));
  };
  const body = () => {
    const pc = Object.assign({}, S.f); ["adv_rec_cum", "ret_cum"].forEach(k => { if (pc[k.startsWith("adv") ? "adv_auto" : "ret_auto"]) delete pc[k]; });
    if (d.items.length) { delete pc.work_cum; delete pc.var_cum; }
    if (d.deds.length || S.deds.length) { delete pc.other_cum; delete pc.other_note; }
    return { pc, lines: d.items.map(it => Object.assign({ item_id: it.id }, S.lines[it.id])), deds: S.deds };
  };
  const save = async certify => {
    try {
      d = await PUT(`/store/est/subpcs/${pcid}/sheet`, body()); S.d = d;
      if (certify && ["Received", "At site"].includes(d.pc.status)) { await POST(`/store/est/subpcs/${pcid}/step`, { step: "Certified" }); d = await GET(`/store/est/subpcs/${pcid}/sheet`); }
      init(); draw(); toast(certify ? "Certified - figures saved" : "Saved"); return true;
    } catch (e) { fail(e); return false; }
  };
  const sign = async (role, undo) => {
    if (!undo && !locked && !(await save(false))) return;
    try { d = await POST(`/store/est/subpcs/${pcid}/sign`, { role, undo }); init(); draw(); toast(undo ? "Signature taken off" : "Signed"); } catch (e) { fail(e); }
  };
  big(`PC ${pad(d.pc.seq, 2)} - ${esc(s.name)} <span class="muted small">${esc(s.scope)} · ${esc(d.project.code)}</span>`, "", () => reload(), "est.sheet");
  $("#b-tools").innerHTML = `${d.items.length ? `<button class="btn btn-ghost" id="sh-items">Item schedule</button>` : ""}<button class="btn btn-ghost" id="sh-prev">Preview</button><button class="btn btn-ghost" id="sh-pdf">Export PDF</button>${locked ? "" : `<button class="btn btn-ghost" id="sh-save">Save</button>${["Received", "At site"].includes(d.pc.status) ? `<button class="btn btn-primary" id="sh-cert">Save & certify</button>` : `<button class="btn btn-primary" id="sh-cert2">Save</button>`}`}`;
  const sv = $("#sh-save"); if (sv) sv.onclick = () => save(false);
  const ce = $("#sh-cert"); if (ce) ce.onclick = () => save(true);
  const c2 = $("#sh-cert2"); if (c2) { c2.onclick = () => save(false); if (sv) sv.remove(); }
  $("#sh-prev").onclick = async () => { if (!locked) await save(false); exportGo("preview", "pc", { id: pcid }); };
  $("#sh-pdf").onclick = async () => { if (!locked) await save(false); exportGo("pdf", "pc", { id: pcid }); };
  const si = $("#sh-items"); if (si) si.onclick = () => { closeBig(); scheduleEditor(s.id); };
  draw();
}
// A certificate opens on the sheet when its subcontract has an item schedule; the quick form stays for a lump sum.
function openCert(sid, pcid) {
  const s = ST.b.subs.find(x => x.id === sid);
  if (s && s.items) pcSheet(pcid); else certifyForm(sid, pcid);
}
document.addEventListener("keydown", e => { if (e.key === "Escape") { const el = document.getElementById("big"); if (el && !el.classList.contains("hide") && $("#modal").classList.contains("hide")) closeBig(() => reload()); } });

// The schedule out of a PDF or Word agreement / quotation: read on this computer (nothing uploaded), every priced
// line shown with its section totals, then put in - replacing the schedule, or after the lines already there.
async function importItemsDoc(sid, file, after) {
  let r, have;
  try {
    toast("Reading " + file.name + " ...");
    const d = await readAgreement(file, m => toast(m));
    [r, have] = await Promise.all([POST("/store/est/read/items", { lines: d.lines }), GET(`/store/est/subs/${sid}/items`)]);
  } catch (e) { return fail(e); }
  if (!r.items.length) { toast("No priced lines were found in " + file.name, { err: true }); return; }
  const c = r.checks || {}, used = have.items.filter(x => x.used).length, total = r.items.reduce((a, x) => a + x.amount, 0);
  let bill = null;
  const rows = r.items.map(x => { let hh = ""; const b = (x.bill || "") + (x.bill_title ? " " + x.bill_title : "");
    if (b !== bill) { bill = b; if (b.trim()) hh += `<tr class="sec"><td colspan="6">${esc(b)}</td></tr>`; }
    return hh + `<tr><td class="small">${esc(x.no)}</td><td>${esc(x.description)}</td><td class="r">${x.qty ?? ""}</td><td>${esc(x.unit)}</td><td class="r">${x.rate ? money(x.rate) : ""}</td><td class="r">${money(x.amount)}</td></tr>`; }).join("");
  const secs = (c.sections || []).map(x => `<span class="st ${x.ok ? "g" : "r"}">${esc(x.bill)} ${money(x.total, false)}${x.ok ? "" : " - agreement says " + money(x.in_doc, false)}</span>`).join(" ");
  modal(`Item schedule - ${file.name}`, [], async () => {
    const mode = ($("input[name=itmode]:checked") || {}).value || "replace";
    const keep = mode === "add" ? have.items : [];
    const add = r.items.map(x => ({ bill: x.bill, bill_title: x.bill_title, section: x.section || "", no: x.no, description: x.description, qty: x.qty || "", unit: x.unit || "", rate: x.rate || "", amount: x.amount, measure: "pct" }));
    await PUT(`/store/est/subs/${sid}/items`, { items: keep.concat(add) });
    toast(`${add.length} lines ${mode === "replace" ? "in" : "added"} - ${money(total, false)}`);
    if (after) await after(); else scheduleEditor(sid);
  }, { wide: true, save: `Bring in ${r.items.length} lines`,
    top: `<div class="strip"><div class="fig"><div class="l">Lines</div><div class="v">${r.items.length}</div></div><div class="fig green"><div class="l">Total</div><div class="v">${money(total, false)}</div>
      ${c.total_in_doc != null ? `<div class="s">${Math.abs(total - c.total_in_doc) < 0.01 ? '<span class="st g">= the document\'s total</span>' : `document total ${money(c.total_in_doc, false)}`}</div>` : ""}</div></div>
      ${secs ? `<div style="margin:6px 0">${secs}</div>` : ""}${(r.notes || []).length ? `<div class="warn" style="margin:0 0 8px">${r.notes.map(esc).join("<br>")}</div>` : ""}
      ${have.items.length ? `<div class="warn" style="margin:0 0 8px">This subcontract already has ${have.items.length} schedule line(s)${used ? `, ${used} of them on certificates` : ""}.
        <label class="chk" style="display:flex;gap:8px;margin-top:6px"><input type="radio" name="itmode" value="replace" ${used ? "disabled" : "checked"}><span><b>Replace them</b>${used ? " - not possible, lines are on certificates" : ""}</span></label>
        <label class="chk" style="display:flex;gap:8px;margin-top:4px"><input type="radio" name="itmode" value="add" ${used ? "checked" : ""}><span><b>Add</b> these lines after them</span></label></div>` : ""}
      <div class="tw" style="max-height:340px;overflow:auto"><table class="t"><thead><tr><th>No</th><th>Description</th><th class="r">Qty</th><th>Unit</th><th class="r">Rate</th><th class="r">Amount</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="small muted" style="margin-top:6px">The file was read on this computer - it is not uploaded or stored. After bringing the lines in, the schedule opens so any line can be changed.</div>` });
}
