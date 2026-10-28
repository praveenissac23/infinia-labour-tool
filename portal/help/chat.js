/* In-app chat - who is online, Everyone, and a private chat with anyone.
   The button sits beside the bell; the panel slides in from the right (full screen on a phone).
   Enter sends, Shift+Enter for a new line, @ to tag someone (@everyone in Everyone). */
(function () {
  if (window.CHAT || !document.getElementById("bell-wrap")) return;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COLORS = ["#C0392B", "#1F7A8C", "#6D4C9F", "#2E7D32", "#B26A00", "#AD1457", "#1565C0", "#5D4037", "#00838F", "#7B1FA2"];
  const col = id => COLORS[(id || 0) % COLORS.length];
  const api = (u, o) => apiCall(u, o);
  const S = { open: false, room: "", users: [], me: 0, unread: {}, last: {}, msgs: {}, lastId: {}, more: {}, timer: 0, busy: false, q: "", edit: null, mentions: 0, total: 0 };

  // ---- the look ------------------------------------------------------------------------------------
  const css = document.createElement("style");
  css.textContent = `
  #chat-btn { position: relative; width: 38px; height: 38px; border-radius: 50%; border: 0; background: transparent; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; margin-right: 6px; color: #3E434A; }
  #chat-btn:hover { background: #F1EFEC; } #chat-btn svg { width: 24px; height: 24px; }
  #chat-btn .n { position: absolute; top: 0; right: -2px; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: #C0392B; color: #fff; font: 700 11px/18px -apple-system, sans-serif; text-align: center; box-sizing: border-box; }
  #chat-btn .dot { position: absolute; bottom: 4px; right: 3px; width: 9px; height: 9px; border-radius: 50%; background: #22A06B; box-shadow: 0 0 0 2px #fff; }
  #chat-pane { position: fixed; top: 72px; right: 14px; bottom: 14px; width: min(860px, calc(100vw - 28px)); z-index: 6000; background: #fff; border-radius: 14px; box-shadow: 0 18px 50px rgba(20,22,26,.28); display: none; overflow: hidden; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #22262A; }
  #chat-pane.on { display: flex; }
  #chat-pane .side { width: 270px; border-right: 1px solid #ECE8E3; display: flex; flex-direction: column; background: #FBFAF8; }
  #chat-pane .side h3 { margin: 0; padding: 14px 16px 6px; font-size: 17px; display: flex; align-items: center; gap: 8px; }
  #chat-pane .side h3 small { font-size: 12px; font-weight: 600; color: #22A06B; }
  #chat-pane .side input { margin: 6px 12px 8px; padding: 8px 10px; border: 1px solid #DDD6CE; border-radius: 8px; font: inherit; font-size: 13px; }
  #chat-pane .list { flex: 1; overflow-y: auto; padding: 0 6px 10px; }
  #chat-pane .grp { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #8A8178; margin: 10px 10px 4px; }
  #chat-pane .who { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 9px; cursor: pointer; }
  #chat-pane .who:hover { background: #F1EDE8; } #chat-pane .who.on { background: #FBE9E7; }
  #chat-pane .who .t { flex: 1; min-width: 0; } #chat-pane .who .t b { display: block; font-weight: 600; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #chat-pane .who .t span { display: block; font-size: 11.5px; color: #8A8178; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #chat-pane .who .u { min-width: 20px; height: 20px; border-radius: 10px; background: #C0392B; color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; padding: 0 6px; box-sizing: border-box; }
  #chat-pane .av { position: relative; width: 34px; height: 34px; border-radius: 50%; color: #fff; font-size: 12.5px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  #chat-pane .av.sm { width: 30px; height: 30px; font-size: 11.5px; }
  #chat-pane .av i { position: absolute; right: -1px; bottom: -1px; width: 10px; height: 10px; border-radius: 50%; background: #B7B0A8; box-shadow: 0 0 0 2px #FBFAF8; }
  #chat-pane .av i.y { background: #22A06B; }
  #chat-pane .av.all { background: linear-gradient(135deg, #C0392B, #7A1E19); font-size: 16px; }
  #chat-pane .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  #chat-pane .hd { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid #ECE8E3; }
  #chat-pane .hd b { font-size: 15.5px; } #chat-pane .hd div > span { font-size: 12px; color: #8A8178; display: block; }
  #chat-pane .hd .sp { flex: 1; } #chat-pane .x, #chat-pane .back { border: 0; background: transparent; font-size: 22px; line-height: 1; cursor: pointer; color: #6B7178; width: 34px; height: 34px; border-radius: 8px; }
  #chat-pane .x:hover, #chat-pane .back:hover { background: #F1EDE8; } #chat-pane .back { display: none; }
  #chat-pane .msgs { flex: 1; overflow-y: auto; padding: 10px 18px 6px; background: #fff; }
  #chat-pane .day { text-align: center; margin: 14px 0 8px; } #chat-pane .day span { font-size: 11.5px; font-weight: 600; color: #8A8178; background: #F4F1ED; padding: 3px 10px; border-radius: 10px; }
  #chat-pane .m { display: flex; gap: 10px; padding: 3px 6px; border-radius: 8px; position: relative; }
  #chat-pane .m:hover { background: #FAF8F6; } #chat-pane .m.first { margin-top: 8px; }
  #chat-pane .m .gut { width: 34px; flex-shrink: 0; font-size: 10.5px; color: #B0A89F; text-align: right; padding-top: 3px; }
  #chat-pane .m:not(:hover) .gut small { visibility: hidden; }
  #chat-pane .m .bd { flex: 1; min-width: 0; } #chat-pane .m .nm { font-weight: 700; font-size: 13.5px; } #chat-pane .m .tm { font-size: 11.5px; color: #8A8178; margin-left: 6px; font-weight: 400; }
  #chat-pane .m .tx { white-space: pre-wrap; overflow-wrap: anywhere; } #chat-pane .m .tx a { color: #1565C0; }
  #chat-pane .m.me-tag { background: #FFF8E1; box-shadow: inset 3px 0 0 #E0A800; }
  #chat-pane .m .ed { font-size: 11px; color: #A39B92; } #chat-pane .m .del { color: #A39B92; font-style: italic; }
  #chat-pane .tag { background: #E9F2FF; color: #0055CC; border-radius: 4px; padding: 0 3px; font-weight: 600; } #chat-pane .tag.me { background: #FDE7B0; color: #7A4F00; }
  #chat-pane .acts { position: absolute; right: 8px; top: -10px; display: none; background: #fff; border: 1px solid #E6E0D9; border-radius: 7px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
  #chat-pane .m:hover .acts { display: flex; } #chat-pane .acts button { border: 0; background: transparent; font-size: 12px; padding: 4px 9px; cursor: pointer; color: #3E434A; } #chat-pane .acts button:hover { background: #F4F1ED; }
  #chat-pane .older { display: block; margin: 6px auto; border: 1px solid #E0D9D1; background: #fff; border-radius: 14px; padding: 4px 12px; font-size: 12px; cursor: pointer; color: #5B6167; }
  #chat-pane .empty { color: #8A8178; text-align: center; margin: 40px 20px; font-size: 13.5px; }
  #chat-pane .cmp { border-top: 1px solid #ECE8E3; padding: 10px 14px 12px; position: relative; }
  #chat-pane .cmp .box { display: flex; gap: 8px; align-items: flex-end; border: 1px solid #DDD6CE; border-radius: 12px; padding: 6px 6px 6px 12px; background: #fff; }
  #chat-pane .cmp .box:focus-within { border-color: #C0392B; box-shadow: 0 0 0 3px rgba(192,57,43,.12); }
  #chat-pane .cmp textarea { flex: 1; border: 0; outline: 0; resize: none; font: inherit; max-height: 160px; min-height: 22px; padding: 5px 0; background: transparent; }
  #chat-pane .cmp .send { border: 0; background: #C0392B; color: #fff; border-radius: 9px; padding: 8px 16px; font-weight: 700; cursor: pointer; font-size: 13.5px; }
  #chat-pane .cmp .send:disabled { opacity: .45; cursor: default; }
  #chat-pane .cmp .hint { font-size: 11px; color: #A39B92; margin-top: 5px; } #chat-pane .cmp .editing { font-size: 12px; color: #B26A00; margin-bottom: 5px; }
  #chat-pane .pick { position: absolute; left: 14px; bottom: calc(100% - 4px); width: 280px; max-height: 240px; overflow-y: auto; background: #fff; border: 1px solid #E0D9D1; border-radius: 10px; box-shadow: 0 8px 26px rgba(0,0,0,.16); padding: 4px; display: none; }
  #chat-pane .pick div { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 7px; cursor: pointer; font-size: 13px; } #chat-pane .pick div.sel, #chat-pane .pick div:hover { background: #F4F1ED; }
  #chat-pane .pick small { color: #8A8178; }
  @media (max-width: 760px) {
    #chat-pane { top: 0; right: 0; bottom: 0; width: 100vw; border-radius: 0; }
    #chat-pane .side { width: 100%; border-right: 0; } #chat-pane .main { display: none; }
    #chat-pane.conv .side { display: none; } #chat-pane.conv .main { display: flex; } #chat-pane .back { display: inline-block; }
    #chat-pane .m .acts { display: flex; position: static; box-shadow: none; border: 0; background: transparent; } #chat-pane .m:not(.mine) .acts { display: none; }
  }`;
  document.head.appendChild(css);

  // ---- the button beside the bell ---------------------------------------------------------------------
  const btn = document.createElement("button");
  btn.id = "chat-btn"; btn.type = "button"; btn.title = "Chat - who is online, messages";
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z"/><path d="M8.5 10.5h7M8.5 13.8h4.5"/></svg><span class="n" style="display:none"></span><span class="dot" style="display:none"></span>`;
  const bw = document.getElementById("bell-wrap"); bw.parentNode.insertBefore(btn, bw);
  btn.onclick = () => (S.open ? close() : open());

  const pane = document.createElement("div"); pane.id = "chat-pane";
  pane.innerHTML = `<div class="side"><h3>Chat <small data-n></small><span style="flex:1"></span><button class="x" data-x title="Close">&times;</button></h3>
      <input type="search" placeholder="Find a person" data-q><div class="list" data-list></div></div>
    <div class="main"><div class="hd" data-hd></div><div class="msgs" data-msgs></div>
      <div class="cmp"><div class="pick" data-pick></div><div class="editing" data-editing style="display:none"></div>
        <div class="box"><textarea rows="1" data-in placeholder="Write a message..."></textarea><button class="send" data-send>Send</button></div>
        <div class="hint">Enter to send &middot; Shift+Enter for a new line &middot; @ to tag someone</div></div></div>`;
  document.body.appendChild(pane);
  const $list = $("[data-list]", pane), $msgs = $("[data-msgs]", pane), $in = $("[data-in]", pane), $hd = $("[data-hd]", pane), $pick = $("[data-pick]", pane);
  $("[data-x]", pane).onclick = close;
  $("[data-q]", pane).oninput = e => { S.q = e.target.value.trim().toLowerCase(); drawList(); };

  // ---- time words -----------------------------------------------------------------------------------
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const hm = d => d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const dayKey = d => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  function dayWord(d) { const t = new Date(), y = new Date(); y.setDate(t.getDate() - 1);
    if (dayKey(d) === dayKey(t)) return "Today"; if (dayKey(d) === dayKey(y)) return "Yesterday";
    return `${d.toLocaleDateString("en-GB", { weekday: "long" })}, ${d.getDate()} ${MON[d.getMonth()]}${d.getFullYear() !== t.getFullYear() ? " " + d.getFullYear() : ""}`; }
  function ago(iso) { if (!iso) return "not seen yet"; const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 3600) return `seen ${Math.max(1, Math.round(s / 60))} min ago`; if (s < 86400) return `seen ${Math.round(s / 3600)} h ago`;
    const d = new Date(iso); return `seen ${d.getDate()} ${MON[d.getMonth()]}`; }

  // ---- the people list --------------------------------------------------------------------------------
  const userBy = id => S.users.find(u => u.id === id) || {};
  const roomName = r => r === "all" ? "Everyone" : (S.users.find(u => u.room === r && !u.me) || {}).name || "Chat";
  function avatar(u, sm) { return `<span class="av ${sm ? "sm" : ""}" style="background:${col(u.id)}">${esc(u.initials || "?")}${u.online !== undefined ? `<i class="${u.online ? "y" : ""}"></i>` : ""}</span>`; }
  function drawList() {
    const others = S.users.filter(u => !u.me && (!S.q || (u.name + " " + u.username).toLowerCase().includes(S.q)));
    const order = (a, b) => (S.unread[b.room] || 0) - (S.unread[a.room] || 0) || (S.last[b.room] || 0) - (S.last[a.room] || 0) || a.name.localeCompare(b.name);
    const on = others.filter(u => u.online).sort(order), off = others.filter(u => !u.online).sort(order);
    const row = u => `<div class="who ${S.room === u.room ? "on" : ""}" data-room="${u.room}">${avatar(u)}<div class="t"><b>${esc(u.name)}</b><span>${u.online ? "Online" : ago(u.last_seen)}</span></div>${S.unread[u.room] ? `<span class="u">${S.unread[u.room]}</span>` : ""}</div>`;
    const n = S.users.filter(u => u.online && !u.me).length;
    $("[data-n]", pane).textContent = `${n} online`;
    $list.innerHTML = (S.q ? "" : `<div class="who ${S.room === "all" ? "on" : ""}" data-room="all"><span class="av all">#</span><div class="t"><b>Everyone</b><span>The whole office sees this</span></div>${S.unread.all ? `<span class="u">${S.unread.all}</span>` : ""}</div>`)
      + `<div class="grp">Online &middot; ${on.length}</div>` + (on.map(row).join("") || `<div class="t" style="padding:4px 12px;font-size:12px;color:#8A8178">Nobody else right now</div>`)
      + (off.length ? `<div class="grp">Offline &middot; ${off.length}</div>` + off.map(row).join("") : "");
    $list.querySelectorAll("[data-room]").forEach(el => el.onclick = () => openRoom(el.dataset.room));
  }

  // ---- messages ------------------------------------------------------------------------------------------
  function fmt(t) {
    let h = esc(t);
    h = h.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
    h = h.replace(/(^|[^\w@])@([A-Za-z0-9][\w.\-]*)/g, (all, pre, tag) => {
      const t2 = tag.toLowerCase().replace(/[.\-]+$/, "");
      if (["everyone", "all", "here"].includes(t2)) return `${pre}<span class="tag me">@everyone</span>`;
      const u = S.users.find(x => x.username.toLowerCase() === t2);
      return u ? `${pre}<span class="tag ${u.me ? "me" : ""}">@${esc(u.name)}</span>${esc(tag.slice(t2.length))}` : all;
    });
    return h;
  }
  function drawMsgs(keepBottom) {
    const ms = S.msgs[S.room] || [];
    const atBottom = keepBottom || $msgs.scrollHeight - $msgs.scrollTop - $msgs.clientHeight < 80;
    if (!ms.length) { $msgs.innerHTML = `<div class="empty">${S.room === "all" ? "Say hello to everyone - the whole office sees what is written here." : `No messages yet. Write to ${esc(roomName(S.room))} - only the two of you see this.`}</div>`; return; }
    let h = S.more[S.room] ? `<button class="older" data-older>Show earlier messages</button>` : "", lastDay = "", prev = null;
    for (const m of ms) {
      const d = new Date(m.at), dk = dayKey(d);
      if (dk !== lastDay) { h += `<div class="day"><span>${dayWord(d)}</span></div>`; lastDay = dk; prev = null; }
      const first = !prev || prev.user_id !== m.user_id || (d - new Date(prev.at)) > 5 * 60000;
      const u = userBy(m.user_id), mine = m.user_id === S.me, tagged = !mine && (m.mentions.includes(S.me) || m.everyone);
      h += `<div class="m ${first ? "first" : ""} ${mine ? "mine" : ""} ${tagged ? "me-tag" : ""}" data-id="${m.id}">
        <div class="gut">${first ? avatar({ id: m.user_id, initials: m.initials }, true) : `<small>${hm(d)}</small>`}</div>
        <div class="bd">${first ? `<div class="nm">${esc(u.name || m.name)}<span class="tm">${hm(d)}</span></div>` : ""}
          <div class="tx">${m.deleted ? `<span class="del">Message deleted</span>` : fmt(m.text)}${m.edited && !m.deleted ? ` <span class="ed">(edited)</span>` : ""}</div></div>
        ${mine && !m.deleted ? `<div class="acts"><button data-ed="${m.id}">Edit</button><button data-dl="${m.id}">Delete</button></div>` : ""}</div>`;
      prev = m;
    }
    $msgs.innerHTML = h;
    if (atBottom) $msgs.scrollTop = $msgs.scrollHeight;
    const older = $("[data-older]", $msgs); if (older) older.onclick = loadOlder;
    $msgs.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => startEdit(+b.dataset.ed));
    $msgs.querySelectorAll("[data-dl]").forEach(b => b.onclick = () => delMsg(+b.dataset.dl));
  }
  function drawHead() {
    const u = S.users.find(x => x.room === S.room && !x.me);
    $hd.innerHTML = `<button class="back" data-back title="Back">&#8249;</button>` + (S.room === "all"
      ? `<span class="av all">#</span><div><b>Everyone</b><span>${S.users.length} people &middot; ${S.users.filter(x => x.online).length} online</span></div>`
      : `${avatar(u || {})}<div><b>${esc(u ? u.name : "")}</b><span>${u && u.online ? "Online" : ago(u && u.last_seen)} &middot; private</span></div>`)
      + `<span class="sp"></span><button class="x" data-x2 title="Close">&times;</button>`;
    $("[data-back]", $hd).onclick = () => { pane.classList.remove("conv"); S.room = ""; drawList(); };
    $("[data-x2]", $hd).onclick = close;
  }

  async function openRoom(room) {
    S.room = room; S.edit = null; showEditing();
    pane.classList.add("conv"); drawList(); drawHead();
    try { localStorage.setItem("chat_room", room); } catch (e) {}
    if (!S.msgs[room]) { $msgs.innerHTML = `<div class="empty">Loading...</div>`; await poll(true); } else { drawMsgs(true); await poll(); }
    if (innerWidth > 760) $in.focus();
  }
  async function loadOlder() {
    const ms = S.msgs[S.room] || []; if (!ms.length) return;
    const h0 = $msgs.scrollHeight;
    const r = await api(`/store/chat/history?room=${encodeURIComponent(S.room)}&before=${ms[0].id}`);
    S.msgs[S.room] = r.messages.concat(ms); S.more[S.room] = r.more;
    drawMsgs(); $msgs.scrollTop = $msgs.scrollHeight - h0;
  }

  // ---- the poll: presence, unread, new messages ---------------------------------------------------------
  async function poll(fresh) {
    if (S.busy || !(typeof TOKEN !== "undefined" ? TOKEN : sessionStorage.getItem("infinia_token"))) return;
    S.busy = true;
    try {
      const room = S.open ? S.room : "";
      const after = room && !fresh ? (S.lastId[room] || 0) : 0;
      const r = await api(`/store/chat/state?room=${encodeURIComponent(room)}&after=${after}`);
      S.me = r.me; S.users = r.users; S.unread = r.unread; S.last = r.last; S.mentions = r.mentions; S.total = r.total;
      if (room && r.messages) {
        if (fresh || !S.msgs[room]) { S.msgs[room] = r.messages; S.more[room] = r.more; }
        else if (r.messages.length) S.msgs[room] = S.msgs[room].concat(r.messages.filter(m => !S.msgs[room].some(x => x.id === m.id)));
        (r.changed || []).forEach(c => { const i = S.msgs[room].findIndex(x => x.id === c.id); if (i >= 0) S.msgs[room][i] = c; });
        const ms = S.msgs[room]; if (ms.length) S.lastId[room] = Math.max(S.lastId[room] || 0, ms[ms.length - 1].id);
        if (room === S.room) { drawMsgs(fresh); markRead(); }
      }
      badge(); if (S.open) { drawList(); if (S.room) drawHead(); }
    } catch (e) { /* signed out or offline - try again next time */ }
    finally { S.busy = false; }
  }
  function markRead() {
    if (!S.room || document.hidden || !S.open) return;
    const id = S.lastId[S.room] || 0; if (!id || !S.unread[S.room]) return;
    S.total -= S.unread[S.room]; S.unread[S.room] = 0; badge(); drawList();
    api("/store/chat/read", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ room: S.room, last_id: id }) }).catch(() => {});
  }
  function badge() {
    const n = $(".n", btn), dot = $(".dot", btn);
    n.style.display = S.total ? "" : "none"; n.textContent = S.total > 99 ? "99+" : S.total;
    const on = S.users.filter(u => u.online && !u.me).length;
    dot.style.display = !S.total && on ? "" : "none";
    btn.title = `Chat - ${on} online${S.total ? `, ${S.total} unread` : ""}`;
  }
  function schedule() { clearTimeout(S.timer); S.timer = setTimeout(async () => { await poll(); schedule(); }, S.open && !document.hidden ? 3000 : 20000); }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { poll().then(markRead); schedule(); } });

  // ---- writing -----------------------------------------------------------------------------------------------
  function grow() { $in.style.height = "auto"; $in.style.height = Math.min($in.scrollHeight, 160) + "px"; }
  async function send() {
    const text = $in.value.trim(); if (!text || !S.room) return;
    const sendB = $("[data-send]", pane); sendB.disabled = true;
    try {
      if (S.edit) {
        const m = await api(`/store/chat/messages/${S.edit}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
        const i = (S.msgs[S.room] || []).findIndex(x => x.id === m.id); if (i >= 0) S.msgs[S.room][i] = m;
        S.edit = null; showEditing();
      } else {
        const m = await api("/store/chat/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ room: S.room, text }) });
        (S.msgs[S.room] = S.msgs[S.room] || []).push(m); S.lastId[S.room] = Math.max(S.lastId[S.room] || 0, m.id);
        S.last[S.room] = m.id;
      }
      $in.value = ""; grow(); drawMsgs(true); drawList();
    } catch (e) { alertMsg(e); }
    finally { sendB.disabled = false; $in.focus(); }
  }
  function alertMsg(e) { const t = (e && (e.message || e.detail)) || "Could not send - check the connection."; $(".hint", pane).textContent = t; $(".hint", pane).style.color = "#C0392B"; setTimeout(() => { $(".hint", pane).innerHTML = "Enter to send &middot; Shift+Enter for a new line &middot; @ to tag someone"; $(".hint", pane).style.color = ""; }, 4000); }
  function startEdit(id) { const m = (S.msgs[S.room] || []).find(x => x.id === id); if (!m) return; S.edit = id; $in.value = m.text; grow(); showEditing(); $in.focus(); }
  function showEditing() { const e = $("[data-editing]", pane); e.style.display = S.edit ? "" : "none"; e.innerHTML = S.edit ? `Editing your message &middot; <a href="#" data-cancel>cancel</a>` : "";
    const c = $("[data-cancel]", e); if (c) c.onclick = ev => { ev.preventDefault(); S.edit = null; $in.value = ""; grow(); showEditing(); }; }
  async function delMsg(id) {
    if (!confirm("Delete this message? Everyone in the chat will see it was deleted.")) return;
    try { await api(`/store/chat/messages/${id}`, { method: "DELETE" }); const m = (S.msgs[S.room] || []).find(x => x.id === id); if (m) { m.deleted = true; m.text = ""; } drawMsgs(); } catch (e) { alertMsg(e); }
  }
  $("[data-send]", pane).onclick = send;

  // @ tagging: a list of people as the name is typed; Enter / Tab / click puts in @username
  let pickAt = -1, pickSel = 0, pickList = [];
  function pickUpdate() {
    const pos = $in.selectionStart, before = $in.value.slice(0, pos), m = before.match(/(^|\s)@([\w.\-]*)$/);
    if (!m) { $pick.style.display = "none"; pickAt = -1; return; }
    pickAt = pos - m[2].length - 1; const q = m[2].toLowerCase();
    pickList = S.users.filter(u => !u.me && (u.name.toLowerCase().split(/\s+/).some(w => w.startsWith(q)) || u.username.toLowerCase().startsWith(q))).slice(0, 8);
    if (S.room === "all" && "everyone".startsWith(q)) pickList.unshift({ username: "everyone", name: "Everyone", initials: "#", id: 0, all: true });
    if (!pickList.length) { $pick.style.display = "none"; return; }
    pickSel = Math.min(pickSel, pickList.length - 1);
    $pick.innerHTML = pickList.map((u, i) => `<div class="${i === pickSel ? "sel" : ""}" data-i="${i}">${u.all ? `<span class="av sm all">#</span>` : avatar(u, true)}<span>${esc(u.name)} <small>@${esc(u.username)}${u.online ? " &middot; online" : ""}</small></span></div>`).join("");
    $pick.style.display = "block";
    $pick.querySelectorAll("[data-i]").forEach(el => el.onmousedown = e => { e.preventDefault(); pickPut(+el.dataset.i); });
  }
  function pickPut(i) { const u = pickList[i]; if (!u) return; const pos = $in.selectionStart;
    $in.value = $in.value.slice(0, pickAt) + "@" + u.username + " " + $in.value.slice(pos); const c = pickAt + u.username.length + 2;
    $in.setSelectionRange(c, c); $pick.style.display = "none"; pickAt = -1; grow(); }
  $in.addEventListener("input", () => { grow(); pickSel = 0; pickUpdate(); });
  $in.addEventListener("click", pickUpdate);
  $in.addEventListener("keydown", e => {
    if ($pick.style.display === "block") {
      if (e.key === "ArrowDown") { e.preventDefault(); pickSel = (pickSel + 1) % pickList.length; pickUpdate(); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); pickSel = (pickSel - 1 + pickList.length) % pickList.length; pickUpdate(); return; }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pickPut(pickSel); return; }
      if (e.key === "Escape") { $pick.style.display = "none"; return; }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    if (e.key === "Escape" && S.edit) { S.edit = null; $in.value = ""; grow(); showEditing(); }
  });

  // ---- open / close ---------------------------------------------------------------------------------------------
  async function open(room) {
    S.open = true; pane.classList.add("on");
    let want = room; if (!want) { try { want = localStorage.getItem("chat_room") || ""; } catch (e) {} }
    if (innerWidth <= 760 && !room) want = "";
    await poll();
    if (want && (want === "all" || S.users.some(u => u.room === want))) openRoom(want);
    else if (innerWidth > 760) openRoom("all");
    else { pane.classList.remove("conv"); drawList(); }
    schedule();
  }
  function close() { S.open = false; pane.classList.remove("on"); $pick.style.display = "none"; schedule(); }
  document.addEventListener("keydown", e => { if (e.key === "Escape" && S.open && $pick.style.display !== "block" && !S.edit && !document.querySelector(".modal.show")) close(); });

  window.CHAT = { open, close, poll, state: S };
  setTimeout(() => { poll(); schedule(); }, 1500);
})();
