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
  ck('eight registers, one open',
     await p.locator('.hr-tab').count() === 8 &&
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

  // Clear what an earlier run of this test left for August, so it runs
  // the same every time, and make sure the month is open.
  await p.evaluate(async () => {
    const runs = (await apiCall('/employees/payroll/runs')).rows;
    for (const r of runs.filter(r => r.company === 'BrowserCo' && r.month_year === 'August 2026'))
      if (r.status === 'approved') await apiCall(`/employees/payroll/runs/${r.id}/reopen`, { method: 'POST' });
    const lv = (await apiCall('/employees/leave?month_year=August 2026')).rows;
    for (const r of lv.filter(r => ['BT001', 'BT002'].includes(r.emp_no)))
      await apiCall(`/employees/leave/entry/${r.batch}`, { method: 'DELETE' });
    const it = (await apiCall('/employees/pay-items?month_year=August 2026')).rows;
    for (const r of it.filter(r => ['BT001', 'BT002'].includes(r.emp_no)))
      await apiCall(`/employees/pay-items/${r.id}`, { method: 'DELETE' });
    await apiCall('/employees/leave', { method: 'POST', body: JSON.stringify({
      emp_no: 'BT002', kind: 'absent', from: '2026-08-11' }) });
    for (const l of (await apiCall('/employees/loans')).rows.filter(l => l.emp_no === 'BT001'))
      for (const r of l.repayments.filter(r => r.source !== 'payroll'))
        await apiCall(`/employees/loans/repayments/${r.id}`, { method: 'DELETE' });
    const run = runs.find(r => r.company === 'BrowserCo' && r.month_year === 'August 2026');
    if (run) {
      const full = await apiCall(`/employees/payroll/runs/${run.id}`);
      await apiCall(`/employees/payroll/runs/${run.id}`, { method: 'PUT', body: JSON.stringify({
        lines: full.lines.map(l => ({ id: l.id, loan_reset: true, remarks: '' })) }) });
    }
  });
  // Any browser pop-up at all is a failure: the page asks its own questions.
  p.on('dialog', d => { errs.push('browser pop-up: ' + d.message().slice(0, 80)); d.dismiss(); });

  // The screen picked up its company list before any of that existed,
  // so it is loaded again here - the same thing that happens when the
  // accountant adds a company and the list refills.
  await p.evaluate('loadHrScreen()');
  await p.waitForTimeout(1200);

  // ---- Opening a cycle fills itself in ---------------------------------
  await p.evaluate("hrTab('payroll')");
  await p.waitForTimeout(400);
  await p.evaluate(() => { document.getElementById('hr-run-company').value = HR_COMPANIES.find(c => c.short_name === 'BrowserCo').id; });
  await p.waitForTimeout(800);
  await p.evaluate(m => { document.getElementById('hr-run-month').value = m; hrSyncBar(); }, CYCLE_MONTH);
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

  // ---- The registers fill the sheet ------------------------------------
  // Nothing is typed on the salary sheet except the instalment and the
  // remark: a bill goes in Additions & Deductions, an absence in
  // Absence, and the open cycle picks both up by itself.
  const cycleLine = async (emp) => {
    const id = await p.evaluate(() => HR_RUN.id);
    await p.evaluate(i => loadPayrollRun(i), id); await p.waitForTimeout(900);
    return p.evaluate(e => HR_RUN.lines.find(l => l.emp_no === e), emp);
  };
  const choose = async (sel, value) => p.evaluate(([s, v]) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }, [sel, value]);
  const ask = async () => {           // answer the page's own question box
    await p.waitForSelector('.hr-ask [data-a="yes"]', { timeout: 5000 });
    await p.click('.hr-ask [data-a="yes"]');
    await p.waitForTimeout(1200);
  };

  await p.evaluate("hrTab('items')"); await p.waitForTimeout(800);
  await choose('#hr-item-emp', 'BT001');
  await p.fill('#hr-item-month', CYCLE_MONTH);
  await choose('#hr-item-dir', 'add'); await choose('#hr-item-cat', 'taxi');
  await p.fill('#hr-item-amount', '150');
  await p.fill('#hr-item-note', 'Taxi bills');
  await p.click('#hr-item-save'); await p.waitForTimeout(1200);
  ck('a taxi bill goes in from the Additions tab',
     (await p.locator('#hr-items-body').textContent()).includes('150.00'),
     await p.locator('#hr-items-body').textContent());

  await p.evaluate("hrTab('leave')"); await p.waitForTimeout(800);
  for (const d of ['2026-08-05', '2026-08-06']) {
    await choose('#hr-leave-emp', 'BT001'); await choose('#hr-leave-kind', 'sick');
    await p.fill('#hr-leave-from', d); await p.fill('#hr-leave-to', '');
    await p.click('#hr-leave-save'); await p.waitForTimeout(1200);
  }
  const lv = await p.locator('#hr-leave-body').textContent();
  ck("the month's first sick day shows paid and the second deducted",
     /5 Aug 2026[\s\S]*Paid/.test(lv) && /6 Aug 2026[\s\S]*Deducted/.test(lv), lv.slice(0, 300));

  await p.evaluate("hrTab('payroll')"); await p.waitForTimeout(500);
  let L1 = await cycleLine('BT001');
  ck('the sheet picked up the bill without it being typed there', L1.other_allowance === 150, L1.other_allowance);
  ck('and one sick day deducted at the daily rate: 166.00', L1.deduction === 166, L1.deduction);
  ck('net pay: 5,000 + 150 - 166 - 200 instalment = 4,784.00', L1.net_pay === 4784, L1.net_pay);
  ck('the bill and the absence are not boxes on the sheet',
     await p.evaluate(id => !document.querySelector(`.hr-cell[data-line="${id}"][data-field="other_allowance"]`), L1.id));

  // The instalment is typed on the sheet, and the net follows at once.
  await p.evaluate(id => {
    const cell = document.querySelector(`.hr-cell[data-line="${id}"][data-field="loan_deduction"]`);
    cell.value = '100'; cell.dispatchEvent(new Event('input', { bubbles: true }));
  }, L1.id);
  await p.waitForTimeout(300);
  ck('typing a smaller instalment moves the net pay at once: 4,884.00',
     (await p.locator('#hr-net-' + L1.id).textContent()).trim() === '4,884.00',
     await p.locator('#hr-net-' + L1.id).textContent());
  await p.evaluate('savePayrollRun()'); await p.waitForTimeout(1200);
  L1 = await cycleLine('BT001');
  ck('and it is kept when the sheet refills', L1.loan_deduction === 100, L1.loan_deduction);
  await p.evaluate(id => {
    const cell = document.querySelector(`.hr-cell[data-line="${id}"][data-field="loan_deduction"]`);
    cell.value = '200'; cell.dispatchEvent(new Event('input', { bubbles: true }));
  }, L1.id);
  await p.evaluate('savePayrollRun()'); await p.waitForTimeout(1200);

  // A vacation, with leave salary offered at a month's gross.
  await p.evaluate("hrTab('leave')"); await p.waitForTimeout(600);
  await choose('#hr-leave-emp', 'BT002'); await choose('#hr-leave-kind', 'vacation');
  await p.evaluate('hrLeaveKindChanged()');
  await p.fill('#hr-leave-from', '2026-08-20'); await p.fill('#hr-leave-to', '2026-08-22');
  await p.evaluate('hrLeaveRangeChanged()');
  ck('a year served, so leave salary is offered at his gross',
     (await p.inputValue('#hr-vac-salary')) === '10,000', await p.inputValue('#hr-vac-salary'));
  ck('and the form says how many days', (await p.locator('#hr-leave-hint').textContent()).includes('3 calendar days'));
  await p.fill('#hr-vac-ticket', '1200');
  await p.click('#hr-leave-save'); await p.waitForTimeout(1300);
  ck('the vacation shows as one line, 20-22 Aug',
     (await p.locator('#hr-leave-body').textContent()).includes('20-22 Aug 2026'),
     await p.locator('#hr-leave-body').textContent());
  await p.evaluate("hrTab('payroll')"); await p.waitForTimeout(400);
  let L2 = await cycleLine('BT002');
  ck('the three days are deducted with the absent day: 1,332.00', L2.deduction === 1332, L2.deduction);
  ck('and leave salary and ticket are on the sheet', L2.leave_salary === 10000 && L2.air_ticket === 1200,
     [L2.leave_salary, L2.air_ticket]);

  // Changing the entry changes the pay.
  await p.evaluate("hrTab('leave')"); await p.waitForTimeout(600);
  const vb = await p.evaluate(() => HR_LEAVE.find(r => r.kind === 'vacation' && r.emp_no === 'BT002').batch);
  await p.evaluate(b => hrLeaveEdit(b), vb);
  ck('Edit loads the entry back into the form', (await p.inputValue('#hr-leave-to')) === '2026-08-22');
  await p.fill('#hr-leave-to', '2026-08-21');
  await p.click('#hr-leave-save'); await p.waitForTimeout(1300);
  await p.evaluate("hrTab('payroll')"); await p.waitForTimeout(400);
  L2 = await cycleLine('BT002');
  ck('shortened to two days, the sheet follows: 999.00', L2.deduction === 999, L2.deduction);

  // Removing asks in the page, not in a browser box.
  await p.evaluate("hrTab('leave')"); await p.waitForTimeout(600);
  const sb = await p.evaluate(() => HR_LEAVE.find(r => r.emp_no === 'BT001' && r.from === '2026-08-06').batch);
  p.evaluate(b => hrLeaveDelete(b), sb);
  await ask();
  ck('an entry is removed after the page asks', !(await p.evaluate(() =>
     HR_LEAVE.some(r => r.emp_no === 'BT001' && r.from === '2026-08-06'))));

  // ---- Approving locks it ---------------------------------------------
  await p.evaluate("hrTab('payroll')"); await p.waitForTimeout(400);
  await cycleLine('BT001');
  p.evaluate('approvePayrollRun()');
  await ask(); await p.waitForTimeout(800);
  ck('approving locks the sheet',
     await p.evaluate(() => HR_RUN.status) === 'approved',
     await p.evaluate(() => HR_RUN.status));
  ck('a locked sheet shows figures, not boxes to type in',
     await p.evaluate(() => document.querySelectorAll('#hr-run-body input').length === 0));
  ck('Save and Approve give way to Reopen',
     await p.locator('#hr-reopen-btn').isVisible() &&
     !(await p.locator('#hr-approve-btn').isVisible()));
  ck('and the instalment came off the loan',
     await p.evaluate(async () => {
       const d = await apiCall('/employees/loans');
       return d.rows.find(l => l.emp_no === 'BT001').balance;
     }) === 2200);
  await p.evaluate("hrTab('leave')"); await p.waitForTimeout(600);
  await choose('#hr-leave-emp', 'BT001'); await choose('#hr-leave-kind', 'absent');
  await p.fill('#hr-leave-from', '2026-08-12'); await p.fill('#hr-leave-to', '');
  await p.click('#hr-leave-save'); await p.waitForTimeout(1000);
  ck('an absence in the approved month is refused, with the reason',
     (await p.locator('#hr-status').textContent()).includes('Reopen'),
     await p.locator('#hr-status').textContent());

  await p.evaluate("hrTab('payroll')"); await p.waitForTimeout(400);
  p.evaluate('reopenPayrollRun()');
  await ask();
  ck('reopening puts the instalment back',
     await p.evaluate(async () => {
       const d = await apiCall('/employees/loans');
       return d.rows.find(l => l.emp_no === 'BT001').balance;
     }) === 2400);
  ck('and the instalment box comes back when it is reopened',
     await p.evaluate(() => document.querySelectorAll('#hr-run-body input.hr-amt').length > 0));

  // ---- A repayment with its own date, and correcting it --------------
  await p.evaluate("hrTab('loans')"); await p.waitForTimeout(800);
  const loanId = await p.evaluate(() => HR_LOANS.find(l => l.emp_no === 'BT001').id);
  await p.evaluate(i => hrLoanToggle(i), loanId); await p.waitForTimeout(300);
  await p.fill('#hr-rep-date', '2026-08-18'); await p.fill('#hr-rep-amount', '300');
  await p.fill('#hr-rep-note', 'Paid at the office');
  await p.click('text=Record repayment'); await p.waitForTimeout(1200);
  const hist = await p.locator('#hr-loan-body').textContent();
  ck('a repayment is recorded in the page with its date - no pop-up',
     hist.includes('18 Aug 2026') && hist.includes('Paid at the office'), hist.slice(0, 300));
  ck('and the balance drops: 2,100.00', hist.includes('2,100.00'));
  const repId = await p.evaluate(() => HR_LOANS.find(l => l.emp_no === 'BT001').repayments
                                  .find(r => r.notes === 'Paid at the office').id);
  await p.evaluate(([l, r]) => hrRepEdit(l, r), [loanId, repId]); await p.waitForTimeout(300);
  await p.fill('#hr-rep-date', '2026-08-19');
  await p.click('text=Save changes'); await p.waitForTimeout(1200);
  ck('its date can be corrected', (await p.locator('#hr-loan-body').textContent()).includes('19 Aug 2026'));
  p.evaluate(r => hrRepDelete(r), repId);
  await ask();
  ck('and it can be removed, putting the balance back',
     (await p.locator('#hr-loan-body').textContent()).includes('2,400.00'));

  // ---- Every register carries the four buttons -------------------------
  const PANES = ['payroll', 'leave', 'items', 'loans', 'staff', 'increments', 'docs', 'gratuity'];
  for (const tab of PANES) {
    await p.evaluate(t => hrTab(t), tab);
    await p.waitForTimeout(700);
    ck(`${tab} opens`, await p.locator(`#hrpane-${tab}`).isVisible());
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
  await p.evaluate("hrTab('gratuity')"); await p.waitForTimeout(900);
  ck('the gratuity tab shows what each has earned',
     (await p.locator('#hr-grat-foot').textContent()).includes('TOTAL LIABILITY'),
     await p.locator('#hr-grat-foot').textContent());
  await p.evaluate("hrTab('increments')"); await p.waitForTimeout(900);
  const incId = await p.evaluate(() => HR_INCS.find(r => r.emp_no === 'BT001').id);
  await p.evaluate(i => hrIncEdit(i), incId);
  ck('a salary history line opens for correction',
     await p.locator('#hr-inc-edit').isVisible() && (await p.inputValue('#hr-ie-basic')) === '2,000');
  await p.evaluate('hrIncReset()');

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
  ck('and the statement headings', body.includes('Gross Salary') && body.includes('Add / Ded.') &&
     body.includes('Net Pay'));
  ck('and the three foot totals',
     body.includes('WPS TOTAL'), body.slice(0, 200));

  // ---- It reads properly -----------------------------------------------
  // Net pay and the remark were pushed off the right-hand edge on a
  // laptop screen, a row's colour vanished on every other line under the
  // zebra striping, and dates read 2026-09-13.
  for (const w of [1280, 1440, 1920]) {
    await p.setViewportSize({ width: w, height: 1000 });
    await p.evaluate("hrTab('payroll')"); await p.waitForTimeout(300);
    const [sw, cw] = await p.evaluate(() => {
      const g = document.querySelector('#hr-run-card .grid-wrap'); return [g.scrollWidth, g.clientWidth]; });
    ck(`at ${w}px the whole salary sheet fits, Net Pay and Remark included`, sw <= cw + 1, `${sw} > ${cw}`);
    const clash = await p.evaluate(() => [...document.querySelectorAll('#hr-run-foot td, #hr-run-body td.num')]
      .filter(td => td.scrollWidth > td.clientWidth + 1).length);
    ck(`at ${w}px no figure spills out of its cell`, clash === 0, clash);
  }
  await p.setViewportSize({ width: 1500, height: 1000 });
  await p.evaluate("hrTab('leave')"); await p.waitForTimeout(400);
  await p.fill('#hr-leave-month', CYCLE_MONTH);
  await p.evaluate('loadLeave()'); await p.waitForTimeout(900);
  ck('an unpaid day is coloured whichever line it falls on',
     await p.evaluate(() => [...document.querySelectorAll('#hr-leave-body tr.hr-bad td')]
       .every(td => getComputedStyle(td).backgroundColor !== 'rgb(252, 252, 252)')));
  ck('dates read the way the statements write them',
     !/\d{4}-\d{2}-\d{2}/.test(await p.locator('#hrpane-leave tbody').textContent()));
  await p.evaluate(async () => {
    await apiCall('/employees/documents', { method: 'POST', body: JSON.stringify({
      emp_no: 'BT001', kind: 'passport', expires_on: '2026-01-01' }) });
    await apiCall('/employees/documents', { method: 'POST', body: JSON.stringify({
      emp_no: 'BT001', kind: 'eid', expires_on: '2030-01-01' }) });
  });
  await p.evaluate("hrTab('docs')"); await p.waitForTimeout(1000);
  ck('each person is one line on the document tracker',
     await p.evaluate(() => [...document.querySelectorAll('#hr-doc-body tr')]
       .filter(tr => tr.textContent.includes('TEST ONE')).length) === 1);
  ck('an expired document is marked on its own date',
     await p.evaluate(() => [...document.querySelectorAll('#hr-doc-body tr')]
       .find(tr => tr.textContent.includes('TEST ONE')).querySelectorAll('td.hr-d-expired').length) >= 1);
  await p.evaluate(() => { const tr = [...document.querySelectorAll('#hr-doc-body tr')]
       .find(tr => tr.textContent.includes('TEST ONE')); tr.querySelector('td.hr-d-expired').click(); });
  ck('clicking a date puts it in the form for renewal',
     (await p.inputValue('#hr-doc-emp')) === 'BT001' && (await p.inputValue('#hr-doc-kind')) === 'passport');

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
  await ph.evaluate("hrTab('docs')"); await ph.waitForTimeout(700);
  ck('on a phone every labelled box is tall enough to type in',
     await ph.evaluate(() => [...document.querySelectorAll('#hrpane-docs .hr-field input')]
       .every(i => i.getBoundingClientRect().height >= 30)));
  await ph.evaluate("hrTab('payroll')"); await ph.waitForTimeout(300);
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
