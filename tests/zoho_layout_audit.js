// Layout audit of the new money screens at 1440 / 1024 / 390:
// clipped placeholders, values spilling past a field, overlapping fields,
// controls running off the screen, sideways page scroll.
const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8032', SH = '/tmp/claude-0/shots/';
let bad = 0; const issues = [];
const AUDIT = () => {
  const out = [];
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none' && el.offsetParent !== null; };
  const scr = [...document.querySelectorAll('.screen, [id^="screen-"], .zx-modal')].filter(vis);
  const root = document.querySelector('.zx-modal') && vis(document.querySelector('.zx-modal')) ? document.querySelector('.zx-modal') : (scr.find(s => s.id && s.id.startsWith('screen-')) || document.body);
  const ctx = document.createElement('canvas').getContext('2d');
  const tw = (el, t) => { const s = getComputedStyle(el); ctx.font = `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`; return ctx.measureText(t).width; };
  const inScroll = el => { for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if ((o === 'auto' || o === 'scroll') && a.scrollWidth > a.clientWidth) return true; } return false; };
  const name = el => '#' + (el.id || (el.className && String(el.className).split(' ')[0]) || el.tagName);
  const ctl = [...root.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=file]), select, textarea')].filter(vis);
  for (const el of ctl) {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    const room = el.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - (el.tagName === 'SELECT' ? 18 : 0);
    if (el.placeholder && !el.value && tw(el, el.placeholder) > room + 1) out.push(`placeholder cut: ${name(el)} "${el.placeholder}" (${Math.round(tw(el, el.placeholder))}>${Math.round(room)})`);
    if (el.tagName === 'SELECT' && el.selectedIndex >= 0) { const t = el.options[el.selectedIndex].text; if (tw(el, t) > room + 2) out.push(`choice cut: ${name(el)} "${t}"`); }
    if (r.right > innerWidth + 1 && !inScroll(el)) out.push(`off screen: ${name(el)} right=${Math.round(r.right)}`);
    if (el.clientWidth < 40 && el.tagName !== 'SELECT') out.push(`too narrow: ${name(el)} ${el.clientWidth}px`);
  }
  for (let i = 0; i < ctl.length; i++) for (let j = i + 1; j < ctl.length; j++) {
    const a = ctl[i].getBoundingClientRect(), b = ctl[j].getBoundingClientRect();
    const ov = Math.min(a.right, b.right) - Math.max(a.left, b.left), oh = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ov > 3 && oh > 3) out.push(`overlap: ${name(ctl[i])} / ${name(ctl[j])}`);
  }
  // labels sitting on top of their field or cut off
  for (const sp of [...root.querySelectorAll('label > span:first-child, .pc-f > span:first-child, .hr-field > span:first-child')].filter(vis)) {
    if (sp.scrollWidth > sp.clientWidth + 2 && getComputedStyle(sp).overflow !== 'visible') out.push(`label cut: "${sp.textContent.trim().slice(0, 40)}"`);
    const r = sp.getBoundingClientRect();
    for (const el of ctl) { const c = el.getBoundingClientRect(); const ov = Math.min(r.right, c.right) - Math.max(r.left, c.left), oh = Math.min(r.bottom, c.bottom) - Math.max(r.top, c.top); if (ov > 4 && oh > 4 && !sp.contains(el)) out.push(`label over field: "${sp.textContent.trim().slice(0, 30)}" / ${name(el)}`); }
  }
  for (const b of [...root.querySelectorAll('button')].filter(vis)) { if (b.scrollWidth > b.clientWidth + 2) out.push(`button text cut: "${b.textContent.trim().slice(0, 30)}"`); if (b.getBoundingClientRect().right > innerWidth + 1 && !inScroll(b)) out.push(`button off screen: "${b.textContent.trim().slice(0, 30)}"`); }
  for (const c of [...root.querySelectorAll('.card, .pc-card')].filter(vis)) if (c.scrollWidth > c.clientWidth + 2) { const w = [...c.querySelectorAll('*')].filter(x => vis(x) && !inScroll(x) && x.getBoundingClientRect().right > c.getBoundingClientRect().right + 1).slice(-1)[0]; out.push(`spills out of its card: ${w ? name(w) + ' "' + (w.textContent || '').trim().slice(0, 40) + '"' : ''}`); }
  if (document.documentElement.scrollWidth > innerWidth + 2) out.push(`page scrolls sideways (${document.documentElement.scrollWidth}>${innerWidth})`);
  return [...new Set(out)];
};
(async () => {
  const b = await chromium.launch();
  for (const W of [1440, 1024, 390]) {
    const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 844 : 950 } });
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/?p=accounts'); await p.fill('#login-username', 'shafiq'); await p.fill('#login-password', 'pass12345');
    await p.evaluate('doLogin()'); await p.waitForSelector('#app-screen', { state: 'visible' }); await p.waitForTimeout(2500);
    const shot = async (tag, prep) => {
      await p.evaluate(prep); await p.waitForTimeout(1500);
      const got = await p.evaluate(AUDIT);
      for (const g of got) { issues.push(`${W} ${tag}: ${g}`); bad++; }
      await p.screenshot({ path: `${SH}audit_${tag}_${W}.png`, fullPage: false });
    };
    await shot('petty', "pgTab('petty'); setTimeout(()=>{ try{pcBook('site')}catch(e){} },300)");
    await shot('petty_vat', "document.getElementById('pc-vat').checked=true; pcVat();");
    for (const k of ['vendor', 'customer', 'expense', 'charge', 'transfer'])
      await shot('bank_' + k, `pgTab('bank'); setTimeout(()=>bkKind('${k}'),400)`);
    await shot('bank_cheque', "bkKind('vendor'); const m=document.getElementById('bk-mode'); m.value=[...m.options].find(o=>/cheque/i.test(o.value)).value; bkMode();");
    await shot('zoho', "pgTab('zoho')");
    await shot('invoice_release', "pgTab('taxinv'); setTimeout(async()=>{ const d=await apiCall('/accounts/invoices?kind=tax').catch(()=>null); const l=(d&&(d.invoices||d))||[]; const x=Array.isArray(l)?l.find(i=>!i.zoho):null; if(x) invRelease(x.id); },900)");
    await p.evaluate("document.querySelectorAll('.zx-modal').forEach(m=>m.remove())");
    await shot('loan', "pgGo ? 0 : 0; location.hash=''; try{ showScreen('hrpayroll'); hrTab('loans'); }catch(e){}");
    if (errs.length) { issues.push(`${W} page errors: ${errs.join(' | ')}`); bad++; }
    await ctx.close();
  }
  console.log(issues.join('\n') || 'no layout issues');
  console.log(bad ? `${bad} ISSUES` : 'ALL PASS');
  await b.close();
})();
