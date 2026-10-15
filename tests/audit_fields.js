// Audit: on every screen, visible boxes without a placeholder (text/number/textarea) and without an (i).
const { chromium } = require('playwright'); const fs = require('fs'); const B = 'http://127.0.0.1:8032';
(async () => { const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1440, height: 950 } })).newPage();
  await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
  await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
  const tree = await p.evaluate(() => Object.entries(ALL_TABS).map(([k, tabs]) => [k, tabs.filter(t => !t.hidden).map(t => ({ id: t.id, subs: t.subs.map(s => s.id) }))]));
  const res = {};
  const check = async where => {
    await p.waitForTimeout(1900);   // tips run 400 ms after changes
    res[where] = await p.evaluate(() => {
      const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
      const name = el => { const lab = el.closest('label'); const f = el.closest('.field'); const t = (lab && lab.textContent) || (f && f.querySelector('label') && f.querySelector('label').textContent) || el.getAttribute('aria-label') || el.name || el.id || '';
        return t.replace(/\s+/g, ' ').replace(/\bi\b$/, '').trim().slice(0, 40) || ('#' + el.id); };
      const boxes = [...document.querySelectorAll('.screen.active input, .screen.active select, .screen.active textarea')].filter(el => vis(el) && !['hidden', 'checkbox', 'radio', 'file', 'button', 'submit', 'color', 'range'].includes(el.type) && !el.closest('table tbody') && !el.readOnly);
      const noPh = boxes.filter(el => ['text', 'number', 'search', 'email', 'tel', ''].includes(el.type) && el.tagName !== 'SELECT' && !el.placeholder && !el.value).map(name);
      const hasI = el => { const lab = el.closest('label'); const f = el.closest('.field'); return !!((lab && lab.querySelector('.help-i')) || (f && f.querySelector('.help-i')) || (el.nextElementSibling && el.nextElementSibling.classList.contains('help-i')) || (el.parentElement && el.parentElement.querySelector(':scope > .help-i'))); };
      const sel = el => el.id ? '#' + el.id : (el.name ? `${el.tagName.toLowerCase()}[name="${el.name}"]` : null);
      const noI = boxes.filter(el => !hasI(el) && el.type !== 'search').map(el => `${sel(el) || '?'} || ${name(el)} || ${el.placeholder || ''} || ${el.tagName === 'SELECT' ? [...el.options].slice(0,4).map(o => o.text).join('/') : el.type}`);
      return { boxes: boxes.length, noPh, noI };
    });
  };
  for (const [key, tabs] of tree) {
    await p.evaluate(k => pgGo(k), key); await p.waitForTimeout(800);
    for (const t of tabs) {
      const ok = await p.evaluate(id => { const t = PAGE.tabs.find(x => x.id === id); return !!t && pgTabOk(t); }, t.id).catch(() => false); if (!ok) continue;
      await p.evaluate(id => pgTab(id), t.id); await check(`${key}>${t.id}`);
      for (const s of t.subs.slice(1)) { await p.evaluate(id => pgSub(id), s); await check(`${key}>${t.id}>${s}`); }
    }
  }
  fs.writeFileSync('/tmp/claude-0/audit/fields.json', JSON.stringify(res, null, 1));
  let tb = 0, tp = 0, ti = 0;
  for (const [w, r] of Object.entries(res)) { tb += r.boxes; tp += r.noPh.length; ti += r.noI.length; if (r.noPh.length || r.noI.length) console.log(`${w}: ${r.boxes} boxes | no placeholder: ${r.noPh.join('; ')} | no (i): ${r.noI.join('; ')}`); }
  console.log(`TOTAL boxes ${tb}, without placeholder ${tp}, without (i) ${ti}`);
  await b.close(); })();
