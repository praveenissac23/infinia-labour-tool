// On a phone, a document preview (tax invoice, receipt, visa expenses, document transmittal) shows its pages:
// a phone browser does not show a PDF inside a page, so the pages are drawn (pdf.js) - not a blank page.
const { chromium, devices } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/phonepdf_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const p = await (await br.newContext({ ...devices['iPhone 13'] })).newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/health');
  let tok = null;
  for (let i = 0; i < 10 && !tok; i++) { tok = await p.evaluate(async () => { try { const r = await fetch('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'username=admin&password=changeme123' }); return (await r.json()).access_token; } catch (e) { return null; } }); if (!tok) await sleep(1500); }
  const H = { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' };
  const n = await p.evaluate(async H => (await (await fetch('/employees/accounts/invoices/next?kind=tax&project_no=906', { headers: H })).json()).number, H);
  const iid = await p.evaluate(async ([H, n]) => (await (await fetch('/employees/accounts/invoices', { method: 'POST', headers: H, body: JSON.stringify({ kind: 'tax', number: n, date: '2026-10-20', client: 'JAMAL KHAN', client_trn: '100000000000003', client_address: 'Dubai', project: 'Villa', project_no: '906', plot: '1', location: 'Dubai', work: 'Joinery', lines: [{ description: 'Joinery works', amount: 3920, vat: 5 }] }) })).json()).id, [H, n]);
  const dl = await p.evaluate(async H => (await (await fetch('/auth/download-token', { method: 'POST', headers: H })).json()).token, H);
  await p.goto(`${B}/export/accounts/invoice/${iid}/view?token=${dl}`); await p.waitForSelector('.pvphone canvas', { timeout: 20000 }).catch(() => {}); await sleep(800);
  const st = await p.evaluate(() => { const c = document.querySelector('.pvphone canvas'); const r = c && c.getBoundingClientRect(); return { n: document.querySelectorAll('.pvphone canvas').length, w: r && r.width, h: r && r.height, vw: innerWidth, wide: getComputedStyle(document.querySelector('.pvwide')).display }; });
  ck('phone: the tax invoice shows its page, full width (not a blank page or "tap share")', st.n >= 1 && st.w > st.vw * 0.85 && st.h > st.w * 1.2 && st.wide === 'none', st);
  await p.screenshot({ path: SH + 'invoice.png' });
  // a wide screen keeps the browser's own PDF viewer
  const d = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  await d.goto(`${B}/export/accounts/invoice/${iid}/view?token=${dl}`); await sleep(1500);
  ck('desktop: the PDF viewer, no drawn pages', await d.evaluate(() => getComputedStyle(document.querySelector('.pvwide')).display !== 'none' && getComputedStyle(document.querySelector('.pvphone')).display === 'none'));
  ck('no page errors', errs.length === 0, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
