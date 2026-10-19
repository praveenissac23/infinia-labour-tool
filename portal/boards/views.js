/* Estimation > Trello - views: Table, Calendar, Timeline, Dashboard (Jira-style), Mind Map. */
"use strict";
function visibleCards() { return Object.values(S.cards).filter(matchFilter); }
function listTitle(id) { return (S.lists.find(l => l.id === id) || {}).title || ""; }
function labelObjs(c) { return c.labels.map(id => S.board.labels.find(l => l.id === id)).filter(Boolean); }

// ---------- Table ----------
let TSORT = { k: "list", dir: 1 };
function tableView(vb) {
  const cols = [["title", "Card"], ["list", "List"], ["labels", "Labels"], ["members", "Members"], ["due", "Due date"], ["check", "Checklist"],
    ...(pu("priority") ? [["priority", "Priority"], ["points", "Points"]] : []), ...(pu("time") ? [["logged", "Time"]] : []),
    ...(pu("fields") ? S.board.fields.map(f => ["f" + f.id, f.name]) : [])];
  const val = (c, k) => k === "list" ? S.lists.findIndex(l => l.id === c.list_id) * 1e6 + c.pos : k === "title" ? c.title.toLowerCase() : k === "due" ? (c.due || "9999") : k === "labels" ? labelObjs(c).map(l => l.name).join() : k === "members" ? c.members.map(id => (person(id) || {}).name || "").join() : k === "check" ? (c.check[1] ? c.check[0] / c.check[1] : -1) : k === "priority" ? ["highest", "high", "medium", "low", "lowest", ""].indexOf(c.priority) : k === "points" ? (c.points ?? -1) : k === "logged" ? (c.logged || 0) : k.startsWith("f") ? String((c.fields || {})[k.slice(1)] ?? "") : "";
  const cards = visibleCards().sort((a, b) => { const x = val(a, TSORT.k), y = val(b, TSORT.k); return (x > y ? 1 : x < y ? -1 : 0) * TSORT.dir; });
  const cell = (c, k) => {
    if (k === "title") return `<b style="font-weight:500">${esc(c.title)}</b>${S.board.prefs.card_numbers ? ` <span class="muted">#${c.no}</span>` : ""}`;
    if (k === "list") return `<select data-mv="${c.id}" onclick="event.stopPropagation()">${S.lists.map(l => `<option value="${l.id}" ${l.id === c.list_id ? "selected" : ""}>${esc(l.title)}</option>`).join("")}</select>`;
    if (k === "labels") return labelObjs(c).map(l => labHtml(l)).join("");
    if (k === "members") return `<span style="display:flex;gap:2px">${c.members.map(person).filter(Boolean).map(p => av(p)).join("")}</span>`;
    if (k === "due") { const ds = dueState(c); return c.due ? `<span class="bdg ${ds === "done" ? "done" : ds === "past" ? "due-past" : ds === "over" ? "due-over" : ds === "soon" ? "due-soon" : ""}" style="margin:0">${fmtDue(c.due)}</span>` : ""; }
    if (k === "check") return c.check[1] ? `${c.check[0]}/${c.check[1]}` : "";
    if (k === "priority") { const p = PRIORITIES.find(x => x[0] === c.priority); return p ? `<span class="bdg pr-${p[0]}" style="margin:0">${ic(p[2])} ${p[1]}</span>` : ""; }
    if (k === "points") return c.points ?? "";
    if (k === "logged") return c.logged ? `${c.logged}h${c.estimate ? " / " + c.estimate + "h" : ""}` : "";
    if (k.startsWith("f")) { const f = S.board.fields.find(x => x.id === +k.slice(1)); const v = (c.fields || {})[k.slice(1)]; if (v === undefined || v === "") return ""; return f.type === "list" ? esc((f.options.find(o => o.id === v) || {}).text || "") : f.type === "checkbox" ? (v ? "✓" : "") : f.type === "date" ? fmtDue(v, false) : esc(String(v)); }
    return "";
  };
  vb.innerHTML = `<div class="vpanel" style="overflow:auto;max-height:100%"><table class="tv"><thead><tr>${cols.map(([k, l]) => `<th data-s="${k}">${esc(l)} ${TSORT.k === k ? (TSORT.dir > 0 ? "▲" : "▼") : ""}</th>`).join("")}</tr></thead>
    <tbody>${cards.map(c => `<tr data-c="${c.id}">${cols.map(([k]) => `<td>${cell(c, k)}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${cols.length}" class="empty">No cards${filterActive() ? " match the filter" : ""}.</td></tr>`}</tbody></table></div>`;
  $$("th[data-s]", vb).forEach(th => th.onclick = () => { TSORT = { k: th.dataset.s, dir: TSORT.k === th.dataset.s ? -TSORT.dir : 1 }; tableView(vb); });
  $$("tr[data-c]", vb).forEach(tr => tr.onclick = e => { if (e.target.closest("select")) return; go(`#/b/${S.board.id}/c/${tr.dataset.c}`); });
  $$("[data-mv]", vb).forEach(s => s.onchange = () => saveCard(+s.dataset.mv, { list_id: +s.value }, { noRender: true }));
}

// ---------- Calendar ----------
let CAL = { y: new Date().getFullYear(), m: new Date().getMonth(), mode: "month" };
function calendarView(vb) {
  const first = new Date(CAL.y, CAL.m, 1);
  let start, days;
  if (CAL.mode === "week") { const t = CAL.week || new Date(); start = new Date(t); start.setDate(t.getDate() - t.getDay()); days = 7; }
  else { start = new Date(first); start.setDate(1 - first.getDay()); days = 42; }
  const by = {};
  visibleCards().forEach(c => { if (c.due) (by[c.due.slice(0, 10)] = by[c.due.slice(0, 10)] || []).push(c); else if (c.start) (by[c.start] = by[c.start] || []).push(c); });
  const td = isoDay(new Date());
  const cells = [];
  for (let i = 0; i < days; i++) { const d = new Date(start); d.setDate(start.getDate() + i); const k = isoDay(d);
    cells.push(`<div class="day ${CAL.mode === "month" && d.getMonth() !== CAL.m ? "o" : ""} ${k === td ? "td" : ""}" data-day="${k}"><span class="dn">${d.getDate() === 1 ? MON[d.getMonth()] + " " : ""}${d.getDate()}</span>
      ${(by[k] || []).sort((a, b) => (a.due || "").localeCompare(b.due || "")).map(c => `<div class="ev ${c.due_complete ? "done" : dueState(c) === "over" || dueState(c) === "past" ? "overdue" : ""}" data-c="${c.id}" draggable="true" title="${esc(c.title)}" style="${c.labels[0] ? "border-left-color:" + labColor((S.board.labels.find(l => l.id === c.labels[0]) || {}).color) : ""}">${c.due && c.due.includes("T") && !["00:00", "17:00"].includes(c.due.slice(11, 16)) ? `<b>${fmtDue(c.due).split(", ").pop()}</b> ` : ""}${esc(c.title)}</div>`).join("")}</div>`); }
  const title = CAL.mode === "week" ? `Week of ${MON[start.getMonth()]} ${start.getDate()}` : `${["January","February","March","April","May","June","July","August","September","October","November","December"][CAL.m]} ${CAL.y}`;
  const noDate = visibleCards().filter(c => !c.due && !c.start).length;
  vb.innerHTML = `<div class="vpanel calv"><div class="ch"><button class="b" data-today>Today</button><button class="x" data-p>${ic("left")}</button><button class="x" data-n>${ic("right")}</button><h3>${title}</h3><span style="flex:1"></span>
      <span class="muted">${noDate} card${noDate === 1 ? "" : "s"} without dates · drag a card to another day to change its date</span>
      <button class="b ${CAL.mode === "week" ? "on" : ""}" data-mode="week">Week</button><button class="b ${CAL.mode === "month" ? "on" : ""}" data-mode="month">Month</button></div>
    <div class="grid" style="${CAL.mode === "week" ? "grid-auto-rows:minmax(400px,1fr)" : ""}">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => `<div class="dow">${d}</div>`).join("")}${cells.join("")}</div></div>`;
  const shift = n => { if (CAL.mode === "week") { const t = CAL.week || new Date(); t.setDate(t.getDate() + 7 * n); CAL.week = t; } else { CAL.m += n; if (CAL.m < 0) { CAL.m = 11; CAL.y--; } if (CAL.m > 11) { CAL.m = 0; CAL.y++; } } calendarView(vb); };
  vb.querySelector("[data-p]").onclick = () => shift(-1); vb.querySelector("[data-n]").onclick = () => shift(1);
  vb.querySelector("[data-today]").onclick = () => { CAL.y = new Date().getFullYear(); CAL.m = new Date().getMonth(); CAL.week = new Date(); calendarView(vb); };
  $$("[data-mode]", vb).forEach(b => b.onclick = () => { CAL.mode = b.dataset.mode; calendarView(vb); });
  $$(".ev", vb).forEach(e => { e.onclick = () => go(`#/b/${S.board.id}/c/${e.dataset.c}`); e.ondragstart = ev => ev.dataTransfer.setData("text/plain", e.dataset.c); });
  $$(".day", vb).forEach(d => {
    d.ondragover = e => { e.preventDefault(); d.classList.add("over"); }; d.ondragleave = () => d.classList.remove("over");
    d.ondrop = e => { e.preventDefault(); d.classList.remove("over"); const cid = +e.dataTransfer.getData("text/plain"); const c = S.cards[cid]; if (!c) return; const t = c.due && c.due.includes("T") ? c.due.slice(11, 16) : "17:00"; saveCard(cid, { due: `${d.dataset.day}T${t}` }, { noRender: true }).then(() => calendarView(vb)); };
    d.ondblclick = e => { if (e.target.closest(".ev")) return; const lid = S.lists[0] && S.lists[0].id; if (!lid) return; const t = prompt("New card due " + d.dataset.day); if (t && t.trim()) POST(`/store/kb/lists/${lid}/cards`, { title: t.trim() }).then(r => PATCH(`/store/kb/cards/${r.id}`, { due: d.dataset.day + "T17:00" })).then(() => reloadBoard(true)).catch(fail); };
  });
}

// ---------- Timeline (Gantt) ----------
let TL = { group: "list", zoom: 28 };
function timelineView(vb) {
  const cards = visibleCards().filter(c => c.due || c.start);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  let min = new Date(today), max = new Date(today); min.setDate(min.getDate() - 14); max.setDate(max.getDate() + 45);
  cards.forEach(c => { const s = parseDue(c.start || c.due), e = parseDue(c.due || c.start); if (s < min) min = new Date(s); if (e > max) max = new Date(e); });
  min.setDate(min.getDate() - 3); max.setDate(max.getDate() + 7); min.setHours(0, 0, 0, 0);
  const nDays = Math.round((max - min) / 86400000) + 1, W = TL.zoom;
  const x = d => Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - min) / 86400000) * W;
  const groups = TL.group === "list" ? S.lists.map(l => ({ key: l.id, title: l.title, cards: cards.filter(c => c.list_id === l.id) }))
    : [...S.board.members.map(m => ({ key: m.id, title: m.name, cards: cards.filter(c => c.members.includes(m.id)) })), { key: 0, title: "No members", cards: cards.filter(c => !c.members.length) }];
  const scale = []; for (let i = 0; i < nDays; i++) { const d = new Date(min); d.setDate(min.getDate() + i); scale.push(`<div class="dd ${[0, 6].includes(d.getDay()) ? "we" : ""} ${isoDay(d) === isoDay(today) ? "td" : ""}" style="width:${W}px">${d.getDate() === 1 || i === 0 ? `<b>${MON[d.getMonth()]}</b><br>` : "<br>"}${W >= 20 ? d.getDate() : ""}</div>`); }
  const rows = groups.filter(g => g.cards.length || TL.group === "list").map(g => {
    const lanes = []; const placed = g.cards.sort((a, b) => (a.start || a.due).localeCompare(b.start || b.due)).map(c => {
      const s = parseDue(c.start || c.due), e = parseDue(c.due || c.start); const l = x(s), w = Math.max(W, x(e) - l + W);
      let lane = lanes.findIndex(end => end <= l); if (lane < 0) { lane = lanes.length; lanes.push(0); } lanes[lane] = l + w + 4;
      const ds = dueState(c);
      return `<div class="tl-bar ${c.due_complete ? "done" : ds === "over" || ds === "past" ? "over" : ""}" data-c="${c.id}" style="left:${l}px;width:${w}px;top:${6 + lane * 34}px;${c.labels[0] && !c.due_complete && !(ds === "over" || ds === "past") ? "background:" + labColor((S.board.labels.find(z => z.id === c.labels[0]) || {}).color) : ""}" title="${esc(c.title)} · ${c.start ? fmtDue(c.start, false) + " - " : ""}${fmtDue(c.due, false)}">${esc(c.title)}</div>`;
    }).join("");
    return `<div class="tl-row"><div class="tl-lab">${esc(g.title)} <span class="muted">${g.cards.length}</span></div><div class="tl-track" style="width:${nDays * W}px;height:${Math.max(40, 12 + lanes.length * 34)}px">${placed}</div></div>`;
  }).join("");
  vb.innerHTML = `<div class="vpanel tl"><div class="tl-h"><b>Timeline</b><span class="muted">Bars run from start date to due date. Drag a bar to move its dates; drag its right end to change the due date.</span><span style="flex:1"></span>
      <span class="muted">Group by</span><button class="b sm ${TL.group === "list" ? "on" : ""}" data-g="list">List</button><button class="b sm ${TL.group === "member" ? "on" : ""}" data-g="member">Member</button>
      <span class="muted" style="margin-left:8px">Zoom</span><button class="b sm" data-z="-1">−</button><button class="b sm" data-z="1">+</button><button class="b sm" data-today>Today</button></div>
    <div class="tl-b"><div class="tl-grid" style="width:${220 + nDays * W}px"><div class="tl-scale"><div class="sl"></div>${scale.join("")}</div>${rows || '<div class="empty">No cards with dates yet. Add start and due dates to see them here.</div>'}<div class="today-line" style="left:${220 + x(today) + W / 2}px"></div></div></div></div>`;
  $$("[data-g]", vb).forEach(b => b.onclick = () => { TL.group = b.dataset.g; timelineView(vb); });
  $$("[data-z]", vb).forEach(b => b.onclick = () => { TL.zoom = Math.max(8, Math.min(60, TL.zoom + (+b.dataset.z) * 8)); timelineView(vb); });
  const tb = vb.querySelector(".tl-b"); const scrollToday = () => { tb.scrollLeft = Math.max(0, x(today) - 200); }; scrollToday();
  vb.querySelector("[data-today]").onclick = scrollToday;
  $$(".tl-bar", vb).forEach(bar => {
    let sx = 0, mode = null, orig = 0, ow = 0, moved = false;
    bar.addEventListener("pointerdown", e => { sx = e.clientX; const r = bar.getBoundingClientRect(); mode = e.clientX > r.right - 8 ? "end" : "move"; orig = bar.offsetLeft; ow = bar.offsetWidth; moved = false; bar.setPointerCapture(e.pointerId); });
    bar.addEventListener("pointermove", e => { if (!mode) return; const dx = e.clientX - sx; if (Math.abs(dx) > 3) moved = true; if (mode === "move") bar.style.left = orig + Math.round(dx / W) * W + "px"; else bar.style.width = Math.max(W, ow + Math.round(dx / W) * W) + "px"; });
    bar.addEventListener("pointerup", e => {
      const m = mode; mode = null; if (!moved) { go(`#/b/${S.board.id}/c/${bar.dataset.c}`); return; }
      const c = S.cards[+bar.dataset.c]; const shiftDays = Math.round((bar.offsetLeft - orig) / W), extra = Math.round((bar.offsetWidth - ow) / W);
      const add = (s, n) => { if (!s) return ""; const d = parseDue(s); d.setDate(d.getDate() + n); return isoDay(d) + (s.includes("T") ? s.slice(10) : ""); };
      const patch = m === "move" ? { start: c.start ? add(c.start, shiftDays) : "", due: add(c.due, shiftDays) } : { due: add(c.due || c.start, extra) };
      if (!c.due && m === "move") patch.start = add(c.start, shiftDays);
      saveCard(c.id, patch, { noRender: true }).then(() => timelineView(vb));
    });
  });
}

// ---------- Dashboard (Jira-style: workload, distribution, progress) ----------
function donut(parts, size = 150) {
  const tot = parts.reduce((a, p) => a + p.v, 0) || 1; let a0 = -Math.PI / 2; const r = size / 2 - 10, cx = size / 2, cy = size / 2;
  const segs = parts.filter(p => p.v).map(p => { const a1 = a0 + p.v / tot * Math.PI * 2; const large = a1 - a0 > Math.PI ? 1 : 0;
    const d = p.v === tot ? `M${cx} ${cy - r}A${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r}` : `M${cx + r * Math.cos(a0)} ${cy + r * Math.sin(a0)}A${r} ${r} 0 ${large} 1 ${cx + r * Math.cos(a1)} ${cy + r * Math.sin(a1)}`;
    a0 = a1; return `<path d="${d}" stroke="${p.c}" stroke-width="22" fill="none"/>`; }).join("");
  const done = parts[0] ? Math.round(parts[0].v * 100 / tot) : 0;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><circle cx="${cx}" cy="${cy}" r="${r}" stroke="#F1F2F4" stroke-width="22" fill="none"/>${segs}<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="24" font-weight="700" fill="#172B4D">${done}%</text><text x="${cx}" y="${cy + 18}" text-anchor="middle" font-size="12" fill="#626F86">Done</text></svg>`;
}
function dashboardView(vb) {
  const cards = visibleCards(), n = cards.length;
  const now = new Date();
  const done = cards.filter(c => c.due_complete).length;
  const overdue = cards.filter(c => c.due && !c.due_complete && parseDue(c.due) < now).length;
  const soon = cards.filter(c => c.due && !c.due_complete && parseDue(c.due) >= now && parseDue(c.due) - now < 7 * 86400000).length;
  const noDue = cards.filter(c => !c.due).length;
  const chk = cards.reduce((a, c) => [a[0] + c.check[0], a[1] + c.check[1]], [0, 0]);
  const DCOL = ["#57A55A", "#F5A623", "#2E7CF6", "#8F7EE7", "#E774BB", "#6CC3E0", "#94C748", "#C97CF4", "#FCA700", "#F87168"];
  // workload per member - like Jira's "Team workload"
  const people = S.board.members.map(m => ({ m, open: cards.filter(c => c.members.includes(m.id) && !c.due_complete).length, all: cards.filter(c => c.members.includes(m.id)).length }));
  const unassigned = cards.filter(c => !c.members.length && !c.due_complete).length;
  const openTot = cards.filter(c => !c.due_complete).length || 1;
  const wl = [...people.filter(p => p.all).sort((a, b) => b.open - a.open), ...(unassigned ? [{ m: { id: 0, name: "Unassigned", initials: "?" }, open: unassigned, all: unassigned }] : [])];
  const bars = (rows, max) => `<div class="hbars">${rows.map(r => `<div class="hb2"><span class="nm" title="${esc(r.name)}">${r.icon || ""}${esc(r.name)}</span><span class="tb"><i style="width:${max ? Math.max(2, r.v * 100 / max) : 0}%;background:${r.c}"></i></span><span class="v">${r.v}</span></div>`).join("")}</div>`;
  const perList = S.lists.map((l, i) => ({ name: l.title, v: cards.filter(c => c.list_id === l.id).length, c: DCOL[i % DCOL.length] }));
  const perLabel = [...S.board.labels.map(l => ({ name: l.name || l.color.replace("_", " "), v: cards.filter(c => c.labels.includes(l.id)).length, c: labColor(l.color) })), { name: "No label", v: cards.filter(c => !c.labels.length).length, c: "#DCDFE4" }].filter(r => r.v);
  const timeRows = Object.entries(S.board.time || {}).map(([uid, h]) => ({ name: (person(+uid) || {}).name || "Someone", v: h, c: "#22A06B" })).sort((a, b) => b.v - a.v);
  const pts = pu("priority") ? S.lists.map((l, i) => ({ name: l.title, v: cards.filter(c => c.list_id === l.id).reduce((a, c) => a + (c.points || 0), 0), c: DCOL[i % DCOL.length] })).filter(r => r.v) : [];
  const prio = pu("priority") ? PRIORITIES.map(([k, l], i) => ({ name: l, v: cards.filter(c => c.priority === k).length, c: ["#C9372C", "#F87168", "#FCA700", "#669DF1", "#1868DB"][i] })).filter(r => r.v) : [];
  const due = [{ v: done, c: "#22A06B", l: "Complete" }, { v: overdue, c: "#C9372C", l: "Overdue" }, { v: soon, c: "#F5CD47", l: "Due this week" }, { v: Math.max(0, n - done - overdue - soon - noDue), c: "#669DF1", l: "Due later" }, { v: noDue, c: "#DCDFE4", l: "No due date" }];
  const recentDone = cards.filter(c => c.due_complete).sort((a, b) => (b.updated || "").localeCompare(a.updated || "")).slice(0, 6);
  const overdueList = cards.filter(c => c.due && !c.due_complete && parseDue(c.due) < now).sort((a, b) => a.due.localeCompare(b.due)).slice(0, 8);
  vb.innerHTML = `<div class="dash">
    <div class="kpis">${[[n, "Cards" + (filterActive() ? " (filtered)" : "")], [done, "Complete"], [overdue, "Overdue"], [soon, "Due in the next 7 days"], [chk[1] ? Math.round(chk[0] * 100 / chk[1]) + "%" : "-", `Checklist items done (${chk[0]}/${chk[1]})`], [S.board.members.length, "Members"]].map(([v, l], i) => `<div class="vpanel kpi"><b style="${i === 2 && overdue ? "color:var(--danger)" : ""}">${v}</b><span>${l}</span></div>`).join("")}</div>
    <div class="vpanel tilebox"><h3>${ic("users")} Team workload</h3><table class="wl"><thead><tr><th>Assignee</th><th>Work distribution</th><th style="text-align:right">Count</th></tr></thead><tbody>
      ${wl.map((p, i) => `<tr><td><span class="who">${p.m.id ? av(p.m) : '<span class="av" style="background:#DCDFE4;color:#44546F">?</span>'} ${esc(p.m.name)}</span></td><td><span class="dist"><span class="tb"><i style="width:${Math.round(p.open * 100 / openTot)}%;background:${DCOL[i % DCOL.length]}"></i></span><span style="width:36px;text-align:right;font-size:13px">${Math.round(p.open * 100 / openTot)}%</span></span></td><td class="cnt">${p.open}</td></tr>`).join("") || '<tr><td colspan="3" class="muted">Put people on cards to see their workload.</td></tr>'}</tbody></table></div>
    <div class="vpanel tilebox"><h3>${ic("clock")} Progress & due dates</h3><div class="donut-wrap">${donut(due)}<div class="legend">${due.map(p => `<div class="lg"><i style="background:${p.c}"></i>${p.l}: <b>${p.v}</b></div>`).join("")}</div></div></div>
    <div class="vpanel tilebox"><h3>${ic("board")} Cards per list</h3>${bars(perList, Math.max(1, ...perList.map(r => r.v)))}</div>
    <div class="vpanel tilebox"><h3>${ic("tag")} Cards per label</h3>${bars(perLabel, Math.max(1, ...perLabel.map(r => r.v)))}</div>
    ${prio.length ? `<div class="vpanel tilebox"><h3>${ic("flag")} Priority</h3>${bars(prio, Math.max(1, ...prio.map(r => r.v)))}</div>` : ""}
    ${pts.length ? `<div class="vpanel tilebox"><h3>${ic("points")} Story points per list</h3>${bars(pts, Math.max(1, ...pts.map(r => r.v)))}</div>` : ""}
    ${timeRows.length ? `<div class="vpanel tilebox"><h3>${ic("timer")} Hours logged per person</h3>${bars(timeRows, Math.max(1, ...timeRows.map(r => r.v)))}</div>` : ""}
    <div class="vpanel tilebox"><h3 style="color:var(--danger)">${ic("clock")} Overdue</h3>${overdueList.map(c => `<div class="pl-card" data-c="${c.id}"><b>${esc(c.title)}</b><small>${esc(listTitle(c.list_id))} · due ${fmtDue(c.due)}</small></div>`).join("") || '<p class="muted">Nothing overdue. 🎉</p>'}</div>
    <div class="vpanel tilebox"><h3>${ic("checksq")} Recently completed</h3>${recentDone.map(c => `<div class="pl-card" data-c="${c.id}"><b>${esc(c.title)}</b><small>${esc(listTitle(c.list_id))}</small></div>`).join("") || '<p class="muted">Mark cards complete to see them here.</p>'}</div>
  </div>`;
  $$("[data-c]", vb).forEach(e => e.onclick = () => go(`#/b/${S.board.id}/c/${e.dataset.c}`));
}

// ---------- Mind Map ----------
function mindmapView(vb) {
  const lists = S.lists.map(l => ({ l, cards: cardsOf(l.id).filter(matchFilter) }));
  const rowH = 30, gapL = 16;
  let y = 30; const nodes = [];
  lists.forEach(g => { const h = Math.max(1, g.cards.length) * rowH; nodes.push({ g, y, h }); y += h + gapL; });
  const H = Math.max(y + 20, 400), W = 1100, bx = 40, by = H / 2, lx = 320, cx = 640;
  const svg = [];
  const tw = (t, max) => t.length > max ? t.slice(0, max - 1) + "…" : t;
  nodes.forEach((n, i) => {
    const ly = n.y + n.h / 2, col = ["#0C66E4", "#1F845A", "#C25100", "#AE4787", "#6E5DC6", "#227D9B", "#5B7F24", "#943D73"][i % 8];
    svg.push(`<path d="M${bx + 200} ${by} C ${bx + 260} ${by}, ${lx - 60} ${ly}, ${lx} ${ly}" stroke="${col}" stroke-width="2.5" fill="none" opacity=".7"/>`);
    svg.push(`<g class="mm-l" data-l="${n.g.l.id}" style="cursor:pointer"><rect x="${lx}" y="${ly - 16}" rx="16" width="240" height="32" fill="${col}"/><text x="${lx + 14}" y="${ly + 5}" fill="#fff" font-size="13" font-weight="600">${esc(tw(n.g.l.title, 26))} (${n.g.cards.length})</text></g>`);
    n.g.cards.forEach((c, j) => {
      const cy = n.y + j * rowH + rowH / 2;
      svg.push(`<path d="M${lx + 240} ${ly} C ${lx + 290} ${ly}, ${cx - 50} ${cy}, ${cx} ${cy}" stroke="${col}" stroke-width="1.5" fill="none" opacity=".45"/>`);
      svg.push(`<g class="mm-c" data-c="${c.id}" style="cursor:pointer"><rect x="${cx}" y="${cy - 12}" rx="6" width="420" height="24" fill="#fff" stroke="${c.due_complete ? "#22A06B" : "#DCDFE4"}"/>${c.labels.slice(0, 3).map((id, k) => `<rect x="${cx + 8 + k * 14}" y="${cy - 4}" width="10" height="8" rx="2" fill="${labColor((S.board.labels.find(l => l.id === id) || {}).color)}"/>`).join("")}<text x="${cx + 12 + Math.min(3, c.labels.length) * 14}" y="${cy + 4}" font-size="12" fill="#172B4D" ${c.due_complete ? 'text-decoration="line-through"' : ""}>${esc(tw(c.title, 56))}</text></g>`);
    });
  });
  vb.innerHTML = `<div class="vpanel mm" style="overflow:auto;max-height:100%"><svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <rect x="${bx}" y="${by - 26}" rx="26" width="200" height="52" fill="#172B4D"/><text x="${bx + 100}" y="${by + 6}" fill="#fff" font-size="16" font-weight="700" text-anchor="middle">${esc(tw(S.board.title, 20))}</text>${svg.join("")}</svg></div>`;
  $$(".mm-c", vb).forEach(g => g.onclick = () => go(`#/b/${S.board.id}/c/${g.dataset.c}`));
  $$(".mm-l", vb).forEach(g => g.onclick = () => { setView("board"); setTimeout(() => { const w = document.querySelector(`.lw[data-l="${g.dataset.l}"]`); if (w) w.scrollIntoView({ inline: "center", behavior: "smooth" }); }, 50); });
}
