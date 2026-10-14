// PPE register screen: opens from Reports > Labour, tiles, grid of workers x
// items, worker card, Give PPE with the too-soon warning and required reason,
// view-only login, help search, layout at 1440 / 1024 / 390.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + '/?p=reports'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); return p;
}
const open = async p => { await p.evaluate(() => { pgTab('labour'); }); await p.waitForTimeout(600); await p.evaluate(() => pgSub('ppe')); await p.waitForTimeout(2200); };
const tiles = p => p.evaluate(() => [...document.querySelectorAll('#pe-tiles .pe-tile')].map(x => x.querySelector('b').textContent));
(async () => {
  const b = await chromium.launch();
  const a = await login(b, 'amal', 'pass12345');
  await a.evaluate(() => pgTab('labour')); await a.waitForTimeout(800);
  ck('Reports > Labour shows the PPE tab', (await a.locator('text=PPE').count()) >= 1);
  await open(a);
  ck('screen opens', await a.locator('#screen-ppe').isVisible());
  const t0 = await tiles(a);
  ck('5 tiles', t0.length === 5, t0);
  const rows = await a.locator('#pe-body tr.pe-row').count();
  ck('grid lists the workers from the sheet', rows > 50, rows);
  ck('cells coloured by state', (await a.locator('#pe-body .pe-s-old').count()) > 0 && (await a.locator('#pe-body .pe-s-mid, #pe-body .pe-s-recent').count()) > 0);
  ck('recent issues listed', (await a.locator('#pe-recent .pe-li').count()) > 5);
  ck('Preview / PDF / Excel / Share buttons', (await a.locator('#screen-ppe .exp-btns .btn').count()) === 4);
  await a.screenshot({ path: SH + 'ppe_1440_full.png', fullPage: true });
  // search by ID without the dash
  const pick = await a.evaluate(() => { const w = PE.workers.find(w => w.emp_id && w.cells['Safety Shoes'].last); return w && { no: w.no, key: w.key, id: w.emp_id }; });
  ck('a worker given shoes exists in the sheet data', !!pick, pick);
  ck('no limits or due dates on the screen', !/limit|due /i.test(await a.locator('#pe-head').textContent() + await a.locator('#pe-body').textContent()));
  ck('cells say how long ago', /ago|today/.test(await a.locator('#pe-body').textContent()));
  await a.fill('#pe-q', pick.no.replace('-', '')); await a.waitForTimeout(300);
  ck('search without the dash finds him', (await a.locator('#pe-body tr.pe-row').count()) === 1);
  await a.click('#pe-body tr.pe-row'); await a.waitForTimeout(1200);
  ck('worker card shows the history', (await a.locator('.pe-m .pe-hist tr').count()) >= 1 && /ago|today/.test(await a.locator('.pe-m .pe-sum').textContent()));
  await a.screenshot({ path: SH + 'ppe_card.png' });
  // give shoes: shows when last given, nothing required
  await a.click('.pe-m .btn-primary >> text=+ Give PPE'); await a.waitForTimeout(900);
  await a.click('#pe-its button[data-it="Safety Shoes"]'); await a.waitForTimeout(900);
  ck('shows when he last had shoes and how long ago', /Last safety shoes given on .* (ago|today)/.test(await a.locator('#pe-chk').textContent()), await a.locator('#pe-chk').textContent());
  ck('no reason box', !(await a.locator('#pe-why').count()));
  await a.click('#pe-save'); await a.waitForTimeout(1800);
  ck('saved', /^Saved\.?$/.test((await a.locator('#pe-status').textContent()).trim()));
  const t1 = await tiles(a);
  ck('Given this month went up by one', +t1[0] === +t0[0] + 1, [t0, t1]);
  ck('his shoes cell now red - given today', await a.locator('#pe-body tr.pe-row').first().locator('.pe-s-recent').count() >= 1);
  // asked again the same day: flagged, not blocked
  await a.evaluate(id => ppeGive(id), pick.id); await a.waitForTimeout(800);
  await a.click('#pe-its button[data-it="Safety Shoes"]'); await a.waitForTimeout(900);
  ck('asked again: "Given recently ... today" shown', /Given recently.*today/.test(await a.locator('#pe-chk').textContent()));
  await a.screenshot({ path: SH + 'ppe_give_recent.png' });
  await a.click('.pe-m .btn-gray >> text=Cancel');
  await a.fill('#pe-q', ''); await a.waitForTimeout(200);
  // stock dialog
  await a.click('#pe-stockbtn'); await a.waitForTimeout(300);
  await a.selectOption('#pe-si', 'Helmet'); await a.fill('#pe-sc', '20'); await a.click('.pe-m .btn-primary'); await a.waitForTimeout(1500);
  ck('stock counted', /Helmet\s*20/.test(await a.locator('#pe-stock').textContent()), await a.locator('#pe-stock').textContent());
  // layout at three widths
  for (const W of [1440, 1024, 390]) {
    const p = W === 1440 ? a : await login(b, 'jomon', 'pass12345', W);
    if (W !== 1440) await open(p);
    const lay = await p.evaluate(() => {
      const out = [];
      if (document.documentElement.scrollWidth > innerWidth + 2) out.push('page scrolls sideways');
      document.querySelectorAll('#screen-ppe .pe-tile, #screen-ppe .pe-panel').forEach(el => { if (el.scrollWidth > el.clientWidth + 2) out.push('spills: ' + el.textContent.slice(0, 30)); });
      document.querySelectorAll('#screen-ppe button').forEach(el => { if (el.offsetParent && el.getBoundingClientRect().right > innerWidth + 1) out.push('off screen: ' + el.textContent.slice(0, 20)); });
      return out;
    });
    ck(`layout clean at ${W}`, lay.length === 0, lay);
    await p.evaluate(() => scrollTo(0, 0)); await p.waitForTimeout(200);
    await p.screenshot({ path: SH + `ppe_${W}.png`, fullPage: W !== 1440 });
    if (p.errs.length) ck(`no page errors at ${W}`, false, p.errs);
  }
  // view-only
  const v = await login(b, 'assistant', 'pass12345');
  await open(v);
  ck('viewer sees the register', (await v.locator('#pe-body tr.pe-row').count()) > 50);
  ck('viewer has no Give / Count buttons', !(await v.locator('#pe-give').isVisible()) && !(await v.locator('#pe-stockbtn').isVisible()));
  const r = await v.evaluate(async () => { try { await apiCall('/store/ppe', { method: 'POST', body: JSON.stringify({ employee_id: 1, item: 'Helmet' }) }); return 'done'; } catch (e) { return errText(e); } });
  ck('viewer cannot add even directly', r !== 'done', r);
  // help search
  for (const w of ['uniform', 'shoes']) {
    await v.fill('#help-search', ''); await v.type('#help-search', w); await v.waitForTimeout(500);
    const hs = await v.evaluate(() => [...document.querySelectorAll('#help-results > *')].map(x => x.textContent.trim()).join(' | '));
    ck(`help search "${w}" finds the PPE guides`, /PPE/i.test(hs), hs.slice(0, 200));
  }
  ck('no page errors', !a.errs.length && !v.errs.length, [...a.errs, ...v.errs]);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await b.close();
})();
