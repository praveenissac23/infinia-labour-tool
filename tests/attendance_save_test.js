const { chromium } = require('playwright');
(async () => { const b = await chromium.launch();
for (const url of ['/?p=attendance', '/app-classic.html']) {
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  let sent = 0; p.on('request', r => { if (r.url().includes('/attendance/save')) sent++; });
  await p.goto('http://127.0.0.1:8032' + url); await p.fill('#login-username','admin'); await p.fill('#login-password','changeme123'); await p.evaluate('doLogin()'); await p.waitForTimeout(3500);
  if (url.includes('classic')) { await p.evaluate("switchScreen('attendance')"); await p.waitForTimeout(2500); }
  const i = url.includes('classic') ? 12 : 9; const row = p.locator('#grid-body tr').nth(i); const sels = row.locator('select');
  await sels.nth(0).selectOption('Absent'); await sels.nth(1).selectOption('Absent'); await p.waitForTimeout(300);
  await p.click('#floating-save-btn'); await p.waitForTimeout(3000);
  const st = await p.evaluate(() => document.getElementById('att-status').textContent);
  // read it back from the server
  const emp = await row.locator('td.empno').textContent();
  const back = await p.evaluate(async e => (await apiCall('/attendance/' + currentDate)).find(r => r.emp_no === e), emp);
  console.log(url, '| request sent:', sent, '| message:', st.replace(/\s+/g, ' ').slice(0, 90), '| on server:', emp, back && back.am, back && back.pm, '| errors:', errs.length);
  await p.close(); }
await b.close(); })();
