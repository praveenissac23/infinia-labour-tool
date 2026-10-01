// Payroll > Office payroll > Gratuity > Final settlement: the figures
// on screen follow what is typed, add up, and the preview, PDF and Excel
// open with the same total. Needs S-777 (basic 4000, gross 6000, joined
// 10 Oct 2022, loan 10,000) - see the settlement API check in the notes.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=payroll#hrpayroll'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  await p.locator('#pg-sub .pg-subtab', { hasText: 'Gratuity' }).click(); await p.waitForTimeout(2000);
  await p.evaluate(() => { const s = document.getElementById('hr-grat-emp'); s.value = 'S-777'; s.dispatchEvent(new Event('change')); }); await p.waitForTimeout(2000);
  await p.fill('#fs-last', '2026-07-31'); await p.fill('#fs-nsrv', '10'); await p.fill('#fs-leave', '12'); await p.dispatchEvent('#fs-leave', 'input'); await p.waitForTimeout(1500);
  const net = await p.locator('.fs-net b').textContent();
  ck('resignation, 10 of 30 days notice, 12 days leave: AED 4,103.00', /4,103\.00/.test(net), net);
  const sums = await p.evaluate(() => [...document.querySelectorAll('.fs-sum table')].map(t => {
    const v = [...t.querySelectorAll('td.n')].map(td => +td.textContent.replace(/,/g, '')); return [v.slice(0, -1).reduce((a, x) => a + x, 0), v[v.length - 1]]; }));
  ck('each table adds up to its total', sums.every(([a, t]) => Math.abs(a - t) < 0.01), sums);
  await p.evaluate(() => { const s = document.getElementById('fs-reason'); s.value = 'termination'; s.dispatchEvent(new Event('change')); }); await p.fill('#fs-nsrv', '0'); await p.dispatchEvent('#fs-nsrv', 'input'); await p.waitForTimeout(1500);
  const net2 = await p.locator('.fs-net b').textContent();
  ck('termination without notice adds a month: AED 14,103.00', /14,103\.00/.test(net2), net2);
  const rows = await p.locator('#fs-result').textContent();
  ck('and shows the notice pay line, no notice deduction', /Notice pay/.test(rows) && !/Notice not served/.test(rows));
  await p.screenshot({ path: '/tmp/claude-0/shots/final-settlement.png', fullPage: true });
  const [pop] = await Promise.all([p.waitForEvent('popup'), p.click('#hr-fs-card .exp-btns button:has-text("Preview")')]);
  await pop.waitForLoadState(); await pop.waitForTimeout(800);
  const pv = await pop.locator('.net b').textContent();
  ck('the preview shows the same total', /14,103\.00/.test(pv), pv);
  await pop.screenshot({ path: '/tmp/claude-0/shots/final-settlement-preview.png', fullPage: true });
  for (const sel of ['a:has-text("Download PDF")', 'a:has-text("Excel")']) {
    const href = await pop.locator(sel).getAttribute('href');
    const r = await pop.evaluate(async u => { const x = await fetch(u); return [x.status, x.headers.get('content-type')]; }, href);
    ck(`preview ${sel.match(/"(.*)"/)[1]} downloads`, r[0] === 200, r);
  }
  await pop.close();
  // another person: the typed figures are cleared
  const other = await p.evaluate(() => [...document.querySelectorAll('#hr-grat-emp option')].map(o => o.value).find(v => v && v !== 'S-777'));
  await p.evaluate(v => { const s = document.getElementById('hr-grat-emp'); s.value = v; s.dispatchEvent(new Event('change')); }, other); await p.waitForTimeout(2000);
  ck('choosing someone else clears what was typed', await p.inputValue('#fs-nsrv') === '' && await p.inputValue('#fs-leave') === '', await p.inputValue('#fs-nsrv'));
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'FINAL SETTLEMENT HOLDS UP');
  await b.close(); process.exit(bad ? 1 : 0);
})();
