// The purchase order form, in a real browser.
//
// Run: node tests/lpo_form_test.js      (serve_like_nginx.py on 8032)
//
// Three things here need layout and a live datalist, so jsdom cannot
// check them and the sweep leaves them alone:
//
//   * The material box offers the catalogue. It pointed at a chip list
//     on another screen rather than a datalist, so nothing was ever
//     suggested and every material had to be spelled out from memory.
//   * Typing a material keeps the cursor. The rate lookup redraws the
//     lines 350ms after a keystroke, throwing away the box being typed
//     into - the name had to be clicked back into every few letters.
//   * Every hint fits the box it sits in. A placeholder cut in half
//     reads as a broken screen, and the form is used at whatever width
//     the office laptop happens to be.
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:8032';
const WIDTHS = [1500, 1280, 1100, 960, 860, 430];   // 430 is a phone
const FAIL = [];
const ck = (m, cond, ctx) => {
  console.log((cond ? 'PASS ' : 'FAIL ') + m + (cond ? '' : `  [${ctx}]`));
  if (!cond) FAIL.push(m);
};

(async () => {
  const b = await chromium.launch();
  const errs = [];

  const open = async (width) => {
    const p = await b.newPage({ viewport: { width, height: 1000 } });
    p.on('pageerror', e => errs.push(`${width}px: ${String(e).slice(0, 160)}`));
    await p.goto(BASE + '/app.html');
    await p.fill('#login-username', 'admin');
    await p.fill('#login-password', 'changeme123');
    await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 });
    await p.waitForTimeout(2200);
    await p.evaluate("switchScreen('purchase')");
    await p.waitForTimeout(1200);
    await p.evaluate(async () => { await newLpo(); });
    await p.waitForTimeout(1200);
    return p;
  };

  const p = await open(1400);

  // Something to find in the picker, whatever the database holds.
  await p.evaluate(async () => {
    for (const [name, unit] of [['Cement OPC 50kg', 'bags'], ['Marine Plywood 18mm', 'sheet']]) {
      try {
        await apiCall('/store/items', { method: 'POST',
          body: JSON.stringify({ name, unit, item_type: 'consumable' }) });
      } catch (e) { /* already there from another run */ }
    }
    await loadStoreItems(true);
  });
  await p.evaluate(async () => { await newLpo(); });
  await p.waitForTimeout(1200);

  // ---- The suggestions appear as you type ---------------------------
  // Not a <datalist>: an iPhone ignores those completely, so on a phone
  // the picker never appeared at all. This is our own list.
  const box = p.locator('#lpo-lines tr .lpo-mat').first();
  await box.click();
  await p.waitForTimeout(400);
  ck('focusing the material box offers the catalogue',
     await p.locator('#lpo-match .match-row').count() > 0);

  await p.keyboard.type('cem');
  await p.waitForTimeout(500);
  const hits = await p.evaluate(() => [...document.querySelectorAll('#lpo-match .match-row')]
    .map(r => r.querySelector('.match-name').textContent));
  ck('typing narrows it to what was typed',
     hits.length > 0 && hits.every(h => /cem/i.test(h)), JSON.stringify(hits));
  ck('and each suggestion shows the code and unit beside the name',
     await p.locator('#lpo-match .match-row .match-meta').first().textContent() !== '');

  // The list is hung off the page, or the scrolling materials table
  // would cut it off at its own edge.
  ck('the list is not trapped inside the scrolling table',
     await p.evaluate(() => {
       const l = document.getElementById('lpo-match');
       return l && l.parentElement === document.body
         && getComputedStyle(l).position === 'fixed';
     }));
  const place = await p.evaluate(() => {
    const el = document.getElementById('lpo-match');
    if (!el) return { missing: true };
    const l = el.getBoundingClientRect();
    const b = document.querySelector('#lpo-lines .lpo-mat').getBoundingClientRect();
    // Below the box, or above it when the box sits near the bottom of
    // the window - which is where it lands on a phone with the keyboard
    // up. Either way it touches the box and is wholly on screen.
    const under = Math.abs(l.top - b.bottom) < 6;
    const over = Math.abs(l.bottom - b.top) < 6;
    return { ok: (under || over) && Math.abs(l.left - b.left) < 40
                 && l.top >= 0 && l.bottom <= window.innerHeight,
             where: under ? 'below' : (over ? 'above' : 'adrift'),
             list: [Math.round(l.top), Math.round(l.bottom), Math.round(l.left)],
             box: [Math.round(b.top), Math.round(b.bottom), Math.round(b.left)] };
  });
  ck('and it sits against the box, wholly on screen', place.ok === true, JSON.stringify(place));

  // ---- The cursor stays where it is being typed ---------------------
  await p.keyboard.type('e');
  await p.waitForTimeout(800);                 // past the 350ms rate lookup
  const typed = await p.evaluate(() => {
    const first = document.querySelector('#lpo-lines .lpo-mat');
    return { focused: document.activeElement === first,
             value: first.value, caret: first.selectionStart };
  });
  ck('typing a material keeps the cursor in the box', typed.focused, JSON.stringify(typed));
  ck('nothing typed is dropped', typed.value === 'ceme', typed.value);
  ck('and the caret stays at the end', typed.caret === 4, typed.caret);

  // Typing a rate repaints the amount - the boxes must not be rebuilt.
  await p.evaluate(() => {
    document.querySelectorAll('#lpo-lines tr')[0].querySelectorAll('input')[2].focus();
  });
  await p.keyboard.type('10');
  await p.waitForTimeout(300);
  await p.evaluate(() => {
    document.querySelectorAll('#lpo-lines tr')[0].querySelectorAll('input')[4].focus();
  });
  await p.keyboard.type('16');
  await p.waitForTimeout(400);
  await p.keyboard.type('.5');
  await p.waitForTimeout(500);
  const rate = await p.evaluate(() => {
    const row = document.querySelectorAll('#lpo-lines tr')[0];
    const r = row.querySelectorAll('input')[4];
    return { focused: document.activeElement === r, value: r.value,
             amount: row.querySelector('.lpo-amt').textContent };
  });
  ck('typing a rate keeps its cursor too', rate.focused && rate.value === '16.5',
     JSON.stringify(rate));
  ck('and the amount follows along', /165/.test(rate.amount.replace(/[^0-9]/g, '')),
     rate.amount);

  // ---- Choosing one fills the line ----------------------------------
  const chose = await p.evaluate(async () => {
    const el = document.querySelector('#lpo-lines .lpo-mat');
    el.focus(); el.value = 'cem';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 400));
    const row = document.querySelector('#lpo-match .match-row');
    if (!row) return { none: true };
    row.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
    await new Promise(r => setTimeout(r, 700));
    return { desc: lpoLines[0].description, id: lpoLines[0].item_id,
             unit: lpoLines[0].unit, shown: document.querySelector('#lpo-lines .lpo-mat').value,
             open: !!document.getElementById('lpo-match') };
  });
  ck('tapping a suggestion puts the name in the box',
     chose.desc && chose.shown === chose.desc, JSON.stringify(chose));
  ck('and takes its id, so the rate history is the right one',
     !!chose.id, JSON.stringify(chose));
  ck('and its unit', !!chose.unit, JSON.stringify(chose));
  ck('and the list closes behind it', chose.open === false, JSON.stringify(chose));

  // Arrow keys and Enter, for whoever never touches the mouse.
  const byKey = await p.evaluate(async () => {
    const el = document.querySelector('#lpo-lines .lpo-mat');
    el.focus(); el.value = 'ply';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 400));
    const down = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true });
    el.dispatchEvent(down);
    const hot = document.querySelector('#lpo-match .match-row.on');
    const name = hot && hot.querySelector('.match-name').textContent;
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await new Promise(r => setTimeout(r, 500));
    return { wanted: name, got: lpoLines[0].description };
  });
  ck('arrow down and Enter choose one without the mouse',
     byKey.wanted && byKey.got === byKey.wanted, JSON.stringify(byKey));

  await p.close();

  // ---- Every hint fits its box, at every width the office uses ------
  const measure = async (page) => page.evaluate(() =>
    [...document.querySelectorAll('.lpo-side input, #lpo-lines input')]
      .filter(el => el.placeholder && !el.value && el.clientWidth > 0)
      .filter(el => {
        const probe = document.createElement('span');
        probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;';
        probe.style.font = getComputedStyle(el).font;
        probe.textContent = el.placeholder;
        document.body.appendChild(probe);
        const need = probe.offsetWidth + 18;
        probe.remove();
        return need > el.clientWidth;
      })
      .map(el => el.placeholder));

  for (const w of WIDTHS) {
    const pg = await open(w);
    const cut = await measure(pg);
    ck(`every hint fits its box at ${w}px`, cut.length === 0, cut.join(' | '));
    if (w === 430) {
      const onPhone = await pg.evaluate(async () => {
        const el = document.querySelector('#lpo-lines .lpo-mat');
        el.focus(); el.value = 'cem';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        await new Promise(r => setTimeout(r, 500));
        const l = document.getElementById('lpo-match');
        if (!l) return { shown: false };
        const r = l.getBoundingClientRect();
        return { shown: true, onScreen: r.left >= 0 && r.right <= window.innerWidth
                 && r.top >= 0 && r.bottom <= window.innerHeight,
                 rows: l.querySelectorAll('.match-row').length,
                 tall: l.querySelector('.match-row').getBoundingClientRect().height };
      });
      ck('the picker still opens on a phone', onPhone.shown, JSON.stringify(onPhone));
      ck('fully on the screen', onPhone.onScreen, JSON.stringify(onPhone));
      ck('with rows big enough for a finger', onPhone.tall >= 38, onPhone.tall);
    }
    if (w === 960) {
      const stacked = await pg.evaluate(() => {
        const s = document.querySelectorAll('.lpo-sides .lpo-side');
        return s.length === 2 && s[1].offsetTop > s[0].offsetTop;
      });
      ck('and below 1000px the two panels stack instead of squeezing', stacked);
    }
    await pg.close();
  }

  console.log(errs.length ? '\nPAGE ERRORS:\n - ' + errs.join('\n - ') : '\nno page errors');
  console.log('\n' + (FAIL.length || errs.length
    ? `${FAIL.length} FAILED: ` + FAIL.join('; ') : 'LPO FORM CLEAN'));
  await b.close();
  process.exit(FAIL.length || errs.length ? 1 : 0);
})();
