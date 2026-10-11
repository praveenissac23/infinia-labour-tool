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
  }
  window.HELP_TIPS_RUN = run;
  if (!window.__helpTipsTimer) window.__helpTipsTimer = setInterval(() => run(document), 1500);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => run(document)); else run(document);
})();
