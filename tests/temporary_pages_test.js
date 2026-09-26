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
  payroll: ['labourpay', 'hrpayroll'],
  store: ['store', 'rentals', 'requests', 'purchasing'],
  reports: ['labour', 'office', 'people', 'storerep'], settings: ['general', 'companies', 'logins', 'access', 'activity'],
};
const SCREEN_OF = { labourpay: 'combine', rentals: 'store', purchasing: 'purchase', general: 'settings', companies: 'settings', logins: 'settings', labour: 'reports', office: 'hrpayroll', people: 'pgreports', storerep: 'store', activity: 'activity', access: 'settings' };

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e))); p.on('dialog', d => { errs.push('pop-up: ' + d.message()); d.dismiss(); });
  await p.goto(BASE + 'dashboard.html');
  ck('a temporary page opens on the sign-in', await p.locator('#login-screen').isVisible());
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1500);
  ck('the new menu has seven entries and the old one is hidden', await p.locator('.pg-side .pg-item:visible').count() === 7 && !(await p.locator('#legacy-sidebar').isVisible()));
  ck('the dashboard has no tab strip (one screen)', !(await p.locator('#pg-tabs').isVisible()));

  for (const [page, screens] of Object.entries(PAGES)) {
    await p.goto(BASE + (page === 'reports' ? 'reporting' : page) + '.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1500);
    ck(`${page}.html opens on ${screens[0]}`, await p.locator(`#screen-${SCREEN_OF[screens[0]] || screens[0]}.active`).count() === 1, await p.locator('.screen.active').getAttribute('id'));
    ck(`${page}.html: its menu entry is lit`, await p.locator(`.pg-side .pg-item.active[data-page="${page}"]`).count() === 1);
    if (screens.length > 1) {
      ck(`${page}.html: ${screens.length} tabs`, await p.locator('#pg-tabs .pg-tab').count() === screens.length, await p.locator('#pg-tabs').textContent());
      for (const s of screens) {
        if (s === 'access') continue;   // goes to access.html - checked below
        await p.click(`#pg-tabs .pg-tab[data-tab="${s}"]`); await p.waitForTimeout(700);
        ck(`${page}.html: tab ${s} shows its screen`, await p.locator(`#screen-${SCREEN_OF[s] || s}.active`).count() === 1 && await p.locator(`#pg-tabs .pg-tab.active[data-tab="${s}"]`).count() === 1);
        if (SCREEN_OF[s] === 'settings') {
          const shown = await p.locator('#screen-settings > .card:visible, #screen-settings > div[id]:visible').count();
          const want = { general: 5, companies: 2, logins: 2 }[s];
          ck(`${page}.html: ${s} shows only its part (${shown})`, shown === want, shown);
        }
        if (SCREEN_OF[s] === 'pgreports') {
          const shown = await p.locator('#pg-sub .pg-subtab').count();
          ck(`${page}.html: ${s} shows its sub-tabs (${shown})`, shown >= 2, shown);
        }
      }
    }
  }
  // A company added under Settings is a choice on every company dropdown, straight away.
  await p.evaluate(async () => apiCall('/employees/companies', { method: 'POST', body: JSON.stringify({ name: 'DROPDOWN CHECK LLC', short_name: 'DropCo', code_prefix: 'DC' }) }).catch(() => {}));
  for (const [pg, tab, id] of [['reporting', '', 'report-company'], ['attendance', 'masterdata', 'md-emp-company'], ['payroll', 'hrpayroll', 'hr-run-company'], ['people', '', 'f-company']]) {
    await p.goto(BASE + pg + '.html' + (tab ? '#' + tab : '')); await p.waitForTimeout(2500);
    const opts = await p.locator('#' + id + ' option').allTextContents();
    ck(`${pg} ${id} lists the new company`, opts.includes('DropCo'), opts);
  }
  // The reports page: tabs inside tabs, the working screen underneath.
  await p.goto(BASE + 'reporting.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1800);
  ck('the reports page opens on Labour › Cycle report builder', await p.locator('#screen-reports.active').count() === 1 && (await p.locator('#pg-sub .pg-subtab.active').textContent()) === 'Cycle report builder');
  const EXPECT = { office: '#screen-hrpayroll', people: '#screen-pgreports', storerep: '#screen-store' };
  for (const t of ['office', 'people', 'storerep']) {
    await p.click(`#pg-tabs .pg-tab[data-tab="${t}"]`); await p.waitForTimeout(900);
    const subs = await p.locator('#pg-sub .pg-subtab').allTextContents();
    ck(`${t}: has sub-tabs (${subs.length})`, subs.length >= 2, subs);
    for (let i = 0; i < subs.length; i++) {
      await p.locator('#pg-sub .pg-subtab').nth(i).click(); await p.waitForTimeout(1200);
      ck(`${t} › ${subs[i]} is the active sub-tab`, (await p.locator('#pg-sub .pg-subtab.active').textContent()) === subs[i]);
      const activeId = await p.evaluate("document.querySelector('.screen.active') && document.querySelector('.screen.active').id");
      if (t === 'office') {
        ck(`office › ${subs[i]} shows one HR pane, without the screen's own tab row`, activeId === 'screen-hrpayroll' && await p.locator('.hr-pane:visible').count() === 1 && await p.locator('.hr-tabs:visible').count() === 0, activeId);
      } else if (t === 'people') {
        await p.waitForFunction(() => !/Loading/.test(document.getElementById('pg-people-body').textContent), null, { timeout: 15000 }).catch(() => {});
        const rows = await p.locator('#pg-people-body tr').count();
        ck(`people › ${subs[i]} lists on screen (${rows} rows)`, activeId === 'screen-pgreports' && rows >= 1, rows);
      } else if (['LPO register', 'Order follow-up', 'Suppliers'].includes(subs[i])) {
        ck(`store › ${subs[i]} opens its screen`, ['screen-lporegister', 'screen-followup', 'screen-suppliers'].includes(activeId), activeId);
      } else {
        ck(`store › ${subs[i]} shows the report panel with its buttons`, activeId === 'screen-store' && await p.locator('#store-report-result:visible').count() === 1 && await p.locator('#store-report-result button:visible:has-text("Preview")').count() === 1, activeId);
      }
    }
  }
  await p.click('#pg-tabs .pg-tab[data-tab="people"]'); await p.waitForTimeout(900);
  await p.click('#pg-opt-group button[data-v="office"]'); await p.waitForTimeout(1200);
  ck('the group switch reloads the People list', (await p.locator('#pg-people-body').innerText()).includes('IC0'));
  await p.click('#pg-tabs .pg-tab[data-tab="labour"]'); await p.waitForTimeout(400);
  await p.locator('#pg-sub .pg-subtab', { hasText: 'Salary cards' }).click(); await p.waitForTimeout(800);
  ck('a Labour sub-tab opens that screen under the same tab', await p.locator('#screen-combine.active').count() === 1 && (await p.locator('#pg-tabs .pg-tab.active').textContent()) === 'Labour');
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
  ck('an assistant without the office right gets no Office payroll tab on Reports', atabs.join(',') === 'Labour,Staff', atabs);
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
  ck('the dashboard store shortcuts land on the store page', p.url().includes('store.html#items') && await p.locator('#screen-store.active').count() === 1 && await p.locator('#store-items').isVisible(), p.url());
  await p.click('.pg-side .pg-item[data-page="people"]'); await p.waitForTimeout(1200);
  ck('People opens from the menu on the same sign-in', p.url().endsWith('people.html') && await p.locator('#shell').isVisible());
  await p.goto(BASE + 'settings.html'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1200);
  ck('Settings has an Access tab for the admin', await p.locator('#pg-tabs .pg-tab[data-tab="access"]').count() === 1);
  await p.click('#pg-tabs .pg-tab[data-tab="access"]'); await p.waitForTimeout(1500);
  ck('and it opens the Access page under Settings', p.url().endsWith('access.html') && await p.locator('#shell').isVisible() && await p.locator('.tab.active:has-text("Access")').count() === 1);

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
  ck('a requests-only login sees only its tabs on the store page', tabs.length === 0 || tabs.join(',') === 'Requests', tabs);
  const rsubs = await p2.locator('#pg-sub .pg-subtab').allTextContents();
  ck('and only its sub-tabs', rsubs.join(',') === 'Material requests,Order follow-up', rsubs);
  ck('and lands on requests', await p2.locator('#screen-requests.active').count() === 1);
  const menu = await p2.locator('.pg-side .pg-item:visible').allTextContents();
  ck('the menu shows only the pages it may open', menu.join(',') === 'Dashboard,Store & Purchasing,Reports,Settings', menu);
  // Moving between pages, the menu never shows an entry this login may not open - not even for a frame.
  const seenMenu = new Set();
  await p2.goto(BASE + 'settings.html');
  for (let i = 0; i < 30; i++) { seenMenu.add(await p2.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item[data-page]')].filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden').map(e => e.dataset.page).join(',')).catch(() => 'nav')); await p2.waitForTimeout(50); }
  ck('the menu never flashes entries the login lacks', [...seenMenu].every(v => v === 'nav' || v === '' || v === 'dashboard,store,reports,settings'), [...seenMenu]);
  await p2.goto(BASE + 'payroll.html'); await p2.waitForTimeout(2500);
  ck('a page with nothing for that login sends it to one that has', !p2.url().includes('payroll.html'), p2.url());
  ck('no script errors for the limited login', errs2.length === 0, errs2.slice(0, 3));
  await p2.goto(BASE + 'settings.html'); await p2.waitForSelector('#app-screen', { state: 'visible' }); await p2.waitForTimeout(1500);
  const stabs = await p2.locator('#pg-tabs .pg-tab').allTextContents();
  ck('a non-admin login with Settings gets no Access tab', !stabs.includes('Access'), stabs);
  const rr = await p2.evaluate(async () => { try { await apiCall('/permissions/roles'); return 200; } catch (e) { return e.status; } });
  ck('and the server refuses it the roles', rr === 403, rr);
  await p2.goto(BASE + 'access.html'); await p2.waitForTimeout(1800);
  ck('typing access.html sends a non-admin back to Settings, still signed in', p2.url().endsWith('settings.html') && await p2.evaluate("!!sessionStorage.getItem('infinia_token')"), p2.url());
  await p2.close();
  await p.evaluate(async () => { const u = (await apiCall('/users')).find(x => x.username === 'tmp_req'); if (u) await apiCall(`/users/${u.id}`, { method: 'DELETE' }).catch(() => {}); });
  ck('no script errors, no pop-ups', errs.length === 0, errs.slice(0, 5));
  await b.close();
  console.log(fails ? `\n${fails} FAILED` : '\nTEMPORARY PAGES: EVERY TAB OPENS');
  process.exit(fails ? 1 : 0);
})();
