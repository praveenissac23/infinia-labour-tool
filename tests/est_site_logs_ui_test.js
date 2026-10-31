// Site & technical: submittals, RFIs and NOCs & approvals - added by typing one line, status by one click (its date
// stamps itself), remarks typed straight into the line and kept, no form to fill for the everyday steps.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/slog_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = async (path) => p.evaluate(async path => (await fetch(path, { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json(), path);
  let meta = {}; for (let i = 0; i < 10 && !meta.projects; i++) { meta = await api('/store/est/meta').catch(() => ({})); if (!meta.projects) await sleep(1500); }
  const P = meta.projects.find(x => x.code === '914').id;
  const logs = async kind => (await api(`/store/est/projects/${P}`)).logs.filter(l => l.kind === kind);
  const today = await p.evaluate(() => today());
  // ---- submittals ----
  await p.evaluate(pid => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'site.submittal'); }, P); await p.reload(); await sleep(1800);
  // Submittals are now the material submittal log (its own form, tests/submittals_ui_test.js): the one-line add is checked there
  if (await p.$('#qa-title')) {
  await p.fill('#qa-title', 'Waterproofing system - Sika membrane'); await p.press('#qa-title', 'Enter'); await sleep(1500);
  await p.fill('#qa-title', 'Aluminium windows shop drawings'); await p.press('#qa-title', 'Enter'); await sleep(1500);
  let L = await logs('submittal');
  const s1 = L.find(l => /Sika/.test(l.title));
  ck('typed + Enter: submittal added, sent today, reply due set, status Submitted - no form', s1 && s1.sent === today && !!s1.due && s1.status === 'Submitted', s1);
  ck('the box is ready for the next one', await p.evaluate(() => document.activeElement && document.activeElement.id === 'qa-title'));
  await p.click(`[data-step="${s1.id}"][data-v="Revise & resubmit"]`); await sleep(1500);
  L = await logs('submittal'); let x = L.find(l => l.id === s1.id);
  ck('one click "Revise": status and reply date (today) in', x.status === 'Revise & resubmit' && x.replied === today, x);
  await p.fill(`[data-cell="${s1.id}"][data-k="note"]`, 'Consultant wants the 2-coat system - datasheet to resend'); await p.press(`[data-cell="${s1.id}"][data-k="note"]`, 'Enter'); await sleep(1200);
  L = await logs('submittal'); x = L.find(l => l.id === s1.id);
  ck('remark typed in the line is kept', x.note === 'Consultant wants the 2-coat system - datasheet to resend', x.note);
  await p.click(`[data-resub="${s1.id}"]`); await sleep(1500);
  L = await logs('submittal'); x = L.find(l => l.id === s1.id);
  ck('"Resubmit as rev 1": rev 1, Submitted again, reply date cleared', x.rev === '1' && x.status === 'Submitted' && !x.replied, x);
  const s2 = L.find(l => /Aluminium/.test(l.title));
  await p.click(`[data-step="${s2.id}"][data-v="Approved as noted"]`); await sleep(1500);
  await p.screenshot({ path: SH + '1_submittals.png' });
  } else console.log('NOTE submittals: the material submittal log (no one-line add) - see submittals_ui_test.js');
  // ---- NOCs & approvals ----
  await p.evaluate(() => { localStorage.setItem('est_sec', 'site.approval'); }); await p.reload(); await sleep(1800);
  L = await logs('approval');
  const a1 = L[0], a2 = L[1];
  ck('NOCs & approvals: the tracker items are there', L.length >= 10, L.length);
  await p.click(`[data-step="${a1.id}"][data-v="Submitted"]`); await sleep(1400);
  await p.click(`[data-step="${a1.id}"][data-v="Approved"]`); await sleep(1400);
  await p.fill(`[data-cell="${a1.id}"][data-k="ref"]`, 'CD-2026-4471'); await p.press(`[data-cell="${a1.id}"][data-k="ref"]`, 'Enter'); await sleep(900);
  await p.click(`[data-step="${a2.id}"][data-v="Submitted"]`); await sleep(1400);
  await p.fill(`[data-cell="${a2.id}"][data-k="note"]`, 'Waiting for the consultant stamp on the soil report'); await p.press(`[data-cell="${a2.id}"][data-k="note"]`, 'Enter'); await sleep(1200);
  L = await logs('approval'); const b1 = L.find(l => l.id === a1.id), b2 = L.find(l => l.id === a2.id);
  ck('two clicks: Submitted then Approved - both dates today, ref typed in the line', b1.status === 'Approved' && b1.sent === today && b1.replied === today && b1.ref === 'CD-2026-4471', b1);
  ck('remark on a stuck item kept', b2.status === 'Submitted' && /consultant stamp/.test(b2.note), b2);
  ck('the done count moves', /1 of \d+ done/.test(await p.textContent('.prog')), await p.textContent('.prog'));
  await p.screenshot({ path: SH + '2_approvals.png' });
  await p.click(`[data-edit="${a2.id}"]`); await sleep(500);
  const fieldsInForm = await p.$$eval('#m-body .frm label', x => x.map(y => y.textContent.trim().replace(/\s+i$/, '')));
  ck('the details form is short: no status to pick (that is the one click), dates only to correct', fieldsInForm.length <= 7 && !fieldsInForm.some(t => /^Status/.test(t)), fieldsInForm);
  await p.screenshot({ path: SH + '3_form.png' });
  await p.click('#m-cancel');
  // ---- RFI ----
  await p.evaluate(() => { localStorage.setItem('est_sec', 'site.rfi'); }); await p.reload(); await sleep(1800);
  await p.fill('#qa-title', 'Column C4 reinforcement clash with MEP sleeve'); await p.press('#qa-title', 'Enter'); await sleep(1500);
  const r1 = (await logs('rfi')).find(l => /C4/.test(l.title));
  ck('RFI typed in: Open, sent today', r1 && r1.status === 'Open' && r1.sent === today, r1);
  await p.click(`[data-step="${r1.id}"][data-v="Answered"]`); await sleep(1400);
  ck('one click "Answered": reply date today', (await logs('rfi')).find(l => l.id === r1.id).replied === today);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
