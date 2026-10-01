// On a phone: three taps on the Tax Invoices heading bring the Register up.
const { chromium, devices } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  for (const dev of ['iPhone 13', 'Pixel 7']) {
    const ctx = await b.newContext({ ...devices[dev] });
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'chiefacc'); await p.fill('#login-password', 'chief12345'); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
    const tabs = () => p.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
    ck(`${dev}: heading visible`, await p.locator('#screen-title').isVisible());
    if (dev === 'iPhone 13') await p.screenshot({ path: SH + 'acc_mobile_1.png' });
    for (const sel of ['#screen-title', '#inv-list-title']) {
      for (let i = 0; i < 3; i++) { await p.tap(sel); await p.waitForTimeout(250); }
      await p.waitForTimeout(900);
      ck(`${dev}: three taps on ${sel} bring the Register up`, (await tabs()).includes('Register') && await p.locator('#reg-lock').isVisible(), await tabs());
      if (dev === 'iPhone 13' && sel === '#screen-title') await p.screenshot({ path: SH + 'acc_mobile_2.png' });
      await p.tap('.pg-tab[data-tab="taxinv"]'); await p.waitForTimeout(900);
      ck(`${dev}: gone again after leaving`, !(await tabs()).includes('Register'));
    }
    // slow taps do nothing
    for (let i = 0; i < 3; i++) { await p.tap('#screen-title'); await p.waitForTimeout(900); }
    await p.waitForTimeout(500);
    ck(`${dev}: three slow taps do nothing`, !(await tabs()).includes('Register'));
    ck(`${dev}: no errors`, !errs.length, errs);
    await ctx.close();
  }
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'MOBILE TAPS OK');
})();
