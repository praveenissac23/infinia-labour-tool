// Zoho account picker: Shafeeq's own Zoho accounts, grouped as Zoho shows
// them (type, parent, sub-account), his most-used on top, search, keyboard,
// Transfer to Cash / Machinery / Job Assets offered, project not demanded
// for them, the split and the Bank tab use the same list.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
const TAG = String(Date.now()).slice(-6);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 950 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); await p.evaluate(t => { window.TAG = t; }, TAG);
  // a site line with no project, and an office line, waiting for Zoho
  await p.evaluate(async () => {
    for (const b of [{ book: 'site', date: '2026-10-13', description: 'Machinery repair - generator '+TAG+'', supplier: '', paid: 150 },
                     { book: 'office', date: '2026-10-13', description: 'Cash handed back to cash box '+TAG+'', supplier: '', paid: 500 }])
      try { await apiCall('/store/petty-cash', { method: 'POST', body: JSON.stringify(b) }); } catch (e) { console.log(e.message); }
  });
  await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Send to Zoho'); t.click(); });
  await p.waitForTimeout(3500);
  const n = await p.locator('#zh-body .za-btn').count();
  ck('each line has the account button (no long dropdown)', n > 0 && (await p.locator('#zh-body select.zh-acc').count()) === 0, n);
  const row = p.locator('#zh-body tr', { hasText: 'Machinery repair - generator '+TAG+'' });
  ck('test line listed', await row.count() === 1);
  await row.locator('.za-btn').click(); await p.waitForTimeout(250);
  ck('picker opens with search focused', await p.evaluate(() => document.activeElement && document.activeElement.id === 'za-q'));
  const heads = await p.locator('#za-pop .za-h').allTextContents();
  ck('Most used first, then Zoho\'s groups', heads[0] === 'Most used' && heads.includes('Project costs') && heads.includes('Expenses') && heads.includes('Machinery, tools & assets') && heads.some(h => /^Transfers/.test(h)), heads);
  const top = await p.locator('#za-pop .za-i').evaluateAll(e => e.slice(0, 5).map(x => x.textContent.trim()));
  ck('his asked-for accounts top the list', /Machinery Repair/.test(top[0]) && top.some(t => /Tip for security and driver/i.test(t)) && top.some(t => /Labour Camp Expenses/.test(t)), top);
  const all = await p.locator('#za-pop .za-i').count();
  ck(`his accounts plus the cost heads with theirs, not 1,300 (${all})`, all > 300 && all < 800, all);
  await p.screenshot({ path: SH + 'za_open.png' });
  // search: machinery
  await p.fill('#za-q', 'machinery'); await p.waitForTimeout(150);
  const m = await p.locator('#za-pop .za-i').allTextContents();
  ck('search "machinery" finds Tools & Machinery, Rent and Repair', m.some(t => /Tools & Machinery/.test(t)) && m.some(t => /^Machinery Rent$/.test(t.trim())) && m.some(t => /Machinery Repair/.test(t)), m);
  ck('parent shown above its sub-accounts', (await p.locator('#za-pop .za-p').allTextContents()).some(t => /Preliminaries|Job Related/.test(t)));
  await p.screenshot({ path: SH + 'za_search.png' });
  // keyboard: down + enter picks
  await p.fill('#za-q', 'machinery rent'); await p.waitForTimeout(100);
  const first = (await p.locator('#za-pop .za-i').first().textContent()).trim();
  await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  ck('Enter picks the first match and closes', !(await p.locator('#za-pop').count()), first);
  const acc = await p.evaluate(() => { const r = ZH.rows.find(x => x.description === 'Machinery repair - generator '+TAG+''); return [ZH_PICK[r.id].account, zhFlags(r)]; });
  ck('picked: Machinery Rent, nothing to fix (no project asked)', /Machinery Rent/.test(acc[0]) && !acc[1].length, acc);
  ck('button shows the account', /Machinery Rent/.test(await row.locator('.za-btn').textContent()));
  // Transfer to Cash on the office line
  const orow = p.locator('#zh-body tr', { hasText: 'Cash handed back to cash box '+TAG });
  await orow.locator('.za-btn').click(); await p.fill('#za-q', 'transfer to cash'); await p.waitForTimeout(100);
  await p.locator('#za-pop .za-i', { hasText: 'Transfer to Cash' }).first().click(); await p.waitForTimeout(300);
  const o = await p.evaluate(() => { const r = ZH.rows.find(x => x.description === 'Cash handed back to cash box '+TAG+''); return [ZH_PICK[r.id].account, zhFlags(r)]; });
  ck('Transfer to Cash can be picked, ready to send', o[0] === 'Transfer to Cash' && !o[1].length, o);
  // the server agrees
  const srv = await p.evaluate(async () => { const r = ZH.rows.find(x => x.description === 'Cash handed back to cash box '+TAG+'');
    try { return await apiCall('/store/zoho/approve', { method: 'POST', body: JSON.stringify({ lines: [{ id: r.id, account: 'Transfer to Cash' }] }) }); } catch (e) { return { err: e.message }; } });
  ck('server accepts Transfer to Cash (approved)', srv.approved === 1 && !(srv.refused || []).length, srv);
  const srv2 = await p.evaluate(async () => { const r = ZH.rows.find(x => x.description === 'Machinery repair - generator '+TAG+'');
    try { return await apiCall('/store/zoho/approve', { method: 'POST', body: JSON.stringify({ lines: [{ id: r.id, account: 'Job Related › Job Assets' }] }) }); } catch (e) { return { err: e.message }; } });
  ck('server accepts Job Assets with no project', srv2.approved === 1, srv2);
  const srv3 = await p.evaluate(async () => { await zhLoad(); const r = ZH.rows[0]; if (!r) return { skip: 1 };
    try { return await apiCall('/store/zoho/approve', { method: 'POST', body: JSON.stringify({ lines: [{ id: r.id, account: 'Not A Zoho Account' }] }) }); } catch (e) { return { err: e.message }; } });
  ck('an account Zoho does not have is refused', srv3.skip || (srv3.approved === 0 && (srv3.refused || []).length === 1), srv3);
  // Escape closes, click outside closes
  await p.locator('#zh-body .za-btn').first().click(); await p.keyboard.press('Escape'); await p.waitForTimeout(150);
  ck('Escape closes', !(await p.locator('#za-pop').count()));
  // split uses the picker, no transfers there
  const sid = await p.evaluate(() => { const r = ZH.rows.find(x => x.kind === 'paid'); if (r) zhSplit(r.id); return r ? r.id : 0; });
  if (sid) {
    await p.waitForTimeout(300);
    ck('split rows use the picker', await p.locator('.zx-modal .zs-row .za-btn').count() === 2);
    await p.locator('.zx-modal .zs-row .za-btn').nth(1).click(); await p.waitForTimeout(150);
    const sh = await p.locator('#za-pop .za-h').allTextContents();
    ck('split offers costs only, no transfers', !sh.some(h => /^Transfers/.test(h)), sh);
    await p.locator('#za-pop .za-i').nth(2).click(); await p.waitForTimeout(200);
    ck('split part picked', await p.evaluate(id => !!ZH_PICK[id].splits[1].account, sid));
    await p.screenshot({ path: SH + 'za_split.png' });
    await p.click('#zs-close');
  }
  // Bank tab: the same list
  await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Bank'); t.click(); }); await p.waitForTimeout(2500);
  const hasExp = await p.evaluate(() => { if (typeof bkKind !== 'function') return false; bkKind('expense'); return true; });
  await p.waitForTimeout(400);
  if (hasExp && await p.locator('#bk-acc-btn .za-btn').count()) {
    await p.locator('#bk-acc-btn .za-btn').click(); await p.fill('#za-q', 'tools'); await p.waitForTimeout(100);
    await p.locator('#za-pop .za-i').first().click(); await p.waitForTimeout(200);
    ck('Bank: account picked into the form', /Tools & Machinery/.test(await p.inputValue('#bk-acc')), await p.inputValue('#bk-acc'));
    await p.screenshot({ path: SH + 'za_bank.png' });
  } else ck('Bank expense form has the picker', false, hasExp);
  // phone width
  await p.setViewportSize({ width: 390, height: 844 });
  await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Send to Zoho'); t.click(); }); await p.waitForTimeout(2500);
  await p.locator('#zh-body .za-btn').first().scrollIntoViewIfNeeded(); await p.locator('#zh-body .za-btn').first().click(); await p.waitForTimeout(250);
  const bx = await p.locator('#za-pop').boundingBox();
  ck('phone: picker fits the screen', bx && bx.x >= 0 && bx.x + bx.width <= 390, bx);
  await p.screenshot({ path: SH + 'za_phone.png' });
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await b.close();
})();
