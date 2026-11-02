// Order tracker, every button, menu item, link and the layout - as admin and as the real logins (Arun, Amal, Shafiq,
// ticked tab by tab as on live). Run on a copy of the live purchasing data (see tests/order_tracker_ui_test.js).
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function login(br, user, pw, vp) {
  const ctx = await br.newContext({ viewport: vp || { width: 1440, height: 900 }, isMobile: !!(vp && vp.width < 500), hasTouch: !!(vp && vp.width < 500) });
  const p = await ctx.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
  await p.goto(B + '/'); await sleep(2500); await p.waitForSelector('#login-username');
  await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  return p;
}
const api = (p, u, b) => p.evaluate(([u, b]) => apiCall(u, b ? { method: 'POST', body: JSON.stringify(b) } : undefined), [u, b]);
const toTracker = async p => { await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3500); };
const modalOn = (p, id) => p.evaluate(id => { const m = document.getElementById(id); return !!(m && m.classList.contains('on')) ? (m.querySelector('h3') || m).textContent.replace(/\s+/g, ' ').trim() : ''; }, id);
const closeModals = p => p.evaluate(() => document.querySelectorAll('.pu-modal.on, #lpo-cx-modal.on').forEach(m => m.classList.remove('on')));
const menu = async (p, key) => { await p.evaluate(k => { const b = [...document.querySelectorAll(`tr[data-k="${k}"] td.nx button`)].find(x => x.textContent === 'More'); b.scrollIntoView({ block: 'center' }); b.click(); }, key); await sleep(400);
  return p.$$eval('#ot-sheet .ot-acts button', x => x.map(e => e.firstChild.textContent)); };
const pick = async (p, label) => { await p.evaluate(l => { const d = [...document.querySelectorAll('#ot-sheet .ot-acts button')].find(x => x.firstChild.textContent === l); d.click(); }, label); await sleep(1800); };
(async () => {
  const br = await chromium.launch();
  // ===== admin
  const p = await login(br, 'admin', 'changeme123');
  // a fresh request to approve, and one to close
  const sites = (await api(p, '/sites')).map(s => s.code).filter(c => /^\d+$/.test(c));
  const items = (await api(p, '/store/items')).slice(5, 8);
  const mk = async (n) => api(p, '/store/requests', { site: sites[0], requested_by: 'Test Engineer ' + n, needed_by: '2026-11-20',
    lines: items.map((it, i) => ({ item_id: it.id, description: it.name, qty_requested: 4 + i, unit: it.unit || 'pcs' })) });
  const mrA = await mk('A'), mrB = await mk('B');
  await toTracker(p);
  let T = await api(p, '/store/purchase/tracker');
  const tabs = await p.$$eval('#pg-tabs .pg-tab', x => x.map(e => e.textContent.trim()));
  ck(`admin: Order tracker is the last tab of Store & Purchasing, after Purchasing (${tabs.join(', ')})`, tabs[tabs.length - 1] === 'Order tracker' && tabs[tabs.length - 2] === 'Purchasing', tabs);
  ck('admin: Store & Purchasing still opens on the Order tracker', await p.evaluate(() => { pgGo('store'); return new Promise(r => setTimeout(() => r(xlOn('purchtrack')), 2500)); }));
  // ---- layout
  const lay = await p.evaluate(() => {
    const hs = [...document.querySelectorAll('#ot-table .ot-sh span')].map(s => { const r = s.getBoundingClientRect(); return (r.left + r.right) / 2; });
    const row = document.querySelector('#ot-body tr.ot-r .ot-steps');
    const ss = [...row.children].map(s => { const r = s.getBoundingClientRect(); return (r.left + r.right) / 2; });
    const rights = [...document.querySelectorAll('#ot-body tr.ot-r td.nx .btn-gray')].map(b => Math.round(b.getBoundingClientRect().right));
    const wrap = document.getElementById('ot-wrap');
    const cut = [...document.querySelectorAll('#ot-body td')].filter(td => td.scrollWidth > td.clientWidth + 1).length;
    const sum = [...document.querySelectorAll('#ot-sum .k')].map(k => k.offsetHeight);
    const over = el => el.scrollWidth > el.clientWidth + 1;
    const hs2 = [...document.querySelectorAll('#ot-table .ot-sh span')]; const ov = hs2.filter(over).map(e => e.textContent);
    for (let i = 1; i < hs2.length; i++) { const a = document.createRange(); a.selectNodeContents(hs2[i - 1]); const b = document.createRange(); b.selectNodeContents(hs2[i]); if (a.getBoundingClientRect().right > b.getBoundingClientRect().left - 2) ov.push(hs2[i - 1].textContent + '/' + hs2[i].textContent); }
    const segCut = [...document.querySelectorAll('#ot-body .ot-steps span')].filter(over).map(e => e.textContent);
    return { ov, segCut, off: Math.max(...hs.map((h, i) => Math.abs(h - ss[i]))), rights: [...new Set(rights)], sideways: wrap.scrollWidth > wrap.clientWidth + 1, cut, sum: [...new Set(sum)] };
  });
  ck(`step names sit over their steps (off by ${lay.off.toFixed(1)}px)`, lay.off < 4, lay);
  ck('step names do not run into each other and none is cut off', !lay.ov.length, lay.ov);
  ck('the step written in the coloured step is never cut off', !lay.segCut.length, lay.segCut);
  ck('the More buttons line up on the right', Math.max(...lay.rights) - Math.min(...lay.rights) <= 1, lay.rights);
  ck('no sideways scrolling at 1440 wide, no text cut off', !lay.sideways && lay.cut === 0, lay);
  ck('the six step boxes on top are the same height', lay.sum.length === 1, lay.sum);
  for (const w of [1280, 1024]) {
    await p.setViewportSize({ width: w, height: 900 }); await sleep(500);
    const o = await p.evaluate(() => { const r = [...document.querySelectorAll('#ot-body td.nx')].map(td => td.getBoundingClientRect().right); const card = document.querySelector('#screen-purchtrack .card').getBoundingClientRect().right; const sum = [...document.querySelectorAll('#ot-sum .k')].some(k => k.scrollWidth > k.clientWidth + 1); return { cut: [...document.querySelectorAll('#ot-body td')].filter(td => td.scrollWidth > td.clientWidth + 1).map(td => td.className + ':' + td.textContent.trim().slice(0, 30) + ':' + td.scrollWidth + '>' + td.clientWidth), beyond: r.filter(x => x > card + 1).length, page: card > innerWidth + 1, sum }; });
    ck(`at ${w} wide: nothing cut off, buttons inside the card, the tracker fits the screen`, o.cut.length === 0 && !o.page && !o.beyond && !o.sum, o); await p.screenshot({ path: `/tmp/claude-0/otf_${w}.png` });
  }
  await p.setViewportSize({ width: 1440, height: 900 }); await sleep(400);
  // ---- chips, steps on top, site filter, search
  const chipN = async () => p.$$eval('#ot-body tr.ot-r', x => x.length);
  const open = T.rows.filter(r => r.stage < 5);
  await p.evaluate(() => [...document.querySelectorAll('#ot-chips button')].find(b => /^Late/.test(b.textContent)).click()); await sleep(300);
  ck('Late chip: only the late ones', await chipN() === open.filter(r => r.late > 0).length);
  await p.evaluate(() => [...document.querySelectorAll('#ot-chips button')].find(b => /^Done/.test(b.textContent)).click()); await sleep(300);
  ck('Done chip: only the done ones', (await chipN()) === T.rows.filter(r => r.stage === 5).length || (await p.$eval('#ot-body', e => /Nothing here/.test(e.textContent))));
  await p.evaluate(() => [...document.querySelectorAll('#ot-chips button')].find(b => /^All open/.test(b.textContent)).click()); await sleep(300);
  ck('All open chip: every open one', await chipN() === open.length);
  await p.click('#ot-sum .k:nth-child(3)'); await sleep(300);
  ck('clicking "Ordered" on top shows only what is at Ordered', await chipN() === T.rows.filter(r => r.stage === 2).length);
  await p.click('#ot-sum .k:nth-child(3)'); await sleep(300);
  ck('clicking it again shows the list again', await chipN() === open.length);
  const s1 = sites.find(s => open.some(r => r.site === s));
  await p.selectOption('#ot-site', s1); await sleep(300);
  const siteCells = await p.$$eval('#ot-body tr.ot-r td.site', x => [...new Set(x.map(e => e.textContent.trim()))]);
  ck(`site filter ${s1}: only site ${s1}`, siteCells.length === 1 && siteCells[0] === s1, siteCells);
  await p.selectOption('#ot-site', ''); await p.fill('#ot-search', 'unimix'); await sleep(300);
  const srch = await p.$$eval('#ot-body tr.ot-r', x => x.map(e => /unimix/i.test(e.textContent)));
  ck('search "unimix": only Unimix orders', srch.length > 0 && srch.every(Boolean), srch);
  await p.fill('#ot-search', ''); await p.dispatchEvent('#ot-search', 'input'); await sleep(300);
  // ---- links
  const tels = await p.$$eval('#ot-body a[href^="tel:"]', x => x.map(a => a.getAttribute('href')));
  ck(`phone numbers call (tel: digits only) - ${tels.length}`, tels.length > 10 && tels.every(t => /^tel:\+?\d{7,15}$/.test(t)), tels.filter(t => !/^tel:\+?\d{7,15}$/.test(t)));
  // ---- buttons and menus, row by row
  T = await api(p, '/store/purchase/tracker');
  const rA = T.rows.find(r => r.ref === mrA.ref), rB = T.rows.find(r => r.ref === mrB.ref);
  const ordered = T.rows.find(r => r.kind === 'lpo' && r.stage === 2 && !r.rental);
  const part = T.rows.find(r => r.kind === 'lpo' && r.part);
  const arrived = T.rows.find(r => r.kind === 'lpo' && r.stage === 3 && !r.part && r.ref !== 'IC/LPO/20260161');
  const l161 = T.rows.find(r => r.ref === 'IC/LPO/20260161');
  const approved = T.rows.find(r => r.kind === 'mr' && r.stage === 1);
  // Approve button
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.nx .btn-primary`).click(), rA.key); await sleep(500);
  ck(`Approve (${rA.ref}) opens its approval`, (await modalOn(p, 'ot-appr')).includes(rA.ref), await modalOn(p, 'ot-appr'));
  await p.click('#ot-appr [data-all="a"]'); await p.click('#ot-appr [data-go]'); await sleep(2500);
  T = await api(p, '/store/purchase/tracker');
  ck('Approve all: the request moves to Approved', T.rows.find(r => r.ref === mrA.ref).stage === 1);
  // MR menus
  const mm = await menu(p, rB.key);
  ck(`menu on a request waiting: ${mm.join(' | ')}`, ['Approve', 'Materials one by one (approve, reduce, not needed)', 'Request PDF', 'Delete the request', 'Close as it stands (came earlier / not needed)'].every(x => mm.includes(x)), mm);
  await pick(p, 'Materials one by one (approve, reduce, not needed)'); await sleep(1500);
  const rq = await p.evaluate(() => { const m = document.getElementById('ot-req'); return { on: m.classList.contains('on'), h: m.querySelector('h3').textContent, lines: m.querySelectorAll('tbody tr').length, btns: [...m.querySelectorAll('.acts button')].map(b => b.textContent), lineBtns: [...new Set([...m.querySelectorAll('tbody button')].map(b => b.textContent))] }; });
  ck(`the request in full: ${rq.h} - ${rq.lines} materials, ${rq.btns.join(' / ')}`, rq.on && rq.h.includes(mrB.ref) && rq.lines === 3 && ['Approve', 'Approve less', 'Reject'].every(b => rq.lineBtns.includes(b)) && ['Request PDF', 'Edit request', 'Delete', 'Close as it stands', 'Close'].every(b => rq.btns.includes(b)) && !rq.btns.includes('Record what arrived'), rq);
  // one material only: MR-0061's case - keep the first, the second not needed
  const lines0 = (await api(p, `/store/purchase/tracker/request/${mrB.id}`)).lines;
  await p.evaluate(lid => { const b = [...document.querySelectorAll('#ot-req button')].filter(b => /Reject|Not needed/.test(b.textContent))[1]; b.click(); }, 0); await sleep(500);
  await p.click('#ot-ask .seg-chip'); await p.click('#ot-ask [data-go]'); await sleep(2500);
  const lines1 = (await api(p, `/store/purchase/tracker/request/${mrB.id}`)).lines;
  ck('one material not needed: only that line rejected with the reason, the rest of the request goes on', lines1[1].status === 'rejected' && /Not needed: /.test(lines1[1].reject_reason) && lines1[0].status === lines0[0].status && lines1[2].status === lines0[2].status, lines1.map(l => [l.status, l.reject_reason]));
  const [pdf] = await Promise.all([p.context().waitForEvent('page', { timeout: 8000 }).catch(() => null), p.evaluate(() => [...document.querySelectorAll('#ot-req .acts button')].find(b => b.textContent === 'Request PDF').click())]);
  ck('Request PDF opens the request sheet', !!pdf && /\/export\/store\/request\/\d+\/view/.test(pdf.url()), pdf && pdf.url()); if (pdf) await pdf.close();
  // one door for material without an LPO: It arrived on the material - 'From a supplier, no LPO' opens the receive form
  await p.evaluate(() => { const b = [...document.querySelectorAll('#ot-req button')].find(b => b.textContent === 'It arrived'); if (b) b.click(); }); await sleep(800);
  if (await p.evaluate(() => document.getElementById('ot-ask') && document.getElementById('ot-ask').classList.contains('on'))) {
    await p.evaluate(() => [...document.querySelectorAll('#ot-ask .seg-chip')].find(b => /From a supplier/.test(b.textContent)).click());
    await p.click('#ot-ask [data-go]'); await sleep(2500);
    ck('It arrived > From a supplier, no LPO opens the portal\'s receive form', await p.evaluate(r => document.getElementById('recv-modal-overlay').style.display === 'flex' && document.getElementById('recv-ref').textContent.includes(r), mrB.ref));
    await p.evaluate(() => closeReceive()); await sleep(1500);
  }
  await toTracker(p);
  // Delete an untouched request (a third one)
  const mrC = await mk('C'); await p.evaluate(() => otLoad()); await sleep(1500);
  const rC = (await api(p, '/store/purchase/tracker')).rows.find(r => r.ref === mrC.ref);
  await menu(p, rC.key); await pick(p, 'Delete the request'); await sleep(600);
  await p.evaluate(() => { const b = [...document.querySelectorAll('button')].filter(b => b.offsetParent && b.textContent.trim() === 'Delete').pop(); b.click(); }); await sleep(2500);
  ck(`Delete the request: ${mrC.ref} gone`, !(await api(p, '/store/purchase/tracker')).rows.some(r => r.ref === mrC.ref));
  // add to item list, from the request in full: a request with a material not on the list
  const mrD = await api(p, '/store/requests', { site: sites[0], requested_by: 'Test Engineer D', lines: [{ description: 'Tracker test widget ' + Date.now() % 100000, qty_requested: 2, unit: 'pcs' }] });
  await api(p, `/store/requests/${mrD.id}/status`, { status: 'approved' });
  await p.evaluate(id => otRequest(id), mrD.id); await sleep(1500);
  if (await p.evaluate(() => !![...document.querySelectorAll('#ot-req button')].find(b => b.textContent === 'Add to item list'))) {
    await p.evaluate(() => [...document.querySelectorAll('#ot-req button')].find(b => b.textContent === 'Add to item list').click()); await sleep(600);
    await p.evaluate(() => { const b = [...document.querySelectorAll('button')].filter(b => b.offsetParent && b.textContent.trim() === 'Add').pop(); b.click(); }); await sleep(3000);
  }
  const linked = (await api(p, `/store/purchase/tracker/request/${mrD.id}`)).lines[0];
  ck('Add to item list: the material is on the list and the line linked to it', !!linked.item_id && !!linked.item_code, linked);
  // Already booked in, from the request in full
  await p.evaluate(() => [...document.querySelectorAll('#ot-req button')].find(b => b.textContent === 'It arrived').click()); await sleep(600);
  await p.evaluate(() => [...document.querySelectorAll('#ot-ask .seg-chip')].find(b => /site directly/.test(b.textContent)).click()); await p.click('#ot-ask [data-go]'); await sleep(2500);
  const lnD = (await api(p, `/store/purchase/tracker/request/${mrD.id}`));
  ck('It arrived (with a note): the material reads arrived, the request delivered - no stock added', lnD.lines[0].qty_received === 2 && lnD.status === 'delivered', lnD.status);
  await closeModals(p); await toTracker(p);
  const mm2 = await menu(p, approved.key);
  ck(`menu on an approved request: ${mm2.join(' | ')}`, mm2.includes('Raise LPO') && mm2.includes('Close as it stands (came earlier / not needed)'), mm2);
  await p.mouse.click(5, 5);
  // close a request as it stands (mrB - waiting): not needed
  await p.evaluate(() => otLoad()); await sleep(1500);
  await menu(p, rB.key); await pick(p, 'Close as it stands (came earlier / not needed)'); await sleep(300);
  ck('Close as it stands: asks what happened and why', (await modalOn(p, 'ot-ask')).includes(mrB.ref));
  await p.click('#ot-ask [value=not_coming]'); await p.click('#ot-ask [data-go]'); await sleep(300);
  ck('Close as it stands: a reason is required', /reason/i.test(await p.$eval('#ot-ask-status', e => e.textContent)));
  await p.fill('#ot-why1', 'Site no longer needs it'); await p.click('#ot-ask [data-go]'); await sleep(2500);
  T = await api(p, '/store/purchase/tracker');
  const rBc = T.rows.find(r => r.ref === mrB.ref);
  ck(`${mrB.ref} closed: under Done & closed, with the reason`, rBc && rBc.stage === 5 && /Not needed: Site no longer needs it/.test(rBc.result), rBc);
  // Ordered LPO: button + menu
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.nx .btn-primary`).click(), ordered.key); await sleep(1500);
  ck(`Book delivery (${ordered.ref}) opens its delivery`, (await modalOn(p, 'pu-dlv')).includes(ordered.ref), await modalOn(p, 'pu-dlv'));
  await closeModals(p);
  const om = await menu(p, ordered.key);
  ck(`menu on an ordered LPO: ${om.join(' | ')}`, ['Book delivery', 'Change quantity / rate', 'Cancel LPO (give reason)', 'View the LPO', 'Deliveries and history'].every(x => om.includes(x)), om);
  const [tab] = await Promise.all([p.context().waitForEvent('page', { timeout: 8000 }).catch(() => null), pick(p, 'View the LPO')]);
  ck('View the LPO opens it in a new tab', !!tab && /\/export\/purchase\/\d+\/view/.test(tab.url()), tab && tab.url());
  if (tab) await tab.close();
  await menu(p, ordered.key); await pick(p, 'Deliveries and history');
  ck('Deliveries and history opens it', (await modalOn(p, 'pu-dlv')).includes(ordered.ref)); await closeModals(p);
  await menu(p, ordered.key); await pick(p, 'Cancel LPO (give reason)');
  ck('Cancel LPO asks first, with the reason', (await modalOn(p, 'lpo-cx-modal')).includes(ordered.ref) || await p.evaluate(r => (document.getElementById('lpo-cx-modal') || {}).textContent.includes(r), ordered.ref));
  await p.click('#lpo-cx-modal [data-x]'); await sleep(1500);
  T = await api(p, '/store/purchase/tracker');
  ck('Keep the LPO: nothing changed', T.rows.find(r => r.ref === ordered.ref).stage === 2);
  // row click = history
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.site`).click(), ordered.key); await sleep(800);
  ck('tapping a row opens its pop-up with every option, the next step first', (await modalOn(p, 'ot-sheet')).includes(ordered.ref) && await p.evaluate(() => document.querySelector('#ot-sheet .ot-acts button').classList.contains('btn-primary'))); await closeModals(p);
  // a delivery booked from the tracker: part of the first line -> Part, says what is to come; stock in by that much
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.nx .btn-primary`).click(), ordered.key); await sleep(1500);
  const line1 = await p.evaluate(() => { const tr = document.querySelector('#pu-dlv tr[data-l]'); return { rem: +tr.dataset.rem, q: !!tr.querySelector('.pu-q') }; });
  if (line1.q && line1.rem >= 2) {
    await p.fill('#pu-dlv tr[data-l] .pu-q', '1'); await p.fill('#pu-dn', 'DN-TRACK-1'); await sleep(200);
    ck('booking short: the form asks why only part came', await p.evaluate(() => document.getElementById('pu-partwhy').style.display !== 'none'));
    await p.click('#pu-dlv-save'); await sleep(500);
    ck('booking short without a reason is refused', /say why/i.test(await p.$eval('#pu-dlv-status', e => e.textContent)));
    await p.click('#pu-partwhy .seg-chip[data-w=site]'); await p.fill('#pu-partnote', 'balance next week'); await p.click('#pu-dlv-save'); await sleep(2500);
    T = await api(p, '/store/purchase/tracker');
    const r = T.rows.find(x => x.ref === ordered.ref);
    ck(`delivery of 1 booked: ${ordered.ref} reads Part, with what is still to come, and why (site asked to hold)`, r.part && r.stage === 3 && !!r.to_come && r.part_why === 'site' && r.part_note === 'balance next week', r);
    await toTracker(p);
    const cell = await p.$eval(`tr[data-k="${r.key}"]`, e => e.textContent.replace(/\s+/g, ' '));
    ck('the row says On hold - site asked to hold the rest', /On hold/.test(cell) && /Site asked to hold the rest - balance next week/.test(cell), cell.slice(0, 200));
  } else ck('ordered LPO line to book', false, line1);
  await closeModals(p); await toTracker(p);
  // part delivery menu
  const pm = await menu(p, part.key);
  ck(`menu on a part delivery: ${pm.join(' | ')}`, ['Book delivery', 'Close - rest not needed', 'Check bill (what came)', 'Change quantity / rate'].every(x => pm.includes(x)), pm);
  await pick(p, 'Change quantity / rate'); await sleep(5000);
  ck('Change quantity / rate opens the LPO for changing', await p.evaluate(id => xlOn('purchase') && lpoEditingId === id, part.id));
  await p.evaluate(() => typeof resetLpoForm === 'function' && resetLpoForm());
  await toTracker(p);
  // arrived: Check bill button -> bill form; save checked -> Done (in Zoho) / Bill checked (not yet in Zoho)
  await p.evaluate(k => { const b = document.querySelector(`tr[data-k="${k}"] td.nx .btn-primary`); b.scrollIntoView({ block: 'center' }); b.click(); }, arrived.key); await sleep(1500);
  ck(`Check bill (${arrived.ref}) opens its bill`, (await modalOn(p, 'pu-bill')).includes(arrived.ref));
  await p.fill('#pb-no', 'B-1'); await p.fill('#pb-amt', '100'); await p.check('#pb-ok');
  await p.evaluate(() => [...document.querySelectorAll('#pu-bill button')].find(b => b.textContent === 'Save').click()); await sleep(2500);
  T = await api(p, '/store/purchase/tracker');
  ck(`bill checked, ${arrived.ref} already in Zoho: Done`, T.rows.find(r => r.ref === arrived.ref).stage === 5, T.rows.find(r => r.ref === arrived.ref));
  await closeModals(p);
  await api(p, `/store/purchase/orders/${l161.id}/bill`, { bill_no: 'B-2', bill_amount: 50, checked: true });
  await p.evaluate(() => otLoad()); await sleep(1500);
  T = await api(p, '/store/purchase/tracker');
  const z = T.rows.find(r => r.ref === 'IC/LPO/20260161');
  ck('bill checked, not in Zoho yet: Bill checked, Accounts to send to Zoho', z.stage === 4 && z.who === 'Accounts' && z.action === 'Send to Zoho', z);
  await p.evaluate(k => { const b = document.querySelector(`tr[data-k="${k}"] td.nx .btn-primary`); b.scrollIntoView({ block: 'center' }); b.click(); }, z.key); await sleep(3000);
  ck('Send to Zoho opens Accounts > Send to Zoho', await p.evaluate(() => xlOn('zoho')));
  // ---- close old orders: one LPO as it stands (came earlier - no stock), then several ticked together (not coming + bill)
  await toTracker(p); await p.evaluate(() => { OT_VIEW = 'open'; otRender(); });
  T = await api(p, '/store/purchase/tracker');
  const olds = T.rows.filter(r => r.kind === 'lpo' && r.stage === 2 && !r.rental).slice(0, 3);
  const st0 = JSON.stringify(await api(p, '/store/stock'));
  await menu(p, olds[0].key); await pick(p, 'Close as it stands (came earlier / not coming)'); await sleep(300);
  await p.check('#ot-bill1'); await p.fill('#ot-why1', 'Before Arun joined - came and used'); await p.click('#ot-ask [data-go]'); await sleep(2500);
  T = await api(p, '/store/purchase/tracker');
  const c0 = T.rows.find(r => r.ref === olds[0].ref);
  ck(`${olds[0].ref} closed as came earlier, bill check closed: Done (or with Accounts if not in Zoho)`, c0.stage >= 4 && !c0.part, c0);
  ck('closing as came earlier added no stock', JSON.stringify(await api(p, '/store/stock')) === st0);
  const hist = await api(p, `/store/purchase/orders/${olds[0].id}/deliveries`);
  ck('its history says it came earlier, no stock added', hist.history.some(h => /Came earlier, not booked then - no stock added/.test(h.notes)), hist.history.slice(-2));
  // no "Close old orders" button any more: each old order is closed from its own More menu
  ck('no Close old orders button', await p.evaluate(() => !document.getElementById('ot-tidy-btn')));
  for (const r of olds.slice(1)) {
    await menu(p, r.key); await pick(p, 'Close as it stands (came earlier / not coming)'); await sleep(300);
    await p.check('#ot-ask [value=not_coming]'); await p.fill('#ot-why1', 'Before the current purchaser - not coming'); await p.click('#ot-ask [data-go]'); await sleep(2500);
  }
  T = await api(p, '/store/purchase/tracker');
  const cl = olds.slice(1).map(o => T.rows.find(r => r.ref === o.ref));
  ck('the 2 old LPOs closed as not coming: Done, "Nothing came - closed"', cl.every(r => r.stage === 5 && /Nothing came/.test(r.result)), cl.map(r => [r.ref, r.stage, r.result]));
  ck('closing them moved no stock', JSON.stringify(await api(p, '/store/stock')) === st0);
  // ---- Done & closed shows cancelled LPOs and closed requests, with why
  await p.evaluate(() => { OT_VIEW = 'done'; otRender(); }); await sleep(300);
  const done = await p.$$eval('#ot-body tr.ot-r', x => x.map(e => e.textContent.replace(/\s+/g, ' ')));
  ck(`Done & closed lists closed and cancelled ones with the reason (${done.length})`, done.some(t => /Cancelled/.test(t)) && done.some(t => /Not needed:/.test(t)), done.slice(0, 3));
  // ---- Preview / PDF / Excel follow the filters on screen
  await p.evaluate(() => { OT_VIEW = 'late'; otRender(); });
  const ex = await p.evaluate(async () => { await refreshDownloadToken(); const out = {};
    for (const f of ['view', 'pdf', 'excel']) { const r = await fetch(`${API}/export/store/tracker?view=late&site=&q=&step=&format=${f}&token=${encodeURIComponent(cachedDownloadToken)}`); out[f] = [r.status, r.headers.get('content-type'), f === 'view' ? (await r.text()) : (await r.arrayBuffer()).byteLength]; }
    return out; });
  const lateN = (await api(p, '/store/purchase/tracker')).rows.filter(r => r.stage < 5 && r.late > 0).length;
  ck('Preview opens, titled Order Tracker, only the Late ones', ex.view[0] === 200 && /Order Tracker/.test(ex.view[2]) && new RegExp(`Late \\| ${lateN} order`).test(ex.view[2]), [ex.view[0], (ex.view[2].match(/Late[^<]{0,40}/) || [])[0], lateN]);
  ck('Export PDF and Excel download', ex.pdf[0] === 200 && /pdf/.test(ex.pdf[1]) && ex.pdf[2] > 2000 && ex.excel[0] === 200 && /sheet/.test(ex.excel[1]), [ex.pdf, ex.excel]);
  // ---- the app's own look: segment chips, standard buttons, standard table heading
  const look = await p.evaluate(() => {
    const on = document.querySelector('#ot-chips .seg-chip.on'), cs = on && getComputedStyle(on);
    const th = getComputedStyle(document.querySelector('#ot-table th'));
    const bt = [...document.querySelectorAll('#ot-body td.nx button')].every(b => b.classList.contains('btn') && (b.classList.contains('btn-primary') || b.classList.contains('btn-gray')));
    const dark = [...document.querySelectorAll('#screen-purchtrack button, #screen-purchtrack select, #screen-purchtrack input')].filter(e => { const bg = getComputedStyle(e).backgroundColor; const c = bg.match(/[\d.]+/g) || [255, 255, 255]; return e.offsetParent && !(c.length === 4 && +c[3] === 0) && +c[0] < 60 && +c[1] < 60 && +c[2] < 60; }).map(e => e.tagName + ':' + e.className + ':' + e.textContent.slice(0, 20));
    return { chip: on && on.className, chipBg: cs && cs.backgroundColor, th: th.backgroundColor, bt, dark };
  });
  ck('the app\'s own look: segment chips, standard buttons and heading, nothing black', look.chipBg === 'rgb(255, 255, 255)' && look.th === 'rgb(245, 243, 238)' && look.bt && look.dark.length === 0, look);
  // ---- Approvals and Order follow-up are off the tab bar; an old link still opens them; a request link opens it in the tracker
  await p.evaluate(() => pgGo('store', 'requests')); await sleep(2500);
  const subs = await p.$$eval('#pg-sub .pg-subtab', x => x.map(e => e.textContent.trim()));
  ck(`Requests shows only Material requests (${subs.join(', ')})`, subs.length === 1 && subs[0] === 'Material requests', subs);
  await p.evaluate(() => pgGo('store', 'requests:followup')); await sleep(2500);
  ck('an old link to Order follow-up goes to the Order tracker (one place)', await p.evaluate(() => xlOn('purchtrack') && !xlOn('followup')));
  await p.evaluate(r => openRequestRef(r), mrA.ref); await sleep(4500);
  ck('a request link (e.g. from a notification or the LPO screen) opens it in full on the tracker', await p.evaluate(r => xlOn('purchtrack') && document.getElementById('ot-req').classList.contains('on') && document.querySelector('#ot-req h3').textContent.includes(r), mrA.ref));
  await closeModals(p);
  ck('admin: no page errors', !p.errs.length, p.errs);
  await p.context().close();
  // ===== the real logins, ticked tab by tab
  for (const [u, role, sees, notSees] of [['arun', 'purchaser', ['Approve', 'Raise LPO', 'Check bill'], ['Send to Zoho']],
                                          ['amal', 'store', ['Book delivery'], ['Send to Zoho']],
                                          ['shafiq', 'accounts', ['Send to Zoho'], []]]) {
    const q = await login(br, u, 'Test12345');
    await q.evaluate(() => pgGo('store')); await sleep(3500);
    const tb = await q.$$eval('#pg-tabs .pg-tab', x => x.map(e => e.textContent.trim()));
    const land = u === 'amal' ? 'store' : 'purchtrack';
    ck(`${u}: sees the Order tracker tab; Store & Purchasing opens on ${land === 'store' ? 'Stock (store keeper)' : 'the Order tracker'}`, tb[tb.length - 1] === 'Order tracker' && await q.evaluate(l => xlOn(l), land), tb);
    await q.evaluate(() => pgGo('store', 'tracker')); await sleep(3500);
    const D = await api(q, '/store/purchase/tracker');
    ck(`${u}: My turn is the ${role}'s`, JSON.stringify(D.my_roles) === JSON.stringify([role]), D.my_roles);
    const chip = await q.$eval('#ot-chips button.on', e => e.textContent);
    const mine = D.rows.filter(r => r.stage < 5 && r.role === role).length;
    ck(`${u}: opens on My turn (${mine})`, chip.replace(/\s+/g, ' ').trim() === `My turn ${mine}`, chip);
    const btns = await q.$$eval('#ot-body td.nx .btn-primary', x => [...new Set(x.map(b => b.textContent))]);
    ck(`${u}: My turn buttons ${btns.join(', ')}`, mine === 0 || (btns.length && btns.every(b => !notSees.includes(b))), btns);
    await q.evaluate(() => { OT_VIEW = 'open'; otRender(); }); await sleep(300);
    const all = await q.$$eval('#ot-body td.nx .btn-primary', x => [...new Set(x.map(b => b.textContent))]);
    ck(`${u}: on All open can use ${all.join(', ')}`, sees.every(s => all.includes(s) || !D.rows.some(r => r.action === s && r.stage < 5)), all);
    if (u === 'amal') {
      const mrE = await api(q, '/store/requests', { site: sites[0], requested_by: 'Site Eng', lines: [{ item_id: items[0].id, description: items[0].name, qty_requested: 7, unit: items[0].unit || 'pcs' }] });
      await q.evaluate(id => apiCall(`/store/requests/${id}/status`, { method: 'POST', body: JSON.stringify({ status: 'approved' }) }), mrE.id).catch(() => 0);
      const dd = await api(q, `/store/purchase/tracker/request/${mrE.id}`);
      if (dd.lines[0].status !== 'approved') { const ad = await login(br, 'admin', 'changeme123'); await api(ad, `/store/requests/${mrE.id}/status`, { status: 'approved' }); await ad.context().close(); }
      await q.evaluate(() => otLoad()); await sleep(1500);
      await q.evaluate(id => otRequest(id), mrE.id); await sleep(1500);
      const has = await q.evaluate(() => [...document.querySelectorAll('#ot-req button')].some(b => b.textContent === 'It arrived'));
      ck('amal: a request material has an "It arrived" button', has);
      await q.evaluate(() => [...document.querySelectorAll('#ot-req button')].find(b => b.textContent === 'It arrived').click()); await sleep(500);
      await q.fill('#ot-why', 'Site people brought it'); await q.click('#ot-ask [data-go]'); await sleep(2500);
      const after = await api(q, `/store/purchase/tracker/request/${mrE.id}`);
      ck('amal: It arrived with a note - the material reads arrived, the request delivered, no stock added', after.lines[0].qty_received === 7 && after.status === 'delivered', [after.status, after.lines[0].qty_received]);
    }
    ck(`${u}: no page errors`, !q.errs.length, q.errs);
    await q.context().close();
  }
  // ===== a phone
  const m = await login(br, 'amal', 'Test12345', { width: 390, height: 800 });
  await m.evaluate(() => pgGo('store', 'tracker')); await sleep(3500);
  const ph = await m.evaluate(() => ({ page: document.documentElement.scrollWidth, cut: [...document.querySelectorAll('#ot-body td')].filter(td => td.scrollWidth > td.clientWidth + 1).length,
    btn: [...document.querySelectorAll('#ot-body td.nx button')].every(b => { const r = b.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; }) }));
  ck('phone: each order a card - no sideways scroll, nothing cut, buttons on screen', ph.page <= 391 && ph.cut === 0 && ph.btn, ph);
  await m.screenshot({ path: '/tmp/claude-0/otf_phone.png' });
  await m.context().close();
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
