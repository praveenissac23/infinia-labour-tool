// Bills > Sheets: the Excel-like ribbon - one band of tools (undo/redo, copy/paste, format painter, font, alignment, number, rows, cells), the formula line with the sheet picker and zoom.
//   BASE=http://127.0.0.1:8042 BID=<a draft bill id> node tests/bill_ribbon_ui_test.js
const { chromium } = require('playwright'); const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
(async () => { const b = await chromium.launch(); const B = process.env.BASE || 'http://127.0.0.1:8032';
  const ctx = await b.newContext({ viewport: { width: 1600, height: 900 } }); await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: B });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const BID = +(process.env.BID || 4);
  await p.evaluate(id => openBill(id, 'sheets'), BID); await sleep(3500);
  const st = k => p.$eval(`.sv-in td[data-k="${k}"]`, t => t.getAttribute('style') || '');
  const cell = k => p.$(`.sv-in td[data-k="${k}"]`);
  // pick a typed cell and a plain cell on the IPA sheet
  const ks = await p.$$eval('.sv-in td.ed[data-k]', x => x.map(t => t.dataset.k));
  ck('ribbon in one row at 1600px', (await p.$eval('.sv-bar', x => x.getBoundingClientRect().height)) < 45);
  ck('sheet picker, cell box, fx, zoom on one line', (await p.$eval('.sv-fbar', x => x.getBoundingClientRect().height)) < 45 && !!(await p.$('.sv-fbar .sv-pick')) && !!(await p.$('.sv-fbar .sv-zoom')));
  ck('no help line, no row bar taking space', !(await p.$('.ipa-sheets-help')) && !(await p.$('#sv-rows:not([style*="none"])')) );
  const k1 = ks[0]; await (await cell(k1)).click(); await sleep(300);
  const before = await st(k1);
  await p.click('#sv-fmt [data-fx="i"]'); await sleep(1500);
  ck('Italic from the ribbon', /italic/.test(await st(k1)), await st(k1));
  // undo from the ribbon pair
  await sleep(600); const uDis = await p.$eval('#sv-fmt .ipa-u', x => x.disabled);
  ck('ribbon Undo lit after a change', !uDis);
  await p.click('#sv-fmt .ipa-u'); await sleep(2000);
  ck('ribbon Undo puts it back', !/italic/.test(await st(k1)), await st(k1));
  // format painter: bold header cell -> a plain cell
  const head = await p.$$eval('.sv-in td[data-k]', x => { const t = x.find(t => /font-weight:\s*700/.test(t.getAttribute('style') || '')); return t ? t.dataset.k : null; });
  const plain = await p.$$eval('.sv-in td.ed[data-k]', x => { const t = x.find(t => !/font-weight:\s*700/.test(t.getAttribute('style') || '')); return t ? t.dataset.k : null; });
  ck('found a bold cell and a plain one', !!head && !!plain, [head, plain]);
  await (await cell(head)).click(); await sleep(200);
  await p.click('#sv-fmt [data-fx="paint"]'); await sleep(300);
  ck('painter button lit', await p.$eval('#sv-fmt [data-fx="paint"]', x => x.classList.contains('on')));
  await (await cell(plain)).click(); await sleep(2000);
  ck('painter gave the plain cell the bold look', /font-weight:\s*700/.test(await st(plain)), await st(plain));
  ck('painter off after use', !(await p.$eval('#sv-fmt [data-fx="paint"]', x => x.classList.contains('on'))));
  await p.keyboard.press('Control+z'); await sleep(2000);
  ck('Ctrl+Z takes the painted look off', !/font-weight:\s*700/.test(await st(plain)), await st(plain));
  // copy / paste with the ribbon buttons
  const src = await p.$$eval('.sv-in td.ed[data-k]', x => { const t = x.find(t => (t.dataset.raw || '') !== '' && !t.dataset.raw.startsWith('=') && isNaN(Number(t.dataset.raw))); return t ? [t.dataset.k, t.dataset.raw] : null; });
  const dst = await p.$$eval('.sv-in td.ed[data-k]', x => { const t = x.find(t => (t.dataset.raw || '') === ''); return t ? t.dataset.k : null; });
  if (src && dst) {
    await (await cell(src[0])).click(); await p.click('#sv-fmt [data-fx="copy"]'); await sleep(400);
    await (await cell(dst)).click(); await p.click('#sv-fmt [data-fx="paste"]'); await sleep(2000);
    ck('Copy / Paste buttons', (await p.$eval(`.sv-in td[data-k="${dst}"]`, t => t.dataset.raw)) === src[1], [src, dst]);
    await p.keyboard.press('Control+z'); await sleep(2000);
    ck('undo the paste', (await p.$eval(`.sv-in td[data-k="${dst}"]`, t => t.dataset.raw || '')) === '');
  } else ck('copy/paste cells found', false, [src, dst]);
  // rows: insert a line below the picked cell's row, hide it, show again, undo
  const nRows = async () => p.$$eval('.sv-in tr[data-r]', x => x.length);
  const n0 = await nRows(); await (await cell(k1)).click(); await sleep(200);
  await p.click('#sv-fmt [data-fx="rbelow"]'); await sleep(2200);
  if (await p.$('#m-save')) { ck('row below in a table opens the line form', true); await p.click('#m-cancel, .modal [data-close]').catch(() => {}); }
  else ck('Insert line below adds a row', (await nRows()) === n0 + 1, [n0, await nRows()]);
  await p.keyboard.press('Control+z'); await sleep(2200);
  ck('undo takes the new row off', (await nRows()) === n0, [n0, await nRows()]);
  await (await cell(k1)).click(); await p.click('#sv-fmt [data-fx="rhide"]'); await sleep(2200);
  ck('Hide line', (await nRows()) === n0 - 1 && !!(await p.$('[data-rw="show"]')), [n0, await nRows()]);
  await p.click('[data-rw="show"]'); await sleep(2200);
  ck('Show hidden lines', (await nRows()) === n0);
  // switch sheet with the picker in the formula line, the ribbon is there too
  const opts = await p.$$eval('.sv-pick option', x => x.map(o => o.value));
  await p.selectOption('.sv-pick', opts[1]); await sleep(2500);
  ck('another sheet opens with the same ribbon', !!(await p.$('#sv-fmt [data-fx="paint"]')) && (await p.$eval('.sv-pick', x => x.value)) === opts[1]);
  await p.screenshot({ path: '/tmp/claude-0/shots/rbf.png' });
  ck('no page errors', errs.length === 0, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await b.close(); process.exit(bad ? 1 : 0); })();
