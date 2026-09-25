// The request form on a slow connection: Material Requests opened before
// the app's start-up fetch of sites and engineers has returned must still
// get its site and name lists. Run: python3 tests/serve_like_nginx.py, then node tests/requests_race_test.js
const { chromium } = require('playwright');
let fails = 0;
const ck = (l, ok, c) => { console.log((ok ? 'PASS ' : 'FAIL ') + l + (ok ? '' : `  [${c}]`)); if (!ok) fails++; };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('http://127.0.0.1:8032/app.html');
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1200);
  await p.evaluate(async () => {
    const users = await apiCall('/users'); let u = users.find(x => x.username === 'race_req');
    if (!u) u = await apiCall('/users', { method: 'POST', body: JSON.stringify({ username: 'race_req', password: 'racereq123', full_name: 'Race', role: 'site' }) });
    await apiCall(`/users/${u.id}/permissions`, { method: 'POST', body: JSON.stringify({ permissions: 'dashboard,requests,settings' }) });
  });
  await p.evaluate('doLogout()');
  // A slow line: the people lists take three seconds to arrive.
  const slow = await (await b.newContext()).newPage();
  await slow.route(/\/(sites|engineers|employees\?)/, async route => { await new Promise(r => setTimeout(r, 3000)); route.continue(); });
  await slow.goto('http://127.0.0.1:8032/app.html');
  await slow.fill('#login-username', 'race_req'); await slow.fill('#login-password', 'racereq123'); await slow.evaluate('doLogin(); 0');
  await slow.waitForSelector('#app-screen', { state: 'visible' });
  // Tap Material Requests straight away, before the lists are back.
  await slow.evaluate("switchScreen('requests')");
  await slow.waitForTimeout(5000);
  const sites = await slow.locator('#mr-site option').count(), names = await slow.locator('#mr-by option').count();
  ck(`the request form gets its site list even when opened early (${sites} options)`, sites > 2, sites);
  ck(`and its name list (${names} options)`, names > 2, names);
  await p.evaluate(async () => { const u = (await apiCall('/users')).find(x => x.username === 'race_req'); if (u) await apiCall(`/users/${u.id}`, { method: 'DELETE' }).catch(() => {}); }).catch(() => {});
  await b.close();
  console.log(fails ? `\n${fails} FAILED` : '\nTHE FORM WAITS FOR ITS LISTS');
  process.exit(fails ? 1 : 0);
})();
