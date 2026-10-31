// Send to Zoho > Petty cash: Send Anyway (no open bill - supplier advance) and Send Excess (more than
// the bill), each with its confirm box; Bank tab shows the advance; Sent to Zoho shows the chip and
// the Supplier advances list. Zoho's supplier and bill look-ups are stood in by the browser.
//   server: DATABASE_URL=sqlite:////<copy of full.db> SRV_PORT=8950 SRV_API_PORT=8951 python3 tests/serve_like_nginx.py
//   run:    ADV_PORT=8950 ADV_DB=/<copy of full.db> node tests/zoho_advance_ui_test.js
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const B = `http://127.0.0.1:${process.env.ADV_PORT || 8950}`, DB = process.env.ADV_DB, SH = (process.env.ADV_SHOTS || '/tmp/claude-0/shots') + '/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
const BILLS = { 'V-ENG': [], 'V-SWD': [{ id: 'B-1', number: 'ENG-26-041', date: '2026-10-20', due: '', total: 800, balance: 800, status: 'open' }],
                'V-AKS': [{ id: 'B-2', number: 'AK-77', date: '2026-10-21', due: '', total: 1200, balance: 1200, status: 'open' }] };
const VENDORS = [{ id: 'V-ENG', name: 'EngiNova Technical Services' }, { id: 'V-SWD', name: 'Swaidan Trading Co LLC' }, { id: 'V-AKS', name: 'Al Kashif Steel' }];
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  const approves = []; const pull = async () => { approves.length = 0; approves.push(...await p.evaluate(() => window.__approves || [])); };
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  const today = await p.evaluate(() => pcToday());
  for (const [desc, amt, sup] of [['ADVT Salary for Enginova Staff by Cash', 1175, 'EngiNova Technical Services L.L.C'], ['ADVT Manpower week 42', 1175, 'Swaidan Trading'], ['ADVT Steel bars', 500, 'Al Kashif Steel']])
    await p.evaluate(async a => apiCall('/store/petty-cash', { method: 'POST', body: JSON.stringify({ book: 'office', date: a[3], description: a[0], supplier: a[2], site: '', received: 0, paid: a[1], vat: false, trn: '', receipt_no: '1486' }) }), [desc, amt, sup, today]);
  await p.evaluate(() => pgGo('accounts')); await p.waitForTimeout(2000); await p.evaluate(() => pgTab('zoho')); await p.waitForTimeout(3000);
  // Zoho's suppliers and their open bills, stood in inside the page (Zoho is not connected here)
  await p.evaluate(([V, BL]) => {
    const real = window.apiCall; window.__approves = [];
    window.apiCall = async (u, o) => {
      if (u.startsWith('/store/zoho/vendors')) return { vendors: V };
      if (u.startsWith('/store/zoho/bills')) return { bills: BL[new URLSearchParams(u.split('?')[1]).get('vendor_id')] || [] };
      if (u.startsWith('/store/zoho/approve')) window.__approves.push(JSON.parse(o.body));
      return real(u, o);
    };
  }, [VENDORS, BILLS]);
  await p.evaluate(async () => { await zhVendorsLoad(); zhDraw(); });
  await p.evaluate(() => zhPane('petty')); await p.fill('#zh-q', 'ADVT'); await p.waitForTimeout(300);
  const row = d => p.locator('#zh-body tr', { hasText: d });
  async function payTo(desc, vendor) {
    await row(desc).locator('select.zh-kind').selectOption('payment'); await p.waitForTimeout(200);
    await row(desc).locator('input.zh-vendor').fill(vendor); await row(desc).locator('input.zh-vendor').dispatchEvent('change'); await p.waitForTimeout(800);
  }
  // ---- Send Anyway ----
  await payTo('ADVT Salary', 'EngiNova Technical Services');
  let t = await row('ADVT Salary').textContent();
  ck('no open bill: amber note, not red', /No open bill in Zoho for this supplier · advance 1,175\.00/.test(t) && !(await row('ADVT Salary').getAttribute('class')).includes('zh-fix'), t);
  ck('no open bill: "Send Anyway (advance)" button, tick box off', await row('ADVT Salary').locator('button', { hasText: 'Send Anyway(advance)' }).count() === 1
     && await row('ADVT Salary').locator('input[type=checkbox]').isDisabled());
  ck('bill choice still reads "No open bill in Zoho"', /No open bill in Zoho/.test(await row('ADVT Salary').locator('select.zh-bill').textContent()));
  await p.screenshot({ path: SH + 'adv_petty_anyway.png' });
  await row('ADVT Salary').locator('button', { hasText: 'Send Anyway' }).click(); await p.waitForTimeout(300);
  const m1 = await p.locator('.zx-modal').textContent();
  ck('confirm box: supplier, amount, what Zoho records', /EngiNova Technical Services/.test(m1) && /AED 1,175\.00/.test(m1) && /No bill applied · advance 1,175\.00/.test(m1) && /unused amount \(supplier advance \/ payment on account\)/.test(m1), m1);
  await p.screenshot({ path: SH + 'adv_confirm_anyway.png' });
  await p.click('.zx-modal #za-no'); await p.waitForTimeout(300);
  await pull(); ck('Cancel sends nothing', approves.length === 0 && await p.locator('.zx-modal').count() === 0);
  await row('ADVT Salary').locator('button', { hasText: 'Send Anyway' }).click(); await p.waitForTimeout(300);
  await p.click('.zx-modal #za-yes'); await p.waitForTimeout(1500);
  await pull(); const a1 = approves[0] && approves[0].lines[0];
  ck('approve carries advance "advance", supplier, no bill', a1 && a1.advance === 'advance' && a1.vendor_id === 'V-ENG' && a1.bill_id === '' && a1.zoho_kind === 'payment', a1);
  ck('the line left the waiting list', await row('ADVT Salary').count() === 0);
  // ---- Send Excess ----
  await payTo('ADVT Manpower', 'Swaidan Trading Co LLC');
  t = await row('ADVT Manpower').textContent();
  ck('more than the bill: "Bill ENG-26-041 balance 800.00 · applied 800.00 · advance 375.00"', /Bill ENG-26-041 balance 800\.00 · applied 800\.00 · advance 375\.00/.test(t), t);
  ck('more than the bill: "Send Excess" button', await row('ADVT Manpower').locator('button', { hasText: 'Send Excess' }).count() === 1);
  await p.screenshot({ path: SH + 'adv_petty_excess.png' });
  await row('ADVT Manpower').locator('button', { hasText: 'Send Excess' }).click(); await p.waitForTimeout(300);
  const m2 = await p.locator('.zx-modal').textContent();
  ck('confirm box: bill, applied, advance', /Bill ENG-26-041 balance 800\.00 · applied 800\.00 · advance 375\.00/.test(m2) && /becomes paid/.test(m2), m2);
  await p.screenshot({ path: SH + 'adv_confirm_excess.png' });
  await p.click('.zx-modal #za-yes'); await p.waitForTimeout(1500);
  await pull(); const a2 = approves[1] && approves[1].lines[0];
  ck('approve carries advance "excess" and the bill', a2 && a2.advance === 'excess' && a2.bill_id === 'B-1' && a2.bill_no === 'ENG-26-041', a2);
  // ---- unchanged: within the bill ----
  await payTo('ADVT Steel', 'Al Kashif Steel');
  t = await row('ADVT Steel').textContent();
  ck('within the bill: plain Send, no advance note, tick box on', !/advance/i.test(t.replace(/Advance/g, 'x')) && await row('ADVT Steel').locator('button', { hasText: /^Send$/ }).count() === 1
     && !(await row('ADVT Steel').locator('input[type=checkbox]').isDisabled()), t);
  await row('ADVT Steel').locator('button', { hasText: /^Send$/ }).click(); await p.waitForTimeout(1500);
  await pull(); const a3 = approves[2] && approves[2].lines[0];
  ck('within the bill: no confirm box, request has no advance key', a3 && !('advance' in a3) && a3.bill_id === 'B-2', a3);
  // ---- Bank tab ----
  await p.evaluate(async d => apiCall('/store/bank', { method: 'POST', body: JSON.stringify({ kind: 'vendor', date: d, party: 'ADVT Bank Supplier', party_id: 'V-BNK', amount: 1175, mode: 'Bank Transfer', reference: 'ADVT-REF',
                                                                                          docs: [{ id: 'B-9', number: 'ENG-9', amount: 800 }] }) }), today);
  await p.evaluate(() => zhLoad()); await p.waitForTimeout(2000); await p.evaluate(() => zhPane('bank')); await p.waitForTimeout(500);
  const bt = await p.locator('#zh-bank tr', { hasText: 'ADVT Bank Supplier' }).textContent();
  ck('Bank: advance shown, button reads Send Excess', /Bills ENG-9 applied 800\.00 · advance 375\.00/.test(bt) && /Send Excess/.test(bt), bt);
  await p.screenshot({ path: SH + 'adv_bank.png' });
  // ---- Sent to Zoho: chip and Supplier advances ----
  if (DB) execSync(`python3 - <<'PY'
import sqlite3, json, datetime
c = sqlite3.connect('${DB}')
now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
uid = c.execute("select id from users where username='admin'").fetchone()[0]
for i, (amt, adv, appl) in enumerate([(1175.0, 1175.0, 0.0), (1175.0, 375.0, 800.0)]):
    c.execute("insert into zoho_log (at,user_id,source,item_id,ref,action,kind,zoho_id,number,on_date,amount,from_acc,to_acc,detail,ok,error) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (now, uid, 'petty', None, 'PC-ADVT%d' % i, 'create', 'vendorpayment', 'VPX%d' % i, str(9900 + i), '${today}', amt, 'Company Petty Cash', 'ADVT EngiNova (supplier)',
               json.dumps({"advance": adv, "applied": appl, "vendor_id": "V-ENG"}), 1, ''))
c.commit()
PY`);
  await p.evaluate(() => zhPane('sent')); await p.waitForTimeout(1500); await p.fill('#zs-q', 'ADVT'); await p.waitForTimeout(300);
  const st = await p.locator('#zs-body').textContent();
  ck('Sent to Zoho: chip "Advance – to be adjusted" with applied / advance', (st.match(/Advance – to be adjusted/g) || []).length === 2 && /applied 800\.00 · advance 375\.00/.test(st), st);
  await p.screenshot({ path: SH + 'adv_sent.png' });
  await p.click('#screen-zoho button:has-text("Supplier advances")'); await p.waitForTimeout(1200);
  const av = await p.locator('#zs-adv').textContent();
  ck('Supplier advances: supplier once, both payments, total', /ADVT EngiNova/.test(av) && /2 payments · advance 1,550\.00/.test(av) && /375\.00/.test(av), av.slice(0, 400));
  ck('Supplier advances: Sent to Zoho table hidden while open', !(await p.locator('#zs-body').isVisible()));
  await p.screenshot({ path: SH + 'adv_list.png' });
  await p.click('#zs-adv button:has-text("Back to Sent to Zoho")'); await p.waitForTimeout(300);
  ck('Back returns to Sent to Zoho', await p.locator('#zs-body').isVisible() && !(await p.locator('#zs-adv').isVisible()));
  ck('no page errors', errs.length === 0, errs);
  await b.close();
  console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
