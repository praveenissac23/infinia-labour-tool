"""Purchasing the way the purchaser works (31 Oct 2026, from Arun's questionnaire).

  Deliveries against LPOs   every LPO not cancelled - raised from a material request or straight away - is on
                            the store keeper's list to book in (all of it or part, line by line), with the
                            supplier's delivery note number and date; delivered to the LPO's site unless the LPO
                            is for the store. The LPO reads Ordered -> Part delivered -> Delivered from it.
  Services                  pump, temperature control, transport, installation, printing, charges (by the
                            words, the material's type, or the 'Service' tick on the LPO line) are never stock;
                            their cost is the LPO's site's.
  Rentals                   an LPO's material and the Rentals material it is booked in as are linked (one to
                            many / many to one); a hire LPO line reads delivered from what Rentals booked in at
                            that site from that supplier - nothing is booked twice.
  Cancelled everywhere      a material request line whose only LPOs are cancelled reads 'To order' again, never
                            'Ordered' (old cancellations included, worked out when read).
  Petty cash                an approved request with no LPO can be marked arrived, bought with petty cash -
                            linked to the petty cash bill line when known; no LPO cost is made up.
  Supplier bill check       the purchaser records the bill (no., date, amount) and ticks it checked against the
                            LPO and the delivery note; the difference to the LPO total (round off included)
                            is shown, and the chief accountant's Send to Zoho list shows it.
  Material names            a typed name close to one already on the list is pointed out.
  Revisions                 IC/LPO/20260150R1 replaces IC/LPO/20260150 everywhere.
"""
import difflib
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
import main as M

router = APIRouter()
EPS = 1e-9
TAG = "purchasing questionnaire 31/10/2026"

# ---------------------------------------------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------------------------------------------
_UNIT = r"(?:mm|cm|mtrs?|mtr|m|ltrs?|ltr|lt|l|kgs?|kg|g|pcs|pc|nos|no)"


def _fmt_num(s):
    try:
        v = float(s)
    except ValueError:
        return s
    return ("%f" % v).rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def plain(name):
    """A material's name made plain for matching: case, punctuation, spaces, a unit after a number and the word
    'Rental' ignored; numbers written one way ('Rental Standard 1.00M' and 'standard 1.0 m' -> 'standard 1')."""
    t = (name or "").lower().replace("–", "-")
    t = re.sub(r"\brental\b", " ", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*" + _UNIT + r"\b", r"\1 ", t)
    t = re.sub(r"\d+(?:\.\d+)?", lambda m: " " + _fmt_num(m.group(0)) + " ", t)
    t = re.sub(r"[^a-z0-9.]+", " ", t)
    t = re.sub(r"(?<![0-9])\.|\.(?![0-9])", " ", t)
    return " ".join(t.split())


def _nums(key):
    return sorted(w for w in key.split() if re.fullmatch(r"\d+(?:\.\d+)?", w))


def similar(a, b):
    """Two names for the same material? Same plain name; or one the start of the other; or nearly the same
    words with the same sizes ('Ledger 1.2' is never 'Ledger 1.3')."""
    ka, kb = plain(a), plain(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = sorted((ka, kb), key=len)
    if len(short) >= 8 and long_.startswith(short + " "):
        return True
    if _nums(ka) != _nums(kb):
        return False
    return difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.85


# ---------------------------------------------------------------------------------------------------------------
# services
# ---------------------------------------------------------------------------------------------------------------
SERVICE_RX = re.compile(r"temperature\s*control|temp\.?\s*control|\btra+nsport|\binstall|\bprinting\b|\bcharges?\b|"
                        r"\bservices?\b|\bpumping\b|\bhire charges?\b|\bdelivery charges?\b", re.I)
_PUMP = re.compile(r"\bpump", re.I)
_NOT_PUMP = re.compile(r"motor|submersible|water|machine|dewater|filter|hose|spare", re.I)
SERVICE_WORDS = "pump (concrete), temperature control, transport, installation, printing, charges, service"


def words_say_service(text):
    t = text or ""
    return bool(SERVICE_RX.search(t) or (_PUMP.search(t) and not _NOT_PUMP.search(t)))


def is_service(line, item=None):
    """A service line: never stock. The tick on the LPO line decides when it was set; else the material's type
    ('service'); else the words."""
    v = getattr(line, "service", None)
    if v is not None:
        return bool(v)
    if item is not None and (item.item_type or "") == "service":
        return True
    return words_say_service(f"{line.description or ''} {(item.name if item is not None else '')}")


# ---------------------------------------------------------------------------------------------------------------
# where an LPO's line goes
# ---------------------------------------------------------------------------------------------------------------
class _Sites:
    def __init__(self, db):
        self.codes = {x.lower(): x for (x,) in db.query(models.Site.code).all() if x}

    def key(self, o, l=None):
        """Same answer as main._lpo_site_key: a site code, 'STORE', or the place as typed."""
        text = ((getattr(l, "cost_to", "") or "") if (l is not None and getattr(o, "combined", False)) else "") \
            or (o.project_location or "")
        if text.strip().upper() in ("STORE", "CENTRAL STORE", ""):
            return "STORE"
        toks = [t.strip() for t in re.split(r"[,/;&]+|\s+", text) if t.strip()]
        for tok in toks:
            if tok.lower() in self.codes:
                c = self.codes[tok.lower()]
                return "STORE" if c.upper() == "STORE" else c
        return toks[0][:40] if len(toks) == 1 else "STORE"

    def location(self, o, l=None):
        """The stock location: '' (the central store) for the store, else the site."""
        k = self.key(o, l)
        return M.CENTRAL if k == "STORE" else k

    def is_site(self, code):
        return bool(code) and code.lower() in self.codes and code.upper() != "STORE"


def _ids(text):
    return [int(x) for x in (text or "").split(",") if x.strip().isdigit()]


# ---------------------------------------------------------------------------------------------------------------
# Rentals <-> LPO materials
# ---------------------------------------------------------------------------------------------------------------
def rental_item_ids(db):
    """Materials that are Rentals materials: of the Rental type, named 'Rental ...', or ever booked in on hire."""
    ids = {i for (i,) in db.query(models.StoreMovement.item_id).filter(models.StoreMovement.owner_id.isnot(None)).distinct()}
    for it in db.query(models.StoreItem).all():
        if (it.item_type or "") == "rental" or (it.name or "").strip().lower().startswith("rental "):
            ids.add(it.id)
    return ids


class _Maps:
    def __init__(self, db):
        self.rows = db.query(models.RentalMap).all()
        self.by_item, self.by_key = defaultdict(set), defaultdict(set)
        for r in self.rows:
            if r.lpo_item_id:
                self.by_item[r.lpo_item_id].add(r.rental_item_id)
            if r.lpo_key:
                self.by_key[r.lpo_key].add(r.rental_item_id)
        self.rental = rental_item_ids(db)
        # who we hire from: a trader something was ever booked in on hire from, or one an LPO ordered a Rentals
        # material from. Only their LPO lines are read as hired - the same 'Ledger 1.2m' bought from a trader
        # is our own stock.
        self.hire_sups = {s for (s,) in db.query(models.StoreMovement.owner_id).filter(models.StoreMovement.owner_id.isnot(None)).distinct()}
        if self.rental:
            self.hire_sups |= {s for (s,) in db.query(models.PurchaseOrder.supplier_id).join(
                models.PurchaseOrderLine, models.PurchaseOrderLine.order_id == models.PurchaseOrder.id)
                .filter(models.PurchaseOrderLine.item_id.in_(list(self.rental))).distinct() if s}

    def for_order(self, o, line, item_name=""):
        """The Rentals materials of an LPO line - only on an LPO from a trader we hire from."""
        if not o.supplier_id or (o.supplier_id not in self.hire_sups and (line.item_id or 0) not in self.rental):
            return []
        return self.of(line, item_name)

    def of(self, line, item_name=""):
        """The Rentals materials an LPO line is booked in as ([] when it is not a hired material)."""
        out = set(self.by_item.get(line.item_id or 0, set()))
        for nm in (line.description or "", item_name or ""):
            k = plain(nm)
            if k:
                out |= self.by_key.get(k, set())
        if not out and line.item_id and line.item_id in self.rental:
            out = {line.item_id}                    # ordered under its Rentals name already
        return sorted(out)


def add_map(db, lpo_name, rental_item_id, lpo_item_id=None, source="manual", user_id=None):
    """Add one link (nothing if it is there already). Returns the row or None."""
    key = plain(lpo_name)
    if not key and not lpo_item_id:
        return None
    q = db.query(models.RentalMap).filter(models.RentalMap.rental_item_id == rental_item_id)
    for r in q.all():
        if (key and r.lpo_key == key) or (lpo_item_id and r.lpo_item_id == lpo_item_id):
            return None
    row = models.RentalMap(lpo_item_id=lpo_item_id, lpo_key=key, lpo_name=(lpo_name or "").strip()[:200],
                           rental_item_id=rental_item_id, source=source, created_by=user_id)
    db.add(row)
    db.flush()
    return row


# The purchaser's answers (Q26, Q28) and the portal's own match he confirmed line by line (Part D)
QUESTIONNAIRE_MAPS = [
    ("Spigot / Nut & Bolt", "Rental Spigot Pin"),
    ("Spigot / Nut & Bolt", "Rental Spigot Pin Nut/Bolt"),
    ("M.D Props 3.20 to 5.0m", "Rental Prop 5.0M"),
    ("M.D Props 3.20 to 6.0m", "Rental Prop 6.0M"),
    ("Adjustable Base/base jack", "Rental ADJ Base Jack"),
    ('Adjustable "U" Head', "Rental U-Head Jack"),
    ("Swivel Coupler - Forged", "Rental Swivel Clamp"),
    ("Bracing Tube 4.0m", "Rental Tube 4.0M"),
]


def prefill_maps(db, user_id=None, questionnaire=True):
    """Links made without anyone typing: the purchaser's answers, then every LPO material bought from a
    supplier we hire from whose plain name is a Rentals material's ('Ledger 1.2m' = 'Rental Ledger 1.2M').
    Returns the links added [(LPO name, Rentals name, source)]."""
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    rental = rental_item_ids(db)
    by_name = defaultdict(list)
    for i in rental:
        it = items.get(i)
        if it:
            by_name[plain(it.name)].append(it)
    added = []

    def rid(name):
        k = plain(name)
        c = [it for it in by_name.get(k, []) if (it.name or "").lower().startswith("rental")] or by_name.get(k, [])
        exact = [it for it in c if " ".join((it.name or "").lower().split()) == " ".join(name.lower().split())]
        return (exact or c)[0].id if (exact or c) else None

    if questionnaire:
        for lpo_name, rname in QUESTIONNAIRE_MAPS:
            r = rid(rname)
            if r and add_map(db, lpo_name, r, source="questionnaire", user_id=user_id):
                added.append((lpo_name, items[r].name, "questionnaire"))
    hire_sups = {s for (s,) in db.query(models.StoreMovement.owner_id).filter(models.StoreMovement.owner_id.isnot(None)).distinct()}
    seen = set()
    for l, o in (db.query(models.PurchaseOrderLine, models.PurchaseOrder)
                   .join(models.PurchaseOrder, models.PurchaseOrder.id == models.PurchaseOrderLine.order_id)
                   .filter(models.PurchaseOrder.supplier_id.in_(hire_sups or {-1})).all()):
        if l.item_id in rental and (items[l.item_id].name or "").strip().lower().startswith("rental"):
            continue                                # ordered under its Rentals name already
        for nm in {l.description or "", (items[l.item_id].name if l.item_id in items else "")}:
            k = plain(nm)
            if not k or k in seen:
                continue
            seen.add(k)
            cands = [it for it in by_name.get(k, []) if (it.name or "").lower().startswith("rental")]
            if len(cands) == 1 and add_map(db, nm, cands[0].id, source="auto", user_id=user_id):
                added.append((nm, cands[0].name, "auto"))
    return added


# ---------------------------------------------------------------------------------------------------------------
# what an LPO's material requests are
# ---------------------------------------------------------------------------------------------------------------
def _related_lines(db, o, by_req, all_reqs):
    """The request lines an LPO stands for: those it was raised for, the requests it made for itself, the
    request it names; for an LPO raised before any of that was kept, the same supplier's requests of the
    three weeks before it."""
    ids = set(_ids(o.request_line_ids))
    reqs = {mr.id for mr in all_reqs if mr.lpo_id == o.id}
    if o.request_id:
        reqs.add(o.request_id)
    out = [l for r in reqs for l in by_req.get(r, [])]
    out += [l for r in all_reqs for l in by_req.get(r.id, []) if l.id in ids and l.request_id not in reqs]
    if not out and o.supplier_id and o.order_date:
        lo, hi = o.order_date - timedelta(days=21), o.order_date + timedelta(days=3)
        for mr in all_reqs:
            if mr.lpo_id or not mr.requested_on or not (lo <= mr.requested_on <= hi):
                continue
            out += [l for l in by_req.get(mr.id, []) if l.supplier_id == o.supplier_id]
    return out


def _fits(lpo_line, lpo_item, mrl, mr_item):
    if lpo_line.item_id and mrl.item_id and lpo_line.item_id == mrl.item_id:
        return "item"
    a = [lpo_line.description or "", lpo_item.name if lpo_item else ""]
    b = [mrl.description or "", mr_item.name if mr_item else ""]
    if any(similar(x, y) for x in a if x for y in b if y):
        return "name"
    return ""


def _same_unit(a, b):
    a, b = plain(a or ""), plain(b or "")
    alias = {"nos": "pcs", "no": "pcs", "pc": "pcs", "": "pcs", "bags": "bag", "trips": "trip", "rolls": "roll", "drums": "drum"}
    return alias.get(a, a) == alias.get(b, b)


# ---------------------------------------------------------------------------------------------------------------
# the delivery position of every LPO
# ---------------------------------------------------------------------------------------------------------------
class Book:
    """Everything needed to say how far each LPO has come, read once."""

    def __init__(self, db):
        self.db = db
        self.orders = (db.query(models.PurchaseOrder).options(joinedload(models.PurchaseOrder.lines))
                         .order_by(models.PurchaseOrder.order_date, models.PurchaseOrder.id).all())
        self.items = {i.id: i for i in db.query(models.StoreItem).all()}
        self.sites = _Sites(db)
        self.maps = _Maps(db)
        self.receipts = db.query(models.LpoReceipt).order_by(models.LpoReceipt.id).all()
        self.reqs = db.query(models.MaterialRequest).all()
        self.req_by_id = {r.id: r for r in self.reqs}
        self.mr_lines = db.query(models.MaterialRequestLine).all()
        self.by_req = defaultdict(list)
        for l in self.mr_lines:
            self.by_req[l.request_id].append(l)
        self.mrl = {l.id: l for l in self.mr_lines}
        self._calc()

    # ---- receipts
    def _rec_line(self, o, r):
        """Which line of the order a receipt is on: by id, else by material (an edited LPO)."""
        ids = {l.id for l in o.lines}
        if r.line_id in ids:
            return r.line_id
        for l in o.lines:
            if r.item_id and l.item_id == r.item_id:
                return l.id
        for l in o.lines:
            if r.line_key and plain(l.description) == r.line_key:
                return l.id
        return None

    def _calc(self):
        rec_by_order = defaultdict(list)
        for r in self.receipts:
            rec_by_order[r.order_id].append(r)
        # which Rentals material each Rentals receipt booked (a line booked as two materials needs both)
        mids = [r.movement_id for r in self.receipts if r.kind == "rentals" and r.movement_id]
        self.mv_item = dict(self.db.query(models.StoreMovement.id, models.StoreMovement.item_id)
                            .filter(models.StoreMovement.id.in_(mids)).all()) if mids else {}
        # request lines: what came in on them that no LPO receipt already accounts for
        on_mrl = defaultdict(float)
        for r in self.receipts:
            if r.request_line_id and r.kind in ("delivered", "rentals", "service"):
                on_mrl[r.request_line_id] += float(r.qty or 0)
        pool = {l.id: max(0.0, float(l.qty_received or 0) - on_mrl.get(l.id, 0.0)) for l in self.mr_lines}
        # Rentals: hire-ins not already tied to an LPO line
        tied = defaultdict(float)
        for r in self.receipts:
            if r.kind == "rentals" and r.movement_id:
                tied[r.movement_id] += float(r.qty or 0)
        rpool = defaultdict(list)                 # (owner, location, item) -> [[date, qty left, movement id]]
        for m in (self.db.query(models.StoreMovement).filter(models.StoreMovement.kind == "in",
                                                              models.StoreMovement.owner_id.isnot(None))
                    .order_by(models.StoreMovement.moved_on, models.StoreMovement.id).all()):
            left = float(m.qty or 0) - tied.get(m.id, 0.0)
            if left > EPS:
                rpool[(m.owner_id, (m.location or "").strip().upper(), m.item_id)].append([m.moved_on, left, m.id])
        self.out = {}
        for o in self.orders:
            self.out[o.id] = self._one(o, rec_by_order.get(o.id, []), pool, rpool)
        self.pool_left = pool            # what came in on each request line that no LPO line has taken

    def _one(self, o, recs, pool, rpool):
        live = (o.status or "issued") != "cancelled"
        related = _related_lines(self.db, o, self.by_req, self.reqs) if live else []
        by_line = defaultdict(list)
        for r in recs:
            by_line[self._rec_line(o, r)].append(r)
        lines = []
        for l in o.lines:
            it = self.items.get(l.item_id)
            service = is_service(l, it)
            loc = self.sites.location(o, l)
            rmap = [] if service else self.maps.for_order(o, l, it.name if it else "")
            rs = by_line.get(l.id, [])
            ordered = float(l.qty or 0)
            booked = sum(float(r.qty or 0) for r in rs if r.kind in ("delivered", "service"))
            rent = defaultdict(float)
            for r in rs:
                if r.kind == "rentals":
                    rent[self.mv_item.get(r.movement_id)] += float(r.qty or 0)
            if rent:
                # one LPO line booked on Rentals as two materials (pin + nut/bolt) has come when both have
                booked += min(rent.get(i, 0.0) for i in rmap) if rmap and set(rmap) <= set(rent) else \
                    (min(rent.values()) if not rmap else 0.0)
            closed = sum(float(r.qty or 0) for r in rs if r.kind == "not_needed")
            how, legacy = [], 0.0
            due = ordered - booked - closed
            if live and due > EPS:
                if rmap and o.supplier_id:
                    # what Rentals booked in at this site from this supplier, from a week before the LPO on
                    keys = [(o.supplier_id, (loc or "").strip().upper(), i) for i in rmap]
                    since = (o.order_date or date.min) - timedelta(days=7)
                    avail = lambda k: sum(x[1] for x in rpool.get(k, []) if x[0] >= since)
                    take = min([due] + [avail(k) for k in keys])
                    if take > EPS:
                        for k in keys:
                            need = take
                            for x in rpool.get(k, []):
                                if x[0] < since or x[1] <= EPS:
                                    continue
                                t = min(need, x[1]); x[1] -= t; need -= t
                                if need <= EPS:
                                    break
                        legacy += take
                        how.append("booked in on Rentals")
                else:
                    for mrl in related:
                        if pool.get(mrl.id, 0) <= EPS or (mrl.status or "pending") == "rejected":
                            continue
                        fit = _fits(l, it, mrl, self.items.get(mrl.item_id))
                        if not fit:
                            continue
                        if fit == "name" and not _same_unit(l.unit, mrl.unit):
                            take = due                              # counted in another unit: it is this line
                            pool[mrl.id] = 0.0
                        else:
                            take = min(due, pool[mrl.id]); pool[mrl.id] -= take
                        legacy += take; due -= take
                        mr = self.req_by_id.get(mrl.request_id)
                        how.append(f"booked on {mr.ref if mr else 'a request'}")
                        if due <= EPS:
                            break
            delivered = min(ordered, booked + legacy)
            remaining = max(0.0, ordered - delivered - closed) if live else 0.0
            lines.append({"line_id": l.id, "item_id": l.item_id, "description": l.description or (it.name if it else ""),
                          "unit": l.unit or (it.unit if it else ""), "ordered": round(ordered, 3),
                          "delivered": round(delivered, 3), "closed": round(closed, 3), "remaining": round(remaining, 3),
                          "service": service, "location": loc, "site": self.sites.key(o, l),
                          "rentals": [self.items[i].name for i in rmap if i in self.items],
                          "rental_ids": rmap, "how": sorted(set(how))})
        if not live:
            st = "superseded" if (o.superseded_by or "") else "cancelled"
        elif not lines:
            st = "ordered"
        elif all(x["remaining"] <= EPS for x in lines):
            st = "delivered" if any(x["delivered"] > EPS for x in lines) else "closed"
        elif any(x["delivered"] > EPS or x["closed"] > EPS for x in lines):
            st = "part"
        else:
            st = "ordered"
        # raised straight away by the purchaser: no site's request behind it (only the tracking it made for itself)
        own = lambda mrl: (self.req_by_id.get(mrl.request_id) is not None and
                           (self.req_by_id[mrl.request_id].lpo_id == o.id or
                            (self.req_by_id[mrl.request_id].notes or "").startswith("Stock for the store, ordered on")))
        direct = not _ids(o.request_line_ids) and all(own(x) for x in related)
        return {"id": o.id, "ref": o.ref, "status": st, "lines": lines, "related": [x.id for x in related], "direct": direct}

    def of(self, o):
        return self.out.get(o.id if hasattr(o, "id") else o)


STATUS_WORDS = {"ordered": "Ordered", "part": "Part delivered", "delivered": "Delivered", "closed": "Closed",
                "cancelled": "Cancelled", "superseded": "Superseded"}


def lpo_status_map(db):
    """{order id: 'ordered' | 'part' | 'delivered' | 'closed' | 'cancelled' | 'superseded'}"""
    b = Book(db)
    return {k: v["status"] for k, v in b.out.items()}


# ---------------------------------------------------------------------------------------------------------------
# request lines whose only LPOs are cancelled read 'To order' again
# ---------------------------------------------------------------------------------------------------------------
def freed_lines(db):
    """{request line id: the cancelled LPO's ref} for every line still marked ordered from a supplier when every
    LPO behind it is cancelled - shown 'To order' (and back on the purchaser's list) when read."""
    reqs = {r.id: r for r in db.query(models.MaterialRequest).filter(
        models.MaterialRequest.status.in_(["ordered", "partial", "approved", "arranging", "lpo_sent"])).all()}
    if not reqs:
        return {}
    lines = [l for l in db.query(models.MaterialRequestLine).filter(
        models.MaterialRequestLine.request_id.in_(list(reqs)), models.MaterialRequestLine.supplier_id.isnot(None)).all()
        if (l.status or "pending") != "rejected" and (l.qty_requested or 0) - (l.qty_received or 0) > EPS]
    if not lines:
        return {}
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    orders = db.query(models.PurchaseOrder).options(joinedload(models.PurchaseOrder.lines)).all()
    out = {}
    for l in lines:
        mr = reqs[l.request_id]
        refs = []
        for o in orders:
            hit = l.id in _ids(o.request_line_ids) or (o.request_id and o.request_id == mr.id) or (mr.lpo_id and mr.lpo_id == o.id)
            if not hit and o.supplier_id and o.supplier_id == l.supplier_id and not _ids(o.request_line_ids) \
                    and o.order_date and mr.requested_on and o.order_date >= mr.requested_on - timedelta(days=1):
                hit = any(_fits(x, items.get(x.item_id), l, items.get(l.item_id)) for x in o.lines)
            if hit:
                refs.append(o)
        if refs and all((o.status or "") == "cancelled" for o in refs):
            out[l.id] = sorted(refs, key=lambda o: o.id)[-1].ref
    return out


# ---------------------------------------------------------------------------------------------------------------
# booking a delivery against an LPO
# ---------------------------------------------------------------------------------------------------------------
def _settle(mr):
    M._settle_status(mr)


def _mr_line_for(book, o, l, it, exclude=()):
    """The request line an LPO line stands for, with something still to come on it."""
    for mrl in [book.mrl[i] for i in book.of(o)["related"] if i in book.mrl]:
        if mrl.id in exclude or (mrl.status or "pending") == "rejected":
            continue
        if (mrl.qty_requested or 0) - (mrl.qty_received or 0) <= EPS:
            continue
        if _fits(l, it, mrl, book.items.get(mrl.item_id)):
            return mrl
    return None


def book_delivery(db, o, entries, dn_no, dn_date, user_id=None, location=None, tag="", notes="", check=True, stock=True):
    """Book what came against an LPO. entries: [{"line_id", "qty", "close": bool}] - close = the rest of the line
    will not come. Material: stock in at the LPO's site (the store for a store LPO) unless another place is
    given; a hired material: booked in on Rentals under its Rentals name(s), owned by the supplier; a service:
    no stock. The request line it stands for moves with it. Returns [what was done, said in words]."""
    dn_no = " ".join(str(dn_no or "").split())[:80]
    if check:
        if (o.status or "") == "cancelled":
            raise HTTPException(status_code=400, detail=f"{o.ref} is cancelled - nothing can be booked against it.")
        if not dn_no:
            raise HTTPException(status_code=400, detail="Type the delivery note (DN) number from the supplier's paper.")
        if not dn_date:
            raise HTTPException(status_code=400, detail="Give the delivery note date.")
        if dn_date > M._dubai_today() + timedelta(days=1):
            raise HTTPException(status_code=400, detail="The delivery date is in the future - check the date.")
    book = Book(db)
    pos = {x["line_id"]: x for x in book.of(o)["lines"]}
    lines = {l.id: l for l in o.lines}
    disc = float(o.discount_pct or 0)
    done, used_mrl, touched = [], set(), set()
    for e in entries:
        lid = int(e.get("line_id") or 0)
        l, p = lines.get(lid), pos.get(lid)
        if not l or not p:
            raise HTTPException(status_code=400, detail=f"Line {lid} is not on {o.ref}.")
        qty = float(e.get("qty") or 0)
        if qty < -EPS:
            raise HTTPException(status_code=400, detail="A quantity cannot be below zero.")
        name = p["description"]
        if qty > p["remaining"] + 1e-6:
            raise HTTPException(status_code=400, detail=f"{name}: only {p['remaining']:g} {p['unit']} still to come on {o.ref}.")
        it = book.items.get(l.item_id)
        loc = p["location"] if location is None else (location or M.CENTRAL)
        base = dict(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=plain(l.description), dn_no=dn_no,
                    dn_date=dn_date, location=loc, tag=tag, created_by=user_id, notes=(notes or "")[:300])
        if qty > EPS:
            # the request line this LPO line stands for comes in with it (Order follow-up, the request's status)
            mrl = _mr_line_for(book, o, l, it, exclude=used_mrl)
            on_req = f" (on {mrl.request.ref})" if mrl else ""
            if p["service"]:
                db.add(models.LpoReceipt(kind="service", qty=qty, request_line_id=mrl.id if mrl else None, **base))
                done.append(f"{name}: {qty:g} {p['unit']} done (service - no stock, cost to {p['site']}){on_req}")
            elif p["rental_ids"] and o.supplier_id:
                first = True
                for rid in p["rental_ids"]:
                    ri = book.items.get(rid)
                    m = models.StoreMovement(item_id=rid, kind="in", qty=qty, location=loc, owner_id=o.supplier_id,
                                             supplier=o.supplier_name or "", reference=dn_no,
                                             notes=f"{o.ref} line: {name}", moved_on=dn_date, created_by=user_id,
                                             request_id=mrl.request_id if mrl else None)
                    db.add(m); db.flush()
                    db.add(models.LpoReceipt(kind="rentals", qty=qty, movement_id=m.id,
                                             request_line_id=(mrl.id if (mrl and first) else None), **base))
                    first = False
                    done.append(f"{name}: {qty:g} booked in on hire as {ri.name if ri else rid} at {loc or M.CENTRAL_LABEL}{on_req}")
            elif not stock:
                # delivered, but not to a place stock is kept (an office, a number that is not a site): recorded
                # against the LPO only
                db.add(models.LpoReceipt(kind="delivered", qty=qty, request_line_id=mrl.id if mrl else None, **base))
                done.append(f"{name}: {qty:g} {p['unit']} delivered to {loc or M.CENTRAL_LABEL} (not a store or site - no stock){on_req}")
            else:
                if not l.item_id:
                    raise HTTPException(status_code=400, detail=f"{name} is not on the material list, so it cannot go into stock.")
                m = models.StoreMovement(item_id=l.item_id, kind="in", qty=qty, location=loc,
                                         supplier=o.supplier_name or "", unit_cost=round(float(l.rate or 0) * (1 - disc / 100.0), 4),
                                         reference=dn_no, notes=f"Against {o.ref}" + (f" ({mrl.request.ref})" if mrl else ""),
                                         moved_on=dn_date, created_by=user_id, request_id=mrl.request_id if mrl else None)
                db.add(m); db.flush()
                db.add(models.LpoReceipt(kind="delivered", qty=qty, movement_id=m.id,
                                         request_line_id=mrl.id if mrl else None, **base))
                done.append(f"{name}: {qty:g} {p['unit']} in at {loc or M.CENTRAL_LABEL}{on_req}")
            if mrl:
                take = min(qty, (mrl.qty_requested or 0) - (mrl.qty_received or 0))
                mrl.qty_received = (mrl.qty_received or 0) + take
                used_mrl.add(mrl.id); touched.add(mrl.request)
        if e.get("close"):
            rest = round(p["remaining"] - qty, 6)
            if rest > EPS:
                db.add(models.LpoReceipt(kind="not_needed", qty=rest, **base))
                done.append(f"{name}: the other {rest:g} {p['unit']} will not come - closed")
                mrl = _mr_line_for(book, o, l, it)
                if mrl:
                    q = max(float(mrl.qty_received or 0), float(mrl.qty_requested or 0) - rest)
                    mrl.qty_requested = mrl.qty_approved = q
                    touched.add(mrl.request)
    for mr in [x for x in touched if x]:
        _settle(mr)
    db.flush()
    settle_tracking(db, o)
    return done


def settle_tracking(db, o):
    """The requests an LPO made for itself follow it: a material the LPO has had in full (or closed) is no
    longer 'to arrive' on them, however it was booked. Returns [what changed]. Site requests are left alone -
    what they asked for may be on more than one LPO."""
    book = Book(db)
    p = book.of(o)
    if not p:
        return []
    done_lines = [x for x in p["lines"] if x["remaining"] <= EPS]
    m = _REV.match(o.ref or "")
    refs = {o.ref, m.group(1).strip()} if m and m.group(1).rstrip()[-1:].isdigit() else {o.ref}
    own = [r for r in book.reqs if r.lpo_id == o.id
           or any((r.notes or "") == f"Stock for the store, ordered on {x}" for x in refs)]
    out, touched = [], set()
    for mr in own:
        for mrl in book.by_req.get(mr.id, []):
            if (mrl.status or "pending") == "rejected" or (mrl.qty_received or 0) >= (mrl.qty_requested or 0) - EPS:
                continue
            for x in done_lines:
                l = next((y for y in o.lines if y.id == x["line_id"]), None)
                if l is not None and _fits(l, book.items.get(l.item_id), mrl, book.items.get(mrl.item_id)):
                    before = mrl.qty_received or 0
                    got = min(float(mrl.qty_requested or 0), x["delivered"]) if x["closed"] > EPS else float(mrl.qty_requested or 0)
                    if x["closed"] > EPS and got < (mrl.qty_requested or 0):
                        mrl.qty_requested = mrl.qty_approved = max(got, float(before))
                    mrl.qty_received = max(float(before), got)
                    touched.add(mr)
                    out.append(f"{mr.ref} {mrl.description or (book.items[mrl.item_id].name if mrl.item_id in book.items else '')}: "
                               f"received {before:g} -> {mrl.qty_received:g} ({o.ref} has had it)")
                    break
    for mr in touched:
        _settle(mr)
    db.flush()
    return out


# ---------------------------------------------------------------------------------------------------------------
# revisions
# ---------------------------------------------------------------------------------------------------------------
_REV = re.compile(r"^(.*?)(?:R(\d+))$", re.I)


def earlier_versions(db, o):
    """The live orders a revision replaces: IC/LPO/20260150 and any R below this one."""
    m = _REV.match((o.ref or "").strip())
    if not m or not m.group(1).rstrip().endswith(tuple("0123456789")):
        return []
    base, n = m.group(1).strip(), int(m.group(2))
    names = {base.upper()} | {f"{base}R{k}".upper() for k in range(0, n)}
    return [x for x in db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id != o.id).all()
            if (x.ref or "").strip().upper() in names and (x.status or "") != "cancelled"]


def apply_revision(db, o, user, call_zoho=True):
    """A revision replaces the order before it everywhere: the material requests, what was booked in against it
    and its place on the lists move to the revision; the older one is cancelled ('Replaced by ...')."""
    olds = earlier_versions(db, o)
    for old in olds:
        ids = _ids(o.request_line_ids) + [i for i in _ids(old.request_line_ids) if i not in _ids(o.request_line_ids)]
        o.request_line_ids = ("," + ",".join(map(str, ids)) + ",") if ids else ""
        if old.request_id and not o.request_id:
            o.request_id = old.request_id
        for mr in db.query(models.MaterialRequest).filter(models.MaterialRequest.lpo_id == old.id).all():
            mr.lpo_id = o.id
        for r in db.query(models.LpoReceipt).filter(models.LpoReceipt.order_id == old.id).all():
            r.order_id = o.id
        old.request_line_ids = ""
        old.request_id = None
        M._cancel_lpo_core(db, old, f"Replaced by {o.ref}", not_needed=False, user=user, release=False,
                           superseded_by=o.ref, call_zoho=call_zoho)
    if olds:
        db.flush()
        rekey_receipts(db, o)
    return [x.ref for x in olds]


def rekey_receipts(db, o):
    """After an LPO's lines are rewritten (an edit), each delivery finds its line again by material."""
    lines = list(o.lines)
    ids = {l.id for l in lines}
    for r in db.query(models.LpoReceipt).filter(models.LpoReceipt.order_id == o.id).all():
        if r.line_id in ids:
            continue
        hit = next((l for l in lines if r.item_id and l.item_id == r.item_id), None) or \
            next((l for l in lines if r.line_key and plain(l.description) == r.line_key), None)
        r.line_id = hit.id if hit else None


# ---------------------------------------------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------------------------------------------
def _date(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], f).date()
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail=f"'{s}' is not a date (dd/mm/yyyy).")


def _who(db, uid):
    u = db.get(models.User, uid) if uid else None
    return (u.full_name or u.username) if u else ""


@router.get("/store/purchase/deliveries")
def deliveries(show: str = "open", db: Session = Depends(get_db),
               user: models.User = Depends(M.require_any_screen("store", "approvals", "requests"))):
    """The store keeper's list: every LPO not cancelled with something still to come - raised from a request
    or straight away - line by line. show=all: delivered ones too."""
    b = Book(db)
    names = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    out, covered, line_lpo = [], set(), {}
    for o in sorted(b.orders, key=lambda o: (o.order_date or date.min, o.id), reverse=True):
        p = b.of(o)
        if p["status"] in ("cancelled", "superseded"):
            continue
        covered |= set(p["related"])
        for i in p["related"]:
            line_lpo.setdefault(i, o.id)
        if show != "all" and p["status"] in ("delivered", "closed"):
            continue
        out.append({"id": o.id, "ref": o.ref, "date": o.order_date.isoformat() if o.order_date else "",
                    "supplier": o.supplier_name or "", "site": o.project_location or "",
                    "deliver_to": b.sites.key(o), "status": p["status"], "status_word": STATUS_WORDS[p["status"]],
                    "from_request": bool(p["related"]), "direct": p["direct"], "by": names.get(o.created_by, ""),
                    "lines": p["lines"]})
    return {"orders": out, "covered_request_lines": sorted(covered), "request_line_lpo": line_lpo,
            "service_words": SERVICE_WORDS}


@router.get("/store/purchase/orders/{order_id}/deliveries")
def order_deliveries(order_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(M.require_any_screen("store", "approvals", "requests"))):
    o = db.get(models.PurchaseOrder, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    b = Book(db)
    p = b.of(o)
    names = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    desc = {l.id: l.description for l in o.lines}
    hist = [{"date": r.dn_date.isoformat() if r.dn_date else "", "dn": r.dn_no or "", "kind": r.kind,
             "line": desc.get(b._rec_line(o, r), ""), "qty": r.qty, "to": r.location or "",
             "by": names.get(r.created_by, ""), "notes": r.notes or "", "tag": r.tag or ""}
            for r in db.query(models.LpoReceipt).filter(models.LpoReceipt.order_id == o.id).order_by(models.LpoReceipt.id).all()]
    return {"id": o.id, "ref": o.ref, "supplier": o.supplier_name or "", "site": o.project_location or "",
            "deliver_to": b.sites.key(o), "status": p["status"], "status_word": STATUS_WORDS[p["status"]],
            "lines": p["lines"], "history": hist, "superseded_by": o.superseded_by or "", **bill_of(o)}


@router.post("/store/purchase/orders/{order_id}/deliver")
def deliver(order_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
            user: models.User = Depends(M.require_any_screen("store", "approvals"))):
    """A delivery against an LPO: the DN number and date, how much of each line came (all of it or part);
    the rest stays to come, or is closed when it will not come."""
    o = db.get(models.PurchaseOrder, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    entries = [e for e in (payload.get("lines") or []) if float(e.get("qty") or 0) > 0 or e.get("close")]
    if not entries:
        raise HTTPException(status_code=400, detail="Enter how much came for at least one line.")
    where = payload.get("deliver_to")
    if where is not None:
        where = str(where).strip()
        if where.upper() in ("STORE", "CENTRAL STORE", M.CENTRAL_LABEL.upper()):
            where = M.CENTRAL
        elif where:
            known = db.query(models.Site).filter(models.Site.code.ilike(where)).first()
            where = known.code if known else where[:40]
    done = book_delivery(db, o, entries, payload.get("dn_no"), _date(payload.get("dn_date")), user_id=user.id,
                         location=where, notes=str(payload.get("notes") or ""))
    db.commit()
    M.log_action(db, user.id, "lpo_delivery", f"{o.ref} DN {payload.get('dn_no')} ({_date(payload.get('dn_date')).strftime('%d/%m/%Y')}): " + "; ".join(done))
    b = Book(db)
    return {"ok": True, "done": done, "status": b.of(o)["status"], "status_word": STATUS_WORDS[b.of(o)["status"]],
            "lines": b.of(o)["lines"]}


# ---- the purchaser's bill check -------------------------------------------------------------------------------
def bill_of(o):
    total = M.lpo_total(o)
    amt = o.bill_amount
    return {"bill_no": o.bill_no or "", "bill_date": o.bill_date.isoformat() if o.bill_date else "",
            "bill_amount": amt, "bill_checked": bool(o.bill_checked), "bill_note": o.bill_note or "",
            "lpo_total": total, "round_off": M.lpo_round_off(o),
            "bill_diff": round(float(amt) - total, 2) if amt is not None else None,
            "bill_checked_on": o.bill_checked_at.strftime("%d/%m/%Y") if o.bill_checked_at else ""}


@router.post("/store/purchase/orders/{order_id}/bill")
def save_bill(order_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
              user: models.User = Depends(M.require_screen("approvals"))):
    """The supplier's bill against the LPO, and the purchaser's tick: checked against the LPO and the DN."""
    o = db.get(models.PurchaseOrder, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    no = " ".join(str(payload.get("bill_no") or "").split())[:60]
    when = _date(payload.get("bill_date"))
    amt = payload.get("bill_amount")
    try:
        amt = None if amt in (None, "") else round(float(str(amt).replace(",", "")), 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="The bill amount is not a number.")
    checked = bool(payload.get("checked"))
    if checked and (not no or amt is None):
        raise HTTPException(status_code=400, detail="Enter the bill number and amount before ticking it checked.")
    before = bill_of(o)
    o.bill_no, o.bill_date, o.bill_amount = no, when, amt
    o.bill_note = " ".join(str(payload.get("note") or "").split())[:200]
    if checked and not o.bill_checked:
        o.bill_checked_by, o.bill_checked_at = user.id, datetime.now(timezone.utc)
    if not checked:
        o.bill_checked_by, o.bill_checked_at = None, None
    o.bill_checked = checked
    db.commit()
    after = bill_of(o)
    diff = after["bill_diff"]
    M.log_action(db, user.id, "lpo_bill_check",
                 f"{o.ref}: bill {no or '-'}" + (f" dated {when.strftime('%d/%m/%Y')}" if when else "")
                 + (f", AED {amt:,.2f}" if amt is not None else "") + f" against LPO total AED {after['lpo_total']:,.2f}"
                 + (f" (difference {diff:+,.2f})" if diff else "") + ("; checked against the LPO and DN" if checked else "; not checked")
                 + (f" (was: bill {before['bill_no']}, {'checked' if before['bill_checked'] else 'not checked'})" if before["bill_no"] else ""))
    return {"ok": True, **after}


# ---- Rentals links --------------------------------------------------------------------------------------------
def _map_rows(db):
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    rows = []
    for r in db.query(models.RentalMap).order_by(models.RentalMap.lpo_name, models.RentalMap.id).all():
        ri = items.get(r.rental_item_id)
        li = items.get(r.lpo_item_id) if r.lpo_item_id else None
        rows.append({"id": r.id, "lpo_name": r.lpo_name or (li.name if li else ""), "lpo_item_id": r.lpo_item_id,
                     "rental_item_id": r.rental_item_id, "rental_name": ri.name if ri else f"#{r.rental_item_id}",
                     "rental_code": ri.code if ri else "", "source": r.source or ""})
    return rows


@router.get("/store/rental-map")
def rental_map(db: Session = Depends(get_db), user: models.User = Depends(M.require_any_screen("store", "approvals"))):
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    rental = sorted(rental_item_ids(db), key=lambda i: (items[i].name or "").lower() if i in items else "")
    return {"rows": _map_rows(db),
            "rentals": [{"id": i, "code": items[i].code, "name": items[i].name} for i in rental if i in items]}


@router.post("/store/rental-map")
def rental_map_add(payload: dict = Body(...), db: Session = Depends(get_db),
                   user: models.User = Depends(M.require_any_screen("store", "approvals"))):
    name = " ".join(str(payload.get("lpo_name") or "").split())
    rid = int(payload.get("rental_item_id") or 0)
    lid = payload.get("lpo_item_id") or None
    if not name and not lid:
        raise HTTPException(status_code=400, detail="Type the material as the LPO names it.")
    ri = db.get(models.StoreItem, rid)
    if not ri:
        raise HTTPException(status_code=400, detail="Pick the Rentals material.")
    if lid and not name:
        li = db.get(models.StoreItem, int(lid))
        name = li.name if li else ""
    row = add_map(db, name, rid, lpo_item_id=int(lid) if lid else None, source="manual", user_id=user.id)
    db.commit()
    if row:
        M.log_action(db, user.id, "rental_map", f"LPO '{name}' = Rentals '{ri.name}'")
    return {"ok": True, "added": bool(row), "rows": _map_rows(db)}


@router.delete("/store/rental-map/{map_id}")
def rental_map_delete(map_id: int, db: Session = Depends(get_db),
                      user: models.User = Depends(M.require_any_screen("store", "approvals"))):
    r = db.get(models.RentalMap, map_id)
    if not r:
        raise HTTPException(status_code=404, detail="That link is not on file.")
    ri = db.get(models.StoreItem, r.rental_item_id)
    txt = f"LPO '{r.lpo_name}' = Rentals '{ri.name if ri else r.rental_item_id}'"
    db.delete(r)
    db.commit()
    M.log_action(db, user.id, "rental_map_delete", txt)
    return {"ok": True, "rows": _map_rows(db)}


@router.post("/store/rental-map/prefill")
def rental_map_prefill(db: Session = Depends(get_db),
                       user: models.User = Depends(M.require_any_screen("store", "approvals"))):
    added = prefill_maps(db, user.id)
    db.commit()
    if added:
        M.log_action(db, user.id, "rental_map", f"{len(added)} link(s) made by name: " + "; ".join(f"{a} = {b}" for a, b, _ in added[:30]))
    return {"ok": True, "added": [{"lpo_name": a, "rental_name": b, "source": c} for a, b, c in added], "rows": _map_rows(db)}


# ---- material names -------------------------------------------------------------------------------------------
@router.get("/store/items/similar")
def similar_items(name: str = "", db: Session = Depends(get_db), user: models.User = Depends(M.require_any_screen("store", "approvals", "requests"))):
    """Materials already on the list whose name is close to the one typed (not the same) - so a new name is
    not made for a material we already have."""
    typed = " ".join((name or "").split())
    k = plain(typed)
    if len(k) < 3:
        return {"exact": None, "close": []}
    exact, close = None, []
    for it in db.query(models.StoreItem).filter(models.StoreItem.active.isnot(False)).all():
        if (it.name or "").strip().lower() == typed.lower():
            exact = {"id": it.id, "code": it.code, "name": it.name, "unit": it.unit}
            continue
        if similar(typed, it.name or ""):
            r = difflib.SequenceMatcher(None, k, plain(it.name)).ratio()
            close.append((r, {"id": it.id, "code": it.code, "name": it.name, "unit": it.unit}))
    close.sort(key=lambda x: -x[0])
    return {"exact": exact, "close": [c for _, c in close[:5]]}


# ---- petty cash: an approved request with no LPO, bought with petty cash ---------------------------------------
def petty_candidates(db, mr, line=None):
    """Petty cash bills that could be this purchase: paid from 3 days before the request to 30 days after,
    the material's words in the bill's description or supplier, best first."""
    lo = (mr.requested_on or M._dubai_today()) - timedelta(days=3)
    hi = (mr.requested_on or M._dubai_today()) + timedelta(days=30)
    lines = [line] if line is not None else list(mr.lines)
    words = set()
    for l in lines:
        nm = (l.item.name if l.item else "") or l.description or ""
        words |= {w for w in plain(nm).split() if len(w) > 2 and not w[0].isdigit()}
    out = []
    for p in db.query(models.PettyCash).filter(models.PettyCash.on_date >= lo, models.PettyCash.on_date <= hi,
                                               models.PettyCash.paid > 0).all():
        txt = plain(f"{p.description or ''} {p.supplier or ''}")
        hit = sum(1 for w in words if w in txt.split() or (len(w) > 4 and w in txt))
        if not hit:
            continue
        out.append({"id": p.id, "date": p.on_date.isoformat(), "book": p.book or "", "description": p.description or "",
                    "supplier": p.supplier or "", "site": p.site or "", "paid": float(p.paid or 0), "score": hit})
    out.sort(key=lambda x: (-x["score"], x["date"]))
    return out[:10]


@router.get("/store/requests/{req_id}/petty-candidates")
def petty_cands(req_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(M.require_any_screen("store", "approvals", "requests"))):
    mr = db.get(models.MaterialRequest, req_id)
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"ref": mr.ref, "rows": petty_candidates(db, mr)}


def arrive_petty(db, mr, entries, when, user_id=None, petty_id=None, deliver_to=None, note=""):
    """Request lines that came, bought with petty cash: stock in at the request's site (or where given), no
    LPO, no cost made up; the line remembers it was petty cash and the bill line it was paid on."""
    where = mr.site if deliver_to is None else deliver_to
    where = (where or "").strip()
    if where.upper() in ("STORE", "CENTRAL STORE", M.CENTRAL_LABEL.upper()):
        where = M.CENTRAL
    elif where:
        known = db.query(models.Site).filter(models.Site.code.ilike(where)).first()
        where = known.code if known else where
    pc = db.get(models.PettyCash, petty_id) if petty_id else None
    done = []
    for e in entries:
        l = next((x for x in mr.lines if x.id == int(e.get("line_id") or 0)), None)
        if not l:
            raise HTTPException(status_code=400, detail="That material is not on this request.")
        qty = float(e.get("qty") or 0)
        due = (l.qty_requested or 0) - (l.qty_received or 0)
        name = (l.item.name if l.item else "") or l.description or ""
        if qty <= EPS:
            continue
        if (l.status or "pending") == "rejected":
            raise HTTPException(status_code=400, detail=f"{name}: the office turned this down.")
        if qty > due + 1e-6:
            raise HTTPException(status_code=400, detail=f"{name}: only {due:g} {l.unit} still due.")
        if not l.item_id:
            raise HTTPException(status_code=400, detail=f"{name} is not on the material list yet - add it first.")
        db.add(models.StoreMovement(item_id=l.item_id, kind="in", qty=qty, location=where,
                                    supplier=(pc.supplier if pc else "") or "", unit_cost=0.0,
                                    reference=(pc.receipt_no if pc and pc.receipt_no else "Petty cash"),
                                    notes=(f"Against {mr.ref} - bought with petty cash" + (f" ({note})" if note else ""))[:300],
                                    moved_on=when, created_by=user_id, request_id=mr.id))
        l.qty_received = (l.qty_received or 0) + qty
        l.source = "petty"
        if pc:
            l.petty_cash_id = pc.id
        if (l.status or "pending") == "pending":
            l.status = "approved"
        done.append(f"{name} {qty:g} {l.unit or ''}".strip())
    if not done:
        raise HTTPException(status_code=400, detail="Enter how much arrived for at least one material.")
    _settle(mr)
    if mr.status == "delivered":
        mr.closed_on = when
    return done, where, pc


@router.post("/store/requests/{req_id}/arrived-petty")
def arrived_petty(req_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(M.require_any_screen("store", "approvals"))):
    """Material on a request that nobody raised an LPO for, bought with petty cash and arrived."""
    mr = db.get(models.MaterialRequest, req_id)
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    if (mr.status or "") in ("rejected", "closed"):
        raise HTTPException(status_code=400, detail=f"{mr.ref} is {mr.status} - nothing can arrive on it.")
    when = _date(payload.get("received_on")) or M._dubai_today()
    if when > M._dubai_today() + timedelta(days=1):
        raise HTTPException(status_code=400, detail="The date is in the future - check it.")
    done, where, pc = arrive_petty(db, mr, payload.get("lines") or [], when, user.id, payload.get("petty_cash_id"),
                                   payload.get("deliver_to"), " ".join(str(payload.get("note") or "").split())[:120])
    db.commit()
    M.log_action(db, user.id, "material_request_receive",
                 f"{mr.ref}: {', '.join(done)} arrived - bought with petty cash, at {where or M.CENTRAL_LABEL}"
                 + (f" (petty cash {pc.on_date.strftime('%d/%m/%Y')} {pc.description or ''} AED {float(pc.paid or 0):,.2f})" if pc else ""))
    return {"ok": True, "status": mr.status, "done": done}
