// The app must not download a backup file by itself after login (Acronis backs up the server now).
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const ctx = await b.newContext({ acceptDownloads: true });
  const p = await ctx.newPage(); const errs = [], dls = [];
  p.on('pageerror', e => errs.push(e.message)); p.on('download', d => dls.push(d.suggestedFilename()));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' });
  await p.waitForTimeout(70000);
  ck('no file downloaded in the 70 seconds after login', dls.length === 0, dls);
  ck('settings backup button still there', await p.evaluate(() => typeof downloadBackupById === 'function'));
  ck('no page errors', !errs.length, errs);
  await b.close();
  console.log(bad ? `${bad} FAILURE(S)` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
