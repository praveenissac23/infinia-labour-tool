// Estimation > project > Dashboard > Client payment certificates (31 Oct 2026, "match the certificate"): IPA 07's
// Amount due is the certificate's 153,134.00, the app's own 153,134.21 shown only as a small note under it; IPA 06
// (nothing from its certificate) shows the worked-out figure, no note. The certificate form has the certificate boxes.
// Run: seeds the database the server uses (DB, default /tmp/run_js.db) with tests/seed_est_cert.py, then
//      node tests/est_cert_figure_ui_test.js   (serve_like_nginx.py on 8032, a copy of full.db)
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const path = require('path');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/shots/';
const DB = process.env.DB || '/tmp/run_js.db';
execSync(`python3 ${path.join(__dirname, 'seed_est_cert.py')}`, { cwd: path.join(__dirname, '..', 'app'),
  env: { ...process.env, DATABASE_URL: 'sqlite:///' + DB, INFINIA_NO_SCHED: '1', INFINIA_NO_PUSH: '1' }, stdio: 'ignore' });
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = (u) => p.evaluate(async u => (await fetch(u, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), u);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === 'T914').id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'home.dash'); }, [P]); await p.reload(); await sleep(2500);
  const heads = await p.$$eval('#dash-cpc thead th', t => t.map(x => x.textContent.replace(/[▲▼i]/g, '').trim()));
  ck('Dashboard IPA list has an Amount due column before Status', heads.indexOf('Amount due') === heads.length - 2, heads);
  const rows = await p.$$eval('#dash-cpc tbody tr', t => t.map(r => r.textContent.replace(/\s+/g, ' ').trim()));
  const r7 = rows.find(x => /^07/.test(x)) || '', r6 = rows.find(x => /^06/.test(x)) || '';
  ck('IPA 07: Amount due 153,134.00 (the certificate)', /153,134\.00/.test(r7), r7);
  ck('IPA 07: a small note under it "worked out 153,134.21 (−0.21)"', r7.includes('worked out 153,134.21 (−0.21)'), r7);
  const tt = await p.$eval('#dash-cpc .cpc-note', el => el.title).catch(() => '');
  ck('... the full note on hover: "Certificate 153,134.00 · worked out 153,134.21 · difference −0.21 (consultant rounds to whole dirhams)"',
     tt.includes('Certificate 153,134.00 · worked out 153,134.21 · difference −0.21 (consultant rounds to whole dirhams)'), tt);
  const fits = await p.$eval('#dash-cpc .tw', el => el.scrollWidth <= el.clientWidth + 1);
  ck('the list fits its box (no sideways scroll)', fits);
  ck('IPA 06: the worked-out figure, no note', !/worked out/.test(r6) && !/Certificate/.test(r6), r6);
  const fs = await p.$eval('#dash-cpc .cpc-note', el => getComputedStyle(el).fontSize).catch(() => '');
  ck('the note is small', parseFloat(fs) <= 12.5, fs);
  const foot = await p.textContent('#dash-cpc tfoot');
  ck('the Amount due total = IPA 06 worked out 1,231,371.73 + IPA 07 certificate 153,134.00 = 1,384,505.73', foot.includes('1,384,505.73'), foot);
  await p.$eval('#dash-cpc', el => el.scrollIntoView({ block: 'center' })); await sleep(300);
  await p.screenshot({ path: SH + 'est-cert-1-dash.png' });
  // the certificate form (still reachable from code): the three certificate boxes
  await p.evaluate(() => cpcForm(ST.b.clientpcs.find(c => c.seq === 7))); await sleep(800);
  ck('the PC form has the certificate boxes (amount due, VAT, previous payments)',
     await p.$('#f-cert_due') !== null && await p.$('#f-cert_vat') !== null && await p.$('#f-cert_prev') !== null);
  ck('the form shows the full cross-check at the top', (await p.textContent('#m-body')).includes('Certificate 153,134.00'));
  await p.screenshot({ path: SH + 'est-cert-2-form.png' });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
