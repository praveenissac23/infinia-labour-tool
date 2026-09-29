// A labourer added on Staff > Labour is the same record as Attendance >
// Labour master data: same fields and names (trade, pay type, total,
// basic, joining date), there at once, and a change on either page shows
// on the other.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=people'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const f = p.frameLocator('#pg-staff-frame');
  const fr = p.frames().find(x => x.url().includes('people.html'));
  await fr.evaluate(() => openNew()); await p.waitForTimeout(500);
  await fr.evaluate(() => { segSet(document.getElementById('n-group'), 'labour'); newGroupChanged(); });
  await p.waitForTimeout(300);
  const labels = await fr.evaluate(() => [document.getElementById('n-desig-l').textContent, document.getElementById('n-gross-l').textContent, getComputedStyle(document.getElementById('n-paytype-row')).display]);
  ck('Labour register asks for Trade, Pay type and Total salary - the Master Data names', labels[0] === 'Trade' && /Total salary/.test(labels[1]) && labels[2] !== 'none', labels);
  await fr.fill('#n-emp_no', 'F-990'); await fr.fill('#n-name', 'TEST LINKED WORKER'); await fr.fill('#n-designation', 'MASON');
  await fr.fill('#n-joined_on', '2026-09-20'); await fr.evaluate(() => segSet(document.getElementById('n-pay_type'), 'fixed'));
  await fr.fill('#n-gross', '1800'); await fr.fill('#n-basic', '1200');
  await p.screenshot({ path: SH + 'link-1-staff-new.png' });
  await fr.evaluate(() => saveNew()); await p.waitForTimeout(2000);
  const emp = await p.evaluate(async () => (await apiCall('/employees?active_only=false')).find(e => e.emp_no === 'F-990'));
  ck('saved on Staff, he is on Master Data with the same trade, pay type, total, basic and joining date',
     emp && emp.trade === 'MASON' && emp.pay_type === 'fixed' && emp.total_salary === 1800 && emp.basic_salary === 1200 && emp.joined_on === '2026-09-20', emp);
  // change on Master Data -> seen on Staff
  await p.goto(B + '/?p=attendance#masterdata'); await p.waitForTimeout(3500);
  await p.evaluate(() => { const e = employees.find(x => x.emp_no === 'F-990'); if (e) editEmployee ? editEmployee(e.emp_no) : null; }).catch(() => {});
  await p.fill('#md-emp-no', 'F-990'); await p.fill('#md-emp-name', 'TEST LINKED WORKER'); await p.fill('#md-emp-trade', 'SENIOR MASON');
  await p.selectOption('#md-emp-paytype', 'fixed'); await p.fill('#md-emp-total', '1800'); await p.fill('#md-emp-basic', '1200'); await p.fill('#md-emp-joined', '2026-09-20');
  await p.evaluate(() => saveEmployee()); await p.waitForTimeout(2000);
  await p.screenshot({ path: SH + 'link-2-masterdata.png' });
  const person = await p.evaluate(async () => (await apiCall('/employees/people/F-990')).person);
  ck('the trade changed on Master Data reads the same on his Staff file', person.designation === 'SENIOR MASON' || person.trade === 'SENIOR MASON', person.trade);
  const count = await p.evaluate(async () => (await apiCall('/employees?active_only=false')).filter(e => e.name === 'TEST LINKED WORKER').length);
  ck('still one worker, never two', count === 1, count);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'ONE LABOURER, ONE RECORD, TWO PAGES');
  await b.close(); process.exit(bad ? 1 : 0);
})();
