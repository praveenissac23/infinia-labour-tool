// Accounts > Bank: Show one month, one day, or from - to; the list, totals and the paper follow it.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'shafiq'); await p.fill('#login-password', 'pass12345'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Bank'); t.click(); }); await p.waitForTimeout(2500);
  for (const [d, a] of [['2026-10-04', '100'], ['2026-10-05', '200'], ['2026-10-05', '50'], ['2026-10-10', '300']])
    await p.evaluate(async ([d, a]) => { await apiCall('/store/bank', { method: 'POST', body: JSON.stringify({ kind: 'charge', date: d, mode: 'Bank Transfer', amount: a }) }); }, [d, a]);
  const rows = () => p.evaluate(() => BK.rows.length), paid = () => p.evaluate(() => BK.paid);
  await p.evaluate(() => { document.getElementById('bk-month').value = '2026-10'; return bkLoad(); }); await p.waitForTimeout(1200);
  ck('one month: all 4', await rows() === 4 && await paid() === 650, [await rows(), await paid()]);
  await p.selectOption('#bk-range', 'day'); await p.fill('#bk-day', '2026-10-05'); await p.dispatchEvent('#bk-day', 'change'); await p.waitForTimeout(1200);
  ck('one day 5 Oct: 2 lines, 250.00', await rows() === 2 && await paid() === 250, [await rows(), await paid()]);
  ck('the totals say the day', /05 Oct 2026/.test(await p.locator('#bk-stats').textContent()));
  await p.screenshot({ path: SH + 'bank_day.png' });
  await p.selectOption('#bk-range', 'dates'); await p.fill('#bk-dfrom', '2026-10-05'); await p.fill('#bk-dto', '2026-10-10'); await p.dispatchEvent('#bk-dto', 'change'); await p.waitForTimeout(1200);
  ck('5 - 10 Oct: 3 lines, 550.00', await rows() === 3 && await paid() === 550, [await rows(), await paid()]);
  const ex = await p.evaluate(async () => { await refreshDownloadToken(); const r = await fetch(`${API}/export/accounts/bank?format=view&${bkQS()}&token=${encodeURIComponent(cachedDownloadToken)}`); return await r.text(); });
  ck('the preview follows the dates', /05 Oct - 10 Oct 2026/.test(ex) && /550\.00/.test(ex));
  await p.fill('#bk-dfrom', '2026-10-10'); await p.fill('#bk-dto', '2026-10-05'); await p.dispatchEvent('#bk-dto', 'change'); await p.waitForTimeout(1200);
  ck('dates the wrong way round still work', await rows() === 3);
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await b.close();
})();
