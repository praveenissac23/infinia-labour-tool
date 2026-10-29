"""The Activity Monitor shows the chat (29 Oct 2026): every message - Everyone and private - photos, files and
voice messages by name, edits (before and after) and deletes (what it said), under a "Chat" filter.
    cd app && DATABASE_URL=sqlite:////tmp/ca.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/chat_activity_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, chat

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.User(username='amal', hashed_password=auth.hash_password('p'), full_name='Amal', role='office', permissions='store'))
db.commit(); ids = {u.username: u.id for u in db.query(models.User).all()}; db.close()
c = TestClient(main.app, raise_server_exceptions=False)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, A = tok('admin'), tok('amal')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:300]}]'))
    if not ok: FAIL.append(l)

dm = f"dm:{min(ids.values())}-{max(ids.values())}"
m1 = c.post('/store/chat/send', json={'room': 'all', 'text': 'Cement arrives at 903 tomorrow'}, headers=A).json()
m2 = c.post('/store/chat/send', json={'room': dm, 'text': 'Please approve my request'}, headers=A).json()
c.post('/store/chat/upload', data={'room': dm, 'text': 'the crack'}, files={'file': ('wall.jpg', b'\xff\xd8\xff' + b'0' * 300, 'image/jpeg')}, headers=A)
c.post('/store/chat/upload', data={'room': 'all', 'kind': 'voice', 'duration': '12'}, files={'file': ('v.webm', b'0' * 500, 'audio/webm')}, headers=A)
c.put(f"/store/chat/messages/{m1['id']}", json={'text': 'Cement arrives at 903 on Saturday'}, headers=A)
c.delete(f"/store/chat/messages/{m2['id']}", headers=A)

log = c.get('/audit-log?group=chat', headers=H).json()
rows = [(r['label'], r['full_name'], r['details']) for r in log['rows']]
txt = '\n'.join(' | '.join(r) for r in rows); print(txt)
ck('there is a Chat filter', any(g['key'] == 'chat' and g['label'] == 'Chat' for g in log['groups']))
ck('an Everyone message, with what it said', ('Chat message', 'Amal', 'Everyone: Cement arrives at 903 tomorrow') in rows)
ck('a private message, and to whom', ('Chat message', 'Amal', 'Private to Administrator: Please approve my request') in rows)
ck('a photo by name with its caption', ('Chat photo / file', 'Amal', 'Private to Administrator: photo wall.jpg - the crack') in rows)
ck('a voice message and its length', ('Chat voice message', 'Amal', 'Everyone: voice message 0:12') in rows)
ck('an edit, before and after', ('Chat message edited', 'Amal', 'Everyone: "Cement arrives at 903 tomorrow" changed to "Cement arrives at 903 on Saturday"') in rows)
ck('a delete keeps what it said', ('Chat message deleted', 'Amal', 'Private to Administrator: Please approve my request') in rows)
ck('the search finds chat words', any('Saturday' in r['details'] for r in c.get('/audit-log?q=Saturday', headers=H).json()['rows']))
ck('Amal cannot open the Activity Monitor', c.get('/audit-log', headers=A).status_code == 403)
# messages sent before this was logged are put in once
db = database.SessionLocal()
db.query(models.AuditLog).filter(models.AuditLog.action.like('chat%')).delete(synchronize_session=False); db.commit(); db.close()
chat.backfill_audit(database.SessionLocal); chat.backfill_audit(database.SessionLocal)
back = [r['details'] for r in c.get('/audit-log?group=chat', headers=H).json()['rows']]
ck('earlier messages are filled in once (deleted ones are not)', sorted(back) == sorted(['Everyone: Cement arrives at 903 on Saturday', 'Private to Administrator: photo wall.jpg - the crack', 'Everyone: voice message 0:12']), back)
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')
