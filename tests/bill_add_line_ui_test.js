// Work done: "+ Line" / "+ Section" on each section, and a ⋮ on every line and heading - Edit line details,
// Add line below, Add section below, Remove (only what was added and never billed). The new line works like the
// ones around it (QTY x RATE, % columns) and the totals take it in.
//   python3 tests/make_ipa_like_914.py /tmp/claude-0/bills/914-like.xlsx ; BASE=http://127.0.0.1:8042 node tests/bill_add_line_ui_test.js
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/bal_', F = process.env.BILL || '/tmp/claude-0/bills/914-like.xlsx';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = (path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === '904').id;
  const b64 = fs.readFileSync(F).toString('base64');
  await p.evaluate(async ([pid, b64]) => { const fd = new FormData(); fd.append('project_id', pid); fd.append('file', new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))]), '914-like.xlsx');
    await fetch('/store/est/ipa/format', { method: 'POST', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') }, body: fd }); }, [P, b64]);
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, [P]); await p.reload(); await sleep(2500);
  await p.click('#ipa-new'); await sleep(2500);
  const D = 'Division 03-Concrete Works', C = 'APP C';
  const sec = n => `.ipa-sec:has(h3:text-is("${n}"))`;
  ck('each section has + Line and + Section', (await p.$$('[data-addln]')).length >= 2 && (await p.$$('[data-addsec]')).length >= 2);
  ck('the headings 3.1.1 / 3.2.2 show between the lines', (await p.$$eval(`${sec(D)} tr.hd .it`, x => x.map(e => e.textContent))).join() === '3.1.1,3.2.2');
  ck('every line has a ⋮', (await p.$$(`${sec(D)} tr[data-line] .ln-menu`)).length === 3);
  const due = async () => (await p.textContent('.ipa-due b')).replace(/[^\d.-]/g, '') * 1;
  const due0 = await due();
  // + Line on the Division: the form asks Item, Description, Unit, QTY, RATE
  await p.click(`[data-addln="${D}"]`); await sleep(500);
  const labels = await p.$$eval('#m-body label', x => x.map(e => e.childNodes[0].textContent.trim()));
  ck('new line form: Item, Description, Unit, Qty, Rate (amount worked out, not asked)', ['Item / ref.', 'Description', 'Unit'].every(l => labels.includes(l)) && labels.some(l => /qty/i.test(l)) && labels.some(l => /rate/i.test(l)) && !labels.some(l => /^Amount/.test(l)), labels);
  await p.fill('#f-item', '3.2.2.3'); await p.fill('#f-desc', 'Additional lintel beams'); await p.fill('#f-unit', 'M3'); await p.fill('#f-c5', '4'); await p.fill('#f-c6', '2000');
  await p.screenshot({ path: SH + '1_form.png' });
  await p.click('#m-save'); await sleep(1800);
  const row = `${sec(D)} tr[data-line]:has(td.it:text-is("3.2.2.3"))`;
  ck('the new line is in the section, marked added, 8,000', !!(await p.$(row)) && /added/.test(await p.textContent(row)) && /8,000/.test(await p.textContent(`${row} td[data-l="Amount"]`)));
  ck('...its Total % box is ready to type', await p.evaluate(() => document.activeElement && document.activeElement.classList.contains('ipa-in')));
  await p.fill(`${row} input[data-w="tot"]`, '50'); await p.press(`${row} input[data-w="tot"]`, 'Enter'); await sleep(3500);
  const due1 = await due();
  ck('50% typed: total due up by 4,000', Math.abs(due1 - due0 - 4000) < 0.01, [due0, due1]);
  // ⋮ on V02: edit its details (description + amount)
  const v2 = `${sec(C)} tr[data-line]:has(td.it:text-is("V02"))`;
  await p.click(`${v2} .ln-menu`); await sleep(300);
  ck('⋮ menu: Edit line details / Add line below / Add section below (no Remove on a consultant line)', (await p.$$eval('#ln-pop button', x => x.map(e => e.textContent))).join('|') === 'Edit line details|Add line below|Add section below');
  await p.screenshot({ path: SH + '2_menu.png' });
  await p.click('#ln-pop [data-do="edit"]'); await sleep(400);
  await p.fill('#f-desc', 'Kitchen extension'); await p.fill('#f-amount', '5000'); await p.click('#m-save'); await sleep(1500);
  ck('V02 now reads Kitchen extension, 5,000', /Kitchen extension/.test(await p.textContent(v2)) && /5,000/.test(await p.textContent(`${v2} td[data-l="Amount"]`)));
  // a new variation under V05 from its ⋮
  await p.click(`${sec(C)} tr[data-line]:has(td.it:text-is("V05")) .ln-menu`); await sleep(300); await p.click('#ln-pop [data-do="line"]'); await sleep(400);
  ck('APP C form asks the amount', !!(await p.$('#f-amount')));
  await p.fill('#f-item', 'V06'); await p.fill('#f-desc', 'Extra skylight'); await p.fill('#f-amount', '12000'); await p.click('#m-save'); await sleep(1800);
  const items = await p.$$eval(`${sec(C)} tr[data-line] td.it`, x => x.map(e => e.textContent));
  ck('V06 lands right after V05', items.indexOf('V06') === items.indexOf('V05') + 1, items);
  // a section after 3.2.2.3, then a line under it from the section's ⋮
  await p.click(`${row} .ln-menu`); await sleep(300); await p.click('#ln-pop [data-do="head"]'); await sleep(400);
  ck('section form: Ref. and Section name', (await p.$$eval('#m-body label', x => x.map(e => e.childNodes[0].textContent.trim()))).join('|') === 'Ref. (optional)|Section name');
  await p.fill('#f-item', '3.3'); await p.fill('#f-desc', 'Additional works'); await p.click('#m-save'); await sleep(1800);
  const hd = `${sec(D)} tr.hd:has(.hd-t:text-is("Additional works"))`;
  ck('the section shows as a heading', !!(await p.$(hd)));
  await p.click(`${hd} .ln-menu`); await sleep(300); await p.click('#ln-pop [data-do="line"]'); await sleep(400);
  await p.fill('#f-item', '3.3.1'); await p.fill('#f-desc', 'Pump room slab'); await p.fill('#f-unit', 'M3'); await p.fill('#f-c5', '2'); await p.fill('#f-c6', '1500'); await p.click('#m-save'); await sleep(1800);
  const order = await p.$$eval(`${sec(D)} tbody tr`, x => x.map(e => (e.querySelector('.it') || {}).textContent));
  ck('order: ... 3.2.2.3, 3.3 (section), 3.3.1', order.slice(-3).join() === '3.2.2.3,3.3,3.3.1', order);
  await p.$eval(hd, el => el.scrollIntoView({ block: 'center' })); await sleep(300);
  await p.screenshot({ path: SH + '3_added.png' });
  // remove the line under the section
  const l331 = `${sec(D)} tr[data-line]:has(td.it:text-is("3.3.1"))`;
  await p.click(`${l331} .ln-menu`); await sleep(300);
  ck('an added line has Remove line', /Remove line/.test(await p.textContent('#ln-pop')));
  await p.click('#ln-pop [data-do="del"]'); await sleep(400);
  ck('...which asks first', await p.isVisible('#cfm'));
  await p.click('#cfm-ok'); await sleep(1500);
  ck('...and it is gone, the section stays', !(await p.$(l331)) && !!(await p.$(hd)));
  // the sheet view: + Line below on a line of the table opens the same form
  await p.click('#ipa-nav [data-step="sheets"]'); await sleep(1800);
  await p.selectOption('.sv-pick', { label: D }); await sleep(1500);
  await p.click('.sv-in tr[data-r="9"]'); await sleep(300); await p.click('[data-rw="below"]'); await sleep(500);
  ck('Sheets: + Line below on a table line opens the same form', await p.isVisible('#modal:not(.hide) #f-c5'));
  await p.click('#m-cancel'); await sleep(300);
  // phone
  await p.setViewportSize({ width: 390, height: 844 }); await p.click('#ipa-nav [data-step="work"]').catch(() => {}); await p.evaluate(() => { IPA.step = 'work'; drawBill(); }); await sleep(1200);
  await p.$eval(hd, el => el.scrollIntoView({ block: 'center' })); await sleep(300);
  const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  ck('phone: no sideways scroll', ov <= 1, ov);
  await p.screenshot({ path: SH + '4_phone.png' });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
