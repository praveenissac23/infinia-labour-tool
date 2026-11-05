// Trello boards dashboard in dark glass (5 Nov 2026): the dashboard (Boards, Templates, Home) gets the dark glass
// background, frosted panels and white text; opening a board drops it - the board keeps its own background.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/roles.db 8510 tests/boards_glass_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
(async () => { const br = await chromium.launch();
  for (const vw of [{ width: 1440, height: 860, n: 'desk' }, { width: 390, height: 844, n: 'phone' }]) {
    const p = await (await br.newContext({ viewport: { width: vw.width, height: vw.height } })).newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/portal/boards.html'); await sleep(1500);
    if (await p.isVisible('#lg-u')) { await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); }
    await sleep(3000);
    if (vw.n === 'desk') await p.evaluate(async () => { for (const [title, bg] of [['913 - Sobha Hartland WS-25', 'g_ocean'], ['914 - Emkaan villa', 'g_peach'], ['Tenders - VE278', 'g_crystal'], ['QS team - bills', 'blue'], ['Site 912 snags', 'g_earth'], ['Pools division', 'g_flower']]) await POST('/store/kb/boards', { title, bg, visibility: 'team' }); });
    await p.evaluate(() => { location.hash = '#/x'; location.hash = '#/'; }); await sleep(2500);
    const look = () => p.evaluate(() => ({ home: document.body.classList.contains('on-home'), bg: getComputedStyle(document.getElementById('home')).backgroundImage.slice(0, 30),
      blur: getComputedStyle(document.querySelector('.home-nav')).backdropFilter, h3: getComputedStyle(document.querySelector('.home-main h3')).color,
      tt: (document.querySelector('.tile .tt') ? getComputedStyle(document.querySelector('.tile .tt')).color : '') }));
    const a = await look();
    ck(`${vw.n}: dashboard in dark glass - glow background, frosted panels, white headings`, a.home && /radial-gradient/.test(a.bg) && /blur/.test(a.blur) && a.h3 === 'rgb(241, 242, 244)' && a.tt === 'rgb(255, 255, 255)', a);
    await p.screenshot({ path: `/tmp/claude-0/ui2/glass/final_${vw.n}_boards.png` });
    for (const t of ['templates', 'home']) {
      await p.evaluate(t => { location.hash = '#/' + t; }, t); await sleep(1500);
      ck(`${vw.n}: ${t} page in the same glass`, (await look()).home);
      await p.screenshot({ path: `/tmp/claude-0/ui2/glass/final_${vw.n}_${t}.png` });
    }
    await p.evaluate(() => { location.hash = '#/'; }); await sleep(1500);
    await p.click('.tile[data-b]'); await sleep(2500);
    const bd = await p.evaluate(() => ({ home: document.body.classList.contains('on-home'), board: document.body.classList.contains('on-board'), hdr: getComputedStyle(document.getElementById('hdr')).backdropFilter }));
    ck(`${vw.n}: opening a board leaves the glass - the board keeps its own look`, !bd.home && bd.board, bd);
    if (vw.n === 'desk') await p.screenshot({ path: `/tmp/claude-0/ui2/glass/final_desk_board.png` });
    await p.click('#go-home'); await sleep(2000);
    ck(`${vw.n}: back to the dashboard - glass again`, (await look()).home);
    ck(`${vw.n}: no page errors`, !errs.length, errs);
    await p.context().close();
  }
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close(); })();
