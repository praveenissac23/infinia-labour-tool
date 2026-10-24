// Estimation > Bills > Work done: a line that "follows the line on row 21" is a link that takes you to row 21
// (scrolled into view, flashed, its % box focused) - also when a search or filter had hidden that line.
const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/billsfol_';
const D = process.env.BILLS_DIR || '/mnt/user-data/attachments/80e871d8-70e2-5c6a-a360-434939dea359/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const file = pat => D + fs.readdirSync(D).find(n => n.includes(pat) && n.endsWith('.xlsx'));

(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  let meta = {};
  for (let i = 0; i < 10 && !meta.projects; i++) {          // the server may still be warming up
    meta = await p.evaluate(async () => (await fetch('/store/est/meta', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).catch(() => ({}));
    if (!meta.projects) { await sleep(1500); await p.reload(); await sleep(1000); if (await p.$('#lg-u')) { await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500); } }
  }
  const P = meta.projects.find(x => x.code === '914' || x.code === '913').id;
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); }, [P]); await p.reload(); await sleep(1800);
  await p.click('#ipa-up'); await sleep(300);
  await p.setInputFiles('#fm-file', file('914_-_IPA_-_07')); await p.fill('#f-name', '914 - consultant IPA');
  await p.click('#m-save'); await sleep(8000);
  await p.click('#ipa-new'); await sleep(3500);

  const links = await p.$$('a.fl[data-goto]');
  ck('"follows" lines are links', links.length >= 10, links.length);
  const txt = await links[0].textContent();
  ck('link names the item and the row', /follows item 4 \(row 21\)/.test(txt), txt);
  // go to the bottom so the target is off screen, then click a link
  const far = links[3]; await far.scrollIntoViewIfNeeded(); await sleep(200);
  await far.click(); await sleep(1200);
  const st = await p.evaluate(() => {
    const id = document.querySelector('a.fl[data-goto]').dataset.goto, tr = document.querySelector(`tr[data-line="${CSS.escape(id)}"]`);
    const r = tr.getBoundingClientRect();
    return { inView: r.top >= 0 && r.bottom <= innerHeight, flash: tr.classList.contains('flash'), focused: tr.contains(document.activeElement) && document.activeElement.tagName === 'INPUT', item: tr.querySelector('.it').textContent };
  });
  ck('click takes you to row 21 (item 4): in view, highlighted, % box ready', st.inView && st.flash && st.focused && st.item === '4', st);
  await p.screenshot({ path: SH + '1_jump.png' });

  // hidden by a search: the link clears it and still gets there
  await p.fill('#ipa-q', '4.2.3'); await sleep(700);
  const goto = await p.getAttribute('a.fl[data-goto$="|34"]', 'data-goto');
  ck('search shows only the 4.2.3 lines', !(await p.$(`tr[data-line="${goto}"]`)), goto);
  await p.click('a.fl[data-goto$="|34"]'); await sleep(1300);
  const st2 = await p.evaluate(g => { const tr = document.querySelector(`tr[data-line="${CSS.escape(g)}"]`); return tr && { q: document.querySelector('#ipa-q').value, flash: tr.classList.contains('flash'), item: tr.querySelector('.it').textContent }; }, goto);
  ck('link clears the search and goes to row 34 (item 4.2.2.1)', st2 && st2.q === '' && st2.flash && st2.item === '4.2.2.1', st2);
  await p.screenshot({ path: SH + '2_after_search.png' });

  ck('no page errors', errs.length === 0, errs);
  await br.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  process.exit(bad ? 1 : 0);
})();
