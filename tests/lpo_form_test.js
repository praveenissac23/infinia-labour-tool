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
const WIDTHS = [1500, 1280, 1100, 960, 860];
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

  // ---- The catalogue is behind the box ------------------------------
  const dl = await p.evaluate(() => {
    const d = document.getElementById('material-list-all');
    const box = document.querySelector('#lpo-lines input');
    return { options: d ? d.querySelectorAll('option').length : 0,
             points_at: box ? box.getAttribute('list') : null,
             sample: d ? [...d.querySelectorAll('option')].slice(0, 2).map(o => o.value) : [] };
  });
  ck('the material box is wired to the catalogue',
     dl.points_at === 'material-list-all', dl.points_at);
  ck('and the catalogue has materials in it', dl.options > 0, JSON.stringify(dl));
  ck('listed by code and name, so one can be found among thousands',
     dl.sample.every(v => / - /.test(v)), dl.sample);

  // ---- The cursor stays where it is being typed ---------------------
  const box = p.locator('#lpo-lines tr input').first();
  await box.click();
  for (const ch of 'ceme') { await p.keyboard.type(ch); await p.waitForTimeout(240); }
  await p.waitForTimeout(800);                 // past the 350ms rate lookup
  const typed = await p.evaluate(() => {
    const first = document.querySelector('#lpo-lines input');
    return { focused: document.activeElement === first,
             value: first.value, caret: first.selectionStart };
  });
  ck('typing a material keeps the cursor in the box', typed.focused, JSON.stringify(typed));
  ck('nothing typed is dropped', typed.value === 'ceme', typed.value);
  ck('and the caret stays at the end', typed.caret === 4, typed.caret);

  // Typing a rate redraws the row too - the same rule holds there.
  await p.evaluate(() => {
    const r = document.querySelectorAll('#lpo-lines tr')[0].querySelectorAll('input')[4];
    r.focus();
  });
  await p.keyboard.type('16');
  await p.waitForTimeout(400);
  await p.keyboard.type('.5');
  await p.waitForTimeout(400);
  const rate = await p.evaluate(() => {
    const r = document.querySelectorAll('#lpo-lines tr')[0].querySelectorAll('input')[4];
    return { focused: document.activeElement === r, value: r.value };
  });
  ck('and typing a rate does the same', rate.focused && rate.value === '16.5',
     JSON.stringify(rate));

  // ---- Picking a whole entry prints the name, not the code ----------
  const picked = await p.evaluate(async () => {
    const it = (storeItems || []).find(i => i.name === 'Cement OPC 50kg') || (storeItems || [])[0];
    const el = document.querySelectorAll('#lpo-lines tr')[0].querySelectorAll('input')[0];
    el.value = `${it.code} - ${it.name}`;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 800));
    return { want: it.name, id: it.id, unit: it.unit,
             got: lpoLines[0].description, gotId: lpoLines[0].item_id,
             gotUnit: lpoLines[0].unit };
  });
  ck('picking one off the list prints the name, not the code',
     picked.got === picked.want, JSON.stringify(picked));
  ck('and takes its id, so the rate history is the right one',
     picked.gotId === picked.id, JSON.stringify(picked));
  ck('and its unit', picked.gotUnit === picked.unit, JSON.stringify(picked));
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
