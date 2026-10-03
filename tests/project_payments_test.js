// Accounts > Project payments: the project payment tracker.
// Admin and the chief accountant only; loaded once from the 02-Oct-2026
// sheet (34 scopes, contract 39,553,906.82, received 21,883,355.70);
// received / remaining / status worked out from the payments; two
// papers (Summary, With payment dates) as Preview, PDF and Excel.
// Needs logins chiefacc (given the right by the upgrade), protest, keeper2.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const login = async (u, pw, url = '/?p=accounts#projects', vp = { width: 1440, height: 900 }) => {
    const p = await (await b.newContext({ viewport: vp, isMobile: vp.width < 600, hasTouch: vp.width < 600 })).newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + url); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500); return p;
  };
  const api = (p, u, m, body) => p.evaluate(async ([u, m, body]) => { try { return { ok: 1, d: await apiCall(u, m ? { method: m, body: JSON.stringify(body) } : undefined) }; } catch (e) { return { ok: 0, status: e.status, msg: String(e.message || e) }; } }, [u, m, body]);
  const tabs = p => p.evaluate(() => [...document.querySelectorAll('#pg-tabs .pg-tab')].filter(x => x.offsetParent).map(x => x.textContent.trim()));
  const today = new Date(Date.now() + 4 * 3600e3).toISOString().slice(0, 10);

  const c = await login('chiefacc', 'chief12345');
  ck('chief accountant: Accounts has a Project payments tab', (await tabs(c)).includes('Project payments'), await tabs(c));
  ck('it opens on the tracker', await c.locator('#screen-projpay.active').count() === 1);
  const d = await c.evaluate(() => PP);
  ck('the 02-Oct-2026 sheet is in: 34 scopes, 72 payments', d.rows.length === 34 && d.rows.reduce((a, r) => a + r.payments.length, 0) === 72, [d.rows.length]);
  ck('totals match the sheet: contract 39,553,906.82, received 21,883,355.70, remaining 17,670,551.12',
     d.totals.contract === 39553906.82 && d.totals.received === 21883355.7 && d.totals.remaining === 17670551.12, d.totals);
  const r914 = d.rows.find(r => r.project === '914' && r.scope === 'CORE & SHELL');
  ck('914 Core & Shell: received 1,172,735.24, remaining 740,677.76, last 273,168.57 on 02-Oct-26, Partial',
     r914.received === 1172735.24 && r914.remaining === 740677.76 && r914.last_amount === 273168.57 && r914.last_date === '2026-10-02' && r914.status === 'Partial', r914);
  ck('status is worked out: 103 Completed, 924 Pending', d.rows.find(r => r.project === '103').status === 'Completed' && d.rows.find(r => r.project === '924').status === 'Pending');
  ck('the four figures are on top', /AED 39,553,906.82/.test(await c.locator('#pp-stats').innerText()) && /55.3%/.test(await c.locator('#pp-stats').innerText()));
  ck('914 shows once with a project total line', await c.locator('#pp-body td.proj', { hasText: /^914$/ }).count() === 1 && await c.locator('#pp-body tr.sub', { hasText: 'Project 914 total' }).count() === 1);
  await c.screenshot({ path: SH + 'pp-1-summary.png' });

  // With payment dates
  await c.selectOption('#pp-report', 'detail'); await c.waitForTimeout(300);
  ck('With payment dates: each payment with its date', /31-Dec-25\s*1,730,952.38/.test(await c.locator('#pp-body').innerText()));
  await c.screenshot({ path: SH + 'pp-2-detail.png' });
  await c.selectOption('#pp-report', 'summary');

  // Filters
  await c.check('#pp-hide'); await c.waitForTimeout(200);
  ck('Hide completed: the 7 completed scopes go', await c.locator('#pp-body tr.row').count() === 27, await c.locator('#pp-body tr.row').count());
  ck('the figures follow the list', !/AED 39,553,906.82/.test(await c.locator('#pp-stats').innerText()));
  await c.uncheck('#pp-hide');
  await c.fill('#pp-q', 'retention'); await c.dispatchEvent('#pp-q', 'input'); await c.waitForTimeout(200);
  ck('Search finds remarks too (2 retention lines)', await c.locator('#pp-body tr.row').count() === 2);
  await c.fill('#pp-q', ''); await c.dispatchEvent('#pp-q', 'input');

  // Periods: a month, a year, any two dates
  await c.selectOption('#pp-period', 'month'); await c.fill('#pp-month', '2026-09'); await c.dispatchEvent('#pp-month', 'change'); await c.waitForTimeout(1200);
  ck('Month September 2026: the 6 scopes paid in it, AED 1,748,592.38 received', await c.locator('#pp-body tr.row').count() === 6 && /Received - September 2026\s*AED 1,748,592.38/i.test(await c.locator('#pp-stats').innerText()),
     [await c.locator('#pp-body tr.row').count(), await c.locator('#pp-stats').innerText()]);
  const s914 = await c.evaluate(() => PP.rows.find(r => r.project === '914'));
  ck('as at 30-Sep: 914 Core & Shell received to date 899,566.67 (the 02-Oct payment is after)', s914.received === 899566.67 && s914.in_period === 156931.43, s914);
  ck('the columns: Received in period, Received to date', /RECEIVED IN PERIOD/i.test(await c.locator('#pp-head').innerText()) && /RECEIVED TO DATE/i.test(await c.locator('#pp-head').innerText()));
  await c.screenshot({ path: SH + 'pp-4-month.png' });
  const sepPaper = await c.evaluate(async () => { await refreshDownloadToken(); const r = await fetch(`${API}/export/accounts/projects?report=detail&format=excel&start=2026-09-01&end=2026-09-30&token=${encodeURIComponent(cachedDownloadToken)}`); return r.status + ' ' + r.headers.get('content-disposition'); });
  ck('the month paper is named for it', /With_Dates_September_2026\.xlsx/.test(sepPaper), sepPaper);
  await c.selectOption('#pp-period', 'year'); await c.waitForTimeout(1200);
  ck('Year 2026: 28 scopes, AED 11,978,375.70', await c.locator('#pp-body tr.row').count() === 28 && /AED 11,978,375.70/.test(await c.locator('#pp-stats').innerText()), await c.locator('#pp-stats').innerText());
  await c.selectOption('#pp-period', 'range'); await c.fill('#pp-from', '2026-08-15'); await c.dispatchEvent('#pp-from', 'change'); await c.fill('#pp-to', '2026-09-10'); await c.dispatchEvent('#pp-to', 'change'); await c.waitForTimeout(1200);
  ck('Date range 15-Aug to 10-Sep: AED 2,835,175.24', /15-Aug-26 to 10-Sep-26\s*AED 2,835,175.24/i.test(await c.locator('#pp-stats').innerText()), await c.locator('#pp-stats').innerText());
  await c.fill('#pp-from', '2027-01-01'); await c.dispatchEvent('#pp-from', 'change'); await c.fill('#pp-to', '2027-01-31'); await c.dispatchEvent('#pp-to', 'change'); await c.waitForTimeout(1200);
  ck('a period with nothing in it says so', /No payments in/.test(await c.locator('#pp-body').innerText()));
  await c.selectOption('#pp-period', 'full'); await c.waitForTimeout(1200);
  ck('back to Full: 34 scopes', await c.locator('#pp-body tr.row').count() === 34);

  // Add a scope with two payments
  await c.click('button:has-text("+ Add scope")'); await c.waitForTimeout(300);
  await c.fill('#pp-project', '914'); await c.fill('#pp-scope', 'TEST FIT-OUT'); await c.fill('#pp-contract', '100,000'); await c.fill('#pp-remarks', 'test line');
  await c.click('button:has-text("+ Add payment")'); await c.locator('#pp-pay-rows .pp-a').last().fill('25000');
  await c.click('button:has-text("+ Add payment")'); await c.locator('#pp-pay-rows .pp-a').last().fill('15000');
  ck('the form adds up as you type: received 40,000 remaining 60,000 Partial', /Received AED 40,000.00/.test(await c.locator('#pp-sum').innerText()) && /Remaining AED 60,000.00/.test(await c.locator('#pp-sum').innerText()) && /Partial/.test(await c.locator('#pp-sum').innerText()));
  await c.click('#pp-save'); await c.waitForTimeout(1200);
  const nr = await c.evaluate(() => PP.rows.find(r => r.scope === 'TEST FIT-OUT'));
  ck('saved: it joins project 914 (listed with 914, not at the end)', nr && nr.received === 40000 && nr.status === 'Partial' &&
     await c.evaluate(() => { const i = PP.rows.findIndex(r => r.scope === 'TEST FIT-OUT'); return PP.rows[i - 1].project === '914'; }), nr);
  ck('totals grew by the new contract and payments', await c.evaluate(() => PP.totals.contract) === 39653906.82 && await c.evaluate(() => PP.totals.received) === 21923355.7);
  // Refusals
  const fut = await api(c, `/employees/accounts/projects/${nr.id}`, 'PUT', { project: '914', scope: 'TEST FIT-OUT', contract: 100000, payments: [{ date: '2099-01-01', amount: 10 }] });
  ck('a payment dated in the future is refused', !fut.ok && fut.status === 400, fut);
  const over = await api(c, `/employees/accounts/projects/${nr.id}`, 'PUT', { project: '914', scope: 'TEST FIT-OUT', contract: 100000, payments: [{ date: today, amount: 100001 }] });
  ck('payments above the contract value are refused', !over.ok && over.status === 400, over);
  const noc = await api(c, '/employees/accounts/projects', 'POST', { project: '930', scope: 'X', contract: 0 });
  ck('a scope without a contract value is refused', !noc.ok && noc.status === 400, noc);
  // Edit: pay the rest -> Completed
  await c.evaluate(id => ppEdit(id), nr.id); await c.waitForTimeout(300);
  await c.click('button:has-text("+ Add payment")'); await c.locator('#pp-pay-rows .pp-a').last().fill('60000');
  await c.click('#pp-save'); await c.waitForTimeout(1200);
  ck('paid in full: Completed, remaining 0', await c.evaluate(id => { const r = PP.rows.find(x => x.id === id); return r.status === 'Completed' && r.remaining === 0; }, nr.id));
  // Remove
  await c.evaluate(id => ppEdit(id), nr.id); await c.waitForTimeout(300);
  await c.evaluate(() => { ppDelete(); }); await c.waitForTimeout(400);
  ck('remove asks first', /Remove 914 - TEST FIT-OUT and its 3 payment/.test(await c.locator('.hr-ask-msg').textContent()));
  await c.click('.hr-ask [data-a="yes"]'); await c.waitForTimeout(1200);
  ck('removed: back to the sheet totals', await c.evaluate(() => PP.rows.length) === 34 && await c.evaluate(() => PP.totals.contract) === 39553906.82);

  // Papers
  const papers = await c.evaluate(async () => {
    await refreshDownloadToken(); const t = encodeURIComponent(cachedDownloadToken), base = `${API}/export/accounts/projects`, out = {};
    for (const rep of ['summary', 'detail']) {
      const v = await (await fetch(`${base}/view?report=${rep}&token=${t}`)).text();
      const p = await fetch(`${base}?report=${rep}&format=pdf&token=${t}`); const x = await fetch(`${base}?report=${rep}&format=excel&token=${t}`);
      out[rep] = { v: v.slice(0, 200000), pdf: p.status + ' ' + p.headers.get('content-type') + ' ' + (await p.arrayBuffer()).byteLength, xl: x.status + ' ' + x.headers.get('content-disposition') };
    }
    return out;
  });
  ck('Summary preview: title, the four figures, Last payment column', /PROJECT PAYMENT TRACKER/.test(papers.summary.v) && /AED 39,553,906.82/.test(papers.summary.v) && /Last payment/.test(papers.summary.v) && !/Payments received/.test(papers.summary.v));
  ck('With dates preview: every payment with its date', /Payments received/.test(papers.detail.v) && /<em>31-Dec-25<\/em>1,730,952.38/.test(papers.detail.v));
  ck('both PDFs download', /^200 application\/pdf \d{4,}/.test(papers.summary.pdf) && /^200 application\/pdf \d{4,}/.test(papers.detail.pdf), [papers.summary.pdf, papers.detail.pdf]);
  ck('both Excels download with their names', /Project_Payment_Tracker_Summary_/.test(papers.summary.xl) && /Project_Payment_Tracker_With_Dates_/.test(papers.detail.xl), [papers.summary.xl, papers.detail.xl]);
  ck('no script errors (chief accountant)', !c.errs.length, c.errs);

  // Nobody else
  for (const [u, pw] of [['protest', 'pro12345'], ['keeper2', 'keep12345']]) {
    const p = await login(u, pw, '/?p=accounts#projects');
    ck(`${u}: no Project payments tab`, !(await tabs(p)).includes('Project payments'), await tabs(p));
    ck(`${u}: the screen does not open`, await p.locator('#screen-projpay.active').count() === 0);
    const r = await api(p, '/employees/accounts/projects');
    ck(`${u}: the API refuses`, r.status === 403, r);
    const x = await p.evaluate(async () => { await refreshDownloadToken(); return (await fetch(`${API}/export/accounts/projects?format=pdf&token=${encodeURIComponent(cachedDownloadToken)}`)).status; });
    ck(`${u}: the paper is refused`, x === 403, x);
    ck(`${u}: no script errors`, !p.errs.length, p.errs);
  }
  const a = await login('admin', 'changeme123');
  ck('admin has it', (await tabs(a)).includes('Project payments'));

  // Phone
  const m = await login('chiefacc', 'chief12345', '/?p=accounts#projects', { width: 390, height: 844 });
  ck('phone: opens on the tracker', await m.locator('#screen-projpay.active').count() === 1);
  ck('phone: no sideways scroll on the page', await m.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), await m.evaluate(() => [document.documentElement.scrollWidth, innerWidth]));
  await m.screenshot({ path: SH + 'pp-3-phone.png' });
  ck('phone: no script errors', !m.errs.length, m.errs);
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASSED');
  process.exit(bad ? 1 : 0);
})();
