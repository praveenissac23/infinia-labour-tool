// Estimation: a project under several contracts with the client (914: Shell & Core, MEP, Swimming pool).
// The Bills tab shows one contract at a time - its own bill format, bills and figures; the dashboard shows each and the total.
const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/ctr_';
const D = process.env.BILLS_DIR || '/mnt/user-data/attachments/80e871d8-70e2-5c6a-a360-434939dea359/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const file = pat => D + fs.readdirSync(D).find(n => n.includes(pat) && n.endsWith('.xlsx'));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  let meta = {}; for (let i = 0; i < 10 && !meta.projects; i++) { meta = await api('/store/est/meta').catch(() => ({})); if (!meta.projects) await sleep(1500); }
  const P = meta.projects.find(x => x.code === '914').id;
  await api(`/store/est/projects/${P}`, { method: 'PATCH', body: { contract_value: 4850000, adv_pct: 10, ret_pct: 10, vat_pct: 5 } });
  await p.evaluate(pid => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, P); await p.reload(); await sleep(1800);
  // one agreement today: its format and a bill, as before
  await p.click('#ipa-up'); await sleep(300); await p.setInputFiles('#fm-file', file('914_-_IPA_-_07')); await p.click('#m-save'); await sleep(8000);
  await p.click('#ipa-new'); await sleep(3500); await p.keyboard.press('Escape'); await p.evaluate(() => { const x = document.querySelector('#big .x, #b-x'); if (x) x.click(); }); await sleep(800);
  await p.evaluate(pid => { localStorage.setItem('est_sec', 'bills.ipa'); }, P); await p.reload(); await sleep(1800);
  ck('one contract: no contract row, "+ Another contract" offered', !(await p.$('.ctrs')) && await p.isVisible('#ctr-add'));
  // add MEP: the existing agreement is named Shell & Core
  await p.click('#ctr-add'); await sleep(400);
  await p.fill('#f-first_name', 'Shell & Core'); await p.fill('#f-name', 'MEP'); await p.fill('#f-ref', 'IC/914/MEP'); await p.fill('#f-value', '1620000'); await p.fill('#f-ret_pct', '5'); await p.fill('#f-adv_pct', '0');
  await p.screenshot({ path: SH + '1_add.png' });
  await p.click('#m-save'); await sleep(2500);
  // and the pool
  await p.click('#ctr-add'); await sleep(400);
  await p.fill('#f-name', 'Swimming pool'); await p.fill('#f-ref', 'IC/914/POOL'); await p.fill('#f-value', '385000'); await p.click('#m-save'); await sleep(2500);
  let chips = await p.$$eval('.ctr[data-ctrpick] b', x => x.map(y => y.textContent));
  ck('three contracts on the Bills tab', JSON.stringify(chips) === JSON.stringify(['Shell & Core', 'MEP', 'Swimming pool']), chips);
  ck('the new contract (pool) is picked, with no bills and no format yet', /Swimming pool/.test(await p.textContent('.ctr.on')) && !(await p.$('[data-ipa]')) && /No bill format for the Swimming pool contract/.test(await p.textContent('#sec')));
  // Shell & Core keeps the bill made before
  await p.click('.ctr[data-ctrpick]:has-text("Shell & Core")'); await sleep(1500);
  ck('Shell & Core: its bill and format stayed with it', (await p.$$('[data-ipa]')).length === 1 && /4,850,000/.test(await p.textContent('.ctrk')), await p.textContent('.ctrk'));
  await p.screenshot({ path: SH + '2_shell.png' });
  // MEP: its own format and bill
  await p.click('.ctr[data-ctrpick]:has-text("MEP")'); await sleep(1500);
  ck('MEP: nothing of Shell & Core shows', (await p.$$('[data-ipa]')).length === 0);
  await p.click('#ipa-up'); await sleep(300); await p.setInputFiles('#fm-file', file('913-IPA_09')); await p.click('#m-save'); await sleep(8000);
  await p.click('#ipa-new'); await sleep(3500); await p.evaluate(() => { const x = document.querySelector('#big .x, #b-x'); if (x) x.click(); }); await sleep(800);
  await p.reload(); await sleep(1800);
  ck('MEP picked again after reload, with its one bill', /MEP/.test(await p.textContent('.ctr.on')) && (await p.$$('[data-ipa]')).length === 1);
  await p.screenshot({ path: SH + '3_mep.png' });
  const L = await api(`/store/est/ipa/list?project_id=${P}`);
  const b = await api(`/store/est/projects/${P}`); const ks = b.contracts;
  const id = n => ks.find(k => k.name === n).id;
  ck('server: each bill is on its own contract', L.bills.filter(x => x.contract_id === id('Shell & Core')).length === 1 && L.bills.filter(x => x.contract_id === id('MEP')).length === 1, L.bills.map(x => x.contract_id));
  ck('project contract value = 4,850,000 + 1,620,000 + 385,000', b.summary.contract === 6855000, b.summary.contract);
  // a variation must say which contract
  await p.evaluate(() => { localStorage.setItem('est_sec', 'site.vo'); }); await p.reload(); await sleep(1800);
  await p.click('#add-vo'); await sleep(400);
  ck('variation form asks for the contract', await p.isVisible('#f-contract_id'));
  await p.fill('#f-title', 'Pool underwater lights'); await p.selectOption('#f-contract_id', String(id('Swimming pool'))); await p.click('#m-save'); await sleep(1500);
  ck('variation shows its contract', /Swimming pool/.test(await p.textContent('tr:has-text("Pool underwater lights")')));
  // dashboard
  await p.evaluate(() => { localStorage.setItem('est_sec', 'home.dash'); }); await p.reload(); await sleep(2000);
  const rows = await p.$$eval('[data-ctr]', x => x.length);
  ck('dashboard: a line per contract and the project total', rows === 3 && /Project 914 total/.test(await p.textContent('#sec')));
  await p.screenshot({ path: SH + '4_dash.png', fullPage: false });
  await p.click('[data-ctr]:has-text("MEP")'); await sleep(1800);
  ck('clicking a contract on the dashboard opens its bills', /MEP/.test(await p.textContent('.ctr.on')));
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
