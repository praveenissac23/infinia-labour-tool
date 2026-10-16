// Activity monitor: long details read as headline + chips, long lists fold out.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(1200);
  await p.evaluate('switchScreen("activity")'); await p.waitForTimeout(2000);
  ck('real log renders', await p.locator('#activity-body tr').count() > 1);
  await p.evaluate(() => {
    const t = (h, m) => new Date(2026, 9, 16, h, m).toISOString(), pur = { group: 'purchasing', group_label: 'Purchasing', full_name: 'sreekanth', username: 'sreekanth' };
    currentActivityLog = [
      { ...pur, created_at: t(15, 0), label: 'Purchase order raised', details: 'IC/LPO/20260133 to Gemini Building Materials LLC (2 line(s)); added to the material list: ITM3606 NATIONAL SYNTHETIC ENAMEL 440 18LTR, ITM3607 NATIONAL LAQUER THINNER 4LTR' },
      { ...pur, created_at: t(14, 54), label: 'Purchase order raised', details: 'IC/LPO/20260132 to Gemini Building Materials LLC (13 line(s)); supplier list updated: contact, phone, email; added to the material list: ITM3593 GYPSUM BOARD RG 12.5MMX1200X2400 KNAUF, ITM3594 MAIN CHANNEL 38X12X0.5X3000 KNAUF, ITM3595 FURRING CHANNEL 35X22X68X0.5X3000 KNAUF, ITM3596 WALL ANGLE 25X25X0.5X3000MM KNAUF, ITM3597 GI HANGING WIRE 4KG, ITM3598 GI WIRE CLIPS, ITM3599 CEILINIG WEDGE ANCHOR 6X40 KNAUF, ITM3600 DRYWALL SCREW TN3.5X25MM KNAUF' },
      { ...pur, created_at: t(14, 27), label: 'Purchase order edited', details: 'IC/LPO/20260129 to Shafa Al Nahdah Ready Mixe Concrete Manufacturing LLC (3 line(s)), amount before tax 38,000.00 -> 38,000.00; added to the material list: ITM3554 CONCRETE C45/20 400KG(64%OPC+36%GGBS) SUPER STRUCTURE' },
      { ...pur, created_at: t(14, 10), label: 'Materials added', details: '72 material(s) added from LPO lines: ITM3448 Fischer Chemical Capsule RM 12mm -, ITM3449 Fischer Chemical Capsule RM 16mm, ITM3450 Fischer Chemical Bolt FTR 12x160, ITM3451 Fischer Chemical Bolt FTR 16x190, ITM3452 TILE CLEAR 5LTR CAN, ITM3453 6 Bosch BEL554MS0M Built In Microwave Oven, ITM3454 Bosch VBC011BR0M Built In Oven 90cm' },
      { created_at: t(13, 50), group: 'admin', group_label: 'Settings & access', full_name: 'Administrator', username: 'admin', label: 'Role saved', details: 'Chief Accountant: dashboard,attendance,masterdata,reports,combine,adjustments,livecard,store,requests,approvals,errorcheck,settings,hrpayroll,people_labour' },
      { created_at: t(13, 40), group: 'office', group_label: 'Accounts & cheques', full_name: 'Jomon', username: 'jomon', label: 'Petty cash edited', details: '#3074 pro book, Sarah Adil Work permit Cancellaction ( Completed ): date 2026-10-15 -> 2026-10-15, in 0.00 -> 0.00, out 114.21 -> 114.21' },
      { created_at: t(13, 2), group: 'signin', group_label: 'Sign-ins', full_name: 'Shafeeq', username: 'shafiq', label: 'Signed in', details: 'Chrome on Windows' },
    ];
    renderActivityLog();
  });
  await p.waitForTimeout(300);
  const row = i => p.locator('#activity-body tr:not(.act-day)').nth(i);
  ck('LPO number shown as headline', (await row(1).innerText()).includes('IC/LPO/20260132'));
  ck('long material list hidden at first', !(await row(1).locator('.act-items').isVisible()));
  ck('count chip "8 new materials"', (await row(1).innerText()).includes('8 new materials'));
  ck('supplier chip', (await row(1).innerText()).includes('Supplier details updated'));
  ck('single new material folds too', await row(2).locator('.act-more').count() === 1);
  ck('amount chip with arrow', (await row(2).innerText()).includes('38,000.00 (unchanged)'));
  ck('role screens fold into a list', (await row(4).innerText()).includes('14 items'));
  ck('short details unchanged', (await row(6).innerText()).includes('Chrome on Windows'));
  ck('petty edit stays as text', (await row(5).innerText()).includes('out 114.21'));
  await p.screenshot({ path: SH + 'act_final_1.png' });
  await row(1).locator('.act-more').click(); await p.waitForTimeout(200);
  ck('opens on click', await row(1).locator('.act-items').isVisible());
  ck('button says Hide', (await row(1).locator('.act-more').innerText()).startsWith('Hide'));
  await p.screenshot({ path: SH + 'act_final_2.png' });
  await row(1).locator('.act-more').click(); await p.waitForTimeout(200);
  ck('closes again', !(await row(1).locator('.act-items').isVisible()));
  await p.setViewportSize({ width: 390, height: 844 }); await p.waitForTimeout(300);
  ck('no sideways scroll on phone', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  ck('no page errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILURE(S)` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
