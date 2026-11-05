// Cycle report builder (5 Nov 2026): tick employees, "Show only ticked" - rows, totals, Preview, PDF and Excel are of
// those employees only; a grouped row ticks everyone in it; Show all / Clear ticks bring everyone back.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/full.db 8550 tests/report_pick_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => { errs.push('dialog'); d.dismiss(); });
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  await p.goto(B + '/?p=reports'); await sleep(3500);
  // per worker: Employee No, Name, Days present, Final salary cost
  await p.evaluate(() => { document.querySelectorAll('#report-column-picker-id input[data-dim]').forEach(b => { b.checked = ['emp_no', 'name'].includes(b.dataset.dim); });
    document.querySelectorAll('#report-column-picker-measure input[data-measure]').forEach(b => { b.checked = ['days_present', 'final_salary_cost'].includes(b.dataset.measure); }); });
  await p.evaluate(() => loadReports()); await sleep(3000);
  const all = await p.evaluate(() => ({ n: currentCustomReport.rows.length, tot: currentCustomReport.totals.final_salary_cost, boxes: document.querySelectorAll('#report-body td.rp-cb input').length }));
  ck(`every row has a tick box (${all.n} employees)`, all.n > 3 && all.boxes === all.n, all);
  const hint = await p.textContent('#rp-pick'); ck('before ticking: a hint how to use it', /Tick employees/.test(hint), hint);
  await p.screenshot({ path: '/tmp/claude-0/ui2/rp_before.png', clip: { x: 0, y: 0, width: 1500, height: 950 } });
  const picked = await p.evaluate(() => { const rows = rpShownRows.slice(0, 3); const boxes = [...document.querySelectorAll('#report-body td.rp-cb input')].slice(0, 3);
    boxes.forEach(b => { b.checked = true; b.dispatchEvent(new Event('change')); });
    return rows.map(r => ({ e: r.dim_0, v: r.final_salary_cost })); });
  const chip = await p.textContent('#rp-pick');
  ck('ticking 3: "3 employees ticked" with Show only ticked', /3 employees ticked/.test(chip) && /Show only ticked/.test(chip), chip);
  await p.screenshot({ path: '/tmp/claude-0/ui2/rp_ticked.png', clip: { x: 0, y: 0, width: 1500, height: 950 } });
  await p.click('#rp-pick button:has-text("Show only ticked")'); await sleep(2500);
  const only = await p.evaluate(() => ({ rows: currentCustomReport.rows.map(r => r.dim_0), tot: currentCustomReport.totals.final_salary_cost, chip: document.getElementById('rp-pick').textContent }));
  const want = picked.reduce((a, x) => a + x.v, 0);
  ck('only the 3 ticked employees are in the report', JSON.stringify(only.rows.sort()) === JSON.stringify(picked.map(x => x.e).sort()), only);
  ck(`the total is theirs only (${want.toFixed(2)})`, Math.abs(only.tot - want) < 0.01, only.tot);
  ck('the heading says so, with Show all', /Only 3 ticked employees/.test(only.chip) && /Show all/.test(only.chip), only.chip);
  await p.screenshot({ path: '/tmp/claude-0/ui2/rp_only.png', clip: { x: 0, y: 0, width: 1500, height: 950 } });
  // Preview / PDF / Excel: the same three
  const urls = []; p.on('popup', pp => urls.push(pp.url()));
  await p.evaluate(() => { window.__open = window.open; window.open = u => { window.__last = u; }; exportReportTable('excel'); });
  const xl = await p.evaluate(() => window.__last);
  ck('Excel export asks for the ticked employees only', /emp_nos=/.test(xl), xl);
  const rows = await p.evaluate(async u => { const r = await fetch(u.replace('format=excel', 'format=rows')); return (await r.json()).rows.length; }, xl);
  ck(`the exported sheet has 3 employees (+ heading/total rows: ${rows})`, rows >= 3 && rows <= 6, rows);
  await p.evaluate(() => exportReportTable('view')); const vw = await p.evaluate(() => window.__last);
  const vhtml = await p.evaluate(async u => (await (await fetch(u)).text()), vw);
  ck('Preview keeps them through its own PDF / Excel buttons', /emp_nos=/.test(vw) && /emp_nos=/.test(vhtml), vw);
  await p.click('#rp-pick button:has-text("Show all")'); await sleep(2500);
  const back = await p.evaluate(() => ({ n: currentCustomReport.rows.length, chip: document.getElementById('rp-pick').textContent }));
  ck('Show all: everyone again, ticks kept', back.n === all.n && /3 employees ticked/.test(back.chip), back);
  // grouped by site: one tick = everyone at that site
  await p.evaluate(() => { document.querySelectorAll('#report-column-picker-id input[data-dim]').forEach(b => { b.checked = b.dataset.dim === 'site'; }); });
  await p.evaluate(() => { reportPick = new Set(); loadReports(); }); await sleep(3000);
  const site = await p.evaluate(() => { const r = rpShownRows.find(x => (x._emps || []).length > 1); const i = rpShownRows.indexOf(r);
    const b = document.querySelectorAll('#report-body td.rp-cb input')[i]; b.checked = true; b.dispatchEvent(new Event('change')); return { n: r._emps.length, picked: reportPick.size }; });
  ck(`by site: ticking a site ticks its ${site.n} employees`, site.n === site.picked, site);
  await p.click('#rp-pick button:has-text("Clear ticks")'); await sleep(2000);
  ck('Clear ticks: none ticked, everyone shown', await p.evaluate(() => reportPick.size === 0 && !reportOnlyPicked));
  // the monthly report stays everyone, no ticks
  await p.evaluate(() => { reportPick = new Set(['x']); reportOnlyPicked = true; }); await p.evaluate(() => { switchScreen('monthly'); openMonthlyReport(); }); await sleep(4000);
  const mon = await p.evaluate(() => ({ boxes: document.querySelectorAll('#report-body td.rp-cb').length, n: currentCustomReport.rows.length }));
  ck('the Monthly Report is not narrowed and has no tick boxes', mon.boxes === 0 && mon.n > 1, mon);
  ck('no page errors', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close(); })();
