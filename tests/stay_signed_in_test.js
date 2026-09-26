// Leaving a page at any moment - even while the Staff screen is still
// loading quietly in the background - must never sign the person out.
// A cut-off request once cleared the shared sign-in, so the next page
// showed the sign-in box. Also: a sign-in check that fails on a weak
// connection must retry, not sign out.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/temporary/Infinia/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const p = await b.newPage();
  await p.goto(BASE + 'dashboard.html'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await p.waitForTimeout(2500);
  const pages = ['dashboard', 'attendance', 'payroll', 'store', 'reporting', 'settings'];
  for (let i = 0; i < 36; i++) {
    const delay = 1300 + (i % 12) * 100;          // 1.3 s - 2.4 s: right across the frame's loading
    await p.goto(BASE + pages[i % 6] + '.html'); await p.waitForTimeout(delay);
    const tok = await p.evaluate(() => !!sessionStorage.getItem('infinia_token'));
    if (!tok) { bad++; console.log(`FAIL left ${pages[i % 6]} after ${delay} ms - signed out`); }
  }
  await p.goto(BASE + 'store.html');
  const ok = await p.waitForSelector('#app-screen', { state: 'visible', timeout: 10000 }).then(() => true).catch(() => false);
  if (!ok) bad++;
  console.log(`${ok ? 'PASS' : 'FAIL'} still signed in after 36 quick page changes`);
  // A weak connection: the first sign-in check fails, the page must retry and get in.
  const c2 = await b.newContext(); const q = await c2.newPage();
  await q.goto(BASE + 'dashboard.html'); await q.fill('#login-username', 'admin'); await q.fill('#login-password', 'changeme123'); await q.evaluate('doLogin()'); await q.waitForTimeout(2000);
  let drop = 2; await q.route('**/auth/me', r => { if (drop-- > 0) r.abort('connectionreset'); else r.continue(); });
  await q.goto(BASE + 'payroll.html'); await q.waitForTimeout(7000);
  const in2 = await q.evaluate(() => !!sessionStorage.getItem('infinia_token') && getComputedStyle(document.getElementById('app-screen')).display !== 'none' && getComputedStyle(document.getElementById('login-screen')).display === 'none');
  if (!in2) bad++;
  console.log(`${in2 ? 'PASS' : 'FAIL'} two dropped sign-in checks: the page retried and stayed signed in`);
  // A sign-in the server refuses still ends properly.
  await q.unroute('**/auth/me'); await q.evaluate(() => sessionStorage.setItem('infinia_token', 'expired'));
  await q.goto(BASE + 'store.html'); await q.waitForTimeout(3000);
  const out = await q.locator('#login-screen').isVisible();
  if (!out) bad++;
  console.log(`${out ? 'PASS' : 'FAIL'} an expired sign-in shows the sign-in box`);
  console.log(bad ? `${bad} FAILED` : 'NEVER SIGNED OUT BY ACCIDENT');
  await b.close(); process.exit(bad ? 1 : 0);
})();
