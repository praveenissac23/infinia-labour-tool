// Payroll > Office payroll opens on All companies with every company's
// sheet editable in place: a remark, a loan instalment or a hold typed in
// one company's section is saved to that company's sheet (and no other),
// its totals and the grand total follow at once, and each company is
// approved and reopened on its own. It is drawn once - no flicker.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); let bad = 0; const errs = [];
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => { errs.push('pop-up ' + d.message()); d.dismiss(); });
  await p.goto(B + '/?p=payroll'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2000);
  await p.evaluate(() => { window.__f = []; const t0 = performance.now(); (function tick() { const c = document.getElementById('hr-run-all'); const h = c && getComputedStyle(c).display !== 'none' && c.closest('.screen.active') ? Math.round(c.getBoundingClientRect().height) : 0; window.__f.push(h); if (performance.now() - t0 < 4000) requestAnimationFrame(tick); })(); });
  await p.click('#pg-tabs .pg-tab[data-tab="hrpayroll"]'); await p.waitForTimeout(4200);
  const f = await p.evaluate(() => window.__f); const shownStates = [...new Set(f.filter(h => h > 0))];
  ck('opens on All companies, drawn once (no empty card, no Loading)', shownStates.length === 1 && shownStates[0] > 300, shownStates);
  ck('the single-company sheet is not shown', !(await p.locator('#hr-run-card').isVisible()));
  const secs = p.locator('#hr-all-body [data-run]');
  const n = await secs.count(); ck(`every company with staff has an editable sheet (${n})`, n >= 2, n);
  ck('no "Open for editing" link any more', await p.locator('#hr-all-body a', { hasText: 'Open for editing' }).count() === 0);
  const runIds = await secs.evaluateAll(els => els.map(e => Number(e.dataset.run)));
  const api = x => p.evaluate(async u => apiCall(u), x);
  // remark in the second company
  const sec2 = secs.nth(1); const rem = sec2.locator('textarea.hr-rem').first();
  const line2 = Number(await rem.getAttribute('data-line'));
  await rem.fill('Test remark company 2'); await rem.blur(); await p.waitForTimeout(1500);
  const r2 = await api(`/employees/payroll/runs/${runIds[1]}`); const r1 = await api(`/employees/payroll/runs/${runIds[0]}`);
  ck('a remark typed in the 2nd company is saved to that company\'s sheet', (r2.lines.find(l => l.id === line2) || {}).remarks === 'Test remark company 2');
  ck('and not to the 1st company', !r1.lines.some(l => l.remarks === 'Test remark company 2'));
  // loan instalment, wherever a loan box is
  const loanBox = p.locator('#hr-all-body input[data-field="loan_deduction"]').first();
  if (await loanBox.count()) {
    const lid = Number(await loanBox.getAttribute('data-line'));
    const runOf = Number(await loanBox.evaluate(e => e.closest('[data-run]').dataset.run));
    const grandBefore = await p.locator('#hr-all-grand').textContent();
    await loanBox.fill('1000'); await p.waitForTimeout(300);
    const net = await p.locator(`#hr-net-${lid}`).textContent();
    const grandMid = await p.locator('#hr-all-grand').textContent();
    ck('typing a loan instalment updates that row\'s net pay and the grand total at once', grandMid !== grandBefore, { net, grandBefore: grandBefore.slice(0, 80), grandMid: grandMid.slice(0, 80) });
    await loanBox.blur(); await p.waitForTimeout(1500);
    const rr = await api(`/employees/payroll/runs/${runOf}`); const line = rr.lines.find(l => l.id === lid);
    ck('the instalment is saved to that company\'s sheet', line && Number(line.loan_deduction) === 1000, line && line.loan_deduction);
    // While the month is running the column is Salary To Date; after it, Net Pay.
    const want = rr.progress && rr.progress.running ? line.to_date : line.net_pay;
    const shownNow = (await p.locator(`#hr-net-${lid}`).textContent()).replace(/,/g, '');
    ck(`the figure on screen matches the server (${rr.progress && rr.progress.running ? 'salary to date' : 'net pay'} ${want}; net pay ${line.net_pay} = ${line.payable} - ${line.loan_deduction})`,
       line && Math.abs(Number(want) - Number(shownNow)) < 0.01 && Math.abs(line.payable - line.loan_deduction + (line.leave_salary || 0) + (line.air_ticket || 0) - line.net_pay) < 0.01, { server: want, screen: shownNow });
  } else console.log('(no loan box on this month - skipped)');
  // hold a salary in company 2
  const hold = secs.nth(1).locator('tbody input[type=checkbox]').first(); const hl = Number(await hold.evaluate(e => e.closest('tr').dataset.line));
  await hold.uncheck(); await p.waitForTimeout(1500);
  const rh = await api(`/employees/payroll/runs/${runIds[1]}`);
  ck('unticking Pay holds that salary on that company\'s sheet', (rh.lines.find(l => l.id === hl) || {}).held === true);
  await secs.nth(1).locator(`tr[data-line="${hl}"] input[type=checkbox]`).check(); await p.waitForTimeout(1500);
  // approve company 1 only, then reopen
  await secs.nth(0).locator('button', { hasText: 'Approve' }).click(); await p.waitForTimeout(500);
  await p.locator('.hr-ask [data-a="yes"], .ask [data-a="yes"]').first().click().catch(() => {}); await p.waitForTimeout(2000);
  const a1 = await api(`/employees/payroll/runs/${runIds[0]}`), a2 = await api(`/employees/payroll/runs/${runIds[1]}`);
  ck('Approve on the 1st company locks that sheet only', a1.status === 'approved' && a2.status !== 'approved', [a1.status, a2.status]);
  ck('its section shows locked, with no boxes to type in', await secs.nth(0).locator('.hr-badge.ok').count() === 1 && await secs.nth(0).locator('textarea, input[type=text]').count() === 0);
  await secs.nth(0).locator('button', { hasText: 'Reopen' }).click(); await p.waitForTimeout(500);
  await p.locator('.hr-ask [data-a="yes"], .ask [data-a="yes"]').first().click().catch(() => {}); await p.waitForTimeout(2000);
  ck('Reopen puts it back to draft', (await api(`/employees/payroll/runs/${runIds[0]}`)).status === 'draft');
  // switch away and back: still no flicker, figures kept
  await p.locator('.pg-subtab', { hasText: 'Absence' }).click(); await p.waitForTimeout(1200);
  await p.evaluate(() => { window.__f = []; const t0 = performance.now(); (function tick() { const c = document.getElementById('hr-run-all'); window.__f.push(c && getComputedStyle(c).display !== 'none' && c.closest('.screen.active') && !c.closest('.pg-hide') ? Math.round(c.getBoundingClientRect().height) : 0); if (performance.now() - t0 < 3000) requestAnimationFrame(tick); })(); });
  await p.locator('.pg-subtab', { hasText: 'Salary cycle' }).click(); await p.waitForTimeout(3200);
  const f2 = [...new Set((await p.evaluate(() => window.__f)).filter(h => h > 0))];
  ck('coming back to it from Absence draws it once', f2.length === 1, f2);
  ck('the remark is still there after coming back', await secs.nth(1).locator('textarea.hr-rem').first().inputValue() === 'Test remark company 2');
  // one company still opens as its own sheet from the picker
  await p.selectOption('#hr-run-company', { index: 1 }); await p.dispatchEvent('#hr-run-company', 'change'); await p.waitForTimeout(2500);
  ck('picking one company opens its own sheet', await p.locator('#hr-run-card').isVisible() && !(await p.locator('#hr-run-all').isVisible()));
  await p.selectOption('#hr-run-company', ''); await p.dispatchEvent('#hr-run-company', 'change'); await p.waitForTimeout(2500);
  ck('and All companies comes back editable', await p.locator('#hr-run-all').isVisible() && await secs.count() >= 2);
  ck('no script errors or pop-ups', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'EVERY COMPANY EDITABLE IN PLACE, NO FLICKER');
  await b.close(); process.exit(bad ? 1 : 0);
})();
