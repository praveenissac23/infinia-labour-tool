// Petty cash in three boxes - Site, PRO, Office - each behind its own
// right. The store keeper sees only Site (with the old lines), the PRO
// only PRO, the chief accountant only Office; nobody can read or change
// another box through the address or the API; admin sees all three,
// each with its own balance and paper; the Access page offers the three.
// Needs logins: amaltest (store,storekeeper - given Site by the upgrade),
// protest (petty_pro), acctest (petty_office).
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const login = async (u, pw, url = '/?p=accounts#petty') => {
    const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + url); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500); return p;
  };
  const subs = p => p.evaluate(() => [...document.querySelectorAll('.pg-subtab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  const api = (p, u, m, body) => p.evaluate(async ([u, m, body]) => { try { return { ok: 1, d: await apiCall(u, m ? { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined) }; } catch (e) { return { ok: 0, status: e.status, msg: String(e.message || e) }; } }, [u, m, body]);
  const add = async (p, kind, desc, amt) => {
    await p.click(`#screen-pettycash .pc-kind button[data-k="${kind}"]`); await p.fill('#pc-desc', desc); await p.fill('#pc-sup', 'Test'); await p.fill('#pc-amt', String(amt));
    await p.click('#pc-save'); await p.waitForTimeout(1000);
  };
  const today = new Date(Date.now() + 4 * 3600e3).toISOString().slice(0, 10);

  // Store keeper: Site only, and the old register lines are in it.
  const s = await login('amaltest', 'amal12345');
  const sSubs = await subs(s);
  ck('store keeper: Petty cash shows only the Site box', !sSubs.some(x => /PRO|Office/.test(x)), sSubs);
  ck('the heading says Site petty cash', (await s.locator('#pc-heading').textContent()) === 'Site petty cash');
  await add(s, 'received', 'Cash for site', 1000); await add(s, 'paid', 'Nails', 100);
  ck('site balance 900 after his two lines', (await s.evaluate(() => PC.closing)) - (await s.evaluate(() => PC.opening)) === 900, await s.evaluate(() => PC.closing));
  const sp = await api(s, '/store/petty-cash?book=pro');
  ck('asking for the PRO box by address is refused', !sp.ok && sp.status === 403, sp);
  const so = await api(s, '/store/petty-cash?book=office');
  ck('asking for the Office box is refused', !so.ok && so.status === 403, so);
  const sneak = await api(s, '/store/petty-cash', 'POST', { book: 'pro', date: today, description: 'x', paid: 5 });
  ck('he cannot slip a line into the PRO box', !sneak.ok && sneak.status === 403, sneak);
  await s.goto(B + '/?p=accounts#petty:pro'); await s.waitForTimeout(3000);
  ck('opening #petty:pro still shows him Site', (await s.locator('#pc-heading').textContent()) === 'Site petty cash');
  await s.screenshot({ path: SH + 'petty-books-site.png' });

  // PRO: PRO only.
  const r = await login('protest', 'pro12345');
  ck('PRO: Petty cash opens on the PRO box', (await r.locator('#pc-heading').textContent()) === 'PRO petty cash', await r.locator('#pc-heading').textContent());
  ck('PRO: no Site or Office tab', !(await subs(r)).some(x => /Site|Office/.test(x)), await subs(r));
  ck('PRO: no Stock or Purchasing tabs either', !(await r.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].filter(x => x.offsetParent).map(x => x.textContent))).some(x => /Stock|Purchasing/.test(x)));
  ck('PRO box starts empty - none of the site lines', (await r.evaluate(() => PC.rows.length)) === 0 && (await r.evaluate(() => PC.opening)) === 0);
  await add(r, 'received', 'Cash from office for visas', 5000); await add(r, 'paid', 'Visa renewal fee', 1250);
  ck('PRO balance 3,750', (await r.evaluate(() => PC.closing)) === 3750, await r.evaluate(() => PC.closing));
  const proId = await r.evaluate(() => PC.rows[0].id);
  const siteRead = await api(r, '/store/petty-cash?book=site');
  ck('PRO cannot read the Site box', !siteRead.ok && siteRead.status === 403);
  await r.screenshot({ path: SH + 'petty-books-pro.png' });

  // The store keeper cannot edit or remove the PRO's line by its number.
  const e1 = await api(s, `/store/petty-cash/${proId}`, 'PUT', { date: today, description: 'changed', paid: 1 });
  const e2 = await api(s, `/store/petty-cash/${proId}`, 'DELETE');
  ck('store keeper cannot edit or remove a PRO line by its number', !e1.ok && e1.status === 403 && !e2.ok && e2.status === 403, [e1, e2]);

  // Chief accountant: Office only.
  const a = await login('acctest', 'acc12345');
  ck('accountant: opens on Office petty cash', (await a.locator('#pc-heading').textContent()) === 'Office petty cash');
  await add(a, 'received', 'Opening float', 3000); await add(a, 'paid', 'Courier', 80);
  ck('Office balance 2,920', (await a.evaluate(() => PC.closing)) === 2920);
  ck('accountant cannot read PRO', (await api(a, '/store/petty-cash?book=pro')).status === 403);

  // Admin: all three, separate balances, papers titled per box.
  const ad = await login('admin', 'changeme123');
  const aSubs = await subs(ad);
  ck('admin sees Site, PRO and Office', ['Site', 'PRO', 'Office'].every(x => aSubs.includes(x)), aSubs);
  const bal = {};
  for (const bk of ['site', 'pro', 'office']) bal[bk] = (await api(ad, `/store/petty-cash?book=${bk}`)).d.closing;
  ck('each box keeps its own balance (PRO 3,750, Office 2,920)', bal.pro === 3750 && bal.office === 2920 && bal.site !== bal.pro, bal);
  await ad.evaluate(() => pgSub('pro')); await ad.waitForTimeout(1500);
  ck('admin clicking PRO shows the PRO lines', (await ad.locator('#pc-heading').textContent()) === 'PRO petty cash' && await ad.evaluate(() => PC.rows.some(x => /Visa/.test(x.description))));
  await ad.screenshot({ path: SH + 'petty-books-admin.png' });
  const [pop] = await Promise.all([ad.waitForEvent('popup'), ad.evaluate(() => pcExport('view'))]);
  await pop.waitForLoadState(); await pop.waitForTimeout(700);
  ck('the PRO paper is titled PRO PETTY CASH REGISTER and shows 3,750', /PRO PETTY CASH REGISTER/.test(await pop.locator('.page').textContent()) && /3,750\.00/.test(await pop.locator('.page').textContent()));
  const pdfHref = await pop.locator('a:has-text("Download PDF")').getAttribute('href');
  ck('its PDF link is for the PRO box', /book=pro/.test(pdfHref), pdfHref);
  await pop.close();
  const roles = (await api(ad, '/permissions/roles')).d;
  const pg = roles.pages.find(x => x[0] === 'Accounts');
  ck('Access page: the three petty cash boxes are under Accounts', pg && ['petty_site', 'petty_pro', 'petty_office'].every(r => pg[1].includes(r)) && roles.labels.petty_pro === 'PRO petty cash', pg);
  for (const p of [s, r, a, ad]) ck('no script errors', p.errs.length === 0, p.errs);
  console.log(bad ? `${bad} FAILED` : 'EACH PETTY CASH BOX IS ITS OWN');
  await b.close(); process.exit(bad ? 1 : 0);
})();
