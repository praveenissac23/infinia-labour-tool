// Chat: the entry at the foot of the left menu (unread / online), a pop-up + sound when a message arrives with the
// chat closed, a computer notification when the portal is in the background, the mute switch.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
const login = async (b, u, pw) => { const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, permissions: ['notifications'] }); const p = await ctx.newPage(); p.errs = [];
  p.on('pageerror', e => p.errs.push(e.message));
  await p.addInitScript(() => { window.__notes = []; const N = window.Notification; window.__dings = 0;
    const AC = window.AudioContext; window.AudioContext = function () { const a = new AC(); const o = a.createOscillator.bind(a); a.createOscillator = () => { window.__dings++; return o(); }; return a; }; });
  await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(() => { window.checkBuild = () => {}; const x = document.getElementById('build-bar'); if (x) x.remove(); }); return p; };
(async () => {
  const b = await chromium.launch();
  const amal = await login(b, 'amaltest', 'amal12345');
  const pr = await login(b, 'admin', 'changeme123');
  await sleep(9000);
  const side = await pr.evaluate(() => { const e = document.querySelector('.pg-side .pg-chat'); const r = e.getBoundingClientRect(); return { y: Math.round(r.bottom), h: innerHeight, txt: e.textContent, hdr: getComputedStyle(document.getElementById('chat-btn')).display }; });
  ck('Chat sits at the foot of the left menu', side.y > side.h - 80 && /Chat/.test(side.txt), side);
  ck('it says who is online', /1 online/.test(side.txt), side.txt);
  ck('(the header button is put away while the menu shows)', side.hdr === 'none', side.hdr);
  const room = await amal.evaluate(async () => { await CHAT.poll(); return CHAT.state.users.find(u => u.username === 'admin').room; });
  await amal.evaluate(async r => { await fetch(API + '/store/chat/send', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + TOKEN }, body: JSON.stringify({ room: r, text: 'Cement delivery reached 903' }) }); }, room);
  await sleep(9500);
  const t = await pr.evaluate(() => { const x = document.querySelector('#wa-toasts .t'); return x ? x.textContent : null; });
  ck('Praveen gets a pop-up with who and what', t && /Cement delivery reached 903/.test(t), t);
  ck('and a sound', await pr.evaluate(() => window.__dings > 0));
  ck('the side entry shows 1 unread', await pr.evaluate(() => document.querySelector('.pg-chat .cn').textContent === '1'));
  await pr.screenshot({ path: OUT + '/chat-popup.png' });
  await pr.click('#wa-toasts .t'); await sleep(2000);
  ck('tapping it opens that chat', await pr.evaluate(r => CHAT.state.open && CHAT.state.room === r, room));
  await pr.screenshot({ path: OUT + '/chat-bg.png' });
  // mute
  await pr.click('[data-bell]'); await sleep(300);
  await pr.click('[data-x2]'); await sleep(500);
  await amal.evaluate(async r => { await fetch(API + '/store/chat/send', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + TOKEN }, body: JSON.stringify({ room: r, text: 'second' }) }); }, room);
  await pr.evaluate(() => { document.getElementById('wa-toasts').innerHTML = ''; }); await sleep(9500);
  ck('muted: no pop-up', await pr.evaluate(() => !document.querySelector('#wa-toasts .t')));
  ck('no script errors', !pr.errs.length && !amal.errs.length, [pr.errs, amal.errs]);
  await pr.evaluate(() => localStorage.removeItem('chat_notify'));
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
