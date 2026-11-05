// 914 Al Raida (5 Nov 2026): the certificate rolls every column up - section, bill (trade), grand total - live from the
// lines; the schedule upload stops a total that is not the subcontract value, and lines already in.
//   RAIDA=/path/RAIDA.xlsx /tmp/claude-0/run_on.sh <db after deploy/sub_914_raida script> 8520 tests/sub_boq_rollup_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html'); await sleep(1500);
  if (await p.isVisible('#lg-u')) { await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); } await sleep(3000);
  const info = await p.evaluate(async () => { const m = await GET('/store/est/meta'); const pid = m.projects.find(x => x.code === '914').id; const pr = await GET('/store/est/projects/' + pid);
    const s = pr.subs.find(x => /AL RAIDA/.test(x.name)); return { sid: s.id, pcs: s.pcs.map(x => x.id) }; });
  const pc2 = info.pcs[info.pcs.length - 1];
  await p.evaluate(id => pcSheet(id), pc2); await sleep(2500);
  const sum = await p.evaluate(() => [...document.querySelectorAll('table.rollsum tbody tr')].map(tr => [...tr.children].map(td => td.textContent.trim())));
  ck('summary: HVAC, Electrical, Plumbing and the grand total', sum.length === 4 && /HVAC/.test(sum[0][0]) && /Grand total/.test(sum[3][0]), sum);
  ck('contract per bill and grand total = 560,700 (no subtotal counted twice)', sum.map(r => r[1]).join('|') === '234,900.00|172,800.00|153,000.00|560,700.00', sum.map(r => r[1]));
  ck('PC 02 work (20% of shop drawings = 1,620) reaches the HVAC total and the grand total', sum[0][4] === '1,620.00' && sum[3][4] === '1,620.00' && sum[1][4] === '0.00', sum);
  ck('% done is weighted (1,620 / 234,900 = 0.69%) and balance = contract - to date', sum[0][5] === '0.69%' && /233,280\.00/.test(sum[0][6]), sum[0]);
  // type on an Electrical line and a Plumbing line: the figure runs up unchanged through section, bill and grand total
  await p.evaluate(() => { const it = S_items => 0; });
  const moved = await p.evaluate(() => {
    const row = t => [...document.querySelectorAll('tr[data-row]')].find(tr => tr.textContent.includes(t));
    const set = (t, v) => { const i = row(t).querySelector('input[data-k="pct"]'); i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); };
    set('13A switch socket outlet', '50');          // 10,062 x 50% = 5,031
    set('Manholes', '100');                           // 4,500
    const tds = tr => [...tr.children].map(td => td.textContent.trim());
    const sec = [...document.querySelectorAll('tr.rsub')].map(tds).filter(r => /M POWER OUTLETS|SOUNDPRROF/.test(r[1]));
    const tot = [...document.querySelectorAll('tr.rtot')].map(tds);
    const sm = [...document.querySelectorAll('table.rollsum tbody tr')].map(tds);
    return { sec, tot, sm };
  });
  ck('Electrical line 5,031 shows in its section subtotal', moved.sec.some(r => /M POWER OUTLETS/.test(r[1]) && r.includes('5,031.00')), moved.sec);
  ck('... in the Electrical bill total and the summary', moved.tot.some(r => /Electrical/i.test(r[1]) && r.includes('5,031.00')) && moved.sm[1][4] === '5,031.00', { tot: moved.tot, sm: moved.sm[1] });
  ck('Plumbing 4,500 the same way; grand total = 1,620 + 5,031 + 4,500 = 11,151', moved.sm[2][4] === '4,500.00' && moved.sm[3][4] === '11,151.00', moved.sm);
  await p.evaluate(() => { const t = document.querySelector('table.rollsum'); t.scrollIntoView(); }); await sleep(300);
  await p.screenshot({ path: '/tmp/claude-0/ui2/raida/summary.png' });
  await p.evaluate(() => { const r = [...document.querySelectorAll('tr.rsub')].find(tr => /M POWER OUTLETS/.test(tr.textContent)); r.scrollIntoView({ block: 'center' }); }); await sleep(300);
  await p.screenshot({ path: '/tmp/claude-0/ui2/raida/section.png' });
  // over the contract: flagged
  const over = await p.evaluate(() => { const tr = [...document.querySelectorAll('tr[data-row]')].find(tr => tr.textContent.includes('Shaver Socket'));
    const i = tr.querySelector('input[data-k="pct"]'); i.value = '150'; i.dispatchEvent(new Event('input', { bubbles: true }));
    return [...document.querySelectorAll('tr.over')].map(tr => tr.children[1].textContent.trim().slice(0, 40)); });
  ck('a line done above its contract amount is flagged (Shaver Socket at 150%)', over.length === 1 && /Shaver Socket/.test(over[0]), over);
  await p.evaluate(() => closeModal && 0).catch(() => {});
  // ---- the upload: the BOQ against the subcontract value, and lines already in
  await p.goto(B + '/portal/est-app.html'); await sleep(2500);
  await p.evaluate(() => { const i = document.createElement('input'); i.type = 'file'; i.id = 'tf'; document.body.appendChild(i); });
  await p.setInputFiles('#tf', process.env.RAIDA);
  await p.evaluate(sid => importItems(sid, document.getElementById('tf').files[0], async () => {}), info.sid); await sleep(3500);
  const mod = await p.evaluate(() => ({ t: document.getElementById('m-body').innerText, force: !!document.getElementById('it-force') }));
  ck('upload shows the BOQ total against the subcontract value, with the difference', /add up to 560,700\.00 - the subcontract value is 568,800\.00 \(difference -8,100\.00\)/.test(mod.t) && mod.force, mod.t.slice(0, 600));
  ck('... and the file\'s own errors: HVAC 6/6 repeats page 5, /10 with 9 pages, 8/9 twice', /repeats page 5's total/.test(mod.t) && /numbered '\/10' but has 9 pages/.test(mod.t) && /8\/9' is listed twice/.test(mod.t));
  ck('... and that all 49 lines are already in the schedule', /49 of these lines are already in this schedule/.test(mod.t), mod.t.slice(-400));
  await p.screenshot({ path: '/tmp/claude-0/ui2/raida/upload.png' });
  await p.evaluate(() => { const r = document.querySelector('input[name=itmode][value=add]'); if (r) r.checked = true; });
  await p.click('#m-save'); await sleep(1500);
  const msg = await p.evaluate(() => (document.querySelector('.toast, #toast') || {}).textContent || '');
  const n = await p.evaluate(async sid => (await GET(`/store/est/subs/${sid}/items`)).items.length, info.sid);
  ck('Add without ticking: nothing saved, says why', n === 49 && /not equal the subcontract value|already in/.test(msg), { n, msg });
  ck('no page errors', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close(); })();
