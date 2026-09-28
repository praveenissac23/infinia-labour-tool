// Expiry Reminder (its own page): any kind of expiry. People get any
// document by name ("Other - type the name"); vehicles, licences and
// anything else go on the second list, with free categories. Sorted by
// what expires first, renew by clicking, preview / PDF / Excel.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=expiry'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  await p.waitForTimeout(1500);
  const iso = n => { const d = new Date(Date.now() + 4 * 3600e3 + n * 864e5); return d.toISOString().slice(0, 10); };
  // a person's own named document
  await p.fill('#hr-doc-emp', 'IC001'); await p.selectOption('#hr-doc-kind', 'custom'); await p.waitForTimeout(200);
  ck('"Other - type the name" opens a name box', await p.locator('#hr-doc-custom').isVisible());
  await p.fill('#hr-doc-custom', 'Safety card'); await p.fill('#hr-doc-expires', iso(20)); await p.click('#screen-expiry button:has-text("Save document")'); await p.waitForTimeout(1500);
  const named = await p.evaluate(() => HR_DOCS.find(x => x.emp_no === 'IC001' && x.kind_label === 'Safety card'));
  ck('a person can be given any document by name (Safety card, due in 20 days)', named && named.status === 'urgent', named);
  await p.screenshot({ path: SH + 'expiry-1-people.png' });
  // vehicles and others
  await p.locator('#pg-sub .pg-subtab', { hasText: 'Company' }).click(); await p.waitForTimeout(1200);
  const add = async (cat, item, kind, num, exp, notes) => {
    await p.fill('#hr-exp-cat', cat); await p.fill('#hr-exp-item', item); await p.fill('#hr-exp-kind', kind);
    await p.fill('#hr-exp-number', num); await p.fill('#hr-exp-expires', exp); await p.fill('#hr-exp-notes', notes);
    await p.click('#hr-doc-company button:has-text("Save")'); await p.waitForTimeout(1000);
  };
  await add('Vehicle', 'Toyota Hilux - Dubai P 12345', 'Registration (Mulkiya)', 'P 12345', iso(12), 'With Rajesh, site 912');
  await add('Vehicle', 'Toyota Hilux - Dubai P 12345', 'Insurance', 'POL-88213', iso(75), '');
  await add('Vehicle', 'Nissan Urvan - Dubai K 45120', 'Registration (Mulkiya)', 'K 45120', iso(-3), 'Renewal booked');
  await add('Trade licence', 'Infinia Contracting LLC', 'Trade licence', 'DED 812345', iso(160), '');
  await add('Equipment', 'Mobile crane 25T', 'Third-party inspection certificate', 'TPI-5521', iso(40), '');
  await add('NOC', 'Villa 347 Sobha Hartland', 'Developer NOC', 'SH-NOC-2291', iso(55), 'Renew before handover');
  await add('Permit', 'Villa 347 Sobha Hartland', 'Road closure permit', 'RTA-77120', iso(8), '');
  const rows = await p.evaluate(() => HR_EXP.rows.map(r => [r.item.split(' - ')[0], r.kind, r.status]));
  ck('seven items saved (incl. a NOC and a permit), the expired Urvan first, then by days left', rows.length === 7 && rows[0][2] === 'expired' && rows[1][1] === 'Road closure permit', rows);
  ck('a category typed once is offered next time (Equipment)', await p.evaluate(() => HR_EXP.categories.includes('Equipment')));
  await p.screenshot({ path: SH + 'expiry-2-vehicles.png', fullPage: true });
  // renew by clicking: new date
  await p.locator('#hr-exp-body tr', { hasText: 'Nissan Urvan' }).click(); await p.waitForTimeout(300);
  await p.fill('#hr-exp-expires', iso(365)); await p.click('#hr-doc-company button:has-text("Save")'); await p.waitForTimeout(1000);
  ck('renewing the Urvan: click the line, type the new date - now valid', await p.evaluate(() => HR_EXP.rows.find(r => r.item.startsWith('Nissan')).status) === 'valid');
  await p.selectOption('#hr-exp-within', '30'); await p.waitForTimeout(300);
  ck('"Due in 30 days" shows the Hilux registration and the road permit', (await p.locator('#hr-exp-body tr').count()) === 2);
  await p.selectOption('#hr-exp-within', '-1');
  const [pop] = await Promise.all([p.waitForEvent('popup'), p.click('#hr-doc-company .hr-menu-btn').then(() => p.click('#hr-doc-company .hr-menu-list button:has-text("Preview")'))]);
  await pop.waitForLoadState(); await pop.waitForTimeout(800);
  ck('preview lists the items', /Vehicle Expiry Tracker/.test(await pop.content()) && /Mobile crane/.test(await pop.content()));
  await pop.screenshot({ path: SH + 'expiry-3-preview.png' });
  const st = await pop.evaluate(async () => { const a = document.querySelector('a[href*="expiries"]'); if (!a) return 'no link'; const r = await fetch(a.href); return r.status; });
  ck('the PDF downloads from the preview', st === 200, st);
  await pop.close();
  // a login with only the Expiry Reminder right
  const q = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  q.on('pageerror', e => errs.push(e.message));
  await q.goto(B + '/'); await q.fill('#login-username', 'docsonly'); await q.fill('#login-password', 'docs12345'); await q.evaluate('doLogin()');
  await q.waitForSelector('#app-screen', { state: 'visible' }); await q.waitForTimeout(2500);
  const menu = await q.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  ck('a login given only Expiry Reminder sees just that page in the menu', menu.join('|') === 'Expiry Reminder', menu);
  await q.click('.pg-side .pg-item[data-page="expiry"]'); await q.waitForTimeout(2000);
  ck('and the people list opens for him', (await q.locator('#hr-doc-body tr').count()) > 3);
  const pay = await q.evaluate(async () => { try { await apiCall('/employees/staff'); return 'open'; } catch (e) { return 'refused'; } });
  ck('office salaries stay closed to him', pay === 'refused', pay);
  await q.locator('#pg-sub .pg-subtab', { hasText: 'Company' }).click(); await q.waitForTimeout(1200);
  ck('he sees the company documents too', (await q.locator('#hr-exp-body tr').count()) >= 7);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'ANY EXPIRY, ONE TRACKER');
  await b.close(); process.exit(bad ? 1 : 0);
})();
