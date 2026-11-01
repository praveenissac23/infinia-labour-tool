"""One-off correction of rental stock (01/11/2026). Owner: "There are three types of items: Rental, Consumables, Asset.
If any items are rental - even if I add it as rental, even if I get it from the purchase as rental - it must be under
rental. It must be shown in the stock and in the rental area."

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_rentals_2026_11_01.py            (dry run - nothing written)
    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_rentals_2026_11_01.py --apply    (writes it, in one go)

Run it after the new app version is deployed (git pull && sudo systemctl restart infinia): it uses the app's own models
and rules, and refuses to run on a database without the new LPO 'Rental' column, or one that does not look like the
live one. The dry run prints every change, in plain words with before -> after, and a summary; --apply makes exactly
those changes in one transaction (all or nothing) with an activity-log entry for each, tagged 'rental stock
01/11/2026'. Running it again changes nothing. It works whether or not deploy/fix_purchasing_2026_10_31.py has been
run; the order to run them in is printed at the top.

Nothing in payroll is touched, no money amount on any LPO changes, and no stock movement is deleted (a delivery
booked twice is taken off with a correction line that says why).

The rule: a material is RENTAL when a supplier owns it.
  1  Booked twice: the same delivery note booked on 'Material arrived' as ours AND on Rentals as the supplier's
     (DN 402545 at 926, 31/10/2026) - the 'ours' copy is taken off with a correction (never deleted). A Rental
     material booked in as ours from a supplier we rent from, with no twin, is put under that supplier.
  2  Ours and rental on one material ('Ledger 1.8 M': 239 ours at the sites, 405 Desarch's at 914) - the rental part's
     movements move to the material's Rental twin ('Rental Ledger 1.8M'; made 'Rental <name>' if there is none),
     our part stays. Reported, not moved, when it is not clear which Rental material it is.
  3  A material whose stock is all a supplier's becomes type Rental, with its rental supplier.
  4  The six 'rental' entries that are not materials (crane / bobcat / shovel hire charges, subcontract works) -
     a service (category Service), no stock.
  5  Rental LPOs: IC/LPO/20260103 (Najm Al Ofuq), 20260148, 20260150R1, 20260170 (Desarch) - and any LPO of a supplier
     we only ever rent from - ticked Rental; IC/LPO/20260109 (replacement of lost items, bought) ticked not Rental.
     Each line linked to its Rental material (LPO names <-> Rentals names); what Rentals already booked in at the
     LPO's site from that supplier is recorded as delivered against the line (no stock booked twice).
  6  The LPO-named twins that never held stock ('Standard 2.0m' -> 'Rental Standard 2.0M'), used by nothing else -
     off the material list (inactive; the LPOs keep them). Others reported.
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)

TAG = "rental stock 01/11/2026"
EPS = 1e-6
RENTAL_LPOS = ["IC/LPO/20260103", "IC/LPO/20260148", "IC/LPO/20260150R1", "IC/LPO/20260170"]
BOUGHT_LPOS = {"IC/LPO/20260109": "replacement of lost rental items - bought, ours"}
NOT_MATERIALS = [("ITM1014", "Subcon Power Float"), ("ITM1019", "GRP Lining Work"), ("ITM1114", "Hire Of Crawler Crane"),
                 ("ITM1102", "Shovel Hourly"), ("ITM1200", "Scaffold Hiring"), ("ITM1078", "Bob Cat Monthly")]
ORDER_NOTE = ("Run order: deploy/fix_purchasing_2026_10_31.py first (dry run, then --apply), then this one (dry run, then --apply). "
              "Either order ends with the same stock; if this one was run first, run it once more after the purchasing "
              "correction - it then also takes off the list the LPO-named twins that requests were still waiting for.")


def find_url(arg):
    if arg:
        return arg
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from clear_test_returns import _find_database_url
    return _find_database_url()


def shape_check(url):
    """Refuse a database without the new column, or one that does not look like the live one."""
    from sqlalchemy import create_engine, inspect, text
    eng = create_engine(url)
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    need = {"purchase_orders", "purchase_order_lines", "store_movements", "store_items", "suppliers", "audit_log",
            "employees", "lpo_receipts", "rental_maps", "hire_return_lines"}
    missing = sorted(need - tables)
    if missing:
        sys.exit("Refused: this database has no " + ", ".join(missing) + " table - deploy the new app version first "
                 "(git pull && sudo systemctl restart infinia), then run this again.")
    cols = {c["name"] for c in insp.get_columns("purchase_orders")}
    if "rental" not in cols:
        sys.exit("Refused: purchase_orders.rental is missing - deploy the new app version first "
                 "(git pull && sudo systemctl restart infinia), then run this again.")
    with eng.connect() as cx:
        refs = {r for (r,) in cx.execute(text("SELECT ref FROM purchase_orders"))}
        n_emp = cx.execute(text("SELECT count(*) FROM employees")).scalar()
        n_rent = cx.execute(text("SELECT count(*) FROM store_movements WHERE owner_id IS NOT NULL")).scalar()
        desarch = cx.execute(text("SELECT count(*) FROM suppliers WHERE lower(name) LIKE 'desarch%'")).scalar()
    found = sum(1 for r in RENTAL_LPOS if r in refs)
    if found < 3 or n_emp < 20 or n_rent < 50 or not desarch:
        sys.exit(f"Refused: this does not look like the live database ({found} of the {len(RENTAL_LPOS)} rental LPOs, "
                 f"{n_emp} employees, {n_rent} rental stock movements, Desarch {'found' if desarch else 'not found'}).")
    eng.dispose()
    return found


class Fix:
    def __init__(self, db, M, P, models):
        self.db, self.M, self.P, self.models = db, M, P, models
        self.changes, self.notes = [], []
        self.counts = defaultdict(int)
        self.sups = {s.id: s for s in db.query(models.Supplier).all()}

    # ---- recording -------------------------------------------------------------------------------------------
    def change(self, section, text, kind=None):
        self.changes.append((section, text))
        self.counts[kind or section] += 1
        self.db.add(self.models.AuditLog(user_id=None, action="rental_stock_fix", details=f"{text} [{TAG}]"[:3000]))

    def note(self, section, text):
        self.notes.append((section, text))

    def sname(self, sid):
        s = self.sups.get(sid)
        return s.name if s else f"supplier {sid}"

    @staticmethod
    def place(loc):
        return loc or "central store"

    @staticmethod
    def dmy(d):
        return d.strftime("%d/%m/%Y") if d else "-"

    def items(self):
        return {i.id: i for i in self.db.query(self.models.StoreItem).all()}

    def positions(self):
        """{(item, place, owner): qty} - the ledger as the app reads it."""
        self.db.flush()
        return self.M._stock_map(self.db, by_owner=True)

    # ---- 1 booked twice / a Rental material booked in as ours ----------------------------------------------------
    def booked_twice(self):
        mods = self.models
        Mv = mods.StoreMovement
        items = self.items()
        rentalish = {i.id for i in items.values() if (i.item_type or "") == "rental" or (i.name or "").lower().startswith("rental ")}
        if not rentalish:
            return
        owned_in = (self.db.query(Mv).filter(Mv.kind == "in", Mv.owner_id.is_(None), Mv.item_id.in_(list(rentalish)))
                    .order_by(Mv.id).all())
        hired_in = (self.db.query(Mv).filter(Mv.kind == "in", Mv.owner_id.isnot(None), Mv.item_id.in_(list(rentalish)))
                    .order_by(Mv.id).all())
        reversals = self.db.query(Mv).filter(Mv.kind == "adjust", Mv.notes.like("%Booked twice%")).all()
        used = set()
        for r in reversals:
            for h in hired_in:
                if f"movement #{h.id})" in (r.notes or ""):
                    used.add(h.id)
        rental_sups = self.P.rental_suppliers(self.db)
        for m in owned_in:
            it = items[m.item_id]
            if any(f"reverses #{m.id} " in (r.notes or "") for r in reversals):
                continue
            twin = next((h for h in hired_in if h.id not in used and h.item_id == m.item_id
                         and (h.location or "") == (m.location or "") and (h.reference or "").strip() == (m.reference or "").strip()
                         and abs(float(h.qty or 0) - float(m.qty or 0)) < EPS and h.moved_on and m.moved_on
                         and abs((h.moved_on - m.moved_on).days) <= 3), None)
            if twin is not None:
                used.add(twin.id)
                rev = mods.StoreMovement(item_id=m.item_id, kind="adjust", qty=-float(m.qty or 0), location=m.location or "",
                                         from_location=m.location or "", owner_id=None, supplier="", reference=m.reference or "",
                                         incharge="", moved_on=m.moved_on, request_id=None, created_by=None,
                                         notes=(f"Booked twice: reverses #{m.id} (booked as ours on {self.dmy(m.moved_on)}"
                                                + (f", against request" if m.request_id else "") + f") - the same DN {m.reference} "
                                                f"is booked on Rentals as {self.sname(twin.owner_id)}'s (movement #{twin.id}) [{TAG}]")[:500])
                rev._rental_rule_off = True
                self.db.add(rev)
                self.change("1 Booked twice", f"{it.name} {float(m.qty):g} at {self.place(m.location)}, DN {m.reference} "
                            f"({self.dmy(m.moved_on)}): booked twice - as ours (#{m.id}) and as {self.sname(twin.owner_id)}'s "
                            f"rental (#{twin.id}) -> the 'ours' copy taken off with a correction line; "
                            f"{self.place(m.location)} holds {float(m.qty):g} rental, not {2 * float(m.qty):g}", "deliveries booked twice taken off")
                continue
            sup = self.db.query(mods.Supplier).filter(mods.Supplier.name_key == self.M._supplier_key(m.supplier or "")).first() \
                if (m.supplier or "").strip() else None
            if sup is not None and sup.id in rental_sups:
                self.change("1 Booked twice", f"{it.name} {float(m.qty):g} at {self.place(m.location)} (#{m.id}, DN {m.reference or '-'}): "
                            f"ours -> {sup.name}'s rental (a Rental material, from a supplier we rent from)", "rental stock put under its supplier")
                m.owner_id = sup.id
            else:
                self.note("1 Booked twice", f"{it.name} {float(m.qty):g} at {self.place(m.location)} (#{m.id}): booked as ours on a "
                          f"Rental material, supplier '{m.supplier or '-'}' - not changed; check it and use Rentals > owner correction")

    # ---- 2 ours and rental on one material ---------------------------------------------------------------------
    def split_mixed(self):
        mods = self.models
        Mv = mods.StoreMovement
        items = self.items()
        pos = self.positions()
        hired_items = defaultdict(set)
        for iid, own in self.db.query(Mv.item_id, Mv.owner_id).filter(Mv.owner_id.isnot(None)).distinct().all():
            hired_items[iid].add(own)
        returns = defaultdict(set)
        for iid, sid in (self.db.query(mods.HireReturnLine.item_id, mods.HireReturn.supplier_id)
                         .join(mods.HireReturn, mods.HireReturn.id == mods.HireReturnLine.return_id).all()):
            returns[iid].add(sid)
        for iid in sorted(hired_items):
            it = items.get(iid)
            if it is None or (it.item_type or "") == "rental" or (it.name or "").lower().startswith("rental "):
                continue
            ours = {loc: q for (i, loc, o), q in pos.items() if i == iid and o is None and abs(q) > EPS}
            if not ours:
                continue                                  # all of it a supplier's - section 3
            for sid in sorted(hired_items[iid]):
                sup = self.sups.get(sid)
                key = self.P.plain(it.name)
                cands = [x for x in items.values() if x.id != iid and x.active is not False and self.P.plain(x.name) == key
                         and (x.name or "").lower().startswith("rental ")]
                if len(cands) > 1:
                    self.note("2 Ours and rental", f"{it.name}: {self.sname(sid)}'s rental part not moved - more than one Rental "
                              f"material by that name ({', '.join(c.name for c in cands)}); pick one and move it by hand")
                    continue
                if sid in returns.get(iid, set()):
                    self.note("2 Ours and rental", f"{it.name}: {self.sname(sid)}'s rental part not moved - a return note to "
                              f"{self.sname(sid)} names this material; move it by hand")
                    continue
                target, how = self.P.rental_item_for(self.db, it, sup, retype_ok=False)
                mvs = self.db.query(Mv).filter(Mv.item_id == iid, Mv.owner_id == sid).order_by(Mv.id).all()
                where = defaultdict(float)
                for (i, loc, o), q in pos.items():
                    if i == iid and o == sid and abs(q) > EPS:
                        where[loc] += q
                for m in mvs:
                    m.item_id = target.id
                self.db.flush()
                owned_txt = ", ".join(f"{q:g} at {self.place(l)}" for l, q in sorted(ours.items()))
                rent_txt = ", ".join(f"{q:g} at {self.place(l)}" for l, q in sorted(where.items())) or "none in hand now"
                self.change("2 Ours and rental", f"{it.name} ({it.code}): ours and {self.sname(sid)}'s rental were one row -> "
                            f"ours stays on {it.name} ({owned_txt}); the rental part ({rent_txt}; movement(s) "
                            f"{', '.join('#' + str(m.id) for m in mvs)}) moved to {target.name} ({target.code}"
                            + (", new Rental material" if how == "created" else "") + ")", "materials split: ours / rental")
                items = self.items()

    # ---- 3 all of it a supplier's: type Rental ---------------------------------------------------------------
    def retype(self):
        mods = self.models
        Mv = mods.StoreMovement
        items = self.items()
        pos = self.positions()
        hired = defaultdict(lambda: defaultdict(float))
        ever = defaultdict(set)
        for iid, own in self.db.query(Mv.item_id, Mv.owner_id).filter(Mv.owner_id.isnot(None)).distinct().all():
            ever[iid].add(own)
        for (i, loc, o), q in pos.items():
            if o is not None and abs(q) > EPS:
                hired[i][o] += q
        for iid in sorted(ever):
            it = items.get(iid)
            if it is None:
                continue
            ours = {loc: q for (i, loc, o), q in pos.items() if i == iid and o is None and abs(q) > EPS}
            if ours:
                if (it.item_type or "") != "rental":
                    self.note("3 Type Rental", f"{it.name}: still holds ours ({', '.join(f'{q:g} at {self.place(l)}' for l, q in ours.items())}) "
                              f"and rental - left as {it.item_type}")
                continue
            sids = sorted(ever[iid], key=lambda s: -sum(hired[iid].values()) if s in hired[iid] else 0)
            main = max(ever[iid], key=lambda s: (hired[iid].get(s, 0), -s))
            sup_name = self.sname(main)
            held = sum(hired[iid].values())
            if (it.item_type or "") != "rental":
                was = it.item_type
                it.item_type = "rental"
                if not (it.rental_supplier or "").strip():
                    it.rental_supplier = sup_name
                self.change("3 Type Rental", f"{it.name} ({it.code}): {was} -> Rental, rental supplier {it.rental_supplier} "
                            f"({held:g} {it.unit or ''} in hand, all {sup_name}'s)".replace("  ", " "), "materials made type Rental")
                if len(ever[iid]) > 1:
                    self.note("3 Type Rental", f"{it.name}: rented from more than one supplier ({', '.join(self.sname(s) for s in sids)}) - "
                              f"each quantity stays under its own supplier; the material names {sup_name}")
            elif not (it.rental_supplier or "").strip():
                it.rental_supplier = sup_name
                self.change("3 Type Rental", f"{it.name} ({it.code}): rental supplier (blank) -> {sup_name}", "rental supplier filled in")

    # ---- 4 not materials ---------------------------------------------------------------------------------------
    def not_materials(self):
        mods = self.models
        for code, start in NOT_MATERIALS:
            it = self.db.query(mods.StoreItem).filter(mods.StoreItem.code == code).first()
            if it is None or not (it.name or "").lower().startswith(start.lower()):
                self.note("4 Not materials", f"{code} {start}: not found as expected - nothing changed")
                continue
            if (it.item_type or "") != "rental" and (it.category or "").lower() == "service":
                continue                                 # done already
            n_mv = self.db.query(mods.StoreMovement.id).filter(mods.StoreMovement.item_id == it.id).count()
            if n_mv:
                self.note("4 Not materials", f"{it.name}: has {n_mv} stock movement(s) - not changed; check it")
                continue
            was = f"{it.item_type}{', category ' + it.category if it.category else ''}"
            it.item_type = "consumable"
            it.category = "Service"
            it.rental_supplier = ""
            it.notes = ((it.notes or "") + ("\n" if it.notes else "") + f"A service (equipment charge / subcontract work), not stock [{TAG}]")[:2000]
            self.change("4 Not materials", f"{it.name} ({it.code}): {was} -> a service (category Service), no stock - "
                        f"an equipment charge / subcontract work, not a rental material", "non-materials made services")

    # ---- 5 rental LPOs ---------------------------------------------------------------------------------------------
    def rental_lpos(self):
        mods = self.models
        P = self.P
        for a, b, src in P.prefill_maps(self.db, user_id=None, questionnaire=True):
            how = "the purchaser's answer, 31/10/2026" if src == "questionnaire" else "same name"
            self.change("5 Rental LPOs", f"Rentals link: LPO material '{a}' = Rentals '{b}' ({how})", "Rentals links made")
        orders = {o.ref: o for o in self.db.query(mods.PurchaseOrder).all()}
        Mv = mods.StoreMovement
        owners = {s for (s,) in self.db.query(Mv.owner_id).filter(Mv.owner_id.isnot(None)).distinct()}
        # a supplier we only ever rent from: nothing of theirs booked in as ours (copies taken off as booked twice aside)
        rev_ids = set()
        for (n,) in self.db.query(Mv.notes).filter(Mv.kind == "adjust", Mv.notes.like("%Booked twice: reverses #%")).all():
            try:
                rev_ids.add(int((n or "").split("reverses #", 1)[1].split(" ", 1)[0]))
            except (IndexError, ValueError):
                pass
        only_rent = set()
        for sid in owners:
            s = self.sups.get(sid)
            if s is None:
                continue
            ours = [m for m in self.db.query(Mv).filter(Mv.kind == "in", Mv.owner_id.is_(None)).all()
                    if self.M._supplier_key(m.supplier or "") == self.M._supplier_key(s.name) and m.id not in rev_ids]
            if not ours:
                only_rent.add(sid)
        want = [orders[r] for r in RENTAL_LPOS if r in orders]
        for r in RENTAL_LPOS:
            if r not in orders:
                self.note("5 Rental LPOs", f"{r} not found")
        want += [o for o in orders.values() if o.supplier_id in only_rent and o not in want and (o.status or "") != "cancelled"
                 and o.ref not in BOUGHT_LPOS]
        for o in want:
            if o.rental is None:
                o.rental = True
                self.change("5 Rental LPOs", f"{o.ref} ({o.supplier_name}): Rental (by the supplier) -> ticked Rental - what comes on it "
                            f"is the supplier's and is booked into Rentals", "LPOs ticked Rental")
            elif o.rental is False:
                self.note("5 Rental LPOs", f"{o.ref}: someone unticked Rental by hand - left as it is")
        for ref, why in BOUGHT_LPOS.items():
            o = orders.get(ref)
            if o is None:
                self.note("5 Rental LPOs", f"{ref} not found")
            elif o.rental is None:
                o.rental = False
                self.change("5 Rental LPOs", f"{o.ref} ({o.supplier_name}): Rental (by the supplier) -> not Rental ({why})", "LPOs marked bought, not Rental")
        self.db.flush()
        # each line of a rental LPO linked to its Rental material
        for o in [x for x in want if x.rental]:
            book = P.Book(self.db)
            p = book.of(o)
            sup = self.sups.get(o.supplier_id)
            for x in p["lines"]:
                l = next(y for y in o.lines if y.id == x["line_id"])
                if x["rental_ids"] and P.plain(l.description) not in {P.plain(n) for n in x["rentals"]} \
                        and not any(r.lpo_key == P.plain(l.description) for r in book.maps.rows):
                    self.note("5 Rental LPOs", f"{o.ref} '{l.description}' is linked to Rentals {' + '.join(x['rentals'])} through its "
                              f"material's name - check the size on the LPO")
                if x["service"] or x["rental_ids"]:
                    continue
                it = book.items.get(l.item_id)
                key_d, key_i = P.plain(l.description), P.plain(it.name if it else "")
                pick = None
                for key, via in ((key_d, "same name"), (key_i, "same name as its material")):
                    c = [i for i in book.items.values() if i.active is not False and P.plain(i.name) == key and key
                         and ((i.item_type or "") == "rental" or (i.name or "").lower().startswith("rental "))]
                    if len(c) == 1:
                        pick = (c[0], via)
                        break
                    if len(c) > 1:
                        self.note("5 Rental LPOs", f"{o.ref} '{l.description}': more than one Rental material fits "
                                  f"({', '.join(i.name for i in c)}) - link it on Rentals")
                        pick = ("skip", "")
                        break
                if pick and pick[0] == "skip":
                    continue
                if pick:
                    ri, via = pick
                    if (ri.item_type or "") != "rental":
                        ri.item_type = "rental"
                        ri.rental_supplier = ri.rental_supplier or (sup.name if sup else "")
                    P.add_map(self.db, l.description, ri.id, source=TAG)
                    self.change("5 Rental LPOs", f"Rentals link: {o.ref} '{l.description}' = Rentals '{ri.name}' ({via})"
                                + (f" - check: the LPO line says '{l.description}', the material is '{it.name}'" if via != "same name" and it else ""),
                                "Rentals links made")
                    continue
                was = (it.item_type if it else "") or "consumable"
                ri, how = P.rental_item_for(self.db, it, sup, name=l.description, unit=l.unit)
                if how == "retyped":
                    self.change("5 Rental LPOs", f"{ri.name} ({ri.code}): {was} -> Rental, rental supplier "
                                f"{ri.rental_supplier} (only ever on {o.supplier_name}'s rental LPOs, never held stock)", "materials made type Rental")
                else:
                    P.add_map(self.db, l.description, ri.id, source=TAG)
                    self.change("5 Rental LPOs", f"{o.ref} '{l.description}': no Rental material -> {ri.name} ({ri.code})"
                                + (" made" if how == "created" else "") + " and linked", "Rentals links made")
            self.db.flush()
        # what Rentals already booked in against each line - recorded on the LPO, nothing booked twice
        for o in [x for x in want if x.rental]:
            self.link_delivered(o)

    def link_delivered(self, o):
        mods, P = self.models, self.P
        self.db.flush()
        book = P.Book(self.db)
        p = book.of(o)
        tied = defaultdict(float)
        mv_item = {}
        for r in book.receipts:
            if r.kind == "rentals" and r.movement_id:
                tied[r.movement_id] += float(r.qty or 0)
                if r.movement_id not in mv_item:
                    m0 = self.db.get(mods.StoreMovement, r.movement_id)
                    mv_item[r.movement_id] = m0.item_id if m0 else None
        since = (o.order_date or date.min) - timedelta(days=7)
        for x in p["lines"]:
            if x["service"] or not x["rental_ids"]:
                continue
            l = next(y for y in o.lines if y.id == x["line_id"])
            mine = [r for r in book.receipts if r.order_id == o.id and book._rec_line(o, r) == l.id]
            per = defaultdict(float)
            for r in mine:
                if r.kind == "rentals":
                    per[mv_item.get(r.movement_id)] += float(r.qty or 0)
            linked = min(per.get(i, 0.0) for i in x["rental_ids"])
            closed = sum(float(r.qty or 0) for r in mine if r.kind == "not_needed")
            need = x["ordered"] - linked - closed
            if need <= EPS:
                continue
            pools = {}
            for rid in x["rental_ids"]:
                mv = (self.db.query(mods.StoreMovement).filter(mods.StoreMovement.kind == "in", mods.StoreMovement.owner_id == o.supplier_id,
                                                               mods.StoreMovement.item_id == rid, mods.StoreMovement.location == x["location"],
                                                               mods.StoreMovement.moved_on >= since)
                      .order_by(mods.StoreMovement.moved_on, mods.StoreMovement.id).all())
                pools[rid] = [[m, float(m.qty or 0) - tied[m.id]] for m in mv if float(m.qty or 0) - tied[m.id] > EPS]
            take = min([need] + [sum(q for _, q in v) for v in pools.values()])
            if take <= EPS:
                continue
            dns = set()
            for rid, v in pools.items():
                left = take
                for pair in v:
                    if left <= EPS:
                        break
                    m, q = pair
                    t = min(left, q)
                    self.db.add(mods.LpoReceipt(order_id=o.id, line_id=l.id, item_id=l.item_id, line_key=P.plain(l.description),
                                                kind="rentals", qty=t, dn_no=(m.reference or "not recorded")[:80], dn_date=m.moved_on,
                                                location=x["location"], movement_id=m.id, tag=TAG,
                                                notes=f"booked in on Rentals as {book.items[rid].name if rid in book.items else rid}"))
                    tied[m.id] += t
                    pair[1] -= t
                    left -= t
                    dns.add(m.reference or "-")
            self.change("5 Rental LPOs", f"{o.ref} {x['description']} {take:g} of {x['ordered']:g}: to arrive -> arrived (booked in on "
                        f"Rentals at {self.place(x['location'])} as {' + '.join(x['rentals'])}, DN {', '.join(sorted(dns))}; "
                        f"no stock booked again)", "rental LPO lines recorded delivered")
            if need - take > EPS:
                self.note("5 Rental LPOs", f"{o.ref} {x['description']}: {need - take:g} still not on Rentals at {self.place(x['location'])} - left to arrive")
        self.db.flush()

    # ---- 6 LPO-named twins that never held stock ------------------------------------------------------------------
    def twins(self):
        mods, P = self.models, self.P
        self.db.flush()
        book = P.Book(self.db)
        Mv = mods.StoreMovement
        moved = {i for (i,) in self.db.query(Mv.item_id).distinct()}
        mapped_to = {r.rental_item_id for r in self.db.query(mods.RentalMap).all()}
        rental_orders = {o.id for o in book.orders if book.of(o)["rental"]}
        lines_by_item = defaultdict(list)
        for o in book.orders:
            for l in o.lines:
                if l.item_id:
                    lines_by_item[l.item_id].append(o)
        open_req = defaultdict(list)
        for l in book.mr_lines:
            if l.item_id and (l.status or "pending") != "rejected" and (l.qty_requested or 0) - (l.qty_received or 0) > EPS:
                req = book.req_by_id.get(l.request_id)
                if req is not None and (req.status or "") not in ("closed", "rejected", "delivered", "cancelled"):
                    open_req[l.item_id].append(req.ref)
        seen = set()
        for o in book.orders:
            if o.id not in rental_orders:
                continue
            for x in book.of(o)["lines"]:
                iid = x["item_id"]
                it = book.items.get(iid)
                if not it or iid in seen or not x["rental_ids"] or iid in x["rental_ids"]:
                    continue
                seen.add(iid)
                if it.active is False:
                    continue
                why = []
                if iid in moved:
                    why.append("it has stock movements")
                if iid in mapped_to or (it.item_type or "") == "rental":
                    why.append("it is a Rentals material itself")
                others = sorted({oo.ref for oo in lines_by_item[iid] if oo.id not in rental_orders})
                if others:
                    why.append("also on " + ", ".join(others))
                if open_req.get(iid):
                    why.append("still to come on " + ", ".join(sorted(set(open_req[iid]))))
                names = " + ".join(x["rentals"])
                if why:
                    self.note("6 LPO-named twins", f"{it.name} ({it.code}) = Rentals {names}: kept on the list - {'; '.join(why)}")
                    continue
                it.active = False
                self.change("6 LPO-named twins", f"{it.name} ({it.code}): on the material list -> off it (inactive) - the rental "
                            f"LPO's name for {names}; it never held stock and nothing else uses it (its LPO lines keep it)",
                            "LPO-named twins taken off the list")

    # ---- checks ---------------------------------------------------------------------------------------------------
    def summary(self):
        self.db.flush()
        st = self.M._stock_rows(self.db)
        rent = self.M._on_rent(self.db)
        a = {}
        for r in st["rows"]:
            if r["item_type"] == "rental":
                for loc, q in ([("", r["in_store"])] + list(r["by_site"].items())):
                    if abs(q) > EPS:
                        a[(r["_item_id"], r["_supplier_id"], loc)] = round(q, 2)
        b = {}
        for r in rent:
            for loc, q in r["by_location"].items():
                if abs(q) > EPS:
                    b[(r["item_id"], r["supplier_id"], loc)] = round(q, 2)
        both = 0
        pos = self.M._stock_map(self.db, by_owner=True)
        owned = {i for (i, l, o), q in pos.items() if o is None and abs(q) > EPS}
        hired = {i for (i, l, o), q in pos.items() if o is not None and abs(q) > EPS}
        both = len(owned & hired)
        return st["type_totals"], a == b, both, len(b)


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
        before = M._stock_rows(db)["type_totals"]
        fx.booked_twice()
        fx.split_mixed()
        fx.retype()
        fx.not_materials()
        fx.rental_lpos()
        fx.retype()
        fx.twins()
        after, same, both, n_rent = fx.summary()
    except Exception:
        db.rollback()
        db.close()
        raise
    print(("APPLYING" if a.apply else "DRY RUN - nothing is written") + f" - rental stock 01/11/2026 ({found} of the "
          f"{len(RENTAL_LPOS)} rental LPOs found)\n")
    print(ORDER_NOTE)
    purch = db.query(models.AuditLog).filter(models.AuditLog.action == "purchasing_fix").first() is not None
    print(f"(deploy/fix_purchasing_2026_10_31.py has {'already' if purch else 'NOT yet'} been applied on this database.)\n")
    last = None
    for sec, t in fx.changes:
        if sec != last:
            print(f"\n== {sec} ==")
            last = sec
        print("  - " + t)
    if fx.notes:
        print("\n== Not changed - reported ==")
        for sec, t in fx.notes:
            print(f"  . [{sec}] {t}")
    fmt = lambda tt: "; ".join(f"{v['label']}: {v['materials']} material(s), {v['total']:g} held" for v in tt.values()) or "-"
    print("\nStock by type (Current stock):")
    print(f"  before: {fmt(before)}")
    print(f"  after:  {fmt(after)}")
    print(f"  Stock (type Rental) and Rentals show the same quantity for every material, supplier and place: {'yes' if same else 'NO'} "
          f"({n_rent} material/supplier/place figures)")
    print(f"  materials still holding ours and rental on one row: {both}")
    print("\nSummary:")
    for k, v in fx.counts.items():
        print(f"  {v:4d}  {k}")
    print(f"  {len(fx.changes):4d}  changes in all ({len(fx.notes)} reported only)")
    if a.apply:
        db.commit()
        print("\nWritten - one activity-log entry per change, tagged 'rental stock 01/11/2026'.")
    else:
        db.rollback()
        print("\nDry run - nothing was written. Run again with --apply to make these changes.")
    db.close()


if __name__ == "__main__":
    main()
