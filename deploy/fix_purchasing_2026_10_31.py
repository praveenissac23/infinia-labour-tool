"""One-off correction of the purchasing records from the purchaser's questionnaire (Arun, returned 31/10/2026).

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_purchasing_2026_10_31.py            (dry run - nothing written)
    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_purchasing_2026_10_31.py --apply    (writes it, in one go)

Run it after the new app version is deployed (git pull && sudo systemctl restart infinia): it uses the app's own
models and rules, and refuses to run on a database without the new purchasing columns, or one that does not look
like the live one. The dry run prints every change it would make, in plain words with before -> after, and a
summary; --apply makes exactly those changes in one transaction (all or nothing) and writes an activity-log
entry for each, tagged 'purchasing questionnaire 31/10/2026'. Running it again changes nothing.

Everything is found by LPO and request number, never by row number. Nothing in payroll is touched, and no money
amount on any LPO changes.

What it does, from the answers:
  1  Rentals links: 'Spigot / Nut & Bolt' = Spigot Pin + Spigot Pin Nut/Bolt (Q26), 'M.D Props 3.20 to 5.0m /
     6.0m' = Prop 5.0M / 6.0M (Q28), the matches the purchaser confirmed line by line (Part D), and every hire LPO
     material whose plain name is a Rentals material's.
  2  The store top-up requests made for site LPOs (MR-0019 ... MR-0045 'Stock for the store, ordered on ...')
     are put under the LPO's site (Q1: deliveries always go straight to the site).
  3  IC/LPO/20260150 (if it exists) - replaced by 20260150R1 (Q29).
  4  IC/LPO/20260157 - cancelled (will not come), through the cancel-everywhere rules; accounts are told to cancel
     it in Zoho (this script does not call Zoho).
  5  MR-0038 (cement; its LPO 20260151 was cancelled) - closed, not needed (Q17).
  6  Booked into the central store but went to the site (Q30-35): pump / temperature control of 20260129, 130,
     134, 144, 147 - taken out of stock (a service, cost to the site); black sand / aggregate of 20260140-143,
     rebar of 20260123 and 20260135, Legrand sockets of 20260161, the wire nails of 20260166 (cost to 913) -
     moved to the LPO's site.
  7  October LPOs marked Full - recorded delivered to the LPO's site, DN 'not recorded (per purchaser
     31/10/2026)', on the LPO's date; a line already booked (on a request, or by hand with the same quantity) is
     not booked again; service lines are services, not stock; a place that is not a site or the store (900,
     Office) - recorded against the LPO without stock.
  8  Desarch hire LPOs 20260148 (919) and 20260150R1 (913): linked to what Rentals booked in at the site
     (nothing booked twice); line 12 of R1, 1 prop short (damaged, returned) - closed, not needed.
  9  The LPOs' own requests follow them (Order follow-up stops showing what has come).
 10  Reported only, left for the staff: MR-0040 / 0041 / 0045 and LPOs 20260162 / 163 / 164 (blocks, part
     arrived - quantities not given, Amal books them with the DN); 20260152 / 159 (still to come); MR-0042 / 043 /
     046 / 048 (their position, and the petty cash bill line if one fits).
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)

TAG = "purchasing questionnaire 31/10/2026"
DN_TEXT = "not recorded (per purchaser 31/10/2026)"
EPS = 1e-6

FULL = ["20260114", "20260115", "20260116", "20260117", "20260118", "20260119", "20260120", "20260121", "20260122",
        "20260123", "20260124", "20260127", "20260128", "20260129", "20260130", "20260131", "20260132", "20260133",
        "20260134", "20260135", "20260136", "20260137", "20260138", "20260139", "20260140", "20260141", "20260142",
        "20260143", "20260144", "20260145", "20260146", "20260147", "20260149", "20260154", "20260155", "20260156",
        "20260158", "20260160", "20260161", "20260165"]
HIRE = ["20260148", "20260150R1"]
NONE_YET = ["20260152", "20260159"]
PART = ["20260162", "20260163", "20260164"]
CANCEL = "20260157"
WRONG_STORE = ["20260129", "20260130", "20260134", "20260144", "20260147", "20260140", "20260141", "20260142", "20260143",
               "20260123", "20260135", "20260161", "20260166"]
CLOSE_SHORT = {("20260150R1", "M.D Props 3.20 to 5.0m"): ("1 damaged - returned to supplier, not needed (purchaser 31/10/2026)", 1.0)}
OPEN_MRS = ["MR-0040", "MR-0041", "MR-0045"]
PETTY_MRS = ["MR-0042", "MR-0043", "MR-0046", "MR-0048"]
ALL_REFS = FULL + HIRE + NONE_YET + PART + [CANCEL, "20260151", "20260166"]


def ref(n):
    return f"IC/LPO/{n}"


def find_url(arg):
    if arg:
        return arg
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from clear_test_returns import _find_database_url
    return _find_database_url()


def shape_check(url):
    """Refuse a database without the new purchasing columns, or one that does not look like the live one."""
    from sqlalchemy import create_engine, inspect, text
    eng = create_engine(url)
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    need = {"purchase_orders", "purchase_order_lines", "material_requests", "material_request_lines", "store_movements",
            "store_items", "suppliers", "audit_log", "employees", "sites", "petty_cash", "lpo_receipts", "rental_maps"}
    missing = sorted(need - tables)
    if missing:
        sys.exit("Refused: this database has no " + ", ".join(missing) + " table - deploy the new app version first "
                 "(git pull && sudo systemctl restart infinia), then run this again.")
    cols = {(t, c["name"]) for t in ("purchase_orders", "purchase_order_lines", "material_request_lines") for c in insp.get_columns(t)}
    for t, c in (("purchase_order_lines", "service"), ("purchase_orders", "superseded_by"), ("purchase_orders", "bill_no"),
                 ("material_request_lines", "source"), ("purchase_orders", "request_line_ids")):
        if (t, c) not in cols:
            sys.exit(f"Refused: {t}.{c} is missing - deploy the new app version first, then run this again.")
    with eng.connect() as cx:
        refs = {r for (r,) in cx.execute(text("SELECT ref FROM purchase_orders"))}
        n_emp = cx.execute(text("SELECT count(*) FROM employees")).scalar()
    found = sum(1 for n in ALL_REFS if ref(n) in refs)
    if found < 30 or n_emp < 20:
        sys.exit(f"Refused: this does not look like the live database ({found} of the {len(ALL_REFS)} LPOs in the "
                 f"questionnaire found, {n_emp} employees).")
    eng.dispose()
    return found


class Fix:
    def __init__(self, db, M, P, models):
        self.db, self.M, self.P, self.models = db, M, P, models
        self.changes = []          # (section, text)
        self.notes = []            # (section, text) - reported, nothing changed
        self.counts = defaultdict(int)

    # ---- recording -------------------------------------------------------------------------------------------
    def change(self, section, text, kind=None):
        self.changes.append((section, text))
        self.counts[kind or section] += 1
        self.db.add(self.models.AuditLog(user_id=None, action="purchasing_fix", details=f"{text} [{TAG}]"[:3000]))

    def note(self, section, text):
        self.notes.append((section, text))

    # ---- lookups ---------------------------------------------------------------------------------------------
    def lpo(self, n):
        o = self.db.query(self.models.PurchaseOrder).filter(self.models.PurchaseOrder.ref == ref(n)).first()
        return o

    def mr(self, r):
        return self.db.query(self.models.MaterialRequest).filter(self.models.MaterialRequest.ref == r).first()

    def book(self):
        self.db.flush()
        return self.P.Book(self.db)

    def dmy(self, d):
        return d.strftime("%d/%m/%Y") if d else "-"

    def item_name(self, item_id):
        it = self.db.get(self.models.StoreItem, item_id) if item_id else None
        return it.name if it else ""

    # ---- 1 Rentals links -------------------------------------------------------------------------------------
    def rentals_links(self):
        for a, b, src in self.P.prefill_maps(self.db, user_id=None, questionnaire=True):
            how = "the purchaser's answer" if src == "questionnaire" else "same name"
            self.change("1 Rentals links", f"Rentals link: LPO material '{a}' = Rentals '{b}' ({how})", "rental links")

    # ---- 2 store top-up requests of site LPOs ----------------------------------------------------------------
    def store_requests_to_site(self):
        sites = self.P._Sites(self.db)
        prefix = "Stock for the store, ordered on "
        oct_refs = {ref(n) for n in ALL_REFS} | {ref("20260150")}
        for mr in self.db.query(self.models.MaterialRequest).filter(self.models.MaterialRequest.notes.like(prefix + "%")).all():
            lref = (mr.notes or "")[len(prefix):].strip()
            o = self.db.query(self.models.PurchaseOrder).filter(self.models.PurchaseOrder.ref == lref).first() or \
                self.db.query(self.models.PurchaseOrder).filter(self.models.PurchaseOrder.ref.like(lref + "R%")).order_by(
                    self.models.PurchaseOrder.id.desc()).first()
            if not o:
                continue
            key = sites.key(o)
            if key == "STORE" or (mr.site or "") == key:
                continue
            if lref not in oct_refs and o.ref not in oct_refs:
                self.note("2 Requests to site", f"{mr.ref} ({o.ref}, {self.dmy(o.order_date)}) is under STORE though the LPO is for {key} "
                          "- outside the questionnaire, left as it is")
                continue
            self.change("2 Requests to site", f"{mr.ref}: site {mr.site or 'Store'} -> {key} ({o.ref} is for {key}; "
                        "deliveries go straight to the site)", "requests moved to their site")
            mr.site = key

    # ---- 3 revision ------------------------------------------------------------------------------------------
    def revision(self):
        r1, base = self.lpo("20260150R1"), self.lpo("20260150")
        if not r1:
            self.note("3 Revision", "IC/LPO/20260150R1 not found - nothing to do")
            return
        if not base:
            self.note("3 Revision", "IC/LPO/20260150 (without R1) is not in the portal - nothing to replace")
            return
        if (base.status or "") == "cancelled":
            self.note("3 Revision", f"IC/LPO/20260150 is already cancelled ({base.cancel_reason or ''})")
            return
        replaced = self.P.apply_revision(self.db, r1, None, call_zoho=False)
        self.change("3 Revision", f"IC/LPO/20260150: issued -> cancelled, replaced by {r1.ref} (its requests and deliveries "
                    f"moved to the revision; accounts told){' - ' + ', '.join(replaced) if replaced else ''}", "LPOs superseded")

    # ---- 4 cancel 20260157 -----------------------------------------------------------------------------------
    def cancel_157(self):
        o = self.lpo(CANCEL)
        if not o:
            self.note("4 Cancel", f"{ref(CANCEL)} not found")
            return
        if (o.status or "") == "cancelled":
            self.note("4 Cancel", f"{o.ref} is already cancelled")
            return
        if self.db.query(self.models.LpoReceipt).filter(self.models.LpoReceipt.order_id == o.id).first():
            self.note("4 Cancel", f"{o.ref}: something was booked against it since - NOT cancelled, check with the purchaser")
            return
        zoho, freed = self.M._cancel_lpo_core(self.db, o, "Will not come - per purchaser (questionnaire 31/10/2026)",
                                              not_needed=True, user=None, call_zoho=False)
        self.change("4 Cancel", f"{o.ref} ({o.supplier_name}, {self.dmy(o.order_date)}, AED {self.M.lpo_total(o):,.2f}): issued -> cancelled "
                    f"(will not come); {freed} request line(s) closed" + (f"; {zoho}" if zoho else ""), "LPOs cancelled")

    # ---- 5 MR-0038 -------------------------------------------------------------------------------------------
    def close_mr38(self):
        mr, o = self.mr("MR-0038"), self.lpo("20260151")
        if not mr:
            self.note("5 MR-0038", "MR-0038 not found")
            return
        lines = [l for l in mr.lines if (l.status or "pending") != "rejected" and (l.qty_requested or 0) - (l.qty_received or 0) > EPS]
        if not lines:
            self.note("5 MR-0038", f"MR-0038 is already {mr.status} - nothing to do")
            return
        if o is None or (o.status or "") != "cancelled":
            self.note("5 MR-0038", "IC/LPO/20260151 is not cancelled in this database - MR-0038 left as it is")
            return
        before = mr.status
        what = ", ".join(f"{(l.item.name if l.item else l.description)} {l.qty_requested:g} {l.unit or ''}".strip() for l in lines)
        self.M._settle_request_lines(self.db, o, lines, True, "not needed (purchaser 31/10/2026)")
        self.change("5 MR-0038", f"MR-0038 ({what}): {before} -> {mr.status} - not needed, its LPO {o.ref} was cancelled", "requests closed")

    # ---- 6 central store -> site / service -------------------------------------------------------------------
    def central_to_site(self):
        M_, mods = self.models.StoreMovement, self.models
        sites = self.P._Sites(self.db)
        tied = {r.movement_id for r in self.db.query(mods.LpoReceipt).filter(mods.LpoReceipt.movement_id.isnot(None)).all()}
        for n in WRONG_STORE:
            o = self.lpo(n)
            if not o:
                self.note("6 Central store", f"{ref(n)} not found")
                continue
            reqs = {r.id: r for r in self.db.query(mods.MaterialRequest).all()
                    if r.id == o.request_id or r.lpo_id == o.id or (r.notes or "").endswith(o.ref)
                    or any(l.id in self.P._ids(o.request_line_ids) for l in r.lines)}
            refs = {r.ref: r.id for r in reqs.values()}
            lines = {l.item_id: l for l in o.lines if l.item_id}
            # services taken out of stock before (also those booked on the LPO's request but not a line of the LPO)
            tied |= {int(x) for (nt,) in self.db.query(M_.notes).filter(M_.kind == "adjust", M_.notes.like("%(movement #%")).all()
                     for x in [nt.split("(movement #", 1)[1].split(")", 1)[0]] if x.isdigit()}
            svc_item = lambda i: self.P.words_say_service(self.item_name(i))
            moves = [m for m in self.db.query(M_).filter(M_.kind == "in", M_.owner_id.is_(None),
                                                         func_coalesce(M_.location) == "").all()
                     if (m.item_id in lines or svc_item(m.item_id))
                     and (m.request_id in reqs or (m.request_id is None and (m.reference or "") in refs))]
            if not moves or all(m.id in tied for m in moves):
                done = self.db.query(mods.LpoReceipt).filter(mods.LpoReceipt.order_id == o.id, mods.LpoReceipt.tag == TAG,
                                                             mods.LpoReceipt.notes == "was booked into the central store").count()
                self.note("6 Central store", f"{o.ref}: " + ("already put right" if done else "nothing of it is booked in the central store"))
                continue
            for m in moves:
                if m.id in tied:
                    continue
                l = lines.get(m.item_id)
                if l is None:
                    # a service booked on this LPO's request though the LPO has no such line: out of stock, cost is the site's
                    key = sites.key(o)
                    if key == "STORE":
                        continue
                    nm = self.item_name(m.item_id)
                    self.db.add(M_(item_id=m.item_id, kind="adjust", qty=-float(m.qty or 0), location="", from_location="",
                                   reference=o.ref, moved_on=m.moved_on, request_id=m.request_id,
                                   notes=f"A service, not stock: {o.ref} for {key} (purchaser 31/10/2026) (movement #{m.id})"))
                    self.change("6 Central store", f"{o.ref} {nm} {m.qty:g} (booked {self.dmy(m.moved_on)} on its request, not a line of the LPO): "
                                f"stock in the central store -> not stock - a service for {key}", "service lines taken out of stock")
                    tied.add(m.id)
                    continue
                key = sites.key(o, l)
                if key == "STORE":
                    continue                       # meant for the store (a combined LPO's store lines)
                rid = m.request_id or refs.get(m.reference or "")
                mrl = next((x for x in reqs[rid].lines if x.item_id == m.item_id), None) if rid in reqs else None
                is_svc = self.P.is_service(l, l.item)
                dn = (m.reference or "") if (m.reference or "") not in refs else DN_TEXT
                if is_svc:
                    self.db.add(M_(item_id=m.item_id, kind="adjust", qty=-float(m.qty or 0), location="", from_location="",
                                   reference=o.ref, moved_on=m.moved_on, request_id=m.request_id,
                                   notes=f"A service, not stock: {o.ref} for {key} (purchaser 31/10/2026) (movement #{m.id})"))
                    self.db.add(mods.LpoReceipt(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=self.P.plain(l.description),
                                                kind="service", qty=float(m.qty or 0), dn_no=dn[:80], dn_date=m.moved_on, location=key,
                                                movement_id=m.id, request_line_id=mrl.id if mrl else None, tag=TAG,
                                                notes="was booked into the central store"))
                    self.change("6 Central store", f"{o.ref} {l.description} {m.qty:g} {l.unit or ''}: stock in the central store "
                                f"(booked {self.dmy(m.moved_on)}{' on ' + reqs[rid].ref if rid in reqs else ''}) -> not stock - a service, "
                                f"cost to {key}", "service lines taken out of stock")
                else:
                    m.location = key
                    m.notes = ((m.notes or "") + f" | moved to {key}: delivered there (purchaser 31/10/2026)").strip(" |")[:500]
                    self.db.add(mods.LpoReceipt(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=self.P.plain(l.description),
                                                kind="delivered", qty=float(m.qty or 0), dn_no=dn[:80], dn_date=m.moved_on, location=key,
                                                movement_id=m.id, request_line_id=mrl.id if mrl else None, tag=TAG,
                                                notes="was booked into the central store"))
                    self.change("6 Central store", f"{o.ref} {l.description} {m.qty:g} {l.unit or ''} (booked {self.dmy(m.moved_on)}): "
                                f"central store -> site {key} (cost to {key})", "materials moved to the site")
                tied.add(m.id)

    # ---- 7 October LPOs delivered in full ---------------------------------------------------------------------
    def _earlier(self, o, x, book, used_mrl, used_mv):
        """A booking made another way that is this line: a request line of the LPO's with something left on it
        (same first words, or the same quantity and unit), or a stock-in by hand of the same quantity."""
        mods = self.models
        words = self.P.plain(x["description"]).split()
        lead = words[:2]
        for mid in book.of(o)["related"]:
            mrl = book.mrl.get(mid)
            if not mrl or mid in used_mrl or book.pool_left.get(mid, 0) <= EPS or (mrl.status or "") == "rejected":
                continue
            mname = (book.items[mrl.item_id].name if mrl.item_id in book.items else "") or mrl.description or ""
            if self.P.words_say_service(mname) != bool(x["service"]):
                continue                                   # a service is never a material, nor the other way
            nm = self.P.plain(mname).split()
            same_words = len(lead) == 2 and nm[:2] == lead
            # the same quantity and unit, and a word of the name in common (primer / primer)
            sig = {w for w in words if len(w) >= 4 and w.isalpha()}
            same_qty = abs(book.pool_left[mid] - x["remaining"]) < EPS and self.P._same_unit(x["unit"], mrl.unit) \
                and bool(sig & {w for w in nm if len(w) >= 4 and w.isalpha()})
            if same_words or same_qty:
                return ("request", mrl)
        if not o.order_date:
            return None
        sig = {w for w in words if len(w) >= 4 and w.isalpha()}
        tied = {r.movement_id for r in book.receipts if r.movement_id}
        for m in self.db.query(mods.StoreMovement).filter(mods.StoreMovement.kind == "in", mods.StoreMovement.owner_id.is_(None),
                                                          mods.StoreMovement.request_id.is_(None),
                                                          mods.StoreMovement.moved_on >= o.order_date - timedelta(days=2),
                                                          mods.StoreMovement.moved_on <= o.order_date + timedelta(days=25)).all():
            if m.id in tied or m.id in used_mv or abs(float(m.qty or 0) - x["remaining"]) > EPS:
                continue
            if (m.location or "") not in ("", x["location"]):
                continue
            nm = set(self.P.plain(self.item_name(m.item_id)).split())
            if sig & nm:
                return ("move", m)
        return None

    def full_lpos(self):
        mods = self.models
        sites = self.P._Sites(self.db)
        for n in FULL:
            o = self.lpo(n)
            if not o:
                self.note("7 Full", f"{ref(n)} not found")
                continue
            if (o.status or "") == "cancelled":
                self.note("7 Full", f"{o.ref} is cancelled - not booked")
                continue
            book = self.book()
            p = book.of(o)
            todo = [x for x in p["lines"] if x["remaining"] > EPS]
            if not todo:
                continue
            used_mrl, used_mv, entries = set(), set(), {True: [], False: []}
            for x in todo:
                if x["rental_ids"]:
                    self.note("7 Full", f"{o.ref} {x['description']}: a hired material - book it on Rentals")
                    continue
                hit = None if x["service"] else self._earlier(o, x, book, used_mrl, used_mv)
                l = next(y for y in o.lines if y.id == x["line_id"])
                if hit:
                    kind, obj = hit
                    if kind == "request":
                        used_mrl.add(obj.id)
                        take = min(x["remaining"], book.pool_left[obj.id]) if self.P._same_unit(x["unit"], obj.unit) else x["remaining"]
                        self.db.add(mods.LpoReceipt(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=self.P.plain(l.description),
                                                    kind="delivered", qty=x["remaining"], dn_no=DN_TEXT, dn_date=o.order_date,
                                                    location=x["location"], request_line_id=obj.id, tag=TAG,
                                                    notes=f"booked earlier on {obj.request.ref} as {self.item_name(obj.item_id) or obj.description}"))
                        book.pool_left[obj.id] -= take
                        self.change("7 Full", f"{o.ref} {x['description']} {x['remaining']:g} {x['unit']}: to come -> delivered "
                                    f"(it was booked in on {obj.request.ref} as '{self.item_name(obj.item_id) or obj.description}' - not booked again)",
                                    "LPO lines matched to earlier bookings")
                    else:
                        used_mv.add(obj.id)
                        self.db.add(mods.LpoReceipt(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=self.P.plain(l.description),
                                                    kind="delivered", qty=x["remaining"], dn_no=DN_TEXT, dn_date=o.order_date,
                                                    location=x["location"], movement_id=obj.id, tag=TAG,
                                                    notes=f"booked earlier ({obj.reference or 'by hand'}, {self.dmy(obj.moved_on)}) as {self.item_name(obj.item_id)}"))
                        self.change("7 Full", f"{o.ref} {x['description']} {x['remaining']:g} {x['unit']}: to come -> delivered "
                                    f"(booked in {self.dmy(obj.moved_on)} as '{self.item_name(obj.item_id)}' ({obj.reference or 'by hand'}) - not booked again)",
                                    "LPO lines matched to earlier bookings")
                    continue
                stock = x["service"] or x["location"] == "" or sites.is_site(x["location"])
                entries[stock].append({"line_id": x["line_id"], "qty": x["remaining"]})
            for stock, ent in entries.items():
                if not ent:
                    continue
                done = self.P.book_delivery(self.db, o, ent, DN_TEXT, o.order_date, user_id=None, tag=TAG,
                                            notes="Full delivery per purchaser (questionnaire 31/10/2026)", check=False, stock=stock)
                for d in done:
                    self.change("7 Full", f"{o.ref} ({self.dmy(o.order_date)}): {d}", "LPO lines booked delivered")

    # ---- 8 Desarch hire LPOs -----------------------------------------------------------------------------------
    def hire_lpos(self):
        mods = self.models
        for n in HIRE:
            o = self.lpo(n)
            if not o:
                self.note("8 Hire", f"{ref(n)} not found")
                continue
            book = self.book()
            p = book.of(o)
            tied = defaultdict(float)
            for r in book.receipts:
                if r.kind == "rentals" and r.movement_id:
                    tied[r.movement_id] += float(r.qty or 0)
            since = (o.order_date or date.min) - timedelta(days=7)
            mv_item = {}
            for r in book.receipts:
                if r.kind == "rentals" and r.movement_id and r.movement_id not in mv_item:
                    m0 = self.db.get(mods.StoreMovement, r.movement_id)
                    mv_item[r.movement_id] = m0.item_id if m0 else None
            for x in p["lines"]:
                l = next(y for y in o.lines if y.id == x["line_id"])
                if not x["rental_ids"]:
                    if x["remaining"] > EPS:
                        self.note("8 Hire", f"{o.ref} line '{x['description']}': no Rentals material linked - not booked; link it on Rentals")
                    continue
                # what is tied to this line already, one Rentals material at a time (a pin + nut/bolt line needs both)
                mine = [r for r in book.receipts if r.order_id == o.id and book._rec_line(o, r) == l.id]
                per = defaultdict(float)
                for r in mine:
                    if r.kind == "rentals":
                        per[mv_item.get(r.movement_id)] += float(r.qty or 0)
                linked = min(per.get(i, 0.0) for i in x["rental_ids"])
                closed = sum(float(r.qty or 0) for r in mine if r.kind == "not_needed")
                need = x["ordered"] - linked - closed
                if need > EPS:
                    pools = {}
                    for rid in x["rental_ids"]:
                        mv = (self.db.query(mods.StoreMovement).filter(mods.StoreMovement.kind == "in", mods.StoreMovement.owner_id == o.supplier_id,
                                                                       mods.StoreMovement.item_id == rid, mods.StoreMovement.location == x["location"],
                                                                       mods.StoreMovement.moved_on >= since)
                              .order_by(mods.StoreMovement.moved_on, mods.StoreMovement.id).all())
                        pools[rid] = [[m, float(m.qty or 0) - tied[m.id]] for m in mv if float(m.qty or 0) - tied[m.id] > EPS]
                    take = min([need] + [sum(q for _, q in v) for v in pools.values()])
                    if take > EPS:
                        for rid, v in pools.items():
                            left = take
                            for pair in v:
                                if left <= EPS:
                                    break
                                m, q = pair
                                t = min(left, q)
                                self.db.add(mods.LpoReceipt(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=self.P.plain(l.description),
                                                            kind="rentals", qty=t, dn_no=(m.reference or DN_TEXT)[:80], dn_date=m.moved_on,
                                                            location=x["location"], movement_id=m.id, tag=TAG,
                                                            notes=f"booked in on Rentals as {self.item_name(rid)}"))
                                tied[m.id] += t
                                pair[1] -= t
                                left -= t
                        self.change("8 Hire", f"{o.ref} {x['description']} {take:g} of {x['ordered']:g}: to arrive -> arrived "
                                    f"(booked in on Rentals at {x['location']} as {' + '.join(x['rentals'])}; nothing booked twice)",
                                    "hire LPO lines linked to Rentals")
                    need -= take
                key = next((k for k in CLOSE_SHORT if k[0] == n and self.P.plain(k[1]) == self.P.plain(x["description"])), None)
                if need > EPS and key:
                    why, q = CLOSE_SHORT[key]
                    if abs(need - q) < EPS:
                        self.db.add(mods.LpoReceipt(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=self.P.plain(l.description),
                                                    kind="not_needed", qty=need, dn_no="", dn_date=None, location=x["location"], tag=TAG, notes=why))
                        self.change("8 Hire", f"{o.ref} {x['description']}: {need:g} short -> closed, not needed ({why})", "lines closed - not needed")
                        need = 0
                if need > EPS:
                    self.note("8 Hire", f"{o.ref} {x['description']}: {need:g} still not on Rentals at {x['location']} - left open")
            # hire-ins booked on this LPO's own request but at another site belong to the other site's LPO
            own = [r for r in book.reqs if r.id == o.request_id]
            for r in own:
                for m in self.db.query(mods.StoreMovement).filter(mods.StoreMovement.request_id == r.id,
                                                                  mods.StoreMovement.owner_id.isnot(None)).all():
                    if (m.location or "") == (r.site or "") or not r.site:
                        continue
                    other = next((self.lpo(k) for k in HIRE if self.lpo(k) and book.sites.key(self.lpo(k)) == (m.location or "")), None)
                    if other and other.request_id and other.request_id != r.id:
                        oth = self.db.get(mods.MaterialRequest, other.request_id)
                        self.change("8 Hire", f"Hire-in {m.reference} {self.item_name(m.item_id)} {m.qty:g} at {m.location}: on {r.ref} "
                                    f"(for {r.site}) -> on {oth.ref} (for {oth.site})", "hire-ins put on the right request")
                        m.request_id = other.request_id

    # ---- 9 the LPOs' own requests ----------------------------------------------------------------------------------
    def tracking(self):
        for n in FULL + HIRE + [CANCEL]:
            o = self.lpo(n)
            if not o or (o.status or "") == "cancelled":
                continue
            for t in self.P.settle_tracking(self.db, o):
                self.change("9 Requests follow", t, "request lines brought in step")

    # ---- 10 reported only ------------------------------------------------------------------------------------------
    def report_only(self):
        book = self.book()
        for n in PART + NONE_YET:
            o = self.lpo(n)
            if not o:
                self.note("10 Left for staff", f"{ref(n)} not found")
                continue
            p = book.of(o)
            due = "; ".join(f"{x['description']} {x['remaining']:g} {x['unit']} to come" for x in p["lines"] if x["remaining"] > EPS) or "nothing to come"
            word = "part arrived - quantities not given" if n in PART else "still to come"
            self.note("10 Left for staff", f"{o.ref} ({word}): {self.P.STATUS_WORDS.get(p['status'], p['status'])} - {due}"
                      + (" - Amal books what came with the DN on Material arrived" if n in PART else ""))
        for r in OPEN_MRS:
            mr = self.mr(r)
            if not mr:
                self.note("10 Left for staff", f"{r} not found")
                continue
            due = "; ".join(f"{(l.item.name if l.item else l.description)} {(l.qty_requested or 0) - (l.qty_received or 0):g} of {l.qty_requested:g}"
                            for l in mr.lines if (l.status or "") != "rejected" and (l.qty_requested or 0) - (l.qty_received or 0) > EPS)
            self.note("10 Left for staff", f"{r} (site {mr.site}): {mr.status} - still to come: {due or 'nothing'}")
        for r in PETTY_MRS:
            mr = self.mr(r)
            if not mr:
                self.note("10 Left for staff", f"{r} not found")
                continue
            due = [l for l in mr.lines if (l.status or "") != "rejected" and (l.qty_requested or 0) - (l.qty_received or 0) > EPS]
            lpos = [o for o in self.db.query(self.models.PurchaseOrder).all()
                    if any(l.id in self.P._ids(o.request_line_ids) for l in mr.lines)]
            got = self.db.query(self.models.StoreMovement).filter(self.models.StoreMovement.request_id == mr.id,
                                                                  self.models.StoreMovement.kind == "in").all()
            if not due:
                self.note("10 Left for staff", f"{r}: already received" + (f" on {self.dmy(got[0].moved_on)} (DN {got[0].reference}, at "
                          f"{got[0].location or 'central store'})" if got else "") +
                          (f" - it was ordered on {', '.join(o.ref for o in lpos)} ({lpos[0].supplier_name}), not bought with petty cash; nothing changed"
                           if lpos else " - nothing changed"))
                continue
            if lpos:
                self.note("10 Left for staff", f"{r}: on {', '.join(o.ref for o in lpos)} - booked with that LPO, not petty cash")
                continue
            cands = self.P.petty_candidates(self.db, mr)
            best = [c for c in cands if c["score"] == cands[0]["score"]] if cands else []
            pc = best[0] if len(best) == 1 else None
            ent = [{"line_id": l.id, "qty": (l.qty_requested or 0) - (l.qty_received or 0)} for l in due if l.item_id]
            if not ent:
                self.note("10 Left for staff", f"{r}: not on the material list - book it by hand")
                continue
            when = date.fromisoformat(pc["date"]) if pc else date(2026, 10, 31)
            done, where, _pc = self.P.arrive_petty(self.db, mr, ent, when, None, pc["id"] if pc else None, None, "per purchaser 31/10/2026")
            self.change("10 Petty cash", f"{r}: approved, no LPO -> arrived in full ({', '.join(done)}), bought with petty cash, at "
                        f"{where or 'central store'}" + (f"; petty cash bill {self.dmy(when)} {pc['description']} AED {pc['paid']:,.2f}" if pc
                                                        else "; no single petty cash bill line fits - link it later"), "requests arrived - petty cash")

    def run(self):
        self.rentals_links()
        self.store_requests_to_site()
        self.revision()
        self.cancel_157()
        self.close_mr38()
        self.central_to_site()
        self.full_lpos()
        self.hire_lpos()
        self.tracking()
        self.report_only()
        self.db.flush()


def func_coalesce(col):
    from sqlalchemy import func
    return func.coalesce(col, "")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the changes (without it: a dry run, nothing written)")
    ap.add_argument("--database-url", default="", help="the database (default: the app's own, as the server runs it)")
    a = ap.parse_args()
    url = find_url(a.database_url)
    if not url:
        sys.exit("Could not find DATABASE_URL.")
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("INFINIA_NO_PUSH", "1")
    os.environ.setdefault("INFINIA_NO_SCHED", "1")
    found = shape_check(url)
    import main as M          # noqa: E402  - the app's own models and rules
    import purchasing as P    # noqa: E402
    import models             # noqa: E402
    from database import SessionLocal  # noqa: E402

    db = SessionLocal()
    fx = Fix(db, M, P, models)
    try:
        fx.run()
    except Exception:
        db.rollback()
        db.close()
        raise
    print(("APPLYING" if a.apply else "DRY RUN - nothing is written") + f" - purchasing questionnaire 31/10/2026 ({found} of the "
          f"questionnaire's LPOs found)\n")
    last = None
    for sec, t in fx.changes:
        if sec != last:
            print(f"\n== {sec} ==")
            last = sec
        print("  - " + t)
    if fx.notes:
        print("\n== Not changed - reported for the staff ==")
        for sec, t in fx.notes:
            print(f"  . [{sec}] {t}")
    print("\nSummary:")
    for k, v in fx.counts.items():
        print(f"  {v:4d}  {k}")
    print(f"  {len(fx.changes):4d}  changes in all ({len(fx.notes)} reported only)")
    if a.apply:
        db.commit()
        print("\nWritten - one activity-log entry per change, tagged 'purchasing questionnaire 31/10/2026'.")
    else:
        db.rollback()
        print("\nDry run - nothing was written. Run again with --apply to make these changes.")
    db.close()


if __name__ == "__main__":
    main()
