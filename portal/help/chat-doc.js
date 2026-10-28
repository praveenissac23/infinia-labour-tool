/* Infinia Chat - documents open in a preview, as on WhatsApp: a PDF shows its first page in the chat and opens
   page by page; Excel / CSV open as a table (sheet tabs), Word as its text, PowerPoint slide by slide, text files as text.
   Anything else says there is no preview and offers the download.
   CHAT_DOC.thumb(url, imgEl, onPages)   CHAT_DOC.open({ url, dl, name, size, who }) */
(function () {
  if (window.CHAT_DOC) return;
  const V = "/portal/vendor/";
  const loaded = {};
  const load = src => loaded[src] || (loaded[src] = new Promise((ok, no) => { const s = document.createElement("script"); s.src = V + src; s.onload = ok; s.onerror = () => { delete loaded[src]; no(new Error("Could not load the viewer")); }; document.head.appendChild(s); }));
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ext = n => ((n || "").split(".").pop() || "").toLowerCase();
  const kind = n => { const e = ext(n);
    if (e === "pdf") return "pdf"; if (["xlsx", "xlsm", "xls", "csv", "ods"].includes(e)) return "sheet";
    if (e === "docx") return "docx"; if (e === "pptx") return "pptx";
    if (["txt", "log", "md", "json", "xml", "html", "htm"].includes(e)) return "text"; return ""; };
  async function pdfjs() { await load("pdf-3.11.174.min.js"); pdfjsLib.GlobalWorkerOptions.workerSrc = V + "pdf.worker-3.11.174.min.js"; return pdfjsLib; }
  const bufs = new Map();          // one download per file, even when the thumb and the preview both want it
  const get = url => bufs.get(url) || (bufs.set(url, fetch(url).then(r => { if (!r.ok) throw new Error(r.status === 404 ? "This file is no longer kept - the sender has left the portal." : "Could not open the file"); return r.arrayBuffer(); }).catch(e => { bufs.delete(url); throw e; })), bufs.get(url));

  // ---- the first page of a PDF, in the chat -------------------------------------------------------------------
  const thumbs = new Map();
  function thumb(url, img, onPages) {
    let t = thumbs.get(url);
    if (!t) { t = (async () => { const L = await pdfjs(); const doc = await L.getDocument({ data: (await get(url)).slice(0), isEvalSupported: false }).promise;
      const pg = await doc.getPage(1), v0 = pg.getViewport({ scale: 1 }), k = 640 / v0.width, v = pg.getViewport({ scale: k });
      const c = document.createElement("canvas"); c.width = Math.round(v.width); c.height = Math.round(Math.min(v.height, v.width * 0.62));   // the top of page 1, WhatsApp-style
      const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
      await pg.render({ canvasContext: g, viewport: v }).promise; return { src: c.toDataURL("image/jpeg", 0.8), pages: doc.numPages }; })();
      thumbs.set(url, t); t.catch(() => thumbs.delete(url)); }
    t.then(r => { img.src = r.src; img.parentNode && img.parentNode.classList.add("ok"); onPages && onPages(r.pages); }).catch(() => { img.parentNode && img.parentNode.remove(); });
  }

  // ---- the preview ---------------------------------------------------------------------------------------------
  const css = document.createElement("style");
  css.textContent = `
  #wa-doc { position: fixed; inset: 0; z-index: 7000; background: #E9EDEF; display: none; flex-direction: column; font: 14px/1.45 "Segoe UI", -apple-system, sans-serif; color: #111B21; }
  #wa-doc.on { display: flex; }
  #wa-doc .hd { height: 60px; flex-shrink: 0; display: flex; align-items: center; gap: 12px; padding: 0 12px 0 16px; background: #fff; border-bottom: 1px solid #E1E4E7; box-shadow: 0 1px 3px rgba(11,20,26,.06); }
  #wa-doc .hd .di { width: 32px; height: 40px; border-radius: 4px; color: #fff; font: 700 9px/1 sans-serif; display: flex; align-items: flex-end; justify-content: center; padding-bottom: 6px; flex-shrink: 0; box-sizing: border-box; }
  #wa-doc .hd .nm { flex: 1; min-width: 0; } #wa-doc .hd .nm b { display: block; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } #wa-doc .hd .nm small { color: #667781; font-size: 12.5px; }
  #wa-doc .ib { width: 42px; height: 42px; border-radius: 50%; border: 0; background: transparent; color: #54656F; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; }
  #wa-doc .ib:hover { background: #F0F2F5; } #wa-doc .ib svg { width: 22px; height: 22px; }
  #wa-doc .bd { flex: 1; min-height: 0; overflow: auto; padding: 22px 16px 40px; }
  #wa-doc .pg { display: block; margin: 0 auto 14px; background: #fff; box-shadow: 0 2px 10px rgba(11,20,26,.14); max-width: 900px; width: 100%; }
  #wa-doc .pg canvas { display: block; width: 100%; }
  #wa-doc .pn { text-align: center; color: #667781; font-size: 12px; margin: -8px 0 14px; }
  #wa-doc .paper { background: #fff; max-width: 860px; margin: 0 auto; padding: 48px 56px; box-shadow: 0 2px 10px rgba(11,20,26,.14); box-sizing: border-box; }
  #wa-doc .paper p { margin: 0 0 10px; white-space: pre-wrap; } #wa-doc .paper h1, #wa-doc .paper h2, #wa-doc .paper h3 { margin: 16px 0 8px; }
  #wa-doc .paper table { border-collapse: collapse; margin: 8px 0 14px; width: 100%; } #wa-doc .paper td { border: 1px solid #CDD3D8; padding: 4px 7px; vertical-align: top; }
  #wa-doc pre { background: #fff; max-width: 1000px; margin: 0 auto; padding: 22px 26px; box-shadow: 0 2px 10px rgba(11,20,26,.14); white-space: pre-wrap; word-break: break-word; font: 13px/1.5 Consolas, Menlo, monospace; }
  #wa-doc .tabs { display: flex; gap: 4px; flex-wrap: wrap; max-width: 1200px; margin: 0 auto 10px; }
  #wa-doc .tabs button { border: 1px solid #D1D7DB; background: #fff; border-radius: 16px; padding: 5px 14px; cursor: pointer; font: inherit; font-size: 13px; color: #3B4A54; }
  #wa-doc .tabs button.on { background: #1D6F42; border-color: #1D6F42; color: #fff; }
  #wa-doc .sh { overflow: auto; max-width: 1200px; margin: 0 auto; background: #fff; box-shadow: 0 2px 10px rgba(11,20,26,.14); }
  #wa-doc .sh table { border-collapse: collapse; font-size: 13px; } #wa-doc .sh td { border: 1px solid #E1E4E7; padding: 4px 8px; white-space: nowrap; max-width: 380px; overflow: hidden; text-overflow: ellipsis; }
  #wa-doc .sh tr:first-child td { background: #F3F6F4; font-weight: 600; position: sticky; top: 0; }
  #wa-doc .sh td.rn { background: #F7F8FA; color: #8696A0; text-align: right; font-size: 11.5px; position: sticky; left: 0; }
  #wa-doc .slide { background: #fff; max-width: 860px; aspect-ratio: 16/9; margin: 0 auto 14px; padding: 34px 44px; box-sizing: border-box; box-shadow: 0 2px 10px rgba(11,20,26,.14); overflow: hidden; }
  #wa-doc .slide .no { color: #D24726; font-weight: 700; font-size: 12px; margin-bottom: 8px; } #wa-doc .slide p { margin: 0 0 6px; } #wa-doc .slide p:first-of-type { font-size: 22px; font-weight: 700; }
  #wa-doc .msg { text-align: center; color: #54656F; margin-top: 12vh; } #wa-doc .msg .big { width: 74px; height: 92px; border-radius: 8px; margin: 0 auto 18px; color: #fff; font: 700 15px/1 sans-serif; display: flex; align-items: flex-end; justify-content: center; padding-bottom: 14px; box-sizing: border-box; }
  #wa-doc .msg a { display: inline-block; margin-top: 16px; background: #C0392B; color: #fff; padding: 10px 22px; border-radius: 20px; text-decoration: none; font-weight: 600; }
  #wa-doc .spin { width: 34px; height: 34px; border: 3px solid #D1D7DB; border-top-color: #C0392B; border-radius: 50%; margin: 14vh auto 0; animation: wadspin .8s linear infinite; } @keyframes wadspin { to { transform: rotate(360deg); } }
  @media (max-width: 760px) { #wa-doc .bd { padding: 10px 6px 30px; } #wa-doc .paper { padding: 22px 18px; } #wa-doc .slide { padding: 16px 18px; } }`;
  document.head.appendChild(css);
  const IC = {
    dl: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19.1 17.2l-5.3-5.2 5.3-5.3-1.8-1.8-5.3 5.3-5.2-5.3-1.9 1.8 5.3 5.3-5.3 5.2 1.9 1.9 5.2-5.3 5.3 5.3z"/></svg>',
  };
  const COL = { PDF: "#E5252A", XLSX: "#1D6F42", XLSM: "#1D6F42", XLS: "#1D6F42", CSV: "#1D6F42", DOC: "#2B579A", DOCX: "#2B579A", PPT: "#D24726", PPTX: "#D24726", ZIP: "#7D7D7D", DWG: "#C2185B" };
  const el = document.createElement("div"); el.id = "wa-doc";
  el.innerHTML = `<div class="hd"><span class="di" data-di></span><span class="nm"><b data-nm></b><small data-sub></small></span>
    <a class="ib" data-dl title="Download" target="_blank" rel="noopener">${IC.dl}</a><button class="ib" data-x title="Close">${IC.x}</button></div><div class="bd" data-bd></div>`;
  document.body.appendChild(el);
  const $ = s => el.querySelector(s), bd = $("[data-bd]");
  let RUN = 0;
  function close() { RUN++; el.classList.remove("on"); bd.innerHTML = ""; }
  $("[data-x]").onclick = close;
  document.addEventListener("keydown", e => { if (e.key === "Escape" && el.classList.contains("on")) { e.stopPropagation(); close(); } }, true);

  async function open(o) {
    const run = ++RUN, E = ext(o.name).toUpperCase(), k = kind(o.name);
    $("[data-di]").textContent = E.slice(0, 4); $("[data-di]").style.background = COL[E] || "#8696A0";
    $("[data-nm]").textContent = o.name; $("[data-sub]").textContent = o.sub || ""; $("[data-dl]").href = o.dl;
    el.classList.add("on");
    const none = why => { bd.innerHTML = `<div class="msg"><div class="big" style="background:${COL[E] || "#8696A0"}">${esc(E.slice(0, 4) || "FILE")}</div>${esc(why)}<br><a href="${esc(o.dl)}" target="_blank" rel="noopener">Download</a></div>`; };
    if (!k) { none(`There is no preview for ${E ? E + " files" : "this file"} - download it to open it.`); return; }
    bd.innerHTML = `<div class="spin"></div>`;
    try {
      const buf = await get(o.url); if (run !== RUN) return;
      if (k === "pdf") await showPdf(buf, run);
      else if (k === "sheet") await showSheet(buf, E, run);
      else if (k === "docx") await showDocx(buf, run);
      else if (k === "pptx") await showPptx(buf, run);
      else { const t = new TextDecoder().decode(buf); bd.innerHTML = `<pre>${esc(t.length > 400000 ? t.slice(0, 400000) + "\n..." : t)}</pre>`; }
    } catch (e) { if (run === RUN) none((e && e.message) || "This file could not be shown."); }
  }

  async function showPdf(buf, run) {
    const L = await pdfjs(); const doc = await L.getDocument({ data: buf.slice(0), isEvalSupported: false }).promise; if (run !== RUN) return;
    $("[data-sub]").textContent = `${doc.numPages} page${doc.numPages === 1 ? "" : "s"}` + ($("[data-sub]").textContent ? " · " + $("[data-sub]").textContent : "");
    bd.innerHTML = ""; const n = Math.min(doc.numPages, 200);
    const io = new IntersectionObserver(es => es.forEach(async en => { if (!en.isIntersecting || en.target._done) return; en.target._done = true; io.unobserve(en.target);
      const pg = await doc.getPage(en.target._n); if (run !== RUN) return;
      const w = en.target.clientWidth || 800, v0 = pg.getViewport({ scale: 1 }), dpr = Math.min(window.devicePixelRatio || 1, 2), v = pg.getViewport({ scale: w / v0.width * dpr });
      const c = document.createElement("canvas"); c.width = Math.round(v.width); c.height = Math.round(v.height);
      await pg.render({ canvasContext: c.getContext("2d"), viewport: v }).promise; en.target.innerHTML = ""; en.target.style.aspectRatio = ""; en.target.appendChild(c); }), { root: bd, rootMargin: "800px" });
    for (let i = 1; i <= n; i++) {
      const pg = await doc.getPage(i); const v = pg.getViewport({ scale: 1 }); if (run !== RUN) return;
      const box = document.createElement("div"); box.className = "pg"; box.style.aspectRatio = `${v.width} / ${v.height}`; box._n = i; bd.appendChild(box);
      if (doc.numPages > 1) { const t = document.createElement("div"); t.className = "pn"; t.textContent = `Page ${i} of ${doc.numPages}`; bd.appendChild(t); }
      io.observe(box);
    }
  }
  async function showSheet(buf, E, run) {
    await load("xlsx-0.18.5.core.min.js"); if (run !== RUN) return;
    const wb = E === "CSV" ? XLSX.read(new TextDecoder().decode(buf), { type: "string" }) : XLSX.read(new Uint8Array(buf), { type: "array", cellDates: true });
    const names = wb.SheetNames;
    const draw = i => {
      const ws = wb.Sheets[names[i]]; const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: false, blankrows: true, defval: "" }).slice(0, 3000);
      while (rows.length && rows[rows.length - 1].every(c => c === "")) rows.pop();
      const w = Math.min(60, Math.max(1, ...rows.map(r => { let n = r.length; while (n && r[n - 1] === "") n--; return n; })));
      bd.innerHTML = (names.length > 1 ? `<div class="tabs">${names.map((s, j) => `<button data-t="${j}" class="${j === i ? "on" : ""}">${esc(s)}</button>`).join("")}</div>` : "")
        + `<div class="sh">${rows.length ? `<table>${rows.map((r, j) => `<tr><td class="rn">${j + 1}</td>${Array.from({ length: w }, (_, c) => `<td title="${esc(r[c])}">${esc(r[c])}</td>`).join("")}</tr>`).join("")}</table>` : `<div style="padding:30px;color:#667781">This sheet is empty.</div>`}</div>`;
      bd.querySelectorAll("[data-t]").forEach(b => b.onclick = () => draw(+b.dataset.t));
    };
    draw(0);
  }
  async function zip(buf) { await load("jszip-3.10.1.min.js"); return JSZip.loadAsync(buf); }
  const X = s => new DOMParser().parseFromString(s, "application/xml");
  async function showDocx(buf, run) {
    const z = await zip(buf); const f = z.file("word/document.xml"); if (!f) throw new Error("This Word file could not be read.");
    const doc = X(await f.async("string")); if (run !== RUN) return;
    const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    const runs = p => [...p.getElementsByTagNameNS(W, "r")].map(r => { const t = [...r.childNodes].map(n => n.localName === "t" ? n.textContent : n.localName === "tab" ? "\t" : n.localName === "br" ? "\n" : "").join("");
      const pr = r.getElementsByTagNameNS(W, "rPr")[0]; const b = pr && pr.getElementsByTagNameNS(W, "b")[0] && pr.getElementsByTagNameNS(W, "b")[0].getAttributeNS(W, "val") !== "0";
      const i = pr && pr.getElementsByTagNameNS(W, "i")[0]; const u = pr && pr.getElementsByTagNameNS(W, "u")[0];
      let h = esc(t); if (b) h = `<b>${h}</b>`; if (i) h = `<i>${h}</i>`; if (u) h = `<u>${h}</u>`; return h; }).join("");
    const para = p => { const st = p.getElementsByTagNameNS(W, "pStyle")[0], s = st ? st.getAttributeNS(W, "val") || "" : ""; const h = runs(p);
      const m = /heading\s*(\d)|^title$/i.exec(s); if (m) { const lv = Math.min(3, +(m[1] || 1)); return `<h${lv}>${h}</h${lv}>`; }
      const li = p.getElementsByTagNameNS(W, "numPr")[0]; return `<p>${li ? "&bull; " : ""}${h || "&nbsp;"}</p>`; };
    const body = doc.getElementsByTagNameNS(W, "body")[0]; let out = "";
    for (const n of body.childNodes) {
      if (n.localName === "p") out += para(n);
      else if (n.localName === "tbl") out += `<table>${[...n.childNodes].filter(r => r.localName === "tr").map(r => `<tr>${[...r.childNodes].filter(c => c.localName === "tc").map(c => `<td>${[...c.getElementsByTagNameNS(W, "p")].map(runs).join("<br>")}</td>`).join("")}</tr>`).join("")}</table>`;
    }
    bd.innerHTML = `<div class="paper">${out || "<p>This document has no text.</p>"}</div>`;
  }
  async function showPptx(buf, run) {
    const z = await zip(buf); const names = Object.keys(z.files).filter(n => /^ppt\/slides\/slide\d+\.xml$/.test(n)).sort((a, b) => +a.match(/\d+/)[0] - +b.match(/\d+/)[0]);
    const A = "http://schemas.openxmlformats.org/drawingml/2006/main"; let out = "";
    for (let i = 0; i < names.length; i++) { const d = X(await z.file(names[i]).async("string")); if (run !== RUN) return;
      const ps = [...d.getElementsByTagNameNS(A, "p")].map(p => [...p.getElementsByTagNameNS(A, "t")].map(t => t.textContent).join("")).filter(s => s.trim());
      out += `<div class="slide"><div class="no">Slide ${i + 1}</div>${ps.map(s => `<p>${esc(s)}</p>`).join("") || "<p style='color:#8696A0'>(pictures only)</p>"}</div>`; }
    $("[data-sub]").textContent = `${names.length} slide${names.length === 1 ? "" : "s"}` + ($("[data-sub]").textContent ? " · " + $("[data-sub]").textContent : "");
    bd.innerHTML = out || `<div class="msg">This presentation has no slides.</div>`;
  }
  window.CHAT_DOC = { open, close, thumb, kind };
})();
