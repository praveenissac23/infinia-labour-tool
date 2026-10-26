// "Keep me signed in on this device": the browser closed and opened again, the app opens signed in.
const { chromium } = require('playwright');
const fs = require('fs');
const Buffer = require('buffer').Buffer;
const B = 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const dir = '/tmp/claude-0/keepdir_' + process.pid; fs.rmSync(dir, { recursive: true, force: true });
  const open = async () => chromium.launchPersistentContext(dir, { viewport: { width: 1400, height: 900 } });
  let c = await open(); let p = c.pages()[0] || await c.newPage();
  await p.goto(B + '/'); await sleep(1500);
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.check('#login-keep');
  await p.press('#login-password', 'Enter'); await sleep(3500);
  await p.screenshot({ path: '/tmp/claude-0/ks/after_login.png' }); ck('signed in', await p.isVisible('#app-screen'));
  const st = await p.evaluate(() => ({ keep: !!localStorage.getItem('infinia_keep'), url: location.href }));
  ck('kept on the device', st.keep, st);
  await p.goto(B + '/?p=estimation#estproj'); await sleep(3000);
  ck('still kept after moving around', await p.evaluate(() => !!localStorage.getItem('infinia_keep')));
  await c.close();
  c = await open(); p = c.pages()[0] || await c.newPage();
  for (const path of ['/', '/?p=accounts#accounts', '/portal/est-app.html?view=projects']) {
    await p.goto(B + path); await sleep(3500);
    const s = await p.evaluate(() => ({ login: !!document.querySelector('#login-screen') && getComputedStyle(document.querySelector('#login-screen')).display !== 'none', lg: !!document.querySelector('#lg-u') && document.querySelector('#lg-u').offsetParent !== null, keep: !!localStorage.getItem('infinia_keep') }));
    ck(`browser reopened, ${path}: signed in, no sign-in box`, !s.login && !s.lg, s);
  }
  // the kept sign-in was renewed on opening (30 days from today again), and still a kept one
  const t2 = await p.evaluate(() => localStorage.getItem('infinia_keep'));
  const pl = JSON.parse(Buffer.from(t2.split('.')[1], 'base64').toString());
  ck('renewed on opening: a kept sign-in with ~30 days left', pl.keep === true && pl.exp - Date.now() / 1000 > 29.9 * 86400, pl);
  // sign out, and the tick is still there next time
  await p.goto(B + '/'); await sleep(3000); await p.evaluate(() => doLogout()); await sleep(2500);
  ck('signed out: the kept sign-in is gone, the tick is remembered', await p.evaluate(() => !localStorage.getItem('infinia_keep') && document.getElementById('login-keep').checked));
  await c.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
