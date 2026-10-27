// Clicking through the menu as a person does: time until the next page shows its data, and how long the browser
// was frozen (long tasks), on a normal and on a slow connection. Live-size data: /tmp/claude-0/vol.db.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const READY = {
  dashboard: () => !!document.querySelector('#screen-dashboard.active'),
  store: () => document.querySelector('#home-stock-body tr') && !/Loading/.test(document.querySelector('#home-stock-body').textContent),
  attendance: () => document.querySelectorAll('#screen-attendance table tbody tr').length > 3,
  payroll: () => !!document.querySelector('#screen-combine.active, #screen-hrpayroll.active'),
  estimation: () => { const f = document.querySelector('.screen.active iframe'); try { return !!(f && f.contentDocument && f.contentDocument.querySelector('#app:not(.hide) .card, #app:not(.hide) table')); } catch (e) { return false; } },
  reports: () => !!document.querySelector('.screen.active'),
  accounts: () => !!document.querySelector('.screen.active'),
  settings: () => !!document.querySelector('#screen-settings.active'),
};
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  await p.addInitScript(() => { window.__lt = 0; try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt += e.duration; }).observe({ type: 'longtask', buffered: true }); } catch (e) {} });
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  for (const slow of [false, true]) {
    const cdp = await ctx.newCDPSession(p);
    await cdp.send('Network.emulateNetworkConditions', slow ? { offline: false, latency: 150, downloadThroughput: 1.5 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 } : { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    for (const round of [1, 2]) {
      const out = [];
      for (const pg of ['store', 'estimation', 'attendance', 'payroll', 'reports', 'accounts', 'settings', 'dashboard']) {
        await p.evaluate(() => { window.__lt = 0; }); const t0 = Date.now();
        await p.click(`.pg-side .pg-item[data-page="${pg}"]`).catch(() => {});
        await p.waitForFunction(READY[pg], null, { timeout: 30000, polling: 50 }).catch(() => {});
        const ms = Date.now() - t0, lt = Math.round(await p.evaluate(() => window.__lt));
        out.push(`${pg} ${ms}ms${lt > 50 ? ` (frozen ${lt}ms)` : ''}`);
      }
      console.log(`${slow ? 'SLOW 1.5 Mbps' : 'NORMAL'} round ${round}${round === 1 ? ' (first visit)' : ' (again)'}: ` + out.join(' · '));
    }
  }
  const n = await p.evaluate(() => document.getElementsByTagName('*').length);
  console.log('elements on the page at the end:', n);
  await b.close();
})();
