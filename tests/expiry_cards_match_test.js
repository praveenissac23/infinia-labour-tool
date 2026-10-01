// Expiry Reminder: every counter's number is the number of lines its
// click shows - People counts people, Company counts documents; the
// menu badge keeps the total of both.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=expiry#expiry:people'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500);
  const card = k => p.evaluate(k => +document.querySelector(`.exp-card[data-k="${k}"] b`).textContent, k);
  const rows = (body) => p.evaluate(body => [...document.querySelectorAll(`#${body} tr`)].filter(r => !r.querySelector('td[colspan]')).length, body);
  for (const tab of ['people', 'company']) {
    await p.evaluate(t => { hrDocMode(t); }, tab); await p.waitForTimeout(1200);
    const body = tab === 'people' ? 'hr-doc-body' : 'hr-exp-body';
    for (const k of ['expired', 'week', 'month', tab === 'people' ? 'missing' : 'all']) {
      const n = await card(k);
      await p.evaluate(k => expCard(k), k); await p.waitForTimeout(700);
      const r = await rows(body);
      ck(`${tab}: "${k}" card says ${n}, its list shows ${r}`, n === r, [n, r]);
    }
    await p.evaluate(() => expCard('week')); await p.waitForTimeout(600);
    await p.screenshot({ path: SH + `expiry-cards-${tab}.png` });
  }
  const s = await p.evaluate(() => EXP_SUM);
  ck('company tab and people tab together make up the overall "due in 7 days"', s.people.week + s.company.week <= s.week && s.company.week > 0, [s.people, s.company, s.week]);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'EVERY CARD MATCHES ITS LIST');
  await b.close(); process.exit(bad ? 1 : 0);
})();
