// Accounts > Subcontractor payments and Estimation are one record: paid in Accounts shows paid in
// Estimation (invoice tracker, subcontract register, payment figures), and undone either side, both follow.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/subpay_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta'); const P = meta.projects.find(x => x.code === '922');
  let b0 = await api(`/store/est/projects/${P.id}`);
  const allPcs = b0 => b0.subs.flatMap(s => s.pcs);
  if (!allPcs(b0).some(x => x.status === 'With Accounts')) {      // a certificate waiting with Accounts (no test data on the app since go-live)
    const sid = (await api('/store/est/subs', { method: 'POST', body: { project_id: P.id, name: 'Subpay Link Test Contracting', scope: 'Tiling', value: 100000, ret_pct: 10, vat_pct: 5, status: 'Active' } })).id;
    const pid = (await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sid, inv_ref: 'SLT-1', inv_amount: 21000, work_cum: 20000, adv_auto: false, ret_auto: false, ret_cum: 2000 } })).id;
    const d = new Date().toISOString().slice(0, 10);
    await api(`/store/est/subpcs/${pid}`, { method: 'PATCH', body: { certified_on: d, issued: d } });
    for (const step of ['Certified', 'PC issued', 'With Accounts']) await api(`/store/est/subpcs/${pid}/step`, { method: 'POST', body: { step } });
    b0 = await api(`/store/est/projects/${P.id}`);
  }
  const subs = b0.subs, pc = allPcs(b0).find(x => x.status === 'With Accounts');
  ck('a certificate is waiting with Accounts on 922', !!pc);
  const sub = subs.find(s => s.id === pc.sub_id);
  const paidBefore = (b0.subs.find(s => s.id === sub.id) || {}).paid || 0;
  // ---- Accounts marks it paid ----
  await p.goto(B + '/?p=accounts#subpay'); await sleep(3500);
  const fr = p.frameLocator('#pg-subpay-frame');
  await fr.locator(`[data-ppay="${pc.id}"]`).click(); await sleep(500);
  const amt = await fr.locator('#f-amount').inputValue();
  await fr.locator('#f-ref').fill('ADCB TT 4471'); await fr.locator('#m-save').click(); await sleep(1500);
  await p.screenshot({ path: SH + '1_accounts.png' });
  const b1 = await api(`/store/est/projects/${P.id}`), pc1 = allPcs(b1).find(x => x.id === pc.id);
  ck(`Estimation record is Paid, ${amt} on today's date, ref kept`, pc1.status === 'Paid' && Math.abs(pc1.paid_amount - +amt) < .005 && pc1.paid_ref === 'ADCB TT 4471' && !!pc1.paid_on, pc1);
  const s1 = b1.subs.find(s => s.id === sub.id);
  ck('the subcontract\'s paid to date went up by the same amount', Math.abs((s1.paid || 0) - paidBefore - +amt) < .005, [paidBefore, s1.paid, amt]);
  // ---- Estimation shows it ----
  await p.goto(B + '/?p=estimation#estproj'); await sleep(3500);
  const ef = p.frameLocator('#pg-estproj-frame');
  await ef.locator('body').evaluate((_, pid) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.inv'); location.reload(); }, P.id).catch(() => {});
  await sleep(4000);
  const row = ef.locator('table tbody tr', { hasText: sub.name }).filter({ hasText: 'PC ' + String(pc.seq).padStart(2, '0') }).first();
  const txt = await row.textContent();
  ck('Estimation > invoice tracker shows it Paid', /Paid/.test(txt) && !/Mark paid/.test(txt), txt.slice(0, 200));
  await p.screenshot({ path: SH + '2_estimation.png' });
  // ---- undone in Estimation, Accounts follows ----
  await api(`/store/est/subpcs/${pc.id}/step`, { method: 'POST', body: { step: 'Paid', undo: true } });
  await p.goto(B + '/?p=accounts#subpay'); await sleep(3500);
  ck('undone in Estimation: Accounts shows Mark paid again', await p.frameLocator('#pg-subpay-frame').locator(`[data-ppay="${pc.id}"]`).count() === 1);
  const b2 = await api(`/store/est/projects/${P.id}`);
  ck('and the paid to date is back as it was', Math.abs((b2.subs.find(s => s.id === sub.id).paid || 0) - paidBefore) < .005);
  ck('no page errors', !errs.length, errs);
  await br.close();
  console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
