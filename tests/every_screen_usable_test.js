// Every screen, every tab and sub-tab (admin): the boxes can be typed in, the dropdowns open with choices, and nothing
// lies on top of a box or button so a click misses it. No page errors. (2 Nov 2026 - "not able to type, dropdown not coming")
//   BASE=http://127.0.0.1:8032 node tests/every_screen_usable_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 600))); };
(async () => {
  const br = await chromium.launch();
  for (const vw of [{ width: 1440, height: 900 }, { width: 1280, height: 760 }]) {
    const p = await (await br.newContext({ viewport: vw })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/'); await sleep(2500); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3500);
    const pages = await p.evaluate(() => Object.values(ALL_PAGES).map(pg => ({ key: pg.key, tabs: pg.tabs.filter(t => !t.hidden).map(t => ({ id: t.id, subs: (t.subs || []).filter(s => !s.hidden).map(s => s.id) })) })));
    for (const pg of pages) for (const t of pg.tabs) for (const s of (t.subs.length ? t.subs : [null])) {
      const where = `${vw.width} ${pg.key}/${t.id}${s ? ':' + s : ''}`; const e0 = errs.length;
      await p.evaluate(([a, b, c]) => { window.checkBuild = () => {}; const z = document.getElementById('build-bar'); if (z) z.remove(); c ? pgGo(a, b + ':' + c) : pgGo(a, b); }, [pg.key, t.id, s]); await sleep(2400);
      const r = await p.evaluate(() => {
        const out = { covered: [], noOpts: [], frames: 0 };
        const vis = e => { const rc = e.getBoundingClientRect(); const cs = getComputedStyle(e); return rc.width > 4 && rc.height > 4 && cs.visibility !== 'hidden' && rc.bottom > 0 && rc.top < innerHeight && rc.right > 0 && rc.left < innerWidth; };
        const name = e => (e.id ? '#' + e.id : '') + (e.name ? '[' + e.name + ']' : '') + ' ' + (e.placeholder || e.textContent || '').trim().slice(0, 30);
        const scan = (doc, off) => {
          const els = [...doc.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), select, textarea, button')].filter(e => !e.disabled && vis(e) && !e.closest('[aria-hidden=true]'));
          for (const e of els) {
            const rc = e.getBoundingClientRect(); const x = rc.left + Math.min(rc.width / 2, 20), y = rc.top + rc.height / 2;
            const top = doc.elementFromPoint(x, y);
            if (top && top !== e && !e.contains(top) && !top.contains(e) && !(top.tagName === 'LABEL' && top.control === e)) {
              // a floating helper (INFI, help button, toast, the floating Save) lying over the corner is the known exception only if the box is still clickable elsewhere
              const t2 = doc.elementFromPoint(rc.left + rc.width / 2, y), t3 = doc.elementFromPoint(rc.right - 6, y);
              const ok2 = [t2, t3].some(tt => tt && (tt === e || e.contains(tt)));
              if (!ok2) out.covered.push(name(e) + ' under ' + (top.id ? '#' + top.id : top.className || top.tagName).toString().slice(0, 40));
            }
            if (e.tagName === 'SELECT' && !e.options.length) out.noOpts.push(name(e));
          }
          doc.querySelectorAll('iframe').forEach(f => { try { if (vis(f) && f.contentDocument) { out.frames++; scan(f.contentDocument); } } catch (x) {} });
        };
        scan(document); return out;
      });
      // type into the first visible empty text box and check it took (then put it back)
      const typed = await p.evaluate(() => {
        const vis = e => { const rc = e.getBoundingClientRect(); return rc.width > 4 && rc.height > 4 && getComputedStyle(e).visibility !== 'hidden' && rc.top > 0 && rc.top < innerHeight; };
        const scr = document.querySelector('#app-screen .screen.active') || document;
        const e = [...scr.querySelectorAll('input[type=text], input[type=search], input:not([type]), textarea')].find(x => !x.disabled && !x.readOnly && !x.value && vis(x));
        if (!e) return null; e.setAttribute('data-typetest', '1'); return e.id || e.placeholder || 'box';
      });
      if (typed) {
        const loc = p.locator('[data-typetest="1"]').first();
        let got = '';
        try { await loc.click({ timeout: 2500 }); await p.keyboard.type('Zq7', { delay: 15 }); got = await loc.inputValue(); await loc.fill(''); await loc.dispatchEvent('input'); } catch (x) { got = 'ERR ' + x.message.split('\n')[0].slice(0, 120); }
        await p.evaluate(() => { const e = document.querySelector('[data-typetest]'); if (e) e.removeAttribute('data-typetest'); }); await p.keyboard.press('Escape');
        ck(`${where}: can type in "${typed}"`, got === 'Zq7', got);
      }
      // something floating (Save, INFI) over a row is fine only if the row can be scrolled clear of it
      let still = [];
      if (r.covered.length) still = await p.evaluate(() => {
        const out = [];
        const els = [...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), select, textarea, button')].filter(e => !e.disabled && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
        const hit = e => { const rc = e.getBoundingClientRect(); if (rc.bottom < 0 || rc.top > innerHeight) return true; const y = rc.top + rc.height / 2;
          return [rc.left + 6, rc.left + rc.width / 2, rc.right - 6].some(x => { const t = document.elementFromPoint(x, y); return t && (t === e || e.contains(t) || (t.tagName === 'LABEL' && t.control === e)); }); };
        for (const e of els) { if (hit(e)) continue; e.scrollIntoView({ block: 'center' }); if (!hit(e)) { const rc = e.getBoundingClientRect(); const t = document.elementFromPoint(rc.left + rc.width / 2, rc.top + rc.height / 2);
          out.push(((e.id ? '#' + e.id + ' ' : '') + e.textContent.trim().slice(0, 25)) + ' under ' + (t ? (t.id ? '#' + t.id : String(t.className).slice(0, 30)) : '?')); } }
        scrollTo(0, 0); return out; });
      ck(`${where}: nothing covers a box or button (after scrolling it into view)`, !still.length, { still: still.slice(0, 8), atFirst: r.covered.slice(0, 4) });
      ck(`${where}: every dropdown has choices`, !r.noOpts.length, r.noOpts.slice(0, 8));
      ck(`${where}: no page errors`, errs.length === e0, errs.slice(e0, e0 + 3));
      await p.evaluate(() => { document.querySelectorAll('.modal.show, .overlay.show').forEach(m => m.classList.remove('show')); });
    }
    await p.context().close();
  }
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await br.close(); process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
