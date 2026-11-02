// One place for each purchasing job (2 Nov 2026) - every link that used to lead to a second place now leads to the
// Order tracker, nothing points at a removed button, and the departments (not names) show who is next.
// Run on a copy of the live purchasing data with the department logins (see tests/order_tracker_ui_test.js).
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 500))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function login(br, user, pw) {
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
  await p.goto(B + '/'); await sleep(2500); await p.waitForSelector('#login-username');
  await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000);
  return p;
}
const api = (p, u, b) => p.evaluate(([u, b]) => apiCall(u, b ? { method: 'POST', body: JSON.stringify(b) } : undefined), [u, b]);
const where = p => p.evaluate(() => ({ screen: (document.querySelector('.screen.active') || {}).id || '', tab: ((document.querySelector('#pg-tabs .pg-tab.on, #pg-tabs .pg-tab.active') || {}).textContent || '').trim(),
  sub: ((document.querySelector('#pg-sub .on, #pg-sub .active') || {}).textContent || '').trim(), url: location.pathname + location.search + location.hash }));
const modalOn = (p, id) => p.evaluate(id => { const m = document.getElementById(id); return !!(m && (m.classList.contains('on') || m.style.display === 'flex')); }, id);
const closeAll = p => p.evaluate(() => { document.querySelectorAll('.pu-modal.on, #lpo-cx-modal.on').forEach(m => m.classList.remove('on')); const r = document.getElementById('recv-modal-overlay'); if (r) r.style.display = 'none'; });
const REMOVED = ['Material arrived', 'Approvals', 'Order follow-up'];

(async () => {
  const br = await chromium.launch();
  const a = await login(br, 'admin', 'changeme123');
  // test data: a request waiting for approval, one approved (to order), one approved for the 'It arrived' doors
  const sites = (await api(a, '/sites')).map(s => s.code).filter(c => /^\d+$/.test(c));
  const items = (await api(a, '/store/items')).slice(10, 12);
  const mk = n => api(a, '/store/requests', { site: sites[0], requested_by: 'Link test ' + n, needed_by: '2026-11-25',
    lines: items.map((it, i) => ({ item_id: it.id, description: it.name, qty_requested: 3 + i, unit: it.unit || 'pcs' })) });
  const mrWait = await mk('wait'), mrOk = await mk('ok'), mrArr = await mk('arrive');
  await api(a, `/store/requests/${mrOk.id}/status`, { status: 'approved' });
  await api(a, `/store/requests/${mrArr.id}/status`, { status: 'approved' });

  for (const [u, pw, dept] of [['admin', 'changeme123', ''], ['arun', 'Test12345', 'purchaser'], ['amal', 'Test12345', 'store'], ['shafiq', 'Test12345', 'accounts']]) {
    const p = u === 'admin' ? a : await login(br, u, pw);
    // ---- the department's turn, never a name
    const T = await api(p, '/store/purchase/tracker');
    ck(`${u}: My turn is by department (${JSON.stringify(T.my_roles)})`, dept ? JSON.stringify(T.my_roles) === JSON.stringify([dept]) : T.my_roles.length === 0, T.my_roles);
    ck(`${u}: next is a department - ${[...new Set(T.rows.map(r => r.who).filter(Boolean))].join(', ')}`, T.rows.every(r => !r.who || ['Purchase', 'Store', 'Accounts'].includes(r.who)));
    // ---- Store & Purchasing tabs: no second place left
    await p.evaluate(() => pgGo('store', 'store')); await sleep(2500);
    const subs = await p.$$eval('#pg-sub > *', x => x.map(e => e.textContent.trim()).filter(Boolean));
    await p.evaluate(() => pgGo('store', 'requests')); await sleep(2500);
    const subs2 = await p.$$eval('#pg-sub > *', x => x.map(e => e.textContent.trim()).filter(Boolean));
    ck(`${u}: Stock / Requests tabs - ${subs.join(', ')} | ${subs2.join(', ')}`, !REMOVED.some(x => subs.includes(x) || subs2.includes(x)), [subs, subs2]);
    // ---- Stock home: no Material Arrived tile; every tile goes somewhere real
    await p.evaluate(() => pgGo('store', 'store', 'home')); await sleep(2500);
    const tiles = await p.$$eval('#screen-store .store-tile', x => x.filter(e => e.offsetParent).map(e => e.querySelector('.store-tile-t').textContent.trim()));
    ck(`${u}: Stock tiles - ${tiles.join(', ')}`, !tiles.includes('Material Arrived'), tiles);
    for (const t of []) {
      await p.evaluate(() => pgGo('store', 'store', 'home')); await sleep(1800);
      await p.evaluate(t => [...document.querySelectorAll('#screen-store .store-tile')].find(e => e.offsetParent && e.querySelector('.store-tile-t').textContent.trim() === t).click(), t); await sleep(2500);
      const w = await where(p);
      ck(`${u}: Stock tile "${t}" opens ${w.screen} ${w.tab}${w.sub ? ' > ' + w.sub : ''}`, !!w.screen && !REMOVED.includes(w.sub) && (t !== 'Order Tracker' && t !== 'Order tracker' || w.screen === 'screen-purchtrack'), w);
    }
    // ---- dashboard tiles: one tile for the tracker, each goes where it says
    await p.evaluate(() => typeof pgGo === 'function' && pgGo('dashboard')); await sleep(3000);
    const dq = await p.$$eval('.dq-tile', x => x.map(e => e.dataset.dq));
    ck(`${u}: dashboard tiles ${dq.join(', ')} - no Approvals / Follow-up / Material arrived`, !dq.some(x => ['appr', 'follow', 'arrive'].includes(x)) && dq.filter(x => x === 'track').length <= 1, dq);
    for (const id of dq.filter(x => ['track', 'mreq', 'lpo', 'lporeg', 'stock', 'give', 'returns', 'items', 'rent', 'supp'].includes(x))) {
      await p.evaluate(() => pgGo('dashboard')); await sleep(1500);
      await p.evaluate(id => dqGo(id), id); await sleep(2500);
      const w = await where(p);
      const want = { track: 'screen-purchtrack', mreq: 'screen-requests', lpo: 'screen-purchase', lporeg: 'screen-lporegister', supp: 'screen-suppliers' }[id];
      ck(`${u}: dashboard "${id}" opens ${w.screen} ${w.tab}${w.sub ? ' > ' + w.sub : ''}`, !!w.screen && (!want || w.screen === want), w);
    }
    // ---- old links people may have saved
    for (const h of ['#store:arrive', '#requests:approvals', '#requests:followup']) {
      await p.goto(B + '/?p=store' + h); await sleep(3500);
      const w = await where(p);
      ck(`${u}: old link ${h} goes to the Order tracker (${w.screen} ${w.tab})`, w.screen === 'screen-purchtrack', w);
    }
    // ---- Material requests: raise and see your own requests - approving, ordering and booking are on the tracker only
    if (dept === 'purchaser' || !dept) {
      await p.evaluate(() => pgGo('store', 'requests', 'requests')); await sleep(3000);
      const rb = await p.evaluate(() => [...document.querySelectorAll('#screen-requests button')].filter(b => b.offsetParent).map(b => b.textContent.trim()));
      ck(`${u}: Material requests has no Approve / Raise LPO / Record delivery (Direct purchase stays)`, !rb.some(x => /^(Approve|Raise LPO|Record delivery)/.test(x)), rb);
      await p.evaluate(() => pgGo('store', 'purchasing', 'purchase')); await sleep(3000);
      const pend = await p.evaluate(() => { const c = document.getElementById('lpo-pending-card'); return !!(c && c.offsetParent) && !!document.querySelector('button[onclick="lpoFromTicked()"]'); });
      ck(`${u}: Purchase orders shows the approved request materials waiting to be ordered, and New Purchase Order`, pend && await p.evaluate(() => !!document.querySelector('button[onclick="newLpo()"]')));
      // Raise LPO from the tracker still fills the LPO from the request
      await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3000);
      await p.evaluate(() => { OT_VIEW = 'open'; OT_STEP = null; otRender(); }); await sleep(800);
      await p.evaluate(k => otRaise(k), 'mr' + mrOk.id); await sleep(5000);
      const w2 = await where(p), form = await p.evaluate(() => { const c = document.getElementById('lpo-form-card'); return { on: !!(c && c.offsetParent), lines: [...document.querySelectorAll('#lpo-lines tr')].filter(t => t.querySelector('input')).length }; });
      ck(`${u}: tracker > Raise LPO on ${mrOk.ref} opens the LPO filled in (${w2.screen}, ${form.lines} lines)`, w2.screen === 'screen-purchase' && form.on && form.lines > 0, { w2, form });
      // the LPO register: look only
      await p.evaluate(() => pgGo('store', 'purchasing', 'lporegister')); await sleep(3000);
      await p.evaluate(() => { const s = document.getElementById('lpr-show'); if (s) s.value = 'all'; loadLpoReport(); }); await sleep(2500);
      const reg = await p.evaluate(() => { const tr = [...document.querySelectorAll('#lpr-body tr')].find(t => t.querySelector('.lpr-dlv')); return tr ? [...tr.querySelectorAll('button')].map(b => b.textContent.trim()) : null; });
      ck(`${u}: LPO register row buttons - ${reg && reg.join(', ')}`, reg && reg.length === 1 && reg[0] === 'Deliveries', reg);
      await p.evaluate(() => [...document.querySelectorAll('#lpr-body .lpr-dlv')][0].click()); await sleep(2500);
      ck(`${u}: LPO register > Deliveries shows what came, nothing to book`, await p.evaluate(() => { const m = document.getElementById('pu-dlv'); return !!(m && m.classList.contains('on')) && !document.getElementById('pu-dlv-save') && !document.getElementById('pu-dn'); }));
      await closeAll(p);
    }
    // ---- the one door for material without an LPO: It arrived on the material
    if (dept === 'store' || !dept) {
      await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3000);
      await p.evaluate(() => { OT_VIEW = 'open'; OT_STEP = null; otRender(); }); await sleep(800);
      const menuItems = await p.evaluate(k => { const b = [...document.querySelectorAll(`tr[data-k="${k}"] td.nx button`)].find(x => x.textContent === 'More'); if (!b) return null; b.click(); return [...document.querySelectorAll('#ot-sheet .ot-acts button')].map(e => e.firstChild.textContent); }, 'mr' + mrArr.id);
      ck(`${u}: menu on an approved request - ${menuItems && menuItems.join(' | ')}`, menuItems && !menuItems.some(x => /Record what arrived/.test(x)) && menuItems.includes('It arrived (no LPO) - material by material'), menuItems);
      if (menuItems) { await p.evaluate(() => [...document.querySelectorAll('#ot-sheet .ot-acts button')].find(e => /^It arrived/.test(e.firstChild.textContent)).click()); await sleep(2500); }
      const btns = await p.evaluate(() => [...document.querySelectorAll('#ot-req button')].map(b => b.textContent.trim()));
      ck(`${u}: the request opens with It arrived per material, no second "Record what arrived"`, btns.includes('It arrived') && !btns.includes('Record what arrived'), btns);
      for (const [chip, modal] of [['Bought with petty cash', 'pu-petty'], ['From a supplier', 'recv-modal-overlay']]) {
        await p.evaluate(rid => otRequest(rid), mrArr.id); await sleep(2000);
        await p.evaluate(() => [...document.querySelectorAll('#ot-req button')].find(b => b.textContent.trim() === 'It arrived').click()); await sleep(800);
        const chips = await p.$$eval('#ot-ask .seg-chip', x => x.map(e => e.textContent));
        await p.evaluate(c => [...document.querySelectorAll('#ot-ask .seg-chip')].find(b => b.textContent.startsWith(c)).click(), chip);
        await p.click('#ot-ask [data-go]'); await sleep(2500);
        ck(`${u}: It arrived > "${chip}..." opens its form (adds to stock)`, await modalOn(p, modal), chips);
        await closeAll(p);
      }
      // nothing was saved by opening the forms
      const after = await api(p, `/store/purchase/tracker/request/${mrArr.id}`);
      ck(`${u}: opening the forms saved nothing (${mrArr.ref} still to come)`, after.lines.every(l => !(l.qty_received > 0)), after.lines.map(l => l.qty_received));
    }
    // ---- delivery form wording
    if (dept === 'store' || !dept) {
      const T2 = await api(p, '/store/purchase/tracker');
      const lpo = T2.rows.find(r => r.kind === 'lpo' && r.stage === 2);
      if (lpo) {
        await p.evaluate(id => lpoDlvOpen(id, () => {}), lpo.id); await sleep(2500);
        const b = await p.evaluate(() => [...document.querySelectorAll('#pu-dlv button')].map(x => x.textContent.trim()));
        ck(`${u}: Book delivery says "All came - fill the quantities"`, b.includes('All came - fill the quantities') && !b.some(x => /Everything still to come/.test(x)), b);
        await closeAll(p);
      }
    }
    ck(`${u}: no page errors`, !p.errs.length, p.errs);
  }
  // tidy: the test requests
  for (const m of [mrWait, mrOk, mrArr]) await api(a, `/store/requests/${m.id}`).catch(() => {});
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await br.close(); process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
