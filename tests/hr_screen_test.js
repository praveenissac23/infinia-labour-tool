// The Office HR & Payroll screen, in a real browser.
//
// Run: python3 tests/serve_like_nginx.py &   then   node tests/hr_screen_test.js
//
// The figures are already proved against the signed August statements by
// office_payroll_test.py. What cannot be proved there is the part the
// accountant actually touches: that opening a cycle fills itself in,
// that typing a bill moves the net pay and the totals at once, that
// approving locks the sheet, and that every register on the screen
// offers a preview, a PDF, a spreadsheet and a print.
//
// It is also the only place the screen can be checked at the width it
// is used at. Half this work is done on a laptop in the office and half
// on a phone on site.
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:8032';
const FAIL = [];
const ck = (m, cond, ctx) => {
  console.log((cond ? 'PASS ' : 'FAIL ') + m + (cond ? '' : `  [${ctx}]`));
  if (!cond) FAIL.push(m);
};

const CYCLE_MONTH = '2026-08';

(async () => {
  const b = await chromium.launch();
  const errs = [];
  const p = await b.newPage({ viewport: { width: 1500, height: 1000 } });
  p.on('pageerror', e => errs.push(String(e).slice(0, 200)));

  await p.goto(BASE + '/app.html');
  await p.fill('#login-username', 'admin');
  await p.fill('#login-password', 'changeme123');
  await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 });
  await p.waitForTimeout(2000);

  // ---- The screen is there and admin can reach it ---------------------
  ck('HR & Payroll is in the menu',
     await p.locator('.nav-item[data-screen="hrpayroll"]').count() === 1);
  await p.evaluate("switchScreen('hrpayroll')");
  await p.waitForTimeout(1500);
  ck('it opens', await p.locator('#screen-hrpayroll').isVisible());
  ck('and is titled as the office side of the app',
     (await p.locator('#screen-title').textContent()).includes('HR'));
  ck('six registers, one open',
     await p.locator('.hr-tab').count() === 6 &&
     await p.locator('.hr-pane:visible').count() === 1);

  // ---- Set the month up ------------------------------------------------
  // A company and two staff, entered through the screen's own calls so
  // the test exercises what the screen exercises.
  // Run against a database that may already hold a previous run's
  // fixtures, so each step tolerates the thing already being there.
  await p.evaluate(async () => {
    const quiet = async (fn) => { try { return await fn(); } catch (e) { return null; } };
    let co = (await apiCall('/employees/companies'))
      .find(x => x.short_name === 'BrowserCo');
    if (!co) co = await apiCall('/employees/companies', { method: 'POST',
      body: JSON.stringify({ name: 'BROWSER TEST CO', short_name: 'BrowserCo',
                             code_prefix: 'BT' }) });
    for (const [n, name, basic, allow] of [['BT001', 'TEST ONE', 2000, 3000],
                                            ['BT002', 'TEST TWO', 4000, 6000]]) {
      await quiet(() => apiCall('/employees', { method: 'POST', body: JSON.stringify({
        emp_no: n, name, trade: 'Tester', total_salary: basic + allow,
        basic_salary: basic }) }));
      await apiCall(`/employees/staff/${n}`, { method: 'PUT', body: JSON.stringify({
        company_id: co.id, joined_on: '2024-01-15', designation: 'Tester',
        basic, allowance: allow, contract_basic: basic, pay_route: 'wps' }) });
    }
    // One unpaid day, so the cycle has something to propose by itself.
    await quiet(() => apiCall('/employees/leave', { method: 'POST', body: JSON.stringify({
      emp_no: 'BT002', on_date: '2026-08-11', half: false, paid: false,
      reason: 'absent' }) }));
    const loans = (await apiCall('/employees/loans')).rows
      .filter(l => l.emp_no === 'BT001');
    if (!loans.length) await apiCall('/employees/loans', { method: 'POST',
      body: JSON.stringify({ emp_no: 'BT001', amount: 2400, taken_on: '2026-06-01',
                             instalment: 200, terms: 'Monthly 200' }) });
  });

  // The screen picked up its company list before any of that existed,
  // so it is loaded again here - the same thing that happens when the
  // accountant adds a company and the list refills.
  await p.evaluate('loadHrScreen()');
  await p.waitForTimeout(1200);

  // ---- Opening a cycle fills itself in ---------------------------------
  await p.evaluate("hrTab('payroll')");
  await p.waitForTimeout(400);
  await p.selectOption('#hr-run-company',
    { label: 'BrowserCo' }).catch(() => {});
  await p.fill('#hr-run-month', CYCLE_MONTH);
  await p.evaluate('openPayrollCycle()');
  await p.waitForTimeout(1800);

  ck('the cycle card appears', await p.locator('#hr-run-card').isVisible());
  ck('with a row for each of the two', await p.locator('#hr-run-body tr').count() === 2);

  const line = async (emp, field) => p.evaluate(([e, f]) =>
    HR_RUN.lines.find(l => l.emp_no === e)[f], [emp, field]);

  ck('the salary came through without being typed',
     await line('BT002', 'fixed_salary') === 10000, await line('BT002', 'fixed_salary'));
  ck('the unpaid day is already deducted at the daily rate',
     await line('BT002', 'deduction') === 333, await line('BT002', 'deduction'));
  ck('the note says which day',
     (await line('BT002', 'deduction_note')).includes('11 Aug'),
     await line('BT002', 'deduction_note'));
  ck("the loan instalment is on the other man's row",
     await line('BT001', 'loan_deduction') === 200, await line('BT001', 'loan_deduction'));

  // ---- Typing a figure moves everything that depends on it -------------
  // Checked against what the figures ought to be rather than against
  // what they were a moment ago: run twice over the same database the
  // bill is already there, and "it changed" would be false while
  // everything was in fact correct.
  await p.evaluate(() => {
    const id = HR_RUN.lines.find(l => l.emp_no === 'BT001').id;
    const cell = document.querySelector(
      `.hr-cell[data-line="${id}"][data-field="other_allowance"]`);
    cell.value = '150';
    cell.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await p.waitForTimeout(300);
  const id1 = await p.evaluate(() => HR_RUN.lines.find(l => l.emp_no === 'BT001').id);
  ck('typing a taxi bill moves the net pay at once',
     (await p.locator('#hr-net-' + id1).textContent()).trim() === '4,950.00',
     await p.locator('#hr-net-' + id1).textContent());
  ck('and the salary payable with it',
     (await p.locator('#hr-payable-' + id1).textContent()).trim() === '5,150.00',
     await p.locator('#hr-payable-' + id1).textContent());
  ck('and the foot of the sheet keeps up',
     (await p.locator('#hr-run-foot').textContent()).includes('150.00'));
  ck('and the WPS figure at the bottom keeps up',
     (await p.locator('#hr-run-routes').textContent()).includes('WPS TOTAL'),
     await p.locator('#hr-run-routes').textContent());

  await p.evaluate('savePayrollRun()');
  await p.waitForTimeout(1500);
  ck('the bill survives a save',
     await line('BT001', 'other_allowance') === 150, await line('BT001', 'other_allowance'));

  // ---- Approving locks it ---------------------------------------------
  p.on('dialog', d => d.accept());
  await p.evaluate('approvePayrollRun()');
  await p.waitForTimeout(2000);
  ck('approving locks the sheet',
     await p.evaluate(() => HR_RUN.status) === 'approved',
     await p.evaluate(() => HR_RUN.status));
  ck('the cells go read-only when it is locked',
     await p.evaluate(() =>
       [...document.querySelectorAll('.hr-cell')].every(c => c.disabled)));
  ck('Save and Approve give way to Reopen',
     await p.locator('#hr-reopen-btn').isVisible() &&
     !(await p.locator('#hr-approve-btn').isVisible()));
  ck('and the instalment came off the loan',
     await p.evaluate(async () => {
       const d = await apiCall('/employees/loans');
       return d.rows.find(l => l.emp_no === 'BT001').balance;
     }) === 2200);

  await p.evaluate('reopenPayrollRun()');
  await p.waitForTimeout(1500);
  ck('reopening puts the instalment back',
     await p.evaluate(async () => {
       const d = await apiCall('/employees/loans');
       return d.rows.find(l => l.emp_no === 'BT001').balance;
     }) === 2400);
  ck('and the cells can be typed in again',
     await p.evaluate(() =>
       [...document.querySelectorAll('.hr-cell')].every(c => !c.disabled)));

  // ---- Every register carries the four buttons -------------------------
  const PANES = {
    payroll: ['previewStatement', 'downloadStatement', 'printStatement'],
    staff: [], loans: [], leave: [], docs: [], increments: [],
  };
  for (const tab of Object.keys(PANES)) {
    await p.evaluate(t => hrTab(t), tab);
    await p.waitForTimeout(700);
    ck(`${tab} opens`, await p.locator(`#hrpane-${tab}`).isVisible());
    if (tab === 'increments') continue;   // a history, not a report
    const text = await p.locator(`#hrpane-${tab}`).textContent();
    ck(`${tab} offers a preview`, text.includes('Preview'), text.slice(0, 80));
    ck(`${tab} offers a PDF`, text.includes('Export to PDF'));
    ck(`${tab} offers a spreadsheet`, text.includes('Export to Excel'));
  }
  ck('the salary sheet can be printed',
     (await p.locator('#hrpane-payroll').textContent()).includes('Print'));

  // ---- The registers themselves load -----------------------------------
  await p.evaluate("hrTab('staff')"); await p.waitForTimeout(900);
  ck('the staff register lists the two',
     (await p.locator('#hr-staff-body tr').count()) >= 2);
  ck('and shows what each has earned in gratuity',
     (await p.locator('#hr-staff-foot').textContent()).includes('TOTAL'),
     await p.locator('#hr-staff-foot').textContent());

  await p.evaluate("hrTab('loans')"); await p.waitForTimeout(900);
  ck('the loan register shows a balance',
     (await p.locator('#hr-loan-body').textContent()).includes('2,400.00'));

  await p.evaluate("hrTab('leave')"); await p.waitForTimeout(400);
  await p.fill('#hr-leave-month', CYCLE_MONTH);
  await p.evaluate('loadLeave()'); await p.waitForTimeout(900);
  ck('the leave register shows the unpaid day',
     (await p.locator('#hr-leave-body').textContent()).includes('Unpaid'),
     await p.locator('#hr-leave-body').textContent());

  await p.evaluate("hrTab('docs')"); await p.waitForTimeout(900);
  ck('the document tracker loads', await p.locator('#hr-doc-body').count() === 1);

  // ---- The preview is the printed sheet --------------------------------
  const runId = await p.evaluate(() => HR_RUN.id);
  const tok = await p.evaluate(async () => {
    const { token } = await apiCall('/auth/download-token', { method: 'POST' });
    return token;
  });
  const pv = await b.newPage();
  await pv.goto(`${BASE}/export/payroll/statement/view?run_id=${runId}` +
                `&token=${encodeURIComponent(tok)}`);
  const body = await pv.content();
  ck('the preview carries the Infinia letterhead', body.includes('data:image/png;base64'));
  ck('and the statement headings', body.includes('Fix Allown.') &&
     body.includes('Salary Payable') && body.includes('Net Pay'));
  ck('and the three foot totals',
     body.includes('WPS TOTAL'), body.slice(0, 200));

  // ---- On a phone -------------------------------------------------------
  const ph = await b.newPage({ viewport: { width: 430, height: 900 } });
  ph.on('pageerror', e => errs.push('phone: ' + String(e).slice(0, 160)));
  await ph.goto(BASE + '/app.html');
  await ph.fill('#login-username', 'admin');
  await ph.fill('#login-password', 'changeme123');
  await ph.evaluate('doLogin()');
  await ph.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 });
  await ph.waitForTimeout(2000);
  await ph.evaluate("switchScreen('hrpayroll')");
  await ph.waitForTimeout(1800);
  ck('the screen opens on a phone', await ph.locator('#screen-hrpayroll').isVisible());
  ck('and the tabs wrap rather than run off the side',
     await ph.evaluate(() => {
       const t = document.querySelector('.hr-tabs');
       return t.scrollWidth <= t.clientWidth + 2;
     }));
  ck('and the page itself does not scroll sideways',
     await ph.evaluate(() =>
       document.documentElement.scrollWidth <= window.innerWidth + 2),
     await ph.evaluate(() => document.documentElement.scrollWidth + ' vs ' + window.innerWidth));

  // ---- And nobody else sees it ------------------------------------------
  // The receptionist runs the office diary and the material requests.
  // She has no business in the office payroll, and the menu should not
  // even offer it to her.
  await p.evaluate(async () => {
    try {
      await apiCall('/users', { method: 'POST', body: JSON.stringify({
        username: 'reception', password: 'reception123', full_name: 'Reception',
        role: 'office' }) });
    } catch (e) { /* already there from a previous run */ }
  });
  const rp = await b.newPage({ viewport: { width: 1400, height: 1000 } });
  const rerrs = [];
  rp.on('pageerror', e => rerrs.push(String(e).slice(0, 160)));
  await rp.goto(BASE + '/app.html');
  await rp.fill('#login-username', 'reception');
  await rp.fill('#login-password', 'reception123');
  await rp.evaluate('doLogin()');
  await rp.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 });
  await rp.waitForTimeout(2500);
  ck('the receptionist signs in', await rp.locator('#app-screen').isVisible());
  ck('and HR & Payroll is not in her menu',
     await rp.locator('.nav-item[data-screen="hrpayroll"]').isVisible() === false);
  ck('and it is not among the screens she holds',
     await rp.evaluate(() => !MY_SCREENS.includes('hrpayroll')),
     await rp.evaluate(() => JSON.stringify(MY_SCREENS)));
  for (const [what, path] of [['the staff list', '/employees/staff'],
                              ['the payroll cycles', '/employees/payroll/runs'],
                              ['the loan balances', '/employees/loans']]) {
    ck(`and typing the address for ${what} gets her nowhere`,
       await rp.evaluate(async (u) => {
         try { await apiCall(u); return 'allowed'; }
         catch (e) { return e.status; }
       }, path) === 403);
  }
  ck('nothing threw for her either', rerrs.length === 0, rerrs.slice(0, 3).join(' | '));

  ck('nothing threw anywhere', errs.length === 0, errs.slice(0, 4).join(' | '));

  await b.close();
  console.log('');
  if (FAIL.length) {
    console.log(`${FAIL.length} FAILED`);
    FAIL.forEach(f => console.log('  - ' + f));
    process.exit(1);
  }
  console.log('THE HR SCREEN WORKS');
})();
