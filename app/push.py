"""Phone notifications (Web Push) - Android and iPhone, no app store needed.

A phone that has turned notifications on (Settings, or the banner in the
app) sends us its push address. Every two minutes the server works out
each such login's notifications - exactly the list behind the bell, so
each person only hears about what their access covers - and pushes any
it has not pushed before. Tapping one opens the app on that item.

Standard Web Push (RFC 8030 / 8291 / 8292) written out here with the
`cryptography` package the app already has, so nothing new needs
installing on the server: VAPID signs who we are, aes128gcm encrypts the
message so only that phone can read it.

The VAPID key pair is made once, on first start, and kept in Settings;
changing it would silently cut off every phone already signed up.
"""
import base64
import json
import os
import struct
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.exc import IntegrityError

from database import Base

CONTACT = "mailto:engineers@infinia.ae"
EVERY_SECONDS = 120


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    endpoint = Column(String, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    device = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_ok = Column(DateTime, nullable=True)


class PushSent(Base):
    """One line per notification pushed to a login, so it is pushed once."""
    __tablename__ = "push_sent"
    __table_args__ = (UniqueConstraint("user_id", "nid", name="uq_push_sent"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    nid = Column(String, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---- Keys --------------------------------------------------------------------

def vapid_keys(db, models):
    """(private key, public key as base64url) - made once and kept."""
    row = db.query(models.Setting).filter(models.Setting.key == "vapid_private").first()
    if not row:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
        row = models.Setting(key="vapid_private", value=pem)
        db.add(row)
        db.commit()
    key = serialization.load_pem_private_key(row.value.encode(), password=None)
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return key, b64u(pub)


def _vapid_header(key, pub_b64, endpoint):
    u = urlparse(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                            "sub": CONTACT}, separators=(",", ":")).encode())
    der = key.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{body}.{sig}, k={pub_b64}"


def _hkdf(salt, ikm, info, n):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def encrypt(payload: bytes, p256dh: str, auth: str, salt: bytes = None, server_key=None) -> bytes:
    """RFC 8291 aes128gcm: only the phone holding the matching key can read it."""
    ua_pub_bytes = unb64u(p256dh)
    auth_secret = unb64u(auth)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_bytes)
    as_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = as_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    secret = as_key.exchange(ec.ECDH(), ua_pub)
    ikm = _hkdf(auth_secret, secret, b"WebPush: info\x00" + ua_pub_bytes + as_pub, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack(">I", 4096) + bytes([len(as_pub)]) + as_pub + body


def send(key, pub_b64, sub, message: dict, ttl=86400):
    """Push one message to one phone. Returns the HTTP status (410/404 = gone)."""
    data = encrypt(json.dumps(message).encode(), sub.p256dh, sub.auth)
    req = urllib.request.Request(sub.endpoint, data=data, method="POST", headers={
        "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
        "TTL": str(ttl), "Urgency": "normal", "Authorization": _vapid_header(key, pub_b64, sub.endpoint)})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def message_for(n: dict) -> dict:
    """A bell notification as a phone notification, with where tapping goes."""
    q = f"/?n_screen={n.get('screen') or ''}&n_target={n.get('target') or ''}&n_id={n.get('id') or ''}"
    return {"title": n.get("title") or "Infinia", "body": n.get("detail") or "", "tag": n.get("id") or "",
            "url": q}


# ---- The round every two minutes ------------------------------------------------

def push_new(SessionLocal, models, notes_for, seed=False, only_user=None):
    """Push each signed-up login's new notifications. seed=True records what
    is already there without pushing it (a phone that has just signed up
    is not flooded with every old item)."""
    # Nobody is woken up: from 9 at night to 7 in the morning (Dubai) the
    # round waits, and what came in overnight arrives at 7.
    hour = (datetime.utcnow().hour + 4) % 24
    if not seed and not (7 <= hour < 21) and os.environ.get("INFINIA_PUSH_ANYTIME") != "1":
        return 0
    db = SessionLocal()
    pushed = 0
    try:
        key, pub = vapid_keys(db, models)
        q = db.query(PushSubscription)
        if only_user:
            q = q.filter(PushSubscription.user_id == only_user)
        by_user = {}
        for s in q.all():
            by_user.setdefault(s.user_id, []).append(s)
        for uid, subs in by_user.items():
            user = db.query(models.User).filter(models.User.id == uid).first()
            if not user or not user.active:
                continue
            try:
                notes = notes_for(db, user)
            except Exception:
                continue
            done = {r.nid for r in db.query(PushSent.nid).filter(PushSent.user_id == uid).all()}
            for n in notes:
                nid = str(n.get("id") or "")
                if not nid or nid in done:
                    continue
                # Claimed first, so two server processes never push it twice.
                db.add(PushSent(user_id=uid, nid=nid))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue
                if seed:
                    continue
                msg = message_for(n)
                for s in list(subs):
                    st = send(key, pub, s, msg)
                    if st in (200, 201, 202):
                        s.last_ok = datetime.utcnow(); pushed += 1
                    elif st in (404, 410):
                        db.delete(s); subs.remove(s)     # the phone turned it off or the address expired
                db.commit()
    finally:
        db.close()
    return pushed


def start_loop(SessionLocal, models, notes_for):
    def run():
        time.sleep(30)
        while True:
            try:
                push_new(SessionLocal, models, notes_for)
            except Exception as e:      # never let one bad round stop the next
                print("push round failed:", e)
            time.sleep(EVERY_SECONDS)
    threading.Thread(target=run, daemon=True, name="push").start()
