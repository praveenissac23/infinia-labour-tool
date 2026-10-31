// The confirm screen for a document read into an Estimation form (Previous records, Read from document on the
// project and client-bill forms, Read from agreement, Import log).
//
// The file is sent to the server and read there (app/est_fileread.py + app/docread - no AI, nothing kept): every
// figure comes back with a status and where it was found. The form then shows, beside its boxes, the page itself
// (from the file this browser still holds: PDF.js for a PDF or scan, a small grid for Excel, the picture for a
// photo), a chip on every box that was read - green "ok" (one of the document's own sums ties it in), amber "check"
// (look at it), blue "derived" (worked out from the other figures) - and the document's sums with a tick or a cross
// at the top. Tapping a box or its chip marks where it came from on the page. Save needs every amber box confirmed
// (tap its chip) or corrected. Nothing is saved until Save. On a phone the page sits above the boxes.
//
// When the server cannot read the file itself (no PDF / OCR package there - it answers 501 with the reason) the file
// is read on this computer as before (portal/est/agreement.js) and its text is sent instead.
(function () {
  "use strict";
  const V = "/portal/vendor/";
  const CFV = { on: false, r: null, file: null, map: {}, kind: "", page: 1, pdf: null, wb: null, url: null, rows: null, token: 0 };
  window.CFV = CFV;
  function load(src) {
    return new Promise((ok, no) => {
      if (document.querySelector(`script[data-v="${src}"]`)) return ok();
      const s = document.createElement("script"); s.src = V + src; s.dataset.v = src; s.onload = ok; s.onerror = () => no(new Error("Could not load the page preview."));
      document.head.appendChild(s);
    });
  }
  const isXl = f => /\.(xlsx|xlsm|xls)$/i.test(f.name || "");
  const isPdf = f => /\.pdf$/i.test(f.name || "") || f.type === "application/pdf";
  const isImg = f => /\.(jpe?g|png|webp|bmp|gif)$/i.test(f.name || "") || /^image\//.test(f.type || "");

  // ---- reading: the file to the server; this computer reads it when the server cannot ----------------------------
  // url: /store/est/read/<kind>, /store/est/subs/agreement/read ...; extra: more form fields (objects sent as JSON)
  async function cfvRead(url, file, extra, say) {
    say = say || (() => {});
    extra = extra || {};
    try {
      say(`Sending ${file.name} to be read ...`);
      const fd = new FormData();
      await addFile(fd, file);
      Object.entries(extra).forEach(([k, v]) => fd.append(k, typeof v === "string" ? v : JSON.stringify(v)));
      say(`Reading ${file.name} ... (a scanned page takes a little longer)`);
      return await api(url, { method: "POST", body: fd });
    } catch (e) {
      if (e.status !== 501) throw e;
      // this server cannot read it itself: read on this computer, its text sent instead
      const why = e.message;
      say(why);
      const d = await readAgreement(file, say);
      const r = await POST(url, Object.assign({ lines: d.lines, name: file.name }, extra));
      r.notes = [why].concat(r.notes || []);
      r.read_here = true;
      return r;
    }
  }
  window.cfvRead = cfvRead;

  // ---- the page preview ---------------------------------------------------------------------------------------
  function docPane() { return document.querySelector("#m-body .cfv-doc"); }
  async function preview(file, r) {
    const pane = docPane(); if (!pane) return;
    const tok = ++CFV.token;
    CFV.pdf = null; CFV.wb = null; if (CFV.url) { URL.revokeObjectURL(CFV.url); CFV.url = null; }
    const pages = (r.pages || []).length || 1;
    pane.innerHTML = `<div class="cfv-bar"><b>${esc(file.name)}</b><span class="spacer"></span><span class="cfv-nav"></span></div><div class="cfv-view"><div class="agnote">Opening the page ...</div></div>`;
    try {
      if (isPdf(file)) {
        await load("pdf-3.11.174.min.js");
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = V + "pdf.worker-3.11.174.min.js";
        const data = new Uint8Array(await file.arrayBuffer());
        CFV.pdf = await window.pdfjsLib.getDocument({ data, isEvalSupported: false }).promise;
        CFV.kind = "pdf"; CFV.npages = CFV.pdf.numPages;
      } else if (isImg(file)) {
        CFV.kind = "img"; CFV.url = URL.createObjectURL(file); CFV.npages = 1;
      } else if (isXl(file)) {
        await load("xlsx-0.18.5.core.min.js");
        CFV.wb = window.XLSX.read(new Uint8Array(await file.arrayBuffer()), { type: "array" });
        CFV.kind = "sheet";
        CFV.sheets = CFV.wb.SheetNames.filter((n, i) => !(CFV.wb.Workbook && CFV.wb.Workbook.Sheets && CFV.wb.Workbook.Sheets[i] && CFV.wb.Workbook.Sheets[i].Hidden));
        CFV.npages = CFV.sheets.length;
      } else {
        CFV.kind = "none"; CFV.npages = 0;
      }
    } catch (e) { CFV.kind = "none"; }
    if (tok !== CFV.token) return;
    CFV.page = 1;
    if (CFV.kind === "sheet") { const first = (r.pages || []).find(p => p.kind === "sheet"); if (first) { const i = CFV.sheets.indexOf(first.name); if (i >= 0) CFV.page = i + 1; } }
    await showPage(CFV.page);
    void pages;
  }
  async function showPage(n, mark) {
    const pane = docPane(); if (!pane) return;
    const view = pane.querySelector(".cfv-view"), nav = pane.querySelector(".cfv-nav");
    if (CFV.npages > 1) {
      const lab = CFV.kind === "sheet" ? esc(CFV.sheets[n - 1]) : `Page ${n} of ${CFV.npages}`;
      nav.innerHTML = `<button type="button" class="btn btn-plain btn-sm" data-cfp="-1" ${n <= 1 ? "disabled" : ""} aria-label="Previous page">&lsaquo;</button><span class="small">${lab}</span><button type="button" class="btn btn-plain btn-sm" data-cfp="1" ${n >= CFV.npages ? "disabled" : ""} aria-label="Next page">&rsaquo;</button>`;
      nav.querySelectorAll("[data-cfp]").forEach(b => b.onclick = () => showPage(Math.min(CFV.npages, Math.max(1, CFV.page + +b.dataset.cfp))));
    } else nav.innerHTML = "";
    CFV.page = n;
    const W = Math.max(240, view.clientWidth - 2);
    if (CFV.kind === "pdf") {
      const page = await CFV.pdf.getPage(n), v1 = page.getViewport({ scale: 1 }), sc = W / v1.width, vp = page.getViewport({ scale: sc });
      const dpr = Math.min(2, window.devicePixelRatio || 1), cv = document.createElement("canvas");
      cv.width = Math.round(vp.width * dpr); cv.height = Math.round(vp.height * dpr); cv.style.width = Math.round(vp.width) + "px"; cv.style.height = Math.round(vp.height) + "px";
      const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      await page.render({ canvasContext: ctx, viewport: vp }).promise;
      view.innerHTML = ""; const box = document.createElement("div"); box.className = "cfv-page"; box.style.width = cv.style.width; box.style.height = cv.style.height;
      box.appendChild(cv); view.appendChild(box);
      CFV.scale = sc;
    } else if (CFV.kind === "img") {
      view.innerHTML = `<div class="cfv-page"><img alt="The page" src="${CFV.url}" style="width:${W}px;display:block"></div>`;
      const im = view.querySelector("img");
      await new Promise(ok => { if (im.complete) ok(); else { im.onload = ok; im.onerror = ok; } });
      const pg = (CFV.r.pages || [])[0]; CFV.scale = pg && pg.w ? W / pg.w : W / (im.naturalWidth || W);
    } else if (CFV.kind === "sheet") {
      view.innerHTML = gridHtml(CFV.sheets[n - 1]);
    } else {
      view.innerHTML = `<div class="agnote">No page picture for this kind of file - the boxes show what was read from it.</div>`;
    }
    if (mark) mark();
  }
  function gridHtml(name) {
    const X = window.XLSX, ws = CFV.wb.Sheets[name]; if (!ws || !ws["!ref"]) return `<div class="agnote">This sheet is empty.</div>`;
    const rg = X.utils.decode_range(ws["!ref"]), r1 = Math.min(rg.e.r, rg.s.r + 299), c1 = Math.min(rg.e.c, rg.s.c + 25);
    const hidR = ws["!rows"] || [], hidC = ws["!cols"] || [];
    const cols = []; for (let c = rg.s.c; c <= c1; c++) if (!(hidC[c] && hidC[c].hidden)) cols.push(c);
    let h = `<table class="cfv-grid"><thead><tr><th></th>${cols.map(c => `<th>${X.utils.encode_col(c)}</th>`).join("")}</tr></thead><tbody>`;
    for (let r = rg.s.r; r <= r1; r++) {
      if (hidR[r] && hidR[r].hidden) continue;
      h += `<tr data-row="${r + 1}"><th>${r + 1}</th>`;
      for (const c of cols) {
        const a = X.utils.encode_cell({ r, c }), cell = ws[a];
        const t = cell ? (cell.w != null ? cell.w : cell.v != null ? String(cell.v) : "") : "";
        h += `<td data-ref="${a}" class="${cell && cell.t === "n" ? "n" : ""}">${esc(t)}</td>`;
      }
      h += "</tr>";
    }
    return h + "</tbody></table>";
  }
  // Mark where a field came from: {page, bbox} on a page, {ref: "Sheet!E14"} in a workbook
  async function mark(where) {
    const pane = docPane(); if (!pane || !where) return;
    pane.querySelectorAll(".cfv-hl").forEach(x => x.remove());
    pane.querySelectorAll(".cfv-grid .hl").forEach(x => x.classList.remove("hl"));
    const ref = where.ref || "";
    if (CFV.kind === "sheet" && ref) {
      const m = /^(.*)!(?:([A-Z]+\d+)|row (\d+))$/.exec(ref); if (!m) return;
      const i = CFV.sheets.indexOf(m[1]);
      const go = () => {
        const view = pane.querySelector(".cfv-view");
        const el = m[2] ? view.querySelector(`td[data-ref="${m[2]}"]`) : view.querySelector(`tr[data-row="${m[3]}"]`);
        if (!el) return;
        (m[2] ? [el] : [...el.children]).forEach(x => x.classList.add("hl"));
        scrollInside(view, el);
      };
      if (i >= 0 && i + 1 !== CFV.page) await showPage(i + 1, go); else go();
      return;
    }
    if ((CFV.kind === "pdf" || CFV.kind === "img") && where.bbox) {
      const go = () => {
        const page = pane.querySelector(".cfv-page"); if (!page) return;
        const [x0, y0, x1, y1] = where.bbox, s = CFV.scale || 1, pad = 3;
        const hl = document.createElement("div"); hl.className = "cfv-hl";
        Object.assign(hl.style, { left: (x0 * s - pad) + "px", top: (y0 * s - pad) + "px", width: Math.max(8, (x1 - x0) * s + 2 * pad) + "px", height: Math.max(8, (y1 - y0) * s + 2 * pad) + "px" });
        page.appendChild(hl);
        scrollInside(pane.querySelector(".cfv-view"), hl);
      };
      const pn = where.page || 1;
      if (CFV.kind === "pdf" && pn !== CFV.page) await showPage(pn, go); else go();
    }
  }
  function scrollInside(box, el) {
    if (!box || !el) return;
    const b = box.getBoundingClientRect(), e = el.getBoundingClientRect();
    box.scrollTop += (e.top - b.top) - (b.height / 2 - e.height / 2);
    box.scrollLeft += (e.left - b.left) - (b.width / 2 - e.width / 2);
  }

  // ---- the chips ----------------------------------------------------------------------------------------------
  const CHIP = { ok: ["ok", "One of the document's own sums ties this figure in."], check: ["check", "Look at this one on the page - tap the chip when it is right, or correct the box."],
                 derived: ["derived", "Not printed on the document - worked out from its other figures."] };
  function detailOf(k) {
    const det = (CFV.r && CFV.r.detail) || {}, m = CFV.map[k];
    for (const dk of String(m || k).split("|")) if (det[dk]) return det[dk];
    return null;
  }
  function chipHtml(k, d) {
    const st = CHIP[d.status] ? d.status : "check", [lab, why] = CHIP[st];
    const pct = d.confidence != null ? ` · ${Math.round(d.confidence * 100)}% sure` : "";
    const where = d.where ? (d.where.ref ? ` · ${d.where.ref}` : ` · page ${d.where.page || 1}`) : "";
    return `<button type="button" class="cfchip ${st}" data-cfk="${esc(k)}" title="${esc(why + (d.note ? " (" + d.note + ")" : "") + pct + where)}">${lab}</button>`;
  }
  function chipDone(k, how) {
    document.querySelectorAll(`#m-body .cfchip[data-cfk="${CSS.escape(k)}"]`).forEach(c => {
      if (!c.classList.contains("check") || c.classList.contains("done")) return;
      c.classList.add("done"); c.textContent = how === "edit" ? "corrected" : "checked"; c.title = how === "edit" ? "Corrected by you" : "Confirmed by you";
    });
    countLeft();
  }
  function countLeft() {
    const n = document.querySelectorAll("#m-body .cfchip.check:not(.done):not(.static)").length, el = document.querySelector("#m-body .cfv-left");
    if (el) { el.textContent = n ? `${n} amber figure${n > 1 ? "s" : ""} to check before Save` : "Every figure checked"; el.className = "cfv-left " + (n ? "a" : "g"); }
  }

  // Put the confirm screen on the open form. map: { form box key: "detail key" | "key1|key2" }; null = the same keys.
  function confirmView(r, file, map) {
    const body = document.getElementById("m-body"); if (!body || !r) return;
    CFV.on = true; CFV.r = r; CFV.file = file; CFV.map = map || {};
    document.querySelector(".mbox").classList.add("cfm");
    let lay = body.querySelector(".cfv");
    if (!lay) {
      lay = h(`<div class="cfv"><div class="cfv-doc"></div><div class="cfv-main"></div></div>`);
      const main = lay.querySelector(".cfv-main");
      while (body.firstChild) main.appendChild(body.firstChild);
      body.appendChild(lay);
    }
    const main = lay.querySelector(".cfv-main");
    main.querySelectorAll(".cfchip,.cfv-head").forEach(x => x.remove());
    const det = r.detail || {};
    const keys = map ? Object.keys(map) : Object.keys(det);
    keys.forEach(k => {
      const el = document.getElementById("f-" + k); if (!el) return;
      const d = detailOf(k); if (!d) return;
      const has = el.type === "checkbox" ? el.checked : String(el.value || "").trim() !== "";
      if (!has) return;
      const lab = main.querySelector(`label[for="f-${CSS.escape(k)}"]`) || (el.closest(".f") && el.closest(".f").querySelector("label"));
      if (!lab) return;
      lab.insertAdjacentHTML("beforeend", chipHtml(k, d));
      if (!el._cfv) {
        el._cfv = 1;
        const edited = e => { if (e.isTrusted) chipDone(k, "edit"); };
        el.addEventListener("input", edited); el.addEventListener("change", edited);
        const seg = document.querySelector(`.seg[data-segfor="${CSS.escape(k)}"]`);
        if (seg) seg.addEventListener("click", e => { if (e.isTrusted && e.target.closest("button")) chipDone(k, "edit"); });
      }
    });
    const nAmber = main.querySelectorAll(".cfchip.check").length;
    const how = r.read_here ? "read on this computer" : r.engine === "older reader" ? "read on the server (the older reader)" : "read on the server";
    main.insertAdjacentHTML("afterbegin", `<div class="cfv-head"><span class="cfchip ok static">ok</span> tied in by the document's sums <span class="cfchip check static">check</span> look at it <span class="cfchip derived static">derived</span> worked out
      ${tip("Tap a box or its chip to see where it is on the page. Amber boxes need a look: tap the chip when the figure is right, or correct it - Save waits until every amber box is checked. Nothing is saved until you press Save.")}
      <span class="spacer"></span><span class="small muted">${esc(how)}</span><span class="cfv-left"></span></div>`);
    countLeft();
    preview(file, r);
    void nAmber;
    // the form's own Save & exit (when leaving with changes) waits for the amber boxes too
    try { const g = GUARD.modal; if (g && !g._cfv) { const o = g.save; g.save = async x => (gate() ? o(x) : false); g._cfv = 1; } } catch (e) { /* no guard on this form */ }
  }
  window.confirmView = confirmView;

  // The variation log's lines: a chip per line read (amber when a cell of it was hard to read), a tap shows it.
  function confirmRows(r, file, table) {
    if (!table || !(r.detail || []).some(Boolean)) return;      // the team's own Excel log, read exactly: nothing to point at
    CFV.on = true; CFV.r = r; CFV.file = file; CFV.map = {};
    const body = document.getElementById("m-body"); if (!body) return;
    document.querySelector(".mbox").classList.add("cfm");
    let lay = body.querySelector(".cfv");
    if (!lay) {
      lay = h(`<div class="cfv"><div class="cfv-doc"></div><div class="cfv-main"></div></div>`);
      const main = lay.querySelector(".cfv-main");
      while (body.firstChild) main.appendChild(body.firstChild);
      body.appendChild(lay);
    }
    const det = r.detail || [];
    CFV.rows = det;
    table.querySelectorAll("tbody tr").forEach((tr, i) => {
      const d = det[i]; const td = tr.querySelector("td"); if (!td) return;
      if (!d) return;
      const bad = (d.check && d.check.length) || (d.conf != null && d.conf < 0.85);
      td.insertAdjacentHTML("afterbegin", `<button type="button" class="cfchip ${bad ? "check" : "ok"}" data-cfrow="${i}" data-cfk="row${i}" title="${bad ? esc("Look at this line on the page" + (d.check && d.check.length ? " (" + d.check.join(", ") + " hard to read)" : "") + " - tap when it is right") : "Read clearly"}">${bad ? "check" : "ok"}</button> `);
      tr.dataset.cfrow = i; tr.style.cursor = "pointer";
    });
    const main = lay.querySelector(".cfv-main");
    main.insertAdjacentHTML("afterbegin", `<div class="cfv-head"><span class="small">Tap a line to see it on the page.</span>${tip("Lines marked check had a figure or word that was hard to read: look at each on the page and tap its chip when it is right. Wrong lines can be corrected on the variation after it is added.")}<span class="spacer"></span><span class="cfv-left"></span></div>`);
    countLeft();
    preview(file, r);
  }
  window.confirmRows = confirmRows;

  function gate() {
    if (!CFV.on || document.getElementById("modal").classList.contains("hide")) return true;
    const left = [...document.querySelectorAll("#m-body .cfchip.check:not(.done):not(.static)")];
    if (!left.length) return true;
    toast(`Check the ${left.length} amber figure${left.length > 1 ? "s" : ""} first - tap each amber chip when it is right, or correct the box.`, { err: true, ms: 6000 });
    const c = left[0]; c.classList.remove("pulse"); void c.offsetWidth; c.classList.add("pulse");
    c.scrollIntoView({ block: "center", behavior: "smooth" });
    showFor(c);
    return false;
  }
  window.cfvGate = gate;
  function showFor(c) {
    if (c.dataset.cfrow != null) { const d = (CFV.rows || [])[+c.dataset.cfrow]; if (d) mark(d.where); return; }
    const d = detailOf(c.dataset.cfk); if (d && d.where) mark(d.where);
  }
  // Save (button or Enter in a box) waits for the amber figures
  document.addEventListener("click", e => {
    const t = e.target;
    if (t.closest && t.closest("#m-save") && !gate()) { e.stopImmediatePropagation(); e.preventDefault(); return; }
    const chip = t.closest && t.closest("#m-body .cfchip:not(.static)");
    if (chip) {
      e.preventDefault(); e.stopPropagation();
      if (chip.classList.contains("check") && !chip.classList.contains("done")) chipDone(chip.dataset.cfk, "ok");
      showFor(chip);
      return;
    }
    const tr = t.closest && t.closest("#m-body tr[data-cfrow]");
    if (tr && CFV.rows) { const d = CFV.rows[+tr.dataset.cfrow]; if (d) mark(d.where); }
  }, true);
  document.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && e.target && e.target.tagName === "INPUT" && e.target.closest("#m-body") && !gate()) { e.stopImmediatePropagation(); e.preventDefault(); }
  }, true);
  // a box with a reading: its place on the page when it is picked
  document.addEventListener("focusin", e => {
    if (!CFV.on || !e.target || !e.target.id || !e.target.id.startsWith("f-") || !e.target.closest("#m-body")) return;
    const d = detailOf(e.target.id.slice(2)); if (d && d.where) mark(d.where);
  });
  // a new form: the confirm screen goes with the old one
  window.cfvReset = () => {
    CFV.on = false; CFV.r = null; CFV.rows = null; CFV.token++; CFV.pdf = null; CFV.wb = null;
    if (CFV.url) { URL.revokeObjectURL(CFV.url); CFV.url = null; }
    const mb = document.querySelector(".mbox"); if (mb) mb.classList.remove("cfm");
  };
  let rz = null;
  addEventListener("resize", () => { if (!CFV.on || !docPane() || CFV.kind === "sheet") return; clearTimeout(rz); rz = setTimeout(() => showPage(CFV.page), 250); });
})();
