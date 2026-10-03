// Accounts page: only for a login with the accounts rights (and admin).
// Tax Invoice / Proforma Invoice tabs share one screen; the Register asks
// for its password every time it is opened and locks on leaving.
// Needs: chiefacc with pdc,settings,accounts_invoices,accounts_register; docsonly without.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const login = async (u, pw, url = '/?p=accounts') => {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 950 } });
    const p = await ctx.newPage(); p.ctx = ctx; p.reqs = []; ctx.on('request', r => p.reqs.push(r.url()));
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + url); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000); return p;
  };
  const menu = p => p.evaluate(() => [...document.querySelectorAll('.pg-side .pg-item')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  const tabs = p => p.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  const vis = (p, s) => p.locator(s).isVisible();

  // ---- the chief accountant -------------------------------------------
  const c = await login('chiefacc', 'chief12345');
  ck('chief: Accounts in the menu', (await menu(c)).some(x => x.startsWith('Accounts')), await menu(c));
  ck('chief: four tabs (Petty cash = Naveen / Praveen, Project payments), no Register on view', JSON.stringify(await tabs(c)) === JSON.stringify(['Tax Invoice', 'Proforma Invoice', 'Petty cash', 'Project payments']), await tabs(c));
  ck('tax invoice screen first', await vis(c, '#screen-invoices'));
  ck('title says Tax Invoices', (await c.textContent('#screen-title')).includes('Tax Invoices'));
  const yy = String(new Date().getFullYear()).slice(2);
  await c.fill('#inv-pno', '906'); await c.dispatchEvent('#inv-pno', 'change'); await c.waitForTimeout(700);
  ck('number fills in', (await c.inputValue('#inv-no')) === `IC/${yy}/906/01`, await c.inputValue('#inv-no'));
  await c.fill('#inv-client', 'Mr. Mohammed Ahmed Al Hammadi'); await c.fill('#inv-trn', '100234567800003');
  await c.fill('#inv-addr', 'Dubai, UAE'); await c.fill('#inv-project', '(B+G+1+R) Villa'); await c.fill('#inv-plot', '6457380');
  await c.fill('#inv-loc', 'Al Barsha South Third'); await c.fill('#inv-work', 'Phase 2 Works');
  const rows = c.locator('#inv-lines tr');
  await rows.nth(0).locator('input').nth(0).fill('Block work and plaster - 30% progress as per certified IPC 03');
  await rows.nth(0).locator('input').nth(1).fill('56,339');
  await c.click('text=+ Add line');
  await rows.nth(1).locator('input').nth(0).fill('Variation - additional boundary wall');
  await rows.nth(1).locator('input').nth(1).fill('11138');
  await c.waitForTimeout(200);
  ck('live total', (await c.textContent('#inv-tot')) === 'AED 70,850.85', await c.textContent('#inv-tot'));
  ck('live VAT', (await c.textContent('#inv-vat')) === '3,373.85', await c.textContent('#inv-vat'));
  await c.screenshot({ path: SH + 'acc_1_taxform.png', fullPage: true });
  const [pdf] = await Promise.all([c.ctx.waitForEvent('page'), c.click('#inv-save-pdf')]);
  await pdf.waitForURL(/export/, { timeout: 8000 }).catch(() => {});
  ck('PDF opened in new tab', /export\/accounts\/invoice\/\d+/.test(pdf.url()) || c.reqs.some(u => /export\/accounts\/invoice\/\d+\?token=/.test(u)), pdf.url()); await pdf.close();
  await c.waitForTimeout(800);
  ck('saved in list', (await c.textContent('#inv-body')).includes(`IC/${yy}/906/01`));
  ck('form ready for next number', (await c.inputValue('#inv-no')).endsWith('/01') === false || (await c.inputValue('#inv-no')) === `IC/${yy}/01`, await c.inputValue('#inv-no'));
  await c.fill('#inv-pno', '906'); await c.dispatchEvent('#inv-pno', 'change'); await c.waitForTimeout(700);
  ck('project no brings client back', (await c.inputValue('#inv-client')) === 'Mr. Mohammed Ahmed Al Hammadi', await c.inputValue('#inv-client'));
  ck('next number /02', (await c.inputValue('#inv-no')) === `IC/${yy}/906/02`, await c.inputValue('#inv-no'));
  await c.click('#inv-clear');
  await c.screenshot({ path: SH + 'acc_2_taxlist.png', fullPage: true });

  // ---- proforma tab, same screen ---------------------------------------
  await c.click('.pg-tab[data-tab="proforma"]'); await c.waitForTimeout(900);
  ck('proforma: title', (await c.textContent('#screen-title')).includes('Proforma'), await c.textContent('#screen-title'));
  ck('proforma: list empty', (await c.textContent('#inv-body')).includes('No proforma'), await c.textContent('#inv-body'));
  await c.fill('#inv-pno', '920'); await c.dispatchEvent('#inv-pno', 'change'); await c.waitForTimeout(700);
  ck('proforma number PI/', (await c.inputValue('#inv-no')) === `PI/${yy}/920/01`, await c.inputValue('#inv-no'));
  await c.fill('#inv-client', 'Mrs. Fatima Khalid'); await rows.nth(0).locator('input').nth(0).fill('Advance payment - 20% of contract value'); await rows.nth(0).locator('input').nth(1).fill('100000');
  await c.click('#inv-save'); await c.waitForTimeout(900);
  ck('proforma saved', (await c.textContent('#inv-body')).includes(`PI/${yy}/920/01`));
  // convert
  await c.click('#inv-body tr >> nth=0 >> .hr-menu-btn'); await c.click('text=Make tax invoice from this');
  await c.click('.hr-ask [data-a="yes"]'); await c.waitForTimeout(900);
  ck('converted note', (await c.textContent('#inv-status')).includes(`IC/${yy}/920/01`), await c.textContent('#inv-status'));
  ck('proforma tagged Invoiced', (await c.textContent('#inv-body')).includes('Invoiced'));
  await c.screenshot({ path: SH + 'acc_3_proforma.png', fullPage: true });
  await c.click('.pg-tab[data-tab="taxinv"]'); await c.waitForTimeout(900);
  ck('back on tax: both invoices', (await c.textContent('#inv-body')).includes(`IC/${yy}/920/01`) && (await c.textContent('#inv-body')).includes(`IC/${yy}/906/01`));

  // ---- help: invoice guides yes, nothing at all about the register -------
  const h = await c.evaluate(() => ({
    inv: HELP.search('tax invoice').map(g => g.id), pro: HELP.search('proforma').map(g => g.id),
    cash: ['cash register', 'register password', 'cash received', 'secret', 'cash book', 'register'].map(q => HELP.search(q).filter(g => (g.go && g.go.tab === 'register') || /^inv-/.test(g.id) && /register|secret/.test(q)).map(g => g.id)).flat(),
    any: HELP_GUIDES.some(g => (g.go && (g.go.tab === 'register')) || /cash ?reg|reg-|cashreg/i.test(JSON.stringify(g))),
    tips: Object.keys(window.HELP_TIPS || {}).some(k => /reg-/.test(k)) }));
  ck('help: tax invoice guide found', h.inv.includes('inv-tax'), h.inv);
  ck('help: proforma guides found', h.pro.includes('inv-proforma') && h.pro.includes('inv-convert'), h.pro);
  ck('help: searching the register finds nothing about it', !h.cash.length, h.cash);
  ck('help: no guide or tip points at the register', !h.any && !h.tips);
  // ---- the register ----------------------------------------------------
  // two clicks do nothing; three on the proforma heading do nothing
  await c.click('#inv-list-title', { clickCount: 2 }); await c.waitForTimeout(400);
  ck('two clicks: still hidden', !(await tabs(c)).includes('Register'));
  await c.click('.pg-tab[data-tab="proforma"]'); await c.waitForTimeout(700);
  await c.click('#inv-list-title', { clickCount: 3 }); await c.waitForTimeout(600);
  ck('three clicks on Proforma heading: still hidden', !(await tabs(c)).includes('Register'));
  await c.click('.pg-tab[data-tab="taxinv"]'); await c.waitForTimeout(700);
  await c.click('#screen-title', { clickCount: 3 }); await c.waitForTimeout(900);
  ck('three clicks on Tax Invoices heading: Register appears', (await tabs(c)).includes('Register'), await tabs(c));
  ck('register: locked on open', await vis(c, '#reg-lock') && !(await vis(c, '#reg-body')));
  await c.screenshot({ path: SH + 'acc_4_locked.png' });
  await c.fill('#reg-pass', 'infinia2022'); await c.click('#reg-open-btn'); await c.waitForTimeout(600);
  ck('wrong password message', (await c.textContent('#reg-lock-msg')).includes('Wrong password'), await c.textContent('#reg-lock-msg'));
  await c.fill('#reg-pass', 'Infinia2022!'); await c.press('#reg-pass', 'Enter'); await c.waitForTimeout(1000);
  ck('right password opens', await vis(c, '#reg-body') && !(await vis(c, '#reg-lock')));
  ck('chief: no change-password option', !(await vis(c, '#reg-pw-btn')));
  const add = async (kind, date, desc, amt, rem = '') => {
    await c.click(`#reg-kind button[data-k="${kind}"]`); await c.fill('#reg-date', date); await c.fill('#reg-desc', desc);
    await c.fill('#reg-amt', amt); if (rem) await c.fill('#reg-rem', rem); await c.click('#reg-save'); await c.waitForTimeout(600);
  };
  await add('received', '2026-09-01', 'Balance brought from cash file', '45,000');
  await add('received', '2026-09-14', 'Received from Mr. Ahmed - Plot 906', '20000');
  await add('paid', '2026-09-03', 'Paid to Al Hassai Building - cement', '3250.50', 'Site 906');
  await add('paid', '2026-09-18', 'Labour advance - Ramesh', '1500', 'F-712');
  ck('balance shown', (await c.textContent('#reg-stats')).includes('60,249.50'), await c.textContent('#reg-stats'));
  ck('two sides', (await c.locator('#reg-rec tr').count()) === 2 && (await c.locator('#reg-paid tr').count()) === 2);
  await c.screenshot({ path: SH + 'acc_5_register.png', fullPage: true });
  // edit by clicking
  await c.click('#reg-paid tr >> nth=1'); await c.waitForTimeout(400);
  ck('click row to edit', (await c.inputValue('#reg-desc')) === 'Labour advance - Ramesh' && (await c.textContent('#reg-save')) === 'Save changes');
  await c.click('#reg-cancel');
  // PDF export opens a blob
  const [rp] = await Promise.all([c.ctx.waitForEvent('page'), c.evaluate(() => regExport('view'))]);
  await rp.waitForURL(/^blob:/, { timeout: 8000 }).catch(() => {}); ck('register PDF opens from memory (blob)', rp.url().startsWith('blob:') || c.reqs.some(u => u.startsWith('blob:')), c.reqs.slice(-4));
  ck('register key fetched, not navigated', !(await rp.evaluate(() => location.href)).includes('rk=')); await rp.close();
  // leave and come back: locked again
  await c.click('.pg-tab[data-tab="taxinv"]'); await c.waitForTimeout(700);
  ck('key dropped on leaving', await c.evaluate(() => REG_KEY === ''));
  ck('Register tab gone again after leaving', !(await tabs(c)).includes('Register'), await tabs(c));
  await c.goto(B + '/?p=accounts#register'); await c.waitForTimeout(3500);
  ck('typing #register in the address does not open it', !(await vis(c, '#screen-cashreg')) && !(await tabs(c)).includes('Register'));
  await c.evaluate(() => { location.hash = 'register'; }); await c.waitForTimeout(800);
  ck('changing the hash does not open it', !(await vis(c, '#screen-cashreg')));
  await c.click('#inv-list-title', { clickCount: 3 }); await c.waitForTimeout(900);
  ck('asks again on return', await vis(c, '#reg-lock') && !(await vis(c, '#reg-body')));
  ck('no figures left in the page', !(await c.textContent('#screen-cashreg')).includes('60,249'));
  // leave to another page
  await c.fill('#reg-pass', 'Infinia2022!'); await c.press('#reg-pass', 'Enter'); await c.waitForTimeout(900);
  await c.evaluate(() => pgGo('expiry')); await c.waitForTimeout(900);
  await c.evaluate(() => pgGo('accounts')); await c.waitForTimeout(900);
  await c.click('#inv-form-title', { clickCount: 3 }); await c.waitForTimeout(900);
  ck('locked after visiting another page', await vis(c, '#reg-lock'));
  // the lock button
  await c.fill('#reg-pass', 'Infinia2022!'); await c.press('#reg-pass', 'Enter'); await c.waitForTimeout(900);
  await c.click('#reg-body button:has-text("Lock")'); ck('lock button', await vis(c, '#reg-lock'));
  // a reload asks again (key never stored)
  await c.reload(); await c.waitForTimeout(3500);
  await c.evaluate(() => pgGo('accounts')); await c.waitForTimeout(900);
  await c.click('#screen-title', { clickCount: 3 }); await c.waitForTimeout(900);
  ck('after reload: locked', await vis(c, '#reg-lock') && !(await vis(c, '#reg-body')));
  ck('no page errors (chief)', !c.errs.length, c.errs);

  // ---- admin sees change password ------------------------------------
  const a = await login('admin', 'changeme123', '/?p=accounts');
  ck('admin: Accounts in the menu', (await menu(a)).some(x => x.startsWith('Accounts')));
  await a.click('#screen-title', { clickCount: 3 }); await a.waitForTimeout(900);
  ck('admin: register locked on open', await vis(a, '#reg-lock'), await a.evaluate(() => document.querySelector('.screen.active').id));
  await a.fill('#reg-pass', 'Infinia2022!'); await a.press('#reg-pass', 'Enter'); await a.waitForTimeout(900);
  ck('admin: sees entries the chief made', (await a.textContent('#reg-rec')).includes('Mr. Ahmed'));
  ck('admin: change-password option', await a.evaluate(() => document.getElementById('reg-pw-btn').style.display !== 'none'));
  ck('no page errors (admin)', !a.errs.length, a.errs);

  // ---- invoices only: three clicks bring nothing up --------------------
  const io = await login('invonly', 'inv12345');
  ck('invoices-only: Accounts with two tabs', JSON.stringify(await tabs(io)) === JSON.stringify(['Tax Invoice', 'Proforma Invoice']), await tabs(io));
  await io.click('#screen-title', { clickCount: 3 }); await io.waitForTimeout(900);
  ck('invoices-only: three clicks do nothing', !(await tabs(io)).includes('Register') && !(await vis(io, '#screen-cashreg')));
  ck('no page errors (invoices-only)', !io.errs.length, io.errs);

  // ---- someone without the rights --------------------------------------
  const d = await login('docsonly', 'docs12345', '/?p=expiry');
  ck('documents login: no Accounts in menu', !(await menu(d)).some(x => x.startsWith('Accounts')), await menu(d));
  const r = await d.evaluate(async () => { try { await apiCall('/employees/accounts/invoices'); return 200; } catch (e) { return e.status; } });
  ck('documents login: invoices refused by server', r === 403, r);
  ck('documents login: no invoice guides', !(await d.evaluate(() => HELP.search('tax invoice').some(g => g.area === 'Accounts'))));
  await d.goto(B + '/?p=accounts#register'); await d.waitForTimeout(3000);
  ck('documents login: typed address does not show register', !(await vis(d, '#screen-cashreg')) && !(await vis(d, '#screen-invoices')));
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ACCOUNTS PAGE OK');
})();
