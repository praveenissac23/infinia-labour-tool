// Certificate preview: "Hide columns" puts a tick box in every column heading; unticking one leaves that column off
// the screen, the PDF and Share; Done puts the boxes away; the choice is saved on the certificate.
//   BASE=... PC_PROJECT=912 node tests/pc_hide_cols_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', O = process.env.SHOTS || '/tmp/claude-0/ui2/';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => {
  const br = await chromium.launch();
  for (const vw of [{ width: 1440, height: 900, n: 'desk' }, { width: 390, height: 844, n: 'phone' }]) {
    const p = await (await br.newContext({ viewport: { width: vw.width, height: vw.height }, deviceScaleFactor: vw.n === 'phone' ? 2 : 1 })).newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/'); await sleep(2500); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3500);
    const info = await p.evaluate(async code => { const m = await apiCall('/store/est/meta'); const pid = m.projects.find(x => x.code === code).id;
      const b = await apiCall('/store/est/projects/' + pid); const s = b.subs.find(x => x.pcs.length > 1) || b.subs[0]; const pc = s.pcs[s.pcs.length - 1];
      const t = await apiCall('/auth/download-token', { method: 'POST' }); return { id: pc.id, tok: t.token }; }, process.env.PC_PROJECT || '912');
    // start from the default
    await p.evaluate(async i => fetch(`/export/est/pc/${i.id}/cols?token=${i.tok}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hide: { A: [3, 5] } }) }), info);
    const url = `${B}/export/est/pc/${info.id}?token=${info.tok}&format=preview`;
    await p.goto(url); await sleep(1500);
    const vis = () => p.evaluate(() => { const t = document.querySelector('table.t[data-k=A]'); return [...t.querySelector('tr').children].filter(th => getComputedStyle(th).display !== 'none').map(th => th.textContent.replace(/✓/g, '').trim()); });
    let cols = await vis();
    ck(`${vw.n}: Int. Qty and Contract amt hidden, no tick boxes showing (${cols.slice(2, 6)})`, !cols.includes('Int. Qty') && !cols.includes('Contract amt') && cols.includes('Rate') && await p.evaluate(() => !document.querySelector('.t th .tk') || getComputedStyle(document.querySelector('.t th .tk')).display === 'none'), cols);
    ck(`${vw.n}: button says "Hide columns (2 hidden)"`, (await p.textContent('#colbtn')) === 'Hide columns (2 hidden)');
    await p.click('#colbtn'); await sleep(300);
    const ed = await p.evaluate(() => ({ btn: document.getElementById('colbtn').textContent, boxes: [...document.querySelectorAll('.t th .tk')].filter(x => getComputedStyle(x).display !== 'none').length, note: getComputedStyle(document.querySelector('.cnote')).display }));
    ck(`${vw.n}: pressed - a tick box in every heading, the note, button "Done"`, ed.btn === 'Done' && ed.boxes > 20 && ed.note === 'block', ed);
    cols = await vis();
    ck(`${vw.n}: while choosing, the hidden columns show greyed`, cols.includes('Int. Qty') && cols.includes('Contract amt'), cols);
    await p.evaluate(() => document.querySelector('table.t[data-k=A]').scrollIntoView({ block: 'start' })); await p.evaluate(() => scrollBy(0, -110)); await sleep(200);
    await p.screenshot({ path: O + `hidecols_${vw.n}_1_choosing.png` });
    // untick Remarks (14), tick Int. Qty (3) back
    await p.evaluate(() => { const hr = document.querySelector('table.t[data-k=A] tr'); hr.children[14].click(); hr.children[3].click(); }); await sleep(900);
    await p.click('#colbtn'); await sleep(400);
    cols = await vis();
    ck(`${vw.n}: Done - Remarks gone, Int. Qty back, Contract amt still off`, !cols.includes('Remarks') && cols.includes('Int. Qty') && !cols.includes('Contract amt'), cols);
    ck(`${vw.n}: button "Hide columns (2 hidden)"`, (await p.textContent('#colbtn')) === 'Hide columns (2 hidden)', await p.textContent('#colbtn'));
    await p.evaluate(() => document.querySelector('table.t[data-k=A]').scrollIntoView({ block: 'start' })); await p.evaluate(() => scrollBy(0, -110)); await sleep(200);
    await p.screenshot({ path: O + `hidecols_${vw.n}_2_done.png` });
    await p.goto(url); await sleep(1200);
    cols = await vis();
    ck(`${vw.n}: opened again - the choice was saved`, !cols.includes('Remarks') && cols.includes('Int. Qty'), cols);
    const pdf = await p.evaluate(async i => { const r = await fetch(`/export/est/pc/${i.id}?token=${i.tok}&format=pdf`); return r.status + ':' + (await r.arrayBuffer()).byteLength; }, info);
    ck(`${vw.n}: PDF builds with the choice (${pdf})`, /^200:\d{4,}/.test(pdf), pdf);
    ck(`${vw.n}: no page errors`, !errs.length, errs);
    await p.evaluate(async i => fetch(`/export/est/pc/${i.id}/cols?token=${i.tok}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hide: { A: [3, 5] } }) }), info);
    await p.context().close();
  }
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await br.close(); process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
