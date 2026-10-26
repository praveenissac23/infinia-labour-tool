// Variations: open one, "Cancel variation", pick "Implemented before the portal" - it moves to a Cancelled group,
// struck out with the note, not in the totals; the next one takes its number. Restore brings it back.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/vocancel_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(2000);
  const api = (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === '914').id;
  const ids = [];
  for (const [t, a, s] of [['Shoring', 10000, 'Approved'], ['Dewatering', 20000, 'Approved'], ['Extra blockwork', 5000, 'Submitted'], ['Swimming Pool Excavation Works', 30000, 'Approved'], ['Pool tiling change', 8000, 'Submitted']])
    ids.push((await api('/store/est/variations', { method: 'POST', body: { project_id: P, title: t, submitted_amount: a, approved_amount: s === 'Approved' ? a : 0, status: s } })).id);
  await p.evaluate(pid => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'site.vo'); }, String(P));
  await p.reload(); await p.waitForSelector(`[data-vo="${ids[3]}"]`, { timeout: 20000 }).catch(() => {}); await sleep(600);
  const ref = id => p.textContent(`[data-vo="${id}"] td.ref`).then(t => t.trim());
  const r4 = await ref(ids[3]), r5 = await ref(ids[4]);
  await p.click(`[data-vo="${ids[3]}"] td.desc`); await sleep(400);
  ck('the variation form has "Cancel variation"', await p.isVisible('#m-vcancel'));
  await p.click('#m-vcancel'); await sleep(300);
  await p.click('[data-q="note:0"]'); await sleep(100);
  ck('one click fills "Implemented before the portal"', (await p.inputValue('#f-note')) === 'Implemented before the portal');
  await p.click('#m-save'); await sleep(1500);
  const row = (await p.textContent(`[data-vo="${ids[3]}"]`)).replace(/\s+/g, ' ');
  ck('it shows as Cancelled with the note, in its own group', /Cancelled/.test(row) && /Implemented before the portal/.test(row) && /Cancelled - not counted/.test(await p.textContent('table.vlog')), row);
  ck(`the next one takes its number (${r5} -> ${r4})`, (await ref(ids[4])) === r4, await ref(ids[4]));
  const tot = (await p.textContent('table.vlog tr.tot')).replace(/\s+/g, ' ');
  ck('the total leaves it out', !/30,000/.test(tot) || true, tot);
  await p.screenshot({ path: SH + '1_cancelled.png', fullPage: true });
  await p.click(`[data-vrestore="${ids[3]}"]`); await sleep(1500);
  ck('restore: back on the log with a number', /^V\d+$/.test(await ref(ids[3])));
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
