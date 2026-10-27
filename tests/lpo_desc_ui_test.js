// LPO line descriptions as typed: Enter = new line, an empty line = a gap, **bold** - on the form, the
// printed LPO, the PDF and the Excel. Delivery date can be words ("As per site requirement") instead of a date.
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/lpod_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const DESC = 'Supply and installation of a steel structure for the villa elevation at roof floor level front and back elevations\n\nPlate Supports at Concrete wall MS 12mm Plate\n\nChemical Bolts 8.8 Grade Length 150mm\n\nPaint - Two coats epoxy system\n\n**Size : 10.80x0.85m, 9.15x1.80m**';
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/?p=store'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  const api = (path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const o = await api('/store/purchase/orders', 'POST', { supplier_name: 'Dynamic Point Steel Construction Contracting L.l.c', supplier_trn: '104064136500003', job_scope: 'Villa Elevation Steel Structure Work',
    project_location: '909', delivery_note: 'As per site requirement', terms: '25% Advance, 25% upon material delivery 50% progressive payment',
    lines: [{ description: 'Villa elevation steel structure', description2: DESC, qty: 1, unit: 'lmpsm', rate: 40000, tax_pct: 5 },
            { description: 'Cement OPC', description2: 'Double washed', qty: 10, unit: 'bag', rate: 16.5, tax_pct: 5 }] });
  ck('LPO saved', !!o.id, o);
  const g = await api(`/store/purchase/orders/${o.id}`);
  ck('description kept exactly as typed (lines and gaps)', g.lines[0].description2 === DESC, g.lines[0].description2);
  ck('delivery words kept', g.delivery_note === 'As per site requirement', g.delivery_note);
  const tok = (await api('/auth/download-token', 'POST')); const t = tok.token || tok.download_token;
  // printed LPO (HTML)
  const v = await ctx.newPage(); await v.goto(`${B}/export/purchase/${o.id}/view?token=${t}`); await sleep(1500);
  const html = await v.content();
  ck('print: each line kept with gaps (<br><br>)', /elevations<br><br>Plate Supports/.test(html) && /<b>Size : 10\.80x0\.85m, 9\.15x1\.80m<\/b>/.test(html));
  ck('print: delivery "As per site requirement"', /As per site requirement/.test(await v.textContent('body')));
  ck('print: a short note stays the small grey line', /class="sub">Double washed/.test(html));
  await v.screenshot({ path: SH + 'print.png', fullPage: false });
  // PDF
  const pdf = await v.evaluate(async u => { const r = await fetch(u); return [r.status, r.headers.get('content-type'), (await r.arrayBuffer()).byteLength]; }, `${B}/export/purchase/${o.id}?token=${t}&format=pdf`);
  ck('PDF builds', pdf[0] === 200 && /pdf/.test(pdf[1]) && pdf[2] > 3000, pdf);
  const t2 = (await api('/auth/download-token', 'POST')); const tk2 = t2.token || t2.download_token;
  const xl = await v.evaluate(async u => { const r = await fetch(u); return [r.status, (await r.arrayBuffer()).byteLength]; }, `${B}/export/purchase/${o.id}?token=${tk2}&format=excel`);
  ck('Excel builds', xl[0] === 200 && xl[1] > 3000, xl);
  // the form
  await p.evaluate(id => editLpo ? editLpo(id) : null, o.id).catch(() => {}); await sleep(1500);
  if (!(await p.isVisible('#lpo-form-card'))) { await p.evaluate(() => pgSub && pgSub('purchase')); await sleep(1200); await p.evaluate(id => editLpo(id), o.id).catch(e => console.log('edit', e.message)); await sleep(1500); }
  const ta = await p.$('#lpo-lines textarea.lpo-d2');
  ck('form: the description is a multi-line box showing every line', !!ta && (await ta.inputValue()) === DESC && (await ta.evaluate(el => el.offsetHeight)) > 120);
  ck('form: delivery words shown beside the date', (await p.inputValue('#lpo-delivery-note')) === 'As per site requirement');
  await ta.evaluate(el => el.scrollIntoView({ block: 'center' })); await sleep(300);
  await p.screenshot({ path: SH + 'form.png' });
  ck('no page errors', !errs.length, errs);
  fs.writeFileSync('/tmp/claude-0/lpod_id.txt', String(o.id));
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
