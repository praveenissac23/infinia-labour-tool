// Purchasing on screen (31 Oct 2026, Arun's questionnaire):
//  - Material arrived: a direct LPO is listed; 'Book delivery' asks for the DN number, books part, then all
//  - Order follow-up: the direct LPO's lines are there with 'It arrived'; an approved request with no LPO has
//    'Bought with petty cash'
//  - LPO register: delivery status, Delivery and Bill buttons; the bill difference is shown as it is typed
//  - LPO form: the Service tick follows the words (pump ticked, cement not); the tick is saved
//  - Rentals: LPO names <-> Rentals names, 'Link the same names', add, take off
//  - no script errors; screenshots of each
//    BASE=http://127.0.0.1:8850 OUT=/tmp/x NODE_OPTIONS=--require=./tests/_relogin_shim.js node tests/purchasing_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8850', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  let dialogs = []; p.on('dialog', d => { dialogs.push(d.message()); d.accept(); });
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  const api = (u, o) => p.evaluate(async ([u, o]) => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    const r = await fetch(u, Object.assign({ headers: { Authorization: 'Bearer ' + T, 'Content-Type': 'application/json' } }, o || {})); return [r.status, await r.json()]; }, [u, o]);
  const kill = () => p.evaluate(() => { window.checkBuild = () => {}; const z = document.getElementById('build-bar'); if (z) z.remove(); });
  for (const s of ['913', '919']) await api('/sites', { method: 'POST', body: JSON.stringify({ code: s, active: true }) });
  await p.evaluate(async () => { try { sites = await apiCall('/sites'); } catch (e) {} });
  const [, cem] = await api('/store/items', { method: 'POST', body: JSON.stringify({ name: 'Cement Ultratech', unit: 'bag', item_type: 'consumable' }) });
  const [, po] = await api('/store/purchase/orders', { method: 'POST', body: JSON.stringify({ supplier_name: 'Al Danube', order_date: '2026-10-21', project_location: '913',
    lines: [{ item_id: cem.id, description: 'Cement Ultratech', qty: 100, unit: 'bag', rate: 16, tax_pct: 5 }, { description: 'TRANSPORTATION', qty: 1, unit: 'trip', rate: 80, tax_pct: 5 }] }) });

  // ---- Material arrived ------------------------------------------------------------------------------------
  await p.goto(B + '/?p=store#store:arrive'); await sleep(2500); await kill();
  await p.evaluate(() => { if (typeof pgStorePanel === 'function') pgStorePanel('arrive'); else storeGo('arrive'); }); await sleep(2000);
  const arr = await p.evaluate(() => [...document.querySelectorAll('#arrive-list .arr-lpo')].map(x => x.innerText));
  ck('Material arrived lists the direct LPO, with its site and "direct LPO"', arr.some(t => t.includes(po.ref) && /913/.test(t) && /direct LPO/i.test(t)), arr);
  await p.screenshot({ path: OUT + '/pu-material-arrived.png' });
  await p.evaluate(id => lpoDlvOpen(id, m => { window.__msg = m; loadArrivePanel(); }), po.id); await sleep(1500);
  const modal = await p.evaluate(() => { const m = document.getElementById('pu-dlv'); return m && m.classList.contains('on') ? m.innerText : ''; });
  ck('the delivery window: DN number, date, delivered to 913, both lines, transport marked a service', /DN number/i.test(modal) && /Service - no stock/.test(modal)
     && await p.evaluate(() => document.getElementById('pu-where').value) === '913', modal.slice(0, 400));
  await p.screenshot({ path: OUT + '/pu-delivery-window.png' });
  await p.fill('#pu-dlv tr[data-l] .pu-q', '60');
  await p.click('#pu-dlv-save'); await sleep(800);
  const warn = await p.evaluate(() => document.getElementById('pu-dlv-status').innerText);
  ck('no DN number: it asks for it, nothing saved', /DN number/.test(warn), warn);
  await p.fill('#pu-dn', 'DN-4401'); await p.click('#pu-dlv-save'); await sleep(1800);
  ck('part delivery saved: Part delivered', /Part delivered/.test(await p.evaluate(() => window.__msg || '')), await p.evaluate(() => window.__msg));
  const [, d1] = await api(`/store/purchase/orders/${po.id}/deliveries`);
  ck('...60 of 100 came, 40 to come, at 913', d1.lines[0].delivered === 60 && d1.lines[0].remaining === 40 && d1.history[0].to === '913' && d1.history[0].dn === 'DN-4401', d1.lines);
  await p.evaluate(id => lpoDlvOpen(id, m => { window.__msg = m; }), po.id); await sleep(1200);
  await p.click('text=Everything still to come arrived'); await p.fill('#pu-dn', 'DN-4402'); await p.click('#pu-dlv-save'); await sleep(1800);
  ck('the rest: Delivered', /Delivered/.test(await p.evaluate(() => window.__msg || '')), await p.evaluate(() => window.__msg));

  // ---- Order follow-up: direct LPO lines; petty cash for a request with no LPO ------------------------------
  const [, po2] = await api('/store/purchase/orders', { method: 'POST', body: JSON.stringify({ supplier_name: 'Srayedin', order_date: '2026-10-21', project_location: '919',
    lines: [{ description: 'Black Sand 3M3', qty: 3, unit: 'trip', rate: 300, tax_pct: 5 }] }) });
  const [, br] = await api('/store/items', { method: 'POST', body: JSON.stringify({ name: 'Plastic Broom', unit: 'nos', item_type: 'consumable' }) });
  const [, mr] = await api('/store/requests', { method: 'POST', body: JSON.stringify({ site: '913', requested_by: 'Amal', urgency: 'normal', notes: '', lines: [{ item_id: br.id, qty_requested: 20, unit: 'nos' }] }) });
  await api(`/store/requests/${mr.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'approved' }) });
  await p.goto(B + '/?p=store#requests:followup'); await sleep(3000); await kill();
  if (!await p.evaluate(() => document.getElementById('fu-list') && document.getElementById('fu-list').offsetParent)) { await p.evaluate(() => typeof pgGo === 'function' && pgGo('store', 'requests', 'followup')); await sleep(2500); }
  await p.evaluate(() => loadFollowUp()); await sleep(1500);
  const fu = await p.evaluate(() => [...document.querySelectorAll('#fu-list tbody tr')].map(tr => tr.innerText));
  ck('follow-up: the direct LPO\'s line, with It arrived', fu.some(t => /Black Sand/.test(t) && t.includes(po2.ref) && /It arrived/.test(t)), fu);
  ck('follow-up: the request with no LPO offers Bought with petty cash', fu.some(t => /Plastic Broom/.test(t) && /petty cash/i.test(t)), fu);
  await p.screenshot({ path: OUT + '/pu-followup.png' });
  await p.evaluate(id => pettyArriveOpen(id, m => { window.__msg = m; loadFollowUp(); }), mr.id); await sleep(1500);
  await p.screenshot({ path: OUT + '/pu-petty.png' });
  await p.click('#pcx-save'); await sleep(1800);
  ck('petty cash arrival saved', /petty cash/.test(await p.evaluate(() => window.__msg || '')), await p.evaluate(() => window.__msg));
  const fu2 = await p.evaluate(() => [...document.querySelectorAll('#fu-list tbody tr')].map(tr => tr.innerText));
  ck('...and the broom is off the chase list', !fu2.some(t => /Plastic Broom/.test(t) && t.includes(mr.ref)), fu2);
  ck('...and the transport (a service) of the delivered LPO is off it too', !fu2.some(t => /TRANSPORTATION/.test(t) && t.includes(po.ref)), fu2);

  // ---- LPO register: status, Delivery, Bill ----------------------------------------------------------------
  await p.goto(B + '/?p=store#purchase:lporegister'); await sleep(3000); await kill();
  if (!await p.evaluate(() => document.getElementById('lpr-body') && document.getElementById('lpr-body').offsetParent)) { await p.evaluate(() => typeof pgGo === 'function' && pgGo('store', 'purchase', 'lporegister')); await sleep(2500); }
  await p.evaluate(() => { document.getElementById('lpr-show').value = 'all'; loadLpoReport(); }); await sleep(1800);
  const reg = await p.evaluate(() => [...document.querySelectorAll('#lpr-body tr')].map(tr => tr.innerText));
  ck('register: Delivered / Ordered shown per LPO', reg.some(t => t.includes(po.ref) && /Delivered/.test(t)) && reg.some(t => t.includes(po2.ref) && /Ordered/.test(t)), reg);
  ck('register: Delivery and Bill buttons on the row', await p.evaluate(() => !!document.querySelector('#lpr-body .lpr-dlv') && !!document.querySelector('#lpr-body .lpr-bill')));
  await p.screenshot({ path: OUT + '/pu-register.png' });
  await p.evaluate(id => lpoBillOpen(id, m => { window.__msg = m; loadLpoReport(); }), po.id); await sleep(1500);
  await p.fill('#pb-no', 'AD/2231'); await p.fill('#pb-date', '2026-10-28'); await p.fill('#pb-amt', '1764'); await p.dispatchEvent('#pb-amt', 'input'); await sleep(300);
  const diff = await p.evaluate(() => document.getElementById('pb-diff').innerText);
  ck('bill window: the difference to the LPO total is shown (1,764.00 vs 1,764.00 -> same)', /Same as the LPO total/.test(diff), diff);
  await p.fill('#pb-amt', '1770'); await p.dispatchEvent('#pb-amt', 'input'); await sleep(200);
  ck('...a different amount says how much more', /6\.00 more/.test(await p.evaluate(() => document.getElementById('pb-diff').innerText)));
  await p.fill('#pb-amt', '1764'); await p.check('#pb-ok'); await p.screenshot({ path: OUT + '/pu-bill.png' });
  await p.click('#pu-bill .btn-primary'); await sleep(1800);
  const reg2 = await p.evaluate(() => [...document.querySelectorAll('#lpr-body tr')].map(tr => tr.innerText));
  ck('register: bill checked shown', reg2.some(t => t.includes(po.ref) && /bill checked/.test(t)), reg2);

  // ---- LPO form: the Service tick ----------------------------------------------------------------------------
  await p.goto(B + '/?p=store#purchase:purchase'); await sleep(2500); await kill();
  await p.evaluate(() => newLpo()); await sleep(1200);
  await p.fill('#lpo-lines tr:nth-child(1) .lpo-mat', 'PUMP 42MTR'); await sleep(500);
  ck('LPO form: typing "PUMP 42MTR" ticks Service', await p.evaluate(() => document.querySelector('#lpo-lines tr .lpo-svc').checked));
  await p.evaluate(() => addLpoLine()); await sleep(300);
  await p.fill('#lpo-lines tr:nth-child(2) .lpo-mat', 'Cement Ultratech'); await sleep(500);
  ck('...cement is not a service', !(await p.evaluate(() => document.querySelectorAll('#lpo-lines tr .lpo-svc')[1].checked)));
  await p.evaluate(() => { const b = document.querySelectorAll('#lpo-lines tr .lpo-svc')[0]; b.click(); });
  ck('...unticking keeps it unticked (the person decides)', await p.evaluate(() => lpoLines[0].service === false));
  await p.screenshot({ path: OUT + '/pu-lpo-form.png' });

  // ---- Rentals links ------------------------------------------------------------------------------------------
  await api('/store/items', { method: 'POST', body: JSON.stringify({ name: 'Rental Ledger 1.2M', unit: 'nos', item_type: 'asset' }) });
  await api('/store/hire/in', { method: 'POST', body: JSON.stringify({ supplier_name: 'Desarch', received_on: '2026-10-27', location: '919', reference: '402417', lines: [{ item_id: (await api('/store/items'))[1].find(i => i.name === 'Rental Ledger 1.2M').id, qty: 85 }] }) });
  await api('/store/purchase/orders', { method: 'POST', body: JSON.stringify({ supplier_name: 'Desarch', order_date: '2026-10-23', project_location: '919',
    lines: [{ description: 'Ledger 1.2m', qty: 85, unit: 'nos', rate: 0.35, tax_pct: 5 }] }) });
  await p.goto(B + '/?p=store#rentals:hire'); await sleep(2500); await kill();
  if (!await p.evaluate(() => document.getElementById('rmap-card') && document.getElementById('rmap-card').offsetParent)) { await p.evaluate(() => typeof pgGo === 'function' && pgGo('store', 'rentals', 'hire')); await sleep(2500); }
  ck('Rentals: the links card is there', await p.evaluate(() => !!document.getElementById('rmap-card') && document.getElementById('rmap-card').offsetParent !== null));
  await p.click('text=Link the same names'); await sleep(1500);
  const rows = await p.evaluate(() => [...document.querySelectorAll('#rmap-body tr')].map(tr => tr.innerText));
  ck('"Link the same names": Ledger 1.2m = Rental Ledger 1.2M', rows.some(t => /Ledger 1\.2m/.test(t) && /Rental Ledger 1\.2M/.test(t)), rows);
  await p.fill('#rmap-lpo', 'Ledger 1.2 mtr'); await p.selectOption('#rmap-rental', { label: await p.evaluate(() => [...document.querySelectorAll('#rmap-rental option')].find(o => /Rental Ledger 1\.2M/.test(o.text)).text) });
  await p.click('#rmap-card .btn-primary'); await sleep(1200);
  const st = await p.evaluate(() => document.getElementById('rmap-status').innerText);
  ck('a link added by hand (same plain name - said it is there already, or linked)', /Linked|already/.test(st), st);
  await p.screenshot({ path: OUT + '/pu-rentals-links.png' });
  const n0 = await p.evaluate(() => document.querySelectorAll('#rmap-body tr').length);
  await p.click('#rmap-body tr:first-child button'); await sleep(1200);
  ck('a link taken off', await p.evaluate(() => document.querySelectorAll('#rmap-body tr').length) === n0 - 1 || /No links/.test(await p.evaluate(() => document.getElementById('rmap-body').innerText)));

  // ---- phone width: the delivery window fits ---------------------------------------------------------------------
  await p.setViewportSize({ width: 390, height: 844 });
  await p.evaluate(id => lpoDlvOpen(id), po2.id); await sleep(1200);
  const fits = await p.evaluate(() => { const b = document.querySelector('#pu-dlv .box'); return b.getBoundingClientRect().width <= window.innerWidth; });
  ck('phone: the delivery window fits the screen', fits);
  await p.screenshot({ path: OUT + '/pu-delivery-phone.png' });

  ck('no script errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
