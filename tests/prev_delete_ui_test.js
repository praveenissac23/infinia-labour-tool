// Previous records: what was brought in is listed from the records themselves (with its file), a bill
// uploaded twice is marked Twice, and Delete (pressed twice) removes the extra one.
const { chromium } = require('playwright');
const B = process.env.BASE || 'http://127.0.0.1:8032', SH = process.env.SHOTS || '/tmp/claude-0/prevdel_';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go'); await sleep(1500);
  const api = (path, method = 'GET', body) => p.evaluate(async ([path, method, body]) => { const r = await fetch(path, { method, headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return r.json(); }, [path, method, body]);
  const P = (await api('/store/est/meta')).projects.find(x => x.code === '901').id;
  const mk = (seq, file, cum, due) => api('/store/est/clientpcs', 'POST', { project_id: P, seq, claimed_cum: cum, status: 'Paid', period_to: '2026-05-14',
    remarks: `Previous record: ${file} · bill ${seq} · amount due ${due}` });
  await mk(1, '914-IPA-01 R3.xlsx', 289140.83, '273,238.00');
  await mk(2, '914-IPA-02 - R1.xlsx', 427959, '140,903.00');
  await api('/store/est/clientpcs', 'POST', { project_id: P, seq: 2, claimed_cum: 427959, status: 'Paid', period_to: '2026-05-14', remarks: '' });   // twice - and its remarks empty, as on 914
  await mk(3, '914 - IPA - 03 - R1.xlsx', 605743.28, '161,447.00');
  await p.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'prev.rec'); }, [P]); await p.reload(); await sleep(1800);
  const txt = await p.textContent('#sec');
  ck('the brought-in list is there after a reload, with the file names', txt.includes('Client bills and subcontractor PCs in the app') && txt.includes('914-IPA-02 - R1.xlsx') && txt.includes('914-IPA-01 R3.xlsx'));
  ck('Bill 2 is marked Twice (both rows), the others not', (await p.$$('#sec .st.a')).length === 2, (await p.$$('#sec .st.a')).length);
  await p.screenshot({ path: SH + '1_twice.png', fullPage: false });
  const dels = await p.$$('#sec [data-pdel]');
  const btn = dels[2];                                    // the second Bill 2
  await btn.click(); await sleep(300);
  ck('first press asks', (await btn.textContent()).includes('Press again'));
  await btn.click(); await sleep(1500);
  const left = (await api(`/store/est/projects/${P}`)).clientpcs.filter(c => c.seq === 2).length;
  ck('second press deletes it: one Bill 2 left', left === 1, left);
  ck('no Twice mark any more', (await p.$$('#sec .st.a')).length === 0);
  await p.screenshot({ path: SH + '2_after.png', fullPage: false });
  ck('no page errors', !errs.length, errs);
  await br.close(); console.log(bad ? `\n${bad} FAILED` : '\nALL PASS'); process.exit(bad ? 1 : 0);
})();
