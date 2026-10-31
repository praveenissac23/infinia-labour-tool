// Estimation uploads read on the server (app/docread) and checked on the confirm screen, through the real screens:
// Previous records - a typed PDF client bill, a scanned client bill, an Excel subcontractor PC (subcontractor added
// from the certificate) and a variation log PDF. For each: the page preview beside the form (PDF.js page / Excel
// grid), a chip on the boxes read, tapping a box marks its place on the page, the sums with ticks at the top, Save
// refused while an amber figure is not confirmed, and the saved figures equal the document's true figures (the
// generator's ground truth). The log brought in twice adds nothing twice; the confirm screen stacks on a phone.
//   BASE=http://127.0.0.1:8750 node tests/est_upload_confirm_ui_test.js      (a server on a COPY of a full database)
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/upconf_';
const CODE = process.env.PROJECT || '901';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const near = (a, b) => Math.abs(Number(a) - Number(b)) < 0.006;
(async () => {
  // the documents and their true figures: made by the reader's own generator (tests/docread/synth.py), seed fixed
  const D = process.env.CORPUS || path.join(require('os').tmpdir(), 'upconf_corpus');
  if (!fs.existsSync(path.join(D, 'truth.json'))) execSync(`python3 ${__dirname}/docread/synth.py ${D} --n 4 --seed 2026 --scans 0.5 --vo 3 --contracts 1`, { stdio: 'ignore' });
  const T = JSON.parse(fs.readFileSync(path.join(D, 'truth.json')));
  const doc = f => { const c = T.find(x => x.file === f); if (!c) throw new Error('not in the corpus: ' + f); return Object.assign({ path: path.join(D, f) }, c); };
  const typed = doc('ipa_00_single.pdf'), scan = doc('ipa_01_three_scan.pdf'), xl = doc('subpc_01_three.xlsx'), vo = doc('vo_01.pdf');

  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 1000 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/health');
  let tok = null;
  for (let i = 0; i < 10 && !tok; i++) { tok = await p.evaluate(async () => { try { const r = await fetch('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username: 'admin', password: 'changeme123' }) }); return (await r.json()).access_token; } catch (e) { return null; } }); if (!tok) await sleep(1500); }
  const api = (u, opt = {}) => p.evaluate(async ([u, t, opt]) => { const r = await fetch(u, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [u, tok, opt]);
  const meta = await api('/store/est/meta');
  const P = meta.projects.find(x => x.code === CODE).id;
  const open = async () => {
    await p.goto(B + '/portal/est-app.html?view=projects');
    await p.evaluate(([t, pid]) => { sessionStorage.setItem('infinia_token', t); localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'prev.rec'); }, [tok, String(P)]);
    await p.goto(B + '/portal/est-app.html?view=projects'); await p.waitForSelector('[data-pup]', { timeout: 20000 });
  };
  await open();
  ck('Previous records: the four upload cards', (await p.$$('[data-pup]')).length === 4);
  const formOpen = async (title, ms = 120000) => { await p.waitForFunction(t => !document.getElementById('modal').classList.contains('hide') && new RegExp(t).test(document.getElementById('m-title').textContent), title, { timeout: ms }); await sleep(600); };
  const amber = () => p.$$eval('#m-body .cfchip.check:not(.done):not(.static)', a => a.map(c => c.dataset.cfk));
  const confirmAll = async () => { for (const k of await amber()) { await p.click(`#m-body .cfchip.check[data-cfk="${k}"]`); await sleep(80); } };
  const saveRefused = async () => {
    const left = (await amber()).length; if (!left) return null;
    await p.click('#m-save'); await sleep(700);
    return !(await p.$eval('#modal', m => m.classList.contains('hide'))) && /amber/.test(await p.textContent('.toast').catch(() => ''));
  };
  const chips = () => p.$$eval('#m-body .frm .cfchip', a => a.map(c => [c.dataset.cfk, c.classList.contains('ok') ? 'ok' : c.classList.contains('derived') ? 'derived' : 'check']));
  const val = k => p.inputValue('#f-' + k).then(v => Number(String(v).replace(/,/g, '')));

  // ---- 1. a typed PDF client bill -------------------------------------------------------------------------
  let reads = 0; p.on('request', r => { if (/\/store\/est\/read\/ipa/.test(r.url()) && /multipart/.test(r.headers()['content-type'] || '')) reads++; });
  await p.setInputFiles('#pf-clientpc', typed.path);
  await formOpen('Previous bill');
  ck('typed PDF bill: the file itself went to the server (multipart)', reads === 1, reads);
  await p.waitForSelector('#m-body .cfv-doc canvas', { timeout: 20000 });
  ck('...the page is shown beside the form (PDF.js)', !!(await p.$('#m-body .cfv-doc canvas')) && !!(await p.$('#m-body .cfv-main .frm')));
  const c1 = await chips();
  ck('...a chip on the figures read (ok / check / derived)', c1.length >= 5 && c1.some(c => c[1] === 'ok'), c1);
  ck('...the sums at the top, every one ticked', (await p.$$('#m-body .prev-chk .ok')).length >= 3 && !(await p.$('#m-body .prev-chk .bad')));
  const t1 = typed.truth;
  ck('...figures as on the bill', (await val('claimed_cum')) === t1.claimed_cum && (await val('ret_cum')) === t1.ret_cum && (await val('adv_rec_cum')) === t1.adv_rec_cum && (await val('seq')) === t1.seq,
     [await val('claimed_cum'), t1.claimed_cum, await val('ret_cum'), t1.ret_cum]);
  await p.click('#f-claimed_cum'); await sleep(500);
  const hl = await p.$eval('#m-body .cfv-hl', e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }).catch(() => null);
  ck('...tapping a box marks where it is on the page', hl && hl[0] > 8 && hl[1] > 6, hl);
  await p.screenshot({ path: SH + '1_typed_bill.png' });
  ck('...Save refused while an amber figure is not confirmed', (await saveRefused()) !== false);
  await confirmAll();
  ck('...every amber figure confirmed: "Every figure checked"', /Every figure checked/.test(await p.textContent('#m-body .cfv-left')));
  const nc0 = (await api(`/store/est/projects/${P}`)).clientpcs.length;
  await p.click('#m-save'); await p.waitForFunction(() => document.getElementById('modal').classList.contains('hide'), null, { timeout: 20000 }); await sleep(1500);
  let b = await api(`/store/est/projects/${P}`);
  const bill1 = b.clientpcs.find(c => c.seq === t1.seq);
  ck('...saved once, figures equal the ground truth', b.clientpcs.length === nc0 + 1 && bill1 && near(bill1.claimed_cum, t1.claimed_cum) && near(bill1.ret_cum, t1.ret_cum) && near(bill1.adv_rec_cum, t1.adv_rec_cum) && bill1.submitted === t1.submitted,
     bill1 && [bill1.claimed_cum, bill1.ret_cum, bill1.adv_rec_cum, bill1.submitted, b.clientpcs.length - nc0]);

  // ---- 2. a scanned client bill (OCR on the server) --------------------------------------------------------
  await p.setInputFiles('#pf-clientpc', scan.path);
  await formOpen('Previous bill', 240000);
  await p.waitForSelector('#m-body .cfv-doc canvas', { timeout: 30000 });
  const t2 = scan.truth;
  ck('scanned bill: the page shown, figures as on the bill', (await val('claimed_cum')) === t2.claimed_cum && (await val('ret_cum')) === t2.ret_cum && (await val('seq')) === t2.seq,
     [await val('claimed_cum'), t2.claimed_cum, await val('ret_cum'), t2.ret_cum, await val('seq'), t2.seq]);
  ck('...the sums ticked', (await p.$$('#m-body .prev-chk .ok')).length >= 3 && !(await p.$('#m-body .prev-chk .bad')));
  await p.click('#f-ret_cum'); await sleep(500);
  ck('...the box marked on the scan', !!(await p.$('#m-body .cfv-hl')));
  await p.screenshot({ path: SH + '2_scan_bill.png' });
  await confirmAll();
  await p.click('#m-save'); await p.waitForFunction(() => document.getElementById('modal').classList.contains('hide'), null, { timeout: 20000 }); await sleep(1500);
  b = await api(`/store/est/projects/${P}`);
  const bill2 = b.clientpcs.find(c => c.seq === t2.seq);
  ck('...saved, figures equal the ground truth', bill2 && near(bill2.claimed_cum, t2.claimed_cum) && near(bill2.ret_cum, t2.ret_cum) && near(bill2.adv_rec_cum, t2.adv_rec_cum), bill2);

  // ---- 3. an Excel subcontractor PC, the subcontractor added from it ---------------------------------------
  await p.setInputFiles('#pf-subpc', xl.path);
  await formOpen('Previous PC');
  await p.waitForSelector('#m-body .cfv-grid', { timeout: 20000 });
  ck('Excel PC: the sheet shown as a small grid', (await p.$$('#m-body .cfv-grid td')).length > 20);
  ck('...the subcontractor offered as a new one', !!(await p.$('#pv-newsub')));
  await p.click('#pv-newsub'); await formOpen('Previous PC'); await p.waitForSelector('#m-body .cfv-grid', { timeout: 20000 });
  const t3 = xl.truth;
  ck('...figures as on the certificate', (await val('work_cum')) === t3.work_cum && (await val('ret_cum')) === t3.ret_cum && (await val('adv_rec_cum')) === t3.adv_rec_cum && (await val('var_cum')) === (t3.var_cum || 0),
     [await val('work_cum'), t3.work_cum, await val('var_cum'), t3.var_cum]);
  await p.click('#f-work_cum'); await sleep(500);
  const cell = await p.$eval('#m-body .cfv-grid td.hl', e => e.textContent).catch(() => null);
  ck('...tapping a box marks its cell in the grid', cell && Number(cell.replace(/[^0-9.]/g, '')) === t3.work_cum, cell);
  ck('...the app agrees with the certificate (net, VAT, amount due)', (await p.$$('#pv-calc .ok')).length >= 3 && !(await p.$('#pv-calc .bad')), (await p.textContent('#pv-calc')).replace(/\s+/g, ' ').slice(0, 300));
  await p.screenshot({ path: SH + '3_excel_pc.png' });
  ck('...Save refused while an amber figure is not confirmed', (await saveRefused()) !== false);
  await confirmAll();
  await p.click('#m-save'); await p.waitForFunction(() => document.getElementById('modal').classList.contains('hide'), null, { timeout: 20000 }); await sleep(1500);
  b = await api(`/store/est/projects/${P}`);
  const sub = b.subs.find(s => /woodcraft/i.test(s.name));
  const pc = sub && sub.pcs.find(x => x.seq === t3.seq);
  ck('...saved, figures equal the ground truth', pc && near(pc.work_cum, t3.work_cum) && near(pc.var_cum, t3.var_cum || 0) && near(pc.ret_cum, t3.ret_cum) && near(pc.adv_rec_cum, t3.adv_rec_cum) && near(pc.this, t3.net) && near(pc.vat, t3.vat),
     pc && [pc.work_cum, pc.var_cum, pc.ret_cum, pc.adv_rec_cum, pc.this, t3.net, pc.vat, t3.vat]);
  ck('...earlier PCs as one opening line: previously certified as on the paper', sub && sub.pcs.length === 2 && near(sub.pcs[0].net_cum, t3.prev_cert), sub && sub.pcs.map(x => [x.seq, x.net_cum]));
  ck('the queue: every file Saved', (await p.$$eval('#sec td .st', a => a.filter(x => /Saved/.test(x.textContent)).length)) >= 3);

  // ---- 4. a variation log PDF --------------------------------------------------------------------------------
  const nv0 = b.variations.length;
  await p.setInputFiles('#pf-variation', vo.path);
  await formOpen('Import', 120000);
  await p.waitForSelector('#m-body .cfv-doc canvas', { timeout: 20000 });
  const rowsShown = await p.$$eval('#vo-lines tbody tr', a => a.length);
  ck('variation log PDF: every line, the page beside them', rowsShown === vo.truth.length, [rowsShown, vo.truth.length]);
  ck('...a chip on each line', (await p.$$('#vo-lines .cfchip')).length === rowsShown);
  await p.click('#vo-lines tbody tr:nth-child(2) td:nth-child(2)'); await sleep(500);
  ck('...tapping a line marks it on the page', !!(await p.$('#m-body .cfv-hl')));
  await p.screenshot({ path: SH + '4_vo_log.png' });
  if ((await amber()).length) ck('...Save refused while a line is not confirmed', (await saveRefused()) !== false);
  await confirmAll();
  await p.click('#m-save'); await p.waitForFunction(() => document.getElementById('modal').classList.contains('hide'), null, { timeout: 30000 }); await sleep(1500);
  b = await api(`/store/est/projects/${P}`);
  const added = b.variations.slice(nv0);
  const sum = (a, k) => Math.round(a.reduce((n, x) => n + (Number(x[k]) || 0), 0) * 100) / 100;
  ck('...every line saved, the amounts equal the ground truth', added.length === vo.truth.length && near(sum(added, 'submitted_amount'), sum(vo.truth, 'submitted_amount')) && near(sum(added, 'approved_amount'), sum(vo.truth, 'approved_amount')),
     [added.length, vo.truth.length, sum(added, 'submitted_amount'), sum(vo.truth, 'submitted_amount'), sum(added, 'approved_amount'), sum(vo.truth, 'approved_amount')]);
  const same = t => added.find(a => a.title === t.title && near(a.submitted_amount, t.submitted_amount) && near(a.approved_amount, t.approved_amount) && a.status === t.status);
  ck('...each line as on the log (description, submitted / approved amount, status)', vo.truth.every(same), vo.truth.filter(t => !same(t)).map(t => [t.title, t.submitted_amount, t.status, (added.find(a => a.title === t.title) || {}).status]));

  // ---- 5. on a phone: the page above the boxes; the same log again adds nothing --------------------------------
  await p.setViewportSize({ width: 390, height: 844 }); await sleep(400);
  await p.setInputFiles('#pf-variation', vo.path);
  await formOpen('Import', 120000);
  await p.waitForSelector('#m-body .cfv-doc canvas', { timeout: 20000 });
  const lay = await p.evaluate(() => { const d = document.querySelector('#m-body .cfv-doc').getBoundingClientRect(), m = document.querySelector('#m-body .cfv-main').getBoundingClientRect(); return [d.top < m.top, d.width > 300, m.width > 300, document.documentElement.scrollWidth <= innerWidth + 1]; });
  ck('phone: the page above the lines, both full width, nothing sideways', lay.every(Boolean), lay);
  await p.screenshot({ path: SH + '5_phone.png', fullPage: false });
  await confirmAll();
  await p.click('#m-save'); await p.waitForFunction(() => document.getElementById('modal').classList.contains('hide'), null, { timeout: 30000 }); await sleep(1500);
  b = await api(`/store/est/projects/${P}`);
  ck('...the same log brought in again adds nothing twice', b.variations.length === nv0 + vo.truth.length, [b.variations.length, nv0 + vo.truth.length]);
  ck('no page errors', errs.length === 0, errs);
  await br.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})().catch(e => { console.log('FAIL crashed: ' + (e && e.stack || e)); process.exit(1); });
