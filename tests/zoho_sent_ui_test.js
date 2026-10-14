// Send to Zoho > Sent to Zoho: the log of what went where (from -> to),
// filters, Check and Reverse buttons, the reason box, exports.
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
execSync(`python3 - <<'PY'
import sqlite3, json, datetime
c = sqlite3.connect('/tmp/zm.db')
c.execute("""create table if not exists zoho_log (id integer primary key, at datetime, user_id integer, source varchar, item_id integer, ref varchar, action varchar,
  kind varchar, zoho_id varchar, number varchar, on_date varchar, amount float, from_acc varchar, to_acc varchar, detail text, ok boolean, error varchar,
  reversed_at datetime, reversed_by integer, reverse_reason varchar)""")
now = datetime.datetime.utcnow()
uid = c.execute("select id from users where username='admin'").fetchone()[0]
pid = c.execute("select id from petty_cash order by id desc limit 1").fetchone()[0]
rows = [("petty", pid, "PC-%d" % pid, "create", "expense", "E1", "PC-%d" % pid, 420.0, "Site Petty Cash", "05. Blockworks › Block Purchase", {"project": "913", "supplier": "Dani Building Materials", "vat": "5% claimed"}, 1, ""),
        ("petty", pid, "PC-%d" % pid, "create", "banktransaction", "T2", "PC-%d" % pid, 500.0, "Site Petty Cash", "Cash", {}, 1, ""),
        ("bank", 1, "BK-1", "create", "vendorpayment", "VP3", "12", 23505.72, "ADCB", "Ghantoot Building Materials (supplier)", {}, 1, ""),
        ("petty", pid, "PC-%d" % pid, "create", "expense", "", "", 10.0, "Site Petty Cash", "Office Pantry Expenses", {}, 0, "Account is inactive"),
        ("supplier", 1, "Dani", "update", "contact", "C9", "", 0.0, "Portal supplier list", "Dani Building Materials", {}, 1, "")]
for i, (src, item, ref, act, kind, zid, num, amt, fr, to, det, ok, err) in enumerate(rows):
    c.execute("insert into zoho_log (at,user_id,source,item_id,ref,action,kind,zoho_id,number,on_date,amount,from_acc,to_acc,detail,ok,error) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ((now - datetime.timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S'), uid, src, item, ref, act, kind, zid, num, '2026-10-14', amt, fr, to, json.dumps(det), ok, err))
c.commit()
PY`);
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  await p.evaluate(() => { const t = [...document.querySelectorAll('#pg-tabs .pg-tab')].find(x => x.textContent.trim() === 'Send to Zoho'); t.click(); }); await p.waitForTimeout(3000);
  const tabs = await p.evaluate(() => [...document.querySelectorAll('#zh-tabs .zh-tab')].map(t => t.textContent.trim()));
  ck('Sent to Zoho tab is there', tabs.some(t => /^Sent to Zoho/.test(t)), tabs);
  await p.click('#zh-tabs .zh-tab >> text=Sent to Zoho'); await p.waitForTimeout(1500);
  const n = await p.locator('#zs-body tr').count();
  ck('three lines in Zoho listed (refusals and supplier updates hidden)', n === 3, n);
  const first = await p.locator('#zs-body tr').first().textContent();
  ck('from -> to shown with parent account', /Site Petty Cash/.test(first) && /05\. Blockworks ›/.test(first) && /Block Purchase/.test(first) && /→/.test(first), first);
  ck('project, supplier, VAT and Zoho number shown', /Project 913/.test(first) && /Dani Building/.test(first) && /5% claimed/.test(first) && /Expense/.test(first));
  ck('Open, Check, Reverse on each', await p.locator('#zs-body tr').first().locator('.btn').count() === 3);
  const st = await p.locator('#zs-stats').textContent();
  ck('totals: 3 lines, AED 24,425.72', /3 lines/.test(st) && /24,425\.72/.test(st), st);
  await p.screenshot({ path: SH + 'zs_list.png' });
  // all changes
  await p.check('#zs-allc'); await p.waitForTimeout(1200);
  const n2 = await p.locator('#zs-body tr').count();
  ck('All changes adds the refusal and the supplier update', n2 === 5, n2);
  ck('refusal shows Zoho\'s reason', /Account is inactive/.test(await p.locator('#zs-body').textContent()));
  await p.uncheck('#zs-allc'); await p.waitForTimeout(1200);
  // search
  await p.fill('#zs-q', 'ghantoot'); await p.waitForTimeout(200);
  ck('search narrows the list', await p.locator('#zs-body tr').count() === 1);
  await p.fill('#zs-q', ''); await p.waitForTimeout(200);
  // check (Zoho not connected here): a clear message, no crash
  await p.locator('#zs-body tr').first().locator('button', { hasText: 'Check' }).click(); await p.waitForTimeout(800);
  ck('Check without Zoho connected says so', /not connected/i.test(await p.locator('#zs-body tr').first().textContent()));
  // reverse dialog
  await p.locator('#zs-body tr').first().locator('button', { hasText: 'Reverse' }).click(); await p.waitForTimeout(300);
  ck('reverse asks why, shows what will happen', await p.locator('.zx-modal #zr-why').count() === 1 && /deleted in Zoho/i.test(await p.locator('.zx-modal').textContent()));
  await p.screenshot({ path: SH + 'zs_reverse.png' });
  await p.click('#zr-yes'); await p.waitForTimeout(600);
  ck('no reason: refused with a message', /reason/i.test(await p.locator('#zr-err').textContent()), await p.locator('#zr-err').textContent());
  await p.fill('#zr-why', 'wrong account'); await p.click('#zr-yes'); await p.waitForTimeout(800);
  ck('Zoho not connected: says so, nothing changed', /not connected/i.test(await p.locator('#zr-err').textContent()));
  await p.click('#zr-no');
  // exports
  const tok = await p.evaluate(async () => { await refreshDownloadToken(); return cachedDownloadToken; });
  for (const f of ['view', 'pdf', 'excel']) {
    const r = await p.request.get(`${B}/export/zoho/sent?format=${f}&start=2026-10-01&end=2026-12-31&source=&all=0&token=${encodeURIComponent(tok)}`);
    ck(`export ${f}`, r.ok() && (await r.body()).length > 500, r.status());
  }
  // phone
  await p.setViewportSize({ width: 390, height: 844 }); await p.waitForTimeout(400);
  ck('phone: no sideways scroll of the page', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
  await p.screenshot({ path: SH + 'zs_phone.png' });
  ck('no page errors', !errs.length, errs);
  console.log(bad ? `${bad} FAILED` : 'ALL PASS'); await b.close();
})();
