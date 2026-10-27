// Store > Stock on hand and the site lists show every type: consumables (also at a site until returned), assets and
// rentals (a rental always, even when nothing is on hire); the Type chips filter them.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  const run = Date.now() % 100000, today = await p.evaluate(() => isoLocal(new Date()));
  const site = await p.evaluate(() => (sites[0] || {}).code);
  await p.evaluate(async ([run, today, site]) => {
    const post = (u, b) => apiCall(u, { method: 'POST', body: JSON.stringify(b) });
    const c = await post('/store/items', { name: 'Cement bag ' + run, unit: 'bag', item_type: 'consumable' });
    await post('/store/movements', { item_id: c.id, kind: 'in', qty: 50, moved_on: today, supplier: 'Test' });
    await post('/store/movements', { item_id: c.id, kind: 'out', qty: 20, location: site, incharge: 'Akhil', moved_on: today });
    await post('/store/items', { name: 'Bob Cat monthly ' + run, unit: 'nos', item_type: 'rental', rental_supplier: 'Al Hassai Hire' });
  }, [run, today, site]);
  await p.evaluate(() => { for (const k in API_SHARED) delete API_SHARED[k]; try { sessionStorage.removeItem(STOCK_HOME_KEY); } catch (e) {} pgGo('store'); }); await sleep(5000);
  await p.evaluate(() => loadStoreHome && loadStoreHome()).catch(() => {}); await sleep(3000);
  const find = async t => { await p.fill('#home-stock-search', t); await p.dispatchEvent('#home-stock-search', 'input'); await sleep(300); return p.$$eval('#home-stock-body tr[data-code]', x => x.map(r => r.textContent.replace(/\s+/g, ' ').trim())); };
  const cem = await find('Cement bag ' + run);
  ck(`a consumable sent to site ${site}: 30 in store, 20 out at sites, 50 held`, cem.length === 1 && /30/.test(cem[0]) && /20/.test(cem[0]) && /50/.test(cem[0]), cem);
  const bob = await find('Bob Cat monthly ' + run);
  ck('a rental with nothing on hire is still listed', bob.length === 1 && /rental/.test(bob[0]), bob);
  await p.fill('#home-stock-search', ''); await p.dispatchEvent('#home-stock-search', 'input'); await sleep(300);
  const chips = await p.$$eval('#home-stock-type .seg-chip', x => x.map(e => e.textContent.replace(/\s+/g, ' ').trim()));
  ck('Type chips: All, Consumables, Assets, Rentals with counts', chips.length === 4 && /^All \d/.test(chips[0]) && /^Rentals \d/.test(chips[3]), chips);
  await p.click('#home-stock-type .seg-chip:nth-child(4)'); await sleep(300);
  const types = await p.$$eval('#home-stock-body tr[data-code] .pill', x => [...new Set(x.map(e => e.textContent))]);
  ck('Rentals chip: only rentals', types.length === 1 && types[0] === 'rental', types);
  await p.screenshot({ path: '/tmp/claude-0/types_1.png' });
  await p.click('#home-stock-type .seg-chip:nth-child(1)'); await sleep(300);
  // the At Sites report and the site holding view
  const rep = await p.evaluate(async site => (await apiCall('/store/report?kind=by_site&site=' + encodeURIComponent(site))).rows.map(r => r.name), site);
  ck(`Reports > At sites (${site}) lists the consumable`, rep.some(n => n.toLowerCase().startsWith('cement bag ' + run)), rep.slice(0, 8));
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
