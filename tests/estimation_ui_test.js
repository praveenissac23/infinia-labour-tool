// Estimation > Dashboard / Projects / Tenders, clicked through like a person would.
// Needs the server (tests/serve_like_nginx.py) with the admin login and a site in Settings.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/estui_';
let bad = 0; const fails = [];
const ck = (name, ok, info) => { if (!ok) { bad++; fails.push(name); } console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '  ' + JSON.stringify(info === undefined ? '' : info).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch();
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load/.test(m.text())) errs.push(m.text()); });
  await p.goto(B + '/portal/est-app.html?view=projects'); await p.fill('#lg-u', 'admin'); await p.fill('#lg-p', 'changeme123'); await p.click('#lg-go');
  await p.waitForSelector('#p-new'); await sleep(400);
  const api = async (path, opt = {}) => p.evaluate(async ([path, opt]) => { const r = await fetch(path, { method: opt.method || 'GET', headers: { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' }, body: opt.body ? JSON.stringify(opt.body) : undefined }); return r.json(); }, [path, opt]);
  const meta = await api('/store/est/meta');
  const used = new Set(meta.projects.map(x => x.code));
  const site = meta.sites.find(s => !used.has(s.code));
  ck('a free site to make a project from', !!site);
  // ---- new project from the site list ----
  await p.click('#p-new'); await sleep(300);
  await p.fill('#f-code', site.code); await p.dispatchEvent('#f-code', 'input');
  await p.fill('#f-contract_value', '1000000');
  await p.click('[data-q="ret_pct:1"]'); await p.click('[data-q="adv_pct:1"]');
  await p.click('#m-save'); await sleep(1200);
  const pname = await p.inputValue('.combo input');
  ck('project made and opened', pname.startsWith(site.code), pname);
  const pid = await p.evaluate(() => ST.pid);
  // ---- subcontract ----
  await p.click('#add-sub'); await sleep(300);
  await p.fill('#f-name', 'UI TEST CONTRACTING LLC'); await p.fill('#f-scope', 'Blockwork');
  await p.fill('#f-value', '200000'); await p.click('[data-q="adv_pct:1"]'); await p.click('[data-q="ret_pct:2"]');
  await p.click('#m-save'); await sleep(1200);
  ck('subcontract opened after saving', await p.isVisible('#drawer') && (await p.textContent('#d-title')).includes('UI TEST'));
  // advance PC, one click
  await p.click('#s-adv'); await sleep(300); await p.click('#m-save'); await sleep(900);
  let sub = (await api(`/store/est/projects/${pid}`)).subs[0];
  ck('advance PC = 10% of 200,000', sub.pcs[0].adv_amount === 20000 && sub.pcs[0].this === 20000, sub.pcs[0]);
  // invoice received + sent to site
  await p.click('#s-inv'); await sleep(300);
  await p.fill('#f-inv_ref', 'TINV-7'); await p.fill('#f-inv_amount', '60000');
  await p.click('#m-save'); await sleep(1000);
  sub = (await api(`/store/est/projects/${pid}`)).subs[0];
  ck('invoice logged and at site', sub.pcs[1].status === 'At site' && sub.pcs[1].to_site, sub.pcs[1].status);
  await p.click('#d-x'); await sleep(200);
  // invoice tracker: next-step buttons
  await p.click('[data-s="inv"]'); await sleep(400);
  await p.click(`[data-next="${sub.pcs[1].id}"]`); await sleep(900);
  sub = (await api(`/store/est/projects/${pid}`)).subs[0];
  ck('one click: back from site', sub.pcs[1].status === 'Back from site', sub.pcs[1].status);
  await p.click(`[data-next="${sub.pcs[1].id}"]`); await sleep(500);
  ck('Certify opens the certificate form', await p.isVisible('#f-work_cum'));
  await p.click('[data-q="work_cum:1"]'); await sleep(200);   // 25%
  const shown = await p.$$eval('#calc tr', rs => rs.map(r => r.textContent));
  const payTxt = shown.find(t => t.startsWith('Amount payable')) || '';
  // 25% of 200,000 = 50,000; adv rec 10% = 5,000; ret 10% = 5,000; adv paid 20,000 -> net 60,000; this = 40,000; +5% = 42,000
  ck('live figures: payable 42,000.00', payTxt.includes('42,000.00'), shown);
  ck('retention and recovery worked out', (await p.inputValue('#f-ret_cum')) === '5000' && (await p.inputValue('#f-adv_rec_cum')) === '5000');
  await p.click('#m-save'); await sleep(1100);
  sub = (await api(`/store/est/projects/${pid}`)).subs[0];
  ck('server agrees with the live figures', sub.pcs[1].payable === 42000 && sub.pcs[1].status === 'Certified', sub.pcs[1]);
  await p.screenshot({ path: SH + 'tracker.png' });
  await p.click(`[data-next="${sub.pcs[1].id}"]`); await sleep(800);
  await p.click(`[data-next="${sub.pcs[1].id}"]`); await sleep(800);
  sub = (await api(`/store/est/projects/${pid}`)).subs[0];
  ck('PC issued, then with Accounts', sub.pcs[1].status === 'With Accounts', sub.pcs[1].status);
  await p.click(`[data-next="${sub.pcs[1].id}"]`); await sleep(300);
  ck('Mark paid prefilled with the payable', (await p.inputValue('#f-amount')) === '42000');
  await p.fill('#f-ref', 'TT-55'); await p.click('#m-save'); await sleep(900);
  sub = (await api(`/store/est/projects/${pid}`)).subs[0];
  ck('paid', sub.pcs[1].status === 'Paid' && sub.pcs[1].paid_amount === 42000 && sub.pcs[1].paid_ref === 'TT-55', sub.pcs[1]);
  // undo with the arrow
  await p.click(`[data-undo="${sub.pcs[1].id}"]`); await sleep(800);
  sub = (await api(`/store/est/projects/${pid}`)).subs[0];
  ck('back one step with the arrow', sub.pcs[1].status === 'With Accounts' && sub.pcs[1].paid_amount === 0);
  // chips filter
  await p.click('[data-f="With Accounts"]'); await sleep(300);
  ck('status chip filters the list', (await p.$$('[data-next]')).length === 1);
  // ---- finalization: click to cycle ----
  await p.click('[data-s="final"]'); await sleep(400);
  const cell = await p.$('[data-fc$=":st"]');
  await cell.click(); await sleep(400); await cell.click(); await sleep(600);
  const fin = (await api(`/store/est/projects/${pid}`)).finals[0];
  ck('finalization cell cycles ✔ then X and saves', fin.st === 'X', fin.st);
  // ---- approvals: one click stamps the date ----
  await p.click('[data-g="site"]'); await sleep(300); await p.click('[data-s="approval"]'); await sleep(400);
  const ab = await p.$('[data-aq$=":Submitted"]'); await ab.click(); await sleep(800);
  const apr = (await api(`/store/est/projects/${pid}`)).logs.find(l => l.kind === 'approval' && l.status === 'Submitted');
  ck('approval submitted today', apr && apr.sent === meta.today, apr);
  // ---- RFI ----
  await p.click('[data-s="rfi"]'); await sleep(300);
  await p.click('#add-log'); await sleep(300); await p.fill('#f-title', 'Lintel detail'); await p.click('#m-save'); await sleep(900);
  ck('RFI listed as RFI-001', (await p.textContent('#sec')).includes('RFI-001'));
  await p.click('[data-reply]'); await sleep(800);
  ck('answer received in one click', (await api(`/store/est/projects/${pid}`)).logs.find(l => l.kind === 'rfi').status === 'Answered');
  // ---- BOQ paste ----
  await p.click('[data-g="client"]'); await sleep(300); await p.click('[data-s="boq"]'); await sleep(300);
  await p.click('#boq-paste'); await sleep(300);
  await p.fill('#f-text', 'WORKS\n1\tBlockwork\tm2\t100\t70\n2\tPlaster\tm2\t200\t30');
  await p.click('#m-save'); await sleep(1000);
  ck('BOQ pasted and totalled', (await p.textContent('#sec')).includes('13,000.00'));
  // inline edit of a rate
  await p.click('[data-ed$=":rate"]'); await p.fill('[data-ed$=":rate"] input', '80'); await p.keyboard.press('Enter'); await sleep(900);
  ck('click a rate, type, Enter', (await p.textContent('#sec')).includes('14,000.00'));
  // ---- exports open ----
  const [pop] = await Promise.all([p.waitForEvent('popup'), p.click('[data-xp="preview"]')]); await pop.waitForLoadState();
  ck('Preview opens with the filter', (await pop.title()).length > 0 && (await pop.content()).includes('BOQ'));
  await pop.close();
  // ---- remembers the project ----
  await p.reload(); await sleep(1500);
  ck('reload keeps the project and the tab', (await p.inputValue('.combo input')).startsWith(site.code) && await p.isVisible('#boq-paste'));
  // ---- picker search ----
  await p.click('.combo input'); await p.fill('.combo input', site.code); await sleep(200);
  ck('picker filters by code', (await p.$$('.combo .opt')).length >= 1);
  await p.keyboard.press('Escape');
  // ---- tenders ----
  await p.goto(B + '/portal/est-app.html?view=tenders'); await sleep(1200);
  await p.click('#add-t'); await sleep(300); await p.fill('#f-name', 'UI tender villa'); await p.click('[data-q="due:1"]'); await p.click('#m-save'); await sleep(900);
  ck('tender added', (await p.textContent('#app')).includes('UI tender villa'));
  // ---- dashboard ----
  await p.goto(B + '/portal/est-app.html?view=dash'); await sleep(1500);
  ck('dashboard lists the project', (await p.textContent('#app')).includes(site.code));
  await p.screenshot({ path: SH + 'dash.png' });
  // ---- phone ----
  const ph = await br.newContext({ viewport: { width: 390, height: 844 }, isMobile: true }); const q = await ph.newPage();
  q.on('pageerror', e => errs.push('phone: ' + e.message));
  const tok = await p.evaluate(() => sessionStorage.getItem('infinia_token'));
  await q.goto(B + '/portal/est-app.html?view=projects'); await q.evaluate(t => sessionStorage.setItem('infinia_token', t), tok);
  await q.evaluate(([pid]) => { localStorage.setItem('est_pid', pid); localStorage.setItem('est_sec', 'subs.inv'); }, [pid]);
  await q.reload(); await sleep(1800);
  const over = await q.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ck('phone: no sideways page scroll', over <= 1, over);
  await q.screenshot({ path: SH + 'phone.png' });
  await q.click('#add-inv'); await sleep(300);
  ck('phone: form fills the screen', (await q.$eval('.mbox', e => e.getBoundingClientRect().width)) >= 380);
  ck('no page errors', errs.length === 0, errs);
  console.log(bad ? `\n${bad} FAILED: ${fails.join(' | ')}` : '\nALL PASS');
  await br.close(); process.exit(bad ? 1 : 0);
})();
