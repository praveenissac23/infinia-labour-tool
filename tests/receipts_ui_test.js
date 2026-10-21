// Accounts > Invoices > Receipts and the PAID stamp: receive payment from a tax invoice, part against a second, oldest first,
// stamp the invoice paid in full, cancel takes money and stamp off, receipt PDF.   node tests/receipts_ui_test.js
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032'; const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i))); };
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 1100 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load/.test(m.text())) errs.push(m.text()); });
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  const api = (path, opt) => p.evaluate(([path, opt]) => apiCall(path, opt), [path, opt]);
  // two tax invoices for one client
  const mk = async (no, amt) => (await api('/employees/accounts/invoices', { method: 'POST', body: JSON.stringify({ kind: 'tax', number: no, date: '2026-10-01', client: 'Emkaan Design LLC', client_trn: '100345678900003', client_address: 'Sharjah Media City, Sharjah', project_no: '914', project: 'VE-208 Villa', lines: [{ description: 'PC ' + no, amount: amt, vat: 5 }] }) })).id;
  const run = Date.now() % 1000;
  const i1 = await mk('IC/26/914/T' + run + 'A', 75000), i2 = await mk('IC/26/914/T' + run + 'B', 50000);
  await p.goto(B + '/?p=accounts#invoices:tax'); await sleep(3500);
  // Receive payment from the first invoice
  await p.evaluate(id => rcFromInvoice(id), i1); await sleep(3000);
  ck('Receipts opens with the invoice ticked for its balance', (await p.inputValue('#rc-amt')).replace(/,/g, '') === '78750.00', await p.inputValue('#rc-amt'));
  ck('both open invoices of the client listed', await p.locator('#rc-inv tr').count() >= 2, await p.locator('#rc-inv tr').count());
  // tick the second one too, then type 100,000 -> 78,750 + 21,250
  const boxes = p.locator('#rc-inv input[type=checkbox]');
  for (let k = 0; k < await boxes.count(); k++) { if (!(await boxes.nth(k).isChecked())) { await boxes.nth(k).check(); } }
  await p.fill('#rc-amt', '100000'); await p.dispatchEvent('#rc-amt', 'input'); await sleep(200);
  await p.click('.rc-modes button:has-text("Cheque")'); await p.fill('#rc-ref', '000184'); await p.fill('#rc-bank', 'Emirates NBD'); await p.fill('#rc-chq', '2026-10-21');
  await p.fill('#rc-notes', 'Payment for MEP and pool works');
  
  await p.click('#rc-save'); await sleep(2500);
  const r = await api('/employees/accounts/receipts');
  const mine = r.rows[0];
  ck('saved: 100,000 set oldest first (78,750 + 21,250)', mine.amount === 100000 && mine.allocations.length >= 2 && Math.abs(mine.applied - 100000) < .01, mine);
  const inv = await api('/employees/accounts/invoices?kind=tax');
  const a = inv.rows.find(x => x.id === i1), b = inv.rows.find(x => x.id === i2);
  ck('invoice paid in full got the PAID stamp, the other did not', a.paid_stamp && !b.paid_stamp && a.balance === 0, [a.paid_stamp, b.paid_stamp, a.balance, b.balance]);
  
  await p.goto(B + '/?p=accounts#invoices:tax'); await sleep(3500);
  
  // cancel the receipt -> stamp comes off
  await api(`/employees/accounts/receipts/${mine.id}/cancel`, { method: 'POST', body: '{}' });
  const inv2 = await api('/employees/accounts/invoices?kind=tax');
  ck('cancelling the receipt takes the money and the stamp off', !inv2.rows.find(x => x.id === i1).paid_stamp && inv2.rows.find(x => x.id === i1).balance === 78750);
  // the receipt PDF
  const t = await p.evaluate(async () => { await refreshDownloadToken(); return cachedDownloadToken; });
  const pdf = await ctx.request.get(`${B}/export/accounts/receipt/${mine.id}?token=${encodeURIComponent(t)}`);
  
  ck('receipt PDF', (await pdf.body()).slice(0, 4).toString() === '%PDF');
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? bad + ' FAILED' : 'ALL PASS');
})();
