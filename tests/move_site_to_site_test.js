// Store > Move material, site to site: whatever the site holds - assets
// that are not in the central store as well - can be typed and moved.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  // an asset and a returnable that are all out at site 905 - none in the store
  const today = await p.evaluate(() => { const d = new Date(Date.now() + 4 * 3600e3); return d.toISOString().slice(0, 10); });
  const ids = await p.evaluate(async (today) => {
    const mk = async (name, type) => {
      const it = await apiCall('/store/items', { method: 'POST', body: JSON.stringify({ name, unit: 'pcs', item_type: type }) });
      await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({ item_id: it.id, kind: 'in', qty: 40, moved_on: today, supplier: 'Test Supplier' }) });
      await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({ item_id: it.id, kind: 'out', qty: 40, location: '905', incharge: 'Akhil', moved_on: today }) });
      return it.id;
    };
    return [await mk('Test Adjustable Base Jack', 'asset'), await mk('Test Ledger 1.8 M', 'returnable')];
  }, today);
  await p.evaluate(() => pgSub('give')); await p.waitForTimeout(1500);
  await p.fill('#out-person', 'Akhil');
  await p.selectOption('#out-from', '905'); await p.dispatchEvent('#out-from', 'change'); await p.waitForTimeout(800);
  await p.selectOption('#out-site', '906'); await p.dispatchEvent('#out-site', 'change'); await p.waitForTimeout(1500);
  const list = await p.evaluate(() => { const t = document.querySelector('#out-lines .ol-item-txt'); const dl = document.getElementById(t.getAttribute('list')); return [t.getAttribute('list'), [...dl.options].map(o => o.value)]; });
  ck('the material box lists what site 905 holds (asset and returnable not in the store)', list[1].some(v => /Test Adjustable Base Jack/.test(v)) && list[1].some(v => /Test Ledger 1.8 M/.test(v)), list[0]);
  const code = list[1].find(v => /Test Adjustable Base Jack/.test(v));
  await p.fill('#out-lines .ol-item-txt', code); await p.dispatchEvent('#out-lines .ol-item-txt', 'input');
  await p.fill('#out-lines .ol-qty', '15'); await p.dispatchEvent('#out-lines .ol-qty', 'input'); await p.waitForTimeout(300);
  ck('the "at site 905" column shows 40', /40/.test(await p.locator('#out-lines .ol-have').textContent()));
  await p.click('#out-save-btn'); await p.waitForTimeout(2500);
  const st = await p.locator('#store-status').textContent();
  const at905 = await p.evaluate(async id => (await apiCall('/store/at-site?site=905')).rows.find(r => r.item_id === id), ids[0]);
  const at906 = await p.evaluate(async id => (await apiCall('/store/at-site?site=906')).rows.find(r => r.item_id === id), ids[0]);
  ck(`moved 15 from 905 to 906 (905 now ${at905 && at905.qty}, 906 now ${at906 && at906.qty})`, at905 && at905.qty === 25 && at906 && at906.qty === 15, st);
  // asking more than the site holds is stopped with the site's figure
  await p.evaluate(() => addOutLine()); await p.waitForTimeout(200);
  const last = '#out-lines tr:last-child';
  await p.locator('#out-lines tr').first().locator('.ol-item-txt').fill(''); await p.evaluate(() => { const r = document.querySelectorAll('#out-lines tr'); if (r.length > 1) r[0].remove(); });
  const ledger = list[1].find(v => /Test Ledger 1.8 M/.test(v));
  await p.fill(`${last} .ol-item-txt`, ledger); await p.dispatchEvent(`${last} .ol-item-txt`, 'input');
  await p.fill(`${last} .ol-qty`, '99'); await p.click('#out-save-btn'); await p.waitForTimeout(1500);
  ck('asking 99 when the site has 40 is stopped with the site\'s own figure', /only 40 at site 905/.test(await p.locator('#store-status').textContent()), await p.locator('#store-status').textContent());
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'ANY MATERIAL AT A SITE MOVES TO ANOTHER');
  await b.close(); process.exit(bad ? 1 : 0);
})();
