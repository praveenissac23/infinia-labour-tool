// Overview > BOQ & budget: the internal BOQ workbook uploaded, previewed bill by bill against its own
// summary, saved, then shown one row per trade (opened with a click). Since 3 Nov 2026 only priced lines come in
// (excluded / phase 2 listed, not brought in) - see also boq_upload_ui_test.js (WS-25 R10, tick & delete).
//   BOQ_FILE=<internal BOQ.xlsx> node tests/est_boqimport_ui_test.js
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/boqui_', FILE = process.env.BOQ_FILE;
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const goSec = async (pg, gs) => { const [g, s] = gs.split('.'); await pg.click(`#pnav [data-g="${g}"]`); await sleep(300); if (g !== 'home') await pg.click(`#psub [data-s="${s}"]`); };
(async () => {
  if (!FILE) { console.log('BOQ_FILE not given - skipped'); return; }
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta');
  const P = meta.projects.find(x => x.code === '922').id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'client.boq'); }, [P]); await p.reload(); await sleep(1500);
  await goSec(p, 'client.boq'); await sleep(400);
  await p.setInputFiles('#boq-up-f', FILE); await sleep(2500);
  ck('preview opens with the bills', /02\. Sub ?structure/i.test(await p.textContent('#m-body')));
  ck('preview: total tallies with the workbook summary', (await p.textContent('#m-body')).includes('tallies with the SUMMARY sheet'), await p.textContent('#m-body'));
  await p.screenshot({ path: SH + '1_preview.png' });
  const r = p.locator('input[name=boqmode][value=replace]'); if (await r.count()) await r.check();
  await p.click('#m-save'); await sleep(2000);
  const b = await api(`/store/est/projects/${P}`);
  ck('BOQ value = 5,598,800.00 (the workbook total)', Math.abs(b.summary.boq_value - 5598800) < .005, b.summary.boq_value);
  ck('one row per trade, closed', (await p.locator('tr.bill').count()) === 20 && (await p.locator('table.boq tbody tr:not(.bill):not(.tot)').count()) === 0, await p.locator('tr.bill').count());
  await p.screenshot({ path: SH + '2_bills.png' });
  const sub = p.locator('tr.bill').filter({ hasText: /02\. Sub ?structure/i }).first();
  await sub.click(); await sleep(400);
  ck('a trade opens with its sections and lines', (await p.locator('tr.sec').count()) >= 5 && (await p.locator('table.boq tbody tr:not(.bill):not(.tot):not(.sec)').count()) > 0);
  await p.screenshot({ path: SH + '3_substructure.png', fullPage: true });
  await sub.click(); await sleep(300);
  await p.fill('[data-q]', 'raft'); await sleep(900);
  ck('search finds lines across closed trades', (await p.locator('table.boq tbody tr:not(.bill):not(.tot):not(.sec)').count()) >= 1);
  await p.screenshot({ path: SH + '4_search.png' });
  ck('no page errors', !errs.length, errs);
  await br.close();
  console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
