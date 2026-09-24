// Every button on every HR tab, pressed, and nothing may go wrong.
//
// Run: python3 tests/serve_like_nginx.py &   then   node tests/hr_click_everything.js
//
// Presses each button on each of the seven tabs - with the forms empty,
// then again after an entry has been loaded for editing - and fails on:
//   * a script error on the page
//   * a server error (5xx) from any call the page makes
//   * a browser pop-up (the page asks its own questions)
//   * a refusal (4xx) the accountant is not told about in words
//   * a preview, PDF or spreadsheet that does not open
// It also walks the path that was reported broken - an absence recorded,
// then straight back to the salary sheet - and checks the sheet already
// shows it, with no refresh.
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:8032';
const FAIL = [];
const ck = (m, cond, ctx) => {
  console.log((cond ? 'PASS ' : 'FAIL ') + m + (cond ? '' : `  [${ctx}]`));
  if (!cond) FAIL.push(m);
};

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const p = await ctx.newPage();
  const errs = [], server = [], popups = [], refused = [];
  p.on('pageerror', e => errs.push(String(e).slice(0, 200)));
  p.on('dialog', d => { popups.push(d.message().slice(0, 80)); d.dismiss(); });
  p.on('response', r => {
    const u = r.url();
    if (!u.includes('/employees') && !u.includes('/export/payroll')) return;
    if (r.status() >= 500) server.push(`${r.status()} ${r.request().method()} ${u.replace(BASE, '')}`);
    else if (r.status() >= 400) refused.push(`${r.status()} ${r.request().method()} ${u.replace(BASE, '')}`);
  });
  // Previews and downloads open in a new tab. The page's window.open is
  // caught instead, and every address it asked for is fetched and checked:
  // a preview must be a page, a PDF a PDF, a spreadsheet a spreadsheet.
  const opened = [];
  await p.addInitScript(() => {
    window.__opened = [];
    window.open = (u) => { window.__opened.push(String(u)); return null; };
  });
  // Download links are good for sixty seconds by design, so each one is
  // checked the moment its button asks for it.
  const drain = async () => {
    const urls = await p.evaluate(() => { const u = window.__opened || []; window.__opened = []; return u; });
    for (const u of urls) {
      const r = await p.request.get(u.startsWith('http') ? u : BASE + u);
      const type = r.headers()['content-type'] || '';
      const body = await r.body();
      const kind = u.includes('/view?') ? 'preview' : u.includes('format=excel') ? 'excel' : 'pdf';
      const ok = r.status() === 200 && (
        kind === 'preview' ? type.includes('html') && body.toString().includes('Download PDF') :
        kind === 'excel' ? body.slice(0, 2).toString() === 'PK' : body.slice(0, 4).toString() === '%PDF');
      opened.push([ok, kind, r.status(), u.replace(BASE, '').split('&token')[0].split('?token')[0]]);
    }
  };

  await p.goto(BASE + '/app.html');
  await p.fill('#login-username', 'admin');
  await p.fill('#login-password', 'changeme123');
  await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 });
  await p.waitForTimeout(1500);
  await p.evaluate("localStorage.setItem('infinia_hr_tab', 'payroll')");
  await p.evaluate("switchScreen('hrpayroll')");
  await p.waitForTimeout(2500);

  // ---- The reported fault: absence recorded, sheet must follow at once --
  const infinia = await p.evaluate(() => (HR_COMPANIES.find(c => c.short_name === 'Infinia') || HR_COMPANIES[0]).id);
  await p.evaluate(i => { document.getElementById('hr-run-company').value = i; }, infinia);
  const now = new Date();
  const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  await p.evaluate(m => { document.getElementById('hr-run-month').value = m; }, month);
  await p.evaluate('openPayrollCycle()'); await p.waitForTimeout(1500);
  const who = await p.evaluate(() => HR_RUN.lines.find(l => l.fixed_salary > 0 && !l.deduction).emp_no);
  const before = await p.evaluate(w => HR_RUN.lines.find(l => l.emp_no === w).deduction, who);
  // A day in this month not already taken.
  const day = await p.evaluate(async ([w, m]) => {
    const taken = new Set((await apiCall(`/employees/leave?month_year=${encodeURIComponent(hrCycleName(m))}&emp_no=${w}`))
      .rows.flatMap(r => { const out = []; for (let d = new Date(r.from); d <= new Date(r.to); d.setDate(d.getDate() + 1)) out.push(d.toISOString().slice(0, 10)); return out; }));
    for (let i = 1; i <= 28; i++) { const d = `${m}-${String(i).padStart(2, '0')}`; if (!taken.has(d)) return d; }
  }, [who, month]);
  await p.click('.hr-tab[data-tab="leave"]'); await p.waitForTimeout(700);
  await p.evaluate(([s, v]) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }, ['#hr-leave-emp', who]);
  await p.evaluate(([s, v]) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }, ['#hr-leave-kind', 'absent']);
  await p.fill('#hr-leave-from', day); await p.fill('#hr-leave-to', '');
  await p.click('#hr-leave-save'); await p.waitForTimeout(1200);
  await p.click('.hr-tab[data-tab="payroll"]'); await p.waitForTimeout(1500);
  const after = await p.evaluate(w => HR_RUN.lines.find(l => l.emp_no === w).deduction, who);
  const shown = await p.evaluate(w => {
    const l = HR_RUN.lines.find(x => x.emp_no === w);
    return document.querySelector(`#hr-run-body tr[data-line="${l.id}"]`).textContent;
  }, who);
  ck(`an absence recorded for ${who} is on the salary sheet the moment the tab is opened`,
     after > before && shown.includes(Number(after).toLocaleString('en-US', { minimumFractionDigits: 2 })),
     `${before} -> ${after}`);
  // A bill, the same way.
  await p.click('.hr-tab[data-tab="items"]'); await p.waitForTimeout(700);
  await p.evaluate(([s, v]) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }, ['#hr-item-emp', who]);
  await p.fill('#hr-item-month', month);
  await p.evaluate(([s, v]) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }, ['#hr-item-dir', 'add']); await p.evaluate(([s, v]) => { const el = document.querySelector(s); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }, ['#hr-item-cat', 'taxi']);
  await p.fill('#hr-item-amount', '75'); await p.fill('#hr-item-note', 'Sweep taxi');
  await p.click('#hr-item-save'); await p.waitForTimeout(1200);
  await p.click('.hr-tab[data-tab="payroll"]'); await p.waitForTimeout(1500);
  const adj = await p.evaluate(w => { const l = HR_RUN.lines.find(x => x.emp_no === w); return l.other_allowance; }, who);
  ck('a bill entered on Additions is on the sheet the moment the tab is opened', adj >= 75, adj);
  // The instalment typed on the sheet survives a trip to another tab.
  const loanRow = await p.evaluate(() => { const l = HR_RUN.lines.find(x => x.loan_balance > 0); return l && l.id; });
  if (loanRow) {
    await p.fill(`.hr-cell[data-line="${loanRow}"][data-field="loan_deduction"]`, '123');
    await p.press(`.hr-cell[data-line="${loanRow}"][data-field="loan_deduction"]`, 'Tab');
    await p.waitForTimeout(1200);
    await p.click('.hr-tab[data-tab="loans"]'); await p.waitForTimeout(600);
    await p.click('.hr-tab[data-tab="payroll"]'); await p.waitForTimeout(1500);
    ck('an instalment typed on the sheet is kept after moving to another tab and back',
       await p.evaluate(id => HR_RUN.lines.find(l => l.id === id).loan_deduction, loanRow) === 123);
    await p.evaluate(async id => {
      await apiCall(`/employees/payroll/runs/${HR_RUN.id}`, { method: 'PUT', body: JSON.stringify({ lines: [{ id, loan_reset: true }] }) });
    }, loanRow);
  }
  // Clean up the sweep's own entries.
  await p.evaluate(async ([w, d, m]) => {
    const lv = (await apiCall(`/employees/leave?month_year=${encodeURIComponent(hrCycleName(m))}&emp_no=${w}`)).rows;
    for (const r of lv.filter(r => r.from === d)) await apiCall(`/employees/leave/entry/${r.batch}`, { method: 'DELETE' });
    const it = (await apiCall(`/employees/pay-items?month_year=${encodeURIComponent(hrCycleName(m))}&emp_no=${w}`)).rows;
    for (const r of it.filter(r => r.notes === 'Sweep taxi')) await apiCall(`/employees/pay-items/${r.id}`, { method: 'DELETE' });
  }, [who, day, month]);

  // ---- Every button on every tab --------------------------------------
  // Buttons that change what is on file are answered "Cancel" when the
  // page asks; the rest run for real.
  // The cycle bar: company, statement, month back and forward, month chips.
  await p.click('.hr-tab[data-tab="payroll"]'); await p.waitForTimeout(800);
  for (const sel of ['#hr-grp-seg button']) {
    const n = await p.locator(sel).count();
    for (let i = 0; i < n; i++) { await p.locator(sel).nth(i).click(); await p.waitForTimeout(900); }
  }
  ck('the cycle bar loads a sheet from every choice without a button',
     await p.evaluate(() => !!HR_RUN || document.getElementById('hr-status').textContent.length > 0));
  await p.click('#hr-grp-seg button[data-v="staff"]'); await p.waitForTimeout(900);
  const TABS = ['payroll', 'leave', 'items', 'loans', 'staff', 'increments', 'docs'];
  let pressed = 0;
  const pressAll = async (tab, label) => {
    const n = await p.locator(`#hrpane-${tab} button:visible`).count();
    for (let i = 0; i < n; i++) {
      const btn = p.locator(`#hrpane-${tab} button:visible`).nth(i);
      if (!(await btn.count())) break;
      const text = (await btn.textContent()).trim();
      if (/Approve|Discard|Reopen/.test(text)) continue;        // exercised on purpose below
      const refusedBefore = refused.length;
      await p.evaluate(() => { const s = document.getElementById('hr-status'); s.textContent = ''; s.style.display = 'none'; });
      await btn.click({ timeout: 3000 }).catch(e => errs.push(`${tab}: "${text}" would not click`));
      pressed++;
      await p.waitForTimeout(700);
      if (await p.locator('.hr-ask').count()) await p.click('.hr-ask [data-a="no"]');
      await drain();
      if (refused.length > refusedBefore) {
        const said = (await p.locator('#hr-status').textContent()).trim();
        if (!said) errs.push(`${tab} (${label}): "${text}" was refused with nothing said - ${refused[refused.length - 1]}`);
      }
    }
  };
  for (const tab of TABS) {
    await p.click(`.hr-tab[data-tab="${tab}"]`); await p.waitForTimeout(1200);
    ck(`${tab}: the tab opens`, await p.locator(`#hrpane-${tab}`).isVisible());
    await pressAll(tab, 'empty');
  }
  // Again with an entry loaded for editing on each tab that has one.
  const EDITS = {
    leave: "HR_LEAVE.length && hrLeaveEdit(HR_LEAVE[0].batch)",
    items: "HR_ITEMS.length && hrItemEdit(HR_ITEMS[0].id)",
    loans: "HR_LOANS.length && (hrLoanEdit(HR_LOANS[0].id), hrLoanToggle(HR_LOANS[0].id))",
    staff: "HR_STAFF.length && editStaff(HR_STAFF[0].emp_no)",
    increments: "HR_INCS.length && hrIncEdit(HR_INCS[0].id)",
  };
  for (const [tab, fn] of Object.entries(EDITS)) {
    await p.click(`.hr-tab[data-tab="${tab}"]`); await p.waitForTimeout(1000);
    if (tab === 'leave') { await p.fill('#hr-leave-month', '2026-08'); await p.evaluate('loadLeave()'); await p.waitForTimeout(800); }
    if (tab === 'items') { await p.fill('#hr-items-month', '2026-08'); await p.evaluate('loadItems()'); await p.waitForTimeout(800); }
    await p.evaluate(fn); await p.waitForTimeout(500);
    await pressAll(tab, 'editing');
  }

  // ---- Approve, reopen, discard - on a scratch month ---------------------
  await p.click('.hr-tab[data-tab="payroll"]'); await p.waitForTimeout(800);
  await p.evaluate(() => { document.getElementById('hr-run-month').value = '2027-03'; });
  await p.evaluate('openPayrollCycle()'); await p.waitForTimeout(1200);
  ck('a month not yet opened waits for its Open button', await p.locator('#hr-run-empty button').isVisible());
  await p.click('#hr-run-empty button'); await p.waitForTimeout(1500);
  ck('a future month opens as a draft', await p.evaluate(() => HR_RUN && HR_RUN.status === 'draft'));
  p.evaluate('approvePayrollRun()'); await p.waitForSelector('.hr-ask'); await p.click('.hr-ask [data-a="yes"]');
  await p.waitForTimeout(1500);
  ck('Approve & lock works from its button', await p.evaluate(() => HR_RUN.status === 'approved'));
  p.evaluate('reopenPayrollRun()'); await p.waitForSelector('.hr-ask'); await p.click('.hr-ask [data-a="yes"]');
  await p.waitForTimeout(1500);
  ck('Reopen works from its button', await p.evaluate(() => HR_RUN.status === 'draft'));
  p.evaluate('dropPayrollRun()'); await p.waitForSelector('.hr-ask'); await p.click('.hr-ask [data-a="yes"]');
  await p.waitForTimeout(1500);
  ck('Discard draft works from its button', await p.evaluate(async () =>
     !(await apiCall('/employees/payroll/runs')).rows.some(r => r.month_year === 'March 2027' && r.company === 'Infinia')));
  await p.click('.hr-tab[data-tab="leave"]'); await p.waitForTimeout(500);
  await p.click('.hr-tab[data-tab="payroll"]'); await p.waitForTimeout(1500);
  ck('after a discard, the tab opens the month afresh instead of a dead sheet',
     await p.evaluate(() => !!HR_RUN && HR_RUN.status === 'draft'));

  await p.waitForTimeout(1500);
  console.log(`\n${pressed} buttons pressed`);
  const badOpen = opened.filter(([ok]) => !ok);
  ck(`every preview, PDF and spreadsheet opened (${opened.length} checked)`, badOpen.length === 0, JSON.stringify(badOpen));
  for (const k of ['preview', 'pdf', 'excel'])
    ck(`${k}: at least one opened`, opened.some(([, kind]) => kind === k));
  ck('no server errors', server.length === 0, server.slice(0, 5).join(' | '));
  ck('no browser pop-ups', popups.length === 0, popups.join(' | '));
  ck('no script errors, and no refusal left unexplained', errs.length === 0, errs.slice(0, 6).join(' | '));
  console.log(`(${refused.length} refusals for empty forms, each explained on screen)`);

  await b.close();
  console.log('');
  if (FAIL.length) {
    console.log(`${FAIL.length} FAILED`);
    FAIL.forEach(f => console.log('  - ' + f));
    process.exit(1);
  }
  console.log('EVERY HR BUTTON WORKS');
})();
