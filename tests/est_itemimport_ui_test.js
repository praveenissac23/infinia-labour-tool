// Subcontract > Item schedule > Upload Excel: a payment certificate read, checked sheet by sheet, saved, then
// opened in the schedule editor.   ITEM_FILE=<certificate.xlsx> node tests/est_itemimport_ui_test.js
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/itui_', FILE = process.env.ITEM_FILE;
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  if (!FILE) { console.log('ITEM_FILE not given - skipped'); return; }
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta'); const P = meta.projects.find(x => x.code === '908').id;
  const sid = (await api('/store/est/subs', { method: 'POST', body: { project_id: P, name: 'AL RAIDA UI TEST ' + (Date.now() % 10000), scope: 'MEP', value: 393000 } })).id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.reg'); }, [P]); await p.reload(); await sleep(1500);
  await p.click(`[data-sub="${sid}"]`); await sleep(500);
  await p.setInputFiles('#s-up-f', FILE); await sleep(2500);
  const body = await p.textContent('#m-body');
  ck('preview: every sheet equal to its total', body.includes('every sheet = its total'), body.slice(0, 300));
  ck('preview: contract lines = subcontract value', body.includes('= subcontract value'));
  await p.screenshot({ path: SH + '1_preview.png' });
  await p.click('#m-save'); await sleep(2500);
  ck('the schedule editor opens with the lines', (await p.locator('#b-body [data-i]').count()) === 43, await p.locator('#b-body [data-i]').count());
  await p.screenshot({ path: SH + '2_editor.png' });
  const it = await api(`/store/est/subs/${sid}/items`);
  ck('saved total 393,000.00', Math.abs(it.total - 393000) < .005, it.total);
  ck('no page errors', !errs.length, errs);
  await api(`/store/est/subs/${sid}`, { method: 'DELETE' });
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
