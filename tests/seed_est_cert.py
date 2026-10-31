"""Seed for est_cert_figure_ui_test.js: project T914 with IPA 06 and IPA 07 (live 914 figures); IPA 07's remarks
keep the certificate's own figures as Previous records saved them (amount due 153,134.00).

    cd app && DATABASE_URL=sqlite:////tmp/run_js.db INFINIA_NO_SCHED=1 python3 ../tests/seed_est_cert.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import main  # noqa: F401  (estimation is loaded through main)
from database import SessionLocal, engine
import estimation as E

E.create_tables(engine)
db = SessionLocal()
if not db.query(E.EstProject).filter(E.EstProject.code == "T914").first():
    p = E.EstProject(code="T914", name="Certificate figure test", ret_pct=10, vat_pct=5, contract_value=4850000)
    db.add(p); db.commit()
    rem = "Previous record: 914 - IPA - 07 - R2.xlsx · bill 7-R2 · previous payments 1,172,735.24 · VAT 7,292.09 · amount due 153,134.00"
    for seq, cert, ret, st, r in ((6, 1300104.03, 127369.05, "Paid", ""), (7, 1462150.81, 143573.73, "Invoiced", rem)):
        db.add(E.EstClientPC(project_id=p.id, seq=seq, claimed_cum=cert, certified_cum=cert, ret_cum=ret, ret_auto=False, adv_auto=False,
                             status=st, remarks=r))
    db.commit()
db.close()
print("seeded")
