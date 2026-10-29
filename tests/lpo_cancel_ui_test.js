// LPO cancelled: struck through on the register with the reason, out of the totals, stamped CANCELLED;
// LPO edited: accounts see exactly what changed on Send to Zoho (and on the bell).
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  const api = (u, o) => p.evaluate(async ([u, o]) => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    const r = await fetch(u, Object.assign({ headers: { Authorization: 'Bearer ' + T, 'Content-Type': 'application/json' } }, o || {})); return r.json(); }, [u, o]);
  const list = (await api('/store/purchase/report?group_by=order&measures=total&status=issued')).rows;
  const [x, y] = list.slice(0, 2);
  // edit one: change a qty, add a line
  const full = await api(`/store/purchase/orders/${y.id}`);
  const body = Object.assign({}, full, { lines: full.lines.map((l, i) => i === 0 ? Object.assign({}, l, { qty: (l.qty || 1) + 5 }) : l).concat([{ description: 'Binding wire 1.2mm', qty: 3, unit: 'roll', rate: 25, tax_pct: 5 }]) });
  const ed = await api(`/store/purchase/orders/${y.id}`, { method: 'PUT', body: JSON.stringify(body) });
  ck('the purchaser edits an LPO', ed.id === y.id, ed);
  await p.goto(B + '/?p=store#purchasing:lporegister'); await sleep(2500);
  await p.evaluate(() => { window.checkBuild = () => {}; const z = document.getElementById('build-bar'); if (z) z.remove(); });
  if (!await p.evaluate(() => !!document.querySelector('#lpr-body tr'))) { await p.evaluate(() => typeof pgGo === 'function' && pgGo('store', 'purchasing', 'lporegister')); await sleep(2500); }
  const tot0 = await p.evaluate(() => document.getElementById('lpr-total').textContent);
  await p.evaluate(ref => { const tr = [...document.querySelectorAll('#lpr-body tr')].find(t => t.textContent.includes(ref)); tr.querySelector('.lpr-cancel').click(); }, x.label);
  await sleep(400);
  ck('Cancel asks why', await p.evaluate(() => document.getElementById('lpo-cx-modal').classList.contains('on')));
  await p.click('#lpo-cx-modal [data-go]'); await sleep(300);
  ck('a reason is required', await p.evaluate(() => /Say why/.test(document.getElementById('lpo-cx-status').textContent)));
  await p.click('#lpo-cx-modal .chips button'); await p.screenshot({ path: OUT + '/lpo-cancel-ask.png' });
  await p.click('#lpo-cx-modal [data-go]'); await sleep(2500);
  const row = await p.evaluate(ref => { const tr = [...document.querySelectorAll('#lpr-body tr')].find(t => t.textContent.includes(ref)); return tr ? { cls: tr.className, txt: tr.textContent, deco: getComputedStyle(tr.querySelector('.lpr-no')).textDecorationLine } : null; }, x.label);
  ck('the LPO stays on the register, struck through, with the reason', row && /lpr-cxrow/.test(row.cls) && /CANCELLED/.test(row.txt) && /no longer needed/.test(row.txt) && row.deco === 'line-through', row);
  const tot1 = await p.evaluate(() => document.getElementById('lpr-total').textContent);
  ck('and its amount is out of the total', tot1 !== tot0, [tot0, tot1]);
  ck('no Edit or Cancel on a cancelled LPO', await p.evaluate(ref => !([...document.querySelectorAll('#lpr-body tr')].find(t => t.textContent.includes(ref)).querySelector('button')), x.label));
  ck('the purchaser is told accounts know', await p.evaluate(() => /Accounts have been told/.test(document.getElementById('lpr-status').textContent)));
  await p.screenshot({ path: OUT + '/lpo-register-cancelled.png' });
  // the LPO itself: stamped
  const tk = await api('/auth/download-token', { method: 'POST' }).catch(() => null);
  const html = await p.evaluate(async id => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    await refreshDownloadToken(); const r = await fetch(`/export/purchase/${id}/view?token=${encodeURIComponent(cachedDownloadToken)}`); return r.text(); }, x.id);
  ck('the LPO opens stamped CANCELLED with the reason', /CANCELLED<\/div>/.test(html) && /no longer needed/.test(html));
  const v = await b.newPage({ viewport: { width: 1000, height: 1100 } }); await v.setContent(html.replace(/<script[\s\S]*?<\/script>/g, '')); await v.screenshot({ path: OUT + '/lpo-stamp.png' }); await v.close();
  // accounts: Send to Zoho shows what changed
  await p.goto(B + '/?p=accounts#zoho'); await sleep(3000);
  await p.evaluate(() => { const t = [...document.querySelectorAll('button, a')].find(e => /Purchase orders|LPOs?/.test(e.textContent) && e.offsetParent && /zh/.test(e.className + (e.getAttribute('onclick') || ''))); if (t) t.click(); }); await sleep(800);
  const card = await p.evaluate(() => { const c = document.querySelector('.zh-lpochg'); return c ? c.textContent : ''; });
  ck('accounts see the edited LPO and what changed', new RegExp(y.label.replace(/[/]/g, '\\/')).test(card) && /Added line .*Binding wire 1\.2mm/.test(card) && /qty/.test(card) && /Total incl\. VAT/.test(card), card.slice(0, 400));
  ck('and the cancelled one with its reason', card.includes(x.label) && /Cancelled - Site says material no longer needed/.test(card));
  await p.evaluate(() => document.querySelector('.zh-lpochg').scrollIntoView()); await sleep(300);
  await p.screenshot({ path: OUT + '/lpo-accounts-changes.png' });
  const bell = await api('/notifications');
  const items = Array.isArray(bell) ? bell : (bell.notifications || []);
  ck('both on the accounts bell', items.filter(n => /^lpochg-/.test(n.id)).length >= 2, items.map(n => n.id));
  await p.evaluate(id => document.querySelector(`.zh-chg[data-chg="${id}"] button`).click(), y.id); await sleep(1200);
  ck('Seen takes it off', await p.evaluate(id => !document.querySelector(`.zh-chg[data-chg="${id}"]`), y.id));
  ck('no script errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
