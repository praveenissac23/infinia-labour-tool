// Opening Staff (menu) and Settings > Access, frame by frame: they open in
// place inside the app - the page never reloads, the sign-in box never
// shows (in the app or the frame), the frame never shows its own menu, and
// the screen is on the first frame after the click.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/portal/';
const INIT = `
  window.__f = [];
  (function tick() {
    try {
      const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
      const login = document.getElementById('login') || document.getElementById('login-screen');
      const side = document.querySelector('.sidebar');
      const scr = [...document.querySelectorAll('.screen.active')].map(e => e.id);
      window.__f.push({ t: Math.round(performance.now()), login: vis(login), side: vis(side), scr, path: location.pathname.split('/').pop() });
    } catch (e) {}
    requestAnimationFrame(tick);
  })();`;
(async () => {
  const b = await chromium.launch(); let bad = 0;
  for (const [user, pw, pages] of [['admin', 'changeme123', ['people', 'access']], ['chief', 'chief12345', ['people']], ['assistant', 'asst12345', ['people']]]) {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); await ctx.addInitScript(INIT);
    const p = await ctx.newPage();
    await p.goto(BASE + 'store.html'); await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin(); 0'); await p.waitForTimeout(3500);
    for (const pg of pages) {
      const fid = pg === 'people' ? 'pg-staff-frame' : 'pg-access-frame';
      if (pg === 'access') { await p.click('.pg-side .pg-item[data-page="settings"]'); await p.waitForTimeout(800); }
      await p.evaluate('window.__f = []; window.__same = 1; window.__tc = 0; document.addEventListener("click", () => { if (!window.__tc) window.__tc = performance.now(); }, true)');
      if (pg === 'people') await p.click('.pg-side .pg-item[data-page="people"]');
      else await p.click('#pg-tabs .pg-tab[data-tab="access"]');
      await p.waitForTimeout(3000);
      const same = await p.evaluate('window.__same === 1'); const loads = same ? [] : ['reloaded'];
      const tc = await p.evaluate('window.__tc');
      const top = (await p.evaluate('window.__f')).filter(x => x.t >= tc);
      const want = pg === 'people' ? 'screen-pgstaff' : 'screen-pgaccess';
      const firstOn = top.findIndex(x => x.scr.includes(want));
      const inner = await p.frameLocator('#' + fid).locator('body').evaluate(() => window.__f).catch(() => []);
      const frameShown = await p.frameLocator('#' + fid).locator('#shell').isVisible().catch(() => false);
      const tLogin = top.filter(x => x.login).length, iLogin = inner.filter(x => x.login).length, iSide = inner.filter(x => x.side).length;
      const ok = loads.length === 0 && tLogin === 0 && iLogin === 0 && iSide === 0 && firstOn >= 0 && firstOn <= 2 && frameShown;
      if (!ok) bad++;
      console.log(`${ok ? 'PASS' : 'FAIL'} ${user}: ${pg} - reloads ${loads.length}, screen on frame ${firstOn}, sign-in box app ${tLogin} / frame ${iLogin}, frame menu ${iSide}, content shown ${frameShown}`);
      await p.click('.pg-side .pg-item[data-page="dashboard"]'); await p.waitForTimeout(800);
    }
    await ctx.close();
  }
  console.log(bad ? `${bad} FAILED` : 'STAFF AND ACCESS OPEN IN PLACE WITHOUT A FLASH');
  await b.close();
})();
