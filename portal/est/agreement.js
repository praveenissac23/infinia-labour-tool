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
          end = it.x + it.w; cur.e = Math.round(end); size = Math.max(size, it.h);
        });
        cells.forEach(function (c) { c.t = c.t.replace(/\s+/g, " ").trim(); });   // c.e: where the cell ends (figures line up on the right)
        cells = cells.filter(function (c) { return c.t; });
        if (!cells.length) return;
        out.push({ p: pn, y: Math.round(r.y), h: Math.round(size * 10) / 10, c: cells.map(function (c) { return c.t; }), x: cells.map(function (c) { return c.x; }), xe: cells.map(function (c) { return c.e; }),
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
      // A real date cell is written out day first (06/10/2026). Excel's default "Short Date" would come out US
      // style (10/6/26) and be read back as 10 June - the office reads every date as dd/mm/yyyy.
      var ws = wb.Sheets[name];
      Object.keys(ws).forEach(function (k) {
        var c = ws[k];
        if (k.charAt(0) !== "!" && c && c.t === "d" && c.v instanceof Date && !isNaN(c.v)) {
          var d = new Date(c.v.getTime()), p2 = function (n) { return (n < 10 ? "0" : "") + n; };
          // SheetJS can land a few seconds before midnight in some time zones: that is the next day
          if (d.getHours() === 23 && d.getMinutes() >= 59) d = new Date(d.getTime() + 60 * 1000);
          var day = p2(d.getDate()) + "/" + p2(d.getMonth() + 1) + "/" + d.getFullYear();
          c.w = (d.getHours() || d.getMinutes()) ? day + " " + p2(d.getHours()) + ":" + p2(d.getMinutes()) : day;
        }
      });
      var rows = root.XLSX.utils.sheet_to_json(ws, { header: 1, raw: false, defval: "" });
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
  // A second reader for figures only: each number on the page is read again, close up, digits only.
  var numWorker = null;
  async function numOcr() {
    if (numWorker) return numWorker;
    var base = location.origin + V + "tesseract/";
    numWorker = await root.Tesseract.createWorker("eng", 1, { workerPath: base + "worker.min.js", corePath: base, langPath: base.replace(/\/$/, ""), gzip: true,
                                                             workerBlobURL: false, cacheMethod: "readwrite" });
    await numWorker.setParameters({ tessedit_char_whitelist: "0123456789.,-/:%", tessedit_pageseg_mode: "7" });
    return numWorker;
  }
  // Clean the picture before reading: grey, the contrast stretched (faded scans, watermarks, phone shadows),
  // and small pictures (screenshots, WhatsApp photos) enlarged so letters are big enough to read surely.
  function prep(cv) {
    var mode = root.__ocrPrep || "up";                       // measured best: small pictures enlarged, the picture as it is (test switch: none | contrast | up | both)
    if (mode === "none") { cv._up = 1; return cv; }
    var W = cv.width, H = cv.height, side = Math.max(W, H), up = mode === "contrast" ? 1 : (side < 1100 ? Math.min(2, 1600 / Math.max(1, side)) : 1);   // only small pictures (WhatsApp, screenshots) are enlarged
    var out = cv;
    if (up > 1.05) {
      out = document.createElement("canvas"); out.width = Math.round(W * up); out.height = Math.round(H * up);
      var c2 = out.getContext("2d"); c2.imageSmoothingEnabled = true; c2.imageSmoothingQuality = "high"; c2.drawImage(cv, 0, 0, out.width, out.height);
      W = out.width; H = out.height;
    }
    var ctx = out.getContext("2d"), im = ctx.getImageData(0, 0, W, H), d = im.data, hist = new Uint32Array(256), n = W * H, i;
    for (i = 0; i < n; i++) { var g = Math.round(d[i * 4] * 0.3 + d[i * 4 + 1] * 0.59 + d[i * 4 + 2] * 0.11); d[i * 4] = g; hist[g]++; }
    var lo = 0, hi = 255, acc = 0;
    for (i = 0; i < 256; i++) { acc += hist[i]; if (acc > n * 0.01) { lo = i; break; } }
    acc = 0; for (i = 255; i >= 0; i--) { acc += hist[i]; if (acc > n * 0.02) { hi = i; break; } }
    if (hi - lo < 40 || mode === "up") { lo = 0; hi = 255; }
    var k = 255 / Math.max(1, hi - lo);
    for (i = 0; i < n; i++) { var v = Math.max(0, Math.min(255, (d[i * 4] - lo) * k)); d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = v; }
    ctx.putImageData(im, 0, 0);
    out._up = up;
    return out;
  }
  // Every word with a figure in it is read again by the digits-only reader, from the picture enlarged; the surer
  // reading is kept. A dropped or doubled digit ("11118.18" read as "1118.18") is put right here.
  async function recheckNumbers(cv, data) {
    var words = [];
    (data.lines || []).forEach(function (ln) { (ln.words || []).forEach(function (w) { if (/\d/.test(w.text || "") && (w.text || "").replace(/[^0-9]/g, "").length >= 2) words.push(w); }); });
    if (!words.length) return;
    words.sort(function (a, b) { return a.confidence - b.confidence; });
    words = words.slice(0, 80);
    var nw = await numOcr();
    for (var i = 0; i < words.length; i++) {
      var w = words[i], b = w.bbox, hgt = b.y1 - b.y0, pad = Math.round(hgt * 0.45);
      var x0 = Math.max(0, b.x0 - pad), y0 = Math.max(0, b.y0 - pad), x1 = Math.min(cv.width, b.x1 + pad), y1 = Math.min(cv.height, b.y1 + pad);
      if (x1 - x0 < 4 || y1 - y0 < 4) continue;
      var z = Math.max(1, Math.min(4, 48 / Math.max(1, hgt))), c = document.createElement("canvas");
      c.width = Math.round((x1 - x0) * z); c.height = Math.round((y1 - y0) * z);
      var cx = c.getContext("2d"); cx.fillStyle = "#fff"; cx.fillRect(0, 0, c.width, c.height); cx.imageSmoothingQuality = "high";
      cx.drawImage(cv, x0, y0, x1 - x0, y1 - y0, 0, 0, c.width, c.height);
      try {
        var r = await nw.recognize(c), t = (r.data.text || "").replace(/\s+/g, ""), conf = r.data.confidence || 0;
        var digitsOld = (w.text || "").replace(/[^0-9]/g, ""), digitsNew = t.replace(/[^0-9]/g, "");
        if (!digitsNew || digitsNew === digitsOld) continue;
        // keep the letters around the figure ("AED", "Dhs") as they were; put the surer figure in
        var dotsOld = ((w.text || "").match(/\./g) || []).length, dotsNew = (t.match(/\./g) || []).length;
        if (dotsOld && dotsNew !== dotsOld) continue;          // never lose or add a decimal point ("2.5" is not "25")
        if (conf >= Math.max(70, w.confidence + 5) && Math.abs(digitsNew.length - digitsOld.length) <= 2) {
          var m = (w.text || "").match(/^([^0-9]*)([0-9][0-9.,\-\/:%]*[0-9%]?)(.*)$/);
          w.text = m ? m[1] + t + m[3] : t; w.confidence = conf; w._rechecked = 1;
        }
      } catch (e) { /* the first reading stays */ }
    }
  }
  // what the recogniser saw, as lines and cells (a wide gap between words starts a new cell)
  function ocrLines(data, pn, scale, rules) {
    var out = [];
    rules = rules || [];
    var ruleBetween = function (a, b, y0, y1) {       // a column rule between two words of this line (page pixels)
      for (var i = 0; i < rules.length; i++) { var r = rules[i]; if (r[0] > a && r[0] < b && r[1] < y1 && r[2] > y0) return true; }
      return false;
    };
    (data.lines || []).forEach(function (ln) {
      var words = (ln.words || []).filter(function (w) { return w.text && w.text.trim() && w.confidence > 15; });
      if (!words.length) return;
      var h = (ln.bbox.y1 - ln.bbox.y0) / scale, cells = [], cur = null, end = -1;
      var cut = false;
      words.forEach(function (w) {
        var x0 = w.bbox.x0 / scale, x1 = w.bbox.x1 / scale, t = w.text.trim();
        if (/^[|\[\]{}~=_—–\\\/]+$/.test(t) && t !== "/") { cut = true; return; }   // a table rule read as a letter: a cell ends here
        t = t.replace(/^[|\[\]]+|[|\[\]]+$/g, ""); if (!t) { cut = true; return; }
        if (cur && !cut && rules.length && ruleBetween(end * scale, w.bbox.x0, w.bbox.y0, w.bbox.y1)) cut = true;
        if (cur && !cut && x0 - end < Math.max(6, h * 1.1)) cur.t += " " + t; else { cur = { t: t, x: Math.round(x0) }; cells.push(cur); }
        cut = false; end = x1; cur.e = Math.round(x1);
      });
      out.push({ p: pn, y: Math.round(ln.bbox.y0 / scale), h: Math.round(Math.min(h, 14) * 10) / 10, c: cells.map(function (c) { return c.t.trim(); }),
                 x: cells.map(function (c) { return c.x; }), xe: cells.map(function (c) { return c.e; }), t: cells.map(function (c) { return c.t.trim(); }).join("  "), ocr: 1 });
    });
    return out;
  }
  // Table rules confuse the recogniser (a ruled line read as "|", figures beside it lost): long straight dark
  // runs - far longer than any letter - are painted white first, so only the words are left.
  function deRule(cv) {
    var W = cv.width, H = cv.height, ctx = cv.getContext("2d"), im = ctx.getImageData(0, 0, W, H), d = im.data;
    var dark = new Uint8Array(W * H), i, x, y;
    for (i = 0; i < W * H; i++) dark[i] = (d[i * 4] * 0.3 + d[i * 4 + 1] * 0.59 + d[i * 4 + 2] * 0.11) < 150 ? 1 : 0;
    // how far each dark pixel runs across and down: a rule is long one way and thin the other
    // (a shaded cell or a filled box is long both ways, and is left alone with its text)
    var hl = new Uint16Array(W * H), vl = new Uint16Array(W * H), hmin = Math.max(60, Math.round(W * 0.06)), vmin = Math.max(70, Math.round(H * 0.035)), THIN = Math.max(6, Math.round(Math.max(W, H) * 0.005));
    for (y = 0; y < H; y++) { var st = -1; for (x = 0; x <= W; x++) { var on = x < W && dark[y * W + x]; if (on && st < 0) st = x; if (!on && st >= 0) { for (var k = st; k < x; k++) hl[y * W + k] = Math.min(65535, x - st); st = -1; } } }
    for (x = 0; x < W; x++) { var sv = -1; for (y = 0; y <= H; y++) { var on2 = y < H && dark[y * W + x]; if (on2 && sv < 0) sv = y; if (!on2 && sv >= 0) { for (var q = sv; q < y; q++) vl[q * W + x] = Math.min(65535, y - sv); sv = -1; } } }
    var kill = new Uint8Array(W * H), cols = [];
    for (i = 0; i < W * H; i++) if (dark[i] && ((hl[i] >= hmin && vl[i] <= THIN) || (vl[i] >= vmin && hl[i] <= THIN))) kill[i] = 1;
    for (x = 0; x < W; x++) { var vr = 0; for (y = 0; y <= H; y++) { if (y < H && dark[y * W + x] && vl[y * W + x] >= vmin && hl[y * W + x] <= THIN) vr++; else { if (vr >= vmin) cols.push([x, y - vr, y]); vr = 0; } } }
    cv._rules = cols;
    var n = 0;
    for (i = 0; i < W * H; i++) if (kill[i]) { d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = 255; n++; }
    if (n) ctx.putImageData(im, 0, 0);
    return cv;
  }
  function imageCanvas(url) {
    return new Promise(function (ok, no) {
      var img = new Image();
      img.onload = function () {
        var k = Math.min(1, 4000 / Math.max(img.naturalWidth, img.naturalHeight)), cv = document.createElement("canvas");
        cv.width = Math.round(img.naturalWidth * k); cv.height = Math.round(img.naturalHeight * k);
        cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height); ok({ cv: cv, k: k });
      };
      img.onerror = function () { no(new Error("That picture could not be opened.")); };
      img.src = url;
    });
  }
  async function ocrImage(src, pn, scale, say) {
    var w = await ocr(), up = 1;
    try { if (src && src.getContext) { src = prep(src); up = src._up || 1; } } catch (e) { /* leave it as it is */ }
    var clean = src;
    try { if (src && src.getContext) { var keep = document.createElement("canvas"); keep.width = src.width; keep.height = src.height; keep.getContext("2d").drawImage(src, 0, 0); clean = keep; src = deRule(src); } } catch (e) { /* leave it as it is */ }
    var r = await w.recognize(src);
    try { if (clean && clean.getContext && !root.__noRecheck) await recheckNumbers(clean, r.data); } catch (e) { /* the first reading stays */ }
    return ocrLines(r.data, pn, (scale || 1) * up, src && src._rules);
  }
  async function readAgreement(file, say) {
    say = say || function () {};
    var name = (file.name || "").toLowerCase(), data = new Uint8Array(await file.arrayBuffer());
    if (/\.(jpe?g|png|webp|bmp|tiff?)$/.test(name) || /^image\//.test(file.type || "")) {
      say("Recognising the text in the picture ... (the first time takes a little longer)");
      var url = URL.createObjectURL(file);
      try { var ic = await imageCanvas(url); var il = await ocrImage(ic.cv, 1, 2 * ic.k); } finally { URL.revokeObjectURL(url); }
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
