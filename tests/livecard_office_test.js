// Live Card: an office login (like the assistant accountant's) sees the same full list of workers as the admin,
// and a worker's card shows every day of the cycle at once - no scrolling inside the card.
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/lcoff_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
// The office login the test signs in with is made here (it used to be assumed to exist, so on a fresh copy of the
// database the second sign-in failed and the check read 0 workers): an office role with the Live card screen.
async function ensureOfficeLogin() {
  const tok = (await (await fetch(B + '/auth/login', { method: 'POST', body: new URLSearchParams({ username: 'admin', password: 'changeme123' }) })).json()).access_token;
  const H = { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' };
  let u = (await (await fetch(B + '/users', { headers: H })).json()).find(x => x.username === 'lc_office');
  if (!u) u = await (await fetch(B + '/users', { method: 'POST', headers: H, body: JSON.stringify({ username: 'lc_office', password: 'pass12345', role: 'office' }) })).json();
  await fetch(B + `/users/${u.id}/permissions`, { method: 'POST', headers: H, body: JSON.stringify({ permissions: 'attendance,livecard' }) });
}
(async () => {
  await ensureOfficeLogin();
  const br = await chromium.launch();
  const look = async (u, pw, w, h) => {
    const p = await (await br.newContext({ viewport: { width: w, height: h } })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()'); await sleep(3500);
    await p.goto(B + '/?p=attendance#livecard'); await sleep(3500);
    await p.evaluate(() => { if (typeof switchScreen === 'function' && !document.querySelector('#screen-livecard.active')) switchScreen('livecard'); }); await sleep(2500);
    const n = await p.$$eval('#livecard-worker-body tr.clickable-row', x => x.length);
    const cnt = await p.textContent('#lc-count').catch(() => '');
    await p.evaluate(() => { const s = document.getElementById('livecard-cycle'); const o = [...s.options].find(x => /25\/10\/2026$/.test(x.text) || /October 2026/.test(x.value)); if (o) { s.value = o.value; s.dispatchEvent(new Event('change')); } }); await sleep(2000);
    await p.click('#livecard-worker-body tr.clickable-row').catch(() => {}); await sleep(2500);
    const card = await p.evaluate(() => { const g = document.querySelector('#livecard-detail .grid-wrap'); return g ? { inner: g.scrollHeight - g.clientHeight } : null; });
    await p.screenshot({ path: `${SH}${u}_${w}.png` });
    return { n, cnt, card, errs };
  };
  const a = await look('admin', 'changeme123', 1440, 900);
  const o = await look('lc_office', 'pass12345', 1366, 768);
  ck(`office login sees the same workers as admin (${o.n} / ${a.n}) ${o.cnt}`, o.n === a.n && a.n > 10, [a, o]);
  ck('the card shows every day at once (no scroll inside the card) - admin', a.card && a.card.inner <= 1, a.card);
  ck('the card shows every day at once - office login, laptop screen', o.card && o.card.inner <= 1, o.card);
  ck('no page errors', !a.errs.length && !o.errs.length, [a.errs, o.errs]);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
