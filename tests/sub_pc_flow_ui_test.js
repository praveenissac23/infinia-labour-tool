// Subcontractor certificates - the approval way on the pages people use: the invoice tracker shows whose desk each one
// is on and for how long (stuck in red), "Waiting for me", the button only for the person whose turn it is; Accounts'
// Payments page: to verify (with the checks) and to pay, WhatsApp to the MD; the MD's approval page from the link: the
// PDF itself on a phone, Approve / Reject below it, done -> Accounts told.
const { chromium, devices } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/pcflow_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const errs = [];
  const page = async (opts = { viewport: { width: 1440, height: 900 } }) => { const p = await (await br.newContext(opts)).newPage(); p.on('pageerror', e => errs.push(e.message)); return p; };
  const p0 = await page(); await p0.goto(B + '/health');
  const tokOf = async (u, pw) => { for (let i = 0; i < 10; i++) { const t = await p0.evaluate(async ([u, pw]) => { try { const r = await fetch('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username: u, password: pw }) }); return (await r.json()).access_token; } catch (e) { return null; } }, [u, pw]); if (t) return t; await sleep(1500); } };
  const ADM = await tokOf('admin', 'changeme123');
  const api = (path, opt = {}, tok = ADM) => p0.evaluate(async ([path, opt, tok]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return { s: r.status, j: await r.json().catch(() => ({})) }; }, [path, opt, tok]);
  const mkUser = async (u, full, perms) => { let r = await api('/users', { method: 'POST', body: { username: u, password: u + '12345', full_name: full, role: 'office' } });
    const id = r.s < 300 ? r.j.id : (await api('/users')).j.find(x => x.username === u).id; await api(`/users/${id}/permissions`, { method: 'POST', body: { permissions: perms } }); };
  await mkUser('anoopf', 'Anoop S', 'estimation_projects'); await mkUser('shafeeqf', 'Shafeeq', 'accounts_bank');
  await api('/store/est/rules', { method: 'PUT', body: { pc_cm: 'Anoop', stuck_days: 2 } });
  const P = (await api('/store/est/meta')).j.projects.find(x => x.code === '909').id;
  const sub = async (name, scope) => (await api('/store/est/subs', { method: 'POST', body: { project_id: P, name, scope, value: 600000, adv_pct: 10, ret_pct: 5, vat_pct: 5 } })).j.id;
  const pc = async (sid, ref, work, steps, as = {}) => { const id = (await api('/store/est/subpcs', { method: 'POST', body: { sub_id: sid, inv_ref: ref, inv_amount: work / 4, work_cum: work, received: '2026-10-20' } })).j.id;
    for (const s of steps) { const r = await api(`/store/est/subpcs/${id}/step`, { method: 'POST', body: Object.assign({ step: s }, s === 'Certified' ? { by: 'Akhil' } : {}) }); if (r.s !== 200) console.log('step', s, r.j); } return id; };
  const wood = await sub('Woodcraft Interiors', 'Joinery'), glass = await sub('Gulf Glass', 'Glazing'), steel = await sub('Steel Line', 'Steel works'), noor = await sub('Al Noor Technical', 'MEP');
  const W = await pc(wood, 'WD/71', 240000, ['Certified', 'Prepared']);                       // Anoop's turn
  const G = await pc(glass, 'GG/229', 120000, ['At site']);                                   // site's turn - made stuck below
  const S = await pc(steel, 'SL/1180', 300000, ['Certified', 'Prepared', 'CM approved']);     // Accounts to verify
  const N = await pc(noor, 'ANT/14', 90000, ['Certified', 'Prepared', 'CM approved', 'Verified', 'Sent to MD']);   // with the MD
  // Gulf Glass has sat at site for 4 days
  await api(`/store/est/subpcs/${G}`, { method: 'PATCH', body: { to_site: '2026-10-22' } });
  await p0.evaluate(() => 0);
  const AN = await tokOf('anoopf', 'anoopf12345'), SF = await tokOf('shafeeqf', 'shafeeqf12345');

  // ---- Anoop: the invoice tracker ----
  const a = await page();
  await a.goto(B + '/portal/est-app.html?view=projects'); await a.evaluate(([t, pid]) => { sessionStorage.setItem('infinia_token', t); localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.inv'); }, [AN, String(P)]);
  await a.goto(B + '/portal/est-app.html?view=projects'); await a.waitForSelector('tr[data-row]', { timeout: 20000 }).catch(() => {}); await sleep(800);
  const rowTxt = id => a.textContent(`tr[data-row="${id}"]`).then(t => t.replace(/\s+/g, ' '));
  ck('Anoop: his row says "You" - to approve, and is first', /You\s*to approve/.test(await rowTxt(W)) && (await a.$$eval('tr[data-row]', r => r.map(x => x.dataset.row)))[0] === String(W), await rowTxt(W));
  ck('Anoop: the Approve button only on his row', await a.isVisible(`[data-pc="${W}"][data-to="CM approved"]`) && !(await a.$(`[data-pc="${S}"][data-to="Verified"]`)));
  ck('others show whose turn: "Accounts\'s turn", "Managing Director\'s turn"', /Accounts's turn/.test(await rowTxt(S)) && /Managing Director's turn/.test(await rowTxt(N)), [await rowTxt(S), await rowTxt(N)]);
  ck('the last stamp shows: who prepared, when', /Prepared - Admin|Prepared - /.test(await rowTxt(W)));
  const chips = await a.textContent('.chips.crow');
  ck('chips: Waiting for me 1', /Waiting for me\s*1/.test(chips), chips);
  await a.screenshot({ path: SH + '1_anoop_tracker.png' });
  await a.click(`[data-pc="${W}"][data-to="CM approved"]`); await sleep(1200);
  ck('Anoop approves in one click - it moves to Accounts', /Accounts\s*to verify/.test(await rowTxt(W)), await rowTxt(W));
  // send back
  ck('nothing waiting for Anoop now', /Waiting for me\s*0/.test(await a.textContent('.chips.crow')));

  // ---- the stuck one, seen by the admin ----
  const ad = await page();
  await ad.goto(B + '/portal/est-app.html?view=projects'); await ad.evaluate(([t, pid]) => { sessionStorage.setItem('infinia_token', t); localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.inv'); }, [ADM, String(P)]);
  // 4 days at site: stage_at back-dated through the API is not possible - the old-style date fallback is used when stage_at is empty, so the row is made from before
  await ad.goto(B + '/portal/est-app.html?view=projects'); await ad.waitForSelector('tr[data-row]', { timeout: 20000 }).catch(() => {}); await sleep(800);
  ck('admin (Managing Director): Waiting for me = the one with the MD', await ad.isVisible(`[data-pc="${N}"][data-to="MD approved"]`) && /You\s*to approve/.test((await ad.textContent(`tr[data-row="${N}"]`)).replace(/\s+/g, ' ')));
  ck('WhatsApp button on the one with the MD', await ad.isVisible(`[data-wa="${N}"]`));

  // ---- Shafeeq: Accounts > Subcontractor payments ----
  const s = await page();
  await s.goto(B + '/portal/est-app.html?view=pay'); await s.evaluate(t => sessionStorage.setItem('infinia_token', t), SF);
  await s.goto(B + '/portal/est-app.html?view=pay'); await s.waitForSelector(`[data-pver="${S}"]`, { timeout: 20000 }).catch(() => {}); await sleep(600);
  ck('Shafeeq: Waiting for me - two to verify (Steel Line, Woodcraft)', await s.isVisible(`[data-pver="${S}"]`) && await s.isVisible(`[data-pver="${W}"]`));
  const t = (await s.textContent('table.t')).replace(/\s+/g, ' ');
  ck('the checks show for one to verify', /First certificate|Previous/.test(t) && /Agreement on file|No agreement/.test(t), t.slice(0, 300));
  await s.screenshot({ path: SH + '2_shafeeq_payments.png' });
  await s.click(`[data-pver="${S}"]`); await sleep(1500);
  ck('verified -> it stays with Accounts: "Verified - send to MD" with a Send to MD button', await s.isVisible(`[data-psend="${S}"]`) && /Verified - send to MD/.test(await s.textContent('table.t')) && !(await s.isVisible('#modal')));
  await s.screenshot({ path: SH + '2b_send_to_md.png' });
  await s.click(`[data-psend="${S}"]`); await sleep(1500);
  const msg = await s.textContent('#m-body').catch(() => '');
  ck('Send to MD -> "Sent to the Managing Director - tell them on WhatsApp?" with the link typed', await s.isVisible('#modal') && /approve\.html\?pc=/.test(msg) && /Steel Line PC 01/.test(msg), msg);
  await s.screenshot({ path: SH + '3_shafeeq_whatsapp.png' });
  const wa = await s.evaluate(() => { let u = ''; window.open = x => { u = x; }; document.querySelector('#m-save').click(); return new Promise(r => setTimeout(() => r(u), 300)); });
  ck('WhatsApp opens with the message (wa.me, the approval link)', /^https:\/\/wa\.me\/\?text=/.test(wa) && decodeURIComponent(wa).includes('/portal/approve.html?pc=' + S), wa);
  const st = (await api(`/store/est/subpcs/${S}/approval`)).j;
  ck('it is now with the MD', st.status === 'Verified' && st.can_act && st.turn === 'md');
  await s.click('#modal [id="m-cancel"]').catch(() => {}); await sleep(400);
  await s.click('[data-pf="Verified"]'); await sleep(500);
  ck('Payments page: "With the MD", sent time shown', /With the MD\s*sent/.test((await s.textContent('table.t')).replace(/\s+/g, ' ')));

  // ---- the MD on the phone: the link ----
  const m = await page({ ...devices['iPhone 13'] });
  await m.goto(B + `/portal/approve.html?pc=${S}`); await sleep(1200);
  ck('not signed in on this phone: asks once (keep me signed in ticked)', await m.isVisible('#lg-u') && await m.isChecked('#lg-k'));
  await m.fill('#lg-u', 'admin'); await m.fill('#lg-p', 'changeme123'); await m.click('#lg-go');
  await m.waitForSelector('#pages canvas', { timeout: 25000 }).catch(() => {}); await sleep(1500);
  const cv = await m.evaluate(() => { const c = document.querySelectorAll('#pages canvas'); const r = c[0] && c[0].getBoundingClientRect(); return { n: c.length, w: r && r.width, vw: innerWidth, px: c[0] && c[0].width }; });
  ck('the PDF itself: every page drawn, full width, sharp enough to zoom', cv.n >= 1 && cv.w > cv.vw * 0.9 && cv.px > cv.w * 2, cv);
  ck('Approve and Reject fixed at the bottom, the amount beside', await m.isVisible('#b-ok') && await m.isVisible('#b-no') && /AED/.test(await m.textContent('.bar')));
  ck('"2 of 2"? - the other one with the MD comes next (1 of 2)', /1 of 2/.test(await m.textContent('#t-title')), await m.textContent('#t-title'));
  await m.screenshot({ path: SH + '4_md_phone_pdf.png' });
  await m.click('#b-ok'); await sleep(400);
  await m.screenshot({ path: SH + '5_md_confirm.png' });
  await m.click('#c-go'); await sleep(1500);
  ck('approved: done, Accounts told, next one offered', /Approved/.test(await m.textContent('.donebox')) && await m.isVisible('#d-next'));
  await m.screenshot({ path: SH + '6_md_done.png' });
  const after = (await api(`/store/est/subpcs/${S}/approval`)).j;
  ck('the portal is updated: MD approved, now Accounts to pay', after.status === 'MD approved' && after.waiting === 'Accounts');
  await m.click('#d-next'); await m.waitForSelector('#b-no', { timeout: 20000 }).catch(() => {}); await sleep(800);
  await m.click('#b-no'); await sleep(300);
  await m.fill('#r-note', 'Back-charge for the crane not deducted'); await m.selectOption('#r-to', 'CM approved');
  await m.screenshot({ path: SH + '7_md_reject.png' });
  await m.click('#r-go'); await sleep(1300);
  const nb = (await api(`/store/est/subpcs/${N}/approval`)).j;
  ck('rejected: back with Accounts, the note on it', nb.status === 'CM approved' && nb.stamps.some(x => x.back && /crane/.test(x.note)), nb);
  // reloaded tracker for Anoop shows the note? (it went to Accounts) - Shafeeq's page shows the note
  await s.goto(B + '/portal/est-app.html?view=pay'); await sleep(2500);
  ck("Shafeeq sees the MD's note on it", /crane not deducted/.test(await s.textContent('table.t')));
  // Shafeeq pays the approved one
  await s.click('[data-pf="MD approved"]'); await sleep(300);
  await s.click(`[data-ppay="${S}"]`); await sleep(300); await s.fill('#f-ref', 'ADCB TT 4471'); await s.click('#m-save'); await sleep(1500);
  const pd = (await api(`/store/est/subpcs/${S}/approval`)).j;
  ck('Shafeeq marks it paid - done', pd.status === 'Paid');
  await a.goto(B + '/portal/est-app.html?view=projects'); await a.waitForSelector('tr[data-row]').catch(() => {}); await sleep(800);
  ck('Estimation sees it paid at once', /Paid/.test(await a.textContent(`tr[data-row="${S}"]`).catch(() => '')));
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
