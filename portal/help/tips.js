/* The small (i) beside a box, everywhere in the app.
   Where it comes from, in order:
     1. window.HELP_TIPS (guides.js): selector -> text, written for each box;
     2. any box with a title="..." - the title becomes its (i), so a new
        field gets one simply by being given a title;
     3. data-tip="..." on a box, the same.
   The (i) sits in the box's own label so boxes stay in line. Runs again
   every second and a half, so boxes drawn later get theirs too. */
(function () {
  "use strict";
  function put(el, text) {
    if (!el || el.dataset.helpI || !text) return;
    el.dataset.helpI = "1";
    const i = document.createElement("span");
    i.className = "help-i"; i.tabIndex = 0; i.textContent = "i"; i.dataset.tip = text;
    const lab = el.closest("label"), cap = lab && lab.querySelector(":scope > span");
    const field = !cap && el.closest(".field"), flab = field && field.querySelector(":scope > label");
    if (cap && !cap.contains(el)) { i.classList.add("in-label"); cap.appendChild(i); }
    else if (flab) { i.classList.add("in-label"); flab.appendChild(i); }
    else el.insertAdjacentElement("afterend", i);
  }
  // ---- An (i) on every column heading and form label that has a note in heads.js -------------
  // window.HEAD_TIPS: "heading" -> note, or "<where>|heading" when the same word means something
  // else on one screen. <where> is the screen (screen-store -> "store"), or what the page says it
  // is showing (body data-ctx, set by the Estimation pages: "est.client.boq", "est.schedule" ...).
  // Sort arrows and a figure in brackets ("Retention to date (5%)") are not part of the name.
  const norm = t => String(t || "").replace(/[\u25B2\u25BC\u2191\u2193]/g, "").replace(/\([^)]*\d[^)]*\)/g, "")
    .replace(/\s+/g, " ").trim().replace(/[*:]+$/, "").trim().toLowerCase();
  function whereOf(el) {
    const scr = el.closest && el.closest('[id^="screen-"]');
    if (scr) return scr.id.slice(7);
    const big = el.closest && el.closest("[data-ctx]");
    if (big) return big.dataset.ctx;
    const pg = (location.pathname.split("/").pop() || "").replace(/\.html$/, "");
    return document.body.dataset.ctx || (pg === "boards" ? "est.boards" : pg);
  }
  function headTip(el, words) {
    const H = window.HEAD_TIPS; if (!H) return "";
    const k = norm(words); if (!k || k === "#") return "";
    const w = whereOf(el);
    if (w) {
      const parts = w.split(".");
      for (let n = parts.length; n > 0; n--) { const t = H[parts.slice(0, n).join(".") + "|" + k]; if (t) return t; }
    }
    return H[k] || "";
  }
  function heads(root) {
    if (!window.HEAD_TIPS) return;
    root.querySelectorAll("th").forEach(th => {
      if (th.dataset.helpI || th.querySelector(".help-i")) return;
      const lbl = th.querySelector(".lbl, .hw") || th;
      const t = headTip(th, lbl.textContent);
      th.dataset.helpI = "1";
      if (!t) return;
      const i = document.createElement("span");
      i.className = "help-i in-label in-head"; i.tabIndex = 0; i.textContent = "i"; i.dataset.tip = t;
      lbl.appendChild(i);
    });
    root.querySelectorAll(".frm .f > label, .field > label, label > span:first-child").forEach(lab => {
      if (lab.dataset.helpI || lab.querySelector(".help-i")) return;
      const box = lab.parentElement;
      if (box && box.querySelector(".help-i")) { lab.dataset.helpI = "1"; return; }
      const t = headTip(lab, lab.textContent);
      lab.dataset.helpI = "1";
      if (!t) return;
      const i = document.createElement("span");
      i.className = "help-i in-label"; i.tabIndex = 0; i.textContent = "i"; i.dataset.tip = t;
      lab.appendChild(i);
    });
  }
  function run(root) {
    const t = window.HELP_TIPS || {};
    for (const sel in t) { try { root.querySelectorAll(sel).forEach(el => put(el, t[sel])); } catch (e) {} }
    root.querySelectorAll("input[title], select[title], textarea[title], input[data-tip], select[data-tip], textarea[data-tip]").forEach(el => {
      if (el.dataset.helpI || el.type === "hidden" || el.type === "checkbox" || el.type === "search") return;
      if (!el.closest("label, .field")) return;
      const text = el.dataset.tip || el.getAttribute("title");
      el.removeAttribute("title");              // one explanation, not two
      put(el, text);
    });
    try { heads(root); } catch (e) {}      // after the box notes, so a box never gets two
  }
  // One shared note box, placed under (or above) the (i) and kept inside
  // the window on every side.
  let box = null, shownAt = 0;
  const touch = matchMedia("(hover: none)").matches;
  function show(i) {
    if (!box) { box = document.createElement("div"); box.className = "help-tipbox"; document.body.appendChild(box); }
    box.textContent = i.dataset.tip || ""; box.classList.add("on"); shownAt = Date.now();
    const r = i.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight, pad = 8;
    let left = r.left - 14;                      // starts at the (i), reads to the right
    left = Math.max(pad, Math.min(left, innerWidth - w - pad));
    let top = r.bottom + 6;
    if (top + h > innerHeight - pad) top = Math.max(pad, r.top - 6 - h);
    box.style.left = left + "px"; box.style.top = top + "px";
  }
  function hide() { if (box) box.classList.remove("on"); }
  // A tap scrolls or moves focus a little as it lands; that must not close
  // the note it just opened.
  const softHide = () => { if (Date.now() - shownAt > 500) hide(); };
  document.addEventListener("mouseover", e => { const i = e.target.closest && e.target.closest(".help-i"); if (i) show(i); });
  document.addEventListener("mouseout", e => { if (!touch && e.target.closest && e.target.closest(".help-i")) hide(); });
  document.addEventListener("focusin", e => { if (e.target.classList && e.target.classList.contains("help-i")) show(e.target); });
  document.addEventListener("focusout", e => { if (e.target.classList && e.target.classList.contains("help-i")) softHide(); });
  document.addEventListener("click", e => { const i = e.target.closest && e.target.closest(".help-i"); if (i) { e.preventDefault(); e.stopPropagation(); show(i); } else hide(); }, true);
  window.addEventListener("scroll", softHide, true);
  // ---- A small x inside a filled box, to clear it in one tap -------------
  // One shared button laid over the right end of whichever text box has the
  // cursor. Nothing on the page is wrapped or moved; clearing tells the page
  // the box changed, so lists and searches update as if it was typed.
  const CLEARABLE = el => el && el.tagName === "INPUT" && /^(text|tel|email|url|)$/.test(el.type || "")
    && !el.readOnly && !el.disabled && el.dataset.noclear === undefined;
  let xb = null, xfor = null;
  function placeX() {
    if (!xb || !xfor) return;
    if (!xfor.value || !document.contains(xfor) || !xfor.getClientRects().length) { xb.style.display = "none"; return; }
    const r = xfor.getBoundingClientRect();
    xb.style.display = "flex";
    xb.style.left = (r.right - 24) + "px";
    xb.style.top = (r.top + r.height / 2 - 9) + "px";
  }
  function showX(el) {
    if (!xb) {
      xb = document.createElement("button");
      xb.type = "button"; xb.className = "field-x"; xb.tabIndex = -1; xb.title = "Clear"; xb.textContent = "\u00d7";
      xb.addEventListener("mousedown", e => {
        e.preventDefault();                       // the cursor stays in the box
        const el = xfor; if (!el) return;
        el.value = "";
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        el.focus(); placeX();
      });
      document.body.appendChild(xb);
    }
    xfor = el;
    if (!el.dataset.xpad) {                       // room so typed text never runs under the x
      el.dataset.xpad = "1";
      const pr = parseFloat(getComputedStyle(el).paddingRight) || 0;
      if (pr < 22) el.style.paddingRight = "24px";
    }
    placeX();
  }
  document.addEventListener("focusin", e => { if (CLEARABLE(e.target)) showX(e.target); else if (xb && e.target !== xb) { xfor = null; xb.style.display = "none"; } });
  document.addEventListener("input", e => { if (e.target === xfor) placeX(); });
  document.addEventListener("change", e => { if (e.target === xfor) placeX(); });
  // The x never outlives its box: gone, hidden, emptied, or neither focused nor under the pointer -> it goes.
  function checkX() {
    if (!xb || xb.style.display === "none") return;
    const el = xfor;
    if (!el || !document.contains(el) || !el.getClientRects().length || !el.value
        || (document.activeElement !== el && !el.matches(":hover") && !xb.matches(":hover"))) { xb.style.display = "none"; return; }
    placeX();
  }
  setInterval(checkX, 250);
  new MutationObserver(checkX).observe(document.documentElement, { childList: true, subtree: true });
  // Also when the pointer is over a filled box, not only when it has the cursor.
  document.addEventListener("mouseover", e => {
    const el = e.target;
    if (CLEARABLE(el) && el.value && (el !== xfor || !xb || xb.style.display === "none")) showX(el);
  });
  document.addEventListener("mouseout", e => {
    if (e.target === xfor && document.activeElement !== xfor && e.relatedTarget !== xb && xb) setTimeout(() => {
      if (document.activeElement !== xfor && !(xb.matches(":hover"))) { xb.style.display = "none"; }
    }, 200);
  });
  document.addEventListener("focusout", e => { if (e.target === xfor) setTimeout(() => { if (document.activeElement !== xfor && xb) xb.style.display = "none"; }, 150); });
  window.addEventListener("scroll", placeX, true);
  window.addEventListener("resize", placeX);

  window.HELP_TIPS_RUN = run;
  // Only when the page actually changes (a screen opens, a form is drawn),
  // and at most a few times a second - nothing runs while the app sits idle.
  let pending = false;
  const soon = () => { if (pending) return; pending = true; setTimeout(() => { pending = false; if (!document.hidden) run(document); }, 400); };
  if (!window.__helpTipsObs) { window.__helpTipsObs = new MutationObserver(soon); window.__helpTipsObs.observe(document.documentElement, { childList: true, subtree: true }); }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) soon(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => run(document)); else run(document);
})();
