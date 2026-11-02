// Store & Purchasing > Order tracker: one line per open request / LPO at its step, who is next, late, part delivery,
// supplier contact; approve (all / less / reject) material by material; close the rest of a part delivery without
// moving stock; the tracker agrees with Deliveries; nothing else changes. Run on a copy of the live purchasing data.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  const api = (u, b) => p.evaluate(([u, b]) => apiCall(u, b ? { method: 'POST', body: JSON.stringify(b) } : undefined), [u, b]);
  const stockBefore = await api('/store/stock');
  // a fresh request: 3 materials, waiting for approval
  const site = (await api('/sites')).map(s => s.code).find(c => /^\d+$/.test(c)) || '914';
  const items = (await api('/store/items')).slice(0, 3);
  const mr = await api('/store/requests', { site, requested_by: 'Test Engineer', needed_by: '2026-10-30', urgency: 'normal',
    lines: items.map((it, i) => ({ item_id: it.id, description: it.name, qty_requested: 10 * (i + 1), unit: it.unit || 'pcs', purpose: 'tracker test' })) });
  ck('test request raised', !!mr.id, mr);
  await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3500);
  const t = await api('/store/purchase/tracker');
  const row = t.rows.find(r => r.ref === mr.ref);
  ck('new request is at Requested, Arun to approve, late (needed by 30/10)', row && row.stage === 0 && row.who === 'Arun' && row.action === 'Approve' && row.late === 3, row);
  ck('counts add up to the rows', t.counts.reduce((a, b) => a + b, 0) === t.rows.length, t.counts);
  // every live LPO (not cancelled) is on the tracker exactly once, at the step its deliveries say
  const dl = await api('/store/purchase/deliveries?show=all');
  const lpoRows = t.rows.filter(r => r.kind === 'lpo' && !r.cancelled);
  const want = dl.orders.map(o => o.ref).sort(), got = lpoRows.map(r => r.ref).sort();
  ck(`every live LPO once (${want.length})`, JSON.stringify(want) === JSON.stringify(got), { missing: want.filter(x => !got.includes(x)), extra: got.filter(x => !want.includes(x)) });
  const stOf = Object.fromEntries(dl.orders.map(o => [o.ref, o.status]));
  const wrong = lpoRows.filter(r => (stOf[r.ref] === 'ordered' && r.stage !== 2) || (stOf[r.ref] === 'part' && !(r.stage === 3 && r.part)) || (stOf[r.ref] === 'delivered' && r.stage < 3));
  ck('LPO steps agree with Deliveries (ordered / part / delivered)', !wrong.length, wrong.map(r => [r.ref, stOf[r.ref], r.stage]));
  const partMissing = lpoRows.filter(r => r.part && !r.to_come);
  ck('every part delivery says what is still to come', !partMissing.length, partMissing.map(r => r.ref));
  // the screen shows it
  const shown = await p.$$eval('#ot-body tr.ot-r', x => x.length);
  ck('tracker screen lists the open rows', shown === t.rows.filter(r => r.stage < 5).length, shown);
  await p.screenshot({ path: '/tmp/claude-0/ot_1.png' });
  // approve popup: approve / approve less / reject
  await p.evaluate(k => otApprove(k), row.key); await sleep(500);
  const trs = await p.$$('#ot-appr tr[data-l]');
  await (await trs[0].$('[data-d=a]')).click();
  await (await trs[1].$('[data-d=p]')).click(); await (await trs[1].$('.q')).fill('15'); await (await trs[1].$('.rs')).fill('Only 15 needed this week');
  await (await trs[2].$('[data-d=r]')).click(); await (await trs[2].$('.rs')).fill('Not needed now');
  await p.screenshot({ path: '/tmp/claude-0/ot_2.png' });
  await p.click('#ot-appr [data-go]'); await sleep(2500);
  const mr2 = (await api('/store/requests')).find(x => x.id === mr.id);
  const L = mr2.lines;
  ck('line 1 approved 10', L[0].status === 'approved' && L[0].qty_requested === 10, L[0]);
  ck('line 2 approved 15 of 20 (reason kept)', L[1].status === 'approved' && L[1].qty_requested === 15 && /Asked for 20, approved 15: Only 15/.test(L[1].notes || ''), L[1]);
  ck('line 3 rejected with reason', L[2].status === 'rejected' && /Not needed now/.test(L[2].reject_reason || ''), L[2]);
  const t2 = await api('/store/purchase/tracker');
  const r2 = t2.rows.find(r => r.ref === mr.ref);
  ck('request moves to Approved, Arun to raise the LPO (2 materials)', r2 && r2.stage === 1 && r2.action === 'Raise LPO' && /,/.test(r2.what), r2);
  const pend = await api('/store/purchase/pending');
  ck('LPO queue has the 2 approved lines (10 and 15)', JSON.stringify(pend.filter(x => x.ref === mr.ref).map(x => x.qty).sort((a, b) => a - b)) === '[10,15]', pend.filter(x => x.ref === mr.ref));
  // Raise LPO opens the LPO form with them ticked
  await p.evaluate(k => otRaise(k), r2.key); await sleep(6000);
  const form = await p.evaluate(() => ({ on: xlOn('purchase'), card: getComputedStyle(document.getElementById('lpo-form-card')).display, lines: (lpoLines || []).length, ids: lpoRequestLineIds }));
  ck('Raise LPO: the LPO form opens filled with the 2 materials', form.on && form.card !== 'none' && form.lines === 2, form);
  // close the rest of a part delivery: no stock moves
  await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3000);
  const part = t2.rows.find(r => r.kind === 'lpo' && r.part);
  if (part) {
    const s0 = await api('/store/stock');
    await p.evaluate(k => otCloseRest(k), part.key); await sleep(400);
    await p.screenshot({ path: '/tmp/claude-0/ot_3.png' });
    await p.click('#ot-ask [data-go]'); await sleep(300);
    const warn = await p.$eval('#ot-ask-status', e => e.textContent);
    ck('close the rest: a reason is required', /reason/i.test(warn), warn);
    await p.fill('#ot-why', 'Site requirement changed'); await p.click('#ot-ask [data-go]'); await sleep(2500);
    const t3 = await api('/store/purchase/tracker');
    const r3 = t3.rows.find(r => r.ref === part.ref);
    ck(`${part.ref}: rest closed - no longer part, now the bill check`, r3 && !r3.part && r3.stage === 3 && r3.action === 'Check bill', r3);
    const s1 = await api('/store/stock');
    ck('closing the rest moved no stock', JSON.stringify(s0) === JSON.stringify(s1));
  } else ck('a part delivery to test', false);
  // menus open for every kind of row
  for (const k of [t2.rows.find(r => r.stage === 2 && r.kind === 'lpo'), t2.rows.find(r => r.stage === 3)].filter(Boolean).map(r => r.key)) {
    await p.evaluate(k => otSheet(k), k); await sleep(300);
    const items = await p.$$eval('#ot-sheet .ot-acts button', x => x.map(e => e.textContent));
    ck(`menu for ${k}: ${items.join(' | ')}`, items.length >= 3, items);
    await p.evaluate(() => document.getElementById('ot-sheet').classList.remove('on')); await sleep(200);
  }
  
  await p.screenshot({ path: '/tmp/claude-0/ot_4.png' });
  // nothing but the test request and the closed rest changed: stock same as at the start
  const stockAfter = await api('/store/stock');
  ck('stock unchanged by everything on the tracker', JSON.stringify(stockBefore) === JSON.stringify(stockAfter));
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
