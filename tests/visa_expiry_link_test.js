// PRO Visa tab -> Expiry Reminder: completing a visa asks for the new visa, labour card & EID dates.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=accounts#petty:pro'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000);
  const emp = await p.evaluate(async () => {
    const e = (await apiCall('/employees')).find(x => x.active !== false && !x.staff);
    const d = n => { const t = new Date(); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
    for (const [k, n] of [['visa', 6], ['labour_card', 6], ['eid', 40]])
      await apiCall('/employees/documents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ emp_no: e.emp_no, kind: k, number: '', expires_on: d(n) }) });
    return e;
  });
  await p.goto(B + '/?p=accounts#petty:pro'); await p.waitForTimeout(3000);
  await p.click('#pc-protabs [data-v="visa"]'); await p.waitForTimeout(1500);
  await p.fill('#vh-person', emp.emp_no); await p.fill('#vh-step', 'Medical and EID'); await p.fill('#vh-amt', '320'); await p.click('#vh-save'); await p.waitForTimeout(1800);
  const started = await p.evaluate(async no => { const d = (await apiCall('/employees/expiry/started')).rows; const docs = (await apiCall('/employees/documents')).rows.filter(x => x.emp_no === no && ['visa','labour_card','eid'].includes(x.kind)); return docs.every(x => d.some(r => r.id === x.id && r.visa)); }, emp.emp_no);
  ck('visa file opened: his visa, labour card & EID show Started in Expiry Reminder', started);
  const row = p.locator('#vh-body tr').filter({ has: p.locator('button', { hasText: 'Mark completed' }) }).first();
  await row.locator('button', { hasText: 'Mark completed' }).click(); await p.waitForTimeout(300);
  await p.locator('.hr-ask [data-a="yes"]').click(); await p.waitForTimeout(2000);
  ck('completed: the Set new expiry pop-up opens with Visa, Labour card, Emirates ID', await p.locator('.exp-cm input[type=date]').count() === 3);
  await p.screenshot({ path: SH + 'visa_complete_expiry.png' });
  await p.click('.exp-cm button:has-text("Set new expiry")'); await p.waitForTimeout(1800);
  const yr = await p.evaluate(async no => (await apiCall('/employees/documents')).rows.filter(x => x.emp_no === no && x.kind === 'visa').map(x => x.days_left)[0], emp.emp_no);
  ck('new visa date saved - the same record the Staff register shows', yr > 600, yr);
  ck('message on the Visa tab', /Closed/.test(await p.textContent('#vh-status')));
  ck('no page errors', errs.length === 0, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
