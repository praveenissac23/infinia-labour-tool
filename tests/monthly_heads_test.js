// Monthly report preview: every heading readable - its words and its (i) inside its own column, nothing
// running into the next heading.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/mheads_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 600))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => { const br = await chromium.launch();
  for (const [w, h] of [[1440, 900], [1280, 800], [1000, 700]]) {
    const p = await (await br.newContext({ viewport: { width: w, height: h } })).newPage();
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
    await p.goto(B + '/?p=payroll'); await sleep(2500);
    await p.evaluate(() => switchScreen('monthly')); await sleep(1500);
    await p.evaluate(() => { const s = document.querySelector('#screen-monthly select'); if (s) { const o = [...s.options].find(x => /25\/10\/2026/.test(x.text)); if (o) { s.value = o.value; s.dispatchEvent(new Event('change')); } } }); await sleep(1500);
    await p.evaluate(() => { const b = [...document.querySelectorAll('#screen-monthly button')].find(x => /^Preview$/.test(x.textContent.trim())); if (b) b.click(); }); await sleep(3000);
    const r = await p.evaluate(() => {
      const ths = [...document.querySelectorAll('#monthly-preview-slot thead th')]; const out = [];
      ths.forEach((th, k) => {
        const tr = th.getBoundingClientRect();
        const kids = [...th.querySelectorAll('*')].concat([th]).filter(e => e.getClientRects().length);
        // every piece of text / icon inside the heading stays inside the heading's box
        const range = document.createRange(); range.selectNodeContents(th); const cr = range.getBoundingClientRect();
        const ic = th.querySelector('.help-i'); const ir = ic && ic.getBoundingClientRect();
        if (cr.right > tr.right + 1 || cr.left < tr.left - 1 || (ir && (ir.right > tr.right + 1 || ir.left < tr.left - 1))) out.push({ k, text: th.textContent.trim(), th: [Math.round(tr.left), Math.round(tr.right)], content: [Math.round(cr.left), Math.round(cr.right)], icon: ir && [Math.round(ir.left), Math.round(ir.right)] });
      });
      return { n: ths.length, bad: out };
    });
    ck(`${w}px: all ${r.n} headings fit their columns (text and (i))`, r.n > 3 && !r.bad.length, r.bad);
    // scrolled down: the heading row pinned at the top must read the same
    // the case on a big screen: the list shown in full and the page scrolled - the heading row is pinned as a copy
    await p.evaluate(() => { const g = document.querySelector('#monthly-preview-slot .grid-wrap'); if (g) { g.dataset.mh = 'none'; g.style.maxHeight = 'none'; } }); await sleep(300);
    await p.evaluate(() => { const c = document.querySelector('.content'); window.scrollTo(0, 900); if (c) c.scrollTop = 900; window.dispatchEvent(new Event('scroll')); }); await sleep(900);
    const f = await p.evaluate(() => {
      const box = [...document.querySelectorAll('.freeze-head')].find(b => getComputedStyle(b).display !== 'none'); if (!box) return { pinned: false, bad: ['no pinned row'] };
      const out = [];
      box.querySelectorAll('th').forEach((th, k) => { const tr = th.getBoundingClientRect(); const range = document.createRange(); range.selectNodeContents(th); const cr = range.getBoundingClientRect();
        if (th.scrollWidth > th.clientWidth + 1 || cr.right > tr.right + 1) out.push({ k, text: th.textContent.trim(), sw: th.scrollWidth, cw: th.clientWidth }); });
      return { pinned: true, bad: out };
    });
    ck(`${w}px: scrolled, the pinned heading row reads the same (no words running into the next)`, !f.bad.length, f);
    await p.screenshot({ path: `${SH}${w}_scrolled.png` });
  }
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0); })();
