// Send to Zoho > LPOs: the LPO number opens the LPO; a one-time tip says so
// (once per login, not again after a reload).
const { chromium } = require('playwright');
const { execSync } = require('child_process');
execSync(`cd app && DATABASE_URL=sqlite:////tmp/zm.db python3 -W ignore - <<'PY'
import models
from database import SessionLocal
from datetime import date
s = SessionLocal()
if not s.query(models.PurchaseOrder).filter(models.PurchaseOrder.po_no == 20269901).first():
    o = models.PurchaseOrder(po_no=20269901, ref="IC/LPO/20269901", order_date=date(2026, 10, 14), supplier_name="Cretepro Building Material Trading LLC", status="issued", zoho_status="")
    s.add(o); s.flush()
    s.add(models.PurchaseOrderLine(order_id=o.id, description="Cement OPC", qty=50, unit="bag", rate=16.5, tax_pct=5))
    s.commit()
PY`, { stdio: 'pipe' });
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 950 } }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  const open = async () => {
    await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Send to Zoho'); t.click(); }); await p.waitForTimeout(3000);
    await p.click('#zh-tabs .zh-tab >> text=LPOs'); await p.waitForTimeout(1200);
  };
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  await open();
  const n = await p.locator('#zh-pos .zh-open').count();
  ck('LPO numbers are clickable', n > 0, n);
  ck('no View buttons', await p.locator('#zh-pos .zh-view').count() === 0);
  ck('the tip shows the first time', await p.locator('.zh-tip').isVisible());
  await p.screenshot({ path: SH + 'zh_lpo_tip.png' });
  await p.click('.zh-tip button'); await p.waitForTimeout(300);
  ck('Got it closes it', await p.locator('.zh-tip').count() === 0);
  await p.evaluate(() => { window.__opened = []; window.open = u => { window.__opened.push(u); return null; }; });
  await p.locator('#zh-pos .zh-open').first().click(); await p.waitForTimeout(800);
  const u = await p.evaluate(() => window.__opened[0] || '');
  const r = u ? await ctx.request.get(new URL(u, B).href) : null;
  ck('clicking the number opens the LPO PDF', /\/export\/purchase\//.test(u) && r && r.status() === 200 && /pdf/.test(r.headers()['content-type'] || ''), [u, r && r.status()]);
  await p.reload(); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500); await open();
  ck('not shown again after a reload', await p.locator('.zh-tip').count() === 0);
  ck('no page errors', errs.length === 0, errs);
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0);
})();
