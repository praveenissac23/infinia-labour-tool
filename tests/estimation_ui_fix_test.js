// Estimation: the items from the full check - jumps into Projects from the dashboard and a won tender
// (before the Projects tab was ever opened), figure cards, Accounts > Subcontractor payments, phone width.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0; const fails = [];
const ck = (n, ok, info) => { if (!ok) { bad++; fails.push(n); } console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(2500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + (sessionStorage.getItem('infinia_token') || localStorage.getItem('infinia_keep')), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta');
  const P = meta.projects.find(x => x.code === '912').id;
  const sb = (await api('/store/est/subs', { method: 'POST', body: { project_id: P, name: 'FIX SUB LLC', scope: 'Tiling', value: 100000, ret_pct: 10 } })).id;
  const pc = (await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sb, inv_ref: 'F-1', work_cum: 40000 } })).id;
  for (const s of ['At site', 'Back from site', 'Certified', 'PC issued', 'With Accounts']) await api(`/store/est/subpcs/${pc}/step`, { method: 'POST', body: { step: s } });
  // ---- dashboard figure card -> the project that has the invoices
  await p.goto(B + '/?p=estimation#estdash'); await sleep(3000);
  const fr = n => p.frames().find(f => f.url().includes(n));
  let d = fr('view=dash'); await d.waitForSelector('.strip');
  await d.click('[data-go="subs.pcs"]'); await sleep(3000);
  let pf = fr('view=projects');
  ck('"Waiting payment" opens project 912 (first time Projects is opened)', pf && await pf.evaluate(() => typeof ST !== 'undefined' && ST.b && ST.b.project.code) === '912');
  ck('...at Payment certificates', pf && await pf.evaluate(() => ST.group + '.' + ST.sec) === 'subs.pcs');
  // ---- won tender -> its new project
  await p.evaluate(() => pgTab('esttend')); await sleep(2000);
  const tf = fr('view=tenders');
  const tid = (await api('/store/est/tenders', { method: 'POST', body: { name: 'Fix villa', client: 'Mr Fix', value: 1500000, status: 'Submitted' } })).id;
  await tf.evaluate(() => loadTenders()); await sleep(600);
  await tf.click(`[data-won="${tid}"]`); await sleep(300); await tf.fill('#f-code', '991'); await tf.click('#m-save'); await sleep(3500);
  pf = fr('view=projects');
  ck('won tender jumps to the new project 991', await pf.evaluate(() => ST.b && ST.b.project.code) === '991');
  ck('...and it is in the picker list', await pf.evaluate(() => ST.meta.projects.some(x => x.code === '991')));
  // ---- Accounts > Subcontractor payments with an Accounts-only login
  const r = await api('/users', { method: 'POST', body: { username: 'fx_acc', password: 'pass12345', role: 'office' } });
  if (r.id) await api(`/users/${r.id}/permissions`, { method: 'POST', body: { permissions: 'settings,accounts_bank' } });
  const ctx2 = await br.newContext({ viewport: { width: 1440, height: 900 } }); const a = await ctx2.newPage(); a.on('pageerror', e => errs.push('acc: ' + e.message));
  await a.goto(B + '/'); await a.fill('#login-username', 'fx_acc'); await a.fill('#login-password', 'pass12345'); await a.evaluate('doLogin()'); await sleep(2500);
  await a.goto(B + '/?p=accounts#subpay'); await sleep(3000);
  const af = a.frames().find(f => f.url().includes('view=pay'));
  ck('Accounts login sees Subcontractor payments', !!af && (await af.textContent('#app')).includes('FIX SUB LLC'));
  await af.click(`[data-ppay="${pc}"]`); await sleep(300);
  ck('Mark paid prefilled with the payable (incl. VAT)', (await af.inputValue('#f-amount')) === '37800');
  await af.fill('#f-ref', 'CHQ 77'); await af.click('#m-save'); await sleep(1200);
  const sbp = (await api(`/store/est/projects/${P}`)).subs.find(x => x.id === sb).pcs[0];
  ck('paid by Accounts shows on the QS side', sbp.status === 'Paid' && sbp.paid_amount === 37800 && sbp.paid_ref === 'CHQ 77', sbp);
  // ---- phone: dashboard never scrolls sideways
  const ph = await br.newContext({ viewport: { width: 390, height: 844 }, isMobile: true }); const q = await ph.newPage();
  const tok = await p.evaluate(() => sessionStorage.getItem('infinia_token'));
  await q.goto(B + '/portal/est-app.html?view=dash'); await q.evaluate(t => sessionStorage.setItem('infinia_token', t), tok); await q.reload(); await q.waitForSelector('.strip'); await sleep(500);
  ck('phone dashboard: no sideways scroll', await q.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 1);
  ck('no page errors', errs.length === 0, errs);
  console.log(bad ? `\n${bad} FAILED: ${fails.join(' | ')}` : '\nALL PASS');
  await br.close(); process.exit(bad ? 1 : 0);
})();
