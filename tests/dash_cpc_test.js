// Project dashboard > Client payment certificates: every IPA (scroll, heading kept), oldest first, Authority
// payments in their own column (taken from the remarks of bills brought in, once), headings sort both ways.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/dcpc_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = (path) => p.evaluate(async path => (await fetch(path, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), path);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === '902').id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'home.dash'); }, [P]); await p.reload(); await sleep(2000);
  const seqs = async () => p.$$eval('#dash-cpc tbody tr td:first-child', t => t.map(x => x.textContent.trim()));
  const s0 = await seqs();
  ck('all 7 IPAs listed (not just 4)', s0.length === 7, s0);
  ck('oldest first: 01 ... 07', s0.join() === '01,02,03,04,05,06,07', s0);
  const auth = await p.$$eval('#dash-cpc tbody tr td:nth-child(4)', t => t.map(x => x.textContent.trim()));
  ck('Authority payments column: 9,720.00 on IPA 02 and 250.00 on IPA 04 (from their remarks)', auth[1] === '9,720.00' && auth[3] === '250.00' && auth[0] === '-', auth);
  ck('total of authority payments 9,970.00', (await p.textContent('#dash-cpc tfoot')).includes('9,970.00'));
  const box = await p.$eval('#dash-cpc .tw', el => ({ h: el.clientHeight, sh: el.scrollHeight, ov: getComputedStyle(el).overflowY }));
  ck('the list sits in a box that scrolls', box.ov === 'auto' && box.h <= 300, box);
  await p.$eval('#dash-cpc', el => el.scrollIntoView({ block: 'center' })); await sleep(300);
  await p.screenshot({ path: SH + '1_asc.png' });
  await p.click('#dash-cpc th[data-dsort="seq"]'); await sleep(300);
  ck('click IPA: newest first', (await seqs()).join() === '07,06,05,04,03,02,01', await seqs());
  await p.click('#dash-cpc th[data-dsort="seq"]'); await sleep(300);
  ck('click again: oldest first', (await seqs()).join() === '01,02,03,04,05,06,07');
  await p.click('#dash-cpc th[data-dsort="authority"]'); await p.click('#dash-cpc th[data-dsort="authority"]'); await sleep(300);
  ck('sort by authority payments (largest first): IPA 02 on top', (await seqs())[0] === '02', await seqs());
  await p.screenshot({ path: SH + '2_sorted.png' });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
