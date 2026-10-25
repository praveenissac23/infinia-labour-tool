"""ESTIMATION GO-LIVE (26 Oct 2026) - Estimation starts clean, once.

Kept: the projects (every project number and its details), the real variation logs (the ones the QS team sent -
908, 909, 911, 912, 913, 919) and everything in Trello. Taken out: subcontracts and everything on them (variations
to subcontracts, item schedules, payment certificates with their lines and deductions), client payment
certificates, BOQ & budget, RFIs, submittals, NOCs & approvals, finalization logs, tenders, and the Bills tab
(bill formats and bills; the people's uploaded signatures stay). The test data (est_dummy) is taken out first, with its own reverse, so the test
variations go and a template row it had filled in gets its old values back before it is removed.

Every row taken out is first written to data/estimation/golive_backup_<time>.json - nothing is lost for good. It
runs once: a Setting marks it done. A project opened afterwards gets its standard NOCs & approvals list and
finalization log again, empty, as a new project does.
"""
import base64
import json
import os
from datetime import date, datetime

import models

DONE_KEY = "est_golive_2026_10_26"


def _plain(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"b64": base64.b64encode(bytes(v)).decode()}
    return v


def run(SessionLocal):
    import estimation as E
    import est_pcsheet as S
    import est_bills as BL
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == DONE_KEY).first():
            return
        # children first, so nothing is left pointing at a removed row
        gone = [S.EstPCLine, S.EstPCDeduct, S.EstSubItem, E.EstSubVO, E.EstSubPC, E.EstSub, E.EstClientPC, E.EstBoq,
                E.EstLog, E.EstFinal, E.EstTender, E.EstFile, BL.EstBill, BL.EstBillFormat]
        backup = {}
        for m in gone + [E.EstVariation, E.EstProject]:
            cols = [c.name for c in m.__table__.columns]
            backup[m.__tablename__] = [{c: _plain(getattr(r, c)) for c in cols} for r in db.query(m).all()]
        d = os.path.abspath(E.FILES)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"golive_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w") as fh:
            json.dump(backup, fh)
        n = {}
        for m in gone:
            n[m.__tablename__] = db.query(m).delete(synchronize_session=False)
        # the variations stay; the subcontract they were passed to is gone
        db.query(E.EstVariation).filter(E.EstVariation.sub_id.isnot(None)).update({E.EstVariation.sub_id: None}, synchronize_session=False)
        db.add(models.Setting(key=DONE_KEY, value=json.dumps({"backup": path, "removed": n})))
        db.commit()
        print(f"Estimation go-live: {sum(n.values())} rows taken out (backup {path}); projects, variations and Trello kept")
    except Exception:
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()
