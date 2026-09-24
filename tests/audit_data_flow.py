from playwright.sync_api import sync_playwright
import time
R=[]
def ck(l,c,x=''):
    R.append((l,c)); print(('PASS ' if c else 'FAIL ')+l+('' if c else f'  [{str(x)[:70]}]'))
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1500,'height':1000}, accept_downloads=True)
    pg=ctx.new_page(); errs=[]; pg.on('pageerror', lambda e: errs.append(str(e)[:120]))
    ctx.on('page', lambda np: np.close())
    pg.goto('http://127.0.0.1:8032/app.html')
    pg.fill('#login-username','admin'); pg.fill('#login-password','p'); pg.evaluate('doLogin()')
    pg.wait_for_selector('#app-screen', state='visible', timeout=15000); time.sleep(2)

    pg.evaluate("switchScreen('followup')"); time.sleep(2.5)
    ck('follow-up offers It arrived for the ordered request', pg.evaluate("[...document.querySelectorAll('#screen-followup button')].some(b=>b.textContent.includes('It arrived'))"),
       pg.evaluate("[...document.querySelectorAll('#screen-followup button')].map(b=>b.textContent.trim())"))
    pg.evaluate('''(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('It arrived')); if(b) b.click();})()'''); time.sleep(1.5)
    # The supplier dropdown is the visible control; the free-text box
    # beside it stays hidden until "another supplier" is chosen, so
    # checking that one said the form was shut when it was open.
    ck('delivery form opens', pg.evaluate("document.getElementById('recv-supplier-pick').offsetParent!==null"))
    ck('delivery defaults to the requesting site', pg.evaluate("document.getElementById('recv-where').value")=='901', pg.evaluate("document.getElementById('recv-where').value"))
    pg.fill('#recv-ref-no','DO-9')
    pg.evaluate('''document.querySelector('#recv-lines input[type=number]').value=100;''')
    pg.evaluate('saveReceive()'); time.sleep(2.5)
    # Cement is a consumable, so it is not carried as stock standing at
    # 901 - it shows as what was last sent there. What must be true is
    # that it went to the site and never into the central store.
    st=pg.evaluate('''(async()=>{const r=await apiCall('/store/report?kind=stock');
        const c=r.rows.find(x=>x.name.includes('Cement'));
        const a=await apiCall('/store/at-site?site=901');
        return {in_store:c.in_store, at_sites:c.at_sites,
                sent:(a.recent||[]).find(x=>x.name.includes('Cement'))||null};})()''')
    ck('the delivery booked to site 901, not the store',
       st['in_store']==0 and st['sent'] and st['sent']['qty']==100, st)
    ck('and the cement is not left standing at the site', st['at_sites']==0, st)
    pg.evaluate("switchScreen('followup')"); time.sleep(2)
    ck('nothing left to chase afterwards', 'It arrived' not in pg.inner_text('#screen-followup'))

    pg.evaluate("switchScreen('lporegister')"); time.sleep(2)
    pg.fill('#price-q','cem'); time.sleep(1.5)
    ck('price search finds cement', pg.evaluate("document.querySelectorAll('.price-card').length")>=1)
    ck('register lists the orders', pg.evaluate("document.querySelectorAll('#lpr-body tr').length")>=1)

    pg.evaluate("switchScreen('suppliers')"); time.sleep(1.5)
    # Every box on the supplier card is required - a trader half on file
    # is the one nobody can pay, so the form fills all of it.
    for f,v in (('#sup-name','New Trader LLC'),('#sup-contact','Sam'),
                ('#sup-phone','0501112222'),('#sup-trn','100111222333003'),
                ('#sup-email','sam@newtrader.ae'),('#sup-terms','30 days')): pg.fill(f,v)
    pg.evaluate('saveSupplier()'); time.sleep(1.5)
    ck('supplier saves', 'saved' in pg.inner_text('#sup-status').lower(), pg.inner_text('#sup-status')[:50])

    pg.evaluate("switchScreen('settings')"); time.sleep(1.5)
    pg.fill('#new-user-username','febiyan'); pg.fill('#new-user-password','secret123')
    pg.evaluate('createUser()'); time.sleep(1.5)
    ck('a login is created', 'created' in pg.inner_text('#settings-status').lower(), pg.inner_text('#settings-status')[:50])

    pg.evaluate("switchScreen('attendance')"); time.sleep(2)
    pg.evaluate('''document.querySelectorAll('.row-pick').forEach(c=>c.checked=true); const s=document.getElementById('bulk-status'); if(s) s.value='Present';''')
    pg.evaluate('applyBulk()'); time.sleep(0.6); pg.evaluate('saveAttendance()'); time.sleep(2.5)
    ck('attendance saves', any(k in pg.inner_text('#att-status').lower() for k in ('saved','no change')), pg.inner_text('#att-status')[:60])

    pg.evaluate("switchScreen('combine')"); time.sleep(2.5)
    pg.evaluate('''document.querySelector('#adj-worker-body tr').click()'''); time.sleep(1)
    pg.fill('#adj-desc','Parking fine'); pg.fill('#adj-amount','170'); pg.evaluate('addAdjustmentRow()'); time.sleep(2)
    ck('adjustment added in Salary Cards', 'Parking fine' in pg.inner_text('#adj-list'))

    pg.evaluate("switchScreen('livecard')"); time.sleep(2)
    pg.evaluate('''document.querySelector('#livecard-worker-body tr').click()'''); time.sleep(2)
    ck('live card renders a final salary', 'FINAL SALARY' in pg.inner_text('#livecard-detail').upper())
    pg.evaluate("switchScreen('errorcheck')"); time.sleep(2.5)
    ck('check before you pay runs', pg.evaluate("document.querySelectorAll('#errcheck-body tr').length")>0)

    # The 100 bags above went to site 901, because a delivery books to
    # the site that asked for it. So the central store is put in funds
    # first, otherwise this only re-tests the over-issue guard.
    pg.evaluate('''(async()=>{const it=(await apiCall('/store/items')).find(i=>i.name.includes('Cement'));
        await apiCall('/store/movements',{method:'POST',body:JSON.stringify({item_id:it.id,kind:'in',
        qty:200,location:'',supplier:'Al Raha Trading LLC',notes:'',moved_on:'2026-09-16'})});})()'''); time.sleep(2)
    pg.evaluate("switchScreen('store')"); time.sleep(1); pg.evaluate("storeGo('give')"); time.sleep(1.5)
    pg.evaluate('''(()=>{document.getElementById('out-from').value=''; document.getElementById('out-site').value='904'; onMoveEnds();})()'''); time.sleep(1.5)
    pg.fill('#out-person','D-01 - MOHAMED SALIM'); pg.fill('#out-lines .ol-item-txt','Cement OPC 50kg'); time.sleep(0.8)
    pg.fill('#out-lines .ol-qty','30'); pg.evaluate('saveIssue()'); time.sleep(2.2)
    ck('material moves store to site', '30 bag' in pg.inner_text('#store-status'), pg.inner_text('#store-status')[:70])
    ck('both preview panels drawn', pg.evaluate("document.querySelectorAll('.hold-side').length")==2)

    print(); print('JS errors:', errs if errs else 'none')
    ctx.close(); b.close()
print('PASSED', sum(1 for _,c in R if c), 'of', len(R))
