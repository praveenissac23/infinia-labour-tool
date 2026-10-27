// The October audit fixes, on screen:
//  - Estimation and Accounts > Subcontractor payments (in their frames): a column heading sorts the table.
//  - Tax invoice: "Save & open PDF" floats (the page has three Save buttons; the marked main one floats).
//  - Store > Give out to a site: "Give out to a site" floats.
//  - A hint that does not fit its box is shortened, the full wording kept on the box's tooltip (phone).
//  - Live card with nothing recorded: Export says so instead of opening a tab with an error.
//   BASE=http://127.0.0.1:8042 node tests/audit_fixes_ui_test.js   (help.db: tests/seed_help_data.py)
const { chromium, devices } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8042';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
const login = async (ctx) => { const p = await ctx.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(async () => { window.checkBuild = () => {}; localStorage.setItem('infinia-help-hello', '1'); const m = await apiCall('/store/est/meta'); const pr = m.projects.find(x => x.code === '914') || m.projects[0]; if (pr) localStorage.setItem('est_pid', pr.id); });
  return p; };
const go = (p, g) => p.evaluate(async g => { await HELP.goTo({ go: g }); }, g);
(async () => {
  const br = await chromium.launch();
  const p = await login(await br.newContext({ viewport: { width: 1440, height: 900 } }));
  // ---- sorting inside the frames ------------------------------------------------------------
  await go(p, { page: 'accounts', tab: 'subpay' }); await sleep(4000);
  const sp = await p.evaluate(async () => { const d = document.getElementById('pg-subpay-frame').contentDocument;
    const t = [...d.querySelectorAll('table')].find(x => x.tHead && x.tBodies[0] && x.tBodies[0].rows.length > 3); if (!t) return null;
    const th = [...t.tHead.rows[0].cells].find(c => /payable/i.test(c.textContent)); if (!th) return 'no payable heading';
    const col = [...t.tHead.rows[0].cells].indexOf(th);
    const vals = () => [...t.tBodies[0].rows].filter(r => r.cells.length > col && !/(^|\s)tot(\s|$)/.test(r.className)).map(r => parseFloat(r.cells[col].textContent.replace(/[^\d.]/g, '')) || 0);
    th.click(); await new Promise(r => setTimeout(r, 300)); const a = vals();
    th.click(); await new Promise(r => setTimeout(r, 300)); const z = vals();
    return { sortable: th.classList.contains('tx-s'), asc: a.every((v, i) => !i || a[i - 1] <= v), desc: z.every((v, i) => !i || z[i - 1] >= v), n: a.length }; });
  ck('Subcontractor payments: Payable heading sorts both ways', sp && sp.sortable && sp.asc && sp.desc && sp.n > 3, sp);
  await go(p, { page: 'estimation', tab: 'estproj', est: 'site.submittal' }); await sleep(7000);
  const es = await p.evaluate(() => { const d = document.getElementById('pg-estproj-frame').contentDocument;
    const t = [...d.querySelectorAll('table')].find(x => x.getClientRects().length && x.tHead && [...x.tBodies].reduce((n, b) => n + b.rows.length, 0) > 5);
    return t ? [...t.tHead.rows[t.tHead.rows.length - 1].cells].filter(c => c.classList.contains('tx-s')).length : -1; });
  ck('Estimation submittal log: headings sort', es > 2, es);
  const tv = await p.evaluate(async () => { await HELP.goTo({ go: { page: 'estimation', tab: 'boards', kb: 'board', kbView: 'table' } }); await new Promise(r => setTimeout(r, 3500));
    const d = document.getElementById('pg-boards-frame').contentDocument; const t = d.querySelector('table.tv'); return t ? t.querySelectorAll('th.tx-s').length : -1; });
  ck('Trello table keeps its own sorting (not doubled)', tv === 0, tv);
  // ---- the main button floats --------------------------------------------------------------
  await go(p, { page: 'accounts', tab: 'invoices', sub: 'tax' }); await sleep(2500);
  const inv = await p.evaluate(() => { const b = document.getElementById('inv-save-pdf'); return b && [b.classList.contains('fab'), getComputedStyle(b).position]; });
  ck('Tax invoice: "Save & open PDF" floats', inv && inv[0] && inv[1] === 'fixed', inv);
  await go(p, { page: 'store', tab: 'store', sub: 'give' }); await sleep(2500);
  const out = await p.evaluate(() => { const b = document.getElementById('out-save-btn'); return b && [b.classList.contains('fab'), getComputedStyle(b).position]; });
  ck('Give out to a site floats', out && out[0] && out[1] === 'fixed', out);
  // ---- live card with nothing recorded -------------------------------------------------------
  await go(p, { page: 'attendance', tab: 'livecard' }); await sleep(2500);
  const lc = await p.evaluate(async () => { const opened = []; const o = window.open; window.open = u => { opened.push(u); return null; };
    const c = document.getElementById('livecard-cycle'); const opts = [...c.options].map(x => x.value); c.value = opts[0];
    await selectLiveCardWorker((employees.find(e => e.active !== false) || employees[0]).emp_no); await new Promise(r => setTimeout(r, 800));
    const empty = /No attendance recorded yet/.test(document.getElementById('livecard-detail').textContent);
    exportLiveCard('pdf'); window.open = o;
    return { empty, opened, msg: document.getElementById('livecard-status').textContent }; });
  ck('Live card, nothing recorded: Export says so, no error tab', !lc.empty || (lc.opened.length === 0 && /nothing to print/.test(lc.msg)), lc);
  ck('no script errors (desktop)', !p.errs.length, p.errs);
  // ---- phone: hints that do not fit, small buttons -------------------------------------------
  const q = await login(await br.newContext({ ...devices['iPhone 13'] }));
  await go(q, { page: 'store', tab: 'requests', sub: 'requests' }); await sleep(3000);
  const ph = await q.evaluate(() => { const cv = document.createElement('canvas').getContext('2d'); const cut = [];
    document.querySelectorAll('.screen.active input[placeholder]').forEach(i => { if (!i.getClientRects().length || i.value) return; const cs = getComputedStyle(i); cv.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
      const room = i.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight); if (cv.measureText(i.placeholder).width > room + 2) cut.push(i.placeholder); });
    const sh = [...document.querySelectorAll('.screen.active input[data-ph-full]')].map(i => [i.placeholder, i.dataset.phFull, i.title]);
    return { cut, sh }; });
  ck('Phone, material request: no hint cut off', ph.cut.length === 0, ph.cut);
  ck('the full hint is kept on the tooltip', ph.sh.every(([s, f, t]) => s === f || t === f), ph.sh);
  await go(q, { page: 'attendance', tab: 'attendance' }); await sleep(2500);
  const tap = await q.evaluate(() => [...document.querySelectorAll('.screen.active .att-cal button')].filter(b => b.getClientRects().length).map(b => { const r = b.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }));
  ck('Phone, attendance month arrows are finger-sized', tap.length && tap.every(([w, h]) => w >= 30 && h >= 30), tap);
  ck('no script errors (phone)', !q.errs.length, q.errs);
  await br.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
