// Presses every Preview / Export PDF / Export Excel / PDF / Excel / Share / Print button on every screen (and in the
// Estimation and Trello frames), catches what it opens or downloads, and saves each file for checking:
//   /tmp/claude-0/exports/<n>.<pdf|xlsx|html> and exports.json (screen, button, url, status, type, size).
// Then: python3 tests/check_exports.py
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', OUT = '/tmp/claude-0/exports';
fs.rmSync(OUT, { recursive: true, force: true }); fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const RX = /^(preview|export pdf|export excel|pdf|excel|share|print|print pc|download|print the list|print list)$/i;
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000);
  await p.evaluate(async () => { window.checkBuild = () => {}; try { localStorage.setItem('infinia-help-hello', '1'); const m = await apiCall('/store/est/meta'); localStorage.setItem('est_pid', (m.projects.find(x => x.code === '914') || m.projects[0]).id); } catch (e) {} });
  const screens = await p.evaluate(() => {
    const out = [];
    for (const [key, cfg] of Object.entries(ALL_PAGES)) {
      if (key === 'people') { for (const v of ['register', 'vacation', 'bday']) out.push({ id: `people-${v}`, go: { page: 'people', tab: 'people', view: v } }); continue; }
      for (const t of cfg.tabs) { if (t.hidden) continue;
        if (t.subs.length) for (const sb of t.subs) out.push({ id: `${key}-${t.id}-${sb.id}`, go: { page: key, tab: t.id, sub: sb.id } });
        else out.push({ id: `${key}-${t.id}`, go: { page: key, tab: t.id } }); }
    }
    for (const k of ['home.dash', 'client.boq', 'subs.reg', 'subs.inv', 'subs.pcs', 'subs.final', 'site.rfi', 'site.approval', 'site.submittal', 'site.vo', 'bills.ipa', 'prev.rec'])
      out.push({ id: 'est-' + k.replace('.', '-'), go: { page: 'estimation', tab: 'estproj', est: k } });
    out.push({ id: 'kb-board', go: { page: 'estimation', tab: 'boards', kb: 'board' } });
    return out;
  });
  // every frame: window.open and navigator.share are caught, not followed
  const hook = () => p.evaluate(() => {
    const put = w => { try { if (w.__hooked) return; w.__hooked = true; w.__opened = [];
      w.open = (u) => { if (u) w.__opened.push(String(u)); const loc = { set href(x) { w.__opened.push(String(x)); }, replace(x) { w.__opened.push(String(x)); } };
        return { closed: false, close() {}, focus() {}, document: { write() {}, close() {} }, get location() { return loc; }, set location(x) { w.__opened.push(String(x)); } }; };
      try { w.navigator.share = d => { w.__opened.push('SHARE:' + (d && (d.url || d.text) || '')); return Promise.resolve(); }; } catch (e) {} } catch (e) {} };
    put(window); document.querySelectorAll('iframe').forEach(f => { try { put(f.contentWindow); } catch (e) {} });
  });
  const taken = () => p.evaluate(() => { const all = []; const get = w => { try { all.push(...(w.__opened || [])); w.__opened = []; } catch (e) {} };
    get(window); document.querySelectorAll('iframe').forEach(f => get(f.contentWindow)); return all; });
  const rows = []; let n = 0; const seenUrl = new Set();
  for (const sc of screens) {
    await p.evaluate(async go => { try { await HELP.goTo({ go }); } catch (e) {} }, sc.go); await sleep(2500);
    await hook();
    // the buttons, on the page and in its frame
    const btns = await p.evaluate(RXs => { const RX = new RegExp(RXs, 'i'); const out = [];
      const scr = document.querySelector('.screen.active'); const docs = [[scr || document.body, null]];
      const clear = d => d.querySelectorAll('[data-audit]').forEach(x => x.removeAttribute('data-audit')); clear(document); document.querySelectorAll('iframe').forEach(f => { try { clear(f.contentDocument); } catch (e) {} });
      const fr = scr && [...scr.querySelectorAll('iframe')].find(f => f.offsetParent); if (fr) try { docs.push([fr.contentDocument.body, fr.id]); } catch (e) {}
      docs.forEach(([root, fid]) => { let i = 0; root.querySelectorAll('button, a.btn, .btn').forEach(b => { const t = (b.textContent || '').replace(/\s+/g, ' ').trim();
        if (RX.test(t) && b.getClientRects().length && !b.disabled && !b.closest('.help-drawer, #modal, .modal')) { b.setAttribute('data-audit', fid + ':' + (i)); out.push({ key: fid + ':' + i, t, fid }); i++; } }); });
      return out; }, RX.source);
    for (const b of btns) {
      let dl = null; const dlp = p.waitForEvent('download', { timeout: 4000 }).then(d => { dl = d; }).catch(() => {});
      const popp = ctx.waitForEvent('page', { timeout: 4000 }).catch(() => null);
      await p.evaluate(([key, fid]) => { const doc = fid ? document.getElementById(fid).contentDocument : (document.querySelector('.screen.active') || document); const el = doc.querySelector(`[data-audit="${key}"]`); if (el) el.click(); }, [b.key, b.fid]);
      await Promise.race([dlp, sleep(2500)]);
      let urls = await taken();
      const pop = await Promise.race([popp, sleep(300).then(() => null)]);
      if (pop) { urls.push(pop.url()); await pop.close().catch(() => {}); }
      // a "Share" pop-up drawn on the page
      const sharebox = await p.evaluate(() => { const m = [...document.querySelectorAll('.share-pop, .shr, [data-share], #share-modal, .modal.show, #modal:not(.hide)')].find(x => x.getClientRects().length); if (!m) { for (const f of document.querySelectorAll('iframe')) { try { const x = [...f.contentDocument.querySelectorAll('.share-pop, #modal:not(.hide), .pop')].find(y => y.getClientRects().length); if (x) return x.textContent.replace(/\s+/g, ' ').slice(0, 120); } catch (e) {} } return null; } return m.textContent.replace(/\s+/g, ' ').slice(0, 120); });
      await p.keyboard.press('Escape').catch(() => {});
      await p.evaluate(() => { document.querySelectorAll('iframe').forEach(f => { try { const m = f.contentDocument.getElementById('modal'); if (m) m.classList.add('hide'); } catch (e) {} }); const m = document.querySelector('.modal.show'); if (m) m.classList.remove('show'); }).catch(() => {});
      const rec = { screen: sc.id, button: b.t, urls, download: dl ? dl.suggestedFilename() : null, sharebox };
      if (dl) { const f = `${OUT}/${++n}-${dl.suggestedFilename().replace(/[^\w.-]+/g, '_')}`; await dl.saveAs(f).catch(() => {}); rec.file = f; }
      for (const u of urls.filter(u => /\/(export|portal)\//.test(u) && !u.startsWith('SHARE:'))) {
        const abs = u.startsWith('http') ? u : B + u;
        const key = abs.replace(/token=[^&]+/, '');
        if (seenUrl.has(key)) { rec.dup = true; continue; } seenUrl.add(key);
        const r = await p.evaluate(async u => { try { const r = await fetch(u); const ab = await r.arrayBuffer(); let s = ''; const b = new Uint8Array(ab); for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return { status: r.status, type: r.headers.get('content-type') || '', size: b.length, b64: btoa(s) }; } catch (e) { return { status: 0, err: e.message }; } }, abs);
        const ext = /pdf/.test(r.type || '') ? 'pdf' : /sheet|excel/.test(r.type || '') ? 'xlsx' : /html/.test(r.type || '') ? 'html' : 'bin';
        const f = `${OUT}/${++n}.${ext}`; if (r.b64) fs.writeFileSync(f, Buffer.from(r.b64, 'base64'));
        rec.fetched = (rec.fetched || []).concat([{ url: u.replace(/token=[^&]+/, 'token=…').slice(0, 160), status: r.status, type: r.type, size: r.size, file: f }]);
      }
      rows.push(rec);
      const st = (rec.fetched || []).map(x => `${x.status} ${x.type.split(';')[0]} ${x.size}`).join(', ') || (rec.download ? 'download ' + rec.download : (rec.sharebox ? 'share box' : (urls.length ? urls.join(' ').slice(0, 80) : 'NOTHING')));
      console.log(`${sc.id.padEnd(32)} ${b.t.padEnd(13)} ${st}`);
    }
  }
  fs.writeFileSync(`${OUT}/exports.json`, JSON.stringify({ rows, errs }, null, 1));
  console.log('page errors:', errs.length, errs.slice(0, 5));
  await br.close();
})();
