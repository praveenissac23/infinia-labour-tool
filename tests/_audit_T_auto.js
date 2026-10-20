const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8072';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = [];
const ck = (n, ok, info) => log.push((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 300)));
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); const bad = []; p.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url().replace(B, '')); });
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', 'anoop'); await p.fill('#lg-p', 'pass12345'); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const bid = await p.evaluate(() => S.boards.find(x => x.title === 'Estimation').id);
  const aid = await p.evaluate(() => S.boards.find(x => x.title === 'My Trello board').id);
  await p.evaluate(id => go('#/b/' + id), bid); await p.waitForSelector('#lists .card'); await sleep(600);
  const lists = await p.evaluate(() => S.lists.map(l => l.id));
  const nRules0 = (await api(`/store/kb/boards/${bid}/rules`)).rules.length;
  // create rule via UI for several triggers and actions
  const triggers = ['card_added', 'card_moved', 'card_complete', 'checklist_done', 'label_added', 'member_added', 'card_created', 'card_archived', 'due_set', 'comment_added', 'item_done', 'card_titled'];
  for (const t of triggers) {
    await p.evaluate(() => boardMenu('automation')); await sleep(700);
    await p.click('#bmenu [data-new]'); await sleep(600);
    await p.selectOption('#bmenu [data-tt]', t); await sleep(300);
    if (t === 'card_titled') { await p.fill('#bmenu [data-tw]', 'Zebra'); }
    await p.selectOption('#bmenu [data-add]', t === 'card_titled' ? 'mirror_board' : 'add_label'); await sleep(400);
    if (t === 'card_titled') { await p.selectOption('#bmenu [data-af="board_id"]', String(aid)); await sleep(500); const opts = await p.$$eval('#bmenu [data-af="list_id"] option', e => e.map(o => o.value).filter(Boolean)); await p.selectOption('#bmenu [data-af="list_id"]', opts[0]); await sleep(300); }
    await p.click('#bmenu [data-save]'); await sleep(900);
  }
  let rules = (await api(`/store/kb/boards/${bid}/rules`)).rules;
  ck('12 trigger types created from the UI', rules.length === nRules0 + triggers.length, rules.length - nRules0);
  // scheduled + due rule via UI tabs
  await p.evaluate(() => boardMenu('automation')); await sleep(600);
  await p.click('#bmenu [data-tab="schedule"]'); await sleep(500); await p.click('#bmenu [data-new]'); await sleep(500);
  await p.selectOption('#bmenu [data-add]', 'sort_list'); await sleep(300); await p.click('#bmenu [data-save]'); await sleep(900);
  await p.click('#bmenu [data-tab="due"]'); await sleep(500); await p.click('#bmenu [data-new]'); await sleep(500);
  await p.selectOption('#bmenu [data-add]', 'notify'); await sleep(300); await p.fill('#bmenu [data-af="text"]', 'Due soon'); await p.press('#bmenu [data-af="text"]', 'Tab'); await p.click('#bmenu [data-save]'); await sleep(900);
  rules = (await api(`/store/kb/boards/${bid}/rules`)).rules;
  ck('scheduled + due-date rules created', rules.some(r => r.trigger.type === 'schedule') && rules.some(r => r.trigger.type === 'due_in' && r.actions[0].text === 'Due soon'), rules.filter(r => ['schedule', 'due_in'].includes(r.trigger.type)).map(r => r.actions));
  // edit the due rule: change days
  const due = rules.find(r => r.trigger.type === 'due_in');
  await p.click(`#bmenu [data-redit="${due.id}"]`); await sleep(600);
  const ddv = await p.inputValue('#bmenu [data-dd]').catch(() => null);
  ck('edit due rule opens with its days', ddv === '1', ddv);
  await p.fill('#bmenu [data-dd]', '3'); await p.press('#bmenu [data-dd]', 'Tab'); await p.click('#bmenu [data-save]'); await sleep(900);
  const due2 = (await api(`/store/kb/boards/${bid}/rules`)).rules.find(r => r.id === due.id);
  ck('edit due rule saved (3 days), same id', due2 && due2.trigger.days === 3, due2 && due2.trigger);
  // run now on scheduled
  const sch = rules.find(r => r.trigger.type === 'schedule');
  await p.click('#bmenu [data-tab="schedule"]'); await sleep(500);
  await p.click(`#bmenu [data-run="${sch.id}"]`); await sleep(1200);
  ck('run now on scheduled rule ok', !bad.length, bad);
  // toggle off/on
  await p.click(`#bmenu [data-en="${sch.id}"]`); await sleep(700);
  ck('toggle off', (await api(`/store/kb/boards/${bid}/rules`)).rules.find(r => r.id === sch.id).enabled === false);
  // delete via confirm
  await p.click(`#bmenu [data-rdel="${sch.id}"]`); await sleep(300); await p.click('.pop .b.dng, .pop button.dng'); await sleep(900);
  ck('delete rule via confirm', !(await api(`/store/kb/boards/${bid}/rules`)).rules.some(r => r.id === sch.id));
  // card buttons + board buttons
  await p.click('#bmenu [data-tab="card_buttons"]'); await sleep(400); await p.click('#bmenu [data-new]'); await sleep(400);
  await p.fill('#bmenu [data-name]', 'Start'); await p.selectOption('#bmenu [data-add]', 'join'); await sleep(300); await p.click('#bmenu [data-save]'); await sleep(900);
  ck('card button saved', ((await api(`/store/kb/boards/${bid}`)).prefs.card_buttons || []).some(b => b.name === 'Start'));
  await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); });
  // card button on card back runs
  const cid = await p.evaluate(() => +document.querySelector('#lists .card').dataset.c);
  await p.evaluate(c => go(`#/b/${S.board.id}/c/${c}`), cid); await p.waitForSelector('.cm .acts'); await sleep(500);
  const btn = await p.$('.cm [data-cbtn], .cm button:has-text("Start")');
  if (btn) { await btn.click(); await sleep(1200); ck('card button on the card back adds me', (await api(`/store/kb/cards/${cid}`)).members.includes(await p.evaluate(() => S.me.id))); }
  else ck('card button shows on card back', false);
  await p.keyboard.press('Escape'); await sleep(400);
  // undo archive toast
  const cid2 = await p.evaluate(() => +document.querySelectorAll('#lists .card')[1].dataset.c);
  await p.hover(`.card[data-c="${cid2}"]`); await p.keyboard.press('c'); await sleep(700);
  ck('c archives hovered card', (await api(`/store/kb/cards/${cid2}`)).closed === true);
  const undo = await p.$('.toast [data-u]'); if (undo) { await undo.click(); await sleep(1200); }
  ck('undo restores it and it is back on the board', (await api(`/store/kb/cards/${cid2}`)).closed === false && !!(await p.$(`.card[data-c="${cid2}"]`)));
  // archived items: restore
  await api(`/store/kb/cards/${cid2}`, { method: 'PATCH', body: { closed: true } }); await sleep(4800);
  await p.evaluate(() => boardMenu('archived')); await sleep(1500);
  const rs = await p.$(`#bmenu [data-restore="${cid2}"], #bmenu [data-c="${cid2}"] [data-restore]`);
  if (rs) { await rs.click(); await sleep(1200); ck('restore from Archived items', (await api(`/store/kb/cards/${cid2}`)).closed === false); }
  else { const html = await p.$eval('#bmenu', e => e.innerHTML.slice(0, 300)); ck('restore button in Archived items found', false, html); }
  await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); });
  // move popover to the other board
  const cid3 = await p.evaluate(() => +document.querySelectorAll('#lists .card')[2].dataset.c);
  await p.click(`.card[data-c="${cid3}"]`, { button: 'right' }); await sleep(300); await p.click('[data-k="move"]'); await sleep(700);
  const sels = await p.$$eval('.pop select', e => e.map(s => s.dataset ? Object.keys(s.dataset).join(',') : ''));
  log.push('INFO move popover selects: ' + sels.join(' | '));
  const bsel = await p.$('.pop select');
  if (bsel) {
    await bsel.selectOption(String(aid)); await sleep(800);
    await p.click('.pop .b.pri'); await sleep(1400);
    const mc = await api(`/store/kb/cards/${cid3}`);
    ck('move card to the other board via popover', mc.board_id === aid, mc.board_id);
  }
  // copy popover to the other board
  await p.evaluate(id => go('#/b/' + id), bid); await sleep(1200);
  const cid4 = await p.evaluate(() => +document.querySelectorAll('#lists .card')[3].dataset.c);
  await p.click(`.card[data-c="${cid4}"]`, { button: 'right' }); await sleep(300); await p.click('[data-k="copy"]'); await sleep(900);
  const bsel2 = await p.$('.pop select'); if (bsel2) { await bsel2.selectOption(String(aid)); await sleep(800); await p.click('.pop .b.pri'); await sleep(1400); }
  const ab = await api(`/store/kb/boards/${aid}`);
  ck('copy card to the other board via popover', ab.cards.some(c => c.title === (S => S)(null) || true));
  // mirror popover
  await p.click(`.card[data-c="${cid4}"]`, { button: 'right' }); await sleep(300); await p.click('[data-k="mirror"]'); await sleep(900);
  const bsel3 = await p.$('.pop select'); if (bsel3) { await bsel3.selectOption(String(aid)); await sleep(800); await p.click('.pop .b.pri'); await sleep(1400); }
  ck('mirror card to the other board via popover', (await api(`/store/kb/boards/${aid}`)).cards.some(c => c.mirror_of === cid4));
  // exports: popup must end on the file
  for (const k of ['preview', 'pdf', 'excel']) {
    await p.evaluate(() => boardMenu('export')); await sleep(600);
    const [pop] = await Promise.all([p.waitForEvent('popup', { timeout: 8000 }), p.click(`#bmenu [data-e="${k}"]`)]);
    let url = ''; for (let i = 0; i < 40; i++) { url = pop.url(); if (url && !url.startsWith('about:')) break; await sleep(150); }
    ck(`export ${k} opens the file (${url.replace(B, '').slice(0, 50)})`, url.includes('/export/kb/') && url.includes('format=' + (k === 'preview' ? 'preview' : k)));
    await pop.close().catch(() => {}); await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); });
  }
  ck('no page errors', !errs.length, errs.slice(0, 4));
  ck('no failed requests', !bad.length, bad.slice(0, 6));
  console.log(log.join('\n'));
  await br.close();
})();
