// On screen (31 Oct 2026): Purchasing > Suppliers has Delete beside Edit - an unused supplier goes after a yes,
// a used one offers "Merge into..." with the likely duplicate first; the LPO form has a Round off box beside
// Discount, its effect shown live, saved, re-opened on edit, printed.
// Run: node tests/supplier_delete_round_off_ui_test.js   (serve_like_nginx.py on 8032, a copy of full.db)
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store#purchasing:suppliers'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const api = (u, m, body) => p.evaluate(([u, m, body]) => apiCall(u, m ? { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined), [u, m, body]);
  const full = { contact_person: 'A', phone: '1', trn: '100000000000003', email: 'a@b.c', payment_terms: 'Net 30' };
  await api('/store/suppliers', 'POST', { name: 'Uni Mix Block Industry', ...full });
  await api('/store/suppliers', 'POST', { name: 'Unimix Block Industry', ...full, email: 'sales@unimix.ae' });
  await api('/store/suppliers', 'POST', { name: 'Typo Supplier Zzz', ...full });
  await api('/store/purchase/orders', 'POST', { supplier_name: 'Unimix Block Industry', order_date: '2026-10-20',
    lines: [{ description: 'BLOCK 20CM', qty: 100, unit: 'nos', rate: 3.05, tax_pct: 5 }] });
  await p.evaluate(() => switchScreen('suppliers')); await p.waitForTimeout(800);
  await p.evaluate(() => loadSuppliersScreen()); await p.waitForTimeout(800);
  const row = n => p.locator('#supplier-list tr', { hasText: n }).first();
  ck('each row: Edit and Delete side by side, on the right', await row('Typo Supplier Zzz').locator('button', { hasText: 'Edit' }).count() === 1
     && await row('Typo Supplier Zzz').locator('button', { hasText: 'Delete' }).count() === 1);
  await row('Typo Supplier Zzz').scrollIntoViewIfNeeded(); await p.screenshot({ path: SH + 'sup-del-1-list.png' });

  // unused: a plain yes / no
  await row('Typo Supplier Zzz').locator('button', { hasText: 'Delete' }).click(); await p.waitForTimeout(700);
  const ask = await p.locator('.hr-ask .hr-ask-msg').textContent();
  ck('unused: "Delete Typo Supplier Zzz? This cannot be undone."', ask === 'Delete Typo Supplier Zzz? This cannot be undone.', ask);
  await p.screenshot({ path: SH + 'sup-del-2-ask.png' });
  await p.locator('.hr-ask [data-a="yes"]').click(); await p.waitForTimeout(1200);
  ck('deleted: gone from the list, said so', await row('Typo Supplier Zzz').count() === 0 && /deleted/.test(await p.locator('#sup-status').textContent()));

  // used: merge into the duplicate
  await row('Unimix Block Industry').locator('button', { hasText: 'Delete' }).click(); await p.waitForTimeout(900);
  const msg = await p.locator('.hr-ask .hr-ask-msg').first().textContent();
  ck('used: says what uses it and that it cannot be deleted', /is used by .*1 LPOs.*cannot be deleted/.test(msg), msg);
  const first = await p.locator('.hr-ask .sm-list label').first().textContent();
  ck('the likely duplicate is offered first: Uni Mix Block Industry', /Uni Mix Block Industry/.test(first) && /looks like the same supplier/.test(first), first);
  await p.fill('.hr-ask .sm-q', 'uni mix'); await p.waitForTimeout(300);
  ck('the pick can be searched', await p.locator('.hr-ask .sm-list label').count() >= 1);
  await p.screenshot({ path: SH + 'sup-del-3-merge.png' });
  ck('Merge stays off until a supplier is picked', await p.locator('.hr-ask [data-a="yes"]').first().isDisabled());
  await p.locator('.hr-ask .sm-list input[type=radio]').first().check(); await p.waitForTimeout(300);
  ck('picked: the button names it', /Merge into Uni Mix Block Industry/.test(await p.locator('.hr-ask [data-a="yes"]').first().textContent()));
  await p.locator('.hr-ask [data-a="yes"]').first().click(); await p.waitForTimeout(500);
  ck('asked once more before anything moves', /cannot be undone/.test(await p.locator('.hr-ask').last().textContent()));
  await p.locator('.hr-ask').last().locator('[data-a="yes"]').click(); await p.waitForTimeout(1500);
  const st = await p.locator('#sup-status').textContent();
  ck('merged: said how many records moved', /Unimix Block Industry merged into Uni Mix Block Industry: \d+ record\(s\) moved/.test(st), st);
  ck('the duplicate is off the list, the kept one is there', await row('Unimix Block Industry').count() === 0 && await row('Uni Mix Block Industry').count() === 1);
  await p.screenshot({ path: SH + 'sup-del-4-merged.png' });

  // ---- LPO form: Round off --------------------------------------------------------------------------------------
  await p.evaluate(() => switchScreen('purchase')); await p.waitForTimeout(600);
  await p.evaluate(() => newLpo()); await p.waitForTimeout(1200);
  await p.fill('#lpo-supplier', 'Uni Mix Block Industry'); await p.dispatchEvent('#lpo-supplier', 'change');
  await p.fill('#lpo-location', '913');
  await p.evaluate(() => { lpoLines = [{ description: 'CONCRETE C40/20', qty: '34', unit: 'M3', rate: '353', tax_pct: '5' },
    { description: 'PUMP 42MTR', qty: '1', unit: 'NOS', rate: '600', tax_pct: '5' }, { description: 'TEMPERATURE CONTROL', qty: '34', unit: 'M3', rate: '12', tax_pct: '5' }];
    renderLpoLines(); renderLpoTotals(); });
  ck('Round off box beside Discount, empty to start', await p.inputValue('#lpo-roundoff') === '');
  const tot = async () => (await p.locator('#lpo-totals').textContent()).replace(/\s+/g, ' ');
  ck('without it: AED 13,660.50', /Total AED 13,660\.50/.test(await tot()), await tot());
  await p.fill('#lpo-roundoff', '0.50');
  ck('typed 0.50: a Round off line and AED 13,661.00 at once', /Round off \+ 0\.50 Total AED 13,661\.00/.test(await tot()), await tot());
  ck('the (i) beside it explains it', (await p.locator('#lpo-roundoff').locator('xpath=..').locator('.help-i').count()) === 1);
  await p.locator('#lpo-roundoff').scrollIntoViewIfNeeded(); await p.screenshot({ path: SH + 'lpo-ro-1-form.png' });
  await p.fill('#lpo-roundoff', '1.20');
  ck('1.20 refused on the spot', /less than 1\.00/.test(await tot()), await tot());
  await p.fill('#lpo-roundoff', '0.50');
  const [pop] = await Promise.all([p.waitForEvent('popup', { timeout: 15000 }).catch(() => null), p.click('#lpo-save-btn')]);
  if (pop) await pop.close();
  await p.waitForTimeout(1500);
  const list = await api('/store/purchase/orders');
  const o = list.find(x => x.total === 13661);
  ck('saved: 13,661.00 on the register', !!o, list.slice(0, 3));
  if (o) {
    await p.evaluate(id => editLpo(id), o.id); await p.waitForTimeout(1500);
    ck('Edit opens it with 0.50 in the box', await p.inputValue('#lpo-roundoff') === '0.50');
    await p.fill('#lpo-roundoff', '');
    ck('cleared: back to 13,660.50', /Total AED 13,660\.50/.test(await tot()) && !/Round off/.test(await tot()), await tot());
    await p.fill('#lpo-roundoff', '0.5'); await p.click('#lpo-save-btn'); await p.waitForTimeout(1500);
    const tok = await p.evaluate(async () => { await refreshDownloadToken(); return cachedDownloadToken; });
    const pg = await b.newPage({ viewport: { width: 1100, height: 1300 } });
    await pg.goto(`${B}/export/purchase/${o.id}/view?token=${encodeURIComponent(tok)}`); await pg.waitForTimeout(1000);
    const money = (await pg.locator('body').textContent()).replace(/\s+/g, ' ');
    ck('the printed order: Round off 0.50 between VAT and Total AED 13,661.00', /Standard Rate \(5%\) ?650\.50 ?Round off ?0\.50 ?Total ?AED 13,661\.00/.test(money),
       money.slice(money.indexOf('Sub Total'), money.indexOf('Sub Total') + 160));
    await pg.screenshot({ path: SH + 'lpo-ro-2-print.png', fullPage: true });
    await pg.close();
    await p.evaluate(() => switchScreen('lporegister')); await p.waitForTimeout(2000);
    const head = await p.locator('#lpr-head').textContent();
    ck('LPO register: a Round off (AED) column just before Total', /Round off \(AED\)\s*Total \(AED\)/.test(head), head);
    await p.screenshot({ path: SH + 'lpo-ro-3-register.png' });
  }
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await b.close(); process.exit(bad ? 1 : 0);
})();
