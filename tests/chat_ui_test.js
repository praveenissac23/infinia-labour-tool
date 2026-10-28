// In-app chat on screen: two people, who is online, Everyone, a private chat, @tagging, the bell; and on a phone.
//   BASE=http://127.0.0.1:8042 OUT=/tmp node tests/chat_ui_test.js   (full.db: tests/seed_full.py)
const { chromium, devices } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
const login = async (b, u, pw, opts) => { const ctx = await b.newContext(opts || { viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage(); p.errs = [];
  p.on('pageerror', e => p.errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(() => { window.checkBuild = () => {}; const x = document.getElementById('build-bar'); if (x) x.remove(); }); return p; };
(async () => {
  const b = await chromium.launch();
  const amal = await login(b, 'amaltest', 'amal12345');
  const pr = await login(b, 'admin', 'changeme123');
  ck('the chat button sits beside the bell', await pr.$('#chat-btn') !== null);
  await pr.click('#chat-btn'); await sleep(1500);
  const online = await pr.evaluate(() => CHAT.state.users.filter(u => u.online && !u.me).map(u => u.username));
  ck('Amal shows as online', online.includes('amaltest'), online);
  // @ tagging in Everyone
  await pr.click('[data-room="all"]'); await sleep(800);
  await pr.click('[data-in]'); await pr.keyboard.type('Morning team, @Am'); await sleep(300);
  ck('typing @Am offers Amal', await pr.evaluate(() => [...document.querySelectorAll('[data-pick] div')].some(d => /Amal/.test(d.textContent))));
  await pr.keyboard.press('Enter'); await pr.keyboard.type('please send the cement list'); await pr.keyboard.press('Enter'); await sleep(1500);
  const last = await pr.evaluate(() => { const ms = CHAT.state.msgs.all; return ms[ms.length - 1].text; });
  ck('the message goes with the tag', /@amaltest please send the cement list/.test(last), last);
  // Amal: badge, bell, opens and sees it highlighted
  await sleep(21000);
  const b1 = await amal.evaluate(() => document.querySelector('#chat-btn .n').textContent);
  ck('Amal\'s chat button shows 1 unread', b1 === '1', b1);
  await amal.click('#chat-btn'); await sleep(1500);
  await amal.click('[data-room="all"]'); await sleep(1500);
  ck('he sees it, marked as naming him', await amal.evaluate(() => !!document.querySelector('#chat-pane .m.me-tag .tag.me')));
  // private chat
  const room = await amal.evaluate(() => CHAT.state.users.find(u => u.username === 'admin').room);
  await amal.click(`[data-room="${room}"]`); await sleep(800);
  await amal.fill('[data-in]', 'Sending now - 3 items short, will call'); await amal.keyboard.press('Enter'); await sleep(4500);
  const got = await pr.evaluate(r => (CHAT.state.unread[r] || 0) + (CHAT.state.msgs[r] || []).length, room);
  ck('Praveen gets the private message (within seconds)', got >= 1, got);
  await pr.click(`[data-room="${room}"]`); await sleep(1500);
  await pr.screenshot({ path: OUT + '/chat-desktop.png' });
  ck('no script errors', !pr.errs.length && !amal.errs.length, [pr.errs, amal.errs]);
  // phone
  const ph = await login(b, 'amaltest', 'amal12345', { ...devices['iPhone 13'] });
  await ph.click('#chat-btn'); await sleep(1500);
  await ph.screenshot({ path: OUT + '/chat-phone-list.png' });
  await ph.click(`[data-room="${room}"]`); await sleep(1500);
  await ph.screenshot({ path: OUT + '/chat-phone-conv.png' });
  const fits = await ph.evaluate(() => document.getElementById('chat-pane').getBoundingClientRect().width <= innerWidth + 1);
  ck('phone: full screen, nothing off the side', fits);
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
