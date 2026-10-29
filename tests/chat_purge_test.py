"""Chat is kept for a day and then deleted from everywhere (29 Oct 2026): the message, its file, its line in the
Activity Monitor - and it is never in a backup (older backups have it taken out).
    cd app && DATABASE_URL=sqlite:////tmp/cp.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/chat_purge_test.py   (empty db)"""
import sys, os, json
sys.path.insert(0, '.')
from datetime import timedelta, timezone
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, chat

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.User(username='amal', hashed_password=auth.hash_password('p'), full_name='Amal', role='office', permissions='store'))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, A = tok('admin'), tok('amal')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:300]}]'))
    if not ok: FAIL.append(l)

old = c.post('/store/chat/send', json={'room': 'all', 'text': 'yesterday: old news'}, headers=A).json()
f = c.post('/store/chat/upload', data={'room': 'all'}, files={'file': ('plan.pdf', b'%PDF-1.4 ' + b'0' * 300, 'application/pdf')}, headers=A).json()
new = c.post('/store/chat/send', json={'room': 'all', 'text': 'today: fresh news'}, headers=A).json()
# an old backup taken while the chat was in backups (as before this change)
db = database.SessionLocal()
d = main.build_backup_data(db)
d['chat_messages'] = [{'id': 1, 'text': 'yesterday: old news'}]; d['tables'] = list(d['tables']) + ['chat_messages']
db.add(models.Backup(trigger='manual', data=main._backup_dump(d))); db.commit()
fpath = db.query(chat.ChatMessage).filter(chat.ChatMessage.id == f['id']).first().file_path
# 25 hours pass for the first two
for mid in (old['id'], f['id']):
    m = db.query(chat.ChatMessage).filter(chat.ChatMessage.id == mid).first(); m.created_at = chat._now() - timedelta(hours=25)
for l in db.query(models.AuditLog).filter(models.AuditLog.action.like('chat%')).all():
    if 'old news' in l.details or 'plan.pdf' in l.details:
        l.created_at = (chat._now() - timedelta(hours=25)).replace(tzinfo=timezone.utc)
db.commit()
a, b = chat.purge_old(db); db.close()
ck('the day-old message and file are deleted', a == 2, (a, b))
ck('and their lines in the Activity Monitor', b == 2, (a, b))
st = c.get('/store/chat/state?room=all', headers=H).json()
texts = [m['text'] for m in st['messages']]
ck('the chat shows only today', texts == ['today: fresh news'], texts)
ck('the file is gone from the disk', not os.path.exists(os.path.join(chat._dir(), fpath)))
log = [r['details'] for r in c.get('/audit-log?group=chat', headers=H).json()['rows']]
ck('the Activity Monitor keeps only today', log == ['Everyone: today: fresh news'], log)
# backups
r = c.post('/backup/create', headers=H).json()
db = database.SessionLocal()
txt = main._backup_text(db.query(models.Backup).filter(models.Backup.id == r['id']).first().data)
ck('a new backup holds no chat', 'fresh news' not in txt and '"chat_messages"' not in txt and '"chat_seen"' not in txt, txt[:200])
db.close()
n = main.scrub_chat_from_backups(database.SessionLocal)
ck('the older backup has the chat taken out', n == 1, n)
db = database.SessionLocal()
alltxt = ''.join(main._backup_text(x.data) for x in db.query(models.Backup).all())
ck('no backup holds a chat word', 'old news' not in alltxt and 'fresh news' not in alltxt and '"chat_messages"' not in alltxt)
ck('the other tables are still in it', '"users"' in alltxt and '"audit_log"' in alltxt)
db.close()
ck('a second run has nothing to do', main.scrub_chat_from_backups(database.SessionLocal) == 0)
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')
