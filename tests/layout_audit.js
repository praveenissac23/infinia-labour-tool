// Every page, tab and sub-tab, measured for wasted space and alignment:
//   * a vertical gap of more than 28px between two blocks of a screen
//   * a card with more than 60px of empty space under its last content
//   * blocks side by side whose heights differ by more than 24px (the
//     taller one leaves a hole under the shorter - the calendar problem)
//   * top-level blocks whose left edges do not line up
//   * anything wider than the screen (a sideways scroll)
// and a screenshot of each for the eye.
//   node tests/layout_audit.js [width] [height]
const { chromium } = require('playwright');
const fs = require('fs');
const W = +(process.argv[2] || 1440), H = +(process.argv[3] || 900);
const OUT = `/tmp/claude-0/shots/layout-${W}`;
fs.mkdirSync(OUT, { recursive: true });
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: W, height: H } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://127.0.0.1:8032/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  const plan = await p.evaluate(() => Object.values(ALL_PAGES).map(pg => ({ key: pg.key, tabs: pg.tabs.map(t => ({ id: t.id, label: t.label, subs: t.subs.map(s => ({ id: s.id, label: s.label })) })) })));
  const measure = () => p.evaluate(() => {
    const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 2 && r.height > 2 && cs.display !== 'none' && cs.visibility !== 'hidden' && !el.closest('.pg-hide'); };
    const scr = document.querySelector('.screen.active'); if (!scr) return { issues: ['no active screen'] };
    const issues = [];
    const top = [...scr.children].filter(vis).filter(el => !el.classList.contains('status-msg') || el.textContent.trim());
    // gaps between consecutive blocks (in flow order, vertically stacked)
    for (let i = 1; i < top.length; i++) {
      const a = top[i - 1].getBoundingClientRect(), c = top[i].getBoundingClientRect();
      const gap = c.top - a.bottom;
      if (gap > 28 && c.top > a.top) issues.push(`gap ${Math.round(gap)}px between "${label(top[i - 1])}" and "${label(top[i])}"`);
    }
    // left edges of top-level blocks
    const lefts = [...new Set(top.filter(el => getComputedStyle(el).position !== 'fixed').map(el => Math.round(el.getBoundingClientRect().left)))];
    if (lefts.length > 1 && Math.max(...lefts) - Math.min(...lefts) > 2) issues.push(`left edges differ: ${lefts.join(', ')}`);
    // side-by-side siblings with unequal heights, and cards with an empty tail
    scr.querySelectorAll('*').forEach(el => {
      if (!vis(el)) return;
      const cs = getComputedStyle(el);
      if ((cs.display === 'flex' && cs.flexDirection.startsWith('row')) || cs.display === 'grid') {
        const kids = [...el.children].filter(vis).filter(k => k.getBoundingClientRect().height > 60 && k.matches('.card, .bulk-bar, .toolbar, .hr-card, [class*="card"]'));
        const rows = {};
        kids.forEach(k => { const t = Math.round(k.getBoundingClientRect().top / 8); (rows[t] = rows[t] || []).push(k); });
        Object.values(rows).forEach(r => { if (r.length > 1) { const hs = r.map(k => k.getBoundingClientRect().height); if (Math.max(...hs) - Math.min(...hs) > 24) issues.push(`side-by-side heights ${hs.map(Math.round).join(' / ')} in "${label(el)}"`); } });
      }
      if (el.matches('.card') && el.getBoundingClientRect().height > 120) {
        const kids = [...el.children].filter(vis); if (!kids.length) return;
        const last = Math.max(...kids.map(k => k.getBoundingClientRect().bottom));
        const tail = el.getBoundingClientRect().bottom - last - parseFloat(cs.paddingBottom || 0);
        if (tail > 60) issues.push(`card "${label(el)}" has ${Math.round(tail)}px empty at the bottom`);
      }
    });
    if (document.documentElement.scrollWidth > window.innerWidth + 1) issues.push(`page scrolls sideways (${document.documentElement.scrollWidth} > ${window.innerWidth})`);
    return { issues: [...new Set(issues)] };
    function label(el) { const h = el.querySelector('h2,h3,strong,label'); return (el.id ? '#' + el.id + ' ' : '') + ((h && h.textContent.trim()) || el.className || el.tagName).toString().slice(0, 40); }
  });
  let total = 0, n = 0;
  for (const pg of plan) {
    await p.evaluate(k => pgGo(k), pg.key); await p.waitForTimeout(1500);
    for (const t of pg.tabs.length ? pg.tabs : [{ id: null, subs: [] }]) {
      if (t.id) { await p.evaluate(id => pgTab(id), t.id).catch(() => {}); await p.waitForTimeout(1300); }
      for (const s of t.subs.length ? t.subs : [null]) {
        if (s) { await p.evaluate(id => pgSub(id), s.id).catch(() => {}); await p.waitForTimeout(1300); }
        const name = [pg.key, t.label, s && s.label].filter(Boolean).join(' > ');
        const m = await measure(); n++;
        const file = `${OUT}/${String(n).padStart(2, '0')}-${name.replace(/[^a-z0-9]+/gi, '_')}.png`;
        await p.screenshot({ path: file });
        if (m.issues.length) { total += m.issues.length; console.log(`\n${name}`); m.issues.forEach(i => console.log('   - ' + i)); }
      }
    }
  }
  console.log(`\n${n} screens measured at ${W}x${H}; ${total} layout issue(s); script errors: ${errs.length ? errs.join(' | ') : 'none'}`);
  await b.close();
})();
