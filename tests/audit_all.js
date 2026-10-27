// Whole-app audit: every page, tab, sub-tab, Estimation section, Trello view and Staff view - on a computer screen
// and on a phone. For each: errors, failed calls, load time, sideways scrolling, tables not sortable / heading not
// pinned, Save buttons that do not float on a long page, placeholders and buttons cut off, buttons off the standard,
// mixed fonts, small tap targets (phone). A screenshot of each.
//   BASE=http://127.0.0.1:8032 node tests/audit_all.js [desktop|phone]
// Writes /tmp/claude-0/audit/report-<vp>.json and the pictures.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', OUT = process.env.OUT || '/tmp/claude-0/audit';
const only = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

const VPS = { desktop: { viewport: { width: 1440, height: 900 } }, phone: { ...devices['iPhone 13'] } };

(async () => {
  const br = await chromium.launch();
  for (const [vp, opts] of Object.entries(VPS)) {
    if (only && only !== vp) continue;
    const ctx = await br.newContext(opts); const p = await ctx.newPage();
    let errs = [], bad = [], inflight = 0, last = Date.now();
    p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
    p.on('console', m => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text().slice(0, 200)); });
    p.on('request', () => { inflight++; last = Date.now(); });
    p.on('requestfinished', () => { inflight--; last = Date.now(); });
    p.on('requestfailed', r => { inflight--; last = Date.now(); if (!/aborted|cancel/i.test((r.failure() || {}).errorText || '')) bad.push(`${r.url().replace(B, '')} ${(r.failure() || {}).errorText}`); });
    p.on('response', r => { if (r.status() >= 400 && !/favicon|\/help\/img\//.test(r.url())) bad.push(`${r.status()} ${r.request().method()} ${r.url().replace(B, '').slice(0, 120)}`); });
    const settle = async (max = 9000) => { const t0 = Date.now(); await sleep(250); while (Date.now() - t0 < max) { if (inflight <= 0 && Date.now() - last > 700) break; await sleep(100); } return Date.now() - t0; };
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await settle();
    await p.evaluate(async () => { window.checkBuild = () => {}; const b = document.getElementById('build-bar'); if (b) b.remove();
      try { localStorage.setItem('infinia-help-hello', '1'); const m = await apiCall('/store/est/meta'); const pr = m.projects.find(x => x.code === '914') || m.projects[0]; if (pr) localStorage.setItem('est_pid', pr.id); } catch (e) {} });
    const screens = await p.evaluate(() => {
      const out = [];
      for (const [key, cfg] of Object.entries(ALL_PAGES)) {
        if (key === 'people') { for (const v of ['register', 'vacation', 'bday']) out.push({ id: `people-${v}`, title: `Staff > ${v}`, go: { page: 'people', tab: 'people', view: v } }); continue; }
        for (const t of cfg.tabs) {
          if (t.hidden) continue;
          if (t.subs.length) for (const sb of t.subs) out.push({ id: `${key}-${t.id}-${sb.id}`, title: `${cfg.title} > ${t.label} > ${sb.label}`, go: { page: key, tab: t.id, sub: sb.id } });
          else out.push({ id: `${key}-${t.id}`, title: `${cfg.title} > ${t.label}`, go: { page: key, tab: t.id } });
        }
      }
      for (const k of ['home.dash', 'client.boq', 'subs.reg', 'subs.inv', 'subs.pcs', 'subs.final', 'site.rfi', 'site.approval', 'site.submittal', 'site.vo', 'bills.ipa', 'prev.rec'])
        out.push({ id: 'est-' + k.replace('.', '-'), title: `Estimation > Projects > ${k}`, go: { page: 'estimation', tab: 'estproj', est: k } });
      for (const v of ['board', 'table', 'calendar', 'timeline', 'dashboard', 'mindmap'])
        out.push({ id: 'kb-' + v, title: `Trello > ${v}`, go: { page: 'estimation', tab: 'boards', kb: 'board', kbView: v } });
      return out;
    });
    const report = [];
    for (const sc of screens) {
      errs = []; bad = [];
      const t0 = Date.now();
      await p.evaluate(async go => { document.querySelectorAll('.help-drawer').forEach(d => d.classList.remove('open')); try { await HELP.goTo({ go }); } catch (e) { console.error('goTo ' + e.message); } }, sc.go).catch(e => errs.push('nav: ' + e.message));
      await settle();
      const ms = Date.now() - t0;
      const res = await p.evaluate(vp => {
        const out = { overflowX: 0, tables: [], saves: [], cutPh: [], cutBtn: [], smallTap: [], fonts: {}, btnStyles: {}, frame: false };
        const scr = document.querySelector('.screen.active');
        const fr = scr && [...scr.querySelectorAll('iframe')].find(f => f.offsetParent);
        const docs = [document]; if (fr) { try { if (fr.contentDocument) { docs.push(fr.contentDocument); out.frame = true; } } catch (e) {} }
        out.overflowX = Math.max(0, document.documentElement.scrollWidth - window.innerWidth);
        if (fr) try { const d = fr.contentDocument; out.overflowX = Math.max(out.overflowX, d.documentElement.scrollWidth - d.documentElement.clientWidth); } catch (e) {}
        const cv = document.createElement('canvas').getContext('2d');
        for (const d of docs) {
          const w = d.defaultView, root = d === document ? (scr || d.body) : d.body;
          const vis = el => { if (!el.getClientRects().length) return false; const cs = w.getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none' && !el.closest('.help-drawer, .freeze-head, [hidden]'); };
          const inView = el => { const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < w.innerHeight + 2000; };
          // tables
          for (const t of root.querySelectorAll('table')) {
            if (!vis(t) || !t.tHead || !t.tBodies.length || t.closest('.freeze-head')) continue;
            const rows = [...t.tBodies].reduce((n, b) => n + b.rows.length, 0); if (rows < 6) continue;
            const ths = [...t.tHead.rows[t.tHead.rows.length - 1].cells];
            const sortable = t.hasAttribute('data-nosort') || ths.some(th => th.__tx || th.querySelector('.tx-a') || th.classList.contains('sortable') || th.hasAttribute('data-dsort') || th.hasAttribute('onclick'));
            const sticky = ths.some(th => w.getComputedStyle(th).position === 'sticky') || !!w.__freezeHeads;
            const name = (t.id ? '#' + t.id : '') || (t.tBodies[0].id ? 'tbody#' + t.tBodies[0].id : '') || (t.className ? 'table.' + String(t.className).split(' ')[0] : 'table') + ' "' + ths.map(c => c.textContent.trim()).filter(Boolean).slice(0, 3).join('|').slice(0, 40) + '"';
            out.tables.push({ name, rows, sortable, sticky, nofreeze: t.dataset.nofreeze !== undefined });
          }
          // buttons
          for (const b of root.querySelectorAll('button, a.btn, .btn, input[type=button], input[type=submit]')) {
            if (!vis(b) || !inView(b)) continue;
            const cs = w.getComputedStyle(b), r = b.getBoundingClientRect(), txt = (b.textContent || b.value || '').replace(/\s+/g, ' ').trim();
            if (!txt || r.width < 6) continue;
            const key = `${Math.round(parseFloat(cs.fontSize))}px/${Math.round(r.height)}h/${cs.borderRadius}`;
            out.btnStyles[key] = (out.btnStyles[key] || 0) + 1;
            if (b.scrollWidth > b.clientWidth + 2 && cs.overflow !== 'visible' && txt.length > 2) out.cutBtn.push(txt.slice(0, 40));
            if (vp === 'phone' && r.height < 30 && r.width < 30 && txt.length <= 2 && !b.closest('table')) out.smallTap.push(txt + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
            if (/^(save|submit|save &|save and|update|post|record|add to|generate)/i.test(txt) && !b.closest('.modal, #modal, .dlg, .mbox, .hr-dlg, [role=dialog], .pop, .drawer, #drawer')) {
              let fl = false; for (let e = b; e && e !== d.body; e = e.parentElement) { const ps = w.getComputedStyle(e).position; if (ps === 'fixed' || ps === 'sticky') { fl = true; break; } }
              const longPage = d.documentElement.scrollHeight > w.innerHeight * 1.3 || [...root.querySelectorAll('*')].some(x => { const s = w.getComputedStyle(x); return (s.overflowY === 'auto' || s.overflowY === 'scroll') && x.scrollHeight > x.clientHeight + 40 && x.contains(b) === false && x.getBoundingClientRect().height > 300; });
              out.saves.push({ txt: txt.slice(0, 30), floating: fl, longPage });
            }
          }
          // placeholders cut off
          for (const inp of root.querySelectorAll('input[placeholder], textarea[placeholder]')) {
            if (!vis(inp) || !inView(inp) || inp.value) continue;
            const cs = w.getComputedStyle(inp); cv.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
            const room = inp.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - (inp.type === 'search' ? 18 : 0);
            if (inp.tagName === 'INPUT' && cv.measureText(inp.placeholder).width > room + 2) out.cutPh.push(`"${inp.placeholder.slice(0, 50)}" (${Math.round(room)}px)`);
          }
          // fonts on text
          let n = 0;
          for (const el of root.querySelectorAll('td, th, button, label, h1, h2, h3, p, span, a, input, select')) {
            if (n > 500) break; if (!vis(el)) continue; n++;
            const f = w.getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim(); out.fonts[f] = (out.fonts[f] || 0) + 1;
          }
        }
        return out;
      }, vp).catch(e => ({ error: e.message }));
      await p.evaluate(() => { const b = document.getElementById('build-bar'); if (b) b.remove(); }).catch(() => {});
      await p.screenshot({ path: `${OUT}/${vp}-${sc.id}.png` }).catch(() => {});
      report.push({ id: sc.id, title: sc.title, ms, errs: [...new Set(errs)], bad: [...new Set(bad)], ...res });
      const flag = [errs.length && `errors:${errs.length}`, bad.length && `failed:${bad.length}`, res.overflowX > 2 && `sideways:${res.overflowX}px`, ms > 4000 && `slow:${ms}ms`].filter(Boolean).join(' ');
      console.log(`${vp} ${sc.id.padEnd(34)} ${String(ms).padStart(5)}ms ${flag}`);
    }
    fs.writeFileSync(`${OUT}/report-${vp}.json`, JSON.stringify(report, null, 1));
    await ctx.close();
  }
  await br.close();
})();
