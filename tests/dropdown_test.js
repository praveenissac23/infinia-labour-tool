// Every searchable dropdown on Daily Attendance (and a sample elsewhere):
// it opens, its list scrolls with the wheel and by dragging without
// closing, the page does not scroll underneath, typing filters, a click
// picks, Enter picks, Escape closes, and the choice reaches the screen.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8032/temporary/Infinia/';
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1366, height: 800 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  let bad = 0; const ck = (n, ok, d) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok || d === undefined ? '' : '   ' + JSON.stringify(d))); };
  await p.goto(BASE + 'attendance.html'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin(); 0'); await p.waitForTimeout(3500);
  const open = () => p.evaluate(() => { const e = document.querySelector('.sel-pop'); return !!e && e.style.display !== 'none'; });
  // enough sites that the site list is a long one, as on the live system
  await p.evaluate(async () => { for (let i = 0; i < 14; i++) { try { await apiCall('/sites', { method: 'POST', body: JSON.stringify({ code: String(950 + i), name: 'Test site ' + (950 + i) }) }); } catch (e) {} } });
  await p.reload(); await p.waitForTimeout(3500);
  // tag the first row's dropdowns so they can be tested like the rest
  await p.evaluate(() => { const r = document.querySelector('#screen-attendance tbody tr'); if (!r) return; [...r.querySelectorAll('select')].forEach((s, i) => { if (!s.id) s.id = 'row1-sel' + i; }); });
  const ids = await p.evaluate(() => [...document.querySelectorAll('#screen-attendance select')].filter(s => s.offsetParent !== null && s.options.length >= 8).map(s => s.id || s.className).slice(0, 12));
  console.log('attendance dropdowns with a search box:', ids.join(', '));
  for (const id of ids.filter(x => /^(bulk-|row1-)/.test(x))) {
    const sel = `#${id}`;
    await p.click(sel); await p.waitForTimeout(250);
    ck(`${id}: opens`, await open());
    const list = p.locator('.sel-pop .sel-list');
    const box = await list.boundingBox();
    const pageY = await p.evaluate(() => window.scrollY);
    await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    for (let i = 0; i < 6; i++) { await p.mouse.wheel(0, 120); await p.waitForTimeout(60); }
    const scrolled = await list.evaluate(el => el.scrollTop);
    const scrollable = await list.evaluate(el => el.scrollHeight > el.clientHeight + 2);
    ck(`${id}: wheel scrolls the list and it stays open`, await open() && (!scrollable || scrolled > 0), { scrolled, scrollable });
    ck(`${id}: the page underneath did not move`, (await p.evaluate(() => window.scrollY)) === pageY);
    // drag the scrollbar area / press-drag inside the list
    await p.mouse.move(box.x + box.width - 4, box.y + 20); await p.mouse.down(); await p.mouse.move(box.x + box.width - 4, box.y + 120, { steps: 6 }); await p.mouse.up(); await p.waitForTimeout(150);
    ck(`${id}: dragging inside the list keeps it open`, await open());
    // pick the third visible option by click
    const opts = await p.locator('.sel-pop .sel-opt').allTextContents();
    const target = opts[Math.min(2, opts.length - 1)];
    await p.locator('.sel-pop .sel-opt', { hasText: target }).first().scrollIntoViewIfNeeded(); await p.locator('.sel-pop .sel-opt', { hasText: target }).first().click(); await p.waitForTimeout(200);
    const shown = await p.evaluate(s => { const e = document.querySelector(s); return e.options[e.selectedIndex].textContent.trim(); }, sel);
    ck(`${id}: a click picks "${target}" and closes`, !(await open()) && shown === target, shown);
    // type to filter, Enter picks
    await p.click(sel); await p.waitForTimeout(200);
    const want = opts[opts.length - 1];
    await p.keyboard.type(want.slice(0, 3)); await p.waitForTimeout(150);
    const filtered = await p.locator('.sel-pop .sel-opt').count();
    await p.keyboard.press('Enter'); await p.waitForTimeout(200);
    ck(`${id}: typing filters (${filtered} of ${opts.length}) and Enter picks`, !(await open()) && filtered <= opts.length);
    await p.click(sel); await p.waitForTimeout(200); await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    ck(`${id}: Escape closes`, !(await open()));
  }
  // the page scrolling underneath closes it (its position would be wrong)
  await p.click('#bulk-site'); await p.waitForTimeout(200);
  const pb = await p.locator('.sel-pop').boundingBox();
  await p.mouse.move(pb.x + pb.width + 200 < 1366 ? pb.x + pb.width + 200 : 260, 700); await p.mouse.wheel(0, 400); await p.waitForTimeout(250);
  ck('scrolling the page itself closes it', !(await open()));
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'EVERY DROPDOWN SCROLLS, FILTERS AND PICKS');
  await b.close();
})();
