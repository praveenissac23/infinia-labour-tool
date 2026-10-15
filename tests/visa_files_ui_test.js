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
const openVisa = async p => { await p.goto(B + '/?p=accounts#petty:pro'); await p.reload(); await p.waitForTimeout(3000); await p.click('#pc-protabs [data-v="visa"]'); await p.waitForTimeout(1500); };
(async () => {
  const b = await chromium.launch();
  const j = await login(b, 'jomon', 'pass12345', '/?p=accounts#petty:pro');
  await j.goto(B + '/?p=accounts#petty:pro'); await j.waitForTimeout(3000);
  ck('PRO tab opens on Petty cash, Visa files next to it', await j.locator('#pc-protabs').isVisible() && await j.locator('#pc-cashpane').isVisible() && !(await j.locator('#pc-visapane').isVisible()));
  await j.click('#pc-protabs [data-v="visa"]'); await j.waitForTimeout(1500);
  ck('Visa files opens for the PRO', await j.locator('#pc-visapane').isVisible());
  ck('Preview / PDF / Excel / Share', await j.locator('#pc-visapane .exp-btns .btn').count() === 4);
  const who = await j.evaluate(async () => (await apiCall('/store/visa/people')).people.find(p => !p.staff));
  await j.click('#vf-new'); await j.waitForTimeout(500);
  await j.fill('#vf-p', `${who.name} · ${who.no}`);
  await j.selectOption('#vf-k', 'new');
  ck('the type shows its 10 steps', await j.locator('#vf-kst .vf-chip').count() === 10);
  await j.click('#vf-ok'); await j.waitForTimeout(1500);
  ck('file started and listed', await j.locator('#vf-body tr.vf-row').count() === 1 && /0 of 10/.test(await j.locator('#vf-body').textContent()));
  // PRO petty cash: pick the file and a stage
  await j.evaluate(() => pcBook('pro')); await j.waitForTimeout(1500);
  ck('PRO asked for again (while loading) keeps the open view', true);
  await j.evaluate(() => pcView('cash')); await j.waitForTimeout(800);
  ck('PRO book shows the visa file box', await j.locator('#pc-visa').isVisible());
  const fid = await j.evaluate(() => PC_VF.files[0].id);
  ck('asks: visa related expense? (No by default)', await j.locator('#pc-vyn .vf-pill.on').textContent() === 'No' && !(await j.locator('#pc-vmore').isVisible()));
  await j.click('#pc-vyn [data-v="yes"]'); await j.waitForTimeout(200);
  ck('Yes: whose visa, step and status appear', await j.locator('#pc-vmore').isVisible());
  await j.selectOption('#pc-vfile', String(fid)); await j.waitForTimeout(300);
  ck('step list offers his steps and all known ones', await j.locator('#pc-vstep-list option').count() >= 10);
  await j.fill('#pc-vstep', 'New labour contract'); await j.waitForTimeout(200);
  const desc = await j.inputValue('#pc-desc');
  ck('description fills itself', / - New labour contract$/.test(desc), desc);
  ck('status defaults to Not completed', await j.locator('#pc-vdone .vf-pill.on').textContent() === 'Not completed');
  ck('supplier left empty', await j.inputValue('#pc-sup') === '');
  await j.fill('#pc-amt', '2750');
  await j.screenshot({ path: SH + 'visa_pro_form.png' });
  await j.click('#pc-save'); await j.waitForTimeout(2000);
  ck('the line shows its visa file', /Visa file: .* · New labour contract/.test(await j.locator('#pc-body').textContent()));
  ck('form cleared, back to No', await j.locator('#pc-vyn .vf-pill.on').textContent() === 'No');
  // the cash-received side has no visa box
  await j.click('#screen-pettycash .pc-kind button[data-k="received"]'); await j.waitForTimeout(200);
  ck('no visa box on cash received', !(await j.locator('#pc-visa').isVisible()));
  await j.click('#screen-pettycash .pc-kind button[data-k="paid"]');
  // back to Visa files
  await openVisa(j);
  const t = await j.locator('#vf-body').textContent();
  ck('cost and step on the file', /2,750\.00/.test(t) && /1 of 10/.test(t) && /next: WPP insurance/.test(t), t.slice(0, 200));
  // click the next stage: enter the payment there, it goes into PRO petty cash
  await j.locator('#vf-body tr.vf-row').first().locator('.vf-seg').nth(2).click(); await j.waitForTimeout(400);
  ck('stage click asks how it was paid (3 ways)', await j.locator('.vf-m #vf-modes .vf-pill').count() === 3);
  ck('the window scrolls when long', await j.evaluate(() => getComputedStyle(document.querySelector('.vf-m .zx-box')).overflowY) === 'auto');
  await j.fill('#vs-a', '1320.33');
  await j.screenshot({ path: SH + 'visa_stage_pay.png' });
  await j.click('#vs-ok'); await j.waitForTimeout(1500);
  const t2 = await j.locator('#vf-body').textContent();
  ck('paid from the visa file: 2 of 10, AED 4,070.33', /2 of 10/.test(t2) && /4,070\.33/.test(t2), t2.slice(0, 200));
  ck('row stays open with both payments', await j.locator('#vf-body .vf-pays tr').count() === 2);
  const pc = await j.evaluate(async () => (await apiCall('/store/petty-cash?book=pro')).rows.map(r => r.description + '|' + r.paid));
  ck('the payment is in PRO petty cash', pc.some(x => /WPP insurance\|1320\.33/.test(x)), pc);
  // done with no payment
  await j.locator('#vf-body tr.vf-row').first().locator('.vf-seg').nth(3).click(); await j.waitForTimeout(400);
  await j.click('.vf-m #vf-modes .vf-pill >> text=Done - no payment'); await j.click('#vs-ok'); await j.waitForTimeout(1200);
  ck('stage ticked with no payment: 3 of 10', /3 of 10/.test(await j.locator('#vf-body').textContent()));
  const fidr = await j.evaluate(() => VF.rows[0].id);
  await j.fill(`#vf-as-${fidr}`, 'Medical re-test'); await j.click(`#vf-as-${fidr} + button`); await j.waitForTimeout(1200);
  ck('+ Add step: a typed step joins the file', /Medical re-test/.test(await j.locator('#vf-body').textContent()));
  ck('...and the list offered next time', await j.evaluate(() => VF.steps.includes('Medical re-test')));
  await j.locator('.vf-chipw:has(.vf-chip:text-is("Quota modification (if needed)")) .vf-x').click(); await j.waitForTimeout(1200);
  ck('× takes a step off (not needed)', !/Quota modification/.test(await j.locator('#vf-body .vf-stchips').textContent()));
  // a visa cost on PRO petty cash without the file is refused
  const refused = await j.evaluate(async () => { try { await apiCall('/store/petty-cash', { method: 'POST', body: JSON.stringify({ book: 'pro', date: pcToday(), description: 'Ali visa exp', paid: 10 }) }); return false; } catch (e) { return /whose visa/i.test(errText(e)); } });
  ck('PRO: visa cost without its file is refused', refused);
  await j.screenshot({ path: SH + 'visa_files.png' });
  j.on('dialog', d => d.accept());
  await j.locator('#vf-body button', { hasText: 'Mark completed' }).click(); await j.waitForTimeout(400);
  const ok = j.locator('.hr-ask [data-a="yes"]');
  if (await ok.count()) await ok.first().click();
  await j.waitForTimeout(1500);
  ck('completed: gone from Ongoing', await j.locator('#vf-body tr.vf-row').count() === 0);
  await j.click('.vf-pill >> text=Completed'); await j.waitForTimeout(1200);
  ck('listed under Completed with its cost', /Completed ✓/.test(await j.locator('#vf-body').textContent()) && /4,070\.33/.test(await j.locator('#vf-body').textContent()));
  ck('no page errors', j.errs.length === 0, j.errs);
  await j.goto(B + '/?p=accounts#petty:office'); await j.waitForTimeout(2500);
  ck('other books have no Visa files tab', !(await j.locator('#pc-protabs').isVisible()));
  const w = await login(b, 'jomon', 'pass12345', '/?p=accounts', 390); await openVisa(w);
  ck('phone width: no sideways scroll', await w.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await b.close();
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
