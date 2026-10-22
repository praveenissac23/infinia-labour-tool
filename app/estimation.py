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
    """Money to the fils, rounded half up as Excel does (2,617.725 -> 2,617.73; 5% of 33,053.90 -> 1,652.70),
    not Python's float rounding, which can land a fils low."""
    from decimal import Decimal, ROUND_HALF_UP
    v = float(x or 0)
    return float(Decimal(repr(round(v, 9))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) + 0.0


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
    start_date = Column(Date, nullable=True)        # commencement date
    agreement_date = Column(Date, nullable=True)
    contract_type = Column(String, default="")      # Lump sum | Re-measurable (unit rates) | Manpower rates
    pay_terms = Column(Text, default="")            # as printed on the certificate
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
    var_cum = Column(Float, default=0.0)        # value of variations executed to date (kept apart from the work)
    measured_on = Column(Date, nullable=True)   # measurement date printed on the certificate
    inv_lines = Column(Text, default="")        # the subcontractor's bill lines, JSON [{d, a}]
    verified_by = Column(String, default="")    # "Verified at site" - a click, no scan
    verified_on = Column(Date, nullable=True)
    prep_by = Column(String, default="")        # sign-off: prepared (QS), checked, reviewed (Accounts), approved
    prep_on = Column(Date, nullable=True)
    chk_by = Column(String, default="")
    chk_on = Column(Date, nullable=True)
    rev_by = Column(String, default="")
    rev_on = Column(Date, nullable=True)
    app_by = Column(String, default="")
    app_on = Column(Date, nullable=True)
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
    revised_amount = Column(Float, default=0.0)     # what it came down to after the talks (before acceptance)
    absorbed_amount = Column(Float, default=0.0)    # cost Infinia carries itself - never added to the contract
    pc_ref = Column(String, default="")             # where it was claimed (e.g. "Item VII", "V06")
    status = Column(String, default="Identified")   # Identified | Submitted | Approved | Rejected | Absorbed | Claimed
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
    bill = Column(String, default="")           # 02. Substructure - the internal BOQ's trade sheet
    amount = Column(Float, nullable=True)       # the amount as the internal BOQ gives it (lump sums, words); empty = qty x rate
    remark = Column(String, default="")         # "Included above", "By Client" ...
    scope = Column(String, default="")          # "" in the awarded scope; else why not (Excluded, Phase 02 ...) - not counted
    locals().update(_audit())


def boq_amount(b):
    """A BOQ line's amount: the figure the internal BOQ gave, else qty x rate."""
    return r2(b.amount) if b.amount is not None else r2((b.qty or 0) * (b.rate or 0))


def boq_counted(b):
    return 0.0 if (b.scope or "") else boq_amount(b)


def boq_cost(b):
    return 0.0 if (b.scope or "") else r2((b.qty or 0) * (b.cost_rate or 0))


def _boq_amount_in(row, data):
    """A typed amount is kept as typed; a typed qty or rate works the amount out again."""
    if "amount" in data:
        v = data.get("amount")
        row.amount = None if v in (None, "") else _coerce(F, v, "amount")
    elif "qty" in data or "rate" in data:
        row.amount = None


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
                                    "status": S, "start_date": D, "agreement_date": D, "contract_type": S, "pay_terms": S,
                                    "notes": S, "sort": I}),
    "subvos": (EstSubVO, "sub_id", {"on_date": D, "ref": S, "title": S, "amount": F}),
    "subpcs": (EstSubPC, "sub_id", {"seq": I, "pc_type": S, "inv_ref": S, "inv_date": D, "inv_amount": F, "received": D,
                                    "to_site": D, "site_back": D, "certified_on": D, "issued": D, "to_accounts": D, "paid_on": D,
                                    "paid_amount": F, "paid_ref": S, "status": S, "work_cum": F, "mos_cum": F, "adv_amount": F,
                                    "adv_rec_cum": F, "adv_auto": B, "ret_cum": F, "ret_auto": B, "ret_rel_cum": F, "other_cum": F,
                                    "other_note": S, "remarks": S, "var_cum": F, "measured_on": D, "inv_lines": S,
                                    "verified_by": S, "verified_on": D, "prep_by": S, "prep_on": D, "chk_by": S, "chk_on": D,
                                    "rev_by": S, "rev_on": D, "app_by": S, "app_on": D}),
    "clientpcs": (EstClientPC, "project_id", {"seq": I, "pc_type": S, "period_to": D, "submitted": D, "claimed_cum": F,
                                              "certified_cum": F, "certified_on": D, "mos_cum": F, "adv_amount": F,
                                              "adv_rec_cum": F, "adv_auto": B, "ret_cum": F, "ret_auto": B, "ret_rel_cum": F,
                                              "other_cum": F, "status": S, "invoice_no": S, "remarks": S}),
    "variations": (EstVariation, "project_id", {"seq": I, "title": S, "kind": S, "source": S, "ref": S, "on_date": D,
                                                "submitted": D, "submitted_amount": F, "approved_on": D, "approved_amount": F,
                                                "revised_amount": F, "absorbed_amount": F, "pc_ref": S,
                                                "status": S, "sub_id": I, "notes": S}),
    "boq": (EstBoq, "project_id", {"section": S, "code": S, "description": S, "unit": S, "qty": F, "rate": F, "cost_rate": F,
                                   "done_pct": F, "sort": I, "bill": S, "remark": S, "scope": S}),
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
        if x < 0 and field in ("value", "contract_value", "inv_amount", "paid_amount", "qty", "rate", "cost_rate", "work_cum", "mos_cum", "adv_amount"):
            raise HTTPException(400, f"{field.replace('_', ' ').capitalize()} cannot be below zero.")
        if field.endswith("_pct"):
            if x < 0 or x > 100:
                raise HTTPException(400, f"{field.replace('_pct', '').replace('_', ' ').title()} % must be between 0 and 100.")
            return round(x, 4)
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
    if isinstance(row, EstVariation) and (row.kind or "") == "Omission":   # an omission takes money off: kept as a minus figure
        for k in ("submitted_amount", "approved_amount", "revised_amount"):
            setattr(row, k, -abs(getattr(row, k) or 0))


def _iso(d):
    return d.isoformat() if d else ""


def _plain(row, fields):
    out = {"id": row.id}
    for k, t in fields.items():
        v = getattr(row, k)
        out[k] = _iso(v) if t == D else ((round(float(v or 0), 4) if k.endswith("_pct") else r2(v)) if t == F else v)
    return out


def _uname(db, ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.query(models.User).filter(models.User.id.in_(ids)).all()}


# ---- the money --------------------------------------------------------------------------

def sub_revised(s, vos):
    return r2((s.value or 0) + sum(v.amount or 0 for v in vos) - (s.cancelled or 0))


LOCKED_STATUS = ("Paid", "Invoiced")


def _auto_fill(pc, prev_adv_paid, adv_pct, ret_pct, work_key, base=0.0):
    """Advance recovery and retention to date, from the percentages - unless typed.
    With no advance % set, an advance that was paid is recovered pro rata to the
    value (advance / value of the work done), so it is all back at 100%."""
    if (pc.status or "") in LOCKED_STATUS:      # a paid certificate's figures never move again
        return
    work = getattr(pc, work_key) or 0
    var = getattr(pc, "var_cum", 0) or 0         # advance is recovered on the contract work; retention is held on work + variations
    adv_paid = prev_adv_paid + (pc.adv_amount or 0)
    if pc.adv_auto:
        pct = adv_pct or (100.0 * adv_paid / base if base else 0)
        pc.adv_rec_cum = r2(min(adv_paid, work * pct / 100.0)) if pct else r2(min(adv_paid, pc.adv_rec_cum or 0))
    if pc.ret_auto:
        pc.ret_cum = r2((work + var) * (ret_pct or 0) / 100.0)


def chain(pcs, adv_pct, ret_pct, vat_pct, work_key="work_cum", fill=False, base=0.0):
    """Walk a subcontract's (or a project's) certificates in order and work out
    what each one certifies. With fill=True the automatic figures are set
    on the rows themselves (before saving)."""
    out, prev_net, adv_paid = [], 0.0, 0.0
    rows = sorted(pcs, key=lambda p: (p.seq or 0, p.id or 0))
    # Certificates up to the last paid one are history: a paid PC's amount depends on them all.
    last_locked = max([i for i, p in enumerate(rows) if (p.status or "") in LOCKED_STATUS] or [-1])
    for i, pc in enumerate(rows):
        if fill and i > last_locked:
            _auto_fill(pc, adv_paid, adv_pct, ret_pct, work_key, base)
        adv_paid = r2(adv_paid + (pc.adv_amount or 0))
        work = r2(getattr(pc, work_key))
        var = r2(getattr(pc, "var_cum", 0) or 0)
        gross = r2(work + var + (pc.mos_cum or 0))
        net = r2(gross + adv_paid - (pc.adv_rec_cum or 0) - (pc.ret_cum or 0) + (pc.ret_rel_cum or 0) - (pc.other_cum or 0))
        this = r2(net - prev_net)
        vat = r2(this * (vat_pct or 0) / 100.0)
        out.append({"id": pc.id, "work": work, "var": var, "gross": gross, "adv_paid_cum": adv_paid, "net_cum": net, "prev_net": r2(prev_net),
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
    last_work = r2(pc_list[-1]["work"] + pc_list[-1]["var"]) if pc_list else 0.0
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


def _preload(db, projects, with_files=True):
    """Everything the projects need, in one query per table (the dashboard reads every project at once)."""
    from collections import defaultdict
    pids = [p.id for p in projects] or [-1]
    codes = [p.code for p in projects] or ["-"]
    g = lambda: defaultdict(list)
    d = {k: g() for k in ("subs", "vos", "pcs", "cpcs", "vars", "boq", "logs", "finals", "files", "invoices")}
    for x in db.query(EstSub).filter(EstSub.project_id.in_(pids)).order_by(EstSub.sort, EstSub.id):
        d["subs"][x.project_id].append(x)
    sids = [x.id for v in d["subs"].values() for x in v] or [-1]
    for x in db.query(EstSubVO).filter(EstSubVO.sub_id.in_(sids)):
        d["vos"][x.sub_id].append(x)
    for x in db.query(EstSubPC).filter(EstSubPC.sub_id.in_(sids)):
        d["pcs"][x.sub_id].append(x)
    for x in db.query(EstClientPC).filter(EstClientPC.project_id.in_(pids)):
        d["cpcs"][x.project_id].append(x)
    for x in db.query(EstVariation).filter(EstVariation.project_id.in_(pids)).order_by(EstVariation.seq):
        d["vars"][x.project_id].append(x)
    for x in db.query(EstBoq).filter(EstBoq.project_id.in_(pids)).order_by(EstBoq.sort, EstBoq.id):
        d["boq"][x.project_id].append(x)
    for x in db.query(EstLog).filter(EstLog.project_id.in_(pids)).order_by(EstLog.kind, EstLog.sort, EstLog.seq):
        d["logs"][x.project_id].append(x)
    secs = {k: i for i, k in enumerate(list(FINAL_ITEMS) + ["OTHER"])}
    for x in sorted(db.query(EstFinal).filter(EstFinal.project_id.in_(pids)), key=lambda f: (secs.get(f.section, 9), f.sort or 0, f.id)):
        d["finals"][x.project_id].append(x)
    if with_files:
        for x in db.query(EstFile).filter(EstFile.project_id.in_(pids)).order_by(EstFile.id.desc()):
            d["files"][x.project_id].append(x)
    d["received"], d["pp_contract"] = {}, {}
    try:
        import projectpay
        for sc in db.query(projectpay.ProjectScope).filter(projectpay.ProjectScope.project.in_(codes)):
            d["received"][sc.project] = r2(d["received"].get(sc.project, 0) + sum(x.amount or 0 for x in sc.payments))
            d["pp_contract"][sc.project] = r2(d["pp_contract"].get(sc.project, 0) + (sc.contract or 0))
    except Exception:
        pass
    try:
        import accounts
        for i in db.query(accounts.Invoice).filter(accounts.Invoice.project_no.in_(codes)).order_by(accounts.Invoice.inv_date):
            d["invoices"][i.project_no].append({"id": i.id, "kind": i.kind, "number": i.number, "date": _iso(i.inv_date), "client": i.client,
                                                "work": i.work, "subtotal": r2(i.subtotal), "vat": r2(i.vat), "total": r2(i.total), "status": i.status})
    except Exception:
        pass
    return d


def project_bundle(db, p, rules=None, pre=None):
    rules = rules or _rules(db)
    pre = pre or _preload(db, [p])
    subs = pre["subs"].get(p.id, [])
    sub_out = [_sub_bundle(db, s, pre["vos"].get(s.id, []), pre["pcs"].get(s.id, []), rules) for s in subs]
    if sub_out:                                    # how many schedule lines each subcontract has (its PC is then made on the sheet)
        import est_pcsheet
        n = dict(db.query(est_pcsheet.EstSubItem.sub_id, func.count(est_pcsheet.EstSubItem.id))
                 .filter(est_pcsheet.EstSubItem.sub_id.in_([x["id"] for x in sub_out])).group_by(est_pcsheet.EstSubItem.sub_id).all())
        for x in sub_out:
            x["items"] = n.get(x["id"], 0)
    cpcs = pre["cpcs"].get(p.id, [])
    vars_ = pre["vars"].get(p.id, [])
    boq = pre["boq"].get(p.id, [])
    logs = pre["logs"].get(p.id, [])
    finals = pre["finals"].get(p.id, [])
    files = pre["files"].get(p.id, [])
    names = _uname(db, [f.created_by for f in files]) if files else {}
    client = _client_bundle(p, cpcs)
    received, pp_contract = pre["received"].get(p.code, 0.0), pre["pp_contract"].get(p.code, 0.0)
    invoices = pre["invoices"].get(p.code, [])
    approved_vo = r2(sum(v.approved_amount or 0 for v in vars_ if v.status == "Approved"))
    boq_value = r2(sum(boq_counted(b) for b in boq))
    boq_cost_ = r2(sum(boq_cost(b) for b in boq))
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
    draft_adv = 0.0
    if cert:     # an advance still in draft before the last certified one is not certified money
        last_seq = cert[-1]["seq"]
        draft_adv = r2(sum(c["adv_amount"] for c in client if c["pc_type"] == "Advance" and c["status"] == "Draft" and c["seq"] <= last_seq))
    summary = {
        "contract": r2(contract), "approved_vo": approved_vo, "revised": r2(contract + approved_vo),
        "client_certified": r2(cert[-1]["net_cum"] - draft_adv) if cert else 0.0,
        "client_work": cert[-1]["work"] if cert else 0.0,
        "client_claimed": client[-1]["net_cum"] if client else 0.0,
        "received": received, "invoiced": r2(sum(i["total"] for i in invoices if i["kind"] == "tax" and i["status"] != "cancelled")),
        "boq_value": boq_value, "boq_cost": boq_cost_,
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
        "boq": [dict(_plain(b, KINDS["boq"][2]), amount=boq_amount(b), counted=boq_counted(b), cost=boq_cost(b), given=b.amount is not None) for b in boq],
        "logs": [_plain(l, KINDS["logs"][2]) for l in logs],
        "finals": [_plain(f, KINDS["finals"][2]) for f in finals],
        "files": [dict(_plain(f, KINDS["files"][2]), kind=f.kind, row_id=f.row_id, size=f.size, by=names.get(f.created_by, ""),
                       at=f.created_at.isoformat() if f.created_at else "", url=_file_url(f)) for f in files],
        "invoices": invoices, "rules": rules,
    }


# ---- endpoints: lists to pick from ------------------------------------------------------

def _dummy_count(db):
    try:
        import est_dummy
        return db.query(est_dummy.EstDummy).count()
    except Exception:
        return 0


@router.get("/store/est/meta")
def meta(db: Session = Depends(get_db), user: models.User = VIEW):
    perms = M.effective_permissions(user)
    projects = db.query(EstProject).order_by(EstProject.code).all()
    sites = db.query(models.Site).filter(models.Site.active == True).order_by(models.Site.code).all()   # noqa: E712
    sups = db.query(models.Supplier).filter(models.Supplier.active == True).order_by(models.Supplier.name).all()   # noqa: E712
    users = db.query(models.User).filter(models.User.active == True).order_by(models.User.full_name).all() if hasattr(models.User, "active") else db.query(models.User).order_by(models.User.full_name).all()  # noqa: E712
    names = {s.name for s in db.query(EstSub.name).distinct()}
    # What a subcontractor was given last time, and the trade each kind of work usually is -
    # so a new subcontract fills itself in from a click on the name / the work.
    terms, by_scope = {}, {}
    for x in db.query(EstSub).order_by(EstSub.id).all():
        if x.name:
            terms[x.name.strip().lower()] = {"trade": x.trade or "", "kind": x.kind or "", "adv_pct": x.adv_pct or 0, "ret_pct": x.ret_pct or 0,
                                             "vat_pct": 5 if x.vat_pct is None else x.vat_pct, "contract_type": x.contract_type or "",
                                             "pay_terms": x.pay_terms or "", "scope": x.scope or ""}
        if x.scope and x.trade:
            d = by_scope.setdefault(x.scope.strip().lower(), {})
            d[x.trade] = d.get(x.trade, 0) + 1
    scope_trade = {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in by_scope.items()}
    return {
        "sub_terms": terms, "scope_trade": scope_trade,
        "projects": [{"id": p.id, "code": p.code, "name": p.name, "status": p.status, "client": p.client} for p in projects],
        "sites": [{"code": s.code, "name": s.project_name or "", "plot": s.plot_no or ""} for s in sites],
        "suppliers": [{"id": s.id, "name": s.name} for s in sups],
        "sub_names": sorted(n for n in names if n),
        "users": [{"id": u.id, "name": u.full_name} for u in users],
        "trades": TRADES, "scopes": SCOPES, "parties": PARTIES, "disciplines": DISCIPLINES, "doc_categories": DOC_CATEGORIES,
        "log_status": LOG_STATUS, "steps": SUB_STEPS, "rules": _rules(db),
        "dummy": _dummy_count(db),
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
    projects = db.query(EstProject).order_by(EstProject.code).all()
    pre = _preload(db, projects, with_files=False)
    for p in projects:
        b = project_bundle(db, p, rules, pre)
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
                if pc["site_delay"] and st == "At site":           # late now, not late once
                    kpi["site_delays"] += 1
                if pc["pc_delay"] and st in ("Received", "At site", "Back from site", "Certified"):
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
        matrix.append({"id": p.id, "code": p.code, "finals": {f["item"]: {"sc": f["sc"], "st": f["st"]} for f in b["finals"]}})
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
    if (pc.work_cum or 0) < 0 or (pc.mos_cum or 0) < 0:
        raise HTTPException(400, "Work done and material on site cannot be below zero.")
    s = _sub_of(db, pc.sub_id)
    vos = db.query(EstSubVO).filter(EstSubVO.sub_id == s.id).all()
    rev = sub_revised(s, vos)
    done = (pc.work_cum or 0) + (pc.var_cum or 0)
    if rev and done > rev * 1.5 + 1:
        raise HTTPException(400, f"Work done to date ({done:,.2f}) is far above the revised subcontract value ({rev:,.2f}). Check the figure.")


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
    if kind == "boq":
        _boq_amount_in(row, data)
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
            for k in ("work_cum", "var_cum", "mos_cum", "ret_rel_cum", "other_cum"):
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
        if row.pc_type == "Advance":
            if db.query(EstSubPC).filter(EstSubPC.sub_id == row.sub_id, EstSubPC.pc_type == "Advance").first():
                raise HTTPException(400, "This subcontract already has its advance payment certificate.")
            s = _sub_of(db, row.sub_id)
            if not row.adv_amount:
                row.adv_amount = r2((s.value or 0) * (s.adv_pct or 0) / 100.0)
            if not row.adv_amount:
                raise HTTPException(400, "Enter the advance amount (or set the advance % on the subcontract).")
            # An advance is not an invoice to check at site: it is certified when made.
            if "received" not in data:
                row.received = None
            if "status" not in data:
                row.status, row.certified_on = "Certified", t
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
        row.ref = vref(row.seq)                 # every variation is V01, V02 ... in the order made
        if row.on_date is None:
            row.on_date = t
        if not row.title:
            raise HTTPException(400, "What is the variation for?")
    elif kind == "subvos":
        nums = [int(m.group(1)) for (r,) in db.query(EstSubVO.ref).filter(EstSubVO.sub_id == row.sub_id).all()
                for m in [re.match(r"^V(\d+)$", (r or "").strip(), re.I)] if m]
        row.ref = vref(max(nums + [db.query(EstSubVO).filter(EstSubVO.sub_id == row.sub_id).count()]) + 1)
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
    if kind == "subpcs":
        import est_pcsheet
        est_pcsheet.carry_over(db, row)
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
    if kind in ("variations", "subvos"):
        data.pop("ref", None)                   # the V number is given, never typed
    if kind == "subs" and user.role != "admin" and any(k in data and _coerce(F, data[k], k) != round(getattr(row, k) or 0, 4) for k in ("adv_pct", "ret_pct", "vat_pct")) \
            and db.query(EstSubPC).filter(EstSubPC.sub_id == row.id, EstSubPC.status == "Paid").first():
        raise HTTPException(400, "This subcontract has paid certificates - its advance, retention and VAT % are locked. Ask an admin if they must change.")
    if kind == "projects" and user.role != "admin" and any(k in data and _coerce(F, data[k], k) != round(getattr(row, k) or 0, 4) for k in ("adv_pct", "ret_pct", "vat_pct")) \
            and db.query(EstClientPC).filter(EstClientPC.project_id == row.id, EstClientPC.status.in_(LOCKED_STATUS)).first():
        raise HTTPException(400, "This project has invoiced or paid certificates - its advance, retention and VAT % are locked. Ask an admin if they must change.")
    if kind == "subpcs" and user.role != "admin" and row.status != "Paid" and any(k in data for k in ("work_cum", "mos_cum", "adv_amount", "adv_rec_cum", "ret_cum", "ret_rel_cum", "other_cum")) \
            and db.query(EstSubPC).filter(EstSubPC.sub_id == row.sub_id, EstSubPC.status == "Paid", EstSubPC.seq > (row.seq or 0)).first():
        raise HTTPException(400, "A later certificate is already paid - this one's figures are locked. Ask an admin if it must change.")
    if kind == "subpcs" and row.status == "Paid" and any(k in data for k in ("work_cum", "mos_cum", "adv_amount", "adv_rec_cum", "ret_cum", "ret_rel_cum", "other_cum")) and user.role != "admin":
        raise HTTPException(400, "This certificate is paid - its figures are locked. Ask an admin if it must change.")
    # A typed advance recovery / retention switches its automatic figure off.
    if kind in ("subpcs", "clientpcs"):
        if "adv_rec_cum" in data and "adv_auto" not in data:
            data["adv_auto"] = False
        if "ret_cum" in data and "ret_auto" not in data:
            data["ret_auto"] = False
    _apply(row, fields, data)
    if kind == "boq":
        _boq_amount_in(row, data)
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
        import est_pcsheet
        est_pcsheet.drop_sub(db, rid)
        db.query(EstSubPC).filter(EstSubPC.sub_id == rid).delete(synchronize_session=False)
        db.query(EstSubVO).filter(EstSubVO.sub_id == rid).delete(synchronize_session=False)
    if kind == "files":
        try:
            os.remove(os.path.join(FILES, row.stored))
        except OSError:
            pass
    sid = getattr(row, "sub_id", None) if kind == "subpcs" else None
    pid = row.project_id if kind == "clientpcs" else None
    if kind == "subpcs":
        import est_pcsheet
        est_pcsheet.drop_pc(db, row.id)
    db.delete(row)
    db.flush()
    if sid:
        import est_pcsheet
        est_pcsheet.refresh_sub(db, sid)
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
            pc.paid_ref = ""                 # not paid after all: no cheque reference left showing
        step = SUB_STEPS[i - 1] if i else "Received"
    # the steps after this one have not happened (yet / any more): no dates left over from before
    for later in SUB_STEPS[SUB_STEPS.index(step) + 1:]:
        if STEP_DATE.get(later) and later != "Received":
            setattr(pc, STEP_DATE[later], None)
    if step != "Paid":
        pc.paid_amount, pc.paid_ref = 0.0, ""
    pc.status = step
    pc.updated_by = user.id
    db.commit()
    return {"ok": True, "status": pc.status}


# ---- Accounts: the subcontractor certificates sent for payment ----------------------------

@router.get("/store/est/payqueue")
def payqueue(db: Session = Depends(get_db), user: models.User = PAYER):
    """Accounts > Subcontractor payments: every certificate issued or sent to Accounts, and the last 60 days paid."""
    rules = _rules(db)
    projects = db.query(EstProject).order_by(EstProject.code).all()
    pre = _preload(db, projects, with_files=False)
    since = (today() - timedelta(days=60)).isoformat()
    rows = []
    for p in projects:
        for s_ in pre["subs"].get(p.id, []):
            sb = _sub_bundle(db, s_, pre["vos"].get(s_.id, []), pre["pcs"].get(s_.id, []), rules)
            for pc in sb["pcs"]:
                if pc["status"] in ("PC issued", "With Accounts") or (pc["status"] == "Paid" and (pc["paid_on"] or "") >= since):
                    rows.append({"pc_id": pc["id"], "project": p.code, "project_name": p.name, "sub": sb["name"], "scope": sb["scope"],
                                 "seq": pc["seq"], "pc_type": pc["pc_type"], "inv_ref": pc["inv_ref"], "this": pc["this"], "vat": pc["vat"],
                                 "payable": pc["payable"], "issued": pc["issued"], "to_accounts": pc["to_accounts"], "paid_on": pc["paid_on"],
                                 "paid_amount": pc["paid_amount"], "paid_ref": pc["paid_ref"], "status": pc["status"]})
    order = {"With Accounts": 0, "PC issued": 1, "Paid": 2}
    rows.sort(key=lambda r: (order.get(r["status"], 3), r["to_accounts"] or r["issued"] or "", r["project"]))
    perms = M.effective_permissions(user)
    return {"rows": rows, "today": today().isoformat(), "estimation": RIGHT in perms}


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
            txt = cells[di].strip()
            # A heading is a line in capitals (SUBSTRUCTURE) or a BILL / SECTION / PART line - not a note.
            if txt and (txt.upper() == txt or re.match(r"^(bill|section|part|division|elemental)\b", txt, re.I)):
                section = txt[:200]
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


# ---- internal BOQ workbook: read in memory, lines saved, the file itself never kept ---------

def _boq_key(code, desc):
    return ((code or "").strip().lower(), re.sub(r"\s+", " ", (desc or "").strip().lower()))


@router.post("/store/est/projects/{pid}/boq-import")
async def boq_import(pid: int, file: UploadFile = File(...), save: int = Form(0), mode: str = Form("replace"),
                     db: Session = Depends(get_db), user: models.User = VIEW):
    """The estimation team's internal BOQ workbook (1.PRELIM ... 20. SPECIALIZED ITEMS). The first
    call only reads it and shows what will come in; save=1 puts the lines on the project.
    mode=replace takes the project's BOQ lines out first, keeping the cost rate and done % typed
    on any line that comes back (same item no. and description); mode=add puts them after."""
    import est_boqimport
    p = _project(db, pid)
    data = await file.read()
    if len(data) > MAX_FILE:
        raise HTTPException(413, "That file is over 25 MB.")
    if not data[:2] == b"PK":
        raise HTTPException(400, "That is not an Excel workbook (.xlsx). Save the internal BOQ as .xlsx and upload it again.")
    try:
        r = est_boqimport.read_internal_boq(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "That workbook could not be read. Upload the internal BOQ as .xlsx (sheets 1.PRELIM, 2.SUBSTR ...).")
    have = db.query(EstBoq).filter(EstBoq.project_id == pid).order_by(EstBoq.sort, EstBoq.id).all()
    out = {k: r[k] for k in ("bills", "notes", "summary_sheet", "summary_total", "total", "left_out")}
    out.update({"lines": len(r["lines"]), "existing": len(have), "file": file.filename or ""})
    if not save:
        return out
    if mode not in ("replace", "add"):
        raise HTTPException(400, "Replace or add?")
    keep = {}
    if mode == "replace":
        for b in have:
            if (b.cost_rate or 0) or (b.done_pct or 0):
                keep.setdefault(_boq_key(b.code, b.description), (b.cost_rate or 0, b.done_pct or 0))
            db.delete(b)
        db.flush()
        base = 0
    else:
        base = max([b.sort or 0 for b in have] or [0])
    kept = 0
    for i, x in enumerate(r["lines"], 1):
        cr, dp = keep.pop(_boq_key(x["code"], x["description"]), (0.0, 0.0))
        kept += 1 if (cr or dp) else 0
        db.add(EstBoq(project_id=pid, bill=x["bill"][:120], section=x["section"][:200], code=x["code"][:40], description=x["description"][:1000],
                      unit=x["unit"][:20], qty=x["qty"], rate=x["rate"], amount=r2(x["amount"]), remark=x["remark"][:200],
                      scope=x["scope"][:60], cost_rate=cr, done_pct=dp, sort=base + i, created_by=user.id))
    db.commit()
    out.update({"saved": len(r["lines"]), "kept_budget": kept, "mode": mode, "project": p.code})
    return out


@router.post("/store/est/projects/{pid}/boq-scope")
def boq_scope(pid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """Brings a bill (or one section of it) into the awarded scope, or leaves it out again:
    {bill, section?, scope: "" to count it, or the reason it is left out}."""
    _project(db, pid)
    bill = str(data.get("bill") or "")
    q = db.query(EstBoq).filter(EstBoq.project_id == pid, EstBoq.bill == bill)
    if data.get("section") is not None:
        q = q.filter(EstBoq.section == str(data.get("section")))
    rows = q.all()
    if not rows:
        raise HTTPException(404, "Those lines are not there any more.")
    sc = str(data.get("scope") or "").strip()[:60]
    for b in rows:
        b.scope = sc
        b.updated_by = user.id
    db.commit()
    return {"changed": len(rows)}


# ---- variation log brought in from the QS Excel file ---------------------------------------

def vref(seq):
    """A variation's number: V01, V02 ... (V100 after V99)."""
    return f"V{int(seq or 0):02d}"


def renumber_variations(SessionLocal):
    """Once: every variation on every project numbered V01, V02 ... in its log order (client
    variations and subcontract variations alike). A reference that was something else (CP02,
    OHP-1, Amendment 1) is kept in the remarks / description so nothing is lost."""
    import est_pcsheet as S
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == "est_vo_vnumbers").first():
            return
        n = 0
        for pid in [x[0] for x in db.query(EstVariation.project_id).distinct().all()]:
            for i, v in enumerate(db.query(EstVariation).filter(EstVariation.project_id == pid).order_by(EstVariation.seq, EstVariation.id).all(), 1):
                old, new = (v.ref or "").strip(), vref(i)
                if old and old.upper() != new and not (v.notes or "").startswith("QS log ref."):
                    v.notes = (f"QS log ref. {old}" + (f" - {v.notes}" if v.notes else ""))[:4000]
                v.seq, v.ref = i, new
                n += 1
        for sid in [x[0] for x in db.query(EstSubVO.sub_id).distinct().all()]:
            remap = {}
            for i, v in enumerate(db.query(EstSubVO).filter(EstSubVO.sub_id == sid).order_by(EstSubVO.on_date, EstSubVO.id).all(), 1):
                old, new = (v.ref or "").strip(), vref(i)
                if old and old.upper() != new:
                    remap[old.lower()] = new
                    if not re.match(r"^(var|vo|v)[\s.-]*\d+$", old, re.I) and old.lower() not in (v.title or "").lower():
                        v.title = f"{v.title} ({old})"[:4000] if v.title else old
                v.ref = new
                n += 1
            for it in db.query(S.EstSubItem).filter(S.EstSubItem.sub_id == sid, S.EstSubItem.is_var == True).all():  # noqa: E712
                if (it.var_ref or "").strip().lower() in remap:
                    it.var_ref = remap[it.var_ref.strip().lower()]
        db.add(models.Setting(key="est_vo_vnumbers", value="1"))
        db.commit()
        if n:
            print(f"Variations numbered V01, V02 ...: {n}")
    finally:
        db.close()


def _vo_rows_in(db, p, rows, user_id):
    """Puts parsed variation rows on the project, numbered after what is there."""
    seq = _next_seq(db, EstVariation, project_id=p.id) - 1
    for x in rows:
        seq += 1
        v = EstVariation(project_id=p.id, seq=seq, created_by=user_id)
        for k in ("title", "kind", "source", "pc_ref", "status", "notes"):
            setattr(v, k, x.get(k) or "")
        v.ref = vref(seq)
        old = str(x.get("ref") or "").strip()
        if old and old.upper() != v.ref:        # the QS log's own number kept in the remarks
            v.notes = (f"QS log ref. {old}" + (f" - {v.notes}" if v.notes else ""))[:4000]
        for k in ("submitted_amount", "revised_amount", "approved_amount", "absorbed_amount"):
            setattr(v, k, r2(x.get(k)))
        for k in ("submitted", "approved_on"):
            d = x.get(k)
            setattr(v, k, date.fromisoformat(d) if isinstance(d, str) and d else (d or None))
        v.on_date = v.submitted or v.approved_on
        db.add(v)
    return seq


def _vo_summary(rows):
    by = {}
    for x in rows:
        by[x["status"]] = by.get(x["status"], 0) + 1
    return {"rows": len(rows), "by_status": by,
            "approved": r2(sum(x["approved_amount"] for x in rows if x["status"] == "Approved")),
            "submitted": r2(sum(x["submitted_amount"] for x in rows if x["kind"] != "Coordination")),
            "absorbed": r2(sum(x["absorbed_amount"] for x in rows)),
            "lines": [{"ref": x["ref"], "title": x["title"][:120], "status": x["status"], "submitted_amount": r2(x["submitted_amount"]),
                       "approved_amount": r2(x["approved_amount"]), "absorbed_amount": r2(x["absorbed_amount"])} for x in rows]}


@router.post("/store/est/projects/{pid}/variations/import")
async def vo_import(pid: int, file: UploadFile = File(...), save: int = Form(0), take_off_contract: int = Form(0),
                    db: Session = Depends(get_db), user: models.User = VIEW):
    """The variation log Excel (Ref.No, Description, Submitted / Revised / Accepted /
    Absorbed amount, dates, Claimed in PC, Remarks; the OHP sheet too). First call
    shows what will come in; save=1 puts it in. take_off_contract=1 when the
    contract value already includes the accepted variations, so they are not
    counted twice."""
    import est_voimport
    p = _project(db, pid)
    data = await file.read()
    if len(data) > MAX_FILE:
        raise HTTPException(413, "That file is over 25 MB.")
    try:
        rows = est_voimport.read_log(data)
    except Exception as e:
        raise HTTPException(400, f"Couldn't read that file as a variation log: {e}")
    out = _vo_summary(rows)
    out["contract"] = r2(p.contract_value)
    out["have"] = db.query(EstVariation).filter(EstVariation.project_id == pid).count()
    if not save:
        return out
    _vo_rows_in(db, p, rows, user.id)
    if take_off_contract and out["approved"]:
        p.contract_value = r2((p.contract_value or 0) - out["approved"])
    db.commit()
    out["saved"] = True
    out["contract"] = r2(p.contract_value)
    return out


VO_SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "est_vo_seed.json")


def seed_variations(SessionLocal):
    """The variation logs the QS team sent (908, 909, 911, 912, 913, 919), put in
    once. Only on a project with no variations yet; the contract goes back to the
    original only when it still equals the figure that already had the accepted
    variations in it (so Original + approved VOs = the contract as it stood)."""
    import json
    if not os.path.exists(VO_SEED_FILE):
        return
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == "est_vo_seed_v1").first():
            return
        seed = json.load(open(VO_SEED_FILE))
        for code, x in seed.items():
            p = db.query(EstProject).filter(EstProject.code == code).first()
            if not p or db.query(EstVariation).filter(EstVariation.project_id == p.id).first():
                continue
            _vo_rows_in(db, p, x["rows"], None)
            if x.get("approved") and abs((p.contract_value or 0) - x["contract_with_vos"]) < 0.01:
                p.contract_value = r2(x["contract_with_vos"] - x["approved"])
        db.add(models.Setting(key="est_vo_seed_v1", value="1"))
        db.commit()
    except Exception:
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


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
    if not re.match(r"^\d{3,4}$", code) and not db.query(models.Site).filter(models.Site.code == code).first():
        raise HTTPException(400, "A project code is its number, e.g. 928.")
    p = db.query(EstProject).filter(EstProject.code == code).first()
    if p and data.get("new_only"):
        raise HTTPException(400, f"Project {code} is already there - pick a new number.")
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
    # No documents are kept in the app any more (it stays light): figures and references only.
    raise HTTPException(410, "Files are not kept in the app - type the reference instead.")
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
        money = ["Submitted amount", "Revised amount", "Approved amount", "Absorbed amount"]
        for v in b["variations"]:
            sub = next((s["name"] for s in b["subs"] if s["id"] == v["sub_id"]), "")
            r = {"Ref.": v["ref"] or vref(v["seq"]), "Description": v["title"], "Type": v["kind"], "Source": v["source"],
                 "Submitted": _d(v["submitted"]), "Submitted amount": v["submitted_amount"], "Revised amount": v["revised_amount"],
                 "Approved on": _d(v["approved_on"]), "Approved amount": v["approved_amount"], "Absorbed amount": v["absorbed_amount"],
                 "Claimed in PC": v["pc_ref"] or "", "Subcontractor": sub, "Status": v["status"], "Remarks": v["notes"] or ""}
            if keep(r, v["status"]):
                rows.append(r)
    elif what == "boq":
        title = "BOQ & budget"
        totals = ["Amount", "Budget cost", "Margin"]
        money = ["Rate", "Amount", "Cost rate", "Budget cost", "Margin"]
        for x in b["boq"]:
            r = {"Bill": x.get("bill") or "", "Section": x["section"], "Item": x["code"], "Description": x["description"], "Unit": x["unit"], "Qty": x["qty"],
                 "Rate": x["rate"], "Amount": x["counted"], "Cost rate": x["cost_rate"], "Budget cost": x["cost"],
                 "Margin": r2(x["counted"] - x["cost"]) if x["cost_rate"] else "", "Done %": x["done_pct"],
                 "Remark": " - ".join(t for t in (x.get("scope") or "", x.get("remark") or "", f"not counted ({x['amount']:,.2f})" if x.get("scope") else "") if t)}
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

# The subcontractor certificate print lives in est_pcsheet.py (certificate page and appendices).


import est_pcsheet  # noqa: E402,F401  - the item schedule, the monthly sheet and the certificate print
import est_dummy  # noqa: E402,F401  - ESTIMATION DUMMY DATA (reversible test data)
