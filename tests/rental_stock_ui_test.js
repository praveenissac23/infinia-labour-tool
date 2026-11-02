// Rental stock on screen (01 Nov 2026, owner: "If any items are rental ... it must be under rental. It must be shown in
// the stock and in the rental area."):
//  - a Rental material added on the material list with 'Already have': in Stock as 'Rental - <supplier>', same on Rentals
//  - Rental in of one of our own materials: two rows in Stock - ours (Asset) and 'Rental - <supplier>'; the breakup
//    of the rental row shows only the supplier's places
//  - Type chips: totals per type apart; the Rentals chip shows only Rental rows
//  - Stock (Rental) = Rentals screen, per material, supplier and place
//  - LPO form: the Rental tick sets itself for a supplier we rent from; the delivery window says Rental LPO; a delivery
//    booked there goes into Rentals and shows in Stock as Rental
//  - no "hire" word on these screens; no script errors; screenshots
//    BASE=http://127.0.0.1:8710 OUT=/tmp/x node tests/rental_stock_ui_test.js
const { chromium } = (() => { try { return require('playwright'); } catch (e) { return require('/home/claude/.npm-global/lib/node_modules/playwright'); } })();
const B = process.env.BASE || 'http://127.0.0.1:8710', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i).slice(0, 700)}`); };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  p.on('dialog', d => d.accept());
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  const kill = () => p.evaluate(() => { window.checkBuild = () => {}; const z = document.getElementById('build-bar'); if (z) z.remove(); });
  await kill();
  const api = (u, o) => p.evaluate(async ([u, o]) => apiCall(u, o ? { method: o.method, body: o.body } : undefined), [u, o]);
  const run = Date.now() % 100000, SUP = `Rental Test Scaffolding ${run}`;
  const site = await p.evaluate(() => (sites.find(s => /^\d+$/.test(s.code)) || sites[0] || {}).code);

  // ---- 1 a Rental material added on the material list, with 'Already have' --------------------------------------
  await p.goto(B + '/?p=store#store:items'); await sleep(2500); await kill();
  await p.evaluate(() => { if (typeof pgStorePanel === 'function') pgStorePanel('items'); else storeGo('items'); }); await sleep(2000);
  await p.fill('#it-name', `Rental Ledger 1.8M T${run}`);
  await p.selectOption('#it-type', 'rental'); await p.evaluate(() => onItemTypeChange());
  await p.fill('#it-rsupplier', SUP); await p.fill('#it-opening', '120');
  await p.evaluate(() => saveStoreItem()); await sleep(2000);
  const st1 = await p.evaluate(() => (document.getElementById('store-status') || {}).innerText || '');
  ck('a Rental material with "Already have" 120 saves from the material list', /Saved/.test(st1), st1);

  // ---- 2 Rental in of one of our own materials --------------------------------------------------------------------
  const own = await api('/store/items', { method: 'POST', body: JSON.stringify({ name: `Standard 2.0M T${run}`, unit: 'pcs', item_type: 'asset', opening_qty: 40 }) });
  const hin = await api('/store/hire/in', { method: 'POST', body: JSON.stringify({ supplier_name: SUP, received_on: await p.evaluate(() => isoLocal(new Date())),
    location: site, reference: 'DN-' + run, lines: [{ item_id: own.id, qty: 50 }] }) });
  ck('Rental in of our own Standard: booked on its Rental twin, said with the word rental', /Rental Standard 2\.0M/.test(hin.detail) && !/hire/i.test(hin.detail), hin.detail);

  // ---- Stock screen ------------------------------------------------------------------------------------------------
  const openStock = async () => {
    await p.evaluate(() => typeof pgGo === 'function' && pgGo('store', 'store', 'home')); await sleep(1500);
    await p.evaluate(() => { for (const k in API_SHARED) delete API_SHARED[k]; try { sessionStorage.removeItem(STOCK_HOME_KEY); } catch (e) {} if (typeof pgStorePanel === 'function') pgStorePanel('home'); else storeGo('home'); }); await sleep(2500);
    await p.evaluate(() => loadStoreHome && loadStoreHome()).catch(() => {}); await sleep(3000);
  };
  await openStock();
  const find = async t => { await p.fill('#home-stock-search', t); await p.dispatchEvent('#home-stock-search', 'input'); await sleep(400);
    return p.$$eval('#home-stock-body tr[data-key]', x => x.map(r => ({ key: r.dataset.key, text: r.textContent.replace(/\s+/g, ' ').trim() + ' ' + [...r.querySelectorAll('.pill[title]')].map(e => e.title).join(' ') }))); };
  let rows = await find(`T${run}`);
  const rl = rows.find(r => r.text.includes(`Rental Ledger 1.8M T${run}`)), ow = rows.find(r => r.text.includes(`Standard 2.0M T${run}`) && !r.text.includes('Rental Standard')),
    rs = rows.find(r => r.text.includes(`Rental Standard 2.0M T${run}`));
  ck(`Stock: the Rental material shows as "Rental – ${SUP}", 120 held`, rl && rl.text.includes(`Rental – ${SUP}`) && /120/.test(rl.text), rows);
  ck('Stock: ours and the rental are two rows - Standard 2.0M (Asset, 40) and Rental Standard 2.0M (Rental – supplier, 50)',
     ow && /asset/i.test(ow.text) && /40/.test(ow.text) && rs && rs.text.includes(`Rental – ${SUP}`) && /50/.test(rs.text), rows);
  await p.screenshot({ path: OUT + '/rental-stock-rows.png' });
  await p.click(`#home-stock-body tr[data-key="${rs.key}"]`); await sleep(800);
  const brk = await p.evaluate(k => (document.getElementById('sdc-' + k) || {}).innerText || '', rs.key);
  ck(`the rental row's breakup: only the supplier's 50 at ${site}, and says it is not ours`, new RegExp(`Site ${site}\\s+50`).test(brk) && /not ours/.test(brk) && !/\b40 pcs/.test(brk), brk);
  await p.screenshot({ path: OUT + '/rental-stock-breakup.png' });
  await p.fill('#home-stock-search', ''); await p.dispatchEvent('#home-stock-search', 'input'); await sleep(300);
  const chips = await p.$$eval('#home-stock-type .seg-chip', x => x.map(e => ({ t: e.textContent.replace(/\s+/g, ' ').trim(), title: e.title })));
  ck('Type chips: Consumables / Assets / Rentals each with their own total held; the Rentals total says it is the suppliers\'',
     chips.length === 4 && /held/.test(chips[2].t) && /held/.test(chips[3].t) && /suppliers', not ours/.test(chips[3].title), chips);
  await p.click('#home-stock-type .seg-chip:nth-child(4)'); await sleep(400);
  const pills = await p.$$eval('#home-stock-body tr[data-key] .pill', x => [...new Set(x.map(e => e.textContent.split(/ [–·] /)[0]))]);
  ck('the Rentals chip shows only Rental rows', pills.length === 1 && pills[0] === 'Rental', pills);
  await p.screenshot({ path: OUT + '/rental-stock-chip.png' });
  await p.click('#home-stock-type .seg-chip:nth-child(1)'); await sleep(300);

  // ---- Stock (Rental) = Rentals ------------------------------------------------------------------------------------
  const cmp = await p.evaluate(async () => {
    const st = await apiCall('/store/report?kind=stock'), hr = await apiCall('/store/hire');
    const a = {}, b = {};
    st.rows.filter(r => r.item_type === 'rental').forEach(r => [['', r.in_store]].concat(Object.entries(r.by_site || {})).forEach(([l, q]) => { if (q) a[`${r._item_id}|${r._supplier_id}|${l}`] = q; }));
    hr.suppliers.forEach(g => g.items.forEach(i => Object.entries(i.by_location || {}).forEach(([l, q]) => { if (q) b[`${i.item_id}|${i.supplier_id}|${l}`] = q; })));
    return { same: JSON.stringify(Object.keys(a).sort().map(k => [k, a[k]])) === JSON.stringify(Object.keys(b).sort().map(k => [k, b[k]])), n: Object.keys(b).length };
  });
  ck(`Stock (Rental) = Rentals for every material, supplier and place (${cmp.n})`, cmp.same && cmp.n > 0, cmp);
  await p.goto(B + '/?p=store#rentals:hire'); await sleep(2500); await kill();
  await p.evaluate(() => { if (typeof pgStorePanel === 'function') pgStorePanel('hire'); else storeGo('hire'); }); await sleep(2500);
  const rent = await p.evaluate(() => document.getElementById('hire-list').innerText);
  ck('the Rentals screen shows the same: the supplier with Rental Ledger 1.8M 120 and Rental Standard 2.0M 50', rent.includes(SUP)
     && new RegExp(`Rental Ledger 1\\.8M T${run}\\s+120`).test(rent) && new RegExp(`Rental Standard 2\\.0M T${run}\\s+50`).test(rent), rent.slice(0, 600));
  await p.screenshot({ path: OUT + '/rental-rentals-screen.png' });

  // ---- LPO form: the Rental tick -------------------------------------------------------------------------------------
  await p.goto(B + '/?p=purchase'); await sleep(2500); await kill();
  await p.evaluate(async () => { suppliers = await apiCall('/store/suppliers'); switchScreen('purchase'); await newLpo(); }); await sleep(1500);
  await p.fill('#lpo-supplier', SUP); await p.dispatchEvent('#lpo-supplier', 'input'); await sleep(400);
  const tick = await p.evaluate(() => ({ on: document.getElementById('lpo-rental').checked, hint: document.getElementById('lpo-rent-hint').innerText }));
  ck('LPO form: Rental ticks itself for a supplier we rent from, and says so', tick.on && /Ticked by itself/.test(tick.hint), tick);
  await p.evaluate(() => document.getElementById('lpo-rent').scrollIntoView({ block: 'center' })); await sleep(200);
  await p.screenshot({ path: OUT + '/rental-lpo-tick.png' });
  await p.click('#lpo-rent .cmb-h'); await sleep(300);
  const off = await p.evaluate(() => ({ on: document.getElementById('lpo-rental').checked, hint: document.getElementById('lpo-rent-hint').innerText }));
  ck('it can be unticked (bought outright)', !off.on && /bought outright/.test(off.hint), off);
  await p.click('#lpo-rent .cmb-h'); await sleep(200);
  await p.evaluate(() => closeLpoForm());

  // ---- a delivery on a rental LPO ------------------------------------------------------------------------------------
  const po = await api('/store/purchase/orders', { method: 'POST', body: JSON.stringify({ supplier_name: SUP, order_date: await p.evaluate(() => isoLocal(new Date())),
    project_location: site, lines: [{ description: `Ledger 1.8m T${run}`, qty: 30, unit: 'nos', rate: 0.44, tax_pct: 5 }] }) });
  await p.goto(B + '/?p=store#tracker'); await sleep(2500); await kill();   // deliveries are booked from the Order tracker
  await p.evaluate(id => lpoDlvOpen(id, m => { window.__msg = m; }), po.id); await sleep(1500);
  const win = await p.evaluate(() => document.getElementById('pu-dlv').innerText);
  ck('the delivery window says Rental LPO and the line is Rental (booked as the Rental material already on the list)',
     /Rental LPO/.test(win) && new RegExp(`Rental: Rental Ledger 1\\.8M T${run}`).test(win), win.slice(0, 500));
  await p.screenshot({ path: OUT + '/rental-delivery-window.png' });
  await p.fill('#pu-dlv tr[data-l] .pu-q', '30'); await p.fill('#pu-dn', 'DN-R' + run); await p.click('#pu-dlv-save'); await sleep(2000);
  const msg = await p.evaluate(() => window.__msg || '');
  ck('booked: Delivered, into Rentals as the supplier\'s', /Delivered/.test(msg) && /booked in on rental as Rental Ledger 1\.8M/.test(msg) && !/hire/i.test(msg), msg);
  await openStock();
  rows = await find(`Rental Ledger 1.8M T${run}`);
  ck(`Stock: Rental Ledger 1.8M now 150 (120 + 30 at ${site}), still Rental – ${SUP}`, rows.length === 1 && /150/.test(rows[0].text) && rows[0].text.includes(`Rental – ${SUP}`), rows);
  const lpoName = await find(`Ledger 1.8m T${run}`);
  ck('the LPO\'s own name holds nothing - no second material', lpoName.every(r => r.text.includes('Rental')), lpoName);
  await p.screenshot({ path: OUT + '/rental-stock-after-delivery.png' });
  const words = await p.evaluate(() => [document.getElementById('home-stock-body').innerText, (document.getElementById('store-hire') || {}).innerText || ''].join(' '));
  ck('no "hire" word on the Stock or Rentals screens', !/\bhire[ds]?\b/i.test(words), (words.match(/.{30}\bhire[ds]?\b.{30}/i) || [])[0]);
  ck('no page errors', !errs.length, errs);
  await b.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
