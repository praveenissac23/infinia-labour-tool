// Site & technical > Submittals as the material submittal log: grouped by discipline, Sr. No / material /
// specification / supplier / rev / submitted / reviewed / consultant status (NS UR A AAN R&R R), another supplier
// under its item; status picked stamps the date; a new line lands in its discipline; Excel in the log's layout.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/sbm_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'] });
  const a = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); const errs = []; a.on('pageerror', e => errs.push(e.message));
  await a.goto(B + '/'); await a.fill('#login-username', 'admin'); await a.fill('#login-password', 'changeme123'); await a.evaluate('doLogin()'); await sleep(2500);
  const P = await a.evaluate(async () => (await (await fetch('/store/est/meta', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).projects.find(x => x.code === '914').id);
  await a.goto(B + '/?p=estimation#estproj'); await sleep(3000);
  let fr = a.frames().find(f => /est-app\.html/.test(f.url()) && /view=projects/.test(f.url()));
  await fr.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'site.submittal'); }, [P]); await fr.evaluate(() => location.reload()); await sleep(2500);
  fr = a.frames().find(f => /est-app\.html/.test(f.url()) && /view=projects/.test(f.url()));
  const grp = await fr.$$eval('tr.sb-grp b', t => t.map(x => x.textContent));
  ck('grouped as on the log: CIVIL, ELECTRICAL, PLUMBING, HVAC, SHOP DRAWINGS', grp.join() === 'CIVIL,ELECTRICAL,PLUMBING,HVAC,SHOP DRAWINGS', grp);
  ck('52 lines of 914', (await fr.$$('tr.sb-row')).length === 52);
  const hdr = await fr.$$eval('table.sb thead th', t => t.map(x => x.textContent.trim().replace(/\s+/g, ' ')));
  ck('columns as the log', ['Sr. No', 'Material description', 'Specification', 'Manufacturer / supplier', 'Rev', 'Submitted', 'Reviewed', 'Consultant status'].every((h, i) => hdr[i].startsWith(h)), hdr);
  const conc = await fr.$$eval('tr.sb-row', t => t.slice(1, 3).map(r => r.textContent.replace(/\s+/g, ' ').trim()));
  ck('Concrete: Emirates SAS, then Shafa Al Nahdah under it as another supplier', /Concrete.*Emirates SAS/.test(conc[0]) && /another supplier.*SHAFA AL NAHDAH/.test(conc[1]), conc);
  const st = await fr.$eval('tr.sb-row:nth-of-type(2) select.sb-st', s => s.options[s.selectedIndex].text);
  ck('status shown as the consultant code: AAN · As noted', st === 'AAN · As noted', st);
  const page = await fr.evaluate(() => { const w = document.querySelector('.sb-wrap'); return { side: w.scrollWidth - w.clientWidth }; });
  ck('fits the window at 1440 - no sideways scroll', page.side <= 2, page);
  await a.screenshot({ path: SH + '1_log.png' });
  // pick a status: UR -> AAN stamps today as reviewed
  const ur = await fr.$$eval('select.sb-st', s => s.findIndex(x => x.value === 'Under review'));
  const sels = await fr.$$('select.sb-st'); const id = await sels[ur].getAttribute('data-sbst');
  await sels[ur].selectOption('Approved as noted'); await sleep(1500);
  const row = await fr.evaluate(async id => (await (await fetch('/store/est/projects/' + JSON.parse(localStorage.getItem('est_pid')), { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).logs.find(l => l.id === +id), id);
  ck('picking AAN stamps today as reviewed', row.status === 'Approved as noted' && !!row.replied, row);
  // + Add to electrical: a new line at the end of ELECTRICAL with the next Sr. No
  await fr.click('[data-sbadd="ELECTRICAL"]'); await sleep(500);
  await fr.fill('#f-title', 'Distribution Boards'); await fr.fill('#f-spec', 'Schneider'); await fr.click('#m-save'); await sleep(1800);
  const elec = await fr.evaluate(() => { const rows = [...document.querySelectorAll('table.sb tbody')].find(b => b.querySelector('.sb-grp b').textContent === 'ELECTRICAL'); return [...rows.querySelectorAll('tr.sb-row')].map(r => r.cells[1].textContent.trim()); });
  ck('+ Add to electrical: the new line is the last of ELECTRICAL', elec[elec.length - 1] === 'Distribution Boards', elec.slice(-3));
  // Excel in the log's layout
  const xl = await fr.evaluate(async () => { const t = await (await fetch('/auth/download-token', { method: 'POST', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json();
    const r = await fetch(`/export/est/submittal?token=${t.token || t.download_token}&format=excel&pid=${localStorage.getItem('est_pid')}`); return [r.status, (await r.arrayBuffer()).byteLength]; });
  ck('Excel export works', xl[0] === 200 && xl[1] > 3000, xl);
  // narrow laptop
  await a.setViewportSize({ width: 1366, height: 768 }); await sleep(800);
  await a.screenshot({ path: SH + '2_1366.png' });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
