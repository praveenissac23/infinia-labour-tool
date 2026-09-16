from playwright.sync_api import sync_playwright
import time, json, sys
PROBLEMS=[]
SKIP_TEXT=('sign out','delete','remove','cancel','clear','fresh start','restore','reset','give out','save','apply','generate','import','upload','run check','mark all read','untick','tick all','later','close','tick','add','create','update','send','confirm','submit')
def audit(who):
    with sync_playwright() as p:
        b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1500,'height':1000}, accept_downloads=True)
        pg=ctx.new_page(); errs=[]; bad=[]
        pg.on('pageerror', lambda e: errs.append(str(e)[:140]))
        pg.on('response', lambda r: bad.append((r.request.method, r.url.split('8033')[-1][:70], r.status)) if r.status>=400 and '8033' in r.url and '/auth/login' not in r.url else None)
        ctx.on('page', lambda np: np.close())
        pg.goto('http://127.0.0.1:8032/app.html')
        pg.fill('#login-username',who); pg.fill('#login-password','p'); pg.evaluate('doLogin()')
        pg.wait_for_selector('#app-screen', state='visible', timeout=15000); time.sleep(2)
        screens=pg.evaluate("[...document.querySelectorAll('.nav-item')].filter(n=>n.offsetParent).map(n=>n.getAttribute('data-target')||n.getAttribute('data-screen'))")
        clicked=0
        for s in screens:
            if not s: continue
            e0=len(errs); b0=len(bad)
            pg.evaluate(f"switchScreen('{s}')"); time.sleep(1.6)
            # sub-panels on the store screen
            if s=='store':
                for panel in ('home','give','arrive','other','reports','items'):
                    try: pg.evaluate(f"storeGo('{panel}')"); time.sleep(1.2)
                    except Exception as ex: PROBLEMS.append((who,s,f'storeGo({panel})',str(ex)[:80]))
                pg.evaluate("storeGo('home')"); time.sleep(0.6)
            # press every visible non-destructive button on this screen
            btns=pg.evaluate(f'''[...document.querySelectorAll('#screen-{s} button, #screen-{s} .rep-tile, #screen-{s} .store-tile, #screen-{s} .dash-tile')]
                .filter(b=>b.offsetParent!==null && !b.disabled).map((b,i)=>({{i, t:(b.textContent||'').trim().slice(0,40)}}))''')
            for bt in btns:
                t=bt['t'].lower()
                if any(k in t for k in SKIP_TEXT): continue
                e1=len(errs); b1=len(bad)
                try:
                    pg.evaluate(f'''(()=>{{const els=[...document.querySelectorAll('#screen-{s} button, #screen-{s} .rep-tile, #screen-{s} .store-tile, #screen-{s} .dash-tile')].filter(b=>b.offsetParent!==null && !b.disabled); const el=els[{bt['i']}]; if(el) el.click();}})()''')
                    time.sleep(0.7); clicked+=1
                except Exception as ex:
                    PROBLEMS.append((who,s,bt['t'],'click threw: '+str(ex)[:60]))
                for e in errs[e1:]: PROBLEMS.append((who,s,bt['t'],'JS: '+e))
                for x in bad[b1:]: PROBLEMS.append((who,s,bt['t'],f'HTTP {x[2]} {x[0]} {x[1]}'))
                # come back to the screen in case the button navigated
                pg.evaluate(f"switchScreen('{s}')"); time.sleep(0.3)
            for e in errs[e0:]:
                if not any(pr[3]=='JS: '+e for pr in PROBLEMS): PROBLEMS.append((who,s,'(opening screen)','JS: '+e))
            for x in bad[b0:]:
                if not any(pr[3].endswith(x[1]) for pr in PROBLEMS): PROBLEMS.append((who,s,'(opening screen)',f'HTTP {x[2]} {x[0]} {x[1]}'))
        print(f'{who:7} screens: {len(screens):2}  buttons pressed: {clicked:3}  js errors: {len(errs):2}  bad http: {len(bad):2}')
        ctx.close(); b.close()
for who in ('admin','office','amal'):
    audit(who)
print()
seen=set()
for pr in PROBLEMS:
    key=(pr[0],pr[1],pr[3])
    if key in seen: continue
    seen.add(key)
    print(f'  [{pr[0]}] {pr[1]:12} {pr[2][:28]:28} -> {pr[3]}')
print()
print('PROBLEMS FOUND:', len(seen))
