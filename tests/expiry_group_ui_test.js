// Expiry Reminder > All together: visa, labour card & EID as one line, one Mark started for the three.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=expiry'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  const emp = await p.evaluate(async () => {
    const e = (await apiCall('/employees')).find(x => x.active !== false && !x.staff);
    const d = n => { const t = new Date(); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
    const docs = (await apiCall('/employees/documents')).rows.filter(x => x.emp_no === e.emp_no && ['visa', 'labour_card', 'eid'].includes(x.kind));
    for (const x of docs) await apiCall(`/employees/documents/${x.id}`, { method: 'DELETE' }).catch(() => 0);
    for (const [k, n] of [['visa', 5], ['labour_card', 6], ['eid', 9]])
      await apiCall('/employees/documents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ emp_no: e.emp_no, kind: k, number: k.toUpperCase() + '-1', expires_on: d(n) }) });
    return e;
  });
  await p.evaluate(() => hrDocMode('all')); await p.waitForTimeout(2000);
  await p.fill('#exp-all-search', emp.emp_no); await p.evaluate(() => renderAllDocs()); await p.waitForTimeout(300);
  const rows = p.locator('#exp-all-body tr', { hasText: 'Visa, labour card & Emirates ID' });
  ck('one line for visa, labour card and EID', await rows.count() === 1 && !(await p.locator('#exp-all-body tr', { hasText: /^Labour card$/ }).count()), await p.textContent('#exp-all-body'));
  ck('the line shows each date and number', /Labour card/.test(await rows.textContent()) && /VISA-1/.test(await rows.textContent()));
  await p.screenshot({ path: SH + 'expiry_group_before.png' });
  await rows.locator('button', { hasText: 'Mark started' }).click(); await p.waitForTimeout(1500);
  ck('one click: Started', await p.locator('#exp-all-body tr', { hasText: 'Visa, labour card & Emirates ID' }).locator('button', { hasText: 'Started' }).count() === 1);
  const st = await p.evaluate(async no => { const d = (await apiCall('/employees/documents')).rows.filter(x => x.emp_no === no && ['visa', 'labour_card', 'eid'].includes(x.kind)); return d.every(x => expStarted('person', x.id)); }, emp.emp_no);
  ck('all three documents marked started', st);
  const bell = await p.evaluate(async no => { const n = (await apiCall('/notifications')).notifications.find(x => x.kind === 'expiry'); return n ? n.detail : ''; }, emp.emp_no);
  ck('bell no longer names him', !bell.includes(emp.emp_no), bell);
  await p.screenshot({ path: SH + 'expiry_group_started.png' });
  ck('no page errors', errs.length === 0, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
