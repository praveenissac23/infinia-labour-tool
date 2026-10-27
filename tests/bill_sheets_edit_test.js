// A bill's sheets: one viewer (zoom - / + / Fit width / 100%, the sheet filling the window), click a row to put a
// line or a section next to it or hide it, + Add page (a copy of a sheet, kept on the next bill), Delete page;
// the Excel opens with the added page in it. A new bill is made from the last bill, with what was added on it.
const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/bse_', DIR = process.env.BILLS || '/tmp/claude-0/bills/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'] }); const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = (path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === '904').id;
  const b64 = fs.readFileSync(DIR + '914-IPA-07.xlsx').toString('base64');
  await p.evaluate(async ([pid, b64]) => { const fd = new FormData(); fd.append('project_id', pid); fd.append('file', new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))]), '914-IPA-07.xlsx');
    await fetch('/store/est/ipa/format', { method: 'POST', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token') }, body: fd }); }, [P, b64]);
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'bills.ipa'); localStorage.removeItem('est_sheet_zoom'); }, [P]); await p.reload(); await sleep(2500);
  await p.click('#ipa-new'); await sleep(2500);
  await p.click('#ipa-nav [data-step="sheets"]'); await sleep(1800);
  // the viewer
  ck('zoom bar: - % + Fit width 100%', !!(await p.$('[data-sv="out"]')) && !!(await p.$('[data-sv="in"]')) && !!(await p.$('[data-sv="fit"]')) && !!(await p.$('[data-sv="one"]')));
  const box = await p.$eval('.sv-box', el => { const r = el.getBoundingClientRect(); return { bottom: innerHeight - r.bottom, sw: el.scrollWidth - el.clientWidth }; });
  ck('the sheet fills the window to the bottom (no empty band)', box.bottom >= 0 && box.bottom < 30, box);
  ck('fitted to the width: nothing cut off sideways', box.sw <= 2, box);
  const z0 = await p.textContent('.sv-pc'); await p.click('[data-sv="in"]'); await sleep(200); const z1 = await p.textContent('.sv-pc');
  ck('+ zooms in', parseInt(z1) > parseInt(z0), [z0, z1]);
  await p.click('[data-sv="one"]'); await sleep(200); ck('100% = actual size', (await p.textContent('.sv-pc')) === '100%');
  await p.click('[data-sv="fit"]'); await sleep(200);
  await p.selectOption('.sv-pick', { label: 'Works' }); await sleep(1500);
  await p.screenshot({ path: SH + '1_sheet.png' });
  // a row: line below, section
  const rows0 = await p.$$eval('.sv-box tr[data-r]', t => t.length);
  await p.click('.sv-box tr[data-r="4"] td:nth-child(2)'); await sleep(300);
  await p.keyboard.press('Escape'); await sleep(200);
  ck('clicking a row offers + Line above / below, + Section, Hide', (await p.textContent('#sv-rows')).includes('Row 4') && !!(await p.$('[data-rw="section"]')));
  await p.screenshot({ path: SH + '2_row.png' });
  await p.click('[data-rw="below"]'); await sleep(1800);
  const rows1 = await p.$$eval('.sv-box tr[data-r]', t => t.length);
  ck('+ Line below adds a line', rows1 === rows0 + 1, [rows0, rows1]);
  await p.click('.sv-box tr[data-r="5"] td:nth-child(2)'); await sleep(300); await p.keyboard.press('Escape'); await sleep(200);
  await p.click('[data-rw="section"]'); await sleep(1800);
  ck('+ Section below adds a heading line and a line', (await p.$$eval('.sv-box tr[data-r]', t => t.length)) === rows1 + 2);
  // type a heading in the new section line
  await p.click('.sv-box tr[data-r="6"] td:nth-child(2)'); await sleep(400);
  const cell = await p.$('.ipa-cell'); if (cell) { await cell.fill('Additional works'); await p.keyboard.press('Enter'); await sleep(1800); }
  ck('typed in the new line', (await p.textContent('.sv-box')).includes('Additional works'));
  // a page
  await p.click('[data-pg="add"]'); await sleep(400);
  await p.fill('#f-name', 'Variations 2'); await p.click('#m-save'); await sleep(2500);
  ck('+ Add page: "Variations 2" added and shown', (await p.inputValue('.sv-pick').catch(() => '')) !== '' && (await p.$eval('.sv-pick', s => s.options[s.selectedIndex].text)).includes('Variations 2'));
  await p.screenshot({ path: SH + '3_page.png' });
  const bid = (await api(`/store/est/ipa/list?project_id=${P}`)).bills[0].id;
  const tok = (await api('/auth/download-token', 'POST')); const t = tok.token || tok.download_token;
  const xl = await p.evaluate(async u => { const r = await fetch(u); const b = new Uint8Array(await r.arrayBuffer()); let s = ''; for (const x of b) s += String.fromCharCode(x); return [r.status, btoa(s)]; }, `${B}/export/est/ipa/${bid}?token=${t}&format=excel`);
  ck('Excel downloads', xl[0] === 200, xl[0]);
  fs.writeFileSync('/tmp/claude-0/bse_bill.xlsx', Buffer.from(xl[1], 'base64'));
  // the next bill keeps the page and the lines
  const nb = await api('/store/est/ipa/new', 'POST', { project_id: P });
  const nbill = await api(`/store/est/ipa/bill/${nb.id}`);
  ck('next bill keeps the added page', nbill.sheets.some(s => s.name === 'Variations 2'), nbill.sheets.map(s => s.name));
  await api(`/store/est/ipa/bill/${nb.id}`, 'DELETE');
  // delete the page
  await p.click('[data-pg="del"]'); await sleep(300); await p.click('#cfm-ok'); await sleep(2000);
  ck('Delete page takes it off', !(await p.$eval('.sv-pick', s => [...s.options].some(o => o.text.includes('Variations 2')))));
  // the previous-bill reader uses the same viewer
  await p.click('#b-back'); await sleep(1500);
  await p.click('#sec [data-fmview]'); await sleep(1500);
  ck('previous bill reader: same zoom bar, fills the window', !!(await p.$('#b-body [data-sv="fit"]')) && (await p.$eval('.sv-box', el => innerHeight - el.getBoundingClientRect().bottom)) < 30);
  await p.screenshot({ path: SH + '4_reader.png' });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
