// PRO petty cash, the visa question: no Visa files tab; Yes -> whose visa
// (ongoing names offered, a new name opens a visa), step (pick or type),
// Not completed / Completed.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + '/?p=accounts#petty:pro'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(3000); return p;
}
(async () => {
  const b = await chromium.launch();
  const j = await login(b, 'jomon', 'pass12345');
  await j.goto(B + '/?p=accounts#petty:pro'); await j.reload(); await j.waitForTimeout(3500);
  ck('no Visa files tab', await j.locator('#pc-protabs').count() === 0 && await j.locator('#pc-visapane').count() === 0);
  ck('PRO form asks: visa related expense? (No first)', await j.locator('#pc-visa').isVisible() && (await j.locator('#pc-vyn .vf-pill.on').textContent()) === 'No' && !(await j.locator('#pc-vmore').isVisible()));
  const entry = async (desc, amt, who, step, done) => {
    await j.fill('#pc-desc', desc); await j.fill('#pc-sup', 'Cash payment'); await j.fill('#pc-amt', String(amt));
    if (who) {
      await j.click('#pc-vyn [data-v="yes"]'); await j.waitForTimeout(150);
      await j.fill('#pc-vperson', who); await j.press('#pc-vperson', 'Enter');
      await j.fill('#pc-vstep', step);
      if (done) await j.click('#pc-vdone [data-v="yes"]');
    }
  };
  await entry('Medical for Eric', 320, 'Eric Mambo', 'Medical and EID', false);
  ck('new name: says a new visa will open', /New visa - opened for Eric Mambo/.test(await j.textContent('#pc-vnew')));
  ck('step list holds the standard steps', await j.locator('#pc-vstep-list option').count() >= 18);
  ck('description left as typed', await j.inputValue('#pc-desc') === 'Medical for Eric');
  await j.screenshot({ path: SH + 'visa_pro_form.png' });
  await j.click('#pc-save'); await j.waitForTimeout(2000);
  ck('saved: line shows whose visa and step', /Visa file: Eric Mambo · Medical and EID/.test(await j.textContent('#pc-body')));
  ck('form back to No', (await j.locator('#pc-vyn .vf-pill.on').textContent()) === 'No');
  await j.click('#pc-vyn [data-v="yes"]'); await j.waitForTimeout(400);
  ck('Eric now offered under Whose visa', await j.evaluate(() => [...document.querySelectorAll('#pc-vperson-list option')].some(o => o.value === 'Eric Mambo')));
  await j.click('#pc-vyn [data-v="no"]');
  await entry('Eric re-test', 75, 'Eric Mambo', 'Medical re-test', true);
  ck('known name: no "new visa" note', !(await j.locator('#pc-vnew').isVisible()));
  await j.click('#pc-save'); await j.waitForTimeout(2000);
  const st = await j.evaluate(async () => (await apiCall('/store/visa/open')));
  ck('typed step kept for next time', st.steps.includes('Medical re-test'));
  ck('Completed: Eric no longer offered', !st.files.some(f => f.person === 'Eric Mambo'), st.files.map(f => f.person));
  await entry('Travel report', 275.65, '', '', false); await j.fill('#pc-sup', 'GDRFA');
  await j.click('#pc-save'); await j.waitForTimeout(1500);
  ck('a normal line (No) saves with any description', /Travel report/.test(await j.textContent('#pc-body')));
  ck('no page errors', j.errs.length === 0, j.errs);
  const w = await login(b, 'jomon', 'pass12345', 390);
  ck('phone width: no sideways scroll', await w.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
