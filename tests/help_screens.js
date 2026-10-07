// Makes the Help pictures and checks every guide still fits the app.
//
//   DATABASE_URL=sqlite:////tmp/help.db nohup python3 tests/serve_like_nginx.py &
//   node tests/help_screens.js            (all guides)
//   node tests/help_screens.js lpo move   (only these)
//
// For each guide in portal/help/guides.js it signs in, walks the guide
// with "Show me" exactly as a user would, and saves one picture per step
// to portal/help/img/<id>-<n>.jpg, then writes portal/help/img/manifest.js.
// It FAILS - naming the guide and step - when a page, tab or button a
// guide points to is no longer there, so a guide cannot quietly go stale
// after the app changes. Rebuild the app afterwards:
//   python3 deploy/build_temporary_pages.py
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const B = process.env.HELP_BASE || 'http://127.0.0.1:8032';
const USER = process.env.HELP_USER || 'admin', PASS = process.env.HELP_PASS || 'changeme123';
const OUT = path.join(__dirname, '..', 'portal', 'help', 'img');
const only = process.argv.slice(2);

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 780 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/');
  await p.fill('#login-username', USER); await p.fill('#login-password', PASS); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  // A little of everything so the pictures are not empty lists.
  await p.evaluate(async () => {
    const post = (u, body) => apiCall(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).catch(e => null);
    const items = await apiCall('/store/items').catch(() => []);
    const it = (items || [])[0], it2 = (items || [])[1] || it;
    const sites = await apiCall('/sites').catch(() => []);
    const site = ((sites || [])[0] || {}).name || '';
    const today = new Date().toISOString().slice(0, 10);
    if (it) {
      const r = await post('/store/requests', { site, requested_by: 'Site engineer', urgency: 'normal', lines: [{ item_id: it.id, qty_requested: 20, unit: it.unit || 'pcs', purpose: 'Slab casting' }] });
      const r2 = await post('/store/requests', { site, requested_by: 'Foreman', urgency: 'urgent', lines: [{ item_id: it2.id, qty_requested: 50, unit: it2.unit || 'pcs', purpose: 'Block work' }] });
      if (r && r.lines) for (const l of r.lines) await post(`/store/request-lines/${l.id}/decision`, { decision: 'approved', reason: '' });
    }
    await post('/store/petty-cash', { date: today, description: 'Cash received', supplier: 'CASH/ADCB', received: 2000 });
    const inv = { date: today, client: 'Mr. Mohammed Ahmed', client_trn: '100234567800003', client_address: 'Dubai, UAE', project: '(B+G+1+R) Villa',
                  project_no: '906', plot: '6457380', location: 'Al Barsha South', work: 'Phase 2 Works', lines: [{ description: 'Phase 2 works - 30% progress', amount: 56339, vat: 5 }] };
    const yy = today.slice(2, 4);
    await post('/employees/accounts/invoices', { ...inv, kind: 'tax', number: `IC/${yy}/906/01` });
    await post('/employees/accounts/invoices', { ...inv, kind: 'proforma', number: `PI/${yy}/920/01`, project_no: '920', client: 'Mrs. Fatima Khalid' });
    await post('/store/petty-cash', { date: today, description: 'Water and ice for site', supplier: 'GRAND MART', site, paid: 150 });
  });
  await p.reload(); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);

  const guides = await p.evaluate(() => HELP_GUIDES.map(g => ({ id: g.id, title: g.title, n: g.steps.length, ok: HELP.allowed(g) })));
  const stale = [], made = {};
  let prev = {};
  try { const m = fs.readFileSync(path.join(OUT, 'manifest.js'), 'utf8').match(/HELP_IMGS = (\{.*?\});/s); if (m) prev = JSON.parse(m[1]); } catch (e) {}

  // ---- Every screen, button by button (portal/help/auto_guides.js) ----------
  // Nothing to write by hand: each tab of each page is opened, the buttons on
  // it are found, numbered on one picture and listed in plain words. A new
  // button or tab is in Help the next time this runs.
  const explain = (t, title) => {
    const x = t.replace(/\s+/g, ' ').trim(), l = x.toLowerCase(), more = title && title.trim() && title.trim().toLowerCase() !== l ? ` - ${title.trim()}` : '';
    if (/^preview/.test(l)) return `${x}: opens it on screen to read or print${more}.`;
    if (/export pdf|^pdf$/.test(l)) return `${x}: downloads it as a PDF${more}.`;
    if (/export excel|^excel$/.test(l)) return `${x}: downloads it as an Excel sheet${more}.`;
    if (/^save|^update|^set /.test(l)) return `${x}: keeps what you entered - nothing is kept until you press it${more}.`;
    if (/^\+\s*/.test(x)) return `${x}: adds a new ${x.replace(/^\+\s*(new\s+)?/i, '').toLowerCase()}${more}.`;
    if (/^(refresh|reload)/.test(l)) return `${x}: loads the latest figures${more}.`;
    if (/^(delete|remove)/.test(l)) return `${x}: removes it (it asks first)${more}.`;
    if (/^edit/.test(l)) return `${x}: change what is there${more}.`;
    if (/^print/.test(l)) return `${x}: prints it${more}.`;
    if (/^approve/.test(l)) return `${x}: approves it${more}.`;
    if (/^(reject|decline)/.test(l)) return `${x}: turns it down${more}.`;
    if (/^cancel/.test(l)) return `${x}: cancels it${more}.`;
    return `${x}${more ? more.replace(/^ - /, ': ') : ''}.`;
  };
  const autos = [];
  if (!only.length || only.includes('screens')) {
    const screens = await p.evaluate(() => {
      const out = [];
      for (const [key, cfg] of Object.entries(ALL_PAGES)) {
        if (key === 'people') {
          for (const [v, l] of [['register', 'Register'], ['vacation', 'Leave'], ['bday', 'Birthdays']])
            out.push({ id: 'scr-people-' + v, page: 'people', tab: 'people', title: `Staff > ${l}`, view: v });
          continue;
        }
        for (const t of cfg.tabs) {
          if (t.hidden) continue;
          if (t.subs.length) for (const sb of t.subs) out.push({ id: `scr-${key}-${t.id}-${sb.id}`, page: key, tab: t.id, sub: sb.id, title: `${cfg.title} > ${t.label} > ${sb.label}` });
          else out.push({ id: `scr-${key}-${t.id}`, page: key, tab: t.id, title: cfg.tabs.length > 1 ? `${cfg.title} > ${t.label}` : cfg.title });
        }
      }
      return out;
    });
    for (const sc of screens) {
      await p.evaluate(async sc => {
        HELP.endTour(); document.querySelectorAll('.help-drawer').forEach(d => d.classList.remove('open'));
        if (PAGE.key !== sc.page) pgGo(sc.page);
        await new Promise(r => setTimeout(r, 900));
        pgTab(sc.tab); await new Promise(r => setTimeout(r, 500));
        if (sc.sub) pgSub(sc.sub);
      }, sc);
      await p.waitForTimeout(2200);
      if (await p.evaluate(() => !!document.querySelector('.screen.active iframe'))) await p.waitForTimeout(2500);   // Staff, Access, Logins load in a frame
      if (sc.view) { await p.evaluate(v => { const f = document.getElementById('pg-staff-frame'); f && f.contentWindow.showView && f.contentWindow.showView(v); }, sc.view); await p.waitForTimeout(1500); }
      const found = await p.evaluate(() => {
        const vis = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' && !el.closest('.pg-hide');
        const scr = document.querySelector('.screen.active'); if (!scr) return { frame: false, items: [] };
        const fr = scr.querySelector('iframe'), doc = fr ? fr.contentDocument : document, root = fr ? doc.body : scr;
        const off = fr ? fr.getBoundingClientRect() : { left: 0, top: 0 };
        const seen = new Set(), items = [];
        for (const el of root.querySelectorAll('button, a.btn, .btn')) {
          if (!vis(el) || el.disabled || el.closest('.dlg, .help-drawer, .ask')) continue;
          const text = (el.textContent || '').replace(/\s+/g, ' ').trim(); if (!text || text.length > 40 || seen.has(text.toLowerCase())) continue;
          const r = el.getBoundingClientRect(); if (r.top + off.top > innerHeight - 10 || r.width < 8) continue;
          let sel = null;
          if (!fr) {
            if (el.id) sel = '#' + el.id;
            else if (el.getAttribute('onclick')) { const c = `${el.tagName.toLowerCase()}[onclick="${el.getAttribute('onclick').replace(/"/g, '\\"')}"]`;
              try { if ([...document.querySelectorAll(c)].filter(vis).length === 1) sel = c; } catch (e) {} }
          }
          seen.add(text.toLowerCase());
          items.push({ text, title: el.getAttribute('title') || '', sel, x: r.left + off.left, y: r.top + off.top });
          if (items.length >= 12) break;
        }
        // Numbered badges on the picture, matching the list.
        items.forEach((it, i) => { const d = document.createElement('div'); d.className = 'help-auto-badge';
          d.style.cssText = `position:fixed;left:${Math.max(2, it.x - 9)}px;top:${Math.max(2, it.y - 9)}px;z-index:99999;width:20px;height:20px;border-radius:50%;background:#C0392B;color:#fff;font:700 11px/20px Arial;text-align:center;box-shadow:0 0 0 2px #fff`;
          d.textContent = i + 1; document.body.appendChild(d); });
        return { frame: !!fr, items };
      });
      await p.screenshot({ path: path.join(OUT, `${sc.id}-1.jpg`), type: 'jpeg', quality: 68 });
      await p.evaluate(() => document.querySelectorAll('.help-auto-badge').forEach(d => d.remove()));
      const go = { page: sc.page, tab: sc.tab, ...(sc.sub ? { sub: sc.sub } : {}) };
      const first = { say: `This is ${sc.title}. The numbers on the picture match the list below.` };
      if (sc.view) first.run = `var f=document.getElementById('pg-staff-frame'); if (f && f.contentWindow.showView) f.contentWindow.showView('${sc.view}');`;
      autos.push({ id: sc.id, area: 'Every screen', title: sc.title, auto: true,
        words: `${sc.title} ${found.items.map(i => i.text).join(' ')} screen buttons what is`.toLowerCase().replace(/[^a-z0-9 ]+/g, ' '),
        go, steps: [first, ...found.items.map((it, i) => ({ say: `${i + 1}. ${explain(it.text, it.title)}`, ...(it.sel ? { el: it.sel } : {}) }))] });
      made[sc.id] = [1];
      console.log(`screen ${sc.id} (${found.items.length} buttons)`);
    }
    fs.writeFileSync(path.join(OUT, '..', 'auto_guides.js'),
      `// Written by tests/help_screens.js - one guide for every screen, its buttons numbered. Do not edit by hand.\nwindow.HELP_AUTO = ${JSON.stringify(autos, null, 1)};\n`);
  } else for (const k of Object.keys(prev)) if (k.startsWith('scr-')) made[k] = prev[k];
  for (const g of guides) {
    if (only.length && !only.includes(g.id)) { if (prev[g.id]) made[g.id] = prev[g.id]; continue; }
    if (!g.ok) { stale.push(`${g.id}: its page / tab is not in the app any more`); continue; }
    await p.evaluate(id => { HELP.endTour(); document.querySelectorAll('.help-drawer').forEach(d => d.classList.remove('open')); HELP.tour(HELP_GUIDES.find(x => x.id === id)); }, g.id);
    await p.waitForTimeout(2600);
    made[g.id] = [];
    for (let i = 0; i < g.n; i++) {
      await p.evaluate(i => HELP.step(i), i);
      await p.waitForTimeout(1100);
      const st = await p.evaluate(() => ({ missing: HELP.state && HELP.state.missing, sel: HELP.state && HELP.state.g.steps[HELP.state.i].el }));
      if (st.missing) stale.push(`${g.id} step ${i + 1}: "${st.sel}" not found`);
      // The part that matters - the circled button and the note - large
      // enough to read in the side panel; the whole screen when there is
      // nothing circled.
      const clip = await p.evaluate(() => {
        const W = innerWidth, H = innerHeight, rs = [];
        const ring = document.querySelector('.help-ring'), tip = document.querySelector('.help-bubble');
        if (!ring || ring.style.display === 'none') return null;
        for (const el of [ring, tip]) if (el) rs.push(el.getBoundingClientRect());
        let x1 = Math.min(...rs.map(r => r.left)) - 60, y1 = Math.min(...rs.map(r => r.top)) - 60;
        let x2 = Math.max(...rs.map(r => r.right)) + 60, y2 = Math.max(...rs.map(r => r.bottom)) + 60;
        const grow = (a, b, min, max) => { const d = min - (b - a); if (d > 0) { a -= d / 2; b += d / 2; } if (a < 0) { b -= a; a = 0; } if (b > max) { a -= b - max; b = max; } return [Math.max(0, a), Math.min(max, b)]; };
        [x1, x2] = grow(x1, x2, 820, W); [y1, y2] = grow(y1, y2, 480, H);
        return { x: Math.round(x1), y: Math.round(y1), width: Math.round(x2 - x1), height: Math.round(y2 - y1) };
      });
      await p.screenshot({ path: path.join(OUT, `${g.id}-${i + 1}.jpg`), type: 'jpeg', quality: 70, ...(clip ? { clip } : {}) });
      made[g.id].push(i + 1);
    }
    await p.evaluate(() => HELP.endTour());
    console.log(`${stale.some(s => s.startsWith(g.id + ' ')) ? 'STALE' : 'ok   '} ${g.id} (${g.n} steps)`);
  }
  // Pictures of guides that no longer exist are removed.
  for (const f of fs.readdirSync(OUT)) {
    const m = f.match(/^(.*)-(\d+)\.jpg$/);
    if (m && !(made[m[1]] || []).includes(+m[2])) fs.unlinkSync(path.join(OUT, f));
  }
  const v = crypto.createHash('sha1').update(JSON.stringify(made) + Date.now()).digest('hex').slice(0, 10);
  fs.writeFileSync(path.join(OUT, 'manifest.js'),
    `// Written by tests/help_screens.js - which guide has which step pictures.\nwindow.HELP_IMGS = ${JSON.stringify(made)};\nwindow.HELP_IMGS_V = "${v}";\n`);
  if (errs.length) console.log('script errors:', errs);
  if (stale.length) { console.log('\nOUT OF DATE - fix these guides in portal/help/guides.js:\n  ' + stale.join('\n  ')); }
  else console.log(`\nALL ${Object.keys(made).length} GUIDES MATCH THE APP`);
  await b.close(); process.exit(stale.length ? 1 : 0);
})();
