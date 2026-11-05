// Variations (5 Nov 2026): the numbers sent to the consultant (CP01, CP02 ... from the QS log) put back on a past log
// with a preview first; new ones carry on V..; any variation's number (and everything else) edits in its form.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/full.db 8650 tests/vo_numbers_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const SH = process.env.SHOTS || '/tmp/claude-0/ui2/vonum_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(2000);
  const api = (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === '909').id;
  await p.evaluate(pid => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'site.vo'); }, String(P));
  await p.reload(); await p.waitForSelector('table.vlog', { timeout: 20000 }); await sleep(600);
  const refs = () => p.$$eval('table.vlog tr.rowc td.ref', t => t.map(x => x.textContent.trim()));
  const before = await refs();
  ck('909 shows V01..V17 now', before[0] === 'V01' && before.length >= 17, before);
  ck('the button is there', await p.isVisible('#qs-vo'));
  await p.click('#qs-vo'); await sleep(800);
  const prev = await p.$$eval('#m-body tbody tr', t => t.map(r => [...r.children].slice(0, 2).map(c => c.textContent.trim())));
  ck('preview: now / will be, CP01 first', prev[0][0] === 'V01' && prev[0][1] === 'CP01' && prev.length === 17, prev.slice(0, 4));
  ck('... the next new number is said', /next one is V04/.test(await p.textContent('#m-body')));
  await p.screenshot({ path: SH + '1_preview.png' });
  ck('nothing changed until saved', JSON.stringify(await refs()) === JSON.stringify(before));
  await p.click('#m-save'); await sleep(1500);
  const after = await refs();
  ck('saved: CP01, CP02, CP02, CP02, CP03 ... V01 ... OHP-1', after.slice(0, 5).join() === 'CP01,CP02,CP02,CP02,CP03' && after.includes('OHP-1'), after);
  await p.screenshot({ path: SH + '2_log.png', fullPage: true });
  // a new one carries on V04
  await p.click('#add-vo'); await sleep(400);
  ck('a new variation is offered V04', (await p.inputValue('#f-ref')) === 'V04', await p.inputValue('#f-ref'));
  await p.fill('#f-title', 'Extra landscape lights'); await p.click('#m-save'); await sleep(1500);
  ck('... and saved as V04', (await refs()).includes('V04'));
  // edit any number by hand, and the other fields
  const id = await p.$eval('table.vlog tr.rowc', r => r.dataset.vo);
  await p.click(`[data-vo="${id}"] td.desc`); await sleep(500);
  ck('the number box can be typed in', !(await p.$eval('#f-ref', x => x.readOnly)));
  await p.fill('#f-ref', 'CP01.A'); await p.fill('#f-title', 'Supply & Installation of Lift (corrected)');
  await p.screenshot({ path: SH + '3_form.png' });
  await p.click('#m-save'); await sleep(1500);
  const row = (await p.textContent(`[data-vo="${id}"]`)).replace(/\s+/g, ' ');
  ck('number and description saved', /CP01\.A/.test(row) && /\(corrected\)/.test(row), row);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
