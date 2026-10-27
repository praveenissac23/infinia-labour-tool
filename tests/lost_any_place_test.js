// Store > Returns, lost & corrections > Lost or damaged: the material box lists every place that holds the
// material - the central store and each site, with how many - and picking one fills "Lost from".
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/lost_';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  const today = await p.evaluate(() => isoLocal(new Date()));
  const run = Date.now() % 100000, NAME = 'Karandy ' + run;
  const site = await p.evaluate(() => (sites.find(s => s.code === '912') || sites[0]).code);
  const id = await p.evaluate(async ([today, NAME, site]) => {
    const it = await apiCall('/store/items', { method: 'POST', body: JSON.stringify({ name: NAME, unit: 'pcs', item_type: 'returnable' }) });
    await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({ item_id: it.id, kind: 'in', qty: 10, moved_on: today, supplier: 'Test Supplier' }) });
    await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({ item_id: it.id, kind: 'out', qty: 4, location: site, incharge: 'Akhil', moved_on: today }) });
    return it.id;
  }, [today, NAME, site]);
  await p.evaluate(() => loadStoreItems(true)); await p.waitForTimeout(800);
  await p.evaluate(() => pgGo('store')); await p.waitForTimeout(1500); await p.evaluate(() => pgTab('store')); await p.waitForTimeout(800); await p.evaluate(() => pgSub('other')); await p.waitForTimeout(1200);
  await p.evaluate(() => setMvKind('lost')); await p.waitForTimeout(500);
  const opts = await p.evaluate(NAME => { const t = document.getElementById('mv-item-txt'); const dl = document.getElementById(t.getAttribute('list'));
    return [...dl.options].filter(o => o.value.includes(NAME)).map(o => [o.value, o.label]); }, NAME);
  ck('the material is listed in the central store (6) AND at site ' + site + ' (4)', opts.length === 2 && opts.some(o => /Central store/.test(o[0]) && /^6 pcs/.test(o[1])) && opts.some(o => o[0].includes('Site ' + site) && /^4 pcs at site/.test(o[1])), opts);
  // the dropdown as the keeper sees it
  await p.click('#mv-item-txt'); await p.type('#mv-item-txt', 'Karandy ' + run, { delay: 20 }); await p.waitForTimeout(700);
  await p.screenshot({ path: SH + '1_list.png' });
  const siteOpt = opts.find(o => o[0].includes('Site ' + site));
  await p.fill('#mv-item-txt', siteOpt[0]); await p.dispatchEvent('#mv-item-txt', 'input'); await p.waitForTimeout(300);
  ck('picking the site line fills "Lost from" with site ' + site, (await p.inputValue('#mv-from')) === site);
  ck('the material itself is picked', (await p.inputValue('#mv-item')) === String(id));
  const hint = await p.textContent('#mv-stock-hint');
  ck('the line under it says site ' + site + ' holds 4', hint.includes(`Site ${site} holds 4`), hint);
  await p.keyboard.press('Escape').catch(() => {}); await p.click('#mv-qty'); await p.waitForTimeout(300);
  await p.screenshot({ path: SH + '2_picked.png' });
  // the central-store line picks the store
  const stOpt = opts.find(o => /Central store/.test(o[0]));
  await p.fill('#mv-item-txt', stOpt[0]); await p.dispatchEvent('#mv-item-txt', 'input'); await p.waitForTimeout(200);
  ck('picking the central store line fills "Lost from" with Central store', (await p.inputValue('#mv-from')) === '');
  // a site-only material (nothing in the store) is listed too
  const id2 = await p.evaluate(async ([today, NAME, site]) => {
    const it = await apiCall('/store/items', { method: 'POST', body: JSON.stringify({ name: NAME + ' site only', unit: 'pcs', item_type: 'returnable' }) });
    await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({ item_id: it.id, kind: 'in', qty: 3, moved_on: today, supplier: 'Test Supplier' }) });
    await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({ item_id: it.id, kind: 'out', qty: 3, location: site, incharge: 'Akhil', moved_on: today }) });
    return it.id; }, [today, NAME, site]);
  await p.evaluate(() => { for (const k in API_SHARED) delete API_SHARED[k]; return loadStoreItems(true); }); await p.waitForTimeout(800);
  const o2 = await p.evaluate(NAME => [...document.getElementById('material-list-where').options].filter(o => o.value.toLowerCase().includes((NAME + ' site only').toLowerCase())).map(o => o.label), NAME);
  ck('a material only at a site (none in the store) is listed with its site', o2.length === 1 && /3 pcs at site/.test(o2[0]), o2);
  // write off 1 from the site - the site goes down, the store does not
  await p.fill('#mv-item-txt', siteOpt[0]); await p.dispatchEvent('#mv-item-txt', 'input'); await p.fill('#mv-qty', '1'); await p.fill('#mv-notes', 'Broken at site');
  await p.evaluate(() => { const b = [...document.querySelectorAll('#mv-form button')].find(x => /save|write|record/i.test(x.textContent)); if (b) b.click(); }); await p.waitForTimeout(2000);
  const st = await p.evaluate(async id => (await apiCall('/store/stock')).find(s => s.item_id === id), id);
  ck(`written off from the site: site ${site} now 3, store still 6`, st && (st.by_site || {})[site] === 3 && st.central === 6, st);
  ck('no page errors', !errs.length, errs);
  await b.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
