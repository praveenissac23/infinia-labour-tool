const { chromium } = require('playwright');
const B='http://127.0.0.1:8032', SH='/tmp/claude-0/shots/';
let bad=0; const ck=(n,ok,i)=>{ if(!ok) bad++; console.log(`${ok?'PASS':'FAIL'} ${n}${ok?'':'  '+JSON.stringify(i)}`); };
async function login(b,u,pw){ const ctx=await b.newContext({viewport:{width:1440,height:950}}); const p=await ctx.newPage(); p.on('dialog',d=>d.accept()); const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.errs=errs;
 await p.goto(B+'/?p=accounts'); await p.fill('#login-username',u); await p.fill('#login-password',pw); await p.evaluate('doLogin()'); await p.waitForSelector('#app-screen',{state:'visible'}); await p.waitForTimeout(2500); return p; }
(async()=>{
 const b=await chromium.launch();
 const a=await login(b,'admin','changeme123');
 const sites=await a.evaluate(async()=> (await apiCall('/sites')).map(x=>x.code));
 const S=(c)=>sites.includes(c)?c:sites[5];
 const L=[
  ['site','2026-10-07','received','Cash received','Cash','',5000,false,''],
  ['site','2026-10-07','paid','Foam spray for slab ply wood gap filling','DANI BUILDING',S('912'),84,true,'100234567800003'],
  ['site','2026-10-07','paid','Drinks for labours','REAL MINERAL',S('911'),20,false,''],
  ['site','2026-10-08','paid','Additional work F-801','SALARY',S('912'),50,false,''],
  ['site','2026-10-09','paid','Epoxy mortar (steel fixing)','QAMAR AL',S('910'),346.5,true,''],
  ['site','2026-10-09','paid','Tile cutting disc','QAMAR AL',S('910'),63,true,'100555666700003'],
  ['site','2026-10-12','paid','Paint & silicone','LAND MASTER',S('910'),325,true,'100777888900003'],
  ['office','2026-10-04','paid','Paid to crane bills for Sobha','Zahid Pervaiz','',3100,false,''],
  ['office','2026-10-12','paid','Medical expenses for Sanjay at NMC Hospital','NMC','',1800,false,''],
  ['office','2026-10-12','received','From Jomon Petty Cash for Medical for Labour','CASH','',1000,false,''],
  ['pro','2026-10-02','paid','Advt Permit renewal M 28679','RTA','',1020,false,''],
  ['pro','2026-10-13','paid','Benchep Visa Renewal Exp F 727','MOHRE & GDRFA','',4724.85,false,''],
  ['pro','2026-10-12','paid','To Shafique for Company Cash book','Voucher No : 2354','',1000,false,''],
  ['pro','2026-10-10','received','Petty Cash Collected','Bank Transfer','',15000,false,''],
 ];
 for(const l of L){ const r=await a.evaluate(async l=>{ try{ return await apiCall('/store/petty-cash',{method:'POST',body:JSON.stringify({book:l[0],date:l[1],description:l[3],supplier:l[4],site:l[5],received:l[2]==='received'?l[6]:0,paid:l[2]==='paid'?l[6]:0,vat:l[7],trn:l[8]})}); }catch(e){return {err:String(e.message||e)}} },l); if(r.err) console.log('seed err',r.err,l[3]); }
 // bad TRN refused
 const badTrn=await a.evaluate(async()=>{ try{ await apiCall('/store/petty-cash',{method:'POST',body:JSON.stringify({book:'site',date:'2026-10-10',description:'x',supplier:'y',paid:5,vat:true,trn:'123'})}); return 'saved'; }catch(e){return errText(e)} });
 ck('a TRN that is not 15 digits is refused', /15 digits/.test(badTrn), badTrn);
 // TRN lookup
 const t=await a.evaluate(async()=> (await apiCall('/store/petty-cash/trn?supplier='+encodeURIComponent('Dani Building'))).trn);
 ck('TRN remembered for the supplier', t==='100234567800003', t);
 // petty screen
 await a.evaluate(()=>pgTab('petty')); await a.waitForTimeout(1200); await a.evaluate(()=>pcBook('site')); await a.waitForTimeout(800);
 await a.evaluate(()=>{document.getElementById('pc-from').value='2026-10-01'; document.getElementById('pc-to').value='2026-10-31'; loadPettyCash();}); await a.waitForTimeout(1200);
 ck('no Zoho column on the site book - a small mark beside the amount instead', !(await a.locator('#pc-head-row').textContent()).includes('Zoho') && (await a.locator('#pc-body .pz').count()) > 0);
 ck('waiting lines carry the waiting mark', (await a.locator('#pc-body .pz.wait').count()) > 0);
 await a.fill('#pc-desc','Tile adhesive & grout'); await a.fill('#pc-sup','Dani Building'); await a.fill('#pc-amt','189');
 await a.check('#pc-vat'); await a.waitForTimeout(800);
 ck('VAT ticked shows the TRN box', await a.locator('#pc-trn').isVisible());
 await a.screenshot({path:SH+'z1-petty.png'});
 await a.evaluate(()=>{pcReset(); document.querySelectorAll('.spell-pop,.sp-pop,[class*=spell]').forEach(e=>e.remove());});
 // Send to Zoho
 await a.evaluate(()=>pgTab('zoho')); await a.waitForTimeout(1800);
 ck('Send to Zoho opens', await a.locator('#screen-zoho').isVisible());
 ck('connect card shown while not connected', (await a.locator('#zh-conn').textContent()).includes('Connect Zoho Books'));
 const q=await a.evaluate(()=>ZH);
 const N0=q.rows.length; ck('seeded lines waiting', N0>=14, N0);
 const sug=Object.fromEntries(q.rows.map(r=>[r.description,r.account]));
 console.log(JSON.stringify(sug,null,1));
 ck('VAT bill asks: claim or not', q.rows.find(r=>r.description.startsWith('Epoxy')&&r.vat).flags.includes('Pick VAT: claim or not'));
 ck('RTA advert permit suggested as marketing', /Ads/.test(sug['Advt Permit renewal M 28679']||''), sug['Advt Permit renewal M 28679']);
 ck('PRO to office is a transfer', sug['To Shafique for Company Cash book']==='Transfer to Company Petty Cash');
 await a.screenshot({path:SH+'z2-send.png',fullPage:true});
 // fill TRN for epoxy inline
 const ep=q.rows.find(r=>r.description.startsWith('Epoxy')&&r.vat).id;
 await a.evaluate(id=>zhSet(id,'vat_claim','claim'),ep);
 ck('Claim 5% without TRN asks for the TRN', (await a.evaluate(id=>zhFlags(ZH.rows.find(r=>r.id===id)),ep)).includes('VAT claimed without TRN'));
 ck('VAT box is on the row', await a.locator('#zh-body select.zh-vat').count() > 0);
 await a.evaluate(id=>zhSet(id,'trn','100555666700003'),ep);
 ck('with TRN the VAT line is ready', (await a.evaluate(id=>zhFlags(ZH.rows.find(r=>r.id===id)),ep)).length === 0);
 // split: open the dialog on a bill, two parts that must add up
 const dr=q.rows.find(r=>r.description.startsWith('Drinks')).id;
 await a.evaluate(id=>zhSplit(id),dr); await a.waitForTimeout(300);
 ck('split dialog opens with two parts', await a.locator('.zs-row').count() === 2);
 await a.screenshot({path:SH+'z-split.png'});
 await a.evaluate(id=>{ const r=ZH.rows.find(x=>x.id===id); ZH_PICK[id].splits=[{account:'Office › Office Pantry Expenses',amount:r.amount-5},{account:'Office › Staff Meals and Benefits',amount:3}]; },dr);
 await a.click('#zs-ok'); await a.waitForTimeout(200);
 ck('split not adding up is flagged', (await a.evaluate(id=>zhFlags(ZH.rows.find(r=>r.id===id)),dr)).some(f=>/add up/.test(f)));
 await a.evaluate(id=>{ const r=ZH.rows.find(x=>x.id===id); ZH_PICK[id].splits[1].amount=5; zhSet(id,'splits',ZH_PICK[id].splits); },dr);
 ck('split adding up is ready', (await a.evaluate(id=>zhFlags(ZH.rows.find(r=>r.id===id)),dr)).length === 0);
 ck("row shows the split", /Split over 2 cost heads/.test(await a.locator("#zh-body").textContent()));
 // crane: pick a project account without project -> flag
 const cr=q.rows.find(r=>r.description.startsWith('Paid to crane')).id;
 await a.evaluate(id=>zhSet(id,'account','01. Preliminaries Including Mobilization'),cr);
 ck('project head without project asks for one', (await a.evaluate(id=>zhFlags(ZH.rows.find(r=>r.id===id)),cr)).includes('Pick project'));
 await a.evaluate(id=>zhSet(id,'site',ZH_SITES[3]),cr);
 const n=await a.evaluate(()=>zhShown().filter(r=>ZH_PICK[r.id].on).length);
 await a.click('#zh-go'); await a.waitForTimeout(1500);
 const after=await a.evaluate(()=>ZH.rows.length);
 ck(`approved ${n}, rest still waiting`, after===N0-n, {n,after,N0});
 await a.screenshot({path:SH+'z3-after.png',fullPage:true});
 // store keeper sees lock
 const k=await login(b,'amal','pass12345');
 await k.evaluate(()=>pgTab('petty')); await k.waitForTimeout(1200); await k.evaluate(()=>{document.getElementById('pc-from').value='2026-10-01'; document.getElementById('pc-to').value='2026-10-31'; loadPettyCash();}); await k.waitForTimeout(1500);
 const body=await k.locator('#pc-body').textContent();
 ck('store keeper does not see the Zoho column', !(await k.locator('#pc-head-row').textContent()).includes('Zoho') && !body.includes('Approved'), body.slice(0,200));
 ck('store keeper sees approved lines locked', body.includes('Locked - checked by accounts'));
 const lockedId=await k.evaluate(()=>PC.rows.find(r=>r.zoho==='approved').id);
 const e403=await k.evaluate(async id=>{ try{ await apiCall('/store/petty-cash/'+id,{method:'DELETE'}); return 'deleted'; }catch(e){return errText(e)} },lockedId);
 ck('store keeper cannot remove an approved line', /chief accountant/.test(e403), e403);
 const zq=await k.evaluate(async()=>{ try{ await apiCall('/store/zoho/queue'); return 'open'; }catch(e){return 'refused'} });
 ck('store keeper cannot open Send to Zoho', zq==='refused');
 await k.screenshot({path:SH+'z4-keeper.png'});
 // chief accountant (shafiq) has it
 const c=await login(b,'shafiq','pass12345');
 const cq=await c.evaluate(async()=>{ try{ return (await apiCall('/store/zoho/queue')).rows.length; }catch(e){return 'refused '+e.message} });
 ck('chief accountant opens Send to Zoho', typeof cq==='number', cq);
 ck('Send to Zoho tab in his Accounts', await c.evaluate(()=>pgHas('accounts_zoho')));
 // Naveen's book shows the Zoho column to the admin
 await a.evaluate(()=>pgTab('petty')); await a.waitForTimeout(800); await a.evaluate(()=>pcBook('naveen')); await a.waitForTimeout(1200);
 const nv=await a.evaluate(()=>({rows:PC.rows.filter(r=>r.date>=PC.zoho_start).length, marks:document.querySelectorAll('#pc-body .pz').length}));
 ck('Zoho marks on the Naveen book for the chief accountant / admin (one per line from the start date)', nv.marks>=nv.rows, nv);
 // export
 const ex=await a.evaluate(async()=>{ await refreshDownloadToken(); const out={}; for(const f of ['view','pdf','excel']){ const r=await fetch(`${API}/export/accounts/zoho?format=${f}&token=${encodeURIComponent(cachedDownloadToken)}`); out[f]=[r.status,(await r.arrayBuffer()).byteLength]; } return out; });
 ck('preview / PDF / Excel download', Object.values(ex).every(v=>v[0]===200&&v[1]>1500), ex);
 ck('no page errors', !a.errs.length && !k.errs.length && !c.errs.length, [a.errs,k.errs,c.errs]);
 await b.close(); console.log(bad?`${bad} FAILED`:'ALL PASS');
})();
