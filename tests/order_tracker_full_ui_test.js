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
const menu = async (p, key) => { await p.evaluate(k => { document.querySelectorAll('.ot-menu').forEach(x => x.remove()); const b = document.querySelector(`tr[data-k="${k}"] .ot-dots`); b.scrollIntoView({ block: 'center' }); }, key); await sleep(150);
  await p.click(`tr[data-k="${key}"] .ot-dots`); await sleep(250); return p.$$eval('.ot-menu div[data-i]', x => x.map(e => e.textContent)); };
const pick = async (p, label) => { await p.evaluate(l => { const d = [...document.querySelectorAll('.ot-menu div[data-i]')].find(x => x.textContent === l); d.click(); }, label); await sleep(1800); };
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
  ck('admin: Order tracker is the first tab of Store & Purchasing', tabs[0] === 'Order tracker', tabs);
  // ---- layout
  const lay = await p.evaluate(() => {
    const hs = [...document.querySelectorAll('#ot-table .ot-sh span')].map(s => { const r = s.getBoundingClientRect(); return (r.left + r.right) / 2; });
    const row = document.querySelector('#ot-body tr.ot-r .ot-steps');
    const ss = [...row.children].map(s => { const r = s.getBoundingClientRect(); return (r.left + r.right) / 2; });
    const rights = [...document.querySelectorAll('#ot-body tr.ot-r td.nx .ot-dots')].map(b => Math.round(b.getBoundingClientRect().right));
    const wrap = document.querySelector('#screen-purchtrack .ot-wrap');
    const cut = [...document.querySelectorAll('#ot-body td')].filter(td => td.scrollWidth > td.clientWidth + 1).length;
    const sum = [...document.querySelectorAll('#ot-sum .k')].map(k => k.offsetHeight);
    return { off: Math.max(...hs.map((h, i) => Math.abs(h - ss[i]))), rights: [...new Set(rights)], sideways: wrap.scrollWidth > wrap.clientWidth + 1, cut, sum: [...new Set(sum)] };
  });
  ck(`step names sit over their steps (off by ${lay.off.toFixed(1)}px)`, lay.off < 4, lay);
  ck('the ... buttons line up on the right', lay.rights.length === 1, lay.rights);
  ck('no sideways scrolling at 1440 wide, no text cut off', !lay.sideways && lay.cut === 0, lay);
  ck('the six step boxes on top are the same height', lay.sum.length === 1, lay.sum);
  for (const w of [1280, 1024]) {
    await p.setViewportSize({ width: w, height: 900 }); await sleep(500);
    const o = await p.evaluate(() => { const r = [...document.querySelectorAll('#ot-body td.nx')].map(td => td.getBoundingClientRect().right); const card = document.querySelector('#screen-purchtrack .ot-card').getBoundingClientRect().right; const sum = [...document.querySelectorAll('#ot-sum .k')].some(k => k.scrollWidth > k.clientWidth + 1); return { cut: [...document.querySelectorAll('#ot-body td')].filter(td => td.scrollWidth > td.clientWidth + 1).length, beyond: r.filter(x => x > card + 1).length, page: card > innerWidth + 1, sum }; });
    ck(`at ${w} wide: nothing cut off, buttons inside the card, the tracker fits the screen`, o.cut === 0 && !o.page && !o.beyond && !o.sum, o); await p.screenshot({ path: `/tmp/claude-0/otf_${w}.png` });
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
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.nx button:not(.ot-dots)`).click(), rA.key); await sleep(500);
  ck(`Approve (${rA.ref}) opens its approval`, (await modalOn(p, 'ot-appr')).includes(rA.ref), await modalOn(p, 'ot-appr'));
  await p.click('#ot-appr [data-all="a"]'); await p.click('#ot-appr [data-go]'); await sleep(2500);
  T = await api(p, '/store/purchase/tracker');
  ck('Approve all: the request moves to Approved', T.rows.find(r => r.ref === mrA.ref).stage === 1);
  // MR menus
  const mm = await menu(p, rB.key);
  ck(`menu on a request waiting: ${mm.join(' | ')}`, mm.includes('Approve / approve less / reject') && mm.includes('Open the request (full history)'), mm);
  await pick(p, 'Open the request (full history)'); await sleep(2500);
  ck('Open the request: Approvals opens on it', await p.evaluate(r => xlOn('approvals') && document.getElementById('mreq-list').textContent.includes(r), mrB.ref));
  await toTracker(p);
  const mm2 = await menu(p, approved.key);
  ck(`menu on an approved request: ${mm2.join(' | ')}`, mm2.includes('Raise LPO') && mm2.includes('Close - not needed any more'), mm2);
  await p.mouse.click(5, 5);
  // close a request not needed (mrB is waiting - approve then close)
  await api(p, `/store/requests/${mrB.id}/status`, { status: 'approved' });
  await p.evaluate(() => otLoad()); await sleep(1500);
  const rB2 = (await api(p, '/store/purchase/tracker')).rows.find(r => r.ref === mrB.ref);
  await menu(p, rB2.key); await pick(p, 'Close - not needed any more'); await sleep(300);
  ck('Close - not needed: asks why', (await modalOn(p, 'ot-ask')).includes(mrB.ref));
  await p.click('#ot-ask .chips button:first-child'); await p.click('#ot-ask [data-go]'); await sleep(2500);
  T = await api(p, '/store/purchase/tracker');
  ck(`${mrB.ref} closed and gone from the tracker`, !T.rows.some(r => r.ref === mrB.ref));
  // Ordered LPO: button + menu
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.nx button:not(.ot-dots)`).click(), ordered.key); await sleep(1500);
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
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.site`).click(), ordered.key); await sleep(1500);
  ck('clicking a row opens its history', (await modalOn(p, 'pu-dlv')).includes(ordered.ref)); await closeModals(p);
  // a delivery booked from the tracker: part of the first line -> Part, says what is to come; stock in by that much
  await p.evaluate(k => document.querySelector(`tr[data-k="${k}"] td.nx button:not(.ot-dots)`).click(), ordered.key); await sleep(1500);
  const line1 = await p.evaluate(() => { const tr = document.querySelector('#pu-dlv tr[data-l]'); return { rem: +tr.dataset.rem, q: !!tr.querySelector('.pu-q') }; });
  if (line1.q && line1.rem >= 2) {
    await p.fill('#pu-dlv tr[data-l] .pu-q', '1'); await p.fill('#pu-dn', 'DN-TRACK-1'); await p.click('#pu-dlv-save'); await sleep(2500);
    T = await api(p, '/store/purchase/tracker');
    const r = T.rows.find(x => x.ref === ordered.ref);
    ck(`delivery of 1 booked: ${ordered.ref} reads Part, with what is still to come`, r.part && r.stage === 3 && !!r.to_come, r);
  } else ck('ordered LPO line to book', false, line1);
  await closeModals(p); await toTracker(p);
  // part delivery menu
  const pm = await menu(p, part.key);
  ck(`menu on a part delivery: ${pm.join(' | ')}`, ['Book more delivery', 'Close - rest not needed', 'Check bill (what came)', 'Change quantity / rate'].every(x => pm.includes(x)), pm);
  await pick(p, 'Change quantity / rate'); await sleep(5000);
  ck('Change quantity / rate opens the LPO for changing', await p.evaluate(id => xlOn('purchase') && lpoEditingId === id, part.id));
  await p.evaluate(() => typeof resetLpoForm === 'function' && resetLpoForm());
  await toTracker(p);
  // arrived: Check bill button -> bill form; save checked -> Done (in Zoho) / Bill checked (not yet in Zoho)
  await p.evaluate(k => { const b = document.querySelector(`tr[data-k="${k}"] td.nx button:not(.ot-dots)`); b.scrollIntoView({ block: 'center' }); b.click(); }, arrived.key); await sleep(1500);
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
  ck('bill checked, not in Zoho yet: Bill checked, Shafeeq to send to Zoho', z.stage === 4 && z.who === 'Shafeeq' && z.action === 'Send to Zoho', z);
  await p.evaluate(k => { const b = document.querySelector(`tr[data-k="${k}"] td.nx button:not(.ot-dots)`); b.scrollIntoView({ block: 'center' }); b.click(); }, z.key); await sleep(3000);
  ck('Send to Zoho opens Accounts > Send to Zoho', await p.evaluate(() => xlOn('zoho')));
  ck('admin: no page errors', !p.errs.length, p.errs);
  await p.context().close();
  // ===== the real logins, ticked tab by tab
  for (const [u, role, sees, notSees] of [['arun', 'purchaser', ['Approve', 'Raise LPO', 'Check bill'], ['Send to Zoho']],
                                          ['amal', 'store', ['Book delivery'], ['Send to Zoho']],
                                          ['shafiq', 'accounts', ['Send to Zoho'], []]]) {
    const q = await login(br, u, 'Test12345');
    await q.evaluate(() => pgGo('store')); await sleep(3500);
    const tb = await q.$$eval('#pg-tabs .pg-tab', x => x.map(e => e.textContent.trim()));
    ck(`${u}: sees the Order tracker tab, and Store & Purchasing opens on it`, tb[0] === 'Order tracker' && await q.evaluate(() => xlOn('purchtrack')), tb);
    const D = await api(q, '/store/purchase/tracker');
    ck(`${u}: My turn is the ${role}'s`, JSON.stringify(D.my_roles) === JSON.stringify([role]), D.my_roles);
    const chip = await q.$eval('#ot-chips button.on', e => e.textContent);
    const mine = D.rows.filter(r => r.stage < 5 && r.role === role).length;
    ck(`${u}: opens on My turn (${mine})`, chip === `My turn (${mine})`, chip);
    const btns = await q.$$eval('#ot-body td.nx button:not(.ot-dots)', x => [...new Set(x.map(b => b.textContent))]);
    ck(`${u}: My turn buttons ${btns.join(', ')}`, mine === 0 || (btns.length && btns.every(b => !notSees.includes(b))), btns);
    await q.evaluate(() => { OT_VIEW = 'open'; otRender(); }); await sleep(300);
    const all = await q.$$eval('#ot-body td.nx button:not(.ot-dots)', x => [...new Set(x.map(b => b.textContent))]);
    ck(`${u}: on All open can use ${all.join(', ')}`, sees.every(s => all.includes(s) || !D.rows.some(r => r.action === s && r.stage < 5)), all);
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
