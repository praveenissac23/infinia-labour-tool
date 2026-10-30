// With the dd/mm/yyyy date boxes on, every screen of the app and of Estimation opens without a page error and
// every date box on it is turned (none left showing the browser's own mm/dd/yyyy box).
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  await ctx.addInitScript(() => { window.__forceDmy = true; });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + (process.env.PAGE || '/app-classic.html'));
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 }); await sleep(2000);
  const screens = await p.evaluate(() => [...document.querySelectorAll('.screen[id^="screen-"]')].map(s => s.id.replace('screen-', '')));
  const left = [];
  for (const s of screens) {
    await p.evaluate(x => { try { switchScreen(x); } catch (e) {} }, s); await sleep(900);
    const r = await p.evaluate(() => [...document.querySelectorAll('input[type=date],input[type=datetime-local]')].filter(x => !x.__dmy && x.offsetParent !== null).map(x => x.id || x.className));
    if (r.length) left.push([s, r.slice(0, 3)]);
  }
  ck(`all ${screens.length} screens: every visible date box is dd/mm/yyyy`, !left.length, left);
  ck('no page errors on any screen', !errs.length, errs.slice(0, 5));
  const q = await ctx.newPage(); const e2 = []; q.on('pageerror', e => e2.push(e.message));
  await q.goto(B + '/portal/est-app.html?view=projects'); await q.fill('#lg-u', 'admin'); await q.fill('#lg-p', 'changeme123'); await q.click('#lg-go'); await sleep(2500);
  const pid = await q.evaluate(async () => (await (await fetch('/store/est/meta', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).projects[0].id);
  const secs = await q.evaluate(() => typeof SECTIONS !== 'undefined' ? Object.keys(SECTIONS) : []);
  const left2 = [];
  for (const sec of secs) {
    await q.evaluate(([pid, sec]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', sec); }, [pid, sec]);
    await q.reload(); await sleep(1500);
    const r = await q.evaluate(() => [...document.querySelectorAll('input[type=date],input[type=datetime-local]')].filter(x => !x.__dmy && x.offsetParent !== null).length);
    if (r) left2.push([sec, r]);
  }
  ck(`Estimation: all ${secs.length} sections, every visible date box is dd/mm/yyyy`, !left2.length, left2);
  ck('no page errors in Estimation', !e2.length, e2.slice(0, 5));
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
