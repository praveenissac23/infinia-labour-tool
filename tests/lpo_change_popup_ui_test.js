// An LPO edited by purchasing pops up for accounts: what changed, and whether Zoho was updated.
const { chromium } = require('playwright');
// needs a login "chiefacc" with Send to Zoho (accounts_zoho)
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
const login = async (b, u, pw) => { const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.addInitScript(() => { window.__popups = true; });
  await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000);
  await p.evaluate(() => { window.checkBuild = () => {}; const z = document.getElementById('build-bar'); if (z) z.remove(); }); return p; };
(async () => {
  const b = await chromium.launch();
  const acc = await login(b, 'chiefacc', 'chief12345'); const errs = []; acc.on('pageerror', e => errs.push(e.message));
  await acc.evaluate(() => { try { closeNotifications(); } catch (e) {} });
  const adm = await login(b, 'admin', 'changeme123');
  const api = (u, o) => adm.evaluate(async ([u, o]) => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    const r = await fetch(u, Object.assign({ headers: { Authorization: 'Bearer ' + T, 'Content-Type': 'application/json' } }, o || {})); return r.json(); }, [u, o]);
  const y = (await api('/store/purchase/report?group_by=order&measures=total&status=issued')).rows[0];
  const full = await api(`/store/purchase/orders/${y.id}`);
  const body = Object.assign({}, full, { lines: full.lines.map((l, i) => i === 0 ? Object.assign({}, l, { qty: (l.qty || 1) + 10, rate: (l.rate || 1) + 1 }) : l) });
  await api(`/store/purchase/orders/${y.id}`, { method: 'PUT', body: JSON.stringify(body) });
  await acc.evaluate(() => loadNotifications()); await sleep(1500);
  const pop = await acc.evaluate(() => { const o = document.getElementById('notif-overlay'); return o && o.classList.contains('on') ? document.getElementById('notif-box').textContent : ''; });
  ck('accounts get a pop-up: the LPO and exactly what changed', pop.includes(y.label) && /edited by/.test(pop) && /qty/.test(pop) && /rate/.test(pop) && /Total incl\. VAT/.test(pop), pop.slice(0, 300));
  ck('with Seen and Open Send to Zoho', await acc.evaluate(() => !!document.getElementById('notif-seen') && /Send to Zoho/.test(document.getElementById('notif-go').textContent)));
  await acc.screenshot({ path: OUT + '/lpo-change-popup.png' });
  await acc.click('#notif-seen'); await sleep(1500);
  ck('Seen closes it and takes it off Send to Zoho', await acc.evaluate(() => !document.getElementById('notif-overlay').classList.contains('on')));
  const left = await adm.evaluate(async () => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    return (await (await fetch('/store/zoho/pos', { headers: { Authorization: 'Bearer ' + T } })).json()).rows.filter(r => (r.note || []).length).length; });
  ck('the note is marked seen', left === 0, left);
  // a cancel while accounts are away pops up when they next sign in
  const z = (await api('/store/purchase/report?group_by=order&measures=total&status=issued')).rows[1];
  await api(`/store/purchase/orders/${z.id}/cancel`, { method: 'POST', body: JSON.stringify({ reason: 'Site says material no longer needed' }) });
  const acc2 = await login(b, 'chiefacc', 'chief12345'); await sleep(1500);
  const pop2 = await acc2.evaluate(() => { const o = document.getElementById('notif-overlay'); return o && o.classList.contains('on') ? document.getElementById('notif-box').textContent : ''; });
  ck('a cancel pops up at the next sign-in too, with the reason', pop2.includes(z.label) && /cancelled/.test(pop2) && /Site says material no longer needed/.test(pop2), pop2.slice(0, 300));
  await acc2.screenshot({ path: OUT + '/lpo-cancel-popup.png' });
  ck('no script errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
