// Subcontracts: a re-measurable one (value 0) shows the work measured on its certificates as its revised value;
// the subcontract opens as a full page with Back (and the browser Back closes it); the subcontractor list shows the
// name only; the item schedule has a Claimed qty column, visible placeholders and fits the screen.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/remeas_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(2000);
  const api = (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === '914').id;
  const sid = (await api('/store/est/subs', { method: 'POST', body: { project_id: P, name: 'M/s. ROYAL EVERST TECHNICAL SERVICES', scope: 'Manpower For Steel & Shuttering Works', value: 0, ret_pct: 10, vat_pct: 5, contract_type: 'Re-measurable based on actual quantities executed' } })).id;
  await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sid, inv_ref: 'IPC 2', work_cum: 20642.40 } });
  await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sid, inv_ref: 'IPC 3', work_cum: 28397.40 } });
  const s = (await api(`/store/est/projects/${P}`)).subs.find(x => x.id === sid);
  ck('re-measurable: revised = work measured on the certificates (28,397.40), balance 0', s.revised === 28397.4 && s.balance === 0 && s.remeasure, [s.revised, s.balance]);
  await p.evaluate(pid => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.reg'); }, String(P));
  await p.reload(); await p.waitForSelector(`[data-sub="${sid}"]`, { timeout: 20000 }).catch(() => {}); await sleep(500);
  const row = (await p.textContent(`tr[data-sub="${sid}"]`)).replace(/\s+/g, ' ');
  ck('register: REVISED shows 28,397.40 and Done says re-measured', /28,397\.40/.test(row) && /re-measured/.test(row), row);
  await p.screenshot({ path: SH + '1_register.png' });
  await p.click(`tr[data-sub="${sid}"]`); await sleep(800);
  const box = await p.evaluate(() => { const b = document.querySelector('#drawer .dbox').getBoundingClientRect(); return { w: b.width, vw: innerWidth }; });
  ck('the subcontract opens as a full page (not a half window)', box.w >= box.vw - 2, box);
  ck('with a Back button at the top', await p.isVisible('#d-back'));
  const figs = (await p.textContent('#d-body .strip')).replace(/\s+/g, ' ');
  ck('figures: Value "Re-measurable", Revised 28,397.40, Balance work 0', /Re-measurable/.test(figs) && /Revised\s*28,397\.40/.test(figs) && /Balance work\s*0\.00/.test(figs), figs);
  await p.screenshot({ path: SH + '2_full_page.png' });
  await p.goBack(); await sleep(600);
  ck('the browser Back button closes it and shows the list again', !(await p.isVisible('#drawer')) && await p.isVisible(`tr[data-sub="${sid}"]`));
  await p.click(`tr[data-sub="${sid}"]`); await sleep(600); await p.click('#d-back'); await sleep(500);
  ck('Back returns to the list', !(await p.isVisible('#drawer')));
  // the subcontractor list: name only
  await p.click(`tr[data-sub="${sid}"]`); await sleep(600); await p.click('#s-inv'); await sleep(400);
  const opts = await p.$$eval('#f-sub_id option', o => o.map(x => x.textContent));
  ck('Invoice received: the subcontractor list shows the name only', opts.includes('M/s. ROYAL EVERST TECHNICAL SERVICES') && !opts.some(t => /Shuttering/.test(t)), opts);
  await p.click('#m-cancel'); await sleep(300);
  // item schedule: claimed qty
  await p.evaluate(id => scheduleEditor(id), sid); await sleep(800);
  await p.click('#it-add'); await sleep(300);
  const heads = await p.$$eval('#b-body table.sched th', t => t.map(x => x.textContent.trim()));
  ck('item schedule: a Claimed qty column beside Qty', heads.join('|').includes('Qty|Claimed qty|Unit'), heads);
  const ph = await p.$$eval('#b-body tr[data-i] input[placeholder]', x => x.map(i => i.placeholder));
  ck('placeholders on every box', ph.includes('B1') && ph.includes('0.00') && ph.includes('m3') && ph.includes('V01 / LPO'), ph);
  const phColor = await p.evaluate(() => getComputedStyle(document.querySelector('#b-body tr[data-i] input[data-k="qty"]'), '::placeholder').color);
  ck('placeholders visible (grey, not blank)', phColor && phColor !== 'rgba(0, 0, 0, 0)', phColor);
  await p.fill('#b-body tr[data-i] textarea[data-k="description"]', 'Footing works'); await p.fill('#b-body tr[data-i] input[data-k="qty"]', '105.4');
  await p.fill('#b-body tr[data-i] input[data-k="claimed_qty"]', '98.2'); await p.fill('#b-body tr[data-i] input[data-k="unit"]', 'm3'); await p.fill('#b-body tr[data-i] input[data-k="rate"]', '235');
  const fit = await p.evaluate(() => { const t = document.querySelector('#b-body table.sched'); return { tw: t.scrollWidth, vw: innerWidth }; });
  ck('the schedule fits a normal screen (no sideways scrolling at 1440 px)', fit.tw <= fit.vw, fit);
  await p.screenshot({ path: SH + '3_schedule.png' });
  await p.click('#it-save'); await sleep(1000);
  const it = await api(`/store/est/subs/${sid}/items`);
  ck('claimed qty saved (98.2), qty 105.4, amount 24,769.00', it.items[0].claimed_qty === 98.2 && it.items[0].qty === 105.4 && Math.abs(it.items[0].amount - 24769) < .01, it.items[0]);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
