// Estimation: one standard everywhere - full pages have "<- Back" top left (no x), their buttons top right and
// Save floating at the bottom right; pop-up forms have x + Cancel / Save. Leaving anything with changes not
// saved (Back, x, Cancel, Esc, clicking outside, the main app's tabs) asks: Stay / Leave without saving / Save & exit.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/eststd_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta');
  const P = meta.projects.find(x => x.code === '913').id, run = Date.now() % 100000;
  const sid = (await api('/store/est/subs', { method: 'POST', body: { project_id: P, name: 'AL RAIDA ' + run, scope: 'MEP', value: 568800 } })).id;
  await api(`/store/est/subs/${sid}/items`, { method: 'PUT', body: { items: [{ no: '1', description: 'Complete Electrical works', qty: 1, unit: 'LS', rate: 172800, amount: 172800, measure: 'pct' }, { no: '2', description: 'Complete Plumbing works', qty: 1, unit: 'LS', rate: 153000, amount: 153000, measure: 'pct' }] } });
  const pcid = (await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sid, inv_ref: 'INV/ALA/1040/26', inv_amount: 119448 } })).id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.reg'); }, [P]); await p.reload(); await sleep(1500);
  const leaveShown = () => p.isVisible('#leave:not(.hide)');

  // ---- the subcontract page: Back only, no x
  await p.click(`[data-sub="${sid}"]`); await sleep(600);
  ck('subcontract page: "Back" at the top left', await p.isVisible('#d-back'));
  ck('subcontract page: no x', !(await p.$('#drawer .mhead .x')));
  await p.screenshot({ path: SH + '1_subcontract_page.png' });

  // ---- pop-up form: Cancel with nothing changed closes at once
  await p.click('#s-vo'); await sleep(400);
  await p.click('#m-cancel'); await sleep(300);
  ck('form untouched: Cancel closes straight away', !(await leaveShown()) && !(await p.isVisible('#modal:not(.hide)')));
  // changed, then x -> asks
  await p.click('#s-vo'); await sleep(400);
  await p.fill('#f-title', 'Extra DB for the pool pump'); await sleep(100);
  await p.click('#m-x'); await sleep(300);
  ck('form changed: x asks first', await leaveShown());
  ck('the box offers Stay / Leave without saving / Save & exit', (await p.textContent('#leave')).includes('Stay') && (await p.textContent('#leave')).includes('Leave without saving') && (await p.textContent('#leave')).includes('Save & exit'));
  await p.screenshot({ path: SH + '2_form_unsaved.png' });
  await p.click('#lv-stay'); await sleep(200);
  ck('Stay: the form is still open with what was typed', await p.isVisible('#modal:not(.hide)') && (await p.inputValue('#f-title')) === 'Extra DB for the pool pump');
  // clicking outside / Esc ask too
  await p.keyboard.press('Escape'); await sleep(250);
  ck('Esc asks too', await leaveShown());
  await p.keyboard.press('Escape'); await sleep(200);   // Esc on the box = Stay
  ck('Esc on the box = Stay', !(await leaveShown()) && await p.isVisible('#modal:not(.hide)'));
  await p.mouse.click(10, 450); await sleep(250);
  ck('clicking outside the form asks too', await leaveShown());
  await p.click('#lv-drop'); await sleep(300);
  ck('Leave without saving: closed, nothing saved', !(await p.isVisible('#modal:not(.hide)')) && !(await api(`/store/est/projects/${P}`)).subs.find(x => x.id === sid).vos.length);
  // Save & exit saves it
  await p.click('#s-vo'); await sleep(400);
  await p.fill('#f-title', 'Extra DB for the pool pump'); await p.fill('#f-amount', '4500'); await sleep(100);
  await p.click('#m-cancel'); await sleep(300);
  await p.click('#lv-save'); await sleep(1200);
  const vos = (await api(`/store/est/projects/${P}`)).subs.find(x => x.id === sid).vos;
  ck('Save & exit: saved and closed', !(await p.isVisible('#modal:not(.hide)')) && vos.length === 1 && Math.abs(vos[0].amount - 4500) < .01, vos);

  // ---- full page (PC sheet): Back top left, buttons top right, Save floating
  await p.click(`[data-pc="${pcid}"]`); await sleep(1500);
  ck('PC sheet open', await p.isVisible('#big:not(.hide)'));
  ck('PC sheet: "Back" at the top left, no x', await p.isVisible('#b-back') && !(await p.$('#big .mhead .x')));
  const hb = await p.$eval('#big .mhead', el => el.getBoundingClientRect().height);
  ck('header is one line (Back, title, buttons) - nothing wraps under', hb < 70, hb);
  const sb = await p.$eval('#b-savebar', el => { const r = el.getBoundingClientRect(); return { b: innerHeight - r.bottom, r: innerWidth - r.right, vis: !el.classList.contains('hide') }; });
  ck('Save floats at the bottom right, clear of the INFI button', sb.vis && sb.b < 40 && sb.r >= 90, sb);
  await p.screenshot({ path: SH + '3_pc_sheet.png' });
  // nothing changed -> Back closes straight away
  await p.click('#b-back'); await sleep(500);
  ck('sheet untouched: Back closes straight away, back on the subcontract page', !(await leaveShown()) && !(await p.isVisible('#big:not(.hide)')) && await p.isVisible('#drawer:not(.hide)'));
  // changed -> Back asks
  await p.click(`[data-pc="${pcid}"]`); await sleep(1500);
  const pct = await p.$$('#b-body [data-k="pct"][data-l]');
  await pct[0].fill('40'); await sleep(200);
  await p.click('#b-back'); await sleep(300);
  ck('sheet changed: Back asks first', await leaveShown());
  await p.screenshot({ path: SH + '4_pc_sheet_unsaved.png' });
  await p.click('#lv-stay'); await sleep(200);
  ck('Stay keeps the 40%', await p.isVisible('#big:not(.hide)') && (await pct[0].inputValue()) === '40');
  await p.keyboard.press('Escape'); await sleep(300);
  ck('Esc on the sheet asks too', await leaveShown());
  await p.click('#lv-save'); await sleep(1500);
  const sh = await api(`/store/est/subpcs/${pcid}/sheet`);
  ck('Save & exit: the sheet is saved and closed', !(await p.isVisible('#big:not(.hide)')) && Math.abs(sh.calc.work - 69120) < 1, sh.calc);
  ck('still on the subcontract page after it', await p.isVisible('#drawer:not(.hide)'));

  // ---- phone Back on the sheet with changes asks; Stay keeps the page
  await p.click(`[data-pc="${pcid}"]`); await sleep(1500);
  await (await p.$$('#b-body [data-k="pct"][data-l]'))[1].fill('25'); await sleep(200);
  await p.goBack().catch(() => {}); await sleep(500);
  ck('phone / browser Back with changes asks first', await leaveShown());
  await p.click('#lv-stay'); await sleep(300);
  ck('Stay: still on the sheet', await p.isVisible('#big:not(.hide)'));
  await p.click('#b-back'); await sleep(300); await p.click('#lv-drop'); await sleep(500);
  ck('Leave without saving: closed, the 25% not saved', !(await p.isVisible('#big:not(.hide)')) && Math.abs((await api(`/store/est/subpcs/${pcid}/sheet`)).calc.work - 69120) < 1);

  // ---- inside the main app: moving to the Trello tab with the sheet changed asks first
  const a = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await a.goto(B + '/'); await a.fill('#login-username', 'admin'); await a.fill('#login-password', 'changeme123'); await a.evaluate('doLogin()'); await sleep(2500);
  await a.goto(B + '/?p=estimation#estproj'); await sleep(3500);
  const fr = a.frames().find(f => /est-app\.html/.test(f.url()) && /view=projects/.test(f.url()));
  ck('Projects tab loads Estimation', !!fr);
  if (fr) {
    await fr.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.reg'); }, [P]); await fr.evaluate(() => location.reload()); await sleep(2500);
    const f2 = a.frames().find(f => /est-app\.html/.test(f.url()) && /view=projects/.test(f.url()));
    await f2.click(`[data-sub="${sid}"]`); await sleep(600); await f2.click(`[data-pc="${pcid}"]`); await sleep(1500);
    await (await f2.$$('#b-body [data-k="pct"][data-l]'))[1].fill('30'); await sleep(200);
    await a.evaluate(() => pgTab('boards')); await sleep(600);
    ck('main app: Trello tab with the sheet changed asks first', await f2.isVisible('#leave:not(.hide)'));
    ck('...and stays on Projects until answered', await a.isVisible('#screen-pgestproj.active'));
    await a.screenshot({ path: SH + '5_app_tab_unsaved.png' });
    await f2.click('#lv-drop'); await sleep(1500);
    ck('Leave without saving: goes on to Trello', await a.isVisible('#screen-pgboards.active'));
  }
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
