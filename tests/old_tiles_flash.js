// The old store tiles, the store's Back buttons and the HR screen's own tab
// row must never be drawn on the new pages - not for a single frame. Opens
// Store & Purchasing and Payroll from the menu, for admin and the store
// keeper, recording every animation frame from the first paint.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/temporary/Infinia/';
const INIT = `
  window.__bad = [];
  (function tick() {
    try {
      const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
      const found = [];
      document.querySelectorAll('#screen-store .store-tile').forEach(el => { if (vis(el)) found.push('store tile: ' + el.textContent.trim().slice(0, 20)); });
      document.querySelectorAll('#screen-store button[onclick="storeGo(\\'home\\')"]').forEach(el => { if (vis(el)) found.push('store Back button'); });
      document.querySelectorAll('#screen-hrpayroll .hr-tabs').forEach(el => { if (vis(el)) found.push('HR tab row'); });
      if (found.length) window.__bad.push(Math.round(performance.now()) + 'ms ' + found.join(', '));
    } catch (e) {}
    requestAnimationFrame(tick);
  })();`;
(async () => {
  const b = await chromium.launch(); let bad = 0;
  for (const [user, pw] of [['admin', 'changeme123'], ['keeper', 'keep12345']]) {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); await ctx.addInitScript(INIT);
    const p = await ctx.newPage();
    await p.goto(BASE + 'dashboard.html'); await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin(); 0'); await p.waitForTimeout(2500);
    for (const pg of ['store', 'payroll', 'reporting']) {
      const item = p.locator(`.pg-side .pg-item[data-page="${pg === 'reporting' ? 'reports' : pg}"]`);
      if (!(await item.isVisible())) continue;
      await item.click(); await p.waitForTimeout(3500);
      // and every tab and sub-tab on that page
      const tabs = await p.locator('#pg-tabs .pg-tab').count();
      for (let i = 0; i < tabs; i++) {
        await p.locator('#pg-tabs .pg-tab').nth(i).click(); await p.waitForTimeout(800);
        const subs = await p.locator('#pg-sub .pg-subtab').count();
        for (let k = 0; k < subs; k++) { await p.locator('#pg-sub .pg-subtab').nth(k).click(); await p.waitForTimeout(700); }
      }
      const frames = await p.evaluate('window.__bad'); await p.evaluate('window.__bad = []');
      const ok = frames.length === 0; if (!ok) bad++;
      console.log(`${ok ? 'PASS' : 'FAIL'} ${user}: ${pg} - no old tiles, Back buttons or HR tab row in any frame${ok ? '' : '   ' + frames.slice(0, 3).join(' | ')}`);
      await p.goto(BASE + 'dashboard.html'); await p.waitForTimeout(1500);
    }
    await ctx.close();
  }
  console.log(bad ? `${bad} FAILED` : 'NOTHING OLD IS EVER DRAWN');
  await b.close();
})();
