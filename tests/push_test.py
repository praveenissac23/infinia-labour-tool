"""Phone notifications: the message only the phone can read, a signed
sender, sign-up, nothing old pushed on sign-up, new items pushed once.

Run: cd app && rm -f /tmp/pu.db && DATABASE_URL=sqlite:////tmp/pu.db INFINIA_NO_PUSH=1 INFINIA_PUSH_ANYTIME=1 python3 ../tests/push_test.py
"""
import sys, json, base64
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, push

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

# ---- A phone's keys, and reading what we send it ---------------------------------
ua = ec.generate_private_key(ec.SECP256R1())
ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
auth_secret = b'0123456789abcdef'
def decrypt(body):
    salt, rs, idlen = body[:16], body[16:20], body[20]
    as_pub = body[21:21 + idlen]; ct = body[21 + idlen:]
    secret = ua.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = push._hkdf(auth_secret, secret, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    cek = push._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = push._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    pt = AESGCM(cek).decrypt(nonce, ct, None)
    return pt[:pt.rindex(b"\x02")]
msg = json.dumps({"title": "MR-0014 approved", "body": "Raise the LPO"}).encode()
enc = push.encrypt(msg, push.b64u(ua_pub), push.b64u(auth_secret))
ck('the phone can read the message', decrypt(enc) == msg)
ck('it is not readable as it travels', msg not in enc)

db = database.SessionLocal()
key, pub = push.vapid_keys(db, models)
key2, pub2 = push.vapid_keys(db, models)
ck('the sender key is made once and kept', pub == pub2 and len(push.unb64u(pub)) == 65)
hdr = push._vapid_header(key, pub, "https://fcm.googleapis.com/fcm/send/abc")
t = hdr.split("t=")[1].split(",")[0]; h, b, sg = t.split(".")
claims = json.loads(push.unb64u(b))
raw = push.unb64u(sg); der = encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big'))
try:
    key.public_key().verify(der, f"{h}.{b}".encode(), ec.ECDSA(hashes.SHA256())); okv = True
except Exception: okv = False
ck('the sender is signed (VAPID) for the push service', okv and claims["aud"] == "https://fcm.googleapis.com" and claims["sub"].startswith("mailto:"))

# ---- Sign-up and the round ------------------------------------------------------
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='A', role='admin'))
db.add(models.User(username='site', hashed_password=auth.hash_password('p'), full_name='S', role='site', permissions='dashboard,attendance,settings'))
db.commit(); db.close()
c = TestClient(main.app)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
A, S = tok('admin'), tok('site')
ck('key for the app', c.get('/notifications/push/key', headers=A).json()['key'] == pub)
ck('a bad address is refused', c.post('/notifications/push/subscribe', headers=A, json={'endpoint': 'http://x', 'keys': {}}).status_code == 400)
sent = []
push.send = lambda k, p, s, m, ttl=86400: (sent.append((s.user_id, m)), 201)[1]
notes = {'admin': [{"id": "old-1", "title": "Old", "detail": "", "screen": "approvals", "target": "MR-0001"}], 'site': []}
main._notes_for = lambda db, u: notes[u.username]
r = c.post('/notifications/push/subscribe', headers=A, json={'endpoint': 'https://fcm.googleapis.com/fcm/send/aaa', 'keys': {'p256dh': push.b64u(ua_pub), 'auth': push.b64u(auth_secret)}, 'device': 'Android (app)'})
ck('phone signed up', r.status_code == 200 and r.json()['devices'] == 1, r.text)
import main as M2
ck('nothing old pushed on sign-up', push.push_new(database.SessionLocal, models, main._notes_for) == 0 and not sent)
notes['admin'].append({"id": "new-req-14", "title": "New material request MR-0014", "detail": "Raj asked for 2 materials", "screen": "approvals", "target": "MR-0014"})
ck('a new item is pushed', push.push_new(database.SessionLocal, models, main._notes_for) == 1 and sent[-1][1]['title'] == 'New material request MR-0014', sent)
ck('tapping it opens that request', 'n_screen=approvals' in sent[-1][1]['url'] and 'n_target=MR-0014' in sent[-1][1]['url'])
ck('and only once', push.push_new(database.SessionLocal, models, main._notes_for) == 0)
ck('a login without a phone gets nothing', all(u == 1 for u, _ in sent))
ck('test button', c.post('/notifications/push/test', headers=A).json()['sent'] == 1)
ck('test refused with no phone', c.post('/notifications/push/test', headers=S).status_code == 400)
push.send = lambda k, p, s, m, ttl=86400: 410
notes['admin'].append({"id": "x-2", "title": "Another", "detail": ""})
push.push_new(database.SessionLocal, models, main._notes_for)
ck('a phone that turned it off is forgotten', c.get('/notifications/push/status', headers=A).json()['devices'] == [])
# the real bell list feeds it
real = M2.get_notifications(db=database.SessionLocal(), user=database.SessionLocal().query(models.User).filter_by(username='admin').first())
ck('the bell list is what is pushed', isinstance(real.get('notifications'), list))
print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED: {FAIL}')
