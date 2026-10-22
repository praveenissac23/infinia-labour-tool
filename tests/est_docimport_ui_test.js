// Estimation imports from a document: the internal BOQ and the QS variation log as PDFs (read in the
// browser - nothing uploaded), shown first, then brought in.
//   node tests/est_docimport_ui_test.js
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/estdoc_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const C = JSON.parse(execSync(`python3 ${__dirname}/est_docimport_fixtures.py /tmp/claude-0/estdocs`).toString());
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  const errs = [], uploads = []; p.on('pageerror', e => errs.push(e.message));
  p.on('request', r => { if (/multipart/.test(r.headers()['content-type'] || '') || (r.postDataBuffer() || Buffer.alloc(0)).includes(Buffer.from('%PDF'))) uploads.push(r.url()); });
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async path => p.evaluate(async path => (await fetch(path, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), path);
  const meta = await api('/store/est/meta'), P = meta.projects.find(x => x.code === '915').id;
  const go = async sec => { await p.evaluate(([pid, sec]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', sec); }, [P, sec]); await p.goto(B + '/portal/est-app.html?view=projects'); await sleep(1500); };
  // BOQ
  await go('client.boq');
  ck('BOQ: the upload takes PDF / Word / photos', /\.pdf/.test(await p.getAttribute('#boq-up-f', 'accept')));
  await p.setInputFiles('#boq-up-f', C.boq.file); await p.waitForSelector('#m-save', { state: 'visible', timeout: 60000 }); await sleep(400);
  const body = await p.textContent('#m-body');
  ck('BOQ preview: 5 lines in 2 bills, 191,785.00 = the document\'s grand total', /Bring in 5 lines/.test(await p.textContent('#m-save')) && /191,785/.test(body) && /matches the document/.test(body), body.slice(0, 300));
  await p.screenshot({ path: SH + 'boq.png' });
  const rep = await p.$('input[name=boqmode][value=replace]'); if (rep) await rep.check();
  await p.click('#m-save'); await sleep(1800);
  let b = await api(`/store/est/projects/${P}`);
  ck('BOQ saved: 5 lines, 191,785.00, bills A and B', b.boq.length === 5 && Math.abs(b.boq.reduce((a, x) => a + x.amount, 0) - 191785) < .005, [b.boq.length, b.boq.reduce((a, x) => a + x.amount, 0)]);
  // variation log
  await go('client.vo');
  const before = (await api(`/store/est/projects/${P}`)).variations.length;
  await p.setInputFiles('#imp-vo-f', C.volog.file); await p.waitForSelector('#m-save', { state: 'visible', timeout: 60000 }); await sleep(400);
  ck('VO log preview: 3 variations', /Add 3 variations/.test(await p.textContent('#m-save')), await p.textContent('#m-save'));
  await p.screenshot({ path: SH + 'volog.png' });
  await p.click('#m-save'); await sleep(1800);
  b = await api(`/store/est/projects/${P}`);
  const added = b.variations.slice(before);
  const want = [['Additional pergola at roof terrace', 48750, 45000], ['Change of floor tiles to marble in majlis and entrance lobby', 126400, 0], ['Omission of garden pavilion', -32000, -32000]];
  const got = added.map(v => [v.title, v.submitted_amount, v.approved_amount || 0]);
  ck('VO log saved: titles (a wrapped one joined), submitted and approved amounts', JSON.stringify(got) === JSON.stringify(want), got);
  ck('VO log: numbered on from the project\'s own V-numbers', added.every(v => /^V\d{2}$/.test(v.ref || '')), added.map(v => v.ref));
  ck('no file was ever sent to the server', uploads.length === 0, uploads);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
