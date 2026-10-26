"""Working offline: a save is never made twice.

The app on a computer that lost the server keeps each save and sends it again when the server is back
(sw.js). Every save carries its own id (X-Req-Id). If the first try did reach the server just before the
line dropped, the server has already done it: the same id coming again gets the answer it got the first
time, and nothing is saved a second time. Kept 14 days.
"""
from datetime import datetime, timedelta

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from starlette.responses import Response

from database import Base, SessionLocal


class OfflineReq(Base):
    __tablename__ = "offline_requests"
    id = Column(String(80), primary_key=True)
    path = Column(String(300), default="")
    status = Column(Integer, default=200)
    ctype = Column(String(120), default="application/json")
    body = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


def create_tables(engine):
    OfflineReq.__table__.create(bind=engine, checkfirst=True)
    db = SessionLocal()
    try:
        db.query(OfflineReq).filter(OfflineReq.created_at < datetime.utcnow() - timedelta(days=14)).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def once(request, call_next):
    rid = request.headers.get("x-req-id")
    if not rid or request.method in ("GET", "HEAD", "OPTIONS") or len(rid) > 80:
        return await call_next(request)
    db = SessionLocal()
    try:
        hit = db.query(OfflineReq).get(rid)
        if hit:
            return Response(content=hit.body.encode(), status_code=hit.status, media_type=hit.ctype or "application/json", headers={"X-Replayed": "1"})
    finally:
        db.close()
    resp = await call_next(request)
    if resp.status_code >= 500:
        return resp
    body = b""
    async for chunk in resp.body_iterator:
        body += chunk if isinstance(chunk, bytes) else chunk.encode()
    ctype = resp.headers.get("content-type", "application/json")
    if len(body) < 2_000_000 and ("json" in ctype or "text" in ctype):
        db = SessionLocal()
        try:
            db.add(OfflineReq(id=rid, path=request.url.path[:300], status=resp.status_code, ctype=ctype[:120], body=body.decode("utf-8", "replace")))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-encoding")}
    return Response(content=body, status_code=resp.status_code, headers=headers, media_type=resp.media_type)
