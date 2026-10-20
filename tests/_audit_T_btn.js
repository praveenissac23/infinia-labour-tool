const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8072';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const user = process.argv[2] || 'anoop', pass = process.argv[3] || 'pass12345', mobile = process.argv[4] === 'phone';
const log = [];
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  let errs = [], bad = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
  p.on('response', r => { if (r.status() >= 400 && !r.url().includes('/auth/me')) bad.push(r.status() + ' ' + r.request().method() + ' ' + r.url().replace(B, '')); });
  p.on('popup', pp => pp.close().catch(() => {}));
  const step = async (name, fn) => {
    errs = []; bad = [];
    try { await fn(); await sleep(350); } catch (e) { log.push(`FAIL ${name}: ${e.message.split('\n')[0].slice(0, 200)}`); return; }
    if (errs.length || bad.length) log.push(`FAIL ${name}: ${[...errs, ...bad].join(' | ').slice(0, 300)}`); else log.push(`ok   ${name}`);
  };
  const esc = async () => { await p.keyboard.press('Escape'); await sleep(150); await p.keyboard.press('Escape'); await sleep(150); };
  await p.goto(B + '/portal/boards.html'); await p.fill('#lg-u', user); await p.fill('#lg-p', pass); await p.click('#lg-go'); await p.waitForSelector('.home-wrap');
  // home + header
  for (const id of ['#hb-boards', '#hb-recent', '#hb-starred', '#hb-templates', '#hb-create', '#hb-notes', '#hb-help', '#hb-me']) {
    await step('header ' + id, async () => { const e = await p.$(id); if (!e || !(await e.isVisible())) throw new Error('not visible'); await e.click(); await sleep(400); const pops = await p.$$('.pop'); if (!pops.length && !(await p.$('.dlg, .modal, #keys'))) throw new Error('nothing opened'); });
    // click every menu button inside the popover (non-destructive)
    if (id === '#hb-create' || id === '#hb-me') {
      const labels = await p.$$eval('.pop .mi, .pop button', e => e.map(x => x.textContent.trim()).filter(Boolean)); log.push('     items: ' + labels.join(' / ').slice(0, 200));
    }
    await esc();
  }
  await step('search box', async () => { await p.fill('#q', '906'); await sleep(900); const r = await p.$$('#srch-res .sr, #srch-res a, #srch-res div'); if (!r.length) throw new Error('no results'); await p.keyboard.press('Escape'); });
  await p.fill('#q', ''); await esc();
  const bid = await p.evaluate(() => S.boards.find(x => x.title === 'Estimation').id);
  await p.evaluate(id => go('#/b/' + id), bid); await p.waitForSelector('#lists .card'); await sleep(700);
  // board header
  for (const id of ['#bh-star', '#bh-star', '#bh-vis', '#bh-view', '#bh-pu', '#bh-auto', '#bh-filter', '#bh-share', '#bh-menu', '#bh-dash', '#bh-mind']) {
    await step('board header ' + id, async () => { const e = await p.$(id); if (!e) throw new Error('missing'); if (!(await e.isVisible())) { log.push('     (hidden on this screen) ' + id); return; } await e.click(); await sleep(500); });
    await esc(); await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); if (S.view !== 'board') setView('board'); });
  }
  // views
  for (const v of ['table', 'calendar', 'timeline', 'dashboard', 'mindmap', 'board']) await step('view ' + v, async () => { await p.evaluate(v => setView(v), v); await sleep(600); if (v !== 'board' && !(await p.$('.view, #view, .vb'))) throw new Error('view not drawn'); });
  // board menu sections
  for (const s of ['about', 'activity', 'archived', 'automation', 'background', 'export', 'fields', 'labels', 'powerups', 'settings', 'visibility', 'copy']) {
    await step('board menu ' + s, async () => { await p.evaluate(s => boardMenu(s), s); await sleep(700); if (!(await p.$('#bmenu'))) throw new Error('menu not open'); const t = await p.$eval('#bmenu .bm-b', e => e.textContent.length); if (t < 10) throw new Error('empty section'); });
    await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); }); await esc();
  }
  // export buttons (Preview/PDF/Excel)
  for (const k of ['preview', 'pdf', 'excel']) await step('export ' + k, async () => { await p.evaluate(() => boardMenu('export')); await sleep(600); const [pop] = await Promise.all([p.waitForEvent('popup', { timeout: 8000 }), p.click(`#bmenu [data-e="${k}"]`)]); await pop.waitForLoadState().catch(() => {}); const ct = await pop.evaluate(() => document.contentType).catch(() => '?'); log.push('     export ' + k + ' opened ' + ct + ' ' + pop.url().replace(B, '').slice(0, 60)); });
  await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); });
  // list menu items
  const lid = await p.evaluate(() => S.lists.find(l => cardsOf(l.id).length >= 3).id);
  const items = await (async () => { await p.click(`.lw[data-l="${lid}"] [data-lmenu]`); await sleep(300); const ks = await p.$$eval('.pop [data-k]', e => e.map(x => x.dataset.k)); await esc(); return ks; })();
  log.push('     list menu: ' + items.join(','));
  for (const k of items.filter(k => !['archive', 'archiveall', 'moveall'].includes(k))) {
    await step('list menu ' + k, async () => { await p.click(`.lw[data-l="${lid}"] [data-lmenu]`); await sleep(300); await p.click(`.pop [data-k="${k}"]`); await sleep(500); });
    await esc(); await p.evaluate(() => { const m = document.getElementById('bmenu'); if (m) m.remove(); document.querySelectorAll('.composer').forEach(c => c.remove()); });
    await p.evaluate(l => { const w = document.querySelector(`.lw.collapsed[data-l="${l}"]`); if (w) listPatch(l, { collapsed: false }); }, lid); await sleep(300);
  }
  // card quick edit
  const cid = await p.evaluate(l => cardsOf(l)[0].id, lid);
  await step('quick edit (right click)', async () => { await p.click(`.card[data-c="${cid}"]`, { button: 'right' }); await sleep(400); if (!(await p.$('#qe'))) throw new Error('quick edit not open'); });
  const qks = await p.$$eval('#qe [data-k], .qe-btns [data-k]', e => e.map(x => x.dataset.k)).catch(() => []);
  log.push('     quick edit: ' + qks.join(','));
  await esc();
  for (const k of qks.filter(k => k !== 'archive')) {
    await step('quick edit ' + k, async () => { await p.click(`.card[data-c="${cid}"]`, { button: 'right' }); await sleep(350); await p.click(`[data-k="${k}"]`); await sleep(500); });
    await esc(); await p.evaluate(() => { const q = document.getElementById('qe'); if (q) q.remove(); });
  }
  // card back buttons
  await p.evaluate(c => { S.full = null; go(`#/b/${S.board.id}/c/${c}`); }, cid);
  try { await p.waitForSelector('.cm .acts', { timeout: 6000 }); } catch (e) { const st = await p.evaluate(() => ({ hash: location.hash, ov: !!document.getElementById('cm-ov'), open: S.openCard, board: S.board && S.board.id, qe: !!document.getElementById('qe'), pops: document.querySelectorAll('.pop').length, cm: document.querySelector('#cm-ov') && document.querySelector('#cm-ov').innerHTML.slice(0, 200) })); log.push('FAIL card back does not open after quick edit sweep: ' + JSON.stringify(st)); console.log(log.join('\n')); process.exit(1); }
  await sleep(500);
  const cks = await p.$$eval('.cm .acts [data-k]', e => e.map(x => x.dataset.k));
  log.push('     card back: ' + cks.join(','));
  for (const k of cks) {
    await step('card back ' + k, async () => { const e = await p.$(`.cm .acts [data-k="${k}"]`); if (!e) throw new Error('gone'); await e.click(); await sleep(500); });
    await p.keyboard.press('Escape'); await sleep(200);
    if (!(await p.$('.cm'))) { log.push('     (card closed after ' + k + ', url ' + p.url().split('#')[1] + ')'); await p.evaluate(c => { S.full = null; go(`#/b/${S.board.id}/c/${c}`); }, cid); try { await p.waitForSelector('.cm .acts', { timeout: 5000 }); } catch (e) { log.push('FAIL card does not reopen after ' + k + ' url=' + p.url().split('#')[1] + ' ov=' + !!(await p.$('#cm-ov'))); await p.evaluate(() => go('#/')); await sleep(500); await p.evaluate(c => go(`#/b/${S.board.id || 0}/c/${c}`), cid).catch(()=>{}); } await sleep(300); }
  }
  // more menu items on card back
  await step('card back more', async () => { const e = await p.$('.cm [data-k="more"]'); if (!e) throw new Error('no more'); await e.click(); await sleep(300); log.push('     more: ' + (await p.$$eval('.pop [data-a]', e => e.map(x => x.dataset.a))).join(',')); });
  await esc();
  // keyboard shortcuts on hovered card
  await esc(); await p.evaluate(() => go(`#/b/${S.board.id}`)); await sleep(500);
  const cid2 = await p.evaluate(l => cardsOf(l)[1].id, lid);
  for (const k of ['l', 'm', 'd', 'e', 't', ' ', 'q', 'f', '?', 'w']) {
    await step(`key "${k}"`, async () => { await p.hover(`.card[data-c="${cid2}"]`); await sleep(150); await p.keyboard.press(k === ' ' ? 'Space' : k); await sleep(500); });
    await esc(); await p.evaluate(() => { const q = document.getElementById('qe'); if (q) q.remove(); const m = document.getElementById('bmenu'); if (m) m.remove(); });
  }
  console.log(log.join('\n'));
  await br.close();
})();
