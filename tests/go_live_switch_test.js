// Going live: app.infinia.ae keeps its address and opens the new app.
// Every page lives at the same address (/?p=<page>), old links of every
// kind land on the right page, a signed-in person stays signed in, the
// address never loops, the old app is still at /app-classic.html, and
// Back/Forward move between pages without reloading.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (name, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  const addr = () => { const u = new URL(p.url()); return u.pathname + u.search + u.hash; };
  const land = async (url) => { await p.goto(B + url); await p.waitForTimeout(1200); return addr(); };
  // signed out: every address shows the sign-in on the same address
  for (const [from, to] of [['/', '/'], ['/app.html', '/'], ['/?p=store', '/?p=store'], ['/?p=payroll#hrpayroll', '/?p=payroll#hrpayroll'],
                            ['/portal/store.html', '/?p=store'], ['/portal/reporting.html', '/?p=reports'],
                            ['/temporary/Infinia/payroll.html#hrpayroll', '/?p=payroll#hrpayroll'], ['/temporary/Infinia/access.html', '/?p=settings#access'],
                            ['/temporary/Infinia/', '/'], ['/some/old/bookmark', '/'], ['/?p=nonsense', '/']]) {
    const at = await land(from); ck(`${from}  ->  ${to}`, at === to, at);
  }
  ck('signed out, the sign-in box shows', await p.locator('#login-screen').isVisible());
  // sign in at app.infinia.ae
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1500);
  ck('signing in at app.infinia.ae opens the new app on the same address', addr() === '/' && await p.locator('.pg-side').isVisible() && await p.locator('#screen-dashboard.active').count() === 1, addr());
  const menu = await p.locator('.pg-side').textContent();
  ck('no TEMPORARY / classic entries in the menu', !/TEMPORARY|classic/i.test(menu), menu);
  // moving between pages: the address changes, the page does not reload
  await p.evaluate('window.__same = 1');
  for (const [pg, want, screen] of [['store', '/?p=store', 'store'], ['payroll', '/?p=payroll', 'combine'], ['reports', '/?p=reports', null], ['settings', '/?p=settings', 'settings'], ['people', '/?p=people', 'pgstaff'], ['dashboard', '/', 'dashboard']]) {
    await p.click(`.pg-side .pg-item[data-page="${pg}"]`); await p.waitForTimeout(700);
    const a = addr().split('#')[0];
    ck(`menu ${pg}: address ${want}${screen ? ', screen ' + screen : ''}, no reload`, a === want && await p.evaluate('window.__same === 1') && (!screen || await p.locator(`#screen-${screen}.active`).count() === 1), a);
  }
  await p.goBack(); await p.waitForTimeout(700);
  ck('Back returns to the previous page without reloading', addr().split('#')[0] === '/?p=people' && await p.evaluate('window.__same === 1'), addr());
  await p.goForward(); await p.waitForTimeout(700);
  ck('Forward goes on again', addr() === '/' && await p.locator('#screen-dashboard.active').count() === 1, addr());
  // reload keeps the page and the tab
  await p.goto(B + '/?p=payroll#hrpayroll'); await p.waitForTimeout(2500);
  ck('reloading /?p=payroll#hrpayroll opens that page and tab, still signed in', await p.locator('#screen-hrpayroll.active').count() === 1 && !(await p.locator('#login-screen').isVisible()), addr());
  // old bookmarks, signed in
  for (const [from, screen] of [['/app.html', 'dashboard'], ['/portal/store.html', 'store'], ['/temporary/Infinia/settings.html#logins', 'pglogins']]) {
    await p.goto(B + from); await p.waitForTimeout(2200);
    ck(`old link ${from} opens the right screen, signed in`, await p.locator(`#screen-${screen}.active`).count() === 1 && !(await p.locator('#login-screen').isVisible()), addr());
  }
  // no loop: one load per visit
  let navs = 0; p.on('framenavigated', f => { if (f === p.mainFrame()) navs++; });
  await p.goto(B + '/portal/payroll.html'); await p.waitForTimeout(2500);
  ck('an old link loads once - no redirect chain', navs <= 2, navs);
  // the old app is still there, whole
  await p.goto(B + '/app-classic.html'); await p.waitForTimeout(2500);
  ck('the old app still opens at /app-classic.html, signed in', await p.locator('#app-screen').isVisible() && await p.locator('.pg-side').count() === 0, addr());
  // Staff frame and exports are served from their own paths
  const st = await p.evaluate(async () => [(await fetch('/portal/people.html')).status, (await fetch('/portal/access.html')).status, (await fetch('/health')).status]);
  ck('Staff and Access pages and the API answer', st.every(x => x === 200), st);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'SAME ADDRESS, NEW APP - THE SWITCH IS CLEAN');
  await b.close(); process.exit(bad ? 1 : 0);
})();
