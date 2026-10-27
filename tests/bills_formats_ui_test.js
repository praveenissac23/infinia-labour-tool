// Bills: the uploaded workbook with the highest bill no. is the bill format (not the last uploaded); the others are
// previous bills - listed, clickable, read sheet by sheet. + New bill is made from the format without asking.
// A draft bill can be deleted from the list; every delete asks in one standard box (Cancel / Delete).
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/bfm_', DIR = process.env.BILLS || '/tmp/claude-0/bills/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const P = await p.evaluate(async () => (await (await fetch('/store/est/meta', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).projects.find(x => x.code === '903').id);
  for (const f of ['914-IPA-01.xlsx', '914-IPA-03.xlsx', '914-IPA-07.xlsx', '914-IPA-02.xlsx']) {      // IPA-02 uploaded last, as Anoop did
    const b64 = fs.readFileSync(DIR + f).toString('base64');
    const r = await p.evaluate(async ([pid, f, b64]) => { const fd = new FormData(); fd.append('project_id', pid); fd.append('name', f);
      fd.append('file', new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))]), f);
      const r = await fetch('/store/est/ipa/format', { method: 'POST', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') }, body: fd }); return r.status; }, [P, f, b64]);
    if (r !== 200) console.log('upload', f, r);
  }
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, [P]); await p.reload(); await sleep(2500);
  const fmtCard = await p.textContent('#sec');
  ck('Bill format = bill 7 (the highest), not IPA-02 uploaded last', /Bill format[\s\S]*914-IPA-07\.xlsx[\s\S]*Previous bills/.test(fmtCard), fmtCard.slice(0, 400));
  const prevRows = await p.$$eval('#sec .card:last-child tbody tr td:first-child', t => t.map(x => x.textContent.trim()));
  ck('Previous bills: 1, 2, 3 in order', prevRows.join() === '1,2,3', prevRows);
  await p.screenshot({ path: SH + '1_formats.png', fullPage: true });
  // a previous bill opens to read
  await p.click('#sec .card:last-child tbody tr:nth-child(2)'); await sleep(1500);
  ck('previous bill 2 opens, read only, sheet by sheet', await p.isVisible('#big:not(.hide)') && (await p.textContent('#b-title')).includes('Bill 2') && !!(await p.$('.sv-pick')) && !(await p.$('#b-body td.ed')));
  await p.selectOption('.sv-pick', { label: 'Works' }); await sleep(1200);
  ck('its Works sheet shows the lines', (await p.textContent('#b-body')).includes('Superstructure'));
  await p.screenshot({ path: SH + '2_view.png' });
  await p.click('#b-back'); await sleep(500);
  // new bill from the format, no question
  await p.click('#ipa-new'); await sleep(2500);
  ck('+ New bill opens straight away as bill 8 (from bill 7)', await p.isVisible('#big:not(.hide)') && (await p.textContent('#b-title')).includes('Interim Bill 8'), await p.textContent('#b-title').catch(() => ''));
  await p.click('#b-back'); await sleep(1500);
  // delete the draft from the list: the standard box
  await p.click('#sec [data-ipadel]'); await sleep(400);
  ck('Delete asks in the standard box', await p.isVisible('#cfm:not(.hide)') && (await p.textContent('#cfm')).includes('Delete bill 8?'));
  await p.screenshot({ path: SH + '3_confirm.png' });
  await p.click('#cfm-no'); await sleep(300);
  ck('Cancel keeps it', (await p.$$('#sec [data-ipadel]')).length === 1);
  await p.click('#sec [data-ipadel]'); await sleep(300); await p.click('#cfm-ok'); await sleep(1500);
  ck('Delete removes the draft bill', (await p.$$('#sec [data-ipadel]')).length === 0);
  // deleting a previous bill workbook asks too
  const before = (await p.$$('#sec [data-fmdel]')).length;
  await p.click('#sec .card:last-child [data-fmdel]'); await sleep(300);
  ck('deleting a previous bill asks', (await p.textContent('#cfm')).includes('Delete previous bill'));
  await p.click('#cfm-ok'); await sleep(1500);
  ck('...and it is gone', (await p.$$('#sec [data-fmdel]')).length === before - 1);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
