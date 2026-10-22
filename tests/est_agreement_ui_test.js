// Read from agreement: a subcontract agreement opened in the browser (nothing uploaded), the form filled in,
// the priced schedule saved as the item schedule - for any layout: Infinia's 909 joinery PDF, a Word MEP
// subcontract, an Excel LPO and a plain PDF work order.
//   AGREEMENT_FILE=<909 agreement.pdf> node tests/est_agreement_ui_test.js
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/agrui_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const DIR = '/tmp/claude-0/agrfix';
(async () => {
  const exp = JSON.parse(execSync(`python3 ${__dirname}/est_agreement_fixtures.py ${DIR}`).toString());
  const files = [];
  if (process.env.AGREEMENT_FILE) files.push({ path: process.env.AGREEMENT_FILE, code: '909', e: { name: 'Woodcraft Interiors (SPS LLC)', agreement: 'IC/909/SCA/01/26', date: '2026-10-22', value: 534000, type: 'Lump sum contract', adv: 50, ret: 10, items: 26, bills: { A: 453802.81, B: 31197.19, C: 49000 }, scope: 'Joinery' } });
  files.push({ path: `${DIR}/912 MEP subcontract.docx`, code: '912', e: exp.docx });
  files.push({ path: `${DIR}/913 shoring LPO.xlsx`, code: '913', e: exp.xlsx });
  files.push({ path: `${DIR}/915 painting work order.pdf`, code: '915', e: exp.pdf2 });
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  const uploads = []; p.on('request', r => { if (r.method() === 'POST' && (r.postDataBuffer() || Buffer.alloc(0)).includes(Buffer.from('%PDF'))) uploads.push(r.url()); if (/multipart/.test(r.headers()['content-type'] || '')) uploads.push(r.url()); });
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async path => p.evaluate(async path => (await fetch(path, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), path);
  const meta = await api('/store/est/meta');
  for (const F of files) {
    const P = meta.projects.find(x => x.code === F.code).id, e = F.e, tag = F.path.split('/').pop();
    await p.evaluate(pid => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.reg'); }, P); await p.goto(B + '/portal/est-app.html?view=projects'); await sleep(1500);
    await p.click('#add-sub'); await sleep(400);
    ck(`${tag}: the form has "Read from agreement"`, await p.isVisible('#ag-pick'));
    await p.setInputFiles('#ag-file', F.path); await p.waitForSelector('.agres, .agnote.bad', { timeout: 30000 }); await sleep(300);
    const v = async k => p.inputValue('#f-' + k);
    const bad0 = await p.$('.agnote.bad'); if (bad0) { ck(`${tag}: read`, false, await bad0.textContent()); continue; }
    ck(`${tag}: subcontractor "${e.name}"`, (await v('name')) === e.name, await v('name'));
    if (e.agreement) ck(`${tag}: agreement no. ${e.agreement}`, (await v('agreement')) === e.agreement, await v('agreement'));
    if (e.lpo) ck(`${tag}: LPO no. ${e.lpo}`, (await v('lpo')) === e.lpo && (await v('kind')) === 'LPO', [await v('lpo'), await v('kind')]);
    ck(`${tag}: agreement date ${e.date}`, (await v('agreement_date')) === e.date, await v('agreement_date'));
    ck(`${tag}: value ${e.value}`, Math.abs(Number(String(await v('value')).replace(/,/g, '')) - e.value) < .005, await v('value'));
    if (e.type) ck(`${tag}: contract type`, (await v('contract_type')) === e.type, await v('contract_type'));
    if (e.adv !== undefined) ck(`${tag}: advance ${e.adv}%`, Number(await v('adv_pct')) === e.adv, await v('adv_pct'));
    if (e.ret !== undefined) ck(`${tag}: retention ${e.ret}%`, Number(await v('ret_pct')) === e.ret, await v('ret_pct'));
    if (e.scope) ck(`${tag}: work "${e.scope}"`, (await v('scope')) === e.scope, await v('scope'));
    const res = await p.textContent('.agres');
    ck(`${tag}: ${e.items} priced lines, total = contract value`, res.includes(`Save the ${e.items} priced line`) && res.includes('= contract value'), res.slice(0, 300));
    if (F.code === '909') { await p.click('.agsched summary'); await sleep(200); await p.screenshot({ path: SH + '909_form.png' }); }
    await p.click('#m-save'); await sleep(2000);
    const b = await api(`/store/est/projects/${P}`);
    const sub = b.subs.filter(x => x.name === e.name).pop();
    ck(`${tag}: saved on the register`, !!sub && Math.abs(sub.value - e.value) < .005, sub && sub.value);
    if (!sub) continue;
    const its = await api(`/store/est/subs/${sub.id}/items`);
    ck(`${tag}: item schedule saved - ${e.items} lines, ${e.value.toLocaleString()}`, its.items.length === e.items && Math.abs(its.total - e.value) < .005, [its.items.length, its.total]);
    if (e.bills) for (const [bl, amt] of Object.entries(e.bills))
      ck(`${tag}: section ${bl} = ${amt}`, Math.abs(its.items.filter(x => x.bill === bl).reduce((a, x) => a + x.amount, 0) - amt) < .005);
    if (F.code === '909') { await p.screenshot({ path: SH + '909_saved.png' }); }
    if (F.code === '912') ck(`${tag}: re-measurable -> lines measured by quantity`, its.items.every(x => x.measure === 'qty'), its.items.map(x => x.measure));
  }
  // not a file it can read
  await p.click('#add-sub').catch(() => {}); await sleep(300);
  require('fs').writeFileSync(`${DIR}/note.txt`, 'hello');
  await p.setInputFiles('#ag-file', `${DIR}/note.txt`); await sleep(800);
  ck('a file it cannot read says so', /PDF, Word/.test(await p.textContent('#ag-out')), await p.textContent('#ag-out'));
  ck('the file itself was never sent to the server', uploads.length === 0, uploads);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
