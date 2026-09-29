// Help: search (everyday words, typos), guide drawer with pictures, "?"
// list for the page, Show me, Watch, the first-login hello, and a login
// with fewer rights finding only its own guides.
// Needs a login amaltest / amal12345 with store + storekeeper.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const login = async (u, pw, popups) => {
    const p = await (await b.newContext({ viewport: { width: 1360, height: 820 } })).newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    if (popups) await p.addInitScript(() => { window.__popups = 1; });
    await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3500); return p;
  };
  const p = await login('admin', 'changeme123', true);
  ck('the hello waits while the sign-in notice is open', !(await p.locator('.help-hello').count()) || !(await p.locator('#notif-overlay.on').count()));
  if (await p.locator('#notif-overlay.on').count()) { await p.locator('#notif-overlay button', { hasText: 'Close' }).first().click(); await p.waitForTimeout(2000); }
  ck('first sign-in shows the hello next to the search box', await p.locator('.help-hello').isVisible());
  await p.screenshot({ path: SH + 'help-0-hello.png' });
  await p.click('.help-hello [data-ok]');
  ck('"Got it" puts it away for good', !(await p.locator('.help-hello').count()) && await p.evaluate(() => localStorage.getItem('infinia-help-hello') === '1'));
  const top = async q => { await p.fill('#help-search', q); await p.waitForTimeout(250); return p.evaluate(() => [...document.querySelectorAll('#help-results .help-r')].map(x => x.dataset.id)); };
  const cases = [['worker fired', 'worker-leaves'], ['resigned labour', 'worker-leaves'], ['termnate', 'worker-leaves'], ['how to buy cement', 'lpo'],
    ['LPO', 'lpo'], ['add stock', 'stock-add'], ['visa expiry', 'expiry-person'], ['mulkiya', 'expiry-company'], ['salary increase labour', 'worker-increment'],
    ['petty', 'petty'], ['send material to site', 'move'], ['broken', 'lost'], ['eid holiday', 'att-holiday'], ['payslip', 'labour-cards'], ['supplier', 'supplier']];
  for (const [q, want] of cases) { const r = await top(q); ck(`"${q}" finds "${want}" in the top 3`, r.slice(0, 3).includes(want), r.slice(0, 4)); }
  await top('worker left');
  await p.screenshot({ path: SH + 'help-1-search.png' });
  ck('nonsense gets a friendly "no guide" line', /No guide/.test(await (async () => { await top('zzqx'); return p.locator('#help-results').textContent(); })()));
  await top('lpo'); await p.keyboard.press('Enter'); await p.waitForTimeout(900);
  ck('Enter opens the guide in the side panel', await p.locator('.help-drawer.open .help-title').textContent() === 'How to make an LPO (purchase order)');
  const imgs = await p.evaluate(() => Promise.all([...document.querySelectorAll('.help-steps img')].map(i => i.decode().then(() => i.naturalWidth).catch(() => 0))));
  ck('every step has its picture, and each loads', imgs.length === 4 && imgs.every(w => w > 500), imgs);
  await p.screenshot({ path: SH + 'help-2-guide.png' });
  await p.click('[data-watch]'); await p.waitForTimeout(800);
  ck('Watch plays the pictures with the step written under', /1\./.test(await p.locator('.help-wcap').textContent()));
  await p.screenshot({ path: SH + 'help-3-watch.png' });
  await p.click('.help-watchbox .help-x');
  await p.click('[data-show]'); await p.waitForTimeout(3000);
  ck('Show me goes to Purchasing > Purchase orders', /p=store#purchasing:purchase/.test(p.url()), p.url());
  ck('and circles the list of approved requests', await p.evaluate(() => HELP.state && HELP.state.el && HELP.state.el.id === 'lpo-pending-card'));
  await p.click('.help-bubble [data-n]'); await p.waitForTimeout(900);
  ck('Next moves to step 2, the Generate button', await p.evaluate(() => HELP.state.i === 1 && /lpoFromTicked/.test(HELP.state.el.getAttribute('onclick'))));
  await p.keyboard.press('Escape');
  ck('Escape closes Show me', !(await p.locator('.help-ring').count()));
  await p.click('#help-q'); await p.waitForTimeout(600);
  const here = await p.evaluate(() => { const h = [...document.querySelectorAll('.help-lists h4')][0]; return h && h.textContent; });
  ck('"?" opens this page\'s guides first', here === 'On this page');
  await p.screenshot({ path: SH + 'help-4-list.png' });
  await p.click('.help-x'); await p.goto(B + '/?p=attendance#masterdata'); await p.waitForTimeout(3500);
  ck('the (i) sits beside "new salary from" and shows its note', await p.locator('#md-rate-from + .help-i').count() === 1);
  await p.hover('#md-rate-from + .help-i'); await p.screenshot({ path: SH + 'help-5-tip.png' });
  ck('no script errors (admin)', p.errs.length === 0, p.errs);

  const a = await login('amaltest', 'amal12345', true);
  const mine = await a.evaluate(() => HELP_GUIDES.filter(HELP.allowed).map(g => g.area));
  ck('the store keeper finds store guides', mine.includes('Store'));
  ck('but no payroll or expiry guides', !mine.includes('Payroll') && !mine.includes('Expiry'), [...new Set(mine)]);
  await a.fill('#help-search', 'salary cards'); await a.waitForTimeout(300);
  ck('searching "salary cards" shows him nothing about pay', !(await a.evaluate(() => [...document.querySelectorAll('#help-results .help-r')].some(x => /labour-cards|office/.test(x.dataset.id)))));
  ck('no script errors (store keeper)', a.errs.length === 0, a.errs);
  console.log(bad ? `${bad} FAILED` : 'HELP HOLDS UP');
  await b.close(); process.exit(bad ? 1 : 0);
})();
