// PAY = who goes on the Preview / Export / Pay full month now (office) and on the salary card exports
// (labour). Paid people drop off the selection and the Preview; ticked again they print with
// "Already paid". Select all with ticked / dash / empty states. Hold is its own link and still works.
// Run: /tmp/claude-0/run_on.sh /tmp/claude-0/full.db 8082 tests/pay_select_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8082';
const SH = (process.env.SHOTS || '/tmp/claude-0/selshots') + '/';
require('fs').mkdirSync(SH, { recursive: true });
let bad = 0;
const ck = (m, c, x) => { console.log((c ? 'PASS ' : 'FAIL ') + m + (c ? '' : '  [' + JSON.stringify(x).slice(0, 400) + ']')); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1600, height: 1000 } });
  const errs = []; const p = await ctx.newPage();
  p.on('pageerror', e => errs.push(String(e).slice(0, 200)));
  await p.goto(B + '/app-classic.html');
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123');
  await p.evaluate('doLogin()'); await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 }); await sleep(1500);
  await p.evaluate(() => { window.__opened = []; window.open = u => { window.__opened.push(u); return null; }; });
  const lastUrl = () => p.evaluate(() => window.__opened[window.__opened.length - 1] || '');
  const getText = u => p.evaluate(async u => (await fetch(u)).text(), u);
  await p.evaluate("localStorage.setItem('infinia_hr_tab', 'payroll')");
  await p.evaluate("switchScreen('hrpayroll')"); await sleep(2500);
  const infinia = await p.evaluate(() => (HR_COMPANIES.find(c => c.short_name === 'Infinia') || HR_COMPANIES[0]).id);
  await p.evaluate(async () => { try { await apiCall('/employees/payroll/full-month', { method: 'POST', body: JSON.stringify({ month_year: 'October 2026', group: 'staff', on: false }) }); } catch (e) {} });
  await p.evaluate(i => { document.getElementById('hr-run-company').value = i; document.getElementById('hr-run-month').value = '2026-10'; }, infinia);
  await p.evaluate('openPayrollCycle()'); await sleep(2500);

  const st = () => p.evaluate(() => ({ ticked: [...document.querySelectorAll('#hr-run-body input.hr-pick:checked')].map(x => +x.dataset.line),
    boxes: document.querySelectorAll('#hr-run-body input.hr-pick').length,
    all: (b => ({ c: b.checked, i: b.indeterminate }))(document.querySelector('#hr-run-card .hr-pay-all')),
    foot: document.querySelector('#hr-run-foot td').textContent.trim(), prevDis: document.querySelector('#hr-run-card .hr-needs-sel').disabled }));
  let s = await st();
  const L = await p.evaluate(() => HR_RUN.lines.filter(l => !l.held && !(l.pay && l.pay.locked)).map(l => ({ id: l.id, name: l.name, emp: l.employee_id })));
  ck('on opening: every unpaid row ticked, Select all ticked', s.ticked.length === L.length && s.all.c && !s.all.i, s);
  ck('TOTAL counts the ticked staff', new RegExp(`TOTAL - ${L.length} of`).test(s.foot), s.foot);
  await p.screenshot({ path: SH + '01_office_all_ticked.png' });

  // (a) mark one paid in full -> PAY unticks -> Preview leaves him out
  const a = L[0];
  await p.click(`#hr-run-body tr[data-line="${a.id}"] button.pay-btn`); await sleep(1000);
  await p.check('#pay-types input[value="early_full"]'); await sleep(800);
  await p.click('#pay-go'); await sleep(3000);
  s = await st();
  ck('(a) marked paid -> his PAY unticks by itself', !s.ticked.includes(a.id) && s.ticked.length === L.length - 1, s);
  ck('(a) Select all shows ticked (every unpaid one is ticked)', s.all.c && !s.all.i, s.all);
  await p.evaluate('previewStatement()'); await sleep(500);
  let u = await lastUrl(), html = await getText(u);
  ck('(a) Preview sends only the ticked staff', /emps=/.test(u) && !u.split('emps=')[1].split(',').map(Number).includes(a.emp), u);
  ck('(a) Preview leaves the paid person out', !html.includes(a.name) && html.includes(L[1].name), a.name);
  await p.screenshot({ path: SH + '02_office_paid_unticked.png' });

  // (b) tick him again -> in the Preview, marked Already paid
  await p.check(`#hr-run-body input.hr-pick[data-line="${a.id}"]`); await sleep(400);
  await p.evaluate('previewStatement()'); await sleep(500);
  html = await getText(await lastUrl());
  ck('(b) re-ticked: in the Preview with "Already paid"', html.includes(a.name + '  (Already paid)') || html.includes(a.name + ' (Already paid)') || new RegExp(a.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s+\\(Already paid\\)').test(html), html.slice(0, 300));
  await p.evaluate("downloadStatement('excel')"); await sleep(400);
  u = await lastUrl();
  const xr = await p.evaluate(async u => { const r = await fetch(u); return [r.status, (await r.arrayBuffer()).byteLength]; }, u);
  ck('(b) Export Excel follows the ticks too', /format=excel/.test(u) && /emps=/.test(u) && xr[0] === 200, [u, xr]);

  // (c) Select all: off / dash / on
  await p.click('#hr-run-card .hr-pay-all'); await sleep(400); s = await st();
  ck('(c) Select all again: everyone unticked, box empty', s.ticked.length === 0 && !s.all.c && !s.all.i, s);
  ck('(c) nothing ticked: Preview / Export disabled', s.prevDis, s);
  ck('(c) TOTAL shows 0 ticked', /TOTAL - 0 of/.test(s.foot), s.foot);
  await p.check(`#hr-run-body input.hr-pick[data-line="${L[1].id}"]`); await sleep(300); s = await st();
  ck('(c) one ticked: Select all shows the dash', !s.all.c && s.all.i && !s.prevDis, s.all);
  await p.screenshot({ path: SH + '03_office_indeterminate.png' });
  await p.click('#hr-run-card .hr-pay-all'); await sleep(400); s = await st();
  ck('(c) Select all: every unpaid ticked, the paid one stays unticked', s.ticked.length === L.length - 1 && !s.ticked.includes(a.id) && s.all.c, s);

  // Hold is its own link: holds and releases; held is off the selection
  await p.click(`#hr-run-body tr[data-line="${L[2].id}"] .hr-hold-link`); await sleep(1500);
  s = await st();
  ck('Hold link holds the salary - row shows held, no PAY box', !(await p.$(`#hr-run-body input.hr-pick[data-line="${L[2].id}"]`)) && /held over/.test(s.foot), s.foot);
  await p.click(`#hr-run-body tr[data-line="${L[2].id}"] .hr-hold-link`); await sleep(1500);
  s = await st();
  ck('Held - release puts him back, ticked', s.ticked.includes(L[2].id) && !/held over/.test(s.foot), s);

  // Pay full month now: only the ticked rows
  const fm = await p.evaluate(() => !!document.querySelector('#hr-run-card .hr-full-btn') && document.querySelector('#hr-run-card .hr-full-btn').style.display !== 'none');
  if (fm) {
    await p.click('#hr-run-card .hr-pay-all'); await sleep(300);     // untick all
    await p.check(`#hr-run-body input.hr-pick[data-line="${L[1].id}"]`); await sleep(200);
    await p.click('#hr-run-card .hr-full-btn'); await sleep(800);
    await p.click('.hr-ask-box [data-a="yes"]'); await sleep(3500);
    const f = await p.evaluate(([x, y]) => HR_RUN.lines.filter(l => [x, y].includes(l.id)).map(l => [l.id, l.full_month, l.to_date === l.net_pay]), [L[1].id, L[3].id]);
    const r1 = f.find(x => x[0] === L[1].id), r3 = f.find(x => x[0] === L[3].id);
    ck('Pay full month now: the ticked row on the full month, an unticked one stays on salary to date', r1 && r1[1] && r1[2] && r3 && !r3[1], f);
    ck('the full-month row is tagged "Full month"', /Full month/.test(await p.textContent(`#hr-run-body tr[data-line="${L[1].id}"]`)));
    await p.screenshot({ path: SH + '04_office_full_month_ticked.png' });
    await p.click('#hr-run-card .hr-full-btn'); await sleep(3000);     // back to salary to date
  } else console.log('SKIP full month (not early in the month)');

  // All companies: one Select all for every company; Preview / Export follow it
  await p.evaluate(() => { document.getElementById('hr-run-company').value = ''; }); await p.evaluate('openPayrollCycle()'); await sleep(4000);
  const all = () => p.evaluate(() => ({ runs: Object.keys(HR_ALL_RUNS).length, ticked: document.querySelectorAll('#hr-all-body input.hr-pick:checked').length,
    boxes: document.querySelectorAll('#hr-all-body input.hr-pick').length, b: (b => [b.checked, b.indeterminate])(document.querySelector('#hr-run-all .hr-pay-all')),
    count: document.querySelector('#hr-run-all .hr-pay-count').textContent }));
  let A = await all();
  ck('all companies: the selection starts again (company changed) - unpaid ticked', A.ticked > 0 && A.ticked < A.boxes + 1, A);
  await p.click('#hr-run-all .hr-pay-all'); await sleep(400); A = await all();
  const A2 = A;
  await p.click('#hr-run-all .hr-pay-all'); await sleep(400); A = await all();
  ck('all companies: Select all toggles every company', (A2.ticked === 0 && A.ticked > 0 && A.b[0]) || (A2.ticked > 0 && A.ticked === 0), [A2, A]);
  if (!A.ticked) { await p.click('#hr-run-all .hr-pay-all'); await sleep(300); }
  // untick one in the second company -> dash
  await p.evaluate(() => { const x = [...document.querySelectorAll('#hr-all-body input.hr-pick:checked')].pop(); x.click(); }); await sleep(300); A = await all();
  ck('all companies: one unticked -> the dash', !A.b[0] && A.b[1], A);
  await p.evaluate('previewConsolidated()'); await sleep(400);
  u = await lastUrl(); html = await getText(u);
  ck('all companies Preview carries the ticks', /consolidated\/view/.test(u) && /emps=/.test(u) && /Salary Statement/.test(html), u);
  await p.evaluate('previewConsolidated(true)'); await sleep(400);
  ck('Consolidated statement (office + local) is everyone - no ticks sent', !/emps=/.test(await lastUrl()), await lastUrl());
  const grand = await p.textContent('#hr-all-grand');
  ck('GRAND TOTAL counts the ticked staff', /GRAND TOTAL - \d+ of \d+ staff ticked/.test(grand), grand);
  await p.screenshot({ path: SH + '05_all_companies.png', fullPage: true });
  // month changes -> starts again
  await p.evaluate(() => { document.getElementById('hr-run-month').value = '2026-09'; }); await p.evaluate('openPayrollCycle()'); await sleep(3500);
  await p.evaluate(() => { document.getElementById('hr-run-month').value = '2026-10'; }); await p.evaluate('openPayrollCycle()'); await sleep(3500);
  A = await all();
  ck('month switched and back: selection reset to "unpaid ticked"', A.b[0] && !A.b[1], A);

  // Labour: PAY on the Paid status card; card exports follow it
  await p.evaluate("switchScreen('combine')"); await sleep(2500);
  const cyc = await p.evaluate(async () => { const sel = document.getElementById('combine-cycle');
    for (const o of sel.options) { const d = await apiCall('/employees/pay/labour?month_year=' + encodeURIComponent(o.value)); if (d.groups.length) { sel.value = o.value; return o.value; } } return ''; });
  await p.evaluate('payLabLoad()'); await sleep(3000);
  const lab = () => p.evaluate(() => ({ boxes: document.querySelectorAll('#lab-pay-body input.lab-pick').length, ticked: [...document.querySelectorAll('#lab-pay-body input.lab-pick:checked')].map(x => x.dataset.emp),
    b: (b => [b.checked, b.indeterminate])(document.getElementById('lab-pay-all')), foot: (document.querySelector('#lab-pay-body .lab-tot-l') || {}).textContent }));
  let Lb = await lab();
  ck('labour: PAY column with every unpaid worker ticked, Select all ticked', Lb.boxes > 1 && Lb.ticked.length > 0 && Lb.b[0], [cyc, Lb]);
  await p.click('#lab-pay-all'); await sleep(300); Lb = await lab();
  ck('labour: Select all again unticks everyone', Lb.ticked.length === 0 && !Lb.b[0] && !Lb.b[1], Lb);
  await p.evaluate("exportCombineCards('view')"); await sleep(300);
  ck('labour: nothing ticked -> no export, says so', /No workers selected/.test(await p.textContent('#combine-status')));
  const two = await p.evaluate(() => [...document.querySelectorAll('#lab-pay-body input.lab-pick')].slice(0, 2).map(x => { x.click(); return x.dataset.emp; })); await sleep(300);
  Lb = await lab();
  ck('labour: two ticked -> the dash, TOTAL counts them', Lb.b[1] && /TOTAL - \d+ of/.test(Lb.foot), Lb);
  await p.evaluate("exportCombineCards('view')"); await sleep(400);
  u = await lastUrl(); html = await getText(u);
  ck('labour: card Preview only the ticked workers', /emp_nos=/.test(u) && /2 worker/.test(html), [u, html.slice(0, 200)]);
  await p.evaluate("exportCombineCards('pdf')"); await sleep(300);
  const pr = await p.evaluate(async u => { const r = await fetch(u); return [r.status, (await r.arrayBuffer()).byteLength]; }, await lastUrl());
  ck('labour: Combine to PDF with the ticks', pr[0] === 200 && pr[1] > 1000, pr);
  // mark one of them paid -> unticks; re-tick -> card says Already paid
  await p.click(`#lab-pay-body tr:has(input.lab-pick[data-emp="${two[0]}"]) button.pay-btn`); await sleep(1000);
  await p.check('#pay-types input[value="early_full"]').catch(() => {}); await sleep(800);
  await p.click('#pay-go'); await sleep(3000);
  Lb = await lab();
  ck('labour: marked paid -> his PAY unticks', !Lb.ticked.includes(two[0]) && Lb.ticked.includes(two[1]), Lb);
  await p.check(`#lab-pay-body input.lab-pick[data-emp="${two[0]}"]`); await sleep(300);
  await p.evaluate("exportCombineCards('view')"); await sleep(400);
  html = await getText(await lastUrl());
  ck('labour: re-ticked paid worker prints with "(Already paid)"', /\(Already paid\)/.test(html), html.length);
  await p.screenshot({ path: SH + '06_labour.png' });
  ck('no page errors', !errs.length, errs);
  await br.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
