// Material request: the real button click sends once - and a double click still sends only once.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  const posts = []; p.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/store/requests')) posts.push(1); });
  await p.goto(B + '/?p=store'); await p.fill('#login-username', process.env.MR_USER || 'admin'); await p.fill('#login-password', process.env.MR_PW || 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  await p.evaluate(() => { pgTab('requests'); pgSub('requests'); }); await p.waitForTimeout(2500);
  const fill = async (desc) => {
    await p.selectOption('#mr-site', { index: 1 }); await p.selectOption('#mr-by', { index: 1 }); await p.fill('#mr-needed', '2099-01-01');
    const r = p.locator('#mr-lines tr').first(); await r.locator('.mr-desc').fill(desc); await r.locator('.mr-qty').fill('3'); await r.locator('.mr-purpose').fill('test');
  };
  await fill('Click test cement'); await p.click('#mr-send-btn'); await p.waitForTimeout(3000);
  ck('one click sends the request', posts.length === 1 && /sent to the office/.test(await p.textContent('#mreq-status')), [posts.length, await p.textContent('#mreq-status')]);
  ck('button back to normal', await p.evaluate(() => { const b = document.getElementById('mr-send-btn'); return !b.disabled && !b.dataset.sending && b.textContent === 'Send Request to Office'; }));
  posts.length = 0;
  await fill('Double click sand'); await p.click('#mr-send-btn', { clickCount: 2 }); await p.waitForTimeout(3000);
  ck('a double click still sends only once', posts.length === 1, posts.length);
  ck('no page errors', !errs.length, errs);
  await b.close(); console.log(bad ? `${bad} FAILURE(S)` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
