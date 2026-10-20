const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8072';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const out = [];
const ck = (n, ok, info) => { out.push((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 400))); };
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', 'anoop'); await p.fill('#lg-p', 'pass12345'); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const bid = await p.evaluate(() => S.boards.find(x => x.title === 'Estimation').id);
  await p.evaluate(id => go('#/b/' + id), bid); await p.waitForSelector('#lists .card'); await sleep(700);
  const srvOrder = async lid => (await api(`/store/kb/boards/${bid}`)).cards.filter(c => c.list_id === lid).sort((a, b) => a.pos - b.pos || a.id - b.id).map(c => c.id);
  const domOrder = lid => p.$$eval(`.lw[data-l="${lid}"] .card`, e => e.map(x => +x.dataset.c));
  const drag = async (from, to, opts = {}) => {
    const a = await from.boundingBox(); const sx = a.x + a.width / 2, sy = a.y + Math.min(15, a.height / 2);
    await p.mouse.move(sx, sy); await p.mouse.down(); await p.mouse.move(sx + 10, sy + 10, { steps: 3 });
    const tx = typeof to.x === 'number' ? to : null; let b;
    if (!tx) { b = await to.boundingBox(); }
    const ex = tx ? tx.x : b.x + b.width / 2, ey = tx ? tx.y : (opts.below ? b.y + b.height - 2 : b.y + 3);
    await p.mouse.move(ex, ey, { steps: 15 }); if (opts.hold) await sleep(opts.hold); await sleep(150); await p.mouse.up(); await sleep(1300);
  };
  const lists = await p.evaluate(() => S.lists.map(l => ({ id: l.id, title: l.title, n: cardsOf(l.id).length })));
  const L0 = lists.find(l => l.n >= 4), L1 = lists.find(l => l.id !== L0.id && l.n >= 2);
  // 1 within a list: first card below third
  let before = await domOrder(L0.id);
  let cards = await p.$$(`.lw[data-l="${L0.id}"] .card`);
  await drag(cards[0], cards[2], { below: true });
  let d = await domOrder(L0.id), s = await srvOrder(L0.id);
  ck('within list: dom == server', JSON.stringify(d) === JSON.stringify(s), { d, s });
  ck('within list: card moved down', d.indexOf(before[0]) === 2, { before, d });
  // 2 to another list (right)
  cards = await p.$$(`.lw[data-l="${L0.id}"] .card`); const mv = +(await cards[1].getAttribute('data-c'));
  const tcards = await p.$$(`.lw[data-l="${L1.id}"] .card`);
  await drag(cards[1], tcards[1]);
  s = await srvOrder(L1.id); d = await domOrder(L1.id);
  ck('to other list: lands where dropped (index 1)', s.indexOf(mv) === 1 && d.indexOf(mv) === 1, { s, d, mv });
  ck('to other list: removed from source on server', !(await srvOrder(L0.id)).includes(mv));
  // counts
  const cnt = await p.$eval(`.lw[data-l="${L1.id}"] [data-cnt]`, e => e.textContent);
  ck('list count updated', +cnt === (await srvOrder(L1.id)).length, cnt);
  // 3 to an empty list: create one via API (another user) then drag
  const empty = await api(`/store/kb/boards/${bid}/lists`, { method: 'POST', body: { title: 'ZZ Empty' } });
  await sleep(5000);
  const hasEmpty = await p.$(`.lw[data-l="${empty.id}"]`);
  ck('new list from other user appears by poll', !!hasEmpty);
  // scroll to end and drag first visible card of L0 into it
  await p.evaluate(() => { const w = document.getElementById('lists'); w.scrollLeft = 0; }); await sleep(300);
  cards = await p.$$(`.lw[data-l="${L0.id}"] .card`); const mv2 = +(await cards[0].getAttribute('data-c'));
  // drag to right edge to auto-scroll
  const a = await cards[0].boundingBox();
  await p.mouse.move(a.x + 20, a.y + 10); await p.mouse.down(); await p.mouse.move(a.x + 40, a.y + 20, { steps: 3 });
  await p.mouse.move(1430, 300, { steps: 10 });
  for (let i = 0; i < 80; i++) { const vis = await p.evaluate(id => { const w = document.querySelector(`.lw[data-l="${id}"]`); if (!w) return false; const r = w.getBoundingClientRect(); return r.left < innerWidth - 100 && r.right > 0; }, empty.id); if (vis) break; await sleep(60); }
  const eb = await p.evaluate(id => { const w = document.querySelector(`.lw[data-l="${id}"] .lst`); const r = w.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + 60 }; }, empty.id);
  await p.mouse.move(eb.x, eb.y, { steps: 10 }); await sleep(200);
  const phIn = await p.evaluate(id => !!document.querySelector(`.lw[data-l="${id}"] .ph`), empty.id);
  ck('auto-scroll to off-screen list + placeholder shows in it', phIn);
  await p.mouse.up(); await sleep(1400);
  ck('card dropped into empty off-screen list (server)', (await srvOrder(empty.id)).includes(mv2), await srvOrder(empty.id));
  // 4 list reorder: drag list header of L1 to before L0
  await p.evaluate(() => { document.getElementById('lists').scrollLeft = 0; }); await sleep(300);
  const before2 = (await api(`/store/kb/boards/${bid}`)).lists.map(l => l.id);
  const lh = await p.$(`.lw[data-l="${L1.id}"] .lhd`); const firstL = await p.$(`.lw[data-l]`);
  const hb = await lh.boundingBox(), fb = await firstL.boundingBox();
  await p.mouse.move(hb.x + 30, hb.y + 10); await p.mouse.down(); await p.mouse.move(hb.x + 40, hb.y + 15, { steps: 3 }); await p.mouse.move(fb.x + 20, fb.y + 20, { steps: 15 }); await sleep(200); await p.mouse.up(); await sleep(1400);
  const after2 = (await api(`/store/kb/boards/${bid}`)).lists.map(l => l.id);
  const domL = await p.$$eval('.lw[data-l]', e => e.map(x => +x.dataset.l));
  ck('list reorder: moved to first (server)', after2[0] === L1.id, { before2: before2.slice(0, 4), after2: after2.slice(0, 4) });
  ck('list reorder: dom == server', JSON.stringify(domL) === JSON.stringify(after2), { domL: domL.slice(0, 5), after2: after2.slice(0, 5) });
  // 5 collapsed list drop
  const LC = lists.find(l => ![L0.id, L1.id].includes(l.id) && l.n >= 1);
  await api(`/store/kb/lists/${LC.id}`, { method: 'PATCH', body: { collapsed: true } }); await sleep(4800);
  const col = await p.$(`.lw.collapsed[data-l="${LC.id}"]`); ck('collapsed list shows collapsed (by poll)', !!col);
  if (col) {
    cards = await p.$$(`.lw[data-l="${L0.id}"] .card`); const mv3 = +(await cards[0].getAttribute('data-c'));
    await drag(cards[0], col);
    const inC = (await srvOrder(LC.id)).includes(mv3);
    out.push('INFO drop onto collapsed list -> ' + (inC ? 'moved into it' : 'not accepted (returned)'));
  }
  await api(`/store/kb/lists/${LC.id}`, { method: 'PATCH', body: { collapsed: false } });
  // 6 filtered board drag
  await sleep(4500);
  await p.evaluate(() => { S.filter.q = '906'; applyFilter(); renderHeader(); }); await sleep(300);
  const vis = await p.$$eval(`.lw[data-l="${L0.id}"] .card:not(.filtered-out)`, e => e.map(x => +x.dataset.c));
  out.push('INFO filtered visible in L0: ' + vis.length);
  if (vis.length >= 2) {
    const c1 = await p.$(`.card[data-c="${vis[0]}"]`), c2 = await p.$(`.card[data-c="${vis[vis.length - 1]}"]`);
    await drag(c1, c2, { below: true });
    const so = await srvOrder(L0.id); const visAfter = so.filter(x => vis.includes(x));
    ck('filtered drag: moved after last visible', visAfter[visAfter.length - 1] === vis[0], { vis, visAfter });
    ck('filtered drag: dom == server', JSON.stringify(await domOrder(L0.id)) === JSON.stringify(so));
  }
  await p.evaluate(() => { S.filter = emptyFilter(); applyFilter(); renderHeader(); });
  // 7 drag while another user edits (poll mid-drag)
  cards = await p.$$(`.lw[data-l="${L0.id}"] .card`); const mv4 = +(await cards[0].getAttribute('data-c'));
  const b0 = await cards[0].boundingBox();
  await p.mouse.move(b0.x + 20, b0.y + 10); await p.mouse.down(); await p.mouse.move(b0.x + 40, b0.y + 30, { steps: 3 });
  await api(`/store/kb/cards/${mv4 + 1}`, { method: 'PATCH', body: { title: 'Edited during drag' } });
  await sleep(5000);
  const t2 = await p.$$(`.lw[data-l="${L1.id}"] .card`); const tb = await t2[0].boundingBox();
  await p.mouse.move(tb.x + 50, tb.y + 3, { steps: 10 }); await sleep(150); await p.mouse.up(); await sleep(1500);
  ck('drag survives another user editing meanwhile', (await srvOrder(L1.id)).includes(mv4));
  await sleep(4500);
  ck('...and the other edit shows after', (await p.textContent('#lists')).includes('Edited during drag'));
  // 8 reload: order identical
  const allBefore = await p.evaluate(() => S.lists.map(l => [l.id, [...document.querySelectorAll(`.lw[data-l="${l.id}"] .card`)].map(e => +e.dataset.c)]));
  await p.reload(); await p.waitForSelector('#lists .card'); await sleep(800);
  const allAfter = await p.evaluate(() => S.lists.map(l => [l.id, [...document.querySelectorAll(`.lw[data-l="${l.id}"] .card`)].map(e => +e.dataset.c)]));
  ck('after reload the screen order is identical', JSON.stringify(allBefore) === JSON.stringify(allAfter));
  ck('no page errors', errs.length === 0, errs.slice(0, 5));
  console.log(out.join('\n'));
  await br.close();
})();
