// PDCs: what is in the form is always the cheque that was clicked - from
// the cheque list, from a figure on the monthly grid, from a payee name -
// and the list, the grid and the form never disagree. Real-data copy.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://127.0.0.1:8032/?p=expiry#expiry:pdc'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(4000);
  const form = () => p.evaluate(() => ({ title: document.getElementById('pdc-form-title').textContent, payee: document.getElementById('pdc-payee').value, amt: +document.getElementById('pdc-amt').value,
    notes: document.getElementById('pdc-notes').value, no: document.getElementById('pdc-no').value, date: document.getElementById('pdc-date').value, edit: PDC_EDIT }));
  // ---- every cheque in the list, clicked, fills the form with itself --------
  await p.evaluate(() => { pdcView('list'); document.getElementById('pdc-filter').value = 'all'; document.getElementById('pdc-search').value = ''; pdcDrawList(); });
  const rows = await p.evaluate(() => PDC.rows.map(r => ({ id: r.id, payee: r.payee, amount: r.amount, notes: r.notes, no: r.cheque_no, date: r.date_tbc ? '' : r.date })));
  let wrong = [];
  for (let i = 0; i < rows.length; i++) {
    await p.evaluate(i => { document.querySelectorAll('#pdc-lbody tr')[i].click(); }, i);
    const f = await form();
    const r = rows.find(x => x.id === f.edit);
    const shown = await p.evaluate(i => document.querySelectorAll('#pdc-lbody tr')[i].children[1].textContent.trim(), i);
    if (!r || f.payee !== r.payee || shown !== r.payee || Math.abs(f.amt - r.amount) > .005 || f.notes !== r.notes || f.no !== r.no || f.date !== r.date || !f.title.includes(r.payee)) wrong.push([i, shown, f, r]);
  }
  ck(`each of the ${rows.length} cheques in the list opens itself in the form`, !wrong.length, wrong.slice(0, 2));
  const edited = await p.evaluate(() => document.querySelectorAll('#pdc-lbody tr.edit').length);
  ck('the row being edited is the one marked', edited === 1, edited);
  // ---- clicking a payee on the grid while editing another closes that edit --
  await p.evaluate(() => pdcView('grid')); await p.waitForTimeout(300);
  const other = await p.evaluate(() => { const ed = PDC.rows.find(r => r.id === PDC_EDIT); return [...document.querySelectorAll('#pdc-gbody a.xl')].map(a => a.textContent).find(t => t !== ed.payee); });
  await p.click(`#pdc-gbody a.xl:text-is("${other}")`); await p.waitForTimeout(500);
  let f = await form();
  ck('grid payee -> list of that payee, form not left on another cheque', f.edit === null && f.title === 'Add a cheque' && (await p.inputValue('#pdc-search')) === other, f);
  const listed = await p.evaluate(() => [...new Set([...document.querySelectorAll('#pdc-lbody tr td:nth-child(2)')].map(td => td.textContent.trim()))]);
  ck('the list shows only that payee', listed.length === 1 && listed[0] === other, listed);
  // ---- a figure on the grid opens the cheque behind it ------------------------
  await p.evaluate(() => pdcView('grid')); await p.waitForTimeout(300);
  const cells = await p.evaluate(() => [...document.querySelectorAll('#pdc-gbody td.pdc-hit')].map((td, i) => ({ i, payee: td.parentElement.querySelector('td b').textContent.trim(), n: td.querySelectorAll('small.pdc-when').length, txt: td.firstChild ? td.firstChild.textContent.trim() : '' })));
  let bad2 = [];
  for (const c of cells.slice(0, 40)) {
    await p.evaluate(() => pdcView('grid'));
    await p.evaluate(i => document.querySelectorAll('#pdc-gbody td.pdc-hit')[i].click(), c.i); await p.waitForTimeout(80);
    f = await form();
    if (c.n === 1) { if (f.payee !== c.payee || Math.abs(f.amt - parseFloat(c.txt.replace(/,/g, ''))) > .005) bad2.push([c, f]); }
    else if (f.edit !== null || (await p.inputValue('#pdc-search')) !== c.payee) bad2.push([c, f]);
  }
  ck(`each grid figure (${Math.min(cells.length, 40)}) opens its own cheque, or that payee's list`, !bad2.length, bad2.slice(0, 2));
  // ---- a counter, or a search that hides the cheque, closes the edit -------
  await p.evaluate(() => { pdcView('list'); document.getElementById('pdc-search').value = ''; document.getElementById('pdc-filter').value = 'all'; pdcDrawList(); });
  await p.evaluate(() => document.querySelector('#pdc-lbody tr').click());
  await p.fill('#pdc-search', 'zzzz-nothing'); await p.dispatchEvent('#pdc-search', 'input'); await p.waitForTimeout(200);
  f = await form(); ck('a search that hides the cheque being edited closes the form', f.edit === null, f);
  await p.evaluate(() => { document.getElementById('pdc-search').value = ''; pdcDrawList(); document.querySelector('#pdc-lbody tr').click(); });
  await p.evaluate(() => pdcCard('nodate')); await p.waitForTimeout(200);
  f = await form(); ck('a counter card closes the edit too', f.edit === null, f);
  // ---- grid totals = list totals ----------------------------------------------
  const tot = await p.evaluate(() => ({ grid: PDC_GRID.grand, pending: PDC.summary.pending_amount }));
  ck('grid total equals the cheques to be paid', Math.abs(tot.grid - tot.pending) < 0.01, tot);
  ck('no script errors', !errs.length, errs);
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'PDC FORM, LIST AND GRID AGREE');
})();
