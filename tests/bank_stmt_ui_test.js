// Accounts > Bank: upload an ADCB statement, see the counts, Bank ✓ on the
// matched entries, Enter fills the form from a bank line, Match... and
// 'No entry needed', layout at 1440 / 390.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/', FILE = '/tmp/claude-0/stmt/ADCB_Statement_Oct_2026.xlsx';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); return p;
}
const openBank = async p => { await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Bank'); t.click(); }); await p.waitForTimeout(2500);
  await p.evaluate(() => { document.getElementById('bk-month').value = '2026-10'; return bkLoad(); }); await p.waitForTimeout(1500); };
const tiles = p => p.evaluate(() => [...document.querySelectorAll('.bs-tile b')].map(x => +x.textContent));
(async () => {
  const b = await chromium.launch();
  const p = await login(b, 'shafiq', 'pass12345');
  await openBank(p);
  ck('before any statement: How it works shown', /How it works/.test(await p.locator('#bk-stmt').textContent()));
  // three entries typed in the portal
  const add = body => p.evaluate(async b => { try { return (await apiCall('/store/bank', { method: 'POST', body: JSON.stringify(b) })).id || 'ok'; } catch (e) { return errText(e); } }, body);
  const r1 = await add({ kind: 'vendor', date: '2026-10-02', party: 'Ghantoot Building Materials', mode: 'Bank Transfer', reference: 'PHUB726068648', amount: '23505.72' });
  const r2 = await add({ kind: 'customer', date: '2026-10-05', party: 'Emkaan Design', mode: 'Bank Transfer', reference: '', amount: '105000' });
  const r3 = await add({ kind: 'vendor', date: '2026-10-09', party: 'Casa Fiora FZE', mode: 'Bank Transfer', reference: 'PHUB555', amount: '3700' });
  ck('three entries saved', [r1, r2, r3].every(x => typeof x === 'number' || x === 'ok'), [r1, r2, r3]);
  await openBank(p);
  await p.setInputFiles('#bk-stmt input[type=file]', FILE); await p.waitForTimeout(2500);
  ck('upload message', /4 lines, 4 new.*2 matched/.test(await p.locator('#bk-status').textContent()), await p.locator('#bk-status').textContent());
  ck('tiles: 4 lines, 2 verified, 2 not entered, 1 entered not in bank', JSON.stringify(await tiles(p)) === '[4,2,2,1]', await tiles(p));
  ck('Bank ✓ on the two matched entries in the list', (await p.locator('#bk-body .zx-tag.zx-ok', { hasText: 'Bank ✓' }).count()) === 2);
  ck('red list shows the charge and DEWA, amber shows Casa Fiora', (await p.locator('.bs-list tr.bad').count()) === 2 && (await p.locator('.bs-list tr.warn').count()) === 1);
  await p.screenshot({ path: SH + 'bank_stmt_1440.png', fullPage: true });
  // Enter from a bank line: the form fills, saving matches it
  await p.locator('.bs-list tr.bad', { hasText: 'SERVICE CHARGES' }).locator('button', { hasText: 'Enter' }).click(); await p.waitForTimeout(600);
  ck('Enter fills the form as a bank charge with the amount', await p.evaluate(() => BK_KIND === 'charge' && document.getElementById('bk-amt').value === '52.50'));
  await p.click('#bk-save'); await p.waitForTimeout(2500);
  ck('after saving, it matches by itself: 3 verified', JSON.stringify(await tiles(p)) === '[4,3,1,1]', await tiles(p));
  // No entry needed with a reason
  await p.locator('.bs-list tr.bad', { hasText: 'DEWA' }).locator('button', { hasText: 'No entry needed' }).click(); await p.waitForTimeout(400);
  await p.click('.bs-m .btn-primary'); await p.waitForTimeout(400);
  ck('a reason is required', /why/i.test(await p.locator('#bs-msg').textContent()));
  await p.fill('#bs-why', 'Paid by director card - booked separately'); await p.screenshot({ path: SH + 'bank_stmt_ignore.png' });
  await p.click('.bs-m .btn-primary'); await p.waitForTimeout(1800);
  ck('set aside: nothing red left', (await tiles(p))[2] === 0, await tiles(p));
  // Match... with no candidate says so
  await p.click('.bs-tile >> nth=0'); await p.waitForTimeout(300);
  await p.locator('.bs-list tr.ign button.bs-x').click(); await p.waitForTimeout(1500);
  await p.locator('.bs-list tr.bad', { hasText: 'DEWA' }).locator('button', { hasText: 'Match' }).click(); await p.waitForTimeout(900);
  ck('Match... with nothing of that amount explains what to do', /No entry with exactly this amount/.test(await p.locator('.bs-m').textContent()));
  await p.screenshot({ path: SH + 'bank_stmt_match.png' });
  await p.click('.bs-m .btn-gray');
  // the same file again adds nothing
  await p.setInputFiles('#bk-stmt input[type=file]', FILE); await p.waitForTimeout(2500);
  ck('same file again: 0 new, 4 already in', /0 new, 4 already in/.test(await p.locator('#bk-status').textContent()), await p.locator('#bk-status').textContent());
  const lay = await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2);
  ck('layout 1440 clean', lay);
  ck('no page errors', !p.errs.length, p.errs);
  const m = await login(b, 'shafiq', 'pass12345', 390); await openBank(m);
  ck('phone: no sideways scroll', await m.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
  await m.screenshot({ path: SH + 'bank_stmt_390.png', fullPage: true });
  // Send to Zoho: the Link suppliers step (Zoho not connected on the copy -> button disabled but explained)
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await b.close();
})();
