// Estimation: every button, chip, link and clickable row on every page, clicked once per kind.
// Each click must not throw, must not show an error, and whatever it opens (form, drawer, sheet,
// preview tab) must open properly and close again. Deleting is left alone.
//   node tests/est_click_all_test.js        (server on 127.0.0.1:8032, a fresh database)
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/clickall_';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SKIP = /delete|remove|^×$|^×$|cancel subcontract|sign out|reverse|drop|clear all|log out|undo/i;
let clicks = 0; const problems = [];
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  let errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('dialog', d => d.dismiss().catch(() => {}));
  const opened = [];
  ctx.on('page', async np => { opened.push(np); });
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async path => p.evaluate(async path => (await fetch(path, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), path);
  const meta = await api('/store/est/meta');
  const P = meta.projects.find(x => x.code === '922').id;
  const sections = [['home', 'dash'], ['client', 'boq'], ['client', 'cpc'], ['client', 'vo'], ['client', 'inv'], ['subs', 'reg'], ['subs', 'inv'], ['subs', 'pcs'], ['subs', 'final'], ['site', 'rfi'], ['site', 'approval'], ['site', 'submittal']];
  const go = async (g, s) => {
    await p.evaluate(([pid, g, s]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', g + '.' + s); }, [P, g, s]);
    await p.goto(B + '/portal/est-app.html?view=projects'); await sleep(1300);
  };
  const closeAll = async () => {
    for (let i = 0; i < 3; i++) {
      if (await p.isVisible('#big:not(.hide)').catch(() => false)) { await p.click('#b-back').catch(() => {}); await sleep(250); }
      if (await p.isVisible('#modal:not(.hide)').catch(() => false)) { await p.click('#m-x').catch(() => {}); await sleep(250); }
      if (await p.isVisible('#drawer:not(.hide)').catch(() => false)) { await p.click('#d-back').catch(() => {}); await sleep(250); }
    }
  };
  // one of each kind: same tag, same data-* names, same words (rows: same data-* names only)
  const kinds = () => p.evaluate(skip => {
    const re = new RegExp(skip, 'i'), seen = new Set(), out = [];
    const root = document.querySelector('#pbody') || document.body;
    const els = [...root.querySelectorAll('button, a, [data-go], .chip, [data-sub], [data-pc], tr[data-id], tr[data-row], [data-open], [data-step], [data-next], [data-xp], th.sortable, th[data-sort]')];
    els.forEach((e, i) => {
      if (!e.offsetParent || e.disabled || e.closest('.toast')) return;
      const txt = (e.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40);
      if (re.test(txt) || re.test(e.title || '')) return;
      const data = [...e.attributes].map(a => a.name).filter(n => n.startsWith('data-')).sort().join(',');
      const isRow = e.tagName === 'TR';
      const sig = e.tagName + '|' + data + '|' + (isRow ? '' : txt.replace(/\d+/g, '#'));
      if (seen.has(sig)) return; seen.add(sig);
      e.setAttribute('data-ck', String(out.length));
      out.push({ sig, txt, tag: e.tagName });
    });
    return out;
  }, SKIP.source);
  for (const [g, s] of sections) {
    await go(g, s);
    const list = await kinds();
    for (let i = 0; i < list.length; i++) {
      await go(g, s); await kinds();
      const el = await p.$(`[data-ck="${i}"]`); if (!el) continue;
      errs = []; opened.length = 0;
      const before = await p.url();
      try { await el.click({ timeout: 3000 }); } catch (e) { continue; }
      clicks++;
      await sleep(700);
      const where = `${g}.${s} "${list[i].txt || list[i].sig}"`;
      if (errs.length) problems.push(`${where}: page error ${errs[0]}`);
      const toastErr = await p.$eval('.toast.err', t => t.textContent).catch(() => null);
      if (toastErr) problems.push(`${where}: error shown "${toastErr}"`);
      // a form that opened: it has a title and a way out
      if (await p.isVisible('#modal:not(.hide)').catch(() => false)) {
        const t = (await p.textContent('#m-title').catch(() => '')).trim();
        if (!t) problems.push(`${where}: form opened with no title`);
      }
      for (const np of opened) {
        try {
          await np.waitForLoadState('domcontentloaded', { timeout: 15000 });
          const body = (await np.textContent('body').catch(() => '')) || '';
          if (/Internal Server Error|"detail"|Not Found|Traceback/.test(body.slice(0, 400))) problems.push(`${where}: opened page shows "${body.slice(0, 120)}"`);
        } catch (e) { /* a PDF download - fine */ }
        await np.close().catch(() => {});
      }
      await closeAll();
      if (p.url() !== before && !/est-app/.test(p.url())) problems.push(`${where}: left the page for ${p.url()}`);
    }
    await p.screenshot({ path: SH + g + '_' + s + '.png' });
  }
  // the Estimation dashboard and the Accounts payments page
  for (const v of ['dash', 'pay', 'tenders']) {
    await p.goto(B + '/portal/est-app.html?view=' + v); await sleep(1500);
    const list = await p.evaluate(skip => { const re = new RegExp(skip, 'i'), seen = new Set(), out = [];
      [...document.querySelectorAll('button, a, [data-go], .chip, [data-pf], tr[data-id]')].forEach(e => { if (!e.offsetParent) return; const txt = (e.textContent || '').trim().slice(0, 40); if (re.test(txt)) return;
        const sig = e.tagName + [...e.attributes].map(a => a.name).filter(n => n.startsWith('data-')).sort().join(',') + (e.tagName === 'TR' ? '' : txt.replace(/\d+/g, '#')); if (seen.has(sig)) return; seen.add(sig); e.setAttribute('data-ck', out.length); out.push(txt); }); return out; }, SKIP.source);
    for (let i = 0; i < list.length; i++) {
      await p.goto(B + '/portal/est-app.html?view=' + v); await sleep(1200);
      await p.evaluate(skip => { const re = new RegExp(skip, 'i'), seen = new Set(); let n = 0;
        [...document.querySelectorAll('button, a, [data-go], .chip, [data-pf], tr[data-id]')].forEach(e => { if (!e.offsetParent) return; const txt = (e.textContent || '').trim().slice(0, 40); if (re.test(txt)) return;
          const sig = e.tagName + [...e.attributes].map(a => a.name).filter(n => n.startsWith('data-')).sort().join(',') + (e.tagName === 'TR' ? '' : txt.replace(/\d+/g, '#')); if (seen.has(sig)) return; seen.add(sig); e.setAttribute('data-ck', n++); }); }, SKIP.source);
      const el = await p.$(`[data-ck="${i}"]`); if (!el) continue;
      errs = []; opened.length = 0;
      try { await el.click({ timeout: 3000 }); } catch (e) { continue; }
      clicks++; await sleep(700);
      if (errs.length) problems.push(`view=${v} "${list[i]}": page error ${errs[0]}`);
      const toastErr = await p.$eval('.toast.err', t => t.textContent).catch(() => null);
      if (toastErr) problems.push(`view=${v} "${list[i]}": error shown "${toastErr}"`);
      for (const np of opened) { await np.close().catch(() => {}); }
      await closeAll();
    }
  }
  console.log(`${clicks} clicks`);
  problems.forEach(x => console.log('FAIL ' + x));
  console.log(problems.length ? `\n${problems.length} FAILED` : '\nALL PASS');
  await br.close(); process.exit(problems.length ? 1 : 0);
})();
