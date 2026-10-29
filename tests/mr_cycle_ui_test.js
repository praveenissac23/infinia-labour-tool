// Material request cycle on screen: a direct LPO for a site shows on Order follow-up under that site, every line;
// hired material booked in on Rentals comes off it; 'Already booked in' takes a line off without stock.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  const api = (u, o) => p.evaluate(async ([u, o]) => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    const r = await fetch(u, Object.assign({ headers: { Authorization: 'Bearer ' + T, 'Content-Type': 'application/json' } }, o || {})); return [r.status, await r.json()]; }, [u, o]);
  const [, po] = await api('/store/purchase/orders', { method: 'POST', body: JSON.stringify({ supplier_name: 'Desarch Building Contracting', order_date: '2026-10-29',
    project_location: '913', lines: [{ description: 'Ledger 1.2m', qty: 85, unit: 'nos', rate: 0.35, tax_pct: 5 }, { description: 'Aluminium Beam 3.5m', qty: 145, unit: 'nos', rate: 5.25, tax_pct: 5 }] }) });
  await p.goto(B + '/?p=store#requests:followup'); await sleep(3000);
  await p.evaluate(() => { window.checkBuild = () => {}; const z = document.getElementById('build-bar'); if (z) z.remove(); });
  if (!await p.evaluate(() => document.getElementById('fu-list') && document.getElementById('fu-list').offsetParent)) { await p.evaluate(() => typeof pgGo === 'function' && pgGo('store', 'requests', 'followup')); await sleep(2500); }
  await p.fill('#fu-search', 'Desarch'); await p.evaluate(() => renderFollowUp()); await sleep(500);
  const rows = await p.evaluate(() => [...document.querySelectorAll('#fu-list tbody tr')].map(tr => [...tr.cells].map(c => c.innerText.trim().split('\n')[0])));
  ck('a direct LPO for 913: both lines on follow-up, for site 913', rows.length === 2 && rows.every(r => r[2] === '913'), rows);
  await p.screenshot({ path: OUT + '/followup-direct-lpo.png' });
  // the ledgers are booked in on Rentals at 913 under the hire company's own name
  const [, it] = await api('/store/items', { method: 'POST', body: JSON.stringify({ name: 'Rental Ledger 1.2M', unit: 'nos', item_type: 'asset' }) });
  const [st] = await api('/store/hire/in', { method: 'POST', body: JSON.stringify({ supplier_name: 'Desarch Building Contracting', received_on: '2026-10-29', location: '913', reference: 'DN-77', lines: [{ item_id: it.id, qty: 85 }] }) });
  await p.evaluate(() => loadFollowUp()); await sleep(1500); await p.fill('#fu-search', 'Desarch'); await p.evaluate(() => renderFollowUp()); await sleep(400);
  const rows2 = await p.evaluate(() => [...document.querySelectorAll('#fu-list tbody tr')].map(tr => tr.innerText));
  ck('booked in on Rentals: the ledgers come off follow-up, the beams stay', st === 200 && rows2.length === 1 && /Aluminium Beam/.test(rows2[0]), rows2);
  await p.click('#fu-list .fu-booked'); await sleep(1500);
  const rows3 = await p.evaluate(() => [...document.querySelectorAll('#fu-list tbody tr')].map(tr => tr.innerText));
  ck('"Already booked in": the beams come off too', !rows3.some(r => /Aluminium Beam/.test(r) && /Desarch/.test(r)), rows3);
  ck('no script errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
