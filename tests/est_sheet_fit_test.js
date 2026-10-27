// The PC sheet fits the window: Contract works needs no sideways scroll on a normal laptop (1366 / 1440 / 1920
// wide, inside the app with its menu), the figures go under the tables when there is no room beside them,
// and the total due stays in view beside the floating Save.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/fit_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'] });   // scroll bars as people see them
  const a = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); const errs = []; a.on('pageerror', e => errs.push(e.message));
  await a.goto(B + '/'); await a.fill('#login-username', 'admin'); await a.fill('#login-password', 'changeme123'); await a.evaluate('doLogin()'); await sleep(2500);
  const api = async (path, opt = {}) => a.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta'); const P = meta.projects.find(x => x.code === '913').id, run = Date.now() % 100000;
  const sid = (await api('/store/est/subs', { method: 'POST', body: { project_id: P, name: 'M/s. AL RAIDA ELECTROMECHANICAL SERVICES LLC ' + run, scope: 'Electrical, Low Current, Telephone, Home Automation, CCTV, Plumbing, Drainage And HVAC Works', value: 568800 } })).id;
  await api(`/store/est/subs/${sid}/items`, { method: 'PUT', body: { items: [
    { no: '1', description: 'Complete Electrical works', qty: 1, unit: 'LS', rate: 172800, amount: 172800, measure: 'pct' },
    { no: '2', description: 'Complete Plumbing, Water Supply & Drainage works', qty: 1, unit: 'LS', rate: 153000, amount: 153000, measure: 'pct' },
    { no: '6', description: 'Complete VRF System from brand Daikin Asia with Flow bar grill', qty: 1, unit: 'LS', rate: 243000, amount: 243000, measure: 'pct' }] } });
  const pcid = (await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sid, inv_ref: 'INV/ALA/AREMS-1040/26', inv_amount: 119448 } })).id;
  for (const [w, h] of [[1366, 768], [1440, 900], [1920, 1080]]) {
    await a.setViewportSize({ width: w, height: h });
    await a.goto(B + '/?p=estimation#estproj'); await sleep(3000);
    let fr = a.frames().find(f => /est-app\.html/.test(f.url()) && /view=projects/.test(f.url()));
    await fr.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.reg'); }, [P]); await fr.evaluate(() => location.reload()); await sleep(2500);
    fr = a.frames().find(f => /est-app\.html/.test(f.url()) && /view=projects/.test(f.url()));
    await fr.click(`[data-sub="${sid}"]`); await sleep(600); await fr.click(`[data-pc="${pcid}"]`); await sleep(1500);
    const m = await fr.evaluate(() => { const tw = document.querySelector('table.sl').closest('.tw'); const bb = document.querySelector('#b-body');
      const tools = document.querySelector('#b-tools').getBoundingClientRect(), hd = document.querySelector('#big .mhead').getBoundingClientRect();
      return { scroll: tw.scrollWidth - tw.clientWidth, page: bb.scrollWidth - bb.clientWidth, side: getComputedStyle(document.querySelector('.sheet')).gridTemplateColumns.split(' ').length,
               toolsIn: tools.right <= hd.right + 1, tot: (document.querySelector('#sb-tot') || {}).textContent || '' }; });
    ck(`${w}px: Contract works fits - no sideways scroll`, m.scroll <= 1, m);
    ck(`${w}px: the page itself has no sideways scroll`, m.page <= 1, m);
    ck(`${w}px: header buttons inside the window`, m.toolsIn, m);
    ck(`${w}px: total due beside Save`, /Total due/.test(m.tot) && /AED/.test(m.tot), m.tot);
    if (w === 1920) ck('1920px: figures beside the tables', m.side === 2, m); else ck(`${w}px: figures go under the tables`, m.side === 1, m);
    await a.screenshot({ path: SH + w + '.png' });
    await fr.evaluate(() => document.querySelector('.sh-side').scrollIntoView()); await sleep(300);
    if (w === 1366) await a.screenshot({ path: SH + w + '_bottom.png' });
  }
  // narrow window (half screen): a scroll bar appears and is always visible
  await a.setViewportSize({ width: 900, height: 800 }); await sleep(800);
  const fr = a.frames().find(f => /est-app\.html/.test(f.url()) && /view=projects/.test(f.url()));
  await fr.evaluate(() => document.querySelector('table.sl').scrollIntoView({ block: 'center' })); await sleep(300);
  const sb = await fr.evaluate(() => { const tw = document.querySelector('table.sl').closest('.tw'); return { need: tw.scrollWidth > tw.clientWidth, bar: tw.offsetHeight - tw.clientHeight }; });
  ck('half-width window: the table scrolls sideways with a visible bar', !sb.need || sb.bar >= 10, sb);
  await a.screenshot({ path: SH + '900.png' });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
