// Authority fees on screen (28/11/2026): x removes the line at once with "Line removed - Undo", the SN is the app's,
// the sub-total and the side panel follow, and after a page refresh the removed lines stay gone; APP B on Sheets
// and the preview show no blank row between the fee and "Sub - Total from Current Bill" (Anoop's a-e).
//   python3 tests/make_ipa_fee_spares.py /tmp/claude-0/bills/fee-spares.xlsx ; BASE=http://127.0.0.1:8032 node tests/bill_fee_remove_ui_test.js
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/fee_', F = process.env.BILL || '/tmp/claude-0/bills/fee-spares.xlsx';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = (path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const P = (await api('/store/est/meta')).projects[0].id;
  const b64 = fs.readFileSync(F).toString('base64');
  await p.evaluate(async ([pid, b64]) => { const fd = new FormData(); fd.append('project_id', pid); fd.append('file', new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))]), 'fee-spares.xlsx');
    await fetch('/store/est/ipa/format', { method: 'POST', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') }, body: fd }); }, [P, b64]);
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, [P]); await p.reload(); await sleep(2500);
  await p.click('#ipa-new'); await sleep(2500);
  const bid = await p.evaluate(() => IPA.bill.id);
  // as Anoop had it: IPA 11, the DM fee on line 1, two empty lines under it
  let b = await api(`/store/est/ipa/bill/${bid}`);
  let fe = b.fees[0];
  const ln = fe.rows.find(x => !x.head);
  await api(`/store/est/ipa/bill/${bid}`, 'PUT', { set: { [fe.sheet]: { [ln.desc.key]: 'DM inspection fee', [ln.ref.key]: 'WIFBP2044806 dtd. 23/11/2026', [ln.amount.key]: 260 } } });
  b = await api(`/store/est/ipa/bill/${bid}`); fe = b.fees[0];
  const openFees = async () => { await p.evaluate(async id => { await openBill(id); }, bid); await sleep(1500); await p.click('#ipa-nav [data-step="fees"]'); await sleep(800); };
  await openFees();
  // the two empty lines put in while the bill is open (opening a bill now takes empty lines off by itself)
  await p.evaluate(async () => { for (let k = 0; k < 2; k++) { const t = IPA.bill.fees[0], last = t.rows[t.rows.length - 1];
    IPA.bill = await POST(`/store/est/ipa/bill/${IPA.bill.id}/rows`, { sheet: t.sheet, at: last.r + 1, n: 1, like: last.r }); } drawBill(); }); await sleep(800);
  const rowsNow = () => p.$$eval('#ipa-main table.ipa-pay tbody tr:not(.old):not(.tot)', trs => trs.map(tr => tr.classList.contains('hd') ? 'H:' + tr.querySelector('input').value : [...tr.cells].slice(0, 4).map(td => { const i = td.querySelector('input'); return (i ? i.value : td.textContent).trim(); }).join('|')));
  const before = await rowsNow();
  const HEAD = (before[0] || '').slice(2), HR = new RegExp('^\\s*' + HEAD + '\\s*$');   // this bill's heading ("IPA 11")
  ck(`set-up on screen: ${HEAD}, 1 DM inspection fee 260.00, two empty lines`, before.length === 4 && /^H:IPA \d+$/.test(before[0]) && /^1\|DM inspection fee\|WIFBP2044806.*\|260\.00$/.test(before[1]) && before[2] === '|||' && before[3] === '|||', before);
  ck('SN is not a box to type in', !(await p.$('#ipa-main input[data-c="sn"]')));
  await p.screenshot({ path: SH + 'a0_before.png' });
  // a) x on both empty lines
  for (let k = 0; k < 2; k++) {
    const xs = await p.$$('#ipa-main table.ipa-pay tbody tr:not(.old):not(.tot):not(.hd) [data-clear]');
    await xs[xs.length - 1].click(); await sleep(1200);
    if (k === 0) { const t = await p.textContent('.toast').catch(() => ''); ck('a) the toast reads "Line removed" with Undo', /Line removed/.test(t) && /Undo/.test(t), t); await p.screenshot({ path: SH + 'a1_toast.png' }); }
  }
  let now = await rowsNow();
  ck('a) only line 1 is left', now.length === 2 && /^1\|DM inspection fee/.test(now[1]), now);
  ck('a) sub-total this bill 260.00', /260\.00/.test(await p.textContent('#ipa-main tr.tot:not(.old)')));
  await p.screenshot({ path: SH + 'a2_after.png' });
  // b) F5
  await p.reload(); await sleep(2500); await openFees();
  now = await rowsNow();
  ck('b) after F5: still only line 1', now.length === 2 && /^1\|DM inspection fee/.test(now[1]), now);
  await p.screenshot({ path: SH + 'b_refresh.png' });
  // c) Sheets -> APP B
  await p.click('#ipa-nav [data-step="sheets"]'); await sleep(800);
  const tabs = await p.$$('[data-sheet], .ipa-tab, .ipa-sheets button');
  await p.evaluate(async () => { const s = IPA.bill.sheets.find(x => x.name === 'APP B'); IPA.sheet = s.i; drawBill(); }); await sleep(1800);
  const sheetRows = await p.$$eval('#ipa-sheet tr', trs => trs.map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.trim()).filter(Boolean).join(' | ')).filter(Boolean));
  const i11 = sheetRows.findIndex(r => HR.test(r));
  const seg = sheetRows.slice(i11, i11 + 3);
  ck('c) Sheets APP B: IPA 11, then 1 DM inspection fee ... 260.00, then Sub - Total from Current Bill 260.00', i11 >= 0 && /^1 \| DM inspection fee .*260\.00$/.test(seg[1]) && /Sub - Total from Current Bill.*260\.00/.test(seg[2]), sheetRows.slice(Math.max(0, i11 - 1), i11 + 4));
  const gap = await p.evaluate(h => { const trs = [...document.querySelectorAll('#ipa-sheet tr')]; const a = trs.findIndex(t => t.textContent.trim() === h); const z = trs.findIndex(t => /Sub - Total from Current Bill/.test(t.textContent)); return trs.slice(a, z + 1).filter(t => !t.textContent.trim()).length; }, HEAD);
  ck('c) no blank rows between them', gap === 0, gap);
  await (await p.$('#ipa-sheet')).screenshot({ path: SH + 'c_sheet.png' });
  // d) three filled lines, the 2nd deleted
  await p.click('#ipa-nav [data-step="fees"]'); await sleep(800);
  for (const [d, r, a] of [['DEWA meter fee', 'DEWA/M/5521', '410.25'], ['Trakhees permit renewal for the boundary wall and gate', 'TRK-2026-7781', '1150']]) {
    await p.click('#ipa-main [data-addfee]'); await sleep(1500);
    const tr = (await p.$$('#ipa-main table.ipa-pay tbody tr:not(.old):not(.tot):not(.hd)')).pop();
    await (await tr.$('input[data-c="desc"]')).fill(d); await (await tr.$('input[data-c="desc"]')).press('Tab'); await sleep(900);
    const tr2 = (await p.$$('#ipa-main table.ipa-pay tbody tr:not(.old):not(.tot):not(.hd)')).pop();
    await (await tr2.$('input[data-c="ref"]')).fill(r); await (await tr2.$('input[data-c="ref"]')).press('Tab'); await sleep(900);
    const tr3 = (await p.$$('#ipa-main table.ipa-pay tbody tr:not(.old):not(.tot):not(.hd)')).pop();
    await (await tr3.$('input[data-c="amount"]')).fill(a); await (await tr3.$('input[data-c="amount"]')).press('Enter'); await sleep(1500);
  }
  now = await rowsNow();
  ck('d) three lines: SN 1, 2, 3 and sub-total 1,820.25', now.length === 4 && now.slice(1).map(x => x.split('|')[0]).join() === '1,2,3' && /1,820\.25/.test(await p.textContent('#ipa-main tr.tot:not(.old)')), now);
  const side0 = await p.textContent('#ipa-nav');
  ck('d) the side panel reads this bill 1,820.25', /this bill 1,820\.25/.test(side0), side0.slice(0, 300));
  await p.screenshot({ path: SH + 'd0_three.png' });
  const xs = await p.$$('#ipa-main table.ipa-pay tbody tr:not(.old):not(.tot):not(.hd) [data-clear]');
  await xs[1].click(); await sleep(1500);
  now = await rowsNow();
  ck('d) the 2nd deleted: SN 1, 2 - DM and Trakhees', now.length === 3 && /^1\|DM inspection fee/.test(now[1]) && /^2\|Trakhees/.test(now[2]), now);
  ck('d) sub-total 1,410.00 and the side panel follows', /1,410\.00/.test(await p.textContent('#ipa-main tr.tot:not(.old)')) && /this bill 1,410\.00/.test(await p.textContent('#ipa-nav')));
  await p.screenshot({ path: SH + 'd1_deleted.png' });
  await p.reload(); await sleep(2500); await openFees();
  now = await rowsNow();
  ck('d) after F5: SN 1, 2 and 1,410.00', now.length === 3 && now.slice(1).map(x => x.split('|')[0]).join() === '1,2' && /1,410\.00/.test(await p.textContent('#ipa-main tr.tot:not(.old)')), now);
  await p.screenshot({ path: SH + 'd2_refresh.png' });
  // Undo from the toast brings a removed line back
  const xs2 = await p.$$('#ipa-main table.ipa-pay tbody tr:not(.old):not(.tot):not(.hd) [data-clear]');
  await xs2[1].click(); await sleep(1300);
  await p.click('.toast [data-u]'); await sleep(2000);
  await p.click('#ipa-nav [data-step="fees"]').catch(() => {}); await sleep(800);
  now = await rowsNow();
  ck('Undo on the toast: the line is back', now.length === 3 && /^2\|Trakhees/.test(now[2]), now);
  // e) the preview (what the PDF prints)
  const tok = (await api('/auth/download-token', 'POST')).token;
  const pv = await ctx.newPage(); await pv.goto(`${B}/export/est/ipa/${bid}?token=${tok}&format=preview`); await sleep(2500);
  const pvRows = await pv.$$eval('tr', trs => trs.map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.trim()).filter(Boolean).join(' | ')).filter(Boolean));
  const j = pvRows.findIndex(r => HR.test(r));
  ck('e) preview APP B: IPA 11 / 1 DM 260.00 / 2 Trakhees 1,150.00 / Sub - Total 1,410.00', /^1 \| DM inspection fee.*260\.00$/.test(pvRows[j + 1]) && /^2 \| Trakhees.*1,150\.00$/.test(pvRows[j + 2]) && /Sub - Total from Current Bill.*1,410\.00/.test(pvRows[j + 3]), pvRows.slice(j, j + 4));
  const el = await pv.$(`section.pg:has-text("APPENDIX - B")`); if (el) await el.screenshot({ path: SH + 'e_preview.png' }); else await pv.screenshot({ path: SH + 'e_preview.png', fullPage: true });
  ck('no script errors', !errs.length, errs);
  await br.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
