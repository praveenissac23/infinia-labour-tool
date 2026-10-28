// Chat photo editor (as on WhatsApp): pick a photo -> draw, circle, box, arrow, text, sticker, undo, rotate -> caption -> send.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp', PHOTO = process.env.PHOTO;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch();
  for (const [vw, vh, tag] of [[1440, 900, 'pc'], [390, 844, 'phone']]) {
    const ctx = await b.newContext({ viewport: { width: vw, height: vh }, hasTouch: tag === 'phone' }); const p = await ctx.newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
    await p.evaluate(() => { window.checkBuild = () => {}; const x = document.getElementById('build-bar'); if (x) x.remove(); });
    if (tag === 'pc') {
      const side = await p.evaluate(() => { const e = document.querySelector('.pg-side .pg-chat'); const cs = getComputedStyle(e); return cs.backgroundImage; });
      ck('pc: the Chat menu entry is a plain menu line, not a red block', side === 'none', side);
      await p.click('.pg-side .pg-chat');
    } else await p.click('#chat-btn');
    await sleep(1200); await p.click('[data-room="all"]'); await sleep(800);
    await p.setInputFiles('[data-file]', PHOTO); await sleep(1200);
    ck(tag + ': picking a photo opens the editor', await p.evaluate(() => document.getElementById('wa-draw').classList.contains('on')));
    const box = await p.locator('#wa-draw canvas').boundingBox();
    const at = (fx, fy) => [box.x + box.width * fx, box.y + box.height * fy];
    const drag = async (tool, a, z) => { await p.click(`#wa-draw [data-tool="${tool}"]`); const [x1, y1] = at(...a), [x2, y2] = at(...z);
      await p.mouse.move(x1, y1); await p.mouse.down(); for (let i = 1; i <= 8; i++) await p.mouse.move(x1 + (x2 - x1) * i / 8, y1 + (y2 - y1) * i / 8); await p.mouse.up(); };
    await p.click('#wa-draw [data-c="#FDD835"]');
    await drag('circle', [.25, .25], [.55, .55]);
    await p.click('#wa-draw [data-c="#E53935"]');
    await drag('arrow', [.85, .85], [.6, .6]);
    await drag('rect', [.6, .1], [.9, .3]);
    await drag('pen', [.1, .8], [.4, .9]);
    await p.click('#wa-draw [data-tool="text"]'); const [tx, ty] = at(.1, .1); await p.mouse.click(tx, ty); await sleep(200);
    await p.keyboard.type('Crack here'); await p.keyboard.press('Enter');
    await p.click('#wa-draw [data-tool="sticker"]'); await p.click('#wa-draw [data-s="⚠️"]');
    const n = await p.evaluate(() => document.querySelectorAll('#wa-draw .txin').length);
    ck(tag + ': text box closed after Enter', n === 0, n);
    await p.screenshot({ path: `${OUT}/chat-edit-${tag}.png` });
    // undo removes the sticker, then put it back
    await p.click('#wa-draw [data-undo]'); await p.click('#wa-draw [data-tool="sticker"]'); await p.click('#wa-draw [data-s="✅"]');
    // move the sticker to the corner
    const [sx, sy] = at(.5, .5), [ex, ey] = at(.8, .45); await p.mouse.move(sx, sy); await p.mouse.down(); await p.mouse.move(ex, ey, { steps: 6 }); await p.mouse.up();
    const pix = await p.evaluate(() => { const c = document.querySelector('#wa-draw canvas'), g = c.getContext('2d');
      const d = g.getImageData(Math.round(c.width * .25), Math.round(c.height * .4), 1, 1).data; return [d[0], d[1], d[2]]; });
    ck(tag + ': the yellow circle is drawn on the photo', pix[0] > 200 && pix[1] > 180 && pix[2] < 120, pix);
    await p.fill('#wa-draw [data-cap]', 'Marked up - ' + tag); await p.click('#wa-draw [data-send]'); await sleep(2500);
    ck(tag + ': editor closed', await p.evaluate(() => !document.getElementById('wa-draw').classList.contains('on')));
    const last = await p.evaluate(async () => { const i = [...document.querySelectorAll('#wa .ph img')].pop(); if (!i) return null;
      await new Promise(r => i.complete ? r() : i.onload = r); return { w: i.naturalWidth, cap: [...document.querySelectorAll('#wa .ln .bub')].pop().textContent }; });
    ck(tag + ': the marked-up photo is sent with its caption', last && last.w > 0 && /Marked up/.test(last.cap), last);
    await p.screenshot({ path: `${OUT}/chat-edit-sent-${tag}.png` });
    // cancel path: nothing sent
    const before = await p.evaluate(() => document.querySelectorAll('#wa .ph img').length);
    await p.setInputFiles('[data-file]', PHOTO); await sleep(1000); await p.click('#wa-draw [data-close]'); await sleep(800);
    ck(tag + ': cancel sends nothing', await p.evaluate(b => document.querySelectorAll('#wa .ph img').length === b && !document.getElementById('wa-draw').classList.contains('on'), before));
    ck(tag + ': no script errors', !errs.length, errs);
    await ctx.close();
  }
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
