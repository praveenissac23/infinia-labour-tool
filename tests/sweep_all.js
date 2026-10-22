// The whole-app sweep: every page, tab and sub-tab, as a given login, at a given width. On each screen:
//   errors (script, console, HTTP >= 400), time to settle, repeated API calls, layout shift (flicker),
//   sideways scroll, mixed fonts, overlapping controls, clipped text, table totals that don't add up,
//   header sorting that doesn't sort, then every Preview opened and checked the same way, and every
//   harmless button clicked (filters, pills, toggles, exports) - anything that saves, sends or deletes is left.
//   BASE=http://127.0.0.1:8042 node tests/sweep_all.js [user] [pass] [width] [pageFilter]
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const USER = process.argv[2] || 'admin', PW = process.argv[3] || 'changeme123', W = +(process.argv[4] || 1440), ONLY = process.argv[5] || '';
const OUT = `/tmp/claude-0/sweep/${USER}_${W}`; fs.mkdirSync(OUT, { recursive: true });
const DANGER = /delete|remove|save|send|approve|reject|cancel|clear|reset|submit|confirm|sign ?out|log ?out|restore|fresh|disconnect|reverse|mark|pay\b|paid|complete|close|lock|unlock|import|upload|generate|create|add|new|\+|issue|return|receive|arriv|record|post|push|sync|refresh zoho|apply|undo|archive|move|copy|duplicate|terminate|renew|reveal|password|backup|run|calculate|approve|sign|won|lost|convert|release|skip|retry|book|assign|free|link|unlink|subscribe|test mail|mail|whatsapp|share|print|edit|rename|change|set |upload|choose|read from|start|stop|done|transfer|hire|pick|reopen/i;
const findings = []; const add = (scr, kind, msg) => { findings.push({ scr, kind, msg }); };
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 }, acceptDownloads: true, ...(W < 500 ? { isMobile: true, hasTouch: true, deviceScaleFactor: 2 } : {}) });
  const p = await ctx.newPage();
  let errs = [], reqs = [];
  const hook = pg => {
    pg.on('pageerror', e => errs.push('JS ' + e.message.slice(0, 200)));
    pg.on('console', m => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errs.push('CONSOLE ' + m.text().slice(0, 200)); });
    pg.on('response', r => { if (r.status() >= 400 && !/\/health|favicon/.test(r.url())) errs.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(B, '').slice(0, 120)}`); });
    pg.on('request', r => { if (['fetch', 'xhr'].includes(r.resourceType())) reqs.push({ u: r.url().replace(B, '').replace(/([?&])(_|t|v)=[^&]*/g, '$1$2=*'), t: Date.now(), m: r.method() }); });
  };
  hook(p);
  ctx.on('page', np => { hook(np); });
  await p.addInitScript(() => {
    window.__cls = 0;
    try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true }); } catch (e) {}
  });
  await p.goto(B + '/'); await p.fill('#login-username', USER); await p.fill('#login-password', PW); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 30000 }); await p.waitForTimeout(2500);
  const landed = await p.evaluate(() => (document.querySelector('.screen.active') || {}).id);
  add('login', 'info', 'landed on ' + landed + ' url ' + p.url().replace(B, ''));

  const settle = async () => {
    let n = -1, still = 0;
    for (let i = 0; i < 60; i++) { await p.waitForTimeout(200); if (reqs.length === n) { still += 200; if (still >= 800) break; } else { still = 0; n = reqs.length; } }
  };

  // ---- checks run inside every frame of the screen ------------------------------------------------
  const CHECK = () => {
    const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
    const root = document.querySelector('.screen.active') || document.querySelector('.dlg.open, .modal.show') || document.body;
    const out = { fonts: {}, overlaps: [], clipped: [], totals: [], aligns: [], sortable: 0, emptyCols: [], overflow: document.documentElement.scrollWidth - innerWidth, tinyText: [], colours: {} };
    // fonts: the first family of every visible text element
    root.querySelectorAll('*').forEach(el => {
      if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
      if (!vis(el) || el.closest('svg, .help-i, code, pre, .mono, [class*=icon]')) return;
      const s = getComputedStyle(el); const f = s.fontFamily.split(',')[0].replace(/["']/g, '').trim();
      out.fonts[f] = (out.fonts[f] || 0) + 1;
      if (parseFloat(s.fontSize) < 10.5 && el.textContent.trim().length > 2) out.tinyText.push(el.textContent.trim().slice(0, 30) + ' ' + s.fontSize);
      // clipped: text cut off without an ellipsis meant for it
      if (el.scrollWidth > el.clientWidth + 2 && ['hidden', 'clip'].includes(s.overflowX) && s.textOverflow !== 'ellipsis' && el.clientWidth > 0) out.clipped.push(el.textContent.trim().slice(0, 40));
    });
    // overlapping buttons / inputs
    const ctl = [...root.querySelectorAll('button, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, a.btn')].filter(vis).filter(e => !e.closest('.dlg:not(.open), [hidden]') && !(e.closest('details') && !e.closest('details').open && !e.closest('summary')) && !/^[×x✕]$/.test((e.textContent || '').trim()));
    const R = ctl.map(e => e.getBoundingClientRect());
    for (let i = 0; i < ctl.length && out.overlaps.length < 8; i++) for (let j = i + 1; j < ctl.length; j++) {
      const a = R[i], b = R[j];
      if (ctl[i].contains(ctl[j]) || ctl[j].contains(ctl[i])) continue;
      const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left), iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ix > 4 && iy > 4) out.overlaps.push(`${(ctl[i].textContent || ctl[i].id || ctl[i].name || ctl[i].tagName).trim().slice(0, 25)} / ${(ctl[j].textContent || ctl[j].id || ctl[j].name || ctl[j].tagName).trim().slice(0, 25)}`);
    }
    // tables: totals, alignment of figures, sortable headers
    const num = t => { t = (t || '').replace(/AED|Dhs|,|\s/g, ''); if (/^\(?[-+]?\d+(\.\d+)?\)?$/.test(t)) { const v = parseFloat(t.replace(/[()+]/g, '')); return /^\(/.test(t) ? -v : v; } return null; };
    root.querySelectorAll('table').forEach((tb, ti) => {
      if (!vis(tb)) return;
      const rows = [...tb.querySelectorAll('tr')].filter(vis);
      const head = tb.querySelector('thead tr:last-child') || rows[0];
      const heads = head ? [...head.children].map(c => c.textContent.trim().replace(/\s+/g, ' ')) : [];
      if (head) out.sortable += [...head.children].filter(th => th.onclick || th.dataset.sort !== undefined || /sort|tx-s/.test(th.className) || getComputedStyle(th).cursor === 'pointer').length;
      const body = rows.filter(r => r !== head && !r.closest('thead'));
      let acc = {}, n = 0, all = {}, alln = 0;
      for (const r of body) {
        const cells = [...r.children]; if (cells.some(c => +c.colSpan > 1)) { acc = {}; n = 0; continue; }
        const struck = cells.some(c => /line-through/.test(getComputedStyle(c).textDecorationLine)) || +getComputedStyle(r).opacity < 0.8 || /cancel/i.test(r.className) || /\bCancelled\b/.test(r.textContent);
        if (struck && !/total/i.test(r.textContent)) continue;               // a cancelled line is shown but not counted
        if (cells.some(c => +c.rowSpan > 1)) { acc = {}; n = 0; continue; }  // grouped table (project over its scopes): totals checked by group only
        const label = (cells[0] && cells[0].textContent || '').trim() + ' ' + (cells[1] && cells[1].textContent || '').trim();
        const isTot = /^(grand )?total\b|^sub[- ]?total\b|^totals?\b/i.test(label.trim()) || /\btot\b|total/.test(r.className);
        if (isTot) {
          if (n >= 2) cells.forEach((c, k) => {
            const v = num(c.textContent); if (v === null || acc[k] === undefined) return;
            const h = heads[k] || ''; if (/balance|%|rate|qty|no\b|days|price/i.test(h)) return;
            if (Math.abs(v - acc[k]) > 0.011 && !(all[k] !== undefined && Math.abs(v - all[k]) <= 0.011)) out.totals.push(`table ${ti} "${h}": rows add to ${acc[k].toFixed(2)}, total says ${v.toFixed(2)}`);
          });
          acc = {}; n = 0; if (/grand|^total\b/i.test(label.trim())) { all = {}; alln = 0; } continue;
        }
        cells.forEach((c, k) => { const v = num(c.textContent); if (v !== null && /[.,]\d{2}\b|^[-+]?\d{1,3}(,\d{3})+$/.test(c.textContent.trim())) { acc[k] = (acc[k] || 0) + v; all[k] = (all[k] || 0) + v; } });
        n++;
      }
      // figures aligned the same way down a column; heading alignment beside it
      if (body.length >= 3 && head) [...head.children].forEach((th, k) => {
        const cs = body.map(r => r.children[k]).filter(c => c && num(c.textContent) !== null && /\.\d{2}$/.test(c.textContent.trim()));
        if (cs.length < 3) return;
        const al = [...new Set(cs.map(c => getComputedStyle(c).textAlign))];
        if (al.length > 1) out.aligns.push(`table ${ti} "${heads[k]}": figures aligned ${al.join('/')}`);
        if (al[0] === 'left' || al[0] === 'start') out.aligns.push(`table ${ti} "${heads[k]}": amounts aligned left`);
      });
    });
    return out;
  };

  const runChecks = async (scr) => {
    for (const f of p.frames()) {
      let r; try { r = await f.evaluate(CHECK); } catch (e) { continue; }
      const where = f === p.mainFrame() ? scr : scr + ' [frame ' + f.url().replace(B, '').split('?')[0] + ']';
      const fonts = Object.entries(r.fonts).filter(([k, n]) => n > 0).sort((a, b) => b[1] - a[1]);
      if (fonts.length > 1) add(where, 'font', fonts.map(([k, n]) => `${k}:${n}`).join(' '));
      if (r.overflow > 2 && f === p.mainFrame()) add(where, 'overflow', `page scrolls sideways by ${r.overflow}px`);
      r.overlaps.forEach(o => add(where, 'overlap', o));
      if (r.clipped.length) add(where, 'clipped', r.clipped.slice(0, 6).join(' | '));
      r.totals.forEach(o => add(where, 'TOTAL', o));
      r.aligns.forEach(o => add(where, 'align', o));
      if (r.tinyText.length) add(where, 'tiny', r.tinyText.slice(0, 4).join(' | '));
    }
  };

  // header sorting: click each sortable heading of the first visible table, check the column comes out ordered
  const checkSort = async (scr) => {
    const res = await p.evaluate(async () => {
      const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const sc = document.querySelector('.screen.active'); if (!sc) return [];
      const out = [];
      const tables = [...sc.querySelectorAll('table')].filter(vis).slice(0, 3);
      for (const tb of tables) {
        const ths = [...(tb.querySelector('thead tr:last-child') || { children: [] }).children];
        for (let k = 0; k < ths.length; k++) {
          const th = ths[k];
          if (!(th.onclick || th.dataset.sort !== undefined || /sort|tx-s/.test(th.className) || getComputedStyle(th).cursor === 'pointer')) continue;
          // a heading row inside the table (a group: "Former workers") starts a new run - each run sorted on its own
          const ti = tables.indexOf(tb); const col = () => { const t2 = th.closest('table') || [...sc.querySelectorAll('table')].filter(vis).slice(0, 3)[ti]; if (!t2) return []; const out = []; let g = 0; [...t2.querySelectorAll('tbody tr')].forEach(r => { if (r.children.length !== ths.length || /total/i.test(r.className + ' ' + ((r.children[0] || {}).textContent || ''))) { g++; return; } out.push('\u0001' + g + '\u0002' + ((r.children[k] || {}).textContent || '').trim()); }); return out; };
          const before = col(); if (before.length < 3) continue;
          { const t3 = th.isConnected ? th.closest('table') : [...sc.querySelectorAll('table')].filter(vis).slice(0, 3)[ti]; const h3 = t3 && t3.querySelector('thead tr:last-child') ? t3.querySelector('thead tr:last-child').children[k] : th; (h3 || th).click(); } await new Promise(z => setTimeout(z, 500));
          const a = col();
          { const t3 = th.isConnected ? th.closest('table') : [...sc.querySelectorAll('table')].filter(vis).slice(0, 3)[ti]; const h3 = t3 && t3.querySelector('thead tr:last-child') ? t3.querySelector('thead tr:last-child').children[k] : th; (h3 || th).click(); } await new Promise(z => setTimeout(z, 500));
          const b = col();
          const grp = s => s.split('\u0002')[0]; const txt = s => s.split('\u0002').slice(1).join(''); const key = s0 => { const s = txt(s0); const n = s.replace(/AED|,|\s/g, ''); if (/^[-+]?\d+(\.\d+)?$/.test(n)) return [0, parseFloat(n)]; const dm = s.match(/(\d{1,2})[- ]([A-Za-z]{3})[- ](\d{2,4})/); if (dm) { const d = Date.parse(`${dm[1]} ${dm[2]} ${dm[3].length === 2 ? '20' + dm[3] : dm[3]}`); if (!isNaN(d)) return [1, d]; } return [2, s.toLowerCase()]; };
          const cmp = (x0, y0) => { if (grp(x0) !== grp(y0)) return 0; const x = txt(x0), y = txt(y0); const X = key(x0), Y = key(y0); if (X[0] !== Y[0]) return 0; if (X[0] === 2) return x.localeCompare(y, undefined, { numeric: true, sensitivity: 'base' }); return X[1] < Y[1] ? -1 : X[1] > Y[1] ? 1 : 0; };
          const viol = (arr, dir) => arr.filter((v, i) => i > 0 && dir * cmp(arr[i - 1], v) > 0).length; const sorted = arr => Math.min(viol(arr, 1), viol(arr, -1)) <= Math.max(0, Math.floor(arr.length * 0.0));
          const h = th.textContent.trim().replace(/\s+/g, ' ').slice(0, 30); if ([...(th.closest('table') || tb).querySelectorAll('tbody tr')].some(r => r.children[k] && r.children[k].querySelector('select, input'))) continue; const varied = arr => { const m = {}; arr.forEach(v => { (m[grp(v)] = m[grp(v)] || new Set()).add(txt(v)); }); return Object.values(m).some(x => x.size > 1); }; if (!varied(before)) continue;
          if (JSON.stringify(a) === JSON.stringify(before) && JSON.stringify(b) === JSON.stringify(before) && new Set(before).size > 1) out.push(`"${h}" click does nothing`);
          else if (!sorted(a) || !sorted(b)) { const bad = (arr) => { const i = arr.findIndex((v, j) => j > 0 && cmp(arr[j - 1], v) > 0 && arr.slice(0, j).some((w, q) => q > 0 && cmp(arr[q - 1], w) < 0)); return i > 0 ? arr[i - 1] + ' > ' + arr[i] : ''; }; out.push(`"${h}" not in order after click: ${(bad(a) || bad(b) || a.slice(0, 4).join(' | ')).replace(/\u0001\d+\u0002/g, '')}`); }
          else if (JSON.stringify(a) === JSON.stringify(b) && new Set(a).size > 1) out.push(`"${h}" second click does not reverse`);
        }
      }
      return out;
    }).catch(e => ['sort check failed ' + e.message]);
    res.forEach(r => add(scr, 'SORT', r));
  };

  // previews: open each, check, close
  const checkPreviews = async (scr, reopen) => {
    const n = await p.evaluate(() => [...(document.querySelector('.screen.active') || document).querySelectorAll('button, a')].filter(b => /^\s*preview/i.test(b.textContent) && b.getBoundingClientRect().width > 0).length).catch(() => 0);
    for (let i = 0; i < Math.min(n, 4); i++) {
      errs = [];
      const popup = ctx.waitForEvent('page', { timeout: 4000 }).catch(() => null);
      await p.evaluate(i => { const bs = [...(document.querySelector('.screen.active') || document).querySelectorAll('button, a')].filter(b => /^\s*preview/i.test(b.textContent) && b.getBoundingClientRect().width > 0); bs[i] && bs[i].click(); }, i);
      await settle(); await p.waitForTimeout(800);
      const np = await popup;
      const tag = `${scr} > Preview ${i + 1}`;
      const target = np || p;
      if (np) { await np.waitForLoadState('load').catch(() => {}); await np.waitForTimeout(1200); }
      await target.screenshot({ path: `${OUT}/${tag.replace(/[^a-z0-9]+/gi, '_')}.png`, fullPage: false }).catch(() => {});
      // the preview's own checks: in a popup, or an overlay / iframe on the page
      const frames = np ? np.frames() : p.frames();
      for (const f of frames) {
        const r = await f.evaluate(() => {
          const t = document.querySelector('.preview, .pv, #pv, .modal, .dlg.open, [id*=preview], body');
          const fonts = {}; let red = 0, colourText = [];
          document.querySelectorAll('h1,h2,h3,h4,.title,td,th,p,span,div').forEach(el => {
            if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
            const r = el.getBoundingClientRect(); if (!r.width) return;
            const s = getComputedStyle(el); const f = s.fontFamily.split(',')[0].replace(/["']/g, '').trim(); fonts[f] = (fonts[f] || 0) + 1;
            const c = s.color.match(/\d+/g).map(Number); const isColour = Math.max(...c) - Math.min(...c) > 60;
            if (isColour && el.tagName !== 'TH' && !el.closest('th, thead, .hdr, .head') && el.textContent.trim().length > 3) colourText.push(el.textContent.trim().slice(0, 25) + ' ' + s.color);
          });
          return { fonts, colourText: colourText.slice(0, 6), url: location.href.slice(-60), sideways: document.documentElement.scrollWidth - innerWidth };
        }).catch(() => null);
        if (!r) continue;
        const fl = Object.keys(r.fonts); if (fl.length > 1) add(tag, 'font', JSON.stringify(r.fonts));
        if (r.colourText.length > 2) add(tag, 'colour', r.colourText.join(' | '));
      }
      if (np) { for (const f of np.frames()) { try { const rr = await f.evaluate(CHECK); rr.totals.forEach(o => add(tag, 'TOTAL', o)); rr.aligns.forEach(o => add(tag, 'align', o)); } catch (e) {} } }
      [...new Set(errs)].forEach(e => add(tag, 'ERROR', e));
      if (np) await np.close().catch(() => {});
      else { await p.keyboard.press('Escape').catch(() => {}); await p.evaluate(() => { document.querySelectorAll('.pv-close, .modal-close, [data-close], .dlg.open .btn-gray, #pv-close, .preview-close').forEach(b => { if (b.getBoundingClientRect().width) b.click(); }); }).catch(() => {}); await p.waitForTimeout(400); }
      await reopen();
    }
  };

  // harmless buttons: filters, pills, toggles, exports - each clicked once, errors watched
  const clickAround = async (scr, reopen) => {
    const labels = await p.evaluate(src => {
      const re = new RegExp(src, 'i');
      const sc = document.querySelector('.screen.active'); if (!sc) return [];
      return [...sc.querySelectorAll('button, .vf-pill, .pg-sub, [role=tab]')].filter(b => b.getBoundingClientRect().width > 0 && !b.disabled)
        .map(b => b.textContent.trim().replace(/\s+/g, ' ')).filter(t => t && t.length < 40 && !re.test(t) && !/^preview/i.test(t));
    }, DANGER.source);
    const uniq = [...new Set(labels)].slice(0, 25);
    for (const lab of uniq) {
      errs = [];
      const popup = ctx.waitForEvent('page', { timeout: 1500 }).catch(() => null);
      const dl = p.waitForEvent('download', { timeout: 1500 }).catch(() => null);
      const ok = await p.evaluate(lab => { const sc = document.querySelector('.screen.active'); const b = [...sc.querySelectorAll('button, .vf-pill, .pg-sub, [role=tab]')].find(x => x.textContent.trim().replace(/\s+/g, ' ') === lab && x.getBoundingClientRect().width > 0); if (!b) return false; b.click(); return true; }, lab).catch(() => false);
      if (!ok) continue;
      await settle();
      const np = await popup; if (np) { await np.waitForTimeout(800); await np.close().catch(() => {}); }
      await dl;
      [...new Set(errs)].forEach(e => add(`${scr} > [${lab}]`, 'ERROR', e));
      // a dialog left open: close it
      await p.keyboard.press('Escape').catch(() => {});
    }
    await reopen();
  };

  // ---- walk the tree ------------------------------------------------------------------------------
  const tree = await p.evaluate(() => Object.entries(ALL_PAGES).map(([k, pg]) => [k, pg.tabs.filter(t => !t.hidden).map(t => ({ id: t.id, label: t.label, subs: (t.subs || []).map(s => s.id || s) }))]));
  const summary = [];
  for (const [key, tabs] of tree) {
    if (ONLY && !ONLY.split(',').includes(key)) continue;
    if (key === 'access' || key === 'people') continue;    // their own pages, swept separately
    errs = []; reqs = [];
    const t0 = Date.now();
    await p.evaluate(() => { window.__cls = 0; });
    await p.goto(B + (key === 'dashboard' ? '/' : '/?p=' + key)); await p.waitForSelector('#app-screen', { state: 'visible', timeout: 20000 }).catch(() => {});
    await settle();
    const loadMs = Date.now() - t0;
    const cls = await p.evaluate(() => window.__cls).catch(() => 0);
    const scrLoad = `${key} (load)`;
    if (loadMs > 4000) add(scrLoad, 'slow', `${loadMs}ms to settle`);
    if (cls > 0.1) add(scrLoad, 'FLICKER', `layout shift ${cls.toFixed(3)}`);
    [...new Set(errs)].forEach(e => add(scrLoad, 'ERROR', e));
    for (const t of tabs) {
      const ok = await p.evaluate(id => { const t = PAGE.tabs.find(x => x.id === id); return !!t && pgTabOk(t); }, t.id).catch(() => false);
      if (!ok) continue;
      const subs = t.subs.length ? t.subs : [null];
      for (let si = 0; si < subs.length; si++) {
        const s = subs[si];
        const scr = `${key} > ${t.id}${s ? ' > ' + s : ''}`;
        const open = async () => { await p.evaluate(([id, s, first]) => { pgTab(id); if (s && !first) pgSub(s); }, [t.id, s, si === 0]).catch(() => {}); await settle(); };
        errs = []; reqs = []; await p.evaluate(() => { window.__cls = 0; }).catch(() => {});
        const t1 = Date.now(); await open(); const ms = Date.now() - t1;
        const cls2 = await p.evaluate(() => window.__cls).catch(() => 0);
        const cnt = {}; reqs.filter(r => r.m === 'GET').forEach(r => { cnt[r.u] = (cnt[r.u] || 0) + 1; });
        const dups = Object.entries(cnt).filter(([, n]) => n > 1);
        if (ms > 3000) add(scr, 'slow', `${ms}ms to settle (${reqs.length} calls)`);
        if (cls2 > 0.05) add(scr, 'FLICKER', `layout shift ${cls2.toFixed(3)}`);
        if (dups.length) add(scr, 'dup-calls', dups.map(([u, n]) => `${n}x ${u}`).join(' | ').slice(0, 300));
        [...new Set(errs)].forEach(e => add(scr, 'ERROR', e));
        const empty = await p.evaluate(() => { const sc = document.querySelector('.screen.active'); if (sc && sc.querySelector('iframe')) { const f = sc.querySelector('iframe'); try { return !f.contentDocument || f.contentDocument.body.innerText.trim().length < 20; } catch (e) { return false; } } return !sc || sc.innerText.trim().length < 20; }).catch(() => true);
        if (empty) add(scr, 'EMPTY', 'screen shows nothing');
        await p.screenshot({ path: `${OUT}/${scr.replace(/[^a-z0-9]+/gi, '_')}.png`, fullPage: true }).catch(() => {});
        await runChecks(scr);
        await checkSort(scr);
        await open();
        await checkPreviews(scr, open);
        if (!process.env.NOCLICK) await clickAround(scr, open);
        summary.push(`${scr} ${ms}ms`);
        console.log(`${scr.padEnd(45)} ${String(ms).padStart(5)}ms cls ${cls2.toFixed(3)} ${findings.filter(f => f.scr.startsWith(scr)).length} findings`);
      }
    }
  }
  fs.writeFileSync(`${OUT}/findings.json`, JSON.stringify(findings, null, 1));
  const by = {}; findings.forEach(f => { by[f.kind] = (by[f.kind] || 0) + 1; });
  console.log('\nFINDINGS', JSON.stringify(by));
  for (const f of findings.filter(f => f.kind !== 'info')) console.log(`${f.kind.padEnd(9)} ${f.scr} :: ${f.msg}`);
  await br.close();
})();
