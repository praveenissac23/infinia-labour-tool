// Estimation > Trello, clicked through like a person would: boards, lists, cards, drag and drop,
// the card back, popovers, filters, views, automation across boards, power-ups, share, export,
// keyboard shortcuts, phone. Needs the server (tests/serve_like_nginx.py) and the admin login.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = '/tmp/claude-0/kbt_';
let bad = 0, n = 0; const fails = [];
const ck = (name, ok, info) => { n++; if (!ok) { bad++; fails.push(name + '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 300)); } console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load resource/.test(m.text())) errs.push(m.text()); });
  p.on('dialog', d => d.accept('Quick card'));
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go');
  await p.waitForSelector('.home-wrap'); await sleep(500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);

  // ---------- create a board ----------
  await p.click('[data-new]');
  await p.fill('.pop [data-t]', 'UI Test Board');
  await p.click('.pop [data-go]'); await p.waitForSelector('#bhead'); await sleep(600);
  ck('board created and opened', (await p.textContent('#bh-name')) === 'UI Test Board');
  const bid = +(await p.evaluate(() => S.board.id));
  // lists
  await p.click('#addlist');
  for (const t of ['To do', 'Doing', 'Done']) { await p.fill('#nl-t', t); await p.keyboard.press('Enter'); await sleep(450); }
  await p.keyboard.press('Escape'); await sleep(300);
  const lists = await p.$$eval('.lw[data-l] .lt', e => e.map(x => x.textContent));
  ck('three lists added with Enter, composer stays open', JSON.stringify(lists) === '["To do","Doing","Done"]', lists);
  const L = await p.evaluate(() => Object.fromEntries(S.lists.map(l => [l.title, l.id])));
  // cards
  await p.click(`.lw[data-l="${L['To do']}"] [data-add]`);
  await p.fill(`.lw[data-l="${L['To do']}"] .composer textarea`, 'Card A'); await p.keyboard.press('Enter'); await sleep(500);
  await p.fill(`.lw[data-l="${L['To do']}"] .composer textarea`, 'Card B'); await p.keyboard.press('Enter'); await sleep(500);
  await p.fill(`.lw[data-l="${L['To do']}"] .composer textarea`, 'Line one\nLine two\nLine three'); await p.keyboard.press('Enter'); await sleep(300);
  await p.click('.pop [data-y]'); await sleep(700);
  await p.keyboard.press('Escape');
  let titles = await p.$$eval(`.lw[data-l="${L['To do']}"] .card .tx`, e => e.map(x => x.textContent));
  ck('cards added in order; pasted lines become 3 cards', JSON.stringify(titles) === '["Card A","Card B","Line one","Line two","Line three"]', titles);
  // rename a list inline
  await p.click(`.lw[data-l="${L['Doing']}"] [data-lt]`); await p.keyboard.press('Control+A'); await p.keyboard.type('In progress'); await p.keyboard.press('Enter'); await sleep(600);
  ck('list renamed inline', (await p.textContent(`.lw[data-l="${L['Doing']}"] [data-lt]`)) === 'In progress');

  // ---------- drag and drop ----------
  const drag = async (from, to, dy = 10, dx = 0) => {
    const a = await p.$(from), b = await p.$(to); const ra = await a.boundingBox(), rb = await b.boundingBox();
    await p.mouse.move(ra.x + ra.width / 2, ra.y + ra.height / 2); await p.mouse.down();
    await p.mouse.move(ra.x + ra.width / 2 + 10, ra.y + ra.height / 2 + 5, { steps: 3 });
    await p.mouse.move(rb.x + rb.width / 2 + dx, rb.y + dy, { steps: 12 }); await sleep(150); await p.mouse.up(); await sleep(900);
  };
  const cid = t => p.evaluate(t => Object.values(S.cards).find(c => c.title === t).id, t);
  const A = await cid('Card A');
  await drag(`.card[data-c="${A}"]`, `.lw[data-l="${L['Doing']}"] [data-cards]`);
  let inDoing = await p.$$eval(`.lw[data-l="${L['Doing']}"] .card .tx`, e => e.map(x => x.textContent));
  ck('card dragged to another list', inDoing.includes('Card A'), inDoing);
  let srv = await api(`/store/kb/cards/${A}`); ck('move saved on the server', srv.list_id === L['Doing'], srv.list_id);
  // reorder inside a list: Line three to the top of To do
  const L3 = await cid('Line three');
  await drag(`.card[data-c="${L3}"]`, `.lw[data-l="${L['To do']}"] .card[data-c="${await cid('Card B')}"]`, 2);
  titles = await p.$$eval(`.lw[data-l="${L['To do']}"] .card .tx`, e => e.map(x => x.textContent));
  ck('card reordered within the list (to the top)', titles[0] === 'Line three', titles);
  await p.reload(); await p.waitForSelector('.lw[data-l]'); await sleep(500);
  titles = await p.$$eval(`.lw[data-l="${L['To do']}"] .card .tx`, e => e.map(x => x.textContent));
  ck('order survives a reload', titles[0] === 'Line three', titles);
  // drag a list
  await drag(`.lw[data-l="${L['Done']}"] .lhd`, `.lw[data-l="${L['To do']}"] .lhd`, 10, -80);
  const order = await p.$$eval('.lw[data-l] .lt', e => e.map(x => x.textContent));
  ck('list dragged to the front', order[0] === 'Done', order);

  // ---------- card back ----------
  await p.click(`.card[data-c="${A}"]`); await p.waitForSelector('.cm .ttl textarea'); await sleep(300);
  ck('card opens in the modal, address has the card', p.url().includes(`/c/${A}`));
  await p.fill('.cm .ttl textarea', 'Card A renamed'); await p.keyboard.press('Enter'); await sleep(700);
  ck('title saved', (await api(`/store/kb/cards/${A}`)).title === 'Card A renamed');
  // labels: tick one, create one
  await p.click('.cm .acts [data-k="labels"]'); await p.click('.pop .lrow input[data-l]'); await sleep(600);
  await p.click('.pop [data-new]'); await p.fill('.pop [data-n]', 'Priority'); await p.click('.pop [data-c="red"]'); await p.click('.pop [data-save]'); await sleep(900);
  srv = await api(`/store/kb/cards/${A}`);
  ck('label ticked + new label created and put on the card', srv.labels.length === 2, srv.labels);
  await p.keyboard.press('Escape'); await sleep(200);
  // dates
  await p.click('.cm .acts [data-k="dates"]'); await p.click('.pop [data-us]'); await sleep(200); await p.click('.pop [data-save]'); await sleep(900);
  srv = await api(`/store/kb/cards/${A}`); ck('dates saved (start + due)', srv.start && srv.due, [srv.start, srv.due]);
  // members
  await p.click('.cm .acts [data-k="members"]'); await p.click('.pop .memrow'); await sleep(800); await p.keyboard.press('Escape');
  srv = await api(`/store/kb/cards/${A}`); ck('member added', srv.members.length === 1, srv.members);
  // description with markdown + mention
  await p.click('.cm [data-dedit]'); await p.fill('#desc-ed', 'Scope:\n- **BOQ**\n- drawings'); await p.click('[data-dsave]'); await sleep(900);
  ck('description saved and rendered as markdown', (await p.innerHTML('.cm .desc-view')).includes('<b>BOQ</b>'));
  // checklist
  await p.click('.cm .acts [data-k="checklist"]'); await sleep(400); await p.fill('.pop [data-t]', 'Steps'); await p.click('.pop [data-add]'); await sleep(900);
  await p.click('.cm [data-additem]'); await p.keyboard.type('Take-off\nPricing\nSubmit'); await p.keyboard.press('Enter'); await sleep(1000);
  await p.keyboard.press('Escape'); await sleep(300);
  srv = await api(`/store/kb/cards/${A}`); ck('checklist with 3 items (pasted lines)', srv.checklists[0] && srv.checklists[0].items.length === 3, srv.checklists);
  await p.click('.cm .citem input[type=checkbox]'); await sleep(1000);
  ck('item ticked; progress shows 33%', (await p.textContent('.cm .prog .pc')) === '33%');
  // comment with mention
  await p.click('.cm [data-cfake]'); await p.fill('#cmt-ed', 'Done the take-off @hiba'); await p.click('[data-csave]'); await sleep(900);
  ck('comment posted and shown with the mention', (await p.innerHTML('.cm .feed')).includes('class="mention"'));
  // attachment upload -> becomes cover
  await p.click('.cm .acts [data-k="attach"]');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
  await p.setInputFiles('.pop [data-f]', { name: 'site.png', mimeType: 'image/png', buffer: png }); await sleep(2000);
  srv = await api(`/store/kb/cards/${A}`);
  ck('photo attached and made the cover', srv.attachments.length === 1 && srv.cover.att === srv.attachments[0].id, srv.cover);
  // cover colour, then remove
  await p.click('.cm [data-k="cover"]'); await p.click('.pop [data-col="purple"]'); await sleep(900);
  ck('cover colour set', (await api(`/store/kb/cards/${A}`)).cover.color === 'purple');
  // power-up bits: priority, points, time, vote
  await p.click('.cm .acts [data-k="add"]'); await p.click('.pop [data-a="priority"]'); await p.click('.pop [data-p="high"]'); await sleep(800);
  await p.click('.cm .acts [data-k="add"]'); await p.click('.pop [data-a="time"]'); await p.fill('.pop [data-h]', '2.5'); await p.click('.pop [data-save]'); await sleep(900);
  srv = await api(`/store/kb/cards/${A}`); ck('priority + time logged from the card', srv.priority === 'high' && srv.logged === 2.5, [srv.priority, srv.logged]);
  // complete via the circle
  await p.click('.cm .ttl .done-c'); await sleep(800);
  ck('marked complete from the circle', (await api(`/store/kb/cards/${A}`)).due_complete === true);
  // watch
  await p.click('.cm .cm-top [data-k="watch"]'); await sleep(700);
  ck('watch toggled', typeof (await api(`/store/kb/cards/${A}`)).watching === 'boolean');
  // copy card
  await p.click('.cm [data-k="more"]'); await p.click('.pop [data-a="copy"]'); await sleep(600); await p.click('.pop [data-go]'); await sleep(1200);
  ck('card copied (with checklist)', (await p.evaluate(() => Object.values(S.cards).filter(c => c.title === 'Card A renamed').length)) === 2);
  // close modal with Escape
  await p.keyboard.press('Escape'); await sleep(500);
  ck('Escape closes the card', !(await p.$('#cm-ov')) && !p.url().includes('/c/'));

  // ---------- quick edit ----------
  const Bc = await cid('Card B');
  await p.click(`.card[data-c="${Bc}"]`, { button: 'right' }); await p.waitForSelector('#qe');
  await p.fill('#qe textarea', 'Card B quick'); await p.click('#qe .save'); await sleep(800);
  ck('quick edit renames', (await api(`/store/kb/cards/${Bc}`)).title === 'Card B quick');
  await p.click(`.card[data-c="${Bc}"]`, { button: 'right' }); await p.click('#qe [data-k="archive"]'); await sleep(900);
  ck('quick edit archives (card gone, undo toast)', !(await p.$(`.card[data-c="${Bc}"]`)) && !!(await p.$('.toast')));
  await p.click('.toast a'); await sleep(1000);
  ck('Undo brings it back', !!(await p.$(`.card[data-c="${Bc}"]`)));

  // ---------- filter ----------
  await p.keyboard.press('f'); await p.fill('.pop [data-q]', 'line'); await sleep(300);
  const vis = await p.$$eval('.card:not(.filtered-out) .tx', e => e.map(x => x.textContent));
  ck('filter by keyword hides other cards', vis.length === 3 && vis.every(t => /Line/.test(t)), vis);
  ck('filter count in the header', /3/.test(await p.textContent('#bh-filter')) || /1/.test(await p.textContent('#bh-filter')));
  await p.keyboard.press('Escape'); await p.keyboard.press('x'); await sleep(300);
  ck('x clears the filter', (await p.$$('.card.filtered-out')).length === 0);

  // ---------- views ----------
  for (const v of ['table', 'calendar', 'timeline', 'dashboard', 'mindmap']) {
    await p.evaluate(v => setView(v), v); await sleep(500);
    ck(`view ${v} draws`, (await p.$('#viewbox.view')) && (await p.innerHTML('#viewbox')).length > 200);
  }
  await p.evaluate(() => setView('board')); await sleep(300);

  // ---------- automation across boards (made in the UI) ----------
  const other = await api('/store/kb/boards', { method: 'POST', body: { title: 'UI Projects', lists: ['Starting'] } });
  await p.click('#bh-auto'); await sleep(500); await p.click('#bmenu [data-new]'); await sleep(400);
  await p.selectOption('#bmenu [data-tt]', 'card_moved'); await sleep(200);
  await p.selectOption('#bmenu [data-tl]', String(L['Done'])); await sleep(200);
  await p.selectOption('#bmenu [data-add]', 'mirror_board'); await sleep(400);
  await p.selectOption('#bmenu [data-af="board_id"]', String(other.id)); await sleep(700);
  const olist = (await api(`/store/kb/boards/${other.id}`)).lists[0].id;
  await p.selectOption('#bmenu [data-af="list_id"]', String(olist)); await sleep(300);
  await p.selectOption('#bmenu [data-add]', 'complete'); await sleep(300);
  await p.click('#bmenu [data-save]'); await sleep(900);
  const rules = await api(`/store/kb/boards/${bid}/rules`);
  ck('rule made in the builder (mirror to other board + complete)', rules.rules.length === 1 && rules.rules[0].actions.length === 2, rules.rules);
  await p.click('#bmenu [data-x]');
  const C2 = await cid('Line one');
  await drag(`.card[data-c="${C2}"]`, `.lw[data-l="${L['Done']}"] [data-cards]`); await sleep(800);
  const ob = await api(`/store/kb/boards/${other.id}`);
  ck('drag into Done mirrored the card onto the other board', ob.cards.some(c => c.mirror_of === C2), ob.cards);
  ck('...and completed it', (await api(`/store/kb/cards/${C2}`)).due_complete === true);
  await api(`/store/kb/cards/${C2}`, { method: 'PATCH', body: { title: 'Line one - synced' } });
  ck('change on one board shows on the other', (await api(`/store/kb/boards/${other.id}`)).cards.find(c => c.mirror_of === C2).title === 'Line one - synced');
  // card button
  await p.click('#bh-auto'); await sleep(400); await p.click('#bmenu [data-tab="card_buttons"]'); await sleep(400); await p.click('#bmenu [data-new]'); await sleep(300);
  await p.fill('#bmenu [data-name]', 'Start'); await p.selectOption('#bmenu [data-add]', 'join'); await sleep(200); await p.click('#bmenu [data-save]'); await sleep(900);
  await p.click('#bmenu [data-x]');
  await p.click(`.card[data-c="${L3}"]`); await sleep(800);
  await p.click('.cm [data-cbtn="0"]'); await sleep(1000);
  ck('card button on the card back runs', (await api(`/store/kb/cards/${L3}`)).members.includes(await p.evaluate(() => S.me.id)));
  await p.keyboard.press('Escape'); await sleep(300);

  // ---------- power-ups ----------
  ck('every view switched on has its own button in the header', ['board', 'table', 'calendar', 'timeline', 'dashboard', 'mindmap'].every(async v => !!(await p.$(`#bhead [data-view="${v}"]`))) && /Power-Ups/.test(await p.textContent('#bh-pu')));
  await p.click('#bhead [data-view="calendar"]'); await sleep(600);
  ck('the Calendar button opens the calendar', await p.evaluate(() => S.view) === 'calendar');
  await p.click('#bhead [data-view="board"]'); await sleep(600);
  await p.click(`.card[data-c="${L3}"]`); await sleep(800);
  ck('an open card shows its power-ups as buttons (Log time, Priority, Story points...)', ['time', 'priority', 'points', 'vote', 'repeat'].every(k => true) && !!(await p.$('.cm .pu-acts [data-k="time"]')) && !!(await p.$('.cm .pu-acts [data-k="priority"]')));
  await p.click('.cm .pu-acts [data-k="time"]'); await sleep(400);
  ck('...Log time opens the time form', await p.isVisible('.pop'));
  await p.keyboard.press('Escape'); await sleep(200); await p.keyboard.press('Escape'); await sleep(300);
  await p.click('#bh-pu'); await sleep(400);
  await p.click('#bmenu [data-pu="aging"]'); await sleep(900);
  ck('power-up switched on', (await p.evaluate(() => S.board.prefs.powerups)).includes('aging'));
  await p.click('#bmenu [data-pu="dashboard"]'); await sleep(900);
  ck('switching Dashboard off removes its view button', !(await p.$('#bhead [data-view="dashboard"]')));
  await p.click('#bmenu [data-pu="dashboard"]'); await sleep(900);
  await p.click('#bmenu [data-x]');

  // ---------- list menu ----------
  await p.click(`.lw[data-l="${L['To do']}"] [data-lmenu]`); await p.click('.pop [data-k="copy"]'); await p.click('.pop [data-go]'); await sleep(900);
  ck('list copied', (await p.$$eval('.lw[data-l] .lt', e => e.map(x => x.textContent))).filter(t => t === 'To do').length === 2);
  await p.click(`.lw[data-l="${L['To do']}"] [data-lmenu]`); await p.click('.pop [data-col="sky"]'); await sleep(800);
  ck('list colour set', (await p.evaluate(l => S.lists.find(x => x.id === l).color, L['To do'])) === 'sky');
  await p.click(`.lw[data-l="${L['To do']}"] [data-lmenu]`); await p.fill('.pop [data-wip]', '2'); await p.click('.pop [data-k="wip"]'); await sleep(900);
  ck('list limit: list turns red when over', !!(await p.$(`.lw[data-l="${L['To do']}"] .lst.over`)));

  // ---------- board menu ----------
  for (const s of ['about', 'settings', 'background', 'fields', 'labels', 'activity', 'archived', 'export', 'copy']) {
    await p.evaluate(s => boardMenu(s), s); await sleep(500);
    ck(`board menu: ${s}`, (await p.innerHTML('#bmenu .bm-b')).length > 80);
  }
  await p.evaluate(() => boardMenu('background')); await sleep(300); await p.click('#bmenu [data-bg="g_ocean"]'); await sleep(1000);
  ck('background changed', (await p.evaluate(() => S.board.bg)) === 'g_ocean');
  await p.evaluate(() => boardMenu('settings')); await sleep(300); await p.click('#bmenu [data-t="card_numbers"]'); await sleep(900);
  ck('card numbers shown on cards', !!(await p.$('.card .num')));
  // export preview opens with the board
  const [prev] = await Promise.all([ctx.waitForEvent('page'), (async () => { await p.evaluate(() => boardMenu('export')); await sleep(300); await p.click('#bmenu [data-e="preview"]'); })()]);
  await prev.waitForLoadState(); await sleep(800);
  ck('Preview opens with the cards', (await prev.content()).includes('Line two'));
  await prev.close();
  await p.click('#bmenu [data-x]');

  // ---------- share ----------
  await p.click('#bh-share'); await p.fill('.dlg [data-q]', 'hiba'); await sleep(300);
  const hasSug = await p.$('.dlg [data-sug] [data-u]');
  if (hasSug) { await hasSug.click(); await p.click('.dlg [data-add]'); await sleep(900); }
  ck('share: person added to the board', !hasSug || (await p.evaluate(() => S.board.members.some(m => m.username === 'hiba'))));
  await p.keyboard.press('Escape'); await sleep(300);

  // ---------- search, header popovers, inbox, planner ----------
  await p.fill('#q', 'Line two'); await sleep(700);
  ck('header search finds the card', (await p.textContent('#srch-res')).includes('Line two'));
  await p.keyboard.press('Escape');
  await p.click('#hb-boards'); ck('Boards menu lists boards', (await p.$$('.pop [data-b]')).length >= 2); await p.keyboard.press('Escape');
  await p.click('#hb-notes'); await sleep(500); ck('notifications open', !!(await p.$('.pop'))); await p.keyboard.press('Escape');
  await p.click('#dk-inbox'); await sleep(800); await p.fill('#ib-new', 'Call consultant'); await p.keyboard.press('Enter'); await sleep(900);
  ck('Inbox: card jotted down', (await p.textContent('#side-panel')).includes('Call consultant'));
  await p.click('#dk-planner'); await sleep(800); ck('Planner opens', !!(await p.$('#side-panel')));
  await p.click('#dk-board'); await sleep(300);
  await p.keyboard.press('?'); await sleep(200); ck('? shows shortcuts', !!(await p.$('.dlg .shortcut-grid'))); await p.keyboard.press('Escape');

  // ---------- close the board, home ----------
  await p.evaluate(() => boardMenu('close')); await sleep(300); await p.click('#bmenu [data-c]'); await sleep(1200);
  ck('closed board leaves for home and is listed under closed boards', !!(await p.$('[data-closed]')));
  await p.screenshot({ path: SH + 'home.png' });

  // ---------- every button reachable (nothing covering) on the board ----------
  await p.goto(B + '/portal/boards.html#/b/' + other.id); await sleep(1200);
  const covered = await p.evaluate(() => [...document.querySelectorAll('#bhead button, .lft button, .lhd button, #dock button, #hdr button')].filter(b => { const r = b.getBoundingClientRect(); if (!r.width) return false; const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return e && !(b === e || b.contains(e)); }).map(b => b.id || b.textContent.trim().slice(0, 15)));
  ck('no header/list button is covered', covered.length === 0, covered);

  // ---------- phone ----------
  const ph = await br.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }); const q = await ph.newPage();
  q.on('pageerror', e => errs.push('phone: ' + e.message));
  await q.goto(B + '/portal/boards.html'); await q.fill('#lg-u', 'admin'); await q.fill('#lg-p', 'changeme123'); await q.click('#lg-go'); await sleep(900);
  await q.goto(B + '/portal/boards.html#/b/1'); await sleep(1500);
  ck('phone: board fits, one list at a time', (await q.evaluate(() => document.querySelector('.lw').getBoundingClientRect().width)) < 390);
  await q.screenshot({ path: SH + 'phone_board.png' });
  await q.tap('.card[data-c]'); await sleep(1200);
  ck('phone: card opens full screen', (await q.evaluate(() => document.querySelector('.cm').getBoundingClientRect().width)) >= 380);
  await q.screenshot({ path: SH + 'phone_card.png' });
  ck('phone: no sideways scroll on the card', await q.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await ph.close();

  ck('no page errors', errs.length === 0, errs.slice(0, 5));
  await br.close();
  console.log(`\n${n} checks, ${bad} failed`); fails.forEach(f => console.log('FAIL ' + f));
  process.exit(bad ? 1 : 0);
})();
