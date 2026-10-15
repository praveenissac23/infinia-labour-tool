// Store & Purchasing > Stock > Docs to office: Amal sends a transmittal,
// Muhsina ticks it in; numbering, buttons, rights, no page errors.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  p.on('dialog', d => d.accept(d.type() === 'prompt' ? 'invoice copy not in the envelope' : undefined));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); return p;
}
const open = async p => { await p.evaluate(() => { pgTab('store'); }); await p.waitForTimeout(700); await p.evaluate(() => pgSub('docs')); await p.waitForTimeout(1800); };
(async () => {
  const b = await chromium.launch();
  const a = await login(b, 'amal', 'pass12345');
  await open(a);
  ck('Docs to office opens for Amal', await a.locator('#screen-docsoffice').isVisible());
  ck('new transmittal numbered DOF:005', await a.locator('#dt-form input[readonly]').inputValue() === 'DOF:005');
  ck('date defaults to today', (await a.locator('#dt-date').inputValue()).length === 10);
  const rows = a.locator('#dt-form .dt-lines tbody tr');
  await rows.nth(0).locator('input[type=text]').nth(0).fill('Delivery note - cement 50 bags');
  await rows.nth(0).locator('input[type=text]').nth(1).fill('84295');
  await a.click('#dt-form >> text=+ Add line'); await a.waitForTimeout(200);
  await rows.nth(1).locator('input[type=text]').nth(0).fill('Tax invoice copy');
  await rows.nth(1).locator('input[type=text]').nth(1).fill('INV-771');
  await a.screenshot({ path: SH + 'docs_office_form.png' });
  await a.click('#dt-save'); await a.waitForTimeout(1500);
  ck('sent: listed with two documents', /DOF:005/.test(await a.locator('#dt-body').textContent()) && await a.locator('#dt-body .dt-l').count() === 2);
  ck('next number is DOF:006', await a.locator('#dt-form input[readonly]').inputValue() === 'DOF:006');
  ck('Preview / PDF / Excel / Share on the row', await a.locator('#dt-body tr').first().locator('button', { hasText: /^(Preview|PDF|Excel|Share)$/ }).count() === 4);
  ck('Amal cannot mark received', await a.locator('#dt-body button', { hasText: 'Mark received' }).count() === 0);
  ck('no page errors (Amal)', a.errs.length === 0, a.errs);
  const m = await login(b, 'muhsina', 'pass12345');
  await open(m);
  ck('Muhsina sees it, without the send form', await m.locator('#dt-body .dt-l').count() === 2 && (await m.locator('#dt-form').innerHTML()).trim() === '');
  await m.locator('.dt-ck').nth(1).uncheck();
  await m.click('#dt-body button:has-text("Mark received")'); await m.waitForTimeout(1500);
  ck('one unticked: shows 1 not received', /1 not received/.test(await m.locator('#dt-body').textContent()));
  await m.screenshot({ path: SH + 'docs_office_checked.png' });
  ck('no page errors (Muhsina)', m.errs.length === 0, m.errs);
  const w = await login(b, 'amal', 'pass12345', 390); await open(w);
  ck('phone width: no sideways scroll', await w.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
