// Combined LPO on the form: hidden until switched on; then each item says who pays (filled from its request),
// the split is shown, and the saved LPO keeps it - the printed LPO unchanged.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.goto(B + '/?p=store#purchasing:purchase'); await sleep(2500);
  await p.evaluate(() => { window.checkBuild = () => {}; const z = document.getElementById('build-bar'); if (z) z.remove(); });
  await p.evaluate(async () => { await newLpo(); });
  await sleep(800);
  ck('a normal LPO: the combined part is closed', await p.evaluate(() => !document.getElementById('lpo-combined').checked && document.getElementById('lpo-cmb-body').style.display === 'none'));
  await p.evaluate(() => {
    document.getElementById('lpo-supplier').value = 'Al Waha Hardware Trading LLC'; document.getElementById('lpo-location').value = 'STORE';
    lpoLines.length = 0;
    [['SAFETY COVERALL (WORKLAND)', 20, 'pcs', 28, 'MR-0041', 'STORE'], ['WIRE NAIL 2.5"', 25, 'kg', 6.5, 'MR-0042', '913'], ['SOFT BRUSH 12" WITH STICK', 6, 'pcs', 14, 'MR-0043', '910'],
     ['WHITE SILICONE 300ML', 24, 'pcs', 9.5, 'MR-0043', '910'], ['MMA WELDING MACHINE ( ESAB ROGUE ES201I)', 1, 'nos', 1450, 'MR-0041', 'STORE']]
      .forEach(([d, q, u, r, ref, st]) => lpoLines.push({ item_id: null, description: d, description2: '', qty: q, unit: u, rate: r, tax_pct: 5, last: null, req_ref: ref, req_site: st }));
    renderLpoLines(); lpoCmbHint();
  });
  ck('materials for several sites: a hint to switch it on', await p.evaluate(() => /3 sites/.test(document.getElementById('lpo-cmb-hint').textContent)));
  await p.evaluate(() => document.getElementById('lpo-cmb').scrollIntoView({ block: 'center' }));
  await p.screenshot({ path: OUT + '/lpo-combined-off.png' });
  await p.click('#lpo-cmb .cmb-h'); await sleep(400);
  const sel = await p.evaluate(() => [...document.querySelectorAll('#lpo-cmb-body select')].map(s => s.value));
  ck('switched on: who pays filled in from each request', JSON.stringify(sel) === JSON.stringify(['STORE', '913', '910', '910', 'STORE']), sel);
  const chips = await p.evaluate(() => [...document.querySelectorAll('#lpo-cmb-body .chip')].map(c => c.textContent.replace(/\s+/g, ' ').trim()));
  ck('the split: Store / 910 / 913', chips.join('|').replace(/ /g, '') === 'StorestockAED2,110.50|Site910AED327.60|Site913AED170.63', chips);
  await p.evaluate(() => document.getElementById('lpo-cmb').scrollIntoView({ block: 'center' }));
  await p.screenshot({ path: OUT + '/lpo-combined-on.png' });
  // a qty change updates the split
  await p.evaluate(() => { lpoLines[1].qty = 50; renderLpoTotals(); });
  ck('changing a qty updates the split', await p.evaluate(() => /Site 913\s*AED 341\.25/.test(document.getElementById('lpo-cmb-body').textContent)));
  await p.evaluate(() => { lpoLines[1].qty = 25; renderLpoTotals(); });
  // save
  const [tab] = await Promise.all([ctx.waitForEvent('page'), p.click('#lpo-save-btn')]);
  await sleep(2500);
  const saved = await p.evaluate(async () => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    const l = (await (await fetch('/store/purchase/report?group_by=order&measures=total&status=all', { headers: { Authorization: 'Bearer ' + T } })).json()).rows[0];
    return (await fetch(`/store/purchase/orders/${l.id}`, { headers: { Authorization: 'Bearer ' + T } })).json(); });
  ck('saved: combined, each line with who pays', saved.combined && saved.lines.map(l => l.cost_to).join() === 'STORE,913,910,910,STORE', saved);
  await sleep(1500);
  const printed = await tab.content();
  ck('the LPO that opens shows one location, no split', /STORE/.test(printed) && !/Cost to|Site 913|>913</.test(printed));
  await tab.screenshot({ path: OUT + '/lpo-combined-printed.png' });
  // edit: comes back switched on
  await p.evaluate(id => editLpo(id), saved.id); await sleep(1500);
  ck('edit: opens with the split as saved', await p.evaluate(() => document.getElementById('lpo-combined').checked && [...document.querySelectorAll('#lpo-cmb-body select')].map(s => s.value).join() === 'STORE,913,910,910,STORE'));
  ck('no script errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
