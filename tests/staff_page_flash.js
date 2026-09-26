// Opening Staff (and Access) from the menu, frame by frame from the first
// paint: the sign-in box must never show for a signed-in user, the menu
// must never show entries the login lacks, and the page chrome must be
// there from the first frame.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/temporary/Infinia/';
const INIT = `
  window.__f = [];
  (function tick() {
    try {
      const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
      const login = document.getElementById('login') || document.getElementById('login-screen');
      const shell = document.getElementById('shell') || document.getElementById('app-screen');
      const menu = [...document.querySelectorAll('.sidebar .nav-item, .pg-side .pg-item')].filter(vis).map(e => e.textContent.trim());
      window.__f.push({ t: Math.round(performance.now()), login: vis(login), shell: vis(shell), blank: !vis(login) && !vis(shell), menu, path: location.pathname.split('/').pop() });
    } catch (e) {}
    requestAnimationFrame(tick);
  })();`;
(async () => {
  const b = await chromium.launch(); let bad = 0;
  for (const [user, pw, pages] of [['admin', 'changeme123', ['people', 'access']], ['chief', 'chief12345', ['people']], ['assistant', 'asst12345', ['people']]]) {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); await ctx.addInitScript(INIT);
    const p = await ctx.newPage();
    await p.goto(BASE + 'store.html'); await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin(); 0'); await p.waitForTimeout(3000);
    const finalMenu = await p.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item')].filter(e => e.style.display !== 'none').map(e => e.textContent.trim()));
    for (const pg of pages) {
      if (pg === 'people') await p.click('.pg-side .pg-item[data-page="people"]');
      else { await p.goto(BASE + 'settings.html'); await p.waitForTimeout(2000); await p.click('#pg-tabs .pg-tab[data-tab="access"]'); }
      await p.waitForTimeout(3000);
      const f = (await p.evaluate('window.__f')).filter(x => x.path === pg + '.html');
      const login = f.filter(x => x.login).length, blank = f.filter(x => x.blank).length;
      const stray = [...new Set(f.flatMap(x => x.menu).filter(m => !finalMenu.includes(m) && !['Access'].includes(m)))];
      const ok = f.length > 0 && login === 0 && blank <= 1 && stray.length === 0; if (!ok) bad++;
      console.log(`${ok ? 'PASS' : 'FAIL'} ${user}: ${pg}.html - ${f.length} frames, sign-in box in ${login}, blank in ${blank}, stray menu ${JSON.stringify(stray)}`);
      await p.goto(BASE + 'store.html'); await p.waitForTimeout(2500);
    }
    await ctx.close();
  }
  console.log(bad ? `${bad} FAILED` : 'STAFF AND ACCESS OPEN WITHOUT A FLASH');
  await b.close();
})();
