"""Faster opening (27/11/2026), from the live speed report.

1. deploy/speed_fix.sh: nginx compresses scripts too, keeps files whose address carries their content stamp, and
   uses HTTP/2. Since a stamped file is now kept by the browser for a year, EVERY stamp must match the file it
   points at - this test fails the push if a file changed and the pages were not rebuilt.
2. The download key: every open app asked for a new one every 45 s, also in the background, and each answer was
   stored (235,415 of 251,656 stored answers, 166 MB). Now not stored, and not asked for while the app is hidden.

Run: python3 tests/run_all.py speed_fix
"""
import glob, hashlib, os, re, sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, offline_once
FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok:
        FAIL.append(l)


R = '..'
# ---- 1. every stamp matches its file
files = [f'{R}/app.html', f'{R}/sw.js'] + glob.glob(f'{R}/portal/*.html') + glob.glob(f'{R}/portal/*/*.html') + glob.glob(f'{R}/portal/*.js') + glob.glob(f'{R}/portal/*/*.js')
stale, n = [], 0
for f in files:
    s = open(f, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'(/portal/[A-Za-z0-9_./-]+\.(?:js|css|png|webp|jpg|svg|woff2?|ttf))\?v=([0-9a-f]{10,})(?=[&"\'`\s)])', s):
        t = R + m.group(1)
        if not os.path.exists(t):
            stale.append((f, m.group(1), 'missing')); continue
        d = open(t, 'rb').read(); n += 1
        if not any(getattr(hashlib, h)(d).hexdigest().startswith(m.group(2)) for h in ('sha1', 'sha256', 'md5')):
            stale.append((os.path.basename(f), m.group(1)))
ck(f'every stamped file address matches the file ({n} checked) - if not: python3 deploy/build_temporary_pages.py', n > 50 and not stale, stale[:5])
for f in glob.glob(f'{R}/portal/logo-*.png'):
    pass
logos = set(re.findall(r'/portal/logo-([0-9a-f]{8})\.png', open(f'{R}/app.html', encoding='utf-8').read()))
ck('the logo the app uses is named by its own content', logos and all(hashlib.sha1(open(f'{R}/portal/logo-{h}.png', 'rb').read()).hexdigest().startswith(h) for h in logos), logos)

sh = open(f'{R}/deploy/speed_fix.sh', encoding='utf-8').read()
ck('the script keeps a copy, has nginx check the change, and puts the copy back if refused',
   'cp -a "$SITE" "$SITE.before-speed-$STAMP"' in sh and 'if nginx -t' in sh and 'cp -a "$SITE.before-speed-$STAMP" "$SITE"' in sh)
ck('...reload only (nobody signed out), never a restart', 'systemctl reload nginx' in sh and 'restart' not in sh)
ck('...only stamped addresses are kept; the page and everything else is checked on every open',
   'default                                          "no-cache, must-revalidate";' in sh and '"~^[^?]+\\.(js|css|png|webp|jpg|svg|woff2?|ttf)\\?(.*&)?v=[0-9a-f]{10,}(&|$)"' in sh and 'html' not in sh[sh.index('map $request_uri'):sh.index("echo '}'")])
ck('...a gzip setting already in nginx.conf is not added twice', sh.count("|| echo \"gzip_") == 5)
ck('...it says how to undo it', 'To undo:' in sh)
ck('...it picks live\'s own nginx file, not the test copy with the same name in it', "| grep -v staging | head -1" in sh)
ck('...a stop part-way puts everything back too', "trap 'put_back;" in sh and sh.index('trap ') < sh.index('> "$CONF"'))
_m = open('main.py', encoding='utf-8').read()
ck('the app really clears the kept answers at its start (it never did)', '\n    offline_once.create_tables(engine)' in _m)
ck('a chat sign-off resent is still done once only', '/store/chat/bye' not in offline_once.NOT_KEPT)

# ---- 2. the download key
c = TestClient(main.app, raise_server_exceptions=False)
db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin')); db.commit()
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
db.add(offline_once.OfflineReq(id='old-key', path='/auth/download-token', body='{"token":"x"}'))
db.add(offline_once.OfflineReq(id='a-save', path='/store/petty-cash', body='{}')); db.commit()
offline_once.create_tables(database.engine)
ck('stored key answers are cleared at start; real saves stay', db.get(offline_once.OfflineReq, 'old-key') is None and db.get(offline_once.OfflineReq, 'a-save') is not None)
r1 = c.post('/auth/download-token', headers={**H, 'X-Req-Id': 'k1'})
r2 = c.post('/auth/download-token', headers={**H, 'X-Req-Id': 'k1'})
db.expire_all()
ck('a new key is never stored...', r1.status_code == 200 and db.get(offline_once.OfflineReq, 'k1') is None, r1.text)
ck('...so asking again gives a new working key, not an old one handed back', r2.status_code == 200 and 'X-Replayed' not in r2.headers)
r3 = c.post('/sites', json={'code': 'SPD1', 'active': True}, headers={**H, 'X-Req-Id': 's1'})
db.expire_all()
ck('a real save sent with its id is still stored (sent twice, done once)', db.get(offline_once.OfflineReq, 's1') is not None, r3.status_code)
db.close()
page = open(f'{R}/app-classic.html', encoding='utf-8').read()
ck('the key is not asked for while the app is in the background', 'setTimeout(() => { if (!document.hidden) refreshDownloadToken(); }, 45000);' in page)
ck('...and on coming back a key too old to use is dropped and asked for afresh',
   'if (Date.now() - downloadTokenAt > 50000) cachedDownloadToken = null;' in page)
ck('the built page carries it', 'document.hidden||refreshDownloadToken()},45e3)' in open(f'{R}/app.html', encoding='utf-8').read())
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)
