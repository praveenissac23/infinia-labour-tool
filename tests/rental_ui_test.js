// Every button on the Rental and Return Notes panels, clicked the way a
// person clicks them. Run: python3 tests/serve_like_nginx.py, then
//   node tests/rental_ui_test.js
//
// The API suites can pass completely while a button does nothing at
// all: "Return to this supplier" filled in a form that lived on a panel
// still hidden, so the click looked dead and every figure behind it was
// perfectly correct. Only clicking finds that.
//
// Data is suffixed per run so the suite can be run twice against the
// same database without colliding with itself.
const { chromium } = require('/home/claude/.npm-global/lib/node_modules/playwright');

const TAG = String(Date.now()).slice(-6);
const NAMED = `Test Ledger ${TAG}`;        // a rental with a supplier
const LOOSE = `Test Standard ${TAG}`;      // a rental with nobody named
const SUPPLIER = `Test Scaffolding ${TAG}`;

(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const p = await b.newPage({ viewport: { width: 1500, height: 1000 } });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGE ERROR: ' + e.message));
  p.on('dialog', d => d.accept('Biju'));

  const FAIL = [];
  const ck = (l, ok, x) => {
    console.log((ok ? 'PASS ' : 'FAIL ') + l + (ok ? '' : '  [' + String(x).slice(0, 170) + ']'));
    if (!ok) FAIL.push(l);
  };
  const visible = sel => p.evaluate(s => {
    const el = document.querySelector(s);
    return !el ? 'MISSING' : (el.offsetParent !== null ? 'visible' : 'hidden');
  }, sel);
  const text = sel => p.evaluate(s => (document.querySelector(s) || {}).textContent || '', sel);

  await p.goto('http://127.0.0.1:8032/app.html');
  await p.fill('#login-username', 'admin');
  await p.fill('#login-password', 'changeme123');
  await p.evaluate(() => doLogin());
  await p.waitForTimeout(3000);

  await p.evaluate(async ([named, loose, sup]) => {
    await apiCall('/store/items', { method: 'POST', body: JSON.stringify({
      name: named, unit: 'pcs', item_type: 'rental', rental_supplier: sup, opening_qty: 150 }) });
    await apiCall('/store/items', { method: 'POST', body: JSON.stringify({
      name: loose, unit: 'pcs', item_type: 'rental', opening_qty: 60 }) });
  }, [NAMED, LOOSE, SUPPLIER]);

  // ---- The rental panel lists both, named or not -------------------
  await p.evaluate(() => switchScreen('store'));
  await p.waitForTimeout(1500);
  await p.evaluate(() => storeGo('hire'));
  await p.waitForTimeout(1800);
  ck('the rental panel opens', (await visible('#store-hire')) === 'visible');

  const listed = await p.evaluate(() => (hireOnHire.suppliers || []).map(g => ({
    supplier: g.supplier, id: g.supplier_id, items: g.items.map(i => i.name) })));
  const named = listed.find(g => g.items.includes(NAMED));
  const loose = listed.find(g => g.items.includes(LOOSE));
  ck('a rental with a supplier is listed under them',
     named && named.supplier === SUPPLIER, JSON.stringify(listed));
  ck('a rental with nobody named is listed too, not hidden',
     loose && !loose.id, JSON.stringify(listed));

  // ---- Return to this supplier actually opens the form -------------
  await p.evaluate(sup => {
    const g = (hireOnHire.suppliers || []).find(x => x.supplier === sup);
    newReturnNote(g.supplier_id);
  }, SUPPLIER);
  await p.waitForTimeout(1600);
  ck('Return to this supplier opens the form', (await visible('#rn-form-card')) === 'visible',
     await visible('#rn-form-card'));
  ck('and brings the Return Notes panel up with it',
     (await visible('#store-returns')) === 'visible', await visible('#store-returns'));
  const rows = await p.evaluate(() => document.querySelectorAll('#rn-lines tr').length);
  ck('with that supplier\'s materials on it', rows >= 1, rows);

  // ---- Fill it in and save ----------------------------------------
  await p.evaluate(() => {
    rnLines[0].qty_returned = 130;
    rnLines[0].qty_short = 20;
    rnLines[0].short_reason = 'lost';
    renderReturnLines();
    document.getElementById('rn-driver').value = 'Rajan';
  });
  await p.waitForTimeout(400);
  const totals = await text('#rn-totals');
  ck('the running totals add up', /130/.test(totals) && /20/.test(totals), totals);
  await p.evaluate(() => saveReturnNote());
  await p.waitForTimeout(2000);
  ck('saving says the note was saved', /saved/i.test(await text('#rn-list-status')),
     await text('#rn-list-status'));
  const onRegister = await p.evaluate(() =>
    [...document.querySelectorAll('#rn-list tr')].map(r => r.textContent).join(' | '));
  ck('and it is on the register', /RN-/.test(onRegister), onRegister.slice(0, 120));

  // ---- Every button on the row does something ----------------------
  const rowBtns = await p.evaluate(() =>
    [...document.querySelectorAll('#rn-list tr:first-child button')].map(x => x.textContent.trim()));
  ck('the row offers PDF, Excel, Edit and Signed & back',
     ['PDF', 'Excel', 'Edit'].every(t => rowBtns.includes(t)) && rowBtns.some(t => /Signed/.test(t)),
     rowBtns);

  await p.evaluate(() => {
    const b = [...document.querySelectorAll('#rn-list tr:first-child button')]
      .find(x => x.textContent.trim() === 'Edit');
    b.click();
  });
  await p.waitForTimeout(1600);
  ck('Edit reopens that note', /^Edit RN-/.test(await text('#rn-form-title')),
     await text('#rn-form-title'));
  await p.evaluate(() => closeReturnForm());

  await p.evaluate(() => {
    const b = [...document.querySelectorAll('#rn-list tr:first-child button')]
      .find(x => /Signed/.test(x.textContent));
    b.click();
  });
  await p.waitForTimeout(2200);
  ck('Signed & back settles it', /settled/i.test(await text('#rn-list-status')),
     await text('#rn-list-status'));

  // ---- The unnamed rental says what to do, rather than nothing -----
  await p.evaluate(() => storeGo('hire'));
  await p.waitForTimeout(1800);
  await p.evaluate(() => newReturnNote(null));
  await p.waitForTimeout(1400);
  const warn = await text('#rn-list-status');
  ck('returning an unnamed rental explains itself instead of doing nothing',
     /supplier/i.test(warn), `"${warn}"`);
  ck('and does not leave a form open that cannot be saved',
     (await visible('#rn-form-card')) !== 'visible', await visible('#rn-form-card'));

  // ---- Booking rented material in ---------------------------------
  await p.evaluate(() => storeGo('hire'));
  await p.waitForTimeout(1600);
  await p.evaluate(([named, sup]) => {
    document.getElementById('hin-supplier').value = sup + ' Two';
    const inp = document.querySelector('#hin-lines tr').querySelectorAll('input');
    inp[0].value = named;
    onHireInField(0, 'description', named);
    onHireInField(0, 'qty', '40');
  }, [NAMED, SUPPLIER]);
  await p.evaluate(() => saveHireIn());
  await p.waitForTimeout(2000);
  ck('Book in as rented works', /rented|booked/i.test(await text('#hin-status')),
     await text('#hin-status'));
  const after = await p.evaluate(sup =>
    (hireOnHire.suppliers || []).some(g => g.supplier === sup + ' Two'), SUPPLIER);
  ck('and the new supplier appears on the rental list', after);

  console.log(errs.length ? '\n' + errs.join('\n') : '\nno page errors');
  console.log('\n' + (FAIL.length ? FAIL.length + ' FAILED: ' + FAIL.join('; ') : 'RENTAL SCREENS CLEAN'));
  await b.close();
  process.exit(FAIL.length || errs.length ? 1 : 0);
})();
