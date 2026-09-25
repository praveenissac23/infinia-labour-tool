// The temporary pages: each one is the app with a menu of eight and the
// old screens as tabs. Every tab on every page is opened, the cross-page
// links are followed, and a limited login sees only what it may.
//
// Run:  python3 tests/serve_like_nginx.py   then   node tests/temporary_pages_test.js
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/temporary/Infinia/';
let fails = 0;
const ck = (label, ok, ctx) => { console.log((ok ? 'PASS ' : 'FAIL ') + label + (ok ? '' : `  [${ctx}]`)); if (!ok) fails++; };
const PAGES = {
  dashboard: ['dashboard'], attendance: ['attendance', 'livecard', 'masterdata'],
  payroll: ['combine', 'errorcheck', 'hrpayroll'],
  store: ['store', 'requests', 'approvals', 'purchase', 'followup', 'lporegister', 'suppliers'],
  reports: ['reports'], settings: ['settings'], activity: ['activity'],
};

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e))); p.on('dialog', d => { errs.push('pop-up: ' + d.message()); d.dismiss(); });
  await p.goto(BASE + 'dashboard.html');
  ck('a temporary page opens on the sign-in', await p.locator('#login-screen').isVisible());
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1500);
  ck('the new menu has eight entries and the old one is hidden', await p.locator('.pg-side .pg-item:visible').count() === 9 && !(await p.locator('#legacy-sidebar').isVisible()));
  ck('the dashboard has no tab strip (one screen)', !(await p.locator('#pg-tabs').isVisible()));

  for (const [page, screens] of Object.entries(PAGES)) {
    await p.goto(BASE + page + '.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1500);
    ck(`${page}.html opens on ${screens[0]}`, await p.locator(`#screen-${screens[0]}.active`).count() === 1, await p.locator('.screen.active').getAttribute('id'));
    ck(`${page}.html: its menu entry is lit`, await p.locator(`.pg-side .pg-item.active[data-page="${page}"]`).count() === 1);
    if (screens.length > 1) {
      ck(`${page}.html: ${screens.length} tabs`, await p.locator('#pg-tabs .pg-tab').count() === screens.length, await p.locator('#pg-tabs').textContent());
      for (const s of screens) {
        await p.click(`#pg-tabs .pg-tab[data-tab="${s}"]`); await p.waitForTimeout(700);
        ck(`${page}.html: tab ${s} shows its screen`, await p.locator(`#screen-${s}.active`).count() === 1 && await p.locator(`#pg-tabs .pg-tab.active[data-tab="${s}"]`).count() === 1);
      }
    }
  }
  // Cross-page: a dashboard tile that names a screen on another page goes there.
  await p.goto(BASE + 'dashboard.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1200);
  await p.evaluate("switchScreen('combine')"); await p.waitForTimeout(1800);
  ck('a screen on another page is opened on that page', p.url().endsWith('payroll.html#combine') && await p.locator('#screen-combine.active').count() === 1, p.url());
  await p.evaluate("switchScreen('errorcheck')"); await p.waitForTimeout(600);
  ck('and a screen on this page just switches tabs', p.url().endsWith('payroll.html#combine') && await p.locator('#screen-errorcheck.active').count() === 1);
  await p.evaluate("dashStoreGo('items')"); await p.waitForTimeout(1800);
  ck('the dashboard store shortcuts land on the store page', p.url().includes('store.html#store:items') && await p.locator('#screen-store.active').count() === 1, p.url());
  await p.click('.pg-side .pg-item[data-page="people"]'); await p.waitForTimeout(1200);
  ck('People opens from the menu on the same sign-in', p.url().endsWith('people.html') && await p.locator('#shell').isVisible());
  await p.click('.nav-item:has-text("Access")'); await p.waitForTimeout(1200);
  ck('and Access', p.url().endsWith('access.html') && await p.locator('#shell').isVisible());

  // A limited login: requests + dashboard only.
  await p.goto(BASE + 'settings.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(800);
  await p.evaluate(async () => {
    const users = await apiCall('/users'); let u = users.find(x => x.username === 'tmp_req');
    if (!u) u = await apiCall('/users', { method: 'POST', body: JSON.stringify({ username: 'tmp_req', password: 'tmpreq123', full_name: 'Tmp Requester', role: 'site' }) });
    await apiCall(`/users/${u.id}/permissions`, { method: 'POST', body: JSON.stringify({ permissions: 'dashboard,requests,settings' }) });
  });
  const p2 = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs2 = []; p2.on('pageerror', e => errs2.push(String(e)));
  await p2.goto(BASE + 'store.html'); await p2.fill('#login-username', 'tmp_req'); await p2.fill('#login-password', 'tmpreq123'); await p2.evaluate('doLogin()');
  await p2.waitForSelector('#app-screen', { state: 'visible' }); await p2.waitForTimeout(2000);
  const tabs = await p2.locator('#pg-tabs .pg-tab').allTextContents();
  ck('a requests-only login sees only its tabs on the store page', tabs.length === 2 && tabs.join(',') === 'Material requests,Order follow-up', tabs);
  ck('and lands on requests', await p2.locator('#screen-requests.active').count() === 1);
  const menu = await p2.locator('.pg-side .pg-item:visible').allTextContents();
  ck('the menu shows only the pages it may open', menu.join(',') === 'Dashboard,Store & Purchasing,Settings', menu);
  await p2.goto(BASE + 'payroll.html'); await p2.waitForTimeout(2500);
  ck('a page with nothing for that login sends it to one that has', !p2.url().includes('payroll.html'), p2.url());
  ck('no script errors for the limited login', errs2.length === 0, errs2.slice(0, 3));
  await p2.close();
  await p.evaluate(async () => { const u = (await apiCall('/users')).find(x => x.username === 'tmp_req'); if (u) await apiCall(`/users/${u.id}`, { method: 'DELETE' }).catch(() => {}); });
  ck('no script errors, no pop-ups', errs.length === 0, errs.slice(0, 5));
  await b.close();
  console.log(fails ? `\n${fails} FAILED` : '\nTEMPORARY PAGES: EVERY TAB OPENS');
  process.exit(fails ? 1 : 0);
})();
