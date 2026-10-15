/* A quiet spelling hint for anything typed in words - descriptions, notes,
   terms. It never changes what is typed and never takes the cursor: when a
   finished word looks misspelt, a small line appears under the box -
   "Did you mean COMING?" - with Use and Keep. Ignore it and keep typing;
   it goes by itself.

   It knows: common English, construction and UAE words and acronyms
   (words.js), and this company's own words - people, suppliers, sites,
   materials, anything typed often (from the server). Short capital words
   (MEP, NOC, DM...) are taken as acronyms. "Keep" remembers a word on this
   device. A box can opt out with data-spell="off". */
(function () {
  "use strict";
  if (window.__spellOn) return; window.__spellOn = true;
  let WORDS = null, RANK = null;
  const MINE = new Set();
  try { (JSON.parse(localStorage.getItem("infinia-spell-keep") || "[]")).forEach(w => MINE.add(w)); } catch (e) {}

  // The word list (a quarter of a megabyte) is fetched the first time a box
  // that takes words is clicked - never at start-up.
  let asked = false;
  function fetchWords() {
    if (asked || window.SPELL_WORDS) return; asked = true;
    const sc = document.createElement("script");
    sc.src = (window.SPELL_WORDS_SRC || "/portal/help/words.js"); sc.async = true;
    document.head.appendChild(sc);
  }
  document.addEventListener("focusin", e => { if (eligible(e.target)) fetchWords(); });
  function load() {
    if (WORDS) return true;
    if (!window.SPELL_WORDS) { fetchWords(); return false; }
    const list = String(window.SPELL_WORDS || "").split(" ").filter(Boolean);
    WORDS = new Set(list); RANK = new Map(list.map((w, i) => [w, i]));
    // the company's own words, once a session
    const tok = (() => { try { return sessionStorage.getItem("infinia_token") || localStorage.getItem("infinia_token"); } catch (e) { return null; } })();
    if (tok) fetch("/employees/vocab", { headers: { Authorization: "Bearer " + tok } })
      .then(r => r.ok ? r.json() : null).then(d => { if (d) d.words.forEach(w => MINE.add(w)); }).catch(() => {});
  }
  const known = w => WORDS.has(w) || MINE.has(w);

  // Spelling candidates one change away (a letter missing, extra, swapped
  // or wrong), the commonest first; two away for long words.
  const ABC = "abcdefghijklmnopqrstuvwxyz";
  function edits1(w) {
    const out = new Set();
    for (let i = 0; i <= w.length; i++) {
      const a = w.slice(0, i), b = w.slice(i);
      if (b) out.add(a + b.slice(1));                                    // delete
      if (b.length > 1) out.add(a + b[1] + b[0] + b.slice(2));           // swap
      for (const c of ABC) { if (b) out.add(a + c + b.slice(1)); out.add(a + c + b); }   // replace, insert
    }
    return out;
  }
  function best(cands) {
    let top = null, r = Infinity;
    for (const c of cands) { const k = MINE.has(c) ? -1 : (RANK.has(c) ? RANK.get(c) : Infinity); if (k < r) { r = k; top = c; } }
    return r === Infinity ? null : top;
  }
  function suggest(w) {
    const one = [...edits1(w)].filter(known);
    if (one.length) return best(one);
    if (w.length < 6 || w.length > 13) return null;
    const two = new Set();
    for (const e of edits1(w)) for (const f of edits1(e)) if (known(f)) two.add(f);
    return two.size ? best(two) : null;
  }
  const styled = (orig, word) => orig === orig.toUpperCase() ? word.toUpperCase()
    : orig[0] === orig[0].toUpperCase() ? word[0].toUpperCase() + word.slice(1) : word;

  // Which boxes: free words only - not codes, numbers, phones, emails, IBANs.
  const SKIP = /(code|^no$|-no$|number|trn|iban|mobile|phone|email|ref|search|pno|plot|amount|amt|qty|rate|date|password|pw|map|tag|prefix|wps|token)/i;
  function eligible(el) {
    if (!el || el.dataset.spell === "off") return false;
    if (el.tagName === "TEXTAREA") return true;
    if (el.tagName !== "INPUT" || !/^(text|)$/.test(el.type || "")) return false;
    if (el.inputMode === "decimal" || el.inputMode === "numeric") return false;
    return !SKIP.test(el.id || "") && !SKIP.test(el.name || "");
  }

  // The hint line, one at a time, just under the box.
  let hint = null, cur = null;
  function close() { if (hint) hint.remove(); hint = null; cur = null; }
  function show(el, word, start, fix) {
    close();
    const r = el.getBoundingClientRect();
    hint = document.createElement("div");
    hint.className = "spell-hint";
    hint.innerHTML = `<span>Did you mean <b></b>?</span><button type="button" data-use>Use</button><button type="button" data-keep>Keep "<span></span>"</button>`;
    hint.querySelector("b").textContent = fix; hint.querySelector("[data-keep] span").textContent = word;
    document.body.appendChild(hint);
    const w = hint.offsetWidth;
    hint.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + "px";
    hint.style.top = (r.bottom + 4 + hint.offsetHeight > innerHeight ? r.top - hint.offsetHeight - 4 : r.bottom + 4) + "px";
    cur = { el, word, start, fix };
    // Buttons never take the cursor away from the box.
    hint.addEventListener("mousedown", e => e.preventDefault());
    hint.querySelector("[data-use]").onclick = () => {
      const v = el.value;
      if (v.substr(cur.start, cur.word.length) === cur.word) {
        const at = el.selectionStart, d = cur.fix.length - cur.word.length;
        el.value = v.slice(0, cur.start) + cur.fix + v.slice(cur.start + cur.word.length);
        el.dispatchEvent(new Event("input", { bubbles: true }));
        try { el.setSelectionRange(at + d, at + d); } catch (e) {}
      }
      close();
    };
    hint.querySelector("[data-keep]").onclick = () => {
      MINE.add(cur.word.toLowerCase());
      try { localStorage.setItem("infinia-spell-keep", JSON.stringify([...MINE].filter(x => !WORDS.has(x)).slice(-500))); } catch (e) {}
      close();
    };
    clearTimeout(show.t); show.t = setTimeout(close, 9000);
  }

  // Look at the word just finished (a space or punctuation typed after it),
  // or every word when the box is left.
  function check(el, all) {
    if (!load()) return;
    const v = el.value; if (!v) { close(); return; }
    const re = /[A-Za-z]+(?:'[A-Za-z]+)?/g; let m, found = null;
    const end = all ? v.length : el.selectionStart;
    while ((m = re.exec(v))) {
      const w = m[0], s = m.index, e = s + w.length;
      if (!all && e >= end) break;                       // the word still being typed
      if (w.length < 3) continue;
      if (w === w.toUpperCase() && w.length <= 4) continue;   // acronym
      const lw = w.toLowerCase().replace(/'s$/, "");
      if (known(lw)) continue;
      const fix = suggest(lw);
      if (fix && fix !== lw) found = { w, s, fix: styled(w, fix) };
    }
    if (found) show(el, found.w, found.s, found.fix);
    else if (cur && cur.el === el) close();
  }
  document.addEventListener("input", e => {
    const el = e.target; if (!eligible(el)) return;
    const ch = el.value.charAt((el.selectionStart || 1) - 1);
    // checked a moment after the word ends, off the typing path, so the
    // keys never wait on it
    if (/[\s.,;:!?)\-/]/.test(ch)) { clearTimeout(check.t); check.t = setTimeout(() => check(el, false), 250); }
  });
  document.addEventListener("focusout", e => { const el = e.target; if (eligible(el)) setTimeout(() => check(el, true), 0); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && hint) close(); });
  window.addEventListener("scroll", () => { if (hint && cur) { const r = cur.el.getBoundingClientRect(); hint.style.top = (r.bottom + 4) + "px"; } }, true);
  window.SPELL = { suggest: w => load() ? suggest(String(w).toLowerCase()) : null, known: w => load() ? known(String(w).toLowerCase()) : true };
})();
