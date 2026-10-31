// Payroll > Office payroll > Gratuity > Final settlement (31 Oct 2026): salary already paid for the settlement's
// own days comes off by itself - PI003-like PX003, November's 7 days, 1,575.00 paid early on 28/10/2026. The line
// is on screen and on the preview; Remove asks for a reason (the app's own window, no browser prompt), the reason
// shows as a note and the net goes back up; Put back restores it. A payroll login without the approve right sees
// no Remove button.
// Run: seeds the database the server uses (DB, default /tmp/run_js.db) with tests/seed_settlement_paid.py, then
//      node tests/settlement_paid_ui_test.js   (serve_like_nginx.py on 8032, a copy of full.db)
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const path = require('path');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/shots/';
const DB = process.env.DB || '/tmp/run_js.db';
execSync(`python3 ${path.join(__dirname, 'seed_settlement_paid.py')}`, { cwd: path.join(__dirname, '..', 'app'),
  env: { ...process.env, DATABASE_URL: 'sqlite:///' + DB, INFINIA_NO_SCHED: '1', INFINIA_NO_PUSH: '1' }, stdio: 'ignore' });
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const open = async (user, pw) => {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + '/?p=payroll#hrpayroll'); await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
    await p.locator('#pg-sub .pg-subtab', { hasText: 'Gratuity' }).click(); await p.waitForTimeout(2000);
    await p.evaluate(() => { const s = document.getElementById('hr-grat-emp'); s.value = 'PX003'; s.dispatchEvent(new Event('change')); });
    await p.waitForTimeout(2500);
    return p;
  };
  const p = await open('admin', 'changeme123');
  const LBL = 'Less: salary already paid on 28/10/2026 (period 01/11/2026 – 07/11/2026)';
  const ded = await p.locator('.fs-sum table').nth(1).textContent();
  ck('screen: the Less line with 1,575.00 in Deductions', ded.includes(LBL) && /1,575\.00/.test(ded), ded);
  const net0 = (await p.locator('.fs-net b').textContent()).trim();
  ck('screen: net AED 0.00 (7 days paid, 7 days already paid)', net0 === 'AED 0.00', net0);
  ck('screen: says it is deducted automatically, with a Remove button', /deducted automatically/.test(await p.locator('.fs-paid').textContent())
     && await p.locator('.fs-paid button', { hasText: 'Remove' }).count() === 1);
  await p.locator('#hr-fs-card').scrollIntoViewIfNeeded(); await p.screenshot({ path: SH + 'fs-paid-1-line.png', fullPage: false });
  const [pop] = await Promise.all([p.waitForEvent('popup'), p.click('#hr-fs-card .exp-btns button:has-text("Preview")')]);
  await pop.waitForLoadState(); await pop.waitForTimeout(800);
  ck('preview: the same line and net', (await pop.locator('body').textContent()).includes(LBL) && (await pop.locator('.net b').textContent()).trim() === 'AED 0.00');
  await pop.screenshot({ path: SH + 'fs-paid-2-preview.png', fullPage: true }); await pop.close();

  // Remove: a reason box, not a browser prompt
  let prompted = false; p.on('dialog', d => { prompted = true; d.dismiss(); });
  await p.locator('.fs-paid button', { hasText: 'Remove' }).click(); await p.waitForTimeout(500);
  ck('Remove opens the app\'s reason window; the button stays off until a reason is typed',
     await p.locator('.hr-ask .hr-ask-why').count() === 1 && await p.locator('.hr-ask [data-a="yes"]').isDisabled());
  await p.fill('.hr-ask .hr-ask-why', 'Agreed with the MD - November paid as a bonus');
  await p.screenshot({ path: SH + 'fs-paid-3-reason.png' });
  await p.locator('.hr-ask [data-a="yes"]').click(); await p.waitForTimeout(2000);
  const net1 = (await p.locator('.fs-net b').textContent()).trim();
  ck('removed: the line is gone and the net is back up by 1,575.00', net1 === 'AED 1,575.00' && !(await p.locator('.fs-sum table').nth(1).textContent()).includes(LBL), net1);
  const notes = await p.locator('.fs-notes').textContent();
  ck('removed: the note names who and why', /not deducted - taken out by Administrator.*Agreed with the MD/.test(notes) || /taken out by .*Agreed with the MD/.test(notes), notes);
  ck('removed: the row says not deducted, with Put back', /not deducted/.test(await p.locator('.fs-paid').textContent())
     && await p.locator('.fs-paid button', { hasText: 'Put back' }).count() === 1);
  await p.screenshot({ path: SH + 'fs-paid-4-removed.png' });
  await p.locator('.fs-paid button', { hasText: 'Put back' }).click(); await p.waitForTimeout(400);
  await p.locator('.hr-ask [data-a="yes"]').click(); await p.waitForTimeout(2000);
  ck('put back: line and net AED 0.00 again', (await p.locator('.fs-net b').textContent()).trim() === 'AED 0.00');
  ck('no browser prompt used', !prompted);
  ck('no script errors (admin)', p.errs.length === 0, p.errs);

  const q = await open('sp_hr', 'pw12345');
  ck('payroll login without the approve right: line shown, no Remove', (await q.locator('.fs-sum table').nth(1).textContent()).includes(LBL)
     && await q.locator('.fs-paid button').count() === 0);
  ck('no script errors (payroll login)', q.errs.length === 0, q.errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await b.close(); process.exit(bad ? 1 : 0);
})();
