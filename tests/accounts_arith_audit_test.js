// Accounts arithmetic on the screens themselves: the figures a form shows while it is filled in must be the
// figures the saved record, its PDF and Zoho carry (see accounts_arith_audit_test.py for the server side).
//   * Tax invoice form: VAT per line exactly as the saved invoice (85,538.10 x 5% = 4,276.90, total 89,815.00 -
//     the form used to show 4,276.91 / 89,815.01), over awkward amounts, each one saved and compared.
//   * LPO form: each line's own VAT rate on its discounted amount (a 0% line stays 0% with a discount), and
//     every LPO on file shows on the form the total the register has.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123');
  await p.evaluate('doLogin()').catch(() => {});
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  const num = t => +String(t).replace(/[^0-9.\-]/g, '');

  // ---- tax invoice form against the saved invoice ----------------------------------------------------
  const cases = [[85538.10], [1234.50, 100.10], [20000.30], [0.30], [2.50], [12.50, 0.10], [190476.19], [16713.33], [3920, 3200],
                 [37258.25], [999999.99], [0.01], [0.09, 0.11, 0.13]];
  for (let i = 0; i < 25; i++) cases.push([Math.round(Math.random() * 5e7) / 100]);
  const lines = c => c.map((a, j) => ({ description: 'Audit line ' + (j + 1), amount: a, vat: 5 })).concat(c.length > 1 ? [{ description: 'Authority fee', amount: 500, vat: 0 }] : []);
  let n = 0, wrong = [];
  for (const c of cases) {
    const ls = lines(c);
    const form = await p.evaluate(ls => { INV_LINES = ls.map(l => ({ ...l })); invTotals();
      return ['inv-sub', 'inv-vat', 'inv-tot'].map(id => document.getElementById(id).textContent); }, ls);
    const r = await p.evaluate(async ls => { const no = 'AUDIT/' + Math.random().toString(36).slice(2, 9);
      const x = await apiCall('/employees/accounts/invoices', { method: 'POST', body: JSON.stringify({ kind: 'tax', number: no, date: '2026-10-01', client: 'Audit Client', lines: ls }) });
      const row = (await apiCall('/employees/accounts/invoices?kind=tax')).rows.find(r => r.id === x.id);
      await apiCall(`/employees/accounts/invoices/${x.id}/cancel`, { method: 'POST', body: JSON.stringify({ reason: 'arithmetic audit' }) });
      return row; }, ls);
    n++;
    if (Math.abs(num(form[0]) - r.subtotal) > 0.001 || Math.abs(num(form[1]) - r.vat) > 0.001 || Math.abs(num(form[2]) - r.total) > 0.001)
      wrong.push({ lines: c, form, saved: [r.subtotal, r.vat, r.total] });
  }
  ck(`tax invoice form shows the saved subtotal / VAT / total (${n} invoices, awkward amounts)`, !wrong.length, wrong.slice(0, 4));
  const ipa = await p.evaluate(() => { INV_LINES = [{ description: 'IPA03', amount: 85538.10, vat: 5 }]; invTotals(); return document.getElementById('inv-tot').textContent; });
  ck('85,538.10 + 5% on the form: AED 89,815.00, as saved and as in Zoho', /89,815\.00/.test(ipa), ipa);

  // ---- LPO form ---------------------------------------------------------------------------------------
  const lpoTotal = (ls, d) => { const k = 1 - d / 100; const net = ls.reduce((a, l) => a + l.qty * l.rate, 0) * k;
    const vat = ls.reduce((a, l) => a + l.qty * l.rate * k * l.tax_pct / 100, 0); return Math.round((net + vat) * 100) / 100; };
  const shown = (ls, d, ro) => p.evaluate(([ls, d, ro]) => { lpoLines = ls.map(l => ({ ...l, qty: String(l.qty), rate: String(l.rate), tax_pct: String(l.tax_pct) }));
    document.getElementById('lpo-discount').value = String(d); document.getElementById('lpo-roundoff').value = ro ? String(ro) : ''; renderLpoTotals();
    const t = document.getElementById('lpo-totals').textContent; return t.slice(t.lastIndexOf('AED')); }, [ls, d, ro || 0]);
  const mix = [{ description: 'Rebar', qty: 3.333, rate: 1234.567, tax_pct: 5 }, { description: 'Cement', qty: 7, rate: 18.25, tax_pct: 5 },
               { description: 'DM fee', qty: 1, rate: 105, tax_pct: 0 }];
  let t = await shown(mix, 7.5);
  ck(`LPO form, 7.5% discount with a 0% authority fee: AED ${lpoTotal(mix, 7.5).toFixed(2)} (no VAT on the fee)`, Math.abs(num(t) - lpoTotal(mix, 7.5)) < 0.006, t);
  t = await shown(mix, 0);
  ck(`LPO form, no discount: AED ${lpoTotal(mix, 0).toFixed(2)}`, Math.abs(num(t) - lpoTotal(mix, 0)) < 0.006, t);
  // round off to the supplier's invoice (IC/LPO/20260130 and 20260144): on the total, no VAT on it
  const c130 = [{ description: 'CONCRETE C40/20', qty: 34, rate: 353, tax_pct: 5 }, { description: 'PUMP 42MTR', qty: 1, rate: 600, tax_pct: 5 },
                { description: 'TEMPERATURE CONTROL', qty: 34, rate: 12, tax_pct: 5 }];
  const c144 = [{ description: 'CONCRETE C40/20', qty: 11, rate: 348, tax_pct: 5 }, { description: 'PUMP 42MTR', qty: 1, rate: 600, tax_pct: 5 }];
  t = await shown(c130, 0); ck('LPO form 20260130 without a round off: AED 13,660.50', /13,660\.50/.test(t), t);
  t = await shown(c130, 0, '0.50'); ck('LPO form 20260130 with round off 0.50: AED 13,661.00 (the invoice)', /13,661\.00/.test(t), t);
  t = await shown(c144, 0, '-0.40'); ck('LPO form 20260144 with round off -0.40: AED 4,649.00 (the invoice)', /4,649\.00/.test(t), t);
  const vatTxt = await p.evaluate(() => document.getElementById('lpo-totals').textContent);
  ck('VAT is not charged on the round off (221.40 still), Round off line shown', /VAT\s*221\.40/.test(vatTxt) && /Round off\s*-\s*0\.40/.test(vatTxt), vatTxt);
  t = await shown(c144, 0, '1.00');
  const errTxt = await p.evaluate(() => document.getElementById('lpo-totals').textContent);
  ck('round off 1.00 refused on the form (less than 1.00 either way), total left as without it', /less than 1\.00/.test(errTxt) && /4,649\.40/.test(t), errTxt);
  t = await shown(c144, 0, '0.505');
  ck('round off 0.505 refused on the form (2 decimals)', /2 decimals/.test(await p.evaluate(() => document.getElementById('lpo-totals').textContent)), t);
  const reg = await p.evaluate(async () => { const out = []; for (const o of (await apiCall('/store/purchase/orders?limit=5000')).slice(0, 80)) {
    const d = await apiCall(`/store/purchase/orders/${o.id}`); out.push({ ref: o.ref, total: o.total, disc: d.discount_pct || 0, ro: d.round_off || 0, lines: d.lines }); } return out; });
  await p.evaluate(() => { document.getElementById('lpo-roundoff').value = ''; });
  wrong = [];
  for (const o of reg) {
    const s = await shown(o.lines.map(l => ({ description: l.description, qty: l.qty, rate: l.rate, tax_pct: l.tax_pct })), o.disc, o.ro);
    if (Math.abs(num(s) - o.total) > 0.006) wrong.push([o.ref, s, o.total]);
  }
  ck(`every LPO on file (${reg.length}) shows on the form the total the register has`, !wrong.length, wrong.slice(0, 5));
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await b.close(); process.exit(bad ? 1 : 0);
})();
