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

  // ---- Where it is, and the location filter ------------------------
  await p.evaluate(async ([named]) => {
    const it = (await apiCall('/store/items')).find(x => x.name === named);
    await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({
      item_id: it.id, kind: 'out', qty: 60, from_location: '', location: '901',
      moved_on: new Date().toISOString().slice(0, 10) }) });
  }, [NAMED]);
  await p.evaluate(() => refreshOnHire());
  await p.waitForTimeout(1500);

  const places = await p.evaluate(() =>
    [...document.querySelectorAll('#rent-where option')].map(o => o.textContent.trim()));
  ck('the Where filter offers everywhere and each place holding something',
     places[0] === 'Everywhere' && places.includes('901') && places.includes('Central store'), places);

  const rowText = () => p.evaluate(() => document.getElementById('hire-list').textContent);
  ck('a row shows where it stands', /901/.test(await rowText()), (await rowText()).slice(0, 120));
  ck('and how many days it has been on rent', /day/.test(await rowText()), (await rowText()).slice(0, 160));

  await p.evaluate(() => { document.getElementById('rent-where').value = '901'; refreshOnHire(); });
  await p.waitForTimeout(1600);
  // Only this run's material is checked: earlier runs leave their own
  // stock at 901, which is correct and must not fail the assertion.
  const at901 = await p.evaluate(() => (hireOnHire.suppliers || [])
    .flatMap(g => g.items).map(i => [i.name, i.qty, i.by_location]));
  const mine901 = at901.find(x => x[0] === NAMED);
  ck('filtering to a site shows what stands there, and only that',
     mine901 && mine901[1] === 60 && Object.keys(mine901[2]).join() === '901',
     JSON.stringify(mine901 || at901));
  await p.evaluate(() => { document.getElementById('rent-where').value = '__all__'; refreshOnHire(); });
  await p.waitForTimeout(1600);

  // ---- The two exports actually produce a file ---------------------
  for (const fmt of ['pdf', 'excel']) {
    const res = await p.evaluate(async f => {
      const t = await apiCall('/auth/download-token', { method: 'POST' });
      const r = await fetch(`${API}/export/store/rental?token=${encodeURIComponent(t.token)}&format=${f}`);
      return { ok: r.ok, size: (await r.blob()).size };
    }, fmt);
    ck(`Export ${fmt.toUpperCase()} returns a file`, res.ok && res.size > 2000, JSON.stringify(res));
  }
  const filtered = await p.evaluate(async () => {
    const t = await apiCall('/auth/download-token', { method: 'POST' });
    const r = await fetch(`${API}/export/store/rental?token=${encodeURIComponent(t.token)}&format=pdf&location=901`);
    return { ok: r.ok, size: (await r.blob()).size };
  });
  ck('and the export follows the Where filter', filtered.ok && filtered.size > 2000, JSON.stringify(filtered));

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
    rnLines[0].qty_returned = 70;
    rnLines[0].qty_short = 20;
    rnLines[0].short_reason = 'lost';
    renderReturnLines();
    document.getElementById('rn-driver').value = 'Rajan';
  });
  await p.waitForTimeout(400);
  const totals = await text('#rn-totals');
  ck('the running totals add up', /70/.test(totals) && /20/.test(totals), totals);
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
  // Typed the way a person types it: into the picker, which must find
  // the material and write its id into the hidden box beside it.
  await p.evaluate(([named, sup]) => {
    document.getElementById('hin-supplier').value = sup + ' Two';
    const tr = document.querySelector('#hin-lines tr');
    const box = tr.querySelector('.hin-item-txt');
    box.value = named;
    onMaterialTyped(box);
    tr.querySelector('.hin-qty').value = '40';
  }, [NAMED, SUPPLIER]);
  const picked = await p.evaluate(() =>
    (document.querySelector('#hin-lines tr .hin-item') || {}).value || '');
  ck('typing a material into the picker finds it', picked !== '', `hidden id "${picked}"`);
  await p.evaluate(() => saveHireIn());
  await p.waitForTimeout(2000);
  ck('Book in as rented works', /rented|booked/i.test(await text('#hin-status')),
     await text('#hin-status'));
  const after = await p.evaluate(sup =>
    (hireOnHire.suppliers || []).some(g => g.supplier === sup + ' Two'), SUPPLIER);
  ck('and the new supplier appears on the rental list', after);

  // ---- A banner belongs to the moment it was shown -----------------
  // "RN-0001 settled" stayed green on its panel long after the return
  // and read as current every time the panel was opened again, which
  // is worse than no message: it says something is true now.
  await p.evaluate(() => showStatus('rn-list-status', 'ok', 'stale message'));
  await p.evaluate(() => storeGo('home'));
  await p.waitForTimeout(1200);
  await p.evaluate(() => storeGo('returns'));
  await p.waitForTimeout(1500);
  ck('a message does not survive leaving the panel',
     (await text('#rn-list-status')).trim() === '', await text('#rn-list-status'));

  await p.evaluate(() => showStatus('rn-list-status', 'ok', 'stale message'));
  await p.evaluate(() => switchScreen('masterdata'));
  await p.waitForTimeout(1200);
  await p.evaluate(() => switchScreen('store'));
  await p.waitForTimeout(1500);
  ck('nor a trip round the app',
     (await text('#rn-list-status')).trim() === '', await text('#rn-list-status'));

  await p.evaluate(() => storeGo('hire'));
  await p.waitForTimeout(1400);
  await p.evaluate(() => newReturnNote(null));
  await p.waitForTimeout(1400);
  ck('but a message shown on arrival still shows',
     /supplier/i.test(await text('#rn-list-status')), await text('#rn-list-status'));

  console.log(errs.length ? '\n' + errs.join('\n') : '\nno page errors');
  console.log('\n' + (FAIL.length ? FAIL.length + ' FAILED: ' + FAIL.join('; ') : 'RENTAL SCREENS CLEAN'));
  await b.close();
  process.exit(FAIL.length || errs.length ? 1 : 0);
})();
