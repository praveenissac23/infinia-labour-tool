// Accounts > Invoices: one tab with Tax Invoice and Proforma Invoice under it.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2000);
  // a fresh sign-in starts on the login's own first page: go to Accounts
  await p.evaluate(() => pgGo('accounts')); await p.waitForTimeout(2000);
  const tabs = await p.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  ck('one Invoices tab, no separate Tax / Proforma tabs', tabs[0] === 'Invoices' && !tabs.includes('Tax Invoice') && !tabs.includes('Proforma Invoice'), tabs);
  await p.click('.pg-tab[data-tab="invoices"]'); await p.waitForTimeout(1200);
  const subs = await p.evaluate(() => [...document.querySelectorAll('#pg-sub .pg-subtab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  // (Receipts joined them on 24 Oct 2026)
  ck('under it: Tax Invoice, Proforma Invoice, Receipts', JSON.stringify(subs) === JSON.stringify(['Tax Invoice', 'Proforma Invoice', 'Receipts']), subs);
  ck('opens on Tax invoices', /Tax/.test(await p.textContent('#inv-list-title')), await p.textContent('#inv-list-title'));
  await p.screenshot({ path: SH + 'invoices_tab.png' });
  await p.click('#pg-sub .pg-subtab[data-sub="proforma"]'); await p.waitForTimeout(1200);
  ck('Proforma Invoice sub-tab', /Proforma/.test(await p.textContent('#inv-list-title')), await p.textContent('#inv-list-title'));
  await p.click('#pg-sub .pg-subtab[data-sub="tax"]'); await p.waitForTimeout(1200);
  ck('back to Tax', /Tax/.test(await p.textContent('#inv-list-title')));
  await p.goto(B + '/?p=accounts#invoices:proforma'); await p.waitForTimeout(3000);
  ck('a link straight to proforma works', /Proforma/.test(await p.textContent('#inv-list-title')), await p.textContent('#inv-list-title'));
  ck('no page errors', errs.length === 0, errs);
  const q = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
  // the chief accountant's login (on the full test database: chiefacc; 'shafiq' there is the bank / Zoho login only)
  await q.goto(B + '/?p=accounts'); await q.fill('#login-username', 'chiefacc'); await q.fill('#login-password', 'chief12345'); await q.evaluate('doLogin()').catch(() => {});
  await q.waitForSelector('#app-screen', { state: 'visible' }); await q.waitForTimeout(3000);
  const t2 = await q.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  ck('chief accountant keeps invoices (moved under Invoices)', t2.includes('Invoices') && !t2.includes('Tax Invoice'), t2);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
