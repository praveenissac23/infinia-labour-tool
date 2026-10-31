// Office salary sheet on screen: the TOTAL line adds up the figures the rows show, for the people ticked
// under PAY - and is the same total the Preview prints - including while the month is still running, when
// the last money column is "Salary To Date" (not Net Pay).
//
// Run against a copy of a database that holds office cycles, with the server believing it is the middle of a
// month (so the salary-to-date figures are on the screen):
//   SRV_TODAY=2026-10-15 SRV_PORT=8032 SRV_API_PORT=8033 DATABASE_URL=sqlite:////tmp/copy.db python3 tests/serve_like_nginx.py &
//   SRV_TODAY=2026-10-15 node tests/office_pay_arith_audit_ui_test.js
// The row figures themselves are worked out by hand in office_pay_arith_audit_test.py; here every visible
// row's salary to date is also re-derived from the visible Basic, Fix Allown., Add / Ded. and Absent Ded.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const PW = process.env.ADMIN_PW || 'changeme123';
const TODAY = process.env.SRV_TODAY || new Date().toISOString().slice(0, 10);
const FAIL = []; let N = 0;
const ck = (m, ok, ctx) => { N++; if (!ok) { FAIL.push(m); console.log('FAIL ' + m + '  [' + JSON.stringify(ctx) + ']'); } else if (process.env.VERBOSE) console.log('PASS ' + m); };
const num = t => { const s = String(t || '').replace(/[^0-9.\-]/g, ''); return s === '' || s === '-' ? 0 : parseFloat(s); };
const same = (a, b) => Math.abs(Math.round(a * 100) - Math.round(b * 100)) <= 1;

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  const errs = []; p.on('pageerror', e => errs.push(String(e).slice(0, 200)));
  await p.goto(B + '/app-classic.html');
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', PW);
  await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 });
  await p.waitForTimeout(1500);
  await p.evaluate("switchScreen('hrpayroll')"); await p.waitForTimeout(1500);
  await p.evaluate("hrTab('payroll')"); await p.waitForTimeout(800);

  const ym = TODAY.slice(0, 7);
  const [y, m] = ym.split('-').map(Number);
  const days = new Date(y, m, 0).getDate(), day = Number(TODAY.slice(8, 10));
  const month = new Date(y, m - 1, 1).toLocaleString('en-GB', { month: 'long' }) + ' ' + y;
  const runs = (await p.evaluate(() => apiCall('/employees/payroll/runs'))).rows.filter(r => r.month_year === month);
  ck(`there are ${month} sheets to check`, runs.length > 0, runs.length);

  // Read the sheet as it is drawn: every ticked row's figures, and the TOTAL line.
  const readSheet = scope => p.evaluate(sc => {
    const root = sc ? document.querySelector(sc) : document.getElementById('hr-run-card');
    const rows = [...root.querySelectorAll('tbody tr[data-line]')].map(tr => {
      // A figure is the box's value where there is a box (the loan instalment), never the "... owed" note under it.
      const fig = td => { const i = td.querySelector('input'); if (i) return i.value || '0';
                          const c = td.cloneNode(true); c.querySelectorAll('.sub').forEach(s => s.remove()); return c.textContent.trim(); };
      const tds = [...tr.querySelectorAll('td')], nums = [...tr.querySelectorAll('td.num')].map(fig);
      const pick = tr.querySelector('input.hr-pick');
      return { id: Number(tr.dataset.line), ticked: !!(pick && pick.checked), held: tr.classList.contains('hr-held'),
               code: tds[1].textContent.trim(), basic: nums[0], allow: nums[1], adj: nums[2], absent: nums[3], loan: nums[4], net: nums[5],
               fullTag: /Full month/.test(tds[2].textContent), locked: tr.classList.contains('pay-locked') };
    });
    const foot = root.querySelector('tfoot tr.hr-foot');
    const fnums = foot ? [...foot.querySelectorAll('td.num')].map(td => td.textContent.trim()) : [];
    const head = [...root.querySelectorAll('thead th')].map(th => th.textContent.trim());
    return { rows, fnums, footText: foot ? foot.textContent : '', head };
  }, scope);

  for (const r of runs) {
    const co = await p.evaluate(name => (HR_COMPANIES.find(c => (c.short_name || c.name) === name) || {}).id, r.company);
    await p.evaluate(([cid, mv, g]) => {
      const ms = document.getElementById('hr-run-month');
      if (![...ms.options].some(o => o.value === mv)) ms.add(new Option(mv, mv));
      ms.value = mv; document.getElementById('hr-run-company').value = String(cid);
      document.getElementById('hr-run-group').value = g; hrSyncBar();
    }, [co, ym, r.group || 'staff']);
    await p.evaluate('openPayrollCycle()'); await p.waitForTimeout(1500);
    const run = await p.evaluate(() => HR_RUN && { id: HR_RUN.id, progress: HR_RUN.progress, status: HR_RUN.status });
    const tag = `${r.company} ${month} (${r.group})`;
    ck(`${tag}: the sheet opens`, run && run.id === r.id, run);
    if (!run) continue;
    const running = !!(run.progress && run.progress.running);
    for (const pass of ['as opened', 'one row unticked']) {
      if (pass === 'one row unticked') {
        const first = await p.$('#hr-run-body input.hr-pick:checked');
        if (!first) continue;
        await first.click(); await p.waitForTimeout(300);
      }
      const s = await readSheet(null);
      const last = s.head.find(h => /Salary To Date|Net Pay/.test(h)) || '';
      ck(`${tag} [${pass}]: last money column says ${running ? 'Salary To Date' : 'Net Pay'}`, last.includes(running ? 'Salary To Date' : 'Net Pay'), last);
      const t = s.rows.filter(x => x.ticked && !x.held);
      const sum = k => t.reduce((a, x) => a + num(x[k]), 0);
      const want = [sum('basic'), sum('allow'), sum('adj'), sum('absent'), sum('loan'), sum('net')];
      ['Basic', 'Fix Allown.', 'Add / Ded.', 'Absent Ded.', 'Loan', last].forEach((h, i) =>
        ck(`${tag} [${pass}]: TOTAL ${h} = the ${t.length} ticked rows added up (${want[i].toFixed(2)})`, same(num(s.fnums[i]), want[i]), s.fnums[i]));
      ck(`${tag} [${pass}]: TOTAL says ${t.length} ticked`, s.footText.includes(`${t.length} of`), s.footText.slice(0, 80));
      // Each row's salary to date, from what the row itself shows.
      if (pass === 'as opened') for (const x of s.rows.filter(x => !x.held)) {
        const gross = num(x.basic) + num(x.allow);
        const net = gross + num(x.adj) - num(x.absent) - num(x.loan);
        const wantRow = (!running || x.fullTag || x.locked) ? net
          : Math.round(gross * day / days * 100) / 100 + num(x.adj) - num(x.absent);
        ck(`${tag}: ${x.code} shows ${running && !x.fullTag && !x.locked ? 'salary to date' : 'net pay'} ${wantRow.toFixed(2)}`, same(num(x.net), wantRow), x);
      }
      // The Preview of the same ticks prints the same TOTAL.
      const emps = await p.evaluate(() => hrSelEmps([HR_RUN]).join(','));
      if (!emps) continue;
      const tok = await p.evaluate(async () => (await apiCall('/auth/download-token', { method: 'POST' })).token);
      const html = await (await p.request.get(`${B}/export/payroll/statement/view?run_id=${run.id}&token=${encodeURIComponent(tok)}&emps=${emps}`)).text();
      const tr = (html.match(/<tr class="tot">([\s\S]*?)<\/tr>/) || [])[1] || '';
      const cells = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(mm => mm[1].replace(/<[^>]+>/g, '').trim()).filter(v => /\d/.test(v));
      ck(`${tag} [${pass}]: Preview TOTAL ${cells[cells.length - (html.includes('>Pension<') ? 2 : 1)]} = screen TOTAL ${s.fnums[5]}`,
         cells.some(v => same(num(v), num(s.fnums[5]))), cells);
    }
  }

  // All companies on one screen: each company's TOTAL and the GRAND TOTAL add up what the rows show.
  for (const g of ['staff', 'local']) {
    if (!runs.some(r => (r.group || 'staff') === g)) continue;
    await p.evaluate(gg => { document.getElementById('hr-run-company').value = ''; document.getElementById('hr-run-group').value = gg; hrSyncBar(); }, g);
    await p.evaluate('openPayrollCycle()'); await p.waitForTimeout(2500);
    const all = await p.evaluate(() => {
      const secs = [...document.querySelectorAll('#hr-all-body .hr-all-co[data-run]')].map(sec => {
        const rows = [...sec.querySelectorAll('tbody tr[data-line]')].filter(tr => (tr.querySelector('input.hr-pick') || {}).checked)
          .map(tr => [...tr.querySelectorAll('td.num')].map(td => td.textContent.trim()));
        const foot = [...sec.querySelectorAll('tfoot tr.hr-foot td.num')].map(td => td.textContent.trim());
        return { rows, foot };
      });
      const grand = [...document.querySelectorAll('#hr-all-grand td.num')].map(td => td.textContent.trim());
      return { secs, grand };
    });
    let gnet = 0;
    all.secs.forEach((sec, i) => {
      const net = sec.rows.reduce((a, r) => a + num(r[5]), 0); gnet += net;
      ck(`all companies (${g}) sheet ${i + 1}: TOTAL ${sec.foot[5]} = its ticked rows ${net.toFixed(2)}`, same(num(sec.foot[5]), net), sec.foot);
    });
    ck(`all companies (${g}): GRAND TOTAL ${all.grand[5]} = every ticked row ${gnet.toFixed(2)}`, all.secs.length > 0 && same(num(all.grand[5]), gnet), all.grand);
  }

  ck('nothing threw', errs.length === 0, errs.slice(0, 3));
  await b.close();
  console.log(`\n${N} checks`);
  if (FAIL.length) { console.log(`${FAIL.length} FAILED`); process.exit(1); }
  console.log('THE SCREEN TOTALS ADD UP');
})();
