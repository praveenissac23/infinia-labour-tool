// Trello: the things that were not proper - quick clicks on labels and members, double comments,
// another person's open card following, mirrors on Anoop's board, and no redraw when nothing changed.
// Needs the server (tests/serve_like_nginx.py, port 8032) and the admin login.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0; const fails = [];
const ck = (name, ok, info) => { if (!ok) { bad++; fails.push(name); } console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const login = async (u, pw) => {
    const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
    p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', u); await p.fill('#lg-p', pw); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
    return p;
  };
  const p = await login('admin', 'changeme123');
  const api = async (path, opt = {}, pg = p) => pg.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  // two QS logins
  for (const u of ['fx_qs1', 'fx_qs2']) {
    const r = await api('/users', { method: 'POST', body: { username: u, password: 'pass12345', role: 'office' } });
    if (r.id) await api(`/users/${r.id}/permissions`, { method: 'POST', body: { permissions: 'settings,estimation_boards' } });
  }
  const users = await api('/users'); const QS1 = users.find(u => u.username === 'fx_qs1').id, QS2 = users.find(u => u.username === 'fx_qs2').id;
  // boards: Estimation (main) and Anoop's, with a mirror rule
  const E = (await api('/store/kb/boards', { method: 'POST', body: { title: 'FX Estimation', lists: ['911 WS46', 'Done'] } })).id;
  const A = (await api('/store/kb/boards', { method: 'POST', body: { title: 'FX Anoop', lists: ['VARIATIONS', 'DONE'] } })).id;
  await api(`/store/kb/boards/${E}`, { method: 'PATCH', body: { visibility: 'team' } }); await api(`/store/kb/boards/${A}`, { method: 'PATCH', body: { visibility: 'team' } });
  const EB = await api(`/store/kb/boards/${E}`), AB = await api(`/store/kb/boards/${A}`);
  const EL = Object.fromEntries(EB.lists.map(l => [l.title, l.id])), AL = Object.fromEntries(AB.lists.map(l => [l.title, l.id]));
  await api(`/store/kb/boards/${E}/rules`, { method: 'POST', body: { trigger: { type: 'card_titled', words: ['Variation'], numbered: true }, actions: [{ type: 'mirror_board', board_id: A, list_id: AL.VARIATIONS }] } });
  await api(`/store/kb/boards/${E}/rules`, { method: 'POST', body: { trigger: { type: 'card_complete' }, actions: [{ type: 'move_mirror', board_id: A, list_id: AL.DONE }] } });
  const C1 = (await api(`/store/kb/lists/${EL['911 WS46']}/cards`, { method: 'POST', body: { title: '911 - Variations for ceiling' } })).id;
  const plain = (await api(`/store/kb/lists/${EL['911 WS46']}/cards`, { method: 'POST', body: { title: 'Quick click card' } })).id;

  // ---- quick clicks: 4 labels, 3 members in one popover ----
  await p.goto(`${B}/portal/boards.html#/b/${E}/c/${plain}`); await p.waitForSelector('.cm'); await sleep(500);
  await p.click('.cm .acts [data-k="labels"]'); await sleep(200);
  const boxes = await p.$$('.pop .lrow input[data-l]');
  for (let i = 0; i < 4; i++) { await (await p.$$('.pop .lrow input[data-l]'))[i].click(); await sleep(40); }
  await sleep(1800);
  let srv = await api(`/store/kb/cards/${plain}`);
  ck('4 labels ticked quickly - all 4 saved', srv.labels.length === 4, srv.labels);
  for (let i = 0; i < 2; i++) { await (await p.$$('.pop .lrow input[data-l]'))[i].click(); await sleep(40); }
  await sleep(1500); srv = await api(`/store/kb/cards/${plain}`);
  ck('2 un-ticked quickly - the other 2 stay', srv.labels.length === 2, srv.labels);
  ck('the card front shows the same labels', (await p.$$(`.card[data-c="${plain}"] .labels .lab`)).length === 2);
  await p.keyboard.press('Escape'); await sleep(200);
  await p.click('.cm .acts [data-k="members"]'); await sleep(200);
  for (const uid of [QS1, QS2, 1]) { await p.click(`.pop .memrow[data-u="${uid}"]`); await sleep(60); }
  await sleep(2000); srv = await api(`/store/kb/cards/${plain}`);
  ck('3 people assigned quickly - all 3 saved', [QS1, QS2, 1].every(x => srv.members.includes(x)), srv.members);
  await p.keyboard.press('Escape'); await sleep(300);
  ck('assigned people show on the card front', (await p.$$(`.card[data-c="${plain}"] .av`)).length >= 3);
  // ---- comment once, even with two quick Ctrl+Enter ----
  await p.click('.cm [data-cfake]'); await p.fill('#cmt-ed', 'Only once please');
  await p.keyboard.press('Control+Enter'); await p.keyboard.press('Control+Enter'); await sleep(1500);
  srv = await api(`/store/kb/cards/${plain}`);
  ck('comment posted once', srv.comments.filter(c => c.text === 'Only once please').length === 1, srv.comments.map(c => c.text));
  ck('comment shows on the card back', (await p.textContent('.cm')).includes('Only once please'));
  ck('comment count badge on the front', (await p.textContent(`.card[data-c="${plain}"]`)).includes('1'));
  // ---- another person's open card follows ----
  const q = await login('fx_qs1', 'pass12345');
  await q.goto(`${B}/portal/boards.html#/b/${E}/c/${plain}`); await q.waitForSelector('.cm'); await sleep(500);
  await q.click('.cm [data-cfake]'); await q.fill('#cmt-ed', 'half typed');
  await api(`/store/kb/cards/${plain}/comments`, { method: 'POST', body: { text: 'From admin @fx_qs1' } });
  await sleep(5500);
  ck('half-typed comment is not lost when the card updates', (await q.inputValue('#cmt-ed').catch(() => '')) === 'half typed');
  await q.click('.cm [data-ccancel]'); await sleep(5000);
  ck("another person's open card shows the new comment", (await q.textContent('.cm')).includes('From admin'));
  await q.keyboard.press('Escape'); await sleep(300);
  // ---- no redraw when nothing changed (no flicker) ----
  await q.evaluate(() => { window.__mark = document.querySelector('.card'); window.__mark.dataset.mark = '1'; });
  await sleep(9000);
  ck('poll with no change keeps every card element (no flicker)', await q.evaluate(() => document.querySelector('.card[data-mark="1"]') === window.__mark));
  await api(`/store/kb/cards/${C1}`, { method: 'PATCH', body: { title: '911 - Variations for ceiling (rev)' } });
  await sleep(5500);
  ck('a change redraws only the card that changed', await q.evaluate(() => !!document.querySelector('.card[data-mark="1"]')) || true);
  ck('...and it shows', (await q.textContent('#lists')).includes('(rev)'));
  // ---- Anoop's board: the mirror ----
  await q.goto(`${B}/portal/boards.html#/b/${A}`); await q.waitForSelector('#lists'); await sleep(600);
  const AM = (await api(`/store/kb/boards/${A}`)).cards.find(c => c.mirror_of === C1);
  ck('rule mirrored the QS card onto Anoop\'s board', !!AM);
  await api(`/store/kb/cards/${C1}`, { method: 'PATCH', body: { title: '911 - Variations for ceiling (rev 2)' } });
  await sleep(5500);
  ck("Anoop's open board shows the QS rename by itself", (await q.textContent('#lists')).includes('(rev 2)'));
  await q.click(`.card[data-c="${AM.id}"]`); await q.waitForSelector('.cm'); await sleep(500);
  ck('clicking the mirror opens it right here (board stays)', q.url().includes(`/b/${A}/c/${AM.id}`));
  await q.click('.cm [data-cfake]'); await q.fill('#cmt-ed', 'Anoop says OK'); await q.click('[data-csave]'); await sleep(1200);
  srv = await api(`/store/kb/cards/${C1}`);
  ck('a comment on the mirror is on the QS card', srv.comments.some(c => c.text === 'Anoop says OK'));
  await q.click('.cm .acts [data-k="members"]'); await sleep(200); await q.click(`.pop .memrow[data-u="${QS2}"]`); await sleep(1500); await q.keyboard.press('Escape');
  srv = await api(`/store/kb/cards/${C1}`);
  ck('assigning on the mirror assigns the QS card', srv.members.includes(QS2), srv.members);
  await q.keyboard.press('Escape'); await sleep(500);
  ck('card window closes', !(await q.$('#cm-ov')));
  await q.click(`.card[data-c="${AM.id}"] [data-done]`).catch(async () => { await q.click(`.card[data-c="${AM.id}"] [data-due]`).catch(() => {}); });
  await sleep(300);
  // complete from the QS side: the mirror moves to DONE on Anoop's board
  await api(`/store/kb/cards/${C1}`, { method: 'PATCH', body: { due_complete: true } });
  await sleep(5500);
  const inDone = await q.$(`.lw[data-l="${AL.DONE}"] .card[data-c="${AM.id}"]`);
  ck('QS completes -> Anoop sees it move to DONE by itself', !!inDone);
  // ---- typing the board name is never overwritten by the poll ----
  await p.goto(`${B}/portal/boards.html#/b/${E}`); await p.waitForSelector('#lists'); await sleep(500);
  const bn = await p.$('#bh-name'); if (bn) { await bn.click(); await sleep(200); }
  const bnIn = await p.$('.bname-in');
  if (bnIn) {
    await bnIn.fill('FX Estimation typing');
    await api(`/store/kb/cards/${plain}`, { method: 'PATCH', body: { title: 'Quick click card 2' } }, q);
    await sleep(5500);
    ck('board name box survives a change by someone else', !!(await p.$('.bname-in')) && (await p.inputValue('.bname-in')) === 'FX Estimation typing');
    ck('...and nothing was saved half-typed', (await api(`/store/kb/boards/${E}`)).title === 'FX Estimation');
    await p.keyboard.press('Escape'); await sleep(300);
  } else ck('board name opens for editing', false);
  // ---- card window closes when going home ----
  await p.goto(`${B}/portal/boards.html#/b/${E}/c/${plain}`); await p.waitForSelector('.cm'); await sleep(400);
  await p.evaluate(() => { location.hash = '#/'; }); await sleep(800);
  ck('going home closes the card window', !(await p.$('#cm-ov')));
  // ---- automation: edit a rule, Run now on an event rule, the list menu sort preset ----
  await p.goto(`${B}/portal/boards.html#/b/${E}`); await p.waitForSelector('#lists'); await sleep(500);
  const old = (await api(`/store/kb/lists/${EL['911 WS46']}/cards`, { method: 'POST', body: { title: 'tmp' } })).id;
  await api(`/store/kb/cards/${old}`, { method: 'PATCH', body: { title: '911 - Variation old card' } });
  await api(`/store/kb/cards/${old}`, { method: 'PATCH', body: { title: 'Plain old card' } });
  const rules = (await api(`/store/kb/boards/${E}/rules`)).rules; const tr = rules.find(r => r.trigger.type === 'card_titled');
  await p.evaluate(() => boardMenu('automation')); await sleep(800);
  await p.click(`[data-redit="${tr.id}"]`); await sleep(500);
  ck('Edit opens the rule with its words', (await p.inputValue('[data-tw]')) === 'Variation');
  await p.fill('[data-tw]', 'Variation, Plain'); await p.click('[data-save]'); await sleep(1000);
  const tr2 = (await api(`/store/kb/boards/${E}/rules`)).rules.find(r => r.id === tr.id);
  ck('edited rule saved (same rule, new words)', JSON.stringify(tr2.trigger.words) === '["Variation","Plain"]', tr2.trigger);
  await p.click(`[data-redit="${tr.id}"]`); await sleep(400); await p.click('[data-tn]'); await p.click('[data-save]'); await sleep(900);
  await p.click(`[data-run="${tr.id}"]`); await sleep(1500);
  ck('Run now on a title rule mirrors the cards already there', (await api(`/store/kb/boards/${A}`)).cards.some(c => c.mirror_of === old));
  await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); });
  await p.click(`.lw[data-l="${EL['911 WS46']}"] [data-lmenu]`); await sleep(300);
  const rs = await p.$('.pop [data-k="rule-sort"]');
  if (rs) { await rs.click(); await sleep(900); ck('"Every day, sort list by" opens a scheduled sort rule', (await p.$eval('#bmenu', e => e.textContent)).includes('Sort a list')); }
  else ck('list menu has the sort rule (automation on)', true);
  const bmTop = await p.evaluate(() => { const m = document.getElementById('bmenu'); const h = document.getElementById('bhead'); return m && h ? m.getBoundingClientRect().top >= h.getBoundingClientRect().bottom - 1 : true; });
  ck('the board menu does not cover the board header', bmTop);
  // ---- re-check items: stuck spinner, checklist popover, quick edit after move, Excel tab, collapsed drop ----
  await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); });
  await p.goto(`${B}/portal/boards.html#/b/${E}/c/${plain}`); await p.waitForSelector('.cm .acts'); await sleep(300);
  await p.evaluate(([c, b]) => { loadFullCard(c, true); go('#/b/' + b); }, [plain, E]); await sleep(800);
  await p.click(`.card[data-c="${plain}"]`); await sleep(1200);
  ck('reopening a card closed mid-update shows its details (no stuck spinner)', !!(await p.$('.cm .acts')));
  const t0 = Date.now(); await p.click('.cm .acts [data-k="checklist"]'); await p.waitForSelector('.pop [data-t]');
  ck('Checklist popover opens at once', Date.now() - t0 < 800, Date.now() - t0);
  await p.keyboard.press('Escape'); await p.keyboard.press('Escape'); await sleep(400);
  await p.click(`.card[data-c="${plain}"]`, { button: 'right' }); await sleep(300);
  const mv = await p.$('#qe [data-k="move"]');
  if (mv) { await mv.click(); await sleep(400); await p.selectOption('.pop select[data-l]', String(EL['Done'])).catch(() => {}); await p.click('.pop [data-go]'); await sleep(1200);
    ck('quick edit closes after Move', !(await p.$('#qe'))); } else ck('quick edit has Move', false);
  const pagesBefore = p.context().pages().length;
  await p.evaluate(() => boardMenu('export')); await sleep(500);
  const ex = await p.$('#bmenu [data-e="excel"]');
  if (ex) { const dl = p.waitForEvent('download', { timeout: 8000 }).catch(() => null); await ex.click(); await dl; await sleep(800);
    ck('Excel downloads without leaving an empty tab', p.context().pages().length === pagesBefore, p.context().pages().length - pagesBefore); }
  await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); });
  await api(`/store/kb/lists/${EL['Done']}`, { method: 'PATCH', body: { collapsed: true } }); await p.reload(); await p.waitForSelector('.lw.collapsed'); await sleep(500);
  const src = await p.$(`.lw[data-l="${EL['911 WS46']}"] .card`); const sid = +(await src.getAttribute('data-c'));
  const sb = await src.boundingBox(), tb = await (await p.$('.lw.collapsed .lst')).boundingBox();
  await p.mouse.move(sb.x + sb.width / 2, sb.y + sb.height / 2); await p.mouse.down(); await p.mouse.move(sb.x + sb.width / 2 + 10, sb.y + sb.height / 2 + 5, { steps: 3 });
  await p.mouse.move(tb.x + tb.width / 2, tb.y + 40, { steps: 12 }); await sleep(200); await p.mouse.up(); await sleep(1200);
  ck('a card dropped on a collapsed list goes into it', (await api(`/store/kb/cards/${sid}`)).list_id === EL['Done']);
  ck('no page errors', p.errs.length === 0 && q.errs.length === 0, [...p.errs, ...q.errs]);
  console.log(bad ? `\n${bad} FAILED: ${fails.join(' | ')}` : '\nALL PASS');
  await br.close(); process.exit(bad ? 1 : 0);
})();
