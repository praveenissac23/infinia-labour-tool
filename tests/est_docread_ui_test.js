// "Read from document" on every Estimation form: a letter of award, a tender invitation, a subcontractor's
// invoice, a variation quotation, a cost proposal, an interim payment certificate, an RFI, a NOC - and a PDF
// priced schedule into a subcontract's item schedule. The file is read in the browser; nothing is uploaded.
//   AGREEMENT_FILE=<909 agreement.pdf> node tests/est_docread_ui_test.js
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/docui_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const C = JSON.parse(execSync(`python3 ${__dirname}/est_docread_fixtures.py /tmp/claude-0/docfix`).toString());
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  const uploads = []; p.on('request', r => { if (/multipart/.test(r.headers()['content-type'] || '') || (r.postDataBuffer() || Buffer.alloc(0)).includes(Buffer.from('%PDF'))) uploads.push(r.url()); });
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta');
  const go = async (code, sec) => { const P = meta.projects.find(x => x.code === code).id; await p.evaluate(([pid, sec]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', sec); }, [P, sec]); await p.goto(B + '/portal/est-app.html?view=projects'); await sleep(1400); return P; };
  const read = async (kind, open) => {
    await open(); await sleep(400);
    ck(`${kind}: the form has "Read from document"`, await p.isVisible('#doc-pick'));
    await p.setInputFiles('#doc-file', C[kind].file); await p.waitForSelector('#doc-out .agres, #doc-out .agnote.bad', { timeout: 30000 }); await sleep(300);
    const e = C[kind].expect, miss = [];
    for (const [k, v] of Object.entries(e)) {
      if (k === 'sub' || k === 'lines') continue;
      const got = await p.inputValue('#f-' + k).catch(() => null);
      if (got === null) continue;                 // this form has no such box
      const ok = typeof v === 'number' ? Math.abs(Number(String(got).replace(/,/g, '')) - v) < .01 : (k === 'title' ? String(got).startsWith(v) : got === v);
      if (!ok) miss.push([k, v, got]);
    }
    ck(`${kind}: every detail filled in (${Object.keys(e).filter(k => k !== 'sub' && k !== 'lines').join(', ')})`, !miss.length, miss);
  };
  // 1. new project from a letter of award
  await go('909', 'home.dash');
  await read('project', () => p.evaluate(() => newProject()));
  await p.screenshot({ path: SH + 'project.png' }); await p.click('#m-cancel');
  // 2. tender
  await p.goto(B + '/portal/est-app.html?view=tenders'); await sleep(1500);
  await read('tender', () => p.evaluate(() => tenderForm()));
  await p.screenshot({ path: SH + 'tender.png' }); await p.click('#m-save'); await sleep(900);
  const tl = await api('/store/est/tenders');
  ck('tender: saved with its submission date', (tl.tenders || []).some(t => t.name.startsWith('Design & Build of B+G+1 Villa') && t.due === '2026-11-05'));
  // 3. invoice received on 922 - the subcontractor picked from the invoice
  let P922 = await go('922', 'subs.inv');
  let b922 = await api(`/store/est/projects/${P922}`);
  if (!b922.subs.some(s => /Al Noor/.test(s.name))) {           // the subcontractor the invoice is from (no test data on the app since go-live)
    await api('/store/est/subs', { method: 'POST', body: { project_id: P922, name: 'Al Noor Technical Manpower', scope: 'Manpower', value: 250000, ret_pct: 10, status: 'Active' } });
    P922 = await go('922', 'subs.inv'); b922 = await api(`/store/est/projects/${P922}`);
  }
  const alnoor = b922.subs.find(s => /Al Noor/.test(s.name));
  await read('invoice', () => p.evaluate(() => invoiceForm()));
  ck('invoice: the subcontractor chosen from the name on the invoice', Number(await p.inputValue('#f-sub_id')) === alnoor.id, await p.inputValue('#f-sub_id'));
  await p.screenshot({ path: SH + 'invoice.png' });
  await p.click('#m-save'); await sleep(1200);
  const b2 = await api(`/store/est/projects/${P922}`), pc = b2.subs.find(s => s.id === alnoor.id).pcs.find(x => x.inv_ref === 'ANT/12');
  ck('invoice: saved, with the 2 bill lines kept for its certificate', !!pc && JSON.parse(pc.inv_lines || '[]').length === 2, pc && pc.inv_lines);
  // 3b. the same invoice scanned, and photographed on a phone
  for (const f of ['Al Noor invoice scanned.pdf', 'Al Noor invoice photo.jpg']) {
    await p.evaluate(() => invoiceForm()); await sleep(400);
    await p.setInputFiles('#doc-file', `${process.env.SCANS || '/tmp/claude-0/docs'}/${f}`); await p.waitForSelector('#doc-out .agres, #doc-out .agnote.bad', { timeout: 180000 }); await sleep(300);
    const got = [await p.inputValue('#f-inv_ref'), await p.inputValue('#f-inv_date'), Number(String(await p.inputValue('#f-inv_amount')).replace(/,/g, '')), Number(await p.inputValue('#f-sub_id'))];
    ck(`${f}: read by text recognition - ANT/12, 18-Oct-2026, 33,600.00, Al Noor`, got[0] === 'ANT/12' && got[1] === '2026-10-18' && Math.abs(got[2] - 33600) < .01 && got[3] === alnoor.id, got);
    if (/photo/.test(f)) await p.screenshot({ path: SH + 'invoice_photo.png' });
    await p.click('#m-cancel');
  }
  // 4. variation to the subcontract
  await read('subvo', () => p.evaluate(id => voSubForm(ST.b.subs.find(s => s.id === id)), alnoor.id));
  await p.click('#m-cancel');
  // 5. client variation, 6. client PC
  await go('909', 'site.vo');
  await read('variation', () => p.evaluate(() => voForm()));
  await p.screenshot({ path: SH + 'variation.png' }); await p.click('#m-cancel');
  await go('909', 'client.cpc');
  await read('clientpc', () => p.evaluate(() => cpcForm()));
  await p.click('#m-cancel');
  // 7. RFI, 8. NOC
  await go('909', 'site.rfi');
  await read('log', () => p.evaluate(() => logForm('rfi')));
  await p.screenshot({ path: SH + 'rfi.png' }); await p.click('#m-cancel');
  await go('909', 'site.approval');
  await read('approval', () => p.evaluate(() => apForm()));
  ck('NOC: authority picked from the list', /DEWA/.test(await p.inputValue('#f-party')), await p.inputValue('#f-party'));
  await p.click('#m-cancel');
  // 9. a PDF priced schedule into a subcontract's item schedule
  if (process.env.AGREEMENT_FILE) {
    const P909 = await go('909', 'subs.reg');
    const sid = (await api('/store/est/subs', { method: 'POST', body: { project_id: P909, name: 'SCHEDULE PDF TEST', scope: 'Joinery', value: 534000 } })).id;
    await go('909', 'subs.reg'); await p.click(`[data-sub="${sid}"]`); await sleep(700);
    await p.setInputFiles('#s-up-f', process.env.AGREEMENT_FILE); await p.waitForSelector('#m-save', { state: 'visible', timeout: 30000 }); await sleep(500);
    ck('schedule: 26 lines from the PDF, sections A B C checked', /Bring in 26 lines/.test(await p.textContent('#m-save')) && (await p.$$eval('#m-body .st.g', x => x.length)) >= 3);
    await p.screenshot({ path: SH + 'schedule.png' });
    await p.click('#m-save'); await sleep(1500);
    const its = await api(`/store/est/subs/${sid}/items`);
    ck('schedule: saved - 26 lines, 534,000.00', its.items.length === 26 && Math.abs(its.total - 534000) < .005, [its.items.length, its.total]);
    await api(`/store/est/subs/${sid}`, { method: 'DELETE' });
  }
  ck('no file was ever sent to the server', uploads.length === 0, uploads);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
