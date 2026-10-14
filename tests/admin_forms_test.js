// Admin > Forms: the side menu item for the PRO and accounts (not the store
// keeper), five form cards with pictures, Preview / PDF / Share, layout.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); return p;
}
const side = p => p.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
(async () => {
  const b = await chromium.launch();
  for (const u of ['jomon', 'shafiq', 'muhsina']) {
    const p = await login(b, u, 'pass12345');
    ck(`${u}: Admin in the side menu`, (await side(p)).some(x => /^Admin/.test(x)), await side(p));
    await p.close();
  }
  const a = await login(b, 'amal', 'pass12345');
  ck('store keeper: no Admin', !(await side(a)).some(x => /^Admin/.test(x)), await side(a));
  const r = await a.evaluate(async () => { try { await apiCall('/store/admin/forms'); return 'opened'; } catch (e) { return 'refused'; } });
  ck('store keeper cannot open the forms even directly', r === 'refused', r);

  for (const W of [1440, 1024, 390]) {
    const p = await login(b, 'jomon', 'pass12345', W);
    await p.evaluate(() => { const it = [...document.querySelectorAll('.pg-side .pg-item')].find(x => /^Admin/.test(x.textContent.trim())); it.click(); });
    await p.waitForTimeout(2500);
    if (W === 1440) {
      ck('screen opens', await p.locator('#screen-adminforms').isVisible());
      ck('Forms tab shown inside Admin', await p.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].map(t => t.textContent.trim()).join('|')) === 'Forms');
      ck('six forms', (await p.locator('#af-grid .af-card').count()) === 6);
      const imgs = await p.evaluate(() => [...document.querySelectorAll('#af-grid img')].map(i => i.complete && i.naturalWidth > 100));
      ck('every card shows the form picture', imgs.length === 6 && imgs.every(Boolean), imgs);
      ck('Preview / PDF / Share on each card', (await p.locator('#af-grid .af-btns .btn').count()) === 18);
      const tk = await p.evaluate(async () => { await refreshDownloadToken(); return cachedDownloadToken; });
      for (const k of ['leave_office', 'leave_site', 'passport_release', 'passport_submit', 'visa_renewal']) {
        const res = await p.request.get(`${B}/export/admin/forms/${k}?format=pdf&dl=1&token=${encodeURIComponent(tk)}`);
        const buf = await res.body();
        ck(`${k}: PDF downloads`, res.ok() && buf.slice(0, 4).toString() === '%PDF' && /attachment/.test(res.headers()['content-disposition']), res.status());
      }
      const pv = await p.request.get(`${B}/export/admin/forms/leave_office?format=view&token=${encodeURIComponent(tk)}`);
      const html = await pv.text();
      ck('preview page has Download PDF, Print and Share', /Download PDF/.test(html) && /Print/.test(html) && /pv-share/.test(html));
      const pg = await b.newPage(); await pg.goto(`${B}/export/admin/forms/leave_office?format=view&token=${encodeURIComponent(tk)}`); await pg.waitForTimeout(1500);
      ck('preview shows the form page', await pg.evaluate(() => { const i = document.querySelector('.pg img'); return !!(i && i.complete && i.naturalWidth > 1000); }));
      await pg.screenshot({ path: SH + 'forms_preview.png' }); await pg.close();
    }
    const lay = await p.evaluate(() => {
      const out = [];
      if (document.documentElement.scrollWidth > innerWidth + 2) out.push('page scrolls sideways');
      document.querySelectorAll('#screen-adminforms .af-card').forEach(el => { if (el.scrollWidth > el.clientWidth + 2) out.push('spills: ' + el.textContent.slice(0, 30)); });
      return out;
    });
    ck(`layout clean at ${W}`, lay.length === 0, lay);
    await p.screenshot({ path: SH + `forms_${W}.png`, fullPage: W === 390 });
    ck(`no page errors at ${W}`, !p.errs.length, p.errs);
  }
  // help search
  const v = await login(b, 'jomon', 'pass12345');
  for (const w of ['passport', 'leave form', 'visa renewal']) {
    await v.fill('#help-search', ''); await v.type('#help-search', w); await v.waitForTimeout(500);
    const hs = await v.evaluate(() => [...document.querySelectorAll('#help-results > *')].map(x => x.textContent.trim()).join(' | '));
    ck(`help search "${w}" finds the forms`, /forms/i.test(hs), hs.slice(0, 200));
  }
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await b.close();
})();
