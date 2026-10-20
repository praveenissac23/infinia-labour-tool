/* Estimation > Trello - the board: header, lists, cards, drag and drop, quick edit. */
"use strict";
try { if (localStorage.getItem("kb_lab_open")) document.body.classList.add("lab-open"); } catch (e) {}

const VIEWS = [["board", "Board", "board"], ["table", "Table", "table"], ["calendar", "Calendar", "cal"], ["timeline", "Timeline", "timeline"], ["dashboard", "Dashboard", "dash"], ["mindmap", "Mind Map", "mind"]];
function pu(k) { const p = (S.board && S.board.prefs && S.board.prefs.powerups) || DEFAULT_PU; return p.includes(k); }
const DEFAULT_PU = ["fields", "dashboard", "calendar", "timeline", "table", "mindmap", "automation", "aging_off", "voting", "time", "repeater", "limits", "priority", "buttons"];

async function openBoard(bid, cid) {
  S.board = null; S.view = (location.hash.match(/view=(\w+)/) || [])[1] || "board"; S.filter = emptyFilter();
  document.body.classList.add("on-board");
  $("#home").classList.add("hide"); const el = $("#board"); el.classList.remove("hide");
  // A board seen before shows at once from memory, then catches up (only what changed is redrawn).
  const cached = BOARD_CACHE[bid];
  if (cached) { S.board = cached; S.cards = {}; cached.cards.forEach(c => S.cards[c.id] = c); S.lists = cached.lists; renderBoard(); if (S.view !== "board") renderView(); }
  else el.innerHTML = `<div class="loading"><div class="spin"></div></div>`;
  try { await reloadBoard(!!cached, bid); } catch (e) { el.innerHTML = `<div class="empty" style="color:#fff;margin-top:80px"><b style="color:#fff">${esc(e.message)}</b><br><button class="b" onclick="go('#/')">Go to boards</button></div>`; return; }
  startPoll();
  if (cid) openCardModal(cid);
}
const BOARD_CACHE = {};
async function reloadBoard(soft, bid) {
  const id = bid || (S.board && S.board.id); if (!id) return;
  const d = await GET(`/store/kb/boards/${id}`);
  const old = S.board, oldCards = S.cards;
  if (soft && old && old.id === d.id && d.version === old.version) return;      // nothing new: nothing redrawn
  S.board = d; S.cards = {}; d.cards.forEach(c => S.cards[c.id] = c); S.lists = d.lists; BOARD_CACHE[d.id] = d;
  if (!soft || !$("#lists") || !old || old.id !== d.id) renderBoard();
  else patchBoard(old, oldCards);
  if (S.view !== "board") renderView();
}
// Only what changed is redrawn: no flash, no scroll jump, the card under the mouse stays put.
function patchBoard(old, oldCards) {
  const d = S.board, J = JSON.stringify;
  const head = o => J([o.title, o.desc, o.bg, o.bg_url, o.visibility, o.starred, o.role, o.prefs, o.members, o.rules, o.closed]);
  if (head(old) !== head(d)) renderHeader();
  const frame = o => J([o.lists, o.labels, o.members, o.people.map(p => [p.id, p.name, p.initials]), o.fields, o.role, o.prefs]);
  if (frame(old) !== frame(d) || $(".composer textarea", $("#lists")) || $(".lhd textarea")) { renderLists(); return; }
  for (const l of d.lists) {
    const w = document.querySelector(`.lw[data-l="${l.id}"]`); if (!w) { renderLists(); return; }
    const box = w.querySelector("[data-cards]"); if (!box) continue;
    const ids = cardsOf(l.id).map(c => c.id), shown = [...box.querySelectorAll(":scope > .card")].map(e => +e.dataset.c);
    if (J(ids) !== J(shown)) {
      const st = box.scrollTop;
      box.innerHTML = ids.map(i => cardHtml(S.cards[i])).join("") + '<div class="pad"></div>';
      $$(".card", box).forEach(wireCard); box.scrollTop = st;
    } else {
      for (const i of ids) if (J(oldCards[i]) !== J(S.cards[i])) renderCardEl(i);
    }
  }
  updateListCounts(); applyFilter();
}

// ---------- header ----------
function renderBoard() {
  const b = S.board, el = $("#board");
  const base = bgBase(b.bg);
  el.style.background = bgCss(b.bg, b.bg_url);
  document.body.style.setProperty("--hdr-bg", b.bg_url || (b.bg || "").startsWith("img:") ? "rgba(0,0,0,.45)" : shade(base, -0.28));
  document.title = `${b.title} | Trello`;
  el.innerHTML = `<div id="bhead"></div><div id="canvas"><div id="lists"></div><div id="viewbox" class="hide"></div></div>`;
  renderHeader(); renderLists(); renderView();
}
function renderHeader() {
  const b = S.board, hd = $("#bhead"); if (!hd) return;
  const vis = b.visibility === "private" ? ["lock", "Private"] : ["team", "Workspace visible"];
  const mem = b.members.slice(0, 5).map(m => av(m).replace('class="av', `data-mem="${m.id}" class="av`)).join("") + (b.members.length > 5 ? `<span class="av more" data-mem="more">+${b.members.length - 5}</span>` : "");
  const viewIc = (VIEWS.find(v => v[0] === S.view) || VIEWS[0]);
  hd.innerHTML = `<button class="bname" id="bh-name" title="Rename board">${esc(b.title)}</button>
    <button class="hbtn ic" id="bh-star" title="Star or unstar board"><svg class="i ${b.starred ? "f" : ""}" style="${b.starred ? "color:#F5CD47" : ""}"><use href="#i-star"/></svg></button>
    <button class="hbtn ic hide-sm" id="bh-vis" title="${vis[1]}">${ic(vis[0])}</button>
    <button class="hbtn" id="bh-view">${ic(viewIc[2])} <span class="hide-sm">${viewIc[1]}</span> ${ic("down", "s14")}</button>
    <span class="sp"></span>
    <div class="facepile hide-sm">${mem}</div>
    ${pu("dashboard") ? `<button class="hbtn hide-sm ${S.view === "dashboard" ? "on" : ""}" id="bh-dash" title="Dashboard - workload, distribution, progress">${ic("chart")} <span>Dashboard</span></button>` : ""}
    ${pu("mindmap") ? `<button class="hbtn hide-sm ${S.view === "mindmap" ? "on" : ""}" id="bh-mind">${ic("mind")} <span>Mind Map</span></button>` : ""}
    ${(b.prefs.board_buttons || []).map((x, i) => `<button class="hbtn hide-sm" data-bbtn="${i}" title="Board button">${ic("btn")} ${esc(x.name)}</button>`).join("")}
    <button class="hbtn ic" id="bh-pu" title="Power-Ups">${ic("plug")}</button>
    <button class="hbtn ic" id="bh-auto" title="Automation">${ic("bolt")}</button>
    <button class="hbtn ${filterActive() ? "on" : ""}" id="bh-filter" title="Filter cards (f)">${ic("filter")}${filterActive() ? ` <span class="filt-n">${filterCount()}</span>` : ""}</button>
    ${filterActive() ? `<button class="hbtn filt-clear" id="bh-fclear">Clear all</button>` : ""}
    <button class="hbtn share" id="bh-share">${ic("share")} <span class="hide-sm">Share</span></button>
    ${window.PG_EMBED ? `<button class="hbtn ic hide-sm" id="bh-full" title="${document.body.classList.contains("kb-full") ? "Exit full screen (Esc)" : "Full screen - hide the app's menu and header"}">${ic(document.body.classList.contains("kb-full") ? "collapse" : "expand")}</button>` : ""}
    <button class="hbtn ic" id="bh-menu" title="Menu (w)">${ic("more")}</button>`;
  const nm = $("#bh-name");
  nm.onclick = () => {
    if (b.role === "observer") return;
    const inp = h(`<input class="bname-in">`); inp.value = b.title; inp.style.width = Math.max(120, nm.offsetWidth + 20) + "px"; nm.replaceWith(inp); inp.focus(); inp.select();
    const done = async ok => { const v = inp.value.trim(); if (ok && v && v !== b.title) { b.title = v; try { await PATCH(`/store/kb/boards/${b.id}`, { title: v }); } catch (e) { fail(e); } } renderHeader(); document.title = `${b.title} | Trello`; };
    inp.onkeydown = e => { if (e.key === "Enter") inp.blur(); if (e.key === "Escape") { inp.value = b.title; inp.blur(); } }; inp.onblur = () => done(true);
  };
  $("#bh-star").onclick = async () => { try { const r = await POST(`/store/kb/boards/${b.id}/star`); b.starred = r.starred; renderHeader(); refreshBoards(); } catch (e) { fail(e); } };
  $("#bh-vis").onclick = e => visibilityPop(e.currentTarget);
  $("#bh-view").onclick = e => viewPop(e.currentTarget);
  const dsh = $("#bh-dash"); if (dsh) dsh.onclick = () => setView(S.view === "dashboard" ? "board" : "dashboard");
  const mm = $("#bh-mind"); if (mm) mm.onclick = () => setView(S.view === "mindmap" ? "board" : "mindmap");
  $("#bh-pu").onclick = () => boardMenu("powerups");
  $("#bh-auto").onclick = () => boardMenu("automation");
  $("#bh-filter").onclick = e => filterPop(e.currentTarget);
  const fc = $("#bh-fclear"); if (fc) fc.onclick = () => clearFilter();
  $("#bh-share").onclick = () => shareDlg();
  $("#bh-menu").onclick = () => boardMenu();
  const fs = $("#bh-full"); if (fs) fs.onclick = () => { try { parent.postMessage({ kb: "fullscreen" }, location.origin); } catch (e) {} };
  $$("[data-mem]", hd).forEach(a => a.onclick = e => a.dataset.mem === "more" ? shareDlg() : memberCardPop(e.currentTarget, +a.dataset.mem));
  $$("[data-bbtn]", hd).forEach(x => x.onclick = async () => { try { const r = await POST(`/store/kb/boards/${b.id}/button`, { index: +x.dataset.bbtn }); toast(`Ran on ${r.cards} card${r.cards === 1 ? "" : "s"}`); reloadBoard(true); } catch (e) { fail(e); } });
}
function renderFilterBtn() { renderHeader(); }
function viewPop(anchor) {
  const p = pop(anchor, "Views", VIEWS.filter(v => v[0] === "board" || pu(v[0])).map(([k, l, i]) => `<button class="mi" data-v="${k}">${ic(i)} ${l}${S.view === k ? `<span class="ck">${ic("check")}</span>` : ""}</button>`).join("")
    + `<hr><p class="muted" style="margin:0">Switch views on or off in Power-Ups.</p>`);
  $$("[data-v]", p).forEach(b => b.onclick = () => { closePops(); setView(b.dataset.v); });
}
function setView(v) { S.view = v; history.replaceState(null, "", `#/b/${S.board.id}${v !== "board" ? "?view=" + v : ""}`); renderHeader(); renderView(); }
function renderView() {
  const lists = $("#lists"), vb = $("#viewbox"); if (!lists) return;
  if (S.view === "board") { lists.classList.remove("hide"); vb.classList.add("hide"); vb.innerHTML = ""; return; }
  lists.classList.add("hide"); vb.classList.remove("hide"); vb.className = "view";
  const fn = { table: tableView, calendar: calendarView, timeline: timelineView, dashboard: dashboardView, mindmap: mindmapView }[S.view];
  if (fn) fn(vb); else { S.view = "board"; renderView(); }
}
function visibilityPop(anchor) {
  const b = S.board;
  const p = pop(anchor, "Change visibility", `<button class="mi" data-v="private">${ic("lock")}<div><b>Private</b><small>Board members and Infinia admins can see and edit this board.</small></div>${b.visibility === "private" ? `<span class="ck">${ic("check")}</span>` : ""}</button>
    <button class="mi" data-v="team">${ic("team")}<div><b>Workspace</b><small>Everyone with Estimation &gt; Trello can see and edit this board.</small></div>${b.visibility === "team" ? `<span class="ck">${ic("check")}</span>` : ""}</button>`, { cls: "wide" });
  $$("[data-v]", p).forEach(x => x.onclick = async () => { closePops(); try { await PATCH(`/store/kb/boards/${b.id}`, { visibility: x.dataset.v }); await reloadBoard(true); } catch (e) { fail(e); } });
}
function memberCardPop(anchor, uid) {
  const m = S.board.members.find(x => x.id === uid) || person(uid); if (!m) return;
  const admin = S.board.role === "admin";
  const p = pop(anchor, m.name, `<div style="display:flex;gap:12px;align-items:center;margin-bottom:8px">${av(m, "xl")}<div><b>${esc(m.name)}</b><div class="muted">@${esc(m.username)} · ${esc(m.board_role || "member")}</div></div></div>
    <button class="mi" data-k="cards">View member's board activity</button>
    <button class="mi" data-k="filter">Show only their cards</button>
    ${admin ? `<button class="mi" data-k="role">Change permissions... <small>${esc(m.board_role || "member")}</small></button>` : ""}
    ${admin || uid === S.me.id ? `<button class="mi dng" data-k="rm">${uid === S.me.id ? "Leave board" : "Remove from board"}</button>` : ""}`);
  p.querySelector('[data-k="cards"]').onclick = () => { closePops(); boardMenu("activity"); };
  p.querySelector('[data-k="filter"]').onclick = () => { closePops(); S.filter = emptyFilter(); S.filter.members = [uid]; applyFilter(); };
  const r = p.querySelector('[data-k="role"]'); if (r) r.onclick = () => { const q = subPop(p, "Change permissions", ["admin", "member", "observer"].map(x => `<button class="mi" data-r="${x}"><div><b>${x[0].toUpperCase() + x.slice(1)}</b><small>${{ admin: "Can view and edit cards, remove members, and change settings for the board.", member: "Can view and edit cards. Can change some board settings.", observer: "Can view and comment." }[x]}</small></div>${m.board_role === x ? `<span class="ck">${ic("check")}</span>` : ""}</button>`).join(""), () => memberCardPop(anchor, uid));
    $$("[data-r]", q).forEach(x => x.onclick = async () => { closePops(); try { await PATCH(`/store/kb/boards/${S.board.id}/members/${uid}`, { role: x.dataset.r }); reloadBoard(true); } catch (e) { fail(e); } }); };
  const rm = p.querySelector('[data-k="rm"]'); if (rm) rm.onclick = () => confirmPop(rm, uid === S.me.id ? "Leave board?" : "Remove member?", uid === S.me.id ? "You will be removed from all cards on this board." : "The member will be removed from all cards on this board.", uid === S.me.id ? "Leave" : "Remove", async () => { try { await DEL(`/store/kb/boards/${S.board.id}/members/${uid}`); if (uid === S.me.id && S.board.visibility === "private") go("#/"); else reloadBoard(true); } catch (e) { fail(e); } });
}

// ---------- lists ----------
function cardsOf(lid) { return Object.values(S.cards).filter(c => c.list_id === lid).sort((a, b) => a.pos - b.pos || a.id - b.id); }
function renderLists() {
  const wrap = $("#lists"); if (!wrap) return;
  const sx = wrap.scrollLeft, scrolls = {};
  $$(".lw", wrap).forEach(w => { const lc = w.querySelector(".lcards"); if (lc) scrolls[w.dataset.l] = lc.scrollTop; });
  const openComp = $(".composer textarea", wrap); const compList = openComp && openComp.closest(".lw") ? openComp.closest(".lw").dataset.l : null; const compVal = openComp ? openComp.value : "";
  wrap.innerHTML = S.lists.map(listHtml).join("") + (S.board.role === "observer" ? "" : `<div class="lw" id="addlist-w"><button class="addlist" id="addlist">${ic("plus")} Add another list</button></div>`);
  $$(".lw[data-l]", wrap).forEach(w => wireList(w));
  const al = $("#addlist"); if (al) al.onclick = () => addListForm();
  wrap.scrollLeft = sx; $$(".lw", wrap).forEach(w => { const lc = w.querySelector(".lcards"); if (lc && scrolls[w.dataset.l]) lc.scrollTop = scrolls[w.dataset.l]; });
  if (compList) { const w = wrap.querySelector(`.lw[data-l="${compList}"]`); if (w) { openComposer(+compList); const t = w.querySelector(".composer textarea"); if (t) t.value = compVal; } }
  applyFilter();
}
function listHtml(l) {
  const cs = cardsOf(l.id), n = cs.length;
  const over = pu("limits") && l.wip && n > l.wip;
  if (l.collapsed) return `<div class="lw collapsed" data-l="${l.id}"><div class="lst collapsed" data-expand>${ic("expand", "s14")}<div class="lv">${esc(l.title)}</div><span class="muted">${n}</span></div></div>`;
  return `<div class="lw" data-l="${l.id}"><div class="lst ${over ? "over" : ""}">
    ${l.color ? `<div class="lcolor" style="background:${labColor(l.color)}"></div>` : ""}
    <div class="lhd"><div class="lt" data-lt>${esc(l.title)}</div><span class="cnt" data-cnt>${pu("limits") && l.wip ? `${n}/${l.wip}` : n}</span><button class="x" data-lmenu title="List actions">${ic("more")}</button></div>
    <div class="lcards" data-cards>${cs.map(cardHtml).join("")}<div class="pad"></div></div>
    ${S.board.role === "observer" ? "" : `<div class="lft"><button class="add" data-add>${ic("plus")} Add a card</button><button class="x" data-tplbtn title="Create from template">${ic("tpl")}</button></div>`}
  </div></div>`;
}
function wireList(w) {
  const lid = +w.dataset.l, l = S.lists.find(x => x.id === lid);
  const ex = w.querySelector("[data-expand]"); if (ex) { ex.onclick = () => listPatch(lid, { collapsed: false }); return; }
  w.onmouseenter = () => HOVER_LIST = lid; w.onmouseleave = () => { if (HOVER_LIST === lid) HOVER_LIST = null; };
  const lt = w.querySelector("[data-lt]");
  lt.onclick = () => {
    if (S.board.role === "observer") return;
    const ta = h(`<textarea rows="1"></textarea>`); ta.value = l.title; lt.replaceWith(ta); ta.focus(); ta.select();
    const fit = () => { ta.style.height = "32px"; ta.style.height = ta.scrollHeight + "px"; }; fit(); ta.oninput = fit;
    ta.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); ta.blur(); } if (e.key === "Escape") { ta.value = l.title; ta.blur(); } };
    ta.onblur = () => { const v = ta.value.trim(); if (v && v !== l.title) { l.title = v; listPatch(lid, { title: v }); } else renderLists(); };
  };
  w.querySelector("[data-lmenu]").onclick = e => listMenu(e.currentTarget, lid);
  const add = w.querySelector("[data-add]"); if (add) add.onclick = () => openComposer(lid);
  const tb = w.querySelector("[data-tplbtn]"); if (tb) tb.onclick = e => cardTemplatesPop(e.currentTarget, lid);
  $$(".card", w).forEach(wireCard);
  // drop files on a card / list
  w.addEventListener("dragover", e => { if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { e.preventDefault(); } });
  w.addEventListener("drop", e => {
    if (!e.dataTransfer || !e.dataTransfer.files.length) return; e.preventDefault();
    const ce = e.target.closest(".card"); if (ce) uploadFiles(+ce.dataset.c, [...e.dataTransfer.files]);
  });
  const hd = w.querySelector(".lhd"); hd.addEventListener("pointerdown", e => { if (e.target.closest("button,textarea,[data-lt]") && !e.target.closest("[data-lt]")) return; startDrag(e, "list", lid, w); });
}
async function listPatch(lid, patch) {
  const l = S.lists.find(x => x.id === lid); if (l) Object.assign(l, patch);
  renderLists();
  try { await PATCH(`/store/kb/lists/${lid}`, patch); await reloadBoard(true); } catch (e) { fail(e); reloadBoard(true); }
}
function updateListCounts() {
  $$(".lw[data-l]").forEach(w => {
    const lid = +w.dataset.l, l = S.lists.find(x => x.id === lid); if (!l) return;
    const all = cardsOf(lid), vis = all.filter(matchFilter).length, cnt = w.querySelector("[data-cnt]");
    if (cnt) cnt.textContent = filterActive() ? `${vis}/${all.length}` : (pu("limits") && l.wip ? `${all.length}/${l.wip}` : all.length);
  });
}
function addListForm() {
  const w = $("#addlist-w");
  w.innerHTML = `<div class="addlist-form"><input class="t" placeholder="Enter list name…" id="nl-t"><div class="composer" style="padding:0"><div class="row"><button class="b pri" id="nl-go">Add list</button><button class="x" id="nl-x">${ic("x")}</button></div></div></div>`;
  const t = $("#nl-t"); t.focus();
  const add = async () => {
    const v = t.value.trim(); if (!v) { t.focus(); return; }
    t.value = ""; t.focus();
    try { await POST(`/store/kb/boards/${S.board.id}/lists`, { title: v }); await reloadBoard(true); const nt = $("#addlist-w") && null; addListForm(); $("#lists").scrollLeft = 1e6; } catch (e) { fail(e); }
  };
  $("#nl-go").onclick = add; t.onkeydown = e => { if (e.key === "Enter") add(); if (e.key === "Escape") renderLists(); };
  $("#nl-x").onclick = () => renderLists();
  t.onblur = () => setTimeout(() => { if ($("#nl-t") && !$("#nl-t").value && document.activeElement !== $("#nl-t")) renderLists(); }, 200);
}
function listMenu(anchor, lid) {
  const l = S.lists.find(x => x.id === lid);
  const p = pop(anchor, "List actions", `<button class="mi" data-k="add">Add card</button><button class="mi" data-k="copy">Copy list</button><button class="mi" data-k="move">Move list</button>
    <button class="mi" data-k="moveall">Move all cards in this list</button><button class="mi" data-k="sort">Sort by…</button>
    <button class="mi" data-k="collapse">Collapse list</button>
    <hr><h5 style="margin-top:4px">Change list color</h5><div class="grid5">${COVER_COLORS.map(x => `<button class="sw ${l.color === x ? "on" : ""}" data-col="${x}" style="background:var(--l-${x});height:28px"></button>`).join("")}</div>
    <button class="b" style="width:100%;margin-top:6px" data-col="">${ic("x", "s14")} Remove color</button>
    ${pu("limits") ? `<hr><h5 style="margin-top:4px">List limit</h5><div style="display:flex;gap:8px"><input class="t" type="number" min="0" data-wip value="${l.wip || ""}" placeholder="No limit"><button class="b" data-k="wip">Save</button></div>` : ""}
    ${pu("automation") ? `<hr><h5 style="margin-top:4px">Automation</h5><button class="mi" data-k="rule-add">When a card is added to the list…</button><button class="mi" data-k="rule-sort">Every day, sort list by…</button>` : ""}
    <hr><button class="mi" data-k="archive">Archive this list</button><button class="mi" data-k="archiveall">Archive all cards in this list</button>`);
  const k = sel => p.querySelector(`[data-k="${sel}"]`);
  k("add").onclick = () => { closePops(); openComposer(lid, null, "top"); };
  k("collapse").onclick = () => { closePops(); listPatch(lid, { collapsed: true }); };
  k("copy").onclick = () => { const q = subPop(p, "Copy list", `<label class="fl" style="margin-top:0">Name</label><textarea class="t" data-n rows="2">${esc(l.title)}</textarea><button class="b pri" style="margin-top:12px" data-go>Create list</button>`, () => listMenu(anchor, lid));
    q.querySelector("[data-go]").onclick = async () => { closePops(); try { await POST(`/store/kb/lists/${lid}/copy`, { title: q.querySelector("[data-n]").value.trim() || l.title }); reloadBoard(true); } catch (e) { fail(e); } }; };
  k("move").onclick = async () => {
    const boards = (await refreshBoards()).boards.filter(b => !b.closed);
    let bid = S.board.id;
    const posHtml = lists => lists.map((x, i) => `<option value="${i}" ${x.id === lid ? "selected" : ""}>${i + 1}${x.id === lid ? " (current)" : ""}</option>`).join("") + (bid !== S.board.id ? `<option value="${lists.length}" selected>${lists.length + 1}</option>` : "");
    const q = subPop(p, "Move list", `<label class="fl" style="margin-top:0">Board</label><select class="t" data-b>${boards.map(b => `<option value="${b.id}" ${b.id === bid ? "selected" : ""}>${esc(b.title)}</option>`).join("")}</select><label class="fl">Position</label><select class="t" data-p>${posHtml(S.lists)}</select><button class="b pri" style="margin-top:12px" data-go>Move</button>`, () => listMenu(anchor, lid));
    let target = S.lists;
    q.querySelector("[data-b]").onchange = async e => { bid = +e.target.value; target = (await boardListsFor(bid)).lists; q.querySelector("[data-p]").innerHTML = posHtml(target); };
    q.querySelector("[data-go]").onclick = async () => {
      closePops(); const i = +q.querySelector("[data-p]").value;
      try {
        if (bid !== S.board.id) { await PATCH(`/store/kb/lists/${lid}`, { board_id: bid }); toast("List moved to the other board"); }
        else { const others = S.lists.filter(x => x.id !== lid); const bef = others[i - 1], aft = others[i]; await PATCH(`/store/kb/lists/${lid}`, { pos: !bef ? (aft ? aft.pos / 2 : 65536) : !aft ? bef.pos + 65536 : (bef.pos + aft.pos) / 2 }); }
        reloadBoard(true);
      } catch (e) { fail(e); }
    };
  };
  k("moveall").onclick = () => { const q = subPop(p, "Move all cards in list", S.lists.map(x => `<button class="mi" data-to="${x.id}" ${x.id === lid ? "disabled style='opacity:.5'" : ""}>${esc(x.title)}${x.id === lid ? " (current)" : ""}</button>`).join(""), () => listMenu(anchor, lid));
    $$("[data-to]", q).forEach(b => b.onclick = async () => { closePops(); try { await POST(`/store/kb/lists/${lid}/move-cards`, { to: +b.dataset.to }); reloadBoard(true); } catch (e) { fail(e); } }); };
  k("sort").onclick = () => { const q = subPop(p, "Sort list", [["created_new", "Date created (newest first)"], ["created_old", "Date created (oldest first)"], ["name", "Card name (alphabetically)"], ["due", "Due date"]].map(([v, t]) => `<button class="mi" data-s="${v}">${t}</button>`).join(""), () => listMenu(anchor, lid));
    $$("[data-s]", q).forEach(b => b.onclick = async () => { closePops(); try { await POST(`/store/kb/lists/${lid}/sort`, { by: b.dataset.s }); reloadBoard(true); } catch (e) { fail(e); } }); };
  $$("[data-col]", p).forEach(b => b.onclick = () => { closePops(); listPatch(lid, { color: b.dataset.col }); });
  const wip = k("wip"); if (wip) wip.onclick = () => { closePops(); listPatch(lid, { wip: +p.querySelector("[data-wip]").value || 0 }); };
  const ra = k("rule-add"); if (ra) ra.onclick = () => { closePops(); boardMenu("automation", { tab: "schedule", trigger: { type: "schedule", every: "day", time: "09:00", cards: "none" }, actions: [{ type: "sort_list", list_id: lid, by: "due" }] }); };
  const rs = k("rule-sort"); if (rs) rs.onclick = () => { closePops(); boardMenu("automation", { trigger: { type: "card_added", list_id: lid } }); };
  k("archive").onclick = async () => { closePops(); try { await PATCH(`/store/kb/lists/${lid}`, { closed: true }); toast("List archived", { undo: async () => { await PATCH(`/store/kb/lists/${lid}`, { closed: false }); reloadBoard(true); } }); reloadBoard(true); } catch (e) { fail(e); } };
  k("archiveall").onclick = () => { const q = subPop(p, "Archive all cards in this list?", `<p style="margin:0 0 12px">This will remove all the cards in this list from the board. To view archived cards and bring them back to the board, click “Menu” &gt; “Archived items.”</p><button class="b dng" style="width:100%">Archive all</button>`, () => listMenu(anchor, lid));
    q.querySelector(".b.dng").onclick = async () => { closePops(); try { await POST(`/store/kb/lists/${lid}/archive-cards`); reloadBoard(true); } catch (e) { fail(e); } }; };
}
function cardTemplatesPop(anchor, lid) {
  const tpls = Object.values(S.cards).filter(c => c.is_template);
  const p = pop(anchor, "Card templates", (tpls.length ? tpls.map(c => `<button class="mi" data-t="${c.id}">${ic("tpl")}<div style="min-width:0">${esc(c.title)}</div></button>`).join("") : '<p class="muted" style="margin:0 0 8px">You can make any card a template: open it, then … &gt; Make template.</p>')
    + `<hr><button class="b" style="width:100%" data-new>${ic("plus", "s14")} Create a new template</button>`);
  $$("[data-t]", p).forEach(b => b.onclick = () => {
    const c = S.cards[+b.dataset.t];
    const q = subPop(p, "Create card from template", `<label class="fl" style="margin-top:0">Card title</label><textarea class="t" data-n rows="2">${esc(c.title)}</textarea><div style="margin-top:8px"><label class="chk"><input type="checkbox" data-m checked> Keep members</label></div><button class="b pri" style="margin-top:12px" data-go>Create card</button>`, () => cardTemplatesPop(anchor, lid));
    q.querySelector("[data-go]").onclick = async () => { closePops(); try { const r = await POST(`/store/kb/lists/${lid}/cards`, { title: q.querySelector("[data-n]").value.trim() || c.title, template_id: c.id, keep_members: q.querySelector("[data-m]").checked }); await reloadBoard(true); go(`#/b/${S.board.id}/c/${r.id}`); } catch (e) { fail(e); } };
  });
  p.querySelector("[data-new]").onclick = async () => { closePops(); try { const r = await POST(`/store/kb/lists/${lid}/cards`, { title: "New template" }); await PATCH(`/store/kb/cards/${r.id}`, { is_template: true }); await reloadBoard(true); go(`#/b/${S.board.id}/c/${r.id}`); } catch (e) { fail(e); } };
}

// ---------- add a card ----------
function openComposer(lid, afterCid, where) {
  $$(".composer").forEach(c => c.remove()); $$(".lft").forEach(f => f.classList.remove("hide"));
  const w = document.querySelector(`.lw[data-l="${lid}"]`); if (!w) return;
  const box = w.querySelector("[data-cards]");
  const comp = h(`<div class="composer"><textarea placeholder="Enter a title or paste a link"></textarea><div class="row"><button class="b pri" data-go>Add card</button><button class="x" data-x>${ic("x")}</button><span style="flex:1"></span><button class="x" data-more title="Options">${ic("more")}</button></div></div>`);
  let pos = "bottom";
  if (where === "top") { box.prepend(comp); pos = "top"; }
  else if (afterCid) { const ce = box.querySelector(`.card[data-c="${afterCid}"]`); ce.after(comp); const cs = cardsOf(lid); const i = cs.findIndex(c => c.id === afterCid); pos = cs[i + 1] ? (cs[i].pos + cs[i + 1].pos) / 2 : "bottom"; }
  else { box.querySelector(".pad").before(comp); w.querySelector(".lft").classList.add("hide"); }
  const ta = comp.querySelector("textarea"); ta.focus(); comp.scrollIntoView({ block: "nearest" });
  const fit = () => { ta.style.height = "56px"; ta.style.height = Math.max(56, ta.scrollHeight) + "px"; }; ta.oninput = fit;
  const add = async () => {
    const v = ta.value.trim(); if (!v) { ta.focus(); return; }
    const lines = v.split(/\n+/).map(x => x.trim()).filter(Boolean);
    let titles = [v.replace(/\n+/g, " ")];
    if (lines.length > 1 && !comp._asked) {
      comp._asked = true;
      const many = await new Promise(res => { const q = pop(ta, "Create cards?", `<p style="margin:0 0 12px">You pasted ${lines.length} lines. Make a card for each line?</p><button class="b pri" style="width:100%" data-y>Create ${lines.length} cards</button><button class="b" style="width:100%;margin-top:8px" data-n>Just one card</button>`, { nofocus: true }); q.querySelector("[data-y]").onclick = () => { closePops(); res(true); }; q.querySelector("[data-n]").onclick = () => { closePops(); res(false); }; });
      if (many) titles = lines;
    }
    comp._asked = false;
    ta.value = ""; fit(); ta.focus();
    // show it at once (Trello feels instant)
    const tmp = -Date.now();
    try {
      const r = await POST(`/store/kb/lists/${lid}/cards`, { titles, pos });
      const cur = cardsOf(lid);
      if (typeof pos === "number") pos = pos + 0.001 * titles.length;
      await reloadBoard(true);
      const w2 = document.querySelector(`.lw[data-l="${lid}"]`);
      if (w2 && !w2.querySelector(".composer")) { openComposer(lid, where === "top" ? null : r.ids[r.ids.length - 1], where === "top" ? "top" : null); }
    } catch (e) { fail(e); }
  };
  comp.querySelector("[data-go]").onclick = add;
  comp.querySelector("[data-x]").onclick = () => { comp.remove(); w.querySelector(".lft").classList.remove("hide"); };
  comp.querySelector("[data-more]").onclick = e => { const q = pop(e.currentTarget, "Options", `<button class="mi" data-k="tpl">${ic("tpl")} Create from template…</button>`); q.querySelector("[data-k]").onclick = () => cardTemplatesPop(e.currentTarget, lid); };
  ta.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); add(); } if (e.key === "Escape") { comp.remove(); w.querySelector(".lft").classList.remove("hide"); } };
  ta.onblur = () => setTimeout(() => { if (comp.isConnected && !ta.value.trim() && document.activeElement !== ta && !$(".pop")) { comp.remove(); w.querySelector(".lft") && w.querySelector(".lft").classList.remove("hide"); } }, 150);
}

// ---------- a card on the board ----------
function cardHtml(c) {
  const cov = c.cover || {}, full = cov.size === "full" && (cov.color || cov.url);
  const labels = c.mirror ? (c.mirror.labels || []) : c.labels.map(id => S.board.labels.find(l => l.id === id)).filter(Boolean);
  const ds = dueState(c);
  const age = pu("aging") && c.updated ? Math.floor((Date.now() - new Date(c.updated)) / 86400000) : 0;
  const ageCls = age >= 28 ? "aged-4" : age >= 21 ? "aged-3" : age >= 14 ? "aged-2" : age >= 7 ? "aged-1" : "";
  const fields = (S.board.fields || []).filter(f => f.on_front && c.fields && c.fields[String(f.id)] !== undefined && c.fields[String(f.id)] !== "" && c.fields[String(f.id)] !== false);
  const prio = c.priority && pu("priority") ? PRIORITIES.find(p => p[0] === c.priority) : null;
  const badges = [
    c.watching ? `<span class="bdg" title="You are watching this card">${ic("eye")}</span>` : "",
    c.due || c.start ? `<span class="bdg ${ds === "done" ? "done" : ds === "past" ? "due-past" : ds === "over" ? "due-over" : ds === "soon" ? "due-soon" : ""} click" data-due title="${ds === "done" ? "This card is complete." : ds === "over" || ds === "past" ? "This card is past due." : ds === "soon" ? "This card is due soon." : "Due date"}">${ic(ds === "done" ? "checksq" : "clock")} ${c.start && c.due ? `${fmtDue(c.start, false)} - ${fmtDue(c.due, false)}` : c.due ? fmtDue(c.due, false) : "Started: " + fmtDue(c.start, false)}</span>` : "",
    c.desc ? `<span class="bdg" title="This card has a description.">${ic("desc")}</span>` : "",
    c.comments ? `<span class="bdg" title="Comments">${ic("cmt")} ${c.comments}</span>` : "",
    c.attachments ? `<span class="bdg" title="Attachments">${ic("clip")} ${c.attachments}</span>` : "",
    c.check[1] ? `<span class="bdg ${c.check[0] === c.check[1] ? "chk-done" : ""}" title="Checklist items">${ic("checksq")} ${c.check[0]}/${c.check[1]}</span>` : "",
    pu("voting") && c.votes && c.votes.length ? `<span class="bdg ${c.votes.includes(S.me.id) ? "voted" : ""}" title="Votes">${ic("thumb")} ${c.votes.length}</span>` : "",
    prio ? `<span class="bdg pr-${prio[0]}" title="Priority: ${prio[1]}">${ic(prio[2])}</span>` : "",
    pu("priority") && c.points != null ? `<span class="bdg fld" title="Story points">${c.points} pts</span>` : "",
    pu("time") && (c.logged || c.estimate) ? `<span class="bdg" title="Time logged / estimate">${ic("timer")} ${+(c.logged || 0).toFixed(2)}${c.estimate ? "/" + c.estimate : ""}h</span>` : "",
    c.location ? `<span class="bdg" title="${esc(c.location)}">${ic("pin")}</span>` : "",
    ...fields.map(f => { const v = c.fields[String(f.id)]; const txt = f.type === "checkbox" ? "✓" : f.type === "list" ? ((f.options.find(o => o.id === v) || {}).text || "") : f.type === "date" ? fmtDue(v, false) : f.type === "number" ? Number(v).toLocaleString() : v; const col = f.type === "list" ? (f.options.find(o => o.id === v) || {}).color : ""; return `<span class="bdg fld" ${col ? `style="background:${labColor(col)}"` : ""} title="${esc(f.name)}">${esc(f.name)}: ${esc(txt)}</span>`; }),
  ].join("");
  const mem = c.members.map(id => person(id)).filter(Boolean).map(p => av(p)).join("");
  const showNo = S.board.prefs.card_numbers;
  const coverHtml = !full && cov.color ? `<div class="cv" style="background:${labColor(cov.color)}"></div>` : !full && cov.url ? `<div class="cv img" style="background-color:${cov.edge || "#DCDFE4"}"><img src="${esc(cov.url)}" loading="lazy" alt=""></div>` : "";
  const fullStyle = full ? (cov.url ? `background-image:url('${esc(cov.full_url || cov.url)}');background-color:${cov.edge || "#555"}` : `background:${labColor(cov.color)}`) : "";
  return `<div class="card ${coverHtml ? "has-cover" : ""} ${full ? "full" + (cov.url ? " img" : "") + (cov.text === "dark" ? " darktext" : "") : ""} ${ageCls} ${c.is_template ? "tpl" : ""} ${c.mirror ? "mirror" : ""}" data-c="${c.id}" style="${fullStyle}">
    ${coverHtml}<div class="cb">
      ${c.mirror ? `<div class="mirror-tag">${ic("mirror", "s12")} ${esc(c.mirror.board || "")}</div>` : ""}
      ${c.is_template ? `<div class="tpl-tag">${ic("tpl", "s12")} This card is a template.</div>` : ""}
      ${!full && labels.length ? `<div class="labels">${labels.map(l => labHtml(l)).join("")}</div>` : ""}
      <div class="title">${S.board.role !== "observer" && !full ? `<button class="done-c ${c.due_complete ? "on" : ""}" data-done title="${c.due_complete ? "Mark incomplete" : "Mark complete"}">${c.due_complete ? ic("check", "s12") : ""}</button>` : ""}<span class="tx">${showNo ? `<span class="num">#${c.no}</span>` : ""}${esc(c.title)}</span></div>
      ${badges || mem ? `<div class="foot"><div class="badges">${badges}</div>${mem ? `<div class="mem">${mem}</div>` : ""}</div>` : ""}
    </div>${S.board.role !== "observer" ? `<button class="edit" data-qe title="Edit card">${ic("edit", "s14")}</button>` : ""}</div>`;
}
function wireCard(el) {
  const cid = +el.dataset.c;
  el.onmouseenter = () => HOVER_CARD = cid; el.onmouseleave = () => { if (HOVER_CARD === cid) HOVER_CARD = null; };
  el.addEventListener("click", e => {
    if (el._dragged) { el._dragged = false; return; }
    if (e.target.closest("[data-qe]")) { e.stopPropagation(); quickEdit(cid); return; }
    if (e.target.closest("[data-done]")) { e.stopPropagation(); const c = S.cards[cid]; saveCard(cid, { due_complete: !c.due_complete }); return; }
    if (e.target.closest(".labels .lab")) { e.stopPropagation(); document.body.classList.toggle("lab-open"); try { localStorage.setItem("kb_lab_open", document.body.classList.contains("lab-open") ? "1" : ""); } catch (er) {} return; }
    if (e.target.closest("[data-due]") && S.board.role !== "observer") { e.stopPropagation(); const c = S.cards[cid]; if (c.due) saveCard(cid, { due_complete: !c.due_complete }); return; }
    go(`#/b/${S.board.id}/c/${cid}`);      // a mirror opens here too, showing the card it mirrors
  });
  el.addEventListener("contextmenu", e => { if (S.board.role === "observer") return; e.preventDefault(); quickEdit(cid); });
  el.addEventListener("pointerdown", e => { if (e.button !== 0 || e.target.closest("button")) return; startDrag(e, "card", cid, el); });
}
function renderCardEl(cid) {
  const old = document.querySelector(`.card[data-c="${cid}"]`), c = S.cards[cid]; if (!old || !c) return;
  const n = h(cardHtml(c)); old.replaceWith(n); wireCard(n); n.classList.toggle("filtered-out", !matchFilter(c));
}
function archiveCard(cid) {
  saveCard(cid, { closed: true }).then(() => toast("Card archived", { undo: () => saveCard(cid, { closed: false }) })).catch(() => {});
  if (S.openCard === cid) go(`#/b/${S.board.id}`);
}

// ---------- drag and drop (cards and lists), mouse and touch ----------
window.DRAG = null;
function startDrag(e, kind, id, el) {
  if (S.board.role === "observer") return;
  const sx = e.clientX, sy = e.clientY, touch = e.pointerType === "touch";
  let started = false, timer = null, cancelled = false;
  const begin = () => {
    started = true; const r = el.getBoundingClientRect();
    const ghost = (kind === "list" ? el.querySelector(".lst") : el).cloneNode(true);
    ghost.classList.add("ghost"); ghost.style.width = r.width - (kind === "list" ? 12 : 0) + "px"; ghost.style.left = (kind === "list" ? r.left + 6 : r.left) + "px"; ghost.style.top = r.top + "px";
    if (kind === "list") ghost.style.height = el.querySelector(".lst").offsetHeight + "px";
    document.body.appendChild(ghost);
    const ph = kind === "card" ? h(`<div class="ph" style="height:${r.height}px"></div>`) : h(`<div class="lw ph-list" style="--phh:${el.querySelector(".lst").offsetHeight}px"><div></div></div>`);
    el.after(ph); el.style.display = "none";
    window.DRAG = { kind, id, el, ghost, ph, dx: sx - r.left, dy: sy - r.top };
    document.body.classList.add("dragging"); closePops();
  };
  const move = ev => {
    if (cancelled) return;
    if (!started) {
      if (touch) { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) > 8) { clearTimeout(timer); cancelled = true; cleanup(); } return; }
      if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 5) return;
      begin();
    }
    ev.preventDefault();
    const D = window.DRAG; D.x = ev.clientX; D.y = ev.clientY;
    D.ghost.style.left = ev.clientX - D.dx + "px"; D.ghost.style.top = ev.clientY - D.dy + "px";
    placeHolder(ev.clientX, ev.clientY); autoScroll(ev.clientX, ev.clientY);
  };
  const up = async ev => {
    clearTimeout(timer); cleanup();
    if (!started) return;
    el._dragged = true; setTimeout(() => el._dragged = false, 50);
    const D = window.DRAG; window.DRAG = null; document.body.classList.remove("dragging"); cancelAnimationFrame(SCROLL_RAF); SCROLL_RAF = null;
    D.ghost.remove();
    if (kind === "card") await dropCard(D); else await dropList(D);
  };
  const cancel = ev => { if (touch && started) return; up(ev); };       // on a phone the browser cancels pointers once it scrolls; a picked-up card is not dropped for that
  const tmove = ev => { if (started) { ev.preventDefault(); const t = ev.touches[0]; if (t) move({ clientX: t.clientX, clientY: t.clientY, preventDefault() {} }); } };
  const tend = ev => { if (started) up(ev); };
  const cleanup = () => { document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up); document.removeEventListener("pointercancel", cancel);
    document.removeEventListener("touchmove", tmove); document.removeEventListener("touchend", tend); document.removeEventListener("touchcancel", tend); };
  document.addEventListener("pointermove", move, { passive: false }); document.addEventListener("pointerup", up); document.addEventListener("pointercancel", cancel);
  if (touch) {
    document.addEventListener("touchmove", tmove, { passive: false }); document.addEventListener("touchend", tend); document.addEventListener("touchcancel", tend);
    timer = setTimeout(() => { if (!cancelled) { begin(); if (navigator.vibrate) navigator.vibrate(15); } }, 260);
  }
}
function placeHolder(x, y) {
  const D = window.DRAG;
  if (D.kind === "card") {
    const lws = $$(".lw[data-l]:not(.collapsed)");
    let lw = lws.find(w => { const r = w.getBoundingClientRect(); return x >= r.left && x <= r.right; });
    if (!lw) { lw = lws.reduce((best, w) => { const r = w.getBoundingClientRect(); const d = Math.min(Math.abs(x - r.left), Math.abs(x - r.right)); return !best || d < best.d ? { w, d } : best; }, null); lw = lw && lw.w; }
    if (!lw) return;
    const box = lw.querySelector("[data-cards]"); const cards = $$(".card:not(.filtered-out)", box).filter(c => c !== D.el);
    let before = null;
    for (const c of cards) { const r = c.getBoundingClientRect(); if (y < r.top + r.height / 2) { before = c; break; } }
    if (before) { if (D.ph.nextSibling !== before) box.insertBefore(D.ph, before); }
    else { const pad = box.querySelector(".pad"); if (D.ph.nextSibling !== pad) box.insertBefore(D.ph, pad); }
  } else {
    const wrap = $("#lists"); const lws = $$(".lw[data-l]", wrap).filter(w => w !== D.el);
    let before = null;
    for (const w of lws) { const r = w.getBoundingClientRect(); if (x < r.left + r.width / 2) { before = w; break; } }
    if (before) { if (D.ph.nextSibling !== before) wrap.insertBefore(D.ph, before); }
    else { const al = $("#addlist-w"); if (al) wrap.insertBefore(D.ph, al); else wrap.appendChild(D.ph); }
  }
}
let SCROLL_RAF = null;
function autoScroll(x, y) {
  const wrap = $("#lists"); if (!wrap) return;
  const step = () => {
    const D = window.DRAG; if (!D) return;
    const r = wrap.getBoundingClientRect(); let moved = false;
    if (D.x < r.left + 60) { wrap.scrollLeft -= 14; moved = true; } else if (D.x > r.right - 60) { wrap.scrollLeft += 14; moved = true; }
    if (D.kind === "card") {
      const lw = $$(".lw[data-l]").find(w => { const q = w.getBoundingClientRect(); return D.x >= q.left && D.x <= q.right; });
      const box = lw && lw.querySelector("[data-cards]");
      if (box) { const q = box.getBoundingClientRect(); if (D.y < q.top + 40) { box.scrollTop -= 12; moved = true; } else if (D.y > q.bottom - 40) { box.scrollTop += 12; moved = true; } }
    }
    if (moved) placeHolder(D.x, D.y);
    SCROLL_RAF = requestAnimationFrame(step);
  };
  if (!SCROLL_RAF) SCROLL_RAF = requestAnimationFrame(step);
}
async function dropCard(D) {
  const lw = D.ph.closest(".lw"); const lid = +lw.dataset.l;
  const c = S.cards[D.id];
  const siblings = []; let n = D.ph.previousElementSibling, m = D.ph.nextElementSibling;
  while (n && !n.classList.contains("card")) n = n.previousElementSibling;
  while (m && !m.classList.contains("card")) m = m.nextElementSibling;
  const bef = n ? S.cards[+n.dataset.c] : null, aft = m ? S.cards[+m.dataset.c] : null;
  const pos = !bef && !aft ? 65536 : !bef ? aft.pos / 2 : !aft ? bef.pos + 65536 : (bef.pos + aft.pos) / 2;
  D.ph.replaceWith(D.el); D.el.style.display = "";
  if (c.list_id === lid && Math.abs(c.pos - pos) < 1e-9) return;
  if (c.list_id === lid && bef && aft && c.pos > bef.pos && c.pos < aft.pos) return;
  const patch = { pos }; if (c.list_id !== lid) patch.list_id = lid;
  c.pos = pos; c.list_id = lid;
  updateListCounts();
  try { await saveCard(D.id, patch, { noRender: true }); } catch (e) { reloadBoard(true); }
}
async function dropList(D) {
  const prev = D.ph.previousElementSibling, next = D.ph.nextElementSibling;
  const bef = prev && prev.dataset.l ? S.lists.find(l => l.id === +prev.dataset.l) : null;
  const aft = next && next.dataset.l ? S.lists.find(l => l.id === +next.dataset.l) : null;
  D.ph.replaceWith(D.el); D.el.style.display = "";
  const l = S.lists.find(x => x.id === D.id);
  const pos = !bef && !aft ? l.pos : !bef ? aft.pos / 2 : !aft ? bef.pos + 65536 : (bef.pos + aft.pos) / 2;
  if (Math.abs(pos - l.pos) < 1e-9) return;
  l.pos = pos; S.lists.sort((a, b) => a.pos - b.pos);
  try { await PATCH(`/store/kb/lists/${D.id}`, { pos }); reloadBoard(true); } catch (e) { fail(e); reloadBoard(true); }
}

// ---------- quick edit ----------
function quickEdit(cid) {
  const el = document.querySelector(`.card[data-c="${cid}"]`), c = S.cards[cid]; if (!el || !c) return;
  closePops(); const r = el.getBoundingClientRect();
  const qe = h(`<div id="qe"><div class="qc" style="left:${r.left}px;top:${r.top}px;width:${r.width}px">
      <div class="qcard">${c.cover && c.cover.color ? `<div style="height:32px;background:${labColor(c.cover.color)}"></div>` : ""}<div style="padding:8px 12px 0">${c.labels.length ? `<div class="labels" style="display:flex;gap:4px;flex-wrap:wrap">${c.labels.map(id => S.board.labels.find(l => l.id === id)).filter(Boolean).map(l => labHtml(l)).join("")}</div>` : ""}</div><textarea></textarea></div>
      <button class="b pri save">Save</button>
      <div class="qbtns">
        <button data-k="open">${ic("board")} Open card</button><button data-k="labels">${ic("tag")} Edit labels</button><button data-k="members">${ic("user")} Change members</button>
        <button data-k="cover">${ic("img")} Change cover</button><button data-k="dates">${ic("clock")} Edit dates</button><button data-k="move">${ic("move")} Move</button>
        <button data-k="copy">${ic("copy")} Copy card</button><button data-k="link">${ic("link")} Copy link</button>${pu("mirror_off") ? "" : `<button data-k="mirror">${ic("mirror")} Mirror</button>`}<button data-k="archive">${ic("archive")} Archive</button>
      </div></div></div>`);
  document.body.appendChild(qe);
  const ta = qe.querySelector("textarea"); ta.value = c.title; ta.focus(); ta.select();
  const btns = qe.querySelector(".qbtns"), qc = qe.querySelector(".qc");
  const right = r.right + 8 + 180 < innerWidth; btns.style.left = right ? (r.width + 8) + "px" : "auto"; if (!right) btns.style.right = (r.width + 8) + "px";
  const top = Math.min(r.top, innerHeight - qc.offsetHeight - 16); if (top < r.top) qc.style.top = Math.max(8, top) + "px";
  if (innerWidth < 600) { qc.style.left = "8px"; qc.style.width = "calc(100vw - 16px)"; btns.style.position = "static"; btns.style.marginTop = "8px"; btns.style.flexDirection = "row"; btns.style.flexWrap = "wrap"; }
  const save = () => { const v = ta.value.trim(); qe.remove(); if (v && v !== c.title) saveCard(cid, { title: v }); };
  qe.querySelector(".save").onclick = save;
  ta.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } if (e.key === "Escape") qe.remove(); };
  qe.addEventListener("mousedown", e => { if (e.target === qe) save(); });
  qe.setAttribute("data-keep-pop", "1");
  const k = (s, fn) => qe.querySelector(`[data-k="${s}"]`) && (qe.querySelector(`[data-k="${s}"]`).onclick = e => fn(e.currentTarget));
  k("open", () => { qe.remove(); go(`#/b/${S.board.id}/c/${cid}`); });
  k("labels", a => labelsPop(a, cid)); k("members", a => membersPop(a, cid)); k("dates", a => datesPop(a, cid));
  k("cover", async a => { await loadFullCard(cid, true, true); coverPop(a, cid); });
  k("move", a => moveCopyPop(a, cid, "move")); k("copy", async a => { await loadFullCard(cid, true, true); moveCopyPop(a, cid, "copy"); }); k("mirror", a => moveCopyPop(a, cid, "mirror"));
  k("link", () => { copyText(cardUrl(S.board.id, cid), "Link copied"); });
  k("archive", () => { qe.remove(); archiveCard(cid); });
}

// ---------- side panels: Inbox, Planner ----------
async function sidePanel(kind) {
  const old = $("#side-panel"); if (old) old.remove();
  S.side = kind; document.body.classList.toggle("with-side", !!kind);
  ["inbox", "planner"].forEach(k => $("#dk-" + k).classList.toggle("on", kind === k)); $("#dk-board").classList.toggle("on", !kind);
  if (!kind) return;
  const p = h(`<aside id="side-panel"><div class="sp-h">${ic(kind === "inbox" ? "inbox" : "cal", "s20")}<h2>${kind === "inbox" ? "Inbox" : "Planner"}</h2><button class="x" data-x>${ic("x")}</button></div><div class="sp-b"><div class="spin dk" style="margin:24px auto"></div></div></aside>`);
  document.body.appendChild(p); p.querySelector("[data-x]").onclick = () => sidePanel(null);
  const body = p.querySelector(".sp-b");
  if (kind === "inbox") {
    const ib = await GET("/store/kb/inbox"); const lid = ib.lists[0].id;
    const draw = () => {
      body.innerHTML = `<div class="composer" style="padding:0;margin-bottom:12px"><textarea placeholder="Add a card… (Enter to save)" id="ib-new"></textarea></div>
        <p class="muted" style="margin:-4px 0 12px">Jot it down here, then drag or move it onto a board.</p>
        ${ib.cards.map(c => `<div class="pl-card" data-c="${c.id}"><b>${esc(c.title)}</b><small>${c.due ? "Due " + fmtDue(c.due) : "Added " + ago(c.created)}</small><div style="display:flex;gap:6px;margin-top:6px"><button class="b sm" data-mv="${c.id}">${ic("move", "s14")} Move to board</button><button class="b sm" data-ar="${c.id}">${ic("archive", "s14")}</button></div></div>`).join("") || '<div class="empty" style="padding:24px 0"><b>Your Inbox is empty</b>Cards you add here are only seen by you.</div>'}`;
      const t = $("#ib-new"); t.onkeydown = async e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); const v = t.value.trim(); if (!v) return; await POST(`/store/kb/lists/${lid}/cards`, { title: v }); const n = await GET("/store/kb/inbox"); ib.cards = n.cards; draw(); $("#ib-new").focus(); } };
      $$("[data-mv]", body).forEach(b => b.onclick = async e => {
        e.stopPropagation(); const cid = +b.dataset.mv; const boards = (await refreshBoards()).boards.filter(x => !x.closed);
        let bid = S.board ? S.board.id : (boards[0] || {}).id; let lists = bid ? (await boardListsFor(bid)).lists : [];
        const q = pop(b, "Move to board", `<label class="fl" style="margin-top:0">Board</label><select class="t" data-b>${boards.map(x => `<option value="${x.id}" ${x.id === bid ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select><label class="fl">List</label><select class="t" data-l>${lists.map(l => `<option value="${l.id}">${esc(l.title)}</option>`).join("")}</select><button class="b pri" style="margin-top:12px" data-go>Move</button>`);
        q.querySelector("[data-b]").onchange = async ev => { bid = +ev.target.value; lists = (await boardListsFor(bid)).lists; q.querySelector("[data-l]").innerHTML = lists.map(l => `<option value="${l.id}">${esc(l.title)}</option>`).join(""); };
        q.querySelector("[data-go]").onclick = async () => { closePops(); try { await PATCH(`/store/kb/cards/${cid}`, { board_id: bid, list_id: +q.querySelector("[data-l]").value }); ib.cards = ib.cards.filter(x => x.id !== cid); draw(); if (S.board && S.board.id === bid) reloadBoard(true); toast("Moved"); } catch (er) { fail(er); } };
      });
      $$("[data-ar]", body).forEach(b => b.onclick = async e => { e.stopPropagation(); await PATCH(`/store/kb/cards/${b.dataset.ar}`, { closed: true }); ib.cards = ib.cards.filter(x => x.id !== +b.dataset.ar); draw(); });
    };
    draw();
  } else {
    const start = new Date(); start.setDate(start.getDate() - 7); const end = new Date(); end.setDate(end.getDate() + 45);
    const d = await GET(`/store/kb/planner?start=${isoDay(start)}&end=${isoDay(end)}`);
    const by = {}; d.cards.forEach(c => { const k = (c.due || c.start).slice(0, 10); (by[k] = by[k] || []).push(c); });
    const td = isoDay(new Date());
    const days = Object.keys(by).sort();
    body.innerHTML = days.length ? days.map(k => { const dd = parseDue(k); return `<div class="pl-day ${k === td ? "td" : ""}"><h4>${k === td ? "Today · " : ""}${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dd.getDay()]} ${MON[dd.getMonth()]} ${dd.getDate()}</h4>${by[k].map(c => `<div class="pl-card" data-b="${c.board_id}" data-c="${c.id}" style="border-left:4px solid ${bgBase(c.bg)}"><b style="${c.due_complete ? "text-decoration:line-through;color:var(--text-subtle)" : ""}">${esc(c.title)}</b><small>${esc(c.board)}${c.due && c.due.includes("T") ? " · " + fmtDue(c.due).split(", ").pop() : ""}${c.due && !c.due_complete && parseDue(c.due) < new Date() ? " · overdue" : ""}</small></div>`).join("")}</div>`; }).join("")
      : '<div class="empty" style="padding:24px 0"><b>Nothing planned</b>Cards you are on with a start or due date show here, day by day.</div>';
    $$("[data-c]", body).forEach(x => x.onclick = () => go(`#/b/${x.dataset.b}/c/${x.dataset.c}`));
  }
}
