// Activity Monitor: the Chat filter shows chat messages with what they said.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(async () => { const T = (typeof TOKEN !== 'undefined' && TOKEN) || sessionStorage.getItem('infinia_token');
    await fetch('/store/chat/send', { method: 'POST', headers: { Authorization: 'Bearer ' + T, 'Content-Type': 'application/json' }, body: JSON.stringify({ room: 'all', text: 'Scaffolding inspection at 903 at 10am - @everyone' }) }); });
  await p.goto(B + '/?p=settings#activity'); await sleep(3000);
  await p.evaluate(() => { window.checkBuild = () => {}; const x = document.getElementById('build-bar'); if (x) x.remove(); });
  const has = await p.evaluate(() => [...document.querySelectorAll('#act-group button')].map(b => b.textContent));
  ck('a Chat filter on the Activity Monitor', has.includes('Chat'), has);
  await p.evaluate(() => [...document.querySelectorAll('#act-group button')].find(b => b.textContent === 'Chat').click()); await sleep(1500);
  const t = await p.evaluate(() => document.getElementById('activity-body').textContent);
  ck('the message and what it said', /Chat message/.test(t) && /Everyone: Scaffolding inspection at 903/.test(t), t.slice(0, 300));
  await p.screenshot({ path: OUT + '/activity-chat.png' });
  ck('no script errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
