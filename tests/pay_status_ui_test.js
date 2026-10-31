// Paid status & payslips in a real browser - office sheet, All companies,
// labour Salary cards and the Staff profile Payslips tab. Saves screenshots
// to $SHOTS (default /tmp/claude-0/payshots/).
// Run: /tmp/claude-0/run_on.sh /tmp/claude-0/full.db 8082 tests/pay_status_ui_test.js
// The sheet must still be running (salary to date short of the month) for a Regular payment to leave a
// balance, so the server is started believing it is mid-October 2026:
//   SRV_TODAY=2026-10-20 python3 tests/serve_like_nginx.py   (from 31 October 2026 the month is over and
//   salary to date = the month's net pay, which is why this failed without it)
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8082';
const SH = (process.env.SHOTS || '/tmp/claude-0/payshots') + '/';
fs.mkdirSync(SH, { recursive: true });
let bad = 0;
const ck = (m, c, x) => { console.log((c ? 'PASS ' : 'FAIL ') + m + (c ? '' : '  [' + JSON.stringify(x) + ']')); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1600, height: 1000 }, acceptDownloads: true });
  const errs = [];
  let p = await ctx.newPage();
  p.on('pageerror', e => errs.push(String(e).slice(0, 200)));
  p.on('dialog', d => d.accept('Entered twice by mistake'));
  await p.goto(B + '/app-classic.html');
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123');
  await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 }); await sleep(1500);
  await p.evaluate("localStorage.setItem('infinia_hr_tab', 'payroll')");
  await p.evaluate("switchScreen('hrpayroll')"); await sleep(2500);
  const infinia = await p.evaluate(() => (HR_COMPANIES.find(c => c.short_name === 'Infinia') || HR_COMPANIES[0]).id);
  await p.evaluate(i => { document.getElementById('hr-run-company').value = i; }, infinia);
  await p.evaluate(() => { document.getElementById('hr-run-month').value = '2026-10'; });
  // the sheet on salary to date, so a regular payment leaves a balance
  await p.evaluate(async () => { try { await apiCall('/employees/payroll/full-month', { method: 'POST', body: JSON.stringify({ month_year: 'October 2026', group: 'staff', on: false }) }); } catch (e) {} });
  await p.evaluate('openPayrollCycle()'); await sleep(2500);

  ck('October 2026 is still running on the server (start it with SRV_TODAY=2026-10-20)',
     await p.evaluate(() => !!(HR_RUN && HR_RUN.progress && HR_RUN.progress.running)));
  const heads = await p.$$eval('#hr-run-head th', x => x.map(t => t.textContent.trim()));
  ck('office sheet: Paid after the salary column, Payslip last', heads.indexOf('Paid') === heads.findIndex(h => /Salary To Date|Net Pay/.test(h)) + 1 && heads[heads.length - 1] === 'Payslip', heads);
  const n = await p.locator('#hr-run-body button.pay-btn').count();
  ck('every unpaid PAY-ticked row offers Mark paid', n >= 3, n);
  await p.screenshot({ path: SH + '01_office_sheet.png' });

  // the first row: someone whose salary to date is still short of the month
  const lines = await p.evaluate(() => { const all = HR_RUN.lines.filter(l => !l.held && l.net_pay > 0);
    const first = all.find(l => l.to_date < l.net_pay - 1) || all[0];
    return [first].concat(all.filter(l => l !== first)).map(l => ({ id: l.id, name: l.name })); });
  // 1. Regular (salary to date)
  await p.click(`#hr-run-body tr[data-line="${lines[0].id}"] button.pay-btn`); await sleep(1200);
  ck('Mark paid dialog opens with the four kinds', (await p.$$eval('#pay-types input', x => x.map(i => i.value))).join() === 'regular,early_full,final,custom');
  await p.fill('#pay-ref', 'WPS-OCT-001');
  await sleep(800);
  const prev = await p.textContent('#pay-preview');
  ck('the dialog shows what is to be paid now', /To pay now/.test(prev), prev);
  await p.locator('#pay-modal > div').screenshot({ path: SH + '02_dialog_regular.png' });
  await p.click('#pay-go'); await sleep(2500);
  let cell = await p.textContent(`#hr-run-body tr[data-line="${lines[0].id}"] td.pay-cell`);
  ck('salary to date paid: part paid, balance and Pay balance', /Part paid/.test(cell) && /Pay balance/.test(cell), cell);
  const slipCell = await p.textContent(`#hr-run-body tr[data-line="${lines[0].id}"] td.pay-slip`);
  ck('payslip generated with the payment: View / Download v1', /View/.test(slipCell) && /v1/.test(slipCell), slipCell);

  // 2. Early full month
  await p.click(`#hr-run-body tr[data-line="${lines[1].id}"] button.pay-btn`); await sleep(900);
  await p.check('#pay-types input[value="early_full"]'); await sleep(900);
  await p.selectOption('#pay-mode', 'bank'); await p.fill('#pay-ref', 'TRF-55120');
  await p.locator('#pay-modal > div').screenshot({ path: SH + '03_dialog_early.png' });
  await p.click('#pay-go'); await sleep(2500);
  cell = await p.textContent(`#hr-run-body tr[data-line="${lines[1].id}"] td.pay-cell`);
  ck('early full month: Paid badge with date, type and mode', /Paid/.test(cell) && /Early full month/.test(cell) && /Bank transfer/.test(cell), cell);
  ck('the paid row is locked - no boxes to type in', await p.locator(`#hr-run-body tr[data-line="${lines[1].id}"] input.hr-cell, #hr-run-body tr[data-line="${lines[1].id}"] textarea`).count() === 0);

  // 3. Final settlement dialog (preview from the Gratuity working)
  await p.click(`#hr-run-body tr[data-line="${lines[2].id}"] button.pay-btn`); await sleep(900);
  await p.check('#pay-types input[value="final"]');
  await p.fill('#pay-last', '2026-10-28'); await p.dispatchEvent('#pay-last', 'change'); await sleep(1800);
  const fprev = await p.textContent('#pay-preview');
  ck('final settlement preview lists the settlement lines', /Gratuity/i.test(fprev) && /To pay now/.test(fprev), fprev);
  await p.locator('#pay-modal > div').screenshot({ path: SH + '04_dialog_final.png' });
  await p.click('#pay-go'); await sleep(800);
  await p.click('.hr-ask-box [data-a="yes"]'); await sleep(3000);
  cell = await p.textContent(`#hr-run-body tr[data-line="${lines[2].id}"] td.pay-cell`);
  ck('final settlement: Settled', /Settled/.test(cell), cell);
  const fslip = await p.textContent(`#hr-run-body tr[data-line="${lines[2].id}"] td.pay-slip`);
  ck('final settlement gets the settlement slip', /settlement/.test(fslip), fslip);

  // 4. Bulk: tick, Mark selected as paid
  const rest = lines.slice(3, 6).map(l => l.id);
  for (const id of rest) await p.check(`#hr-run-body tr[data-line="${id}"] input.pay-pick`);
  await p.click('#hr-pay-sel'); await sleep(900);
  ck('bulk dialog names how many', /Mark 3 as paid/.test(await p.textContent('#pay-go')) || rest.length < 3, await p.textContent('#pay-go'));
  await p.fill('#pay-ref', 'WPS-OCT-BATCH');
  await p.locator('#pay-modal > div').screenshot({ path: SH + '05_dialog_bulk.png' });
  await p.click('#pay-go'); await sleep(3000);
  // 5. Generate payslips for the company
  await p.click('#hr-pay-slips'); await sleep(3000);
  const gen = await p.locator('#hr-run-body td.pay-slip button.pay-btn').count();
  ck('Generate payslips: every payment has its payslip', gen === 0, gen);
  // a second version, never written over
  await p.click(`#hr-run-body tr[data-line="${lines[0].id}"] td.pay-slip a.v`); await sleep(2000);
  ck('a payslip generated again is v2', /v2/.test(await p.textContent(`#hr-run-body tr[data-line="${lines[0].id}"] td.pay-slip`)));
  await p.evaluate(() => document.querySelector('#hr-run-card').scrollIntoView());
  await p.screenshot({ path: SH + '06_office_after.png' });
  await p.locator('#hr-run-card').screenshot({ path: SH + '06b_office_card.png' });

  // ZIP
  const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 20000 }), p.click('text=Download all payslips (ZIP) >> visible=true')]);
  const zp = SH + 'office.zip'; await dl.saveAs(zp);
  ck('Download all payslips (ZIP)', fs.statSync(zp).size > 2000);

  // The payslip PDFs themselves
  const ids = await p.evaluate(() => HR_RUN.lines.flatMap(l => Object.values((l.pay && l.pay.slips) || {}).flat()).map(s => ({ id: s.id, type: s.type })));
  const tok = await p.evaluate(async () => decodeURIComponent(await hrToken()));
  const save = async (id, f) => { const r = await p.request.get(`${B}/export/pay/payslip/${id}?token=${encodeURIComponent(tok)}`); fs.writeFileSync(SH + f, await r.body()); };
  await save(ids.find(x => x.type === 'payslip').id, 'office_payslip.pdf');
  await save(ids.find(x => x.type === 'settlement').id, 'settlement_slip.pdf');

  const emp = await p.evaluate(id => HR_RUN.lines.find(l => l.id === id).emp_no, lines[0].id);
  // 6. All companies
  await p.evaluate(() => { document.getElementById('hr-run-company').value = ''; });
  await p.evaluate('openPayrollCycle()'); await sleep(4000);
  ck('All companies: per-company Mark selected as paid / Generate payslips', await p.locator('#hr-all-body .pay-bulk').count() >= 1);
  ck('All companies shows the same paid badges', await p.locator('#hr-all-body .pay-ok, #hr-all-body .pay-fin').count() >= 2);
  await p.locator('#hr-run-all').screenshot({ path: SH + '07_all_companies.png' });

  // cancel a payment entered by mistake
  const before = await p.locator('#hr-all-body .pay-x').count();
  await p.locator('#hr-all-body .pay-x').last().click(); await sleep(3000);
  ck('a payment entered by mistake can be cancelled', await p.locator('#hr-all-body .pay-x').count() === before - 1);

  // 7. Labour - Salary cards
  await p.evaluate("switchScreen('combine')"); await sleep(1500);
  await p.evaluate(() => { const s = document.getElementById('combine-cycle'); s.value = 'October 2026'; s.dispatchEvent(new Event('change')); }); await sleep(3500);
  const lrows = await p.locator('#lab-pay-body tbody tr').count();
  ck('labour: every card of the cycle by company', lrows > 20, lrows);
  const gi = await p.evaluate(() => PAY_LAB.groups.reduce((b, g, i) => g.rows.length > PAY_LAB.groups[b].rows.length ? i : b, 0));
  const lab = await p.evaluate(i => PAY_LAB.groups[i].rows.slice(0, 5).map(x => x.source_id), gi);
  await p.click(`#lab-pay-body button.pay-btn[onclick="payOpen('labour', ${lab[0]})"]`); await sleep(1200);
  await p.locator('#pay-modal > div').screenshot({ path: SH + '08_labour_dialog.png' });
  await p.click('#pay-go'); await sleep(2500);
  for (const id of lab.slice(1, 4)) await p.check(`#lab-pay-body input.pay-pick[data-id="${id}"]`);
  console.log('lab checked before:', await p.locator('#lab-pay-body input.pay-pick:checked').count(), lab);
  await p.locator(`#lab-pay-body [data-labco="${gi}"] .pay-bulk button`).first().click(); await sleep(900);
  console.log('lab status:', await p.textContent('#lab-pay-status'), await p.locator('#lab-pay-body input.pay-pick:checked').count());
  await p.selectOption('#pay-mode', 'cash'); await p.click('#pay-go'); await sleep(3500);
  await p.locator(`#lab-pay-body [data-labco="${gi}"] .pay-bulk button`).nth(1).click(); await sleep(3500);
  const lpaid = await p.locator('#lab-pay-body .pay-ok').count();
  ck('labour: paid badges after Mark paid and bulk', lpaid >= 4, lpaid);
  await p.evaluate(() => document.getElementById('lab-pay-card').scrollIntoView());
  await p.locator('#lab-pay-card').screenshot({ path: SH + '09_labour_card.png' });
  const lslip = await p.evaluate(i => PAY_LAB.groups[i].rows.flatMap(x => Object.values(x.pay.slips || {}).flat())[0], gi);
  if (lslip) await save(lslip.id, 'labour_payslip.pdf');
  ck('labour payslip generated', !!lslip);

  // 8. Staff profile > Payslips tab
  const q = await ctx.newPage(); q.on('pageerror', e => errs.push(String(e).slice(0, 200)));
  await q.goto(B + '/portal/people.html'); await sleep(1200);
  if (await q.isVisible('#login-username')) { await q.fill('#login-username', 'admin'); await q.fill('#login-password', 'changeme123'); await q.click('#login button'); await sleep(2500); }
  await q.evaluate(async c => { P.group = 'office'; try { await openPerson(c); } catch (e) {} }, emp); await sleep(1500);
  await q.evaluate(() => setSection('payslips')); await sleep(2000);
  const ptxt = await q.textContent('#file');
  ck('Staff profile has a Payslips tab listing every version', /Payslips/.test(ptxt) && /v2/.test(ptxt) && /v1/.test(ptxt), ptxt.slice(0, 300));
  await q.locator('#file').screenshot({ path: SH + '10_profile_payslips.png' });

  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
