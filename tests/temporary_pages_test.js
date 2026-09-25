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
  reports: ['labour', 'office', 'people', 'storerep', 'builder'], settings: ['general', 'companies', 'sites', 'logins', 'backup'], activity: ['activity'],
};
const SCREEN_OF = { general: 'settings', companies: 'settings', sites: 'settings', logins: 'settings', backup: 'settings', labour: 'pgreports', office: 'pgreports', people: 'pgreports', storerep: 'pgreports', builder: 'reports' };

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
    await p.goto(BASE + (page === 'reports' ? 'reporting' : page) + '.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1500);
    ck(`${page}.html opens on ${screens[0]}`, await p.locator(`#screen-${SCREEN_OF[screens[0]] || screens[0]}.active`).count() === 1, await p.locator('.screen.active').getAttribute('id'));
    ck(`${page}.html: its menu entry is lit`, await p.locator(`.pg-side .pg-item.active[data-page="${page}"]`).count() === 1);
    if (screens.length > 1) {
      ck(`${page}.html: ${screens.length} tabs`, await p.locator('#pg-tabs .pg-tab').count() === screens.length, await p.locator('#pg-tabs').textContent());
      for (const s of screens) {
        await p.click(`#pg-tabs .pg-tab[data-tab="${s}"]`); await p.waitForTimeout(700);
        ck(`${page}.html: tab ${s} shows its screen`, await p.locator(`#screen-${SCREEN_OF[s] || s}.active`).count() === 1 && await p.locator(`#pg-tabs .pg-tab.active[data-tab="${s}"]`).count() === 1);
        if (SCREEN_OF[s] === 'settings') {
          const shown = await p.locator('#screen-settings > .card:visible, #screen-settings > div[id]:visible').count();
          const want = { general: 4, companies: 1, sites: 1, logins: 2, backup: 1 }[s];
          ck(`${page}.html: ${s} shows only its part (${shown})`, shown === want, shown);
        }
        if (SCREEN_OF[s] === 'pgreports') {
          const shown = await p.locator('#screen-pgreports > .card:visible').count();
          ck(`${page}.html: ${s} shows one report list`, shown === 1, shown);
        }
      }
    }
  }
  // The reports hub lists every report with working buttons.
  await p.goto(BASE + 'reporting.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1800);
  ck('the reports page opens on Labour, one section at a time', await p.locator('#screen-pgreports.active').count() === 1 && await p.locator('#screen-pgreports .card:visible').count() === 1);
  await p.click('#pg-tabs .pg-tab[data-tab="office"]'); await p.waitForTimeout(500);
  ck('the office statement picker lists the saved cycles', await p.locator('#pgrep-run option').count() >= 1);
  const opened = [];
  ctx.on('page', pg => opened.push(pg));
  let hubBtns = 0;
  for (const t of ['office', 'people']) {
    await p.click(`#pg-tabs .pg-tab[data-tab="${t}"]`); await p.waitForTimeout(500);
    const n = await p.locator('#screen-pgreports button:visible:has-text("Preview")').count(); hubBtns += n;
    for (let i = 0; i < n; i++) { await p.locator('#screen-pgreports button:visible:has-text("Preview")').nth(i).click(); await p.waitForTimeout(500); }
  }
  await p.waitForTimeout(1500);
  ck(`every Preview on the hub opened a page (${hubBtns})`, opened.length === hubBtns, opened.length);
  for (const pg of opened) { await pg.waitForLoadState().catch(() => {}); const h = await pg.content().catch(() => '{"detail"'); ck(`hub preview: ${(pg.url().split('/export/')[1] || '').split('?')[0]}`, !/\{"detail"|Internal Server Error/.test(h) && h.length > 500); await pg.close().catch(() => {}); }
  opened.length = 0;
  await p.click('#pg-tabs .pg-tab[data-tab="labour"]'); await p.waitForTimeout(400);
  await p.click('#screen-pgreports button:visible:has-text("Open")'); await p.waitForTimeout(800);
  ck('an Open button on the hub goes to that screen', await p.locator('#screen-reports.active').count() === 1);
  // A login with labour reports but no office salary right sees no office tab anywhere.
  await p.evaluate(async () => {
    const users = await apiCall('/users'); let u = users.find(x => x.username === 'tmp_asst');
    if (!u) u = await apiCall('/users', { method: 'POST', body: JSON.stringify({ username: 'tmp_asst', password: 'tmpasst123', full_name: 'Tmp Assistant', role: 'office' }) });
    await apiCall(`/users/${u.id}/permissions`, { method: 'POST', body: JSON.stringify({ permissions: 'dashboard,reports,combine,people_labour,settings' }) });
  });
  const pa = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await pa.goto(BASE + 'reporting.html'); await pa.fill('#login-username', 'tmp_asst'); await pa.fill('#login-password', 'tmpasst123'); await pa.evaluate('doLogin()');
  await pa.waitForSelector('#app-screen', { state: 'visible' }); await pa.waitForTimeout(2000);
  const atabs = await pa.locator('#pg-tabs .pg-tab').allTextContents();
  ck('an assistant without the office right gets no Office payroll tab on Reports', atabs.join(',') === 'Labour,People,Report builder', atabs);
  await pa.goto(BASE + 'payroll.html'); await pa.waitForSelector('#app-screen', { state: 'visible' }); await pa.waitForTimeout(1500);
  const ptabs = await pa.locator('#pg-tabs .pg-tab').allTextContents();
  ck('nor on Payroll', !ptabs.includes('Office HR & Payroll') && await pa.locator('#screen-combine.active').count() === 1, ptabs);
  await pa.goto(BASE + 'people.html'); await pa.waitForSelector('#shell', { state: 'visible' }).catch(() => {}); await pa.waitForTimeout(1500);
  const gt = await pa.locator('#tabs .tab').allTextContents();
  ck('and on People only the labour register', gt.length === 2 && gt[0].startsWith('Labour'), gt);
  await pa.close();
  await p.evaluate(async () => { const u = (await apiCall('/users')).find(x => x.username === 'tmp_asst'); if (u) await apiCall(`/users/${u.id}`, { method: 'DELETE' }).catch(() => {}); });
  // No flicker: a resumed page never shows the sign-in box or the dashboard before its own screen.
  const seen = new Set();
  const tok = await p.evaluate(() => sessionStorage.getItem('infinia_token'));
  const p3 = await ctx.newPage();
  await p3.addInitScript(t => sessionStorage.setItem('infinia_token', t), tok);
  await p3.goto(BASE + 'payroll.html#hrpayroll');
  for (let i = 0; i < 25; i++) {
    seen.add(await p3.evaluate(() => { const vis = el => !!(el && el.getClientRects().length); const l = document.getElementById('login-screen'); const a = [...document.querySelectorAll('.screen')].find(vis); return (vis(l) ? 'login' : '') + ':' + (a ? a.id : ''); }).catch(() => 'nav'));
    await p3.waitForTimeout(60);
  }
  ck('a resumed page shows only its own screen from the first paint', [...seen].every(v => v === 'nav' || v === ':screen-hrpayroll' || v === ':'), [...seen]);
  await p3.close();

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
  ck('the menu shows only the pages it may open', menu.join(',') === 'Dashboard,Store & Purchasing,Reports,Settings', menu);
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
