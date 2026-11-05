// LPO (5 Nov 2026): Aa beside the material name, the description and the notes opens a toolbar - bold, italic,
// underline, red / blue / green, plain. On a name it is the whole name; in the description and notes, the words picked.
// Shown on the printed LPO, the PDF and the Excel.
//   /tmp/claude-0/run_on.sh /tmp/claude-0/roles.db 8670 tests/lpo_bold_ui_test.js
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/ui2/lpob_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  const api = (path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const o = await api('/store/purchase/orders', 'POST', { supplier_name: 'Pitbull Safety Trading', job_scope: 'PPE', project_location: '913',
    notes: '**6 months Replacement Warranty** for __sole cracking__ & [red]mould opening[/red]',
    lines: [{ description: 'Pitbull PB-7051 Safety Shoes For Labors - Size: 43', description2: 'Steel toe //S3 SRC// - [blue]black[/blue]', qty: 8, unit: 'pair', rate: 95, tax_pct: 5, style: 'b u red' },
            { description: 'Safety helmet', description2: 'White', qty: 8, unit: 'nos', rate: 12, tax_pct: 5 }] });
  ck('LPO saved', !!o.id, o);
  const g = await api(`/store/purchase/orders/${o.id}`);
  ck('the name look is kept on the line (only that one)', /b/.test(g.lines[0].style) && /u/.test(g.lines[0].style) && /red/.test(g.lines[0].style) && !g.lines[1].style, g.lines.map(l => l.style));
  const t = (await api('/auth/download-token', 'POST')).token;
  const v = await ctx.newPage(); await v.goto(`${B}/export/purchase/${o.id}/view?token=${t}`); await sleep(1500);
  const html = await v.content();
  ck('print: the name bold, underlined, red', /<span class="ink-keep" style="color:#C0392B"><u><b>Pitbull PB-7051/.test(html), html.match(/Pitbull PB-7051[^<]*/));
  ck('print: description italic and blue words', /<i>S3 SRC<\/i>/.test(html) && /<span class="ink-keep" style="color:#1F4E99">black<\/span>/.test(html));
  ck('print: the colours stay (not turned black for printing)', await v.$$eval('.ink-keep', e => e.every(x => getComputedStyle(x).color !== 'rgb(31, 35, 40)')));
  ck('print: notes bold, underline, red - no marks left', /<b>6 months Replacement Warranty<\/b> for <u>sole cracking<\/u> &amp; <span class="ink-keep" style="color:#C0392B">mould opening<\/span>/.test(html) && !/\*\*|__|\[red\]|\/\/S3/.test(html));
  await v.evaluate(() => { const t = [...document.querySelectorAll('table')].find(x => /Item & Description/.test(x.textContent)); t && t.scrollIntoView({ block: 'start' }); window.scrollBy(0, -120); });
  await v.screenshot({ path: SH + 'print.png' });
  const t2 = (await api('/auth/download-token', 'POST')).token;
  const pdf = await v.evaluate(async u => { const r = await fetch(u); return [r.status, r.headers.get('content-type'), (await r.arrayBuffer()).byteLength]; }, `${B}/export/purchase/${o.id}?token=${t2}&format=pdf`);
  ck('PDF builds', pdf[0] === 200 && /pdf/.test(pdf[1]) && pdf[2] > 3000, pdf);
  const t3 = (await api('/auth/download-token', 'POST')).token;
  const xl = await v.evaluate(async u => { const r = await fetch(u); return [r.status, (await r.arrayBuffer()).byteLength]; }, `${B}/export/purchase/${o.id}?token=${t3}&format=excel`);
  ck('Excel builds', xl[0] === 200 && xl[1] > 3000, xl);
  // the form
  await p.evaluate(() => pgGo('store', 'purchasing')); await sleep(1500);
  await p.evaluate(id => editLpo(id), o.id); await sleep(1800);
  const nameAa = p.locator('#lpo-lines input.lpo-mat + .lpo-bbtn').first();
  ck('form: Aa beside the material, marked as styled', await nameAa.isVisible() && /\bon\b/.test(await nameAa.getAttribute('class')));
  ck('form: the name shows in its look in its box', await p.$eval('#lpo-lines input.lpo-mat', x => { const c = getComputedStyle(x); return c.fontWeight >= 700 && /underline/.test(c.textDecorationLine) && c.color === 'rgb(192, 57, 43)'; }));
  await nameAa.click(); await sleep(300);
  ck('Aa opens the toolbar: B I U, three colours, plain', await p.isVisible('#lpo-fmt') && (await p.$$('#lpo-fmt button')).length === 7);
  ck('... B, U and red shown as on', await p.$$eval('#lpo-fmt button.on', b => b.map(x => x.dataset.f).sort().join()) === 'b,red,u');
  await p.click('#lpo-fmt button[data-f="i"]');
  ck('I adds italic to the name', await p.evaluate(() => lpoStyleSet(lpoLines[0]).has('i')));
  await p.click('#lpo-fmt button[data-f="blue"]');
  ck('a colour replaces the other colour', await p.evaluate(() => { const s = lpoStyleSet(lpoLines[0]); return s.has('blue') && !s.has('red'); }));
  await p.locator('#lpo-lines input.lpo-mat').first().scrollIntoViewIfNeeded();
  await p.screenshot({ path: SH + 'form.png' });
  await p.click('#lpo-fmt button[data-f="red"]'); await p.click('#lpo-fmt button[data-f="i"]');
  await p.keyboard.press('Escape');
  // material name: pick ONE word, Aa, B and red - only that word (the name itself stays plain for stock)
  const nm2 = p.locator('#lpo-lines input.lpo-mat').nth(1);
  await nm2.evaluate(el => { el.focus(); el.setSelectionRange(7, 13); });          // "helmet"
  await p.locator('#lpo-lines input.lpo-mat + .lpo-bbtn').nth(1).click(); await sleep(200);
  await p.click('#lpo-fmt button[data-f="b"]'); await p.click('#lpo-fmt button[data-f="red"]');
  ck('name: only the picked word is bold and red', await p.evaluate(() => lpoLines[1].description_fmt) === 'Safety [red]**helmet**[/red]', await p.evaluate(() => lpoLines[1].description_fmt));
  ck('name: the name itself stays plain', await nm2.inputValue() === 'Safety helmet');
  ck('name: "Prints as" shows the word in its look', await p.isVisible('#lpo-lines tr:nth-child(2) .lpo-fmtprev') && /helmet/.test(await p.innerHTML('#lpo-lines tr:nth-child(2) .lpo-fmtprev span[style*="font-weight:700"]')));
  await p.keyboard.press('Escape');
  await nm2.evaluate(el => el.setSelectionRange(el.value.length, el.value.length)); await nm2.press('End'); await nm2.type(' XL'); await sleep(200);
  await p.keyboard.press('Escape');
  ck('name typed on: the word keeps its look', await p.evaluate(() => lpoLines[1].description_fmt) === 'Safety [red]**helmet**[/red] XL', await p.evaluate(() => lpoLines[1].description_fmt));
  await nm2.scrollIntoViewIfNeeded(); await sleep(200);
  await p.screenshot({ path: SH + 'form_word.png' });
  // description: pick a word, Aa, B
  const ta = p.locator('#lpo-lines textarea.lpo-d2').nth(1);
  await ta.fill('White ABS shell'); await ta.evaluate(el => el.setSelectionRange(6, 9));
  await p.locator('#lpo-lines .lpo-d2w .lpo-bbtn').nth(1).click(); await sleep(200);
  await p.click('#lpo-fmt button[data-f="b"]');
  ck('description: the picked words get bold', (await ta.inputValue()) === 'White **ABS** shell', await ta.inputValue());
  ck('description: "Prints as" shows the bold word', /ABS/.test(await p.innerHTML('#lpo-lines tr:nth-child(2) td:nth-child(3) .lpo-fmtprev span[style*="font-weight:700"]')));
  await p.click('#lpo-fmt button[data-f="b"]');
  ck('... B again takes it off', (await ta.inputValue()) === 'White ABS shell', await ta.inputValue());
  await p.keyboard.press('Escape');
  // notes: pick words, Aa, green
  await p.fill('#lpo-notes', 'Deliver before 10 am'); await p.evaluate(() => document.getElementById('lpo-notes').setSelectionRange(15, 20));
  await p.click('.field .lpo-matw .lpo-bbtn'); await sleep(200);
  await p.click('#lpo-fmt button[data-f="green"]');
  ck('notes: "Prints as" shows it, no marks', await p.isVisible('#lpo-notes-prev') && /10 am/.test(await p.innerHTML('#lpo-notes-prev span[style*="color"]')) && !/\[green\]/.test(await p.textContent('#lpo-notes-prev')));
  ck('notes: the picked words get the colour', (await p.inputValue('#lpo-notes')) === 'Deliver before [green]10 am[/green]', await p.inputValue('#lpo-notes'));
  await p.locator('#lpo-notes').scrollIntoViewIfNeeded(); await sleep(200);
  await p.screenshot({ path: SH + 'form_notes.png' });
  // saved from the form: the name look goes with the line
  const saved = await p.evaluate(() => lpoLines.map(l => [...lpoStyleSet(l)].sort().join(' ')));
  ck('the form keeps the name look to save', saved[0] === 'b red u', saved);
  // saved from the form, then printed: the one word
  await p.evaluate(() => { lpoLines[0].style = 'b u red'; lpoLines[0].bold = true; });
  await p.evaluate(() => saveLpo()); await sleep(2500);
  const g2 = await api(`/store/purchase/orders/${o.id}`);
  ck('saved: the stock name plain, the printed name with the word picked out', g2.lines[1].description === 'Safety helmet XL' && g2.lines[1].description_fmt === 'Safety [red]**helmet**[/red] XL', g2.lines[1]);
  const t4 = (await api('/auth/download-token', 'POST')).token;
  const v2 = await ctx.newPage(); await v2.goto(`${B}/export/purchase/${o.id}/view?token=${t4}`); await sleep(1500);
  const h2 = await v2.content();
  ck('print: only "helmet" is bold and red', /Safety <span class="ink-keep" style="color:#C0392B"><b>helmet<\/b><\/span> XL/.test(h2), (h2.match(/Safety[^\n]{0,120}/) || [''])[0]);
  await v2.evaluate(() => { const t = [...document.querySelectorAll('table')].find(x => /Item & Description/.test(x.textContent)); t && t.scrollIntoView({ block: 'start' }); window.scrollBy(0, -120); });
  await v2.screenshot({ path: SH + 'print_word.png' });
  const t5 = (await api('/auth/download-token', 'POST')).token;
  const pdf2 = await v2.evaluate(async u => { const r = await fetch(u); return r.status; }, `${B}/export/purchase/${o.id}?token=${t5}&format=pdf`);
  const t6 = (await api('/auth/download-token', 'POST')).token;
  const xl2 = await v2.evaluate(async u => { const r = await fetch(u); return r.status; }, `${B}/export/purchase/${o.id}?token=${t6}&format=excel`);
  ck('PDF and Excel build with it', pdf2 === 200 && xl2 === 200, [pdf2, xl2]);
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS');
})();
