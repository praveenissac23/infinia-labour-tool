// Every Preview / Export PDF / Export Excel button in the app, pressed the
// way a person does, on every page / tab / sub-tab. The addresses they
// open are collected and fetched; HTML previews are photographed, PDFs
// saved for drawing, spreadsheets saved for checking (export_audit.py).
//   node tests/export_audit.js [user] [pass]
const { chromium } = require('playwright');
const fs = require('fs');
const U = process.argv[2] || 'admin', PW = process.argv[3] || 'changeme123', OUT = '/tmp/claude-0/exp/';
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://127.0.0.1:8032/'); await p.fill('#login-username', U); await p.fill('#login-password', PW); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(4000);
  await p.evaluate(() => { window.__opened = []; const o = window.open; window.open = (u, t) => { window.__opened.push(String(u || '')); return { location: { set href(v) { window.__opened.push(String(v)); } }, set location(v) { window.__opened.push(String(v)); }, close() {}, addEventListener() {}, focus() {} }; }; });
  const plan = await p.evaluate(() => Object.values(ALL_PAGES).map(pg => ({ key: pg.key, tabs: pg.tabs.filter(t => pgTabOk(t)).map(t => ({ id: t.id, subs: t.subs.filter(s => pgHas(s.right)).map(s => s.id) })) })).filter(pg => pg.tabs.length));
  const found = []; const seen = new Set();
  const harvest = async label => {
    await p.waitForTimeout(900);
    const btns = await p.evaluate(() => (document.querySelectorAll('[data-expi]').forEach(e => e.removeAttribute('data-expi')), [...document.querySelectorAll('.screen.active button, .screen.active a')]).filter(b => b.offsetParent && /^(Preview|Export PDF|Export Excel)$/.test(b.textContent.trim())).map((b, i) => { b.dataset.expi = i; return { i, text: b.textContent.trim(), on: b.getAttribute('onclick') || '' }; }));
    for (const bt of btns) {
      const key = label + '|' + bt.on; if (seen.has(key)) continue; seen.add(key);
      await p.evaluate(() => { window.__opened = []; });
      let d = null; const dl = p.waitForEvent('download', { timeout: 4000 }).then(x => { d = x; }).catch(() => null);
      await p.evaluate(i => { const b = document.querySelector(`[data-expi="${i}"]`); b && b.click(); }, bt.i);
      let urls = [];
      for (let k = 0; k < 20 && !urls.length && !d; k++) { await p.waitForTimeout(200); urls = (await p.evaluate(() => window.__opened)).filter(u => u && u !== 'about:blank'); }
      if (!urls.length && !d) await dl;
      const name = `${U}__${label.replace(/[^a-z0-9]+/gi, '_')}__${bt.text.replace(/\s+/g, '')}__${bt.on.replace(/[^a-z0-9]+/gi, '_').slice(0, 40)}`;
      if (d) { const f = OUT + name + '__' + d.suggestedFilename(); await d.saveAs(f); found.push({ label, btn: bt.text, on: bt.on, file: f }); continue; }
      if (!urls.length) { found.push({ label, btn: bt.text, on: bt.on, problem: 'nothing opened' }); continue; }
      const u = urls[urls.length - 1];
      try {
        const r = u.startsWith('blob:') ? null : await p.request.get(u.startsWith('http') ? u : 'http://127.0.0.1:8032' + u);
        if (!r) { found.push({ label, btn: bt.text, on: bt.on, url: u.slice(0, 60), problem: 'blob (opened in memory)' }); continue; }
        const ct = r.headers()['content-type'] || ''; const body = await r.body();
        const ext = /pdf/.test(ct) ? 'pdf' : /html/.test(ct) ? 'html' : /sheet|excel/.test(ct) ? 'xlsx' : 'bin';
        const f = OUT + name + '.' + ext; fs.writeFileSync(f, body);
        found.push({ label, btn: bt.text, on: bt.on, url: u.replace(/token=[^&]+/g, 'token=…').slice(0, 140), status: r.status(), ct: ext, file: f });
        if (ext === 'html' && r.status() === 200) { const v = await ctx.newPage(); await v.setContent(body.toString()); await v.waitForTimeout(500); await v.screenshot({ path: f.replace('.html', '.png'), fullPage: false }); await v.close(); }
      } catch (e) { found.push({ label, btn: bt.text, on: bt.on, url: u, problem: String(e).slice(0, 100) }); }
    }
  };
  for (const pg of plan) {
    await p.evaluate(k => pgGo(k), pg.key); await p.waitForTimeout(1500);
    for (const t of pg.tabs) {
      await p.evaluate(id => pgTab(id), t.id);
      if (!t.subs.length) await harvest(`${pg.key}>${t.id}`);
      for (const s of t.subs) { await p.evaluate(s => pgSub(s), s); await harvest(`${pg.key}>${t.id}>${s}`); }
    }
  }
  fs.writeFileSync(OUT + U + '__index.json', JSON.stringify(found, null, 1));
  for (const f of found) console.log(`${f.problem ? 'PROB' : (f.status && f.status !== 200 ? 'HTTP' + f.status : 'ok  ')} ${f.label.padEnd(30)} ${f.btn.padEnd(12)} ${f.ct || ''} ${f.problem || ''} ${f.url || (f.file || '').split('/').pop()}`);
  console.log(errs.length ? 'SCRIPT ERRORS: ' + errs.join(' / ') : 'no script errors');
  await b.close();
})();
