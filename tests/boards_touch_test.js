// Trello on a phone: hold a card, then drag it to another list (real touch events through Chrome).
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }); const p = await ctx.newPage();
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const bid = (await api('/store/kb/boards', { method: 'POST', body: { title: 'Touch', lists: ['One', 'Two'] } })).id;
  const L = Object.fromEntries((await api(`/store/kb/boards/${bid}`)).lists.map(l => [l.title, l.id]));
  for (const t of ['Card one', 'Card two', 'Card three']) await api(`/store/kb/lists/${L.One}/cards`, { method: 'POST', body: { title: t } });
  await p.goto(`${B}/portal/boards.html#/b/${bid}`); await p.waitForSelector('.card'); await sleep(600);
  const cdp = await ctx.newCDPSession(p);
  const card = await p.$('.lw .card'); const r = await card.boundingBox();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const tp = (type, px, py) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x: px, y: py }] });
  await tp('touchStart', x, y); await sleep(450);
  // drag down within the list, below the third card
  const last = await (await p.$$('.lw .card'))[2].boundingBox();
  for (let i = 1; i <= 10; i++) { await tp('touchMove', x, y + (last.y + last.height + 10 - y) * i / 10); await sleep(30); }
  await tp('touchEnd'); await sleep(1200);
  const order = (await api(`/store/kb/boards/${bid}`)).cards.filter(c => c.list_id === L.One).sort((a, b) => a.pos - b.pos).map(c => c.title);
  const ok = order[order.length - 1] === 'Card one';
  console.log((ok ? 'PASS' : 'FAIL') + ' phone: hold a card and drag it down the list  ' + JSON.stringify(order));
  await br.close(); process.exit(ok ? 0 : 1);
})();
