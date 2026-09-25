// One login at a time: sign in, walk every page, every tab, every sub-tab.
// On every animation frame from the first paint, record which menu
// entries, tabs and screens are visible; anything visible that the login
// does not end up with is a flicker. Every click is checked for landing.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/temporary/Infinia/';
const LOGINS = [[process.argv[2], process.argv[3]]];
const PAGES = ['dashboard', 'attendance', 'people', 'payroll', 'store', 'reporting', 'settings'];
const INIT = `
  window.__frames = []; window.__seen = new Set();
  (function tick() {
    try {
      const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none'; };
      const menu = [...document.querySelectorAll('.pg-side .pg-item[data-page]')].filter(vis).map(e => 'menu:' + e.dataset.page);
      const tabs = [...document.querySelectorAll('#pg-tabs .pg-tab')].filter(vis).map(e => 'tab:' + e.dataset.tab);
      const screens = [...document.querySelectorAll('.screen')].filter(vis).map(e => 'screen:' + e.id);
      const login = document.getElementById('login-screen') && vis(document.getElementById('login-screen')) ? ['login'] : [];
      const legacy = document.getElementById('legacy-sidebar') && vis(document.getElementById('legacy-sidebar')) ? ['legacy-sidebar'] : [];
      window.__frames.push([performance.now(), ...menu, ...tabs, ...screens, ...login, ...legacy]);
    } catch (e) {}
    requestAnimationFrame(tick);
  })();`;
(async () => {
  const b = await chromium.launch();
  let bad = 0; const out = [];
  const say = (ok, msg, d) => { if (!ok) bad++; out.push((ok ? '  ok   ' : '  FAIL ') + msg + (ok || d === undefined ? '' : '   ' + JSON.stringify(d))); };
  for (const [user, pw] of LOGINS) {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); await ctx.addInitScript(INIT);
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
    out.push(`\n== ${user}`);
    await p.goto(BASE + 'dashboard.html'); await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin(); 0'); await p.waitForTimeout(3000);
    const allowedMenu = new Set(await p.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item[data-page]')].filter(e => e.style.display !== 'none').map(e => e.dataset.page)));
    say(allowedMenu.size > 0, `${user}: menu after sign-in = ${[...allowedMenu].join(', ')}`);
    // walk every page this login has, then every page it has not
    for (const pg of PAGES) {
      const file = pg === 'reporting' ? 'reporting' : pg;
      await p.goto(BASE + file + '.html'); await p.waitForTimeout(2500);
      const landed = p.url().split('/').pop().split('#')[0];
      const frames = await p.evaluate('window.__frames');
      const finalMenu = new Set(await p.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item[data-page]')].filter(e => e.style.display !== 'none' && e.style.visibility !== 'hidden').map(e => 'menu:' + e.dataset.page)));
      const finalTabs = new Set(await p.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].map(e => 'tab:' + e.dataset.tab)));
      const finalScreen = await p.evaluate(() => { const s = document.querySelector('.screen.active'); return s ? 'screen:' + s.id : ''; });
      // flicker = anything drawn in an earlier frame that is not in the final state
      const stray = new Set(); let multiScreen = 0, loginFlash = 0, legacy = 0;
      for (const f of frames) {
        const items = f.slice(1);
        if (items.includes('login')) loginFlash++;
        if (items.includes('legacy-sidebar')) legacy++;
        if (items.filter(x => x.startsWith('screen:')).length > 1) multiScreen++;
        for (const x of items) { if (x.startsWith('menu:') && !finalMenu.has(x)) stray.add(x); if (x.startsWith('tab:') && !finalTabs.has(x)) stray.add(x); if (x.startsWith('screen:') && x !== finalScreen) stray.add(x); }
      }
      const expectedHere = allowedMenu.has(pg === 'reporting' ? 'reports' : pg);
      if (expectedHere) say(landed === file + '.html', `${user}: ${file}.html opens here (${finalScreen}, tabs ${[...finalTabs].map(t => t.slice(4)).join('/') || '-'})`, landed);
      else say(landed !== file + '.html' || finalScreen, `${user}: ${file}.html not in menu -> sent to ${landed}`);
      say(stray.size === 0 && loginFlash === 0 && legacy === 0 && multiScreen === 0, `${user}: ${file}.html no flicker (${frames.length} frames)`, { stray: [...stray], loginFlash, legacy, multiScreen });
      if (landed !== file + '.html') continue;
      // every tab, then every sub-tab
      const tabs = await p.locator('#pg-tabs .pg-tab').allTextContents();
      for (let i = 0; i < tabs.length; i++) {
        const before = p.url();
        await p.locator('#pg-tabs .pg-tab').nth(i).click(); await p.waitForTimeout(900);
        if (p.url().split('/').pop().split('#')[0] !== file + '.html') { say(true, `${user}: ${file} > ${tabs[i]} -> ${p.url().split('/').pop()}`); await p.goto(before); await p.waitForTimeout(1500); continue; }
        const active = await p.evaluate(() => { const s = document.querySelector('.screen.active'); return s && s.id; });
        say(!!active && await p.locator('#pg-tabs .pg-tab.active').textContent() === tabs[i], `${user}: ${file} > ${tabs[i]} shows ${active}`);
        const subs = await p.locator('#pg-sub .pg-subtab').allTextContents();
        for (let k = 0; k < subs.length; k++) {
          await p.locator('#pg-sub .pg-subtab').nth(k).click(); await p.waitForTimeout(900);
          const a = await p.evaluate(() => { const s = document.querySelector('.screen.active'); return s && s.id; });
          const ok = !!a && await p.locator('#pg-sub .pg-subtab.active').textContent() === subs[k] && await p.locator('#pg-tabs .pg-tab.active').textContent() === tabs[i];
          say(ok, `${user}: ${file} > ${tabs[i]} > ${subs[k]} shows ${a}`);
        }
      }
    }
    // menu links
    for (const pg of allowedMenu) {
      await p.goto(BASE + 'dashboard.html'); await p.waitForTimeout(2000);
      const st = await p.evaluate(pg => { const e = document.querySelector(`.pg-side .pg-item[data-page="${pg}"]`); const cs = getComputedStyle(e); return { display: cs.display, vis: cs.visibility, login: getComputedStyle(document.getElementById('login-screen')).display, user: (typeof CURRENT_USERNAME !== 'undefined') && CURRENT_USERNAME }; }, pg);
      if (st.display === 'none' || st.vis === 'hidden' || st.login !== 'none') { say(false, `${user}: menu ${pg} hidden on dashboard.html`, st); await p.screenshot({ path: '/tmp/claude-0/-home-claude/80e871d8-70e2-5c6a-a360-434939dea359/scratchpad/hidden.png' }); continue; }
      const shown = await p.evaluate(pg => { const e = document.querySelector(`.pg-side .pg-item[data-page="${pg}"]`); const r = e.getBoundingClientRect(); return { w: r.width, h: r.height, login: getComputedStyle(document.getElementById('login-screen')).display, app: getComputedStyle(document.getElementById('app-screen')).display }; }, pg);
      if (!shown.w) { say(false, `${user}: menu ${pg} not visible on dashboard.html`, shown); continue; }
      await p.click(`.pg-side .pg-item[data-page="${pg}"]`); await p.waitForTimeout(1500);
      say(p.url().includes((pg === 'reports' ? 'reporting' : pg) + '.html'), `${user}: menu ${pg} -> ${p.url().split('/').pop()}`);
    }
    say(errs.length === 0, `${user}: no script errors`, errs.slice(0, 3));
    await ctx.close();
  }
  console.log(out.join('\n')); console.log(bad ? `\n${bad} FAILED` : '\nALL GOOD');
  await b.close();
})();
