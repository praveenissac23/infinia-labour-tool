// How long a menu click takes to show the next page's data, on a normal
// and on a poor connection, and whether the page reloads (a reload is the
// white flash). Uses the menu the way a person does.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/temporary/Infinia/';
const READY = {
  store: () => document.querySelector('#home-stock-body tr') && !/Loading/.test(document.querySelector('#home-stock-body').textContent),
  attendance: () => document.querySelectorAll('#screen-attendance table tbody tr').length > 3,
  payroll: () => !!document.querySelector('#screen-combine.active, #screen-hrpayroll.active'),
  reports: () => !!document.querySelector('.screen.active'),
  settings: () => !!document.querySelector('#screen-settings.active'),
  dashboard: () => !!document.querySelector('#screen-dashboard.active'),
};
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); const p = await ctx.newPage();
  await p.goto(BASE + 'dashboard.html'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin(); 0'); await p.waitForTimeout(3000);
  for (const slow of [false, true]) {
    const cdp = await ctx.newCDPSession(p);
    await cdp.send('Network.emulateNetworkConditions', slow ? { offline: false, latency: 150, downloadThroughput: 1.5 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 } : { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    const out = [];
    for (const round of [1, 2]) {
      for (const pg of ['store', 'attendance', 'payroll', 'reports', 'settings', 'dashboard']) {
        await p.evaluate('window.__stay = 1'); const t0 = Date.now();
        await p.click(`.pg-side .pg-item[data-page="${pg}"]`);
        await p.waitForFunction(READY[pg], null, { timeout: 30000 }).catch(() => {});
        const reloaded = !(await p.evaluate('window.__stay === 1'));
        out.push(`${pg} ${Date.now() - t0}ms${reloaded ? ' (RELOADED)' : ''}`);
      }
    }
    console.log((slow ? 'POOR 1.5 Mbps/150ms: ' : 'NORMAL: ') + out.join(' · '));
  }
  await b.close();
})();
