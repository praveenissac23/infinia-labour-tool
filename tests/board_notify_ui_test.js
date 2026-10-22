// Trello notifications go to the right people only: whoever is @mentioned, and whoever is on the card
// (members / watchers) - not everyone on the board. They pop up in the app, laid out like Trello's.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/bnotify_';
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
  const aarathi = await mk('aarathi' + run, 'Aarathi S'), jibin = await mk('jibin' + run, 'Jibin K');
  const board = await call(admin, '/store/kb/boards', 'POST', { title: 'Estimation ' + run });
  await call(admin, `/store/kb/boards/${board.id}/members`, 'POST', { user_ids: [aarathi, jibin] });
  const l1 = await call(admin, `/store/kb/boards/${board.id}/lists`, 'POST', { title: 'To price' });
  const l2 = await call(admin, `/store/kb/boards/${board.id}/lists`, 'POST', { title: 'Under review' });
  const card = await call(admin, `/store/kb/lists/${l1.id}/cards`, 'POST', { title: 'VE278 - shell & core BOQ' });
  const cid = card.id || (card.cards && card.cards[0] && card.cards[0].id) || (Array.isArray(card) ? card[0].id : null);
  ck('board, lists and a card made', !!cid, card);
  // Aarathi is signed in and working when it happens
  const a = await login('aarathi' + run, 'pass12345');
  const j = await login('jibin' + run, 'pass12345');
  await a.evaluate(() => { window.__popups = true; }); await j.evaluate(() => { window.__popups = true; });
  await call(admin, `/store/kb/cards/${cid}/comments`, 'POST', { text: '@Aarathi please check the plaster quantities against the drawings before Thursday.' });
  const na = await call(a, '/store/kb/notes'), nj = await call(j, '/store/kb/notes');
  ck('the one tagged (@Aarathi, by first name) is told', na.notes.some(n => n.kind === 'mention' && /plaster/.test(n.text)), na.notes);
  ck('someone on the board but not on the card is not told', !nj.notes.some(n => n.card_id === cid), nj.notes);
  await a.evaluate(() => loadNotifications()); await sleep(900);
  ck('a pop-up comes up for Aarathi', await a.isVisible('#notif-overlay.on'));
  const txt = await a.textContent('#notif-box');
  ck('it says who, what, the card, the board and list, and the words', /Administrator|admin/i.test(txt) && txt.includes('mentioned you') && txt.includes('VE278 - shell & core BOQ') && txt.includes('To price') && txt.includes('plaster quantities'), txt);
  await a.screenshot({ path: SH + 'mention.png' });
  await j.evaluate(() => loadNotifications()); await sleep(700);
  ck('no pop-up for Jibin', !(await j.isVisible('#notif-overlay.on')));
  // Open card goes to the card
  await a.click('#notif-go'); await sleep(2500);
  ck('Open card takes her to the Trello page', await a.isVisible('#screen-pgboards'));
  // put on the card -> told about what happens to it after
  await call(admin, `/store/kb/cards/${cid}`, 'PATCH', { add_members: [aarathi] });
  await call(admin, `/store/kb/cards/${cid}`, 'PATCH', { list_id: l2.id });
  await call(admin, `/store/kb/cards/${cid}`, 'PATCH', { due: '2026-10-29T17:00' });
  await call(admin, `/store/kb/cards/${cid}/comments`, 'POST', { text: 'Revised rates are attached on the card.' });
  const na2 = (await call(a, '/store/kb/notes')).notes.map(n => n.kind);
  ck('on the card: told when added, moved, given a due date and commented on', ['added', 'moved', 'due', 'comment'].every(k => na2.includes(k)), na2);
  ck('Jibin still told nothing about the card', !(await call(j, '/store/kb/notes')).notes.some(n => n.card_id === cid));
  await a.goto(B + '/?p=dashboard'); await sleep(2500); await a.evaluate(() => { window.__popups = true; localStorage.removeItem('infinia_seen_notifications'); });
  await a.evaluate(() => { toastReady = true; loadNotifications(); }); await sleep(1000);
  await a.screenshot({ path: SH + 'moved.png' });
  const t2 = await a.textContent('#notif-box').catch(() => '');
  ck('the next pop-up reads properly (who / what / card)', t2.includes('VE278') && /more waiting/.test(t2), t2.slice(0, 200));
  ck('no page errors', !a.errs.length && !j.errs.length, a.errs.concat(j.errs));
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
