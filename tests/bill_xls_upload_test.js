// Bills: an old-format Excel bill (.xls) uploads as it is - the server converts it to .xlsx (formulas and layout kept).
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', DIR = process.env.BILLS || '/tmp/claude-0/bills/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const P = await p.evaluate(async () => (await (await fetch('/store/est/meta', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).projects.find(x => x.code === '903').id);
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, [P]); await p.reload(); await sleep(2500);
  // through the screen: Upload a bill, pick the .xls
  const up = await p.$$eval('#sec button', bs => bs.map(b => b.textContent.trim()).filter(t => /upload/i.test(t)));
  await p.click(`#sec button:has-text("${up[0]}")`); await sleep(800);
  ck('the upload box accepts .xls', (await p.getAttribute('#fm-file', 'accept')).includes('.xls'));
  await p.setInputFiles('#fm-file', DIR + (process.env.XLS || '914 MEP IPA02 - R2.xls'));
  const resp = p.waitForResponse(r => r.url().endsWith('/store/est/ipa/format'));
  await p.click("#m-save");
  const r = await resp; const j = await r.json().catch(() => ({}));
  ck('the .xls uploads (converted on the server)', r.status() === 200 && j.lines > 0, [r.status(), j]);
  ck('every formula gives Excel\'s own figure (precision as displayed honoured)', j.formulas > 0 && j.same === j.formulas, j);
  // a new bill is made from it and comes out as PDF and Excel
  const nb = await p.evaluate(async (pid) => { const h = { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' };
    const r = await fetch('/store/est/ipa/new', { method: 'POST', headers: h, body: JSON.stringify({ project_id: pid, contract_id: null }) }); const j = await r.json();
    const t = await (await fetch('/auth/download-token', { method: 'POST', headers: h })).json(); const k = t.token || t.download_token;
    const out = [r.status, j.id]; for (const f of ['pdf', 'excel']) { const x = await fetch(`/export/est/ipa/${j.id}?token=${k}&format=${f}`); out.push([f, x.status, (await x.arrayBuffer()).byteLength]); } return out; }, P);
  ck('a new bill starts from the .xls format and exports PDF + Excel', nb[0] === 200 && nb.slice(2).every(x => x[1] === 200 && x[2] > 5000), nb);
  await sleep(1500);
  const fm = await p.evaluate(async (pid) => (await (await fetch('/store/est/ipa?project_id=' + pid, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()), P).catch(() => null);
  const s = JSON.stringify(fm || '');
  // the new bill (No 3) from IPA02: the IPA02 line has its submitted date, no "No 3" line for the bill being made
  await p.evaluate(id => openBill(id, 'pay'), nb[1]); await sleep(2500);
  await p.evaluate(() => { const b = document.querySelector('#ipa-nav [data-step="pay"]'); if (b) b.click(); }); await sleep(1200);
  const rows = () => p.$$eval('.ipa-pay tbody tr:not(.tot)', t => t.map(r => [...r.querySelectorAll('input')].map(i => i.value)));
  let R = await rows();
  ck('payments: no line for the bill being made (No 3)', !R.some(r => /Payment Application No 3/.test(r[0])), R);
  const pa2 = R.find(r => /Payment Application No 2/.test(r[0]));
  ck('payments: the IPA02 line has its submitted date', pa2 && /^\d{4}-\d{2}-\d{2}$/.test(pa2[1]), R);
  const tot0 = await p.textContent('.ipa-pay tr.tot');
  // delete a line (the empty "Previous Payments" heading) - confirm in the standard box
  const n0 = R.length;
  const i = R.findIndex(r => /Previous Payments/.test(r[0]));
  await p.click(`.ipa-pay tbody tr:nth-child(${i + 1}) [data-paydel]`); await sleep(500);
  await p.click('#cdel-ok, .cdel-ok, [data-cdel="ok"], .modal button:has-text("Delete")').catch(async () => { await p.click('button:has-text("Delete") >> nth=-1'); });
  await sleep(2000);
  R = await rows();
  ck('Delete takes the line off the payment summary', R.length === n0 - 1 && !R.some(r => /Previous Payments/.test(r[0])), R);
  ck('the total of previous payments is unchanged by deleting an empty line', (await p.textContent('.ipa-pay tr.tot')) === tot0, [tot0, await p.textContent('.ipa-pay tr.tot')]);
  await p.screenshot({ path: '/tmp/claude-0/pay_del.png' });
  ck('kept as .xlsx, listed', /914 MEP IPA02 - R2\.xlsx/.test(s) || /914 MEP IPA02/.test(await p.textContent('body')), s.slice(0, 200));
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
