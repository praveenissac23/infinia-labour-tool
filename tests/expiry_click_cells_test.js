// Expiry Reminder > People: every cell opens the right document - a
// Missing one to add it (code, document and cursor in Expires on), an
// "on file" or a date to renew it, an empty one to add it, Other to add
// any other document. Labour's visa column is the labour card.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=expiry#expiry:people'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const form = () => p.evaluate(() => ({ emp: hr('hr-doc-emp'), kind: hr('hr-doc-kind'), exp: hr('hr-doc-expires'), focus: document.activeElement && document.activeElement.id,
    banner: document.getElementById('hr-doc-editing').style.display !== 'none' ? document.getElementById('hr-doc-editing').innerText : '', id: document.getElementById('hr-doc-editing').dataset.id }));
  await p.evaluate(() => { window.hr = id => document.getElementById(id).value; });
  // Missing view
  await p.evaluate(() => expCard('missing')); await p.waitForTimeout(800);
  const row = p.locator('#hr-doc-body tr', { hasText: 'F-737' });
  ck('missing list shows F-737', await row.count() === 1);
  await row.locator('td').nth(2).click(); await p.waitForTimeout(600);
  let f = await form();
  ck('Missing under Emirates ID: code F-737, Emirates ID picked, cursor in Expires on', f.emp === 'F-737' && f.kind === 'eid' && f.focus === 'hr-doc-expires', f);
  ck('the form says what is being added, visibly', /Adding Emirates ID for F-737/.test(f.banner) && await p.locator('#hr-doc-editing').isVisible(), f.banner);
  await p.screenshot({ path: SH + 'expiry-click-missing.png' });
  await p.fill('#hr-doc-expires', '2028-05-20'); await p.click('button[onclick="addDocument()"]'); await p.waitForTimeout(1500);
  const docs = (await p.evaluate(() => apiCall('/employees/documents'))).rows;
  ck('saved: F-737 now has an Emirates ID to 20 May 2028', docs.some(d => d.emp_no === 'F-737' && d.kind === 'eid' && d.expires_on === '2028-05-20'));
  await p.evaluate(() => expCard('missing')); await p.waitForTimeout(800);
  await row.locator('td').nth(3).click(); await p.waitForTimeout(500);
  f = await form();
  ck('Missing under Visa for a labourer opens Labour card', f.emp === 'F-737' && f.kind === 'labour_card', f);
  await row.locator('td').nth(2).click(); await p.waitForTimeout(500);
  f = await form();
  ck('his Emirates ID now reads "on file" and opens it to renew', f.kind === 'eid' && f.exp === '2028-05-20' && !!f.id && /Editing/.test(f.banner), f);
  await row.locator('td').nth(5).click(); await p.waitForTimeout(500);
  f = await form();
  ck('Other opens "Other - type the name"', f.emp === 'F-737' && f.kind === 'custom' && f.focus === 'hr-doc-custom', f);
  // Full list
  await p.selectOption('#hr-doc-within', '-1'); await p.dispatchEvent('#hr-doc-within', 'change'); await p.waitForTimeout(800);
  const r2 = p.locator('#hr-doc-body tr', { hasText: 'F-737' });
  await r2.locator('td').nth(4).click(); await p.waitForTimeout(500);   // passport - empty
  f = await form();
  ck('full list: an empty "-" under Passport opens Passport for him', f.emp === 'F-737' && f.kind === 'passport' && f.focus === 'hr-doc-expires', f);
  const r3 = p.locator('#hr-doc-body tr', { hasText: 'F-723' });
  await r3.locator('td').nth(2).click(); await p.waitForTimeout(500);
  f = await form();
  ck('a date still opens that document to renew', f.emp === 'F-723' && f.kind === 'eid' && !!f.exp && /Editing/.test(f.banner), f);
  await p.screenshot({ path: SH + 'expiry-click-full.png' });
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'EVERY CELL OPENS ITS DOCUMENT');
  await b.close(); process.exit(bad ? 1 : 0);
})();
