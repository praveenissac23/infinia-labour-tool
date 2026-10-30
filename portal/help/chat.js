/* Infinia Chat - works like WhatsApp (so everyone already knows it), in Infinia's own colours, inside the portal.
   Chats on the left (Everyone + every person, newest first, unread in green, who is online), the conversation
   on the right: bubbles (mine green on the right), time and ticks in the bubble (one grey = sent, two grey =
   delivered, two blue = read), photos, documents and voice notes as WhatsApp shows them.
   Files live only while the sender has the portal open (gone on sign out, closing the portal, computer off).
   Enter sends, Shift+Enter new line, @ to tag someone (@everyone in Everyone). */
(function () {
  if (window.CHAT || !document.getElementById("bell-wrap")) return;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // WhatsApp's own colours for names in a group
  const COLORS = ["#06CF9C", "#FF2E74", "#A62C71", "#E26AB6", "#53BDEB", "#FC9775", "#5BCC88", "#FFBC38", "#00A884", "#7F66FF", "#02A698", "#D88DEF", "#E542A3", "#FA6533"];
  const AVC = ["#DFE5E7"];
  const col = id => COLORS[(id || 0) % COLORS.length];
  const tok = () => (typeof TOKEN !== "undefined" && TOKEN) || sessionStorage.getItem("infinia_token");
  // its own requests: the chat polls all day, and must neither clear the app's shared reads nor hold a screen back
  async function api(u, o = {}) {
    const t = tok();
    const headers = Object.assign({}, o.headers || {}, t ? { Authorization: "Bearer " + t } : {});
    if (typeof o.body === "string" && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const r = await fetch((typeof API !== "undefined" ? API : "") + u, Object.assign({}, o, { headers }));
    if (!r.ok) { let d = ""; try { const j = await r.json(); d = typeof j.detail === "string" ? j.detail : ""; } catch (e) {}
      throw new Error(d || (r.status === 413 ? "That file is too big for the server." : "Could not send - check the connection.")); }
    return r.json();
  }
  const S = { receipts: {}, previews: {}, open: false, room: "", users: [], me: 0, unread: {}, last: {}, msgs: {}, lastId: {}, more: {},
              timer: 0, busy: false, q: "", filter: "all", edit: null, mentions: 0, total: 0, file: null };

  // ---- the look: WhatsApp Web --------------------------------------------------------------------------------
  // The chat's wallpaper: soft flowing lines (like a site survey's contours) on warm paper, a faint Infinia glow
  // in one corner - quiet enough to read on all day.
  const CONTOURS = (() => { let p = ""; const W = 1600, H = 1000;
    for (let k = 0; k < 22; k++) { const y0 = -60 + k * 52, a1 = 26 + (k % 5) * 7, a2 = 14 + (k % 3) * 9, ph = k * 0.55;
      let d = `M -20 ${y0.toFixed(1)}`;
      for (let x = 0; x <= W + 40; x += 40) { const y = y0 + Math.sin(x / 260 + ph) * a1 + Math.sin(x / 113 - ph * 1.7) * a2 + (x / W) * 60; d += ` L ${x} ${y.toFixed(1)}`; }
      p += `<path d="${d}" stroke="${k % 4 === 0 ? "#C9A49A" : "#C8BCAF"}" stroke-opacity="${k % 4 === 0 ? 0.42 : 0.30}" stroke-width="${k % 4 === 0 ? 1.3 : 0.9}" fill="none"/>`; }
    return "data:image/svg+xml," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">${p}</svg>`); })();
  const WALL_OLD = "data:image/svg+xml," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120"><g fill="none" stroke="#d6cfc4" stroke-width="1.2" opacity=".55"><circle cx="18" cy="20" r="6"/><path d="M60 12l6 10H54z"/><rect x="94" y="14" width="12" height="9" rx="2"/><path d="M14 64c4-6 10-6 14 0"/><circle cx="62" cy="62" r="3"/><path d="M96 58l8 8M104 58l-8 8"/><rect x="12" y="98" width="10" height="10" rx="5"/><path d="M56 100h12M62 94v12"/><path d="M94 100q6-8 12 0"/></g></svg>`);
  const css = document.createElement("style");
  css.textContent = `
  #chat-btn { position: relative; width: 38px; height: 38px; border-radius: 50%; border: 0; background: transparent; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; margin-right: 6px; color: #54656F; }
  #chat-btn:hover { background: #F0F2F5; } #chat-btn svg { width: 25px; height: 25px; }
  #chat-btn .n { position: absolute; top: -1px; right: -3px; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 10px; background: #C0392B; color: #fff; font: 700 11px/19px -apple-system, sans-serif; text-align: center; box-sizing: border-box; box-shadow: 0 0 0 2px #fff; }
  #wa { position: fixed; top: 70px; right: 14px; bottom: 14px; width: min(1180px, calc(100vw - 28px)); z-index: 6000; background: #fff; border-radius: 10px; box-shadow: 0 18px 50px rgba(11,20,26,.30); display: none; overflow: hidden;
        font: 14.2px/1.4 "Segoe UI", -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif; color: #111B21; }
  #wa.on { display: flex; } #wa::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: #C0392B; z-index: 3; } #wa * { box-sizing: border-box; }
  #wa .side { width: 36%; min-width: 300px; max-width: 420px; border-right: 1px solid #E9EDEF; display: flex; flex-direction: column; background: #fff; }
  #wa .bar { height: 59px; flex-shrink: 0; background: #F0F2F5; display: flex; align-items: center; gap: 12px; padding: 0 16px; }
  #wa .bar .ttl { font-size: 16px; font-weight: 600; flex: 1; } #wa .bar .sub { font-size: 13px; color: #667781; }
  #wa .ib { border: 0; background: transparent; width: 40px; height: 40px; border-radius: 50%; cursor: pointer; color: #54656F; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
  #wa .ib:hover { background: rgba(11,20,26,.06); } #wa .ib svg { width: 24px; height: 24px; }
  #wa .srch { padding: 7px 12px; border-bottom: 1px solid #E9EDEF; } #wa .srch div { display: flex; align-items: center; gap: 14px; background: #F0F2F5; border-radius: 8px; padding: 0 12px; height: 35px; }
  #wa .srch svg { width: 18px; color: #54656F; flex-shrink: 0; } #wa .srch input { flex: 1; border: 0; background: transparent; outline: 0; font: inherit; font-size: 14px; color: #111B21; }
  #wa .chips { display: flex; gap: 8px; padding: 8px 14px 6px; } #wa .chips button { border: 0; background: #F0F2F5; color: #54656F; border-radius: 16px; padding: 5px 12px; font: inherit; font-size: 14px; cursor: pointer; }
  #wa .chips button.on { background: #FBE9E7; color: #A93226; font-weight: 600; }
  #wa .list { flex: 1; overflow-y: auto; }
  #wa .row { display: flex; align-items: center; height: 72px; padding: 0 0 0 13px; cursor: pointer; }
  #wa .row:hover { background: #F5F6F6; } #wa .row.sel { background: #F6EFEC; box-shadow: inset 3px 0 0 #C0392B; }
  #wa .row .rb { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; justify-content: center; border-bottom: 1px solid #E9EDEF; padding-right: 15px; margin-left: 13px; }
  #wa .row .l1, #wa .row .l2 { display: flex; align-items: center; gap: 6px; } #wa .row .nm { flex: 1; font-size: 17px; color: #111B21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #wa .row .tm { font-size: 12px; color: #667781; } #wa .row.un .tm { color: #C0392B; font-weight: 600; }
  #wa .row .pv { flex: 1; font-size: 14px; color: #667781; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 3px; min-width: 0; }
  #wa .row .pv span.t { overflow: hidden; text-overflow: ellipsis; } #wa .row .ub { min-width: 20px; height: 20px; border-radius: 10px; background: #C0392B; color: #fff; font-size: 12px; font-weight: 600; display: flex; align-items: center; justify-content: center; padding: 0 6px; }
  #wa .row .at { color: #C0392B; font-weight: 700; font-size: 15px; }
  #wa .av { position: relative; width: 49px; height: 49px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; color: #fff; font-weight: 600; font-size: 17px; }
  #wa .av.sm { width: 40px; height: 40px; font-size: 15px; } #wa .av.grp { background: #DFE5E7; color: #fff; } #wa .av.grp svg { width: 30px; height: 30px; }
  #wa .av i { position: absolute; right: 0; bottom: 1px; width: 13px; height: 13px; border-radius: 50%; background: #25D366; box-shadow: 0 0 0 2.5px #fff; }
  #wa .main { flex: 1; display: flex; flex-direction: column; min-width: 0; background: #F7F3EE; position: relative; }
  #wa .main .bar { border-left: 1px solid #E9EDEF; gap: 15px; padding: 0 10px 0 16px; }
  #wa .main .bar .who { flex: 1; min-width: 0; cursor: default; } #wa .main .bar .who b { display: block; font-size: 16px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #wa .main .bar .who span { display: block; font-size: 13px; color: #667781; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #wa .back { display: none; }
  #wa .msgs { flex: 1; overflow-y: auto; padding: 12px 7% 8px;
    background: radial-gradient(900px 520px at 0% 0%, rgba(192,57,43,.075), transparent 62%), radial-gradient(800px 600px at 100% 100%, rgba(120,110,100,.08), transparent 60%),
                url("${CONTOURS}") center / cover no-repeat, linear-gradient(160deg, #FBF8F4 0%, #F2EDE6 100%); }
  #wa .day { text-align: center; margin: 12px 0 10px; } #wa .day span { display: inline-block; font-size: 12.5px; color: #54656F; background: #fff; padding: 5px 12px; border-radius: 7.5px; box-shadow: 0 1px .5px rgba(11,20,26,.13); text-transform: uppercase; }
  #wa .note { text-align: center; margin: 6px auto 12px; max-width: 520px; } #wa .note span { display: inline-block; font-size: 12.5px; color: #54656F; background: #FFEECD; padding: 6px 12px; border-radius: 7.5px; box-shadow: 0 1px .5px rgba(11,20,26,.13); }
  #wa .ln { display: flex; margin-bottom: 2px; } #wa .ln.me { justify-content: flex-end; } #wa .ln.first { margin-top: 10px; }
  #wa .bub { position: relative; max-width: min(65%, 560px); background: #fff; border-radius: 7.5px; padding: 6px 7px 8px 9px; box-shadow: 0 1px .5px rgba(11,20,26,.13); font-size: 14.2px; line-height: 19px; }
  #wa .ln.me .bub { background: #FCE9E4; }
  #wa .ln.first .bub { border-top-left-radius: 0; } #wa .ln.me.first .bub { border-top-left-radius: 7.5px; border-top-right-radius: 0; }
  #wa .ln.first .bub::before { content: ""; position: absolute; top: 0; left: -8px; width: 8px; height: 13px; background: linear-gradient(to bottom left, #fff 50%, transparent 50%); }
  #wa .ln.me.first .bub::before { left: auto; right: -8px; background: linear-gradient(to bottom right, #FCE9E4 50%, transparent 50%); }
  #wa .bub .snd { font-size: 12.8px; font-weight: 500; margin-bottom: 2px; }
  #wa .bub .tx { white-space: pre-wrap; overflow-wrap: anywhere; } #wa .bub .tx a { color: #027EB5; }
  #wa .bub .meta { float: right; margin: 6px 0 -5px 10px; font-size: 11px; color: #667781; display: inline-flex; align-items: center; gap: 3px; height: 15px; position: relative; top: 4px; white-space: nowrap; }
  #wa .bub .meta.ov { position: absolute; right: 6px; bottom: 6px; top: auto; float: none; margin: 0; color: #fff; background: linear-gradient(to top, rgba(0,0,0,.45), transparent); padding: 10px 5px 2px 20px; border-radius: 0 0 6px 6px; height: auto; }
  #wa .bub .ed { font-style: italic; } #wa .bub .dm { display: flex; justify-content: flex-end; margin-top: 2px; } #wa .bub .meta.st { float: none; position: static; margin: 0; height: auto; } #wa .bub .del { color: #8696A0; font-style: italic; }
  #wa .tk svg { width: 16px; height: 11px; display: block; } #wa .tk.s, #wa .tk.d { color: #8696A0; } #wa .tk.r { color: #53BDEB; } #wa .meta.ov .tk.s, #wa .meta.ov .tk.d { color: #fff; }
  #wa .tag { color: #027EB5; } #wa .tag.me { color: #027EB5; font-weight: 600; }
  #wa .ln.ment .bub { box-shadow: 0 1px .5px rgba(11,20,26,.13), inset 3px 0 0 #FFBC38; }
  #wa .menu { position: absolute; top: 2px; right: 2px; width: 26px; height: 22px; border: 0; border-radius: 0 7px 0 12px; background: inherit; color: #8696A0; cursor: pointer; display: none; font-size: 15px; line-height: 1; }
  #wa .bub:hover .menu { display: block; } #wa .pop { position: absolute; z-index: 5; background: #fff; border-radius: 3px; box-shadow: 0 2px 5px rgba(11,20,26,.26), 0 2px 10px rgba(11,20,26,.16); padding: 9px 0; min-width: 150px; }
  #wa .pop button { display: block; width: 100%; text-align: left; border: 0; background: transparent; padding: 9px 24px; font: inherit; font-size: 14.5px; color: #3B4A54; cursor: pointer; } #wa .pop button:hover { background: #F5F6F6; }
  /* photos */
  #wa .bub.img { padding: 3px; } #wa .bub.img .snd { padding: 3px 6px 1px; } #wa .bub.img .tx { padding: 4px 6px 2px; }
  #wa .ph { display: block; position: relative; border-radius: 6px; overflow: hidden; cursor: pointer; } #wa .ph img { display: block; width: 330px; max-width: 100%; max-height: 340px; object-fit: cover; min-height: 120px; background: #D1D7DB; }
  /* documents */
  #wa .doc { display: flex; align-items: center; gap: 10px; background: rgba(11,20,26,.05); border-radius: 6px; padding: 10px; margin: 0 0 2px; text-decoration: none; color: #111B21; min-width: 260px; }
  #wa .ln.me .doc { background: rgba(150,40,30,.06); } #wa .doc .di { width: 30px; height: 38px; border-radius: 3px; position: relative; flex-shrink: 0; color: #fff; font: 700 8px/1 sans-serif; display: flex; align-items: flex-end; justify-content: center; padding-bottom: 5px; }
  #wa .doc .dn { flex: 1; min-width: 0; } #wa .doc .dn b { display: block; font-weight: 400; font-size: 14.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } #wa .doc .dn small { font-size: 12px; color: #667781; }
  #wa .docw { cursor: pointer; min-width: 260px; max-width: 330px; } #wa .docw .doc { min-width: 0; } #wa .docw:hover .doc { background: rgba(11,20,26,.08); }
  #wa .dth { display: none; height: 130px; overflow: hidden; border-radius: 6px 6px 0 0; background: #fff; margin-bottom: -2px; } #wa .dth.ok { display: block; }
  #wa .dth img { width: 100%; display: block; } #wa .dth.ok + .doc { border-radius: 0 0 6px 6px; }
  #wa .doc .dl { text-decoration: none; width: 34px; height: 34px; border-radius: 50%; border: 1px solid #8696A0; color: #8696A0; display: flex; align-items: center; justify-content: center; flex-shrink: 0; } #wa .doc .dl svg { width: 16px; }
  /* voice notes */
  #wa .vn { display: flex; align-items: center; gap: 10px; width: 300px; max-width: 100%; padding: 2px 0 0; }
  #wa .vn .vp { position: relative; flex-shrink: 0; } #wa .vn .vp .av { width: 50px; height: 50px; } #wa .vn .vp .mic { position: absolute; right: -4px; bottom: -2px; color: #53BDEB; width: 19px; height: 19px; }
  #wa .ln.me .vn .vp .mic { color: #53BDEB; }
  #wa .vn .play { width: 34px; height: 34px; border: 0; background: transparent; color: #8696A0; cursor: pointer; flex-shrink: 0; padding: 0; display: flex; align-items: center; justify-content: center; } #wa .vn .play svg { width: 26px; height: 26px; }
  #wa .vn .wv { flex: 1; min-width: 0; } #wa .vn .bars { height: 26px; display: flex; align-items: center; gap: 2px; cursor: pointer; position: relative; }
  #wa .vn .bars i { flex: 1; max-width: 3px; min-width: 2px; background: #B3BABE; border-radius: 2px; } #wa .vn .bars i.p { background: #53BDEB; } #wa .ln.me .vn .bars i { background: #D9A9A1; } #wa .ln.me .vn .bars i.p { background: #53BDEB; }
  #wa .vn .vt { font-size: 11px; color: #667781; margin-top: 2px; display: flex; justify-content: space-between; }
  #wa .vn .spd { border: 0; background: rgba(11,20,26,.1); color: #fff; border-radius: 12px; font-size: 12px; font-weight: 700; padding: 3px 7px; cursor: pointer; display: none; }
  #wa .vn.playing .spd { display: block; background: #8696A0; } #wa .vn.playing .vp { display: none; }
  #wa .gone { display: flex; align-items: center; gap: 8px; color: #667781; font-size: 13.5px; font-style: italic; padding: 4px 2px; }
  #wa .gone svg { width: 18px; flex-shrink: 0; }
  #wa .older { display: block; margin: 4px auto 10px; border: 0; background: #fff; border-radius: 15px; padding: 5px 14px; font-size: 13px; cursor: pointer; color: #54656F; box-shadow: 0 1px .5px rgba(11,20,26,.13); }
  /* the composer */
  #wa .cmp { flex-shrink: 0; background: #F0F2F5; padding: 5px 16px; display: flex; align-items: flex-end; gap: 8px; min-height: 62px; position: relative; }
  #wa .cmp .ib { margin-bottom: 6px; } #wa .cmp .ib svg { width: 26px; height: 26px; }
  #wa .cmp .inw { flex: 1; background: #fff; border-radius: 8px; padding: 9px 12px; margin: 5px 0; min-width: 0; }
  #wa .cmp textarea { width: 100%; border: 0; outline: 0; resize: none; font: inherit; font-size: 15px; line-height: 20px; max-height: 120px; display: block; background: transparent; color: #111B21; }
  #wa .cmp .rec { flex: 1; display: none; align-items: center; justify-content: flex-end; gap: 16px; padding: 0 6px; height: 52px; } #wa .cmp.recording .rec { display: flex; } #wa .cmp.recording .inw, #wa .cmp.recording [data-clip] { display: none; }
  #wa .rec .rd { width: 10px; height: 10px; border-radius: 50%; background: #EA0038; animation: wablink 1.2s infinite; } #wa .rec .rt { font-size: 18px; color: #3B4A54; min-width: 46px; font-variant-numeric: tabular-nums; }
  #wa .rec .wave { width: 160px; height: 26px; display: flex; align-items: center; justify-content: flex-end; gap: 2px; overflow: hidden; } #wa .rec .wave i { width: 3px; background: #8696A0; border-radius: 2px; flex-shrink: 0; }
  #wa .rec .ib.del { color: #8696A0; }
  #wa .snd2 { width: 42px; height: 42px; border-radius: 50%; } #wa .cmp .go { color: #54656F; } #wa .cmp.recording .go, #wa .cmp.typing .go { color: #fff; background: #C0392B; }
  #wa .cmp.recording .go:hover, #wa .cmp.typing .go:hover { background: #A93226; } #wa .cmp .go svg { width: 24px; height: 24px; }
  #wa .cmp .ico-send { display: none; } #wa .cmp.typing .ico-send, #wa .cmp.recording .ico-send { display: block; } #wa .cmp.typing .ico-mic, #wa .cmp.recording .ico-mic { display: none; }
  @keyframes wablink { 50% { opacity: .2; } }
  #wa .att { position: absolute; left: 16px; right: 16px; bottom: calc(100% + 6px); background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(11,20,26,.2); display: flex; align-items: center; gap: 12px; padding: 10px 12px; }
  #wa .att img { width: 56px; height: 56px; object-fit: cover; border-radius: 6px; } #wa .att .an { flex: 1; min-width: 0; } #wa .att .an b { display: block; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } #wa .att .an small { color: #667781; }
  #wa .pick { position: absolute; left: 70px; bottom: calc(100% + 4px); width: 300px; max-height: 260px; overflow-y: auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(11,20,26,.2); padding: 6px 0; display: none; }
  #wa .pick div { display: flex; align-items: center; gap: 10px; padding: 7px 14px; cursor: pointer; } #wa .pick div.sel, #wa .pick div:hover { background: #F5F6F6; } #wa .pick small { color: #667781; }
  #wa .hint { position: absolute; left: 50%; bottom: calc(100% + 8px); transform: translateX(-50%); background: #3B4A54; color: #fff; font-size: 13px; padding: 7px 14px; border-radius: 7px; display: none; white-space: nowrap; max-width: 90%; overflow: hidden; text-overflow: ellipsis; }
  #wa .editing { position: absolute; left: 16px; right: 16px; bottom: calc(100% + 6px); background: #fff; border-left: 4px solid #C0392B; border-radius: 7px; padding: 8px 12px; font-size: 13px; color: #667781; box-shadow: 0 1px 4px rgba(11,20,26,.15); display: none; }
  #wa .editing a { color: #027EB5; margin-left: 8px; }
  #wa .empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; background: #F0F2F5; color: #667781; border-bottom: 6px solid #C0392B; padding: 30px; }
  #wa .empty h2 { font-weight: 300; font-size: 32px; color: #41525D; margin: 20px 0 10px; } #wa .empty p { font-size: 14px; max-width: 460px; line-height: 20px; margin: 0 0 6px; }
  #wa .empty svg { width: 90px; color: #E3C9C4; }
  #wa.drop .main::after { content: "Drop the file here to send it"; position: absolute; inset: 59px 0 0; background: rgba(240,242,245,.92); border: 2px dashed #C0392B; display: flex; align-items: center; justify-content: center; font-size: 18px; color: #A93226; pointer-events: none; z-index: 4; }
  #wa .viewer { position: absolute; inset: 0; background: rgba(233,237,239,.97); z-index: 10; display: none; flex-direction: column; } #wa .viewer.on { display: flex; }
  #wa .viewer .vb { height: 59px; display: flex; align-items: center; gap: 12px; padding: 0 16px; } #wa .viewer .vb b { flex: 1; } #wa .viewer .vi { flex: 1; display: flex; align-items: center; justify-content: center; padding: 10px 30px 30px; min-height: 0; }
  #wa .viewer img { max-width: 100%; max-height: 100%; box-shadow: 0 6px 20px rgba(0,0,0,.2); }
  /* the Chat entry at the foot of the left menu */
  .pg-side .pg-chat { display: flex; align-items: center; gap: 10px; margin-top: 10px !important; border-top: 1px solid rgba(255,255,255,.12); }
  .pg-side .pg-chat .ci svg { width: 19px; height: 19px; display: block; opacity: .9; } .pg-side .pg-chat .cl { flex: 1; line-height: 1.15; }
  .pg-side .pg-chat .cl small { display: block; font-size: 11px; font-weight: 500; opacity: .7; } .pg-side .pg-chat .cl small i { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #3DDC84; margin-right: 5px; vertical-align: 0; }
  .pg-side .pg-chat .cn { min-width: 20px; height: 20px; border-radius: 10px; background: #C0392B; color: #fff; font-size: 11px; font-weight: 800; display: none; align-items: center; justify-content: center; padding: 0 6px; }
  @media (min-width: 901px) {
    .pg-side { display: flex; flex-direction: column; } .pg-side .pg-chat { margin-top: auto !important; position: sticky; bottom: 0; background: inherit; }
    body:not(.pg-noside):not(.pg-full) #chat-btn { display: none; }
  }
  #wa .nbanner { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #FBE9E7; color: #3B4A54; font-size: 13.5px; cursor: pointer; border-bottom: 1px solid #F3D4CF; }
  #wa .nbanner svg { width: 34px; height: 34px; color: #C0392B; flex-shrink: 0; } #wa .nbanner b { display: block; font-weight: 600; color: #111B21; } #wa .nbanner span { color: #A93226; text-decoration: underline; }
  #wa .ib.mute { color: #8696A0; }
  #wa-toasts { position: fixed; right: 18px; bottom: 18px; z-index: 6500; display: flex; flex-direction: column; gap: 10px; align-items: flex-end; pointer-events: none; }
  #wa-toasts .t { pointer-events: auto; width: 340px; max-width: calc(100vw - 36px); display: flex; gap: 12px; align-items: center; background: #fff; border-radius: 12px; padding: 12px 14px; cursor: pointer;
    box-shadow: 0 12px 34px rgba(11,20,26,.24); border-left: 4px solid #C0392B; font: 14px/1.35 "Segoe UI", -apple-system, sans-serif; color: #111B21; animation: wain .25s ease-out; }
  #wa-toasts .t .av { width: 42px; height: 42px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 600; flex-shrink: 0; }
  #wa-toasts .t .tb { flex: 1; min-width: 0; } #wa-toasts .t b { display: block; font-weight: 600; } #wa-toasts .t span { display: block; color: #54656F; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #wa-toasts .t small { color: #8696A0; font-size: 11.5px; }
  @keyframes wain { from { transform: translateY(14px); opacity: 0; } }
  @media (max-width: 760px) {
    #wa { top: 0; right: 0; bottom: 0; width: 100vw; border-radius: 0; }
    #wa .side { width: 100%; max-width: none; border-right: 0; } #wa .main { display: none; }
    #wa.conv .side { display: none; } #wa.conv .main { display: flex; } #wa .back { display: inline-flex; }
    #wa .side .bar { background: #2E3238; color: #fff; } #wa .side .bar .ib { color: #fff; } #wa .side .bar .sub { color: #F2B8AE; }
    #wa .main .bar { background: #2E3238; color: #fff; padding: 0 6px; gap: 8px; } #wa .main .bar .ib { color: #fff; } #wa .main .bar .who span { color: #D6CFC7; }
    #wa .msgs { padding: 10px 10px 6px; } #wa .bub { max-width: 82%; } #wa .cmp { padding: 5px 6px; } #wa .bub:hover .menu, #wa .menu { display: none; }
    #wa .vn { width: 250px; } #wa .doc { min-width: 220px; } #wa .docw { min-width: 230px; max-width: 270px; } #wa .ph img { width: 260px; }
  }`;
  document.head.appendChild(css);

  const I = {
    chat: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.2C6.5 2.2 2.1 6.4 2.1 11.6c0 1.9.6 3.7 1.6 5.2L2.2 21.6l5-1.5c1.4.7 3 1.1 4.8 1.1 5.5 0 9.9-4.2 9.9-9.5S17.5 2.2 12 2.2zm0 17.3c-1.6 0-3-.4-4.3-1.1l-.3-.2-2.9.9.9-2.8-.2-.3c-.9-1.3-1.4-2.8-1.4-4.4 0-4.3 3.7-7.8 8.2-7.8s8.2 3.5 8.2 7.8-3.7 7.9-8.2 7.9z"/><path d="M8 10.2h8M8 13.4h5.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
    search: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M15.9 14.3h-.8l-.3-.3c1-1.1 1.6-2.6 1.6-4.2a6.5 6.5 0 1 0-6.5 6.5c1.6 0 3.1-.6 4.2-1.6l.3.3v.8l5 5 1.5-1.5-5-5zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z"/></svg>`,
    x: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19.1 17.2l-5.3-5.2 5.3-5.3-1.8-1.8-5.3 5.3-5.2-5.3-1.9 1.8 5.3 5.3-5.3 5.2 1.9 1.9 5.2-5.3 5.3 5.3z"/></svg>`,
    back: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l1.4 1.4L7.8 11H20v2H7.8l5.6 5.6L12 20l-8-8z"/></svg>`,
    plus: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 12.998h-6v6h-2v-6H5v-2h6v-6h2v6h6z"/></svg>`,
    mic: `<svg class="ico-mic" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14.6c1.7 0 3-1.4 3-3.1V5.2C15 3.5 13.7 2 12 2S9 3.5 9 5.2v6.3c0 1.7 1.3 3.1 3 3.1zm5.3-3.1c0 3-2.5 5.1-5.3 5.1s-5.3-2.1-5.3-5.1H5c0 3.4 2.7 6.2 6 6.7V22h2v-3.8c3.3-.5 6-3.3 6-6.7h-1.7z"/></svg>`,
    send: `<svg class="ico-send" viewBox="0 0 24 24" fill="currentColor"><path d="M1.1 21.8L23 12 1.1 2.2 1.1 9.8 16.7 12 1.1 14.2z"/></svg>`,
    del: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>`,
    group: `<svg viewBox="0 0 212 212"><path fill="#DFE5E7" d="M106 0a106 106 0 1 0 0 212 106 106 0 0 0 0-212z"/><path fill="#fff" d="M102.4 106.9c11.5 0 20.8-9.4 20.8-21s-9.3-21-20.8-21-20.8 9.4-20.8 21 9.3 21 20.8 21zm-47.7 49.8h95.4v-8.1c0-12.6-25.4-19-47.7-19s-47.7 6.4-47.7 19v8.1zm86.5-58.3c8 0 14.4-6.6 14.4-14.6s-6.4-14.6-14.4-14.6c-2.3 0-4.5.6-6.4 1.6 2.7 4.3 4.3 9.4 4.3 14.9 0 3.6-.7 7-1.9 10.2 1.3.4 2.6.5 4 .5zm6.4 27.6c6.9 5 11 11.6 11 19.6v12.1h18.5v-9.4c0-10-15.9-17.8-29.5-22.3z"/></svg>`,
    person: `<svg viewBox="0 0 212 212"><path fill="#DFE5E7" d="M106 0a106 106 0 1 0 0 212 106 106 0 0 0 0-212z"/><path fill="#fff" d="M173.6 180.6c-8.7-13.6-26.4-23.2-48-27.3a36 36 0 0 0 16.5-30.4c0-20-16.2-36.1-36.1-36.1S69.9 102.9 69.9 122.9c0 12.8 6.6 24 16.5 30.4-21.6 4.1-39.3 13.7-48 27.3A105.6 105.6 0 0 0 106 212c26.5 0 50.6-9.8 69-25.9z"/></svg>`,
    play: `<svg viewBox="0 0 34 34" fill="currentColor"><path d="M8.5 8.7c0-1.7 1.2-2.4 2.6-1.5l14.4 8.3c1.4.8 1.4 2.2 0 3l-14.4 8.3c-1.4.8-2.6.2-2.6-1.5V8.7z"/></svg>`,
    pause: `<svg viewBox="0 0 34 34" fill="currentColor"><path d="M9.2 25c0 .5.4 1 .9 1h3.6c.5 0 .9-.4.9-1V9c0-.5-.4-.9-.9-.9h-3.6c-.5 0-.9.4-.9.9v16zm11-17c-.5 0-1 .4-1 .9V25c0 .5.4 1 1 1h3.6c.5 0 1-.4 1-1V9c0-.5-.4-.9-1-.9h-3.6z"/></svg>`,
    dl: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 15.6l-5-5 1.4-1.4 2.6 2.6V4h2v7.8l2.6-2.6 1.4 1.4-5 5zM5 18h14v2H5z"/></svg>`,
    bell: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 22a2.4 2.4 0 0 0 2.4-2.4H9.6A2.4 2.4 0 0 0 12 22zm7.2-6V11c0-3.5-2-6.4-5.4-7.2V3a1.8 1.8 0 0 0-3.6 0v.8C6.8 4.6 4.8 7.5 4.8 11v5L2.4 18.4v1.2h19.2v-1.2L19.2 16z"/></svg>`,
    bellOff: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 22a2.4 2.4 0 0 0 2.4-2.4H9.6A2.4 2.4 0 0 0 12 22zm7.2-6V11c0-3.5-2-6.4-5.4-7.2V3a1.8 1.8 0 0 0-3.6 0v.8c-.6.1-1.1.3-1.6.6L19.2 17v-1zM3.3 2.6L2 3.9l3.2 3.2c-.3.9-.4 1.9-.4 2.9v5L2.4 18.4v1.2h15.9l2.4 2.4 1.3-1.3L3.3 2.6z"/></svg>`,
    lock: `<svg viewBox="0 0 24 24" fill="currentColor" style="width:13px;vertical-align:-2px"><path d="M17 9h-1V7c0-2.8-2.2-5-5-5S6 4.2 6 7v2H5c-1.1 0-2 .9-2 2v9c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-9c0-1.1-.9-2-2-2zM8 7c0-1.7 1.3-3 3-3s3 1.3 3 3v2H8V7z"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
    micSmall: `<svg class="mic" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14.6c1.7 0 3-1.4 3-3.1V5.2C15 3.5 13.7 2 12 2S9 3.5 9 5.2v6.3c0 1.7 1.3 3.1 3 3.1zm5.3-3.1c0 3-2.5 5.1-5.3 5.1s-5.3-2.1-5.3-5.1H5c0 3.4 2.7 6.2 6 6.7V22h2v-3.8c3.3-.5 6-3.3 6-6.7h-1.7z"/></svg>`,
    cam: `<svg viewBox="0 0 24 24" fill="currentColor" style="width:16px"><path d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM9 2L7.2 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.2L15 2H9zm3 15c-2.8 0-5-2.2-5-5s2.2-5 5-5 5 2.2 5 5-2.2 5-5 5z"/></svg>`,
    file: `<svg viewBox="0 0 24 24" fill="currentColor" style="width:16px"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z"/></svg>`,
  };
  const TICK1 = `<svg viewBox="0 0 16 11" fill="currentColor"><path d="M11.07.65l-.6-.46a.35.35 0 0 0-.49.06L4.62 7.13 2.18 4.8a.35.35 0 0 0-.49 0l-.53.51a.35.35 0 0 0 0 .5l3.24 3.1c.15.14.38.12.51-.04l6.22-7.73a.35.35 0 0 0-.06-.49z"/></svg>`;
  const TICK2 = `<svg viewBox="0 0 16 11" fill="currentColor"><path d="M11.07.65l-.6-.46a.35.35 0 0 0-.49.06L4.62 7.13 2.18 4.8a.35.35 0 0 0-.49 0l-.53.51a.35.35 0 0 0 0 .5l3.24 3.1c.15.14.38.12.51-.04l6.22-7.73a.35.35 0 0 0-.06-.49z"/><path d="M15.07.65l-.6-.46a.35.35 0 0 0-.49.06L8.62 7.13l-.97-.93-.7.87 1.4 1.34c.15.14.38.12.51-.04l6.22-7.73a.35.35 0 0 0-.06-.49z"/></svg>`;

  // ---- the button beside the bell -----------------------------------------------------------------------------------
  const btn = document.createElement("button");
  btn.id = "chat-btn"; btn.type = "button"; btn.title = "Chat";
  btn.innerHTML = I.chat + `<span class="n" style="display:none"></span>`;
  const bw = document.getElementById("bell-wrap"); bw.parentNode.insertBefore(btn, bw);
  btn.onclick = () => (S.open ? close() : open());
  // ... and at the foot of the left menu, where it is always in reach
  const sideItem = document.createElement("div");
  sideItem.className = "pg-item pg-chat"; sideItem.title = "Infinia Chat";
  sideItem.innerHTML = `<span class="ci">${I.chat}</span><span class="cl">Chat<small data-so></small></span><span class="cn" data-sn></span>`;
  sideItem.onclick = () => (S.open ? close() : open());
  const side = document.querySelector(".pg-side"); if (side) side.appendChild(sideItem);

  const pane = document.createElement("div"); pane.id = "wa";
  pane.innerHTML = `<div class="side">
      <div class="bar"><span data-meav></span><span class="ttl">Infinia Chat</span><span class="sub" data-n></span><button class="ib" data-bell title="Notifications">${I.bell}</button><button class="ib" data-x title="Close">${I.x}</button></div>
      <div data-banner></div>
      <div class="srch"><div>${I.search}<input type="search" placeholder="Search or start a new chat" data-q></div></div>
      <div class="chips"><button data-f="all" class="on">All</button><button data-f="online">Online</button><button data-f="unread">Unread</button></div>
      <div class="list" data-list></div></div>
    <div class="main"><div class="empty" data-empty>${I.chat}<h2>Infinia <b style="color:#C0392B;font-weight:600">Chat</b></h2><p>Message anyone in the office, or everyone at once. Photos, documents and voice notes are kept only while the sender has the portal open.</p><p>${I.lock} Private chats are seen only by the two of you.</p></div>
      <div class="bar" data-hd style="display:none"></div><div class="msgs" data-msgs style="display:none"></div>
      <div class="cmp" data-cmp style="display:none"><div class="pick" data-pick></div><div class="editing" data-editing></div><div data-att></div><div class="hint" data-hint></div>
        <button class="ib" data-clip title="Attach a photo or document">${I.plus}</button>
        <div class="inw"><textarea rows="1" data-in placeholder="Type a message"></textarea></div>
        <div class="rec"><button class="ib del" data-rcancel title="Delete recording">${I.del}</button><span class="rd"></span><span class="rt" data-rt>0:00</span><span class="wave" data-wave></span></div>
        <button class="ib snd2 go" data-go title="Voice message">${I.mic}${I.send}</button>
        <input type="file" data-file hidden></div>
      <div class="viewer" data-viewer><div class="vb"><b data-vname></b><a class="ib" data-vdl title="Download" target="_blank">${I.dl}</a><button class="ib" data-vx title="Close">${I.x}</button></div><div class="vi"><img data-vimg alt=""></div></div></div>`;
  document.body.appendChild(pane);
  const $list = $("[data-list]", pane), $msgs = $("[data-msgs]", pane), $in = $("[data-in]", pane), $hd = $("[data-hd]", pane),
        $pick = $("[data-pick]", pane), $cmp = $("[data-cmp]", pane), $att = $("[data-att]", pane), $file = $("[data-file]", pane);
  $("[data-x]", pane).onclick = close;
  $("[data-q]", pane).oninput = e => { S.q = e.target.value.trim().toLowerCase(); drawList(); };
  pane.querySelectorAll("[data-f]").forEach(b => b.onclick = () => { S.filter = b.dataset.f; pane.querySelectorAll("[data-f]").forEach(x => x.classList.toggle("on", x === b)); drawList(); });

  // ---- time words, the way WhatsApp writes them -------------------------------------------------------------
  const dmy = d => `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;   // 30/10/2026
  const hm = d => d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const dayKey = d => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  const yest = () => { const y = new Date(); y.setDate(y.getDate() - 1); return y; };
  function dayWord(d) { const t = new Date();
    if (dayKey(d) === dayKey(t)) return "Today"; if (dayKey(d) === dayKey(yest())) return "Yesterday";
    if ((t - d) < 6 * 86400000) return d.toLocaleDateString("en-GB", { weekday: "long" });
    return dmy(d); }
  function listTime(iso) { if (!iso) return ""; const d = new Date(iso), t = new Date();
    if (dayKey(d) === dayKey(t)) return hm(d); if (dayKey(d) === dayKey(yest())) return "Yesterday";
    if ((t - d) < 6 * 86400000) return d.toLocaleDateString("en-GB", { weekday: "long" });
    return dmy(d); }
  function lastSeen(iso) { if (!iso) return "offline"; const d = new Date(iso);
    if (dayKey(d) === dayKey(new Date())) return `last seen today at ${hm(d)}`;
    if (dayKey(d) === dayKey(yest())) return `last seen yesterday at ${hm(d)}`;
    return `last seen ${dmy(d)} at ${hm(d)}`; }

  // ---- the chats list ----------------------------------------------------------------------------------------------
  const userBy = id => S.users.find(u => u.id === id) || {};
  const PALETTE = ["#C0392B", "#027EB5", "#7F66FF", "#E26AB6", "#FA6533", "#5BCC88", "#53BDEB", "#A62C71", "#02A698", "#FFBC38"];
  function avatar(u, cls = "") {
    if (!u || u.group || u.id === "all") return `<span class="av grp ${cls}">${I.group}</span>`;
    return `<span class="av ${cls}" style="background:${PALETTE[(u.id || 0) % PALETTE.length]}">${esc(u.initials || "?")}${u.online && !u.me ? "<i></i>" : ""}</span>`;
  }
  function preview(room) {
    const p = S.previews[room]; if (!p) return room === "all" ? "The whole office - say hello" : "";
    const mine = p.user_id === S.me, who = room === "all" && !mine ? `${esc((p.name || "").split(" ")[0])}: ` : "";
    const tk = mine && !p.deleted && S.receipts[room] ? ticksFor({ id: p.id, at: p.at }, room) : "";
    if (p.deleted) return `${tk}<span class="t" style="font-style:italic">This message was deleted</span>`;
    const body = p.kind === "voice" ? `${I.micSmall.replace('class="mic"', 'style="width:15px;color:#53BDEB;flex-shrink:0"')}<span class="t">Voice message</span>`
      : p.kind === "image" ? `${I.cam}<span class="t">${esc(p.text || "Photo")}</span>` : p.kind === "file" ? `${I.file}<span class="t">${esc(p.text || "Document")}</span>`
      : `<span class="t">${esc(p.text)}</span>`;
    return `${tk}${who ? `<span>${who}</span>` : ""}${body}`;
  }
  function drawList() {
    const rows = [{ room: "all", name: "Everyone", id: "all", group: true }].concat(S.users.filter(u => !u.me));
    const keep = r => (!S.q || (r.name + " " + (r.username || "")).toLowerCase().includes(S.q))
      && (S.filter !== "online" || (r.room !== "all" && r.online)) && (S.filter !== "unread" || S.unread[r.room]);
    const at = r => (S.previews[r.room] || {}).id || 0;
    const list = rows.filter(keep).sort((a, b) => (a.room === "all" ? -1 : b.room === "all" ? 1 : 0) || at(b) - at(a) || (b.online - a.online) || a.name.localeCompare(b.name));
    const n = S.users.filter(u => u.online && !u.me).length;
    $("[data-n]", pane).textContent = `${n} online`;
    $("[data-meav]", pane).innerHTML = avatar(Object.assign({}, S.users.find(u => u.me) || {}, { online: false }), "sm");
    $list.innerHTML = list.map(r => { const un = S.unread[r.room] || 0, p = S.previews[r.room];
      const mention = r.room === "all" && S.mentions;
      return `<div class="row ${S.room === r.room ? "sel" : ""} ${un ? "un" : ""}" data-room="${r.room}">${avatar(r)}
        <div class="rb"><div class="l1"><span class="nm">${esc(r.name)}</span><span class="tm">${p ? listTime(p.at) : (r.online ? "online" : "")}</span></div>
          <div class="l2"><span class="pv">${preview(r.room) || (r.online ? "online" : esc(lastSeen(r.last_seen)))}</span>${mention ? `<span class="at">@</span>` : ""}${un ? `<span class="ub">${un}</span>` : ""}</div></div></div>`; }).join("")
      || `<div style="padding:30px;text-align:center;color:#667781;font-size:14px">${S.filter === "online" ? "Nobody else is online right now" : S.filter === "unread" ? "No unread chats" : "No one found"}</div>`;
    $list.querySelectorAll("[data-room]").forEach(el => el.onclick = () => openRoom(el.dataset.room));
  }

  // ---- ticks ------------------------------------------------------------------------------------------------------------
  function ticksFor(m, room) {
    const R = S.receipts[room] || [];
    if (!R.length) return `<span class="tk s" title="Sent">${TICK1}</span>`;
    const read = R.filter(r => r.read >= m.id), got = R.filter(r => r.read >= m.id || (r.seen && new Date(r.seen) >= new Date(m.at)));
    const names = l => l.map(r => ((userBy(r.user_id).name || "").split(" ")[0])).filter(Boolean).join(", ");
    if (read.length === R.length) return `<span class="tk r" title="Read${R.length > 1 ? " by everyone" : ""}">${TICK2}</span>`;
    if (got.length === R.length) return `<span class="tk d" title="Delivered${read.length ? " - read by " + names(read) : ""}">${TICK2}</span>`;
    return `<span class="tk s" title="Sent${read.length ? " - read by " + names(read) : ""}">${TICK1}</span>`;
  }

  // ---- a message -----------------------------------------------------------------------------------------------------------
  function fmt(t) {
    let h = esc(t);
    h = h.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
    h = h.replace(/\*([^*\n]+)\*/g, "<b>$1</b>").replace(/(^|\s)_([^_\n]+)_(?=\s|$)/g, "$1<i>$2</i>").replace(/~([^~\n]+)~/g, "<s>$1</s>");   // WhatsApp's *bold* _italic_ ~strike~
    h = h.replace(/(^|[^\w@])@([A-Za-z0-9][\w.\-]*)/g, (all, pre, tag) => {
      const t2 = tag.toLowerCase().replace(/[.\-]+$/, "");
      if (["everyone", "all", "here"].includes(t2)) return `${pre}<span class="tag me">@everyone</span>`;
      const u = S.users.find(x => x.username.toLowerCase() === t2);
      return u ? `${pre}<span class="tag ${u.me ? "me" : ""}">@${esc(u.name)}</span>${esc(tag.slice(t2.length))}` : all;
    });
    return h;
  }
  const kb = n => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " kB";
  const DOCCOL = { PDF: "#E5252A", XLSX: "#1D6F42", XLS: "#1D6F42", CSV: "#1D6F42", DOC: "#2B579A", DOCX: "#2B579A", PPT: "#D24726", PPTX: "#D24726", ZIP: "#7D7D7D", DWG: "#C2185B" };
  function bars(id, n = 36) { let x = (id * 9301 + 49297) % 233280; const out = []; for (let i = 0; i < n; i++) { x = (x * 9301 + 49297) % 233280; out.push(4 + Math.round((x / 233280) * 20 * (0.45 + 0.55 * Math.sin(i / n * Math.PI)))); } return out; }
  const dur = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  function fileHtml(m, meta) {
    const f = m.file;
    if (f.gone || !f.url) return `<div class="gone">${I.clock}<span>${f.kind === "voice" ? "Voice message" : f.kind === "image" ? "Photo" : esc(f.name)} - no longer available (the sender has left the portal)</span></div>${meta}`;
    const u = (typeof API !== "undefined" ? API : "") + f.url;
    if (f.kind === "image") return `<span class="ph" data-view="${m.id}"><img src="${u}" alt="" loading="lazy">${m.text ? "" : meta.replace('class="meta"', 'class="meta ov"')}</span>${m.text ? `<div class="tx">${fmt(m.text)}${meta}</div>` : ""}`;
    if (f.kind === "voice") { const sender = userBy(m.user_id);
      return `<div class="vn" data-vn="${m.id}" data-src="${u}" data-dur="${f.duration || 0}"><span class="vp">${avatar(Object.assign({}, sender, { online: false }))}${I.micSmall}</span>
        <button class="play" data-play>${I.play}</button><div class="wv"><div class="bars" data-bars>${bars(m.id).map(h => `<i style="height:${h}px"></i>`).join("")}</div>
        <div class="vt"><span data-vt>${dur(f.duration || 0)}</span>${meta}</div></div><button class="spd" data-spd>1×</button></div>`; }
    const ext = ((f.name.split(".").pop() || "").slice(0, 4) || "FILE").toUpperCase();
    // tap the document to preview it (as on WhatsApp); the round arrow downloads it. A PDF shows the top of page 1.
    return `<div class="docw" data-doc="${m.id}" title="Open preview">${ext === "PDF" ? `<span class="dth"><img data-th="${m.id}" alt=""></span>` : ""}<div class="doc"><span class="di" style="background:${DOCCOL[ext] || "#8696A0"}">${esc(ext)}</span>
      <span class="dn"><b>${esc(f.name)}</b><small><span data-pgs></span>${esc(ext)} &bull; ${kb(f.size)}</small></span><a class="dl" href="${u}?dl=1" target="_blank" rel="noopener" title="Download">${I.dl}</a></div></div>${m.text ? `<div class="tx">${fmt(m.text)}${meta}</div>` : `<div class="dm">${meta.replace('class="meta"', 'class="meta st"')}</div>`}`;
  }
  function drawMsgs(keepBottom) {
    const ms = S.msgs[S.room] || [];
    const atBottom = keepBottom || $msgs.scrollHeight - $msgs.scrollTop - $msgs.clientHeight < 80;
    let h = S.more[S.room] ? `<button class="older" data-older>Load earlier messages</button>` : "";
    h += `<div class="note"><span>${S.room === "all" ? `${I.lock} Everyone in Infinia sees messages here.` : `${I.lock} Only the two of you can see this chat.`} Messages are deleted after 24 hours. Photos, documents and voice messages stay only while the sender has the portal open.</span></div>`;
    let lastDay = "", prev = null;
    for (const m of ms) {
      const d = new Date(m.at), dk = dayKey(d);
      if (dk !== lastDay) { h += `<div class="day"><span>${dayWord(d)}</span></div>`; lastDay = dk; prev = null; }
      const first = !prev || prev.user_id !== m.user_id || (d - new Date(prev.at)) > 10 * 60000;
      const u = userBy(m.user_id), mine = m.user_id === S.me, tagged = !mine && (m.mentions.includes(S.me) || m.everyone);
      const meta = `<span class="meta">${m.edited && !m.deleted ? `<span class="ed">Edited</span>` : ""}${hm(d)}${mine && !m.deleted ? ticksFor(m, S.room) : ""}</span>`;
      const name = S.room === "all" && !mine && first ? `<div class="snd" style="color:${col(m.user_id)}">${esc(u.name || m.name)}</div>` : "";
      let body;
      if (m.deleted) body = `<div class="tx del">${I.x.replace("<svg", '<svg style="width:15px;vertical-align:-3px"')} ${mine ? "You deleted this message" : "This message was deleted"}${meta}</div>`;
      else if (m.file) body = fileHtml(m, meta);
      else body = `<div class="tx">${fmt(m.text)}${meta}</div>`;
      h += `<div class="ln ${mine ? "me" : ""} ${first ? "first" : ""} ${tagged ? "ment" : ""}" data-id="${m.id}"><div class="bub ${m.file && m.file.kind === "image" && !m.deleted && !m.file.gone ? "img" : ""}">${name}${body}
        ${mine && !m.deleted ? `<button class="menu" data-menu="${m.id}" title="Menu">&#8964;</button>` : ""}</div></div>`;
      prev = m;
    }
    $msgs.innerHTML = h;
    if (atBottom) $msgs.scrollTop = $msgs.scrollHeight;
    const older = $("[data-older]", $msgs); if (older) older.onclick = loadOlder;
    $msgs.querySelectorAll("[data-menu]").forEach(b => b.onclick = e => { e.stopPropagation(); menu(b, +b.dataset.menu); });
    // a phone has no pointer to rest: a tap on your own message opens Edit / Delete
    if (matchMedia("(max-width: 760px)").matches) $msgs.querySelectorAll(".ln.me .bub").forEach(bb => bb.onclick = e => {
      if (e.target.closest("a, button, [data-view], [data-doc], .vn")) return; const mb = bb.querySelector("[data-menu]"); if (mb) { e.stopPropagation(); menu(bb, +mb.dataset.menu); } });
    $msgs.querySelectorAll("[data-view]").forEach(el => el.onclick = () => view(+el.dataset.view));
    $msgs.querySelectorAll("[data-vn]").forEach(wireVoice);
    $msgs.querySelectorAll("[data-doc]").forEach(el => el.onclick = e => { if (e.target.closest(".dl")) return; openDoc(+el.dataset.doc); });
    if (window.CHAT_DOC) $msgs.querySelectorAll("[data-th]").forEach(img => { const m = (S.msgs[S.room] || []).find(x => x.id === +img.dataset.th); if (!m || !m.file) return;
      window.CHAT_DOC.thumb((typeof API !== "undefined" ? API : "") + m.file.url, img, n => { const t = img.closest(".docw").querySelector("[data-pgs]"); if (t) t.textContent = `${n} page${n === 1 ? "" : "s"} \u2022 `; }); });
  }
  function openDoc(id) { const m = (S.msgs[S.room] || []).find(x => x.id === id); if (!m || !m.file || !window.CHAT_DOC) return;
    const u = (typeof API !== "undefined" ? API : "") + m.file.url;
    window.CHAT_DOC.open({ url: u, dl: u + "?dl=1", name: m.file.name, sub: `${kb(m.file.size)} \u00b7 ${userBy(m.user_id).name || ""}, ${dayWord(new Date(m.at))} at ${hm(new Date(m.at))}` }); }
  function menu(anchor, id) {
    closeMenu(); const m = (S.msgs[S.room] || []).find(x => x.id === id); if (!m) return;
    const p = document.createElement("div"); p.className = "pop";
    p.innerHTML = (m.file ? "" : `<button data-a="edit">Edit</button>`) + `<button data-a="del">Delete for everyone</button>`;
    const r = anchor.getBoundingClientRect(), pr = pane.getBoundingClientRect();
    p.style.top = Math.min(r.bottom - pr.top + 2, pr.height - 120) + "px"; p.style.right = (pr.right - r.right) + "px";
    pane.appendChild(p);
    p.querySelectorAll("[data-a]").forEach(b => b.onclick = () => { closeMenu(); b.dataset.a === "edit" ? startEdit(id) : delMsg(id); });
    setTimeout(() => document.addEventListener("click", closeMenu, { once: true }), 0);
  }
  function closeMenu() { pane.querySelectorAll(".pop").forEach(x => x.remove()); }
  // photo viewer
  function view(id) { const m = (S.msgs[S.room] || []).find(x => x.id === id); if (!m || !m.file) return;
    const u = (typeof API !== "undefined" ? API : "") + m.file.url; $("[data-vimg]", pane).src = u; $("[data-vdl]", pane).href = u + "?dl=1";
    $("[data-vname]", pane).textContent = `${userBy(m.user_id).name || ""} - ${dayWord(new Date(m.at))} at ${hm(new Date(m.at))}`; $("[data-viewer]", pane).classList.add("on"); }
  $("[data-vx]", pane).onclick = () => $("[data-viewer]", pane).classList.remove("on");
  // voice note player - WhatsApp's: play, the waveform fills as it plays, tap the waveform to jump, 1x / 1.5x / 2x
  let PLAYING = null;
  function wireVoice(el) {
    const id = +el.dataset.vn, playB = $("[data-play]", el), barsEl = $("[data-bars]", el), vt = $("[data-vt]", el), spd = $("[data-spd]", el);
    const paint = (a, d) => { const k = d ? a.currentTime / d : 0; const bs = barsEl.children; const n = Math.round(k * bs.length);
      for (let i = 0; i < bs.length; i++) bs[i].classList.toggle("p", i < n); vt.textContent = dur(a.paused && !a.currentTime ? d : a.currentTime); };
    playB.onclick = () => {
      if (PLAYING && PLAYING.id === id) { const a = PLAYING.a; if (a.paused) { a.play(); playB.innerHTML = I.pause; el.classList.add("playing"); } else { a.pause(); playB.innerHTML = I.play; el.classList.remove("playing"); } return; }
      if (PLAYING) { PLAYING.a.pause(); PLAYING.stop(); }
      const a = new Audio(el.dataset.src); const d = +el.dataset.dur || 0;
      a.playbackRate = PLAYING_RATE; spd.textContent = PLAYING_RATE + "×";
      const tick = setInterval(() => paint(a, isFinite(a.duration) && a.duration > 0 ? a.duration : d), 100);
      const stop = () => { clearInterval(tick); playB.innerHTML = I.play; el.classList.remove("playing"); };
      a.onended = () => { stop(); a.currentTime = 0; paint(a, d); vt.textContent = dur(d); PLAYING = null; };
      PLAYING = { id, a, stop }; a.play().catch(() => {}); playB.innerHTML = I.pause; el.classList.add("playing");
    };
    barsEl.onclick = e => { if (!PLAYING || PLAYING.id !== id) return; const r = barsEl.getBoundingClientRect(); const a = PLAYING.a;
      const d = isFinite(a.duration) && a.duration > 0 ? a.duration : (+el.dataset.dur || 0); a.currentTime = Math.max(0, Math.min(d, (e.clientX - r.left) / r.width * d)); };
    spd.onclick = () => { PLAYING_RATE = PLAYING_RATE === 1 ? 1.5 : PLAYING_RATE === 1.5 ? 2 : 1; spd.textContent = PLAYING_RATE + "×"; if (PLAYING) PLAYING.a.playbackRate = PLAYING_RATE; };
    if (PLAYING && PLAYING.id === id) { playB.innerHTML = PLAYING.a.paused ? I.play : I.pause; el.classList.toggle("playing", !PLAYING.a.paused); }
  }
  let PLAYING_RATE = 1;

  function drawHead() {
    const u = S.users.find(x => x.room === S.room && !x.me);
    const sub = S.room === "all" ? S.users.map(x => x.me ? "You" : (x.name || "").split(" ")[0]).join(", ") : (u && u.online ? "online" : lastSeen(u && u.last_seen));
    $hd.innerHTML = `<button class="ib back" data-back title="Back">${I.back}</button>${avatar(S.room === "all" ? { group: true } : Object.assign({}, u || {}, { online: false }), "sm")}
      <div class="who"><b>${esc(S.room === "all" ? "Everyone" : (u ? u.name : ""))}</b><span>${esc(sub)}</span></div><button class="ib" data-x2 title="Close">${I.x}</button>`;
    $("[data-back]", $hd).onclick = () => { pane.classList.remove("conv"); S.room = ""; showRoom(); drawList(); };
    $("[data-x2]", $hd).onclick = close;
  }
  function showRoom() {
    const on = !!S.room;
    $("[data-empty]", pane).style.display = on ? "none" : "";
    $hd.style.display = on ? "" : "none"; $msgs.style.display = on ? "" : "none"; $cmp.style.display = on ? "" : "none";
  }

  async function openRoom(room) {
    if (R) stopRec(false);
    S.room = room; S.edit = null; showEditing(); S.file = null; drawAtt();
    pane.classList.add("conv"); showRoom(); drawList(); drawHead();
    try { localStorage.setItem("chat_room", room); } catch (e) {}
    if (!S.msgs[room]) { $msgs.innerHTML = ""; await poll(true); } else { drawMsgs(true); await poll(); }
    if (innerWidth > 760) $in.focus();
  }
  async function loadOlder() {
    const ms = S.msgs[S.room] || []; if (!ms.length) return;
    const h0 = $msgs.scrollHeight;
    const r = await api(`/store/chat/history?room=${encodeURIComponent(S.room)}&before=${ms[0].id}`);
    S.msgs[S.room] = r.messages.concat(ms); S.more[S.room] = r.more;
    drawMsgs(); $msgs.scrollTop = $msgs.scrollHeight - h0;
  }

  // ---- telling people: a pop-up and a soft sound in the portal, a notification on the computer when the portal
  // is in the background (and the phone push from the server when they are away) - switched with the bell in the chat
  const NKEY = "chat_notify";
  const notifyOn = () => { try { return localStorage.getItem(NKEY) !== "off"; } catch (e) { return true; } };
  function drawBell() {
    const b = $("[data-bell]", pane), on = notifyOn();
    b.innerHTML = on ? I.bell : I.bellOff; b.classList.toggle("mute", !on); b.title = on ? "Notifications on - press to mute" : "Notifications muted - press to turn on";
    const ban = $("[data-banner]", pane);
    const ask = on && "Notification" in window && Notification.permission === "default";
    ban.innerHTML = ask ? `<div class="nbanner" data-ask>${I.bell}<div><b>Get notified of new messages</b><span>Turn on desktop notifications</span></div></div>` : "";
    const a = $("[data-ask]", ban); if (a) a.onclick = () => Notification.requestPermission().then(drawBell);
  }
  $("[data-bell]", pane).onclick = () => { const on = !notifyOn(); try { localStorage.setItem(NKEY, on ? "on" : "off"); } catch (e) {}
    if (on && "Notification" in window && Notification.permission === "default") Notification.requestPermission().then(drawBell); drawBell(); };
  let AC = null;
  function ding() {               // two soft notes, like a message arriving
    try { AC = AC || new (window.AudioContext || window.webkitAudioContext)(); const t = AC.currentTime;
      [[880, 0], [1320, 0.11]].forEach(([f, d]) => { const o = AC.createOscillator(), g = AC.createGain(); o.type = "sine"; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t + d); g.gain.exponentialRampToValueAtTime(0.12, t + d + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.28);
        o.connect(g).connect(AC.destination); o.start(t + d); o.stop(t + d + 0.3); }); } catch (e) {}
  }
  const $toasts = document.createElement("div"); $toasts.id = "wa-toasts"; document.body.appendChild($toasts);
  function words(p) { return p.deleted ? "This message was deleted" : p.kind === "voice" ? "🎤 Voice message" : p.kind === "image" ? "📷 " + (p.text || "Photo") : p.kind === "file" ? "📄 " + (p.text || "Document") : p.text; }
  function announce(room, n) {
    const p = S.previews[room]; if (!p || p.user_id === S.me) return;
    const u = userBy(p.user_id), title = room === "all" ? `${p.name || u.name} @ Everyone` : (p.name || u.name);
    const body = (n > 1 ? `${n} new messages - ` : "") + (words(p) || "");
    const tagged = room === "all" ? S.mentions > (S._prevMentions || 0) : true;
    if (!document.hidden) {
      ding();
      const t = document.createElement("div"); t.className = "t";
      t.innerHTML = `<span class="av" style="background:${room === "all" ? "#8696A0" : PALETTE[(p.user_id || 0) % PALETTE.length]}">${room === "all" ? "#" : esc(u.initials || "?")}</span><span class="tb"><b>${esc(title)}</b><span>${esc(body)}</span><small>Infinia Chat &middot; now</small></span>`;
      t.onclick = () => { t.remove(); open(room); };
      $toasts.appendChild(t); while ($toasts.children.length > 3) $toasts.firstChild.remove();
      setTimeout(() => t.remove(), 7000);
    } else if (tagged && "Notification" in window && Notification.permission === "granted") {
      const url = `/?n_screen=chat&n_target=${encodeURIComponent(room)}&n_id=chat-${room}-${p.id}&n_kind=chat`;
      const opts = { body, tag: "chat-" + room, renotify: true, icon: "/portal/icon-192.png", badge: "/portal/icon-192.png", data: { url } };
      (navigator.serviceWorker && navigator.serviceWorker.ready ? navigator.serviceWorker.ready.then(r => r.showNotification(title, opts))
        : Promise.reject()).catch(() => { try { const nn = new Notification(title, opts); nn.onclick = () => { window.focus(); open(room); nn.close(); }; } catch (e) {} });
      ding();
    }
  }

  // ---- the poll: who is online, unread, new messages, ticks ---------------------------------------------------------------
  async function poll(fresh) {
    if (S.busy) { await S.busy; if (!fresh) return; }       // one at a time: wait for the one under way
    if (!tok()) return;
    let done; S.busy = new Promise(r => { done = r; });
    try {
      const room = S.open ? S.room : "";
      const after = room && !fresh ? (S.lastId[room] || 0) : 0;
      const r = await api(`/store/chat/state?room=${encodeURIComponent(room)}&after=${after}`);
      const before = S.seenOnce ? Object.assign({}, S.unread) : null;
      S._prevMentions = S.mentions;
      S.me = r.me; S.users = r.users; S.unread = r.unread; S.last = r.last; S.mentions = r.mentions; S.total = r.total; S.previews = r.previews || {};
      S.seenOnce = true;
      if (before && notifyOn()) for (const [rm, n] of Object.entries(S.unread)) {
        const was = before[rm] || 0; if (n <= was) continue;
        if (S.open && S.room === rm && !document.hidden) continue;        // reading it right now
        announce(rm, n - was);
      }
      if (room && r.messages) {
        if (fresh || !S.msgs[room]) { S.msgs[room] = r.messages; S.more[room] = r.more; }
        else if (r.messages.length) S.msgs[room] = S.msgs[room].concat(r.messages.filter(m => !S.msgs[room].some(x => x.id === m.id)));
        (r.changed || []).forEach(c => { const i = S.msgs[room].findIndex(x => x.id === c.id); if (i >= 0) S.msgs[room][i] = c; });
        // a day only: what the server has deleted goes from this screen too
        const cut = Date.now() - 24 * 3600 * 1000, n0 = S.msgs[room].length;
        S.msgs[room] = S.msgs[room].filter(m => new Date(m.at).getTime() >= cut);
        const pruned = S.msgs[room].length !== n0;
        const rc = JSON.stringify(r.receipts || []), moved = rc !== JSON.stringify(S.receipts[room] || []);
        S.receipts[room] = r.receipts || [];
        const ms = S.msgs[room]; if (ms.length) S.lastId[room] = Math.max(S.lastId[room] || 0, ms[ms.length - 1].id);
        if (room === S.room && (fresh || r.messages.length || (r.changed || []).length || moved || pruned) && !$msgs.querySelector(".vn.playing")) drawMsgs(fresh);
        if (room === S.room) markRead();
      }
      badge(); if (S.open) { drawList(); if (S.room) drawHead(); }
    } catch (e) { /* signed out or offline - try again next time */ }
    finally { S.busy = false; done(); }
  }
  function markRead() {
    if (!S.room || document.hidden || !S.open) return;
    const id = S.lastId[S.room] || 0; if (!id || !S.unread[S.room]) return;
    S.total -= S.unread[S.room]; S.unread[S.room] = 0; if (S.room === "all") S.mentions = 0; badge(); drawList();
    api("/store/chat/read", { method: "POST", body: JSON.stringify({ room: S.room, last_id: id }) }).catch(() => {});
  }
  function badge() {
    const n = $(".n", btn);
    n.style.display = S.total ? "" : "none"; n.textContent = S.total > 99 ? "99+" : S.total;
    const on = S.users.filter(u => u.online && !u.me).length;
    btn.title = `Chat - ${on} online${S.total ? `, ${S.total} unread` : ""}`;
    const sn = $("[data-sn]", sideItem), so = $("[data-so]", sideItem);
    sn.style.display = S.total ? "flex" : "none"; sn.textContent = S.total > 99 ? "99+" : S.total;
    so.innerHTML = on ? `<i></i>${on} online` : "nobody else online";
  }
  function schedule() { clearTimeout(S.timer); S.timer = setTimeout(async () => { await poll(); schedule(); }, S.open && !document.hidden ? 2500 : document.hidden ? 15000 : 8000); }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { poll().then(markRead); schedule(); } });

  // ---- writing ---------------------------------------------------------------------------------------------------------------
  function grow() { $in.style.height = "auto"; $in.style.height = Math.min($in.scrollHeight, 120) + "px"; $cmp.classList.toggle("typing", !!$in.value.trim() || !!S.file); }
  async function send() {
    if (S.file) return sendFile(S.file, $in.value.trim());
    const text = $in.value.trim(); if (!text || !S.room) return;
    $in.value = ""; grow();
    try {
      if (S.edit) {
        const m = await api(`/store/chat/messages/${S.edit}`, { method: "PUT", body: JSON.stringify({ text }) });
        const i = (S.msgs[S.room] || []).findIndex(x => x.id === m.id); if (i >= 0) S.msgs[S.room][i] = m;
        S.edit = null; showEditing();
      } else {
        const m = await api("/store/chat/send", { method: "POST", body: JSON.stringify({ room: S.room, text }) });
        (S.msgs[S.room] = S.msgs[S.room] || []).push(m); S.lastId[S.room] = Math.max(S.lastId[S.room] || 0, m.id);
        S.previews[S.room] = { id: m.id, user_id: m.user_id, at: m.at, text: m.text, kind: "" };
      }
      drawMsgs(true); drawList();
    } catch (e) { $in.value = text; grow(); hint(e); }
    finally { $in.focus(); }
  }
  function hint(e) { const h = $("[data-hint]", pane); h.textContent = (e && e.message) || String(e); h.style.display = "block"; clearTimeout(h._t); h._t = setTimeout(() => { h.style.display = "none"; }, 4000); }
  function startEdit(id) { const m = (S.msgs[S.room] || []).find(x => x.id === id); if (!m) return; S.edit = id; $in.value = m.text; grow(); showEditing(); $in.focus(); }
  function showEditing() { const e = $("[data-editing]", pane); e.style.display = S.edit ? "block" : "none"; e.innerHTML = S.edit ? `Editing message<a href="#" data-cancel>Cancel</a>` : "";
    const c = $("[data-cancel]", e); if (c) c.onclick = ev => { ev.preventDefault(); S.edit = null; $in.value = ""; grow(); showEditing(); }; }
  async function delMsg(id) {
    if (!confirm("Delete this message for everyone?")) return;
    try { await api(`/store/chat/messages/${id}`, { method: "DELETE" }); const m = (S.msgs[S.room] || []).find(x => x.id === id); if (m) { m.deleted = true; m.text = ""; m.file = null; } drawMsgs(); } catch (e) { hint(e); }
  }

  // ---- photos and documents: +, paste, or drop on the chat --------------------------------------------------------------
  $("[data-clip]", pane).onclick = () => $file.click();
  $file.onchange = () => { if ($file.files[0]) pickFile($file.files[0]); $file.value = ""; };
  async function shrink(f) {           // a 6 MB phone photo goes as a sharp 2000-pixel picture of a few hundred kB
    if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size < 900 * 1024) return f;
    try { const bmp = await createImageBitmap(f); const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
      const c = document.createElement("canvas"); c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
      const b = await new Promise(r => c.toBlob(r, "image/jpeg", 0.85)); return b && b.size < f.size ? new File([b], f.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : f;
    } catch (e) { return f; }
  }
  async function pickFile(f) {
    if (!S.room) return;
    if (f.size > 25 * 1048576) { hint(new Error("Files up to 25 MB can be sent.")); return; }
    // a photo opens in the editor first - draw, circle, arrow, write, stickers - as on WhatsApp
    if (/^image\/(jpeg|png|webp|bmp)$/.test(f.type) && window.CHAT_DRAW) {
      const room = S.room, cap = $in.value.trim();
      const ok = await window.CHAT_DRAW.open(f, { name: f.name, caption: cap,
        onSend: (ef, caption) => { if (S.room !== room) return; $in.value = ""; grow(); sendFile(ef, caption); },
        onCancel: () => $in.focus() });
      if (ok) return;
    }
    S.file = await shrink(f); drawAtt(); grow(); $in.placeholder = "Add a caption"; $in.focus();
  }
  function drawAtt() {
    const f = S.file; $in.placeholder = f ? "Add a caption" : "Type a message";
    if (!f) { $att.innerHTML = ""; return; }
    const ext = (f.name.split(".").pop() || "").slice(0, 4).toUpperCase();
    const img = /^image\//.test(f.type) ? `<img src="${URL.createObjectURL(f)}">` : `<span class="di" style="width:42px;height:52px;border-radius:4px;background:${DOCCOL[ext] || "#8696A0"};color:#fff;font:700 10px/52px sans-serif;text-align:center">${esc(ext)}</span>`;
    $att.innerHTML = `<div class="att">${img}<span class="an"><b>${esc(f.name)}</b><small>${kb(f.size)} &middot; add a caption if you like, then send</small></span><button class="ib" data-rm title="Remove">${I.x}</button></div>`;
    $("[data-rm]", $att).onclick = () => { S.file = null; drawAtt(); grow(); };
  }
  async function sendFile(f, text, kind, duration) {
    if (!S.room) return;
    const room = S.room;
    if (!kind) { S.file = null; drawAtt(); $in.value = ""; grow(); }
    try {
      const fd = new FormData(); fd.append("room", room); fd.append("file", f, f.name || "file"); fd.append("text", text || "");
      if (kind) fd.append("kind", kind); if (duration) fd.append("duration", String(duration));
      const m = await api("/store/chat/upload", { method: "POST", body: fd });
      (S.msgs[room] = S.msgs[room] || []).push(m); S.lastId[room] = Math.max(S.lastId[room] || 0, m.id);
      S.previews[room] = { id: m.id, user_id: m.user_id, at: m.at, text: m.text, kind: m.file ? m.file.kind : "" };
      if (room === S.room) drawMsgs(true); drawList();
    } catch (e) { hint(e); }
  }
  $in.addEventListener("paste", e => { const f = [...((e.clipboardData || {}).files || [])][0]; if (f) { e.preventDefault(); pickFile(f); } });
  const main = $(".main", pane);
  main.addEventListener("dragover", e => { if (S.room && [...(e.dataTransfer.types || [])].includes("Files")) { e.preventDefault(); pane.classList.add("drop"); } });
  main.addEventListener("dragleave", e => { if (!main.contains(e.relatedTarget)) pane.classList.remove("drop"); });
  main.addEventListener("drop", e => { e.preventDefault(); pane.classList.remove("drop"); const f = e.dataTransfer.files[0]; if (f) pickFile(f); });

  // ---- voice messages: the microphone (it turns into Send while typing), as on WhatsApp --------------------------------------
  const $rt = $("[data-rt]", pane), $wave = $("[data-wave]", pane);
  let R = null;
  $("[data-go]", pane).onclick = () => { if (R) stopRec(true); else if ($in.value.trim() || S.file) send(); else startRec(); };
  async function startRec() {
    if (!S.room || R) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) { hint(new Error("This browser cannot record - use Chrome, Edge or Safari.")); return; }
    let stream; try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { hint(new Error("The microphone is blocked - allow it for this site and try again.")); return; }
    const type = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
    const rec = new MediaRecorder(stream, type ? { mimeType: type, audioBitsPerSecond: 32000 } : {});
    const chunks = []; rec.ondataavailable = e => e.data.size && chunks.push(e.data);
    let ctx, an; try { ctx = new AudioContext(); an = ctx.createAnalyser(); an.fftSize = 256; ctx.createMediaStreamSource(stream).connect(an); } catch (e) {}
    R = { rec, stream, chunks, t0: Date.now(), ctx, an, send: false, room: S.room };
    rec.onstop = async () => {
      stream.getTracks().forEach(t => t.stop()); try { ctx && ctx.close(); } catch (e) {}
      const secs = Math.round((Date.now() - R.t0) / 1000), go = R.send, room = R.room; clearInterval(R.tick); R = null;
      $cmp.classList.remove("recording"); $wave.innerHTML = ""; grow();
      if (!go || secs < 1 || !chunks.length || room !== S.room) return;
      const mime = (rec.mimeType || "audio/webm").split(";")[0];
      const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
      await sendFile(new File(chunks, `voice.${ext}`, { type: mime }), "", "voice", secs);
    };
    rec.start(250);
    $cmp.classList.add("recording"); $rt.textContent = "0:00";
    const buf = new Uint8Array(128);
    R.tick = setInterval(() => {
      const s = Math.floor((Date.now() - R.t0) / 1000); $rt.textContent = dur(s);
      if (R.an) { R.an.getByteTimeDomainData(buf); let pk = 0; for (const v of buf) pk = Math.max(pk, Math.abs(v - 128));
        const i = document.createElement("i"); i.style.height = Math.max(3, Math.min(24, pk / 2.4)) + "px"; $wave.appendChild(i); if ($wave.children.length > 55) $wave.firstChild.remove(); }
      if (s >= 300) stopRec(true);       // five minutes at most
    }, 120);
  }
  function stopRec(send) { if (!R) return; R.send = send; try { R.rec.stop(); } catch (e) {} }
  $("[data-rcancel]", pane).onclick = () => stopRec(false);

  // @ tagging: a list of people as the name is typed; Enter / Tab / click puts in @username
  let pickAt = -1, pickSel = 0, pickList = [];
  function pickUpdate() {
    const pos = $in.selectionStart, before = $in.value.slice(0, pos), m = before.match(/(^|\s)@([\w.\-]*)$/);
    if (!m) { $pick.style.display = "none"; pickAt = -1; return; }
    pickAt = pos - m[2].length - 1; const q = m[2].toLowerCase();
    pickList = S.users.filter(u => !u.me && (u.name.toLowerCase().split(/\s+/).some(w => w.startsWith(q)) || u.username.toLowerCase().startsWith(q))).slice(0, 8);
    if (S.room === "all" && "everyone".startsWith(q)) pickList.unshift({ username: "everyone", name: "Everyone", group: true, all: true });
    if (!pickList.length) { $pick.style.display = "none"; return; }
    pickSel = Math.min(pickSel, pickList.length - 1);
    $pick.innerHTML = pickList.map((u, i) => `<div class="${i === pickSel ? "sel" : ""}" data-i="${i}">${avatar(u, "sm")}<span>${esc(u.name)}<br><small>@${esc(u.username)}${u.online ? " &middot; online" : ""}</small></span></div>`).join("");
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

  // ---- open / close ------------------------------------------------------------------------------------------------------------
  async function open(room) {
    S.open = true; pane.classList.add("on");
    let want = room; if (!want) { try { want = localStorage.getItem("chat_room") || ""; } catch (e) {} }
    if (innerWidth <= 760 && !room) want = "";
    await poll();
    if (want && (want === "all" || S.users.some(u => u.room === want))) openRoom(want);
    else { S.room = ""; pane.classList.remove("conv"); showRoom(); drawList(); }
    schedule();
  }
  function close() { if (R) stopRec(false); if (PLAYING) { PLAYING.a.pause(); PLAYING.stop(); PLAYING = null; } S.open = false; pane.classList.remove("on"); $pick.style.display = "none"; closeMenu(); schedule(); }
  document.addEventListener("keydown", e => { if (e.key === "Escape" && S.open) { const v = $("[data-viewer]", pane); if (v.classList.contains("on")) { v.classList.remove("on"); return; }
    if ($pick.style.display !== "block" && !S.edit && !document.querySelector(".modal.show")) close(); } });

  // signing out: this person's files go at once, and he shows offline straight away
  const bye = closing => { const t = tok(); if (!t) return;
    try { fetch((typeof API !== "undefined" ? API : "") + "/store/chat/bye", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: t, closing: !!closing }) }); } catch (e) {} };
  if (typeof window.doLogout === "function") { const orig = window.doLogout; window.doLogout = function () { bye(); return orig.apply(this, arguments); }; }
  // closing the window or tab: offline at once (not after the 70 seconds it took before)
  window.addEventListener("pagehide", () => bye(true));
  window.addEventListener("pageshow", e => { if (e.persisted) poll(); });

  drawBell();
  window.CHAT = { open, close, poll, state: S };
  setTimeout(() => { poll(); schedule(); }, 1500);
})();
