// LPO: the contact person brings his own number - the store brings its keeper and his proper mobile, a site its
// in-charge and his; an old or short number on another list never wins; a contact picked by hand stays.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032';
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(i === undefined ? '' : i).slice(0, 300))); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => { const br = await chromium.launch(); const p = await (await br.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()'); await sleep(3000);
  await p.evaluate(async () => { const h = { Authorization: 'Bearer ' + sessionStorage.getItem('infinia_token'), 'Content-Type': 'application/json' };
    await fetch('/engineers', { method: 'POST', headers: h, body: JSON.stringify({ name: 'Amal', mobile: '94039202' }) });          // an old short number on the engineer list
    await fetch('/engineers', { method: 'POST', headers: h, body: JSON.stringify({ name: 'AKHIL', mobile: '0562133135' }) });
    await fetch('/sites', { method: 'POST', headers: h, body: JSON.stringify({ code: 'Store', incharge: 'Amal', incharge_mobile: '0566826227' }) });
    await fetch('/sites', { method: 'POST', headers: h, body: JSON.stringify({ code: '914', incharge: 'AKHIL', incharge_mobile: '0562133135' }) }); });
  await p.goto(B + '/?p=store'); await sleep(3500); await p.evaluate(() => loadPurchase()); await sleep(2500);
  await p.evaluate(() => newLpo()); await sleep(2000);
  const pick = async v => { await p.evaluate(v => { document.getElementById('lpo-location').value = v; onLpoSite(); }, v); await sleep(300); return p.evaluate(() => [document.getElementById('lpo-contact').value, document.getElementById('lpo-mobile').value]); };
  let r = await pick('Store');
  ck('Store: contact Amal with his proper mobile 0566826227 (not the old 94039202)', r[0].toLowerCase() === 'amal' && r[1] === '0566826227', r);
  r = await pick('914');
  ck('914: contact follows the site - AKHIL 0562133135', r[0] === 'AKHIL' && r[1] === '0562133135', r);
  await p.evaluate(() => { const s = document.getElementById('lpo-contact'); const o = [...s.options].find(x => x.value.toLowerCase() === 'amal'); s.value = o.value; s.dispatchEvent(new Event('change')); }); await sleep(300);
  ck('picking a person brings his number', (await p.inputValue('#lpo-mobile')) === '0566826227', await p.inputValue('#lpo-mobile'));
  r = await pick('Store'); r = await pick('914');
  ck('a contact picked by hand stays when the site changes', r[0].toLowerCase() === 'amal' && r[1] === '0566826227', r);
  await br.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS'); process.exit(bad ? 1 : 0); })();
