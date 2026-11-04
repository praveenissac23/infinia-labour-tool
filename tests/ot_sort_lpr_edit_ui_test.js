// Order tracker: newest raised first, every heading sorts (4 Nov 2026). LPO register: Edit beside Deliveries opens the LPO
// in the purchase form; the supplier name is plain text, not a link.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/roles.db 8470 tests/ot_sort_lpr_edit_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => { errs.push('dialog ' + d.message()); d.dismiss(); });
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  const api = u => p.evaluate(u => apiCall(u), u);
  const t = await api('/store/purchase/tracker');
  const cr = t.rows.map(r => r.created || r.date);
  ck(`the tracker comes newest raised first (${t.rows.length} rows)`, t.rows.length > 5 && cr.every((c, i) => !i || cr[i - 1] >= c), cr.slice(0, 6));
  await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3000);
  await p.evaluate(() => { OT_VIEW = 'open'; OT_STEP = null; otRender(); }); await sleep(300);
  const keysOnScreen = () => p.$$eval('#ot-body tr.ot-r', x => x.map(t => t.dataset.k));
  const shown = await keysOnScreen();
  const want = t.rows.filter(r => r.stage < 5).map(r => r.key);
  ck('on screen: All open, newest first', JSON.stringify(shown) === JSON.stringify(want), { shown: shown.slice(0, 5), want: want.slice(0, 5) });
  const heads = await p.$$eval('#ot-head th.ot-srt', x => x.length);
  ck('all six headings are clickable to sort', heads === 6, heads);
  const order = async (lab) => { await p.click(`#ot-head th.ot-srt:has-text("${lab}")`, { position: { x: 8, y: 8 } }); await sleep(250);
    return p.evaluate(() => [...document.querySelectorAll('#ot-body tr.ot-r')].map(tr => otRow(tr.dataset.k))); };
  let r = await order('Supplier'); let s = r.map(x => (x.supplier || '').toLowerCase());
  ck('Supplier: A to Z, with the arrow on it', s.every((v, i) => !i || s[i - 1].localeCompare(v, undefined, { numeric: true }) <= 0) && await p.textContent('#ot-head th.ot-srt.on') .then(x => /Supplier▲/.test(x)), s.slice(0, 6));
  r = await order('Supplier'); s = r.map(x => (x.supplier || '').toLowerCase());
  ck('clicked again: Z to A', s.every((v, i) => !i || s[i - 1].localeCompare(v, undefined, { numeric: true }) >= 0), s.slice(0, 6));
  r = await order('Site'); s = r.map(x => x.site || '');
  ck('Site sorts', s.every((v, i) => !i || s[i - 1].localeCompare(v, undefined, { numeric: true }) <= 0), s.slice(0, 8));
  r = await order('Late / to come'); s = r.map(x => x.late || 0);
  ck('Late: most days late first', s.every((v, i) => !i || s[i - 1] >= v), s.slice(0, 8));
  r = await order('Item / LPO'); s = r.map(x => x.ref);
  ck('Item / LPO sorts by number', s.every((v, i) => !i || s[i - 1].localeCompare(v, undefined, { numeric: true }) <= 0), s.slice(0, 6));
  await p.screenshot({ path: '/tmp/claude-0/ui2/ot_sorted.png', clip: { x: 0, y: 0, width: 1440, height: 700 } });
  await p.click('.ot-sortline a'); await sleep(250);
  ck('"newest first again" puts it back', JSON.stringify(await keysOnScreen()) === JSON.stringify(want));
  await p.screenshot({ path: '/tmp/claude-0/ui2/ot_newest.png', clip: { x: 0, y: 0, width: 1440, height: 700 } });
  // ---- LPO register
  await p.evaluate(() => pgGo('store', 'purchasing', 'lporegister')); await sleep(3000);
  if (!await p.evaluate(() => !!document.querySelector('#lpr-body tr button'))) { await p.goto(B + '/?p=store#purchasing:lporegister'); await sleep(3500); }
  const reg = await p.evaluate(() => { const rows = [...document.querySelectorAll('#lpr-body tr')].filter(t => t.querySelector('.lpr-dlv'));
    return { n: rows.length, edits: rows.filter(t => t.querySelector('.lpr-edit')).length, supLinks: rows.filter(t => t.children[2] && t.children[2].querySelector('a')).length,
             cx: [...document.querySelectorAll('#lpr-body tr.lpr-cxrow')].filter(t => t.querySelector('.lpr-edit')).length }; });
  ck(`every live LPO has Edit beside Deliveries (${reg.n})`, reg.n > 3 && reg.edits === reg.n && reg.cx === 0, reg);
  ck('the supplier name is plain text, not a link', reg.supLinks === 0, reg);
  await p.screenshot({ path: '/tmp/claude-0/ui2/lpr_edit.png', clip: { x: 0, y: 0, width: 1440, height: 640 } });
  const ref = await p.evaluate(() => { const tr = [...document.querySelectorAll('#lpr-body tr')].find(t => t.querySelector('.lpr-edit')); const r = tr.querySelector('.lpr-no').textContent.trim(); tr.querySelector('.lpr-edit').click(); return r; });
  await sleep(4000);
  const form = await p.evaluate(() => ({ on: xlOn('purchase'), title: (document.getElementById('lpo-form-title') || {}).textContent, ref: (document.getElementById('lpo-ref') || {}).value, btn: (document.getElementById('lpo-save-btn') || {}).textContent, newTabs: 0 }));
  ck(`Edit opens ${ref} in the purchase form, keeping its number`, form.on && form.title === 'Edit ' + ref && form.ref === ref && /Save changes/.test(form.btn), form);
  ck('no page errors or pop-ups', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close();
})();
