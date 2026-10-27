// Long lists draw 150 rows at a time (thousands of rows made every screen slow): Store home stock, the materials
// list, Reports > stock. "Show more" draws the next lot, "Show all" the rest; the search still finds any material.
//   needs a store with thousands of materials (tests: /tmp/claude-0/vol.db) - BASE=... node tests/long_lists_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(() => pgGo('store')); await sleep(6000);
  const rows = sel => p.$$eval(sel + ' tr[data-code]', x => x.length).catch(() => 0);
  const home = await rows('#home-stock-body');
  ck('Store home: 150 rows drawn, with "Show more"', home === 150 && /Showing 150 of/.test(await p.textContent('#home-stock-body .list-more')), home);
  await p.click('#home-stock-body .list-more button'); await sleep(400);
  ck('Show more: 300', (await rows('#home-stock-body')) === 300);
  const far = await p.evaluate(() => HOME_STOCK.rows[HOME_STOCK.rows.length - 1].code);
  await p.fill('#home-stock-search', far); await p.dispatchEvent('#home-stock-search', 'input'); await sleep(300);
  ck('search finds the last material (not drawn before)', (await p.$$eval('#home-stock-body tr[data-code]', x => x.map(t => t.dataset.code))).includes(far), far);
  await p.click(`#home-stock-body tr[data-code="${far}"]`); await sleep(1200);
  ck('...and its breakdown opens', await p.isVisible(`#sd-${far}`));
  // materials list
  await p.evaluate(() => { document.getElementById('il-search').value = ''; renderItemMaster(); });
  const il = await p.$$eval('#il-body tr:not(.list-more)', x => x.length);
  ck('Materials list: 150 drawn, count says all', il === 150 && /3,\d{3} material/.test(await p.textContent('#il-count')), [il, await p.textContent('#il-count')]);
  await p.evaluate(() => document.querySelector('#il-body .list-more button:last-child').click()); await sleep(800);
  ck('Show all: every material', (await p.$$eval('#il-body tr:not(.list-more)', x => x.length)) > 3000);
  await p.evaluate(() => { document.getElementById('il-search').value = 'Material 3699 '; renderItemMaster(); }); await sleep(200);
  ck('search narrows (and starts from 150 again)', (await p.$$eval('#il-body tr:not(.list-more)', x => x.length)) === 1);
  // Reports > stock
  await p.evaluate(() => pgGo('reports')); await sleep(1500); await p.evaluate(() => pickReport('stock')); await sleep(4000);
  const rep = await p.$$eval('#store-body > tr:not(.list-more):not([data-total]):not([data-detail])', x => x.length);
  ck('Reports > stock: 150 drawn, Show more under them', rep === 150 && !!(await p.$('#store-body .list-more')), rep);
  await p.evaluate(() => { document.getElementById('store-report-search').value = 'Material 12 '; filterStoreReport(); }); await sleep(400);
  const foot = await p.textContent('#store-report-foot');
  ck('report search looks through all rows', /rows match/.test(foot) && (await p.$$eval('#store-body > tr:not([data-total]):not([data-detail])', x => x.length)) >= 1, foot);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
