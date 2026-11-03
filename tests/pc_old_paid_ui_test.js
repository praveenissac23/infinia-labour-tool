// 'Old PC - already paid' on screen: shown on older unpaid certificates only (never the newest), opens with the payable
// filled in, and after it the certificate is Paid and gone from the approvals.   BASE=... node tests/pc_old_paid_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await sleep(2500); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000);
  const api = (u, b) => p.evaluate(([u, b]) => apiCall(u, b ? { method: 'POST', body: JSON.stringify(b) } : undefined), [u, b]);
  const pid = (await api('/store/est/meta')).projects.find(x => x.code === '912').id;
  const sid = (await api('/store/est/subs', { project_id: pid, name: 'UI Old Paid Joinery', value: 100000, vat_pct: 5 })).id;
  const ids = [];
  for (const [n, w] of [[1, 10000], [2, 25000], [3, 40000]]) {
    const r = await api('/store/est/subpcs', { sub_id: sid, inv_ref: 'UOP/' + n, inv_amount: 1000, inv_date: `2026-0${n + 6}-10`, received: `2026-0${n + 6}-10` });
    await p.evaluate(([i, w]) => apiCall(`/store/est/subpcs/${i}`, { method: 'PATCH', body: JSON.stringify({ work_cum: w }) }), [r.id, w]); ids.push(r.id);
  }
  await p.evaluate(() => { window.checkBuild = () => {}; pgGo('estimation', 'estproj'); }); await sleep(4000);
  const f = p.frameLocator('iframe:visible'); const fr = p.frames().find(x => /est-app/.test(x.url()));
  await fr.evaluate(pid => { location.hash = `#p=${pid}&t=subs.inv`; }, pid).catch(() => {}); await sleep(500);
  await fr.evaluate(async pid => { if (typeof openProject === 'function') await openProject(pid); }, pid).catch(() => {});
  await fr.evaluate(() => { const b = [...document.querySelectorAll('.utabs button, .pills button')].find(x => /Subcontractors/.test(x.textContent)); if (b) b.click(); }); await sleep(1200);
  await fr.evaluate(() => { const b = [...document.querySelectorAll('.utabs button')].find(x => /Invoice tracker/.test(x.textContent)); if (b) b.click(); }); await sleep(1500);
  const btns = await fr.evaluate(ids => ids.map(i => !!document.querySelector(`[data-oldpaid="${i}"]`)), ids);
  ck(`Invoice tracker: the button on PC 01 and PC 02, not on the newest PC 03 (${btns})`, btns[0] && btns[1] && !btns[2], btns);
  await fr.evaluate(i => document.querySelector(`[data-oldpaid="${i}"]`).click(), ids[1]); await sleep(700);
  const form = await fr.evaluate(() => ({ title: document.getElementById('m-title').textContent, amt: (document.getElementById('f-amount') || {}).value, date: (document.getElementById('f-date') || {}).value, save: document.getElementById('m-save').textContent, top: document.getElementById('m-body').textContent }));
  ck(`the form: PC 02, the payable filled in (${form.amt}), the invoice date, says it does not go to Accounts or the MD`, /PC 02/.test(form.title) && /15,?750/.test(form.amt) && form.date === '2026-08-10' && /not\s+sent to the Contracts manager, Accounts or the MD/.test(form.top), form);
  await p.screenshot({ path: '/tmp/claude-0/ui2/oldpaid_form.png' });
  await fr.evaluate(() => document.getElementById('m-save').click()); await sleep(2500);
  const st = await api(`/store/est/projects/${pid}`).catch(() => null);
  const pcs = st ? st.subs.find(x => x.id === sid).pcs : [];
  const two = pcs.find(x => x.id === ids[1]) || {};
  ck(`PC 02 is Paid, ${two.paid_amount}`, two.status === 'Paid' && Math.abs(two.paid_amount - 15750) < 0.01, two);
  ck('its button is gone', await fr.evaluate(i => !document.querySelector(`[data-oldpaid="${i}"]`), ids[1]));
  await p.screenshot({ path: '/tmp/claude-0/ui2/oldpaid_after.png' });
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await br.close(); process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
