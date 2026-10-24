// Estimation > Bills in the browser, step by step: upload the consultant's bill as the format, start next month's bill,
// Cover (bill no., issue date, payment summary), Work done (This month % or Total %, in place), Payments received
// (money not formulas, date picker), Review (checks, preview, status, a figure on a sheet); a second format; phone width.
const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/billsui_';
const D = process.env.BILLS_DIR || '/mnt/user-data/attachments/80e871d8-70e2-5c6a-a360-434939dea359/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const file = pat => D + fs.readdirSync(D).find(n => n.includes(pat));
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

  await p.click('#ipa-up'); await sleep(300);
  if (xls) { await p.setInputFiles('#fm-file', D + xls); await p.click('#m-save'); await sleep(500); ck('.xls refused with Save As advice', (await p.textContent('.toast')).includes('Save As')); }
  await p.setInputFiles('#fm-file', file('913-IPA_09')); await p.fill('#f-name', '913 - consultant IPA');
  await p.click('#m-save'); await sleep(6000);
  const t = await p.textContent('.toast').catch(() => '');
  ck('format read: lines found, every formula as Excel', /lines with Previous/.test(t) && /All \d+ formulas/.test(t), t);

  await p.click('#ipa-new'); await sleep(3000);
  ck('bill opens on Work done, titled Interim Bill 10', await p.isVisible('#big') && (await p.textContent('#b-title')).includes('Interim Bill 10') && (await p.getAttribute('#ipa-nav [data-step="work"]', 'class')).includes('on'));
  ck('no sideways page scroll', await p.evaluate(() => { const b = document.querySelector('#big .bbody'); return b.scrollWidth <= b.clientWidth + 2; }));
  const due = async () => (await p.textContent('#ipa-nav .ipa-due b')).trim();
  const due0 = await due();

  // ---- Work done: MC Scope, RCC 30% -> type 15 in This month
  const row = async txt => (await p.$$('tr[data-line]')).find(async () => true) && (await p.$$eval('tr[data-line]', (rs, txt) => rs.findIndex(r => r.textContent.includes(txt)), txt));
  const i = await row('RCC for Columns');
  const tr = (await p.$$('tr[data-line]'))[i];
  const now = await tr.$('input[data-w="now"]'), tot = await tr.$('input[data-w="tot"]');
  ck('nothing this month: This month is empty, Total = 30', (await now.inputValue()) === '' && (await tot.inputValue()) === '30', [await now.inputValue(), await tot.inputValue()]);
  await now.click(); await now.fill('15'); await p.keyboard.press('Enter'); await sleep(2500);
  ck('Total % fills itself: 45', (await tot.inputValue()) === '45', await tot.inputValue());
  ck('the row is marked moved, this month AED 197,343.15', (await tr.getAttribute('class')).includes('moved') && (await tr.textContent()).includes('197,343.15'), await tr.textContent());
  ck('Enter went on to the next line', await p.evaluate(() => document.activeElement && document.activeElement.dataset.w === 'now' && !document.activeElement.closest('tr').textContent.includes('RCC')));
  const due1 = await due();
  ck('total due worked out again by the consultant formulas', due1 !== due0, [due0, due1]);
  ck('side panel: 1 of N lines moved', (await p.textContent('#ipa-nav [data-step="work"] small')).startsWith('1 of'));
  // Total % typed the other way
  await tot.click(); await tot.fill('50'); await p.keyboard.press('Tab'); await sleep(2500);
  ck('typing Total 50 makes This month 20', (await now.inputValue()) === '20', await now.inputValue());
  // over 100 refused
  const tr0 = (await p.$$('tr[data-line]'))[0];
  const t0 = await tr0.$('input[data-w="tot"]');
  await t0.click(); await t0.fill('140'); await p.keyboard.press('Enter'); await sleep(700);
  ck('over 100% refused, value put back', (await p.textContent('.toast')).includes('cannot go over 100%') && (await t0.inputValue()) !== '140');
  await p.keyboard.press('Escape'); await sleep(200);
  ck('Escape in a box does not close the bill', await p.isVisible('#big'));
  // filters + search
  await p.click('[data-flt="moved"]'); await sleep(500);
  ck('Moved this month shows only the moved line', (await p.$$('tr[data-line]')).length === 1);
  await p.click('[data-flt=""]'); await sleep(400);
  await p.fill('#ipa-q', 'plaster'); await sleep(700);
  ck('search narrows the lines', (await p.$$('tr[data-line]')).length >= 1 && (await p.$$('tr[data-line]')).length < 5);
  await p.fill('#ipa-q', ''); await sleep(600);
  await p.screenshot({ path: SH + '2_work.png' });

  // ---- Cover
  await p.click('#ipa-nav [data-step="cover"]'); await sleep(900);
  const cv = await p.textContent('.ipa-cover');
  ck('cover: project, client, payment summary and words', cv.includes('SOBHA HARTLAND') && cv.includes('ASIF') && cv.includes('Total Amount due for Payment') && /DIRHAMS/i.test(cv), cv.slice(0, 300));
  ck('cover total = side panel total', cv.includes((await due()).replace('AED ', '')));
  await p.fill('#cv-date', '2026-10-25'); await p.dispatchEvent('#cv-date', 'change'); await sleep(1500);
  ck('issue date saved', (await p.textContent('#ipa-nav [data-step="cover"] small')).includes('25-Oct-26'));
  await p.screenshot({ path: SH + '1_cover.png' });

  // ---- Payments
  await p.click('#ipa-nav [data-step="pay"]'); await sleep(900);
  ck('no formula shown in the payments', !(await p.$$eval('.ipa-pin', a => a.some(x => x.value.startsWith('=') || /\(\d+.*\)\/1\.05/.test(x.value)))));
  const descs = await p.$$('.ipa-pin[data-c="desc"]');
  let r9 = null; for (const d of descs) if ((await d.inputValue()) === 'Payment Application No 9') r9 = d;
  ck('IPA 9 is on the list', !!r9);
  const prow = await r9.evaluateHandle(x => x.closest('tr'));
  const am = await prow.$('.ipa-pin[data-c="amount"]');
  await am.click(); await am.fill('(989148-280)/1.05'); await p.keyboard.press('Tab'); await sleep(2500);
  const am2 = (await p.$$('.ipa-pin[data-c="amount"]'))[(await p.$$eval('.ipa-pin[data-c="desc"]', a => a.findIndex(x => x.value === 'Payment Application No 9')))];
  ck('the sum is shown as money: 941,779.05', (await am2.inputValue()) === '941,779.05', await am2.inputValue());
  await am2.click(); await sleep(200);
  ck('...and the sum comes back to change it', (await am2.inputValue()).includes('989148'), await am2.inputValue());
  await p.keyboard.press('Escape'); await am2.evaluate(x => x.blur()); await sleep(500);
  const rowNow = (await p.$$('.ipa-pay tbody tr'))[(await p.$$eval('.ipa-pin[data-c="desc"]', a => a.findIndex(x => x.value === 'Payment Application No 9')))];
  const rc = await rowNow.$('.ipa-pin[data-c="received"]');
  if (rc) { await rc.fill('2026-10-20'); await rc.dispatchEvent('change'); await sleep(1500); }
  const pv = await api(`/store/est/ipa/bill/${(await api(`/store/est/ipa/list?project_id=${P}`)).bills[0].id}`);
  const r9d = pv.payments[0].rows.find(x => x.desc.value === 'Payment Application No 9');
  ck('received date written like the consultant writes it', !rc || ['20.10.2026', 46315].includes(r9d.received.value), r9d.received);
  await p.click('[data-addpay]'); await sleep(500);
  ck('+ Add a payment line gives one empty line', (await p.$$eval('.ipa-pin[data-c="desc"]', a => a.filter(x => !x.value).length)) === 1);
  await p.screenshot({ path: SH + '3_pay.png' });

  // ---- Review
  await p.click('#ipa-nav [data-step="review"]'); await sleep(3500);
  const rv = await p.textContent('.ipa-rev');
  ck('review: total due and checks', rv.includes('Total amount due') && rv.includes('1 line moved on this month') && rv.includes('Every earlier bill'), rv.slice(0, 400));
  const fr = p.frames().find(f => f.url().includes('format=preview'));
  ck('the print preview is on the page', !!fr && (await fr.textContent('body')).includes('PAYMENT APPLICATION'));
  await p.screenshot({ path: SH + '4_review.png' });
  await p.click('#ipa-adv summary'); await sleep(2000);
  ck('a sheet opens for a figure to be changed; blank cells are not typed in', (await p.$$('.ipa-sheet td.ed')).length > 0 && (await p.$$eval('.ipa-sheet td.ed', a => a.every(x => x.textContent.trim() !== ''))));
  await p.selectOption('#sh-pick', { label: 'MC Scope' }); await sleep(1800);
  ck('sheet picker switches sheet', (await p.textContent('.ipa-sheet')).includes('Clearance of site'));
  await p.click('#ipa-submit'); await sleep(1000);
  ck('Mark as submitted', (await p.textContent('#b-title')).includes('Submitted'));
  const heads = await p.evaluate(async () => { const t = await (await fetch('/auth/download-token', { method: 'POST', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json();
    const id = document.querySelector('#b-tools [data-xp]') ? JSON.parse(document.querySelector('#b-tools [data-xp]').dataset.k).extra.id : 0; const o = {};
    for (const f of ['pdf', 'excel']) { const r = await fetch(`/export/est/ipa/${id}?token=${t.token}&format=${f}`); const b = new Uint8Array(await r.arrayBuffer()); o[f] = String.fromCharCode(...b.slice(0, 4)); } return o; });
  ck('PDF and Excel come out', heads.pdf === '%PDF' && heads.excel.startsWith('PK'), heads);
  await p.click('#b-x'); await sleep(1200);
  ck('list shows IPA 10 Submitted', (await p.textContent('#sec')).includes('IPA 10') && (await p.textContent('#sec')).includes('Submitted'));

  // ---- a second consultant's format: Total = Previous + Current, a cover text built from figures (909 / 914)
  const P2 = meta.projects.find(x => x.code === '909').id;
  for (const [pat, code] of [['909-IPA09', '909']]) {
    const b64 = fs.readFileSync(file(pat)).toString('base64');
    await p.evaluate(async ([P, b64, name]) => { const bin = atob(b64); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      const fd = new FormData(); fd.append('project_id', P); fd.append('name', name); fd.append('file', new Blob([u]), name + '.xlsx');
      await fetch('/store/est/ipa/format', { method: 'POST', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') }, body: fd }); }, [P2, b64, pat]);
  }
  const L2 = await api(`/store/est/ipa/list?project_id=${P2}`);
  const nb = await api('/store/est/ipa/new', { method: 'POST', body: { project_id: P2, format_id: L2.formats[0].id } });
  const tok = (await api('/auth/download-token', { method: 'POST' })).token;
  const html = await p.evaluate(async ([id, tok]) => (await fetch(`/export/est/ipa/${id}?token=${tok}&format=preview`)).text(), [nb.id, tok]);
  ck('909 cover: figures inside text shown as money, not 3589674.704', !/\d{7}\.\d{3}/.test(html) && /AED [\d,]+\.\d\d/.test(html));

  // ---- phone
  await p.setViewportSize({ width: 390, height: 820 }); await sleep(300);
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); }, [P]); await p.reload(); await sleep(1800);
  await p.click('[data-ipa]'); await sleep(2500);
  await p.screenshot({ path: SH + '5_phone.png' });
  ck('phone: no page overflow', await p.evaluate(() => { const b = document.querySelector('#big .bbody'); return b.scrollWidth <= b.clientWidth + 2 && document.documentElement.scrollWidth <= innerWidth + 2; }));
  ck('phone: each line shows its description and the % boxes without sideways scroll', await p.evaluate(() => { const tr = document.querySelector('tr[data-line]'); const i = tr.querySelector('input'); const r = i.getBoundingClientRect(); return r.right <= innerWidth && tr.querySelector('.ds').getBoundingClientRect().width > 200; }));
  ck('no page errors', !errs.length, errs);
  await br.close();
  console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
