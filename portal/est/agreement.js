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

  // ---- scans and photos: the text recognised on this computer (Tesseract, in the browser) ----
  var ocrWorker = null;
  async function ocr() {
    if (ocrWorker) return ocrWorker;
    await load("tesseract/tesseract.min.js");
    var base = location.origin + V + "tesseract/";
    ocrWorker = await root.Tesseract.createWorker("eng", 1, { workerPath: base + "worker.min.js", corePath: base, langPath: base.replace(/\/$/, ""), gzip: true,
                                                              workerBlobURL: false, cacheMethod: "readwrite" });
    await ocrWorker.setParameters({ preserve_interword_spaces: "1", tessedit_pageseg_mode: "3" });   // the whole page, laid out (titles and tables too)
    return ocrWorker;
  }
  // what the recogniser saw, as lines and cells (a wide gap between words starts a new cell)
  function ocrLines(data, pn, scale) {
    var out = [];
    (data.lines || []).forEach(function (ln) {
      var words = (ln.words || []).filter(function (w) { return w.text && w.text.trim() && w.confidence > 15; });
      if (!words.length) return;
      var h = (ln.bbox.y1 - ln.bbox.y0) / scale, cells = [], cur = null, end = -1;
      words.forEach(function (w) {
        var x0 = w.bbox.x0 / scale, x1 = w.bbox.x1 / scale;
        if (cur && x0 - end < Math.max(6, h * 1.1)) cur.t += " " + w.text; else { cur = { t: w.text, x: Math.round(x0) }; cells.push(cur); }
        end = x1;
      });
      out.push({ p: pn, y: Math.round(ln.bbox.y0 / scale), h: Math.round(Math.min(h, 14) * 10) / 10, c: cells.map(function (c) { return c.t.trim(); }),
                 x: cells.map(function (c) { return c.x; }), t: cells.map(function (c) { return c.t.trim(); }).join("  "), ocr: 1 });
    });
    return out;
  }
  async function ocrImage(src, pn, scale, say) {
    var w = await ocr();
    var r = await w.recognize(src);
    return ocrLines(r.data, pn, scale || 1);
  }
  async function readAgreement(file, say) {
    say = say || function () {};
    var name = (file.name || "").toLowerCase(), data = new Uint8Array(await file.arrayBuffer());
    if (/\.(jpe?g|png|webp|bmp|tiff?)$/.test(name) || /^image\//.test(file.type || "")) {
      say("Recognising the text in the picture ... (the first time takes a little longer)");
      var url = URL.createObjectURL(file);
      try { var il = await ocrImage(url, 1, 2); } finally { URL.revokeObjectURL(url); }
      if (!il.length) throw new Error("No text could be recognised in that picture - take it again, flat and in good light.");
      return { kind: "image", lines: il, ocr: true };
    }
    if (/\.pdf$/.test(name) || (data[0] === 0x25 && data[1] === 0x50)) {
      await load("pdf-3.11.174.min.js");
      root.pdfjsLib.GlobalWorkerOptions.workerSrc = V + "pdf.worker-3.11.174.min.js";
      var lines = await pdfLines(root.pdfjsLib, data.slice(0));
      // pages with (almost) no text are scans: recognise them
      var doc = await root.pdfjsLib.getDocument({ data: data.slice(0), isEvalSupported: false }).promise, scanned = [];
      for (var pn = 1; pn <= doc.numPages; pn++) {
        var chars = lines.filter(function (l) { return l.p === pn; }).reduce(function (a, l) { return a + l.t.length; }, 0);
        if (chars < 40) scanned.push(pn);
      }
      if (scanned.length) {
        lines = lines.filter(function (l) { return scanned.indexOf(l.p) < 0; });
        for (var k = 0; k < scanned.length; k++) {
          say("Scanned page " + (k + 1) + " of " + scanned.length + " - recognising the text ... (the first time takes a little longer)");
          var page = await doc.getPage(scanned[k]), sc = 2.4, vp = page.getViewport({ scale: sc });
          var cv = document.createElement("canvas"); cv.width = Math.round(vp.width); cv.height = Math.round(vp.height);
          await page.render({ canvasContext: cv.getContext("2d"), viewport: vp }).promise;
          lines = lines.concat(await ocrImage(cv, scanned[k], sc));
        }
        lines.sort(function (a, b) { return a.p - b.p || a.y - b.y; });
      }
      if (!lines.length) throw new Error("No text could be read in this PDF, not even by recognising it - use a clearer scan.");
      return { kind: "pdf", lines: lines, ocr: scanned.length > 0 };
    }
    if (/\.docx$/.test(name)) return { kind: "docx", lines: await docxLines(data) };
    if (/\.doc$/.test(name)) throw new Error("Old .doc files cannot be read - save it as .docx (Word: File > Save As) or PDF.");
    if (/\.(xlsx|xlsm|xls)$/.test(name)) return { kind: "xlsx", lines: await xlsxLines(data) };
    throw new Error("Choose a PDF, Word (.docx), Excel file or a photo.");
  }
  root.readAgreement = readAgreement;
  root.agreementPdfLines = pdfLines;     // for Node tests
})(typeof window !== "undefined" ? window : globalThis);
