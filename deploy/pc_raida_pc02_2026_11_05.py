"""914 and 915 - Al Raida Electromechanical (MEP): PC 02 on each, as Anoop certified them (5 Nov 2026). Run after
deploy/sub_raida_boq_2026_11_05.py --apply (the schedules their lines are on).

914 (RAIDA_914_MEP_PC-02.xls) - certified as claimed: 16,250.00 = Plumbing 11,780.00 + Electrical 4,470.00.
915 (RAIDA_915_MEP_PC-02.xls) - claimed 9,252.00 (Plumbing 6,007.50 + Electrical 3,244.50), certified 8,487.00
    (Plumbing 6,007.50 + Electrical 2,479.50); the claim is kept in the printed remarks.
Line by line as in Raida's sheets. Each goes in the way the
app makes a certificate (the same functions as + PC and Save on the sheet): Received today; the advance recovery, retention
and the amount due are worked out by the app's own rules. The sign-off (certified at site, QS, contracts manager,
accounts, MD) is left to the people - nothing is signed here.
Stops if a PC 02 is already there, or a line is not found on the schedule. Run twice = nothing added twice.

    cd ~/infinia-labour-tool && venv/bin/python deploy/pc_raida_pc02_2026_11_05.py            (dry run - shows it)
    cd ~/infinia-labour-tool && venv/bin/python deploy/pc_raida_pc02_2026_11_05.py --apply    (writes it)
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)

# per project: (bill, the line on the schedule, its amount, % done to date) - Raida's PC 02 sheets; the bill totals; remarks
PCS = {
    "914": {"value": 568800.00, "remarks": "Nil", "expect": {"PLUMBING": 11780.00, "ELECTRICAL": 4470.00}, "claim": [
        ("PLUMBING", "Supply, Install, Testing uPVC pipe work of any kind", 21000.00, 45),
        ("PLUMBING", "Clean Out, CO", 12000.00, 10),
        ("PLUMBING", "Manholes", 5000.00, 10),
        ("PLUMBING", "Gally Trap with Cover 300x300 HD type", 4800.00, 10),
        ("PLUMBING", "Swimming Pool -01", 3000.00, 5),
        ("ELECTRICAL", "20 A Weather Proof TPN Isolator to IP-65", 9000.00, 5),
        ("ELECTRICAL", "30 A Weather Proof TPN Isolator to IP-65", 6400.00, 5),
        ("ELECTRICAL", "40 A Weather Proof TPN Isolator to IP-65", 3500.00, 5),
        ("ELECTRICAL", "63 A Weather Proof TPN Isolator to IP-65", 4500.00, 5),
        ("ELECTRICAL", "80 A Weather Proof TPN Isolator to IP-65", 5000.00, 5),
        ("ELECTRICAL", "Lighting points, generally", 15000.00, 2),
        ("ELECTRICAL", "TELEPHONE AND DATA SYSTEM (Containment only)", 15000.00, 5),
        ("ELECTRICAL", "50mm dia uPVC duct with two Nylon Rope", 4000.00, 50)]},
    "915": {"value": 580500.00, "expect": {"PLUMBING": 6007.50, "ELECTRICAL": 2479.50},
            "remarks": "Claimed 9,252.00 (Plumbing 6,007.50 + Electrical 3,244.50); certified 8,487.00 (Plumbing 6,007.50 + Electrical 2,479.50).",
            "claim": [
        ("PLUMBING", "Supply, Install, Testing uPVC pipe work of any kind", 21600.00, 25),
        ("PLUMBING", "Supply, Install & Testing uPVC rainwater pipework", 9450.00, 5),
        ("PLUMBING", "Swimming Pool -01", 2700.00, 5),
        ("ELECTRICAL", "kWHR", 7650.00, 5),
        ("ELECTRICAL", "20 A Weather Proof TPN Isolator to IP-65", 8100.00, 5),
        ("ELECTRICAL", "30 A Weather Proof TPN Isolator to IP-65", 5760.00, 5),
        ("ELECTRICAL", "40 A Weather Proof TPN Isolator to IP-65", 3150.00, 5),
        ("ELECTRICAL", "63 A Weather Proof TPN Isolator to IP-65", 4050.00, 5),
        ("ELECTRICAL", "80 A Weather Proof TPN Isolator to IP-65", 4500.00, 5),
        ("ELECTRICAL", "TELEPHONE AND DATA SYSTEM (Containment only)", 13500.00, 5),
        ("ELECTRICAL", "50mm dia uPVC duct with two Nylon Rope", 3600.00, 4)]},
}


def find_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from clear_test_returns import _find_database_url
    return _find_database_url()


def norm(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def one(db, E, S, code, spec, apply, user):
    sub = [x for x in db.query(E.EstSub).filter(E.EstSub.name.ilike("%AL RAIDA%")).all()
           if (db.get(E.EstProject, x.project_id).code or "") == code]
    if len(sub) != 1:
        sys.exit(f"Expected one {code} Al Raida subcontract, found {len(sub)} - nothing done.")
    sub = sub[0]
    pcs = db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == sub.id).order_by(E.EstSubPC.seq).all()
    print(f"\n===== {code} {sub.name} - value {sub.value:,.2f}; PCs now: " + ", ".join(f"PC {p.seq:02d} {p.pc_type} {p.status}" for p in pcs))
    if any((p.seq or 0) >= 2 for p in pcs):
        print("  There is already a PC 02 (or later) - left as it is.")
        return
    items = db.query(S.EstSubItem).filter(S.EstSubItem.sub_id == sub.id, S.EstSubItem.is_var == False).all()  # noqa: E712
    if abs(sum(i.amount or 0 for i in items) - spec["value"]) > 0.01:
        sys.exit(f"{code}: the schedule is not Raida's final BOQ ({spec['value']:,.2f}) - run deploy/sub_raida_boq_2026_11_05.py --apply first.")
    lines, by_bill = [], {}
    for bill, desc, amt, pct in spec["claim"]:
        hit = [i for i in items if i.bill == bill and abs((i.amount or 0) - amt) < 0.01 and norm(i.description).startswith(norm(desc))]
        if len(hit) != 1:
            sys.exit(f"{code}: '{desc}' ({amt:,.2f}) found {len(hit)} times on the schedule - nothing done.")
        v = round(amt * pct / 100.0, 2)
        by_bill[bill] = by_bill.get(bill, 0) + v
        lines.append({"item_id": hit[0].id, "pct": pct})
        print(f"  {bill:<11}{desc[:55]:<56}{amt:>11,.2f} x {pct:>3}% = {v:>9,.2f}")
    for b, want in spec["expect"].items():
        if abs(by_bill.get(b, 0) - want) > 0.01:
            sys.exit(f"{code}: {b} adds up to {by_bill.get(b, 0):,.2f}, Raida's sheet says {want:,.2f} - nothing done.")
    print(f"  Work to date: {sum(by_bill.values()):,.2f}  (" + " + ".join(f"{b.title()} {v:,.2f}" for b, v in by_bill.items()) + ")")
    print(f"  Remarks: {spec['remarks']}")
    if not apply:
        return
    rid = E.add_row("subpcs", {"sub_id": sub.id, "pc_type": "Interim", "remarks": spec["remarks"]}, db=db, user=user)["id"]
    S.put_sheet(rid, {"lines": lines}, db=db, user=user)
    db.expire_all()
    pc = db.get(E.EstSubPC, rid)
    print(f"  Done: PC {pc.seq:02d} ({pc.status}) - work to date {pc.work_cum:,.2f}, advance recovered to date {pc.adv_rec_cum or 0:,.2f}, "
          f"retention to date {pc.ret_cum or 0:,.2f}.")


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
    import main as M  # noqa: F401 - the tables and columns
    import models
    import estimation as E
    import est_pcsheet as S
    from database import SessionLocal
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.role == "admin").order_by(models.User.id).first()
        for code, spec in PCS.items():
            one(db, E, S, code, spec, a.apply, user)
        if not a.apply:
            print("\nDry run - nothing written. Run again with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
