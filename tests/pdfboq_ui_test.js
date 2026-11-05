// A priced BOQ that is only a PDF, uploaded on Edit schedule (5 Nov 2026): read like the Excel - the bills, every
// line, items priced together as one lump sum listed under their group.
//   PDF=/path/915.pdf /tmp/claude-0/run_on.sh <db with 915 Al Raida> 8720 tests/pdfboq_ui_test.js
const { chromium } = require('playwright'); const B = process.env.BASE; const sleep = ms => new Promise(r => setTimeout(r, ms));
const SH = process.env.SHOTS || '/tmp/claude-0/ui2/pdfboq_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html'); await sleep(1500);
  if (await p.isVisible('#lg-u')) { await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); } await sleep(3000);
  const sid = await p.evaluate(async () => { const m = await GET('/store/est/meta'); const pid = m.projects.find(x => x.code === '915').id; const pr = await GET('/store/est/projects/' + pid);
    return pr.subs.find(x => /RAIDA/i.test(x.name)).id; });
  await p.evaluate(sid => scheduleEditor(sid), sid); await sleep(2000);
  await p.setInputFiles('#it-up-f', process.env.PDF); await sleep(15000);
  const t = await p.textContent('#m-body');
  ck('the PDF read: 217 lines, = the subcontract value 580,500', /217/.test(await p.textContent('.modal .strip, #m-body .strip')) && /= subcontract value/.test(t), t.slice(0, 300));
  ck('every bill = its own total', /every sheet = its total/.test(t));
  ck('16 groups of items priced as one lump sum, their items listed under them', /16 group\(s\) of items priced as one lump sum/.test(t) && await p.locator('#m-body tr.gin').count() >= 110, (t.match(/\d+ group\(s\)[^.]*/) || [''])[0]);
  const rows = await p.evaluate(() => [...document.querySelectorAll('#m-body tr')].map(tr => [...tr.children].map(td => td.textContent.trim())));
  const k = rows.findIndex(r => r.some(c => /Sanitary Fittings/.test(c)));
  ck('Sanitary Fittings: one line 10,800, Clean Out ... Rain Water Outlet under it', k >= 0 && rows[k].some(c => c === '10,800.00') && rows[k + 1].some(c => c === 'Clean Out, CO'), rows.slice(k, k + 3));
  const g = p.locator('#m-body tr.ghd', { hasText: 'Sanitary Fittings' }); await g.scrollIntoViewIfNeeded(); await sleep(300);
  await p.screenshot({ path: SH + 'upload.png' });
  ck('no page errors', !errs.length, errs);
  console.log(bad ? bad + ' FAILED' : 'ALL PASS'); await br.close(); })();
