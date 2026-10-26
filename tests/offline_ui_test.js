// Working offline: the application stops (an update, an outage) - the banner shows, saves are kept on this
// computer (even with the browser closed), anything needing a number waits with a message; the application
// comes back - the saves go up by themselves, once each, and the banner turns green.
const { chromium } = require('playwright');
const { execSync, spawn } = require('child_process');
const fs = require('fs'), path = require('path');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/offline_';
const PORT = +new URL(B).port, API = PORT + 1, LANE = Math.round((PORT - 8060) / 10);
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const stopApp = () => { try { execSync(`fuser -k ${API}/tcp`, { stdio: 'ignore' }); } catch (e) {} };
let app2 = null;
const startApp = async () => {
  app2 = spawn('python3', ['-m', 'uvicorn', 'main:app', '--port', String(API), '--log-level', 'warning'],
    { cwd: path.join(__dirname, '..', 'app'), env: Object.assign({}, process.env, { DATABASE_URL: `sqlite:////tmp/lane${LANE}.db`, INFINIA_NO_SCHED: '1' }), stdio: 'ignore', detached: true });
  for (let i = 0; i < 60; i++) { try { execSync(`curl -sf http://127.0.0.1:${API}/health`, { stdio: 'ignore' }); return; } catch (e) { await sleep(1000); } }
};
(async () => {
  const dir = '/tmp/claude-0/offdir_' + process.pid; fs.rmSync(dir, { recursive: true, force: true });
  const open = () => chromium.launchPersistentContext(dir, { viewport: { width: 1440, height: 900 } });
  let ctx = await open(); let p = ctx.pages()[0] || await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.check('#lg-keep'); await p.click('#lg-go'); await sleep(1500);
  const api = async u => p.evaluate(async u => (await fetch(u, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), u);
  let meta = {}; for (let i = 0; i < 10 && !meta.projects; i++) { meta = await api('/store/est/meta').catch(() => ({})); if (!meta.projects) await sleep(1500); }
  const P = meta.projects.find(x => x.code === '914').id;
  await p.evaluate(pid => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'site.submittal'); }, P);
  for (let i = 0; i < 6; i++) { await p.reload(); await sleep(1800); if (await p.evaluate(() => !!navigator.serviceWorker.controller)) break; }
  ck('the offline helper is running on the page', await p.evaluate(() => !!navigator.serviceWorker.controller));
  { const m = await ctx.newPage(); await m.goto(B + '/'); await sleep(4000); await m.goto(B + '/?p=attendance'); await sleep(3000); await m.close(); }   // the main app used normally before
  await p.fill('#qa-title', 'Before the outage'); await p.press('#qa-title', 'Enter'); await sleep(1500);
  const before = (await api(`/store/est/projects/${P}`)).logs.filter(l => l.kind === 'submittal');
  // ---- the application stops
  stopApp(); await sleep(1500);
  await p.fill('#qa-title', 'Fire rated doors - made offline'); await p.press('#qa-title', 'Enter'); await sleep(2000);
  let bar = await p.textContent('#off-bar').catch(() => '');
  ck('banner: "Working offline", 1 saved on this computer', /Working offline/.test(bar) && /1 saved on this computer/.test(bar), bar);
  const s0 = before.find(l => /Before the outage/.test(l.title));
  await p.click(`[data-step="${s0.id}"][data-v="Approved"]`).catch(() => {}); await sleep(1500);
  await p.fill(`[data-cell="${s0.id}"][data-k="note"]`, 'Approved by phone - letter to follow'); await p.press(`[data-cell="${s0.id}"][data-k="note"]`, 'Enter'); await sleep(1500);
  bar = await p.textContent('#off-bar');
  ck('the click and the remark are kept too (3 waiting)', /3 saved on this computer/.test(bar), bar);
  const lpo = await p.evaluate(async () => { const r = await fetch('/store/purchase/orders', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') }, body: '{}' }); return { s: r.status, j: await r.json() }; });
  ck('a new LPO waits for the server, with a plain message', lpo.s === 503 && /LPO/.test(lpo.j.detail), lpo);
  await p.click('#off-bar [data-off="list"]'); await sleep(400);
  const items = await p.$$eval('#off-list .it', x => x.map(y => y.textContent.replace(/\s+/g, ' ').trim()));
  ck('"See them" lists the 3 saves', items.length === 3 && /Fire rated doors/.test(items.join(' ')), items);
  await p.screenshot({ path: SH + '1_offline.png' });
  // the main app opens while it is down, signed in, with the banner
  const m = await ctx.newPage(); await m.goto(B + '/'); await sleep(4000);
  ck('main app opens during the outage, signed in, banner on top', await m.isVisible('#app-screen') && /Working offline/.test(await m.textContent('#off-bar').catch(() => '')), await m.textContent('#off-bar').catch(() => ''));
  await m.goto(B + '/?p=attendance'); await sleep(4000);
  ck('the menu and the attendance list show from what was kept', (await m.$$eval('#grid-body tr', x => x.length).catch(() => 0)) > 10 && /Attendance/.test(await m.textContent('.sidebar, nav, #sidebar').catch(() => '')));
  await m.screenshot({ path: SH + '0_mainapp.png' }); await m.close();
  // reopen the page while it is still down: it opens, the list shows, the saves are still there
  await p.goto(B + '/portal/est-app.html?view=projects'); await sleep(3000);
  ck('the page opens while the server is down', await p.isVisible('#qa-title').catch(() => false));
  ck('still 3 waiting after reopening', /3 saved on this computer/.test(await p.textContent('#off-bar').catch(() => '')));
  // the computer is switched off (browser closed) before the server is back
  await ctx.close();
  await startApp();
  ctx = await open(); p = ctx.pages()[0] || await ctx.newPage(); p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await sleep(8000);
  bar = await p.textContent('#off-bar').catch(() => '');
  ck('next time the app is opened: uploaded by itself, banner green', /Back online/.test(bar) && /3 saved items uploaded/.test(bar), bar);
  await p.screenshot({ path: SH + '2_back.png' });
  const after = (await api(`/store/est/projects/${P}`)).logs.filter(l => l.kind === 'submittal');
  const made = after.filter(l => /Fire rated doors/.test(l.title)), s1 = after.find(l => l.id === s0.id);
  ck('the offline submittal is on the server - once', made.length === 1, made.length);
  ck('the click (Approved) and the remark reached the server', s1.status === 'Approved' && /letter to follow/.test(s1.note), s1);
  ck('the page refreshed by itself: the remark shows', /letter to follow/.test(await p.inputValue(`[data-cell="${s0.id}"][data-k="note"]`).catch(() => '')));
  ck('nothing left waiting', await p.evaluate(() => (window.OFFLINE_STATE ? window.OFFLINE_STATE().pending : -1)) === 0);
  ck('no page errors', !errs.length, errs);
  await ctx.close(); try { process.kill(-app2.pid); } catch (e) {}
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
