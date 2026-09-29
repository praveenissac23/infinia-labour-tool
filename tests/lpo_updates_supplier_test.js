// The purchase manager fills supplier details on the LPO, not on the
// supplier list - so the LPO keeps the supplier list up to date: a new
// supplier is added with everything typed, a changed phone/TRN/email
// replaces the old one, an empty box never blanks the list, the LPO's
// default terms never overwrite agreed terms, and editing an LPO counts.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store#purchasing:purchase'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const api = (u, m, body) => p.evaluate(([u, m, body]) => apiCall(u, m ? { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined), [u, m, body]);
  const sup = async name => (await api('/store/suppliers')).find(s => s.name.toLowerCase().replace(/[^a-z]/g, '') === name.toLowerCase().replace(/[^a-z]/g, ''));
  const line = [{ description: 'Cement OPC 50kg', qty: 10, unit: 'bag', rate: 20 }];

  // 1. In the browser, as the purchase manager does it: a new supplier typed on the LPO.
  await p.evaluate(() => newLpo()); await p.waitForTimeout(1200);
  await p.fill('#lpo-supplier', 'Gulf Star Building Materials LLC'); await p.dispatchEvent('#lpo-supplier', 'change');
  await p.fill('#lpo-trn', '100234567800003'); await p.fill('#lpo-sup-contact', 'rashid khan');
  await p.fill('#lpo-sup-phone', '050 111 2233'); await p.fill('#lpo-sup-email', 'sales@gulfstar.ae'); await p.fill('#lpo-terms', '30 days');
  const ins = p.locator('#lpo-lines tr').first().locator('input');
  await ins.nth(0).fill('Cement OPC 50kg'); await p.keyboard.press('Escape');
  await ins.nth(2).fill('10'); await ins.nth(4).fill('20');
  const [pop] = await Promise.all([p.waitForEvent('popup', { timeout: 15000 }).catch(() => null), p.click('#lpo-save-btn')]);
  if (pop) await pop.close();
  await p.waitForTimeout(1500);
  const msg = await p.locator('#lpo-status').textContent();
  ck('saving the LPO says the supplier list was updated', /Supplier list updated for Gulf Star/i.test(msg), msg);
  await p.screenshot({ path: SH + 'lpo-sup-1-saved.png' });
  let s = await sup('Gulf Star Building Materials LLC');
  ck('the new supplier is on the supplier list with TRN, contact, phone, email and terms',
     s && s.trn === '100234567800003' && s.contact_person === 'Rashid Khan' && s.phone === '050 111 2233' && s.email === 'sales@gulfstar.ae' && s.payment_terms === '30 days', s);

  // 2. Next LPO: new phone, email left empty, terms left at the default.
  const r2 = await api('/store/purchase/orders', 'POST', { supplier_name: 'GULF STAR BUILDING MATERIALS LLC', supplier_phone: '055 999 0000', supplier_trn: '100234567800003', terms: 'Due on Receipt', lines: line });
  s = await sup('Gulf Star Building Materials LLC');
  ck('a new phone on a later LPO replaces the old one', s.phone === '055 999 0000', s.phone);
  ck('the email left empty on that LPO stays on the list', s.email === 'sales@gulfstar.ae', s.email);
  ck('"Due on Receipt" (the default) does not overwrite the agreed 30 days', s.payment_terms === '30 days', s.payment_terms);
  ck('the answer names what changed: phone only', JSON.stringify(r2.supplier_updated) === '["phone"]', r2.supplier_updated);
  ck('same supplier typed in capitals is not added twice', (await api('/store/suppliers')).filter(x => /gulf star/i.test(x.name)).length === 1);

  // 3. Editing an LPO also counts.
  const r3 = await api(`/store/purchase/orders/${r2.id}`, 'PUT', { supplier_name: 'Gulf Star Building Materials LLC', supplier_phone: '055 999 0000', supplier_trn: '100234567800099', supplier_email: 'accounts@gulfstar.ae', terms: '60 days', lines: line });
  s = await sup('Gulf Star Building Materials LLC');
  ck('correcting the TRN, email and terms on an LPO edit updates the list', s.trn === '100234567800099' && s.email === 'accounts@gulfstar.ae' && s.payment_terms === '60 days', s);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'THE LPO KEEPS THE SUPPLIER LIST UP TO DATE');
  await b.close(); process.exit(bad ? 1 : 0);
})();
