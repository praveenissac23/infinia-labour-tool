// Naveen's and Praveen's petty cash: two more boxes under Accounts >
// Petty cash, for admin and the chief accountant only. Kept as the
// directors' own sheets are: DR (what he paid for the company) before
// CR (what was paid back to him), balance = what the company owes him.
// Needs a database with the two sheets loaded (load_director_petty_cash.py)
// and logins chiefacc (given both by the upgrade), protest, keeper2.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const login = async (u, pw, url = '/?p=accounts#petty', vp = { width: 1440, height: 900 }) => {
    const p = await (await b.newContext({ viewport: vp, isMobile: vp.width < 600, hasTouch: vp.width < 600 })).newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + url); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500); return p;
  };
  const subs = p => p.evaluate(() => [...document.querySelectorAll('.pg-subtab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  const clickSub = async (p, label) => { await p.locator('.pg-subtab', { hasText: new RegExp('^' + label + '$') }).first().click(); await p.waitForTimeout(1500); };
  const heads = p => p.evaluate(() => [...document.querySelectorAll('#pc-head-row th')].map(x => x.textContent.trim()));
  const stats = p => p.evaluate(() => [...document.querySelectorAll('#pc-stats .pc-stat')].map(x => x.querySelector('span').textContent + ': ' + x.querySelector('b').textContent));
  const month = async (p, m) => { await p.fill('#pc-month', m); await p.dispatchEvent('#pc-month', 'change'); await p.waitForTimeout(1200); };
  const api = (p, u) => p.evaluate(async u => { try { return { ok: 1, d: await apiCall(u) }; } catch (e) { return { ok: 0, status: e.status }; } }, u);

  // Chief accountant: Office, Naveen, Praveen - not the site's or PRO's box.
  const c = await login('chiefacc', 'chief12345');
  const cs = await subs(c);
  ck('chief accountant: Petty cash shows Office, Naveen, Praveen', ['Office', 'Naveen', 'Praveen'].every(x => cs.includes(x)) && !cs.includes('Site') && !cs.includes('PRO'), cs);
  await clickSub(c, 'Naveen');
  ck('heading: Naveen petty cash', (await c.locator('#pc-heading').textContent()) === 'Naveen petty cash');
  ck('the address remembers the Naveen box', (await c.evaluate(() => location.hash)) === '#petty:naveen', await c.evaluate(() => location.hash));
  const h = await heads(c);
  ck('columns read as his sheet: no supplier column, Project, DR before CR, then balance due', h.length === 7 && h[2] === 'Project' && /^DR - Paid by Naveen/.test(h[3]) && /^CR - Repaid/.test(h[4]) && /^Balance due/.test(h[5]), h);
  ck('the Paid to / Ref box is gone from the form', !(await c.locator('#pc-sup-f').isVisible()));
  ck('form buttons say Paid by Naveen / Repaid to Naveen', (await c.evaluate(() => [...document.querySelectorAll('#pc-kind button')].map(x => x.textContent).join('|'))) === 'Paid by Naveen|Repaid to Naveen');
  ck('form site box is called Project', (await c.locator('#pc-form .pc-site span').textContent()) === 'Project');
  await month(c, '2026-09');
  let st = await stats(c);
  ck('Sep 2026: due to Naveen 20,253.65 (the sheet)', st[3] === 'Due to Naveen: 20,253.65', st);
  ck('stats order: brought forward, paid by, repaid, due', /^Brought forward: 21,753.65/.test(st[0]) && /^Paid by Naveen this month/.test(st[1]) && /^Repaid to Naveen this month: 1,500.00/.test(st[2]), st);
  const row = await c.evaluate(() => [...document.querySelectorAll('#pc-body tr')][1].innerText);
  ck('a repayment sits in the CR column', /Paid to Naveen Sir/.test(row) && /\t1,500.00\t20,253.65/.test(row), row);
  await month(c, '2023-09');
  ck('Sep 2023 closes at 233,320.71 as on his sheet', (await c.evaluate(() => PC.closing)) === 233320.71, await c.evaluate(() => PC.closing));
  await month(c, '2024-03');
  const proj = await c.evaluate(() => [...document.querySelectorAll('#pc-body tr td:nth-child(3)')].map(x => x.textContent).filter(Boolean));
  ck('project numbers from the sheet show', proj.includes('906'), proj);
  await c.screenshot({ path: SH + 'petty-naveen.png', fullPage: false });

  // Add, edit, remove a line in the Naveen box.
  await month(c, '2026-10');
  const today = new Date(Date.now() + 4 * 3600e3).toISOString().slice(0, 10);
  const before = await c.evaluate(() => PC.closing);
  await c.click('#pc-kind button[data-k="paid"]'); await c.fill('#pc-date', today); await c.fill('#pc-desc', 'Etisalat bill test');
  await c.selectOption('#pc-site', '906'); await c.fill('#pc-amt', '250'); await c.click('#pc-save'); await c.waitForTimeout(1200);
  ck('paid by Naveen 250 raises what is due by 250', Math.round(((await c.evaluate(() => PC.closing)) - before) * 100) === 25000, [before, await c.evaluate(() => PC.closing)]);
  ck('the status says Due to Naveen', /Due to Naveen: /.test(await c.locator('#pc-status').textContent()), await c.locator('#pc-status').textContent());
  const id = await c.evaluate(() => PC.rows.find(r => r.description === 'Etisalat bill test').id);
  await c.evaluate(id => pcEdit(id), id);
  ck('edit opens with Paid by Naveen and project 906', (await c.inputValue('#pc-site')) === '906' && (await c.evaluate(() => PC_KIND)) === 'paid');
  await c.click('#pc-kind button[data-k="received"]'); await c.fill('#pc-amt', '1000'); await c.click('#pc-save'); await c.waitForTimeout(1200);
  ck('changed to repaid 1,000: due falls by 1,000', Math.round(((await c.evaluate(() => PC.closing)) - before) * 100) === -100000, await c.evaluate(() => PC.closing));
  await c.evaluate(id => { pcDelete(id); }, id); await c.waitForTimeout(500);
  const ask = await c.locator('.hr-ask-msg').textContent();
  ck('remove asks first, naming the Naveen box', /from Naveen petty cash\?$/.test(ask), ask);
  await c.click('.hr-ask [data-a="yes"]'); await c.waitForTimeout(1200);
  ck('removed: back to where it was', (await c.evaluate(() => PC.closing)) === before, await c.evaluate(() => PC.closing));

  // Praveen.
  await clickSub(c, 'Praveen');
  await month(c, '2024-05');
  ck('Praveen: May 2024 closes at 6,210.50 as on his sheet', (await c.evaluate(() => PC.closing)) === 6210.5 && (await heads(c))[3].startsWith('DR - Paid by Praveen'), [await c.evaluate(() => PC.closing), await heads(c)]);
  await month(c, '2026-09');
  ck('Praveen: Sep 2026 due 95,302.06', (await stats(c))[3] === 'Due to Praveen: 95,302.06', await stats(c));

  // Back to the office box: its own words again.
  await clickSub(c, 'Office');
  const oh = await heads(c);
  ck('Office box: Supplier column back, Received / Paid / Balance in hand again', oh.length === 8 && /^Supplier/.test(oh[2]) && /^Received/.test(oh[4]) && /^Paid/.test(oh[5]) && (await stats(c))[3].startsWith('Balance in hand') &&
     (await c.evaluate(() => [...document.querySelectorAll('#pc-kind button')].map(x => x.textContent).join('|'))) === 'Bill paid|Cash received', [oh, await stats(c)]);

  // The papers.
  await clickSub(c, 'Naveen'); await month(c, '2026-07');
  const papers = await c.evaluate(async () => {
    if (!cachedDownloadToken) await refreshDownloadToken();
    const t = encodeURIComponent(cachedDownloadToken), base = `${API}/export/store/petty-cash`;
    const v = await (await fetch(`${base}/view?month=2026-07&book=naveen&token=${t}`)).text();
    const p = await fetch(`${base}?month=2026-07&book=naveen&format=pdf&token=${t}`);
    const x = await fetch(`${base}?month=2026-07&book=naveen&format=excel&token=${t}`);
    return { v, pdf: p.status + ' ' + p.headers.get('content-type') + ' ' + (await p.arrayBuffer()).byteLength,
             xl: x.status + ' ' + x.headers.get('content-disposition') };
  });
  ck('preview: NAVEEN PETTY CASH REGISTER with DR / CR columns and Due to Naveen', /NAVEEN PETTY CASH REGISTER/.test(papers.v) && /Project<\/th><th class="n">DR - Paid by Naveen \(AED\)<\/th><th class="n">CR - Repaid to Naveen/.test(papers.v) && /Due to Naveen<\/span><b>-8,246.35/.test(papers.v) && /preview-bar|pv-bar|Download PDF/.test(papers.v), papers.v.slice(0, 300));
  ck('PDF downloads', /^200 application\/pdf \d{4,}/.test(papers.pdf), papers.pdf);
  ck('Excel downloads as Naveen_petty_cash_2026-07.xlsx', /^200 .*Naveen_petty_cash_2026-07\.xlsx/.test(papers.xl), papers.xl);
  ck('no script errors (chief accountant)', !c.errs.length, c.errs);

  // Nobody else: PRO and the store keeper do not see or reach them.
  for (const [u, pw] of [['protest', 'pro12345'], ['keeper2', 'keep12345']]) {
    const p = await login(u, pw, '/?p=accounts#petty:naveen');
    const ps = await subs(p);
    ck(`${u}: no Naveen or Praveen tab`, !ps.includes('Naveen') && !ps.includes('Praveen'), ps);
    ck(`${u}: #petty:naveen does not open Naveen's box`, !/Naveen|Praveen/.test(await p.locator('#pc-heading').textContent()), await p.locator('#pc-heading').textContent());
    const r1 = await api(p, '/store/petty-cash?book=naveen'), r2 = await api(p, '/store/petty-cash?book=praveen');
    ck(`${u}: the API refuses both`, r1.status === 403 && r2.status === 403, [r1, r2]);
    ck(`${u}: no script errors`, !p.errs.length, p.errs);
  }

  // Admin: all five boxes.
  const a = await login('admin', 'changeme123');
  ck('admin: Site, PRO, Office, Naveen, Praveen', JSON.stringify((await subs(a)).filter(x => /^(Site|PRO|Office|Naveen|Praveen)$/.test(x))) === '["Site","PRO","Office","Naveen","Praveen"]', await subs(a));

  // Phone.
  const m = await login('chiefacc', 'chief12345', '/?p=accounts#petty:naveen', { width: 390, height: 844 });
  await m.waitForTimeout(800);
  ck('phone: opens straight on the Naveen box', (await m.locator('#pc-heading').textContent()) === 'Naveen petty cash');
  ck('phone: no sideways scroll on the page', await m.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), await m.evaluate(() => [document.documentElement.scrollWidth, innerWidth]));
  await m.screenshot({ path: SH + 'petty-naveen-phone.png' });
  ck('phone: no script errors', !m.errs.length, m.errs);

  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASSED');
  process.exit(bad ? 1 : 0);
})();
