// A card member changes a card: every other person on the card gets the pop-up; the one who made the
// change is not told about his own change. A tag (@name) always reaches the person tagged.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/bmember_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const run = Date.now() % 100000;
  const login = async (u, pw) => { const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + '/'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()'); await sleep(2500); return p; };
  const call = (p, path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const admin = await login('admin', 'changeme123');
  const mk = async (u, full) => { const x = await call(admin, '/users', 'POST', { username: u, password: 'pass12345', full_name: full, role: 'office' });
    await call(admin, `/users/${x.id}/permissions`, 'POST', { permissions: 'estimation_boards' }); return x.id; };
  const anoop = await mk('anoop' + run, 'Anoop S'), arathi = await mk('arathi' + run, 'Arathi Sajeendran'), rahul = await mk('rahul' + run, 'Rahul M');
  const board = await call(admin, '/store/kb/boards', 'POST', { title: 'Estimation ' + run });
  await call(admin, `/store/kb/boards/${board.id}/members`, 'POST', { user_ids: [anoop, arathi, rahul] });
  const l1 = await call(admin, `/store/kb/boards/${board.id}/lists`, 'POST', { title: 'To price' });
  const l2 = await call(admin, `/store/kb/boards/${board.id}/lists`, 'POST', { title: 'Submitted' });
  const card = await call(admin, `/store/kb/lists/${l1.id}/cards`, 'POST', { title: 'Villa 909 - joinery BOQ' });
  const cid = card.id;
  await call(admin, `/store/kb/cards/${cid}`, 'PATCH', { add_members: [anoop, arathi] });   // Rahul is on the board, not on the card
  await call(admin, '/store/kb/notes/read', 'POST', {});
  const an = await login('anoop' + run, 'pass12345'), ar = await login('arathi' + run, 'pass12345'), ra = await login('rahul' + run, 'pass12345');
  for (const p of [an, ar, ra]) await call(p, '/store/kb/notes/read', 'POST', {});
  // Anoop (a card member) moves the card and changes its due date
  await call(an, `/store/kb/cards/${cid}`, 'PATCH', { list_id: l2.id });
  await call(an, `/store/kb/cards/${cid}`, 'PATCH', { due: '2026-10-30T17:00' });
  const unread = async p => (await call(p, '/store/kb/notes')).notes.filter(n => !n.read && n.card_id === cid);
  const arN = await unread(ar), anN = await unread(an), raN = await unread(ra), adN = await unread(admin);
  ck('Arathi (on the card) is told about the move and the due date', arN.some(n => n.kind === 'moved') && arN.some(n => n.kind === 'due'), arN);
  ck('the general admin login (not on the card) is not told', adN.length === 0, adN);
  ck('Anoop, who made the change, is NOT told', anN.length === 0, anN);
  ck('Rahul (not on the card) is not told', raN.length === 0, raN);
  await ar.evaluate(() => { window.__popups = true; localStorage.removeItem('infinia_seen_notifications'); toastReady = true; loadNotifications(); }); await sleep(1200);
  ck('Arathi gets the pop-up', await ar.isVisible('#notif-overlay.on'));
  const t = await ar.textContent('#notif-box').catch(() => '');
  ck('pop-up names Anoop, the card and the change', /Anoop/.test(t) && t.includes('Villa 909 - joinery BOQ'), t.slice(0, 300));
  await ar.screenshot({ path: SH + 'arathi_popup.png' });
  await an.evaluate(() => { window.__popups = true; localStorage.removeItem('infinia_seen_notifications'); toastReady = true; loadNotifications(); }); await sleep(1200);
  ck('Anoop gets no pop-up for his own change', !(await an.isVisible('#notif-overlay.on')));
  await an.screenshot({ path: SH + 'anoop_nopopup.png' });
  // Rahul (not on the card) is tagged - he must be told
  await call(an, `/store/kb/cards/${cid}/comments`, 'POST', { text: '@Rahul please price the wardrobe shutters.' });
  const rn = await unread(ra);
  ck('Rahul, tagged, is told', rn.some(n => n.kind === 'mention'), rn);
  ck('Anoop not told about his own comment', (await unread(an)).length === 0);
  await ra.evaluate(() => { window.__popups = true; localStorage.removeItem('infinia_seen_notifications'); toastReady = true; loadNotifications(); }); await sleep(1200);
  ck('Rahul gets the pop-up for the tag', await ra.isVisible('#notif-overlay.on'));
  await ra.screenshot({ path: SH + 'rahul_tag.png' });
  ck('no page errors', ![an, ar, ra].some(p => p.errs.length), [an, ar, ra].map(p => p.errs));
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
