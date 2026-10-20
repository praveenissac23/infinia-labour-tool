const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8072';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', 'anoop'); await p.fill('#lg-p', 'pass12345'); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
  const bid = await p.evaluate(() => S.boards.find(x => x.title === 'Estimation').id);
  await p.evaluate(id => go('#/b/' + id), bid); await p.waitForSelector('#lists .card'); await sleep(600);
  const cid = await p.evaluate(() => +document.querySelector('#lists .card').dataset.c);
  // A: quick edit "Open card" then Escape, then click the card
  await p.click(`.card[data-c="${cid}"]`, { button: 'right' }); await sleep(300); await p.click('[data-k="open"]'); await p.waitForSelector('.cm .acts'); await sleep(300);
  await p.keyboard.press('Escape'); await sleep(400);
  console.log('after Escape: ov', !!(await p.$('#cm-ov')), 'S.full', await p.evaluate(() => S.full && S.full.id), 'hash', await p.evaluate(() => location.hash));
  await p.click(`.card[data-c="${cid}"]`); await sleep(1500);
  console.log('A reopen by click shows card:', !!(await p.$('.cm .acts')));
  await p.keyboard.press('Escape'); await sleep(400);
  // B: race - poll's loadFullCard in flight while closing
  await p.click(`.card[data-c="${cid}"]`); await p.waitForSelector('.cm .acts'); await sleep(300);
  await p.evaluate(c => { loadFullCard(c, true); go('#/b/' + S.board.id); }, cid); await sleep(800);
  console.log('B after race: S.full', await p.evaluate(() => S.full && S.full.id), 'openCard', await p.evaluate(() => S.openCard));
  await p.click(`.card[data-c="${cid}"]`); await sleep(1500);
  console.log('B reopen shows card:', !!(await p.$('.cm .acts')));
  await br.close();
})();
