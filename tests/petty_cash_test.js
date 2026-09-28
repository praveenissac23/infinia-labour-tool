// Store & Purchasing > Petty cash: the store keeper enters bills and cash
// received; the running balance, totals, brought-forward, edit, remove,
// and the preview / PDF / Excel all agree. Office (admin) sees the same.
// Needs a login amaltest / amal12345 with store + storekeeper.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'amaltest'); await p.fill('#login-password', 'amal12345'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  const tab = p.locator('#pg-tabs .pg-tab', { hasText: 'Petty cash' });
  ck('the store keeper sees a Petty cash tab in Store & Purchasing', await tab.count() === 1);
  await tab.click(); await p.waitForTimeout(2000);
  ck('the address is /?p=store#petty', p.url().endsWith('/?p=store#petty'), p.url());
  const add = async (kind, date, desc, sup, site, amt) => {
    await p.click(`.pc-kind button[data-k="${kind}"]`);
    await p.fill('#pc-date', date); await p.fill('#pc-desc', desc); await p.fill('#pc-sup', sup);
    await p.selectOption('#pc-site', site); await p.fill('#pc-amt', String(amt)); await p.click('#pc-save'); await p.waitForTimeout(900);
  };
  await add('received', '2026-08-20', 'Cash received', 'CASH/ADCB', '', 2000);
  await add('paid', '2026-08-22', 'Water and ice', 'GRAND MART', '', 150);
  const sites = await p.evaluate(() => [...document.querySelectorAll('#pc-site option')].map(o => o.value).filter(Boolean));
  const s1 = sites[0] || '', s2 = sites[1] || sites[0] || '';
  await add('paid', '2026-09-13', 'Staff refreshment', 'GRAND MART', s1, 300);
  await add('paid', '2026-09-14', 'Cement for plastering', 'AL HASSAI BUILDING', s2, 500);
  await add('received', '2026-09-15', 'CASH RECEIVED', 'CASH/ADCB', '', 5000);
  await add('paid', '2026-09-20', 'Diesel for generator', 'ENOC', s1, 245.5);
  await p.fill('#pc-month', '2026-09'); await p.dispatchEvent('#pc-month', 'change'); await p.waitForTimeout(1200);
  const d = await p.evaluate(() => PC);
  ck('September brings forward August: 2,000 - 150 = 1,850', d.opening === 1850, d.opening);
  ck('running balance line by line: 1,550 / 1,050 / 6,050 / 5,804.50', JSON.stringify(d.rows.map(r => r.balance)) === JSON.stringify([1550, 1050, 6050, 5804.5]), d.rows.map(r => r.balance));
  ck('totals: received 5,000, paid 1,045.50, in hand 5,804.50', d.received === 5000 && d.paid === 1045.5 && d.closing === 5804.5, [d.received, d.paid, d.closing]);
  const foot = await p.locator('#pc-foot').textContent();
  ck('the total line on screen matches', /5,000\.00/.test(foot) && /1,045\.50/.test(foot) && /5,804\.50/.test(foot), foot);
  await p.screenshot({ path: SH + 'petty-1-register.png', fullPage: true });
  await p.click('.pc-kind button[data-k="paid"]'); await p.fill('#pc-desc', ''); await p.fill('#pc-amt', '50'); await p.click('#pc-save'); await p.waitForTimeout(700);
  ck('a bill with no description is refused with a message', /description/i.test(await p.locator('#pc-status').textContent()));
  await p.fill('#pc-desc', 'Future bill'); await p.evaluate(() => { document.getElementById('pc-date').max = ''; }); await p.fill('#pc-date', '2030-01-01'); await p.click('#pc-save'); await p.waitForTimeout(700);
  ck('a future date is refused', /future/i.test(await p.locator('#pc-status').textContent()));
  await p.evaluate(() => pcReset());
  const id = d.rows.find(r => r.description === 'Diesel for generator').id;
  await p.evaluate(i => pcEdit(i), id); await p.fill('#pc-amt', '250'); await p.click('#pc-save'); await p.waitForTimeout(1000);
  ck('editing the diesel bill to 250 moves the balance to 5,800', (await p.evaluate(() => PC.closing)) === 5800);
  await p.evaluate(() => { const r = PC.rows.find(x => x.description === 'Diesel for generator'); pcEdit(r.id); });
  await p.screenshot({ path: SH + 'petty-2-editing.png' });
  await p.click('#pc-cancel');
  const [pop] = await Promise.all([p.waitForEvent('popup'), p.click('#screen-pettycash button:has-text("Preview")')]);
  await pop.waitForLoadState(); await pop.waitForTimeout(800);
  const txt = await pop.locator('.page').textContent();
  ck('preview: title, company, period, brought forward and in-hand agree', /PETTY CASH REGISTER/.test(txt) && /INFINIA CONTRACTING/.test(txt) && /September 2026/.test(txt) && /1,850\.00/.test(txt) && /5,800\.00/.test(txt));
  await pop.screenshot({ path: SH + 'petty-3-preview.png', fullPage: true });
  for (const sel of ['a:has-text("Download PDF")', 'a:has-text("Excel")']) {
    const href = await pop.locator(sel).getAttribute('href');
    const r = await pop.evaluate(async u => { const x = await fetch(u); return [x.status, x.headers.get('content-type'), (await x.arrayBuffer()).byteLength]; }, href);
    ck(`preview ${sel.match(/"(.*)"/)[1]} downloads`, r[0] === 200 && r[2] > 2000, r);
  }
  await pop.close();
  const rid = await p.evaluate(() => PC.rows.find(x => x.description === 'Staff refreshment').id);
  p.evaluate(i => pcDelete(i), rid).catch(() => {}); await p.waitForTimeout(600); await p.locator('.hr-ask [data-a="yes"]').click(); await p.waitForTimeout(1000);
  ck('removing the 300 bill raises the balance to 6,100', (await p.evaluate(() => PC.closing)) === 6100);
  const p2 = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p2.goto(B + '/?p=store#petty'); await p2.fill('#login-username', 'admin'); await p2.fill('#login-password', 'changeme123'); await p2.evaluate('doLogin()');
  await p2.waitForSelector('#app-screen', { state: 'visible' }); await p2.waitForTimeout(3500);
  await p2.fill('#pc-month', '2026-09'); await p2.dispatchEvent('#pc-month', 'change'); await p2.waitForTimeout(1200);
  const who = await p2.evaluate(() => PC.rows.map(r => r.by));
  ck('admin sees the same balance, with who entered each line', (await p2.evaluate(() => PC.closing)) === 6100 && who.every(x => /Amal/.test(x)), who);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'PETTY CASH HOLDS UP');
  await b.close(); process.exit(bad ? 1 : 0);
})();
