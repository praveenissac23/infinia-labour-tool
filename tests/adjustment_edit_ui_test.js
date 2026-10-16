// Labour Additions & deductions: Edit sits next to Remove and corrects the entry in place.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1200);
  await p.evaluate(() => { pgGo("payroll"); pgTab("labourpay"); pgSub("adjust"); }); await p.waitForTimeout(1800);
  // a cycle that has workers
  for (let i = 0; i < 8; i++) {
    if (await p.locator('#adj-worker-body tr.clickable-row').count()) break;
    await p.evaluate(i => { const s = document.getElementById('adj-cycle'); s.selectedIndex = i; s.onchange(); }, i); await p.waitForTimeout(1200);
  }
  await p.locator('#adj-worker-body tr.clickable-row').first().click(); await p.waitForTimeout(500);
  await p.fill('#adj-desc', 'Fine -Not Wearing Helmet'); await p.fill('#adj-amount', '50'); await p.selectOption('#adj-type', 'true');
  await p.click('#adj-save'); await p.waitForTimeout(1200);
  const line = p.locator('#adj-list > div', { hasText: 'Fine -Not Wearing Helmet' });
  ck('entry added', await line.count() === 1);
  ck('Edit and Remove side by side on the right', await line.locator('button', { hasText: 'Edit' }).count() === 1 && await line.locator('button', { hasText: 'Remove' }).count() === 1);
  await p.screenshot({ path: SH + 'adj_edit_1.png' });
  await line.locator('button', { hasText: 'Edit' }).click(); await p.waitForTimeout(300);
  ck('boxes filled from the entry', await p.inputValue('#adj-desc') === 'Fine -Not Wearing Helmet' && await p.inputValue('#adj-amount') === '50');
  ck('button reads Save changes', (await p.textContent('#adj-save')).trim() === 'Save changes' && await p.locator('#adj-cancel').isVisible());
  await p.fill('#adj-amount', '75'); await p.screenshot({ path: SH + 'adj_edit_2.png' });
  await p.click('#adj-save'); await p.waitForTimeout(1200);
  const after = p.locator('#adj-list > div', { hasText: 'Fine -Not Wearing Helmet' });
  ck('still one entry', await after.count() === 1);
  ck('amount now 75', (await after.innerText()).includes('75.00'), await after.innerText());
  ck('worker list shows -75.00', (await p.locator('#adj-worker-body tr.selected-row').innerText()).includes('-75.00'));
  ck('form back to Add', (await p.textContent('#adj-save')).trim() === 'Add' && !(await p.locator('#adj-cancel').isVisible()));
  await p.screenshot({ path: SH + 'adj_edit_3.png' });
  // Cancel leaves it alone
  await after.locator('button', { hasText: 'Edit' }).click(); await p.fill('#adj-amount', '999'); await p.click('#adj-cancel'); await p.waitForTimeout(300);
  ck('cancel keeps 75', (await p.locator('#adj-list > div', { hasText: 'Fine -Not Wearing Helmet' }).innerText()).includes('75.00'));
  await p.locator('#adj-list > div', { hasText: 'Fine -Not Wearing Helmet' }).locator('button', { hasText: 'Remove' }).click(); await p.waitForTimeout(1200);
  ck('remove still works', await p.locator('#adj-list > div', { hasText: 'Fine -Not Wearing Helmet' }).count() === 0);
  ck('no page errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILURE(S)` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
