// The busiest Trello board: time to draw and elements on the page.  BASE=... node tests/perf_board.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p.addInitScript(() => { window.__lt = 0; try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt += e.duration; }).observe({ type: 'longtask', buffered: true }); } catch (e) {} });
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(1500);
  const tok = await p.evaluate(() => sessionStorage.getItem('infinia_token'));
  const bid = await p.evaluate(async () => (await (await fetch('/store/kb/boards', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).boards.find(b => b.title === 'Designs').id).catch(() => null);
  const t0 = Date.now();
  await p.goto(B + `/portal/boards.html#/b/${bid}`); await p.waitForSelector('.card[data-c]', { timeout: 30000 }).catch(() => {}); await sleep(2500);
  const r = await p.evaluate(() => ({ n: document.getElementsByTagName('*').length, lt: Math.round(window.__lt), cards: document.querySelectorAll(".card[data-c]").length }));
  console.log('board', bid, 'open', Date.now() - t0, 'ms', JSON.stringify(r));
  await p.evaluate(() => { window.__lt = 0; }); const s = Date.now();
  await p.mouse.wheel(600, 0); await sleep(500);
  console.log('scroll long tasks', await p.evaluate(() => Math.round(window.__lt)));
  await br.close();
})();
