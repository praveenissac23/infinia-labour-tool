// Every page, every tab, every sub-tab - clicked for real, desktop and phone.
// Each click must land; the red pill/line must end up exactly under the
// chosen tab; nothing may still be moving after the animation; every
// visible button must be clickable (nothing covering it); no page errors;
// no big layout jumps (flicker).
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0, checks = 0; const fails = [];
const ck = (n, ok, info) => { checks++; if (!ok) { bad++; fails.push(n + '  ' + JSON.stringify(info)); } };
(async () => {
  const b = await chromium.launch();
  for (const vp of [{ w: 1440, h: 900, tag: 'desktop' }, { w: 1280, h: 760, tag: 'laptop' }, { w: 390, h: 844, tag: 'phone' }]) {
    const p = await b.newPage({ viewport: { width: vp.w, height: vp.h } }); const errs = []; p.on('pageerror', e => errs.push(String(e.message||e)+' '+String(e.stack||'').slice(0,300)));
    await p.addInitScript(() => { window.__cls = []; try { new PerformanceObserver(l => l.getEntries().forEach(e => { if (!e.hadRecentInput) window.__cls.push(e.value); })).observe({ type: 'layout-shift', buffered: true }); } catch (e) {} });
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2000);
    const pages = await p.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item[data-page]')].map(x => x.dataset.page));
    const settle = async () => { await p.waitForTimeout(650); };
    const state = (where) => p.evaluate((where) => {
      const out = { where };
      const chk = (boxId, sel, cls) => {
        const box = document.getElementById(boxId), a = box && box.querySelector(sel), el = box && box.querySelector(':scope > .' + cls);
        if (!a || !a.offsetWidth) return null;
        if (!el || el.style.display === 'none') return 'missing';
        const r1 = a.getBoundingClientRect(), r2 = el.getBoundingClientRect();
        return Math.abs(r1.left - r2.left) < 2.5 && Math.abs(r1.width - r2.width) < 2.5 ? 'ok' : `off ${Math.round(r1.left)}/${Math.round(r2.left)} ${Math.round(r1.width)}/${Math.round(r2.width)}`;
      };
      out.pill = chk('pg-tabs', '.pg-tab.active', 'mo-pill'); out.line = chk('pg-sub', '.pg-subtab.active', 'mo-line');
      out.moving = document.getAnimations().filter(a => a.playState === 'running' && !(a.effect && a.effect.getTiming && a.effect.getTiming().iterations === Infinity) && !(a.effect && a.effect.target && (a.effect.target.closest('.mo-toast') || a.effect.target.classList.contains('mo-skel') || a.effect.target.classList.contains('help-tip')))).map(a => (a.effect && a.effect.target && (a.effect.target.id || a.effect.target.className)) || '?').slice(0, 3);
      const scr = document.querySelector('.screen.active'); out.screen = scr ? scr.id : null; out.h = scr ? scr.offsetHeight : 0;
      // every visible button in the viewport can be hit at its centre
      const covered = [];
      for (const btn of document.querySelectorAll('.content button, .content .btn, #pg-tabs .pg-tab, #pg-sub .pg-subtab')) {
        const r = btn.getBoundingClientRect(); if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
        const cs = getComputedStyle(btn); if (cs.visibility === 'hidden' || cs.pointerEvents === 'none' || btn.disabled) continue;
        const x = Math.min(innerWidth - 1, Math.max(0, r.left + r.width / 2)), y = Math.min(innerHeight - 1, Math.max(0, r.top + r.height / 2));
        const hit = document.elementFromPoint(x, y);
        if (hit && !(btn === hit || btn.contains(hit) || hit.contains(btn) || hit.closest('.mo-toast') || hit.closest('.help-i') || hit.closest('.infi-fab, #infi-btn, .infi'))) covered.push((btn.textContent || '').trim().slice(0, 20) + ' <- ' + (hit.id || hit.className || hit.tagName).toString().slice(0, 30));
      }
      out.covered = covered.slice(0, 4);
      out.cls = (window.__cls || []).reduce((a, v) => a + v, 0); window.__cls = [];
      return out;
    }, where);
    let steps = 0;
    for (const pg of pages) {
      const item = p.locator(`.pg-side .pg-item[data-page="${pg}"]`);
      if (!(await item.isVisible())) { await p.evaluate(k => pgGo(k), pg); } else await item.click();
      await settle();
      const tabs = await p.locator('#pg-tabs .pg-tab').count();
      for (let ti = 0; ti < Math.max(1, tabs); ti++) {
        const tab = p.locator('#pg-tabs .pg-tab').nth(ti);
        if (tabs) {
          const label = (await tab.textContent()).trim();
          await tab.scrollIntoViewIfNeeded(); await tab.click(); await settle(); steps++;
          const act = await p.evaluate(() => { const a = document.querySelector('#pg-tabs .pg-tab.active'); return a ? a.textContent.trim() : ''; });
          ck(`${vp.tag} ${pg} > ${label}: click lands`, act === label, act);
        }
        const subs = await p.locator('#pg-sub .pg-subtab').count();
        for (let si = 0; si < subs; si++) {
          const sb = p.locator('#pg-sub .pg-subtab').nth(si); const sl = (await sb.textContent()).trim();
          await sb.scrollIntoViewIfNeeded(); await sb.click(); await settle(); steps++;
          const sact = await p.evaluate(() => { const a = document.querySelector('#pg-sub .pg-subtab.active'); return a ? a.textContent.trim() : ''; });
          ck(`${vp.tag} ${pg} > tab ${ti} > ${sl}: click lands`, sact === sl, sact);
          const s = await state(`${pg}/${ti}/${sl}`);
          ck(`${vp.tag} ${s.where}: line under tab`, s.line === 'ok' || s.line === null, s.line);
          ck(`${vp.tag} ${s.where}: pill under tab`, s.pill === 'ok' || s.pill === null, s.pill);
          ck(`${vp.tag} ${s.where}: nothing still moving`, !s.moving.length, s.moving);
          ck(`${vp.tag} ${s.where}: buttons not covered`, !s.covered.length, s.covered);
          ck(`${vp.tag} ${s.where}: no big jump`, s.cls < 0.25, s.cls);
        }
        if (!subs) {
          const s = await state(`${pg}/${ti}`);
          ck(`${vp.tag} ${s.where}: pill under tab`, s.pill === 'ok' || s.pill === null, s.pill);
          ck(`${vp.tag} ${s.where}: nothing still moving`, !s.moving.length, s.moving);
          ck(`${vp.tag} ${s.where}: buttons not covered`, !s.covered.length, s.covered);
          ck(`${vp.tag} ${s.where}: screen drawn`, s.h > 40, s.h);
          ck(`${vp.tag} ${s.where}: no big jump`, s.cls < 0.25, s.cls);
        }
      }
    }
    // fast clicking: three tabs in quick succession must end on the last one, pill under it
    await p.evaluate(k => pgGo(k), 'accounts'); await settle();
    const tl = p.locator('#pg-tabs .pg-tab'); const n = await tl.count();
    if (n >= 3) { await tl.nth(1).click(); await tl.nth(2).click(); await tl.nth(0).click(); await p.waitForTimeout(800);
      const s = await state('fast clicks'); ck(`${vp.tag} fast clicks end on the last tab with the pill under it`, s.pill === 'ok', s.pill); }
    ck(`${vp.tag}: no page errors`, !errs.length, errs.slice(0, 3));
    ck(`${vp.tag}: no sideways scroll`, await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    console.log(`${vp.tag}: ${steps} tab clicks`);
    await p.close();
  }
  await b.close();
  fails.slice(0, 80).forEach(f => console.log('FAIL ' + f));
  console.log(`${checks} checks, ${bad} failed`); process.exit(bad ? 1 : 0);
})();
