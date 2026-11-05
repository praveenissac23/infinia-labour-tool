// Order tracker search (5 Nov 2026): typing a supplier (or LPO, material) - each result leads with its LPO number, the
// materials under it, and the typed words marked wherever found. Without a search the rows are as before.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/roles.db 8570 tests/ot_search_lpo_first_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1500, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3000);
  await p.evaluate(() => { OT_VIEW = 'open'; OT_STEP = null; otRender(); });
  const sup = await p.evaluate(() => { const r = OT.rows.find(x => x.kind === 'lpo' && x.supplier && x.stage < 5); return r.supplier; });
  const word = sup.split(/\s+/)[0];
  ck('no search: the rows are as before (no LPO-first line)', await p.evaluate(() => !document.querySelector('#ot-body .ot-lpo')));
  await p.fill('#ot-search', word); await sleep(500);
  const res = await p.evaluate(() => [...document.querySelectorAll('#ot-body tr.ot-r')].map(tr => { const w = tr.querySelector('td.what'); const r = otRow(tr.dataset.k);
    return { first: w.firstElementChild.className, lpo: (w.querySelector('.ot-lpo') || {}).textContent || '', ref: r.ref, desc: (w.querySelector('.t1') || {}).textContent, marks: tr.querySelectorAll('mark.ot-hl').length }; }));
  ck(`searching "${word}": every result leads with its LPO number`, res.length > 0 && res.every(x => x.first === 'ot-lpo' && x.lpo.startsWith(x.ref)), res.slice(0, 3));
  ck('the materials come under it', res.every(x => x.desc && x.desc.length > 1), res.slice(0, 3));
  ck('the typed word is highlighted in each result', res.every(x => x.marks >= 1), res.map(x => x.marks));
  ck('a count of results is shown', /result/.test(await p.textContent('#ot-head tr.ot-sortline')));
  await p.screenshot({ path: '/tmp/claude-0/ui2/ot_search.png', clip: { x: 0, y: 0, width: 1500, height: 720 } });
  await p.fill('#ot-search', 'LPO'); await sleep(400);
  ck('searching an LPO number marks it in the LPO line', await p.evaluate(() => !!document.querySelector('#ot-body .ot-lpo mark.ot-hl')));
  await p.fill('#ot-search', 'a.b(c'); await sleep(300);
  ck('odd characters in the search do not break the page', !errs.length, errs);
  await p.fill('#ot-search', ''); await sleep(300);
  ck('search cleared: back to the normal rows', await p.evaluate(() => !document.querySelector('#ot-body .ot-lpo, #ot-body mark')));
  ck('no page errors', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close(); })();
