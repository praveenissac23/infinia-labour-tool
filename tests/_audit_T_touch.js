const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8072';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', 'anoop'); await p.fill('#lg-p', 'pass12345'); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
  const api = async (path) => p.evaluate(async (path) => (await fetch(path, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), path);
  const bid = await p.evaluate(() => S.boards.find(x => x.title === 'Estimation').id);
  await p.evaluate(id => go('#/b/' + id), bid); await p.waitForSelector('#lists .card'); await sleep(800);
  const cdp = await ctx.newCDPSession(p);
  const tp = (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y }] });
  const lids = await p.evaluate(() => S.lists.filter(l => cardsOf(l.id).length >= 2).map(l => l.id));
  // list A is the first visible; target is next list (off screen to the right on a phone)
  const LA = lids[0], LB = await p.evaluate(a => { const i = S.lists.findIndex(l => l.id === a); return S.lists[i + 1].id; }, LA);
  const card = await p.$(`.lw[data-l="${LA}"] .card`); const mv = +(await card.getAttribute('data-c')); const r = await card.boundingBox();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  await tp('touchStart', x, y); await sleep(450);
  // move to right edge and hold so auto-scroll brings the next list
  for (let i = 1; i <= 10; i++) { await tp('touchMove', x + (380 - x) * i / 10, y + 40 * i / 10); await sleep(30); }
  for (let i = 0; i < 60; i++) { await tp('touchMove', 380 + (i % 2), y + 40); await sleep(50); const ok = await p.evaluate(id => { const w = document.querySelector(`.lw[data-l="${id}"]`); const q = w.getBoundingClientRect(); return q.left < 200; }, LB); if (ok) break; }
  const tb = await p.evaluate(id => { const w = document.querySelector(`.lw[data-l="${id}"] .lst`).getBoundingClientRect(); return { x: w.left + w.width / 2, y: w.top + 80 }; }, LB);
  for (let i = 1; i <= 8; i++) { await tp('touchMove', 380 - (380 - tb.x) * i / 8, y + 40 + (tb.y - y - 40) * i / 8); await sleep(30); }
  const st = await p.evaluate(() => ({ drag: !!window.DRAG, ph: window.DRAG && window.DRAG.ph.closest('.lw') ? +window.DRAG.ph.closest('.lw').dataset.l : null }));
  await tp('touchEnd'); await sleep(1500);
  const srv = (await api(`/store/kb/boards/${bid}`)).cards.find(c => c.id === mv);
  console.log('touch drag across lists:', JSON.stringify(st), 'server list', srv.list_id, 'expected', LB, srv.list_id === LB ? 'PASS' : 'FAIL');
  // plain swipe still scrolls the board (no drag)
  const sl0 = await p.evaluate(() => document.getElementById('lists').scrollLeft);
  const c2 = await p.$('.lw .card'); const r2 = await c2.boundingBox();
  await tp('touchStart', r2.x + r2.width - 20, r2.y + 10); for (let i = 1; i <= 6; i++) { await tp('touchMove', r2.x + r2.width - 20 - 40 * i, r2.y + 10); await sleep(16); } await tp('touchEnd'); await sleep(700);
  const sl1 = await p.evaluate(() => document.getElementById('lists').scrollLeft);
  console.log('quick swipe scrolls board:', sl0, '->', sl1, sl1 !== sl0 ? 'PASS' : 'FAIL(maybe)', 'drag active after?', await p.evaluate(() => !!window.DRAG));
  // tap opens card
  const c3 = await p.$('.lw .card'); await c3.tap(); await sleep(900);
  console.log('tap opens card:', !!(await p.$('.cm')) ? 'PASS' : 'FAIL');
  console.log('errors', JSON.stringify(errs));
  await br.close();
})();
