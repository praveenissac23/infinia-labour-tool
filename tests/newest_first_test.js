// Lists added to every day show the newest entry on top: bank, invoices, cash register.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  const r = await p.evaluate(() => {
    const rows = [{ id: 1, date: '2026-10-15' }, { id: 3, date: '2026-10-16' }, { id: 2, date: '2026-10-16' }, { id: 4, date: '2026-10-02' }];
    return newestFirst(rows, 'date').map(x => x.id);
  });
  ck('newest date first, and on the same day the later entry first', JSON.stringify(r) === '[3,2,1,4]', r);
  const b = await p.evaluate(() => { BK = { rows: [{ id: 1, date: '2026-10-15', party: 'A', reference: '', notes: '', docs: [], site: '' }, { id: 2, date: '2026-10-16', party: 'B', reference: '', notes: '', docs: [], site: '' }] }; return bkShown().map(x => x.id); });
  ck('bank list: 16-Oct above 15-Oct', JSON.stringify(b) === '[2,1]', b);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0); })();
