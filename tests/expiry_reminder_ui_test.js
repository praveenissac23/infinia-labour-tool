// Expiry Reminder at a glance: four counters (expired / 7 days / 30 days /
// missing), a click shows that list, the menu shows a red number, one
// line a day in the bell (a popup on first sign-in), daily email box.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message)); await p.addInitScript(() => { window.__popups = 1; });
  await p.goto(B + '/'); await p.fill('#login-username', 'docsonly'); await p.fill('#login-password', 'docs12345'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const toast = await p.evaluate(() => document.body.innerText.includes('Expiries:'));
  ck('on signing in, the day\'s expiry line pops up once', toast);
  const badge = await p.locator('.pg-item[data-page="expiry"] .pg-badge').textContent().catch(() => '');
  ck('the menu shows a red number beside Expiry Reminder', /^\d+$/.test(badge), badge);
  await p.screenshot({ path: SH + 'reminder-0-signin.png' });
  await p.click('#notif-overlay button:has-text("Open")').catch(() => {}); await p.waitForTimeout(2500);
  await p.click('.pg-side .pg-item[data-page="expiry"]'); await p.waitForTimeout(2500);
  const cards = await p.locator('.exp-card').allTextContents();
  ck('four counters: Expired, Due in 7 days, 8 to 30 days, Missing', cards.length === 4 && /Expired/.test(cards[0]) && /Missing/.test(cards[3]), cards);
  const s = await p.evaluate(() => EXP_SUM);
  const shown = await p.locator('#hr-doc-body tr').count();
  ck('it opens on what needs action (expired or due in 30 days), not everyone', await p.inputValue('#hr-doc-within') === '30' && shown < 20, shown);
  await p.screenshot({ path: SH + 'reminder-1-page.png' });
  await p.click('.exp-card[data-k="expired"]'); await p.waitForTimeout(500);
  ck(`"Expired" shows the ${s.expired} people with something expired`, (await p.locator('#hr-doc-body tr').count()) === s.expired);
  await p.click('.exp-card[data-k="missing"]'); await p.waitForTimeout(1500);
  const m = await p.locator('#hr-doc-body tr').count();
  ck(`"Missing documents" lists the ${s.missing} people with nothing on file`, m === s.missing, m);
  await p.screenshot({ path: SH + 'reminder-2-missing.png' });
  await p.locator('#hr-doc-body tr').first().click(); await p.waitForTimeout(200);
  ck('clicking a missing line puts his code in the form', (await p.inputValue('#hr-doc-emp')).length > 1);
  ck('the daily email box shows the saved addresses', /infinia\.ae/.test(await p.inputValue('#exp-mail-to')));
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'NOTHING SLIPS THROUGH');
  await b.close(); process.exit(bad ? 1 : 0);
})();
