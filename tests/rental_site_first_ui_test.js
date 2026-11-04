// Return note: the site is picked first, and only the suppliers and materials still on rent there show (4 Nov 2026).
// Issued to sites: a line entered by mistake can be deleted - and not when its material has already moved on.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/roles.db 8460 tests/rental_site_first_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE; const TAG = String(Date.now()).slice(-6);
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i).slice(0, 400))); };
(async () => {
  const br = await chromium.launch(); const p = await br.newPage({ viewport: { width: 1500, height: 1000 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => { errs.push('dialog ' + d.message()); d.dismiss(); });
  await p.goto(B + '/app-classic.html'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123');
  await p.evaluate(() => doLogin()); await p.waitForTimeout(3000);
  const ids = await p.evaluate(async T => {
    const today = new Date().toISOString().slice(0, 10), mk = async (name, sup) => {
      return (await apiCall('/store/items', { method: 'POST', body: JSON.stringify({ name, unit: 'pcs', item_type: 'rental', rental_supplier: sup, opening_qty: 0 }) })).id; };
    const a = await mk('Rental Standard 2.5M ' + T, 'Scaff A ' + T), a2 = await mk('Rental Standard 2.8M ' + T, 'Scaff A ' + T), b = await mk('Rental Tube 3M ' + T, 'Scaff B ' + T);
    const errs = []; const mv = async (o) => { try { return await apiCall('/store/movements', { method: 'POST', body: JSON.stringify(Object.assign({ moved_on: today }, o)) }); } catch (e) { errs.push(errText(e)); } };
    await mv({ item_id: a, kind: 'in', qty: 16, location: '901', supplier: 'Scaff A ' + T });
    await mv({ item_id: a2, kind: 'in', qty: 16, location: '901', supplier: 'Scaff A ' + T });
    await mv({ item_id: b, kind: 'in', qty: 40, location: '902', supplier: 'Scaff B ' + T });
    await mv({ item_id: a, kind: 'in', qty: 5, location: '902', supplier: 'Scaff A ' + T });
    const h = await apiCall('/store/hire');
    return { a, a2, b, errs, hire: h.suppliers.filter(g => g.supplier.includes(T)).map(g => [g.supplier, g.items.map(i => [i.name, i.by_location])]) };
  }, TAG);
  ck('the deliveries are recorded at the sites', !ids.errs.length && ids.hire.length === 2, ids);
  await p.evaluate(() => { switchScreen('store'); }); await p.waitForTimeout(1200);
  await p.evaluate(() => storeGo('returns')); await p.waitForTimeout(1500);
  await p.click('#store-returns button:has-text("New return note")'); await p.waitForTimeout(1500);
  ck('the "New return note" button on the panel opens the form', await p.evaluate(() => document.getElementById('rn-form-card').offsetParent !== null));
  const order = await p.evaluate(() => [...document.querySelectorAll('#rn-form-card .field label')].slice(0, 3).map(l => l.textContent.trim()));
  ck('the site comes first on the return note', /Returned from/.test(order[1]) && /Going back to/.test(order[2]), order);
  const r = await p.evaluate(T => {
    const from = document.getElementById('rn-from'), sup = document.getElementById('rn-supplier');
    const out = { first: from.value, sites: [...from.options].map(o => o.textContent), supWhilePick: sup.textContent };
    from.value = '902'; onReturnPlace();
    out.sup902 = [...sup.options].map(o => o.textContent).filter(t => t.includes(T));
    const oa = [...sup.options].find(o => o.textContent.includes('Scaff A ' + T)); if (!oa) return Object.assign(out, { all902: [...sup.options].map(o => o.textContent), hire: hireOnHire.suppliers.filter(g => g.supplier.includes(T)).map(g => [g.supplier, g.supplier_id, g.items.map(i => i.by_location)]) });
    sup.value = oa.value; onReturnSupplier();
    out.lines902A = rnLines.map(l => [l.description, l.qty_on_hire]);
    from.value = '901'; onReturnPlace();
    out.sup901 = [...sup.options].map(o => o.textContent).filter(t => t.includes(T));
    out.lines901 = rnLines.map(l => [l.description, l.qty_on_hire]).filter(x => x[0].includes(T));
    return out;
  }, TAG);
  ck('it starts on "Pick the site" with every site holding rental material', r.first === '__pick' && r.sites.some(t => /^901 /.test(t)) && r.sites.some(t => /^902 /.test(t)), r.sites);
  ck('no supplier is offered until a site is picked', /Pick the site first/.test(r.supWhilePick), r.supWhilePick);
  ck('site 902 offers only the suppliers with material there', r.sup902.length === 2, r.sup902);
  ck('and Scaff A at 902 lists only its 5 pcs standing there', JSON.stringify(r.lines902A.filter(x => x[0].includes(TAG))) === JSON.stringify([['Rental Standard 2.5M ' + TAG, 5]]), r.lines902A);
  ck('site 901 offers Scaff A only, with its 2 materials there', r.sup901.length === 1 && /Scaff A .*\(2 items\)/.test(r.sup901[0]) && r.lines901.length === 2, r);
  await p.screenshot({ path: '/tmp/claude-0/ui2/rn_site_first.png', clip: { x: 0, y: 0, width: 1500, height: 560 } });
  // ---- Issued to sites: delete the wrong 2.8M line
  await p.evaluate(async ([a2, T]) => {
    const mid = (await apiCall('/store/movements?item_id=' + a2).catch(() => null));
    window.__mid = Array.isArray(mid) && mid[0] ? mid[0].id : null;
  }, [ids.a2, TAG]);
  let mid = await p.evaluate(() => window.__mid);
  if (!mid) {                                   // find the movement through the usage report
    mid = await p.evaluate(async T => { const d = await apiCall('/store/report?kind=usage'); const r = d.rows.find(x => x.name === 'Rental Standard 2.8M ' + T); return r && r._mid; }, TAG);
  }
  ck('the 2.8M line is in Issued to sites', !!mid, mid);
  await p.evaluate(async ([mid, T]) => { window.USAGE_ROWS = [{ _mid: mid, name: 'Rental Standard 2.8M ' + T, qty: 16, unit: 'pcs', date: new Date().toISOString().slice(0, 10), _loc: '901', _move: 'delivered direct' }]; await editUsageRow(0); }, [mid, TAG]);
  await p.waitForTimeout(600);
  await p.click('#ue-del'); await p.waitForTimeout(200);
  const ask = await p.textContent('#ue-del');
  ck('Delete asks once on the button itself (no pop-up)', /Yes, delete 16 pcs Rental Standard 2\.8M/.test(ask), ask);
  await p.screenshot({ path: '/tmp/claude-0/ui2/usage_delete.png' });
  await p.click('#ue-del'); await p.waitForTimeout(1500);
  const gone = await p.evaluate(async T => { const h = await apiCall('/store/hire'); return h.suppliers.flatMap(g => g.items).filter(i => i.name === 'Rental Standard 2.8M ' + T).length; }, TAG);
  ck('the wrong 2.8M line is gone - nothing on rent for it any more', gone === 0, gone);
  // ---- a line whose material has already moved on cannot be deleted
  const guard = await p.evaluate(async ([b, T]) => {
    await apiCall('/store/movements', { method: 'POST', body: JSON.stringify({ item_id: b, kind: 'transfer', qty: 30, from_location: '902', location: '903', moved_on: new Date().toISOString().slice(0, 10) }) });
    const d = await apiCall('/store/report?kind=usage'); const row = d.rows.find(x => x.name === 'Rental Tube 3M ' + T && /direct/i.test(x._move || ''));
    try { await apiCall('/store/movements/' + row._mid, { method: 'DELETE' }); return 'deleted'; } catch (e) { return errText(e); }
  }, [ids.b, TAG]);
  ck('a delivery already moved on to another site cannot be deleted, and says why', /would leave 902 with -30/.test(guard), guard);
  // ---- the register read one site at a time
  const reg = await p.evaluate(async T => {
    const h = await apiCall('/store/hire'), A = h.suppliers.find(g => g.supplier === 'Scaff A ' + T), Bs = h.suppliers.find(g => g.supplier === 'Scaff B ' + T);
    const it = (g, n) => g.items.find(i => i.name.startsWith(n)).item_id, today = new Date().toISOString().slice(0, 10);
    const mk = (g, loc, item, q) => apiCall('/store/returns', { method: 'POST', body: JSON.stringify({ supplier_id: g.supplier_id, return_date: today, from_location: loc, lines: [{ item_id: item, qty_returned: q }] }) });
    await mk(A, '901', it(A, 'Rental Standard 2.5M'), 6); await mk(A, '902', it(A, 'Rental Standard 2.5M'), 2); await mk(Bs, '902', it(Bs, 'Rental Tube 3M'), 4);
    await refreshReturnList();
    const sites = [...document.querySelectorAll('#rnl-site option')].map(o => o.textContent);
    const pick = (id, v) => { const s = document.getElementById(id); s.value = [...s.options].find(o => o.textContent.startsWith(v)).value; drawReturnList(); };
    pick('rnl-sup', 'Scaff A ' + T); pick('rnl-site', '902');
    const rows902A = [...document.querySelectorAll('#rn-list tr')].map(tr => tr.children[2] && tr.children[2].textContent.trim());
    const sum902A = document.getElementById('rnl-sum').textContent;
    pick('rnl-sup', 'All suppliers'); document.getElementById('rnl-mats').checked = true; drawReturnList();
    const mats = [...document.querySelectorAll('#rnl-mat tr')].map(tr => [...tr.children].map(td => td.textContent.trim()).join(' | ')).filter(t => t.includes(T));
    return { sites, rows902A, sum902A, mats };
  }, TAG);
  ck('the register filters by site, listing each site with its notes', reg.sites[0] === 'All sites' && reg.sites.some(t => /^901 \(/.test(t)) && reg.sites.some(t => /^902 \(/.test(t)), reg.sites);
  ck('site 902 + Scaff A: just its one note, with the Site column, total returned 2', reg.rows902A.length === 1 && reg.rows902A[0] === '902' && /1 note · returned 2/.test(reg.sum902A), reg);
  ck('by material: what came back from 902, material by material', reg.mats.length === 2 && reg.mats.some(t => t.startsWith('Rental Standard 2.5M') && t.endsWith('| 1 | 2 pcs | -')) && reg.mats.some(t => t.startsWith('Rental Tube 3M') && t.endsWith('| 1 | 4 pcs | -')), reg.mats);
  await p.evaluate(() => document.getElementById('rnl-site').scrollIntoView()); await p.evaluate(() => scrollBy(0, -120));
  await p.screenshot({ path: '/tmp/claude-0/ui2/rn_register_site.png' });
  ck('no page errors or pop-ups', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close();
})();
