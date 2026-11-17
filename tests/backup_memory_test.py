"""Server down 15-30 min many times a day (14/11/2026): on every start the app loaded EVERY backup at once to take
chat out of them - 7.5 GB, killed, restarted, again. Now once, one backup at a time; the daily-backup check and the
pruning never load a snapshot.
    cd app && DATABASE_URL=sqlite:////tmp/bm.db INFINIA_NO_SCHED=1 python3 ../tests/backup_memory_test.py  (empty db)"""
import json, sys
sys.path.insert(0, '.')
import database, models
models.Base.metadata.create_all(database.engine)
import main
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:300]}]'))
    if not ok: FAIL.append(l)

db = database.SessionLocal()
db.query(models.Setting).filter(models.Setting.key == 'chat_scrubbed_from_backups').delete()
for i in range(5):
    d = {'tables': ['employees', 'chat_messages'], 'employees': [{'n': i}], 'chat_messages': [{'t': 'hi'}],
         'audit_log': [{'action': 'chat_send'}, {'action': 'login'}]}
    db.add(models.Backup(trigger='auto', data=main._backup_dump(d) if i % 2 else json.dumps(d)))
db.add(models.Backup(trigger='manual', data=json.dumps({'tables': ['employees'], 'employees': []})))
db.commit(); db.close()

loads = []
orig = main._backup_text
def spy(stored):
    loads.append(1); return orig(stored)
main._backup_text = spy
n = main.scrub_chat_from_backups(database.SessionLocal)
ck('chat taken out of the 5 backups that had it', n == 5, n)
db = database.SessionLocal()
left = [main._backup_json(b) for b in db.query(models.Backup).all()]
ck('no chat left in any backup; the rest kept', all('chat_messages' not in x and all(not str(r.get('action', '')).startswith('chat_') for r in x.get('audit_log', [])) for x in left)
   and sum(1 for x in left if x.get('employees')) == 5, left[:2])
db.close()
loads.clear()
ck('second start: does nothing - no backup opened', main.scrub_chat_from_backups(database.SessionLocal) == 0 and not loads, len(loads))

# the daily check and the pruning ask only for ids
import sqlalchemy
seen = []
@sqlalchemy.event.listens_for(database.engine, 'before_cursor_execute')
def _q(conn, cursor, statement, *a):
    if 'backups' in statement and statement.lstrip().upper().startswith('SELECT'):
        seen.append(statement)
db = database.SessionLocal()
main._todays_routine_backup(db)
main.AUTO_BACKUP_KEEP_DAYS, keep = 2, main.AUTO_BACKUP_KEEP_DAYS
try:
    main.maybe_create_auto_backup(db)
finally:
    main.AUTO_BACKUP_KEEP_DAYS = keep
ck('the daily check and the pruning never read the snapshots', seen and not any('backups.data' in q for q in seen), [q[:120] for q in seen])
ck('pruning kept the newest 2 routine backups and the manual one', db.query(models.Backup).filter(models.Backup.trigger.in_(main.ROUTINE_TRIGGERS)).count() == 2
   and db.query(models.Backup).filter(models.Backup.trigger == 'manual').count() == 1)
db.close()
# Settings > Backups: the list and a delete read only the small columns (17/11/2026: the list read every copy and
# the app was stopped at its memory cap)
db = database.SessionLocal()
u = db.query(models.User).first()
if u is None:
    u = models.User(username='admin1', full_name='Admin', role='admin', hashed_password='x'); db.add(u); db.commit()
seen.clear()
lst = main.list_backups(db=db, user=u)
ck('backup list never reads the snapshots', seen and not any('backups.data' in q for q in seen), [q[:160] for q in seen])
ck('backup list still shows id, date, kind, by', lst and all(set(r) == {'id', 'created_at', 'trigger', 'created_by'} for r in lst), lst[:2])
gone = lst[-1]['id']
seen.clear()
r = main.delete_backup(gone, db=db, user=u)
ck('deleting a backup never reads the snapshot', not any('backups.data' in q for q in seen), [q[:160] for q in seen])
ck('the backup is gone', r.get('deleted') == gone and db.query(models.Backup.id).filter(models.Backup.id == gone).first() is None)
try:
    main.delete_backup(999999, db=db, user=u); ck('missing backup -> 404', False)
except main.HTTPException as e:
    ck('missing backup -> 404', e.status_code == 404)
db.close()
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED'))
sys.exit(1 if FAIL else 0)
