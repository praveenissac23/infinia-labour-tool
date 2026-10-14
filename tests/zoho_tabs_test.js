// Send to Zoho in tabs: Petty cash, Bank, LPOs, Staff loans, Needs attention,
// October check, Suppliers - counts on the tabs, ticking lines with a
// running total, Send on one line, the remembered tab, layout.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
async function login(b, u, pw, W = 1440) {
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } }); const p = await ctx.newPage(); p.on('dialog', d => d.accept());
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.errs = errs;
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', u); await p.fill('#login-password', pw); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); return p;
}
const openZoho = async p => { await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Send to Zoho'); t.click(); }); await p.waitForTimeout(3000); };
const tabs = p => p.evaluate(() => [...document.querySelectorAll('#zh-tabs .zh-tab')].map(t => t.textContent.trim()));
const visible = p => p.evaluate(() => [...document.querySelectorAll('#screen-zoho .zh-pane')].filter(x => x.style.display !== 'none').map(x => x.dataset.pane));
(async () => {
  const b = await chromium.launch();
  const p = await login(b, 'shafiq', 'pass12345');
  // two bank lines waiting
  for (const body of [{ kind: 'vendor', date: '2026-10-02', party: 'Ghantoot Building Materials', mode: 'Bank Transfer', reference: 'PHUB1', amount: '1000' },
                      { kind: 'charge', date: '2026-10-03', mode: 'Bank Transfer', amount: '52.50' }])
    await p.evaluate(async b => { try { await apiCall('/store/bank', { method: 'POST', body: JSON.stringify(b) }); } catch (e) {} }, body);
  await openZoho(p);
  const t = await tabs(p);
  ck('eight tabs', t.length === 8 && /^Petty cash/.test(t[0]) && /^Bank/.test(t[1]) && /^LPOs/.test(t[2]) && /^Suppliers/.test(t[6]) && /^Sent to Zoho/.test(t[7]), t);
  ck('Bank tab counts 2', /^Bank2$/.test(t[1]), t[1]);
  ck('one pane at a time', (await visible(p)).length === 1, await visible(p));
  const ready = await p.evaluate(() => ZH.rows.filter(r => !zhFlags(r).length).length);
  const sends = await p.locator('#zh-body .zh-acts .btn-primary', { hasText: 'Send' }).count();
  ck(`petty cash: Send only on ready lines (${ready} ready of ${await p.evaluate(() => ZH.rows.length)})`, sends === ready, sends);
  await p.evaluate(() => scrollTo(0, 0)); await p.screenshot({ path: SH + 'zt_petty.png' });
  // LPOs
  await p.click('#zh-tabs .zh-tab >> text=LPOs'); await p.waitForTimeout(400);
  ck('LPO pane shown', JSON.stringify(await visible(p)) === '["lpo"]');
  const nl = await p.locator('#zh-pos tbody tr').count();
  const nWait = await p.evaluate(() => (ZH.pos || []).filter(o => !o.status && !o.cancelled).length);
  if (!nWait) { ck('no LPOs waiting: the pane says so', /No LPOs waiting/.test(await p.locator('#zh-pos').textContent())); }
  else {
  ck('LPOs listed with a tick box each', nl > 0 && (await p.locator('#zh-pos tbody input[type=checkbox]').count()) === nl, nl);
  const free = p.locator('#zh-pos tbody input[type=checkbox]:not([disabled])');
  if (await free.count() >= 2) {
    await free.nth(0).check(); await free.nth(1).check(); await p.waitForTimeout(200);
    ck('ticking shows how many and the total', /2 LPOs ticked · AED/.test(await p.locator('#zh-pos .zh-foot').textContent()), await p.locator('#zh-pos .zh-foot').textContent());
  } else {
    ck('unlinked LPOs cannot be ticked, the first step says why', /not linked to Zoho yet/.test(await p.locator('#zh-pos').textContent()));
  }
  ck('send buttons wait for Zoho to be connected', await p.locator('#zh-pos .zh-foot .btn-primary').isDisabled());
  }
  await p.screenshot({ path: SH + 'zt_lpo.png' });
  // Bank
  await p.click('#zh-tabs .zh-tab >> text=Bank'); await p.waitForTimeout(400);
  ck('bank pane lists the 2 lines', (await p.locator('#zh-bank tbody tr').count()) === 2);
  await p.click('#zh-bank thead input[type=checkbox]'); await p.waitForTimeout(200);
  ck('tick all: 2 ticked, AED 1,052.50', /2 bank lines ticked · AED 1,052.50/.test(await p.locator('#zh-bank .zh-foot').textContent()), await p.locator('#zh-bank .zh-foot').textContent());
  await p.screenshot({ path: SH + 'zt_bank.png' });
  // Suppliers / October / attention
  await p.click('#zh-tabs .zh-tab >> text=Suppliers'); await p.waitForTimeout(1500);
  ck('suppliers pane loads the list', (await p.locator('#zh-sup-body tr').count()) >= 1 && /linked/.test(await p.locator('#zh-sup-n').textContent()));
  await p.click('#zh-tabs .zh-tab >> text=October check'); await p.waitForTimeout(300);
  ck('October check pane', await p.locator('#zh-oct-btn').isVisible());
  await p.click('#zh-tabs .zh-tab >> text=Needs attention'); await p.waitForTimeout(300);
  ck('needs attention says when nothing is wrong', /Nothing needs attention|approved but not in Zoho|without the supplier/.test(await p.locator('[data-pane=attention]').textContent()));
  // empty ids never sent
  const r = await p.evaluate(async () => { const before = ZH.bank.length; await zhSendIds('bank', [], document.createElement('button')); return before === ZH.bank.length; });
  ck('an empty selection sends nothing', r);
  // remembered tab
  await p.click('#zh-tabs .zh-tab >> text=LPOs'); await p.waitForTimeout(200);
  await p.evaluate(() => { ZH_PANE = null; try { ZH_PANE = localStorage.getItem('infinia_zh_pane'); } catch (e) {} return zhLoad(); }); await p.waitForTimeout(1500);
  ck('the last tab is remembered', JSON.stringify(await visible(p)) === '["lpo"]', await visible(p));
  for (const W of [1440, 1024, 390]) {
    const q = await login(b, 'shafiq', 'pass12345', W); await openZoho(q);
    for (const pane of ['petty', 'bank', 'lpo']) {
      await q.evaluate(k => zhPane(k), pane); await q.waitForTimeout(300);
      ck(`layout ${W} ${pane}: no sideways scroll`, await q.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
    }
    if (W === 390) await q.screenshot({ path: SH + 'zt_390.png', fullPage: true });
    ck(`no page errors at ${W}`, !q.errs.length, q.errs);
  }
  console.log(bad ? `${bad} FAILED` : 'ALL PASS');
  await b.close();
})();
