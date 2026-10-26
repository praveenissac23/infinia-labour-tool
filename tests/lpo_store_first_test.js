// LPO > Project location: the store is the first suggestion.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  await p.evaluate(async () => { const h = { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }; await fetch('/sites', { method: 'POST', headers: h, body: JSON.stringify({ code: 'Store' }) }); });
  await p.goto(B + '/?p=store'); await sleep(3500); await p.evaluate(() => loadPurchase()); await sleep(2500);
  const first = await p.evaluate(() => [...document.querySelectorAll('#site-list option')].map(o => o.value));
  const ok = first[0] === 'Store';
  console.log((ok ? 'PASS' : 'FAIL') + ' the store is the first project location ' + JSON.stringify(first.slice(0, 4)));
  await br.close(); console.log(ok ? 'ALL PASS' : '1 FAILED'); process.exit(ok ? 0 : 1); })();
