// Live card: a worker who left before the chosen cycle is not listed in it;
// he is still there in the cycle he left in.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://127.0.0.1:8032/?p=attendance#livecard'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const list = () => p.evaluate(() => [...document.querySelectorAll('#livecard-worker-body tr td:first-child')].map(t => t.textContent.trim()));
  await p.selectOption('#livecard-cycle', 'October 2026'); await p.dispatchEvent('#livecard-cycle', 'change'); await p.waitForTimeout(1500);
  let l = await list();
  ck('October: the man who left in September (T-901) is not listed', !l.includes('T-901'), l.filter(x => x.startsWith('T-')));
  ck('October: the man leaving this cycle (T-902) is listed', l.includes('T-902'));
  await p.selectOption('#livecard-cycle', 'September 2026'); await p.dispatchEvent('#livecard-cycle', 'change'); await p.waitForTimeout(1500);
  l = await list();
  ck('September: T-901 is listed - he worked it', l.includes('T-901'));
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'LIVE CARD LISTS ONLY WHO WAS ON THE BOOKS');
  await b.close(); process.exit(bad ? 1 : 0);
})();
