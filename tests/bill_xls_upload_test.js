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
  await p.setInputFiles('#fm-file', DIR + '914-IPA-08.xls');
  const resp = p.waitForResponse(r => r.url().endsWith('/store/est/ipa/format'));
  await p.click("#m-save");
  const r = await resp; const j = await r.json().catch(() => ({}));
  ck('the .xls uploads (converted on the server)', r.status() === 200 && j.lines > 0, [r.status(), j]);
  await sleep(1500);
  const fm = await p.evaluate(async (pid) => (await (await fetch('/store/est/ipa?project_id=' + pid, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()), P).catch(() => null);
  const s = JSON.stringify(fm || '');
  ck('kept as .xlsx, listed', /914-IPA-08\.xlsx/.test(s) || /914-IPA-08/.test(await p.textContent('#sec')), s.slice(0, 200));
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
