// Store > Move material: every box keeps the cursor while typing (person, material, qty, note) - typed key by key.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: process.env.MOBILE ? { width: 390, height: 780 } : { width: 1440, height: 900 }, isMobile: !!process.env.MOBILE, hasTouch: !!process.env.MOBILE })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(() => pgGo('store', 'store:give')); await sleep(3500);
  const typeIn = async (sel, text) => { await p.click(sel); await p.keyboard.type(text, { delay: 120 }); await sleep(400);
    return p.$eval(sel, e => ({ v: e.value, focus: document.activeElement === e })); };
  const r1 = await typeIn('#out-person', 'Akhil');
  ck('Who is taking it: typed "Akhil" without clicking again', r1.v === 'Akhil', r1);
  const r2 = await typeIn('#out-lines tr:first-child .ol-item-txt', 'cement');
  ck('Material: typed "cement" without clicking again', r2.v.toLowerCase().startsWith('cement'), r2);
  await p.keyboard.press('Escape');
  const r3 = await typeIn('#out-lines tr:first-child .ol-qty', '125');
  ck('How many: typed 125', r3.v === '125', r3);
  const r4 = await typeIn('#out-lines tr:first-child .ol-note', 'for slab');
  ck('Note: typed "for slab"', r4.v === 'for slab', r4);
  // with both ends picked (site holdings drawn, stock of the place it leaves loaded), and a few lines
  for (const [from, to] of [['', 'SITE'], ['SITE', ''], ['SITE', 'SITE2']]) {
    await p.evaluate(([f, t]) => { const s = sites.map(x => x.code); const v = x => x === 'SITE' ? s[0] : x === 'SITE2' ? s[1] : '';
      document.getElementById('out-from').value = v(f); document.getElementById('out-site').value = v(t); onMoveEnds(); }, [from, to]);
    await sleep(2500);
    await p.evaluate(() => addOutLine()); await sleep(300);
    const n = await p.$$eval('#out-lines tr', x => x.length);
    const sel = `#out-lines tr:nth-child(${n})`;
    const a = await typeIn(sel + ' .ol-item-txt', 'wire nail'); await p.keyboard.press('Escape');
    ck(`[${from || 'store'} -> ${to || 'store'}] material typed key by key`, a.v === 'wire nail' && a.focus, a);
    const b = await typeIn(sel + ' .ol-qty', '45'); ck(`[${from || 'store'} -> ${to || 'store'}] qty typed`, b.v === '45' && b.focus, b);
    const c = await typeIn(sel + ' .ol-note', 'level 2'); ck(`[${from || 'store'} -> ${to || 'store'}] note typed`, c.v === 'level 2' && c.focus, c);
    const d = await typeIn('#out-person', ' K'); ck(`[${from || 'store'} -> ${to || 'store'}] person typed`, d.v.endsWith(' K') && d.focus, d);
    await sleep(+process.env.IDLE || 31000);   // anything that refreshes itself on a timer
    const e = await typeIn(sel + ' .ol-note', ' ok'); ck(`[${from || 'store'} -> ${to || 'store'}] note still typed after 30 s idle`, e.v === 'level 2 ok' && e.focus, e);
  }
  // after a heading of the lines table was clicked (sorted) - the rows must not be moved under the cursor
  await p.evaluate(() => { const h = [...document.querySelectorAll('#store-give thead th')].find(x => /How many/.test(x.textContent)); h.click(); });
  await sleep(500); await p.evaluate(() => addOutLine()); await sleep(300);
  { const n = await p.$$eval('#out-lines tr', x => x.length); const sel = `#out-lines tr:nth-child(${n})`;
    const a = await typeIn(sel + ' .ol-item-txt', 'cement'); await p.keyboard.press('Escape');
    ck('sorted lines table: material typed key by key', a.v === 'cement' && a.focus, a);
    const b = await typeIn(sel + ' .ol-qty', '30'); ck('sorted lines table: qty typed key by key', b.v === '30' && b.focus, b); }
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
