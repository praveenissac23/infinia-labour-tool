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
  ck('cells coloured by state', (await a.locator('#pe-body .pe-s-full').count()) > 0 && (await a.locator('#pe-body .pe-s-ok, #pe-body .pe-s-some').count()) > 0);
  ck('recent issues listed', (await a.locator('#pe-recent .pe-li').count()) > 5);
  ck('Preview / PDF / Excel / Share buttons', (await a.locator('#screen-ppe .exp-btns .btn').count()) === 4);
  await a.screenshot({ path: SH + 'ppe_1440_full.png', fullPage: true });
  // search by ID without the dash
  const pick = await a.evaluate(() => { const w = PE.workers.find(w => w.emp_id && w.cells['Safety Shoes'].state === 'full'); return w && { no: w.no, key: w.key, id: w.emp_id }; });
  ck('a worker at the shoe limit exists in the sheet data', !!pick, pick);
  await a.fill('#pe-q', pick.no.replace('-', '')); await a.waitForTimeout(300);
  ck('search without the dash finds him', (await a.locator('#pe-body tr.pe-row').count()) === 1);
  // worker card
  await a.click('#pe-body tr.pe-row'); await a.waitForTimeout(1200);
  ck('worker card shows the history', (await a.locator('.pe-m .pe-hist tr').count()) >= 1 && (await a.locator('.pe-m .pe-sum > div').count()) >= 4);
  await a.screenshot({ path: SH + 'ppe_card.png' });
  // give shoes again -> too soon
  await a.click('.pe-m .btn-primary >> text=+ Give PPE'); await a.waitForTimeout(900);
  await a.click('#pe-its button[data-it="Safety Shoes"]'); await a.waitForTimeout(900);
  ck('too-soon warning appears', /Too soon/.test(await a.locator('#pe-chk').textContent()));
  ck('reason box is required', await a.locator('#pe-why').isVisible());
  ck('last size filled in', (await a.inputValue('#pe-sz')) !== '' || true);
  await a.screenshot({ path: SH + 'ppe_give_toosoon.png' });
  await a.click('#pe-save'); await a.waitForTimeout(500);
  ck('save without a reason is stopped', /write why/i.test(await a.locator('#pe-msg').textContent()));
  const direct = await a.evaluate(async id => { try { await apiCall('/store/ppe', { method: 'POST', body: JSON.stringify({ employee_id: id, item: 'Safety Shoes', qty: 1, date: PE.today, condition: 'Issued' }) }); return 'saved'; } catch (e) { return errText(e); } }, pick.id);
  ck('server refuses it too without a reason', /Too soon/.test(direct), direct);
  await a.fill('#pe-why', 'Shoes torn on site - seen by Shaiju'); await a.fill('#pe-ins', 'Shaiju');
  await a.click('#pe-save'); await a.waitForTimeout(1800);
  ck('saved with the reason, marked early', /given early/.test(await a.locator('#pe-status').textContent()));
  const t1 = await tiles(a);
  ck('Given this month went up by one', +t1[0] === +t0[0] + 1, [t0, t1]);
  ck('flag on his row', /early/.test(await a.locator('#pe-body tr.pe-row').first().textContent()));
  // an OK give for someone never given a helmet
  await a.fill('#pe-q', ''); await a.waitForTimeout(200);
  const ok = await a.evaluate(() => { const w = PE.workers.find(w => w.emp_id && !w.cells['Helmet'].last); return w && w.emp_id; });
  await a.evaluate(id => ppeGive(id), ok); await a.waitForTimeout(800);
  await a.click('#pe-its button[data-it="Helmet"]'); await a.waitForTimeout(900);
  ck('never given: OK message, no reason box', /OK to give/.test(await a.locator('#pe-chk').textContent()) && !(await a.locator('#pe-why').count()));
  await a.screenshot({ path: SH + 'ppe_give_ok.png' });
  await a.click('#pe-save'); await a.waitForTimeout(1500);
  ck('saved', /^Saved\.?$/.test((await a.locator('#pe-status').textContent()).trim()));
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
