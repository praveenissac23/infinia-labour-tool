// PRO petty cash: General | Visa. Visa payments are held (not in petty cash)
// until the visa is marked completed; then one total line moves to General.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + '/?p=accounts#petty:pro'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000); return p;
}
(async () => {
  const b = await chromium.launch();
  const j = await login(b, 'jomon', 'pass12345');
  await j.goto(B + '/?p=accounts#petty:pro'); await j.reload(); await j.waitForTimeout(3500);
  ck('PRO: General | Visa, opens on General', await j.locator('#pc-protabs').isVisible() && await j.locator('#pc-cashpane').isVisible() && !(await j.locator('#pc-visapane').isVisible()));
  ck('General form has no visa questions', await j.locator('#pc-visa').count() === 0);
  // a general expense
  await j.fill('#pc-desc', 'Tea powder'); await j.fill('#pc-sup', 'Mohammed Mozamel'); await j.fill('#pc-amt', '44.50');
  await j.click('#pc-save'); await j.waitForTimeout(1800);
  const hand0 = await j.evaluate(() => PC.closing);
  // Visa tab
  await j.click('#pc-protabs [data-v="visa"]'); await j.waitForTimeout(1500);
  ck('Visa tab opens', await j.locator('#pc-visapane').isVisible() && !(await j.locator('#pc-cashpane').isVisible()));
  const add = async (who, step, amt) => { await j.fill('#vh-person', who); await j.fill('#vh-step', step); await j.fill('#vh-amt', String(amt)); await j.click('#vh-save'); await j.waitForTimeout(1500); };
  await j.fill('#vh-person', 'Eric Mambo');
  ck('new name: says a new visa will open', /New visa - opened for Eric Mambo/.test(await j.textContent('#vh-new')));
  ck('step list holds the standard steps', await j.locator('#vh-step-list option').count() >= 18);
  await add('Eric Mambo', 'Medical and EID', 320);
  await add('Eric Mambo', 'New labour contract', 1000);
  await add('Diwakar', 'Typing correction', 75);
  const body = await j.textContent('#vh-body');
  ck('two visas held: Eric 1,320.00, Diwakar 75.00', /Eric Mambo/.test(body) && /1,320\.00/.test(body) && /Diwakar/.test(body) && /75\.00/.test(body), body.slice(0, 200));
  ck('held total AED 1,395.00', /1,395\.00/.test(await j.textContent('#vh-stats')));
  ck('Eric offered under Whose visa', await j.evaluate(() => [...document.querySelectorAll('#vh-person-list option')].some(o => o.value === 'Eric Mambo')));
  await j.locator('#vh-body tr', { hasText: 'Eric Mambo' }).locator('button', { hasText: 'View' }).click(); await j.waitForTimeout(300);
  ck('View: the payments one by one', await j.locator('#vh-body .vh-pays tr').count() === 2);
  await j.screenshot({ path: SH + 'visa_tab.png' });
  // General: not booked yet, balance reduced
  await j.click('#pc-protabs [data-v="cash"]'); await j.waitForTimeout(1800);
  ck('General: visa payments not in petty cash yet', !/Eric Mambo/.test(await j.textContent('#pc-body')));
  const st = await j.textContent('#pc-stats');
  ck('Balance in hand takes the held money off', /after AED 1,395\.00 visa payments held/.test(st) && await j.evaluate(h => Math.abs(PC.closing - PC.visa_held - (h - 1395)) < 0.01, hand0), st);
  // complete Eric
  await j.click('#pc-protabs [data-v="visa"]'); await j.waitForTimeout(1200);
  await j.locator('#vh-body tr', { hasText: 'Eric Mambo' }).locator('button', { hasText: 'Mark completed' }).click(); await j.waitForTimeout(300);
  await j.locator('.hr-ask [data-a="yes"]').click(); await j.waitForTimeout(1800);
  ck('completed: Eric leaves Ongoing, listed under Completed', !/Eric Mambo/.test(await j.textContent('#vh-body')) && /Eric Mambo/.test(await j.textContent('#vh-done')));
  await j.click('#pc-protabs [data-v="cash"]'); await j.waitForTimeout(1800);
  const first = await j.locator('#pc-body tr').first().textContent();
  ck('General: one line "Eric Mambo - visa expenses", 1,320.00, on top', /Eric Mambo - visa expenses \(2 payments\)/.test(first) && /1,320\.00/.test(first), first);
  await j.locator('#pc-body .pc-vbd').first().click(); await j.waitForTimeout(800);
  ck('click: breakdown of the 2 payments', await j.locator('.vh-m .vh-pays tr').count() === 3 && /1,320\.00/.test(await j.textContent('.vh-m')));
  await j.screenshot({ path: SH + 'visa_breakdown.png' });
  await j.locator('.vh-m button', { hasText: 'Close' }).click();
  ck('balance now held 75.00 only', /after AED 75\.00 visa payments held/.test(await j.textContent('#pc-stats')));
  const z = await j.evaluate(async () => { try { await apiCall(`/store/petty-cash/${PC.rows.find(r => r.visa_file_id).id}`, { method: 'DELETE' }); return 'deleted'; } catch (e) { return errText(e); } });
  ck('the total line cannot be removed in General', /reopen the visa/i.test(z), z);
  await j.screenshot({ path: SH + 'visa_general.png' });
  ck('no page errors', j.errs.length === 0, j.errs);
  await j.goto(B + '/?p=accounts#petty:office'); await j.waitForTimeout(2500);
  ck('other books: no General | Visa tabs', !(await j.locator('#pc-protabs').isVisible()));
  const w = await login(b, 'jomon', 'pass12345', 390);
  ck('phone width: no sideways scroll', await w.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
