// The real jobs, done end to end the way staff do them (2 Nov 2026 - after the "one place" change hid two):
//  1. Purchase: one LPO from materials of TWO requests, ticked on Purchase orders > Waiting to be ordered
//  2. Store: a direct purchase (no request at all) from Material requests - it goes into stock
//  3. Purchase: an old order closed from its own More menu (no Close old orders button)
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function login(br, user, pw) {
  const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
  await p.goto(B + '/'); await sleep(2500); await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000); return p;
}
const api = (p, u, b) => p.evaluate(([u, b]) => apiCall(u, b ? { method: 'POST', body: JSON.stringify(b) } : undefined), [u, b]);
(async () => {
  const br = await chromium.launch();
  const a = await login(br, 'admin', 'changeme123');
  const sites = (await api(a, '/sites')).map(s => s.code).filter(c => /^\d+$/.test(c));
  const items = (await api(a, '/store/items')).filter(i => (i.item_type || 'consumable') === 'consumable').slice(20, 23);
  const mk = (n, it) => api(a, '/store/requests', { site: sites[0], requested_by: 'Job test ' + n, needed_by: '2026-11-25', lines: [{ item_id: it.id, description: it.name, qty_requested: 5, unit: it.unit || 'pcs' }] });
  const r1 = await mk('one', items[0]), r2 = await mk('two', items[1]);
  for (const r of [r1, r2]) await api(a, `/store/requests/${r.id}/status`, { status: 'approved' });

  // 1. Purchase: one LPO from two requests
  const pu = await login(br, 'arun', 'Test12345');
  await pu.evaluate(() => pgGo('store', 'purchasing', 'purchase')); await sleep(3500);
  const lines = await pu.evaluate(([n1, n2]) => [...document.querySelectorAll('#lpo-pending-card tr')].filter(t => t.textContent.includes(n1) || t.textContent.includes(n2)).map(t => t.querySelector('.lpo-pick') && t.querySelector('.lpo-pick').value), [r1.ref, r2.ref]);
  ck(`Purchase orders lists both requests' materials waiting (${r1.ref}, ${r2.ref})`, lines.filter(Boolean).length >= 2, lines);
  await pu.evaluate(ids => { document.querySelectorAll('.lpo-pick').forEach(b => { b.checked = ids.includes(b.value); }); notePendingPick(); lpoFromTicked(); }, lines.filter(Boolean)); await sleep(3500);
  const form = await pu.evaluate(() => ({ on: !!(document.getElementById('lpo-form-card') || {}).offsetParent, rows: [...document.querySelectorAll('#lpo-lines tr')].filter(t => t.querySelector('input')).map(t => (t.querySelector('textarea, input') || {}).value || '') }));
  ck(`Generate LPO from ticked: one LPO with both materials (${form.rows.length} lines)`, form.on && form.rows.length >= 2, form);
  ck('purchase login: no page errors', !pu.errs.length, pu.errs);

  // 2. Store: direct purchase, no request
  const st = await login(br, 'amal', 'Test12345');
  const it = items[2];
  const before = ((await api(st, '/store/stock')).find(s => s.item_id === it.id) || {}).central || 0;
  await st.evaluate(() => pgGo('store', 'requests', 'requests')); await sleep(3000);
  const has = await st.evaluate(() => { const b = [...document.querySelectorAll('#screen-requests button')].find(b => b.offsetParent && /^Direct purchase/.test(b.textContent.trim())); if (b) b.click(); return !!b; }); await sleep(1200);
  ck('Material requests has the Direct purchase (no request) button', has);
  ck('it opens the direct purchase form', await st.evaluate(() => !!(document.getElementById('direct-purchase') || {}).offsetParent));
  await st.evaluate(() => { if (!document.querySelector('#in-lines tr')) addInLine(); });
  await st.evaluate(id => { const tr = document.querySelector('#in-lines tr'); const sel = tr.querySelector('.il-item'); if (sel.tagName === 'SELECT' && ![...sel.options].some(o => o.value == id)) sel.add(new Option('x', id)); sel.value = String(id); tr.querySelector('.il-qty').value = '7'; }, it.id);
  await st.fill('#in-ref', 'DIRECT-' + Date.now() % 100000);
  await st.evaluate(() => { const s = document.getElementById('in-supplier'); s.style.display = ''; s.value = 'Direct Test Trader'; });
  await st.evaluate(() => saveReceipt()); await sleep(3000);
  const after = ((await api(st, '/store/stock')).find(s => s.item_id === it.id) || {}).central || 0;
  ck(`direct purchase went into stock: ${it.name} ${before} -> ${after}`, Math.abs(after - before - 7) < 1e-6, { before, after });
  ck('store login: no page errors', !st.errs.length, st.errs);

  // 3. Purchase: no Close old orders button; More > Close as it stands is there
  await pu.evaluate(() => pgGo('store', 'tracker')); await sleep(3500);
  ck('Order tracker: no Close old orders button', await pu.evaluate(() => !document.getElementById('ot-tidy-btn')));
  await pu.evaluate(() => { OT_VIEW = 'open'; OT_STEP = null; otRender(); }); await sleep(600);
  const T = await api(pu, '/store/purchase/tracker');
  const old = T.rows.find(r => r.kind === 'lpo' && r.stage === 2);
  const menu = await pu.evaluate(k => { const b = [...document.querySelectorAll(`tr[data-k="${k}"] td.nx button`)].find(x => x.textContent === 'More'); b.click(); return [...document.querySelectorAll('#ot-sheet .ot-acts button')].map(e => e.firstChild.textContent); }, old.key);
  ck(`an open LPO's More menu has Close as it stands (${old.ref})`, menu.includes('Close as it stands (came earlier / not coming)'), menu);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await br.close(); process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
