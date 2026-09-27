// Reports > Labour: switching between the Cycle report builder and the
// Monthly report must show each table once - no old table flashing in,
// no "loading" row, no redraw jumps.
const { chromium } = require('playwright');
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } }); let bad = 0; const errs = [];
p.on('pageerror', e => errs.push(e.message));
await p.goto('http://127.0.0.1:8032/?p=reports'); await p.fill('#login-username','admin'); await p.fill('#login-password','changeme123'); await p.evaluate('doLogin()'); await p.waitForTimeout(3500);
const watch = () => p.evaluate(() => { window.__f = []; const t0 = performance.now(); (function tick() {
  const card = document.getElementById('report-preview-card');
  const shown = card && card.closest('.screen.active') && getComputedStyle(card).visibility !== 'hidden' && getComputedStyle(card.parentElement).visibility !== 'hidden';
  window.__f.push((document.querySelector('.screen.active') || {}).id + '|' + (shown ? `${Math.round(card.getBoundingClientRect().height)}/${document.querySelectorAll('#report-body tr').length}` : '-'));
  if (performance.now() - t0 < 3000) requestAnimationFrame(tick); })(); });
for (const [to, name, scr] of [['Monthly report', 'opening the Monthly report', 'screen-monthly'], ['Cycle report builder', 'back to the builder', 'screen-reports'], ['Monthly report', 'the Monthly report again', 'screen-monthly']]) {
  await watch(); await p.locator('.pg-subtab', { hasText: to }).click(); await p.waitForTimeout(3200);
  const f = (await p.evaluate(() => window.__f)).filter(x => x.startsWith(scr + '|')).map(x => x.split('|')[1]);
  const states = []; for (const x of f) if (x !== '-' && x !== states[states.length - 1]) states.push(x);
  const ok = states.length === 1; if (!ok) bad++;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}: the table appears once${ok ? ' (' + states[0] + ')' : ' - states ' + JSON.stringify(states)}`);
}
if (errs.length) { bad++; console.log('FAIL script errors', errs); }
console.log(bad ? `${bad} FAILED` : 'MONTHLY REPORT OPENS WITHOUT A FLICKER'); await b.close(); process.exit(bad ? 1 : 0); })();
