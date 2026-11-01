const { chromium } = require('playwright');
const B = process.env.BASE;
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username','admin'); await p.fill('#login-password','changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  await p.evaluate(() => pgGo('store')); await p.waitForTimeout(6000);
  console.log(await p.evaluate(() => JSON.stringify({u: location.href, act: (document.querySelector('.screen.active')||{}).id, hs: !!window.HOME_STOCK, loaded: typeof loadStoreHome})));
  if (!(await p.evaluate(() => !!HOME_STOCK))) { await p.evaluate(() => typeof loadStoreHome==='function' && loadStoreHome()); await p.waitForTimeout(5000); }
  const n = () => p.evaluate(() => document.querySelectorAll('#home-stock-body tr[data-key]').length);
  const total = await p.evaluate(() => HOME_STOCK && HOME_STOCK.rows.length);
  const r0 = await n();
  // scroll down repeatedly
  for (let i = 0; i < 12; i++) { await p.mouse.move(700, 600); await p.mouse.wheel(0, 3000); await p.waitForTimeout(400); }
  const r1 = await n();
  // reset and sort by Type
  await p.evaluate(() => { HOME_STOCK.limit = LIST_STEP; renderHomeStock(); });
  await p.waitForTimeout(500);
  await p.evaluate(() => window.scrollTo(0,0)); await p.evaluate(() => document.querySelectorAll('*').forEach(e => { if (e.scrollTop) e.scrollTop = 0; })); await p.waitForTimeout(500);
  const bb = await p.locator('#home-stock-head th', { hasText: 'Type' }).boundingBox(); await p.mouse.click(bb.x + bb.width / 2, bb.y + bb.height / 2); await p.waitForTimeout(1500);
  const r2 = await n();
  const rentData = await p.evaluate(() => HOME_STOCK.rows.filter(r => r.item_type === 'rental').length);
  const rentShown = await p.evaluate(() => [...document.querySelectorAll('#home-stock-body tr[data-key]')].filter(t => /Rental/.test(t.innerText)).length);
  console.log(JSON.stringify({ total, r0, afterScroll: r1, afterSort: r2, rentData, rentShown, errs }));
  await br.close();
})();
