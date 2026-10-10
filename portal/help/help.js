/* In-app help: the search box in the top bar, the "?" button, the guide
   drawer with a picture per step, "Show me" (the app walks to the page
   and circles each button) and "Watch" (the pictures play one after the
   other). Guides live in guides.js; pictures are made by
   tests/help_screens.js. Plain script, no libraries. */
(function () {
  "use strict";
  // The written guides, then one for every screen (auto_guides.js).
  const G = () => (window.HELP_GUIDES || []).concat(window.HELP_AUTO || []);
  const IMGS = () => window.HELP_IMGS || {};
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const $ = (s, r) => (r || document).querySelector(s);
  const imgUrl = (id, n) => `/portal/help/img/${id}-${n}.jpg?v=${(window.HELP_IMGS_V || "")}`;
  const hasImg = (id, n) => (IMGS()[id] || []).includes(n);

  // ---- Who may see which guide: the same right as the tab it is on ----
  function allowed(g) {
    try {
      if (typeof pgHas !== "function" || typeof ALL_PAGES === "undefined") return true;
      if (g.admin && typeof CURRENT_ROLE !== "undefined" && CURRENT_ROLE !== "admin") return false;
      const p = ALL_PAGES[g.go.page]; if (!p) return false;
      const t = p.tabs.find(x => x.id === g.go.tab); if (!t) return false;
      const sb = g.go.sub ? t.subs.find(x => x.id === g.go.sub) : null;
      if (g.go.sub && !sb) return false;
      if (typeof pgSubOk === "function") return sb ? pgSubOk(sb) && pgHas(t.right) : pgTabRightOk(t);   // Settings > Access ticks
      return pgHas(t.right) && (!sb || pgHas(sb.right));
    } catch (e) { return true; }
  }
  const mine = () => G().filter(allowed);

  // ---- Search: everyday words, other words for the same thing, typos ----
  const STOP = new Set("how to a an the i do can my of for in is what where we our it with on at from please me want".split(" "));
  const words = s => String(s || "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  function lev(a, b) {
    if (Math.abs(a.length - b.length) > 2) return 9;
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    return d[a.length][b.length];
  }
  function match(t, hay) {
    let best = 0;
    for (const h of hay) {
      let s = 0;
      if (h === t) s = 3;
      else if (t.length >= 2 && h.startsWith(t)) s = 2;
      else if (h.length >= 4 && t.startsWith(h)) s = 1.5;
      else if (t.length >= 4 && lev(t, h) <= (t.length >= 7 ? 2 : 1)) s = 1.5;
      if (s > best) best = s;
    }
    return best;
  }
  function search(q) {
    const qs = words(q).filter(w => !STOP.has(w));
    if (!qs.length) return [];
    const same = window.HELP_SAME || {};
    return mine().map((g, i) => {
      const title = words(g.title), hay = title.concat(words(g.words), words(g.area));
      let score = 0, hits = 0;
      for (const t of qs) {
        let s = match(t, hay) * (match(t, title) ? 1.3 : 1);
        for (const x of words(same[t])) s = Math.max(s, match(x, hay) * 0.8);
        if (s) hits++;
        score += s;
      }
      return { g, i, score: score * (hits / qs.length) };
    }).filter(r => r.score > 0.9).sort((a, b) => b.score - a.score || a.i - b.i)
      .filter((r, _, all) => r.score >= all[0].score * 0.45).map(r => r.g);
  }

  // ---- The bits on screen ----------------------------------------------
  let box, list, drawer, body;
  function mount() {
    const bar = $(".topbar"); if (!bar || (box && box.isConnected)) return;
    // The box and the ? are in the page itself (so the bar never changes
    // size as the page opens); made here only if a page lacks them.
    if (!$("#help-search")) {
      const right = bar.lastElementChild;
      const wrap = document.createElement("div");
      wrap.className = "help-wrap";
      wrap.innerHTML = `<span class="help-glass">&#128269;</span>
        <input id="help-search" type="search" autocomplete="off" placeholder="Search pages and tasks... e.g. LPO, petty cash, leave">
        <div id="help-results" class="help-results"></div>`;
      const q = document.createElement("button");
      q.id = "help-q"; q.className = "help-q"; q.title = "Help for this page"; q.textContent = "?";
      right.insertBefore(q, right.firstChild);
      right.insertBefore(wrap, right.firstChild);
    }
    $("#help-q").onclick = () => openList();
    box = $("#help-search"); list = $("#help-results");
    box.addEventListener("input", renderResults);
    box.addEventListener("focus", renderResults);
    box.addEventListener("keydown", e => {
      const items = [...list.querySelectorAll(".help-r")];
      const on = list.querySelector(".help-r.on"); let i = items.indexOf(on);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); i = e.key === "ArrowDown" ? Math.min(items.length - 1, i + 1) : Math.max(0, i - 1);
        items.forEach((x, k) => x.classList.toggle("on", k === i));
      } else if (e.key === "Enter") { const t = on || items[0]; if (t) t.click(); }
      else if (e.key === "Escape") { list.style.display = "none"; box.blur(); }
    });
    document.addEventListener("click", e => { if (!e.target.closest(".help-wrap")) list.style.display = "none"; });
    drawer = document.createElement("div");
    drawer.id = "help-drawer"; drawer.className = "help-drawer";
    drawer.innerHTML = `<div class="help-dh"><b>Help</b><button class="help-x" title="Close">&times;</button></div><div class="help-db"></div>`;
    document.body.appendChild(drawer);
    body = drawer.querySelector(".help-db");
    drawer.querySelector(".help-x").onclick = closeDrawer;
  }
  // ---- The top search: every page, tab and task this login may open ----
  // Picking a result goes straight there. Help guides are on the "?".
  function places() {
    const out = [];
    if (typeof ALL_PAGES === "undefined") return out;
    const tabOk = t => { try { return typeof pgTabOk === "function" ? pgTabOk(t) : (typeof pgTabRightOk === "function" ? pgTabRightOk(t) : true); } catch (e) { return true; } };
    const subOk = sb => { try { return typeof pgSubOk === "function" ? pgSubOk(sb) : true; } catch (e) { return true; } };
    Object.values(ALL_PAGES).forEach(pg => {
      if (!pg || !Array.isArray(pg.tabs)) return;
      const tabs = pg.tabs.filter(tabOk);
      if (!tabs.length) return;
      out.push({ id: "pg:" + pg.key, kind: "Page", title: pg.title, where: "", go: { page: pg.key }, hay: pg.title });
      tabs.forEach(t => {
        if (!(t.label === pg.title && pg.tabs.length === 1))
          out.push({ id: `tb:${pg.key}:${t.id}`, kind: "Page", title: t.label, where: pg.title, go: { page: pg.key, tab: t.id }, hay: `${pg.title} ${t.label}` });
        (t.subs || []).filter(subOk).forEach(sb => out.push({ id: `sb:${pg.key}:${t.id}:${sb.id}`, kind: "Page", title: sb.label,
          where: `${pg.title} › ${t.label}`, go: { page: pg.key, tab: t.id, sub: sb.id }, hay: `${pg.title} ${t.label} ${sb.label}` }));
      });
    });
    // The Staff page is one page with views inside it.
    if (out.some(x => x.id === "pg:people")) {
      const has = r => { try { return typeof pgHas !== "function" || pgHas(r); } catch (e) { return true; } };
      [["register", "labour", "Labour register", "people_labour"], ["register", "office", "Office staff register", "people_office"],
       ["register", "local", "Local staff register", "people_local"], ["register", "left", "Staff who left", ["people_labour", "people_office", "people_local"]],
       ["vacation", "", "Leave register (vacation, sick, emergency)", ["people_labour", "people_office", "people_local"]],
       ["bday", "", "Birthdays", ["people_labour", "people_office", "people_local"]]]
        .filter(v => has(v[3])).forEach(([view, group, label]) => out.push({ id: `pv:${view}:${group}`, kind: "Page", title: label, where: "Staff",
          go: { page: "people", view, group }, hay: `staff people employees ${label} ${view === "vacation" ? "leave vacation holiday" : ""}` }));
    }
    // Tasks: what each written guide is for, opened at the page it happens on.
    (window.HELP_GUIDES || []).filter(allowed).forEach(g => out.push({ id: "fn:" + g.id, kind: "Task", title: g.title.replace(/^How to /i, "").replace(/^\w/, c => c.toUpperCase()),
      where: g.area, go: g.go, hay: `${g.title} ${g.words || ""} ${g.area || ""}`, guide: g }));
    return out;
  }
  function find2(q) {
    const qs = words(q).filter(w => !STOP.has(w));
    if (!qs.length) return [];
    const same = window.HELP_SAME || {};
    const seen = new Set();
    return places().map((x, i) => {
      const title = words(x.title), hay = words(x.hay);
      let score = 0, hits = 0;
      for (const t of qs) {
        let sc = match(t, hay) * (match(t, title) ? 1.3 : 1);
        for (const y of words(same[t])) sc = Math.max(sc, match(y, hay) * 0.8);
        if (sc) hits++;
        score += sc;
      }
      // A page whose own name matches comes before a task on it.
      return { x, i, score: score * (hits / qs.length) * (x.kind === "Page" ? 1.15 : 1) };
    }).filter(r => r.score > 0.9).sort((a, b) => b.score - a.score || a.i - b.i)
      .filter((r, _, all) => r.score >= all[0].score * 0.4)
      .map(r => r.x).filter(x => { const k = JSON.stringify(x.go) + x.title; if (seen.has(k)) return false; seen.add(k); return true; });
  }
  let FOUND = [];
  function renderResults() {
    const q = box.value.trim();
    if (!q) { list.style.display = "none"; return; }
    FOUND = find2(q).slice(0, 10);
    list.innerHTML = FOUND.length
      ? FOUND.map((x, k) => `<div class="help-r${k ? "" : " on"}" data-id="${esc(x.id)}" data-k="${k}"><span class="help-area${x.kind === "Task" ? " task" : ""}">${x.kind === "Task" ? "Task" : "Go to"}</span>${esc(x.title)}${x.where ? `<small class="help-where">${esc(x.where)}</small>` : ""}</div>`).join("")
      : `<div class="help-none">Nothing called "${esc(q)}". Try another word - or press <b>?</b> for help.</div>`;
    list.style.display = "block";
    list.querySelectorAll(".help-r").forEach(el => el.onclick = () => {
      const x = FOUND[+el.dataset.k]; list.style.display = "none"; box.value = ""; box.blur();
      if (x) goTo({ go: x.go });
    });
  }
  function openDrawer() { drawer.classList.add("open"); }
  function closeDrawer() { drawer.classList.remove("open"); }

  // The "?" list: this page's guides first, then everything by area.
  function openList() {
    const all = mine(), here = (typeof PAGE !== "undefined" && PAGE) ? all.filter(g => g.go.page === PAGE.key) : [];
    const row = g => `<div class="help-li" data-id="${g.id}">${esc(g.title)}</div>`;
    const areas = [...new Set(all.map(g => g.area))];
    body.innerHTML =
      `<input class="help-dsearch" type="search" placeholder="Type what you want to do...">
       <div class="help-dres"></div>
       <div class="help-lists">
       ${here.length ? `<h4>On this page</h4>${here.map(row).join("")}` : ""}
       <h4>All topics</h4>
       ${areas.map(a => `<details><summary>${esc(a)} <span>${all.filter(g => g.area === a).length}</span></summary>${all.filter(g => g.area === a).map(row).join("")}</details>`).join("")}
       </div>
       <div class="help-foot"><button class="help-link" data-print>Print the whole guide</button></div>`;
    const ds = body.querySelector(".help-dsearch"), dr = body.querySelector(".help-dres"), ls = body.querySelector(".help-lists");
    ds.oninput = () => {
      const q = ds.value.trim(); ls.style.display = q ? "none" : "";
      const r = q ? search(q) : [];
      dr.innerHTML = q ? (r.length ? r.map(row).join("") : `<div class="help-none">No guide for that yet - try other words.</div>`) : "";
      bindRows();
    };
    body.querySelector("[data-print]").onclick = printAll;
    bindRows(); openDrawer();
    setTimeout(() => ds.focus(), 50);
  }
  function bindRows() { body.querySelectorAll(".help-li").forEach(el => el.onclick = () => openGuide(el.dataset.id)); }

  function openGuide(id) {
    const g = G().find(x => x.id === id); if (!g) return;
    body.innerHTML =
      `<button class="help-link" data-back>&larr; All topics</button>
       <div class="help-area">${esc(g.area)}</div>
       <h3 class="help-title">${esc(g.title)}</h3>
       <div class="help-acts">
         <button class="help-show" data-show>&#9654; Show me</button>
         ${(IMGS()[g.id] || []).length ? `<button class="help-watch" data-watch>&#9655; Watch</button>` : ""}
       </div>
       <ol class="help-steps">${g.steps.map((s, i) => `<li><div class="help-say">${esc(s.say)}</div>
         ${hasImg(g.id, i + 1) ? `<img loading="lazy" src="${imgUrl(g.id, i + 1)}" alt="" data-n="${i + 1}">` : ""}</li>`).join("")}</ol>
       ${g.tip ? `<div class="help-tip"><b>Good to know:</b> ${esc(g.tip)}</div>` : ""}`;
    body.querySelector("[data-back]").onclick = openList;
    body.querySelector("[data-show]").onclick = () => { closeDrawer(); tour(g); };
    const w = body.querySelector("[data-watch]"); if (w) w.onclick = () => watch(g, 0);
    body.querySelectorAll(".help-steps img").forEach(im => {
      im.onclick = () => watch(g, +im.dataset.n - 1, true);
      im.onerror = () => im.remove();
    });
    body.scrollTop = 0;
    openDrawer();
  }

  // ---- Show me: go to the page, dim the rest, circle each button ----------
  async function goTo(g) {
    const go = g.go;
    if (typeof pgGo !== "function") return;
    if (!PAGE || PAGE.key !== go.page) { pgGo(go.page); await wait(900); }
    if (go.tab) { pgTab(go.tab); await wait(500); }
    if (go.sub) { pgSub(go.sub); await wait(800); }
    if (go.view) {                         // a view inside the Staff page
      for (let i = 0; i < 30; i++) {
        const f = document.getElementById("pg-staff-frame"), w = f && f.contentWindow;
        let ready = false; try { ready = !!(w && typeof w.showView === "function" && w.eval("typeof ME !== 'undefined' && !!ME")); } catch (e) {}
        if (ready) {
          try { w.showView(go.view); if (go.group && typeof w.setGroup === "function") w.setGroup(go.group); } catch (e) {}
          break;
        }
        await wait(200);
      }
    }
  }
  const visible = el => !!(el && el.getClientRects().length && getComputedStyle(el).visibility !== "hidden");
  function find(sel) {
    if (!sel) return null;
    try { return [...document.querySelectorAll(sel)].find(visible) || null; } catch (e) { return null; }
  }
  let T = null;
  async function tour(g, start) {
    endTour();
    T = { g, i: start || 0 };
    const ring = document.createElement("div"); ring.className = "help-ring";
    const dim = document.createElement("div"); dim.className = "help-dim";
    const tip = document.createElement("div"); tip.className = "help-bubble";
    document.body.append(dim, ring, tip);
    Object.assign(T, { ring, dim, tip });
    window.addEventListener("resize", place); window.addEventListener("scroll", place, true);
    document.addEventListener("keydown", keys);
    await goTo(g);
    await step(T.i);
  }
  function keys(e) {
    if (!T) return;
    if (e.key === "Escape") endTour();
    else if (e.key === "ArrowRight") step(T.i + 1);
    else if (e.key === "ArrowLeft") step(T.i - 1);
  }
  async function step(i) {
    if (!T) return;
    const g = T.g;
    if (i >= g.steps.length) { endTour(); return; }
    if (i < 0) i = 0;
    T.i = i;
    const s = g.steps[i];
    if (s.run && !T["ran" + i]) { T["ran" + i] = 1; try { new Function(s.run)(); } catch (e) { console.error(e); } await wait(600); }
    let el = find(s.el);
    if (s.el && !el) { await wait(700); el = find(s.el); }
    T.el = el;
    T.missing = !!(s.el && !el);
    if (el) { el.scrollIntoView({ block: "center", inline: "nearest" }); await wait(250); }
    T.tip.innerHTML = `<div class="help-bn">Step ${i + 1} of ${g.steps.length}</div>
      <div class="help-bt">${esc(s.say)}</div>
      <div class="help-bb">
        <button class="help-bx" data-x>Close</button>
        <span style="flex:1"></span>
        ${i ? `<button class="help-bback" data-b>Back</button>` : ""}
        <button class="help-bnext" data-n>${i === g.steps.length - 1 ? "Done &#10003;" : "Next &rarr;"}</button>
      </div>`;
    T.tip.querySelector("[data-x]").onclick = endTour;
    T.tip.querySelector("[data-n]").onclick = () => step(T.i + 1);
    const b = T.tip.querySelector("[data-b]"); if (b) b.onclick = () => step(T.i - 1);
    place();
  }
  function place() {
    if (!T) return;
    const { ring, dim, tip, el } = T;
    const W = innerWidth, H = innerHeight;
    if (!el) {
      ring.style.display = "none"; dim.style.display = "block";
      tip.style.left = Math.max(12, (W - 360) / 2) + "px"; tip.style.top = Math.max(12, H / 2 - 80) + "px";
      return;
    }
    dim.style.display = "none"; ring.style.display = "block";
    const r = el.getBoundingClientRect(), p = 6;
    Object.assign(ring.style, { left: r.left - p + "px", top: r.top - p + "px", width: r.width + 2 * p + "px", height: r.height + 2 * p + "px" });
    const tw = Math.min(360, W - 24), th = tip.offsetHeight || 140;
    let top = r.bottom + p + 12;
    if (top + th > H - 8) top = r.top - p - 12 - th;
    if (top < 8) top = Math.min(H - th - 8, r.bottom + p + 12);
    let left = Math.min(Math.max(12, r.left + r.width / 2 - tw / 2), W - tw - 12);
    Object.assign(tip.style, { left: left + "px", top: Math.max(8, top) + "px", width: tw + "px" });
  }
  function endTour() {
    if (!T) return;
    ["ring", "dim", "tip"].forEach(k => T[k] && T[k].remove());
    window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true);
    document.removeEventListener("keydown", keys);
    T = null;
  }

  // ---- Watch: the step pictures, one after the other --------------------------
  function watch(g, from, still) {
    const ns = (IMGS()[g.id] || []).slice().sort((a, b) => a - b); if (!ns.length) return;
    let k = Math.max(0, ns.indexOf(from + 1)), playing = !still, timer = null;
    const m = document.createElement("div"); m.className = "help-watchbox";
    m.innerHTML = `<div class="help-wcard"><div class="help-wtop"><b>${esc(g.title)}</b><button class="help-x">&times;</button></div>
      <div class="help-wimg"><img></div><div class="help-wcap"></div>
      <div class="help-wbar"><button data-p>&larr;</button><button data-play></button><button data-nx>&rarr;</button><span class="help-dots"></span></div></div>`;
    document.body.appendChild(m);
    const img = m.querySelector("img"), cap = m.querySelector(".help-wcap"), dots = m.querySelector(".help-dots"), pb = m.querySelector("[data-play]");
    const show = () => {
      const n = ns[k]; img.src = imgUrl(g.id, n);
      cap.innerHTML = `<b>${n}.</b> ${esc(g.steps[n - 1] ? g.steps[n - 1].say : "")}`;
      dots.innerHTML = ns.map((_, j) => `<i class="${j === k ? "on" : ""}"></i>`).join("");
      pb.innerHTML = playing ? "&#10074;&#10074; Pause" : "&#9654; Play";
      clearTimeout(timer);
      if (playing) timer = setTimeout(() => { if (k < ns.length - 1) { k++; show(); } else { playing = false; show(); } }, 3200);
    };
    const close = () => { clearTimeout(timer); m.remove(); };
    m.querySelector(".help-x").onclick = close;
    m.onclick = e => { if (e.target === m) close(); };
    m.querySelector("[data-p]").onclick = () => { k = Math.max(0, k - 1); show(); };
    m.querySelector("[data-nx]").onclick = () => { k = Math.min(ns.length - 1, k + 1); show(); };
    pb.onclick = () => { playing = !playing; if (playing && k === ns.length - 1) k = 0; show(); };
    show();
  }

  // ---- Print the whole guide ---------------------------------------------------
  function printAll() {
    const all = mine(), areas = [...new Set(all.map(g => g.area))];
    const w = window.open("", "_blank"); if (!w) return;
    w.document.write(`<!doctype html><title>Infinia app - how to</title><style>
      body{font-family:Arial,sans-serif;color:#222;max-width:820px;margin:24px auto;padding:0 16px}
      h1{color:#C0392B} h2{border-bottom:2px solid #C0392B;padding-bottom:4px;margin-top:34px}
      .g{page-break-inside:avoid;margin:18px 0 26px} h3{margin:0 0 8px} li{margin:0 0 10px}
      img{display:block;max-width:100%;border:1px solid #ddd;border-radius:6px;margin-top:6px}
      .tip{background:#FFF7E0;padding:8px 12px;border-radius:6px;font-size:13px}
      @media print{.g{page-break-after:always}}</style>
      <h1>Infinia app - how to</h1><p>${all.length} guides. In the app, type what you want to do in the search box at the top, or press "Show me".</p>
      ${areas.map(a => `<h2>${esc(a)}</h2>` + all.filter(g => g.area === a).map(g => `<div class="g"><h3>${esc(g.title)}</h3><ol>
        ${g.steps.map((s, i) => `<li>${esc(s.say)}${hasImg(g.id, i + 1) ? `<img src="${location.origin}${imgUrl(g.id, i + 1)}">` : ""}</li>`).join("")}</ol>
        ${g.tip ? `<div class="tip"><b>Good to know:</b> ${esc(g.tip)}</div>` : ""}</div>`).join("")).join("")}`);
    w.document.close();
  }

  // ---- The small (i) beside a confusing box ---------------------------------
  function tips() {
    const t = window.HELP_TIPS || {};
    for (const sel in t) {
      document.querySelectorAll(sel).forEach(el => {
        if (el.dataset.helpI) return;
        el.dataset.helpI = "1";
        const i = document.createElement("span");
        i.className = "help-i"; i.tabIndex = 0; i.textContent = "i"; i.dataset.tip = t[sel];
        el.insertAdjacentElement("afterend", i);
      });
    }
  }

  // ---- First sign-in: one short hello pointing at the search box --------------
  function welcome() {
    if (navigator.webdriver && !window.__popups) return;
    try { if (localStorage.getItem("infinia-help-hello")) return; } catch (e) { return; }
    const app = $("#app-screen"); if (!app || getComputedStyle(app).display === "none" || !box) return;
    // Never on top of the sign-in notices; it waits until they are closed.
    if ($("#notif-overlay.on") || $(".hr-ask") || $(".modal.show")) return;
    const r = box.getBoundingClientRect(); if (!r.width) return;
    const done = () => { try { localStorage.setItem("infinia-help-hello", "1"); } catch (e) {} h.remove(); };
    const h = document.createElement("div"); h.className = "help-hello";
    h.innerHTML = `<b>Find any page</b>
      <p>Type in this box to jump to any page or task - for example <i>LPO</i>, <i>petty cash</i> or <i>leave</i>.</p>
      <p>For help, press <b>?</b> - each guide has <b>&#9654; Show me</b>, which circles every button for you.</p>
      <div class="help-bb"><button class="help-bx" data-ok>Got it</button><span style="flex:1"></span><button class="help-bnext" data-try>Try it</button></div>`;
    document.body.appendChild(h);
    h.style.top = r.bottom + 12 + "px"; h.style.left = Math.max(12, Math.min(r.left, innerWidth - 340)) + "px";
    h.querySelector("[data-ok]").onclick = done;
    h.querySelector("[data-try]").onclick = () => { done(); box.value = "petty cash"; box.focus(); renderResults(); };
  }

  function boot() {
    mount();
    setInterval(tips, 1500); tips();
    const t = setInterval(() => { if ($(".help-hello")) { clearInterval(t); return; }
      try { if (!localStorage.getItem("infinia-help-hello") && $("#app-screen") && getComputedStyle($("#app-screen")).display !== "none") { welcome(); if ($(".help-hello")) clearInterval(t); } } catch (e) { clearInterval(t); } }, 1500);
  }
  window.HELP = { search, findPlaces: find2, places, openGuide, openList, tour, endTour, allowed, find, goTo, step: i => step(i), get state() { return T; } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
