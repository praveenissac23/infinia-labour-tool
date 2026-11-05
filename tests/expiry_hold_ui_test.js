// Expiry Reminder: "Not renewing" (5 Nov 2026) - the line stays on the page, greyed, on hold: no bell, no count, no
// morning mail, whatever its date. Renew now puts it back to normal.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/full.db 8560 tests/expiry_hold_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const SH = '/tmp/claude-0/ui2/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300)}`); };
(async () => {
  const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => { errs.push('dialog'); d.dismiss(); });
  await p.goto(B + '/'); await p.waitForTimeout(1500); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2000);
  await p.goto(B + '/?p=expiry'); await p.waitForTimeout(3500);
  const id = await p.evaluate(async () => { const d = n => { const t = new Date(); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
    const r = await apiCall('/employees/expiries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: 'Insurance', item: 'CAR INSURANCE OF 911', kind: 'Insurance', number: 'P/05/4022/2024/63', expires_on: d(-2) }) });
    return r.id; });
  const sum0 = await p.evaluate(async () => (await apiCall('/employees/expiry/summary')).company);
  await p.evaluate(() => { try { pgSub('company'); } catch (e) { hrDocMode('company'); } }); await p.waitForTimeout(2500);
  await p.fill('#hr-exp-search', 'CAR INSURANCE OF 911'); await p.evaluate(() => renderExpiries()); await p.waitForTimeout(300);
  const row = () => p.locator('#hr-exp-body tr', { hasText: 'CAR INSURANCE OF 911' });
  ck('the line offers Mark started, Not renewing and Close', /Mark started/.test(await row().textContent()) && /Not renewing/.test(await row().textContent()) && /Close/.test(await row().textContent()));
  await p.evaluate(() => { const b = document.getElementById('hr-exp-body'); b.scrollIntoView({ block: 'center' }); });
  await p.screenshot({ path: SH + 'exp_hold_before.png' });
  await row().locator('button', { hasText: 'Not renewing' }).click(); await p.waitForTimeout(1800);
  const t = await row().textContent();
  ck('on hold: still on the page, says Not renewing, offers Renew now', /Not renewing/.test(t) && /Renew now/.test(t) && !/Mark started/.test(t), t);
  ck('greyed out', await row().evaluate(tr => tr.classList.contains('exp-hold')));
  await p.screenshot({ path: SH + 'exp_hold_on.png' });
  const after = await p.evaluate(async () => ({ sum: (await apiCall('/employees/expiry/summary')).company, bell: ((await apiCall('/notifications')).notifications.find(x => x.kind === 'expiry') || {}).detail || '' }));
  ck('not counted any more (expired count down by one)', after.sum.expired === sum0.expired - 1, { before: sum0, after: after.sum });
  ck('no bell for it', !/CAR INSURANCE OF 911/.test(after.bell), after.bell);
  ck('still on file (not deleted)', await p.evaluate(async id => !!(await apiCall('/employees/expiries')).rows.find(x => x.id === id), id));
  await row().locator('button', { hasText: 'Renew now' }).click(); await p.waitForTimeout(1800);
  const t2 = await row().textContent();
  ck('Renew now: back to normal - Mark started / Not renewing again, counted again', /Mark started/.test(t2) && !/Renew now/.test(t2)
     && (await p.evaluate(async () => (await apiCall('/employees/expiry/summary')).company.expired)) === sum0.expired, t2);
  // All together tab shows it the same way
  await row().locator('button', { hasText: 'Not renewing' }).click(); await p.waitForTimeout(1500);
  await p.evaluate(() => { try { pgSub('all'); } catch (e) { hrDocMode('all'); } }); await p.waitForTimeout(2500);
  await p.fill('#exp-all-search', 'CAR INSURANCE OF 911'); await p.evaluate(() => renderAllDocs()); await p.waitForTimeout(300);
  const a = await p.locator('#exp-all-body tr', { hasText: 'CAR INSURANCE OF 911' }).textContent();
  ck('All together: the same - Not renewing, Renew now', /Not renewing/.test(a) && /Renew now/.test(a), a);
  await p.screenshot({ path: SH + 'exp_hold_all.png' });
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await b.close();
})();
