// Every date box shows and takes dd/mm/yyyy (portal/dmy-dates.js), on a browser set to US English too:
// typed 05/11/2026 is stored 2026-11-05, a screen setting .value shows it as dd/mm/yyyy, change fires,
// clearing works, invalid 31/02 is refused; boxes added later (Estimation forms) are picked up.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  await ctx.addInitScript(() => { window.__forceDmy = true; });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + (process.env.PAGE || '/app-classic.html'));
  await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible', timeout: 25000 }); await sleep(2000);
  const n = await p.evaluate(() => ({ dates: document.querySelectorAll('input[type=date]').length, done: [...document.querySelectorAll('input[type=date]')].filter(x => x.__dmy).length }));
  ck('every date box on the page is turned into a dd/mm/yyyy box', n.dates > 10 && n.dates === n.done, n);
  // a test box: added later, with a change handler, set by the screen
  const r = await p.evaluate(async () => {
    const box = document.createElement('div'); box.id = 'tbox'; box.innerHTML = '<input type="date" id="td" value="2026-10-30" onchange="window.__ch=(window.__ch||0)+1; window.__v=this.value">';
    document.body.prepend(box); await new Promise(r => setTimeout(r, 300));
    const el = document.getElementById('td'), alt = el.nextElementSibling;
    const out = { shown: alt && alt.value, typeKept: el.type, hidden: getComputedStyle(el).display };
    el.value = '2026-01-07'; out.afterSet = alt.value; out.read = el.value;
    return out; });
  ck('a date set on the page shows as dd/mm/yyyy (30/10/2026)', r.shown === '30/10/2026', r);
  ck('the real box is still type=date and hidden', r.typeKept === 'date' && r.hidden === 'none', r);
  ck('the screen setting .value updates what is shown (07/01/2026) and reads back ISO', r.afterSet === '07/01/2026' && r.read === '2026-01-07', r);
  const alt = '#tbox .dmy-alt';
  await p.click(alt); await p.keyboard.press('Control+A'); await p.keyboard.type('05/11/2026'); await p.keyboard.press('Enter'); await sleep(300); await p.keyboard.press('Escape');
  let v = await p.evaluate(() => [document.getElementById('td').value, window.__ch, window.__v, document.querySelector('#tbox .dmy-alt').value]);
  ck('typed 05/11/2026 is stored as 2026-11-05 (5 November, not 11 May) and change fires ONCE', v[0] === '2026-11-05' && v[1] === 1 && v[2] === '2026-11-05' && v[3] === '05/11/2026', v);
  await p.click(alt); await p.keyboard.press('Control+A'); await p.keyboard.type('31/02/2026'); await p.click('body', { position: { x: 5, y: 600 } }); await sleep(300);
  v = await p.evaluate(() => [document.getElementById('td').value, document.querySelector('#tbox .dmy-alt').value]);
  ck('31/02/2026 is refused - the date stays 05/11/2026', v[0] === '2026-11-05' && v[1] === '05/11/2026', v);
  await p.click(alt); await p.keyboard.press('Control+A'); await p.keyboard.press('Backspace'); await p.click('body', { position: { x: 5, y: 600 } }); await sleep(300);
  v = await p.evaluate(() => [document.getElementById('td').value, window.__v]);
  ck('clearing the box clears the date', v[0] === '' && v[1] === '', v);
  await p.click(alt); await sleep(300);
  const cal = await p.evaluate(() => { const c = document.querySelector('.flatpickr-calendar.open'); return c ? [c.querySelector('.flatpickr-weekday') && c.querySelector('.flatpickr-weekday').textContent.trim()] : null; });
  ck('clicking opens a calendar, week starting Monday', cal && /^Mon/.test(cal[0]), cal);
  const c0 = await p.evaluate(() => window.__ch);
  await p.click('.flatpickr-calendar.open .flatpickr-day:not(.prevMonthDay):not(.nextMonthDay) >> nth=9'); await sleep(400);
  v = await p.evaluate(() => [document.getElementById('td').value, window.__ch, document.querySelector('#tbox .dmy-alt').value]);
  ck('picking a day in the calendar sets it and fires change once', /^\d{4}-\d{2}-10$/.test(v[0]) && v[1] === c0 + 1 && /^10\//.test(v[2]), [c0, v]);
  await p.screenshot({ path: '/tmp/claude-0/dmy_cal.png' });
  await p.keyboard.press('Escape');
  ck('no page errors', !errs.length, errs);
  // Estimation: a form opened later
  const q = await ctx.newPage(); const e2 = []; q.on('pageerror', e => e2.push(e.message));
  await q.goto(B + '/portal/est-app.html?view=projects'); await q.fill('#lg-u', 'admin'); await q.fill('#lg-p', 'changeme123'); await q.click('#lg-go'); await sleep(2500);
  const ok2 = await q.evaluate(async () => { if (typeof modal !== 'function') return 'no modal';
    modal('Test', [{ k: 'd', label: 'Date', type: 'date' }], async () => {}); await new Promise(r => setTimeout(r, 400));
    const el = document.querySelector('#f-d'); return el ? [el.__dmy, el.nextElementSibling && el.nextElementSibling.placeholder] : 'no field'; });
  ck('Estimation form date box (opened later) is dd/mm/yyyy too', Array.isArray(ok2) && ok2[0] === true && ok2[1] === 'dd/mm/yyyy', ok2);
  ck('no page errors on Estimation', !e2.length, e2);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
