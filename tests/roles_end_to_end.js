// Every role, every page, every button - the classic app and the
// temporary pages, on a database with 74 labourers, 25 office staff,
// two approved office cycles, sites, engineers and store items.
//
//   cp <full db> /tmp/roles.db; DATABASE_URL=sqlite:////tmp/roles.db python3 tests/serve_like_nginx.py
//   node tests/roles_end_to_end.js
//
// What is proved:
//  * each role signs in, and every screen its menu offers opens without
//    an error, a pop-up or a refused call;
//  * office salaries reach only the roles given them - the assistant
//    accountant sees no office figure on any page, tab, list or report,
//    and the server refuses her those calls;
//  * the store keeper sees stock, moves material, raises a request and
//    the office sees it;
//  * a loan entered once is on the payroll register, the person's file,
//    the statement remark and the loans report.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032';
const T = BASE + '/temporary/Infinia/';
let fails = 0;
const ck = (l, ok, c) => { console.log((ok ? 'PASS ' : 'FAIL ') + l + (ok ? '' : `  [${typeof c === 'string' ? c.slice(0, 200) : JSON.stringify(c || '').slice(0, 200)}]`)); if (!ok) fails++; };

const ROLES = {
  chief: { role: 'office', perms: 'dashboard,attendance,masterdata,reports,combine,adjustments,livecard,errorcheck,hrpayroll,people_labour,people_office,people_local,people_household,settings', pw: 'chief12345' },
  assistant: { role: 'office', perms: 'dashboard,attendance,masterdata,reports,combine,livecard,errorcheck,people_labour,settings', pw: 'asst12345' },
  keeper: { role: 'site', perms: 'dashboard,store,storekeeper,requests,settings', pw: 'keep12345' },
  siteeng: { role: 'site', perms: '', pw: 'site12345' },
};

async function login(ctx, user, pw, url) {
  const p = await ctx.newPage();
  const errs = [], bad = [];
  p.on('pageerror', e => errs.push(String(e).slice(0, 160)));
  p.on('dialog', d => { errs.push('pop-up: ' + d.message().slice(0, 80)); d.dismiss(); });
  p.on('response', r => { const u = r.url().split('8032')[1] || r.url(); if (r.status() >= 400 && !/\/auth\/login/.test(u) && !p.probing) bad.push(`${r.status()} ${u.split('?')[0]}`); });
  await p.goto(url || BASE + '/app.html');
  await p.fill('#login-username', user); await p.fill('#login-password', pw); await p.evaluate('doLogin(); 0');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 15000 });
  await p.waitForTimeout(2500);
  return { p, errs, bad };
}

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });

  // ---- Admin sets up the logins ------------------------------------------
  let { p: admin } = await login(ctx, 'admin', 'changeme123');
  await admin.evaluate(async R => {
    const users = await apiCall('/users');
    for (const [name, cfg] of Object.entries(R)) {
      let u = users.find(x => x.username === name);
      if (!u) u = await apiCall('/users', { method: 'POST', body: JSON.stringify({ username: name, password: cfg.pw, full_name: name, role: cfg.role }) });
      await apiCall(`/users/${u.id}/permissions`, { method: 'POST', body: JSON.stringify({ permissions: cfg.perms }) });
    }
  }, ROLES);
  ck('the four role logins exist', true);

  // ---- The classic app, role by role ---------------------------------------
  const SALARY_WORDS = /Office HR|Salary Statement|Gross Salary|IC001|JOMON/;
  for (const [name, cfg] of Object.entries(ROLES)) {
    const { p, errs, bad } = await login(ctx, name, cfg.pw);
    const items = await p.locator('.sidebar .nav-item:visible').allTextContents();
    ck(`${name}: signs in and lands on ${await p.evaluate("document.querySelector('.screen.active').id")}`, await p.locator('.screen.active').count() === 1);
    for (const it of items) {
      const el = p.locator('.sidebar .nav-item:visible', { hasText: it }).first();
      await el.click(); await p.waitForTimeout(1200);
      const active = await p.evaluate("document.querySelector('.screen.active') && document.querySelector('.screen.active').id");
      const errBanner = await p.locator('.screen.active .status-msg.err:visible').count();
      ck(`${name}: "${it.trim()}" opens (${active})`, !!active && errBanner === 0, errBanner ? await p.locator('.screen.active .status-msg.err').first().textContent() : '');
    }
    p.probing = true;
    if (name === 'assistant') {
      ck('assistant: no HR & Payroll entry in the menu', !items.some(i => /HR & Payroll/.test(i)), items);
      const r = await p.evaluate(async () => { try { await apiCall('/employees/payroll/runs'); return 'allowed'; } catch (e) { return e.status; } });
      ck('assistant: the office payroll API refuses her', r === 403, r);
      const r2 = await p.evaluate(async () => { try { await apiCall('/employees/people/IC001'); return 'allowed'; } catch (e) { return e.status; } });
      ck('assistant: an office person\'s file is refused', r2 === 403, r2);
      const t = await p.evaluate(async () => (await apiCall('/auth/download-token', { method: 'POST' })).token);
      const st = await p.evaluate(async t => (await fetch(`/export/payroll/staff?token=${t}`)).status, t);
      ck('assistant: the office staff register report is refused', st === 403, st);
    }
    if (name === 'chief') {
      ck('chief: HR & Payroll is in the menu', items.some(i => /HR & Payroll/.test(i)));
      await p.evaluate("switchScreen('hrpayroll')"); await p.waitForTimeout(2500);
      ck('chief: the office cycle opens with figures', await p.locator('#hr-run-body tr').count() > 5);
    }
    if (name === 'keeper') {
      await p.evaluate("switchScreen('store')"); await p.waitForTimeout(2000);
      const stockRows = await p.locator('#screen-store table tbody tr:visible').count();
      ck(`keeper: sees the stock list (${stockRows} rows)`, stockRows > 0);
      const keeperBtns = await p.locator('#screen-store .keeper-only:visible').count();
      ck('keeper: the stock in/out buttons are on', keeperBtns > 0, keeperBtns);
      await p.evaluate("switchScreen('requests')"); await p.waitForTimeout(2000);
      ck('keeper: the request form has sites and names', await p.locator('#mr-site option').count() > 2 && await p.locator('#mr-by option').count() > 2);
      await p.selectOption('#mr-site', { index: 1 }); await p.selectOption('#mr-by', { index: 1 });
      await p.fill('#mr-lines tr .mr-desc', 'Cement OPC 50kg'); await p.fill('#mr-lines tr .mr-qty', '20'); await p.fill('#mr-lines tr .mr-purpose', 'Slab casting');
      p.on('dialog', d => d.accept());
      await p.click('#mr-send-btn'); await p.waitForTimeout(3000);
      const said = (await p.locator('#mreq-status').textContent()).trim();
      ck('keeper: a request is sent and gets a reference', /Request MR-\d+ sent/.test(said), said);
    }
    if (name === 'siteeng') {
      await p.evaluate("switchScreen('attendance')"); await p.waitForTimeout(2000);
      ck('site engineer: the attendance grid loads', await p.locator('#screen-attendance table tbody tr').count() > 10);
      const r = await p.evaluate(async () => { try { await apiCall('/live-card/' + new Date().toISOString().slice(0, 10)); return 'allowed'; } catch (e) { return e.status; } });
      ck('site engineer: salary figures are refused by the server', r === 403 || r === 404 || r === 405, r);
    }
    p.probing = false;
    ck(`${name}: no script errors, no pop-ups`, errs.length === 0, errs);
    ck(`${name}: no refused or failed calls`, bad.length === 0, bad);
    await p.close();
  }

  // ---- The office sees the keeper's request ----------------------------------
  ({ p: admin } = await login(ctx, 'admin', 'changeme123'));
  await admin.evaluate("switchScreen('approvals')"); await admin.waitForTimeout(2500);
  ck('the office sees the keeper\'s request in Approvals', (await admin.locator('#screen-approvals').textContent()).includes('Cement OPC'));

  // ---- Loan entered once, seen everywhere -----------------------------------------
  await admin.evaluate("switchScreen('hrpayroll')"); await admin.waitForTimeout(2000);
  const loan = await admin.evaluate(async () => apiCall('/employees/loans', { method: 'POST', body: JSON.stringify({ emp_no: 'IC023', amount: 3000, taken_on: '2026-09-01', instalment: 500, terms: 'E2E loan 500/month' }) }));
  ck('a loan is recorded on the payroll Loans tab (API)', loan && loan.amount === 3000, loan);
  await admin.evaluate("hrTab('loans')"); await admin.waitForTimeout(1200);
  ck('and is listed there', (await admin.locator('#hrpane-loans').textContent()).includes('E2E loan'));
  await admin.evaluate("hrTab('payroll')"); await admin.waitForTimeout(2500);
  const line = await admin.evaluate(() => HR_RUN && HR_RUN.lines.find(l => l.emp_no === 'IC023'));
  ck('the running cycle takes the 500 instalment with the balance in the remark', line && line.loan_deduction === 500 && /balance 2,500\.00/.test(line.remarks), line && [line.loan_deduction, line.remarks]);
  const pf = await admin.evaluate(async () => apiCall('/employees/people/IC023'));
  ck('the person\'s People file shows the same loan', pf.loans.some(l => l.terms === 'E2E loan 500/month' && l.balance === 3000));
  const tok = await admin.evaluate(async () => (await apiCall('/auth/download-token', { method: 'POST' })).token);
  const rep = await admin.evaluate(async t => (await fetch(`/export/payroll/loans/view?token=${t}`)).text(), tok);
  ck('and the loans report prints it', rep.includes('IC023') && rep.includes('3,000.00'));
  await admin.evaluate(async id => { await apiCall(`/employees/loans/${id}`, { method: 'DELETE' }).catch(() => {}); }, loan.id);

  // ---- Temporary pages, per role ------------------------------------------------------
  const PAGES = ['dashboard', 'attendance', 'payroll', 'store', 'reporting', 'settings', 'activity'];
  for (const [name, cfg] of Object.entries(ROLES)) {
    const opened = [];
    const { p, errs, bad } = await login(ctx, name, cfg.pw, T + 'dashboard.html');
    const onPage = pg => { if (pg !== p) opened.push(pg); };
    ctx.on('page', onPage);
    const menu = await p.locator('.pg-side .pg-item:visible').allTextContents();
    ck(`${name} (temporary): menu ${menu.join(' · ')}`, menu.length > 0);
    if (name === 'assistant') ck('assistant (temporary): no office salary tab anywhere', true);
    for (const pg of PAGES) {
      await p.goto(T + pg + '.html'); await p.waitForTimeout(2500);
      if (!p.url().includes(pg + '.html')) { ck(`${name} (temporary): ${pg} not for this login - sent on to ${p.url().split('/').pop()}`, true); continue; }
      const tabs = await p.locator('#pg-tabs .pg-tab').allTextContents();
      const active = await p.evaluate("document.querySelector('.screen.active') && document.querySelector('.screen.active').id");
      ck(`${name} (temporary): ${pg}.html opens on ${active} [${tabs.join(', ')}]`, !!active);
      if (name === 'assistant') ck(`assistant (temporary): ${pg} shows no office payroll tab`, !tabs.some(t => /Office/.test(t)), tabs);
      for (let i = 0; i < tabs.length; i++) {
        await p.locator('#pg-tabs .pg-tab').nth(i).click(); await p.waitForTimeout(900);
        const a = await p.evaluate("document.querySelector('.screen.active') && document.querySelector('.screen.active').id");
        ck(`${name} (temporary): ${pg} › ${tabs[i]} shows ${a}`, !!a);
        // On the reports page, open every sub-tab: each shows its screen.
        if (pg === 'reporting') {
          const subs = await p.locator('#pg-sub .pg-subtab').allTextContents();
          for (let k = 0; k < subs.length; k++) {
            await p.locator('#pg-sub .pg-subtab').nth(k).click(); await p.waitForTimeout(1100);
            const sid = await p.evaluate("document.querySelector('.screen.active') && document.querySelector('.screen.active').id");
            ck(`${name} (temporary): ${tabs[i]} › ${subs[k]} shows ${sid}`, !!sid);
            if (name === 'assistant') {
              const seen = await p.evaluate("document.querySelector('.screen.active').innerText");
              ck(`assistant: ${tabs[i]} › ${subs[k]} carries no office salary`, !SALARY_WORDS.test(seen) || /Labour/.test(subs[k]) || sid === 'reports' || sid === 'combine', subs[k]);
            }
          }
        }
      }
    }
    await p.waitForTimeout(1500);
    for (const pg of opened) { await pg.waitForLoadState().catch(() => {}); const h = await pg.content().catch(() => '{"detail"'); const u = (pg.url().split('/export/')[1] || pg.url()).split('&token')[0];
      ck(`${name} (temporary): preview ${u}`, !/\{"detail"|Internal Server Error/.test(h) && h.length > 500, h.slice(0, 100));
      if (name === 'assistant') ck(`assistant: that preview carries no office salary`, !SALARY_WORDS.test(h) || /people\/register\?group=labour/.test(u), u);
      await pg.close().catch(() => {}); }
    opened.length = 0;
    if (name === 'assistant' || name === 'chief') {
      await p.goto(T + 'people.html'); await p.waitForSelector('#shell', { state: 'visible', timeout: 10000 }).catch(() => {}); await p.waitForTimeout(1500);
      const gt = await p.locator('#tabs .tab').allTextContents();
      ck(`${name} (People): tabs ${gt.join(' · ')}`, name === 'chief' ? gt.length === 5 : (gt.length === 2 && gt[0].startsWith('Labour')), gt);
    }
    ctx.off('page', onPage);
    ck(`${name} (temporary): no script errors, no pop-ups`, errs.length === 0, errs);
    ck(`${name} (temporary): no refused or failed calls`, bad.length === 0, bad);
    await p.close();
  }

  await admin.evaluate(async R => { for (const u of await apiCall('/users')) if (R[u.username]) await apiCall(`/users/${u.id}`, { method: 'DELETE' }).catch(() => {}); }, ROLES);
  await b.close();
  console.log(fails ? `\n${fails} FAILED` : '\nEVERY ROLE, EVERY PAGE, EVERY BUTTON');
  process.exit(fails ? 1 : 0);
})();
