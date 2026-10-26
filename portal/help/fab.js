// Save, submit, send, record, approve: the page's one main action floats at the bottom of the screen
// (left of INFI), always in reach without scrolling - the same as the main app. Pop-ups keep theirs in
// their own footer; a page showing several such forms at once leaves them in place.
(function () {
  const WORDS = /^\s*(save|submit|send|post|record|issue|approve|update|confirm)\b(?!\s+(a|an|new)\b)/i;
  const st = document.createElement("style");
  st.textContent = `.btn.fab{position:fixed!important;bottom:22px;right:24px;z-index:60;margin:0!important;padding:13px 26px!important;font-size:14px;border-radius:24px!important;box-shadow:0 4px 14px rgba(0,0,0,.28);width:auto!important}
  html.infi-on .btn.fab{right:96px}
  @media (max-width:900px){.btn.fab{bottom:16px;right:16px;padding:12px 20px!important}html.infi-on .btn.fab{right:90px}}
  body.has-fab{padding-bottom:76px}`;
  document.head.appendChild(st);
  function infiOn() {
    try { if (window.parent !== window && parent.document.body.classList.contains("infi-on")) return true; } catch (e) {}
    const b = document.getElementById("infi-btn"); return !!(b && getComputedStyle(b).display !== "none");
  }
  const fixedUp = el => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) if (getComputedStyle(e).position === "fixed") return true; return false; };
  function run() {
    const on = infiOn(); if (document.documentElement.classList.contains("infi-on") !== on) document.documentElement.classList.toggle("infi-on", on);
    const cand = [...document.querySelectorAll(".btn.btn-primary")].filter(b => b.getClientRects().length && WORDS.test(b.textContent)
      && !b.closest("td, th, #login, .login-box") && !fixedUp(b));
    const pick = cand.length === 1 ? cand[0] : null;
    document.querySelectorAll(".fab-auto").forEach(x => { if (x !== pick) x.classList.remove("fab", "fab-auto"); });
    if (pick && !pick.classList.contains("fab-auto")) pick.classList.add("fab", "fab-auto");
    if (document.body.classList.contains("has-fab") !== !!pick) document.body.classList.toggle("has-fab", !!pick);
  }
  let t = 0; const soon = () => { if (t) return; t = setTimeout(() => { t = 0; try { run(); } catch (e) {} }, 120); };
  addEventListener("resize", soon);
  const go = () => { new MutationObserver(soon).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["style", "class", "hidden"] }); soon(); };
  if (document.body) go(); else addEventListener("DOMContentLoaded", go);
})();
