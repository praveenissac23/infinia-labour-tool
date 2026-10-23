// Estimation > Bills in the browser: upload the consultant's bill as the format, start next month's bill,
// type Total % on the Progress view, a payment on Payments, a cell on the sheet itself; preview / PDF / Excel.
const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/billsui_';
const D = process.env.BILLS_DIR || '/mnt/user-data/attachments/80e871d8-70e2-5c6a-a360-434939dea359/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const f913 = D + fs.readdirSync(D).find(n => n.endsWith('913-IPA_09.xlsx'));
const xls = fs.readdirSync(D).find(n => /914_MEP.*\.xls$/.test(n));

(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta');
  const P = meta.projects.find(x => x.code === '913').id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, [P]); await p.reload(); await sleep(1800);
  ck('Bills is a main tab', (await p.textContent('#pnav')).includes('Bills'));
  ck('no format yet: it says what to upload', (await p.textContent('#sec')).includes('No bill format for this project yet'));
  await p.screenshot({ path: SH + '1_empty.png' });

  // an old .xls is stopped in the browser with how to save it
  await p.click('#ipa-up'); await sleep(300);
  if (xls) {
    await p.setInputFiles('#fm-file', D + xls); await p.click('#m-save'); await sleep(500);
    ck('.xls refused with Save As advice', (await p.textContent('.toast')).includes('Save As'));
  }
  await p.setInputFiles('#fm-file', f913); await p.fill('#f-name', '913 - consultant IPA');
  await p.click('#m-save'); await sleep(6000);
  const t = await p.textContent('.toast').catch(() => '');
  ck('format read: lines found, every formula as Excel', /lines with Previous/.test(t) && /All \d+ formulas/.test(t), t);
  ck('format listed with its check', (await p.textContent('#sec')).includes('formulas match'));
  await p.screenshot({ path: SH + '2_format.png' });

  // next month's bill
  await p.click('#ipa-new'); await sleep(3000);
  ck('bill opens full screen as IPA 10', await p.isVisible('#big') && (await p.textContent('#b-title')).includes('IPA 10'), await p.textContent('#b-title'));
  const due0 = await p.textContent('#b-body .fig .v');
  await p.screenshot({ path: SH + '3_progress.png' });
  // MC Scope line at 30% -> 45%
  const inputs = await p.$$('.ipa-pct');
  let target = null;
  for (const i of inputs) { if ((await i.inputValue()) === '30') { target = i; break; } }
  ck('a line at 30% to update', !!target);
  const k = await target.getAttribute('data-k');
  await target.click(); await target.fill('45'); await p.keyboard.press('Enter'); await sleep(2500);
  const due1 = await p.textContent('#b-body .fig .v');
  ck('Total due worked out again after typing 45%', due1 !== due0, [due0, due1]);
  const now = await p.$(`.ipa-pct[data-k="${k}"]`);
  ck('the line keeps 45, marked changed', (await now.inputValue()) === '45' && (await now.getAttribute('class')).includes('ch'));
  ck('focus moved on to the next line', await p.evaluate(() => document.activeElement && document.activeElement.classList.contains('ipa-pct')));
  ck('work this month shown, 1 line moved on', (await p.textContent('#b-body')).includes('1 line moved on') && !(await p.textContent('#b-body .fig:nth-child(2) .v')).startsWith('0.00'));
  await p.fill('.ipa-pct >> nth=0', '150'); await p.keyboard.press('Enter'); await sleep(600);
  ck('over 100% refused', (await p.textContent('.toast')).includes('between 0 and 100'));
  await p.keyboard.press('Escape'); await sleep(200);
  await p.fill('#ipa-q', 'superstructure'); await sleep(900);
  ck('search narrows the lines', (await p.$$('.ipa-pct')).length < inputs.length);
  await p.screenshot({ path: SH + '4_typed.png' });
  await p.fill('#ipa-q', ''); await sleep(800);

  // payments
  await p.click('#ipa-views [data-v="payments"]'); await sleep(600);
  ck('payments show IPA 9 put on the list', (await p.$$eval('.ipa-pay', a => a.map(x => x.value))).includes('Payment Application No 9'));
  const descs = await p.$$('.ipa-pay[data-c="desc"]');
  let row9 = null; for (const d of descs) if ((await d.inputValue()) === 'Payment Application No 9') row9 = d;
  const tr = await row9.evaluateHandle(x => x.closest('tr'));
  const amt = await tr.$('.ipa-pay[data-c="amount"]');
  await amt.fill('=(989148-280)/1.05'); await amt.press('Tab'); await sleep(2500);
  ck('payment formula worked out', (await p.textContent('#ipa-view')).includes('941,779.05'), (await p.textContent('#ipa-view')).slice(0, 400));
  const due2 = await p.textContent('#b-body .fig .v');
  ck('...and comes off the total due', due2 !== due1, [due1, due2]);
  await p.screenshot({ path: SH + '5_payments.png' });

  // the sheet itself
  const sheets = await p.$$eval('#ipa-views [data-v^="sheet:"]', a => a.map(x => [x.dataset.v, x.textContent]));
  const ipa = sheets.find(s => s[1].trim() === 'IPA') || sheets[0];
  await p.click(`#ipa-views [data-v="${ipa[0]}"]`); await sleep(2000);
  ck('the IPA sheet is drawn with its typed cells marked', (await p.$$('.ipa-sheet td.ed')).length > 0 && (await p.textContent('.ipa-sheet')).includes('PAYMENT APPLICATION'));
  ck('...with the logo/stamps', (await p.$$('.ipa-sheet img.xi')).length > 0);
  await p.screenshot({ path: SH + '6_sheet.png' });
  // edit the issue date cell? pick the first editable text cell and put it back
  const ed = (await p.$$('.ipa-sheet td.ed'))[0];
  const before = await ed.getAttribute('data-raw');
  await ed.click(); await sleep(200);
  ck('clicking a blue cell opens it for typing', await p.isVisible('.ipa-cell'));
  await p.keyboard.press('Escape'); await sleep(200);
  ck('Escape closes it unchanged', !(await p.isVisible('.ipa-cell')) && (await ed.getAttribute('data-raw')) === before);

  // status + exports
  await p.selectOption('#ipa-st', 'Submitted'); await sleep(800);
  ck('status changed', (await p.textContent('#b-body')).includes('Submitted'));
  const [pv] = await Promise.all([ctx.waitForEvent('page'), p.click('#b-tools [data-xp="preview"]')]);
  await pv.waitForLoadState(); await sleep(1500);
  ck('preview shows the bill', (await pv.textContent('body')).includes('PAYMENT APPLICATION'));
  await pv.screenshot({ path: SH + '7_preview.png', fullPage: false }); await pv.close();
  const tok = (await api('/auth/download-token', { method: 'POST' })).token;
  const bid = (await api(`/store/est/ipa/list?project_id=${P}`)).bills[0].id;
  const heads = await p.evaluate(async ([bid, tok]) => { const o = {}; for (const f of ['pdf', 'excel']) { const r = await fetch(`/export/est/ipa/${bid}?token=${tok}&format=${f}`); const b = new Uint8Array(await r.arrayBuffer()); o[f] = [r.status, String.fromCharCode(...b.slice(0, 4))]; } return o; }, [bid, tok]);
  ck('PDF and Excel come out', heads.pdf[1] === '%PDF' && heads.excel[1].startsWith('PK'), heads);

  // back to the list
  await p.click('#b-x'); await sleep(1200);
  ck('list shows IPA 10 Submitted with its total', (await p.textContent('#sec')).includes('IPA 10') && (await p.textContent('#sec')).includes('Submitted'));
  await p.screenshot({ path: SH + '8_list.png' });
  // phone width
  await p.setViewportSize({ width: 390, height: 800 }); await sleep(400);
  await p.click('[data-ipa]'); await sleep(2500);
  await p.screenshot({ path: SH + '9_phone.png' });
  const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  ck('phone: no page overflow', ov <= 2, ov);
  ck('no page errors', !errs.length, errs);
  await br.close();
  console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
