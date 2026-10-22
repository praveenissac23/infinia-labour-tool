/* Reading a subcontract agreement on this computer - PDF, Word or Excel.
   The file never leaves the browser: it is opened here, its text is laid out in lines and cells, and
   only that text goes to the server, which picks out the subcontractor, the numbers, the terms and the
   priced schedule (app/est_agreement.py). Nothing is kept on the server.

   The libraries are loaded the first time a file is read (portal/vendor/...). */
(function (root) {
  "use strict";
  var V = "/portal/vendor/";
  function load(src) {
    return new Promise(function (ok, no) {
      if (document.querySelector('script[data-v="' + src + '"]')) return ok();
      var s = document.createElement("script"); s.src = V + src; s.dataset.v = src; s.onload = ok; s.onerror = function () { no(new Error("Could not load the reader (" + src + ").")); };
      document.head.appendChild(s);
    });
  }

  // ---- PDF: the words on each page, put back into lines (same height) and cells (a gap between) ----
  async function pdfLines(pdfjs, data) {
    var doc = await pdfjs.getDocument({ data: data, isEvalSupported: false, useSystemFonts: true }).promise;
    var out = [];
    for (var pn = 1; pn <= doc.numPages; pn++) {
      var page = await doc.getPage(pn), vp = page.getViewport({ scale: 1 });
      var tc = await page.getTextContent();
      var items = tc.items.filter(function (i) { return i.str && i.str.trim(); }).map(function (i) {
        var h = Math.abs(i.transform[3]) || i.height || 8;
        return { s: i.str, x: i.transform[4], y: vp.height - i.transform[5], w: i.width, h: h, f: i.fontName || "" };
      });
      items.sort(function (a, b) { return a.y - b.y || a.x - b.x; });
      var rows = [];
      items.forEach(function (it) {
        var r = rows.length ? rows[rows.length - 1] : null;
        if (r && Math.abs(r.y - it.y) <= Math.max(2, it.h * 0.35)) r.items.push(it); else rows.push({ y: it.y, items: [it] });
      });
      rows.forEach(function (r) {
        r.items.sort(function (a, b) { return a.x - b.x; });
        var cells = [], cur = null, end = -1, size = 0, bold = 0;
        r.items.forEach(function (it) {
          var gap = it.x - end;
          if (cur && gap < Math.max(4, it.h * 0.9)) { cur.t += (gap > it.h * 0.15 && !/\s$/.test(cur.t) && !/^\s/.test(it.s) ? " " : "") + it.s; }
          else { cur = { t: it.s, x: Math.round(it.x) }; cells.push(cur); }
          end = it.x + it.w; size = Math.max(size, it.h);
        });
        cells.forEach(function (c) { c.t = c.t.replace(/\s+/g, " ").trim(); });
        cells = cells.filter(function (c) { return c.t; });
        if (!cells.length) return;
        out.push({ p: pn, y: Math.round(r.y), h: Math.round(size * 10) / 10, c: cells.map(function (c) { return c.t; }), x: cells.map(function (c) { return c.x; }),
                   t: cells.map(function (c) { return c.t; }).join("  ") });
      });
    }
    return out;
  }

  // ---- Word (.docx): paragraphs as lines, table rows as lines of cells ----
  async function docxLines(data) {
    await load("jszip-3.10.1.min.js");
    var zip = await root.JSZip.loadAsync(data);
    var f = zip.file("word/document.xml"); if (!f) throw new Error("That Word file has no text in it.");
    var xml = new DOMParser().parseFromString(await f.async("string"), "application/xml");
    var W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    var text = function (el) { var s = ""; el.querySelectorAll ? null : null;
      var walk = function (n) { if (n.namespaceURI === W && n.localName === "t") s += n.textContent; else if (n.namespaceURI === W && (n.localName === "tab")) s += " "; else if (n.namespaceURI === W && n.localName === "br") s += " "; for (var k = n.firstChild; k; k = k.nextSibling) if (k.nodeType === 1) walk(k); };
      walk(el); return s.replace(/\s+/g, " ").trim(); };
    var body = xml.getElementsByTagNameNS(W, "body")[0], out = [];
    for (var n = body.firstChild; n; n = n.nextSibling) {
      if (n.nodeType !== 1) continue;
      if (n.localName === "p") { var t = text(n); if (t) out.push({ p: 1, c: [t], t: t }); }
      else if (n.localName === "tbl") {
        var rows = n.getElementsByTagNameNS(W, "tr");
        for (var i = 0; i < rows.length; i++) {
          var cells = [], tcs = rows[i].childNodes;
          for (var j = 0; j < tcs.length; j++) if (tcs[j].nodeType === 1 && tcs[j].localName === "tc") cells.push(text(tcs[j]));
          var cl = cells.filter(function (c) { return c; });
          if (cl.length) out.push({ p: 1, c: cells, t: cl.join("  "), tbl: 1 });
        }
      }
    }
    return out;
  }

  // ---- Excel: every visible sheet, row by row ----
  async function xlsxLines(data) {
    await load("xlsx-0.18.5.core.min.js");
    var wb = root.XLSX.read(data, { type: "array", cellDates: true }), out = [];
    wb.SheetNames.forEach(function (name, si) {
      var hidden = wb.Workbook && wb.Workbook.Sheets && wb.Workbook.Sheets[si] && wb.Workbook.Sheets[si].Hidden;
      if (hidden) return;
      var rows = root.XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, raw: false, defval: "" });
      rows.forEach(function (r) {
        var cells = r.map(function (v) { return String(v == null ? "" : v).replace(/\s+/g, " ").trim(); });
        while (cells.length && !cells[cells.length - 1]) cells.pop();
        if (cells.some(function (c) { return c; })) out.push({ p: si + 1, c: cells, t: cells.filter(Boolean).join("  "), sheet: name });
      });
    });
    return out;
  }

  async function readAgreement(file) {
    var name = (file.name || "").toLowerCase(), data = new Uint8Array(await file.arrayBuffer());
    if (/\.pdf$/.test(name) || (data[0] === 0x25 && data[1] === 0x50)) {
      await load("pdf-3.11.174.min.js");
      root.pdfjsLib.GlobalWorkerOptions.workerSrc = V + "pdf.worker-3.11.174.min.js";
      var lines = await pdfLines(root.pdfjsLib, data);
      if (!lines.length) throw new Error("This PDF has no text to read - it looks like a scan. Use the Word or Excel copy, or a PDF saved from the original.");
      return { kind: "pdf", lines: lines };
    }
    if (/\.docx$/.test(name)) return { kind: "docx", lines: await docxLines(data) };
    if (/\.doc$/.test(name)) throw new Error("Old .doc files cannot be read - save it as .docx (Word: File > Save As) or PDF.");
    if (/\.(xlsx|xlsm|xls)$/.test(name)) return { kind: "xlsx", lines: await xlsxLines(data) };
    throw new Error("Choose a PDF, Word (.docx) or Excel file.");
  }
  root.readAgreement = readAgreement;
  root.agreementPdfLines = pdfLines;     // for Node tests
})(typeof window !== "undefined" ? window : globalThis);
