// Board sync, clicked through by two people at once: a QS on Estimation and Anoop on his own board.
// Needs the server on a copy of the live boards (titles "Estimation" and "My Trello board" with the sync set up).
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0; const fails = [];
const ck = (n, ok, info) => { if (!ok) { bad++; fails.push(n); } console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const RUN = String(Date.now()).slice(-5);
(async () => {
  const br = await chromium.launch();
  const login = async (u, pw) => { const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', u); await p.fill('#lg-p', pw); await p.click('#lg-go'); await p.waitForSelector('.home-wrap'); return p; };
  const adm = await login('admin', 'changeme123');
  const api = async (path, opt = {}, pg = adm) => pg.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  for (const u of ['sy_qs', 'sy_anoop']) { const r = await api('/users', { method: 'POST', body: { username: u, password: 'pass12345', role: 'office' } }); if (r.id) await api(`/users/${r.id}/permissions`, { method: 'POST', body: { permissions: 'settings,estimation_boards' } }); }
  const boards = (await api('/store/kb/boards')).boards || (await api('/store/kb/boards'));
  const list = Array.isArray(boards) ? boards : boards.boards;
  const E = list.find(b => b.title === 'Estimation').id, A = list.find(b => b.title === 'My Trello board').id;
  const EB = await api(`/store/kb/boards/${E}`), AB = await api(`/store/kb/boards/${A}`);
  const EL = Object.fromEntries(EB.lists.map(l => [l.title, l.id])), AL = Object.fromEntries(AB.lists.map(l => [l.title, l.id]));
  const qs = await login('sy_qs', 'pass12345'), an = await login('sy_anoop', 'pass12345');
  await qs.goto(`${B}/portal/boards.html#/b/${E}`); await qs.waitForSelector('#lists .card');
  await an.goto(`${B}/portal/boards.html#/b/${A}`); await an.waitForSelector('#lists .card'); await sleep(500);
  // 1. QS adds a task in the 914 list with the composer
  const w = `.lw[data-l="${EL['914VE207']}"]`;
  await qs.click(`${w} [data-add]`); await qs.fill(`${w} .composer textarea`, '914 - Testing new task ' + RUN); await qs.keyboard.press('Enter'); await sleep(600); await qs.keyboard.press('Escape');
  await sleep(5500);
  const otherList = `.lw[data-l="${AL['OTHER TASKS']}"]`;
  ck("QS's new task shows on Anoop's open board by itself (OTHER TASKS)", (await an.textContent(otherList)).includes('914 - Testing new task ' + RUN));
  // 2. QS adds points (description + checklist)
  const qcard = (await api(`/store/kb/boards/${E}`)).cards.find(c => c.title === '914 - Testing new task ' + RUN);
  await qs.click(`.card[data-c="${qcard.id}"]`); await qs.waitForSelector('.cm .acts');
  await qs.click('.cm [data-dedit]'); await qs.fill('#desc-ed', '- confirm FCU count\n- send rates'); await qs.click('[data-dsave]'); await sleep(800);
  await qs.click('.cm .acts [data-k="checklist"]'); await qs.waitForSelector('.pop [data-t]'); await qs.fill('.pop [data-t]', 'Points'); await qs.click('.pop [data-add]'); await sleep(800);
  await qs.click('.cm [data-additem]'); await qs.keyboard.type('Rates from supplier'); await qs.keyboard.press('Enter'); await sleep(800); await qs.keyboard.press('Escape'); await qs.keyboard.press('Escape'); await sleep(5000);
  const acard = (await api(`/store/kb/boards/${A}`)).cards.find(c => c.mirror_of === qcard.id);
  ck("the QS's checklist progress shows on Anoop's card front", (await an.textContent(`.card[data-c="${acard.id}"]`)).includes('0/1'));
  await an.click(`.card[data-c="${acard.id}"]`); await an.waitForSelector('.cm .acts'); await sleep(300);
  ck("Anoop opens it: the QS's points are there", (await an.textContent('.cm')).includes('confirm FCU count') && (await an.textContent('.cm')).includes('Rates from supplier'));
  await an.click('.cm [data-cfake]'); await an.fill('#cmt-ed', 'Anoop: noted'); await an.click('[data-csave]'); await sleep(1000);
  await an.keyboard.press('Escape'); await sleep(300);
  ck("Anoop's comment is on the QS card", (await api(`/store/kb/cards/${qcard.id}`)).comments.some(c => c.text === 'Anoop: noted'));
  // 3. QS ticks it complete on the card front
  await qs.hover(`.card[data-c="${qcard.id}"]`); await sleep(200);
  const done = await qs.$(`.card[data-c="${qcard.id}"] [data-done]`);
  if (done) await done.click(); else await api(`/store/kb/cards/${qcard.id}`, { method: 'PATCH', body: { due_complete: true } }, qs);
  await sleep(5500);
  ck("QS ticks complete -> Anoop's board shows it in DONE by itself", !!(await an.$(`.lw[data-l="${AL['DONE']}"] .card[data-c="${acard.id}"]`)));
  ck("...and on the QS board it stays in 914, complete", (await api(`/store/kb/cards/${qcard.id}`)).list_id === EL['914VE207'] && (await api(`/store/kb/cards/${qcard.id}`)).due_complete);
  // 4. Anoop adds a numbered task in QUANTITY TAKE-OFF
  const aw = `.lw[data-l="${AL['QUANTITY TAKE-OFF']}"]`;
  await an.click(`${aw} [data-add]`); await an.fill(`${aw} .composer textarea`, '912 - Ceiling take-off ' + RUN); await an.keyboard.press('Enter'); await sleep(600); await an.keyboard.press('Escape');
  await sleep(5500);
  ck("Anoop's task shows on the QS board under 912 by itself", (await qs.textContent(`.lw[data-l="${EL['912 Villa']}"]`)).includes('912 - Ceiling take-off ' + RUN));
  // 5. QS adds a variation: goes straight to VARIATIONS & CLAIMS
  await qs.click(`${w} [data-add]`); await qs.fill(`${w} .composer textarea`, '914 - V07 - Extra Lintels ' + RUN); await qs.keyboard.press('Enter'); await sleep(600); await qs.keyboard.press('Escape'); await sleep(5500);
  ck("a variation (V07) goes to VARIATIONS & CLAIMS", (await an.textContent(`.lw[data-l="${AL['VARIATIONS & CLAIMS']}"]`)).includes('914 - V07 - Extra Lintels ' + RUN));
  // 6. the Board sync panel
  await adm.goto(`${B}/portal/boards.html#/b/${E}`); await adm.waitForSelector('#lists'); await sleep(400);
  await adm.evaluate(() => boardMenu('automation')); await sleep(800);
  ck('Automation opens on Board sync with the routes', (await adm.textContent('#bmenu')).includes('Which list a task goes to'));
  await adm.click('#bmenu [data-save]'); await sleep(800);
  ck('saving the sync keeps it', (await api(`/store/kb/boards/${E}/sync`)).conf.board_id === A);
  ck('no page errors', [qs, an, adm].every(p => p.errs.length === 0), [...qs.errs, ...an.errs, ...adm.errs]);
  console.log(bad ? `\n${bad} FAILED: ${fails.join(' | ')}` : '\nALL PASS');
  await br.close(); process.exit(bad ? 1 : 0);
})();
