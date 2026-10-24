// Estimation > a project > Previous records, in the browser: a subcontractor PC (PDF) for a subcontractor not on the
// project (added from the certificate, earlier PCs as one opening line - the totals come out right), a subcontract
// agreement read into the subcontract form, a variation log, and the last client bill (Excel) saved and kept as the
// bill format. Files: the samples attached in this session (PREV_DIRS).
const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/prevui_';
const DIRS = (process.env.PREV_DIRS || '/root/.claude/uploads/80e871d8-70e2-5c6a-a360-434939dea359/:/mnt/user-data/attachments/80e871d8-70e2-5c6a-a360-434939dea359/').split(':');
const file = pat => { for (const d of DIRS) { try { const n = fs.readdirSync(d).find(x => x.includes(pat)); if (n) return d + n; } catch (e) {} } throw new Error('sample missing: ' + pat); };
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await br.newPage({ viewport: { width: 1440, height: 1000 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = path => p.evaluate(async path => (await fetch(path, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), path);
  let meta = {};
  for (let i = 0; i < 10 && !meta.projects; i++) { meta = await api('/store/est/meta').catch(() => ({})); if (!meta.projects) await sleep(1500); }
  const P = meta.projects.find(x => x.code === '909').id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'prev.rec'); }, [P]); await p.reload(); await sleep(2500);
  ck('Previous records is a tab with the four kinds', (await p.textContent('#pnav')).includes('Previous records') && (await p.$$('[data-pup]')).length === 4);
  await p.screenshot({ path: SH + '0_tab.png' });

  // ---- a subcontractor PC, the subcontractor not on 909 yet
  await p.setInputFiles('#pf-subpc', file('915-RoyalEverest-PC12')); await sleep(6000);
  ck('the PC opens on its form, every check of the certificate agreeing', /Previous PC/.test(await p.textContent('#m-title')) && (await p.$$('.prev-chk .ok')).length === 4 && !(await p.$('.prev-chk .bad')));
  ck('the subcontractor is offered as a new one', !!(await p.$('#pv-newsub')));
  await p.click('#pv-newsub'); await sleep(2500);
  ck('...added and picked; figures read', /Royal/i.test(await p.$eval('#f-sub_id', e => e.options[e.selectedIndex].text)) && (await p.inputValue('#f-work_cum')) === '104037.5');
  const calc = await p.textContent('#pv-calc');
  ck('earlier PCs as one opening line: the app agrees with the certificate on every line', (await p.$$('#pv-calc .ok')).length === 4 && !(await p.$('#pv-calc .bad')), calc.replace(/\s+/g, ' '));
  await p.screenshot({ path: SH + '1_pc.png' });
  await p.click('#m-save'); await sleep(3000);
  let b = await api(`/store/est/projects/${P}`);
  const s = b.subs.find(x => /royal/i.test(x.name));
  ck('saved: PC 12 after an opening line of PC 01-11', s && s.pcs.length === 2 && s.pcs[1].seq === 12 && Math.abs(s.pcs[0].net_cum - 95198.75) < 0.01, s && s.pcs.map(x => [x.seq, x.net_cum]));
  ck('the subcontractor\'s totals come out right: certified 104,937.50, nothing left to pay', s && Math.abs(s.certified - 104937.5) < 0.01 && Math.abs(s.to_pay) < 0.01 && Math.abs(s.work_done - 105887.5) < 0.01, s && [s.certified, s.to_pay, s.work_done]);
  ck('this certificate as on the paper: 9,738.75 + VAT 486.94', s && Math.abs(s.pcs[1].this - 9738.75) < 0.01 && Math.abs(s.pcs[1].vat - 486.94) < 0.01, s && [s.pcs[1].this, s.pcs[1].vat]);
  ck('the queue says Saved', /Saved/.test(await p.textContent('#sec')));

  // ---- a subcontract agreement
  await p.setInputFiles('#pf-contract', file('Joinery_Subcontract_Agreement')); await sleep(1200);
  await p.click('#pv-sca'); await sleep(6000);
  ck('the agreement is read into the subcontract form', /Woodcraft/i.test(await p.inputValue('#f-name')) && /Filled in/.test(await p.textContent('#ag-out')));
  await p.click('#m-save'); await sleep(3000);
  b = await api(`/store/est/projects/${P}`);
  ck('...saved as a subcontract', b.subs.some(x => /woodcraft/i.test(x.name)));

  // ---- a variation log
  const nv = b.variations.length;
  await p.setInputFiles('#pf-variation', file('909_-Variation_Logs')); await sleep(4000);
  ck('the variation log opens in the log import', /Import/.test(await p.textContent('#m-title')));
  await p.click('#m-save'); await sleep(3000);
  b = await api(`/store/est/projects/${P}`);
  ck('...variations added', b.variations.length > nv, [nv, b.variations.length]);

  // ---- the last client bill (Excel), kept as the bill format
  const nc = b.clientpcs.length;
  await p.setInputFiles('#pf-clientpc', file('909-IPA09.xlsx')); await sleep(5000);
  ck('the bill opens with its figures and every check agreeing', (await p.inputValue('#f-claimed_cum')) === '3589674.7' && (await p.inputValue('#f-adv_rec_cum')) === '393189.31' && !(await p.$('.prev-chk .bad')));
  ck('"use as the bill format" is ticked for the last bill', await p.$eval('#pv-fmt', e => e.checked));
  await p.screenshot({ path: SH + '2_bill.png' });
  await p.click('#m-save'); await sleep(9000);
  b = await api(`/store/est/projects/${P}`);
  const c = b.clientpcs[b.clientpcs.length - 1];
  ck('bill 9 saved, as on the bill', b.clientpcs.length === nc + 1 && c.seq === 9 && Math.abs(c.claimed_cum - 3589674.7) < 0.01 && c.status === 'Paid', c);
  const fl = await api(`/store/est/ipa/list?project_id=${P}`);
  ck('...and kept as the bill format: every formula as Excel', fl.formats.some(f => f.lines > 100 && f.same === f.formulas), fl.formats.map(f => [f.lines, f.same, f.formulas]));
  await p.screenshot({ path: SH + '3_queue.png' });
  ck('no page errors', errs.length === 0, errs);
  await br.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
