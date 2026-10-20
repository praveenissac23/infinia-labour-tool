/* Estimation > Trello - popovers: labels, members, dates, checklist, attachment, cover, move, copy, mirror, filter, boards ... */
"use strict";
let POP_STACK = [];
function closePops() { $$(".pop").forEach(p => p.remove()); POP_STACK = []; }
function placePop(p, anchor) {
  const r = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: innerWidth / 2 - 150, bottom: 80, top: 80, right: innerWidth / 2 };
  p.style.maxHeight = ""; const w = p.offsetWidth, hgt = p.offsetHeight;
  let x = r.left, y = p._above && r.top - hgt - 6 > 8 ? r.top - hgt - 6 : r.bottom + 6;
  if (x + w > innerWidth - 8) x = Math.max(8, innerWidth - w - 8);
  if (y + hgt > innerHeight - 8) {
    const below = innerHeight - r.bottom - 14, above = r.top - 14;
    if (below >= 260 || below >= above) { y = r.bottom + 6; p.style.maxHeight = Math.max(160, below) + "px"; }   // stay below, scroll inside (Trello does)
    else { y = Math.max(8, r.top - hgt - 6); if (hgt > above) p.style.maxHeight = above + "px"; }
  }
  if (y < 8) y = 8;
  p.style.left = x + "px"; p.style.top = y + "px";
}
// pop(anchor, title, html, {back, cls}) - a Trello popover; a second one from inside replaces it with a back arrow.
function pop(anchor, title, html, o = {}) {
  const keep = o.keep;
  if (!keep) closePops();
  const p = h(`<div class="pop ${o.cls || ""}"><div class="ph-h">${o.back ? `<button class="x" data-back>${ic("left")}</button>` : "<span></span>"}<h2>${esc(title)}</h2><button class="x" data-x>${ic("x")}</button></div><div class="pb">${html}</div></div>`);
  document.body.appendChild(p);
  p._anchor = anchor; p._above = !!o.above; placePop(p, anchor);
  p.querySelector("[data-x]").onclick = () => closePops();
  if (o.back) p.querySelector("[data-back]").onclick = () => o.back();
  setTimeout(() => { const f = p.querySelector("input.t:not([type=hidden]),textarea.t"); if (f && !o.nofocus) f.focus(); }, 30);
  return p;
}
function subPop(p, title, html, back) { const a = p._anchor; p.remove(); return pop(a, title, html, { back, keep: true }); }
document.addEventListener("mousedown", e => {
  if (e.target.closest(".pop") || e.target.closest("[data-keep-pop]")) return;
  if ($(".pop")) closePops();
}, true);
window.addEventListener("resize", () => $$(".pop").forEach(p => placePop(p, p._anchor)));

// ---------- the card being worked on ----------
function cardOf(cid) { return S.cards[cid] || (S.full && S.full.id === cid ? S.full : null); }
// What a change does to a card, shown at once (add_/remove_ labels and members included).
function applyPatch(o, patch) {
  for (const [k, v] of Object.entries(patch)) {
    const m = k.match(/^(add|remove)_(labels|members)$/);
    if (m) { const cur = (o[m[2]] || []).slice(); if (m[1] === "add") v.forEach(x => { if (!cur.includes(x)) cur.push(x); }); o[m[2]] = m[1] === "add" ? cur : cur.filter(x => !v.includes(x)); }
    else o[k] = v;
  }
}
// Saves for one card go one after another, so quick clicks never undo each other.
const SAVE_Q = {}, SAVE_N = {};
function saveCard(cid, patch, opt = {}) {
  const c = S.cards[cid];
  const before = c ? JSON.parse(JSON.stringify(c)) : null;
  if (c) { applyPatch(c, patch); if (!opt.noRender) renderCardEl(cid); }
  if (S.full && S.full.id === cid) { applyPatch(S.full, patch); if (!opt.noRender && (opt.force || !cardBusy())) renderCardModal(); }
  SAVE_N[cid] = (SAVE_N[cid] || 0) + 1;
  const run = async () => {
    try {
      const r = await PATCH(`/store/kb/cards/${cid}`, patch);
      const cc = S.cards[cid];
      if (r && cc) { if (r.pos !== undefined) cc.pos = r.pos; if (r.list_id) cc.list_id = r.list_id; }
      if (--SAVE_N[cid] === 0) {       // the last of a run of quick changes brings the board up to date
        if (opt.reload !== false) await reloadBoard(true);
        if (S.openCard === cid && opt.reloadCard !== false) await loadFullCard(cid, true);
      }
      return r;
    } catch (e) {
      SAVE_N[cid]--;
      if (before && S.cards[cid]) { S.cards[cid] = before; renderCardEl(cid); }
      fail(e); throw e;
    }
  };
  const p = (SAVE_Q[cid] || Promise.resolve()).catch(() => {}).then(run);
  SAVE_Q[cid] = p;
  return p;
}
// Someone is typing on the open card: it is not redrawn under them.
function cardBusy() {
  const ov = document.getElementById("cm-ov"); if (!ov) return false;
  const a = document.activeElement;
  if (a && ov.contains(a) && (a.tagName === "TEXTAREA" || (a.tagName === "INPUT" && a.type !== "checkbox"))) return true;
  return [...ov.querySelectorAll("#cmt-ed, #desc-ed, [data-ebox] textarea")].some(t => t.value.trim());
}

// ---------- labels ----------
function labelsPop(anchor, cid, opt = {}) {
  if (!cardOf(cid)) return;
  const draw = (q = "") => {
    const c = cardOf(cid) || { labels: [] };
    const ls = S.board.labels.filter(l => !q || (l.name || l.color).toLowerCase().includes(q.toLowerCase()));
    return `<input class="t" placeholder="Search labels..." data-q value="${esc(q)}"><h5>Labels</h5>
      ${ls.map(l => `<div class="lrow"><input type="checkbox" data-l="${l.id}" ${c.labels.includes(l.id) ? "checked" : ""}>${labHtml(l).replace('class="lab', `data-l="${l.id}" class="lab`)}<button class="x" data-e="${l.id}" title="Edit">${ic("edit", "s14")}</button></div>`).join("") || '<div class="muted">No labels match.</div>'}
      <button class="b" style="width:100%;margin-top:8px" data-new>Create a new label</button>
      <hr><button class="b" style="width:100%" data-blind>${document.body.classList.contains("lab-open") ? "Hide label text on cards" : "Show label text on cards"}</button>`;
  };
  const p = pop(anchor, "Labels", draw(), opt);
  const wire = () => {
    const q = p.querySelector("[data-q]"); q.oninput = () => { const v = q.value, pos = q.selectionStart; p.querySelector(".pb").innerHTML = draw(v); wire(); const n = p.querySelector("[data-q]"); n.focus(); n.setSelectionRange(pos, pos); };
    $$("[data-l]", p).forEach(el => el.onclick = e => {
      const id = +el.dataset.l; const has = (cardOf(cid) || { labels: [] }).labels.includes(id);
      saveCard(cid, has ? { remove_labels: [id] } : { add_labels: [id] }).catch(() => {});
      p.querySelector(".pb").innerHTML = draw(q.value); wire();
    });
    $$("[data-e]", p).forEach(b => b.onclick = () => labelEditPop(p, cid, S.board.labels.find(l => l.id === +b.dataset.e), () => labelsPop(anchor, cid, opt)));
    p.querySelector("[data-new]").onclick = () => labelEditPop(p, cid, null, () => labelsPop(anchor, cid, opt));
    p.querySelector("[data-blind]").onclick = () => { document.body.classList.toggle("lab-open"); try { localStorage.setItem("kb_lab_open", document.body.classList.contains("lab-open") ? "1" : ""); } catch (e) {} p.querySelector(".pb").innerHTML = draw(q.value); wire(); };
  };
  wire();
}
const LCOLS = ["green_light", "yellow_light", "orange_light", "red_light", "purple_light", "green", "yellow", "orange", "red", "purple",
  "green_dark", "yellow_dark", "orange_dark", "red_dark", "purple_dark", "blue_light", "sky_light", "lime_light", "pink_light", "black_light",
  "blue", "sky", "lime", "pink", "black", "blue_dark", "sky_dark", "lime_dark", "pink_dark", "black_dark"];
function labelEditPop(p, cid, l, back) {
  let color = l ? l.color : "green";
  const html = `<div class="prev"><span data-prev></span></div><label class="fl">Title</label><input class="t" data-n value="${esc(l ? l.name : "")}">
    <label class="fl">Select a color</label><div class="grid5">${LCOLS.map(c => `<button class="sw ${c === color ? "on" : ""}" data-c="${c}" title="${c.replace("_", " ")}" style="background:var(--l-${c})"></button>`).join("")}</div>
    <button class="b" style="width:100%;margin-top:8px" data-none>${ic("x", "s14")} Remove color</button><hr>
    <div style="display:flex;justify-content:space-between"><button class="b pri" data-save>${l ? "Save" : "Create"}</button>${l ? '<button class="b dng" data-del>Delete</button>' : ""}</div>`;
  const q = subPop(p, l ? "Edit label" : "Create label", html, back);
  const prev = () => { q.querySelector("[data-prev]").outerHTML = labHtml({ color, name: q.querySelector("[data-n]").value }).replace('class="lab', 'data-prev class="lab'); };
  prev(); q.querySelector("[data-n]").oninput = prev;
  $$("[data-c]", q).forEach(b => b.onclick = () => { color = b.dataset.c; $$("[data-c]", q).forEach(x => x.classList.toggle("on", x === b)); prev(); });
  q.querySelector("[data-none]").onclick = () => { color = ""; $$("[data-c]", q).forEach(x => x.classList.remove("on")); prev(); };
  q.querySelector("[data-save]").onclick = async () => {
    const name = q.querySelector("[data-n]").value.trim();
    try {
      if (l) await PATCH(`/store/kb/labels/${l.id}`, { name, color });
      else { const r = await POST(`/store/kb/boards/${S.board.id}/labels`, { name, color }); if (cid && cardOf(cid)) await PATCH(`/store/kb/cards/${cid}`, { add_labels: [r.id] }); }
      await reloadBoard(true); if (S.openCard) await loadFullCard(S.openCard, true); back();
    } catch (e) { fail(e); }
  };
  const del = q.querySelector("[data-del]");
  if (del) del.onclick = () => { const x = subPop(q, "Delete label?", `<p style="margin:0 0 12px">This will remove this label from all cards. There is no undo.</p><button class="b dng" style="width:100%">Delete</button>`, () => labelEditPop(q, cid, l, back));
    x.querySelector(".b.dng").onclick = async () => { try { await DEL(`/store/kb/labels/${l.id}`); await reloadBoard(true); if (S.openCard) await loadFullCard(S.openCard, true); back(); } catch (e) { fail(e); } }; };
}

// ---------- members ----------
function membersPop(anchor, cid, opt = {}) {
  if (!cardOf(cid)) return;
  const draw = (q = "") => {
    const c = cardOf(cid) || { members: [] };
    const ql = q.toLowerCase();
    const bm = S.board.members.filter(m => !q || m.name.toLowerCase().includes(ql) || m.username.toLowerCase().includes(ql));
    const others = S.board.people.filter(p => !S.board.members.some(m => m.id === p.id) && (!q || p.name.toLowerCase().includes(ql) || p.username.toLowerCase().includes(ql))).sort((a, b) => a.name.localeCompare(b.name));
    const row = m => `<div class="memrow" data-u="${m.id}">${av(m, "lg")}<div class="nm">${esc(m.name)}<small>@${esc(m.username)}</small></div>${c.members.includes(m.id) ? `<span class="ck">${ic("check")}</span>` : ""}</div>`;
    const on = bm.filter(m => c.members.includes(m.id)), off = bm.filter(m => !c.members.includes(m.id));
    return `<input class="t" placeholder="Search members" data-q value="${esc(q)}">
      ${on.length ? `<h5>Card members</h5>${on.map(row).join("")}` : ""}
      <h5>Board members</h5>${off.map(row).join("") || '<div class="muted">Everyone on the board is on this card.</div>'}
      ${others.length ? `<h5>Everyone else (added to the board when picked)</h5>${others.map(row).join("")}` : ""}`;
  };
  const p = pop(anchor, "Members", draw(), opt);
  const wire = () => {
    const q = p.querySelector("[data-q]");
    q.oninput = () => { const v = q.value, s = q.selectionStart; p.querySelector(".pb").innerHTML = draw(v); wire(); const n = p.querySelector("[data-q]"); n.focus(); n.setSelectionRange(s, s); };
    $$("[data-u]", p).forEach(r => r.onclick = async () => {
      const id = +r.dataset.u;
      if (!S.board.members.some(m => m.id === id)) { try { await POST(`/store/kb/boards/${S.board.id}/members`, { user_id: id }); await reloadBoard(true); } catch (e) { fail(e); return; } }
      const has = (cardOf(cid) || { members: [] }).members.includes(id);
      const sv = saveCard(cid, has ? { remove_members: [id] } : { add_members: [id] }).catch(() => {});
      p.querySelector(".pb").innerHTML = draw(q.value); wire(); await sv;
    });
  };
  wire();
}
function toggleJoin(cid) { const c = cardOf(cid); if (!c) return; const me = S.me.id; saveCard(cid, c.members.includes(me) ? { remove_members: [me] } : { add_members: [me] }).catch(() => {}); }

// ---------- dates ----------
function datesPop(anchor, cid, opt = {}) {
  const c = cardOf(cid); if (!c) return;
  let start = c.start || "", due = c.due ? c.due.slice(0, 10) : "", time = c.due && c.due.includes("T") ? c.due.slice(11, 16) : "17:00";
  let useStart = !!start, useDue = !!due || !start, reminder = c.reminder ?? -1;
  if (!due && useDue) { const d = new Date(); d.setDate(d.getDate() + 1); due = isoDay(d); }
  let month = parseDue(due || start || isoDay(new Date())); month = new Date(month.getFullYear(), month.getMonth(), 1);
  let pickStart = false;
  const draw = () => {
    const first = new Date(month), firstDow = first.getDay(), days = [];
    const gs = new Date(first); gs.setDate(1 - firstDow);
    for (let i = 0; i < 42; i++) { const d = new Date(gs); d.setDate(gs.getDate() + i); days.push(d); }
    const tdy = isoDay(new Date());
    const cell = d => { const k = isoDay(d); const cls = [d.getMonth() !== month.getMonth() ? "o" : "", k === tdy ? "td" : "",
      (useDue && k === due) || (useStart && k === start) ? "sel" : "", useStart && useDue && start && due && k > start && k < due ? "rng" : ""].join(" ");
      return `<td><button class="${cls}" data-d="${k}">${d.getDate()}</button></td>`; };
    return `<div class="cal"><div class="cal-h"><button class="x" data-m="-12" title="Previous year">«</button><button class="x" data-m="-1">${ic("left")}</button><span>${["January","February","March","April","May","June","July","August","September","October","November","December"][month.getMonth()]} ${month.getFullYear()}</span><button class="x" data-m="1">${ic("right")}</button><button class="x" data-m="12" title="Next year">»</button></div>
      <table><tr>${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map(x => `<th>${x}</th>`).join("")}</tr>${[0,1,2,3,4,5].map(r => `<tr>${days.slice(r*7, r*7+7).map(cell).join("")}</tr>`).join("")}</table></div>
      <label class="fl">Start date</label><div class="drow"><input type="checkbox" data-us ${useStart ? "checked" : ""}><input class="t" type="date" data-s value="${start}" ${useStart ? "" : "disabled"} style="width:150px"></div>
      <label class="fl">Due date</label><div class="drow"><input type="checkbox" data-ud ${useDue ? "checked" : ""}><input class="t" type="date" data-dd value="${due}" ${useDue ? "" : "disabled"} style="width:150px"><input class="t" type="time" data-t value="${time}" ${useDue ? "" : "disabled"} style="width:110px"></div>
      <label class="fl">Set due date reminder ${tip("Members and watchers of the card are told this long before it is due.")}</label><select class="t" data-r>${[[-1,"None"],[0,"At time of due date"],[5,"5 Minutes before"],[10,"10 Minutes before"],[15,"15 Minutes before"],[60,"1 Hour before"],[120,"2 Hours before"],[1440,"1 Day before"],[2880,"2 Days before"]].map(([v,l]) => `<option value="${v}" ${+reminder === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <p class="muted" style="margin:6px 0 12px">Reminders go to members and watchers of this card.</p>
      <button class="b pri" style="width:100%" data-save>Save</button><button class="b" style="width:100%;margin-top:8px" data-rm>Remove</button>`;
  };
  const p = pop(anchor, "Dates", draw(), { ...opt, nofocus: true });
  const wire = () => {
    $$("[data-m]", p).forEach(b => b.onclick = () => { month.setMonth(month.getMonth() + +b.dataset.m); p.querySelector(".pb").innerHTML = draw(); wire(); });
    $$("[data-d]", p).forEach(b => b.onclick = () => {
      const k = b.dataset.d;
      if (useStart && (pickStart || !useDue)) { start = k; pickStart = false; if (due && due < start) due = start; }
      else if (useDue) { due = k; if (useStart && start > due) start = due; pickStart = useStart; }
      p.querySelector(".pb").innerHTML = draw(); wire();
    });
    p.querySelector("[data-us]").onchange = e => { useStart = e.target.checked; if (useStart && !start) { const d = parseDue(due || isoDay(new Date())); d.setDate(d.getDate() - 1); start = isoDay(d); } p.querySelector(".pb").innerHTML = draw(); wire(); };
    p.querySelector("[data-ud]").onchange = e => { useDue = e.target.checked; if (useDue && !due) due = isoDay(new Date()); p.querySelector(".pb").innerHTML = draw(); wire(); };
    p.querySelector("[data-s]").onchange = e => { start = e.target.value; };
    p.querySelector("[data-dd]").onchange = e => { due = e.target.value; };
    p.querySelector("[data-t]").onchange = e => { time = e.target.value; };
    p.querySelector("[data-r]").onchange = e => { reminder = +e.target.value; };
    p.querySelector("[data-save]").onclick = () => { closePops(); saveCard(cid, { start: useStart ? start : "", due: useDue && due ? `${due}T${time || "17:00"}` : "", reminder }); };
    p.querySelector("[data-rm]").onclick = () => { closePops(); saveCard(cid, { start: "", due: "", due_complete: false, reminder: -1 }); };
  };
  wire();
}

// ---------- checklist ----------
async function checklistPop(anchor, cid) {
  // Opens at once; the checklists to copy from fill in a moment later.
  const p = pop(anchor, "Add checklist", `<label class="fl" style="margin-top:0">Title</label><input class="t" data-t value="Checklist">
    <label class="fl">Copy items from... ${tip("Start this checklist with the items of a checklist already on another card.")}</label><select class="t" data-c><option value="">(none)</option></select>
    <button class="b pri" style="margin-top:12px" data-add>Add</button>`);
  GET(`/store/kb/boards/${S.board.id}/checklists`).then(d => { const sel = p.querySelector("[data-c]"); if (sel && d) sel.insertAdjacentHTML("beforeend", d.checklists.map(o => `<option value="${o.id}">${esc(o.card)} - ${esc(o.title)}</option>`).join("")); }).catch(() => {});
  const t = p.querySelector("[data-t]"); t.select();
  const add = async () => { try { await POST(`/store/kb/cards/${cid}/checklists`, { title: t.value.trim() || "Checklist", copy_from: p.querySelector("[data-c]").value || null }); closePops(); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } };
  p.querySelector("[data-add]").onclick = add; t.onkeydown = e => { if (e.key === "Enter") add(); };
}

// ---------- attachments ----------
function attachPop(anchor, cid) {
  const p = pop(anchor, "Attach", `<h5 style="margin-top:0">Attach a file from your computer</h5><p class="muted" style="margin:0 0 6px">You can also drag and drop files onto the card.</p>
    <div class="drop" data-drop>Drop files here<br><button class="b" style="margin-top:8px" data-pick>Choose a file</button><input type="file" multiple class="hide" data-f></div>
    <h5>Search or paste a link</h5><input class="t" data-u placeholder="Find recent links or paste a new link">
    <label class="fl">Display text (optional)</label><input class="t" data-n placeholder="Text to display">
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px"><button class="b" data-x2>Cancel</button><button class="b pri" data-ins>Insert</button></div>`, { cls: "wide" });
  const f = p.querySelector("[data-f]");
  p.querySelector("[data-pick]").onclick = () => f.click();
  f.onchange = () => { uploadFiles(cid, [...f.files]); closePops(); };
  const dz = p.querySelector("[data-drop]");
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); }; dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); uploadFiles(cid, [...e.dataTransfer.files]); closePops(); };
  p.querySelector("[data-x2]").onclick = closePops;
  p.querySelector("[data-ins]").onclick = async () => {
    const u = p.querySelector("[data-u]").value.trim(); if (!u) return;
    const fd = new FormData(); fd.append("url", u); fd.append("name", p.querySelector("[data-n]").value.trim());
    try { await api(`/store/kb/cards/${cid}/attachments`, { method: "POST", body: fd }); closePops(); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); }
  };
}
async function shrinkImage(file) {
  // Phone photos are big; send them no wider than 2000 px so the upload is quick and fits the server limit.
  if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size < 900 * 1024) return file;
  try {
    const bmp = await createImageBitmap(file); const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
    const cv = document.createElement("canvas"); cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
    cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
    const blob = await new Promise(r => cv.toBlob(r, "image/jpeg", 0.86));
    return blob && blob.size < file.size ? new File([blob], file.name.replace(/\.\w+$/, ".jpg"), { type: "image/jpeg" }) : file;
  } catch (e) { return file; }
}
async function uploadFiles(cid, files, asCover) {
  if (!files.length) return;
  toast(`Uploading ${files.length} file${files.length > 1 ? "s" : ""}...`, { ms: 60000 });
  let ok = 0;
  for (const f0 of files) {
    const f = await shrinkImage(f0);
    if (f.size > 25 * 1024 * 1024) { toast(`${f.name} is over 25 MB`, { err: true }); continue; }
    const fd = new FormData(); fd.append("file", f, f.name); if (asCover) fd.append("cover", "1");
    try { await api(`/store/kb/cards/${cid}/attachments`, { method: "POST", body: fd }); ok++; } catch (e) { fail(e); }
  }
  if (ok) toast(`${ok} file${ok > 1 ? "s" : ""} attached`);
  if (S.openCard === cid) await loadFullCard(cid, true);
  reloadBoard(true);
}

// ---------- cover ----------
const COVER_COLORS = ["green", "yellow", "orange", "red", "purple", "blue", "sky", "lime", "pink", "black"];
function coverPop(anchor, cid) {
  const c = cardOf(cid); if (!c) return;
  const cov = c.cover || {};
  const imgs = (S.full && S.full.id === cid ? S.full.attachments : []).filter(a => a.image && !a.link);
  const has = cov.color || cov.att;
  const p = pop(anchor, "Cover", `<h5 style="margin-top:0">Size</h5>
    <div class="cvsize"><button data-size="normal" class="${cov.size !== "full" ? "on" : ""}" ${has ? "" : "disabled"}><div class="t1" style="background:${has ? (cov.att ? "#B3BAC5" : labColor(cov.color)) : "#DCDFE4"}"></div><div class="ln"></div><div class="ln" style="width:40%"></div></button>
      <button data-size="full" class="${cov.size === "full" ? "on" : ""}" ${has ? "" : "disabled"} style="background:${has ? (cov.att ? "#B3BAC5" : labColor(cov.color)) : "#DCDFE4"};justify-content:flex-end;padding-bottom:6px"><div class="ln" style="background:rgba(255,255,255,.7)"></div><div class="ln" style="width:40%;background:rgba(255,255,255,.7)"></div></button></div>
    ${has ? '<button class="b" style="width:100%" data-rm>Remove cover</button>' : ""}
    ${cov.size === "full" ? `<h5>Text color</h5><div class="cvsize"><button data-tx="dark" class="${cov.text === "dark" ? "on" : ""}" style="background:#fff;align-items:center;justify-content:center;font-weight:700;color:#172B4D">Aa</button><button data-tx="light" class="${cov.text !== "dark" ? "on" : ""}" style="background:#44546F;align-items:center;justify-content:center;font-weight:700;color:#fff">Aa</button></div>` : ""}
    <h5>Colors</h5><div class="grid5">${COVER_COLORS.map(x => `<button class="sw ${cov.color === x ? "on" : ""}" data-col="${x}" style="background:var(--l-${x})"></button>`).join("")}</div>
    ${imgs.length ? `<h5>Attachments</h5><div class="imgs">${imgs.map(a => `<button data-att="${a.id}" class="${cov.att === a.id ? "on" : ""}" style="background-image:url('${a.thumb}')"></button>`).join("")}</div>` : ""}
    <button class="b" style="width:100%;margin-top:8px" data-up>Upload a cover image</button><input type="file" accept="image/*" class="hide" data-f>
    <p class="muted" style="margin:8px 0 0">Tip: drag an image onto a card to upload it.</p>`);
  const set = v => { closePops(); saveCard(cid, { cover: v }); };
  $$("[data-size]", p).forEach(b => b.onclick = () => set({ ...cov, size: b.dataset.size }));
  $$("[data-tx]", p).forEach(b => b.onclick = () => set({ ...cov, text: b.dataset.tx }));
  $$("[data-col]", p).forEach(b => b.onclick = () => set({ color: b.dataset.col, size: cov.size || "normal", text: cov.text }));
  $$("[data-att]", p).forEach(b => b.onclick = () => set({ att: +b.dataset.att, size: cov.size || "normal", text: cov.text }));
  const rm = p.querySelector("[data-rm]"); if (rm) rm.onclick = () => set({});
  const f = p.querySelector("[data-f]"); p.querySelector("[data-up]").onclick = () => f.click();
  f.onchange = () => { closePops(); uploadFiles(cid, [...f.files], true); };
}

// ---------- move / copy / mirror ----------
async function boardListsFor(bid) {
  if (S.board && bid === S.board.id) return { lists: S.board.lists, cards: Object.values(S.cards) };
  const b = await GET(`/store/kb/boards/${bid}`); return { lists: b.lists, cards: b.cards };
}
async function moveCopyPop(anchor, cid, mode, opt = {}) {
  const c = cardOf(cid); if (!c) return;
  const boards = (await refreshBoards()).boards.filter(b => !b.closed);
  let bid = S.board.id, lid = c.list_id, data = await boardListsFor(bid);
  const posOpts = () => { const n = data.cards.filter(x => x.list_id === lid && x.id !== cid).length; return Array.from({ length: n + 1 }, (_, i) => i + 1); };
  let pos = mode === "move" ? (data.cards.filter(x => x.list_id === lid).sort((a, b) => a.pos - b.pos).findIndex(x => x.id === cid) + 1) || 1 : 1;
  const sel = () => `<label class="fl">Board</label><select class="t" data-b>${boards.map(b => `<option value="${b.id}" ${b.id === bid ? "selected" : ""}>${esc(b.title)}${b.id === S.board.id ? " (current)" : ""}</option>`).join("")}</select>
    <div style="display:flex;gap:8px"><div style="flex:2"><label class="fl">List</label><select class="t" data-l>${data.lists.map(l => `<option value="${l.id}" ${l.id === lid ? "selected" : ""}>${esc(l.title)}${l.id === c.list_id && bid === S.board.id ? " (current)" : ""}</option>`).join("")}</select></div>
    <div style="flex:1"><label class="fl">Position</label><select class="t" data-p>${posOpts().map(i => `<option ${i === pos ? "selected" : ""}>${i}</option>`).join("")}</select></div></div>`;
  const full = S.full && S.full.id === cid ? S.full : null;
  const keepHtml = mode === "copy" ? `<label class="fl" style="margin-top:0">Title</label><textarea class="t" data-title rows="2">${esc(c.title)}</textarea>
    <label class="fl">Keep...</label>
    ${[["checklists", `Checklists (${full ? full.checklists.length : "…"})`], ["labels", "Labels"], ["members", "Members"], ["attachments", "Attachments"], ["comments", "Comments"]].map(([k, l]) => `<div><label class="chk"><input type="checkbox" data-k="${k}" ${k !== "comments" ? "checked" : ""}> ${l}</label></div>`).join("")}<label class="fl">Copy to...</label>` : `<h5 style="margin-top:0">Select destination</h5>`;
  const titles = { move: "Move card", copy: "Copy card", mirror: "Mirror card" };
  const p = pop(anchor, titles[mode], `${keepHtml}<div data-sel>${sel()}</div>
    ${mode === "mirror" ? '<p class="muted">A mirror shows this card on another board. Changes are made on the original and show everywhere.</p>' : ""}
    <button class="b pri" style="margin-top:12px" data-go>${mode === "move" ? "Move" : mode === "copy" ? "Create card" : "Mirror"}</button>`, opt);
  const wire = () => {
    p.querySelector("[data-b]").onchange = async e => { bid = +e.target.value; data = await boardListsFor(bid); lid = data.lists[0] ? data.lists[0].id : 0; pos = 1; p.querySelector("[data-sel]").innerHTML = sel(); wire(); };
    p.querySelector("[data-l]").onchange = e => { lid = +e.target.value; pos = 1; p.querySelector("[data-sel]").innerHTML = sel(); wire(); };
    p.querySelector("[data-p]").onchange = e => { pos = +e.target.value; };
  };
  wire();
  p.querySelector("[data-go]").onclick = async () => {
    const qe = $("#qe"); if (qe) qe.remove();       // quick edit closes with it
    const others = data.cards.filter(x => x.list_id === lid && x.id !== cid).sort((a, b) => a.pos - b.pos);
    const before = others[pos - 2], after = others[pos - 1];
    const np = !before && !after ? 65536 : !before ? after.pos / 2 : !after ? before.pos + 65536 : (before.pos + after.pos) / 2;
    closePops();
    try {
      if (mode === "move") {
        const patch = { list_id: lid, pos: np }; if (bid !== S.board.id) patch.board_id = bid;
        await saveCard(cid, patch, { reloadCard: false });
        if (bid !== S.board.id) { toast("Card moved to the other board"); go(`#/b/${S.board.id}`); }
      } else if (mode === "copy") {
        const keep = {}; $$("[data-k]", p).forEach(k => keep[k.dataset.k] = k.checked);
        const r = await POST(`/store/kb/cards/${cid}/copy`, { board_id: bid, list_id: lid, pos: np, title: p.querySelector("[data-title]").value.trim() || c.title, keep });
        await reloadBoard(true); toast("Card copied", { undo: async () => { await DEL(`/store/kb/cards/${r.id}`); reloadBoard(true); } });
      } else {
        await POST(`/store/kb/cards/${cid}/mirror`, { board_id: bid, list_id: lid, pos: np }); await reloadBoard(true); if (S.openCard) loadFullCard(S.openCard, true); toast("Mirror created");
      }
    } catch (e) { fail(e); }
  };
}

// ---------- custom fields, priority, points, time ----------
function fieldsPop(anchor, cid) {
  const c = cardOf(cid); if (!c) return;
  const fs = S.board.fields;
  const val = f => (c.fields || {})[String(f.id)];
  const p = pop(anchor, "Custom Fields", (fs.length ? fs.map(f => `<label class="fl">${esc(f.name)}</label>` + fieldInput(f, val(f))).join("") : '<p class="muted" style="margin:0">No custom fields on this board yet.</p>')
    + `<hr><button class="b" style="width:100%" data-manage>${ic("field")} Manage fields</button>`, { cls: "wide", nofocus: true });
  wireFieldInputs(p, cid);
  p.querySelector("[data-manage]").onclick = () => { closePops(); boardMenu("fields"); };
}
function fieldInput(f, v) {
  if (f.type === "checkbox") return `<label class="chk"><input type="checkbox" data-f="${f.id}" ${v ? "checked" : ""}> ${esc(f.name)}</label>`;
  if (f.type === "list") return `<select class="t" data-f="${f.id}"><option value="">Select...</option>${f.options.map(o => `<option value="${o.id}" ${v === o.id ? "selected" : ""}>${esc(o.text)}</option>`).join("")}</select>`;
  if (f.type === "date") return `<input class="t" type="date" data-f="${f.id}" value="${esc(v || "")}">`;
  if (f.type === "number") return `<input class="t" type="number" step="any" data-f="${f.id}" value="${v ?? ""}" placeholder="Add number...">`;
  return `<input class="t" data-f="${f.id}" value="${esc(v || "")}" placeholder="Add text...">`;
}
function wireFieldInputs(root, cid) {
  $$("[data-f]", root).forEach(el => el.onchange = () => {
    const f = S.board.fields.find(x => x.id === +el.dataset.f);
    let v = el.type === "checkbox" ? el.checked : el.value;
    if (f.type === "number" && v !== "") v = Number(v);
    const fields = { ...(cardOf(cid).fields || {}) }; fields[String(f.id)] = v;
    saveCard(cid, { fields: { [String(f.id)]: v } });
  });
}
const PRIORITIES = [["highest", "Highest", "pri2"], ["high", "High", "pri"], ["medium", "Medium", "prim"], ["low", "Low", "pril"], ["lowest", "Lowest", "pril2"]];
function priorityPop(anchor, cid) {
  const c = cardOf(cid);
  const p = pop(anchor, "Priority", PRIORITIES.map(([k, l, i]) => `<button class="mi" data-p="${k}"><span class="bdg pr-${k}" style="margin:0">${ic(i)}</span>${l}${c.priority === k ? `<span class="ck">${ic("check")}</span>` : ""}</button>`).join("") + `<hr><button class="mi" data-p="">None</button>`);
  $$("[data-p]", p).forEach(b => b.onclick = () => { closePops(); saveCard(cid, { priority: b.dataset.p }); });
}
function pointsPop(anchor, cid) {
  const c = cardOf(cid);
  const p = pop(anchor, "Story points & estimate", `<label class="fl" style="margin-top:0">Story points</label><div class="grid5" style="margin-bottom:6px">${[1, 2, 3, 5, 8, 13, 21, 0.5, 40, 100].map(n => `<button class="b" data-n="${n}">${n}</button>`).join("")}</div>
    <input class="t" type="number" step="any" data-pt value="${c.points ?? ""}" placeholder="Points">
    <label class="fl">Original estimate (hours) ${tip("Time tracking compares hours logged with this estimate; the bar turns red when it is over.")}</label><input class="t" type="number" step="any" data-es value="${c.estimate ?? ""}" placeholder="e.g. 8">
    <button class="b pri" style="margin-top:12px" data-save>Save</button>`);
  $$("[data-n]", p).forEach(b => b.onclick = () => { p.querySelector("[data-pt]").value = b.dataset.n; });
  p.querySelector("[data-save]").onclick = () => { closePops(); saveCard(cid, { points: p.querySelector("[data-pt]").value, estimate: p.querySelector("[data-es]").value }); };
}
function timePop(anchor, cid) {
  const p = pop(anchor, "Log time", `<label class="fl" style="margin-top:0">Time spent (hours)</label><input class="t" type="number" step="0.25" min="0" data-h placeholder="e.g. 1.5">
    <label class="fl">Date</label><input class="t" type="date" data-d value="${isoDay(new Date())}">
    <label class="fl">What was done (optional)</label><input class="t" data-n placeholder="e.g. BOQ take-off">
    <button class="b pri" style="margin-top:12px" data-save>Log time</button>`);
  const save = async () => { try { await POST(`/store/kb/cards/${cid}/time`, { hours: p.querySelector("[data-h]").value, day: p.querySelector("[data-d]").value, note: p.querySelector("[data-n]").value }); closePops(); toast("Time logged"); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } };
  p.querySelector("[data-save]").onclick = save; p.querySelector("[data-h]").onkeydown = e => { if (e.key === "Enter") save(); };
}
function repeatPop(anchor, cid) {
  const c = cardOf(cid); const r = (S.full && S.full.repeat) || null;
  const d = new Date(); d.setDate(d.getDate() + 1);
  const p = pop(anchor, "Card Repeater", `<p class="muted" style="margin:0 0 8px">A copy of this card is made automatically, with checklists unticked.</p>
    <label class="fl">Repeat</label><div style="display:flex;gap:8px;align-items:center">every <input class="t" type="number" min="1" data-n value="${r ? r.nth : 1}" style="width:64px">
    <select class="t" data-e>${[["day", "day(s)"], ["weekday", "weekday (Mon-Fri)"], ["week", "week(s)"], ["month", "month(s)"], ["year", "year(s)"]].map(([k, l]) => `<option value="${k}" ${(r ? r.every : "week") === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    <label class="fl">First copy on</label><div style="display:flex;gap:8px"><input class="t" type="date" data-s value="${r ? r.next_on : isoDay(d)}"><input class="t" type="time" data-t value="${r ? r.time : "09:00"}" style="width:110px"></div>
    <label class="fl">Put the copy in list ${tip("Each new copy is placed at the top of this list.")}</label><select class="t" data-l>${S.board.lists.map(l => `<option value="${l.id}" ${(r ? r.list_id : c.list_id) === l.id ? "selected" : ""}>${esc(l.title)}</option>`).join("")}</select>
    <label class="fl">Due date on the copy</label><select class="t" data-dd>${[[-1, "None"], [0, "Same day"], [1, "1 day later"], [2, "2 days later"], [3, "3 days later"], [7, "1 week later"]].map(([v, l]) => `<option value="${v}" ${(r ? r.due_days : -1) === v ? "selected" : ""}>${l}</option>`).join("")}</select>
    ${r ? `<p class="muted">${r.made} cop${r.made === 1 ? "y" : "ies"} made so far. Next: ${fmtDue(r.next_on, false)}</p>` : ""}
    <div style="display:flex;gap:8px;margin-top:12px"><button class="b pri" data-save>${r ? "Save" : "Repeat"}</button>${r ? '<button class="b" data-off>Stop repeating</button>' : ""}</div>`);
  p.querySelector("[data-save]").onclick = async () => { try { await PUT(`/store/kb/cards/${cid}/repeat`, { every: p.querySelector("[data-e]").value, nth: p.querySelector("[data-n]").value, start: p.querySelector("[data-s]").value, time: p.querySelector("[data-t]").value, list_id: p.querySelector("[data-l]").value, due_days: p.querySelector("[data-dd]").value }); closePops(); toast("Card will repeat"); loadFullCard(cid, true); } catch (e) { fail(e); } };
  const off = p.querySelector("[data-off]"); if (off) off.onclick = async () => { await PUT(`/store/kb/cards/${cid}/repeat`, { off: true }); closePops(); loadFullCard(cid, true); };
}
async function linkCardPop(anchor, cid) {
  const p = pop(anchor, "Link a card", `<input class="t" data-q placeholder="Search cards by name or #number"><div data-res style="margin-top:8px"></div>`, { cls: "wide" });
  const q = p.querySelector("[data-q]");
  const run = debounce(async () => {
    if (!q.value.trim()) { p.querySelector("[data-res]").innerHTML = ""; return; }
    const d = await GET("/store/kb/search?q=" + encodeURIComponent(q.value.trim()));
    p.querySelector("[data-res]").innerHTML = d.cards.filter(x => x.id !== cid).map(x => `<button class="mi" data-c="${x.id}"><div><b>${esc(x.title)}</b><small>#${x.no} · ${esc(x.board)}: ${esc(x.list)}</small></div></button>`).join("") || '<div class="muted">No cards found.</div>';
    $$("[data-c]", p).forEach(b => b.onclick = () => { const links = [...new Set([...(cardOf(cid).links || []), +b.dataset.c])]; closePops(); saveCard(cid, { links }); });
  }, 200);
  q.oninput = run;
}

// ---------- filter ----------
function emptyFilter() { return { q: "", members: [], noMembers: false, labels: [], noLabels: false, due: [], status: "", all: false }; }
function filterActive() { const f = S.filter; return f && (f.q || f.members.length || f.noMembers || f.labels.length || f.noLabels || f.due.length || f.status); }
function filterCount() { const f = S.filter; if (!f) return 0; return (f.q ? 1 : 0) + f.members.length + (f.noMembers ? 1 : 0) + f.labels.length + (f.noLabels ? 1 : 0) + f.due.length + (f.status ? 1 : 0); }
function matchFilter(c) {
  const f = S.filter; if (!filterActive()) return true;
  const tests = [];
  if (f.q) { const q = f.q.toLowerCase(); tests.push(c.title.toLowerCase().includes(q) || c.labels.some(id => { const l = S.board.labels.find(x => x.id === id); return l && (l.name || "").toLowerCase().includes(q); }) || c.members.some(id => { const p = person(id); return p && (p.name.toLowerCase().includes(q) || p.username.toLowerCase().includes(q)); }) || String(c.no) === q.replace("#", "")); }
  if (f.members.length || f.noMembers) tests.push((f.noMembers && !c.members.length) || f.members.some(m => c.members.includes(m)));
  if (f.labels.length || f.noLabels) tests.push((f.noLabels && !c.labels.length) || (f.all ? f.labels.every(l => c.labels.includes(l)) : f.labels.some(l => c.labels.includes(l))));
  if (f.status) tests.push(f.status === "complete" ? c.due_complete : !c.due_complete);
  if (f.due.length) {
    const d = parseDue(c.due), now = new Date(), day = 86400000;
    tests.push(f.due.some(k => k === "none" ? !c.due : !d ? false : k === "over" ? d < now && !c.due_complete : k === "day" ? d >= now && d - now <= day : k === "week" ? d >= now && d - now <= 7 * day : k === "month" ? d >= now && d - now <= 31 * day : false));
  }
  return f.all ? tests.every(Boolean) : tests.every(Boolean);
}
function filterPop(anchor) {
  if (!S.filter) S.filter = emptyFilter();
  const f = S.filter;
  const ck = (on, attr, content) => `<label class="chk" style="display:flex;margin:6px 0"><input type="checkbox" ${attr} ${on ? "checked" : ""}>${content}</label>`;
  const draw = () => `<label class="fl" style="margin-top:0">Keyword ${tip("Matches card titles, label names, member names and card numbers (#12).")}</label><input class="t" data-q placeholder="Enter a keyword..." value="${esc(f.q)}"><p class="muted" style="margin:4px 0 0">Search cards, members, labels, and more.</p>
    <label class="fl">Members</label>
    ${ck(f.noMembers, "data-nom", `<span class="av" style="background:#DCDFE4;color:#44546F">${ic("user", "s12")}</span> No members`)}
    ${ck(f.members.includes(S.me.id), `data-m="${S.me.id}"`, `${av(S.me)} Cards assigned to me`)}
    ${S.board.members.filter(m => m.id !== S.me.id).map(m => ck(f.members.includes(m.id), `data-m="${m.id}"`, `${av(m)} ${esc(m.name)}`)).join("")}
    <label class="fl">Card status</label>${ck(f.status === "complete", 'data-st="complete"', "Marked as complete")}${ck(f.status === "incomplete", 'data-st="incomplete"', "Not marked as complete")}
    <label class="fl">Due date</label>
    ${[["none", "No dates", "cal"], ["over", "Overdue", "clock"], ["day", "Due in the next day", "clock"], ["week", "Due in the next week", "clock"], ["month", "Due in the next month", "clock"]].map(([k, l, i]) => ck(f.due.includes(k), `data-d="${k}"`, `${ic(i)} ${l}`)).join("")}
    <label class="fl">Labels</label>${ck(f.noLabels, "data-nol", `<span class="lab" style="width:100%;height:32px;line-height:32px;padding:0 12px;border-radius:3px;background:#fff;border:1px solid var(--border)">No labels</span>`)}
    ${S.board.labels.map(l => ck(f.labels.includes(l.id), `data-l="${l.id}"`, labHtml(l).replace('class="lab', 'style="flex:1;height:32px;line-height:32px;padding:0 12px;border-radius:3px;font-size:14px;background:' + labColor(l.color) + '" class="lab'))).join("")}
    <hr><label class="fl" style="margin-top:0">Match</label><select class="t" data-all><option value="0" ${!f.all ? "selected" : ""}>Any match</option><option value="1" ${f.all ? "selected" : ""}>Exact match (all labels)</option></select>
    <p class="muted" data-cnt style="margin:10px 0 0"></p>`;
  const p = pop(anchor, "Filter", draw(), { cls: "wide" });
  const upd = () => { applyFilter(); const n = Object.values(S.cards).filter(c => matchFilter(c)).length; p.querySelector("[data-cnt]").textContent = filterActive() ? `${n} card${n === 1 ? "" : "s"} match filters` : ""; };
  const wire = () => {
    const q = p.querySelector("[data-q]"); q.oninput = () => { f.q = q.value; upd(); };
    p.querySelector("[data-nom]").onchange = e => { f.noMembers = e.target.checked; upd(); };
    $$("[data-m]", p).forEach(x => x.onchange = () => { const id = +x.dataset.m; f.members = x.checked ? [...f.members, id] : f.members.filter(m => m !== id); upd(); });
    $$("[data-st]", p).forEach(x => x.onchange = () => { f.status = x.checked ? x.dataset.st : ""; $$("[data-st]", p).forEach(y => { if (y !== x) y.checked = false; }); upd(); });
    $$("[data-d]", p).forEach(x => x.onchange = () => { f.due = x.checked ? [...f.due, x.dataset.d] : f.due.filter(d => d !== x.dataset.d); upd(); });
    p.querySelector("[data-nol]").onchange = e => { f.noLabels = e.target.checked; upd(); };
    $$("[data-l]", p).forEach(x => x.onchange = () => { const id = +x.dataset.l; f.labels = x.checked ? [...f.labels, id] : f.labels.filter(l => l !== id); upd(); });
    p.querySelector("[data-all]").onchange = e => { f.all = e.target.value === "1"; upd(); };
  };
  wire(); upd();
}
function applyFilter() {
  Object.values(S.cards).forEach(c => { const el = document.querySelector(`.card[data-c="${c.id}"]`); if (el) el.classList.toggle("filtered-out", !matchFilter(c)); });
  updateListCounts(); renderFilterBtn();
  if (S.view !== "board") renderView();
}
function clearFilter() { S.filter = emptyFilter(); applyFilter(); }
function toggleMyCards() { if (!S.filter) S.filter = emptyFilter(); const me = S.me.id; S.filter.members = S.filter.members.includes(me) ? S.filter.members.filter(x => x !== me) : [...S.filter.members, me]; applyFilter(); }

// ---------- header popovers ----------
function boardsPop(anchor, kind) {
  const open = S.boards.filter(b => !b.closed);
  let list = kind === "starred" ? open.filter(b => b.starred) : kind === "recent" ? open.filter(b => b.seen).sort((a, b) => b.seen.localeCompare(a.seen)).slice(0, 8) : kind === "templates" ? open.filter(b => b.is_template) : open;
  const title = { all: "Boards", recent: "Recent boards", starred: "Starred boards", templates: "Templates", switch: "Switch boards" }[kind];
  const row = b => `<button class="mi" data-b="${b.id}"><span style="width:40px;height:32px;border-radius:3px;flex-shrink:0;background:${bgCss(b.bg, b.bg_url)}"></span><div style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">${esc(b.title)}<small>Infinia Estimation</small></div>${b.starred ? `<svg class="i f" style="color:#E2B203"><use href="#i-star"/></svg>` : ""}</button>`;
  const p = pop(anchor, title, (kind === "switch" ? `<input class="t" data-q placeholder="Search your boards" style="margin-bottom:8px">` : "") + `<div data-l>${list.map(row).join("") || `<p class="muted">${kind === "starred" ? "Star important boards to find them quickly." : kind === "templates" ? "No templates yet - make one from a board's menu." : "No boards yet."}</p>`}</div>`
    + (kind === "templates" ? `<hr><button class="b" style="width:100%" data-all>See all templates</button>` : ""), { cls: kind === "switch" ? "wide" : "" });
  const wire = () => $$("[data-b]", p).forEach(b => b.onclick = () => { closePops(); go("#/b/" + b.dataset.b); });
  wire();
  const q = p.querySelector("[data-q]"); if (q) q.oninput = () => { p.querySelector("[data-l]").innerHTML = list.filter(b => b.title.toLowerCase().includes(q.value.toLowerCase())).map(row).join(""); wire(); };
  const all = p.querySelector("[data-all]"); if (all) all.onclick = () => { closePops(); go("#/templates"); };
}
function createPop(anchor) {
  const p = pop(anchor, "Create", `<button class="mi" data-k="board">${ic("board")}<div><b>Create board</b><small>A board is made up of cards ordered on lists. Use it to manage projects, track information, or organize anything.</small></div></button>
    <button class="mi" data-k="tpl">${ic("tpl")}<div><b>Start with a template</b><small>Get started faster with a board template.</small></div></button>
    <button class="mi" data-k="import">${ic("upload")}<div><b>Import from Trello</b><small>Bring a board across from Trello (Menu > Print, export and share > Export as JSON).</small></div></button>`, { cls: "wide" });
  p.querySelector('[data-k="board"]').onclick = () => createBoardPop(anchor);
  p.querySelector('[data-k="tpl"]').onclick = () => { closePops(); go("#/templates"); };
  p.querySelector('[data-k="import"]').onclick = () => { closePops(); importDlg(); };
}
function createBoardPop(anchor, tpl) {
  let bg = tpl ? tpl.bg : "g_ocean";
  const keys = ["g_ocean", "g_crystal", "g_rainbow", "g_peach", "g_flower", "g_earth", "blue", "orange", "green", "red", "purple", "pink"];
  const p = pop(anchor, tpl ? "Create from template" : "Create board", `<div class="prev" style="padding:16px"><div data-pv style="width:200px;height:120px;border-radius:3px;background:${bgCss(bg)};display:flex;justify-content:center;align-items:center"><svg width="160" height="90" viewBox="0 0 160 90"><rect x="10" y="12" width="40" height="66" rx="3" fill="rgba(255,255,255,.8)"/><rect x="60" y="12" width="40" height="44" rx="3" fill="rgba(255,255,255,.8)"/><rect x="110" y="12" width="40" height="56" rx="3" fill="rgba(255,255,255,.8)"/></svg></div></div>
    <label class="fl">Background</label><div class="grid5" style="grid-template-columns:repeat(6,1fr)">${keys.map(k => `<button class="sw ${k === bg ? "on" : ""}" data-bg="${k}" style="background:${bgCss(k)};height:28px"></button>`).join("")}</div>
    <label class="fl">Board title * ${tip("The name shown on the board and in Boards. You can rename it any time by clicking it.")}</label><input class="t" data-t value="${esc(tpl ? tpl.title : "")}">
    <label class="fl">Visibility ${tip("Workspace: everyone with Estimation > Trello can open it. Private: only the people you add.")}</label><select class="t" data-v><option value="team">Workspace - everyone with Trello access can see it</option><option value="private">Private - only board members</option></select>
    ${tpl && tpl.lists ? `<p class="muted">Lists: ${esc(tpl.lists.join(", "))}</p>` : ""}
    ${tpl && tpl.id ? '<div><label class="chk" style="margin-top:8px"><input type="checkbox" data-keep checked> Keep cards</label></div>' : ""}
    <button class="b pri" style="width:100%;margin-top:12px" data-go>Create</button>`, { keep: false });
  $$("[data-bg]", p).forEach(b => b.onclick = () => { bg = b.dataset.bg; $$("[data-bg]", p).forEach(x => x.classList.toggle("on", x === b)); p.querySelector("[data-pv]").style.background = bgCss(bg); });
  const t = p.querySelector("[data-t]");
  const goC = async () => {
    if (!t.value.trim()) { t.focus(); t.style.borderColor = "var(--danger)"; return; }
    try {
      const body = { title: t.value.trim(), bg, visibility: p.querySelector("[data-v]").value };
      if (tpl && tpl.lists) body.lists = tpl.lists;
      if (tpl && tpl.id) { body.from_template = tpl.id; body.keep_cards = p.querySelector("[data-keep]").checked; }
      const r = await POST("/store/kb/boards", body); closePops(); await refreshBoards(); go("#/b/" + r.id);
    } catch (e) { fail(e); }
  };
  p.querySelector("[data-go]").onclick = goC; t.onkeydown = e => { if (e.key === "Enter") goC(); };
}
async function notesPop(anchor) {
  await pollNotes(); const d = S.notes || { notes: [], due: [] };
  const p = pop(anchor, "Notifications", (d.due.length ? `<h5 style="margin-top:0">Due soon</h5>${d.due.map(x => `<button class="mi" data-b="${x.board_id}" data-c="${x.card_id}"><span class="bdg ${x.overdue ? "due-over" : "due-soon"}" style="margin:0">${ic("clock", "s12")} ${fmtDue(x.due)}</span><div style="min-width:0">${esc(x.title)}<small>${esc(x.board)}</small></div></button>`).join("")}<hr>` : "")
    + (d.notes.length ? d.notes.map(n => `<button class="mi" data-b="${n.board_id}" data-c="${n.card_id || ""}" style="${n.read ? "" : "background:#E9F2FF"}"><span class="av" style="background:${avColor(n.who.length)}">${esc(n.initials)}</span><div style="min-width:0"><b>${esc(n.who)}</b> ${esc(n.text)}<small>${esc(n.board)} · ${ago(n.at)}</small></div></button>`).join("") : '<div class="empty" style="padding:24px 0">No notifications yet</div>')
    + (d.unread ? '<hr><button class="b" style="width:100%" data-read>Mark all as read</button>' : ""), { cls: "xwide" });
  $$("[data-b]", p).forEach(b => b.onclick = async () => { closePops(); go(`#/b/${b.dataset.b}${b.dataset.c ? "/c/" + b.dataset.c : ""}`); });
  const r = p.querySelector("[data-read]"); if (r) r.onclick = async () => { await POST("/store/kb/notes/read", {}); closePops(); pollNotes(); };
  if (d.unread) setTimeout(() => POST("/store/kb/notes/read", {}).then(pollNotes).catch(() => {}), 1500);
}
function mePop(anchor) {
  const p = pop(anchor, "Account", `<div style="display:flex;gap:10px;align-items:center;margin-bottom:8px">${av(S.me, "xl")}<div><b>${esc(S.me.name)}</b><div class="muted">@${esc(S.me.username)}</div></div></div><hr>
    <button class="mi" data-k="labels">${document.body.classList.contains("lab-open") ? "Hide" : "Show"} label text on cards</button>
    <button class="mi" data-k="keys">Keyboard shortcuts</button>
    ${window.PG_EMBED ? `<button class="mi" data-k="full">Open Trello in its own tab</button>` : `<button class="mi" data-k="app">Back to the Infinia app</button>`}`);
  p.querySelector('[data-k="labels"]').onclick = () => { closePops(); document.body.classList.toggle("lab-open"); try { localStorage.setItem("kb_lab_open", document.body.classList.contains("lab-open") ? "1" : ""); } catch (e) {} };
  p.querySelector('[data-k="keys"]').onclick = () => { closePops(); shortcutsDlg(); };
  const f = p.querySelector('[data-k="full"]'); if (f) f.onclick = () => { closePops(); window.open(location.pathname + location.hash, "_blank"); };
  const a = p.querySelector('[data-k="app"]'); if (a) a.onclick = () => { location.href = "/?p=estimation"; };
}
function importDlg() {
  const d = dlg(`<h2><span>Import a board from Trello</span><button class="x" data-close>${ic("x")}</button></h2>
    <ol style="margin:0 0 12px;padding-left:20px;line-height:24px"><li>In Trello, open the board.</li><li>Menu (…) → <b>Print, export and share</b> → <b>Export as JSON</b>.</li><li>Save the page (Ctrl+S / Cmd+S) as a .json file and choose it below.</li></ol>
    <p class="muted">Lists, cards (with their numbers), labels, checklists, due dates, covers, custom fields, comments and links come across. People are matched to logins by name.</p>
    <label class="fl">Board title (optional)</label><input class="t" data-t placeholder="Keep the Trello name">
    <div class="drop" data-drop style="border:2px dashed var(--border);border-radius:8px;padding:24px;text-align:center;margin-top:12px">Drop the .json file here or <a data-pick>choose it</a><input type="file" accept=".json,application/json" class="hide" data-f></div>
    <p data-msg class="muted"></p>`);
  const f = d.querySelector("[data-f]"); d.querySelector("[data-pick]").onclick = () => f.click();
  const send = async file => {
    d.querySelector("[data-msg]").textContent = "Importing...";
    const fd = new FormData(); fd.append("title", d.querySelector("[data-t]").value.trim());
    // Trello boards can be many MB as text; send them compressed so they fit the server's upload limit.
    if (window.CompressionStream && file.size > 200 * 1024) { const gz = await new Response(file.stream().pipeThrough(new CompressionStream("gzip"))).blob(); fd.append("file", gz, file.name + ".gz"); }
    else fd.append("file", file);
    try { const r = await api("/store/kb/import", { method: "POST", body: fd }); d.remove(); toast(`Imported: ${r.lists} lists, ${r.cards} cards, ${r.checklists} checklists, ${r.comments} comments`, { ms: 6000 }); go("#/b/" + r.id); }
    catch (e) { d.querySelector("[data-msg]").textContent = e.message; }
  };
  f.onchange = () => f.files[0] && send(f.files[0]);
  const dz = d.querySelector("[data-drop]"); dz.ondragover = e => { e.preventDefault(); dz.style.borderColor = "var(--brand)"; }; dz.ondrop = e => { e.preventDefault(); e.dataTransfer.files[0] && send(e.dataTransfer.files[0]); };
}
async function closedBoardsDlg() {
  await refreshBoards();
  const cl = S.boards.filter(b => b.closed);
  const d = dlg(`<h2><span>Closed boards</span><button class="x" data-close>${ic("x")}</button></h2>${cl.map(b => `<div class="share-row"><span style="width:40px;height:32px;border-radius:3px;background:${bgCss(b.bg, b.bg_url)}"></span><div class="nm">${esc(b.title)}</div><button class="b" data-re="${b.id}">Reopen</button><button class="b dng" data-del="${b.id}">Delete</button></div>`).join("") || '<p class="muted">No closed boards.</p>'}`);
  $$("[data-re]", d).forEach(b => b.onclick = async () => { try { await PATCH(`/store/kb/boards/${b.dataset.re}`, { closed: false }); d.remove(); go("#/b/" + b.dataset.re); } catch (e) { fail(e); } });
  $$("[data-del]", d).forEach(b => b.onclick = () => confirmPop(b, "Delete board?", "All lists, cards and actions will be deleted, and you won't be able to reopen the board. There is no undo.", "Delete", async () => { try { await DEL(`/store/kb/boards/${b.dataset.del}`); d.remove(); closedBoardsDlg(); } catch (e) { fail(e); } }));
}
