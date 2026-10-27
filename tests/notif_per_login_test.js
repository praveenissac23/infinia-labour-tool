// Settings > General > My notifications lists exactly what each login's access gives it - Trello, subcontractor
// PCs, client bills included - and every kind (Trello too) follows the person's ticks. A kind with no group is
// never hidden by another group's tick.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/notif_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const run = Date.now() % 100000;
  const login = async (u, pw) => { const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()'); await sleep(2500); return p; };
  const call = (p, path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const admin = await login('admin', 'changeme123');
  const mk = async (u, perms) => { const x = await call(admin, '/users', 'POST', { username: u, password: 'pass12345', full_name: u, role: 'office' });
    await call(admin, `/users/${x.id}/permissions`, 'POST', { permissions: perms }); return x.id; };
  const qsId = await mk('qs' + run, 'estimation_boards,estimation_projects');
  const keeperId = await mk('keeper' + run, 'store,requests');
  const ids = async p => (await call(p, '/notifications/settings')).groups.map(g => g.id);
  const ga = await ids(admin);
  ck('admin sees every type, the new ones included', ['trello', 'subpc', 'bills', 'watch', 'requests', 'zoho'].every(x => ga.includes(x)), ga);
  const qs = await login('qs' + run, 'pass12345'), kp = await login('keeper' + run, 'pass12345');
  const gq = await ids(qs), gk = await ids(kp);
  ck('a QS (Estimation access) sees Trello, subcontractor PCs and client bills - not store or PDCs', ['trello', 'subpc', 'bills'].every(x => gq.includes(x)) && !gq.includes('store') && !gq.includes('pdc') && !gq.includes('watch'), gq);
  ck('the store keeper sees store and requests - not Trello or Estimation', gk.includes('store') && gk.includes('requests') && !gk.includes('trello') && !gk.includes('subpc'), gk);
  // a feature added to the login shows up straight away
  await call(admin, `/users/${keeperId}/permissions`, 'POST', { permissions: 'store,requests,estimation_boards' });
  const gk2 = await ids(kp);
  ck('give the keeper Trello: Trello appears on his list by itself', gk2.includes('trello'), gk2);
  // Trello follows the tick
  const board = await call(admin, '/store/kb/boards', 'POST', { title: 'N ' + run });
  await call(admin, `/store/kb/boards/${board.id}/members`, 'POST', { user_ids: [qsId] });
  const l = await call(admin, `/store/kb/boards/${board.id}/lists`, 'POST', { title: 'To do' });
  const card = await call(admin, `/store/kb/lists/${l.id}/cards`, 'POST', { title: 'Check BOQ ' + run });
  await call(admin, `/store/kb/cards/${card.id}`, 'PATCH', { add_members: [qsId] });
  const bell = async p => (await call(p, '/notifications')).notifications.filter(n => n.kind === 'board');
  ck('ticked: the QS bell has the Trello note', (await bell(qs)).length > 0);
  await call(qs, '/notifications/settings', 'POST', { on: gq.filter(x => x !== 'trello') });
  ck('Trello unticked: no Trello notes in the bell', (await bell(qs)).length === 0);
  ck('...and the other ticks were kept', (await ids(qs)).length === gq.length && (await call(qs, '/notifications/settings')).groups.filter(g => g.on).length === gq.length - 1);
  // unticking Material requests no longer hides Trello
  await call(qs, '/notifications/settings', 'POST', { on: gq });
  await call(kp, '/notifications/settings', 'POST', { on: ['trello'] });
  await call(admin, `/store/kb/boards/${board.id}/members`, 'POST', { user_ids: [keeperId] });
  await call(admin, `/store/kb/cards/${card.id}`, 'PATCH', { add_members: [keeperId] });
  ck('Material requests unticked: Trello still comes through', (await bell(kp)).length > 0);
  // the screen
  // a login without the Settings page opens it from the bell
  await qs.click('#bell-btn'); await sleep(500);
  await qs.click('#bell-panel button[onclick="openNotifPrefs()"]'); await sleep(1200);
  ck('QS (no Settings page): the bell\'s Settings opens My notifications over the page', await qs.isVisible('#notif-pref-ov #pg-notif-card'));
  const labels = await qs.$$eval('#notif-groups label', ls => ls.map(l => l.textContent.trim()));
  ck('the QS screen lists only his types, none greyed out', labels.length === gq.length && labels.some(t => /Trello/.test(t)) && !(await qs.$('#notif-groups input:disabled')), labels);
  await qs.screenshot({ path: SH + 'qs.png' });
  await qs.uncheck('#notif-groups input[value="bills"]'); await qs.click('#pg-notif-card .btn-primary'); await sleep(800);
  ck('saving from there works', (await call(qs, '/notifications/settings')).groups.find(g => g.id === 'bills').on === false);
  await qs.click('#notif-pref-ov button[onclick="closeNotifPrefs()"]'); await sleep(300);
  ck('Close puts it away', !(await qs.isVisible('#notif-pref-ov')));
  await admin.evaluate(() => pgGo('settings')); await sleep(1800);
  await admin.evaluate(() => { const el = document.getElementById('notif-groups'); if (el) el.scrollIntoView({ block: 'center' }); }); await sleep(400);
  await admin.screenshot({ path: SH + 'admin.png' });
  ck('no page errors', ![admin, qs, kp].some(p => p.errs.length), [admin, qs, kp].map(p => p.errs));
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
