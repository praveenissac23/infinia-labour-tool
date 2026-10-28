// Chat: documents open in a preview (as on WhatsApp) - PDF page by page with page 1 in the chat, Excel as a table,
// Word as text, PowerPoint slide by slide; other files say there is no preview and offer the download.
const { chromium } = require('playwright');
const path = require('path');
const B = process.env.BASE || 'http://127.0.0.1:8042', OUT = process.env.OUT || '/tmp', DOCS = process.env.DOCS;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let bad = 0; const ck = (n, ok, i) => { if (!ok) bad++; console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${ok ? '' : '  ' + JSON.stringify(i)}`); };
(async () => {
  const b = await chromium.launch();
  for (const [vw, vh, tag] of [[1440, 900, 'pc'], [390, 844, 'phone']]) {
    const ctx = await b.newContext({ viewport: { width: vw, height: vh } }); const p = await ctx.newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto(B + '/'); await p.fill('#login-username', 'admin'); await p.fill('#login-password', 'changeme123'); await p.evaluate('doLogin()');
    await p.waitForSelector('#app-screen', { state: 'visible' }); await sleep(2500);
    await p.evaluate(() => { window.checkBuild = () => {}; const x = document.getElementById('build-bar'); if (x) x.remove(); });
    await p.click(tag === 'pc' ? '.pg-side .pg-chat' : '#chat-btn'); await sleep(1200); await p.click('[data-room="all"]'); await sleep(800);
    const files = ['LPO-1042 Al Raha Scaffolding.pdf', 'BOQ 914 rev2.xlsx', 'Subcontract 909.docx', 'Progress 903.pptx', 'notes.zip'];
    if (tag === 'pc') for (const f of files) { await p.setInputFiles('[data-file]', path.join(DOCS, f)); await sleep(400); await p.click('[data-in]'); await p.keyboard.press('Enter'); await sleep(1500); }
    await sleep(2500);
    const th = await p.evaluate(() => { const w = [...document.querySelectorAll('#wa .docw')].find(x => /LPO-1042/.test(x.textContent)); const i = w && w.querySelector('.dth.ok img'); return i ? { w: i.naturalWidth, pg: w.querySelector('[data-pgs]').textContent } : null; });
    ck(tag + ': the PDF shows the top of page 1 in the chat, and its pages', th && th.w > 100 && /3 pages/.test(th.pg), th);
    await p.evaluate(() => { const w = [...document.querySelectorAll('#wa .docw')].find(x => /LPO-1042/.test(x.textContent)); w.scrollIntoView(); });
    await p.screenshot({ path: `${OUT}/chat-docs-${tag}.png` });
    const openIt = async name => { await p.evaluate(n => [...document.querySelectorAll('#wa .docw')].reverse().find(x => x.textContent.includes(n)).querySelector('.dn').click(), name); await sleep(2500); };
    await openIt('LPO-1042');
    const pdf = await p.evaluate(() => ({ on: document.getElementById('wa-doc').classList.contains('on'), pages: document.querySelectorAll('#wa-doc .pg').length, drawn: document.querySelectorAll('#wa-doc .pg canvas').length, sub: document.querySelector('#wa-doc [data-sub]').textContent }));
    ck(tag + ': tapping the PDF opens the preview, page by page', pdf.on && pdf.pages === 3 && pdf.drawn >= 1 && /3 pages/.test(pdf.sub), pdf);
    await p.screenshot({ path: `${OUT}/chat-doc-pdf-${tag}.png` });
    await p.click('#wa-doc [data-x]');
    await openIt('BOQ 914');
    const xl = await p.evaluate(() => ({ tabs: [...document.querySelectorAll('#wa-doc .tabs button')].map(b => b.textContent), first: document.querySelector('#wa-doc .sh tr:nth-child(2)') && document.querySelector('#wa-doc .sh tr:nth-child(2)').textContent }));
    ck(tag + ': Excel opens as a table with its sheets', xl.tabs.join() === 'BOQ,Summary' && /Blockwork 200mm - zone 1/.test(xl.first), xl);
    await p.screenshot({ path: `${OUT}/chat-doc-xlsx-${tag}.png` });
    await p.click('#wa-doc .tabs button:nth-child(2)'); await sleep(300);
    ck(tag + ': the Summary sheet', await p.evaluate(() => /195750/.test(document.querySelector('#wa-doc .sh').textContent)));
    await p.keyboard.press('Escape'); await sleep(300);
    ck(tag + ': Escape closes the preview, the chat stays open', await p.evaluate(() => !document.getElementById('wa-doc').classList.contains('on') && document.getElementById('wa').classList.contains('on')));
    await openIt('Subcontract 909');
    const dx = await p.evaluate(() => document.querySelector('#wa-doc .paper') && document.querySelector('#wa-doc .paper').innerHTML);
    ck(tag + ': Word opens as its text (heading, bold, table)', dx && /<h1>Subcontract Agreement/.test(dx) && /<b>Infinia Contracting L.L.C.<\/b>/.test(dx) && /AED 420,000/.test(dx), dx && dx.slice(0, 300));
    await p.screenshot({ path: `${OUT}/chat-doc-docx-${tag}.png` });
    await p.click('#wa-doc [data-x]');
    await openIt('Progress 903');
    ck(tag + ': PowerPoint slide by slide', await p.evaluate(() => /Progress update - 903/.test(document.querySelector('#wa-doc .slide').textContent) && /1 slide/.test(document.querySelector('#wa-doc [data-sub]').textContent)));
    await p.click('#wa-doc [data-x]');
    await openIt('notes.zip');
    ck(tag + ': a zip: no preview, a Download button', await p.evaluate(() => /no preview/.test(document.querySelector('#wa-doc .msg').textContent) && /dl=1/.test(document.querySelector('#wa-doc .msg a').href)));
    await p.click('#wa-doc [data-x]');
    const dl = await p.evaluate(() => { const a = [...document.querySelectorAll('#wa .docw')].find(x => /BOQ 914/.test(x.textContent)).querySelector('a.dl'); return a && /dl=1/.test(a.href) && a.target === '_blank'; });
    ck(tag + ': the round arrow still downloads', dl);
    ck(tag + ': no script errors', !errs.length, errs);
    await ctx.close();
  }
  await b.close(); console.log(bad ? `${bad} FAILED` : 'ALL PASS');
})();
