// Reports > Cycle report builder: with many columns ticked, every heading (and its i) stays inside its column -
// on the table and on the heading row pinned at the top when the list scrolls.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/rheads_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 600))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const measure = sel => { const out = []; let n = 0;
  document.querySelectorAll(sel).forEach((th, k) => { if (!th.getClientRects().length) return; n++; const tr = th.getBoundingClientRect(); const range = document.createRange(); range.selectNodeContents(th); const cr = range.getBoundingClientRect();
    if (th.scrollWidth > th.clientWidth + 1 || cr.right > tr.right + 1 || cr.left < tr.left - 1) out.push({ k, text: th.textContent.trim(), sw: th.scrollWidth, cw: th.clientWidth }); });
  return { n, bad: out }; };
(async () => { const br = await chromium.launch();
  for (const [w, h] of [[1440, 900], [2000, 1100], [1280, 800]]) {
    const p = await (await br.newContext({ viewport: { width: w, height: h } })).newPage();
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
    await p.goto(B + '/?p=reports'); await sleep(3000);
    await p.evaluate(() => { document.querySelectorAll('#screen-reports input[type=checkbox]').forEach(c => { if (/OT Amount|BH Amount|Final Salary|OT Hours|BH Hours|Days Present|Days Absent|Employee/i.test(c.parentElement.textContent)) c.checked = true; }); }); 
    await p.evaluate(() => { document.querySelectorAll('#screen-reports select').forEach(s => { const o = [...s.options].find(x => /Sep.*25 Oct 2026/.test(x.text)); if (o) { s.value = o.value; s.dispatchEvent(new Event('change')); } }); }); await sleep(800);
    await p.evaluate(() => loadReports()); await sleep(3500);
    let r = await p.evaluate(measure, '#report-preview-card thead th');
    ck(`${w}px: the ${r.n} headings fit their columns`, r.n > 6 && !r.bad.length, r);
    await p.evaluate(() => { const g = document.querySelector('#report-preview-card .grid-wrap'); if (g) { g.dataset.mh = 'none'; g.style.maxHeight = 'none'; } window.scrollTo(0, 1200); const c = document.querySelector('.content'); if (c) c.scrollTop = 1200; window.dispatchEvent(new Event('scroll')); }); await sleep(900);
    const pinned = await p.evaluate(() => !![...document.querySelectorAll('.freeze-head')].find(b => getComputedStyle(b).display !== 'none'));
    r = await p.evaluate(measure, '.freeze-head th');
    ck(`${w}px: scrolled, the pinned heading row reads cleanly${pinned ? "" : " (no pinned row)"}`, pinned && !r.bad.length, r);
    await p.screenshot({ path: `${SH}${w}.png` });
  }
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0); })();
