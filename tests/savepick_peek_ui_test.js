// 5 Nov 2026 (Arun, purchase - for the whole app):
//  - every download opens the Save-as window, in the folder last saved to (portal/help/savepick.js)
//  - every share offers WhatsApp app / WhatsApp Web
//  - Order tracker: the LPO number opens the LPO in a window over the tracker
//   /tmp/claude-0/run_on.sh /tmp/claude-0/roles.db 8580 tests/savepick_peek_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const OUT = process.env.SHOTS || '/tmp/claude-0/ui2';
(async () => { const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1500, height: 900 } });
  // the browser's Save-as window, stood in for: records what it was asked, "saves" straight away
  await ctx.addInitScript(() => {
    window.__saves = [];
    window.showSaveFilePicker = async (o) => { const rec = { name: o.suggestedName, id: o.id, types: o.types }; window.__saves.push(rec);
      return { createWritable: async () => ({ write: async b => { rec.size = b.size; rec.type = b.type; }, close: async () => { rec.closed = true; } }) }; };
  });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  const popups = [];   // pages opened (WhatsApp Web stood in for - no internet here)
  await ctx.route('https://web.whatsapp.com/**', r => { popups.push(r.request().url()); r.fulfill({ status: 200, contentType: 'text/html', body: 'wa' }); });
  ctx.on('page', pg => { setTimeout(() => { if (!/whatsapp/.test(pg.url())) popups.push(pg.url()); }, 300); });
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  ck('the Save-as script is on the app page', await p.evaluate(() => !!window.__infSavePick));

  // ---- Order tracker: the LPO number opens the LPO over the tracker
  await p.evaluate(() => pgGo('store', 'tracker')); await sleep(3000);
  await p.evaluate(() => { OT_VIEW = 'all'; OT_STEP = null; otRender(); });
  const row = await p.evaluate(() => { const r = OT.rows.find(x => x.kind === 'lpo' && x.id && x.supplier); return r && { key: r.key, id: r.id, ref: r.ref, sup: r.supplier }; });
  ck('an LPO row to look at', !!row, row);
  ck('without a search the LPO number is a link too', await p.evaluate(k => !!document.querySelector(`#ot-body tr[data-k="${k}"] a.ot-peek`), row.key));
  await p.fill('#ot-search', row.sup.split(/\s+/)[0]); await sleep(500);
  const link = p.locator(`#ot-body tr[data-k="${row.key}"] .ot-lpo a.ot-peek`);
  ck('searching: the highlighted LPO number is a link', await link.count() === 1);
  await link.click(); await sleep(2500);
  ck('the LPO opens in a window over the tracker', await p.isVisible('#ot-peek .otp-box'));
  ck('the tracker sheet did not open (just the LPO)', await p.evaluate(() => !document.querySelector('.ot-sheet.on, #ot-sheet.on')));
  const fr = p.frame({ url: /\/export\/purchase\/\d+\/view/ });
  ck('it shows the LPO itself', !!fr && (await fr.textContent('body')).includes(row.ref), fr && fr.url());
  ck('its title is the LPO number', (await p.textContent('#otp-title')) === row.ref);
  ck('the tracker is still in view behind it', await p.evaluate(() => { const r = document.querySelector('#ot-peek .otp-box').getBoundingClientRect(); return r.left > 300; }));
  await p.screenshot({ path: OUT + '/ot_peek.png' });
  await p.keyboard.press('Escape'); await sleep(300);
  ck('Esc closes it', !(await p.isVisible('#ot-peek .otp-box')));
  await link.click(); await sleep(800); await p.mouse.click(60, 450); await sleep(300);
  ck('a tap outside closes it', !(await p.isVisible('#ot-peek .otp-box')));
  await p.fill('#ot-search', ''); await sleep(300);

  // ---- Downloads: the Save-as window, in the folder last used
  await p.evaluate(id => downloadLpo(id, 'pdf'), row.id); await sleep(3000);
  let s = await p.evaluate(() => window.__saves.slice());
  ck('LPO PDF download opens the Save-as window', s.length === 1 && /\.pdf$/i.test(s[0].name) && s[0].closed && s[0].size > 500, s);
  ck('... asked to open in the folder last saved to (one id for the app)', s[0] && s[0].id === 'infinia-files', s[0]);
  ck('... with the file name from the server', s[0] && !/^download/.test(s[0].name), s[0]);
  await p.evaluate(() => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['a,b\n1,2'], { type: 'text/csv' })); a.download = 'Test list.csv'; a.click(); }); await sleep(800);
  s = await p.evaluate(() => window.__saves.slice());
  ck('a file made on the page (Excel / CSV) also opens the Save-as window', s.length === 2 && s[1].name === 'Test list.csv' && s[1].size === 7, s[1]);
  await p.evaluate(id => { const a = document.createElement('a'); a.href = `/export/purchase/${id}?token=${encodeURIComponent(cachedDownloadToken)}&format=excel`; a.textContent = 'x'; a.id = 'tst-x'; document.body.appendChild(a); }, row.id);
  await p.click('#tst-x'); await sleep(2500);
  s = await p.evaluate(() => window.__saves.slice());
  ck('an export link clicked opens the Save-as window', s.length === 3 && /\.xlsx$/i.test(s[2].name), s[2]);
  // a PDF the server shows (not downloads) still opens in a tab
  await p.route('**/export/fake/view-pdf*', r => r.fulfill({ status: 200, contentType: 'application/pdf', headers: { 'content-disposition': 'inline; filename="x.pdf"' }, body: '%PDF-1.4 x' }));
  const n0 = popups.length;
  await p.evaluate(() => window.open('/export/fake/view-pdf?format=pdf', '_blank')); await sleep(1500);
  ck('a PDF that is shown, not downloaded, still opens in a tab', popups.length === n0 + 1 && (await p.evaluate(() => window.__saves.length)) === 3, popups.slice(n0));

  // ---- WhatsApp: app or Web
  await p.evaluate(() => window.open('https://wa.me/971501234567?text=' + encodeURIComponent('LPO 123'), '_blank')); await sleep(400);
  ck('WhatsApp link: asks WhatsApp app / WhatsApp Web', await p.evaluate(() => { const t = (document.querySelector('.isp-box') || {}).textContent || ''; return /WhatsApp app/.test(t) && /WhatsApp Web/.test(t); }));
  await p.screenshot({ path: OUT + '/wa_choice.png' });
  const n1 = popups.length;
  await p.click('.isp-box .isp-b:has-text("WhatsApp Web")'); await sleep(1200);
  ck('WhatsApp Web opens web.whatsapp.com with the number and the text', popups.length === n1 + 1 && /web\.whatsapp\.com\/send\?phone=971501234567&text=LPO/.test(popups[n1]), popups.slice(n1));
  // the share button (system share) - the LPO preview page has one
  const vp = await ctx.newPage(); vp.on('pageerror', e => errs.push('view: ' + e.message));
  await vp.goto(await p.evaluate(id => `${API}/export/purchase/${id}/view?token=${encodeURIComponent(cachedDownloadToken)}`, row.id)); await sleep(1200);
  ck('the Save-as script is on the server-made pages too', await vp.evaluate(() => !!window.__infSavePick));
  const shareBtn = await vp.$('#wa-share, #pv-share');
  ck('the LPO page has its share button', !!shareBtn);
  if (shareBtn) {
    await shareBtn.click(); await sleep(2000);
    const t = await vp.evaluate(() => (document.querySelector('.isp-box') || {}).textContent || '');
    ck('Share: WhatsApp app, WhatsApp Web and Save are offered', /WhatsApp app/.test(t) && /WhatsApp Web/.test(t) && /Save the file/.test(t), t);
    await vp.screenshot({ path: OUT + '/share_choice.png' });
    const n2 = popups.length;
    await vp.click('.isp-box .isp-b:has-text("WhatsApp Web")'); await sleep(1200);
    ck('WhatsApp Web opens, and the PDF is ready to save and attach', popups.slice(n2).some(u => /web\.whatsapp\.com/.test(u)) && await vp.isVisible('.isp-toast .go'), popups.slice(n2));
    await vp.click('.isp-toast .go'); await sleep(800);
    const vs = await vp.evaluate(() => window.__saves.slice());
    ck('... Save puts the PDF where they choose', vs.length === 1 && /\.pdf$/i.test(vs[0].name) && vs[0].size > 500, vs);
    await shareBtn.click(); await sleep(2000);
    await vp.click('.isp-box .isp-b:has-text("WhatsApp app")'); await sleep(800);
    ck('WhatsApp app (computer without the system share): WhatsApp opens and the PDF is in Downloads', /Downloads/.test(await vp.textContent('.isp-toast')));
    await vp.screenshot({ path: OUT + '/share_app.png', clip: { x: 300, y: 600, width: 900, height: 300 } });
  }
  ck('no page errors', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close(); })();
