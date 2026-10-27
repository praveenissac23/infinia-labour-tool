// How long each heavy screen takes to be usable in the browser (data + drawing), with long main-thread tasks counted.
//   BASE=http://127.0.0.1:8042 node tests/perf_screens.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  await p.addInitScript(() => { window.__lt = 0; try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt += e.duration; }).observe({ type: 'longtask', buffered: true }); } catch (e) {} });
  const t0 = Date.now();
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForLoadState('networkidle').catch(() => {});
  console.log('main app after login', Date.now() - t0, 'ms; long tasks', Math.round(await p.evaluate(() => window.__lt)), 'ms; DOM nodes', await p.evaluate(() => document.getElementsByTagName('*').length));
  const go = async (name, fn, ready) => {
    await p.evaluate(() => { window.__lt = 0; });
    const s = Date.now(); await p.evaluate(fn); if (ready) await p.waitForSelector(ready, { timeout: 30000 }).catch(() => {}); await p.waitForLoadState('networkidle').catch(() => {}); await sleep(300);
    const lt = await p.evaluate(() => window.__lt); const n = await p.evaluate(() => { let k = document.getElementsByTagName('*').length; document.querySelectorAll('iframe').forEach(f => { try { k += f.contentDocument.getElementsByTagName('*').length; } catch (e) {} }); return k; });
    console.log(`${name.padEnd(28)} ${String(Date.now() - s - 300).padStart(6)} ms   long tasks ${String(Math.round(lt)).padStart(6)} ms   DOM ${n}`);
  };
  await go('Store (materials)', () => pgGo('store'));
  await go('Reports', () => pgGo('reports'));
  await go('Estimation', () => pgGo('estimation'), 'iframe');
  await go('Dashboard', () => pgGo('dashboard'));
  await br.close();
})();
