// Visa files: Jomon (PRO) starts a file, pays a stage on PRO petty cash with
// the visa file picked, the file shows the cost and the stage; completed.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, url, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + url); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); return p;
}
const openVisa = async p => { await p.evaluate(() => pgTab('labour')); await p.waitForTimeout(600); await p.evaluate(() => pgSub('visa')); await p.waitForTimeout(1800); };
(async () => {
  const b = await chromium.launch();
  const j = await login(b, 'jomon', 'pass12345', '/?p=reports');
  await openVisa(j);
  ck('Visa files opens for the PRO', await j.locator('#screen-visa').isVisible());
  ck('Preview / PDF / Excel / Share', await j.locator('#screen-visa .exp-btns .btn').count() === 4);
  const who = await j.evaluate(async () => (await apiCall('/store/visa/people')).people.find(p => !p.staff));
  await j.click('#vf-new'); await j.waitForTimeout(500);
  await j.fill('#vf-p', `${who.name} · ${who.no}`);
  await j.selectOption('#vf-k', 'new');
  ck('the type shows its 8 stages', await j.locator('#vf-kst .vf-chip').count() === 8);
  await j.click('#vf-ok'); await j.waitForTimeout(1500);
  ck('file started and listed', await j.locator('#vf-body tr.vf-row').count() === 1 && /0 of 8/.test(await j.locator('#vf-body').textContent()));
  // PRO petty cash: pick the file and a stage
  await j.goto(B + '/?p=accounts#petty:pro'); await j.waitForTimeout(3500);
  ck('PRO book shows the visa file box', await j.locator('#pc-visa').isVisible());
  const fid = await j.evaluate(() => PC_VF.files[0].id);
  await j.selectOption('#pc-vfile', String(fid)); await j.waitForTimeout(300);
  await j.click('#pc-vstages .vf-chip >> text=Entry permit'); await j.waitForTimeout(200);
  const desc = await j.inputValue('#pc-desc');
  ck('description fills itself', /New visa - Entry permit$/.test(desc), desc);
  ck('supplier fills MOHRE & GDRFA', await j.inputValue('#pc-sup') === 'MOHRE & GDRFA');
  await j.fill('#pc-amt', '2750');
  await j.screenshot({ path: SH + 'visa_pro_form.png' });
  await j.click('#pc-save'); await j.waitForTimeout(2000);
  ck('the line shows its visa file', /Visa file: .* · Entry permit/.test(await j.locator('#pc-body').textContent()));
  ck('form cleared, no visa picked', await j.inputValue('#pc-vfile') === '');
  // the cash-received side has no visa box
  await j.click('#screen-pettycash .pc-kind button[data-k="received"]'); await j.waitForTimeout(200);
  ck('no visa box on cash received', !(await j.locator('#pc-visa').isVisible()));
  await j.click('#screen-pettycash .pc-kind button[data-k="paid"]');
  // back to Visa files
  await j.goto(B + '/?p=reports'); await j.waitForTimeout(2500); await openVisa(j);
  const t = await j.locator('#vf-body').textContent();
  ck('cost and stage on the file', /2,750\.00/.test(t) && /1 of 8/.test(t) && /next: Change of status/.test(t), t.slice(0, 200));
  await j.locator('#vf-body tr.vf-row').first().locator('.vf-seg').nth(1).click(); await j.waitForTimeout(1200);
  ck('a stage ticked from the bar', /2 of 8/.test(await j.locator('#vf-body').textContent()));
  await j.locator('#vf-body tr.vf-row').first().click(); await j.waitForTimeout(400);
  ck('row opens with its payments', await j.locator('#vf-body .vf-pays tr').count() === 1);
  await j.screenshot({ path: SH + 'visa_files.png' });
  j.on('dialog', d => d.accept());
  await j.locator('#vf-body button', { hasText: 'Mark completed' }).click(); await j.waitForTimeout(400);
  const ok = j.locator('.hr-ask [data-a="yes"]');
  if (await ok.count()) await ok.first().click();
  await j.waitForTimeout(1500);
  ck('completed: gone from Ongoing', await j.locator('#vf-body tr.vf-row').count() === 0);
  await j.click('.vf-pill >> text=Completed'); await j.waitForTimeout(1200);
  ck('listed under Completed with its cost', /Completed ✓/.test(await j.locator('#vf-body').textContent()) && /2,750\.00/.test(await j.locator('#vf-body').textContent()));
  ck('no page errors', j.errs.length === 0, j.errs);
  const w = await login(b, 'jomon', 'pass12345', '/?p=reports', 390); await openVisa(w);
  ck('phone width: no sideways scroll', await w.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
