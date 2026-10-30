/* Every date box in the app shows and takes dates as dd/mm/yyyy (30/10/2026), on every computer.

   A browser's own date box follows the computer's language, so on many PCs it showed mm/dd/yyyy. Here each
   <input type="date"> (and type="datetime-local") gets a calendar (flatpickr) that shows dd/mm/yyyy and
   accepts it typed (30/10/2026, 30-10-2026, 30.10.2026, 30102026). The real input stays exactly as it was -
   still type="date", hidden, holding yyyy-mm-dd - so every screen keeps reading and setting .value the way it
   always has, and its change / input events still fire. Boxes added later (forms, tables) are picked up too. */
(function () {
  if (window.__dmyDates) return;
  // automated test runs fill the browser's own date boxes; they turn this on themselves (tests/dmy_dates_test.js)
  if (navigator.webdriver && !window.__forceDmy) return;
  window.__dmyDates = true;
  const ROOT = (document.currentScript && document.currentScript.src || "").replace(/[^/]*$/, "");
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = ROOT + "vendor/flatpickr-4.6.13.min.css";
  document.head.appendChild(css);
  const st = document.createElement("style");
  st.textContent = `.dmy-hide{display:none!important}.dmy-alt{cursor:pointer;background-color:#fff}
    .dmy-alt[disabled]{background-color:#F3F3F3;cursor:default}.flatpickr-calendar{z-index:100000!important;font-family:inherit}`;
  document.head.appendChild(st);
  const proto = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  const KEEP = ["width", "minWidth", "maxWidth", "height", "padding", "border", "borderRadius", "fontSize", "fontFamily",
                "color", "boxSizing", "margin", "textAlign", "verticalAlign", "lineHeight", "fontWeight"];

  const pad = n => String(n).padStart(2, "0");
  function parseDmy(s, time) {
    s = String(s || "").trim();
    if (!s) return null;
    let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2}))?/);           // ISO, as stored
    if (m) return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0));
    m = s.match(/^(\d{1,2})[\/.\- ](\d{1,2})[\/.\- ](\d{2}|\d{4})(?:\s+(\d{1,2}):(\d{2}))?$/) // dd/mm/yyyy, dd-mm-yy ...
      || s.match(/^(\d{2})(\d{2})(\d{4})$/);                                             // 30102026
    if (!m) return null;
    const y = m[3].length === 2 ? 2000 + +m[3] : +m[3];
    const d = new Date(y, +m[2] - 1, +m[1], time ? +(m[4] || 0) : 0, time ? +(m[5] || 0) : 0);
    return d.getDate() === +m[1] && d.getMonth() === +m[2] - 1 ? d : null;                // 31/02 is not a date
  }

  function enhance(el) {
    if (el.__dmy || !window.flatpickr) return;
    const time = el.type === "datetime-local";
    el.__dmy = true;
    // the box's look, taken before it is hidden (a computed style is live - read later it says display:none)
    const live = getComputedStyle(el), cs = {};
    KEEP.concat(["display"]).forEach(k => { cs[k] = live[k]; });
    let busy = false, typed = null, last = el.value;              // last = the date the screen was last told about
    const fp = window.flatpickr(el, {
      altInput: true, altInputClass: "dmy-alt", altFormat: time ? "d/m/Y H:i" : "d/m/Y", dateFormat: time ? "Y-m-d\\TH:i" : "Y-m-d",
      enableTime: time, time_24hr: true, allowInput: true, disableMobile: true, clickOpens: !el.disabled && !el.readOnly,
      minDate: el.min || null, maxDate: el.max || null, locale: { firstDayOfWeek: 1 },
      parseDate: s => parseDmy(s, time),
      onChange: () => { busy = false; },
      onClose: (_d, _s, inst) => {                     // typed and left: read what was typed; a bad date keeps the last good one
        const t = (typed !== null ? typed : inst.altInput.value).trim();
        typed = null;
        if (!t) { if (proto.get.call(el)) inst.clear(false); proto.set.call(el, ""); fire(); return; }
        const d = parseDmy(t, time);
        if (d) { inst.setDate(d, false); fire(); }
        else { inst.setDate(last || null, false); proto.set.call(el, last || ""); }
      },
    });
    const alt = fp.altInput;
    // the real box stays a date box (screens look for input[type=date]) - only hidden
    el.type = time ? "datetime-local" : "date";
    el.classList.add("dmy-hide");
    alt.classList.add("dmy-alt");
    alt.placeholder = el.placeholder || (time ? "dd/mm/yyyy hh:mm" : "dd/mm/yyyy");
    alt.title = el.title || "";
    if (el.style.cssText) alt.style.cssText = el.style.cssText;
    KEEP.forEach(k => { if (!el.style[k] && cs[k] && cs[k] !== "auto" && !(k === "width" && cs[k] === "0px")) alt.style[k] = cs[k]; });
    alt.style.display = cs.display === "none" ? "none" : (cs.display === "block" ? "block" : "inline-block");
    alt.disabled = el.disabled; alt.readOnly = false;
    alt.addEventListener("input", () => { typed = alt.value; });          // what the person typed, before the calendar reads it
    if (el.id) alt.setAttribute("data-for", el.id);
    // events the screens listen for come from the real box, as before
    // One change = one input + one change event, sent once (screens save on change - never twice, never for a
    // mistyped date). The calendar library's own events are held back and sent through here instead.
    const send = EventTarget.prototype.dispatchEvent;
    function fire() {
      const v = proto.get.call(el);
      if (v === last) return;
      last = v;
      for (const t of ["input", "change"]) { const ev = new Event(t, { bubbles: true }); ev.__dmy = true; send.call(el, ev); }
    }
    el.dispatchEvent = function (ev) {
      if ((ev.type === "change" || ev.type === "input") && !ev.__dmy) {
        const tt = typed !== null ? typed : alt.value;
        if (ev.type === "change" && !(!proto.get.call(el) && tt.trim() && !parseDmy(tt, time))) fire();
        return true;
      }
      return send.call(el, ev);
    };
    // a screen that sets .value (or .valueAsDate) updates what is shown
    Object.defineProperty(el, "value", {
      configurable: true,
      get() { return proto.get.call(el); },
      set(v) {
        proto.set.call(el, v);
        if (busy) return;
        // the calendar writing its own pick: leave it (its change event follows); a screen setting a date: show it
        const mine = fp.selectedDates.length ? fp.formatDate(fp.selectedDates[0], fp.config.dateFormat) : "";
        if (proto.get.call(el) === mine || fp.isOpen || document.activeElement === alt) return;   // the person is using the box
        last = proto.get.call(el);
        busy = true; try { fp.setDate(v ? v : null, false); } finally { busy = false; }
      },
    });
    // disabled / hidden / min / max follow the real box
    new MutationObserver(() => {
      alt.disabled = el.disabled; fp.set("clickOpens", !el.disabled && !el.readOnly);
      if (el.min !== (fp.config._min || "")) { fp.set("minDate", el.min || null); fp.config._min = el.min; }
      if (el.max !== (fp.config._max || "")) { fp.set("maxDate", el.max || null); fp.config._max = el.max; }
      if (el.hidden || el.style.display === "none") alt.style.display = "none";
      else if (alt.style.display === "none" && !el.classList.contains("hide")) alt.style.display = cs.display === "block" ? "block" : "inline-block";
    }).observe(el, { attributes: true, attributeFilter: ["disabled", "readonly", "min", "max", "hidden", "style"] });
    // el.focus() / el.click() / showPicker() from a screen open the calendar
    el.focus = () => alt.focus();
    el.showPicker = () => fp.open();
    el.click = () => fp.open();
  }

  function scan(root) {
    if (!root || !root.querySelectorAll) return;
    if (root.matches && root.matches('input[type="date"],input[type="datetime-local"]')) enhance(root);
    root.querySelectorAll('input[type="date"],input[type="datetime-local"]').forEach(enhance);
  }
  function start() {
    scan(document.body);
    new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) scan(n); })))
      .observe(document.body, { childList: true, subtree: true });
  }
  const s = document.createElement("script");
  s.src = ROOT + "vendor/flatpickr-4.6.13.min.js";
  s.onload = () => (document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", start) : start());
  document.head.appendChild(s);
})();
