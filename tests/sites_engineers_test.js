// Settings > Companies & sites: sites and engineers as tables. Add, edit
// and remove each through the screen and check the server and the lists
// that use them (attendance site/engineer boxes).
const { chromium } = require('playwright');
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); let bad = 0; const errs = [];
  const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
  p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto('http://127.0.0.1:8032/?p=settings#companies'); await p.fill('#login-username','admin'); await p.fill('#login-password','changeme123'); await p.evaluate('doLogin()'); await p.waitForTimeout(3000);
  const api = u => p.evaluate(async x => apiCall(x), u);
  const n0 = (await api('/sites')).length;
  ck('sites show as a table, one row each', await p.locator('#md-site-list tbody tr').count() === n0, n0);
  ck('the add form is closed until asked for', !(await p.locator('#md-site-form').isVisible()));
  await p.screenshot({ path: '/tmp/claude-0/shots/sites.png', clip: { x: 220, y: 100, width: 1220, height: 640 } });
  await p.click('button:has-text("+ Add site")'); ck('+ Add site opens the form', await p.locator('#md-site-form').isVisible());
  await p.fill('#md-site-code', '999'); await p.fill('#md-site-plot', 'Plot 12-34'); await p.fill('#md-site-incharge', 'RAVI'); await p.fill('#md-site-mobile', '0501234567'); await p.fill('#md-site-address', 'Street 5, Al Quoz');
  await p.click('button:has-text("Save site")'); await p.waitForTimeout(1200);
  const s1 = (await api('/sites')).find(s => s.code === '999');
  ck('Save site adds it with every detail', s1 && s1.plot_no === 'Plot 12-34' && s1.incharge === 'RAVI' && s1.address === 'Street 5, Al Quoz', s1);
  ck('the form closes and the row appears', !(await p.locator('#md-site-form').isVisible()) && await p.locator('#md-site-list tr', { hasText: 'Plot 12-34' }).count() === 1);
  ck('the new site is in the attendance site list', await p.evaluate(() => [...document.getElementById('bulk-site').options].some(o => o.value === '999')));
  await p.locator('#md-site-list tr', { hasText: '999' }).locator('button:has-text("Edit")').click();
  ck('Edit opens the form filled in', await p.locator('#md-site-form').isVisible() && await p.inputValue('#md-site-plot') === 'Plot 12-34');
  await p.fill('#md-site-incharge', 'RAVI KUMAR'); await p.click('button:has-text("Save site")'); await p.waitForTimeout(1200);
  ck('the change is saved', ((await api('/sites')).find(s => s.code === '999') || {}).incharge === 'RAVI KUMAR');
  await p.locator('#md-site-list tr', { hasText: '999' }).locator('button:has-text("Remove")').click(); await p.waitForTimeout(1200);
  ck('Remove takes it off', !(await api('/sites')).some(s => s.code === '999') && await p.locator('#md-site-list tr', { hasText: 'RAVI KUMAR' }).count() === 0);
  // engineers
  await p.click('button:has-text("+ Add engineer")'); await p.fill('#md-eng-name', 'TEST ENGINEER'); await p.fill('#md-eng-mobile', '0559998888');
  await p.click('button:has-text("Save engineer")'); await p.waitForTimeout(1200);
  ck('an engineer is added with his mobile', ((await api('/engineers')).find(e => e.name === 'TEST ENGINEER') || {}).mobile === '0559998888');
  ck('and appears in the attendance engineer list', await p.evaluate(() => [...document.getElementById('bulk-engineer').options].some(o => o.value === 'TEST ENGINEER')));
  await p.locator('#md-eng-list tr', { hasText: 'TEST ENGINEER' }).locator('button:has-text("Edit")').click();
  await p.fill('#md-eng-mobile', '0551112222'); await p.click('button:has-text("Save engineer")'); await p.waitForTimeout(1200);
  ck('his mobile is changed', ((await api('/engineers')).find(e => e.name === 'TEST ENGINEER') || {}).mobile === '0551112222');
  await p.locator('#md-eng-list tr', { hasText: 'TEST ENGINEER' }).locator('button:has-text("Remove")').click(); await p.waitForTimeout(1200);
  ck('and removed', !(await api('/engineers')).some(e => e.name === 'TEST ENGINEER'));
  // companies: same pattern
  ck('the company form is closed until asked for', !(await p.locator('#co-form').isVisible()));
  await p.click('button:has-text("+ Add company")'); await p.fill('#co-name', 'TEST TRADING LLC'); await p.fill('#co-short', 'TestCo'); await p.fill('#co-prefix', 'TT');
  await p.click('button:has-text("Save company")'); await p.waitForTimeout(1500);
  const co = (await api('/employees/companies')).find(c => c.name === 'TEST TRADING LLC');
  ck('a company is added', co && co.short_name === 'TestCo', co);
  ck('and is in the company lists (e.g. Master data)', await p.evaluate(() => [...document.querySelectorAll('select[data-companies] option')].some(o => /TestCo/.test(o.textContent))));
  await p.locator('#companies-body tr', { hasText: 'TEST TRADING LLC' }).locator('button:has-text("Edit")').click();
  ck('Edit opens it filled in', await p.inputValue('#co-short') === 'TestCo');
  await p.fill('#co-trn', '100200300400500'); await p.click('button:has-text("Save company")'); await p.waitForTimeout(1500);
  ck('the TRN is saved', ((await api('/employees/companies')).find(c => c.name === 'TEST TRADING LLC') || {}).trn === '100200300400500');
  await p.screenshot({ path: '/tmp/claude-0/shots/sites.png', clip: { x: 220, y: 100, width: 1220, height: 700 } });
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'SITES AND ENGINEERS: ADD, EDIT, REMOVE ALL WORK');
  await b.close(); process.exit(bad ? 1 : 0); })();
