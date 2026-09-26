// Every page, every width from 1920 down to 360 in steps: tiles in a row
// must be equal width and equal height, nothing may overflow the window
// sideways, and the content must never be squeezed narrower than 300px.
const { chromium } = require('playwright');
const S = require('os').tmpdir() + '/';
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto('http://127.0.0.1:8032/temporary/Infinia/dashboard.html'); await p.fill('#login-username','admin'); await p.fill('#login-password','changeme123'); await p.evaluate('doLogin(); 0'); await p.waitForTimeout(3000);
  let bad = 0; const widths = [1920, 1680, 1440, 1366, 1280, 1180, 1100, 1024, 960, 900, 880, 820, 768, 700, 600, 480, 390, 360];
  for (const pg of ['dashboard', 'store', 'attendance', 'payroll', 'reporting', 'settings']) {
    await p.goto(`http://127.0.0.1:8032/temporary/Infinia/${pg}.html`); await p.waitForTimeout(2200);
    const issues = [];
    for (const w of widths) {
      await p.setViewportSize({ width: w, height: 900 }); await p.waitForTimeout(250);
      const r = await p.evaluate(() => {
        const out = [];
        const main = document.querySelector('.main'); const mw = main ? main.getBoundingClientRect().width : 0;
        if (mw < Math.min(300, window.innerWidth - 20)) out.push(`content squeezed to ${Math.round(mw)}px`);
        if (document.documentElement.scrollWidth > window.innerWidth + 2) out.push(`page scrolls sideways (${document.documentElement.scrollWidth} > ${window.innerWidth})`);
        const card = document.getElementById('dash-store-card');
        if (card && card.offsetParent !== null) {
          const ws = [...card.querySelectorAll('.store-tile')].filter(t => t.offsetParent !== null && getComputedStyle(t).display !== 'none').map(t => Math.round(t.getBoundingClientRect().width));
          if (ws.length && Math.max(...ws) - Math.min(...ws) > 2) out.push('store section: tiles of different widths ' + [...new Set(ws)].join('/'));
        }
        for (const g of document.querySelectorAll('.dash-tiles, .dash-store-grid, .store-tiles')) {
          if (g.offsetParent === null) continue;
          const tiles = [...g.children].filter(c => c.offsetParent !== null && getComputedStyle(c).display !== 'none');
          const rows = {};
          for (const t of tiles) { const rc = t.getBoundingClientRect(); (rows[Math.round(rc.top)] ||= []).push(rc); }
          for (const [top, rs] of Object.entries(rows)) {
            const ws = rs.map(x => Math.round(x.width)), hs = rs.map(x => Math.round(x.height));
            if (Math.max(...ws) - Math.min(...ws) > 2) out.push(`${g.className}: uneven widths ${ws.join('/')}`);
            if (Math.max(...hs) - Math.min(...hs) > 2) out.push(`${g.className}: uneven heights ${hs.join('/')}`);
          }
          const allW = tiles.map(t => Math.round(t.getBoundingClientRect().width));
          if (allW.length && Math.min(...allW) < 180) out.push(`${g.className}: a tile only ${Math.min(...allW)}px wide`);
        }
        return out;
      });
      for (const x of r) issues.push(`${w}px: ${x}`);
    }
    if (issues.length) bad++;
    console.log(`${issues.length ? 'FAIL' : 'PASS'} ${pg}: ${widths.length} widths${issues.length ? '\n   ' + [...new Set(issues)].slice(0, 6).join('\n   ') : ''}`);
    await p.setViewportSize({ width: 1440, height: 900 });
  }
  for (const w of [1440, 1024, 820, 390]) { await p.goto('http://127.0.0.1:8032/temporary/Infinia/dashboard.html'); await p.setViewportSize({ width: w, height: 900 }); await p.waitForTimeout(1500); await p.screenshot({ path: S + `rs${w}.png`, fullPage: true }); }
  console.log(bad ? `${bad} page(s) with problems` : 'EVERY WIDTH LAYS OUT CLEANLY');
  await b.close();
})();
