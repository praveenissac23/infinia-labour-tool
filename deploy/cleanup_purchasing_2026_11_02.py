"""Purchasing clean-up, 02/11/2026 - Arun's answers on the clean-up form (with Amal and Shafeeq), applied on live.

Every answer is checked against what the portal holds NOW before it is applied; an answer that no longer fits
(already cancelled, a delivery already booked on an LPO marked Cancel...) is NOT applied - it is listed for a decision.

    came       All came          - what is still to come is recorded as came earlier, NOT booked into stock (it was
                                   used), and the bill check is closed (the bill is with accounts / Zoho)
    coming     Still coming      - kept open; the remark kept (site hold marked as 'On hold')
    no_bill    Bill not yet      - kept open for the bill; the remark kept on the bill note
    bill_ok    Bill OK           - the bill check is closed (bill with accounts and correct)
    cancel     Cancel LPO        - cancelled in the portal; Zoho is NOT touched from here - accounts are told on the
                                   bell to cancel the PO in Zoho by hand
    ignore     Ignore - close    - the request is closed with the remark
No stock moves and no amount changes. One activity-log line per order, tagged.

    cd ~/infinia-labour-tool && venv/bin/python deploy/cleanup_purchasing_2026_11_02.py            (dry run - nothing written)
    cd ~/infinia-labour-tool && venv/bin/python deploy/cleanup_purchasing_2026_11_02.py --apply    (writes it)
"""
import argparse
import os
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
TAG = "purchasing clean-up 02/11/2026"
EPS = 1e-9

ANSWERS = {
    # final clean-up form (the 14 September LPOs), answered by Arun and Amal on 02/11/2026
    'IC/LPO/20260100': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260101': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260102': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260103': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260104': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260105': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260106': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260107': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260108': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260109': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260111': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260112': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260113': ('came', 'All came (final clean-up form 02/11)'),
    'IC/LPO/20260110': ('coming', 'Not yet started work'),
    'IC/LPO/20260114': ('came', ''),
    'IC/LPO/20260115': ('came', ''),
    'IC/LPO/20260116': ('came', ''),
    'IC/LPO/20260117': ('came', ''),
    'IC/LPO/20260118': ('came', ''),
    'IC/LPO/20260119': ('came', ''),
    'IC/LPO/20260120': ('came', ''),
    'IC/LPO/20260121': ('came', ''),
    'IC/LPO/20260122': ('came', ''),
    'IC/LPO/20260123': ('came', ''),
    'IC/LPO/20260124': ('came', ''),
    'IC/LPO/20260127': ('no_bill', 'Invoice submission pending'),
    'IC/LPO/20260128': ('came', ''),
    'IC/LPO/20260129': ('came', ''),
    'IC/LPO/20260130': ('came', ''),
    'IC/LPO/20260131': ('coming', 'work started'),
    'IC/LPO/20260132': ('came', ''),
    'IC/LPO/20260133': ('came', ''),
    'IC/LPO/20260134': ('came', ''),
    'IC/LPO/20260135': ('no_bill', 'Invoice submission pending'),
    'IC/LPO/20260136': ('came', ''),
    'IC/LPO/20260137': ('came', ''),
    'IC/LPO/20260138': ('came', ''),
    'IC/LPO/20260139': ('came', ''),
    'IC/LPO/20260140': ('no_bill', 'Invoice submission pending'),
    'IC/LPO/20260141': ('no_bill', 'Invoice submission pending'),
    'IC/LPO/20260142': ('no_bill', 'Invoice submission pending'),
    'IC/LPO/20260143': ('no_bill', 'Invoice submission pending'),
    'IC/LPO/20260144': ('came', ''),
    'IC/LPO/20260145': ('bill_ok', ''),
    'IC/LPO/20260146': ('came', ''),
    'IC/LPO/20260147': ('came', ''),
    'IC/LPO/20260148': ('came', ''),
    'IC/LPO/20260149': ('came', ''),
    'IC/LPO/20260150R1': ('coming', 'Some pcs are damages so returned'),
    'IC/LPO/20260152': ('came', ''),
    'IC/LPO/20260154': ('cancel', ''),
    'IC/LPO/20260155': ('came', ''),
    'IC/LPO/20260156': ('came', ''),
    'IC/LPO/20260157': ('cancel', ''),
    'IC/LPO/20260158': ('came', ''),
    'IC/LPO/20260159': ('coming', 'Waiting for security cheque'),
    'IC/LPO/20260160': ('came', ''),
    'IC/LPO/20260161': ('bill_ok', ''),
    'IC/LPO/20260162': ('coming', 'hold by site'),
    'IC/LPO/20260163': ('coming', 'hold by site'),
    'IC/LPO/20260164': ('coming', 'hold by site people'),
    'IC/LPO/20260165': ('came', ''),
    'IC/LPO/20260166': ('came', ''),
    'IC/LPO/20260167': ('no_bill', 'Invoice submission pending'),
    'IC/LPO/20260168': ('came', ''),
    'IC/LPO/20260169': ('came', ''),
    'IC/LPO/20260171': ('no_bill', 'Invoice submission pending'),
    'MR-0038': ('ignore', 'cancelled by Prem'),
}


def find_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from clear_test_returns import _find_database_url
    return _find_database_url()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    url = find_url()
    if not url:
        sys.exit("Could not find DATABASE_URL.")
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("INFINIA_NO_PUSH", "1")
    os.environ.setdefault("INFINIA_NO_SCHED", "1")
    import models
    import main as M
    import purchasing as P
    import purchtrack as T
    from database import SessionLocal
    db = SessionLocal()
    try:
        who = db.query(models.User).filter(models.User.username == "arun").first() or \
            db.query(models.User).filter(models.User.role == "admin").first()
        stock0 = M._stock_map(db) if hasattr(M, "_stock_map") else None
        book = P.Book(db)
        orders = {o.ref: o for o in book.orders}
        reqs = {r.ref: r for r in book.reqs}
        done, kept, skipped, shafeeq, stockq, already = [], [], [], [], [], []
        print(("DRY RUN - nothing is written" if not a.apply else "WRITING") + f" - {TAG}\n")
        for ref, (ans, rem) in sorted(ANSWERS.items()):
            why = rem or {"came": "All came (clean-up)", "bill_ok": "Bill OK (clean-up)", "cancel": "Cancelled (clean-up)",
                          "ignore": "Ignore - close (clean-up)"}.get(ans, "")
            if ref.startswith("MR-"):
                mr = reqs.get(ref)
                if not mr:
                    skipped.append(f"{ref}: not found"); continue
                if mr.status in ("closed", "rejected", "delivered"):
                    already.append(f"{ref}: already {mr.status}"); continue
                if ans in ("ignore", "not_needed"):
                    done.append(f"{ref}: request closed - {why}")
                    if a.apply:
                        mr.status, mr.closed_on = "closed", M._dubai_today()
                        mr.office_remark = (f"Closed in the clean-up: {why}")[:500]
                        db.add(models.AuditLog(user_id=who.id if who else None, action="purchasing_cleanup", details=f"{ref}: closed - {why} [{TAG}]"))
                else:
                    kept.append(f"{ref}: kept open ({ans})")
                continue
            o = orders.get(ref)
            if not o:
                skipped.append(f"{ref}: not found"); continue
            p = book.of(o)
            st = p["status"]
            left = [x for x in p["lines"] if x["remaining"] > EPS]
            came = [x for x in p["lines"] if x["delivered"] > EPS]
            if st in ("cancelled", "superseded"):
                already.append(f"{ref}: already {st}"); continue
            if ans == "came":
                # what may physically be in the store / at a site now and is NOT in stock after this: assets, rentals,
                # anything delivered to the central store - listed for Amal to book if it is really there
                for x in left:
                    l = next((y for y in o.lines if y.id == x["line_id"]), None)
                    it = book.items.get(l.item_id) if l is not None else None
                    kind = "rental" if x["rental"] else (it.item_type if it is not None else "")
                    if not x["service"] and (kind in ("asset", "rental", "returnable") or (x["location"] or "") == ""):
                        stockq.append(f"{ref} {o.supplier_name}: {x['remaining']:g} {x['unit']} {x['description'][:50]} - "
                                      + ("RENTAL - not on the Rentals page" if kind == "rental" else "ASSET - not on the asset list" if kind in ("asset", "returnable")
                                         else "to the central store - not in store stock"))
                parts = []
                if left:
                    parts.append("still to come recorded as came earlier, no stock: " + "; ".join(f"{x['remaining']:g} {x['unit']} {x['description'][:40]}" for x in left))
                if not o.bill_checked:
                    parts.append("bill check closed")
                if not parts:
                    already.append(f"{ref}: already closed"); continue
                done.append(f"{ref} ({o.supplier_name}): " + "; ".join(parts))
                if not (o.order_date and o.order_date < date(2026, 10, 1)):   # before Zoho (from 01/10) - accounts booked those direct
                    shafeeq.append(f"{ref} {o.supplier_name}: closed as all came - expect the full LPO bill (AED {M.lpo_total(o):,.2f})")
                if a.apply:
                    T._close_lpo_old(db, o, "came", f"Clean-up: {why}", True, who)
                    db.add(models.AuditLog(user_id=who.id if who else None, action="purchasing_cleanup", details=f"{ref}: all came - {'; '.join(parts)} [{TAG}]"))
            elif ans == "bill_ok":
                if o.bill_checked:
                    already.append(f"{ref}: bill already checked"); continue
                done.append(f"{ref} ({o.supplier_name}): bill check closed - bill OK" + (f" ({len(left)} line(s) still to come stay open)" if left else ""))
                if a.apply:
                    o.bill_checked, o.bill_checked_by, o.bill_checked_at = True, (who.id if who else None), datetime.now(timezone.utc)
                    o.bill_note = (f"Bill OK - {TAG}" + (f": {rem}" if rem else ""))[:200]
                    db.add(models.AuditLog(user_id=who.id if who else None, action="purchasing_cleanup", details=f"{ref}: bill OK, bill check closed [{TAG}]"))
            elif ans == "cancel":
                if came:
                    # a delivery is booked, so it is not cancelled (that would take stock back); the rest is closed as
                    # not coming and the bill check is closed - the PO is already cancelled in Zoho, no bill to come
                    if o.bill_checked and not left:
                        already.append(f"{ref}: already closed"); continue
                    got = "; ".join(f"{x['delivered']:g} {x['unit']} {x['description'][:40]}" for x in came)
                    done.append(f"{ref} ({o.supplier_name}): marked Cancel, but {got} was booked as delivered - closed, delivery kept, "
                                + (f"{len(left)} line(s) left closed as not coming, " if left else "") + "no bill to come (cancelled in Zoho)")
                    if a.apply:
                        T._close_lpo_old(db, o, "not_coming", f"Clean-up: {why}", True, who)
                        o.bill_note = f"No bill - Arun marked Cancel; PO already cancelled in Zoho. Delivery kept. {TAG}"[:200]
                        db.add(models.AuditLog(user_id=who.id if who else None, action="purchasing_cleanup", details=f"{ref}: closed, no bill (cancel with delivery) [{TAG}]"))
                    continue
                done.append(f"{ref} ({o.supplier_name}): LPO cancelled - {why}; cancel the PO in Zoho by hand")
                shafeeq.append(f"{ref} {o.supplier_name}: CANCELLED - cancel the PO in Zoho (AED {M.lpo_total(o):,.2f})")
                if a.apply:
                    M._cancel_lpo_core(db, o, f"Clean-up: {why}", not_needed=True, user=who, call_zoho=False)
                    db.add(models.AuditLog(user_id=who.id if who else None, action="purchasing_cleanup", details=f"{ref}: cancelled - {why} [{TAG}]"))
            elif ans in ("coming", "no_bill"):
                hold = ans == "coming" and "hold" in rem.lower()
                kept.append(f"{ref} ({o.supplier_name}): kept open - {'still coming' if ans == 'coming' else 'waiting for the bill'}" + (f" ({rem})" if rem else "")
                            + (" -> On hold (site)" if hold else ""))
                if a.apply and rem:
                    if ans == "coming":
                        o.part_note = rem[:200]
                        if hold:
                            o.part_why = "site"
                    else:
                        o.bill_note = rem[:200]
            else:
                skipped.append(f"{ref}: answer '{ans}' not understood")
        open_now = [o.ref for o in book.orders if book.of(o)["status"] not in ("cancelled", "superseded", "delivered", "closed")]
        print(f"CLOSED / CHANGED ({len(done)}):"); [print("  - " + x) for x in done]
        print(f"\nKEPT OPEN as answered ({len(kept)}):"); [print("  - " + x) for x in kept]
        print(f"\nNOT APPLIED - for a decision ({len(skipped)}):"); [print("  - " + x) for x in skipped]
        print(f"\nALREADY DONE (nothing to do) ({len(already)}): " + ", ".join(x.split(":")[0] for x in already))
        not_on_form = [r for r in open_now if r not in ANSWERS]
        print(f"\nOpen in the portal but not on the form (new since, or left blank) ({len(not_on_form)}): " + ", ".join(not_on_form))
        print(f"\nSTOCK QUESTION - closed as came, but NOT in stock after this; Amal books any that is really there ({len(stockq)}):")
        [print("  - " + x) for x in stockq]
        print(f"\nFOR SHAFEEQ (Zoho) ({len(shafeeq)}):"); [print("  - " + x) for x in shafeeq]
        if not a.apply:
            print("\nDry run - nothing was written. Run again with --apply to make these changes.")
            return
        db.flush()
        if stock0 is not None and M._stock_map(db) != stock0:
            db.rollback()
            sys.exit("Refused: stock would change - nothing written.")
        db.commit()
        print(f"\nWritten - tagged '{TAG}'. Stock unchanged (checked).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
