// Expiry Reminder > PDCs: post-dated cheques for admin and the chief
// accountant only. Monthly cheques count up, the month-by-month grid
// totals both ways, reminders at 14 and 7 days, cleared/cancelled, the
// papers - and nobody else sees a page, a figure, a bell line or a badge.
// Needs logins: chiefacc (pdc,settings), docsonly (expiry,settings), amaltest (store,storekeeper).
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
const iso = d => d.toISOString().slice(0, 10);
const today = new Date(Date.now() + 4 * 3600e3); today.setUTCHours(0, 0, 0, 0);
const plus = n => iso(new Date(today.getTime() + n * 864e5));
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const login = async (u, pw, url = '/?p=expiry') => {
    const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + url); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500); return p;
  };
  const api = (p, u, m, body) => p.evaluate(async ([u, m, body]) => { try { return { ok: 1, d: await apiCall(u, m ? { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined) }; } catch (e) { return { ok: 0, status: e.status, msg: (e.body && e.body.detail) || String(e.message) }; } }, [u, m, body]);
  const subs = p => p.evaluate(() => [...document.querySelectorAll('.pg-subtab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  const badge = p => p.evaluate(() => { const b = document.querySelector('.pg-item[data-page="expiry"] .pg-badge'); return b ? +b.textContent : 0; });

  // ---- Admin enters cheques the way the accountant does --------------------
  const a = await login('admin', 'changeme123', '/?p=expiry#expiry:pdc');
  ck('admin: Expiry Reminder has a PDCs tab', (await subs(a)).includes('PDCs'), await subs(a));
  ck('the address /?p=expiry#expiry:pdc opens it', await a.locator('#screen-pdc').isVisible());
  const add = async (payee, no, date, amt, notes = '', months = '1') => {
    await a.fill('#pdc-payee', payee); await a.fill('#pdc-no', no); await a.fill('#pdc-bank', 'ADCB');
    await a.fill('#pdc-date', date); await a.fill('#pdc-amt', String(amt)); await a.fill('#pdc-notes', notes);
    await a.selectOption('#pdc-repeat', months); await a.click('#pdc-save'); await a.waitForTimeout(1200);
  };
  await add('Office Rent - Bin Bishr', '000451', plus(14), 16590, 'Rent', '3');
  ck('rent for 3 months says "3 monthly cheques added"', /3 monthly cheques/.test(await a.locator('#pdc-status').textContent()));
  let rows = (await api(a, '/employees/pdc')).d.rows.filter(r => /Bin Bishr/.test(r.payee));
  ck('three cheques, numbers 000451/452/453, a month apart', rows.length === 3 && rows.map(r => r.cheque_no).join() === '000451,000452,000453'
     && new Date(rows[1].date).getUTCMonth() === (new Date(rows[0].date).getUTCMonth() + 1) % 12, rows.map(r => [r.cheque_no, r.date]));
  await add('Desarch Scaffolding', '000470', plus(7), 24810.63, 'Scaffold hire');
  await add('SEOMAA Building', '000466', plus(-2), 48596.10, 'Cheque dated');
  await add('Uni Mix Block', '000480', plus(40), 3880.80);
  await add('Salary approx.', '', plus(20), 380000, 'Salaries - no cheque');
  let s = (await api(a, '/employees/pdc')).d.summary;
  ck('cards: 1 overdue (48,596.10), 1 due in 7 days, 1 in 8-14 days', s.overdue === 1 && s.overdue_amount === 48596.1 && s.week === 1 && s.fortnight === 1, s);
  const cards = await a.locator('#pdc-cards').textContent();
  ck('the cards show the overdue amount', /48,596\.10/.test(cards), cards);
  // Grid
  await a.fill('#pdc-from', plus(0).slice(0, 7)); await a.dispatchEvent('#pdc-from', 'change'); await a.waitForTimeout(1200);
  const g = await a.evaluate(() => PDC_GRID);
  const rent = g.rows.find(r => /Bin Bishr/.test(r.payee));
  ck('grid: one line per payee, rent 16,590 x 3 = 49,770 across the months', rent && rent.total === 49770 && rent.cells.filter(v => v === 16590).length >= 2, rent);
  ck('grid: the overdue SEOMAA cheque sits in an Overdue column', g.overdue === 48596.1 && g.rows.find(r => /SEOMAA/.test(r.payee)).overdue === 48596.1, g.overdue);
  const sumCells = g.rows.reduce((x, r) => x + r.total, 0);
  ck('grid: monthly totals and the grand total add up', Math.abs(g.grand - sumCells) < 0.01 && Math.abs(g.grand - (g.overdue + g.totals.reduce((x, y) => x + y, 0))) < 0.01, [g.grand, sumCells]);
  const dmy = isoD => { const d = new Date(isoD + 'T00:00:00Z'); return `${String(d.getUTCDate()).padStart(2, '0')}-${d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' })}-${String(d.getUTCFullYear()).slice(2)}`; };
  const rentLabel = dmy(plus(14)), seoLabel = dmy(plus(-2));
  const gtxt = await a.locator('#pdc-gbody').textContent();
  ck(`screen grid shows the exact cheque date and number under the figure (${rentLabel} #000451)`, gtxt.includes(rentLabel + ' #000451'), gtxt.slice(0, 400));
  ck('the overdue figure shows its date too', gtxt.includes(seoLabel + ' #000466'));
  await a.screenshot({ path: SH + 'pdc-1-grid.png', fullPage: true });
  // Clear / list
  const des = (await api(a, '/employees/pdc')).d.rows.find(r => /Desarch/.test(r.payee));
  await a.evaluate(() => pdcCard('week')); await a.waitForTimeout(500);
  ck('clicking "Due in 7 days" lists the Desarch cheque', /Desarch/.test(await a.locator('#pdc-lbody').textContent()));
  await a.screenshot({ path: SH + 'pdc-2-list.png', fullPage: true });
  await a.locator('#pdc-lbody tr', { hasText: 'Desarch' }).locator('button', { hasText: 'Cleared' }).click(); await a.waitForTimeout(1200);
  s = (await api(a, '/employees/pdc')).d.summary;
  ck('"Cleared" takes it off the reminders', s.week === 0, s);
  await a.evaluate(id => pdcEdit(id), des.id); await a.waitForTimeout(300);
  ck('clicking a cheque opens it for editing with its status', (await a.inputValue('#pdc-st')) === 'cleared' && (await a.locator('#pdc-del').isVisible()));
  await a.selectOption('#pdc-st', 'pending'); await a.click('#pdc-save'); await a.waitForTimeout(1200);
  ck('and it can be put back to pending', (await api(a, '/employees/pdc')).d.summary.week === 1);
  // Bell
  const n = (await api(a, '/notifications')).d.notifications.find(x => x.kind === 'pdc');
  ck('admin bell: one PDC line (overdue, 7 and 14 days)', n && /1 overdue/.test(n.title) && /7 days/.test(n.title) && /14 days/.test(n.title), n);
  ck('it pops up today - a cheque is overdue / at 14 or 7 days', n && n.id === 'pdc-' + plus(0), n && n.id);
  await a.evaluate(() => loadNotifications()); await a.waitForTimeout(800);
  ck('the Expiry Reminder badge includes the cheques due', (await badge(a)) >= 2, await badge(a));
  // Paper
  const [pop] = await Promise.all([a.waitForEvent('popup'), a.evaluate(() => pdcExport('view'))]);
  await pop.waitForLoadState(); await pop.waitForTimeout(700);
  const txt = await pop.locator('.page').textContent();
  ck('the paper: PDC TRACKER, payees, TOTAL (Monthly)', /PDC TRACKER/.test(txt) && /Bin Bishr/.test(txt) && /TOTAL \(Monthly\)/.test(txt) && /Overdue/i.test(txt));
  ck('the paper shows each exact cheque date and number', txt.includes(rentLabel + ' #000451') && txt.includes(seoLabel + ' #000466'));
  for (const fmt of ['pdf', 'excel']) {
    const href = await pop.locator(fmt === 'pdf' ? 'a:has-text("Download PDF")' : 'a:has-text("Excel")').getAttribute('href');
    require('fs').writeFileSync(`/tmp/claude-0/pdc-check.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`, Buffer.from(await pop.evaluate(async u => Array.from(new Uint8Array(await (await fetch(u)).arrayBuffer())), href)));
  }
  const { execSync } = require('child_process');
  const pdfTxt = execSync(`python3 -c "import pdfplumber;print(pdfplumber.open('/tmp/claude-0/pdc-check.pdf').pages[0].extract_text())"`).toString();
  ck('the PDF shows the exact dates', pdfTxt.includes(rentLabel + ' #000451') && pdfTxt.includes(seoLabel + ' #000466'), pdfTxt.slice(0, 300));
  const xl = execSync(`python3 -c "import openpyxl;ws=openpyxl.load_workbook('/tmp/claude-0/pdc-check.xlsx').active;print('|'.join(str(c.value) for r in ws.iter_rows() for c in r if c.value))"`).toString();
  ck('the Excel has a cheque-date line under each payee', xl.includes('cheque date') && xl.includes(rentLabel + ' #000451'), xl.slice(0, 300));
  await pop.screenshot({ path: SH + 'pdc-3-paper.png', fullPage: true });
  for (const sel of ['a:has-text("Download PDF")', 'a:has-text("Excel")']) {
    const href = await pop.locator(sel).getAttribute('href');
    const r = await pop.evaluate(async u => { const x = await fetch(u); return [x.status, (await x.arrayBuffer()).byteLength]; }, href);
    ck(`paper ${sel.match(/"(.*)"/)[1]} downloads`, r[0] === 200 && r[1] > 2000, r);
  }
  await pop.close();

  // ---- Chief accountant: PDCs only ------------------------------------------
  const c = await login('chiefacc', 'chief12345');
  ck('chief accountant: Expiry Reminder is in his menu', await c.locator('.pg-side .pg-item[data-page="expiry"]').isVisible());
  ck('he lands on PDCs, and sees no People / Company tabs', (await c.locator('#screen-pdc').isVisible()) && !(await subs(c)).some(x => /People|Company/.test(x)), await subs(c));
  ck('he sees the same cheques', (await c.evaluate(() => PDC && PDC.summary.overdue)) === 1);
  ck('his badge shows the cheques due', (await badge(c)) >= 2, await badge(c));
  ck('his bell has the PDC line', (await api(c, '/notifications')).d.notifications.some(x => x.kind === 'pdc'));
  ck('he cannot read the people documents', (await api(c, '/employees/expiry/summary')).status === 403);
  await c.screenshot({ path: SH + 'pdc-4-chief.png' });

  // ---- Documents-only login: no PDCs at all ----------------------------------
  const d = await login('docsonly', 'docs12345');
  ck('documents login: no PDCs tab', !(await subs(d)).includes('PDCs'), await subs(d));
  ck('PDC list refused', (await api(d, '/employees/pdc')).status === 403);
  ck('no PDC line in his bell', !(await api(d, '/notifications')).d.notifications.some(x => x.kind === 'pdc'));
  const dn = (await api(d, '/notifications')).d.notifications.find(x => x.kind === 'expiry');
  await d.evaluate(() => loadNotifications()); await d.waitForTimeout(600);
  ck('his badge counts documents only, no cheques', (await badge(d)) === (dn ? dn.count : 0), [await badge(d), dn && dn.count]);
  await d.goto(B + '/?p=expiry#expiry:pdc'); await d.waitForTimeout(3000);
  ck('typing #expiry:pdc does not show the PDC screen', !(await d.locator('#screen-pdc').isVisible()));

  // ---- Store keeper: nothing --------------------------------------------------
  const k = await login('amaltest', 'amal12345', '/?p=store');
  ck('store keeper: no Expiry Reminder in the menu', !(await k.locator('.pg-side .pg-item[data-page="expiry"]').isVisible()));
  const tok = await k.evaluate(async () => { await refreshDownloadToken(); return cachedDownloadToken; });
  const ex = await k.evaluate(async t => (await fetch(`/export/pdc?token=${encodeURIComponent(t)}&format=pdf`)).status, tok);
  ck('PDC paper refused to him (403)', ex === 403, ex);
  ck('no PDC line in his bell', !(await api(k, '/notifications')).d.notifications.some(x => x.kind === 'pdc'));

  const roles = (await api(a, '/permissions/roles')).d;
  ck('Access page: "PDC tracker" sits under Expiry Reminder', JSON.stringify(roles.pages.find(x => x[0] === 'Expiry Reminder')[1]) === '["expiry","pdc"]' && /PDC/.test(roles.labels.pdc));
  for (const p of [a, c, d, k]) ck('no script errors', p.errs.length === 0, p.errs);
  console.log(bad ? `${bad} FAILED` : 'PDCS ARE TRACKED AND KEPT PRIVATE');
  await b.close(); process.exit(bad ? 1 : 0);
})();
