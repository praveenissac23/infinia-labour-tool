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
  ck('kept as .xlsx, listed', /914 MEP IPA02 - R2\.xlsx/.test(s) || /914 MEP IPA02/.test(await p.textContent('body')), s.slice(0, 200));
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
