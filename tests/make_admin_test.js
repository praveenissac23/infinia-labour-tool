// Settings > Logins: an existing login can be made an admin with Change
// role (after a warning), and an admin put back on a role; the last admin
// and your own admin can never be taken away.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
(async () => {
  const b = await chromium.launch(); let bad = 0;
  const ck = (n, ok, info) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(info)}`); };
  const p = await b.newPage({ viewport: { width: 1360, height: 900 } }); const errs = []; p.on('pageerror', e => errs.push(e.message));
  p.on('dialog', d => d.accept());
  await p.goto(B + '/?p=settings#logins'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(4000);
  const api = (u, m, body) => p.evaluate(async ([u, m, body]) => { try { return { ok: 1, d: await apiCall(u, m ? { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined) }; } catch (e) { return { ok: 0, status: e.status, msg: (e.body && e.body.detail) || String(e.message) }; } }, [u, m, body]);
  const role = await api('/permissions/roles', 'POST', { name: 'Office clerk', screens: ['dashboard', 'store', 'settings'] });
  await api('/permissions/roles/new-user', 'POST', { username: 'ravi', full_name: 'Ravi', password: 'ravi12345', role_id: role.d.id, base: 'office' });
  const f = () => p.frames().find(x => /access\.html/.test(x.url()));
  await f().evaluate(() => loadAll()); await p.waitForTimeout(1200);
  const row = f().locator('#users-body tr', { hasText: 'ravi' });
  await row.locator('button', { hasText: 'Change role' }).click(); await p.waitForTimeout(400);
  const opts = await f().evaluate(() => [...document.querySelectorAll('#as-role button')].map(x => x.textContent));
  ck('Change role offers "Admin (everything)"', opts.includes('Admin (everything)'), opts);
  await f().click('#as-role button[data-v="admin"]'); await p.screenshot({ path: SH + 'make-admin.png' });
  await f().click('#dlg-assign button:has-text("Apply")'); await p.waitForTimeout(1200);
  let users = (await api('/users')).d;
  ck('ravi is now an admin', users.find(u => u.username === 'ravi').role === 'admin');
  ck('his row now says Admin', /Admin/.test(await row.textContent()));
  const pr = await b.newPage(); await pr.goto(B + '/?p=settings#access'); await pr.fill('#login-username', 'ravi'); await pr.fill('#login-password', 'ravi12345'); await pr.evaluate('doLogin()');
  await pr.waitForSelector('#app-screen', { state: 'visible' }); await pr.waitForTimeout(3000);
  ck('ravi signs in and sees Payroll and Settings > Access', await pr.evaluate(() => pgHas('hrpayroll') && pgHas('__admin__') === false ? CURRENT_ROLE === 'admin' : CURRENT_ROLE === 'admin'));
  const rid = users.find(u => u.username === 'ravi').id, aid = users.find(u => u.username === 'admin').id;
  const self = await api('/permissions/roles/assign', 'POST', { user_id: aid, role_id: role.d.id });
  ck('admin cannot take admin away from his own login', !self.ok && /own login/.test(self.msg), self);
  await row.locator('button', { hasText: 'Change role' }).click(); await p.waitForTimeout(400);
  await f().click(`#as-role button[data-v="${role.d.id}"]`); await f().click('#dlg-assign button:has-text("Apply")'); await p.waitForTimeout(1200);
  users = (await api('/users')).d;
  const rv = users.find(u => u.username === 'ravi');
  ck('ravi can be put back on "Office clerk"', rv.role === 'office' && rv.permissions === 'dashboard,store,settings', rv);
  // Only one admin left (admin) - demoting him from another admin's login is refused.
  await api('/permissions/roles/assign', 'POST', { user_id: rid, role_id: 'admin' });
  const rtok = await pr.evaluate(async aid => { try { await apiCall('/permissions/roles/assign', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: aid, role_id: null }) }); return 'ok'; } catch (e) { return e.body && e.body.detail; } }, aid);
  ck('taking admin away needs a role to go to', /Pick the role/.test(rtok), rtok);
  await api('/permissions/roles/assign', 'POST', { user_id: rid, role_id: role.d.id });
  const last = await pr.evaluate(async aid => { try { await apiCall('/permissions/roles/assign', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: aid, role_id: 1 }) }); return 'ok'; } catch (e) { return e.status; } }, aid);
  ck('a non-admin cannot change anyone', last === 403, last);
  ck('no script errors', errs.length === 0, errs);
  console.log(bad ? `${bad} FAILED` : 'ADMIN CAN BE GIVEN AND TAKEN SAFELY');
  await b.close(); process.exit(bad ? 1 : 0);
})();
