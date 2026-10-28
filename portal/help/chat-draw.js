/* Infinia Chat - the photo editor, as on WhatsApp: when a photo is picked it opens here first, to draw on it,
   circle or box something, point with an arrow, write on it, put stickers on it - then add a caption and send.
   CHAT_DRAW.open(file, { name, onSend(file, caption), onCancel() }) */
(function () {
  if (window.CHAT_DRAW) return;
  const COLORS = ["#E53935", "#FFFFFF", "#111111", "#FDD835", "#43A047", "#1E88E5", "#FB8C00", "#8E24AA"];
  const STICKERS = ["✅", "❌", "⚠️", "❗", "❓", "👍", "👎", "👌", "👀", "🙏", "⭕", "🔴", "🟢", "🟡", "⬆️", "⬇️", "⬅️", "➡️", "↗️", "↘️",
                    "🔨", "🔧", "🪛", "🧱", "🏗️", "🚧", "🪜", "📏", "📐", "💧", "⚡", "🔥", "🧯", "🦺", "⛑️", "🚿", "🚪", "🪟", "💡", "🔌",
                    "😊", "😂", "😮", "😡", "😢", "👏", "💯", "🆗", "🆕", "⭐"];
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const svg = d => `<svg viewBox="0 0 24 24" fill="currentColor">${d}</svg>`;
  const IC = {
    pen: svg('<path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>'),
    circle: svg('<path d="M12 3C7 3 3 7 3 12s4 9 9 9 9-4 9-9-4-9-9-9zm0 16.2c-4 0-7.2-3.2-7.2-7.2S8 4.8 12 4.8s7.2 3.2 7.2 7.2-3.2 7.2-7.2 7.2z"/>'),
    rect: svg('<path d="M3 5v14h18V5H3zm16.2 12.2H4.8V6.8h14.4v10.4z"/>'),
    arrow: svg('<path d="M5 18.6L15.6 8H9V6h10v10h-2V9.4L6.4 20z"/>'),
    text: svg('<path d="M5 4v3h5.5v12h3V7H19V4H5z"/>'),
    sticker: svg('<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-3.5 6a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zm7 0a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zM12 17.5c-2.3 0-4.3-1.4-5.1-3.5h10.2c-.8 2.1-2.8 3.5-5.1 3.5z"/>'),
    move: svg('<path d="M10 9h4V6h3l-5-5-5 5h3v3zm-1 1H6V7l-5 5 5 5v-3h3v-4zm14 2l-5-5v3h-3v4h3v3l5-5zm-9 3h-4v3H7l5 5 5-5h-3v-3z"/>'),
    undo: svg('<path d="M12.5 8c-2.6 0-5 1-6.9 2.6L2 7v9h9l-3.6-3.6A8 8 0 0 1 20.5 16l2.4-.8A10.5 10.5 0 0 0 12.5 8z"/>'),
    rotate: svg('<path d="M7.1 8.5L5.7 7.1C4.8 8.3 4.2 9.6 4.1 11h2a6 6 0 0 1 1-2.5zM6.1 13h-2c.2 1.4.7 2.7 1.6 3.9l1.4-1.4A6.3 6.3 0 0 1 6.1 13zm1 5.3a8 8 0 0 0 3.9 1.6v-2a6 6 0 0 1-2.5-1L7.1 18.3zM13 4.1V1L8.5 5.5 13 10V6.1a6 6 0 0 1 0 11.8v2A8 8 0 0 0 13 4.1z"/>'),
    x: svg('<path d="M19.1 17.2l-5.3-5.2 5.3-5.3-1.8-1.8-5.3 5.3-5.2-5.3-1.9 1.8 5.3 5.3-5.3 5.2 1.9 1.9 5.2-5.3 5.3 5.3z"/>'),
    send: svg('<path d="M1.1 21.8L23 12 1.1 2.2 1.1 9.8 16.7 12 1.1 14.2z"/>'),
    trash: svg('<path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>'),
  };
  const css = document.createElement("style");
  css.textContent = `
  #wa-draw { position: fixed; inset: 0; z-index: 7000; background: #1B1E22; display: none; flex-direction: column; font: 14px/1.4 "Segoe UI", -apple-system, sans-serif; color: #E9EDEF; user-select: none; }
  #wa-draw.on { display: flex; }
  #wa-draw .tb { height: 62px; display: flex; align-items: center; gap: 4px; padding: 0 14px; background: #24282D; border-bottom: 1px solid #33383E; flex-shrink: 0; }
  #wa-draw .tb .sp { flex: 1; } #wa-draw .tb .nm { font-size: 14px; color: #AEBAC1; margin: 0 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 30vw; }
  #wa-draw .t { width: 42px; height: 42px; border-radius: 50%; border: 0; background: transparent; color: #E9EDEF; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; position: relative; }
  #wa-draw .t:hover { background: rgba(255,255,255,.08); } #wa-draw .t.on { background: #C0392B; color: #fff; } #wa-draw .t svg { width: 23px; height: 23px; }
  #wa-draw .t:disabled { opacity: .3; cursor: default; background: transparent; }
  #wa-draw .tip { position: absolute; top: 46px; left: 50%; transform: translateX(-50%); background: #000; color: #fff; font-size: 11.5px; padding: 3px 8px; border-radius: 5px; white-space: nowrap; display: none; z-index: 3; }
  #wa-draw .t:hover .tip { display: block; }
  #wa-draw .opts { display: flex; align-items: center; gap: 10px; padding: 8px 14px; background: #24282D; flex-shrink: 0; flex-wrap: wrap; min-height: 50px; }
  #wa-draw .sw { width: 26px; height: 26px; border-radius: 50%; border: 2px solid rgba(255,255,255,.25); cursor: pointer; padding: 0; }
  #wa-draw .sw.on { border-color: #fff; box-shadow: 0 0 0 2px #C0392B; transform: scale(1.12); }
  #wa-draw .wd { border: 0; background: transparent; cursor: pointer; width: 34px; height: 34px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; }
  #wa-draw .wd i { display: block; border-radius: 50%; background: #E9EDEF; } #wa-draw .wd.on { background: rgba(255,255,255,.14); }
  #wa-draw .sep { width: 1px; height: 26px; background: #3B4248; margin: 0 4px; }
  #wa-draw .hint2 { color: #8696A0; font-size: 12.5px; margin-left: auto; }
  #wa-draw .hint3 { color: #8696A0; font-size: 12.5px; }
  #wa-draw .stage { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 18px; position: relative; overflow: hidden; }
  #wa-draw canvas { max-width: 100%; max-height: 100%; box-shadow: 0 10px 40px rgba(0,0,0,.5); touch-action: none; cursor: crosshair; background: #fff; }
  #wa-draw canvas.mv { cursor: grab; }
  #wa-draw .stk { position: absolute; top: 120px; left: 50%; transform: translateX(-50%); width: min(520px, 92vw); max-height: 52vh; overflow-y: auto; background: #2A2F34; border-radius: 14px; padding: 12px; display: none; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 4px; box-shadow: 0 12px 40px rgba(0,0,0,.5); z-index: 4; }
  #wa-draw .stk.on { display: grid; } #wa-draw .stk button { font-size: 28px; height: 46px; border: 0; background: transparent; border-radius: 8px; cursor: pointer; } #wa-draw .stk button:hover { background: rgba(255,255,255,.1); }
  #wa-draw .txin { position: absolute; z-index: 5; min-width: 60px; border: 2px dashed rgba(255,255,255,.7); background: rgba(0,0,0,.25); outline: 0; font-weight: 700; padding: 2px 6px; border-radius: 4px; white-space: pre; }
  #wa-draw .bot { flex-shrink: 0; display: flex; align-items: center; gap: 12px; padding: 12px 18px 16px; background: #24282D; }
  #wa-draw .bot input { flex: 1; border: 0; outline: 0; background: #33383E; color: #E9EDEF; border-radius: 9px; padding: 12px 14px; font: inherit; font-size: 15px; }
  #wa-draw .bot input::placeholder { color: #8696A0; }
  #wa-draw .go { width: 54px; height: 54px; border-radius: 50%; border: 0; background: #C0392B; color: #fff; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; box-shadow: 0 4px 14px rgba(192,57,43,.45); flex-shrink: 0; }
  #wa-draw .go:hover { background: #A93226; } #wa-draw .go svg { width: 26px; height: 26px; }
  #wa-draw .del { position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%); width: 50px; height: 50px; border-radius: 50%; background: rgba(0,0,0,.55); color: #fff; display: none; align-items: center; justify-content: center; z-index: 4; }
  #wa-draw .del.on { display: flex; } #wa-draw .del.hot { background: #E53935; transform: translateX(-50%) scale(1.15); } #wa-draw .del svg { width: 24px; }
  @media (max-width: 760px) { #wa-draw .tb { padding: 0 4px; gap: 0; } #wa-draw .t { width: 38px; height: 38px; } #wa-draw .tb .nm { display: none; } #wa-draw .hint2 { display: none; } #wa-draw .stage { padding: 8px; } }`;
  document.head.appendChild(css);

  const el = document.createElement("div"); el.id = "wa-draw";
  const tool = (k, label) => `<button class="t" data-tool="${k}">${IC[k]}<span class="tip">${label}</span></button>`;
  el.innerHTML = `<div class="tb"><button class="t" data-close>${IC.x}<span class="tip">Cancel</span></button><span class="nm" data-name></span><span class="sp"></span>
      ${tool("pen", "Draw")}${tool("circle", "Circle")}${tool("rect", "Box")}${tool("arrow", "Arrow")}${tool("text", "Text")}${tool("sticker", "Sticker")}${tool("move", "Move / resize")}
      <span class="sep"></span><button class="t" data-rot>${IC.rotate}<span class="tip">Rotate</span></button><button class="t" data-undo>${IC.undo}<span class="tip">Undo</span></button></div>
    <div class="opts" data-opts></div>
    <div class="stage" data-stage><canvas data-cv></canvas><div class="stk" data-stk>${STICKERS.map(s => `<button data-s="${s}">${s}</button>`).join("")}</div>
      <div class="del" data-del>${IC.trash}</div></div>
    <div class="bot"><input data-cap placeholder="Add a caption..." maxlength="1000"><button class="go" data-send title="Send">${IC.send}</button></div>`;
  document.body.appendChild(el);
  const $ = s => el.querySelector(s);
  const cv = $("[data-cv]"), ctx = cv.getContext("2d"), stage = $("[data-stage]");

  // ---- state ----
  let IMG = null, OPTS = {}, items = [], T = "pen", COLOR = COLORS[0], WIDTH = 2, cur = null, drag = null, rot = 0;
  const W = () => cv.width, H = () => cv.height, U = () => Math.max(W(), H()) / 1000;      // 1 unit = a thousandth of the picture
  const widths = [1, 2, 4];

  function drawOpts() {
    const o = $("[data-opts]");
    if (T === "sticker" || T === "move") {
      o.innerHTML = `<span class="hint3">${T === "sticker" ? "Pick a sticker - then drag it where it goes; Move / resize to change its size" : "Drag a sticker, text or shape to move it - the corner circle or the mouse wheel changes its size - drag it to the bin to remove it"}</span>`;
      return;
    }
    o.innerHTML = COLORS.map(c => `<button class="sw ${c === COLOR ? "on" : ""}" data-c="${c}" style="background:${c}"></button>`).join("")
      + (T === "text" ? "" : `<span class="sep"></span>` + widths.map(w => `<button class="wd ${w === WIDTH ? "on" : ""}" data-w="${w}"><i style="width:${4 + w * 3}px;height:${4 + w * 3}px"></i></button>`).join(""))
      + `<span class="hint2">${{ pen: "Draw with the mouse or a finger", circle: "Drag to circle something", rect: "Drag to draw a box", arrow: "Drag from where the arrow starts to where it points", text: "Click on the photo where the words go" }[T] || ""}</span>`;
    o.querySelectorAll("[data-c]").forEach(b => b.onclick = () => { COLOR = b.dataset.c; drawOpts(); });
    o.querySelectorAll("[data-w]").forEach(b => b.onclick = () => { WIDTH = +b.dataset.w; drawOpts(); });
  }
  function setTool(k) {
    if (k === "sticker") { $("[data-stk]").classList.toggle("on"); } else $("[data-stk]").classList.remove("on");
    T = k; el.querySelectorAll("[data-tool]").forEach(b => b.classList.toggle("on", b.dataset.tool === k));
    cv.classList.toggle("mv", k === "move" || k === "sticker"); drawOpts();
  }
  el.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
  $("[data-stk]").querySelectorAll("[data-s]").forEach(b => b.onclick = () => {
    items.push({ k: "stk", s: b.dataset.s, x: W() / 2, y: H() / 2, size: 120 * U() }); $("[data-stk]").classList.remove("on"); render(); setTool("move");
  });
  $("[data-undo]").onclick = () => { items.pop(); render(); };

  // ---- drawing everything ----
  function arrowHead(x1, y1, x2, y2, w) {
    const a = Math.atan2(y2 - y1, x2 - x1), L = Math.max(14, w * 5);
    ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - L * Math.cos(a - 0.45), y2 - L * Math.sin(a - 0.45));
    ctx.lineTo(x2 - L * Math.cos(a + 0.45), y2 - L * Math.sin(a + 0.45)); ctx.closePath(); ctx.fill();
  }
  function paint(it) {
    ctx.save(); ctx.strokeStyle = ctx.fillStyle = it.c; ctx.lineWidth = it.w; ctx.lineCap = ctx.lineJoin = "round";
    // a thin dark edge under white / yellow lines keeps them visible on a light wall
    const shadow = ["#FFFFFF", "#FDD835"].includes(it.c); if (shadow) { ctx.shadowColor = "rgba(0,0,0,.45)"; ctx.shadowBlur = it.w; }
    if (it.k === "pen") { ctx.beginPath(); it.p.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); if (it.p.length === 1) ctx.lineTo(it.p[0][0] + .1, it.p[0][1]); ctx.stroke(); }
    else if (it.k === "circle") { const cx = (it.x1 + it.x2) / 2, cy = (it.y1 + it.y2) / 2; ctx.beginPath(); ctx.ellipse(cx, cy, Math.abs(it.x2 - it.x1) / 2 || 1, Math.abs(it.y2 - it.y1) / 2 || 1, 0, 0, Math.PI * 2); ctx.stroke(); }
    else if (it.k === "rect") { ctx.strokeRect(Math.min(it.x1, it.x2), Math.min(it.y1, it.y2), Math.abs(it.x2 - it.x1), Math.abs(it.y2 - it.y1)); }
    else if (it.k === "arrow") { ctx.beginPath(); ctx.moveTo(it.x1, it.y1); ctx.lineTo(it.x2, it.y2); ctx.stroke(); arrowHead(it.x1, it.y1, it.x2, it.y2, it.w); }
    else if (it.k === "text") {
      ctx.shadowBlur = 0; ctx.font = `700 ${it.size}px "Segoe UI", -apple-system, sans-serif`; ctx.textBaseline = "top";
      const lines = it.t.split("\n"), lh = it.size * 1.2, wmax = Math.max(...lines.map(l => ctx.measureText(l).width));
      if (it.bg) { ctx.fillStyle = it.c === "#FFFFFF" || it.c === "#FDD835" ? "rgba(0,0,0,.55)" : "rgba(255,255,255,.85)"; ctx.fillRect(it.x - it.size * .3, it.y - it.size * .15, wmax + it.size * .6, lines.length * lh + it.size * .2); }
      ctx.fillStyle = it.c; lines.forEach((l, i) => ctx.fillText(l, it.x, it.y + i * lh)); it.bw = wmax; it.bh = lines.length * lh;
    }
    else if (it.k === "stk") { ctx.shadowBlur = 0; ctx.font = `${it.size}px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(it.s, it.x, it.y); }
    ctx.restore();
  }
  function render(sel) {
    ctx.save(); ctx.clearRect(0, 0, W(), H());
    ctx.translate(W() / 2, H() / 2); ctx.rotate(rot * Math.PI / 2);
    const iw = IMG.width, ih = IMG.height; ctx.drawImage(IMG, -iw * IMG.k / 2, -ih * IMG.k / 2, iw * IMG.k, ih * IMG.k); ctx.restore();
    items.forEach(paint); if (cur) paint(cur);
    if (sel) { const b = box(sel); if (b) { ctx.save(); ctx.strokeStyle = "#fff"; ctx.setLineDash([8 * U(), 6 * U()]); ctx.lineWidth = 2 * U(); ctx.shadowColor = "rgba(0,0,0,.6)"; ctx.shadowBlur = 4;
      ctx.strokeRect(b.x, b.y, b.w, b.h); ctx.setLineDash([]); ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(b.x + b.w, b.y + b.h, 12 * U(), 0, Math.PI * 2); ctx.fill(); ctx.restore(); } }
  }
  function box(it) {
    if (it.k === "stk") return { x: it.x - it.size / 2, y: it.y - it.size / 2, w: it.size, h: it.size };
    if (it.k === "text") return { x: it.x - it.size * .3, y: it.y - it.size * .15, w: (it.bw || it.size * 3) + it.size * .6, h: (it.bh || it.size) + it.size * .3 };
    if (it.k === "pen") { const xs = it.p.map(p => p[0]), ys = it.p.map(p => p[1]); return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }; }
    return { x: Math.min(it.x1, it.x2), y: Math.min(it.y1, it.y2), w: Math.abs(it.x2 - it.x1), h: Math.abs(it.y2 - it.y1) };
  }
  const hit = (x, y) => { const pad = 14 * U(); for (let i = items.length - 1; i >= 0; i--) { const b = box(items[i]); if (x >= b.x - pad && x <= b.x + b.w + pad && y >= b.y - pad && y <= b.y + b.h + pad) return items[i]; } return null; };
  const move = (it, dx, dy) => { if (it.k === "pen") it.p = it.p.map(([x, y]) => [x + dx, y + dy]); else if ("x1" in it) { it.x1 += dx; it.x2 += dx; it.y1 += dy; it.y2 += dy; } else { it.x += dx; it.y += dy; } };
  const grow = (it, f) => { if (it.k === "stk" || it.k === "text") { it.size = Math.max(10 * U(), Math.min(it.size * f, 900 * U())); }
    else { const b = box(it), cx = b.x + b.w / 2, cy = b.y + b.h / 2; const sc = ([x, y]) => [cx + (x - cx) * f, cy + (y - cy) * f];
      if (it.k === "pen") it.p = it.p.map(sc); else { [it.x1, it.y1] = sc([it.x1, it.y1]); [it.x2, it.y2] = sc([it.x2, it.y2]); } } };

  // ---- the pointer ----
  const pos = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * W() / r.width, (e.clientY - r.top) * H() / r.height]; };
  cv.addEventListener("pointerdown", e => {
    if (txtBox) { commitText(); return; }
    cv.setPointerCapture(e.pointerId); const [x, y] = pos(e); const w = (WIDTH === 1 ? 4 : WIDTH === 2 ? 8 : 16) * U();
    if (T === "move" || T === "sticker") {
      const it = hit(x, y); if (!it) return;
      const b = box(it), corner = Math.hypot(x - (b.x + b.w), y - (b.y + b.h)) < 30 * U();
      items.splice(items.indexOf(it), 1); items.push(it);
      drag = { it, x, y, corner, d0: Math.hypot(x - (b.x + b.w / 2), y - (b.y + b.h / 2)) || 1 }; $("[data-del]").classList.add("on"); render(it); return;
    }
    if (T === "text") { startText(e, x, y); return; }
    if (T === "pen") cur = { k: "pen", c: COLOR, w, p: [[x, y]] };
    else cur = { k: T, c: COLOR, w, x1: x, y1: y, x2: x, y2: y };
    render();
  });
  cv.addEventListener("pointermove", e => {
    const [x, y] = pos(e);
    if (drag) {
      if (drag.corner) { const b = box(drag.it), d = Math.hypot(x - (b.x + b.w / 2), y - (b.y + b.h / 2)) || 1; grow(drag.it, d / drag.d0); drag.d0 = d; }
      else { move(drag.it, x - drag.x, y - drag.y); drag.x = x; drag.y = y; }
      const dr = $("[data-del]").getBoundingClientRect(); $("[data-del]").classList.toggle("hot", e.clientX > dr.left - 10 && e.clientX < dr.right + 10 && e.clientY > dr.top - 10 && e.clientY < dr.bottom + 10);
      render(drag.it); return;
    }
    if (!cur) return;
    if (cur.k === "pen") cur.p.push([x, y]); else { cur.x2 = x; cur.y2 = y; if (e.shiftKey && cur.k !== "arrow") { const s = Math.max(Math.abs(x - cur.x1), Math.abs(y - cur.y1)); cur.x2 = cur.x1 + Math.sign(x - cur.x1) * s; cur.y2 = cur.y1 + Math.sign(y - cur.y1) * s; } }
    render();
  });
  const up = () => {
    if (drag) { if ($("[data-del]").classList.contains("hot")) items.splice(items.indexOf(drag.it), 1); drag = null; $("[data-del]").classList.remove("on", "hot"); render(); return; }
    if (!cur) return; const tiny = cur.k !== "pen" && Math.hypot(cur.x2 - cur.x1, cur.y2 - cur.y1) < 6 * U();
    if (!tiny) items.push(cur); cur = null; render();
  };
  cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
  cv.addEventListener("wheel", e => { if (T !== "move" && T !== "sticker") return; const [x, y] = pos(e); const it = hit(x, y); if (!it) return; e.preventDefault(); grow(it, e.deltaY < 0 ? 1.08 : 0.93); render(it); }, { passive: false });

  // ---- text: typed where it goes ----
  let txtBox = null;
  function startText(e, x, y) {
    const r = cv.getBoundingClientRect(), sr = stage.getBoundingClientRect(), k = r.width / W(), size = 64 * U();
    const t = document.createElement("div"); t.className = "txin"; t.contentEditable = "true";
    t.style.left = (e.clientX - sr.left) + "px"; t.style.top = (e.clientY - sr.top - size * k * .2) + "px"; t.style.color = COLOR; t.style.fontSize = (size * k) + "px";
    stage.appendChild(t); txtBox = { t, x, y, size }; setTimeout(() => t.focus(), 0);
    t.addEventListener("keydown", ev => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); commitText(); } if (ev.key === "Escape") { t.remove(); txtBox = null; } });
  }
  function commitText() {
    if (!txtBox) return; const s = txtBox.t.innerText.replace(/\n$/, "").trim();
    if (s) items.push({ k: "text", t: s, x: txtBox.x, y: txtBox.y, size: txtBox.size, c: COLOR, bg: true });
    txtBox.t.remove(); txtBox = null; render();
  }

  // ---- open, rotate, send ----
  $("[data-rot]").onclick = () => { rot = (rot + 1) % 4; layout(); items = []; render(); };
  function layout() {
    const iw = IMG.width * IMG.k, ih = IMG.height * IMG.k; const side = rot % 2 === 1;
    cv.width = Math.round(side ? ih : iw); cv.height = Math.round(side ? iw : ih);
  }
  function close() { el.classList.remove("on"); IMG = null; items = []; cur = null; drag = null; if (txtBox) { txtBox.t.remove(); txtBox = null; } }
  $("[data-close]").onclick = () => { close(); OPTS.onCancel && OPTS.onCancel(); };
  async function send() {
    commitText(); render();
    const blob = await new Promise(r => cv.toBlob(r, "image/jpeg", 0.88));
    const name = (OPTS.name || "photo").replace(/\.\w+$/, "") + ".jpg";
    const f = new File([blob], name, { type: "image/jpeg" }); const cap = $("[data-cap]").value.trim();
    close(); OPTS.onSend && OPTS.onSend(f, cap);
  }
  $("[data-send]").onclick = send;
  $("[data-cap]").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); send(); } });
  document.addEventListener("keydown", e => {
    if (!el.classList.contains("on") || txtBox || document.activeElement === $("[data-cap]")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); items.pop(); render(); }
    if (e.key === "Escape") { close(); OPTS.onCancel && OPTS.onCancel(); }
  });

  async function open(file, opts) {
    OPTS = opts || {};
    let bmp; try { bmp = await createImageBitmap(file, { imageOrientation: "from-image" }); } catch (e) { try { bmp = await createImageBitmap(file); } catch (x) { return false; } }
    bmp.k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));        // drawn at up to 2000 pixels - sharp, not heavy
    IMG = bmp; rot = 0; items = []; layout();
    $("[data-name]").textContent = OPTS.name || file.name || ""; $("[data-cap]").value = OPTS.caption || "";
    el.classList.add("on"); setTool("pen"); render();
    setTimeout(() => $("[data-cap]").focus(), 50);
    return true;
  }
  window.CHAT_DRAW = { open, close };
})();
