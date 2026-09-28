// Paying before the month / cycle ends: one button puts every sheet on the
// whole month's salary (office and local staff) and every labour card on
// the whole cycle's salary; pressing again puts it back to date.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=payroll#hrpayroll'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(4500);
  const grand = () => p.evaluate(() => { const r = Object.values(HR_ALL_RUNS)[0]; return r && { running: r.progress.running, head: document.querySelector('#hr-all-body th.num.net, #hr-all-body th:nth-last-child(2)') && [...document.querySelectorAll('#hr-all-body thead th')].map(t => t.textContent.trim()).join('|') }; });
  for (const g of ['staff', 'local']) {
    await p.click(`#hr-grp-seg button[data-v="${g}"]`); await p.waitForTimeout(3500);
    const before = await grand();
    ck(`${g}: mid-month the sheet shows the salary to date and the button is offered`, before.running && await p.locator('#hr-run-all .hr-full-btn').isVisible(), before);
    if (g === 'staff') await p.screenshot({ path: SH + 'early-1-office-before.png' });
    await p.locator('#hr-run-all .hr-full-btn').click(); await p.waitForTimeout(500);
    if (g === 'staff') await p.screenshot({ path: SH + 'early-2-office-confirm.png' });
    await p.locator('.hr-ask [data-a="yes"]').click(); await p.waitForTimeout(3500);
    const after = await grand();
    ck(`${g}: after "Pay full month now" every sheet is on the full month (Net Pay)`, !after.running && /NET PAY/i.test(after.head), after);
    if (g === 'staff') await p.screenshot({ path: SH + 'early-3-office-after.png' });
  }
  const pdfTitle = await p.evaluate(async () => { const t = await hrToken(); const x = await fetch(`/export/payroll/consolidated/view?month_year=September%202026&group=local&token=${t}`); return await x.text(); });
  ck('the local statement preview is Net Pay, not Salary To Date', !/Salary To Date/.test(pdfTitle));
  // undo
  await p.locator('#hr-run-all .hr-full-btn').click(); await p.waitForTimeout(3500);
  ck('pressing again puts it back to the salary to date', (await grand()).running);
  // ---- labour ----
  await p.locator('#pg-tabs .pg-tab', { hasText: 'Labour payroll' }).click(); await p.waitForTimeout(1500); await p.locator('#pg-sub .pg-subtab', { hasText: 'Salary cards' }).click(); await p.waitForTimeout(2500);
  const cyc = await p.inputValue('#combine-cycle');
  const tot = async () => (await p.evaluate(async c => apiCall(`/summaries/${encodeURIComponent(c)}`), cyc));
  const s0 = await tot(); const sum0 = s0.reduce((a, s) => a + s.final_salary, 0);
  ck(`labour ${cyc}: the button is offered mid-cycle`, await p.locator('#lab-full-btn').isVisible());
  await p.screenshot({ path: SH + 'early-4-labour-before.png' });
  await p.click('#lab-full-btn'); await p.waitForTimeout(400); await p.locator('.hr-ask [data-a="yes"]').click(); await p.waitForTimeout(5000);
  const s1 = await tot(); const sum1 = s1.reduce((a, s) => a + s.final_salary, 0);
  const one = s1.find(s => s.emp_no === 'T-905'), fixed = s1.find(s => s.emp_no === 'T-906');
  ck(`labour cards rise to the full cycle (${Math.round(sum0)} -> ${Math.round(sum1)})`, sum1 > sum0 * 1.5, { sum0, sum1 });
  ck('a worker with no absences gets his full salary (T-906 fixed 3,100)', fixed && Math.abs(fixed.final_salary - 3100) < 1 + (fixed.ot_amount || 0) + (fixed.bh_amount || 0) || (fixed && fixed.absent_days > 0), fixed && [fixed.final_salary, fixed.absent_days]);
  ck('the leaver T-902 is not paid past his last day', !s1.find(s => s.emp_no === 'T-902') || s1.find(s => s.emp_no === 'T-902').present_days <= s0.find(s => s.emp_no === 'T-902').present_days);
  await p.screenshot({ path: SH + 'early-5-labour-after.png' });
  await p.click('#lab-full-btn'); await p.waitForTimeout(5000);
  const sum2 = (await tot()).reduce((a, s) => a + s.final_salary, 0);
  ck('Back to salary to date restores the cards exactly', Math.abs(sum2 - sum0) < 0.01, { sum0, sum2 });
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'PAY EARLY, FULL SALARY - HOLDS UP');
  await b.close(); process.exit(bad ? 1 : 0);
})();
