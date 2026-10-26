// No empty band under a list: on a computer the last table on a page runs down to the bottom of the window,
// the page itself does not scroll, and the page's Save / submit floats at the bottom of the screen beside INFI.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/band_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  for (const [w, h] of [[1440, 900], [1000, 650], [1728, 1000]]) {
    const p = await (await br.newContext({ viewport: { width: w, height: h } })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
    await p.goto(B + '/?p=attendance'); await sleep(3500);
    await p.evaluate(() => { const d = document.getElementById('date-picker'); if (d) { d.value = '2026-10-25'; d.dispatchEvent(new Event('change')); } }); await sleep(2500);
    const m = await p.evaluate(() => { const g = document.querySelector('#grid-table').closest('.grid-wrap'), r = g.getBoundingClientRect(), s = document.getElementById('floating-save-btn'), sr = s.getBoundingClientRect(), ir = document.getElementById('infi-btn').getBoundingClientRect();
      return { gap: Math.round(innerHeight - r.bottom), scrolls: g.scrollHeight > g.clientHeight, page: document.scrollingElement.scrollHeight - innerHeight, save: sr.width > 0 && sr.bottom <= innerHeight && innerHeight - sr.bottom < 30, clear: !(ir.width && sr.right > ir.left && sr.bottom > ir.top), mh: g.style.maxHeight }; });
    ck(`${w}x${h} attendance: the list reaches the bottom (gap ${m.gap}px), page does not scroll`, (m.gap >= 0 && m.gap <= 24 && m.page <= 2) || m.mh === '260px', m);
    ck(`${w}x${h} attendance: Save Attendance floats at the screen bottom, clear of INFI`, m.save && m.clear, m);
    await p.screenshot({ path: `${SH}att_${w}.png` });
    // a few other lists
    for (const pg of ['payroll', 'reports', 'store', 'accounts', 'expiry', 'settings', 'admin']) {
      await p.goto(`${B}/?p=${pg}`); await sleep(3000);
      const f = await p.evaluate(() => { const fs = [...document.querySelectorAll('.btn.fab')].filter(b => b.getClientRects().length); const ir = document.getElementById('infi-btn').getBoundingClientRect();
        return fs.map(b => { const r = b.getBoundingClientRect(); return { t: b.textContent.trim(), bottom: Math.round(innerHeight - r.bottom), clear: !(ir.width && r.right > ir.left && r.bottom > ir.top) }; }); });
      ck(`${w}x${h} ${pg}: at most one floating save, at the screen bottom, clear of INFI ${JSON.stringify(f.map(x => x.t))}`, f.length <= 1 && f.every(x => x.bottom >= 0 && x.bottom < 30 && x.clear), f);
      if (w === 1440) await p.screenshot({ path: `${SH}${pg}.png` });
      const r = await p.evaluate(() => { const gs = [...document.querySelectorAll('.grid-wrap')].filter(g => g.offsetParent && g.dataset.mh !== undefined); return gs.map(g => ({ gap: Math.round(innerHeight - g.getBoundingClientRect().bottom), full: g.scrollHeight > g.clientHeight })); });
      ck(`${w}x${h} ${pg}: a long list ends at the window bottom`, r.every(x => !x.full || (x.gap >= 0 && x.gap <= 30)), r);
    }
    for (const [pg, fn] of [['store', "storeGo('give')"], ['store', "storeGo('returns')"], ['store', "storeGo('arrive')"], ['store', "storeGo('other')"], ['store', "storeGo('give'); [...document.querySelectorAll('#store-give .btn-primary')].find(b => /Give out/.test(b.textContent)).click()"], ['store', "storeGo('arrive'); [...document.querySelectorAll('#store-arrive .btn-primary')].find(b => /direct purchase/.test(b.textContent)).click()"]]) {
      await p.goto(`${B}/?p=${pg}`); await sleep(3000); await p.evaluate(fn).catch(() => {}); await sleep(1200);
      const f = await p.evaluate(() => { const fs = [...document.querySelectorAll('.btn.fab')].filter(b => b.getClientRects().length); const ir = document.getElementById('infi-btn').getBoundingClientRect();
        const c = [...document.querySelectorAll('#app-screen .screen.active .btn.btn-primary')].filter(b => b.getClientRects().length).map(b => b.textContent.trim());
        return { c, f: fs.map(b => { const r = b.getBoundingClientRect(); return { t: b.textContent.trim(), bottom: Math.round(innerHeight - r.bottom), clear: !(ir.width && r.right > ir.left && r.bottom > ir.top) }; }) }; });
      ck(`${w}x${h} ${fn}: floating ${JSON.stringify(f.f.map(x => x.t))} of ${JSON.stringify(f.c)}`, f.f.length <= 1 && f.f.every(x => x.bottom >= 0 && x.bottom < 30 && x.clear), f);
      if (w === 1440) await p.screenshot({ path: `${SH}${fn.replace(/\W/g, '')}.png` });
    }
    ck(`${w}x${h} no page errors`, !errs.length, errs);
  }
  // the other pages (staff, logins/roles, estimation, Trello) follow the same rule
  {
    const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
    for (const [u, fn] of [['/portal/people.html', "openPerson(P.rows[0].emp_no).then(() => openEdit())"], ['/portal/access.html?view=roles', "0"], ['/portal/est-app.html?view=projects', "0"], ['/portal/boards.html', "0"]]) {
      await p.goto(B + u); await sleep(3000); await p.evaluate(fn).catch(() => {}); await sleep(1500);
      const f = await p.evaluate(() => { const fs = [...document.querySelectorAll('.btn.fab')].filter(b => b.getClientRects().length);
        const c = [...document.querySelectorAll('.btn.btn-primary')].filter(b => b.getClientRects().length).map(b => b.textContent.trim());
        return { c, f: fs.map(b => ({ t: b.textContent.trim(), bottom: Math.round(innerHeight - b.getBoundingClientRect().bottom) })) }; });
      ck(`${u}: floating ${JSON.stringify(f.f.map(x => x.t))} of ${JSON.stringify(f.c)}`, f.f.length <= 1 && f.f.every(x => x.bottom >= 0 && x.bottom < 30), f);
      await p.screenshot({ path: `${SH}${u.replace(/\W/g, '')}.png` });
    }
    ck('portal pages: no page errors', !errs.length, errs);
  }
  // phone: unchanged - the page scrolls and the round save button is there
  const ph = await (await br.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  await ph.goto(B + '/'); await ph.fill('#login-username', 'admin'); await ph.fill('#login-password', 'changeme123'); await ph.evaluate('doLogin()'); await sleep(3000);
  await ph.goto(B + '/?p=attendance'); await sleep(3500);
  ck('phone: floating save button still there', await ph.evaluate(() => getComputedStyle(document.getElementById('floating-save-btn')).display !== 'none'));
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
