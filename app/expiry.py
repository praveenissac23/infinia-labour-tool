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
from sqlalchemy import Column, Integer, String, Date, DateTime, UniqueConstraint
from sqlalchemy.orm import Session

import main as M
import models, mailer
from database import get_db, SessionLocal, Base, engine

router = APIRouter()
MILESTONES = {90, 30, 14, 7, 3, 1, 0}
REQUIRED = [("eid", "Emirates ID"), ("visa", "Visa / labour card"), ("passport", "Passport")]
# Visa, labour card and Emirates ID are renewed as one process by the PRO:
# one reminder for the three, one "Mark started" for the three.
GROUP = ("visa", "labour_card", "eid")
GROUP_LABEL = "Visa, labour card & Emirates ID"
GROUP_NAMES = {"visa": "Visa", "labour_card": "Labour card", "eid": "Emirates ID"}


class ExpiryStarted(Base):
    """'Renewal started' against one document: its reminders stop (bell,
    phone, email) while it still shows on the page as it is. Kept with
    the expiry date it was marked against - once the renewed date is
    entered the mark no longer matches, so the next renewal is reminded
    about as usual."""
    __tablename__ = "expiry_started"
    __table_args__ = (UniqueConstraint("doc_type", "doc_id", name="uq_expiry_started"),)
    id = Column(Integer, primary_key=True)
    doc_type = Column(String, nullable=False)       # person | company
    doc_id = Column(Integer, nullable=False)
    expires_on = Column(Date, nullable=True)
    marked_by = Column(String, default="")
    marked_at = Column(DateTime, default=datetime.utcnow)


ExpiryStarted.__table__.create(bind=engine, checkfirst=True)


def started_keys(db):
    """{(type, id): row} for marks that still match the document's date."""
    return {(r.doc_type, r.doc_id): r for r in db.query(ExpiryStarted).all()}


def _one_started(t, i, expires_on, marks):
    m = marks.get((t, i))
    return bool(m) and (m.expires_on.isoformat() if m.expires_on else None) == (expires_on or None)


def _is_started(item, marks):
    """A grouped item (visa + labour card + EID) is started once its renewal
    is marked - any of the three still carrying a current mark."""
    if item.get("members"):
        return any(_one_started("person", i, e, marks) for i, e in item["members"])
    return _one_started(item["type"], item["id"], item.get("expires_on"), marks)


def notice_items(db):
    """What the reminders talk about: everything due, less what is marked started."""
    marks = started_keys(db)
    return [i for i in _items(db) if not _is_started(i, marks)]


def _raw_items(db):
    """One line a document - what 'Mark started' is kept against."""
    people = M.list_documents(db=db, user=None)["rows"]
    company = M.list_expiries(db=db, user=None)["rows"]
    out = []
    for d in people:
        out.append({"type": "person", "who": f"{d['emp_no']} {d['name']}", "what": d["kind_label"], "kind": d["kind"],
                    "employee_id": d["employee_id"], "expires_on": d["expires_on"], "days_left": d["days_left"], "id": d["id"]})
    for x in company:
        out.append({"type": "company", "who": x["item"], "what": x["kind"], "category": x["category"],
                    "expires_on": x["expires_on"], "days_left": x["days_left"], "id": x["id"]})
    return [i for i in out if i["days_left"] is not None]


def group_members(raw, item):
    """The person's visa, labour card and Emirates ID - renewed together, reminded once."""
    if item["type"] != "person" or item.get("kind") not in GROUP:
        return [item]
    return sorted((x for x in raw if x["type"] == "person" and x.get("kind") in GROUP and x["employee_id"] == item["employee_id"]),
                  key=lambda x: x["days_left"])


def _items(db):
    """What is reminded about: a person's visa, labour card and EID as one
    line, dated by whichever of them expires first."""
    raw = _raw_items(db)
    out, groups = [], {}
    for i in raw:
        if i["type"] == "person" and i.get("kind") in GROUP:
            groups.setdefault(i["employee_id"], []).append(i)
        else:
            out.append(i)
    for allp in groups.values():
        parts = sorted(allp, key=lambda x: x["days_left"])
        first = parts[0]
        out.append({**first, "what": GROUP_LABEL,
                    "members": [(x["id"], x["expires_on"]) for x in parts]})
    return out


def missing_people(db):
    have = {}
    for d in db.query(models.EmployeeDocument).all():
        k = "visa" if d.kind == "labour_card" else d.kind
        have.setdefault(d.employee_id, set()).add(k)
    out = []
    today = M._dubai_today()
    for e in db.query(models.Employee).filter(models.Employee.active == True).order_by(models.Employee.emp_no).all():  # noqa: E712
        if not M.doc_tracked(e, today):
            continue          # left, and his last pay cycle is over
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
    # What each tab of the page shows: people counted once each, by the
    # document of theirs that is soonest (one line a person on that list);
    # company documents one by one (one line a document there). The
    # totals above stay for the menu number and the bell.
    soonest = {}
    for i in items:
        if i["type"] == "person":
            soonest[i["who"]] = min(soonest.get(i["who"], 10 ** 6), i["days_left"])
    comp = [i["days_left"] for i in items if i["type"] == "company"]
    band = lambda xs: {"expired": sum(1 for d in xs if d < 0), "week": sum(1 for d in xs if 0 <= d <= 7),
                       "month": sum(1 for d in xs if 8 <= d <= 30)}
    # The menu number is the bell's number: expired or due in 7 days, less
    # those marked "renewal started" - one figure wherever it is shown.
    its = notice_items(db)
    badge = sum(1 for i in its if i["days_left"] <= 7)
    return {"expired": len(expired), "week": len(week), "month": len(month), "missing": len(miss), "badge": badge,
            "people": band(list(soonest.values())),
            "company": {**band(comp), "all": len(M.list_expiries(db=db, user=None)["rows"])},
            "missing_people": miss,
            "attention": sorted(expired + week, key=lambda i: i["days_left"])}


def digest(db):
    """What needs saying today - short on purpose."""
    items = sorted((i for i in notice_items(db) if i["days_left"] < 0 or i["days_left"] in MILESTONES),
                   key=lambda i: i["days_left"])
    return items


def _when(n):
    return (f"expired {-n} day{'s' if n != -1 else ''} ago" if n < 0 else
            "expires TODAY" if n == 0 else f"in {n} day{'s' if n != 1 else ''}")


def mail_body(db):
    items = digest(db)
    s = summary(db)
    its = notice_items(db)        # marked "renewal started" are not counted in the reminder
    s = {**s, "expired": sum(1 for i in its if i["days_left"] < 0),
         "week": sum(1 for i in its if 0 <= i["days_left"] <= 7),
         "month": sum(1 for i in its if 8 <= i["days_left"] <= 30)}
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

@router.get("/employees/expiry/started")
def get_started(db: Session = Depends(get_db), user: models.User = M.DOCS):
    items = {(i["type"], i["id"]): i for i in _raw_items(db)}
    out = []
    for (t, i), m in started_keys(db).items():
        it = items.get((t, i))
        current = bool(it) and _one_started(t, i, it["expires_on"], {(t, i): m})
        if current:
            out.append({"type": t, "id": i, "by": m.marked_by, "at": m.marked_at.isoformat() if m.marked_at else ""})
    return {"rows": out}


@router.post("/employees/expiry/started")
def set_started(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = M.DOCS):
    t = (payload.get("type") or "").strip()
    try:
        i = int(payload.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Which document?")
    if t not in ("person", "company"):
        raise HTTPException(status_code=400, detail="Which document?")
    raw = _raw_items(db)
    item = next((x for x in raw if x["type"] == t and x["id"] == i), None)
    if not item:
        raise HTTPException(status_code=404, detail="That document is not on file.")
    members = group_members(raw, item)     # visa, labour card and EID go together
    on = payload.get("on", True)
    what = GROUP_LABEL if len(members) > 1 else item["what"]
    for it in members:
        row = db.query(ExpiryStarted).filter(ExpiryStarted.doc_type == t, ExpiryStarted.doc_id == it["id"]).first()
        if on:
            if not row:
                row = ExpiryStarted(doc_type=t, doc_id=it["id"]); db.add(row)
            row.expires_on = M._as_date(it["expires_on"])
            row.marked_by = user.full_name or user.username
            row.marked_at = datetime.utcnow()
        elif row:
            db.delete(row)
    M.log_action(db, user.id, "expiry_started" if on else "expiry_started_off",
                 f"{item['who']}: {what}" + (f" {item['expires_on']}" if on else ""))
    db.commit()
    return {"ok": True, "on": bool(payload.get("on", True))}


# ---- Closed: the renewal is done - the new date goes in (or the entry goes) ----

def _find(db, payload):
    t = (payload.get("type") or "").strip()
    try:
        i = int(payload.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Which document?")
    raw = _raw_items(db)
    item = next((x for x in raw if x["type"] == t and x["id"] == i), None)
    if not item:
        raise HTTPException(status_code=404, detail="That document is not on file.")
    return item, group_members(raw, item)


def _years(kind):
    return 2 if kind in GROUP else 1


@router.get("/employees/expiry/close")
def close_info(type: str = "", id: int = 0, db: Session = Depends(get_db), user: models.User = M.DOCS):
    """What the Close pop-up asks for: the new date of each document in the renewal -
    for visa, labour card and Emirates ID always the three (one not on file can be added)."""
    item, members = _find(db, {"type": type, "id": id})
    out = []
    for x in members:
        old = M._as_date(x["expires_on"])
        try:
            sug = old.replace(year=old.year + _years(x.get("kind")))
        except ValueError:                       # 29 Feb
            sug = old.replace(year=old.year + _years(x.get("kind")), day=28)
        out.append({"id": x["id"], "kind": x.get("kind", ""), "what": GROUP_NAMES.get(x.get("kind"), x["what"]),
                    "expires_on": x["expires_on"], "suggest": sug.isoformat()})
    grouped = item["type"] == "person" and item.get("kind") in GROUP
    if grouped:
        have = {x["kind"] for x in out}
        out += [{"id": f"new:{k}", "kind": k, "what": GROUP_NAMES[k], "expires_on": "", "suggest": ""} for k in GROUP if k not in have]
        order = {k: n for n, k in enumerate(GROUP)}
        out.sort(key=lambda x: order.get(x["kind"], 9))
    return {"who": item["who"], "what": GROUP_LABEL if grouped else item["what"], "type": item["type"], "docs": out}


@router.post("/employees/expiry/close")
def close(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = M.DOCS):
    """Renewal closed: each document gets its new expiry date, the 'started' mark goes.
    A date left as it was is left alone; a document not on file is added if a date is typed."""
    item, members = _find(db, payload)
    dates = {str(k): v for k, v in (payload.get("dates") or {}).items()}
    new, changes = {}, []
    for x in members:
        raw = dates.get(str(x["id"]))
        d = M._as_date(raw)
        name = GROUP_NAMES.get(x.get("kind"), x["what"])
        old = M._as_date(x["expires_on"])
        if not d:
            raise HTTPException(status_code=400, detail=f"Type the new expiry date for the {name}.")
        if d < old:
            raise HTTPException(status_code=400, detail=f"The new {name} date cannot be before the old one ({M._dmy(old)}).")
        if d != old:
            new[x["id"]] = d; changes.append(f"{name} {x['expires_on']} -> {d.isoformat()}")
    adds = {}
    if item["type"] == "person" and item.get("kind") in GROUP:
        have = {x.get("kind") for x in members}
        for k in GROUP:
            d = M._as_date(dates.get(f"new:{k}"))
            if k not in have and d:
                adds[k] = d; changes.append(f"{GROUP_NAMES[k]} added, expires {d.isoformat()}")
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing changed - type the new expiry date.")
    Model = models.EmployeeDocument if item["type"] == "person" else models.CompanyExpiry
    for x in members:
        if x["id"] in new:
            o = db.get(Model, x["id"]); o.expires_on = new[x["id"]]
            if item["type"] == "person" and o.kind == "contract":      # People file shows the same contract
                prof = db.query(models.PeopleProfile).filter(models.PeopleProfile.employee_id == o.employee_id).first()
                if prof:
                    prof.contract_expiry = new[x["id"]]
        db.query(ExpiryStarted).filter(ExpiryStarted.doc_type == item["type"], ExpiryStarted.doc_id == x["id"]).delete()
    for k, d in adds.items():
        db.add(models.EmployeeDocument(employee_id=item["employee_id"], kind=k, expires_on=d, number=""))
    M.log_action(db, user.id, "expiry_closed", f"{item['who']}: " + ", ".join(changes))
    db.commit()
    return {"ok": True, "n": len(changes)}


@router.post("/employees/expiry/remove")
def remove(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = M.DOCS):
    """No longer needed: the entry (all of the renewal's documents) is deleted."""
    item, members = _find(db, payload)
    Model = models.EmployeeDocument if item["type"] == "person" else models.CompanyExpiry
    for x in members:
        o = db.get(Model, x["id"])
        if o:
            db.delete(o)
        db.query(ExpiryStarted).filter(ExpiryStarted.doc_type == item["type"], ExpiryStarted.doc_id == x["id"]).delete()
    M.log_action(db, user.id, "expiry_removed", f"{item['who']}: " + ", ".join(f"{x['what']} {x['expires_on']}" for x in members)
                 + (f" - {str(payload.get('reason')).strip()[:200]}" if payload.get("reason") else ""))
    db.commit()
    return {"ok": True, "n": len(members)}


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
