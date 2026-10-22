/* "Read from document" across the app: a receipt, a cheque, a passport / Emirates ID / visa, a delivery note,
   a supplier's quotation or a bank statement is opened on this computer (PDF, Word, Excel, a scan or a phone
   photo - portal/est/agreement.js), and only its words go to the server, which picks out the details
   (app/est_docread.py). The file itself is never uploaded or kept. The boxes are filled in; nothing is saved
   until the usual Save button is pressed. */
(function () {
  "use strict";
  var AG = "/portal/est/agreement.js";
  function loadReader() {
    if (window.readAgreement) return Promise.resolve();
    return new Promise(function (ok, no) {
      var s = document.createElement("script"); s.src = AG + "?v=" + (window.DOCREAD_V || "1"); s.onload = ok;
      s.onerror = function () { no(new Error("Could not load the document reader.")); }; document.head.appendChild(s);
    });
  }
  var css = ".dr-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 10px;font-size:12.5px;color:#555}" +
    ".dr-bar .dr-btn{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border:1px solid #C9CED6;border-radius:7px;background:#fff;color:#222;font-family:inherit;font-weight:600;font-size:12.5px;cursor:pointer}" +
    ".dr-bar .dr-btn:hover{background:#F4F5F7}.dr-bar .dr-btn[disabled]{opacity:.6;cursor:wait}" +
    ".dr-out{flex:1 1 260px;min-width:200px}.dr-out.ok{color:#1E6B3A}.dr-out.bad{color:#B42318}.dr-out.busy{color:#555}" +
    ".dr-filled{background:#F3F8F4 !important;outline:1px solid #B9D8C2}";
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  function token() { try { return sessionStorage.getItem("infinia_token") || localStorage.getItem("infinia_token") || ""; } catch (e) { return ""; } }
  async function post(path, body) {
    if (window.apiCall) return window.apiCall(path, { method: "POST", body: JSON.stringify(body) });
    var r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token() }, body: JSON.stringify(body) });
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error(j.detail || ("Error " + r.status));
    return j;
  }
  function errMsg(e) { return window.errText ? window.errText(e) : (e && e.message) || String(e); }

  // read a file in the browser -> the server's reading of it
  async function read(kind, file, say, extra) {
    await loadReader();
    var doc = await window.readAgreement(file, say);
    if (kind === "bank") return post("/store/bank/stmt/upload-text", { name: file.name, lines: doc.lines });
    var r = await post("/store/docread/" + kind, Object.assign({ lines: doc.lines }, extra || {}));
    r.ocr = !!doc.ocr; return r;
  }

  // put a value in a box (only when there is one) and mark it as filled from the document
  function put(id, v, root) {
    var el = (root || document).querySelector("#" + id);
    if (!el || v === undefined || v === null || v === "") return false;
    if (el.type === "checkbox") el.checked = !!v; else el.value = typeof v === "number" ? (Math.round(v * 100) / 100).toFixed(2) : v;
    el.classList.add("dr-filled"); el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
    setTimeout(function () { el.classList.remove("dr-filled"); }, 6000);
    return true;
  }

  // a bar with the button, placed before `anchor`
  var ACCEPT = ".pdf,.docx,.xlsx,.xls,.jpg,.jpeg,.png,.webp,image/*";
  function bar(anchor, kind, label, tip, apply, opts) {
    opts = opts || {};
    if (!anchor || anchor.parentNode.querySelector('.dr-bar[data-kind="' + kind + '"]')) return null;
    var b = document.createElement("div"); b.className = "dr-bar"; b.dataset.kind = kind;
    b.innerHTML = '<button type="button" class="dr-btn">&#128196; ' + label + '</button>' +
      '<span class="help-i css-tip" tabindex="0" data-tip="' + tip.replace(/"/g, "&quot;") + '">i</span>' +
      '<span class="dr-out"></span><input type="file" accept="' + (opts.accept || ACCEPT) + '" style="display:none">';
    anchor.parentNode.insertBefore(b, anchor);
    var btn = b.querySelector("button"), inp = b.querySelector("input"), out = b.querySelector(".dr-out");
    var say = function (cls, t) { out.className = "dr-out " + cls; out.textContent = t; };
    btn.onclick = function () { inp.click(); };
    inp.onchange = async function () {
      var f = inp.files[0]; if (!f) return; inp.value = "";
      btn.disabled = true; say("busy", "Reading " + f.name + " on this computer ...");
      try {
        var r = await read(kind, f, function (t) { say("busy", t); }, opts.extra ? opts.extra() : null);
        var msg = apply(r, put) || "";
        if (kind !== "bank") {
          var found = (r.found || []);
          msg = msg || (found.length ? "Filled in: " + found.join(", ") + ". Check, then save." : "Nothing recognisable was found - fill it in by hand.");
          if (r.ocr) msg += " (read from a scan - check the figures)";
          say(found.length ? "ok" : "bad", msg);
        } else say("ok", msg);
      } catch (e) { say("bad", errMsg(e)); }
      btn.disabled = false;
    };
    return b;
  }
  var TIP_NOFILE = " The file is read on this computer - it is not uploaded or kept. Nothing is saved until you press Save.";

  // ---------------------------------------------------------------- the forms ------------------------------------
  function money(v) { return v == null ? "" : (Math.round(v * 100) / 100).toFixed(2); }

  function wirePetty() {
    var f = document.getElementById("pc-form");
    if (f) bar(f, "receipt", "Read from receipt", "A photo or scan of the receipt or bill: the date, supplier, amount, receipt no., VAT and TRN are filled in." + TIP_NOFILE,
      function (r, put) {
        var x = r.fields;
        if (window.pcKind) try { window.pcKind("paid"); } catch (e) {}
        put("pc-date", x.date); put("pc-sup", x.supplier); put("pc-amt", x.amount != null ? money(x.amount) : "");
        put("pc-rcpt", x.receipt_no); if (x.description && !document.getElementById("pc-desc").value) put("pc-desc", x.description);
        if (x.vat || x.trn) { put("pc-vat", true); if (window.pcVat) window.pcVat(); put("pc-trn", x.trn); }
      });
    var v = document.getElementById("vh-form");
    if (v) bar(v, "receipt", "Read from receipt", "A photo or scan of the visa receipt (typing centre, medical, Amer): date, amount and supplier are filled in." + TIP_NOFILE,
      function (r, put) { var x = r.fields; put("vh-date", x.date); put("vh-amt", x.amount != null ? money(x.amount) : ""); put("vh-sup", x.supplier); if (x.description) put("vh-desc", x.description); });
  }

  function wireCheques() {
    var p = document.querySelector(".pdc-form");
    if (p) bar(p, "cheque", "Read from cheque", "A photo or scan of the cheque: payee, cheque no., bank, date and amount are filled in." + TIP_NOFILE,
      function (r, put) { var x = r.fields; put("pdc-payee", x.payee); put("pdc-no", x.no); put("pdc-bank", x.bank); put("pdc-date", x.date); put("pdc-amt", x.amount != null ? money(x.amount) : ""); });
    var s = document.querySelector(".sc-form");
    if (s) bar(s, "cheque", "Read from cheque", "A photo or scan of the security cheque: given to, cheque no., bank, amount and the date (if it has one) are filled in." + TIP_NOFILE,
      function (r, put) {
        var x = r.fields; put("sc-party", x.payee); put("sc-no", x.no); put("sc-bank", x.bank); put("sc-amt", x.amount != null ? money(x.amount) : "");
        if (x.date) { var u = document.getElementById("sc-undated"); if (u && u.checked) { u.checked = false; u.dispatchEvent(new Event("change", { bubbles: true })); } put("sc-date", x.date); }
      });
  }

  var KIND_NAMES = { passport: "passport", eid: "Emirates ID", visa: "residence visa", labour_card: "labour card" };
  function wireIdDocs() {
    var row = document.getElementById("hr-doc-emp");
    row = row && row.closest(".form-row");
    if (row) bar(row, "iddoc", "Read from document", "A photo or scan of the passport, Emirates ID, visa or labour card: the document, its number and dates are filled in, and the person is found when the number is already on file." + TIP_NOFILE,
      function (r, put) {
        var x = r.fields, k = document.getElementById("hr-doc-kind");
        if (x.kind && k && [].some.call(k.options, function (o) { return o.value === x.kind; })) { k.value = x.kind; if (window.hrDocKindChanged) window.hrDocKindChanged(); }
        put("hr-doc-number", x.number); put("hr-doc-issued", x.issued_on); put("hr-doc-expires", x.expires_on);
        var emp = document.getElementById("hr-doc-emp"), docs = window.HR_DOCS || [];
        try { docs = HR_DOCS; } catch (e) {}
        var key = function (s) { return String(s || "").replace(/[^0-9A-Z]/gi, "").toUpperCase(); };
        var hit = x.number && docs.find(function (d) { return key(d.number) === key(x.number); });
        if (hit && emp && !emp.value) put("hr-doc-emp", hit.emp_no);
        var extra = hit ? " Person: " + hit.emp_no + (hit.name ? " " + hit.name : "") + "." : (x.name ? " Name on it: " + x.name + " - type the staff or labour code." : "");
        return (r.found.length ? "Filled in: " + r.found.join(", ") + "." : "Nothing recognisable was found.") + extra + " Check, then save.";
      });
    var dd = document.getElementById("d-number");
    var drow = dd && dd.closest(".row");
    if (drow) bar(drow, "iddoc", "Read from document", "A photo or scan of the passport, Emirates ID, visa or labour card: the document, its number and dates are filled in." + TIP_NOFILE,
      function (r, put) {
        var x = r.fields, seg = document.getElementById("d-kind");
        if (x.kind && seg && window.segSet) try { window.segSet(seg, x.kind); } catch (e) {}
        put("d-number", x.number); put("d-issued_on", x.issued_on); put("d-expires_on", x.expires_on);
      });
  }

  function wireStore() {
    // LPO from a supplier quotation
    var sides = document.querySelector(".lpo-sides");
    if (sides) bar(sides, "quotation", "Read from quotation", "The supplier's quotation (PDF, Word, Excel, scan or photo): supplier, TRN, their ref., date and the priced lines are filled in. Check each line's material and unit." + TIP_NOFILE,
      function (r, put) {
        var x = r.fields;
        put("lpo-supplier", x.supplier); if (window.onLpoSupplier) try { window.onLpoSupplier(); } catch (e) {}
        put("lpo-trn", x.trn); put("lpo-supref", x.ref); put("lpo-date", x.date);
        var items = r.items || [];
        if (items.length && window.addLpoLine) {
          try { lpoLines = lpoLines.filter(function (l) { return String(l.description || "").trim(); }); } catch (e) {}
          items.forEach(function (it) { window.addLpoLine({ description: it.description, qty: it.qty, unit: it.unit, rate: it.rate }); });
          if (window.renderLpoTotals) try { window.renderLpoTotals(); } catch (e) {}
        }
        return "Filled in: " + (r.found || []).join(", ") + (items.length ? " - " + items.length + " line" + (items.length === 1 ? "" : "s") + " added" : "") + ". Check, then save.";
      });
    // material arrived, from the delivery note / supplier invoice
    var rf = document.getElementById("recv-supplier-pick");
    rf = rf && rf.closest(".form-row");
    if (rf) bar(rf, "delivery", "Read from delivery note", "The delivery note or supplier invoice (scan or photo): supplier, DO / invoice no., date and the quantities that arrived are filled in by material name." + TIP_NOFILE,
      function (r, put) {
        var x = r.fields, sel = document.getElementById("recv-supplier-pick");
        var low = function (s) { return String(s || "").toLowerCase().replace(/\b(l\.?l\.?c|est|trading|co)\b\.?/g, "").replace(/[^a-z0-9]+/g, " ").trim(); };
        if (x.supplier && sel) {
          var opt = [].find.call(sel.options, function (o) { var a = low(o.textContent), b = low(x.supplier); return a && b && (a === b || a.indexOf(b) === 0 || b.indexOf(a) === 0); });
          if (opt) { sel.value = opt.value; if (window.onSupplierPick) window.onSupplierPick("recv"); }
        }
        put("recv-ref-no", x.ref); put("recv-date", x.date);
        // quantities by material name
        var words = function (s) { return low(s).split(" ").filter(function (w) { return w.length > 1; }); };
        var score = function (a, b) { var A = words(a), B = words(b); if (!A.length || !B.length) return 0; var n = A.filter(function (w) { return B.indexOf(w) >= 0; }).length; return n / Math.max(A.length, B.length); };
        var rows = [].slice.call(document.querySelectorAll("#recv-lines tr")), matched = 0, left = [], unread = [];
        var used = {};
        (r.items || []).forEach(function (it) {
          var best = null, bs = 0;
          rows.forEach(function (tr, i) { if (used[i] || !tr.querySelector(".recv-qty")) return; var s = score(it.description, tr.cells[0].textContent); if (s > bs) { bs = s; best = i; } });
          if (best !== null && bs >= 0.34) {
            used[best] = 1; var q = rows[best].querySelector(".recv-qty");
            if (it.qty === null || it.qty === undefined) { unread.push(it.description); q.style.outline = "2px solid #B42318"; }   // left as it was - check it
            else { q.value = it.qty; q.classList.add("dr-filled"); }
            matched++;
          }
          else left.push(it.description + " " + it.qty + (it.unit ? " " + it.unit : ""));
        });
        rows.forEach(function (tr, i) { var q = tr.querySelector(".recv-qty"); if (q && !used[i] && (r.items || []).length) q.value = ""; });
        return "Filled in: " + (r.found || []).join(", ") + ". " + matched + " of " + (r.items || []).length + " material line" + ((r.items || []).length === 1 ? "" : "s") + " matched" +
          (left.length ? " - not on this order: " + left.join("; ") : "") + ". Lines not on the note were cleared." +
          (unread.length ? " The quantity could not be read for: " + unread.join("; ") + " - type it from the note." : "") + " Check, then save.";
      });
  }

  // bank statement: a PDF or a scan, as well as the Excel download
  window.bsUploadDoc = async function (inp) {
    var f = inp.files[0]; if (!f) return;
    var isDoc = /\.(pdf|docx|jpe?g|png|webp)$/i.test(f.name) || /^image\//.test(f.type || "");
    if (!isDoc) return window.bsUpload(inp);
    inp.value = "";
    var st = function (k, t) { if (window.showStatus) window.showStatus("bk-status", k, t); };
    st("ok", "Reading " + f.name + " on this computer ...");
    try {
      var d = await read("bank", f, function (t) { st("ok", t); });
      var dt = function (x) { try { return window.pcDate ? window.pcDate(x) : x; } catch (e) { return x; } };
      st(d.breaks ? "err" : "ok", "Statement " + dt(d.from) + " to " + dt(d.to) + ": " + d.lines + " lines, " + d.added + " new" + (d.duplicates ? ", " + d.duplicates + " already in" : "") + ". " + d.matched + " matched to entries." +
         (d.mended ? " " + d.mended + " figure" + (d.mended === 1 ? "" : "s") + " the scan misread " + (d.mended === 1 ? "was" : "were") + " put right from the bank's running balance." : "") +
         (d.breaks ? " Warning: the running balance does not add up in " + d.breaks + " place" + (d.breaks === 1 ? "" : "s") + " - lines may be missing or misread. Check those lines against the paper statement." : " The running balance checks out."));
      try { BS_F = "problems"; } catch (e) {}
      if (window.bkStatement) await window.bkStatement();
    } catch (e) { st("err", errMsg(e)); }
  };

  window.docReadWire = function () { wirePetty(); wireCheques(); wireIdDocs(); wireStore(); };
  window.docReadFile = read;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", window.docReadWire); else window.docReadWire();
})();
