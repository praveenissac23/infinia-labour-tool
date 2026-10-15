// Audit: every page, tab and sub-tab - API calls (duplicates), errors, re-render bursts, overflow, time to settle.
const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8032';
const USER = process.argv[2] || 'admin', PW = process.argv[3] || 'changeme123', W = +(process.argv[4] || 1440);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } });
  const p = await ctx.newPage();
  let reqs = [], errs = [];
  p.on('request', r => { const u = r.url(); if (r.resourceType() === 'fetch' || r.resourceType() === 'xhr') reqs.push({ u: u.replace(B, '').replace(/([?&])(token|_)=[^&]*/g, '$1$2=*'), t: Date.now() }); });
  p.on('pageerror', e => errs.push('PAGEERR ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text().slice(0, 200)); });
  const slow = {};
  p.on('requestfinished', r => { if (['fetch','xhr'].includes(r.resourceType())) { const t = r.timing(); const d = t.responseEnd - t.requestStart; const k = r.url().replace(B, '').split('?')[0]; if (d > (slow[k] || 0)) slow[k] = Math.round(d); } });
  p.on('response', r => { if (r.status() >= 400 && !r.url().includes('/health')) errs.push(`HTTP ${r.status()} ${r.url().replace(B, '')}`); });
  await p.goto(B + '/'); await p.fill('#login-username', USER); await p.fill('#login-password', PW); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  const tree = await p.evaluate(() => Object.entries(ALL_TABS).map(([k, tabs]) => [k, tabs.filter(t => pgTabOk ? true : true).map(t => ({ id: t.id, hidden: t.hidden, subs: t.subs.map(s => s.id) }))]));
  const out = [];
  async function measure(label, go) {
    reqs = []; errs = [];
    await p.evaluate(() => {
      window.__bursts = 0; window.__last = 0; window.__muts = 0;
      if (window.__mo) window.__mo.disconnect();
      window.__mo = new MutationObserver(ms => { const n = performance.now(); window.__muts += ms.length; if (n - window.__last > 120) window.__bursts++; window.__last = n; });
      window.__mo.observe(document.getElementById('app-screen') || document.body, { childList: true, subtree: true });
    }).catch(() => {});
    const t0 = Date.now();
    await go();
    // settle: no request for 800 ms
    let lastN = -1, still = 0;
    for (let i = 0; i < 40; i++) { await p.waitForTimeout(250); if (reqs.length === lastN) { still += 250; if (still >= 1000) break; } else { still = 0; lastN = reqs.length; } }
    const settle = (reqs.length ? reqs[reqs.length - 1].t : t0) - t0;
    const info = await p.evaluate(() => ({ bursts: window.__bursts, muts: window.__muts,
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      title: (document.getElementById('screen-title') || {}).textContent,
      empty: !document.querySelector('.screen.active') })).catch(e => ({ err: e.message }));
    const cnt = {}; reqs.forEach(r => { const k = r.u.split('#')[0]; cnt[k] = (cnt[k] || 0) + 1; });
    const dups = Object.entries(cnt).filter(([, n]) => n > 1).map(([u, n]) => `${n}x ${u}`);
    out.push({ label, n: reqs.length, settle, dups, errs: [...new Set(errs)], ...info });
    console.log(`${label.padEnd(40)} req ${String(reqs.length).padStart(3)} settle ${String(settle).padStart(5)}ms bursts ${info.bursts} ovf ${info.overflow}${dups.length ? ' DUP ' + dups.join(' | ') : ''}${errs.length ? ' ERR ' + [...new Set(errs)].join(' | ') : ''}`);
  }
  for (const [key, tabs] of tree) {
    // fresh load of the page
    await measure(`LOAD ${key}`, () => p.goto(B + (key === 'dashboard' ? '/' : '/?p=' + key)));
    for (const t of tabs) {
      if (t.hidden) continue;
      const ok = await p.evaluate(id => { const t = PAGE.tabs.find(x => x.id === id); return !!t && pgTabOk(t); }, t.id).catch(() => false);
      if (!ok) continue;
      await measure(`${key} > ${t.id}`, () => p.evaluate(id => pgTab(id), t.id));
      for (const s of t.subs.slice(1)) await measure(`${key} > ${t.id} > ${s}`, () => p.evaluate(id => pgSub(id), s));
    }
  }
  fs.writeFileSync(`/tmp/claude-0/audit/crawl_${USER}_${W}.json`, JSON.stringify(out, null, 1));
  console.log('SLOWEST', Object.entries(slow).sort((a, b) => b[1] - a[1]).slice(0, 15).map(([k, v]) => `${v}ms ${k}`).join(' | '));
  await b.close();
})();
