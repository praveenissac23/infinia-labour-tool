// Tables everywhere: click a heading to sort (totals and brought-forward
// stay put), drag a heading to move the column, the order is remembered
// after the screen is drawn again and after a reload.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 950 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.dismiss());
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  const openPetty = async () => { await p.evaluate(() => { pgGo('accounts', 'petty:site'); pgTab('petty'); pgSub('site'); }); await p.waitForTimeout(1200);
    await p.evaluate(() => { document.getElementById('pc-from').value = '2026-10-01'; document.getElementById('pc-to').value = '2026-10-31'; return loadPettyCash(); }); await p.waitForTimeout(1200); };
  await openPetty();
  const heads = () => p.evaluate(() => [...document.querySelectorAll('#pc-head-row th')].map(t => t.textContent.replace(/[▲▼]/g, '').trim()));
  const col = name => p.evaluate(n => { const hs = [...document.querySelectorAll('#pc-head-row th')].map(t => t.textContent.replace(/[▲▼]/g, '').trim()); const i = hs.indexOf(n);
    return [...document.querySelectorAll('#pc-body tr')].filter(r => r.cells.length === hs.length && !r.classList.contains('bf')).map(r => r.cells[i].textContent.trim()); }, name);
  const h0 = await heads();
  ck('petty cash headings are sortable', await p.locator('#pc-head-row th.tx-s').count() >= 4, await p.locator('#pc-head-row th.tx-s').count());
  // sort by Paid, descending after two clicks
  const paidTh = p.locator('#pc-head-row th', { hasText: 'Paid (AED)' });
  await paidTh.click(); await p.waitForTimeout(200); await paidTh.click(); await p.waitForTimeout(200);
  const paid = (await col('Paid (AED)')).map(v => parseFloat(v.replace(/[^0-9.]/g, '')) || 0);
  ck('click twice: Paid largest first', paid.length > 2 && paid.every((v, i) => !i || paid[i - 1] >= v), paid.slice(0, 6));
  ck('brought forward stays the first row', /brought forward/i.test(await p.locator('#pc-body tr').first().textContent()));
  ck('arrow shows the sort', /▼/.test(await paidTh.textContent()));
  // drag Description to the first place
  await p.dragAndDrop('#pc-head-row th:nth-child(2)', '#pc-head-row th:nth-child(1)'); await p.waitForTimeout(300);
  const h1 = await heads();
  ck('dragged Description to the front', h1[0] === 'Description' && h1[1] === 'Date', h1);
  const row = await p.evaluate(() => { const r = [...document.querySelectorAll('#pc-body tr')].find(r => !r.classList.contains('bf') && r.cells.length > 4); return [r.cells[0].textContent.trim(), r.cells[1].textContent.trim()]; });
  ck('the cells moved with the heading', !/^\d{2}-[A-Z][a-z]{2}-\d{2}$/.test(row[0]) && /^\d{2}-[A-Z][a-z]{2}-\d{2}$/.test(row[1]), row);
  // the screen draws itself again: order kept
  await p.evaluate(() => loadPettyCash()); await p.waitForTimeout(1200);
  ck('order kept when the screen is drawn again', (await heads())[0] === 'Description', await heads());
  const dateCol = async () => { const hs = await heads(); const d = await col('Date'); return { at: hs.indexOf('Date'), ok: d.length > 0 && d.every(v => /^\d{2}-[A-Z][a-z]{2}-\d{2}$/.test(v)), d: d.slice(0, 3) }; };
  let dc = await dateCol(); ck('after a redraw every row lines up under its heading', dc.ok && dc.at === 1, dc);
  await p.reload(); await p.waitForTimeout(3500); await openPetty();
  ck('order kept after a reload', (await heads())[0] === 'Description', await heads());
  dc = await dateCol(); ck('after a reload every row lines up under its heading', dc.ok && dc.at === 1, dc);
  await p.evaluate(() => loadPettyCash()); await p.waitForTimeout(1200);
  dc = await dateCol(); ck('and after another redraw', dc.ok && dc.at === 1, dc);
  await p.screenshot({ path: SH + 'table_dragged.png' });
  // put it back
  await p.dragAndDrop('#pc-head-row th:nth-child(2)', '#pc-head-row th:nth-child(1)'); await p.waitForTimeout(300);
  ck('dragged back', JSON.stringify(await heads()) === JSON.stringify(h0), await heads());
  // stock table sorts too
  await p.evaluate(() => { pgGo('store', 'store:home'); pgTab('store'); }); await p.waitForTimeout(2500);
  const st = await p.evaluate(() => document.querySelectorAll('.screen.active th.tx-s').length);
  ck('store stock table is sortable', st > 2, st);
  // a heading with its own sort is left alone (master data)
  await p.evaluate(() => { pgGo('attendance', 'masterdata'); pgTab('masterdata'); }); await p.waitForTimeout(2000);
  ck('headings that sort themselves are untouched', await p.evaluate(() => [...document.querySelectorAll('th.sortable')].every(t => !t.classList.contains('tx-s'))));
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await b.close();
})();
