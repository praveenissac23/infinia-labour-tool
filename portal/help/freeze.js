/* Frozen heading rows, everywhere in the app.
   When a long table scrolls its heading row out of sight, a copy of that row stays pinned at the top
   (under the page's own sticky bar, if it has one) until the table has gone by - in the app screens,
   the Estimation pages, the pop-up forms and every Preview page. Column widths and sideways scrolling
   follow the real table; clicking a pinned heading clicks the real one (so sorting still works).
   Tables whose heading already stays put (a box that scrolls on its own) are left alone. */
(function () {
  "use strict";
  if (window.__freezeHeads) return;
  window.__freezeHeads = true;
  var MIN_ROWS = 6;
  var pins = new Map();             // table -> { box, clone }
  var BARS = ".pvbar, .bar, .topbar, .top-bar, .app-top, .pg-top, #topbar, .mhead, header";

  function visible(el) { return !!(el && el.getClientRects().length && getComputedStyle(el).visibility !== "hidden"); }
  function scroller(el) {
    // the nearest box that really scrolls up and down; null = the page itself
    for (var p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      var oy = getComputedStyle(p).overflowY;
      if ((oy === "auto" || oy === "scroll" || oy === "overlay") && p.scrollHeight > p.clientHeight + 2) return p;
    }
    return null;
  }
  function pageTop() {
    // the bottom of whatever bar stays fixed at the top of the window
    var top = 0;
    document.querySelectorAll(BARS).forEach(function (b) {
      if (!visible(b)) return;
      var cs = getComputedStyle(b);
      if (cs.position !== "fixed" && cs.position !== "sticky") return;
      var r = b.getBoundingClientRect();
      if (r.top <= 2 && r.bottom > 0 && r.height < 220 && !b.closest(".modal, #modal, #drawer, #big, .mbox, .dbox")) top = Math.max(top, r.bottom);
    });
    return top;
  }
  function clipOf(table, sc) {
    // the part of the window the table can be seen in, sideways and from the top
    var left = 0, right = window.innerWidth, top = sc ? 0 : pageTop();
    for (var p = table.parentElement; p && p !== document.body; p = p.parentElement) {
      var cs = getComputedStyle(p);
      if (cs.overflowX !== "visible" || cs.overflowY !== "visible") {
        var r = p.getBoundingClientRect();
        left = Math.max(left, r.left); right = Math.min(right, r.right);
        if (p === sc) top = Math.max(top, r.top);
      }
    }
    if (sc) {
      // inside a modal / drawer: its own fixed heading bar stays above the table
      var head = sc.querySelector(":scope > .mhead, :scope > .dhead, :scope > header");
      if (head && visible(head)) top = Math.max(top, head.getBoundingClientRect().bottom);
    }
    return { left: left, right: right, top: top };
  }
  function build(table) {
    var thead = table.tHead;
    var box = document.createElement("div");
    box.className = "freeze-head";
    box.setAttribute("aria-hidden", "true");
    box.style.cssText = "position:fixed;z-index:900;overflow:hidden;pointer-events:auto;display:none;box-shadow:0 2px 6px rgba(0,0,0,.12);";
    var clone = table.cloneNode(false);
    clone.removeAttribute("id");
    clone.style.margin = "0";
    clone.style.tableLayout = "fixed";
    var cg = table.querySelector(":scope > colgroup");
    if (cg) clone.appendChild(cg.cloneNode(true));
    var th = thead.cloneNode(true);
    th.querySelectorAll("[id]").forEach(function (e) { e.removeAttribute("id"); });
    // the look is copied from the real cells, so a heading styled through its screen still looks the same
    var PROPS = ["background-color", "background-image", "color", "font-family", "font-size", "font-weight", "font-style", "letter-spacing",
                 "text-transform", "text-align", "vertical-align", "padding-top", "padding-right", "padding-bottom", "padding-left",
                 "border-top", "border-right", "border-bottom", "border-left", "line-height", "white-space", "height"];
    var realCells = thead.querySelectorAll("th, td"), cells = th.querySelectorAll("th, td");
    cells.forEach(function (c, i) {
      var cs = realCells[i] && getComputedStyle(realCells[i]);
      if (cs) PROPS.forEach(function (k) { c.style.setProperty(k, cs.getPropertyValue(k)); });
      c.style.position = "static"; c.removeAttribute("draggable");
      [].slice.call(c.attributes).forEach(function (at) { if (/^data-/.test(at.name) && at.name !== "data-tip") c.removeAttribute(at.name); });
    });
    var bg = getComputedStyle(realCells[0] || thead).backgroundColor;
    box.style.background = (bg && bg !== "rgba(0, 0, 0, 0)") ? bg : "#fff";
    clone.appendChild(th);
    box.appendChild(clone);
    document.body.appendChild(box);
    // a click on a pinned heading is a click on the real one
    box.addEventListener("click", function (e) {
      var cell = e.target.closest("th, td"); if (!cell) return;
      var row = cell.parentElement, ri = [].indexOf.call(row.parentElement.rows, row), ci = [].indexOf.call(row.cells, cell);
      var real = thead.rows[ri] && thead.rows[ri].cells[ci];
      if (!real) return;
      var hit = e.target.closest(".help-i") ? real.querySelector(".help-i") : real;
      if (hit) { e.preventDefault(); e.stopPropagation(); hit.click(); setTimeout(function () { refresh(table, true); }, 30); }
    });
    return { box: box, clone: clone, sig: "" };
  }
  function refresh(table, force) {
    var p = pins.get(table); if (!p) return;
    var thead = table.tHead;
    var sig = thead.innerHTML.length + ":" + thead.textContent;
    if (force || sig !== p.sig) {                       // the real heading changed (sort arrow, columns moved)
      p.box.remove(); pins.delete(table);
      p = build(table); p.sig = sig; pins.set(table, p);
    }
    var real = thead.rows, cl = p.clone.tHead.rows;
    for (var r = 0; r < real.length && r < cl.length; r++)
      for (var c = 0; c < real[r].cells.length && c < cl[r].cells.length; c++) {
        var w = real[r].cells[c].getBoundingClientRect().width;
        cl[r].cells[c].style.width = w + "px"; cl[r].cells[c].style.minWidth = w + "px"; cl[r].cells[c].style.maxWidth = w + "px";
        cl[r].cells[c].style.boxSizing = "border-box";
      }
    p.clone.style.width = table.getBoundingClientRect().width + "px";
  }
  function place() {
    var seen = new Set();
    document.querySelectorAll("table").forEach(function (t) {
      if (!t.tHead || !t.tBodies.length || t.closest(".freeze-head") || !visible(t)) return;
      if (t.tBodies[0].rows.length < MIN_ROWS || t.dataset.nofreeze !== undefined) return;
      seen.add(t);
      var sc = scroller(t);
      var clip = clipOf(t, sc);
      var tr = t.getBoundingClientRect(), hr = t.tHead.getBoundingClientRect();
      var show = hr.top < clip.top - 1 && tr.bottom > clip.top + hr.height + 8 && clip.right > clip.left;
      if (show) {
        // only for the table actually on top - never over a pop-up or drawer opened above it
        var x = Math.max(clip.left, tr.left) + 6, y = clip.top + hr.height + 4;
        var under = document.elementFromPoint(Math.min(x, window.innerWidth - 2), Math.min(y, window.innerHeight - 2));
        if (under && !t.contains(under) && !under.closest(".freeze-head")) show = false;
      }
      var p = pins.get(t);
      if (!show) { if (p) p.box.style.display = "none"; return; }
      if (!p) { p = build(t); pins.set(t, p); refresh(t, false); }
      else refresh(t, false);
      p.box.style.display = "block";
      p.box.style.top = clip.top + "px";
      p.box.style.left = clip.left + "px";
      p.box.style.width = (clip.right - clip.left) + "px";
      p.box.style.height = hr.height + "px";
      p.clone.style.transform = "translateX(" + (tr.left - clip.left) + "px)";
    });
    pins.forEach(function (p, t) { if (!seen.has(t) || !document.contains(t)) { p.box.remove(); pins.delete(t); } });
  }
  var queued = false;
  function soon() { if (queued) return; queued = true; requestAnimationFrame(function () { queued = false; try { place(); } catch (e) {} }); }
  window.addEventListener("scroll", soon, true);
  window.addEventListener("resize", soon);
  document.addEventListener("click", function () { setTimeout(soon, 60); }, true);
  new MutationObserver(function () { soon(); }).observe(document.documentElement, { childList: true, subtree: true });
  window.FREEZE_HEADS_REFRESH = soon;
  soon();
})();
