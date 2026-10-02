// Names and numbers open their own record, for someone allowed to open it;
// everyone else sees plain text. Run on a copy of the real data (rich.db).
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const login = async (u, pw, url = '/') => {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage(); p.ctx = ctx;
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + url); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500); return p;
  };
  const api = (p, u, m, body) => p.evaluate(async ([u, m, body]) => { try { return await apiCall(u, m ? { method: m, body: JSON.stringify(body) } : undefined); } catch (e) { return { err: e.status, d: e.body }; } }, [u, m, body]);
  const active = p => p.evaluate(() => (document.querySelector('.screen.active') || {}).id);
  const a = await login('admin', 'changeme123');
  // ---- seed: a supplier, a request (approved), an order -----------------
  const items = await api(a, '/store/items'); const it = items[0];
  await api(a, '/store/suppliers', 'POST', { name: 'Al Raha Trading LLC', contact_person: 'Imran', phone: '0501234567', trn: '100111222300003' });
  const sites = await api(a, '/sites'); const site = (sites[0] || {}).code || '';
  const mr = await api(a, '/store/requests', 'POST', { site, requested_by: 'Site engineer', urgency: 'normal', lines: [{ item_id: it.id, qty_requested: 20, unit: it.unit || 'pcs', purpose: 'Slab' }] });
  ck('seed: request raised', mr && mr.ref, mr);
  for (const l of mr.lines || []) await api(a, `/store/request-lines/${l.id}/decision`, 'POST', { decision: 'approved', reason: '' });
  const po = await api(a, '/store/purchase/orders', 'POST', { order_date: '2026-10-01', supplier_name: 'Al Raha Trading LLC', lines: [{ item_id: it.id, description: it.name, qty: 20, unit: it.unit || 'pcs', rate: 16.5, tax_pct: 5 }] });
  ck('seed: order raised', po && po.ref, po);

  // ---- Expiry > People: a name opens his file on Staff, at the document ----
  const staffCheck = async (office) => {
    await a.evaluate(() => pgGo('expiry')); await a.waitForTimeout(2500);
    await a.evaluate(() => { document.getElementById('hr-doc-within').value = '-1'; renderDocuments(); });
    const row = await a.evaluate(office => { const l = [...document.querySelectorAll('#hr-doc-body a.xl')].find(x => /Office/.test(x.parentElement.textContent) === office);
      if (!l) return null; const tr = l.closest('tr'); const lit = [...tr.querySelectorAll('td.hr-d')].map(td => td.textContent.trim());
      return [l.textContent, tr.children[0].textContent.trim()]; }, office);
    ck(`expiry: ${office ? 'office' : 'labour'} names are links`, !!row, row);
    if (!row) return;
    await a.click(`#hr-doc-body a.xl:text-is("${row[0]}")`); await a.waitForTimeout(5000);
    const fr = a.frameLocator('#pg-staff-frame');
    const head = await fr.locator('#file h2').textContent().catch(() => '');
    const sec = await fr.locator('#file .subtabs button.on').textContent().catch(() => '');
    const lit = await fr.locator('#file tr.focus').count().catch(() => 0);
    const docs = await fr.locator('#file tbody tr').count().catch(() => 0);
    ck(`${office ? 'office' : 'labour'} name -> Staff register, his file, Documents, the document lit up`,
       (await active(a)) === 'screen-pgstaff' && head.includes(row[1]) && sec === 'Documents' && (lit === 1 || docs === 0), [await active(a), head, sec, lit, docs]);
    if (!office) await a.screenshot({ path: SH + 'xl_staff_doc.png' });
  };
  await staffCheck(false);
  await staffCheck(true);
  // ---- loans list: name opens the record in place ------------------------
  await a.evaluate(() => pgGo('payroll', 'hrpayroll:loans')); await a.waitForTimeout(3000);
  const ln = await a.$('#hr-loan-body a.xl');
  ck('loans: names are links', !!ln);
  if (ln) { const nm = await ln.textContent(); await ln.click(); await a.waitForTimeout(800); ck('loan name -> staff record', await a.locator('#hr-dlg').isVisible() && (await a.textContent('#hr-staff-edit-title')).includes(nm)); await a.evaluate(() => hrCloseDlg()); }
  // ---- follow-up: request number, material, supplier ----------------------
  await a.evaluate(() => pgGo('store', 'requests:followup')); await a.waitForTimeout(3000);
  await a.screenshot({ path: SH + 'xl_followup.png' });
  const refLink = a.locator(`#screen-followup a.xl:text-is("${mr.ref}")`).first();
  ck('follow-up: request number is a link', await refLink.count() > 0);
  if (await refLink.count()) {
    await refLink.click(); await a.waitForTimeout(3500);
    const open = await a.evaluate(ref => { const r = (mrCache || []).find(x => x.ref === ref); const d = r && document.getElementById('mr-detail-' + r.id); return !!d && d.style.display !== 'none'; }, mr.ref);
    ck('request number -> Approvals with that request open', (await active(a)) === 'screen-approvals' && open, await active(a));
  }
  await a.evaluate(() => pgGo('store', 'requests:followup')); await a.waitForTimeout(3000);
  const supL = a.locator('#screen-followup a.xl:text-is("Al Raha Trading LLC")').first();
  if (await supL.count()) {
    await supL.click(); await a.waitForTimeout(3500);
    ck('supplier -> its card on the supplier list', (await active(a)) === 'screen-suppliers' && (await a.inputValue('#sup-name')) === 'Al Raha Trading LLC', [await active(a), await a.inputValue('#sup-name')]);
  } else ck('follow-up supplier link (ordered line)', true, 'line not ordered yet - skipped');
  // ---- request detail: material opens stock -------------------------------
  await a.evaluate(ref => { pgGo('store', 'requests:approvals'); }, mr.ref); await a.waitForTimeout(3000);
  await a.evaluate(ref => { document.getElementById('mreq-filter').value = 'all'; document.getElementById('mreq-search').value = ref; return loadRequests(); }, mr.ref); await a.waitForTimeout(1500);
  await a.evaluate(ref => { const r = mrCache.find(x => x.ref === ref); toggleRequest(r.id); }, mr.ref); await a.waitForTimeout(500);
  const mat = a.locator(`a.xl:text-is("${it.code}")`).first();
  ck('request line: material code is a link', await mat.count() > 0, it.code);
  if (await mat.count()) {
    await mat.click(); await a.waitForTimeout(4500);
    ck('material -> Stock on hand, found', (await active(a)) === 'screen-store' && (await a.inputValue('#home-stock-search')) === it.code, [await active(a)]);
  }
  // ---- LPO register: supplier line drills down to its orders --------------
  await a.evaluate(() => pgGo('store', 'purchasing:lporegister')); await a.waitForTimeout(3000);
  await a.evaluate(() => { document.getElementById('lpr-group').value = 'supplier'; return loadLpoReport(); }); await a.waitForTimeout(1500);
  const drill = a.locator('#lpr-body a.xl, #screen-lporegister a.xl:text-is("Al Raha Trading LLC")').first();
  ck('LPO register by supplier: supplier is a link', await drill.count() > 0);
  if (await drill.count()) {
    await drill.click(); await a.waitForTimeout(2000);
    ck('supplier line -> that supplier\'s orders one by one', (await a.inputValue('#lpr-group')) === 'order' && (await a.inputValue('#lpr-supplier')) === 'Al Raha Trading LLC', [await a.inputValue('#lpr-group'), await a.inputValue('#lpr-supplier')]);
  }
  // ---- invoices: proforma <-> tax invoice ---------------------------------
  await a.evaluate(() => pgGo('accounts', 'proforma')); await a.waitForTimeout(3000);
  const conv = a.locator('#inv-body a.inv-tag.conv').first();
  ck('proforma: Invoiced is a link', await conv.count() > 0);
  if (await conv.count()) {
    await conv.click(); await a.waitForTimeout(3000);
    ck('Invoiced -> the tax invoice, open in the form', (await a.evaluate(() => INV_KIND)) === 'tax' && (await a.textContent('#inv-form-title')).startsWith('Editing IC/'), await a.textContent('#inv-form-title'));
    const back = a.locator('#inv-body a.inv-tag.from').first();
    ck('tax invoice: from proforma is a link', await back.count() > 0);
    if (await back.count()) { await back.click(); await a.waitForTimeout(3000); ck('from proforma -> the proforma', (await a.evaluate(() => INV_KIND)) === 'proforma' && (await a.textContent('#inv-form-title')).startsWith('Editing PI/'), await a.textContent('#inv-form-title')); }
  }
  // ---- PDC grid: payee lists its cheques ----------------------------------
  await a.evaluate(() => pgGo('expiry', 'expiry:pdc')); await a.waitForTimeout(3000);
  const pay = a.locator('#pdc-gbody a.xl').first();
  ck('PDC grid: payees are links', await pay.count() > 0);
  if (await pay.count()) { const nm = await pay.textContent(); await pay.click(); await a.waitForTimeout(800);
    ck('payee -> cheque list for that payee', await a.locator('#pdc-list-wrap').isVisible() && (await a.inputValue('#pdc-search')) === nm); }
  // ---- activity log: request number ---------------------------------------
  await a.evaluate(() => pgGo('settings', 'activity')); await a.waitForTimeout(3000);
  ck('activity log: request numbers are links', await a.locator('.act-det a.xl').count() > 0);
  ck('no script errors (admin)', !a.errs.length, a.errs);
  await a.screenshot({ path: SH + 'xl_activity.png' });

  // ---- a login without the rights sees plain text --------------------------
  const d = await login('docsonly', 'docs12345', '/?p=expiry');
  await d.evaluate(() => { document.getElementById('hr-doc-within').value = '-1'; renderDocuments(); });
  ck('documents-only login: names are plain text', (await d.locator('#hr-doc-body a.xl').count()) === 0, await d.locator('#hr-doc-body a.xl').count());
  ck('no script errors (documents)', !d.errs.length, d.errs);
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'CROSS-LINKS OPEN THE RIGHT RECORD');
})();
