// Audit: on every page/tab/sub, press each Preview / PDF / Excel / Share button (window.open caught),
// then fetch every address: status, type, and for previews whether the page fits an A4 width.
const { chromium } = require('playwright'); const fs = require('fs');
const B = 'http://127.0.0.1:8032';
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 950 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  p.on('dialog', d => d.dismiss().catch(() => {}));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  const tree = await p.evaluate(() => Object.entries(ALL_TABS).map(([k, tabs]) => [k, tabs.filter(t => !t.hidden).map(t => ({ id: t.id, subs: t.subs.map(s => s.id) }))]));
  const urls = new Map();
  const press = async where => {
    await p.evaluate(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u || '')); return { location: { set href(v) { window.__opened.push(String(v)); } }, close() {}, document: { write() {}, close() {} } }; };
      try { navigator.share = async d => { window.__opened.push('SHARE:' + (d && (d.url || d.title) || '')); }; } catch (e) {} });
    await p.evaluate(() => document.querySelectorAll('[data-audit-i]').forEach(x => x.removeAttribute('data-audit-i')));
    const btns0 = await p.$$eval('.screen.active button, .screen.active a.btn', bs => bs.map((b, i) => { b.dataset.auditI = i; const r = b.getBoundingClientRect(); return { i, t: (b.textContent || '').trim(), vis: r.width > 0 && r.height > 0 }; })
      .filter(x => x.vis && /^(preview|pdf|export pdf|excel|export excel|share|download pdf|print)$/i.test(x.t)));
    const btns = btns0; console.log(where, 'buttons', btns.map(b => b.t).join(','));
    for (const bt of btns) {
      try { await p.evaluate(i => document.querySelector(`.screen.active [data-audit-i="${i}"]`).click(), bt.i); await p.waitForTimeout(700); } catch (e) { console.log('click fail', where, bt.t, e.message.split('\n')[0]); continue; }
      const op = await p.evaluate(() => window.__opened.splice(0));
      op.filter(u => u && !u.startsWith('SHARE:') && u !== 'about:blank').forEach(u => { const k = u.replace(/token=[^&]+/, 'token=*'); if (!urls.has(k)) urls.set(k, { u, where, btn: bt.t }); });
      if (!op.length) urls.set(`NOTHING ${where} ${bt.t}`, { u: '', where, btn: bt.t, none: true });
      await p.evaluate(() => document.querySelectorAll('.zx-modal').forEach(m => m.remove()));
    }
  };
  for (const [key, tabs] of tree) {
    await p.evaluate(k => pgGo(k), key); await p.waitForTimeout(1500);
    for (const t of tabs) {
      const ok = await p.evaluate(id => { const t = PAGE.tabs.find(x => x.id === id); return !!t && pgTabOk(t); }, t.id).catch(() => false); if (!ok) continue;
      await p.evaluate(id => pgTab(id), t.id); await p.waitForTimeout(1500); await press(`${key}>${t.id}`);
      for (const s of t.subs.slice(1)) { await p.evaluate(id => pgSub(id), s); await p.waitForTimeout(1500); await press(`${key}>${t.id}>${s}`); }
    }
  }
  // fetch each with a fresh token
  const out = [];
  for (const [k, v] of urls) {
    if (v.none) { out.push({ where: v.where, btn: v.btn, status: 'NO ADDRESS OPENED' }); continue; }
    const tok = await p.evaluate(async () => { cachedDownloadToken = null; await refreshDownloadToken(); return cachedDownloadToken; });
    const full = new URL(v.u.replace(/token=[^&]*/, 'token=' + encodeURIComponent(tok)), B).href;
    const r = await ctx.request.get(full).catch(e => null);
    const rec = { where: v.where, btn: v.btn, url: v.u.replace(/token=[^&]+/, 'token=*').slice(0, 140), status: r ? r.status() : 'ERR', type: r ? (r.headers()['content-type'] || '').split(';')[0] : '' };
    if (r && r.ok() && /html/.test(rec.type)) {
      const q = await ctx.newPage(); await q.setViewportSize({ width: 794, height: 1123 });
      await q.setContent(await r.text(), { waitUntil: 'load' }).catch(() => {}); await q.waitForTimeout(300);
      rec.overflow = await q.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - 794);
      rec.wideTables = await q.evaluate(() => [...document.querySelectorAll('table')].filter(t => t.getBoundingClientRect().right > 800).length);
      rec.hasShare = await q.evaluate(() => /share/i.test(document.body.innerText));
      await q.close();
    }
    if (r && r.ok() && /pdf/.test(rec.type)) { const buf = await r.body(); fs.writeFileSync(`/tmp/claude-0/audit/pdf_${out.length}.pdf`, buf); rec.pdf = `pdf_${out.length}.pdf`; rec.kb = Math.round(buf.length / 1024); }
    out.push(rec);
  }
  fs.writeFileSync('/tmp/claude-0/audit/exports.json', JSON.stringify(out, null, 1));
  out.forEach(r => console.log(`${String(r.status).padEnd(4)} ${String(r.type || '').padEnd(18)} ${r.overflow !== undefined ? 'ovf ' + r.overflow + ' wide ' + r.wideTables : ''}${r.kb ? r.kb + 'KB ' : ''} ${r.where} [${r.btn}] ${r.url || ''}`));
  console.log('page errors', errs);
  await b.close();
})();
