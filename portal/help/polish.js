// Small finishing touches that hold on every page (the app, Estimation and Trello in their frames):
//  - A hint inside a box (placeholder) that does not fit is not cut off: a shorter wording is used while
//    the box is narrow (a phone, a narrow column) and the full one comes back when there is room. The
//    full hint shows when the pointer rests on the box.
//  - On a phone, a small one-sign button (◀ ▶ × − +) gets a finger-sized area.
(function () {
  if (window.__polish) return; window.__polish = true;
  const SHORT = {
    "Add a remark...": "Remark", "Optional": "Opt.", "Pick or type the supplier": "Supplier",
    "Not in the list? write it here": "Other item", "Start typing - only what is in the store": "Type to search",
  };
  const cv = document.createElement("canvas").getContext("2d");
  function fits(inp, text, cs) {
    cv.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const room = inp.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - (inp.type === "search" ? 18 : 0);
    return cv.measureText(text).width <= room + 1;
  }
  function options(full, inp) {
    const out = [full];
    if (inp.dataset.phShort) out.push(inp.dataset.phShort);
    if (SHORT[full]) out.push(SHORT[full]);
    const a = full.replace(/^Start typing[^,]*,\s*/i, "");                 // "Start typing, e.g. cement" -> "e.g. cement"
    if (a !== full) out.push(a);
    const b = full.split(/ - | – /)[0].trim(); if (b && b !== full) out.push(b);   // "e.g. Good work - new rate" -> "e.g. Good work"
    for (const x of out.slice()) { const c = x.replace(/^e\.g\.\s*/i, ""); if (c !== x) out.push(c); }   // without the "e.g."
    const w = full.replace(/^e\.g\.\s*/i, "").split(/\s+/); if (w.length > 2) out.push(w.slice(0, 2).join(" ") + "…");
    return [...new Set(out)];
  }
  function fitAll() {
    document.querySelectorAll("input[placeholder]").forEach(inp => {
      if (!inp.getClientRects().length || inp.clientWidth < 20) return;
      if (inp.__phW === inp.clientWidth && inp.__phP === inp.placeholder) return;     // looked at already, nothing changed
      const full = inp.dataset.phFull || inp.placeholder; if (!full) return;
      if (inp.dataset.phFull && inp.placeholder !== inp.dataset.phShown) { inp.dataset.phFull = inp.placeholder; }   // the page set a new hint
      const want = inp.dataset.phFull || full;
      const cs = getComputedStyle(inp);
      if (fits(inp, want, cs)) { if (inp.placeholder !== want) inp.placeholder = want; }
      else {
        const pick = options(want, inp).find(t => fits(inp, t, cs)) || options(want, inp).pop();
        inp.dataset.phFull = want; inp.dataset.phShown = pick;
        if (inp.placeholder !== pick) inp.placeholder = pick;
        if (!inp.title) inp.title = want;
      }
      inp.__phW = inp.clientWidth; inp.__phP = inp.placeholder;
    });
    if (matchMedia("(max-width: 900px)").matches)
      document.querySelectorAll("button, .btn").forEach(b => {
        if (b.__tapDone || !b.getClientRects().length) return;
        const t = (b.textContent || "").trim(); if (!t || t.length > 2 || b.closest("table")) return;
        const r = b.getBoundingClientRect(); if (r.width >= 30 || r.height >= 30) return;
        b.__tapDone = true; b.classList.add("tap-min");
      });
  }
  const st = document.createElement("style");
  st.textContent = `@media (max-width: 900px) { .tap-min { min-width: 34px !important; min-height: 32px !important; display: inline-flex !important; align-items: center; justify-content: center; } }
    input:placeholder-shown { text-overflow: ellipsis; }`;
  (document.head || document.documentElement).appendChild(st);
  let t = 0; const soon = () => { if (t) return; t = setTimeout(() => { t = 0; try { fitAll(); } catch (e) {} }, 250); };
  const start = () => { soon(); new MutationObserver(soon).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style", "placeholder"] }); addEventListener("resize", soon); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
