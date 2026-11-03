// Overview > BOQ & budget with a real internal BOQ (WS-25 R10, 3 Nov 2026): the preview tallies every bill with the
// workbook's SUMMARY, only priced lines come in (Swimming pool sheet read, its excluded sections left out), the BOQ
// screen tallies, and lines / a section / a bill are taken out together with tick boxes.
//   BOQ_FILE=/path/WS25.xlsx BASE=... node tests/boq_upload_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', F = process.env.BOQ_FILE, O = process.env.SHOTS || '/tmp/claude-0/ui2/';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 500))); };
(async () => {
  const phone = process.env.VIEW === 'phone', V = phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, X = phone ? 'phone_' : '';
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: V, deviceScaleFactor: phone ? 2 : 1, isMobile: phone, hasTouch: phone })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await sleep(2500); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(3000);
  const pid = await p.evaluate(async () => (await apiCall('/store/est/meta')).projects.find(x => x.code === '913').id);
  await p.evaluate(() => { window.checkBuild = () => {}; pgGo('estimation', 'estproj'); }); await sleep(4000);
  const fr = p.frames().find(x => /est-app/.test(x.url()));
  fr.on && 0;
  await fr.evaluate(async pid => { await openProject(pid); }, pid); await sleep(1500);
  await fr.evaluate(() => { const b = [...document.querySelectorAll('.pills button')].find(x => /Overview/.test(x.textContent)); if (b) b.click(); }); await sleep(800);
  await fr.evaluate(() => { const b = [...document.querySelectorAll('.utabs button')].find(x => /BOQ/.test(x.textContent)); if (b) b.click(); }); await sleep(1200);
  await fr.setInputFiles('#boq-up-f', F); await sleep(6000);
  const pv = await fr.evaluate(() => ({ title: document.getElementById('m-title').textContent, body: document.getElementById('m-body').innerText, save: document.getElementById('m-save').textContent }));
  ck(`preview opens: ${pv.title}`, /Internal BOQ/.test(pv.title), pv);
  ck('preview: tallies with the SUMMARY sheet', /tallies with the SUMMARY sheet/.test(pv.body), pv.body.slice(0, 600));
  ck('preview: Swimming pool read as bill 03 (51,260.00), Super structure is 04', /03\. Swimming Pool & Holding Tank\s+SWIMMING POOL\s+\d+\s+51,260\.00\s+51,260\.00/.test(pv.body) && /04\. Super Structure\s+3\.SUPERSTR/.test(pv.body), pv.body.slice(0, 2500));
  ck('preview: what is left out is listed (Dewatering - Rate only, Pump room - Excluded)', /DEWATERING WORKS - Rate only/.test(pv.body) && /PUMP ROOM[^\n]*Excluded/.test(pv.body), pv.body.slice(-1500));
  ck(`preview: "${pv.save}"`, /Bring in 216 priced lines/.test(pv.save), pv.save);
  await p.screenshot({ path: O + X + 'boq_preview.png' });
  await fr.evaluate(() => { const m = document.querySelector('#m-body .tw'); if (m) m.scrollTop = 9999; }); await sleep(300);
  await fr.evaluate(() => document.getElementById('m-save').click()); await sleep(5000);
  const book = await p.evaluate(async pid => apiCall('/store/est/projects/' + pid), pid);
  const sum = book.boq.filter(x => !x.scope).reduce((a, x) => a + x.counted, 0);
  ck(`saved: ${book.boq.length} lines, BOQ value ${sum.toFixed(2)} (workbook 5,746,999.997)`, book.boq.length === 216 && Math.abs(sum - 5746999.997) < 0.015, [book.boq.length, sum]);
  ck('no balancing "Difference to the summary" lines', !book.boq.some(x => /Difference to the summary/.test(x.description)));
  ck('every line is priced', book.boq.every(x => x.amount));
  ck('the underground water tank is its own section under 02', book.boq.filter(x => x.section === 'UNDERGROUND WATER TANK' && /^02\./.test(x.bill)).length === 21);
  ck('tally kept on the project', book.boq_tally && Math.abs(book.boq_tally.total - 5746999.997) < 0.01 && Object.keys(book.boq_tally.bills).length === 15, book.boq_tally);
  // the BOQ screen
  await sleep(800);
  const scr = await fr.evaluate(() => ({ strip: (document.querySelector('.strip') || {}).innerText || '', ticks: document.querySelectorAll('tr.bill .st.g').length, bills: document.querySelectorAll('tr.bill').length }));
  ck(`BOQ screen: workbook total tallies, ${scr.ticks} of ${scr.bills} bills ticked`, /tallies/.test(scr.strip) && scr.ticks === scr.bills && scr.bills === 15, scr);
  await fr.evaluate(() => { const b = [...document.querySelectorAll('tr.bill')].find(x => /^01\./.test(x.dataset.bill)); b.click(); }); await sleep(600);
  const dw = await fr.evaluate(() => { const td = document.querySelector('td[data-boq]'); td.scrollIntoView({ block: 'center' }); const r = td.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), t: td.textContent.slice(0, 40) }; });
  ck(`description readable: ${dw.w}px wide, ${dw.h}px tall ("${dw.t}")`, dw.w >= 200 && dw.h <= 80, dw);
  await fr.evaluate(() => { document.querySelectorAll('.tw').forEach(t => t.scrollLeft = 0); const b = document.querySelector('tr.bill'); b.scrollIntoView({ block: 'start' }); scrollBy(0, -120); });
  await sleep(300); await p.screenshot({ path: O + X + 'boq_screen.png' });
  await fr.evaluate(() => { const b = [...document.querySelectorAll('tr.bill')].find(x => /^01\./.test(x.dataset.bill)); b.click(); scrollTo(0, 0); }); await sleep(500);
  // tick a whole section (open bill 02 first) and a single line elsewhere
  await fr.evaluate(() => { const b = [...document.querySelectorAll('tr.bill')].find(x => /^02\./.test(x.dataset.bill)); b.click(); }); await sleep(600);
  await fr.evaluate(() => { const c = [...document.querySelectorAll('[data-pksec]')].find(x => /UNDERGROUND WATER TANK/.test(x.dataset.pksec)); c.click(); }); await sleep(500);
  const bar = await fr.evaluate(() => document.querySelector('.boq-pickbar').innerText);
  ck(`section ticked in one click: "${bar.split('\n')[0]}"`, /21 lines ticked/.test(bar) && /35,580\.70/.test(bar), bar);
  await fr.evaluate(() => { const r = [...document.querySelectorAll('tr.sec')].find(x => /UNDERGROUND WATER TANK/.test(x.textContent)); r.scrollIntoView({ block: 'center' }); }); await sleep(300);
  await p.screenshot({ path: O + X + 'boq_ticked.png' });
  await fr.evaluate(() => document.getElementById('boq-delpick').click()); await sleep(700);
  const cf = await fr.evaluate(() => ({ body: document.getElementById('m-body').innerText, save: document.getElementById('m-save').textContent }));
  ck(`confirm says how many and how much: "${cf.save}"`, /Delete 21 lines/.test(cf.save) && /35,580\.70/.test(cf.body), cf);
  await p.screenshot({ path: O + X + 'boq_confirm.png' });
  await fr.evaluate(() => document.getElementById('m-save').click()); await sleep(3000);
  const book2 = await p.evaluate(async pid => apiCall('/store/est/projects/' + pid), pid);
  ck(`deleted together: ${book2.boq.length} lines left (216 - 21)`, book2.boq.length === 195, book2.boq.length);
  const t2 = await fr.evaluate(() => { const r = [...document.querySelectorAll('tr.bill')].find(x => /^02\./.test(x.dataset.bill)); return r ? r.innerText : ''; });
  ck(`bill 02 now shows its difference to the workbook (${t2.replace(/\s+/g, ' ').slice(0, 120)})`, /workbook 2,397,122\.10/.test(t2) && /35,580\.70/.test(t2), t2);
  await p.screenshot({ path: O + X + 'boq_after_delete.png' });
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await br.close(); process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
