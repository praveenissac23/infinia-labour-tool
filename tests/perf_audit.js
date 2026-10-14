// Every page, tab and sub-tab, as admin: how long it takes to settle, how
// much the layout jumps after it first paints, which server calls are slow,
// page errors, sideways overflow, text boxes without a placeholder, and
// font sizes outside the standard set. Writes /tmp/claude-0/perf.json.
const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8032';
const W = +(process.env.W || 1440);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.dismiss());
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  await p.evaluate(() => {
    window.__pend = 0; window.__calls = [];
    const of = window.fetch;
    window.fetch = async function (u, o) { const t = performance.now(); window.__pend++;
      try { return await of.apply(this, arguments); } finally { window.__pend--; window.__calls.push({ u: String(u).replace(/^https?:\/\/[^/]+/, '').split('?')[0], ms: Math.round(performance.now() - t) }); } };
    window.__cls = 0; window.__shifts = [];
    new PerformanceObserver(l => { for (const e of l.getEntries()) { if (!e.hadRecentInput) { window.__cls += e.value; window.__shifts.push(e.value); } } }).observe({ type: 'layout-shift', buffered: false });
  });
  const tabs = await p.evaluate(() => {
    const out = [];
    for (const [key, cfg] of Object.entries(ALL_PAGES)) {
      if (!pgPageOk(key)) continue;
      for (const t of cfg.tabs) {
        if (t.hidden || !pgTabRightOk(t)) continue;
        const subs = (t.subs || []).filter(pgSubOk);
        if (subs.length) subs.forEach(s => out.push([key, t.id + ':' + s.id, cfg.title + ' > ' + t.label + ' > ' + s.label]));
        else out.push([key, t.id, cfg.title + ' > ' + t.label]);
      }
    }
    return out;
  });
  const res = [];
  for (const [key, hash, name] of tabs) {
    await p.evaluate(() => { window.__calls = []; window.__cls = 0; window.__shifts = []; });
    const e0 = errs.length;
    const t0 = Date.now();
    await p.evaluate(([k, h]) => { pgGo(k, h); const [t, s] = h.split(':'); if (s) { pgTab(t); pgSub(s); } else pgTab(t); }, [key, hash]);
    // settled = no calls in flight and the DOM quiet for 300 ms
    let last = Date.now(), lastLen = -1;
    while (Date.now() - t0 < 15000) {
      const st = await p.evaluate(() => [window.__pend, document.body.innerHTML.length]);
      if (st[0] > 0 || st[1] !== lastLen) { last = Date.now(); lastLen = st[1]; }
      if (Date.now() - last > 300) break;
      await p.waitForTimeout(50);
    }
    const settle = last - t0;
    const info = await p.evaluate(() => {
      const scr = document.querySelector('.screen.active');
      const out = { cls: +window.__cls.toFixed(3), calls: window.__calls.slice().sort((a, b) => b.ms - a.ms).slice(0, 4),
                    overflow: document.documentElement.scrollWidth > innerWidth + 2, noPh: [], fonts: {} };
      if (scr) {
        scr.querySelectorAll('input[type=text]:not([readonly]), input:not([type]), input[type=number], input[type=search], textarea').forEach(i => {
          if (i.offsetParent && !i.placeholder && !i.value) out.noPh.push(i.id || i.name || i.className.slice(0, 20));
        });
        scr.querySelectorAll('*').forEach(el => { if (!el.offsetParent || !el.childNodes.length) return;
          if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
          const f = getComputedStyle(el).fontSize; out.fonts[f] = (out.fonts[f] || 0) + 1; });
      }
      return out;
    });
    res.push({ name, key, hash, settle, ...info, errors: errs.slice(e0) });
    console.log(`${String(settle).padStart(5)}ms  cls ${info.cls.toFixed(3)}  ${name}${info.calls[0] ? '  [' + info.calls[0].u + ' ' + info.calls[0].ms + 'ms]' : ''}${info.overflow ? '  OVERFLOW' : ''}${info.noPh.length ? '  noPh:' + info.noPh.join(',') : ''}${errs.length > e0 ? '  ERR ' + errs.slice(e0)[0] : ''}`);
  }
  fs.writeFileSync(`/tmp/claude-0/perf_${W}.json`, JSON.stringify(res, null, 1));
  await b.close();
})();
