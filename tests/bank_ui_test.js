// Accounts > Bank: enter ADCB payments and receipts; chief accountant only.
const { chromium } = require('playwright');
const B='http://127.0.0.1:8032', SH='/tmp/claude-0/shots/';
let bad=0; const ck=(n,ok,i)=>{ if(!ok) bad++; console.log(`${ok?'PASS':'FAIL'} ${n}${ok?'':'  '+JSON.stringify(i)}`); };
async function login(b,u,pw){ const ctx=await b.newContext({viewport:{width:1440,height:950}}); const p=await ctx.newPage(); p.errs=[]; p.on('pageerror',e=>p.errs.push(e.message));
 await p.goto(B+'/?p=accounts'); await p.fill('#login-username',u); await p.fill('#login-password',pw); await p.evaluate('doLogin()'); await p.waitForSelector('#app-screen',{state:'visible'}); await p.waitForTimeout(2500); return p; }
(async()=>{
 const b=await chromium.launch();
 const c=await login(b,'shafiq','pass12345');
 ck('chief accountant has Bank', await c.evaluate(()=>pgHas('accounts_bank')));
 await c.goto(B+'/?p=accounts'); await c.waitForTimeout(2500);
 const tabs=await c.evaluate(()=>[...document.querySelectorAll('.pg-tab')].map(x=>x.textContent.trim()));
 ck('Bank and Send to Zoho tabs show for him', tabs.includes('Bank') && tabs.includes('Send to Zoho'), tabs);
 await c.evaluate(()=>pgTab('bank')); await c.waitForTimeout(1800);
 ck('Bank opens', await c.locator('#screen-bank').isVisible());
 await c.evaluate(()=>{document.getElementById('bk-month').value='2026-10'; bkLoad();}); await c.waitForTimeout(1200);
 const add=async(kind,f)=>{ await c.evaluate(k=>bkKind(k),kind); await c.waitForTimeout(200);
   for(const [id,v] of Object.entries(f)){ if(id==='bk-acc'){ await c.evaluate(v=>bkAccSet(v),v); } else if(id==='bk-mode'||id==='bk-site'||id==='bk-to'){ await c.selectOption('#'+id,v); await c.evaluate(()=>bkMode()); } else await c.fill('#'+id,String(v)); }
   await c.click('#bk-save'); await c.waitForTimeout(1200); return (await c.locator('#bk-status').textContent()); };
 let m=await add('vendor',{'bk-date':'2026-10-10','bk-party':'Al Raida Electromechanical Services','bk-ref':'PHUB732241116','bk-amt':'83535.22','bk-notes':'908PC08'});
 ck('supplier payment saved', /Saved/.test(m), m);
 m=await add('vendor',{'bk-mode':'Cheque','bk-date':'2026-10-19','bk-party':'SEOMAA Building Materials Trading','bk-amt':'48596.10'});
 ck('cheque without a number refused', /cheque number/i.test(m), m);
 await c.fill('#bk-ref','000156'); await c.click('#bk-save'); await c.waitForTimeout(1200);
 m=await add('customer',{'bk-date':'2026-10-12','bk-party':'Emkaan Design LLC','bk-ref':'PHUB732906914','bk-amt':'83244.65'});
 m=await add('expense',{'bk-date':'2026-10-09','bk-party':'Cadmin Property Valuation','bk-ref':'PHUB731759745','bk-amt':'3150','bk-acc':'01. Preliminaries Including Mobilization','bk-site':(await c.evaluate(()=>BK_SITES[3]))});
 m=await add('charge',{'bk-date':'2026-10-06','bk-ref':'TT CHARGES','bk-amt':'26.25'});
 m=await add('transfer',{'bk-date':'2026-10-10','bk-ref':'PHUB732297071','bk-amt':'15000','bk-to':'Jomon Petty Cash'});
 const d=await c.evaluate(()=>BK);
 ck('6 lines, paid out and received add up', d.rows.length===6 && Math.abs(d.paid-(83535.22+48596.10+3150+26.25+15000))<0.01 && d.received===83244.65, [d.rows.length,d.paid,d.received]);
 ck('all waiting while Zoho is not connected', d.waiting===6);
 ck('cheque keeps its date and number', d.rows.some(r=>r.mode==='Cheque'&&r.reference==='000156'&&r.date==='2026-10-19'));
 await c.screenshot({path:SH+'bk1.png',fullPage:true});
 const ex=await c.evaluate(async()=>{ await refreshDownloadToken(); const o={}; for(const f of ['view','pdf','excel']){ const r=await fetch(`${API}/export/accounts/bank?format=${f}&month=2026-10&token=${encodeURIComponent(cachedDownloadToken)}`); o[f]=[r.status,(await r.arrayBuffer()).byteLength]; } return o; });
 ck('preview / PDF / Excel', Object.values(ex).every(v=>v[0]===200&&v[1]>1500), ex);
 const k=await login(b,'amal','pass12345');
 const kq=await k.evaluate(async()=>{ try{ await apiCall('/store/bank'); return 'open'; }catch(e){ return 'refused'; } });
 ck('store keeper cannot open Bank', kq==='refused');
 ck('no page errors', !c.errs.length && !k.errs.length, [c.errs,k.errs]);
 await b.close(); console.log(bad?`${bad} FAILED`:'ALL PASS');
})();
