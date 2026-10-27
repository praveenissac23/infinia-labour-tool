// Elements on the page after each heavy screen (main page + its frames) and the biggest blocks - a page with tens of
// thousands of elements makes everything slow.   BASE=http://127.0.0.1:8042 node tests/perf_survey.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000);
  const count = async label => {
    let tot = 0; const big = [];
    for (const f of p.frames()) {
      const r = await f.evaluate(() => ({ n: document.getElementsByTagName('*').length,
        big: [...document.querySelectorAll('tbody, ul, .md-chip-wrap, datalist, .kb-list, .list-cards, #app')].map(e => [e.tagName + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ')[0] : ''), e.getElementsByTagName('*').length]).filter(x => x[1] > 1500) })).catch(() => ({ n: 0, big: [] }));
      tot += r.n; big.push(...r.big.map(b => [f.url().split('/').pop().slice(0, 18), ...b]));
    }
    console.log(label.padEnd(26), String(tot).padStart(7), JSON.stringify(big.sort((a, b) => b[2] - a[2]).slice(0, 5)));
  };
  await count('start');
  const t = async (label, fn, wait = 4000) => { const s = Date.now(); await p.evaluate(fn).catch(e => console.log(label, e.message)); await sleep(wait); await count(label); };
  await t('Store', () => pgGo('store'), 8000);
  await t('Store > item list', () => { try { pgSub('items'); } catch (e) {} }, 3000);
  await t('Reports', () => pgGo('reports'));
  await t('Reports > assets', () => pickReport('assets'), 5000);
  await t('Reports > stock', () => pickReport('stock'), 5000);
  await t('Staff', () => pgGo('staff'));
  await t('Estimation', () => pgGo('estimation'), 6000);
  await t('Estimation > Trello', () => { try { pgTab('boards'); } catch (e) { pgGo('boards'); } }, 8000);
  await br.close();
})();
