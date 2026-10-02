// Every page, tab and sub-tab, clicked the way a person does, measured for
// what makes the app feel slow or jumpy:
//   * shift   - the browser's own layout-shift score while the screen settles
//   * moved   - buttons / tabs / headings whose position changed after the
//               first frame (what reads as "buttons realign by themselves")
//   * settle  - ms until nothing on screen changes any more
//   node tests/jank_audit.js [user] [pass] [phone]
const { chromium, devices } = require('playwright');
const U = process.argv[2] || 'admin', PW = process.argv[3] || 'changeme123', PHONE = process.argv[4] === 'phone';
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext(PHONE ? { ...devices['iPhone 13'] } : { viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  if (process.env.SLOW) { const cdp = await ctx.newCDPSession(p); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 180, downloadThroughput: 4 * 1024 * 1024 / 8, uploadThroughput: 1024 * 1024 / 8 }); }
  const errs = []; let cur = 'start'; const bad4 = [];
  p.on('response', r => { if (r.status() >= 400 && !/favicon/.test(r.url())) bad4.push(`${cur}: ${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/, '').split('?')[0]}`); }); p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://127.0.0.1:8032/'); await p.fill('#login-username', U); await p.fill('#login-password', PW); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(4000);
  await p.evaluate(() => {
    window.__shift = 0; window.__src = [];
    const name = n => !n || !n.tagName ? '?' : n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + (n.className && typeof n.className === 'string' ? '.' + n.className.trim().split(/\s+/).slice(0, 2).join('.') : '') + (n.id ? '' : ' "' + (n.textContent || '').trim().slice(0, 25) + '"');
    new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__shift += e.value; for (const s of e.sources || []) window.__src.push(`${name(s.node)} y${Math.round(s.previousRect.y)}->${Math.round(s.currentRect.y)} h${Math.round(s.previousRect.height)}->${Math.round(s.currentRect.height)}`); } }).observe({ type: 'layout-shift', buffered: false });
    window.__mut = Date.now();
    new MutationObserver(() => { window.__mut = Date.now(); }).observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
  });
  const plan = await p.evaluate(() => Object.values(ALL_PAGES).filter(pg => (pg.screens || []).some(s => pgAllowed(s)) || pg.tabs.some(t => pgTabOk(t)))
    .map(pg => ({ key: pg.key, tabs: pg.tabs.filter(t => pgTabOk(t)).map(t => ({ id: t.id, subs: t.subs.filter(s => pgHas(s.right)).map(s => s.id) })) })));
  const snap = () => p.evaluate(() => {
    const out = {};
    document.querySelectorAll('.pg-tab, .pg-subtab, .pg-side .pg-item, .screen.active button, .screen.active h2, #screen-title, .screen.active .exp-btns').forEach((el, i) => {
      if (!el.offsetParent) return;
      const r = el.getBoundingClientRect(); if (r.bottom < 0 || r.top > innerHeight) return;
      let key = (el.id || el.dataset.tab || el.dataset.sub || el.dataset.page || el.getAttribute('onclick') || el.textContent.trim().slice(0, 30)) + '#' + el.tagName;
      let n = 1; while (out[key + (n > 1 ? '~' + n : '')]) n++; if (n > 1) key += '~' + n;
      out[key] = [Math.round(r.left), Math.round(r.top), Math.round(r.width), el.tagName === 'H2' ? 1 : 0];
    });
    return out;
  });
  const rows = [];
  const measure = async (label, act) => {
    cur = label;
    await p.evaluate(() => { window.__shift = 0; window.__src = []; });
    const t0 = Date.now();
    await act();
    await p.waitForTimeout(60);
    const first = await snap();
    // settle: no DOM change for 400ms (cap 8s)
    let settle = 0;
    for (let i = 0; i < 80; i++) { await p.waitForTimeout(100); const quiet = await p.evaluate(() => Date.now() - window.__mut); if (quiet > 400) { settle = Date.now() - t0 - quiet; break; } }
    const last = await snap();
    const moved = Object.keys(first).filter(k => last[k] && (Math.abs(first[k][0] - last[k][0]) > 3 || Math.abs(first[k][1] - last[k][1]) > 3 || (!first[k][3] && Math.abs(first[k][2] - last[k][2]) > 3)))
      .map(k => `${k.slice(0, 50)} ${first[k]}->${last[k]}`);
    const shift = await p.evaluate(() => Math.round(window.__shift * 1000) / 1000);
    const src = await p.evaluate(() => [...new Set(window.__src)].slice(0, 3));
    const shown = await p.evaluate(() => [...document.querySelectorAll('.screen.active .status-msg, .screen.active .empty-note, .screen.active td')]
      .filter(e => e.offsetParent && !e.closest('.act-grid') && (/(could not|not allowed|don't have access|no access|refused|error|failed|\[object)/i.test(e.textContent) || /\b(undefined|NaN)\b/.test(e.textContent))).map(e => e.textContent.trim().slice(0, 90)));
    if (shown.length) bad4.push(`${label}: on screen "${shown[0]}"`);
    rows.push({ label, settle, shift, moved, src });
    if (shift > 0.02 || moved.length || settle > 1500) await p.screenshot({ path: `/tmp/claude-0/shots/jank/${U}${PHONE ? '-phone' : ''}-${label.replace(/[^a-z0-9]+/gi, '_')}.png` });
  };
  for (const pg of plan) {
    const press = sel => PHONE ? p.tap(sel) : p.click(sel);
    await measure(`${pg.key}`, () => press(`.pg-side .pg-item[data-page="${pg.key}"]`));
    for (const t of pg.tabs) {
      if (pg.tabs.length > 1) await measure(`${pg.key}>${t.id}`, () => press(`#pg-tabs .pg-tab[data-tab="${t.id}"]`));
      for (const s of t.subs) await measure(`${pg.key}>${t.id}>${s}`, async () => { if (await p.evaluate(id => !PG_TAB || PG_TAB.id !== id, t.id)) { await press(`#pg-tabs .pg-tab[data-tab="${t.id}"]`); await p.waitForTimeout(800); } await press(`#pg-sub .pg-subtab[data-sub="${s}"]`); });
    }
  }
  let bad = 0;
  for (const r of rows) {
    const flag = r.shift > 0.02 || r.moved.length || r.settle > (process.env.SLOW ? 2500 : 1500);
    if (flag) bad++;
    console.log(`${flag ? 'JANK' : 'ok  '} ${r.label.padEnd(34)} settle ${String(r.settle).padStart(5)}ms  shift ${r.shift}${r.moved.length ? '  moved: ' + r.moved.slice(0, 4).join(' | ') : ''}${flag && r.src.length ? '\n        shifted: ' + r.src.join(' || ') : ''}`);
  }
  console.log(errs.length ? 'SCRIPT ERRORS: ' + errs.join(' / ') : 'no script errors');
  console.log(bad4.length ? 'REFUSED / ERRORS:\n  ' + [...new Set(bad4)].join('\n  ') : 'no refused calls, no error text');
  console.log(`${bad} of ${rows.length} screens jumpy or slow`);
  await b.close();
})();
