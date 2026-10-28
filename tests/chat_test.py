"""In-app chat: online list, Everyone, private chats, @mentions to the bell, read marks, edit / delete.
    cd app && DATABASE_URL=sqlite:////tmp/ch.db python3 ../tests/chat_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, chat

db = database.SessionLocal()
for u, n in (('admin', 'Praveen Isaac'), ('amal', 'Amal Store'), ('shafiq', 'Shafeeq S'), ('gone', 'Old Login')):
    db.add(models.User(username=u, hashed_password=auth.hash_password('p'), full_name=n, role='admin' if u == 'admin' else 'office',
                       permissions='store', active=u != 'gone'))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
P, A, S = tok('admin'), tok('amal'), tok('shafiq')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:220]}]'))
    if not ok: FAIL.append(l)

st = c.get('/store/chat/state', headers=P).json()
ids = {u['username']: u['id'] for u in st['users']}
ck('everyone active is listed, the old login is not', set(ids) == {'admin', 'amal', 'shafiq'}, ids)
ck('only those who have the app open are online', [u['username'] for u in st['users'] if u['online']] == ['admin'], st['users'])
c.get('/store/chat/state', headers=A)
st = c.get('/store/chat/state', headers=P).json()
ck('Amal opens the app: now online', {u['username']: u['online'] for u in st['users']}['amal'], st['users'])

m = c.post('/store/chat/send', json={'room': 'all', 'text': 'Good morning @amal, cement for 903 today? @everyone check the new LPO rule'}, headers=P)
ck('Praveen writes in Everyone', m.status_code == 200, m.text)
m = m.json()
ck('the @ tags are picked up (Amal, and everyone)', m['mentions'] == [ids['amal']] and m['everyone'], m)
sa = c.get('/store/chat/state', headers=A).json()
ck('Amal has 1 unread in Everyone, and it names him', sa['unread'].get('all') == 1 and sa['mentions'] == 1, sa)
bell = c.get('/notifications', headers=A).json()['notifications']
ck('and it is in his bell', any(n['kind'] == 'chat' and n['target'] == 'all' for n in bell), [n['title'] for n in bell][:5])
room = chat.dm_room(ids['admin'], ids['amal'])
c.post('/store/chat/send', json={'room': room, 'text': 'Call me about 909'}, headers=P)
c.post('/store/chat/send', json={'room': room, 'text': 'Urgent'}, headers=P)
bell = c.get('/notifications', headers=A).json()['notifications']
ck('a private message: "sent you 2 messages" in his bell', any(n['kind'] == 'chat' and '2 messages' in n['title'] for n in bell), [n['title'] for n in bell][:5])
ck('Shafeeq cannot read their private chat', c.get(f'/store/chat/state?room={room}', headers=S).status_code == 403)
ck('nor write in it', c.post('/store/chat/send', json={'room': room, 'text': 'hi'}, headers=S).status_code == 403)
ck('Shafeeq sees nothing unread from it', not c.get('/store/chat/state', headers=S).json()['unread'].get(room))
r = c.get(f'/store/chat/state?room={room}', headers=A).json()
ck('Amal opens the chat: both messages', [x['text'] for x in r['messages']] == ['Call me about 909', 'Urgent'], r['messages'])
c.post('/store/chat/read', json={'room': room, 'last_id': r['messages'][-1]['id']}, headers=A)
c.post('/store/chat/read', json={'room': 'all', 'last_id': m['id']}, headers=A)
sa = c.get('/store/chat/state', headers=A).json()
ck('read: nothing unread', sa['total'] == 0, sa['unread'])
ck('and gone from the bell', not any(n['kind'] == 'chat' for n in c.get('/notifications', headers=A).json()['notifications']))
rep = c.post('/store/chat/send', json={'room': room, 'text': 'Will call in 5 min'}, headers=A).json()
r2 = c.get(f'/store/chat/state?room={room}&after={r["messages"][-1]["id"]}', headers=P).json()
ck('Praveen gets only the new reply', [x['text'] for x in r2['messages']] == ['Will call in 5 min'], r2['messages'])
ck('nobody else can edit it', c.put(f"/store/chat/messages/{rep['id']}", json={'text': 'x'}, headers=P).status_code == 403)
e = c.put(f"/store/chat/messages/{rep['id']}", json={'text': 'Will call in 10 min'}, headers=A).json()
ck('Amal corrects his message', e['text'] == 'Will call in 10 min' and e['edited'], e)
ck('Amal deletes it', c.delete(f"/store/chat/messages/{rep['id']}", headers=A).status_code == 200)
r3 = c.get(f'/store/chat/state?room={room}', headers=P).json()
ck('it shows as deleted, the words gone', [x for x in r3['messages'] if x['id'] == rep['id']][0]['deleted'] and not [x for x in r3['messages'] if x['id'] == rep['id']][0]['text'])
ck('an empty message is refused', c.post('/store/chat/send', json={'room': 'all', 'text': '  '}, headers=P).status_code == 400)
ck('a made-up room is refused', c.post('/store/chat/send', json={'room': 'dm:998-999', 'text': 'x'}, headers=P).status_code == 403)
# chat writes do not throw away everybody's bell
g0 = main._WRITE_GEN[0]; c.post('/store/chat/send', json={'room': 'all', 'text': 'x'}, headers=P)
ck('chat does not reset the bell cache', main._WRITE_GEN[0] == g0)
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')
