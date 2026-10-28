/* Estimation > Trello - animated board backgrounds (live wallpapers).
   Three packs - Bubbles, Gradients, Abstract - each a slow, seamless loop drawn on one canvas behind the lists.
   Nothing to download: every wallpaper is drawn by the browser, so it is sharp on any screen and costs no data.
   Kind to the computer: at most 30 frames a second, paused while the tab is hidden, a still frame for anyone
   who has asked their device for reduced motion. Saved on the board as "a_<name>". */
(function () {
  const TAU = Math.PI * 2;
  const rnd = (seed => () => (seed = (seed * 16807) % 2147483647) / 2147483647);
  // a soft round glow
  const glow = (c, x, y, r, col, a) => { const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, col.replace("A", a)); g.addColorStop(1, col.replace("A", 0)); c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill(); };
  const fillBase = (c, w, h, stops, ang = 1) => { const g = c.createLinearGradient(0, 0, w * ang, h); stops.forEach((s, i) => g.addColorStop(i / (stops.length - 1), s)); c.fillStyle = g; c.fillRect(0, 0, w, h); };
  // moving colour fields ("mesh gradient"): big soft blobs on slow loops - drawn small and stretched, so it costs little
  const mesh = (base, blobs, light) => ({ scale: 0.35, draw(c, w, h, t) {
    fillBase(c, w, h, base);
    c.globalCompositeOperation = light ? "source-over" : "lighter";
    blobs.forEach((b, i) => { const k = t / b[3]; const x = w * (0.5 + 0.38 * Math.sin(k * TAU + i * 1.7)), y = h * (0.5 + 0.34 * Math.cos(k * TAU * 0.8 + i * 2.3));
      glow(c, x, y, Math.max(w, h) * b[1], b[0], b[2]); });
    c.globalCompositeOperation = "source-over";
  } });
  const bubbles = (base, tint, count, big) => ({ init(w, h) { const r = rnd(7); return Array.from({ length: count }, () => ({ x: r(), y: r(), s: (big ? 10 : 3) + r() * (big ? 46 : 22), v: 0.012 + r() * 0.03, ph: r() * TAU, a: 0.07 + r() * 0.22 })); },
    draw(c, w, h, t, st) { fillBase(c, w, h, base); const z = Math.min(1, Math.max(w, h) / 1000);
      st.forEach(b0 => { const b = Object.assign({}, b0, { s: b0.s * z }); const y = ((b.y - t * b.v) % 1 + 1) % 1; const yy = y * (h + 120) - 60, xx = b.x * w + Math.sin(t * 0.6 + b.ph) * 18;
        const g = c.createRadialGradient(xx - b.s * 0.3, yy - b.s * 0.3, b.s * 0.1, xx, yy, b.s); g.addColorStop(0, `rgba(${tint},${b.a * 1.4})`); g.addColorStop(0.75, `rgba(${tint},${b.a * 0.35})`); g.addColorStop(1, `rgba(${tint},0)`);
        c.fillStyle = g; c.beginPath(); c.arc(xx, yy, b.s, 0, TAU); c.fill();
        c.strokeStyle = `rgba(255,255,255,${b.a * 0.7})`; c.lineWidth = 1; c.beginPath(); c.arc(xx, yy, b.s * 0.92, 0, TAU); c.stroke(); }); } });

  const A = {
    // ---- Bubbles pack ----
    a_bubbles: { pack: "Bubbles", name: "Deep sea", thumb: "linear-gradient(160deg,#03224C,#0B6E8A)", ...bubbles(["#021B3D", "#0A4F7A", "#0B7C8F"], "170,225,255", 70, false) },
    a_champagne: { pack: "Bubbles", name: "Champagne", thumb: "linear-gradient(160deg,#3A2A12,#9C7A3C)", ...bubbles(["#22180A", "#5E4520", "#A5823F"], "255,232,170", 90, false) },
    a_bokeh: { pack: "Bubbles", name: "Bokeh", thumb: "linear-gradient(160deg,#1B0F2E,#5B2A5E)",
      init() { const r = rnd(11); const cols = ["255,190,110", "255,120,160", "170,140,255", "120,200,255"]; return Array.from({ length: 34 }, () => ({ x: r(), y: r(), s: 0.04 + r() * 0.1, c: cols[Math.floor(r() * 4)], ph: r() * TAU, sp: 0.03 + r() * 0.05 })); },
      draw(c, w, h, t, st) { fillBase(c, w, h, ["#12091F", "#2E1440", "#52244F"]); c.globalCompositeOperation = "lighter";
        st.forEach(b => { const x = ((b.x + t * b.sp * 0.25) % 1) * (w + 200) - 100, y = b.y * h + Math.sin(t * b.sp * 4 + b.ph) * 40, a = 0.16 + 0.12 * Math.sin(t * 0.8 + b.ph);
          glow(c, x, y, Math.min(w, h) * b.s * 2.2, `rgba(${b.c},A)`, a); }); c.globalCompositeOperation = "source-over"; } },
    a_fireflies: { pack: "Bubbles", name: "Fireflies", thumb: "linear-gradient(160deg,#071A12,#1E4A2E)",
      init() { const r = rnd(5); return Array.from({ length: 60 }, () => ({ x: r(), y: r(), ph: r() * TAU, f: 0.2 + r() * 0.5, s: 1.5 + r() * 2.5 })); },
      draw(c, w, h, t, st) { fillBase(c, w, h, ["#04110B", "#0D2A1C", "#1D4630"]); c.globalCompositeOperation = "lighter";
        const z = Math.min(1, Math.max(w, h) / 1000);
        st.forEach(b0 => { const b = Object.assign({}, b0, { s: b0.s * z }); const x = (b.x + 0.05 * Math.sin(t * b.f * 0.5 + b.ph)) * w, y = (b.y + 0.06 * Math.cos(t * b.f * 0.4 + b.ph * 1.3)) * h, a = Math.max(0, Math.sin(t * b.f * 1.6 + b.ph));
          glow(c, x, y, b.s * 9, "rgba(220,255,140,A)", 0.55 * a); c.fillStyle = `rgba(250,255,210,${0.9 * a})`; c.beginPath(); c.arc(x, y, b.s * 0.6, 0, TAU); c.fill(); });
        c.globalCompositeOperation = "source-over"; } },
    a_pearl: { pack: "Bubbles", name: "Pearl", thumb: "linear-gradient(160deg,#E9EDF2,#B9C3CF)", ...bubbles(["#EEF1F5", "#D5DCE4", "#AFBACA"], "255,255,255", 60, true) },
    a_ruby: { pack: "Bubbles", name: "Ruby", thumb: "linear-gradient(160deg,#2A0B0B,#8E1F18)", ...bubbles(["#1A0606", "#4A110E", "#8E1F18"], "255,140,120", 70, false) },
    // ---- Gradients pack ----
    a_aurora: { pack: "Gradients", name: "Aurora", thumb: "linear-gradient(160deg,#061A2B,#0E6B5C,#4B2C7A)", ...mesh(["#04101C", "#071E2E"], [["rgba(40,220,160,A)", 0.55, 0.55, 46], ["rgba(90,80,230,A)", 0.5, 0.5, 58], ["rgba(20,160,220,A)", 0.45, 0.45, 38], ["rgba(190,90,220,A)", 0.35, 0.35, 70]]) },
    a_sunset: { pack: "Gradients", name: "Sunset", thumb: "linear-gradient(160deg,#3B0F3A,#D9534F,#F5A623)", ...mesh(["#2A0A2E", "#4A1238"], [["rgba(250,120,70,A)", 0.55, 0.6, 44], ["rgba(240,70,120,A)", 0.5, 0.55, 56], ["rgba(255,190,80,A)", 0.4, 0.5, 36], ["rgba(140,60,200,A)", 0.45, 0.45, 64]]) },
    a_ocean: { pack: "Gradients", name: "Ocean", thumb: "linear-gradient(160deg,#021F3F,#0A6BC2,#3CC8D8)", ...mesh(["#021428", "#04284A"], [["rgba(20,120,230,A)", 0.6, 0.6, 48], ["rgba(40,210,220,A)", 0.45, 0.5, 40], ["rgba(70,80,220,A)", 0.5, 0.45, 60], ["rgba(120,230,255,A)", 0.3, 0.35, 34]]) },
    a_infinia: { pack: "Gradients", name: "Infinia", thumb: "linear-gradient(160deg,#1C1F24,#7A1E19,#C0392B)", ...mesh(["#121418", "#1D2026"], [["rgba(192,57,43,A)", 0.55, 0.6, 50], ["rgba(140,30,40,A)", 0.5, 0.5, 62], ["rgba(240,120,90,A)", 0.32, 0.35, 40], ["rgba(90,100,120,A)", 0.45, 0.35, 70]]) },
    a_lavender: { pack: "Gradients", name: "Lavender", thumb: "linear-gradient(160deg,#C9B8F0,#F3B5D6,#A8D8F0)", ...mesh(["#B9A8E6", "#D7C6F2"], [["rgba(255,160,205,A)", 0.55, 0.55, 50], ["rgba(130,190,250,A)", 0.5, 0.5, 60], ["rgba(170,130,240,A)", 0.45, 0.5, 42], ["rgba(255,230,190,A)", 0.35, 0.35, 70]], true) },
    a_forest: { pack: "Gradients", name: "Forest", thumb: "linear-gradient(160deg,#06180F,#1F6B3E,#7DBE5A)", ...mesh(["#04120A", "#0A2414"], [["rgba(40,170,90,A)", 0.55, 0.55, 46], ["rgba(150,210,80,A)", 0.4, 0.4, 58], ["rgba(20,130,120,A)", 0.5, 0.5, 40], ["rgba(220,200,90,A)", 0.3, 0.3, 66]]) },
    // ---- Abstract pack ----
    a_waves: { pack: "Abstract", name: "Waves", thumb: "linear-gradient(160deg,#0B1D3A,#1E4D8C)",
      draw(c, w, h, t) { fillBase(c, w, h, ["#081630", "#10305E", "#1C4C88"]);
        for (let i = 0; i < 6; i++) { const y0 = h * (0.45 + i * 0.09), amp = 18 + i * 7, k = (1.2 + i * 0.35) / w * TAU, sp = 0.18 + i * 0.05;
          c.beginPath(); c.moveTo(0, h);
          for (let x = 0; x <= w; x += 12) c.lineTo(x, y0 + Math.sin(x * k + t * sp * TAU / 4 + i) * amp + Math.sin(x * k * 0.5 - t * 0.2 + i * 2) * amp * 0.6);
          c.lineTo(w, h); c.closePath(); c.fillStyle = `rgba(${90 + i * 20},${170 + i * 10},255,${0.07 + i * 0.025})`; c.fill(); } } },
    a_silk: { pack: "Abstract", name: "Silk", thumb: "linear-gradient(160deg,#14121F,#3A2F5C)",
      draw(c, w, h, t) { fillBase(c, w, h, ["#0E0C18", "#211A38", "#3A2D5E"]); c.lineWidth = 1.2;
        for (let i = 0; i < 46; i++) { const p = i / 46; c.strokeStyle = `hsla(${250 + p * 70},80%,75%,${0.06 + 0.14 * Math.sin(p * Math.PI)})`; c.beginPath();
          for (let x = -20; x <= w + 20; x += 16) { const y = h * 0.5 + Math.sin(x / w * TAU * 1.1 + t * 0.25 + p * 2.4) * h * 0.22 * (0.4 + p) + Math.cos(x / w * TAU * 0.6 - t * 0.18 + p * 4) * h * 0.08;
            x < -10 ? c.moveTo(x, y) : c.lineTo(x, y); } c.stroke(); } } },
    a_ribbons: { pack: "Abstract", name: "Ribbons", thumb: "linear-gradient(160deg,#16181C,#5A1712)",
      draw(c, w, h, t) { fillBase(c, w, h, ["#111317", "#1C1F25", "#2A1B1B"]); c.lineWidth = 1.3;
        for (let i = 0; i < 36; i++) { const p = i / 36; c.strokeStyle = `rgba(${200 + p * 40},${50 + p * 60},${40 + p * 30},${0.09 + 0.3 * Math.sin(p * Math.PI)})`; c.beginPath();
          for (let x = -20; x <= w + 20; x += 16) { const y = h * (0.35 + p * 0.3) + Math.sin(x / w * TAU * 0.8 - t * 0.22 + p * 3) * h * 0.18 + Math.sin(x / w * TAU * 1.7 + t * 0.15) * h * 0.04;
            x < -10 ? c.moveTo(x, y) : c.lineTo(x, y); } c.stroke(); } } },
    a_network: { pack: "Abstract", name: "Network", thumb: "linear-gradient(160deg,#071624,#123A55)",
      init() { const r = rnd(3); return Array.from({ length: 70 }, () => ({ x: r(), y: r(), vx: (r() - 0.5) * 0.02, vy: (r() - 0.5) * 0.02 })); },
      draw(c, w, h, t, st) { fillBase(c, w, h, ["#06121E", "#0C2638", "#14405A"]);
        const pts = st.slice(0, Math.max(14, Math.min(st.length, Math.round(w * h / 14000)))).map(p => [(((p.x + p.vx * t) % 1) + 1) % 1 * w, (((p.y + p.vy * t) % 1) + 1) % 1 * h]); const L = Math.min(170, w / 7);
        for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) { const dx = pts[i][0] - pts[j][0], dy = pts[i][1] - pts[j][1], d = Math.hypot(dx, dy);
          if (d < L) { c.strokeStyle = `rgba(120,200,255,${0.28 * (1 - d / L)})`; c.lineWidth = 1; c.beginPath(); c.moveTo(pts[i][0], pts[i][1]); c.lineTo(pts[j][0], pts[j][1]); c.stroke(); } }
        c.fillStyle = "rgba(170,225,255,.8)"; pts.forEach(p => { c.beginPath(); c.arc(p[0], p[1], 1.8, 0, TAU); c.fill(); }); } },
    a_orbit: { pack: "Abstract", name: "Orbit", thumb: "linear-gradient(160deg,#101418,#2B3440)",
      draw(c, w, h, t) { fillBase(c, w, h, ["#0D1014", "#1A2028", "#27313C"]); const cx = w * 0.7, cy = h * 0.55, R = Math.max(w, h);
        for (let i = 1; i <= 14; i++) { const r = R * i * 0.045, sides = 6, rot = t * (i % 2 ? 0.03 : -0.025) * (1 + i * 0.05);
          c.strokeStyle = `rgba(${i % 4 === 0 ? "192,57,43" : "200,210,225"},${0.05 + (i % 4 === 0 ? 0.18 : 0.06)})`; c.lineWidth = i % 4 === 0 ? 1.6 : 1; c.beginPath();
          for (let k = 0; k <= sides; k++) { const a = rot + k / sides * TAU; const x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r; k ? c.lineTo(x, y) : c.moveTo(x, y); } c.stroke(); } } },
    a_drift: { pack: "Abstract", name: "Drift", thumb: "linear-gradient(160deg,#F4F1EC,#D9D2C9)",
      init() { const r = rnd(9); return Array.from({ length: 26 }, () => ({ x: r(), y: r(), s: 20 + r() * 90, r: r() * TAU, v: (r() - 0.5) * 0.06, k: Math.floor(r() * 3) })); },
      draw(c, w, h, t, st) { fillBase(c, w, h, ["#F6F3EE", "#ECE6DE", "#DDD4C8"]);
        st.forEach(p => { const x = ((p.x + t * 0.004) % 1) * (w + 200) - 100, y = p.y * h + Math.sin(t * 0.2 + p.r) * 20, a = p.r + t * p.v;
          c.save(); c.translate(x, y); c.rotate(a); c.strokeStyle = p.k === 1 ? "rgba(192,57,43,.22)" : "rgba(60,70,85,.14)"; c.lineWidth = 1.4; c.beginPath();
          if (p.k === 0) c.arc(0, 0, p.s / 2, 0, TAU); else if (p.k === 1) { c.moveTo(0, -p.s / 2); c.lineTo(p.s / 2.3, p.s / 3); c.lineTo(-p.s / 2.3, p.s / 3); c.closePath(); } else c.rect(-p.s / 2, -p.s / 2, p.s, p.s);
          c.stroke(); c.restore(); }); } },
  };
  window.ANIM_BG = A;
  window.ANIM_PACKS = ["Bubbles", "Gradients", "Abstract"];

  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function runner(canvas, key, small) {
    const def = A[key]; if (!def) return null;
    const c = canvas.getContext("2d"); let st = null, w = 0, h = 0, raf = 0, last = 0, t0 = performance.now(), on = true;
    const size = () => { const r = canvas.getBoundingClientRect(); const s = (def.scale || 1) * Math.min(devicePixelRatio || 1, small ? 1 : 1.5);
      const nw = Math.max(2, Math.round(r.width * s)), nh = Math.max(2, Math.round(r.height * s));
      if (nw !== canvas.width || nh !== canvas.height) { canvas.width = nw; canvas.height = nh; c.setTransform(s, 0, 0, s, 0, 0); w = r.width; h = r.height; st = def.init ? def.init(w, h) : null; } };
    const frame = now => { if (!on) return; if (small && !canvas.isConnected) { on = false; return; } raf = requestAnimationFrame(frame); if (document.hidden || now - last < (small ? 50 : 33)) return; last = now;
      size(); if (w > 1) def.draw(c, w, h, (now - t0) / 1000 + 20, st); };
    if (still) { requestAnimationFrame(() => { size(); def.draw(c, w, h, 20, st); }); return { stop() {} }; }
    raf = requestAnimationFrame(frame);
    return { stop() { on = false; cancelAnimationFrame(raf); } };
  }
  window.animRunner = runner;
  // the board's own wallpaper: one canvas kept across redraws of the board, so the loop never jumps
  let cur = { key: "", canvas: null, run: null };
  window.mountBoardAnim = function (el, key) {
    if (!A[key]) { if (cur.run) cur.run.stop(); if (cur.canvas) cur.canvas.remove(); cur = { key: "", canvas: null, run: null }; return; }
    if (cur.key !== key) { if (cur.run) cur.run.stop(); const cv = document.createElement("canvas"); cv.className = "anim-bg"; cur = { key, canvas: cv, run: null }; el.prepend(cv); cur.run = runner(cv, key, false); return; }
    if (cur.canvas.parentNode !== el) el.prepend(cur.canvas);
  };
})();
