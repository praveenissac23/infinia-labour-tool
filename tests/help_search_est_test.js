// The top search finds Estimation's sections, Trello's views and the new tasks, and goes there; "Show me" circles
// buttons inside the Estimation frame.   (data: tests/seed_help_data.py)   BASE=... node tests/help_search_est_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
  await p.evaluate(async () => { const m = await apiCall('/store/est/meta'); localStorage.setItem('est_pid', (m.projects.find(x => x.code === '914') || m.projects[0]).id); });
  const results = async q => { await p.fill('#help-search', ''); await p.type('#help-search', q, { delay: 15 }); await sleep(400); return p.$$eval('#help-results .help-r', x => x.map(e => e.textContent.replace(/\s+/g, ' ').trim())); };
  const want = { 'submittal': /Submittals.*Estimation › Projects/, 'invoice tracker': /Invoice tracker/, 'bill': /Bills to client/, 'previous records': /Previous records/,
                 'send to md': /sends it to the MD/i, 'add line bill': /new line or section to a bill/i, 'rfi': /RFI log/, 'calendar': /Trello calendar/, 'power ups': /power-ups/i,
                 'time tracking': /Log time on a Trello card|power-ups/i, 'authority payments': /glance|Project dashboard/i, 'lpo description': /long description/i, 'notifications': /notifications/i,
                 'signature': /Signature & stamp/, 'phone notifications': /Notifications on this phone/, 'backup': /Backup/ };
  for (const [q, re] of Object.entries(want)) { const r = await results(q); ck(`search "${q}" finds it`, r.some(x => re.test(x)), r.slice(0, 5)); }
  // go there: Submittals
  await results('submittals'); await p.evaluate(() => { const r = [...document.querySelectorAll('#help-results .help-r')].find(e => /Submittals/.test(e.textContent) && /Go to/.test(e.textContent)); r && r.click(); }); await sleep(4000);
  const sec = await p.evaluate(() => { const w = document.getElementById('pg-estproj-frame').contentWindow; return w.eval('ST.group + "." + ST.sec'); });
  ck('picking it opens Estimation > Projects > Submittals', sec === 'site.submittal', sec);
  await p.screenshot({ path: '/tmp/claude-0/hs_1_submittals.png' });
  // Trello calendar
  await results('trello calendar'); await p.evaluate(() => { const r = [...document.querySelectorAll('#help-results .help-r')].find(e => /Trello calendar/.test(e.textContent)); r && r.click(); }); await sleep(4500);
  const v = await p.evaluate(() => { const w = document.getElementById('pg-boards-frame').contentWindow; return w.eval('S.board && S.view'); });
  ck('Trello calendar opens a board in the Calendar view', v === 'calendar', v);
  // Show me inside the frame
  await p.evaluate(() => HELP.tour(HELP_GUIDES.find(g => g.id === 'est-bill-line'))); await sleep(6000);
  await p.evaluate(() => HELP.step(1)); await sleep(1500);
  const st = await p.evaluate(() => { const r = document.querySelector('.help-ring'); return { missing: HELP.state.missing, shown: r && r.style.display !== 'none', box: r && r.getBoundingClientRect().toJSON() }; });
  ck('Show me circles "+ Line" inside the Estimation frame (a bill open on Work done)', !st.missing && st.shown && st.box.left > 220 && st.box.top > 100, st);
  await p.screenshot({ path: '/tmp/claude-0/hs_2_showme.png' });
  await results('change password'); await p.evaluate(() => { const r = [...document.querySelectorAll('#help-results .help-r')].find(e => /Change my password/.test(e.textContent)); r && r.click(); }); await sleep(2000);
  ck('Change my password: lands on Settings with the password card in view', await p.evaluate(() => { const c = document.getElementById('pg-password-card'); const r = c && c.getBoundingClientRect(); return !!(r && r.top < innerHeight && r.bottom > 0 && c.offsetParent); }));
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
