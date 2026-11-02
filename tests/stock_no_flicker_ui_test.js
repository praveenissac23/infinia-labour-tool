const { chromium } = require('playwright');
const B = process.env.BASE;
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i))); };
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username','admin'); await p.fill('#login-password','changeme123'); await p.evaluate('doLogin()').catch(()=>{}); await p.waitForTimeout(1500);
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  await p.evaluate(() => pgGo('store', 'store:home')); await p.waitForTimeout(6000);
  const r = await p.evaluate(async () => {
    const b = document.getElementById('home-stock-body'); let m = 0;
    const ob = new MutationObserver(x => m += x.length); ob.observe(b, { childList: true, subtree: true });
    const wait = ms => new Promise(r => setTimeout(r, ms));
    await wait(2000); const idle = m; m = 0;
    const heads = [...document.querySelectorAll('#home-stock-head th')]; const th = heads.find(t => /Type/.test(t.textContent)); th.click(); const ci = () => [...document.querySelectorAll('#home-stock-head th')].findIndex(t => /Type/.test(t.textContent));
    await wait(1500); m = 0; await wait(3000); const idleSorted = m;
    const types = [...b.querySelectorAll('tr[data-key]')].map(tr => tr.children[ci()] && tr.children[ci()].innerText.trim().toLowerCase());
    const brk = types.findIndex((t, i) => i > 0 && types[i - 1].localeCompare(t) > 0); const sortedOk = brk < 0; window.__dbg = { brk, around: types.slice(Math.max(0, brk - 2), brk + 2), uniq: [...new Set(types)].slice(0, 8), dir: (document.querySelector('#home-stock-head .tx-a') || {}).textContent };
    // the screen redraws (search) - sort must come back, and settle
    const s = document.getElementById('home-stock-search'); s.value = 'a'; s.dispatchEvent(new Event('input')); await wait(1500);
    m = 0; await wait(2000); const idleAfterSearch = m;
    const t2 = [...b.querySelectorAll('tr[data-key]')].map(tr => tr.children[ci()] && tr.children[ci()].innerText.trim().toLowerCase());
    const sorted2 = t2.every((t, i) => i === 0 || t2[i - 1].localeCompare(t) <= 0);
    ob.disconnect();
    return { dbg: window.__dbg, idle, idleSorted, sortedOk, rows: types.length, total: HOME_STOCK.rows.length, idleAfterSearch, sorted2, rows2: t2.length };
  });
  console.log(JSON.stringify(r));
  ck('idle list does not redraw', r.idle === 0, r.idle);
  ck('after sorting, the list stays still (no flicker)', r.idleSorted === 0, r.idleSorted);
  ck('sort covers every row', r.sortedOk && r.rows === r.total, [r.rows, r.total]);
  ck('after a search redraw: sorted again and still', r.sorted2 && r.idleAfterSearch === 0, [r.sorted2, r.idleAfterSearch]);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
