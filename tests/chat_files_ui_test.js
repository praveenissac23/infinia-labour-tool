// Chat: a photo, a file and a voice message on screen (fake microphone), and how they show.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp', PHOTO = process.env.PHOTO;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, permissions: ['microphone'] }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(() => { window.checkBuild = () => {}; const x = document.getElementById('build-bar'); if (x) x.remove(); });
  await p.click('#chat-btn'); await sleep(1200); await p.click('[data-room="all"]'); await sleep(800);
  // a photo
  await p.setInputFiles('[data-file]', PHOTO); await sleep(800);
  ck('the photo waits above the box, made smaller', await p.evaluate(() => !!document.querySelector('.att img') && CHAT.state.file && CHAT.state.file.size < 900 * 1024), await p.evaluate(() => CHAT.state.file && CHAT.state.file.size));
  await p.fill('[data-in]', 'Blockwork at 903 - finished today'); await p.click('[data-send]'); await sleep(2000);
  ck('sent: the picture shows in the chat', await p.evaluate(() => { const i = document.querySelector('#chat-pane .fimg'); return i && i.complete && i.naturalWidth > 0; }));
  // a file
  await p.setInputFiles('[data-file]', { name: 'BOQ 914 rev2.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('PK' + 'x'.repeat(2000)) });
  await sleep(400); await p.keyboard.press('Enter'); await p.click('[data-send]'); await sleep(2000);
  ck('a file shows as a card to download', await p.evaluate(() => [...document.querySelectorAll('#chat-pane .ffile b')].some(b => /BOQ 914/.test(b.textContent))));
  // a voice message
  await p.click('[data-mic]'); await sleep(3300);
  ck('recording: the timer runs', await p.evaluate(() => document.querySelector('[data-rt]').textContent !== '0:00' && getComputedStyle(document.querySelector('[data-rec]')).display !== 'none'));
  await p.screenshot({ path: OUT + '/chat-recording.png' });
  await p.click('[data-rsend]'); await sleep(2500);
  const v = await p.evaluate(() => { const a = [...document.querySelectorAll('#chat-pane .fvoice audio')].pop(); return a ? { ok: true, src: a.src } : null; });
  ck('the voice message is in the chat, ready to play', v && v.ok, v);
  const dur = await p.evaluate(async () => { const a = [...document.querySelectorAll('#chat-pane .fvoice audio')].pop(); const r = await fetch(a.src); return [r.status, r.headers.get('content-type'), (await r.arrayBuffer()).byteLength]; });
  ck('and the server sends it back as audio', dur[0] === 200 && /audio/.test(dur[1]) && dur[2] > 1000, dur);
  await p.screenshot({ path: OUT + '/chat-files.png' });
  ck('no script errors', !errs.length, errs);
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
