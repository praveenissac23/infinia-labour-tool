// A bill workbook with a formula the app does not work out the same as Excel: the upload stops, shows the cell with
// Excel's figure and this one, and keeps nothing unless "Upload anyway" is pressed.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', DIR = process.env.BILLS || '/tmp/claude-0/bills/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const P = await p.evaluate(async () => (await (await fetch('/store/est/meta', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).projects.find(x => x.code === '903').id);
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, [P]); await p.reload(); await sleep(2500);
  const count = () => p.evaluate(async pid => (await (await fetch('/store/est/ipa/list?project_id=' + pid, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).formats.length, P);
  const n0 = await count();
  const open = async () => { const up = await p.$$eval('#sec button', bs => bs.map(b => b.textContent.trim()).filter(t => /upload/i.test(t)));
    await p.click(`#sec button:has-text("${up[0]}")`); await sleep(600); await p.setInputFiles('#fm-file', DIR + '914-IPA-09 mismatch.xlsx'); await p.click('#m-save'); await sleep(3000); };
  await open();
  const box = await p.evaluate(() => { const c = document.getElementById('cfm'); return c && !c.classList.contains('hide') ? c.textContent : null; });
  ck('upload stops and shows the formula that does not match (cell, Excel 22, here #NAME?)', box && /do(es)? not match Excel/.test(box) && /Z1/.test(box) && /22/.test(box) && /#NAME\?/.test(box), box);
  await p.screenshot({ path: '/tmp/claude-0/mismatch.png' });
  await p.click('#cfm-no'); await sleep(800);
  ck('Cancel: nothing kept', (await count()) === n0, [n0, await count()]);
  await p.keyboard.press('Escape'); await sleep(400);
  await open(); await p.click('#cfm-ok'); await sleep(3000);
  ck('Upload anyway: kept', (await count()) === n0 + 1, [n0, await count()]);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
