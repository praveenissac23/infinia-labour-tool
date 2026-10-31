// Salary, payroll and reports on real-life data (tests/seed_scenarios.py):
// leavers either side of the cycle start, a removed worker, a new joiner,
// a third company, a rate change, adjustments. Every screen is opened the
// way a person would and every script error, refused call or empty screen
// is reported.
//   node tests/scenario_payroll_test.js
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (name, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [], http = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('response', r => { if (r.status() >= 400 && !r.url().includes('/auth/login')) http.push(`${r.status()} ${r.request().method()} ${r.url().replace(B, '')}`); });
  p.on('dialog', d => { errs.push('pop-up: ' + d.message()); d.dismiss(); });
  const clean = (where) => { ck(`${where}: no script errors, no refused calls`, errs.length === 0 && http.length === 0, { errs, http }); errs.length = 0; http.length = 0; };
  const api = (path) => p.evaluate(async x => apiCall(x), path);

  await p.goto(B + '/?p=attendance'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const today = await p.evaluate(() => currentDate);
  // The cycles are worked out from today, the way tests/seed_scenarios.py does (26th - 25th, named by the end month),
  // so the test holds whatever day it is run on - it used to name September / October 2026 and broke once they passed.
  const MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const td = new Date(today + 'T00:00:00');
  const cycOf = d => { const m = d.getDate() >= 26 ? new Date(d.getFullYear(), d.getMonth() + 1, 1) : new Date(d.getFullYear(), d.getMonth(), 1); return { label: `${MON[m.getMonth()]} ${m.getFullYear()}`, start: new Date(m.getFullYear(), m.getMonth() - 1, 26) }; };
  const CUR = cycOf(td), PREV = cycOf(new Date(CUR.start.getTime() - 86400000));
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const plus = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const PL = PREV.label, PLu = encodeURIComponent(PL);
  const leftOn = plus(PREV.start, 12), before = plus(PREV.start, 8);     // seed: T-901 leaves on prev start + 12

  // ---- Attendance -------------------------------------------------------
  const opening = await p.evaluate(() => document.getElementById('att-status').textContent);
  ck('on opening today, the page says the pre-filled Sunday is not saved yet', /not saved yet/.test(opening), opening.slice(0, 100));
  const grid = await p.evaluate(() => [...document.querySelectorAll('#grid-body td.empno')].map(td => td.textContent.trim()));
  ck('today\'s grid leaves out the worker who left last cycle (T-901)', !grid.includes('T-901'), grid.filter(x => x.startsWith('T-')));
  ck('and the removed worker (T-903)', !grid.includes('T-903'));
  ck('but keeps this cycle\'s leaver (T-902) and the new joiner (T-904)', grid.includes('T-902') && grid.includes('T-904'), grid.filter(x => x.startsWith('T-')));
  const t902 = await p.evaluate(() => rowData['T-902'] && rowData['T-902'].am);
  ck('the leaver shows Terminated after his last day', t902 === 'Terminated', t902);
  const rowsBefore = (await api('/attendance/' + today)).filter(r => r.site || r.am || r.pm).length;
  let sent = 0; p.on('request', r => { if (r.url().includes('/attendance/save')) sent++; });
  const answered = p.waitForResponse(r => r.url().includes('/attendance/save'), { timeout: 15000 }).catch(() => null);
  await p.click('#att-save-btn:visible, #floating-save-btn:visible'); const ans = await answered; await p.waitForTimeout(1500);
  const st = await p.evaluate(() => document.getElementById('att-status').textContent);
  ck('Save sends and is answered (today, with leavers around)', sent === 1 && ans && ans.status() === 200 && /Saved/.test(st), { sent, status: ans && ans.status(), st: st.slice(0, 120) });
  const after = await api('/attendance/' + today);
  ck(`Save never removes rows (before ${rowsBefore}, after ${after.filter(r => r.site || r.am || r.pm).length})`, after.filter(r => r.site || r.am || r.pm).length >= rowsBefore);
  if (td.getDay() === 0) ck('and marks every Sunday row', after.filter(r => r.am === 'Sunday').length >= 60, after.filter(r => r.am === 'Sunday').length);
  ck('the message reports the rows saved, not "no changes"', !/no changes/.test(st), st.slice(0, 100));
  const y = new Date(new Date(today + 'T00:00:00').getTime() - 86400000); const yIso = `${y.getFullYear()}-${String(y.getMonth() + 1).padStart(2, '0')}-${String(y.getDate()).padStart(2, '0')}`;
  const comp = await api(`/attendance/completion/${encodeURIComponent(MON[y.getMonth()] + ' ' + y.getFullYear())}?mode=calendar`);
  const yday = comp.days.find(d => d.date === yIso);
  ck(`yesterday (${yIso}) - fully saved - is green, counting only its grid`, yday && yday.complete, yday);
  // a day in the previous cycle, when T-901 was still employed
  await p.fill('#date-picker', iso(before)); await p.dispatchEvent('#date-picker', 'change'); await p.waitForTimeout(2500);
  const grid2 = await p.evaluate(() => [...document.querySelectorAll('#grid-body td.empno')].map(td => td.textContent.trim()));
  ck(`${iso(before)}: T-901 is on the grid (he left on ${iso(leftOn)})`, grid2.includes('T-901'));
  sent = 0; await p.click('#att-save-btn:visible, #floating-save-btn:visible'); await p.waitForTimeout(3000);
  ck(`${iso(before)}: Save sends`, sent === 1, sent);
  const notes = await api('/notifications');
  const attNote = (notes.rows || notes || []).filter ? (notes.rows || notes).filter(n => n.kind === 'attendance') : [];
  ck('no false "yesterday incomplete" warning in the bell', !attNote.some(n => /incomplete|No attendance/.test(n.title)), attNote);
  clean('Attendance');

  // ---- Payroll: salary cards --------------------------------------------
  await p.click('.pg-side .pg-item[data-page="payroll"]'); await p.waitForTimeout(2000);
  await p.selectOption('#combine-cycle', { label: PL }).catch(() => p.selectOption('#combine-cycle', PL));
  await p.dispatchEvent('#combine-cycle', 'change'); await p.waitForTimeout(2500);
  const sums = await api(`/summaries/${PLu}`);
  const byNo = Object.fromEntries(sums.map(s => [s.emp_no, s]));
  ck(`${PL} cards exist for everyone who worked (incl. T-901, T-902, Enginova T-905)`, ['T-901', 'T-902', 'T-905', 'T-906'].every(n => byNo[n]), Object.keys(byNo).filter(x => x.startsWith('T-')));
  ck(`the removed worker still has his ${PL} card (he worked it)`, !!byNo['T-903']);
  ck(`the new joiner has no ${PL} card`, !byNo['T-904']);
  const t901 = byNo['T-901'] || {};
  const paid901 = (t901.present_days || 0) + (t901.sunday_days || 0) + (t901.holiday_days || 0) + (t901.sick_days || 0) + (t901.medical_days || 0);
  ck(`T-901 is paid only up to his leaving day ${iso(leftOn)} (${paid901} paid days, the rest Terminated)`, paid901 <= 13 && (t901.terminated_days || 0) >= Math.round((CUR.start - PREV.start) / 86400000) - 13, t901);
  const neg = sums.filter(s => (s.final_salary ?? s.net_salary ?? 0) < 0);
  ck('no card has a negative final salary', neg.length === 0, neg.map(s => s.emp_no));
  for (const [kind, fmt] of [['combine', 'view'], ['combine', 'excel'], ['combine', 'pdf']]) {
    const u = await p.evaluate(async ([f, cy]) => { const t = (await apiCall('/auth/download-token', { method: 'POST' })).token; return `/export/${cy}/${f === 'view' ? 'cards/view' : f}?token=${t}`; }, [fmt, PLu]);
    const r = await p.evaluate(async url => { const x = await fetch(url); return [x.status, x.headers.get('content-type')]; }, u);
    ck(`salary cards ${fmt} for ${PL} downloads`, r[0] === 200, r);
  }
  clean('Salary cards');

  // ---- Additions & deductions --------------------------------------------
  await p.locator('.pg-subtab', { hasText: 'Additions' }).click(); await p.waitForTimeout(1200);
  await p.selectOption('#adj-cycle', PL).catch(() => {}); await p.evaluate('loadAdjustmentsList()'); await p.waitForTimeout(2000);
  const adjRows = await p.locator('#adj-all-card tbody tr').count();
  ck(`additions & deductions list the ${PL} workers`, adjRows > 50, adjRows);
  clean('Additions & deductions');

  // ---- Check before you pay -----------------------------------------------
  await p.locator('.pg-subtab', { hasText: 'Check before' }).click(); await p.waitForTimeout(1500);
  for (const cy of [PL, CUR.label]) {
    await p.selectOption('#errcheck-cycle', cy).catch(() => {}); await p.evaluate('loadErrorCheck()'); await p.waitForTimeout(2500);
    clean(`Check before you pay (${cy})`);
  }

  // ---- Live card for every special worker, both cycles ------------------
  await p.click('.pg-side .pg-item[data-page="attendance"]'); await p.waitForTimeout(1000);
  await p.click('#pg-tabs .pg-tab[data-tab="livecard"]'); await p.waitForTimeout(2000);
  for (const cy of [PL, CUR.label]) {
    await p.selectOption('#livecard-cycle', cy).catch(() => {}); await p.dispatchEvent('#livecard-cycle', 'change').catch(() => {}); await p.waitForTimeout(800);
    for (const no of ['T-901', 'T-902', 'T-904', 'T-905', 'T-906', 'F-002']) {
      const listed = await p.evaluate(n => employees.some(e => e.emp_no === n), no);
      if (!listed) continue;
      await p.evaluate(n => selectLiveCardWorker(n), no); await p.waitForTimeout(1200);
    }
    clean(`Live card (${cy})`);
  }

  // ---- Reports -----------------------------------------------------------
  await p.click('.pg-side .pg-item[data-page="reports"]'); await p.waitForTimeout(2000);
  const tabs = await p.locator('#pg-tabs .pg-tab').allTextContents();
  for (let i = 0; i < tabs.length; i++) {
    await p.locator('#pg-tabs .pg-tab').nth(i).click(); await p.waitForTimeout(1500);
    const subs = await p.locator('#pg-sub .pg-subtab').count();
    for (let j = 0; j < subs; j++) { await p.locator('#pg-sub .pg-subtab').nth(j).click(); await p.waitForTimeout(1200); }
    clean(`Reports > ${tabs[i]} (${subs} sub-tabs)`);
  }
  // the labour report for each company, previous cycle
  await p.locator('#pg-tabs .pg-tab').first().click(); await p.waitForTimeout(1200);
  if (await p.locator('#report-company').count()) {
    const cos = await p.locator('#report-company option').allTextContents();
    for (const co of cos) {
      await p.selectOption('#report-company', { label: co }).catch(() => {});
      await p.selectOption('#report-cycle', PL).catch(() => {});
      await p.evaluate('loadReports()').catch(e => errs.push(String(e))); await p.waitForTimeout(2000);
    }
    ck('the report company list includes Enginova', cos.some(x => /Enginova/i.test(x)), cos);
    clean(`Labour report for ${cos.length} company choices`);
  }

  // ---- Payroll > Office payroll, Staff, Dashboard ------------------------
  await p.click('.pg-side .pg-item[data-page="payroll"]'); await p.waitForTimeout(1200);
  await p.click('#pg-tabs .pg-tab[data-tab="hrpayroll"]'); await p.waitForTimeout(2500);
  const hsubs = await p.locator('#pg-sub .pg-subtab').count();
  for (let j = 0; j < hsubs; j++) { await p.locator('#pg-sub .pg-subtab').nth(j).click(); await p.waitForTimeout(1500); }
  clean(`Office payroll (${hsubs} sub-tabs)`);
  await p.click('.pg-side .pg-item[data-page="people"]'); await p.waitForTimeout(3000);
  const staffOk = await p.frameLocator('#pg-staff-frame').locator('#shell').isVisible();
  ck('Staff opens', staffOk);
  await p.click('.pg-side .pg-item[data-page="dashboard"]'); await p.waitForTimeout(2500);
  clean('Staff and Dashboard');

  console.log(bad ? `\n${bad} FAILED` : '\nPAYROLL AND REPORTS HOLD UP ON REAL-LIFE DATA');
  await b.close(); process.exit(bad ? 1 : 0);
})();
