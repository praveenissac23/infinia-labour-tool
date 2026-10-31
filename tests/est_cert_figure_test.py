"""Client certificates record what the certificate certifies (owner, 31 Oct 2026: "match the certificate").

The consultant rounds to whole dirhams and books previous payments his own way; the app's exact working can be a
few fils off. Live examples, rebuilt here with the live figures:
  914 IPA07   worked out 153,134.21 - certificate 153,134   (kept in the PC's remarks by Previous records)
  915 IPA07   worked out 329,181.94 - certificate 329,182   (the bill workbook for the same work done)
  914 MEP PC1 worked out  17,548.59 - certificate  17,549   (read from the certificate / typed)
  914 MEP bill 3 previous payments 24,829.52 on the certificate - register net to date 24,829.75
The certificate's figure is the official one (amount due, net, VAT); the working shows only as a small note when it
differs. Records already stored are not rewritten - the figure is shown from what is kept, and stored on the next save.

    cd app && DATABASE_URL=sqlite:////tmp/ecf.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/est_cert_figure_test.py
(an empty database)
"""
import os, sys, io
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import openpyxl
import main as M
import estimation as E
import est_bills
from database import SessionLocal

c = TestClient(M.app); c.__enter__()
FAIL = []


def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}"))
    if not ok:
        FAIL.append(n)


H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
api = lambda m, u, j=None: getattr(c, m)(u, headers=H, **({"json": j} if j is not None else {}))
DL = lambda: c.post("/auth/download-token", headers=H).json()["token"]

db = SessionLocal()
p14 = E.EstProject(code="T914", name="Cert test 914", ret_pct=10, vat_pct=5)
p15 = E.EstProject(code="T915", name="Cert test 915", ret_pct=10, vat_pct=5)
db.add_all([p14, p15]); db.commit()
sc = E.EstContract(project_id=p14.id, name="Shell & Core", value=4850000, ret_pct=10, vat_pct=5, sort=1)
mep = E.EstContract(project_id=p14.id, name="MEP", value=1620000, adv_pct=20, ret_pct=10, vat_pct=5, sort=2)
k15 = E.EstContract(project_id=p15.id, name="Main", value=3000000, ret_pct=10, vat_pct=5, sort=1)
db.add_all([sc, mep, k15]); db.commit()
PC = lambda pid, kid, seq, cert, ret, st, rem="", adv_rec=0, adv=0: E.EstClientPC(
    project_id=pid, contract_id=kid, seq=seq, claimed_cum=cert, certified_cum=cert, ret_cum=ret, ret_auto=False, adv_rec_cum=adv_rec,
    adv_auto=False, adv_amount=adv, status=st, remarks=rem)
REM7 = ("Previous record: 914 - IPA - 07 - R2.xlsx · bill 7-R2 · previous payments 1,172,735.24 · VAT 7,292.09 · amount due 153,134.00")
a6 = PC(p14.id, sc.id, 6, 1300104.03, 127369.05, "Paid")
a7 = PC(p14.id, sc.id, 7, 1462150.81, 143573.73, "Invoiced", REM7)
b6 = PC(p15.id, k15.id, 6, 985197.13, 98117.16, "Paid")
b7 = PC(p15.id, k15.id, 7, 1333537.81, 132951.23, "Invoiced")
m1 = PC(p14.id, mep.id, 1, 23875.62, 2387.56, "Certified", adv_rec=4775.12)
m2 = PC(p14.id, mep.id, 2, 35471.07, 3547.11, "Paid", adv_rec=7094.21)
db.add_all([a6, a7, b6, b7, m1, m2]); db.commit()
# 915's bill workbook for IPA 07: the consultant's format worked out as Excel does - its amount due 329,182
db.add(est_bills.EstBill(project_id=p15.id, format_id=1, contract_id=k15.id, seq=1, label="7", status="Certified",
                         total_due=329182, work_done=1333537.81))
db.commit()
IDS = dict(p14=p14.id, p15=p15.id, sc=sc.id, mep=mep.id, a7=a7.id, b7=b7.id, m1=m1.id, m2=m2.id, a6=a6.id)
db.close()


def bundle(pid):
    return api("get", f"/store/est/projects/{pid}").json()


def row(b, rid):
    return next(x for x in b["clientpcs"] if x["id"] == rid)


# ---- 914 IPA07: the figure kept in the remarks of an older record ------------------------------------------------
b = bundle(IDS["p14"])
r = row(b, IDS["a7"])
ck("914 IPA07: worked out 153,134.21 (the app's own working, kept as the cross-check)", r["calc_payable"] == 153134.21, r["calc_payable"])
ck("914 IPA07: the register shows the certificate's 153,134.00 as the amount due", r["payable"] == 153134.0, r["payable"])
ck("914 IPA07: VAT as printed 7,292.09, net 145,841.91", r["vat"] == 7292.09 and r["this"] == 145841.91, (r["vat"], r["this"]))
NOTE = "Certificate 153,134.00 · worked out 153,134.21 · difference −" + "0.21 (consultant rounds to whole dirhams)"
ck(f'914 IPA07: the note "{NOTE}"', r["cert_note"] == NOTE, r["cert_note"])
ck("914 IPA07: previous payments as printed 1,172,735.24 against 1,172,734.98 worked out",
   r["cert_prev_note"] == "Previous payments on the certificate 1,172,735.24 · worked out 1,172,734.98 · difference +0.26", r["cert_prev_note"])
db = SessionLocal()
ck("914 IPA07: the stored record is NOT rewritten (nothing stored until it is saved)", db.get(E.EstClientPC, IDS["a7"]).cert_due is None)
db.close()
r6 = row(b, IDS["a6"])
ck("914 IPA06 (no certificate figure kept): its worked-out figure stands, no note", r6["cert"] is None and r6["cert_note"] == ""
   and r6["payable"] == r6["calc_payable"], r6)
api("patch", f"/store/est/clientpcs/{IDS['a7']}", {"invoice_no": "INV-T-07"})
db = SessionLocal()
x = db.get(E.EstClientPC, IDS["a7"])
ck("914 IPA07 saved again: the certificate's figures are now stored on the record",
   (x.cert_due, x.cert_vat, x.cert_prev) == (153134.0, 7292.09, 1172735.24) and "remarks" in x.cert_src, (x.cert_due, x.cert_vat, x.cert_prev, x.cert_src))
db.close()
ck("... and the register still shows 153,134.00", row(bundle(IDS["p14"]), IDS["a7"])["payable"] == 153134.0)

# ---- 915 IPA07: the bill workbook for the same work done ----------------------------------------------------------
r = row(bundle(IDS["p15"]), IDS["b7"])
ck("915 IPA07: worked out 329,181.94, certificate (bill workbook) 329,182.00", r["calc_payable"] == 329181.94 and r["payable"] == 329182.0,
   (r["calc_payable"], r["payable"]))
ck("915 IPA07: note says +0.06", r["cert_note"] == "Certificate 329,182.00 · worked out 329,181.94 · difference +0.06 (consultant rounds to whole dirhams)",
   r["cert_note"])
ck("915 IPA07: source bill workbook", r["cert"]["source"] == "bill workbook", r["cert"])

# ---- 914 MEP PC1: typed / read from the certificate ---------------------------------------------------------------
r = row(bundle(IDS["p14"]), IDS["m1"])
ck("914 MEP PC1 before: worked out 17,548.59, nothing known from the certificate", r["payable"] == 17548.59 and r["cert"] is None, r)
rr = api("patch", f"/store/est/clientpcs/{IDS['m1']}", {"cert_due": 17549, "cert_src": "certificate document"})
r = row(bundle(IDS["p14"]), IDS["m1"])
ck("914 MEP PC1 with the certificate's 17,549: the register shows 17,549.00", rr.status_code == 200 and r["payable"] == 17549.0
   and r["cert"]["source"] == "certificate document", (rr.text, r.get("payable")))
ck("914 MEP PC1: note says +0.41", r["cert_note"] == "Certificate 17,549.00 · worked out 17,548.59 · difference +0.41 (consultant rounds to whole dirhams)",
   r["cert_note"])
ck("914 MEP PC1: VAT taken from the amount due (17,549 / 1.05 x 5%) when not printed", r["vat"] == 835.67 and r["this"] == 16713.33, (r["vat"], r["this"]))
rr = api("patch", f"/store/est/clientpcs/{IDS['m1']}", {"cert_due": ""})
r = row(bundle(IDS["p14"]), IDS["m1"])
ck("cleared: back to the worked-out 17,548.59", r["payable"] == 17548.59 and r["cert"] is None, r.get("payable"))

# ---- 914 MEP bill 3: previous payments as printed ------------------------------------------------------------------
rr = api("post", "/store/est/clientpcs", {"project_id": IDS["p14"], "contract_id": IDS["mep"], "seq": 3, "claimed_cum": 52000, "certified_cum": 52000,
                                          "ret_cum": 5200, "adv_rec_cum": 10400, "adv_auto": False, "ret_auto": False, "status": "Submitted",
                                          "cert_due": 38140, "cert_vat": 1816.19, "cert_prev": 24829.52, "cert_src": "certificate document"})
ck("914 MEP bill 3 saved with the certificate's figures", rr.status_code == 200, rr.text)
m3 = rr.json()["id"]
r = row(bundle(IDS["p14"]), m3)
ck("914 MEP bill 3: previous payments 24,829.52 as printed; register net to date 24,829.75 shown only as the check",
   r["cert"]["prev"] == 24829.52 and r["calc_prev_net"] == 24829.75
   and r["cert_prev_note"] == "Previous payments on the certificate 24,829.52 · worked out 24,829.75 · difference −" + "0.23", r)
ck("914 MEP bill 3: amount due, VAT and net as printed", r["payable"] == 38140.0 and r["vat"] == 1816.19 and r["this"] == 36323.81, r)

# ---- everything that reads the PC uses the certified figure ----------------------------------------------------------
xl = c.get(f"/export/est/clientpcs?token={DL()}&format=excel&pid={IDS['p14']}")
wb = openpyxl.load_workbook(io.BytesIO(xl.content)); ws = wb.active
vals = [[v for v in r_ if v is not None] for r_ in ws.iter_rows(values_only=True)]
flat = " ".join(str(v) for r_ in vals for v in r_)
ck("Excel: Total 153,134 for IPA 07 and the cross-check note beside it", any(153134 in r_ for r_ in vals) and "worked out 153,134.21" in flat, flat[:600])

# ---- no certificate figure anywhere: unchanged ------------------------------------------------------------------------
db = SessionLocal()
p9 = E.EstProject(code="T999", name="Plain", ret_pct=10, vat_pct=5); db.add(p9); db.commit()
db.add(E.EstClientPC(project_id=p9.id, seq=1, claimed_cum=100000, certified_cum=100000, status="Certified")); db.commit()
pid9 = p9.id; db.close()
r = bundle(pid9)["clientpcs"][0]
ck("no certificate figure: amount due = worked out (100,000 + VAT = 105,000.00), no note",
   r["payable"] == 105000.0 and r["calc_payable"] == 105000.0 and r["cert"] is None and r["cert_note"] == "", r)

print(f"{len(FAIL)} FAILED" if FAIL else "ALL PASS")
sys.exit(1 if FAIL else 0)
