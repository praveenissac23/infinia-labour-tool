// LPO (5 Nov 2026): B beside a material makes its name bold on the LPO; B beside Notes bolds the words picked
// (**two stars each side**) - on the form, the printed LPO, the PDF and the Excel.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/roles.db 8670 tests/lpo_bold_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/ui2/lpob_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  const api = (path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const o = await api('/store/purchase/orders', 'POST', { supplier_name: 'Pitbull Safety Trading', job_scope: 'PPE', project_location: '913',
    notes: '**6 months Replacement Warranty** for sole cracking & mould opening',
    lines: [{ description: 'Pitbull PB-7051 Safety Shoes For Labors - Size: 43', qty: 8, unit: 'pair', rate: 95, tax_pct: 5, bold: true },
            { description: 'Safety helmet', description2: 'White', qty: 8, unit: 'nos', rate: 12, tax_pct: 5 }] });
  ck('LPO saved', !!o.id, o);
  const g = await api(`/store/purchase/orders/${o.id}`);
  ck('the bold mark is kept on the line (only that one)', g.lines[0].bold === true && g.lines[1].bold === false, g.lines.map(l => l.bold));
  const t = (await api('/auth/download-token', 'POST')).token;
  const v = await ctx.newPage(); await v.goto(`${B}/export/purchase/${o.id}/view?token=${t}`); await sleep(1500);
  const html = await v.content();
  ck('print: the material name bold', /<b>Pitbull PB-7051 Safety Shoes For Labors - Size: 43<\/b>/.test(html));
  ck('print: the other material not bold', !/<b>Safety helmet/.test(html));
  ck('print: the notes words bold, no stars, & kept', /<b>6 months Replacement Warranty<\/b> for sole cracking &amp; mould opening/.test(html) && !/\*\*/.test(html));
  await v.screenshot({ path: SH + 'print.png', clip: { x: 0, y: 380, width: 1440, height: 520 } });
  const t2 = (await api('/auth/download-token', 'POST')).token;
  const pdf = await v.evaluate(async u => { const r = await fetch(u); return [r.status, r.headers.get('content-type'), (await r.arrayBuffer()).byteLength]; }, `${B}/export/purchase/${o.id}?token=${t2}&format=pdf`);
  ck('PDF builds', pdf[0] === 200 && /pdf/.test(pdf[1]) && pdf[2] > 3000, pdf);
  const t3 = (await api('/auth/download-token', 'POST')).token;
  const xl = await v.evaluate(async u => { const r = await fetch(u); return [r.status, (await r.arrayBuffer()).byteLength]; }, `${B}/export/purchase/${o.id}?token=${t3}&format=excel`);
  ck('Excel builds', xl[0] === 200 && xl[1] > 3000, xl);
  // the form: the B buttons
  await p.evaluate(() => pgGo('store', 'purchasing')); await sleep(1500);
  await p.evaluate(id => editLpo(id), o.id); await sleep(1800);
  const btn = p.locator('#lpo-lines .lpo-bbtn').first();
  ck('form: B beside the material, on for the bold one', await btn.isVisible() && /\bon\b/.test(await btn.getAttribute('class')));
  ck('form: the name shows bold in its box', await p.$eval('#lpo-lines input.lpo-mat', x => getComputedStyle(x).fontWeight >= 700));
  const b2 = p.locator('#lpo-lines .lpo-bbtn').nth(1);
  await b2.click();
  ck('form: B on the second material turns it on', await p.evaluate(() => lpoLines[1].bold === true));
  await b2.click();
  ck('... and off again', await p.evaluate(() => lpoLines[1].bold === false));
  // notes: pick a word, B
  await p.fill('#lpo-notes', 'Warranty 6 months'); await p.evaluate(() => document.getElementById('lpo-notes').setSelectionRange(0, 8));
  await p.click('.field .lpo-bbtn');
  ck('notes: the picked words get ** each side', (await p.inputValue('#lpo-notes')) === '**Warranty** 6 months', await p.inputValue('#lpo-notes'));
  await p.click('.field .lpo-bbtn');
  ck('notes: B again takes them off', (await p.inputValue('#lpo-notes')) === 'Warranty 6 months', await p.inputValue('#lpo-notes'));
  await p.fill('#lpo-notes', '**6 months Replacement Warranty** for sole cracking & mould opening');
  await p.locator('#lpo-lines .lpo-bbtn').first().scrollIntoViewIfNeeded(); await sleep(300);
  await p.screenshot({ path: SH + 'form.png' });
  await p.locator('#lpo-notes').scrollIntoViewIfNeeded(); await sleep(200);
  await p.screenshot({ path: SH + 'form_notes.png' });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS');
})();
