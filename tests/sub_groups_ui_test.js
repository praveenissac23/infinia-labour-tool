// Items priced together as ONE lump sum (a bracket in the BOQ - 5 Nov 2026): the group's line carries the money and the %,
// its items are listed under it, indented and folding, never counted.
//   RAIDA915=/path/RAIDA_915_MEP_BOQ.xls /tmp/claude-0/run_on.sh <db after deploy/sub_raida_groups_2026_11_05.py> 8700 tests/sub_groups_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
const SH = process.env.SHOTS || '/tmp/claude-0/ui2/grp_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html'); await sleep(1500);
  if (await p.isVisible('#lg-u')) { await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); } await sleep(3000);
  const info = await p.evaluate(async () => { const m = await GET('/store/est/meta'); const pid = m.projects.find(x => x.code === '915').id; const pr = await GET('/store/est/projects/' + pid);
    const s = pr.subs.find(x => /RAIDA/i.test(x.name)); return { sid: s.id, pc2: s.pcs.find(x => x.seq === 2).id }; });
  const items = (await p.evaluate(sid => GET(`/store/est/subs/${sid}/items`), info.sid)).items;
  const san = items.find(x => x.grp === 'head' && /Sanitary Fittings/.test(x.description));
  const k = items.indexOf(san), kids = []; for (const x of items.slice(k + 1)) { if (x.grp !== 'in') break; kids.push(x); }
  ck('Sanitary: one group line, LS 10,800', san && san.amount === 10800 && san.unit === 'LS' && san.qty === 1, san);
  ck('... its 11 items listed under it, at nil', kids.length === 11 && kids.every(x => !x.amount && !x.rate) && kids[0].description === 'Clean Out, CO' && kids[10].description === 'Rain Water Outlet (RWO)', kids.map(x => x.description));
  const sum = (b) => Math.round(items.filter(x => x.bill === b).reduce((a, x) => a + x.amount, 0) * 100) / 100;
  ck('bill totals as before: HVAC 243,000 / Plumbing 153,000 / Electrical 184,500', sum('HVAC') === 243000 && sum('PLUMBING') === 153000 && sum('ELECTRICAL') === 184500, [sum('HVAC'), sum('PLUMBING'), sum('ELECTRICAL')]);
  // the certificate
  await p.evaluate(id => pcSheet(id), info.pc2); await sleep(2500);
  const row = p.locator(`tr[data-row="${san.id}"]`);
  ck('PC sheet: the group line with "11 items in this lump sum"', /11 items in this lump sum/.test(await row.textContent()));
  ck('... its 11 items under it, indented, with no figures to type', await p.locator(`tr.gin[data-gin="${san.id}"]`).count() === 11 && await p.locator(`tr.gin[data-gin="${san.id}"] input`).count() === 0);
  const summary = () => p.evaluate(() => [...document.querySelectorAll('table.rollsum tbody tr')].map(tr => [...tr.children].map(td => td.textContent.trim())));
  const s0 = await summary();
  ck('summary before: Plumbing to date 6,007.50, grand 8,487.00', s0[1][4] === '6,007.50' && s0[3][4] === '8,487.00', s0);
  const inp = row.locator('input[data-k="pct"]'); await inp.scrollIntoViewIfNeeded(); await inp.fill('10'); await sleep(400);
  ck('10% on the group = 1,080.00 on its line', (await p.textContent(`[data-amt="${san.id}"]`)).trim() === '1,080.00');
  const sub = await p.evaluate(id => { const tr = [...document.querySelectorAll('tr.rsub')].find(t => t.dataset.roll.split(',').includes(String(id))); return tr ? tr.querySelector('[data-rk="td"]').textContent.trim() : null; }, san.id);
  const tot = await p.evaluate(id => { const tr = [...document.querySelectorAll('tr.rtot')].find(t => t.dataset.roll.split(',').includes(String(id))); return tr.querySelector('[data-rk="td"]').textContent.trim(); }, san.id);
  const s1 = await summary();
  console.log('section subtotal', JSON.stringify(sub)); ck('... rolls up: Plumbing total 7,087.50, summary Plumbing 7,087.50, grand total 9,567.00', tot === '7,087.50' && s1[1][4] === '7,087.50' && s1[3][4] === '9,567.00', { sub, tot, s1 });
  ck('... the contract column unchanged (the items count once, in the group)', s1[1][1] === '153,000.00' && s1[3][1] === '580,500.00', s1);
  // alignment (5 Nov 2026 - kept from now on): every row of every bill table has exactly the table's columns; the
  // description column is readable (never squeezed to a word a line); no heading is cut off; figures right-aligned
  const al = await p.evaluate(() => [...document.querySelectorAll('#b-body table.sl')].map(t => {
    const n = t.querySelectorAll('colgroup col').length, hd = t.querySelectorAll('thead th').length;
    const bad = [...t.querySelectorAll('tbody tr')].filter(tr => [...tr.children].reduce((a, td) => a + (+td.colSpan || 1), 0) !== n).length;
    const dw = t.querySelector('thead th:nth-child(2)').getBoundingClientRect().width;
    const cut = [...t.querySelectorAll('thead th')].filter(th => th.scrollWidth > th.clientWidth + 1).map(th => th.textContent.trim());
    const figs = [...t.querySelectorAll('tbody tr:not(.sec) td.r')].filter(td => getComputedStyle(td).textAlign !== 'right').length;
    return { n, hd, bad, dw: Math.round(dw), cut, figs }; }));
  ck('alignment: every row of every bill table has exactly its columns', al.length && al.every(x => x.n === x.hd && x.bad === 0), al);
  ck('alignment: the description column is readable (at least 260px)', al.every(x => x.dw >= 260), al.map(x => x.dw));
  ck('alignment: the table fits its card - no sideways scroll at 1500px', await p.evaluate(() => [...document.querySelectorAll('#b-body table.sl')].every(t => t.offsetWidth <= t.closest('.tw').clientWidth + 1)));
  ck('alignment: no column heading cut off', al.every(x => !x.cut.length), al.map(x => x.cut));
  ck('alignment: figures right-aligned', al.every(x => !x.figs), al.map(x => x.figs));
  await row.scrollIntoViewIfNeeded(); await p.evaluate(() => document.querySelector('#b-body').scrollBy(0, -60)); await sleep(200);
  await p.screenshot({ path: SH + 'pc.png' });
  await p.click(`[data-gtog="${san.id}"]`); await sleep(200);
  ck('folding: the group\'s items hide and show', await p.locator(`tr.gin[data-gin="${san.id}"]:visible`).count() === 0);
  await p.click(`[data-gtog="${san.id}"]`); await sleep(200);
  ck('... and come back', await p.locator(`tr.gin[data-gin="${san.id}"]:visible`).count() === 11);
  await inp.fill('0'); await sleep(200); await p.keyboard.press('Escape'); await sleep(600);
  const leave = p.locator('button', { hasText: 'Leave without saving' }); if (await leave.count() && await leave.first().isVisible()) { await leave.first().click(); await sleep(600); }
  // the upload preview: groups and the review list
  if (process.env.RAIDA915) {
    await p.evaluate(sid => scheduleEditor(sid), info.sid); await sleep(2000);
    await p.setInputFiles('#it-up-f', process.env.RAIDA915); await sleep(6000);
    const t = await p.textContent('#m-body');
    ck('upload preview: the groups said, the items listed under them', /16 group\(s\) of items priced as one lump sum/.test(t) && await p.locator('#m-body tr.gin').count() === 118, (t.match(/\d+ group\(s\)[^.]*/) || [''])[0]);
    const g = p.locator('#m-body tr.ghd', { hasText: 'Sanitary Fittings' }); await g.scrollIntoViewIfNeeded(); await sleep(200);
    await p.screenshot({ path: SH + 'upload.png' });
  }
  ck('no page errors', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close(); })();
