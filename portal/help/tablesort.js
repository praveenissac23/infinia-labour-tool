// ---- Every table: click a heading to sort, drag a heading to move the
// column. The column order is remembered per table on this computer; the
// sort lasts until the page is left. Totals, group and "nothing yet" rows
// stay where they are. Headings that already sort themselves, and the
// tick-box column, are left alone.
(function () {
  if (window.__tableSort) return; window.__tableSort = true;
  const st = document.createElement("style");
  st.textContent = `th.tx-s { cursor: pointer; user-select: none; } th.tx-s:hover { color: #2B2622; }
  th.tx-d { cursor: grab; } th.tx-drag { opacity: .45; } th.tx-over { box-shadow: inset 3px 0 0 #C0392B; }
  th .tx-a { font-size: .8em; margin-left: 4px; color: #C0392B; }`;
  (document.head || document.documentElement).appendChild(st);
  const KEY = "infinia_cols:";
  const txt = td => { if (!td) return ""; const s = td.getAttribute("data-s"); if (s !== null) return s;
    const f = td.querySelector("input:not([type=checkbox]),select,textarea"); return (f ? f.value : td.textContent).trim(); };
  const MON = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
  function key(v) {
    let t = String(v).replace(/AED|,/gi, "").replace(/\s+/g, " ").trim();
    const neg = /^\(.*\)$/.test(t) || /^-/.test(t);
    const n = t.replace(/[()%+\-]/g, "").trim();
    if (n !== "" && !isNaN(n)) return { n: (neg ? -1 : 1) * parseFloat(n) };
    let m = t.match(/^(\d{1,2})[- ]([A-Za-z]{3})[a-z]*[- ,]*(\d{2,4})?/);
    if (m && MON[m[2].toLowerCase()] !== undefined) { const y = m[3] ? (+m[3] < 100 ? 2000 + +m[3] : +m[3]) : new Date().getFullYear(); return { n: new Date(y, MON[m[2].toLowerCase()], +m[1]).getTime() }; }
    m = t.match(/^(\d{4})-(\d{2})-(\d{2})/); if (m) return { n: new Date(+m[1], +m[2] - 1, +m[3]).getTime() };
    m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?: (\d{1,2}):(\d{2}))?/); if (m) return { n: new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0)).getTime() };   // 30/10/2026, 30/10/2026 14:05
    m = t.match(/^(?:(\d+)\s*y)?\s*(?:(\d+)\s*m)?$/i);                          // service "10 y 6 m", "10 m": in months
    if (m && (m[1] || m[2])) return { n: (+(m[1] || 0)) * 12 + (+(m[2] || 0)) };
    m = t.match(/^(\d{1,2})-\d{1,2} ([A-Za-z]{3})[a-z]* (\d{4})/);          // a date range "5-18 Oct 2026": by its first day
    if (m && MON[m[2].toLowerCase()] !== undefined) return { n: new Date(+m[3], MON[m[2].toLowerCase()], +m[1]).getTime() };
    m = t.match(/^(-?\d+(?:\.\d+)?)(?=\s*[^\d.\/:-]|$)/);                    // "1,500 pcs", "640 hrs", "903.00 ◷": by the number
    if (m) return { n: parseFloat(m[1]) };
    return { s: t.toLowerCase() };
  }
  const cmp = (a, b) => a.n !== undefined && b.n !== undefined ? a.n - b.n : a.n !== undefined ? -1 : b.n !== undefined ? 1 : a.s.localeCompare(b.s, undefined, { numeric: true });
  const fixed = tr => /(^|\s)(bf|tot|total|grp|group|sub|empty|edit-row|rep-group)(\s|$)/i.test(tr.className) || [...tr.cells].some(c => c.colSpan > 1)
    || /^(total|grand total|sub ?total|balance brought forward)/i.test((tr.cells[0] || {}).textContent || "") || /^(total|balance brought forward)/i.test((tr.cells[1] || {}).textContent || "");
  const headRow = t => t.tHead && t.tHead.rows.length ? t.tHead.rows[t.tHead.rows.length - 1] : null;
  const label = th => (th.textContent || "").replace(/[▲▼]/g, "").trim();
  function sigOf(t) { const h = headRow(t); return h ? [...h.cells].map(label).join("|") : ""; }
  function storeKey(t) { const scr = t.closest(".screen"); return KEY + (t.id || (scr ? scr.id : "") + "/" + (t.className || "").split(" ")[0]) + "/" + [...headRow(t).cells].map(label).filter(Boolean).sort().join("|").slice(0, 160); }
  // A totals row that spans a few columns ("TOTAL" over Date - Site) is
  // split into single cells, the words kept in the first, so it can move
  // with the columns.
  function normalize(t) {
    const n = headRow(t).cells.length;
    for (const sec of [...t.tBodies, t.tFoot].filter(Boolean))
      for (const tr of sec.rows) {
        const cells = [...tr.cells]; if (cells.length < 2) continue;
        if (cells.reduce((a, c) => a + c.colSpan, 0) !== n || !cells.some(c => c.colSpan > 1)) continue;
        cells.forEach(c => { const k = c.colSpan; if (k < 2) return; c.colSpan = 1; c.style.whiteSpace = "nowrap";
          for (let j = 1; j < k; j++) { const e = document.createElement(c.tagName); e.className = c.className; c.after(e); } });
      }
  }
  function canMove(t) {
    if (t.hasAttribute("data-nomove") || t.closest(".lc-compact")) return false;   // widths set per column position
    const n = headRow(t).cells.length;
    if (t.tHead.rows.length > 1) return false;
    for (const sec of [...t.tBodies, t.tFoot].filter(Boolean))
      for (const tr of sec.rows) { if (tr.cells.length === 1 && tr.cells[0].colSpan >= n - 1) continue; if (tr.cells.length !== n) return false; }
    return true;
  }
  function moveCol(t, from, to) {
    for (const sec of [t.tHead, ...t.tBodies, t.tFoot].filter(Boolean))
      for (const tr of sec.rows) { if (tr.cells.length === 1) continue; const c = tr.cells[from], ref = tr.cells[to];
        if (!c || !ref) continue; if (from < to) ref.after(c); else ref.before(c); }
  }
  // Each heading remembers where its column was drawn (data-txi); a row the
  // screen has just drawn is in that natural order and is put into the
  // order the headings show now. Rows already arranged are marked.
  function arrange(t) {
    const h = headRow(t), n = h.cells.length;
    [...h.cells].forEach((c, i) => { if (c.dataset.txi === undefined) c.dataset.txi = i; });
    const perm = [...h.cells].map(c => +c.dataset.txi);
    const natural = perm.every((v, i) => v === i);
    for (const sec of [...t.tBodies, t.tFoot].filter(Boolean))
      for (const tr of sec.rows) {
        if (tr.__txo || tr.cells.length !== n) continue;
        tr.__txo = true;
        if (natural) continue;
        const cells = [...tr.cells]; perm.forEach(k => tr.appendChild(cells[k]));
      }
  }
  function applyOrder(t) {
    if (t.hasAttribute("data-nomove") || t.closest(".lc-compact")) return;
    t.__busy = true; normalize(t);
    if (!canMove(t)) { t.__busy = false; return; }
    const h = headRow(t);
    [...h.cells].forEach((c, i) => { if (c.dataset.txi === undefined) c.dataset.txi = i; });
    let want; try { want = JSON.parse(localStorage.getItem(storeKey(t)) || "null"); } catch (e) { want = null; }
    if (want) {
      // headings into the remembered order (the rows follow in arrange)
      const cells = [...h.cells], used = new Set(), order = [];
      want.forEach(lab => { const c = cells.find(x => !used.has(x) && label(x) === lab); if (c) { used.add(c); order.push(c); } });
      cells.forEach(c => { if (!used.has(c)) order.push(c); });
      if (order.some((c, i) => c !== cells[i])) {
        // rows already arranged to the old heading order go back to natural first
        const old = cells.map(c => +c.dataset.txi);
        for (const sec of [...t.tBodies, t.tFoot].filter(Boolean))
          for (const tr of sec.rows) if (tr.__txo && tr.cells.length === cells.length) { const cs = [...tr.cells]; const nat = []; old.forEach((k, pos) => nat[k] = cs[pos]); nat.forEach(c => tr.appendChild(c)); tr.__txo = false; }
        order.forEach(c => h.appendChild(c));
      }
    }
    arrange(t);
    t.__busy = false;
  }
  function saveOrder(t) { try { localStorage.setItem(storeKey(t), JSON.stringify([...headRow(t).cells].map(label))); } catch (e) {} }
  function applySort(t) {
    const st = t.__sort; if (!st) return;
    const h = headRow(t); const ci = [...h.cells].findIndex(c => label(c) === st.lab); if (ci < 0) return;
    t.__busy = true;
    // A row's own detail line under it (a request's progress, a visa's payments - one wide cell, no group or
    // total class) moves with its row; group headings and totals stay where they are.
    const detail = (tr, prevData) => prevData && [...tr.cells].some(c => c.colSpan > 1) && (/(^|\s)[a-z]*-?detail(\s|$)/i.test(tr.className)
      || (!tr.className.trim() && !/^(total|grand total|sub ?total|balance brought forward)/i.test((tr.cells[0] || {}).textContent.trim())));
    [...t.tBodies].forEach(b => { const rows = [...b.rows], out = []; let seg = [];
      // an empty box ("", "-") goes to the bottom whichever way the list is sorted
      const blank = v => /^[-–—]?$/.test(v.replace(/[◷✓✔⏱]/g, "").trim());
      const flush = () => { seg.sort((u1, u2) => { const v1 = txt(u1[0].cells[ci]), v2 = txt(u2[0].cells[ci]);
        if (blank(v1) !== blank(v2)) return blank(v1) ? 1 : -1;
        const c = cmp(key(v1), key(v2)); return st.dir === "asc" ? c : -c; }); seg.forEach(u => out.push(...u)); seg = []; };
      rows.forEach(r => {
        if (detail(r, seg.length > 0)) { seg[seg.length - 1].push(r); return; }
        if (fixed(r)) { flush(); out.push(r); } else seg.push([r]);
      }); flush();
      out.forEach(r => b.appendChild(r)); });
    [...h.cells].forEach(c => { const a = c.querySelector(".tx-a"); if (a) a.textContent = label(c) === st.lab ? (st.dir === "asc" ? "▲" : "▼") : ""; });
    t.__busy = false;
  }
  function wire(t) {
    const h = headRow(t); if (!h || h.cells.length < 2) return;
    if (t.closest(".zx-modal,.cp-m,.pe-m,.bs-m") || t.hasAttribute("data-nosort")) return;
    const sig = sigOf(t);
    if (t.__sig === sig) return;           // headings unchanged since last wired
    t.__sig = sig;
    applyOrder(t);
    const move = canMove(t);
    [...headRow(t).cells].forEach((th, i) => {
      if (th.__tx) return; th.__tx = true;
      const plain = !th.onclick && !th.hasAttribute("onclick") && !th.querySelector("input,select,button") && label(th) && !th.hasAttribute("data-col");
      if (plain) {
        th.classList.add("tx-s"); if (!th.querySelector(".tx-a")) { const a = document.createElement("span"); a.className = "tx-a"; th.appendChild(a); }
        th.title = th.title || "Click to sort" + (move ? " - drag to move the column" : "");
        th.addEventListener("click", () => { if (t.__dragged) return; const lab = label(th);
          t.__sort = { lab, dir: t.__sort && t.__sort.lab === lab && t.__sort.dir === "asc" ? "desc" : "asc" }; applySort(t); });
      }
      if (move && label(th)) {
        th.draggable = true; th.classList.add("tx-d");
        th.addEventListener("dragstart", e => { t.__from = [...headRow(t).cells].indexOf(th); t.__dragged = true; e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", "col"); } catch (x) {} th.classList.add("tx-drag"); });
        th.addEventListener("dragend", () => { th.classList.remove("tx-drag"); setTimeout(() => { t.__dragged = false; }, 50); headRow(t) && [...headRow(t).cells].forEach(c => c.classList.remove("tx-over")); });
        th.addEventListener("dragover", e => { if (t.__from === undefined) return; e.preventDefault(); th.classList.add("tx-over"); });
        th.addEventListener("dragleave", () => th.classList.remove("tx-over"));
        th.addEventListener("drop", e => { e.preventDefault(); th.classList.remove("tx-over"); const to = [...headRow(t).cells].indexOf(th);
          if (t.__from !== undefined && to !== t.__from) { t.__busy = true; arrange(t); moveCol(t, t.__from, to); t.__busy = false; saveOrder(t); t.__sig = sigOf(t); }
          t.__from = undefined; });
      }
    });
    if (!t.__obs) {
      // Redrawn by its screen: put the remembered order and the sort back.
      t.__obs = new MutationObserver(() => { if (t.__busy) return; cancelAnimationFrame(t.__raf); t.__raf = requestAnimationFrame(() => {
        if (!headRow(t)) return; t.__sig = null; wire(t); t.__busy = true; arrange(t); t.__busy = false; applySort(t); }); });
      t.__obs.observe(t, { childList: true, subtree: true });
    }
  }
  // The app: the tables of the open screen. Estimation and Trello (in their frames): every table, except
  // Trello's own table view (it sorts itself) and the grouped project list.
  const SEL = document.querySelector(".screen") ? ".screen.active table" : "table:not(.tv):not(.pp-table)";
  function scan() { document.querySelectorAll(SEL).forEach(t => { if (t.tHead && !t.querySelector("th[data-dsort], th[data-s]")) wire(t); }); }
  let pend = false;
  const kick = () => { if (pend) return; pend = true; requestAnimationFrame(() => { pend = false; scan(); }); };
  const start = () => { scan(); new MutationObserver(m => { if (m.some(x => [...x.addedNodes].some(n => n.nodeType === 1 && (n.tagName === "TABLE" || n.tagName === "THEAD" || (n.querySelector && n.querySelector("table")))) || x.attributeName === "class")) kick(); })
    .observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] }); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
