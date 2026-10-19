"""Estimation > Dashboard / Projects / Tenders.

Everything the contracts team kept in Excel, one project at a time:

  Client side      BOQ & budget, payment certificates to the consultant,
                   variations, client invoices (read from Accounts).
  Subcontractors   the subcontract / LPO register, every invoice from the
                   day it arrives to the day it is paid (site check, PC,
                   Accounts, payment), the payment certificate itself, and
                   the finalization log (scope, rate, shop drawing,
                   material, authority approval, status per trade).
  Site & technical RFIs, NOCs & approvals (the project tracker), submittals,
                   documents.
  Tenders          every enquiry until it is won (and becomes a project) or lost.

The money is never typed twice. A payment certificate holds cumulative
figures (work done to date, retention to date ...), and what is certified
this time is always worked out as "net to date now - net to date at the
last certificate". Change an old certificate and every later one follows,
so the register can never disagree with itself. Advance recovery and
retention are worked out from the percentages on the subcontract unless
somebody types their own figure.

Under /store/est/ (screen data) and /export/est/ (Preview / PDF / Excel /
files) - the two prefixes nginx already forwards.
"""
import hashlib
import hmac
import io
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Session

import auth
import main as M
import models
from database import Base, get_db

RIGHT = "estimation_projects"
router = APIRouter()
VIEW = Depends(M.require_screen(RIGHT))
PAYER = Depends(M.require_any_screen(RIGHT, "accounts_bank"))
FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "estimation")
MAX_FILE = 25 * 1024 * 1024


def today():
    return (datetime.utcnow() + timedelta(hours=4)).date()     # Dubai


def r2(x):
    return round(float(x or 0) + 0.0, 2)


# ---- tables -----------------------------------------------------------------------------

def _audit():
    return dict(created_by=Column(Integer, nullable=True), updated_by=Column(Integer, nullable=True),
                created_at=Column(DateTime(timezone=True), server_default=func.now()),
                updated_at=Column(DateTime(timezone=True), onupdate=func.now()))


class EstProject(Base):
    __tablename__ = "est_projects"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)    # 912 - the site code
    name = Column(String, default="")
    client = Column(String, default="")
    consultant = Column(String, default="")
    location = Column(String, default="")
    contract_value = Column(Float, default=0.0)
    adv_pct = Column(Float, default=0.0)        # advance from the client, % of contract
    ret_pct = Column(Float, default=10.0)       # retention the client holds
    vat_pct = Column(Float, default=5.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String, default="Running")
    qs = Column(String, default="")             # the QS looking after it
    notes = Column(Text, default="")
    locals().update(_audit())


class EstSub(Base):
    """A subcontract or an LPO on a project."""
    __tablename__ = "est_subs"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    supplier_id = Column(Integer, nullable=True)
    name = Column(String, default="")           # M/S. ONE GB PILING & FOUNDATION
    scope = Column(String, default="")          # Shoring
    trade = Column(String, default="Civil")
    kind = Column(String, default="Subcontract")    # Subcontract | LPO | Manpower
    agreement = Column(String, default="")      # IC/912 & 913/SCA/01/25
    lpo = Column(String, default="")
    value = Column(Float, default=0.0)          # initial subcontract / LPO amount
    cancelled = Column(Float, default=0.0)      # LPO cancellation
    adv_pct = Column(Float, default=0.0)
    ret_pct = Column(Float, default=0.0)
    vat_pct = Column(Float, default=5.0)
    pay_days = Column(Integer, default=0)
    status = Column(String, default="Active")   # Active | Completed | Closed | Cancelled
    start_date = Column(Date, nullable=True)
    notes = Column(Text, default="")
    sort = Column(Integer, default=0)
    locals().update(_audit())


class EstSubVO(Base):
    """A variation to a subcontract (adds to - or, negative, takes from - its value)."""
    __tablename__ = "est_sub_vos"
    id = Column(Integer, primary_key=True)
    sub_id = Column(Integer, nullable=False, index=True)
    on_date = Column(Date, nullable=True)
    ref = Column(String, default="")
    title = Column(String, default="")
    amount = Column(Float, default=0.0)
    locals().update(_audit())


class EstSubPC(Base):
    """One invoice from a subcontractor, followed until it is paid, and the
    payment certificate made for it. Money columns ending _cum are to date."""
    __tablename__ = "est_sub_pcs"
    id = Column(Integer, primary_key=True)
    sub_id = Column(Integer, nullable=False, index=True)
    seq = Column(Integer, default=1)            # PC No.
    pc_type = Column(String, default="Interim")     # Interim | Advance | Final | Retention release
    inv_ref = Column(String, default="")
    inv_date = Column(Date, nullable=True)
    inv_amount = Column(Float, default=0.0)
    received = Column(Date, nullable=True)      # invoice received in the office
    to_site = Column(Date, nullable=True)
    site_back = Column(Date, nullable=True)
    certified_on = Column(Date, nullable=True)  # figures checked by the QS
    issued = Column(Date, nullable=True)        # PC issued
    to_accounts = Column(Date, nullable=True)
    paid_on = Column(Date, nullable=True)
    paid_amount = Column(Float, default=0.0)
    paid_ref = Column(String, default="")
    status = Column(String, default="Received")
    work_cum = Column(Float, default=0.0)       # value of work done to date
    mos_cum = Column(Float, default=0.0)        # material on site to date
    adv_amount = Column(Float, default=0.0)     # advance paid on this PC
    adv_rec_cum = Column(Float, default=0.0)
    adv_auto = Column(Boolean, default=True)
    ret_cum = Column(Float, default=0.0)
    ret_auto = Column(Boolean, default=True)
    ret_rel_cum = Column(Float, default=0.0)
    other_cum = Column(Float, default=0.0)      # other deductions to date (back-charges, manpower ...)
    other_note = Column(String, default="")
    remarks = Column(Text, default="")
    locals().update(_audit())


class EstClientPC(Base):
    """An interim payment application to the consultant, and what was certified."""
    __tablename__ = "est_client_pcs"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    seq = Column(Integer, default=1)
    pc_type = Column(String, default="Interim")
    period_to = Column(Date, nullable=True)
    submitted = Column(Date, nullable=True)
    claimed_cum = Column(Float, default=0.0)        # work done to date, as claimed
    certified_cum = Column(Float, default=0.0)      # work done to date, as certified
    certified_on = Column(Date, nullable=True)
    mos_cum = Column(Float, default=0.0)
    adv_amount = Column(Float, default=0.0)
    adv_rec_cum = Column(Float, default=0.0)
    adv_auto = Column(Boolean, default=True)
    ret_cum = Column(Float, default=0.0)
    ret_auto = Column(Boolean, default=True)
    ret_rel_cum = Column(Float, default=0.0)
    other_cum = Column(Float, default=0.0)
    status = Column(String, default="Draft")        # Draft | Submitted | Certified | Invoiced | Paid
    invoice_no = Column(String, default="")
    remarks = Column(Text, default="")
    locals().update(_audit())


class EstVariation(Base):
    __tablename__ = "est_variations"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    seq = Column(Integer, default=1)
    title = Column(String, default="")
    kind = Column(String, default="Addition")       # Addition | Omission
    source = Column(String, default="Client instruction")
    ref = Column(String, default="")
    on_date = Column(Date, nullable=True)
    submitted = Column(Date, nullable=True)
    submitted_amount = Column(Float, default=0.0)
    approved_on = Column(Date, nullable=True)
    approved_amount = Column(Float, default=0.0)
    status = Column(String, default="Identified")   # Identified | Submitted | Approved | Rejected
    sub_id = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    locals().update(_audit())


class EstBoq(Base):
    __tablename__ = "est_boq"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    section = Column(String, default="")
    code = Column(String, default="")
    description = Column(String, default="")
    unit = Column(String, default="")
    qty = Column(Float, default=0.0)
    rate = Column(Float, default=0.0)           # rate to the client
    cost_rate = Column(Float, default=0.0)      # budget cost rate
    done_pct = Column(Float, default=0.0)
    sort = Column(Integer, default=0)
    locals().update(_audit())


class EstLog(Base):
    """One line of an RFI log, NOC & approvals tracker, submittal log or document register."""
    __tablename__ = "est_logs"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)   # rfi | approval | submittal | doc
    seq = Column(Integer, default=1)
    group = Column(String, default="")          # approvals: the stage heading
    title = Column(String, default="")
    party = Column(String, default="")          # Consultant / DM / DEWA ...
    discipline = Column(String, default="")
    ref = Column(String, default="")
    rev = Column(String, default="")
    sent = Column(Date, nullable=True)
    due = Column(Date, nullable=True)
    replied = Column(Date, nullable=True)
    status = Column(String, default="Open")
    note = Column(Text, default="")
    sort = Column(Integer, default=0)
    locals().update(_audit())


class EstFinal(Base):
    """The finalization log: one trade on one project."""
    __tablename__ = "est_finals"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    section = Column(String, default="CIVIL")
    item = Column(String, default="")
    sc = Column(String, default="")     # scope: C main contractor | E employer | PS provisional sum | N/A
    rt = Column(String, default="")     # rate finalized       ✔ | X | N/A
    sd = Column(String, default="")     # shop drawing
    ma = Column(String, default="")     # material approval
    aa = Column(String, default="")     # authority approval
    st = Column(String, default="")     # final status
    sub_id = Column(Integer, nullable=True)
    note = Column(String, default="")
    sort = Column(Integer, default=0)
    locals().update(_audit())


class EstTender(Base):
    __tablename__ = "est_tenders"
    id = Column(Integer, primary_key=True)
    seq = Column(Integer, default=1)
    name = Column(String, default="")
    client = Column(String, default="")
    consultant = Column(String, default="")
    location = Column(String, default="")
    kind = Column(String, default="Villa")
    received = Column(Date, nullable=True)
    due = Column(Date, nullable=True)
    submitted = Column(Date, nullable=True)
    value = Column(Float, default=0.0)
    estimator = Column(String, default="")
    status = Column(String, default="Received")     # Received | Pricing | Submitted | Won | Lost | Dropped
    project_id = Column(Integer, nullable=True)
    note = Column(Text, default="")
    locals().update(_audit())


class EstFile(Base):
    __tablename__ = "est_files"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=True, index=True)
    kind = Column(String, default="doc")        # what it hangs on: doc | rfi | subpc | sub | ...
    row_id = Column(Integer, nullable=True)
    name = Column(String, default="")
    stored = Column(String, default="")
    size = Column(Integer, default=0)
    category = Column(String, default="")
    locals().update(_audit())


TABLES = [EstProject, EstSub, EstSubVO, EstSubPC, EstClientPC, EstVariation, EstBoq, EstLog, EstFinal, EstTender, EstFile]


def create_tables(engine):
    for t in TABLES:
        t.__table__.create(bind=engine, checkfirst=True)
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for t in TABLES:
        have = {c["name"] for c in insp.get_columns(t.__tablename__)}
        for col in t.__table__.columns:
            if col.name not in have:
                typ = col.type.compile(engine.dialect)
                with engine.begin() as cx:
                    cx.execute(text(f'ALTER TABLE {t.__tablename__} ADD COLUMN "{col.name}" {typ}'))


# ---- projects 901 to 927, put in once -----------------------------------------------------

# Names the project tracker uses where Settings has none.
TRACKER_NAMES = {"916": "VL-88 Keturah Reserve", "918": "VL-44 Keturah Reserve", "920": "VE-261 Sobha Hartland",
                 "925": "VE-225 Sobha Hartland", "926": "VE-226 Sobha Hartland", "927": "WS-41"}


def seed_projects(SessionLocal, first=901, last=927):
    """Every project from 901 to 927 made once, filled from what the app
    already knows: the site (Settings > Companies & sites), the contract from
    Accounts > Project payments, the client and location from Accounts >
    Invoices. Never again after that, and never over a project already there."""
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == "est_projects_seeded").first():
            return
        try:
            import accounts, projectpay
        except Exception:
            accounts = projectpay = None
        made = []
        for n in range(first, last + 1):
            code = str(n)
            if db.query(EstProject).filter(EstProject.code == code).first():
                continue
            site = db.query(models.Site).filter(models.Site.code == code).first()
            inv = None
            if accounts:
                inv = (db.query(accounts.Invoice).filter(accounts.Invoice.project_no == code)
                       .order_by(accounts.Invoice.inv_date.desc()).first())
            contract = 0.0
            if projectpay:
                contract = sum(x.contract or 0 for x in db.query(projectpay.ProjectScope).filter(projectpay.ProjectScope.project == code))
            name = (site.project_name if site else "") or TRACKER_NAMES.get(code, "")
            if not name and inv and inv.project and not inv.project.lower().startswith("swimming pool"):
                name = re.sub(r"^%s\s*-\s*" % code, "", inv.project).strip()
            plot = (site.plot_no if site else "") or ""
            if not name:
                name = f"Plot {plot}" if plot else ""
            db.add(EstProject(code=code, name=name[:200], client=(inv.client if inv else "") or "",
                              location=((inv.location if inv else "") or (f"Plot {plot}" if plot else ""))[:200],
                              contract_value=r2(contract), status="Running"))
            made.append(code)
        db.add(models.Setting(key="est_projects_seeded", value="1"))
        db.commit()
        if made:
            print("Estimation projects made: " + ", ".join(made))
    except Exception as e:          # never stops the app
        db.rollback()
        print(f"Estimation projects seed skipped: {e}")
    finally:
        db.close()


# ---- the lists people pick from (so nothing is typed that can be picked) ---------------

TRADES = ["Civil", "MEP", "Finishes", "Joinery", "Aluminium & Glazing", "Steel", "External", "Manpower", "Supply", "Other"]
SCOPES = ["Shoring", "Piling", "Dewatering", "Anti Termite", "Waterproofing", "Blockwork", "Plaster", "Tiling", "Painting",
          "False Ceiling", "Gypsum", "Joinery", "Wooden Doors", "Metal Doors", "Kitchen Cabinets", "Wardrobes", "Aluminium & Glazing",
          "Glass Partition", "Cladding", "Stone Cladding", "MEP", "Plumbing", "Electrical", "HVAC", "Fire Fighting", "Lift / Elevators",
          "Swimming Pool", "Landscaping", "Hardscape", "Signage", "Scaffolding", "Steel Structure", "Insulation", "Manpower Supply",
          "Laboratory", "Gym Flooring", "Steam & Sauna", "Play Equipment", "Fire Stop", "Cutting & Chasing", "Other"]
PARTIES = ["Consultant", "Client", "Developer", "DM (Dubai Municipality)", "DEWA", "RTA", "Etisalat / du", "Civil Defence",
           "Trakhees", "Nakheel", "Emaar", "Dubai Properties", "Meraas", "Subcontractor", "Supplier", "Other"]
DISCIPLINES = ["Architectural", "Structural", "MEP", "Electrical", "Plumbing", "HVAC", "Civil", "Landscape", "Interior", "General"]
DOC_CATEGORIES = ["Drawings", "Contract", "Subcontract agreement", "LPO", "Permit / NOC", "Letter", "Minutes of meeting",
                  "Method statement", "Report", "Photo", "Invoice", "Other"]

# The project tracker: what has to be submitted and approved, in order.
APPROVALS = [
    ("Design", "Concept design", "Consultant"), ("Design", "Soil investigation report", "Consultant"),
    ("Preliminary drawings", "Preliminary drawings", "Consultant"), ("Preliminary drawings", "Preliminary drawings", "Developer"),
    ("Preliminary drawings", "Preliminary drawings", "DM (Dubai Municipality)"),
    ("Detail drawings", "Detail drawings", "Consultant"), ("Detail drawings", "Detail drawings", "Developer"),
    ("Detail drawings", "Detail drawings", "DM (Dubai Municipality)"),
    ("Building permit", "Building permit received", "DM (Dubai Municipality)"),
    ("NOCs", "Water NOC", "DEWA"), ("NOCs", "RTA NOC", "RTA"), ("NOCs", "Telecom NOC", "Etisalat / du"),
    ("NOCs", "Electricity NOC", "DEWA"),
    ("Contractor", "Appointment of main contractor", "DM (Dubai Municipality)"), ("Contractor", "CAR insurance", "DM (Dubai Municipality)"),
    ("Contractor", "Building permit with contractor", "DM (Dubai Municipality)"), ("Contractor", "Demarcation", "DM (Dubai Municipality)"),
    ("Shoring", "Shoring design (subcontractor)", "Subcontractor"), ("Shoring", "Shoring permit", "Consultant"),
    ("Shoring", "Shoring permit", "DM (Dubai Municipality)"),
    ("CNOC", "Construction NOC", "Developer"),
    ("Completion", "DEWA connection", "DEWA"), ("Completion", "Civil Defence completion", "Civil Defence"),
    ("Completion", "Completion certificate", "DM (Dubai Municipality)"), ("Completion", "Handover to client", "Client"),
]

# The finalization log's trades, by section.
FINAL_ITEMS = {
    "CIVIL": ["Anti Termite", "Laboratory", "Steel", "Concrete", "Blockworks", "GRP Lining", "Sub Waterproofing - Bitumen",
              "Substructure Waterproofing", "Wet area Waterproofing", "Combo Roof Waterproofing", "Painting works",
              "False Ceiling works", "Fixing of Tiling works (Internal)", "Aluminium & Glazing works", "Canopy & Pergola",
              "Rolling Shutter & Gates", "Wooden Doors", "Kitchen Cabinet", "Wardrobes", "Decorative wall Claddings",
              "Vanity Counters", "Furniture", "WPC louvers - Wooden Panelling", "Structural Steel Works", "Steel Staircase"],
    "MEP": ["Plumbing Works", "Solar Water Heater", "Electrical Works", "AC & Ventilation Works", "Switches & Sockets", "Lift",
            "Sanitary wares", "Lights & Façade Lighting", "Chandeliers", "Home Automation", "Kitchen appliances"],
    "EXTERNAL": ["Floor Tiling works (External)", "External Wall Tiling", "Swimming pool", "Landscaping works", "CAT Ladder",
                 "Boundary Wall Railing & Gate"],
}

LOG_STATUS = {
    "rfi": ["Open", "Answered", "Closed"],
    "approval": ["Not started", "Submitted", "Approved", "Rejected", "N/A"],
    "submittal": ["Preparing", "Submitted", "Approved", "Approved as noted", "Revise & resubmit", "Rejected"],
    "doc": ["Current", "Superseded"],
}
LOG_PREFIX = {"rfi": "RFI", "approval": "AP", "submittal": "SUB", "doc": "DOC"}
SUB_STEPS = ["Received", "At site", "Back from site", "Certified", "PC issued", "With Accounts", "Paid"]
RULES_KEY = "est_rules"
DEFAULT_RULES = {"site_days": 5, "pc_days": 10, "rfi_days": 7, "approval_days": 14, "submittal_days": 14}


def _rules(db):
    s = db.query(models.Setting).filter(models.Setting.key == RULES_KEY).first()
    out = dict(DEFAULT_RULES)
    if s:
        try:
            out.update({k: int(v) for k, v in json.loads(s.value or "{}").items() if k in DEFAULT_RULES})
        except (ValueError, TypeError):
            pass
    return out


# ---- the generic save: field lists per kind ------------------------------------------

S, F, D, I, B = "s", "f", "d", "i", "b"
KINDS = {
    "projects": (EstProject, None, {"code": S, "name": S, "client": S, "consultant": S, "location": S, "contract_value": F,
                                    "adv_pct": F, "ret_pct": F, "vat_pct": F, "start_date": D, "end_date": D, "status": S,
                                    "qs": S, "notes": S}),
    "subs": (EstSub, "project_id", {"supplier_id": I, "name": S, "scope": S, "trade": S, "kind": S, "agreement": S, "lpo": S,
                                    "value": F, "cancelled": F, "adv_pct": F, "ret_pct": F, "vat_pct": F, "pay_days": I,
                                    "status": S, "start_date": D, "notes": S, "sort": I}),
    "subvos": (EstSubVO, "sub_id", {"on_date": D, "ref": S, "title": S, "amount": F}),
    "subpcs": (EstSubPC, "sub_id", {"seq": I, "pc_type": S, "inv_ref": S, "inv_date": D, "inv_amount": F, "received": D,
                                    "to_site": D, "site_back": D, "certified_on": D, "issued": D, "to_accounts": D, "paid_on": D,
                                    "paid_amount": F, "paid_ref": S, "status": S, "work_cum": F, "mos_cum": F, "adv_amount": F,
                                    "adv_rec_cum": F, "adv_auto": B, "ret_cum": F, "ret_auto": B, "ret_rel_cum": F, "other_cum": F,
                                    "other_note": S, "remarks": S}),
    "clientpcs": (EstClientPC, "project_id", {"seq": I, "pc_type": S, "period_to": D, "submitted": D, "claimed_cum": F,
                                              "certified_cum": F, "certified_on": D, "mos_cum": F, "adv_amount": F,
                                              "adv_rec_cum": F, "adv_auto": B, "ret_cum": F, "ret_auto": B, "ret_rel_cum": F,
                                              "other_cum": F, "status": S, "invoice_no": S, "remarks": S}),
    "variations": (EstVariation, "project_id", {"seq": I, "title": S, "kind": S, "source": S, "ref": S, "on_date": D,
                                                "submitted": D, "submitted_amount": F, "approved_on": D, "approved_amount": F,
                                                "status": S, "sub_id": I, "notes": S}),
    "boq": (EstBoq, "project_id", {"section": S, "code": S, "description": S, "unit": S, "qty": F, "rate": F, "cost_rate": F,
                                   "done_pct": F, "sort": I}),
    "logs": (EstLog, "project_id", {"kind": S, "seq": I, "group": S, "title": S, "party": S, "discipline": S, "ref": S, "rev": S,
                                    "sent": D, "due": D, "replied": D, "status": S, "note": S, "sort": I}),
    "finals": (EstFinal, "project_id", {"section": S, "item": S, "sc": S, "rt": S, "sd": S, "ma": S, "aa": S, "st": S,
                                        "sub_id": I, "note": S, "sort": I}),
    "tenders": (EstTender, None, {"seq": I, "name": S, "client": S, "consultant": S, "location": S, "kind": S, "received": D,
                                  "due": D, "submitted": D, "value": F, "estimator": S, "status": S, "project_id": I, "note": S}),
    "files": (EstFile, "project_id", {"category": S, "name": S}),
}
MONEY_LIMIT = 1e10


def _coerce(t, v, field):
    if t == S:
        return "" if v is None else str(v).strip()[:4000]
    if t == F:
        if v in (None, ""):
            return 0.0
        try:
            x = float(str(v).replace(",", ""))
        except ValueError:
            raise HTTPException(400, f"{field.replace('_', ' ')}: that is not a number.")
        if abs(x) > MONEY_LIMIT:
            raise HTTPException(400, f"{field.replace('_', ' ')}: that number is too big.")
        return round(x, 2)
    if t == I:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{field.replace('_', ' ')}: that is not a whole number.")
    if t == D:
        if not v:
            return None
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            raise HTTPException(400, f"{field.replace('_', ' ')}: that is not a date.")
    if t == B:
        return bool(v) and v not in ("0", "false", "False")
    return v


def _apply(row, fields, data):
    for k, v in (data or {}).items():
        if k in fields:
            setattr(row, k, _coerce(fields[k], v, k))


def _iso(d):
    return d.isoformat() if d else ""


def _plain(row, fields):
    out = {"id": row.id}
    for k, t in fields.items():
        v = getattr(row, k)
        out[k] = _iso(v) if t == D else (r2(v) if t == F else v)
    return out


def _uname(db, ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.query(models.User).filter(models.User.id.in_(ids)).all()}


# ---- the money --------------------------------------------------------------------------

def sub_revised(s, vos):
    return r2((s.value or 0) + sum(v.amount or 0 for v in vos) - (s.cancelled or 0))


def _auto_fill(pc, prev_adv_paid, adv_pct, ret_pct, work_key, base=0.0):
    """Advance recovery and retention to date, from the percentages - unless typed.
    With no advance % set, an advance that was paid is recovered pro rata to the
    value (advance / value of the work done), so it is all back at 100%."""
    work = getattr(pc, work_key) or 0
    adv_paid = prev_adv_paid + (pc.adv_amount or 0)
    if pc.adv_auto:
        pct = adv_pct or (100.0 * adv_paid / base if base else 0)
        pc.adv_rec_cum = r2(min(adv_paid, work * pct / 100.0)) if pct else r2(min(adv_paid, pc.adv_rec_cum or 0))
    if pc.ret_auto:
        pc.ret_cum = r2(work * (ret_pct or 0) / 100.0)


def chain(pcs, adv_pct, ret_pct, vat_pct, work_key="work_cum", fill=False, base=0.0):
    """Walk a subcontract's (or a project's) certificates in order and work out
    what each one certifies. With fill=True the automatic figures are set
    on the rows themselves (before saving)."""
    out, prev_net, adv_paid = [], 0.0, 0.0
    for pc in sorted(pcs, key=lambda p: (p.seq or 0, p.id or 0)):
        if fill:
            _auto_fill(pc, adv_paid, adv_pct, ret_pct, work_key, base)
        adv_paid = r2(adv_paid + (pc.adv_amount or 0))
        work = r2(getattr(pc, work_key))
        gross = r2(work + (pc.mos_cum or 0))
        net = r2(gross + adv_paid - (pc.adv_rec_cum or 0) - (pc.ret_cum or 0) + (pc.ret_rel_cum or 0) - (pc.other_cum or 0))
        this = r2(net - prev_net)
        vat = r2(this * (vat_pct or 0) / 100.0)
        out.append({"id": pc.id, "work": work, "gross": gross, "adv_paid_cum": adv_paid, "net_cum": net, "prev_net": r2(prev_net),
                    "this": this, "vat": vat, "payable": r2(this + vat)})
        prev_net = net
    return out


def _sub_bundle(db, s, vos, pcs, rules):
    revised = sub_revised(s, vos)
    calc = {c["id"]: c for c in chain(pcs, s.adv_pct, s.ret_pct, s.vat_pct)}
    pc_list = []
    t = today()
    for p in sorted(pcs, key=lambda p: (p.seq or 0, p.id)):
        d = _plain(p, KINDS["subpcs"][2])
        d.update(calc.get(p.id, {}))
        site_due = p.to_site + timedelta(days=rules["site_days"]) if p.to_site else None
        pc_due = p.received + timedelta(days=rules["pc_days"]) if p.received else None
        d["site_due"] = _iso(site_due)
        d["pc_due"] = _iso(pc_due)
        d["site_delay"] = max(0, ((p.site_back or t) - site_due).days) if site_due and p.to_site else 0
        d["pc_delay"] = max(0, ((p.issued or t) - pc_due).days) if pc_due else 0
        d["sub_id"] = s.id
        pc_list.append(d)
    certified = pc_list[-1]["net_cum"] if pc_list else 0.0
    last_work = pc_list[-1]["work"] if pc_list else 0.0
    paid = r2(sum(p.paid_amount or 0 for p in pcs))
    vat_certified = r2(sum(x["vat"] for x in pc_list))
    adv_paid = pc_list[-1]["adv_paid_cum"] if pc_list else 0.0
    last = sorted(pcs, key=lambda p: (p.seq or 0, p.id))[-1] if pcs else None
    out = _plain(s, KINDS["subs"][2])
    out.update({
        "vos": [_plain(v, KINDS["subvos"][2]) for v in sorted(vos, key=lambda v: (v.on_date or date.min, v.id))],
        "vo_total": r2(sum(v.amount or 0 for v in vos)), "revised": revised, "pcs": pc_list, "pc_count": len(pc_list),
        "work_done": last_work, "certified": certified, "paid": paid, "vat_certified": vat_certified,
        "payable_total": r2(certified + vat_certified),
        "to_pay": r2(certified + vat_certified - paid), "balance": r2(revised - last_work),
        "done_pct": round(100.0 * last_work / revised, 1) if revised else 0.0,
        "adv_paid": adv_paid, "adv_rec": r2(last.adv_rec_cum if last else 0), "adv_left": r2(adv_paid - (last.adv_rec_cum if last else 0)),
        "ret_held": r2(last.ret_cum if last else 0), "ret_released": r2(last.ret_rel_cum if last else 0),
        "ret_left": r2((last.ret_cum if last else 0) - (last.ret_rel_cum if last else 0)),
        "other": r2(last.other_cum if last else 0),
    })
    return out


def _client_bundle(p, pcs):
    calc = {c["id"]: c for c in chain(pcs, p.adv_pct, p.ret_pct, p.vat_pct, work_key="_work")}
    out = []
    for c in sorted(pcs, key=lambda c: (c.seq or 0, c.id)):
        d = _plain(c, KINDS["clientpcs"][2])
        d.update(calc.get(c.id, {}))
        out.append(d)
    return out


# The client certificate works on what was certified once the consultant has
# certified it, and on what was claimed until then.
EstClientPC._work = property(lambda self: (self.certified_cum if (self.certified_cum or 0) > 0 or self.status in ("Certified", "Invoiced", "Paid") else self.claimed_cum) or 0)


def _next_seq(db, model, **filt):
    q = db.query(func.max(model.seq))
    for k, v in filt.items():
        q = q.filter(getattr(model, k) == v)
    return (q.scalar() or 0) + 1


def _project(db, pid):
    p = db.query(EstProject).get(pid)
    if not p:
        raise HTTPException(404, "That project is not there any more.")
    return p


def _invoices_for(db, code):
    try:
        import accounts
        rows = db.query(accounts.Invoice).filter(accounts.Invoice.project_no == code).order_by(accounts.Invoice.inv_date).all()
        return [{"id": i.id, "kind": i.kind, "number": i.number, "date": _iso(i.inv_date), "client": i.client, "work": i.work,
                 "subtotal": r2(i.subtotal), "vat": r2(i.vat), "total": r2(i.total), "status": i.status} for i in rows]
    except Exception:
        return []


def _received_for(db, code):
    try:
        import projectpay
        scopes = db.query(projectpay.ProjectScope).filter(projectpay.ProjectScope.project == code).all()
        return r2(sum(sum(p.amount or 0 for p in s.payments) for s in scopes)), r2(sum(s.contract or 0 for s in scopes))
    except Exception:
        return 0.0, 0.0


def project_bundle(db, p, rules=None):
    rules = rules or _rules(db)
    subs = db.query(EstSub).filter(EstSub.project_id == p.id).order_by(EstSub.sort, EstSub.id).all()
    sids = [s.id for s in subs] or [-1]
    vos = db.query(EstSubVO).filter(EstSubVO.sub_id.in_(sids)).all()
    pcs = db.query(EstSubPC).filter(EstSubPC.sub_id.in_(sids)).all()
    sub_out = [_sub_bundle(db, s, [v for v in vos if v.sub_id == s.id], [c for c in pcs if c.sub_id == s.id], rules) for s in subs]
    cpcs = db.query(EstClientPC).filter(EstClientPC.project_id == p.id).all()
    vars_ = db.query(EstVariation).filter(EstVariation.project_id == p.id).order_by(EstVariation.seq).all()
    boq = db.query(EstBoq).filter(EstBoq.project_id == p.id).order_by(EstBoq.sort, EstBoq.id).all()
    logs = db.query(EstLog).filter(EstLog.project_id == p.id).order_by(EstLog.kind, EstLog.sort, EstLog.seq).all()
    finals = db.query(EstFinal).filter(EstFinal.project_id == p.id).order_by(EstFinal.sort, EstFinal.id).all()
    files = db.query(EstFile).filter(EstFile.project_id == p.id).order_by(EstFile.id.desc()).all()
    names = _uname(db, [f.created_by for f in files])
    client = _client_bundle(p, cpcs)
    received, pp_contract = _received_for(db, p.code)
    invoices = _invoices_for(db, p.code)
    approved_vo = r2(sum(v.approved_amount or 0 for v in vars_ if v.status == "Approved"))
    boq_value = r2(sum((b.qty or 0) * (b.rate or 0) for b in boq))
    boq_cost = r2(sum((b.qty or 0) * (b.cost_rate or 0) for b in boq))
    t = today()
    open_logs = [l for l in logs if l.status in ("Open", "Submitted", "Preparing", "Not started", "Revise & resubmit")]
    overdue = [l for l in open_logs if l.due and l.due < t and l.kind != "approval"]
    proj = _plain(p, KINDS["projects"][2])
    contract = p.contract_value or pp_contract or boq_value
    committed = r2(sum(s["revised"] for s in sub_out if s["status"] != "Cancelled"))
    sub_cert = r2(sum(s["certified"] for s in sub_out))
    sub_paid = r2(sum(s["paid"] for s in sub_out))
    # Only what the consultant has certified counts as certified; an advance counts once it is past draft.
    cert = [c for c in client if c["status"] in ("Certified", "Invoiced", "Paid") or (c["pc_type"] == "Advance" and c["status"] != "Draft")]
    summary = {
        "contract": r2(contract), "approved_vo": approved_vo, "revised": r2(contract + approved_vo),
        "client_certified": cert[-1]["net_cum"] if cert else 0.0,
        "client_work": cert[-1]["work"] if cert else 0.0,
        "client_claimed": client[-1]["net_cum"] if client else 0.0,
        "received": received, "invoiced": r2(sum(i["total"] for i in invoices if i["kind"] == "tax" and i["status"] != "cancelled")),
        "boq_value": boq_value, "boq_cost": boq_cost,
        "committed": committed, "sub_certified": sub_cert, "sub_paid": sub_paid,
        "sub_to_pay": r2(sum(s["to_pay"] for s in sub_out)),
        "margin": r2(contract + approved_vo - committed),
        "open_rfi": sum(1 for l in open_logs if l.kind == "rfi"),
        "open_submittals": sum(1 for l in open_logs if l.kind == "submittal"),
        "approvals_done": sum(1 for l in logs if l.kind == "approval" and l.status in ("Approved", "N/A")),
        "approvals_total": sum(1 for l in logs if l.kind == "approval"),
        "overdue": len(overdue),
        "finals_done": sum(1 for f in finals if f.st == "✔"), "finals_total": sum(1 for f in finals if f.sc not in ("N/A",)),
    }
    return {
        "project": proj, "summary": summary, "subs": sub_out,
        "clientpcs": client, "variations": [_plain(v, KINDS["variations"][2]) for v in vars_],
        "boq": [dict(_plain(b, KINDS["boq"][2]), amount=r2((b.qty or 0) * (b.rate or 0)), cost=r2((b.qty or 0) * (b.cost_rate or 0))) for b in boq],
        "logs": [_plain(l, KINDS["logs"][2]) for l in logs],
        "finals": [_plain(f, KINDS["finals"][2]) for f in finals],
        "files": [dict(_plain(f, KINDS["files"][2]), kind=f.kind, row_id=f.row_id, size=f.size, by=names.get(f.created_by, ""),
                       at=f.created_at.isoformat() if f.created_at else "", url=_file_url(f)) for f in files],
        "invoices": invoices, "rules": rules,
    }


# ---- endpoints: lists to pick from ------------------------------------------------------

@router.get("/store/est/meta")
def meta(db: Session = Depends(get_db), user: models.User = VIEW):
    perms = M.effective_permissions(user)
    projects = db.query(EstProject).order_by(EstProject.code).all()
    sites = db.query(models.Site).filter(models.Site.active == True).order_by(models.Site.code).all()   # noqa: E712
    sups = db.query(models.Supplier).filter(models.Supplier.active == True).order_by(models.Supplier.name).all()   # noqa: E712
    users = db.query(models.User).filter(models.User.active == True).order_by(models.User.full_name).all() if hasattr(models.User, "active") else db.query(models.User).order_by(models.User.full_name).all()  # noqa: E712
    names = {s.name for s in db.query(EstSub.name).distinct()}
    return {
        "projects": [{"id": p.id, "code": p.code, "name": p.name, "status": p.status, "client": p.client} for p in projects],
        "sites": [{"code": s.code, "name": s.project_name or "", "plot": s.plot_no or ""} for s in sites],
        "suppliers": [{"id": s.id, "name": s.name} for s in sups],
        "sub_names": sorted(n for n in names if n),
        "users": [{"id": u.id, "name": u.full_name} for u in users],
        "trades": TRADES, "scopes": SCOPES, "parties": PARTIES, "disciplines": DISCIPLINES, "doc_categories": DOC_CATEGORIES,
        "log_status": LOG_STATUS, "steps": SUB_STEPS, "rules": _rules(db),
        "me": {"id": user.id, "name": user.full_name, "admin": user.role == "admin",
               "accounts": "accounts_invoices" in perms, "boards": "estimation_boards" in perms},
        "today": today().isoformat(),
    }


@router.put("/store/est/rules")
def set_rules(data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    r = _rules(db)
    for k in DEFAULT_RULES:
        if k in data:
            try:
                r[k] = max(0, min(365, int(data[k])))
            except (TypeError, ValueError):
                raise HTTPException(400, "Days must be a whole number.")
    s = db.query(models.Setting).filter(models.Setting.key == RULES_KEY).first()
    if not s:
        s = models.Setting(key=RULES_KEY)
        db.add(s)
    s.value = json.dumps(r)
    db.commit()
    return r


# ---- the dashboard ------------------------------------------------------------------------

@router.get("/store/est/dash")
def dashboard(db: Session = Depends(get_db), user: models.User = VIEW):
    rules = _rules(db)
    rows, kpi = [], {"invoices": 0, "at_site": 0, "site_delays": 0, "pc_delays": 0, "preparing": 0, "issued": 0,
                     "with_accounts": 0, "with_accounts_amount": 0.0, "paid": 0}
    queue, late, matrix = [], [], []
    t = today()
    for p in db.query(EstProject).order_by(EstProject.code).all():
        b = project_bundle(db, p, rules)
        s = b["summary"]
        rows.append({"id": p.id, "code": p.code, "name": p.name, "status": p.status, "client": p.client, **s,
                     "subs": len(b["subs"]), "progress": round(100.0 * s["client_work"] / s["revised"], 1) if s["revised"] else 0.0})
        for sb in b["subs"]:
            for pc in sb["pcs"]:
                if pc["pc_type"] == "Advance" and not pc["inv_ref"] and not pc["received"]:
                    pass
                kpi["invoices"] += 1
                st = pc["status"]
                if st == "At site":
                    kpi["at_site"] += 1
                if pc["site_delay"]:
                    kpi["site_delays"] += 1
                if pc["pc_delay"]:
                    kpi["pc_delays"] += 1
                if st in ("Received", "Back from site", "Certified"):
                    kpi["preparing"] += 1
                if st == "PC issued":
                    kpi["issued"] += 1
                if st == "With Accounts":
                    kpi["with_accounts"] += 1
                    kpi["with_accounts_amount"] = r2(kpi["with_accounts_amount"] + pc["payable"])
                if st == "Paid":
                    kpi["paid"] += 1
                if st != "Paid":
                    item = {"project_id": p.id, "code": p.code, "sub_id": sb["id"], "sub": sb["name"], "scope": sb["scope"],
                            "pc_id": pc["id"], "seq": pc["seq"], "inv_ref": pc["inv_ref"], "status": st, "received": pc["received"],
                            "pc_due": pc["pc_due"], "site_delay": pc["site_delay"], "pc_delay": pc["pc_delay"],
                            "payable": pc["payable"], "this": pc["this"]}
                    queue.append(item)
        for l in b["logs"]:
            if l["status"] in ("Open", "Submitted", "Preparing", "Revise & resubmit") and l["due"] and l["due"] < t.isoformat() and l["kind"] != "approval":
                late.append({"project_id": p.id, "code": p.code, "kind": l["kind"], "id": l["id"], "no": f'{LOG_PREFIX.get(l["kind"], "")}-{l["seq"]:03d}',
                             "title": l["title"], "party": l["party"], "due": l["due"]})
        matrix.append({"id": p.id, "code": p.code, "finals": {f["item"]: f for f in b["finals"]}})
    tenders = db.query(EstTender).filter(EstTender.status.in_(["Received", "Pricing"])).order_by(EstTender.due).all()
    tot = {k: r2(sum(r[k] for r in rows)) for k in ("contract", "revised", "client_certified", "received", "invoiced", "committed",
                                                     "sub_certified", "sub_paid", "sub_to_pay")}
    queue.sort(key=lambda x: (x["pc_due"] or "9999", x["code"]))
    return {"projects": rows, "totals": tot, "kpi": kpi, "queue": queue[:200], "late": late[:100],
            "matrix": matrix, "final_items": FINAL_ITEMS,
            "tenders": [_plain(x, KINDS["tenders"][2]) for x in tenders], "rules": rules, "today": t.isoformat()}


# ---- projects -------------------------------------------------------------------------------

@router.get("/store/est/projects/{pid}")
def get_project(pid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    p = _project(db, pid)
    _seed_project(db, p, user)
    return project_bundle(db, p)


def _seed_project(db, p, user):
    """The standard approvals list and finalization log, put in once per project."""
    changed = False
    if not db.query(EstLog).filter(EstLog.project_id == p.id, EstLog.kind == "approval").first():
        for i, (g, title, party) in enumerate(APPROVALS):
            db.add(EstLog(project_id=p.id, kind="approval", seq=i + 1, group=g, title=title, party=party, status="Not started",
                          sort=i, created_by=user.id))
        changed = True
    if not db.query(EstFinal).filter(EstFinal.project_id == p.id).first():
        n = 0
        for sec, items in FINAL_ITEMS.items():
            for it in items:
                db.add(EstFinal(project_id=p.id, section=sec, item=it, sort=n, created_by=user.id))
                n += 1
        changed = True
    if changed:
        db.commit()


@router.post("/store/est/projects")
def add_project(data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    code = str(data.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Pick the project (site code).")
    if db.query(EstProject).filter(EstProject.code == code).first():
        raise HTTPException(400, f"Project {code} is already there - pick it from the list.")
    p = EstProject(created_by=user.id)
    _apply(p, KINDS["projects"][2], data)
    site = db.query(models.Site).filter(models.Site.code == code).first()
    if site and not p.name:
        p.name = site.project_name or ""
    if not p.contract_value:
        _, pp = _received_for(db, code)
        p.contract_value = pp
    db.add(p)
    db.commit()
    _seed_project(db, p, user)
    return {"id": p.id}


@router.delete("/store/est/projects/{pid}")
def del_project(pid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    p = _project(db, pid)
    if user.role != "admin":
        raise HTTPException(403, "Only an admin can remove a whole project.")
    sids = [s.id for s in db.query(EstSub).filter(EstSub.project_id == pid)]
    if sids:
        db.query(EstSubPC).filter(EstSubPC.sub_id.in_(sids)).delete(synchronize_session=False)
        db.query(EstSubVO).filter(EstSubVO.sub_id.in_(sids)).delete(synchronize_session=False)
    for m in (EstSub, EstClientPC, EstVariation, EstBoq, EstLog, EstFinal, EstFile):
        db.query(m).filter(m.project_id == pid).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    return {"ok": True}


def _parent_ok(db, kind, parent_id):
    model, parent, _ = KINDS[kind]
    if parent == "project_id":
        _project(db, parent_id)
    elif parent == "sub_id":
        if not db.query(EstSub).get(parent_id):
            raise HTTPException(404, "That subcontract is not there any more.")


def _sub_of(db, sid):
    s = db.query(EstSub).get(sid)
    if not s:
        raise HTTPException(404, "That subcontract is not there any more.")
    return s


def _refill_sub(db, sid):
    """Advance recovery and retention to date follow the work done, on every certificate of the subcontract."""
    s = _sub_of(db, sid)
    pcs = db.query(EstSubPC).filter(EstSubPC.sub_id == sid).all()
    vos = db.query(EstSubVO).filter(EstSubVO.sub_id == sid).all()
    chain(pcs, s.adv_pct, s.ret_pct, s.vat_pct, fill=True, base=sub_revised(s, vos))


def _refill_client(db, pid):
    p = _project(db, pid)
    pcs = db.query(EstClientPC).filter(EstClientPC.project_id == pid).all()
    chain(pcs, p.adv_pct, p.ret_pct, p.vat_pct, work_key="_work", fill=True, base=p.contract_value or 0)


def _check_pc(db, pc):
    if pc.work_cum < 0 or pc.mos_cum < 0:
        raise HTTPException(400, "Work done and material on site cannot be below zero.")
    s = _sub_of(db, pc.sub_id)
    vos = db.query(EstSubVO).filter(EstSubVO.sub_id == s.id).all()
    rev = sub_revised(s, vos)
    if rev and pc.work_cum > rev * 1.5 + 1:
        raise HTTPException(400, f"Work done to date ({pc.work_cum:,.2f}) is far above the revised subcontract value ({rev:,.2f}). Check the figure.")


@router.post("/store/est/{kind}")
def add_row(kind: str, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    if kind not in KINDS or kind == "projects":
        raise HTTPException(404, "Unknown list.")
    model, parent, fields = KINDS[kind]
    row = model(created_by=user.id)
    if parent:
        pid = data.get(parent)
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            raise HTTPException(400, "Which project / subcontract is this for?")
        _parent_ok(db, kind, pid)
        setattr(row, parent, pid)
    _apply(row, fields, data)
    for k, ty in fields.items():      # the table's defaults, before anything is worked out
        if getattr(row, k) is None and ty in (F, B, S):
            col = model.__table__.columns[k]
            dv = col.default.arg if col.default is not None and not callable(col.default.arg) else None
            setattr(row, k, dv if dv is not None else (True if ty == B else 0.0 if ty == F else ""))
    t = today()
    if kind == "subs":
        if not row.name and row.supplier_id:
            sup = db.query(models.Supplier).get(row.supplier_id)
            row.name = sup.name if sup else ""
        if not row.name:
            raise HTTPException(400, "Pick the subcontractor.")
        row.sort = (db.query(func.max(EstSub.sort)).filter(EstSub.project_id == row.project_id).scalar() or 0) + 1
    elif kind == "subpcs":
        prev = db.query(EstSubPC).filter(EstSubPC.sub_id == row.sub_id).order_by(EstSubPC.seq.desc(), EstSubPC.id.desc()).first()
        if not data.get("seq"):
            row.seq = (prev.seq if prev else 0) + 1
        if prev:   # to-date figures carry on from the last certificate until changed
            for k in ("work_cum", "mos_cum", "ret_rel_cum", "other_cum"):
                if k not in data:
                    setattr(row, k, getattr(prev, k) or 0)
            if "other_note" not in data:
                row.other_note = prev.other_note or ""
            for k in ("adv_rec_cum", "ret_cum"):
                if k not in data:
                    setattr(row, k, getattr(prev, k) or 0)
            for k in ("adv_auto", "ret_auto"):
                if k not in data:
                    setattr(row, k, getattr(prev, k))
        if row.received is None and "received" not in data:
            row.received = t
        if not row.status:
            row.status = "Received"
        if row.pc_type == "Advance" and not row.adv_amount:
            s = _sub_of(db, row.sub_id)
            row.adv_amount = r2((s.value or 0) * (s.adv_pct or 0) / 100.0)
        _check_pc(db, row)
    elif kind == "clientpcs":
        prev = db.query(EstClientPC).filter(EstClientPC.project_id == row.project_id).order_by(EstClientPC.seq.desc()).first()
        if not data.get("seq"):
            row.seq = (prev.seq if prev else 0) + 1
        if prev:
            for k in ("claimed_cum", "mos_cum", "ret_rel_cum", "other_cum", "adv_rec_cum", "ret_cum"):
                if k not in data:
                    setattr(row, k, getattr(prev, k) or 0)
        if row.pc_type == "Advance" and not row.adv_amount:
            p = _project(db, row.project_id)
            row.adv_amount = r2((p.contract_value or 0) * (p.adv_pct or 0) / 100.0)
        row.status = row.status or "Draft"
        if row.period_to is None:
            row.period_to = t
    elif kind == "variations":
        if not data.get("seq"):
            row.seq = _next_seq(db, EstVariation, project_id=row.project_id)
        if row.on_date is None:
            row.on_date = t
        if not row.title:
            raise HTTPException(400, "What is the variation for?")
    elif kind == "logs":
        if row.kind not in LOG_STATUS:
            raise HTTPException(400, "Unknown log.")
        if not data.get("seq"):
            row.seq = _next_seq(db, EstLog, project_id=row.project_id, kind=row.kind)
        if not row.status:
            row.status = LOG_STATUS[row.kind][0]
        if row.sent is None and "sent" not in data and row.kind in ("rfi", "submittal"):
            row.sent = t
        if row.due is None and row.sent and row.kind in ("rfi", "submittal"):
            row.due = row.sent + timedelta(days=_rules(db)["rfi_days" if row.kind == "rfi" else "submittal_days"])
        row.sort = (db.query(func.max(EstLog.sort)).filter(EstLog.project_id == row.project_id, EstLog.kind == row.kind).scalar() or 0) + 1
    elif kind == "tenders":
        if not data.get("seq"):
            row.seq = _next_seq(db, EstTender)
        if row.received is None and "received" not in data:
            row.received = t
        if not row.name:
            raise HTTPException(400, "Name the tender.")
    elif kind == "finals":
        row.sort = (db.query(func.max(EstFinal.sort)).filter(EstFinal.project_id == row.project_id).scalar() or 0) + 1
    elif kind == "boq":
        row.sort = (db.query(func.max(EstBoq.sort)).filter(EstBoq.project_id == row.project_id).scalar() or 0) + 1
    db.add(row)
    db.flush()
    if kind in ("subpcs", "subvos"):
        _refill_sub(db, row.sub_id)
    if kind == "clientpcs":
        _refill_client(db, row.project_id)
    db.commit()
    return {"id": row.id}


@router.patch("/store/est/{kind}/{rid}")
def edit_row(kind: str, rid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    if kind not in KINDS:
        raise HTTPException(404, "Unknown list.")
    model, parent, fields = KINDS[kind]
    row = db.query(model).get(rid)
    if not row:
        raise HTTPException(404, "That line is not there any more.")
    if kind == "subpcs" and row.status == "Paid" and any(k in data for k in ("work_cum", "mos_cum", "adv_amount", "adv_rec_cum", "ret_cum", "ret_rel_cum", "other_cum")) and user.role != "admin":
        raise HTTPException(400, "This certificate is paid - its figures are locked. Ask an admin if it must change.")
    # A typed advance recovery / retention switches its automatic figure off.
    if kind in ("subpcs", "clientpcs"):
        if "adv_rec_cum" in data and "adv_auto" not in data:
            data["adv_auto"] = False
        if "ret_cum" in data and "ret_auto" not in data:
            data["ret_auto"] = False
    _apply(row, fields, data)
    row.updated_by = user.id
    if kind == "subpcs":
        _check_pc(db, row)
        db.flush()
        _refill_sub(db, row.sub_id)
    elif kind == "subs":
        db.flush()
        _refill_sub(db, row.id)
    elif kind == "subvos":
        db.flush()
        _refill_sub(db, row.sub_id)
    elif kind == "clientpcs":
        db.flush()
        _refill_client(db, row.project_id)
    elif kind == "projects":
        db.flush()
        _refill_client(db, row.id)
    db.commit()
    return {"ok": True}


@router.delete("/store/est/{kind}/{rid}")
def del_row(kind: str, rid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    if kind not in KINDS or kind == "projects":
        raise HTTPException(404, "Unknown list.")
    model, parent, fields = KINDS[kind]
    row = db.query(model).get(rid)
    if not row:
        return {"ok": True}
    if kind == "subpcs" and row.status == "Paid" and user.role != "admin":
        raise HTTPException(400, "A paid certificate cannot be removed. Ask an admin.")
    if kind == "subs":
        if db.query(EstSubPC).filter(EstSubPC.sub_id == rid, EstSubPC.status == "Paid").first() and user.role != "admin":
            raise HTTPException(400, "This subcontract has paid certificates - only an admin can remove it.")
        db.query(EstSubPC).filter(EstSubPC.sub_id == rid).delete(synchronize_session=False)
        db.query(EstSubVO).filter(EstSubVO.sub_id == rid).delete(synchronize_session=False)
    if kind == "files":
        try:
            os.remove(os.path.join(FILES, row.stored))
        except OSError:
            pass
    sid = getattr(row, "sub_id", None) if kind == "subpcs" else None
    pid = row.project_id if kind == "clientpcs" else None
    db.delete(row)
    db.flush()
    if sid:
        _refill_sub(db, sid)
    if kind == "subvos":
        _refill_sub(db, row.sub_id)
    if pid:
        _refill_client(db, pid)
    db.commit()
    return {"ok": True}


# ---- one click: the next step of an invoice ------------------------------------------------

STEP_DATE = {"At site": "to_site", "Back from site": "site_back", "Certified": "certified_on", "PC issued": "issued",
             "With Accounts": "to_accounts", "Paid": "paid_on", "Received": "received"}


@router.post("/store/est/subpcs/{rid}/step")
def pc_step(rid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = PAYER):
    pc = db.query(EstSubPC).get(rid)
    if not pc:
        raise HTTPException(404, "That invoice is not there any more.")
    step = data.get("step")
    if step not in SUB_STEPS:
        raise HTTPException(400, "Unknown step.")
    perms = M.effective_permissions(user)
    if RIGHT not in perms and step not in ("Paid", "With Accounts"):
        raise HTTPException(403, "Accounts can only mark a certificate paid.")
    on = _coerce(D, data.get("date"), "date") or today()
    s = _sub_of(db, pc.sub_id)
    if step == "Paid":
        calc = {c["id"]: c for c in chain(db.query(EstSubPC).filter(EstSubPC.sub_id == s.id).all(), s.adv_pct, s.ret_pct, s.vat_pct)}
        amt = data.get("amount")
        pc.paid_amount = _coerce(F, amt, "amount") if amt not in (None, "") else calc[pc.id]["payable"]
        pc.paid_ref = str(data.get("ref") or pc.paid_ref or "")[:200]
        if not pc.issued:
            pc.issued = on
    if step in ("Certified", "PC issued", "With Accounts") and not pc.certified_on:
        pc.certified_on = on
    if step in ("PC issued", "With Accounts") and not pc.issued:
        pc.issued = on
    setattr(pc, STEP_DATE[step], on)
    if data.get("undo"):
        # Back one step: the date of the step undone is cleared.
        i = SUB_STEPS.index(step)
        setattr(pc, STEP_DATE[step], None)
        if step == "Paid":
            pc.paid_amount = 0.0
        step = SUB_STEPS[i - 1] if i else "Received"
    pc.status = step
    pc.updated_by = user.id
    db.commit()
    return {"ok": True, "status": pc.status}


# ---- BOQ pasted from Excel --------------------------------------------------------------

@router.post("/store/est/projects/{pid}/boq-paste")
def boq_paste(pid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """Lines copied straight out of Excel: item, description, unit, qty, rate
    (tab-separated). A line with only a description becomes the section heading."""
    _project(db, pid)
    text = str(data.get("text") or "")
    section, n, added = str(data.get("section") or ""), 0, 0
    base = db.query(func.max(EstBoq.sort)).filter(EstBoq.project_id == pid).scalar() or 0

    def num(x):
        x = (x or "").replace(",", "").replace("AED", "").strip()
        try:
            return round(float(x), 4)
        except ValueError:
            return None
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("\t")]
        if not any(cells):
            continue
        while len(cells) < 6:
            cells.append("")
        nums = [num(c) for c in cells]
        # Find the description: the longest text cell.
        texts = [(len(c), i) for i, c in enumerate(cells) if c and nums[i] is None]
        if not texts:
            continue
        di = max(texts)[1]
        after = [nums[i] for i in range(di + 1, len(cells)) if nums[i] is not None]
        unit = next((cells[i] for i in range(di + 1, len(cells)) if cells[i] and nums[i] is None and len(cells[i]) <= 8), "")
        code = cells[0] if di > 0 else ""
        if not after:
            section = cells[di][:200]
            continue
        qty = after[0] if len(after) >= 1 else 0
        rate = after[1] if len(after) >= 2 else 0
        n += 1
        db.add(EstBoq(project_id=pid, section=section, code=code[:40], description=cells[di][:1000], unit=unit, qty=qty or 0,
                      rate=rate or 0, sort=base + n, created_by=user.id))
        added += 1
    if not added:
        raise HTTPException(400, "Nothing to add - copy the BOQ lines from Excel (description, unit, quantity, rate) and paste them here.")
    db.commit()
    return {"added": added}


# ---- tenders -------------------------------------------------------------------------------

@router.get("/store/est/tenders")
def tenders(db: Session = Depends(get_db), user: models.User = VIEW):
    rows = db.query(EstTender).order_by(EstTender.seq.desc()).all()
    return {"tenders": [_plain(x, KINDS["tenders"][2]) for x in rows], "today": today().isoformat()}


@router.post("/store/est/tenders/{tid}/won")
def tender_won(tid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    t = db.query(EstTender).get(tid)
    if not t:
        raise HTTPException(404, "That tender is not there any more.")
    code = str(data.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Pick the project code it becomes.")
    p = db.query(EstProject).filter(EstProject.code == code).first()
    if not p:
        p = EstProject(code=code, name=t.name, client=t.client, consultant=t.consultant, location=t.location,
                       contract_value=t.value or 0, created_by=user.id, start_date=today())
        db.add(p)
        db.flush()
    t.status, t.project_id = "Won", p.id
    db.commit()
    _seed_project(db, p, user)
    return {"project_id": p.id}


# ---- files ---------------------------------------------------------------------------------

def _sign(fid, exp):
    return hmac.new(auth.SECRET_KEY.encode(), f"est:{fid}:{exp}".encode(), hashlib.sha256).hexdigest()[:24]


def _file_url(f):
    exp = int(time.time()) + 2 * 86400
    exp -= exp % 3600        # the same link for an hour, so the browser can keep it
    safe = re.sub(r"[^\w.\-]+", "_", f.name or "file")[:80] or "file"
    return f"/export/est/f/{f.id}/{exp}/{_sign(f.id, exp)}/{safe}"


@router.post("/store/est/files/upload")
async def upload(project_id: int = Form(0), kind: str = Form("doc"), row_id: int = Form(0), category: str = Form(""),
                 file: UploadFile = File(...), db: Session = Depends(get_db), user: models.User = VIEW):
    if project_id:
        _project(db, project_id)
    data = await file.read()
    if len(data) > MAX_FILE:
        raise HTTPException(413, "That file is over 25 MB.")
    os.makedirs(FILES, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1][:10].lower()
    stored = uuid.uuid4().hex + ext
    with open(os.path.join(FILES, stored), "wb") as fh:
        fh.write(data)
    f = EstFile(project_id=project_id or None, kind=kind[:20], row_id=row_id or None, name=(file.filename or "file")[:200],
                stored=stored, size=len(data), category=category[:60], created_by=user.id)
    db.add(f)
    db.commit()
    return {"id": f.id, "url": _file_url(f), "name": f.name}


@router.get("/export/est/f/{fid}/{exp}/{sig}/{name}")
def serve_file(fid: int, exp: int, sig: str, name: str, db: Session = Depends(get_db)):
    if not hmac.compare_digest(sig, _sign(fid, exp)) or exp < time.time():
        raise HTTPException(403, "This link has run out - open the project again.")
    f = db.query(EstFile).get(fid)
    if not f:
        raise HTTPException(404, "That file is not there any more.")
    path = os.path.join(FILES, f.stored)
    if not os.path.exists(path):
        raise HTTPException(404, "That file is not there any more.")
    inline = os.path.splitext(f.name or "")[1].lower() in (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt")
    return FileResponse(path, filename=f.name, content_disposition_type="inline" if inline else "attachment",
                        headers={"Cache-Control": "private, max-age=3600"})


# ---- Preview / PDF / Excel ---------------------------------------------------------------

def _m(x):
    return r2(x)


def _d(s):
    if not s:
        return ""
    try:
        return date.fromisoformat(s[:10]).strftime("%d-%b-%y")
    except ValueError:
        return s


def _export_rows(db, what, p, q, status, sub_id):
    """The rows behind each Preview / PDF / Excel, with the screen's filters."""
    b = project_bundle(db, p) if p else None
    ql = (q or "").lower()

    def keep(row, st=None):
        if status and (st or "") != status:
            return False
        return not ql or ql in " ".join(str(v) for v in row.values()).lower()
    rows, money, title, totals = [], [], "", None
    if what == "subs":
        title = "Subcontractors - summary"
        money = ["Initial", "Variation", "Cancelled", "Revised", "Certified", "Paid", "To pay", "Retention held", "Advance left", "Balance work"]
        for i, s in enumerate(b["subs"], 1):
            r = {"Sl.": i, "Subcontractor": s["name"], "Work": s["scope"], "Agreement / LPO": " / ".join(x for x in (s["agreement"], s["lpo"]) if x),
                 "PCs": s["pc_count"], "Initial": s["value"], "Variation": s["vo_total"], "Cancelled": s["cancelled"], "Revised": s["revised"],
                 "Certified": s["certified"], "Paid": s["paid"], "To pay": s["to_pay"], "Retention held": s["ret_left"],
                 "Advance left": s["adv_left"], "Balance work": s["balance"], "Done %": s["done_pct"], "Status": s["status"]}
            if keep(r, s["status"]):
                rows.append(r)
    elif what == "subpcs":
        s = next((x for x in b["subs"] if x["id"] == sub_id), None)
        if not s:
            raise HTTPException(404, "That subcontract is not there any more.")
        title = f"{s['name']} - payment certificates"
        totals = ["This certificate", "VAT", "Payable", "Paid"]      # the rest are to-date figures: never added up
        money = ["Invoice amount", "Work done to date", "Material on site", "Advance paid", "Adv. recovery", "Retention",
                 "Other ded.", "Ret. released", "Net to date", "This certificate", "VAT", "Payable", "Paid"]
        for pc in s["pcs"]:
            r = {"PC No.": f"PC No. {pc['seq']:02d}" + (f" ({pc['pc_type']})" if pc["pc_type"] != "Interim" else ""),
                 "Invoice": pc["inv_ref"], "Inv. date": _d(pc["inv_date"]), "Invoice amount": pc["inv_amount"],
                 "Work done to date": pc["work_cum"], "Material on site": pc["mos_cum"], "Advance paid": pc["adv_paid_cum"],
                 "Adv. recovery": r2(-pc["adv_rec_cum"]), "Retention": r2(-pc["ret_cum"]), "Other ded.": r2(-pc["other_cum"]),
                 "Ret. released": pc["ret_rel_cum"], "Net to date": pc["net_cum"], "This certificate": pc["this"],
                 "VAT": pc["vat"], "Payable": pc["payable"], "Paid": pc["paid_amount"], "Status": pc["status"],
                 "Remarks": " ".join(x for x in (pc["other_note"], pc["remarks"]) if x)}
            if keep(r, pc["status"]):
                rows.append(r)
    elif what == "invoices":
        title = "Subcontractor invoice tracker"
        totals = ["This certificate", "Payable"]
        money = ["Invoice amount", "This certificate", "Payable"]
        for s in b["subs"]:
            for pc in s["pcs"]:
                r = {"Subcontractor": s["name"], "PC No.": pc["seq"], "Invoice ref.": pc["inv_ref"],
                     "Invoice amount": pc["inv_amount"], "Received": _d(pc["received"]), "Back from site": _d(pc["site_back"]),
                     "Site delay": f"{pc['site_delay']} days" if pc["site_delay"] else "Nil", "PC due": _d(pc["pc_due"]),
                     "PC issued": _d(pc["issued"]), "PC delay": f"{pc['pc_delay']} days" if pc["pc_delay"] else "Nil",
                     "This certificate": pc["this"], "Payable": pc["payable"], "Status": pc["status"]}
                if keep(r, pc["status"]):
                    rows.append(r)
    elif what == "clientpcs":
        title = "Payment certificates to the consultant"
        totals = ["This certificate", "VAT", "Total"]
        money = ["Claimed to date", "Certified to date", "Material on site", "Advance", "Adv. recovery", "Retention",
                 "Ret. released", "Other ded.", "Net to date", "This certificate", "VAT", "Total"]
        for c in b["clientpcs"]:
            r = {"PC No.": c["seq"], "Type": c["pc_type"], "Period to": _d(c["period_to"]), "Submitted": _d(c["submitted"]),
                 "Claimed to date": c["claimed_cum"], "Certified to date": c["certified_cum"], "Material on site": c["mos_cum"],
                 "Advance": c["adv_paid_cum"], "Adv. recovery": r2(-c["adv_rec_cum"]), "Retention": r2(-c["ret_cum"]),
                 "Ret. released": c["ret_rel_cum"], "Other ded.": r2(-c["other_cum"]), "Net to date": c["net_cum"],
                 "This certificate": c["this"], "VAT": c["vat"], "Total": c["payable"], "Certified on": _d(c["certified_on"]),
                 "Invoice": c["invoice_no"], "Status": c["status"]}
            if keep(r, c["status"]):
                rows.append(r)
    elif what == "variations":
        title = "Variation log"
        money = ["Submitted amount", "Approved amount"]
        for v in b["variations"]:
            sub = next((s["name"] for s in b["subs"] if s["id"] == v["sub_id"]), "")
            r = {"VO No.": f"VO-{v['seq']:03d}", "Description": v["title"], "Type": v["kind"], "Source": v["source"], "Ref.": v["ref"],
                 "Date": _d(v["on_date"]), "Submitted": _d(v["submitted"]), "Submitted amount": v["submitted_amount"],
                 "Approved on": _d(v["approved_on"]), "Approved amount": v["approved_amount"], "Subcontractor": sub, "Status": v["status"]}
            if keep(r, v["status"]):
                rows.append(r)
    elif what == "boq":
        title = "BOQ & budget"
        totals = ["Amount", "Budget cost", "Margin"]
        money = ["Rate", "Amount", "Cost rate", "Budget cost", "Margin"]
        for x in b["boq"]:
            r = {"Section": x["section"], "Item": x["code"], "Description": x["description"], "Unit": x["unit"], "Qty": x["qty"],
                 "Rate": x["rate"], "Amount": x["amount"], "Cost rate": x["cost_rate"], "Budget cost": x["cost"],
                 "Margin": r2(x["amount"] - x["cost"]), "Done %": x["done_pct"]}
            if keep(r):
                rows.append(r)
    elif what in LOG_STATUS:
        title = {"rfi": "RFI log", "approval": "NOCs & approvals", "submittal": "Submittal log", "doc": "Document register"}[what]
        for l in b["logs"]:
            if l["kind"] != what:
                continue
            r = {"No.": f"{LOG_PREFIX[what]}-{l['seq']:03d}"}
            if what == "approval":
                r.update({"Stage": l["group"], "Item": l["title"], "Authority": l["party"], "Submitted": _d(l["sent"]),
                          "Approved": _d(l["replied"]), "Ref.": l["ref"], "Status": l["status"], "Note": l["note"]})
            else:
                r.update({"Subject": l["title"], "To / from": l["party"], "Discipline": l["discipline"], "Ref.": l["ref"], "Rev.": l["rev"],
                          "Sent": _d(l["sent"]), "Due": _d(l["due"]), "Reply": _d(l["replied"]), "Status": l["status"], "Note": l["note"]})
            if keep(r, l["status"]):
                rows.append(r)
    elif what == "finals":
        title = "Subcontractors' finalization log"
        for f in b["finals"]:
            sub = next((s["name"] for s in b["subs"] if s["id"] == f["sub_id"]), "")
            r = {"Section": f["section"], "Item": f["item"], "Scope": f["sc"], "Rate finalized": f["rt"], "Shop drawing": f["sd"],
                 "Material approval": f["ma"], "Authority approval": f["aa"], "Status": f["st"], "Subcontractor": sub, "Note": f["note"]}
            if keep(r, f["st"]):
                rows.append(r)
    elif what == "tenders":
        title = "Tenders"
        money = ["Value"]
        for t in db.query(EstTender).order_by(EstTender.seq).all():
            r = {"No.": f"T-{t.seq:03d}", "Tender": t.name, "Client": t.client, "Consultant": t.consultant, "Location": t.location,
                 "Type": t.kind, "Received": _d(_iso(t.received)), "Due": _d(_iso(t.due)), "Submitted": _d(_iso(t.submitted)),
                 "Value": r2(t.value), "Estimator": t.estimator, "Status": t.status}
            if keep(r, t.status):
                rows.append(r)
    elif what == "dash":
        title = "Estimation - all projects"
        money = ["Contract", "Revised", "Certified (client)", "Received", "Committed", "Sub certified", "Sub paid", "Sub to pay"]
        d = dashboard(db, None)
        for x in d["projects"]:
            r = {"Project": x["code"], "Name": x["name"], "Client": x["client"], "Status": x["status"], "Contract": x["contract"],
                 "Revised": x["revised"], "Certified (client)": x["client_certified"], "Received": x["received"],
                 "Progress %": x["progress"], "Committed": x["committed"], "Sub certified": x["sub_certified"],
                 "Sub paid": x["sub_paid"], "Sub to pay": x["sub_to_pay"], "Open RFIs": x["open_rfi"], "Overdue": x["overdue"]}
            if keep(r, x["status"]):
                rows.append(r)
    else:
        raise HTTPException(404, "Unknown report.")
    return title, rows, money, (money if totals is None else totals)


@router.get("/export/est/{what}")
def export(what: str, token: str, format: str = "excel", pid: int = 0, q: str = "", status: str = "", sub_id: int = 0,
           db: Session = Depends(get_db)):
    import export_web
    from urllib.parse import urlencode
    u = auth.get_download_user_from_token(token, db)
    if RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Estimation only.")
    p = _project(db, pid) if pid else None
    if what not in ("tenders", "dash") and not p:
        raise HTTPException(400, "Pick a project first.")
    title, rows, money, totals = _export_rows(db, what, p, q, status, sub_id)
    # A column that is empty or nought on every line only takes room from the others.
    if len(rows) > 0:
        def blank(v):
            return v in (None, "", "-", 0, 0.0, "Nil")
        keep = [k for k in rows[0] if not all(blank(r.get(k)) for r in rows)]
        if keep and len(keep) < len(rows[0]):
            rows = [{k: r[k] for k in keep} for r in rows]
            money = [m for m in money if m in keep]
            totals = [m for m in totals if m in keep]
    full = f"{p.code} {p.name} - {title}".strip() if p else title
    bits = [f"{len(rows)} lines", f"As at {today():%d %b %Y}"]
    if status:
        bits.append(status)
    if q:
        bits.append(f'"{q}"')
    sub = " | ".join(bits)
    if not rows:
        rows = [{"": "Nothing to show for these filters"}]
    if format == "preview":
        url = f"/export/est/{what}?" + urlencode({"token": token, "pid": pid, "q": q, "status": status, "sub_id": sub_id})
        return M._preview_page(full, sub, rows, url + "&format=pdf", url + "&format=excel", money_cols=money, total_cols=totals)
    safe = re.sub(r"[^\w]+", "_", full)[:60] or "estimation"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(full, rows, sub, money_cols=money, orientation="landscape", total_cols=totals),
                                 media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={safe}.pdf"})
    return StreamingResponse(export_web.build_store_report_excel(full, rows, sub, money_cols=money, total_cols=totals),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={safe}.xlsx"})


# ---- the payment certificate itself, printed ----------------------------------------------

def _pc_lines(db, pc_id):
    pc = db.query(EstSubPC).get(pc_id)
    if not pc:
        raise HTTPException(404, "That certificate is not there any more.")
    s = _sub_of(db, pc.sub_id)
    p = _project(db, s.project_id)
    vos = db.query(EstSubVO).filter(EstSubVO.sub_id == s.id).all()
    pcs = db.query(EstSubPC).filter(EstSubPC.sub_id == s.id).all()
    calc = {c["id"]: c for c in chain(pcs, s.adv_pct, s.ret_pct, s.vat_pct)}
    c = calc[pc.id]
    prev = [x for x in sorted(pcs, key=lambda x: (x.seq or 0, x.id)) if (x.seq or 0, x.id) < (pc.seq or 0, pc.id)]
    pv = prev[-1] if prev else None
    pvc = calc[pv.id] if pv else {"gross": 0, "adv_paid_cum": 0, "net_cum": 0}

    def trio(label, now, before):
        return (label, r2(before), r2(now - before), r2(now))
    lines = [
        trio("Value of work done", pc.work_cum or 0, pv.work_cum if pv else 0),
        trio("Material on site", pc.mos_cum or 0, pv.mos_cum if pv else 0),
        trio("Advance payment", c["adv_paid_cum"], pvc["adv_paid_cum"]),
        trio("Less advance recovery", -(pc.adv_rec_cum or 0), -(pv.adv_rec_cum if pv else 0)),
        trio("Less retention", -(pc.ret_cum or 0), -(pv.ret_cum if pv else 0)),
        trio("Add release of retention", pc.ret_rel_cum or 0, pv.ret_rel_cum if pv else 0),
        trio("Less other deductions" + (f" ({pc.other_note})" if pc.other_note else ""), -(pc.other_cum or 0), -(pv.other_cum if pv else 0)),
    ]
    lines.append(("Net amount", r2(pvc["net_cum"]), c["this"], c["net_cum"]))
    return pc, s, p, sub_revised(s, vos), lines, c


@router.get("/export/est/pc/{pc_id}")
def pc_print(pc_id: int, token: str, format: str = "preview", db: Session = Depends(get_db)):
    import export_web
    u = auth.get_download_user_from_token(token, db)
    if not ({RIGHT, "accounts_bank"} & set(M.effective_permissions(u))):
        raise HTTPException(status_code=403, detail="Estimation only.")
    pc, s, p, revised, lines, c = _pc_lines(db, pc_id)
    title = f"Payment Certificate No. {pc.seq:02d}" + (f" ({pc.pc_type})" if pc.pc_type != "Interim" else "")
    head = [("Project", f"{p.code} {p.name}".strip()), ("Subcontractor", s.name), ("Scope of work", s.scope),
            ("Agreement / LPO", " / ".join(x for x in (s.agreement, s.lpo) if x) or "-"),
            ("Subcontract value", f"AED {r2(s.value):,.2f}"), ("Revised value", f"AED {revised:,.2f}"),
            ("Invoice", f"{pc.inv_ref or '-'}" + (f" dated {pc.inv_date:%d-%b-%Y}" if pc.inv_date else "")),
            ("Date", f"{(pc.issued or today()):%d-%b-%Y}")]
    if format == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
        st = getSampleStyleSheet()
        el = []
        try:
            el.append(export_web._logo_image(width_mm=60))
        except Exception:
            pass
        el += [Spacer(1, 4 * mm), Paragraph(f"<b>{title}</b>", st["Title"]), Spacer(1, 2 * mm)]
        t = Table([[a, b] for a, b in head], colWidths=[45 * mm, 133 * mm])
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6B7178")),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        el += [t, Spacer(1, 5 * mm)]
        data = [["", "Previous (AED)", "This certificate (AED)", "To date (AED)"]] + [[a, f"{b:,.2f}", f"{cc:,.2f}", f"{d:,.2f}"] for a, b, cc, d in lines]
        data += [["VAT %g%%" % (s.vat_pct or 0), "", f"{c['vat']:,.2f}", ""], ["Amount payable", "", f"{c['payable']:,.2f}", ""]]
        t = Table(data, colWidths=[70 * mm, 36 * mm, 36 * mm, 36 * mm])
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B7322A")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                               ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D5D9DE")),
                               ("FONTNAME", (0, -3), (-1, -3), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                               ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FDF0EE"))]))
        el += [t, Spacer(1, 18 * mm)]
        sig = Table([["Prepared by (QS)", "Checked by", "Approved by"], ["", "", ""]], colWidths=[59 * mm] * 3, rowHeights=[6 * mm, 16 * mm])
        sig.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 1), (-1, 1), .6, colors.black)]))
        el.append(sig)
        doc.build(el)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f"inline; filename=PC_{pc.seq:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', s.name)[:30]}.pdf"})
    from html import escape
    logo = export_web.logo_data_uri()
    rows = "".join(f"<tr{' class=t' if a == 'Net amount' else ''}><td>{escape(a)}</td><td>{b:,.2f}</td><td>{cc:,.2f}</td><td>{d:,.2f}</td></tr>" for a, b, cc, d in lines)
    hd = "".join(f"<tr><th>{escape(a)}</th><td>{escape(str(b))}</td></tr>" for a, b in head)
    pdf = f"/export/est/pc/{pc_id}?token={token}&format=pdf"
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#F1EFEA;margin:0;color:#22262A}}
.bar{{position:sticky;top:0;background:#22262A;color:#fff;padding:10px 16px;display:flex;gap:8px;align-items:center}}
.bar b{{flex:1}} .bar a,.bar button{{background:#C0392B;color:#fff;border:0;border-radius:6px;padding:7px 12px;font-weight:600;text-decoration:none;font-size:13px;cursor:pointer}}
.pg{{background:#fff;max-width:780px;margin:18px auto;padding:28px 34px;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
h1{{text-align:center;font-size:19px;margin:10px 0 16px}} .hd th{{text-align:left;color:#6B7178;font-weight:500;padding:3px 14px 3px 0;width:170px}}
.hd td{{padding:3px 0}} table{{border-collapse:collapse;width:100%;font-size:13px}}
.m{{margin-top:18px}} .m th{{background:#B7322A;color:#fff;padding:7px;text-align:right}} .m th:first-child{{text-align:left}}
.m td{{border:1px solid #E1E4E8;padding:6px 8px;text-align:right}} .m td:first-child{{text-align:left}}
.m tr.t td,.m tr.p td{{font-weight:700}} .m tr.p td{{background:#FDF0EE}}
.sig{{display:flex;gap:30px;margin-top:60px}} .sig div{{flex:1;border-top:1px solid #333;padding-top:6px;font-size:12px;color:#555}}
@media print{{.bar{{display:none}} body{{background:#fff}} .pg{{box-shadow:none;margin:0;max-width:none}}}}
@media (max-width:600px){{.pg{{padding:16px}} .m{{font-size:11.5px}}}}
</style></head><body><div class="bar"><b>{escape(title)}</b><button onclick="print()">Print</button><a href="{pdf}">PDF</a><button onclick="shr()">Share</button></div>
<script>async function shr(){{try{{const r=await fetch("{pdf}");const b=await r.blob();const f=new File([b],"{escape(re.sub(r'[^A-Za-z0-9]+', '_', title))}.pdf",{{type:"application/pdf"}});if(navigator.canShare&&navigator.canShare({{files:[f]}}))await navigator.share({{files:[f],title:"{escape(title)}"}});else{{const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=f.name;a.click();}}}}catch(e){{}}}}</script>
<div class="pg"><img src="{logo}" style="height:54px"><h1>{escape(title)}</h1><table class="hd">{hd}</table>
<table class="m"><tr><th></th><th>Previous (AED)</th><th>This certificate (AED)</th><th>To date (AED)</th></tr>{rows}
<tr><td>VAT {s.vat_pct or 0:g}%</td><td></td><td>{c['vat']:,.2f}</td><td></td></tr>
<tr class="p"><td>Amount payable</td><td></td><td>{c['payable']:,.2f}</td><td></td></tr></table>
<div class="sig"><div>Prepared by (QS)</div><div>Checked by</div><div>Approved by</div></div></div></body></html>""")
