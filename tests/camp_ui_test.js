// Labour accommodation screen: opens from Reports > Labour, counts, filters,
// search, put / move / book / free from the bed dialog, view-only login,
// layout at 1440 / 1024 / 390.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + '/?p=reports'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); return p;
}
const open = async p => { await p.evaluate(() => { pgTab('labour'); }); await p.waitForTimeout(600); await p.evaluate(() => pgSub('accom')); await p.waitForTimeout(1800); };
const tiles = p => p.evaluate(() => [...document.querySelectorAll('#cp-tiles .cp-tile')].map(x => x.querySelector('b').textContent));
(async () => {
  const b = await chromium.launch();
  const c = await login(b, 'shafiq', 'pass12345');
  await c.evaluate(() => pgTab('labour')); await c.waitForTimeout(800); const subs = await c.locator('text=Accommodation').count();
  ck('Reports > Labour shows the Accommodation tab', subs >= 1, subs);
  await open(c);
  ck('screen opens', await c.locator('#screen-camp').isVisible());
  const t0 = await tiles(c);
  ck('counts: 90 beds, 16 free on the 9 Oct sheet (less any on the copy who left)', t0[0] === '90' && +t0[4] >= 16, t0);
  ck('15 room cards', (await c.locator('#cp-grid .cp-room').count()) === 15);
  await c.screenshot({ path: SH + 'camp_1440.png' });
  // filter: free only
  await c.click('#cp-tiles .t-free'); await c.waitForTimeout(300);
  const shown = await c.locator('#cp-grid .cp-room').count();
  ck('Free beds filter shows only rooms with a free bed', shown > 0 && shown < 15, shown);
  await c.click('#cp-tiles .cp-tile >> nth=0'); await c.waitForTimeout(200);
  // search by ID without the dash
  await c.fill('#cp-q', 'F757'); await c.waitForTimeout(300);
  ck('search F757 finds his room', (await c.locator('#cp-grid .cp-room').count()) === 1 && (await c.locator('#cp-grid .cp-bed.hit').count()) === 1);
  await c.fill('#cp-q', ''); await c.waitForTimeout(200);
  // put someone into room 49's first free bed
  const freeBtn = c.locator('#cp-grid .cp-room').first().locator('.cp-bed.free').first();
  await freeBtn.click(); await c.waitForTimeout(400);
  ck('free bed dialog offers put / book / guest', (await c.locator('.cp-m .cp-acts .btn').count()) === 3);
  await c.screenshot({ path: SH + 'camp_dialog_free.png' });
  await c.click('.cp-m .cp-acts .btn >> nth=0'); await c.waitForTimeout(900);
  await c.fill('#cp-pq', 'SHAILENDRA'); await c.waitForTimeout(300);
  const pick = c.locator('#cp-plist .btn').first();
  ck('staff list search in the picker', await pick.count() === 1);
  await c.screenshot({ path: SH + 'camp_dialog_pick.png' });
  await pick.click(); await c.waitForTimeout(1500);
  const t1 = await tiles(c);
  ck('after putting him: one free bed fewer', +t1[4] === +t0[4] - 1, [t0, t1]);
  ck('success message', /given the bed|moved/.test(await c.locator('#cp-status').textContent()));
  // book a bed for a new joiner
  await c.click('#cp-bookbtn'); await c.waitForTimeout(300);
  await c.fill('#cp-bn', 'Rakesh Kumar'); await c.fill('#cp-bt', 'Mason'); await c.fill('#cp-bd', '2026-10-20');
  await c.screenshot({ path: SH + 'camp_dialog_book.png' });
  await c.click('.cp-m .btn-primary'); await c.waitForTimeout(1500);
  const t2 = await tiles(c);
  ck('booked: Booked 1, free one fewer', t2[3] === '1' && +t2[4] === +t1[4] - 1, t2);
  ck('booked bed shows the tag', await c.locator('#cp-grid .cp-tag.cp-book').count() === 1);
  // vacation bed dialog (read-only info + history)
  const vac = c.locator('#cp-grid .cp-bed.vac').first();
  if (await vac.count()) { await vac.click(); await c.waitForTimeout(900); ck('vacation bed explains the bed stays his', /stays his/.test(await c.locator('.cp-m').textContent())); await c.screenshot({ path: SH + 'camp_dialog_vac.png' }); await c.click('.cp-m .btn-gray >> text=Close'); }
  // move someone
  const occ = c.locator('#cp-grid .cp-bed.in').first(); await occ.click(); await c.waitForTimeout(700);
  await c.click('.cp-m .btn >> text=Move to another bed'); await c.waitForTimeout(300);
  await c.click('.cp-m .btn-primary >> nth=0'); await c.waitForTimeout(1500);
  const t3 = await tiles(c);
  ck('move keeps the same number of free beds', t3[4] === t2[4], [t2, t3]);
  // overflow / layout checks at three widths
  for (const W of [1440, 1024, 390]) {
    const p = W === 1440 ? c : await login(b, 'shafiq', 'pass12345', W);
    if (W !== 1440) await open(p);
    const lay = await p.evaluate(() => {
      const out = [];
      if (document.documentElement.scrollWidth > innerWidth + 2) out.push('page scrolls sideways');
      document.querySelectorAll('#screen-camp .cp-room, #screen-camp .cp-tile').forEach(el => { if (el.scrollWidth > el.clientWidth + 2) out.push('spills: ' + el.textContent.slice(0, 30)); });
      document.querySelectorAll('#screen-camp button').forEach(el => { if (el.getBoundingClientRect().right > innerWidth + 1 && el.offsetParent) out.push('off screen: ' + el.textContent.slice(0, 20)); });
      return out;
    });
    ck(`layout clean at ${W}`, lay.length === 0, lay);
    await p.screenshot({ path: SH + `camp_${W}.png`, fullPage: false });
    if (p.errs.length) ck(`no page errors at ${W}`, false, p.errs);
  }
  // view-only login
  const v = await login(b, 'muhsina', 'pass12345');
  await open(v);
  ck('viewer sees the camp', await v.locator('#cp-grid .cp-room').count() >= 15);
  ck('viewer has no Book / Rooms buttons', !(await v.locator('#cp-bookbtn').isVisible()) && !(await v.locator('#cp-roombtn').isVisible()));
  ck('viewer: free beds have no "Put someone"', (await v.locator('#cp-grid .cp-add').count()) === 0);
  const r = await v.evaluate(async () => { try { await apiCall('/store/camp/free', { method: 'POST', body: JSON.stringify({ room_id: 1, bed: 2 }) }); return 'done'; } catch (e) { return errText(e); } });
  ck('viewer cannot change it even directly', /PRO|chief accountant|store keeper/.test(r), r);
  // help search
  await v.fill('#help-search', ''); await v.type('#help-search', 'accommodation'); await v.waitForTimeout(500);
  const hs = await v.evaluate(() => [...document.querySelectorAll('#help-results > *')].map(x => x.textContent.trim()).join(' | '));
  ck('search "accommodation" finds the camp guides', /camp bed|labour camp/i.test(hs), hs);
  ck('no page errors', !c.errs.length && !v.errs.length, [...c.errs, ...v.errs]);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await b.close();
})();
