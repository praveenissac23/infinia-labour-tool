"""Expiry Reminder: what is expired, what is due, what is missing - and
one daily summary instead of a message per document.

  * The summary counts people's documents and the company's own (NOCs,
    permits, licences, vehicles) together.
  * "Missing": a man with no Emirates ID, visa or passport on file can
    never be reminded about it, so he is counted until it is entered.
    UAE nationals (local staff) need no visa.
  * The daily digest names only what needs attention today: anything
    already expired (every day until renewed) and anything reaching
    90, 30, 14, 7, 3 or 1 days - so one visa appears on six mornings,
    not ninety.
  * The same digest goes out by email at 8:00 Dubai time, once a day,
    to the addresses saved on the page (mail settings on the server).
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from html import escape

from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy.orm import Session

import main as M
import models, mailer
from database import get_db, SessionLocal

router = APIRouter()
MILESTONES = {90, 30, 14, 7, 3, 1, 0}
REQUIRED = [("eid", "Emirates ID"), ("visa", "Visa / labour card"), ("passport", "Passport")]


def _items(db):
    people = M.list_documents(db=db, user=None)["rows"]
    company = M.list_expiries(db=db, user=None)["rows"]
    out = []
    for d in people:
        out.append({"type": "person", "who": f"{d['emp_no']} {d['name']}", "what": d["kind_label"],
                    "expires_on": d["expires_on"], "days_left": d["days_left"], "id": d["id"]})
    for x in company:
        out.append({"type": "company", "who": x["item"], "what": x["kind"], "category": x["category"],
                    "expires_on": x["expires_on"], "days_left": x["days_left"], "id": x["id"]})
    return [i for i in out if i["days_left"] is not None]


def missing_people(db):
    have = {}
    for d in db.query(models.EmployeeDocument).all():
        k = "visa" if d.kind == "labour_card" else d.kind
        have.setdefault(d.employee_id, set()).add(k)
    out = []
    for e in db.query(models.Employee).filter(models.Employee.active == True).order_by(models.Employee.emp_no).all():  # noqa: E712
        need = [k for k, _ in REQUIRED if not (k == "visa" and (e.pay_group or "") == "local")]
        miss = [label for k, label in REQUIRED if k in need and k not in have.get(e.id, set())]
        if miss:
            out.append({"emp_no": e.emp_no, "name": e.name, "staff": bool(e.staff),
                        "company": e.company or "", "missing": miss})
    return out


def summary(db):
    items = _items(db)
    miss = missing_people(db)
    expired = [i for i in items if i["days_left"] < 0]
    week = [i for i in items if 0 <= i["days_left"] <= 7]
    month = [i for i in items if 8 <= i["days_left"] <= 30]
    return {"expired": len(expired), "week": len(week), "month": len(month), "missing": len(miss),
            "missing_people": miss,
            "attention": sorted(expired + week, key=lambda i: i["days_left"])}


def digest(db):
    """What needs saying today - short on purpose."""
    items = sorted((i for i in _items(db) if i["days_left"] < 0 or i["days_left"] in MILESTONES),
                   key=lambda i: i["days_left"])
    return items


def _when(n):
    return (f"expired {-n} day{'s' if n != -1 else ''} ago" if n < 0 else
            "expires TODAY" if n == 0 else f"in {n} day{'s' if n != 1 else ''}")


def mail_body(db):
    items = digest(db)
    s = summary(db)
    today = M._dubai_today()
    head = (f"{s['expired']} expired, {s['week']} due within 7 days, {s['month']} within 30 days"
            + (f", {s['missing']} people with a document missing" if s["missing"] else ""))
    lines = [f"Expiry Reminder - {today:%d %b %Y}", head, ""]
    for i in items:
        lines.append(f"- {i['who']}: {i['what']} {M._dmy(M._as_date(i['expires_on']))} ({_when(i['days_left'])})")
    if not items:
        lines.append("Nothing reaches a reminder date today.")
    lines += ["", "Open: https://app.infinia.ae/?p=expiry"]
    rows = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #eee'>{escape(i['who'])}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{escape(i['what'])}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{M._dmy(M._as_date(i['expires_on']))}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee;font-weight:bold;color:"
        f"{'#B7322A' if i['days_left'] < 0 else '#9A6700' if i['days_left'] <= 7 else '#555'}'>{_when(i['days_left'])}</td></tr>"
        for i in items)
    html = (f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#222'>"
            f"<h2 style='color:#B7322A;margin:0 0 6px'>Expiry Reminder - {today:%d %b %Y}</h2>"
            f"<p style='margin:0 0 12px'><b>{escape(head)}</b></p>"
            + (f"<table style='border-collapse:collapse;min-width:520px'><tr style='background:#B7322A;color:#fff'>"
               f"<th style='padding:6px 10px;text-align:left'>Who / what</th><th style='padding:6px 10px;text-align:left'>Document</th>"
               f"<th style='padding:6px 10px;text-align:left'>Expires</th><th style='padding:6px 10px;text-align:left'>When</th></tr>{rows}</table>"
               if items else "<p>Nothing reaches a reminder date today.</p>")
            + "<p style='margin-top:16px'><a href='https://app.infinia.ae/?p=expiry'>Open Expiry Reminder</a></p></div>")
    return f"Expiry Reminder: {head}", "\n".join(lines), html, bool(items or s["missing"])


# ---- The page ------------------------------------------------------------

@router.get("/employees/expiry/summary")
def get_summary(db: Session = Depends(get_db), user: models.User = M.DOCS):
    return summary(db)


@router.get("/employees/expiry/mail")
def get_mail(db: Session = Depends(get_db), user: models.User = M.DOCS):
    return {"to": M.get_setting(db, "expiry_mail_to"), "configured": mailer.configured(),
            "last_sent": M.get_setting(db, "expiry_mail_last")}


@router.post("/employees/expiry/mail")
def set_mail(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = M.DOCS):
    to = ", ".join(x.strip() for x in str(payload.get("to") or "").replace(";", ",").split(",") if x.strip())
    bad = [x for x in to.split(", ") if x and ("@" not in x or "." not in x.split("@")[-1])]
    if bad:
        raise HTTPException(status_code=400, detail=f"Not an email address: {', '.join(bad)}")
    M.put_setting(db, "expiry_mail_to", to)
    M.log_action(db, user.id, "expiry_mail", f"daily expiry email to: {to or '(nobody)'}")
    return {"ok": True, "to": to}


@router.post("/employees/expiry/mail/test")
def test_mail(db: Session = Depends(get_db), user: models.User = M.DOCS):
    to = M.get_setting(db, "expiry_mail_to")
    if not to:
        raise HTTPException(status_code=400, detail="Type at least one email address and save it first.")
    subject, body, html, _ = mail_body(db)
    ok, why = send_all(to, subject, body, html)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Not sent: {why}")
    return {"ok": True, "to": to}


def send_all(to, subject, body, html):
    results = [mailer.send(a.strip(), subject, body, html=html) for a in to.split(",") if a.strip()]
    if all(r[0] for r in results):
        return True, "sent"
    return False, "; ".join(dict.fromkeys(r[1] for r in results if not r[0]))


# ---- 8:00 every morning ----------------------------------------------------

def _tick():
    now = datetime.now(timezone.utc) + timedelta(hours=4)
    if now.hour < 8:
        return
    db = SessionLocal()
    try:
        today = now.date().isoformat()
        if M.get_setting(db, "expiry_mail_last") == today:
            return
        to = M.get_setting(db, "expiry_mail_to")
        if not to or not mailer.configured():
            return
        # Claim the day first, so two workers never send it twice.
        M.put_setting(db, "expiry_mail_last", today)
        subject, body, html, worth = mail_body(db)
        if worth:
            ok, why = send_all(to, subject, body, html)
            print(f"expiry mail {today}: {'sent' if ok else 'NOT sent - ' + why}")
    except Exception as e:  # never take the app down over a mail
        print("expiry mail failed:", e)
    finally:
        db.close()


def _loop():
    while True:
        _tick()
        time.sleep(600)


def start():
    threading.Thread(target=_loop, daemon=True, name="expiry-mail").start()
