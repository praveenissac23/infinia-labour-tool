// Closing the window shows the person offline straight away (not 70 seconds later).
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
const login = async (b, u, pw) => { const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000); return p; };
const onl = p => p.evaluate(async () => { const r = await fetch('/store/chat/state', { headers: { Authorization: 'Bearer ' + ((typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token')) } }); const j = await r.json(); return (j.users.find(u => u.username === 'admin') || {}).online; });
(async () => {
  const b = await chromium.launch();
  const amal = await login(b, 'amaltest', 'amal12345'); const adm = await login(b, 'admin', 'changeme123');
  ck('admin shows online to Amal', await onl(amal) === true);
  await adm.close({ runBeforeUnload: true }); await sleep(1200);
  ck('admin closes the window: offline at once', await onl(amal) === false);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
