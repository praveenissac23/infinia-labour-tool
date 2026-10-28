/* In-app chat - who is online, Everyone, and a private chat with anyone.
   The button sits beside the bell; the panel slides in from the right (full screen on a phone).
   Enter sends, Shift+Enter for a new line, @ to tag someone (@everyone in Everyone). */
(function () {
  if (window.CHAT || !document.getElementById("bell-wrap")) return;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COLORS = ["#C0392B", "#1F7A8C", "#6D4C9F", "#2E7D32", "#B26A00", "#AD1457", "#1565C0", "#5D4037", "#00838F", "#7B1FA2"];
  const col = id => COLORS[(id || 0) % COLORS.length];
  // its own requests: the chat polls all day, and must neither clear the app's shared reads nor hold a screen back
  async function api(u, o = {}) {
    const tok = (typeof TOKEN !== "undefined" && TOKEN) || sessionStorage.getItem("infinia_token");
    const headers = Object.assign({}, o.headers || {}, tok ? { Authorization: "Bearer " + tok } : {});
    if (typeof o.body === "string" && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const r = await fetch((typeof API !== "undefined" ? API : "") + u, Object.assign({}, o, { headers }));
    if (!r.ok) { let d = ""; try { const j = await r.json(); d = typeof j.detail === "string" ? j.detail : ""; } catch (e) {}
      throw new Error(d || (r.status === 413 ? "That file is too big for the server." : "Could not send - check the connection.")); }
    return r.json();
  }
  const KEEP = 7;     // days the server keeps a file or voice message (chat.KEEP_DAYS)
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
  #chat-pane .cmp .tool { border: 0; background: transparent; width: 36px; height: 36px; border-radius: 9px; cursor: pointer; color: #6B7178; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
  #chat-pane .cmp .tool:hover { background: #F4F1ED; color: #22262A; } #chat-pane .cmp .tool svg { width: 21px; height: 21px; }
  #chat-pane .att { display: flex; align-items: center; gap: 10px; border: 1px solid #E6E0D9; background: #FBFAF8; border-radius: 10px; padding: 7px 10px; margin-bottom: 7px; font-size: 13px; }
  #chat-pane .att img { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; } #chat-pane .att .nm2 { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #chat-pane .att button { border: 0; background: transparent; font-size: 18px; cursor: pointer; color: #8A8178; }
  #chat-pane .rec { display: flex; align-items: center; gap: 12px; border: 1px solid #F1C7C1; background: #FFF6F5; border-radius: 12px; padding: 8px 10px 8px 14px; }
  #chat-pane .rec .rd { width: 11px; height: 11px; border-radius: 50%; background: #E03A2F; animation: chatblink 1s infinite; }
  #chat-pane .rec .tm2 { font-variant-numeric: tabular-nums; font-weight: 700; min-width: 44px; } #chat-pane .rec .wave { flex: 1; height: 26px; display: flex; align-items: center; gap: 2px; overflow: hidden; }
  #chat-pane .rec .wave i { width: 3px; background: #E8857C; border-radius: 2px; flex-shrink: 0; }
  #chat-pane .rec button { border: 0; border-radius: 9px; padding: 7px 14px; font-weight: 700; cursor: pointer; font-size: 13px; } #chat-pane .rec .cx { background: transparent; color: #6B7178; } #chat-pane .rec .ok { background: #C0392B; color: #fff; }
  @keyframes chatblink { 50% { opacity: .25; } }
  #chat-pane .fimg { display: block; margin-top: 4px; max-width: min(320px, 100%); max-height: 260px; border-radius: 10px; border: 1px solid #ECE8E3; cursor: zoom-in; }
  #chat-pane .ffile { display: inline-flex; align-items: center; gap: 10px; margin-top: 4px; border: 1px solid #E6E0D9; border-radius: 10px; padding: 8px 12px; text-decoration: none; color: #22262A; max-width: 100%; background: #FBFAF8; }
  #chat-pane .ffile:hover { background: #F4F1ED; } #chat-pane .ffile b { font-weight: 600; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; max-width: 260px; }
  #chat-pane .ffile small, #chat-pane .fnote { font-size: 11px; color: #8A8178; } #chat-pane .ffile .ic { width: 34px; height: 34px; border-radius: 8px; background: #C0392B; color: #fff; font: 700 10px/34px sans-serif; text-align: center; flex-shrink: 0; }
  #chat-pane .fvoice { display: flex; align-items: center; gap: 8px; margin-top: 4px; } #chat-pane .fvoice audio { height: 36px; max-width: 280px; }
  #chat-pane .fgone { display: inline-block; margin-top: 4px; font-size: 12.5px; color: #8A8178; border: 1px dashed #D9D2C9; border-radius: 8px; padding: 6px 10px; }
  #chat-pane.drop .main::after { content: "Drop to send"; position: absolute; inset: 0; background: rgba(192,57,43,.08); border: 2px dashed #C0392B; border-radius: 0 14px 14px 0; display: flex; align-items: center; justify-content: center; font-weight: 700; color: #C0392B; font-size: 16px; pointer-events: none; }
  #chat-pane .main { position: relative; }
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
      <div class="cmp"><div class="pick" data-pick></div><div class="editing" data-editing style="display:none"></div><div data-att></div>
        <div class="box" data-box><button class="tool" data-clip title="Attach a file or photo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5l-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6l7.9-7.9"/></svg></button>
          <textarea rows="1" data-in placeholder="Write a message..."></textarea>
          <button class="tool" data-mic title="Record a voice message"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></button>
          <button class="send" data-send>Send</button></div>
        <div class="rec" data-rec style="display:none"><span class="rd"></span><span class="tm2" data-rt>0:00</span><span class="wave" data-wave></span><button class="cx" data-rcancel>Cancel</button><button class="ok" data-rsend>Send</button></div>
        <input type="file" data-file hidden>
        <div class="hint">Enter to send &middot; Shift+Enter for a new line &middot; @ to tag someone &middot; files and voice messages are kept ${KEEP} days</div></div></div>`;
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
          ${m.text || m.deleted ? `<div class="tx">${m.deleted ? `<span class="del">Message deleted</span>` : fmt(m.text)}${m.edited && !m.deleted ? ` <span class="ed">(edited)</span>` : ""}</div>` : ""}${m.file ? fileHtml(m.file) : ""}</div>
        ${mine && !m.deleted ? `<div class="acts"><button data-ed="${m.id}">Edit</button><button data-dl="${m.id}">Delete</button></div>` : ""}</div>`;
      prev = m;
    }
    $msgs.innerHTML = h;
    if (atBottom) $msgs.scrollTop = $msgs.scrollHeight;
    const older = $("[data-older]", $msgs); if (older) older.onclick = loadOlder;
    $msgs.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => startEdit(+b.dataset.ed));
    $msgs.querySelectorAll("[data-dl]").forEach(b => b.onclick = () => delMsg(+b.dataset.dl));
  }
  const kb = n => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  const until = f => { if (!f.until) return ""; const d = new Date(f.until); return `kept until ${d.getDate()} ${MON[d.getMonth()]}`; };
  function fileHtml(f) {
    if (f.gone || !f.url) return `<div class="fgone">${f.kind === "voice" ? "Voice message" : f.kind === "image" ? "Photo" : esc(f.name)} - no longer kept (files are removed after ${KEEP} days)</div>`;
    const u = (typeof API !== "undefined" ? API : "") + f.url;
    if (f.kind === "image") return `<a href="${u}" target="_blank" rel="noopener"><img class="fimg" src="${u}" alt="${esc(f.name)}" loading="lazy"></a><div class="fnote">${until(f)}</div>`;
    if (f.kind === "voice") return `<div class="fvoice"><audio controls preload="metadata" src="${u}"></audio><span class="fnote">${f.duration ? Math.floor(f.duration / 60) + ":" + String(f.duration % 60).padStart(2, "0") + " &middot; " : ""}${until(f)}</span></div>`;
    const ext = (f.name.split(".").pop() || "file").slice(0, 4).toUpperCase();
    return `<a class="ffile" href="${u}?dl=1" target="_blank" rel="noopener"><span class="ic">${esc(ext)}</span><span><b>${esc(f.name)}</b><small>${kb(f.size)} &middot; ${until(f)} &middot; download</small></span></a>`;
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
    if (R) stopRec(false);
    S.room = room; S.edit = null; showEditing(); S.file = null; drawAtt();
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
    if (S.file) return sendFile(S.file, $in.value.trim());
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
  // ---- files and photos: the paper clip, a paste, or a drop on the chat ----------------------------------------
  const $att = $("[data-att]", pane), $file = $("[data-file]", pane);
  $("[data-clip]", pane).onclick = () => $file.click();
  $file.onchange = () => { if ($file.files[0]) pickFile($file.files[0]); $file.value = ""; };
  async function shrink(f) {           // a phone photo of 6 MB goes as a sharp 2000-pixel picture of a few hundred KB
    if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size < 900 * 1024) return f;
    try { const bmp = await createImageBitmap(f); const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
      const c = document.createElement("canvas"); c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
      const b = await new Promise(r => c.toBlob(r, "image/jpeg", 0.85)); return b && b.size < f.size ? new File([b], f.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : f;
    } catch (e) { return f; }
  }
  async function pickFile(f) {
    if (!S.room) return;
    if (f.size > 25 * 1048576) { alertMsg(new Error("Up to 25 MB can be sent.")); return; }
    S.file = await shrink(f); drawAtt(); $in.focus();
  }
  function drawAtt() {
    const f = S.file; if (!f) { $att.innerHTML = ""; return; }
    const img = /^image\//.test(f.type) ? `<img src="${URL.createObjectURL(f)}">` : `<span class="ic" style="width:44px;height:44px;border-radius:6px;background:#C0392B;color:#fff;font:700 11px/44px sans-serif;text-align:center">${esc((f.name.split(".").pop() || "").slice(0, 4).toUpperCase())}</span>`;
    $att.innerHTML = `<div class="att">${img}<span class="nm2"><b>${esc(f.name)}</b><br><small style="color:#8A8178">${kb(f.size)} &middot; add a message if you like, then Send</small></span><button title="Remove" data-rm>&times;</button></div>`;
    $("[data-rm]", $att).onclick = () => { S.file = null; drawAtt(); };
  }
  async function sendFile(f, text, kind, duration) {
    if (!S.room) return;
    const sendB = $("[data-send]", pane); sendB.disabled = true; const was = sendB.textContent; sendB.textContent = "Sending...";
    try {
      const fd = new FormData(); fd.append("room", S.room); fd.append("file", f, f.name || "file"); fd.append("text", text || "");
      if (kind) fd.append("kind", kind); if (duration) fd.append("duration", String(duration));
      const m = await api("/store/chat/upload", { method: "POST", body: fd });
      (S.msgs[S.room] = S.msgs[S.room] || []).push(m); S.lastId[S.room] = Math.max(S.lastId[S.room] || 0, m.id); S.last[S.room] = m.id;
      if (!kind) { S.file = null; drawAtt(); $in.value = ""; grow(); }
      drawMsgs(true); drawList();
    } catch (e) { alertMsg(e); }
    finally { sendB.disabled = false; sendB.textContent = was; }
  }
  $in.addEventListener("paste", e => { const f = [...(e.clipboardData || {}).files || []][0]; if (f) { e.preventDefault(); pickFile(f); } });
  const main = $(".main", pane);
  main.addEventListener("dragover", e => { if ([...(e.dataTransfer.types || [])].includes("Files")) { e.preventDefault(); pane.classList.add("drop"); } });
  main.addEventListener("dragleave", e => { if (!main.contains(e.relatedTarget)) pane.classList.remove("drop"); });
  main.addEventListener("drop", e => { e.preventDefault(); pane.classList.remove("drop"); const f = e.dataTransfer.files[0]; if (f) pickFile(f); });

  // ---- voice messages: press the microphone, speak, Send (up to 5 minutes) -------------------------------------
  const $rec = $("[data-rec]", pane), $box = $("[data-box]", pane), $rt = $("[data-rt]", pane), $wave = $("[data-wave]", pane);
  let R = null;
  $("[data-mic]", pane).onclick = startRec;
  async function startRec() {
    if (!S.room || R) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) { alertMsg(new Error("This browser cannot record - use Chrome, Edge or Safari.")); return; }
    let stream; try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { alertMsg(new Error("The microphone is blocked - allow it for this site and try again.")); return; }
    const type = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
    const rec = new MediaRecorder(stream, type ? { mimeType: type, audioBitsPerSecond: 32000 } : {});
    const chunks = []; rec.ondataavailable = e => e.data.size && chunks.push(e.data);
    let ctx, an; try { ctx = new AudioContext(); an = ctx.createAnalyser(); an.fftSize = 256; ctx.createMediaStreamSource(stream).connect(an); } catch (e) {}
    R = { rec, stream, chunks, t0: Date.now(), ctx, an, send: false };
    rec.onstop = async () => {
      stream.getTracks().forEach(t => t.stop()); try { ctx && ctx.close(); } catch (e) {}
      const secs = Math.round((Date.now() - R.t0) / 1000), go = R.send; clearInterval(R.tick); R = null;
      $rec.style.display = "none"; $box.style.display = ""; $wave.innerHTML = "";
      if (!go || secs < 1 || !chunks.length) return;
      const mime = (rec.mimeType || "audio/webm").split(";")[0];
      const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
      await sendFile(new File(chunks, `voice.${ext}`, { type: mime }), "", "voice", secs);
    };
    rec.start(250);
    $box.style.display = "none"; $rec.style.display = "flex";
    const bars = new Uint8Array(128);
    R.tick = setInterval(() => {
      const s = Math.floor((Date.now() - R.t0) / 1000); $rt.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
      if (R.an) { R.an.getByteTimeDomainData(bars); let pk = 0; for (const v of bars) pk = Math.max(pk, Math.abs(v - 128));
        const i = document.createElement("i"); i.style.height = Math.max(3, Math.min(26, pk / 2.4)) + "px"; $wave.appendChild(i); if ($wave.children.length > 120) $wave.firstChild.remove(); }
      if (s >= 300) stopRec(true);       // five minutes at most
    }, 120);
  }
  function stopRec(send) { if (!R) return; R.send = send; try { R.rec.stop(); } catch (e) {} }
  $("[data-rcancel]", pane).onclick = () => stopRec(false);
  $("[data-rsend]", pane).onclick = () => stopRec(true);

  function alertMsg(e) { const t = (e && (e.message || e.detail || (e.body && e.body.detail))) || "Could not send - check the connection."; $(".hint", pane).textContent = t; $(".hint", pane).style.color = "#C0392B"; setTimeout(() => { $(".hint", pane).innerHTML = `Enter to send &middot; Shift+Enter for a new line &middot; @ to tag someone &middot; files and voice messages are kept ${KEEP} days`; $(".hint", pane).style.color = ""; }, 4000); }
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
  function close() { if (R) stopRec(false); S.open = false; pane.classList.remove("on"); $pick.style.display = "none"; schedule(); }
  document.addEventListener("keydown", e => { if (e.key === "Escape" && S.open && $pick.style.display !== "block" && !S.edit && !document.querySelector(".modal.show")) close(); });

  window.CHAT = { open, close, poll, state: S };
  setTimeout(() => { poll(); schedule(); }, 1500);
})();
