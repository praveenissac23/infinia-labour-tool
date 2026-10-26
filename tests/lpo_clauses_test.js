// LPO clause sets: Standard on every order; a material on the lines brings its own set (with a heading,
// numbering carried on); x takes a set off; a new set is made in the library and comes in by its words;
// "Save as a new clause set" keeps typed clauses; the order saves with the clauses.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/lpocl_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 400))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  await p.goto(B + '/?p=store'); await sleep(3000);
  await p.evaluate(() => switchScreen('purchase')); await sleep(1500); await p.evaluate(() => newLpo()); await sleep(2000);
  const terms = () => p.inputValue('#lpo-termstext'), chips = () => p.$$eval('#lpo-clsets .lpo-chip', x => x.map(y => y.textContent.replace('×', '').trim()));
  ck('a new LPO starts with the Standard clauses', /^1\. We reserve rights/.test(await terms()) && (await chips()).length === 1, [await terms(), await chips()]);
  // the library: a concrete set
  await p.click('#lpo-clman'); await sleep(800);
  ck('the library has the three sets of today', (await p.$$eval('.lpo-clm-t tbody tr', x => x.length)) === 3);
  await p.click('.lpo-clm [data-a="new"]'); await sleep(300);
  await p.fill('#clm-name', 'Ready-mix concrete'); await p.fill('#clm-words', 'concrete, ready mix, RMC');
  await p.fill('[data-c="0"]', 'Cube test results (7 and 28 days) for every pour; failed cubes at the supplier\'s cost.');
  await p.click('.lpo-clm [data-a="addc"]'); await sleep(200);
  await p.fill('[data-c="1"]', 'Delivery tickets must show batch time, grade and slump.');
  await p.screenshot({ path: SH + '2_library.png' });
  await p.click('.lpo-clm [data-a="save"]'); await sleep(1200);
  ck('saved: 4 sets in the library', (await p.$$eval('.lpo-clm-t tbody tr', x => x.length)) === 4, [await p.textContent('#lpo-status').catch(() => ''), await p.textContent('.lpo-clm').catch(() => '')]);
  await p.click('.lpo-clm [data-a="close"]'); await sleep(300);
  // a concrete line brings it in
  await p.evaluate(() => { lpoLines[0].description = 'Ready-mix concrete C40 (OPC)'; lpoLines[0].qty = 45; lpoLines[0].rate = 310; renderLpoLines(); renderLpoTotals(); }); await sleep(400);
  let t = await terms();
  ck('a concrete line brings its clauses: heading, numbering 3 and 4', /Ready-mix concrete\n3\. Cube test/.test(t) && /4\. Delivery tickets/.test(t), t);
  ck('its chip says it came from the lines', (await chips()).some(c => /Ready-mix concrete \(2\)/.test(c) && /from the lines/.test(c)), await chips());
  await p.screenshot({ path: SH + '1_lpo.png' });
  // added by hand / taken off
  await p.selectOption('#lpo-cladd', 'rental'); await sleep(300);
  ck('Rental added by hand', /Rental\n\d+\. Lost Price/.test(await terms()), await terms());
  await p.click('[data-cloff="rental"]'); await sleep(300);
  ck('x takes it off again', !/Rental/.test(await terms()));
  // typed in the box: kept; a new line does not overwrite it
  await p.evaluate(() => { const b = document.getElementById('lpo-termstext'); b.value += '\n5. Pump standby over 2 hours only if agreed in writing.'; b.dispatchEvent(new Event('input')); }); await sleep(200);
  await p.evaluate(() => { addLpoLine({ description: 'Sand' }); renderLpoTotals(); }); await sleep(300);
  ck('typing in the box is kept for this order', /Pump standby/.test(await terms()));
  ck('"Update the clauses" offered', await p.isVisible('#lpo-clupd'));
  await p.click('#lpo-clsave'); await sleep(500);
  ck('"Save as a new clause set" brings the typed clause into a new set', /Pump standby/.test(await p.inputValue('[data-c="0"]')), await p.inputValue('[data-c="0"]').catch(() => ''));
  await p.fill('#clm-name', 'Concrete pump'); await p.click('.lpo-clm [data-a="save"]'); await sleep(1200);
  const lib = await p.evaluate(async () => (await (await fetch('/store/purchase/clauses', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') } })).json()).sets.map(x => x.name));
  ck('the library now has 5 sets', lib.length === 5 && lib.includes('Concrete pump'), lib);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0); })();
