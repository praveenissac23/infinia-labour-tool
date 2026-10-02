// Opening each page fresh (typed address / refresh), the way it happens
// many times a day: how much the screen jumps while it builds itself, and
// how long until it is still. Live-like network (180ms each way).
//   node tests/first_load_audit.js [user] [pass] [phone]
const { chromium, devices } = require('playwright');
const U = process.argv[2] || 'admin', PW = process.argv[3] || 'changeme123', PHONE = process.argv[4] === 'phone';
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext(PHONE ? { ...devices['iPhone 13'] } : { viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => {
    window.__shift = 0; window.__src = [];
    const name = n => !n || !n.tagName ? '?' : n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + (n.className && typeof n.className === 'string' ? '.' + n.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
    new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__shift += e.value; for (const s of e.sources || []) window.__src.push(`t${Math.round(e.startTime)} ${name(s.node)} y${Math.round(s.previousRect.y)}->${Math.round(s.currentRect.y)} h${Math.round(s.previousRect.height)}->${Math.round(s.currentRect.height)}`); } }).observe({ type: 'layout-shift', buffered: true });
  });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  const cdp = await ctx.newCDPSession(p); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 180, downloadThroughput: 4 * 1024 * 1024 / 8, uploadThroughput: 1024 * 1024 / 8 });
  await p.goto('http://127.0.0.1:8032/'); await p.fill('#login-username', U); await p.fill('#login-password', PW); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(5000);
  const pages = await p.evaluate(() => Object.keys(ALL_PAGES).filter(k => (ALL_PAGES[k].screens || []).some(s => pgAllowed(s))));
  let bad = 0;
  for (const k of pages) {
    const t0 = Date.now();
    await p.goto(`http://127.0.0.1:8032/?p=${k}`); await p.waitForTimeout(4500);
    const r = await p.evaluate(() => ({ shift: Math.round(window.__shift * 1000) / 1000, src: [...new Set(window.__src)].slice(0, 4), screen: (document.querySelector('.screen.active') || {}).id }));
    const flag = r.shift > 0.05; if (flag) bad++;
    console.log(`${flag ? 'JUMP' : 'ok  '} ${k.padEnd(12)} shift ${r.shift}  (${r.screen})${flag ? '\n        ' + r.src.join(' || ') : ''}`);
    if (flag) await p.screenshot({ path: `/tmp/claude-0/shots/jank/load-${U}-${k}${PHONE ? '-phone' : ''}.png` });
  }
  console.log(errs.length ? 'SCRIPT ERRORS: ' + errs.join(' / ') : 'no script errors');
  console.log(`${bad} of ${pages.length} pages jump while opening`);
  await b.close();
})();
