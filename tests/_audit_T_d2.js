const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8072';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', 'anoop'); await p.fill('#lg-p', 'pass12345'); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const bid = await p.evaluate(() => S.boards.find(x => x.title === 'Estimation').id);
  await p.evaluate(id => go('#/b/' + id), bid); await p.waitForSelector('#lists .card'); await sleep(700);
  const lids = await p.evaluate(() => S.lists.filter(l => cardsOf(l.id).length >= 3).map(l => l.id));
  const [LA, LB] = lids;
  for (const hold of [0, 5000]) {
    const cards = await p.$$(`.lw[data-l="${LA}"] .card`); const mv = +(await cards[0].getAttribute('data-c'));
    const other = +(await cards[1].getAttribute('data-c'));
    const b0 = await cards[0].boundingBox();
    await p.mouse.move(b0.x + b0.width / 2, b0.y + b0.height / 2); await p.mouse.down(); await p.mouse.move(b0.x + b0.width / 2 + 20, b0.y + b0.height / 2 + 20, { steps: 3 });
    if (hold) { await api(`/store/kb/cards/${other}`, { method: 'PATCH', body: { title: 'Edited mid drag ' + Date.now() } }); await sleep(hold); }
    const t2 = await p.$$(`.lw[data-l="${LB}"] .card`); const tb = await t2[0].boundingBox();
    await p.mouse.move(tb.x + 50, tb.y + 3, { steps: 10 }); await sleep(150);
    const st = await p.evaluate(() => ({ drag: !!window.DRAG, ph: window.DRAG && window.DRAG.ph && window.DRAG.ph.closest('.lw') ? +window.DRAG.ph.closest('.lw').dataset.l : null, connected: window.DRAG && window.DRAG.ph.isConnected }));
    await p.mouse.up(); await sleep(1500);
    const srv = (await api(`/store/kb/boards/${bid}`)).cards.find(c => c.id === mv);
    console.log('hold', hold, JSON.stringify(st), 'card now in', srv.list_id, 'expected', LB, 'dom in', await p.evaluate(id => { const e = document.querySelector(`.card[data-c="${id}"]`); return e && e.closest('.lw') ? +e.closest('.lw').dataset.l : null; }, mv));
  }
  await br.close();
})();
