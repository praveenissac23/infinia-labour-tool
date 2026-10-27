// The payment certificate sheet in the browser: schedule pasted from Excel, invoice in, the sheet filled
// (quantities, deductions, one not taken), live figures = server, certify, sign, print. 913 Shoring PC05 figures.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/pcui_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const goSec = async (pg, gs) => { const [g, s] = gs.split('.'); await pg.click(`#pnav [data-g="${g}"]`); await new Promise(r => setTimeout(r, 300)); if (g !== 'home') await pg.click(`#psub [data-s="${s}"]`); };

(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta');
  const P = meta.projects.find(x => x.code === '913').id;
  const run = Date.now() % 100000;
  const sid = (await api('/store/est/subs', { method: 'POST', body: { project_id: P, name: 'ONEGB PILING ' + run, scope: 'Shoring', value: 0, contract_type: 'Unit rate re-measurement contract' } })).id;
  for (const w of [50000, 100000, 150000, 209467]) await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sid, inv_ref: 'OLD', work_cum: w } });
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.reg'); }, [P]); await p.reload(); await sleep(1500);
  await p.click(`[data-sub="${sid}"]`); await sleep(500);
  ck('subcontract page shows the item schedule card', (await p.textContent('#d-body')).includes('Item schedule'));
  await p.click('#s-paste'); await sleep(300);
  await p.fill('#f-text', '1\tDesign, shop drawings, shoring permit, mobilization\t1\tLS\t15,000.00\t15,000.00\n2\tSupply and install secant piles\t26.8\tL.M\t6,800.00\t182,240.00\n3\tH beam and anchors\t1\tLS\t60,580.00\t60,580.00');
  ck('re-measurable subcontract: paste defaults to quantity x rate', (await p.inputValue('#f-measure')) === 'qty');
  await p.click('#m-save'); await sleep(1200);
  const it = await api(`/store/est/subs/${sid}/items`);
  ck('3 lines pasted, 257,820.00', it.items.length === 3 && Math.abs(it.total - 257820) < .01, it.total);
  // invoice in -> Certify opens the sheet
  await p.click('#s-inv'); await sleep(300); await p.fill('#f-inv_ref', '1GB/585/04/2025'); await p.fill('#f-inv_amount', '35912'); await p.click('#m-save'); await sleep(1200);
  await p.click('#d-back'); await sleep(200); await goSec(p, 'subs.inv'); await sleep(500);
  const pc = (await api(`/store/est/projects/${P}`)).subs.find(x => x.id === sid).pcs.at(-1);
  await p.click(`[data-pc="${pc.id}"][data-to="Certified"]`); await sleep(500);   // certified at site
  await p.click('#m-save'); await sleep(1000);
  await p.click(`[data-pc="${pc.id}"][data-to="open"]`); await sleep(1200);       // Open PC -> the sheet
  ck('Open PC opens the full sheet (the subcontract has a schedule)', await p.isVisible('#big') && (await p.textContent('#b-title')).includes('PC 05'));
  const qs = await p.$$('[data-k="qty"][data-l]');
  await qs[0].fill('1'); await qs[1].fill('26.8'); await qs[2].fill('1'); await sleep(200);
  ck('live: work to date 257,820.00', (await p.textContent('#calcbox')).includes('257,820.00'));
  await p.fill('[data-f="measured_on"]', '2026-09-26');
  const addDed = async (cat, date, desc, q, unit, rate, counted = true) => { await p.click('#de-add'); await sleep(150); const n = (await p.$$('[data-d][data-k="cat"]')).length - 1;
    await p.selectOption(`[data-d="${n}"][data-k="cat"]`, cat); await p.fill(`[data-d="${n}"][data-k="on_date"]`, date); await p.fill(`[data-d="${n}"][data-k="description"]`, desc);
    await p.fill(`[data-d="${n}"][data-k="qty"]`, String(q)); await p.fill(`[data-d="${n}"][data-k="unit"]`, unit); await p.fill(`[data-d="${n}"][data-k="rate"]`, String(rate));
    if (!counted) await p.uncheck(`[data-d="${n}"][data-k="counted"]`); };
  await addDed('Material', '2026-06-24', 'C 20/20 concrete', 18.5, 'm3', 358);
  await addDed('Manpower', '2026-06-17', '10 labours x 3 days with 2 hours OT', 30, 'No', 137);
  await addDed('Manpower', '2026-06-20', 'with 1 hour OT', 14, 'No', 131);
  await addDed('Plant & Equipment', '2026-06-17', 'Jack hammer', 18, 'No', 88);
  await addDed('Other', '2026-06-30', 'Dewatering charges for 7 days (not applied - management)', 7, 'Days', 7200, false);
  await sleep(300);
  const calc = await p.textContent('#calcbox');
  ck('live: deductions 14,151.00 (dewatering not taken)', calc.includes('14,151.00'), calc);
  ck('live: net 34,202.00, VAT 1,710.10, total AED 35,912.10', calc.includes('34,202.00') && calc.includes('1,710.10') && calc.includes('35,912.10'), calc);
  ck('the invoice difference is flagged (35,912.00 vs 35,912.10)', calc.includes('difference'));
  await p.screenshot({ path: SH + 'sheet.png' });
  await p.click('#sh-cert, #sh-save'); await sleep(1500);
  const srv = await api(`/store/est/subpcs/${pc.id}/sheet`);
  ck('saved & certified: the server agrees (34,202.00 / 35,912.10)', srv.pc.status === 'Certified' && Math.abs(srv.calc.this - 34202) < .01 && Math.abs(srv.calc.payable - 35912.1) < .01, srv.calc);
  await p.click('[data-sign="prep"]'); await sleep(900);
  ck('Prepared: signed with the name and date', (await p.textContent('.sgs')).includes('Administrator') || (await p.textContent('.sgs')).includes('admin'), await p.textContent('.sgs'));
  await p.screenshot({ path: SH + 'sheet_signed.png' });
  const [pop] = await Promise.all([p.waitForEvent('popup'), p.click('#sh-prev')]); await pop.waitForLoadState(); await sleep(500);
  const t = await pop.textContent('body');
  ck('preview: the certificate and appendices', t.includes('PAYMENT CERTIFICATE') && t.includes('Appendix - A') && t.includes('Appendix - C') && t.includes('35,912.10'));
  await pop.screenshot({ path: SH + 'preview.png', fullPage: false }); await pop.close();
  // schedule editor
  await p.click('#sh-items'); await sleep(800);
  ck('item schedule opens with the 3 lines', (await p.$$('#b-body tr[data-i]')).length === 3);
  await p.click('#it-addv'); await sleep(200); const rows = await p.$$('#b-body tr[data-i]'); const last = rows.at(-1);
  await (await last.$('[data-k="description"]')).fill('Extra H beam retraction'); await (await last.$('[data-k="qty"]')).fill('2'); await (await last.$('[data-k="rate"]')).fill('1500');
  ck('qty x rate fills the amount', (await (await last.$('[data-k="amount"]')).inputValue()) === '3000');
  await p.click('#it-save'); await sleep(1000);
  const it2 = await api(`/store/est/subs/${sid}/items`);
  ck('variation line saved (3,000)', Math.abs(it2.var_total - 3000) < .01, it2.var_total);
  await p.screenshot({ path: SH + 'schedule.png' });
  await p.click('#b-back'); await sleep(500);
  // phone
  const q = await (await br.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  const tok = await p.evaluate(() => sessionStorage.getItem('infinia_token'));
  await q.goto(B + '/portal/est-app.html?view=projects'); await q.evaluate(t => sessionStorage.setItem('infinia_token', t), tok);
  await q.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.inv'); }, [P]); await q.reload(); await sleep(1500);
  await q.evaluate(id => pcSheet(id), pc.id); await sleep(1200);
  ck('phone: the sheet opens, no sideways page scroll', await q.isVisible('#big') && (await q.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 1);
  await q.screenshot({ path: SH + 'phone.png' });
  ck('no page errors', errs.length === 0, errs);
  console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); await br.close(); process.exit(bad ? 1 : 0);
})();
