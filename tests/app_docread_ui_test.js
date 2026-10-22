// "Read from document" across the app: petty cash from a receipt (PDF and phone photo), a PDC and a security
// cheque from a cheque photo, an expiry document from a passport / Emirates ID photo, an LPO from a supplier's
// quotation, material arrived from a delivery note (PDF and scan), the ADCB statement as a PDF and a scan, and
// a person's document in People. Each file is read in the browser - none is ever uploaded.
//   node tests/app_docread_ui_test.js
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/appdoc_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const C = JSON.parse(execSync(`python3 ${__dirname}/app_docread_fixtures.py /tmp/claude-0/appdocs`).toString());
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 1000 } });
  const uploads = [], errs = [];
  const page = async (path) => {
    const p = await ctx.newPage(); p.on('pageerror', e => errs.push(e.message));
    p.on('request', r => { if (/multipart/.test(r.headers()['content-type'] || '') || (r.postDataBuffer() || Buffer.alloc(0)).includes(Buffer.from('%PDF'))) uploads.push(r.url()); });
    await p.goto(B + path); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(1500);
    await p.goto(B + path); await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000); return p;
  };
  const readInto = async (p, kind, near, file) => {
    const bar = p.locator(`${near} >> xpath=preceding-sibling::div[contains(@class,"dr-bar")][@data-kind="${kind}"][1]`);
    ck(`${kind}: "Read from ..." button beside the form`, await bar.isVisible(), near);
    await bar.locator('input[type=file]').setInputFiles(file);
    await p.waitForFunction(b => { const o = b.querySelector('.dr-out'); return o && /ok|bad/.test(o.className); }, await bar.elementHandle(), { timeout: 120000 });
    return (await bar.locator('.dr-out').textContent()) || '';
  };
  const val = (p, id) => p.inputValue('#' + id);
  const num = s => Number(String(s).replace(/,/g, ''));

  // ---- 1. petty cash from a receipt: PDF, then a phone photo
  let p = await page('/?p=accounts#petty');
  for (const [k, f] of [['receipt', 'PDF'], ['receipt_photo', 'photo']]) {
    const msg = await readInto(p, 'receipt', '#pc-form', C[k].file);
    const got = { date: await val(p, 'pc-date'), sup: await val(p, 'pc-sup'), amt: num(await val(p, 'pc-amt')), rcpt: await val(p, 'pc-rcpt'), vat: await p.isChecked('#pc-vat'), trn: await val(p, 'pc-trn') };
    ck(`petty cash from the receipt ${f}: 19-Oct-2026, Al Hassai, 483.00, AH-55871, VAT ticked, TRN`, got.date === '2026-10-19' && /AL HASSAI/.test(got.sup) && got.amt === 483 && got.rcpt === 'AH-55871' && got.vat && got.trn === '100234567800003', [got, msg]);
    if (k === 'receipt_photo') await p.screenshot({ path: SH + 'petty.png' });
  }
  ck('petty cash: the visa form has its own "Read from receipt"', (await p.locator('.dr-bar[data-kind="receipt"]').count()) === 2);
  // save it the normal way and check the saved line
  await p.fill('#pc-desc', 'Cement and sand - from receipt');
  const saved = await p.evaluate(async () => { try { await pcSave(); return true; } catch (e) { return e.message; } }); await sleep(1500);
  const rows = await p.evaluate(async () => (await apiCall('/store/petty-cash?' + pcPeriodQuery()).catch(() => ({}))));
  const hit = JSON.stringify(rows).includes('AH-55871');
  ck('petty cash: saved with the receipt no. (only when Save is pressed)', saved === true && hit, [saved, JSON.stringify(rows).slice(0, 200)]);

  // ---- 2. bank statement: PDF and scan
  await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Bank'); t && t.click(); }); await sleep(2500);
  await p.evaluate(() => { const m = document.getElementById('bk-month'); if (m) { m.value = '2026-10'; return bkLoad(); } }); await sleep(1500);
  const accept = await p.getAttribute('#bk-stmt input[type=file]', 'accept');
  ck('bank: the statement upload takes PDF and photos too', /\.pdf/.test(accept) && /\.jpg/.test(accept), accept);
  await p.setInputFiles('#bk-stmt input[type=file]', C.bank.file); await p.waitForFunction(() => /Statement|Could|No text/.test(document.getElementById('bk-status').textContent), null, { timeout: 60000 });
  let bs = await p.textContent('#bk-status');
  ck('bank: the PDF statement - 4 lines, 2-Oct to 12-Oct, the running balance checks out', /4 lines, (4 new|0 new, 4 already in)/.test(bs) && /checks out/.test(bs), bs);
  await p.screenshot({ path: SH + 'bank_pdf.png' });
  const lines = await p.evaluate(async () => (await apiCall('/store/bank/stmt?month=2026-10').catch(() => null)));
  await p.setInputFiles('#bk-stmt input[type=file]', C.bank_scan.file); await p.waitForFunction(() => /Statement .*scan|Statement/.test(document.getElementById('bk-status').textContent) && !/Reading|Scanned page|Recognising/.test(document.getElementById('bk-status').textContent), null, { timeout: 180000 });
  bs = await p.textContent('#bk-status');
  ck('bank: the scanned statement - 4 lines, the balance checks out (misread figures put right from the balance)', /4 lines/.test(bs) && /checks out/.test(bs), bs);
  await p.close();

  // ---- 3. PDC and security cheque from a cheque photo
  p = await page('/?p=expiry#expiry:pdc'); await sleep(2000);
  await readInto(p, 'cheque', '.pdc-form', C.cheque.file);
  let g = { payee: await val(p, 'pdc-payee'), no: await val(p, 'pdc-no'), bank: await val(p, 'pdc-bank'), date: await val(p, 'pdc-date'), amt: num(await val(p, 'pdc-amt')) };
  ck('PDC from the cheque photo: Desarch Scaffolding LLC, 000451, ADCB, 15-Nov-2026, 12,500.00', g.payee === 'Desarch Scaffolding LLC' && g.no === '000451' && g.bank === 'ADCB' && g.date === '2026-11-15' && g.amt === 12500, g);
  await p.screenshot({ path: SH + 'pdc.png' });
  await p.goto(B + '/?p=expiry#expiry:security'); await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3500);
  await readInto(p, 'cheque', '.sc-form', C.cheque.file);
  g = { party: await val(p, 'sc-party'), no: await val(p, 'sc-no'), amt: num(await val(p, 'sc-amt')), date: await val(p, 'sc-date'), und: await p.isChecked('#sc-undated') };
  ck('security cheque from the photo: given to, cheque no., amount, dated (not undated)', g.party === 'Desarch Scaffolding LLC' && g.no === '000451' && g.amt === 12500 && g.date === '2026-11-15' && !g.und, g);

  // ---- 4. expiry documents from a passport and an Emirates ID
  await p.goto(B + '/?p=expiry#expiry:all'); await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3500);
  await p.evaluate(() => { const b = document.getElementById('hr-doc-people'); if (b) b.style.display = ''; });
  for (const [k, e] of [['passport', { kind: 'passport', number: 'Z1234567', iss: '2020-02-03', exp: '2030-02-02' }], ['eid', { kind: 'eid', number: '784-1988-1234567-1', iss: '2025-03-14', exp: '2027-03-13' }]]) {
    const msg = await readInto(p, 'iddoc', '#hr-doc-emp >> xpath=ancestor::div[contains(@class,"form-row")][1]', C[k].file);
    g = { kind: await val(p, 'hr-doc-kind'), number: await val(p, 'hr-doc-number'), iss: await val(p, 'hr-doc-issued'), exp: await val(p, 'hr-doc-expires') };
    ck(`expiry document from the ${k} photo: ${e.kind}, ${e.number}, issued ${e.iss}, expires ${e.exp}`, JSON.stringify(g) === JSON.stringify(e), [g, msg]);
    if (k === 'passport') await p.screenshot({ path: SH + 'passport.png' });
  }
  await p.close();

  // ---- 5. LPO from a supplier quotation
  p = await page('/?p=store#purchasing'); await sleep(1500);
  await p.evaluate(async () => { await newLpo(); }); await sleep(1200);
  await readInto(p, 'quotation', '.lpo-sides', C.quotation.file);
  const lpo = await p.evaluate(() => ({ sup: document.getElementById('lpo-supplier').value, trn: document.getElementById('lpo-trn').value, ref: document.getElementById('lpo-supref').value, date: document.getElementById('lpo-date').value,
                                        lines: lpoLines.map(l => [l.description, +l.qty, l.unit, +l.rate]) }));
  ck('LPO from the quotation: supplier, TRN, their ref., date', /EMIRATES TILES/.test(lpo.sup) && lpo.trn === '100456789100003' && lpo.ref === 'ETQ/26/1184' && lpo.date === '2026-10-16', lpo);
  ck('LPO: the 3 priced lines with qty, unit and rate (420 sqm @ 38, 180 bag @ 21.50, 60 bag @ 18)', JSON.stringify(lpo.lines) === JSON.stringify(C.quotation.expect.items), lpo.lines);
  await p.screenshot({ path: SH + 'lpo.png' });

  // ---- 6. material arrived from a delivery note: the order's lines on the form, one not on the note
  for (const [k, f] of [['delivery', 'PDF'], ['delivery_scan', 'scan']]) {
    await p.evaluate(() => {
      const opt = document.getElementById('recv-supplier-pick');
      opt.innerHTML = '<option value="">- pick -</option><option value="7">Gulf Steel Trading LLC</option><option value="8">Emirates Tiles</option>';
      window.suppliers = (window.suppliers || []).concat([{ id: 7, name: 'Gulf Steel Trading LLC' }]);
      const row = (n, due, u) => `<tr data-sup=""><td>${n}</td><td>${due} ${u}</td><td>-</td><td><strong>${due}</strong></td><td><input type="number" class="recv-qty" step="any" max="${due}" value="${due}"></td><td></td></tr>`;
      document.getElementById('recv-lines').innerHTML = row('<strong>RB12</strong> Rebar 12 mm Grade 60', 5, 'ton') + row('<strong>RB16</strong> Rebar 16 mm Grade 60', 3, 'ton') + row('Binding wire 1.2 mm', 20, 'roll') + row('Cover blocks 40mm', 500, 'pcs');
      document.getElementById('recv-ref-no').value = ''; document.getElementById('recv-date').value = '';
      document.getElementById('recv-modal-overlay').style.display = 'flex';
    });
    const msg = await readInto(p, 'delivery', '#recv-supplier-pick >> xpath=ancestor::div[contains(@class,"form-row")][1]', C[k].file);
    const q = await p.$$eval('#recv-lines .recv-qty', x => x.map(i => i.value));
    g = { ref: await val(p, 'recv-ref-no'), date: await val(p, 'recv-date'), sup: await p.$eval('#recv-supplier-pick', s => s.options[s.selectedIndex].text) };
    ck(`material arrived from the delivery note ${f}: GS-DO-7781, 20-Oct-2026, Gulf Steel picked`, g.ref === 'GS-DO-7781' && g.date === '2026-10-20' && /Gulf Steel/.test(g.sup), [g, msg]);
    ck(`delivery note ${f}: quantities by material - 2.5, 1.75, 10, and the cover blocks (not on the note) cleared`, JSON.stringify(q) === JSON.stringify(['2.5', '1.75', '10', '']), [q, msg]);
    if (k === 'delivery_scan') await p.screenshot({ path: SH + 'delivery.png' });
  }
  await p.close();

  // ---- 7. People: a person's document from a passport photo
  p = await ctx.newPage(); p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/people.html'); await sleep(800);
  if (await p.isVisible('#login-username')) { await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.click('#login button'); await sleep(2500); }
  const opened = await p.evaluate(async () => { try { const r = document.querySelector('[onclick^="openPerson"]'); if (r) { r.click(); } await new Promise(z => setTimeout(z, 1500)); openDoc(null); return true; } catch (e) { return e.message; } });
  if (opened === true) {
    const msg = await readInto(p, 'iddoc', '#d-number >> xpath=ancestor::div[contains(@class,"row")][1]', C.passport.file);
    g = { number: await val(p, 'd-number'), iss: await val(p, 'd-issued_on'), exp: await val(p, 'd-expires_on') };
    ck('People document from the passport photo: Z1234567, issued 2020-02-03, expires 2030-02-02', g.number === 'Z1234567' && g.iss === '2020-02-03' && g.exp === '2030-02-02', [g, msg]);
    await p.screenshot({ path: SH + 'people.png' });
  } else ck('People: document dialog opened', false, opened);

  ck('no file was ever sent to the server', uploads.length === 0, uploads);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
