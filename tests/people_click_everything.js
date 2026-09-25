// The People and Access pages, every tab, section and button pressed.
//
// Run:  python3 tests/serve_like_nginx.py   (with a database that has people in it)
//       node tests/people_click_everything.js [password]
//
// Behind the nginx rule, like the other sweeps: a path the live server
// would not forward fails here first.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032';
const PASS = process.argv[2] || 'p';
let fails = 0;
const ck = (label, ok, ctx) => { console.log((ok ? 'PASS ' : 'FAIL ') + label + (ok ? '' : `  [${ctx}]`)); if (!ok) fails++; };

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [], http = [];
  p.on('pageerror', e => errs.push(String(e)));
  p.on('dialog', d => { errs.push('browser pop-up: ' + d.message()); d.dismiss(); });
  p.on('response', r => { if (r.status() >= 500) http.push(`${r.status()} ${r.url()}`); });

  // ---- The gate -------------------------------------------------------------
  await p.goto(BASE + '/temporary/Infinia/people.html');
  ck('the page is served at its temporary address', (await p.title()).includes('People'));
  ck('and shows a sign-in, nothing else', await p.locator('#login').isVisible() && !(await p.locator('#shell').isVisible()));
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'wrong'); await p.click('#login button'); await p.waitForTimeout(600);
  ck('a wrong password is refused in the page', (await p.locator('#login-error').textContent()).includes('Wrong'));
  await p.fill('#login-password', PASS); await p.click('#login button');
  await p.waitForSelector('#shell', { state: 'visible' }); await p.waitForTimeout(1500);
  ck('admin is in', await p.locator('#shell').isVisible());

  // ---- Register: every tab, every section --------------------------------------
  const tabs = await p.locator('#tabs .tab').allTextContents();
  ck('five register tabs', tabs.length === 5, tabs);
  let pressed = 0;
  const closeAll = async () => {
    for (const id of ['dlg-edit', 'dlg-new', 'dlg-doc', 'dlg-asset', 'dlg-loan', 'dlg-repay']) if (await p.locator('#' + id).isVisible()) await p.evaluate(`closeDlg('${id}')`);
    if (await p.locator('.ask').count()) await p.click('.ask [data-a="no"]');
  };
  const newPages = [];
  ctx.on('page', pg => newPages.push(pg));
  for (const tab of ['labour', 'office', 'local', 'household', 'left']) {
    await p.click(`#tabs .tab[data-tab="${tab}"]`); await p.waitForTimeout(900);
    const n = await p.locator('#list .person').count();
    ck(`${tab}: the tab opens (${n} listed)`, await p.locator(`#tabs .tab[data-tab="${tab}"].active`).count() === 1);
    if (!n) continue;
    ck(`${tab}: the first person's file opens by itself`, await p.locator('#file h2').count() === 1);
    for (const sec of ['identity', 'employment', 'pay', 'documents', 'leave', 'money', 'assets', 'history']) {
      await p.click(`#file .subtabs button[data-section="${sec}"]`); await p.waitForTimeout(250);
      ck(`${tab}: ${sec} section shows`, await p.locator(`#file .subtabs button[data-section="${sec}"].on`).count() === 1 && (await p.locator('#file').textContent()).length > 50);
      // Every button in the section, answered "Cancel" where it asks.
      const btns = await p.locator('#file button:visible').count();
      for (let i = 0; i < btns; i++) {
        const btn = p.locator('#file button:visible').nth(i);
        if (!(await btn.count())) break;
        const text = (await btn.textContent()).trim();
        if (/Remove/.test(text)) { await btn.click(); pressed++; await p.waitForTimeout(300); ck(`${tab}/${sec}: "${text}" asks in the page`, await p.locator('.ask').count() === 1); await closeAll(); continue; }
        await btn.click({ timeout: 3000 }).catch(() => errs.push(`${tab}/${sec}: "${text}" would not click`)); pressed++;
        await p.waitForTimeout(400); await closeAll();
      }
    }
  }
  ck('Print file opened a preview in a new tab', newPages.length > 0, newPages.length);
  for (const pg of newPages) { await pg.waitForLoadState().catch(() => {}); const t = await pg.title().catch(() => ''); const html = await pg.content().catch(() => '{"detail"'); ck(`preview page: ${t.slice(0, 50)}`, !/\{"detail"|Internal Server Error/.test(html) && html.length > 500, html.slice(0, 120)); await pg.close().catch(() => {}); }
  newPages.length = 0;

  // ---- Toolbar buttons --------------------------------------------------------------
  await p.click('#tabs .tab[data-tab="office"]'); await p.waitForTimeout(800);
  for (const text of ['Preview', 'Export to PDF', 'Export to Excel']) {
    await p.click(`#view-register .row button:has-text("${text}")`); pressed++; await p.waitForTimeout(700);
  }
  ck('register preview / PDF / Excel each opened a tab', newPages.length === 3, newPages.length);
  for (const pg of newPages) await pg.close().catch(() => {});
  newPages.length = 0;
  await p.fill('#f-q', 'zzzz-nobody'); await p.waitForTimeout(200);
  ck('search narrows the list', (await p.locator('#list').textContent()).includes('No one here'));
  await p.fill('#f-q', ''); await p.waitForTimeout(200);
  await p.click('#f-active button[data-v="all"]'); await p.waitForTimeout(700); await p.click('#f-active button[data-v="active"]'); await p.waitForTimeout(700);

  // ---- Edit, for real, and read it back through the OLD app's API -----------------------
  const code = await p.locator('#list .person.on b').textContent();
  await p.click('#file button:has-text("Edit")'); await p.waitForTimeout(400);
  ck('Edit opens the file dialog', await p.locator('#dlg-edit').isVisible());
  await p.fill('#e-nationality', 'Indian'); await p.fill('#e-mobile', '+971 55 000 0000'); await p.fill('#e-emergency_name', 'Test Contact');
  await p.click('#e-gender button[data-v="Male"]');
  await p.click('#dlg-edit button:has-text("Save")'); await p.waitForTimeout(1200);
  ck('the file saves without a pop-up', !(await p.locator('#dlg-edit').isVisible()) && (await p.locator('#status').textContent()).includes('Saved'));
  await p.click('#file .subtabs button[data-section="identity"]'); await p.waitForTimeout(200);
  ck('and the Identity section shows it', (await p.locator('#file').textContent()).includes('Test Contact'));
  const seen = await p.evaluate(async c => (await apiCall('/employees/staff')).rows.find(s => s.emp_no === c), code);
  ck('the OLD Staff Register still holds the same person, untouched salary', seen && seen.gross > 0, seen);

  // Document: add, edit, remove.
  await p.click('#file .subtabs button[data-section="documents"]'); await p.waitForTimeout(200);
  await p.click('#file button:has-text("+ Document")'); await p.waitForTimeout(300);
  await p.click('#d-kind button[data-v="driving"]'); await p.fill('#d-number', 'DL-TEST-1'); await p.fill('#d-expires_on', '2029-01-31');
  await p.click('#dlg-doc button:has-text("Save")'); await p.waitForTimeout(1000);
  ck('a driving licence is recorded', (await p.locator('#file').textContent()).includes('DL-TEST-1'));
  const tracker = await p.evaluate(async c => (await apiCall('/employees/documents')).rows.some(d => d.emp_no === c && d.kind === 'driving'), code);
  ck('and the OLD document tracker lists it', tracker);
  const row = p.locator('#file tr', { hasText: 'DL-TEST-1' });
  await row.locator('button:has-text("Remove")').click(); await p.waitForTimeout(200); await p.click('.ask [data-a="yes"]'); await p.waitForTimeout(900);
  ck('and it can be removed', !(await p.locator('#file').textContent()).includes('DL-TEST-1'));

  // Asset: issue and return.
  await p.click('#file .subtabs button[data-section="assets"]'); await p.waitForTimeout(200);
  await p.click('#file button:has-text("+ Issue an item")'); await p.waitForTimeout(300);
  await p.fill('#a-item', 'Test laptop'); await p.fill('#a-tag', 'T-1'); await p.click('#dlg-asset button:has-text("Save")'); await p.waitForTimeout(900);
  ck('an item is issued', (await p.locator('#file').textContent()).includes('Test laptop'));
  await p.locator('#file tr', { hasText: 'Test laptop' }).locator('button:has-text("Remove")').click(); await p.waitForTimeout(200); await p.click('.ask [data-a="yes"]'); await p.waitForTimeout(900);
  ck('and taken off', !(await p.locator('#file').textContent()).includes('Test laptop'));

  // A loan entered here is the payroll register's loan.
  await p.click('#file .subtabs button[data-section="money"]'); await p.waitForTimeout(200);
  await p.click('#file button:has-text("+ Loan")'); await p.waitForTimeout(300);
  await p.fill('#l-amount', '1000'); await p.fill('#l-instalment', '100'); await p.fill('#l-terms', 'Sweep loan');
  await p.click('#dlg-loan button:has-text("Record loan")'); await p.waitForTimeout(1200);
  ck('a loan recorded on People shows on the file', (await p.locator('#file').textContent()).includes('Sweep loan'));
  const reg = await p.evaluate(async c => (await apiCall('/employees/loans')).rows.find(l => l.emp_no === c && l.terms === 'Sweep loan'), code);
  ck('and is on the payroll Loans register - entered once', !!reg && reg.amount === 1000 && reg.instalment === 100, reg);
  await p.locator('#file tr', { hasText: 'Sweep loan' }).locator('button:has-text("Repayment")').click(); await p.waitForTimeout(300);
  await p.fill('#r-amount', '250'); await p.click('#dlg-repay button:has-text("Record")'); await p.waitForTimeout(1200);
  ck('a repayment brings the balance down here and there', (await p.evaluate(async id => (await apiCall('/employees/loans')).rows.find(l => l.id === id).balance, reg.id)) === 750
     && (await p.locator('#file').textContent()).includes('750.00'));
  await p.evaluate(async id => { for (const r of (await apiCall('/employees/loans')).rows.find(l => l.id === id).repayments) await apiCall(`/employees/loans/repayments/${r.id}`, { method: 'DELETE' }).catch(() => {}); await apiCall(`/employees/loans/${id}`, { method: 'DELETE' }).catch(() => {}); }, reg.id);

  // New person, then remove the test record through the OLD API so the data is left clean.
  await p.click('#view-register button:has-text("+ New person")'); await p.waitForTimeout(300);
  ck('New person opens in the page', await p.locator('#dlg-new').isVisible());
  await p.click('#n-group button[data-v="office"]');
  await p.fill('#n-emp_no', 'ZZ901'); await p.fill('#n-name', 'Sweep Test'); await p.fill('#n-designation', 'Tester'); await p.fill('#n-joined_on', '2026-09-01');
  await p.fill('#n-gross', '5000'); await p.dispatchEvent('#n-gross', 'input');
  ck('the 40/60 split fills itself', await p.inputValue('#n-basic') === '2000.00' && await p.inputValue('#n-allowance') === '3000.00');
  await p.click('#dlg-new button:has-text("Add to the register")'); await p.waitForTimeout(2500);
  ck('the joiner is added and opened', (await p.locator('#file h2').textContent()).includes('ZZ901'));
  const onOld = await p.evaluate(async () => (await apiCall('/employees/staff')).rows.some(s => s.emp_no === 'ZZ901' && s.gross === 5000));
  ck('the OLD Staff Register has him at once, gross 5,000', onOld);
  await p.click('#view-register button:has-text("+ New person")'); await p.waitForTimeout(200);
  await p.click('#n-group button[data-v="office"]'); await p.fill('#n-emp_no', 'ZZ901'); await p.fill('#n-name', 'Dup'); await p.fill('#n-joined_on', '2026-09-01'); await p.fill('#n-gross', '1');
  await p.click('#dlg-new button:has-text("Add to the register")'); await p.waitForTimeout(800);
  ck('a duplicate code is refused, in the dialog', (await p.locator('#new-msg').textContent()).includes('already'));
  await p.evaluate("closeDlg('dlg-new')");
  const gone = await p.evaluate(async () => { try { await apiCall('/employees/people/ZZ901', { method: 'DELETE' }); return true; } catch (e) { return JSON.stringify(e); } });
  ck('a record added by mistake can be removed while nothing hangs off it', gone === true, gone);

  // ---- Documents due and leave balances ---------------------------------------------------
  await p.click('.nav-sub[data-view="due"]'); await p.waitForTimeout(900);
  ck('Documents due opens', await p.locator('#view-due').isVisible() && (await p.locator('#due-count').textContent()).includes('document'));
  for (const d of ['30', '180', '90']) { await p.click(`#due-days button[data-v="${d}"]`); pressed++; await p.waitForTimeout(500); }
  for (const g of ['labour', 'office', '']) { await p.click(`#due-group button[data-v="${g}"]`); pressed++; await p.waitForTimeout(500); }
  for (const text of ['Preview', 'Export to PDF', 'Export to Excel']) { await p.click(`#view-due button:has-text("${text}")`); pressed++; await p.waitForTimeout(600); }
  await p.click('.nav-sub[data-view="leave"]'); await p.waitForTimeout(900);
  ck('Leave balances opens', await p.locator('#view-leave').isVisible() && await p.locator('#lv-body tr').count() > 0);
  for (const g of ['office', 'local', 'household', 'labour']) { await p.click(`#lv-group button[data-v="${g}"]`); pressed++; await p.waitForTimeout(500); }
  for (const text of ['Preview', 'Export to PDF', 'Export to Excel']) { await p.click(`#view-leave button:has-text("${text}")`); pressed++; await p.waitForTimeout(600); }
  ck('the six report buttons opened six tabs', newPages.length === 6, newPages.length);
  for (const pg of newPages) { await pg.waitForLoadState().catch(() => {}); ck(`opened: ${((await pg.url()).split('/export/')[1] || pg.url()).split('&token')[0]}`, !/"detail"/.test(await pg.content().catch(() => '"detail"'))); await pg.close().catch(() => {}); }
  newPages.length = 0;
  const openBtn = p.locator('#lv-body button:has-text("Open")').first();
  if (await openBtn.count()) { await openBtn.click(); await p.waitForTimeout(900); ck('Open from a list lands on that person\'s Leave section', await p.locator('#view-register').isVisible() && await p.locator('#file .subtabs button[data-section="leave"].on').count() === 1); }

  // ---- Access page ---------------------------------------------------------------------------
  await p.goto(BASE + '/temporary/Infinia/access.html'); await p.waitForSelector('#shell', { state: 'visible' }); await p.waitForTimeout(800);
  ck('the Access page opens on the same sign-in', await p.locator('#pane-roles').isVisible());
  await p.click('button:has-text("+ New role")'); await p.waitForTimeout(300);
  await p.fill('#r-name', 'Sweep Role'); await p.click('#r-rights input[value="attendance"]'); await p.click('#r-rights input[value="reports"]');
  await p.click('#dlg-role button:has-text("Save role")'); await p.waitForTimeout(900);
  ck('a role is made from ticks', (await p.locator('#roles-body').textContent()).includes('Sweep Role'));
  await p.click('.tab[data-tab="users"]'); await p.waitForTimeout(300);
  ck('the logins tab lists the logins', await p.locator('#users-body tr').count() >= 1);
  await p.click('button:has-text("+ New login")'); await p.waitForTimeout(300);
  await p.fill('#u-username', 'sweepuser'); await p.fill('#u-full_name', 'Sweep User'); await p.fill('#u-password', 'sweep123');
  await p.click('#u-role button:has-text("Sweep Role")');
  await p.click('#dlg-user button:has-text("Create login")'); await p.waitForTimeout(900);
  ck('a login is created from the role', (await p.locator('#users-body').textContent()).includes('sweepuser'));
  const rowU = p.locator('#users-body tr', { hasText: 'sweepuser' });
  ck('and shows the role', (await rowU.textContent()).includes('Sweep Role'));
  await rowU.locator('button:has-text("Role")').click(); await p.waitForTimeout(300);
  await p.click('#as-role button[data-v=""]'); await p.click('#dlg-assign button:has-text("Apply")'); await p.waitForTimeout(800);
  ck('a role can be taken off a login', (await p.locator('#users-body tr', { hasText: 'sweepuser' }).textContent()).includes('set by hand'));
  await p.click('.tab[data-tab="roles"]'); await p.waitForTimeout(200);
  await p.locator('#roles-body tr', { hasText: 'Sweep Role' }).locator('button:has-text("Delete")').click(); await p.waitForTimeout(200);
  ck('delete asks in the page', await p.locator('.ask').count() === 1);
  await p.click('.ask [data-a="yes"]'); await p.waitForTimeout(800);
  ck('and the role is gone', !(await p.locator('#roles-body').textContent()).includes('Sweep Role'));
  // The sweep login cannot open either page.
  const p2 = await (await b.newContext()).newPage();
  await p2.goto(BASE + '/temporary/Infinia/people.html'); await p2.fill('#login-username', 'sweepuser'); await p2.fill('#login-password', 'sweep123'); await p2.click('#login button'); await p2.waitForTimeout(1200);
  ck('a login without the right is turned away at the door', (await p2.locator('#login-error').textContent()).includes('not available') && !(await p2.locator('#shell').isVisible()));
  await p2.close();
  await p.evaluate(async () => { const u = (await apiCall('/users')).find(x => x.username === 'sweepuser'); if (u) await apiCall(`/users/${u.id}`, { method: 'DELETE' }).catch(() => {}); });

  console.log(`\n${pressed} buttons pressed`);
  ck('no server errors', http.length === 0, http.slice(0, 3));
  ck('no browser pop-ups, no script errors', errs.length === 0, errs.slice(0, 5));
  await b.close();
  console.log(fails ? `\n${fails} FAILED` : '\nPEOPLE AND ACCESS: EVERYTHING CLICKS');
  process.exit(fails ? 1 : 0);
})();
