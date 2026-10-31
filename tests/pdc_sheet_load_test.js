// The accountant's Supplier Tracker loaded by deploy/load_pdc_tracker.py:
// month totals as on the sheet, the three dated cheques dated, the rest
// "date to fill" (screen, list, paper), a Date-to-fill box, the bell asks
// for the dates, and putting a date in settles the line.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 1000 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=expiry#expiry:pdc'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const api = (u, m, body) => p.evaluate(async ([u, m, body]) => apiCall(u, m ? { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined), [u, m, body]);
  // Start from exactly the accountant's sheet: the cheques already in this copy of the database are taken off,
  // then deploy/load_pdc_tracker.py loads the sheet into the database the test server runs on (never live).
  for (const r of (await api('/employees/pdc')).rows) await api(`/employees/pdc/${r.id}`, 'DELETE');
  const root = require('path').resolve(__dirname, '..');
  const ROOT = require('fs').existsSync(root + '/deploy/load_pdc_tracker.py') ? root : process.cwd();
  require('child_process').execSync(`python3 deploy/load_pdc_tracker.py`, { cwd: ROOT, env: { ...process.env, DATABASE_URL: 'sqlite:////tmp/run_js.db' } });
  await p.evaluate(() => pdcLoad()); await p.waitForTimeout(800);
  const today = await p.evaluate(() => pcToday ? pcToday() : new Date().toISOString().slice(0, 10));
  await p.fill('#pdc-from', '2026-10'); await p.dispatchEvent('#pdc-from', 'change'); await p.waitForTimeout(1200);
  const g = await p.evaluate(() => PDC_GRID);
  ck('Oct / Nov / Dec / Jan totals as on the sheet', JSON.stringify(g.totals) === JSON.stringify([640093.92, 448784.81, 720590, 380000]), g.totals);
  ck('grand total 2,189,468.73 = the four month totals (the sheet showed 2,189,025.73 - it missed Al Refada 443.00, whose row total was blank)', g.grand === 2189468.73, g.grand);
  const gt = await p.locator('#pdc-gbody').textContent();
  ck('dated ones show their date (01/12/2026, 05/12/2026, 19/10/2026)', ['01/12/2026', '05/12/2026', '19/10/2026'].every(x => gt.includes(x)));
  ck('the rest say "date to fill"', (gt.match(/date to fill/g) || []).length === 18, (gt.match(/date to fill/g) || []).length);
  const s = (await api('/employees/pdc')).summary;
  ck('a Date-to-fill box: 18 cheques', s.no_date === 18 && (await p.locator('.exp-card[data-k="nodate"]').count()) === 1, s.no_date);
  // only a dated cheque can be overdue (SEOMAA's 19/10/2026 is, once that day has passed); the 18 undated never are
  const datedPast = ['2026-10-19', '2026-12-01', '2026-12-05'].filter(d => d < today).length;
  ck(`undated cheques are not counted as overdue (${datedPast} dated one(s) past their day)`, s.overdue === datedPast, s.overdue);
  await p.screenshot({ path: SH + 'pdc-sheet-1.png', fullPage: true });
  const n = (await api('/notifications')).notifications.find(x => x.kind === 'pdc');
  ck('the bell asks for the dates', n && /18 with no date/.test(n.title), n && n.title);
  // Paper
  const [pop] = await Promise.all([p.waitForEvent('popup'), p.evaluate(() => pdcExport('view'))]);
  await pop.waitForLoadState(); await pop.waitForTimeout(600);
  const txt = await pop.locator('.page').textContent();
  ck('paper: "date to fill" under undated figures, real dates under dated ones', /date to fill/.test(txt) && /19\/10\/2026/.test(txt) && /2,189,468\.73/.test(txt));
  await pop.screenshot({ path: SH + 'pdc-sheet-2-paper.png', fullPage: true }); await pop.close();
  // Fill a date
  await p.evaluate(() => pdcCard('nodate')); await p.waitForTimeout(500);
  ck('"Date to fill" lists them, each showing its month', (await p.locator('#pdc-lbody tr').count()) === 18 && /Oct-26: date to fill/.test(await p.locator('#pdc-lbody').textContent()));
  await p.screenshot({ path: SH + 'pdc-sheet-3-list.png', fullPage: true });
  await p.locator('#pdc-lbody tr', { hasText: 'Pergola' }).click(); await p.waitForTimeout(300);
  ck('opening one: date box empty, the title asks for the date', (await p.inputValue('#pdc-date')) === '' && /put the cheque date in/.test(await p.locator('#pdc-form-title').textContent()));
  await p.fill('#pdc-no', '000777'); await p.click('#pdc-save'); await p.waitForTimeout(1000);
  let r = (await api('/employees/pdc')).rows.find(x => /Pergola/.test(x.payee));
  ck('saving with no date keeps it as "date to fill" (cheque no saved)', r.date_tbc && r.cheque_no === '000777' && r.date.startsWith('2026-10'), r);
  await p.locator('#pdc-lbody tr', { hasText: 'Pergola' }).click(); await p.waitForTimeout(300);
  await p.fill('#pdc-date', '2026-10-12'); await p.click('#pdc-save'); await p.waitForTimeout(1000);
  r = (await api('/employees/pdc')).rows.find(x => /Pergola/.test(x.payee));
  ck('putting the date in settles it (12-Oct-26, reminders now work)', !r.date_tbc && r.date === '2026-10-12' && r.days_left !== null, r);
  ck('Date-to-fill now 17', (await api('/employees/pdc')).summary.no_date === 17);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'THE SHEET IS IN, DATES TO FILL');
  await b.close(); process.exit(bad ? 1 : 0);
})();
