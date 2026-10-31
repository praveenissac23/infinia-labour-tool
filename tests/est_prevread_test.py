"""Estimation > Previous records: the client bill (IPA) and subcontractor PC readers, on the words the browser reads from
real files - Excel, typed PDFs and scanned PDFs (text recognition on the computer). Every figure must be the
certificate's own, and every check of the certificate's arithmetic must agree.
    cd app && DATABASE_URL=sqlite:////tmp/epr.db INFINIA_NO_SCHED=1 python3 ../tests/est_prevread_test.py
"""
import os, sys, json
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "prev")
def read(kind, name, subs=None):
    lines = json.load(open(os.path.join(FX, name)))["lines"]
    r = c.post(f"/store/est/read/{kind}", json={"lines": lines, "subs": subs or []}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()
def same(r, want):
    f = r["fields"]
    return all(abs((f.get(k) or 0) - v) < 0.005 if isinstance(v, float) else f.get(k) == v for k, v in want.items()), {k: f.get(k) for k in want}

IPA = {
    "913-IPA_09.xlsx.json": {"seq": 9, "claimed_cum": 4798952.78, "adv_rec_cum": 291990.93, "previous": 3565182.86, "vat": 47088.95, "authority": 280.0, "total": 989148.0, "submitted": "2026-10-06"},
    "scan_829b1b6e-913-IPA_09.pdf.json": {"seq": 9, "claimed_cum": 4798952.78, "adv_rec_cum": 291990.93, "previous": 3565182.86, "total": 989148.0},
    "909-IPA09.xlsx.json": {"seq": 9, "claimed_cum": 3589674.7, "adv_rec_cum": 393189.31, "previous": 2363586.66, "vat": 41819.94, "total": 878219.0},
    "909-IPA09.pdf.json": {"seq": 9, "claimed_cum": 3589674.7, "adv_rec_cum": 393189.31, "total": 878219.0},
    "scan_6c95d3d9-909-IPA09.pdf.json": {"seq": 9, "claimed_cum": 3589674.7, "adv_rec_cum": 393189.31, "total": 878219.0},
    "911-IPA_Pre_Final_Bill.xlsx.json": {"pc_type": "Final", "claimed_cum": 4941791.26, "adv_rec_cum": 637152.0, "authority": 360.0, "total": 119885.0},
    "914_-_IPA_-_07_-_R2.xlsx.json": {"seq": 7, "claimed_cum": 1462150.81, "variation": 26413.48, "ret_cum": 143573.73, "total": 153134.0},
}
for name, want in IPA.items():
    r = read("ipa", name)
    ok, got = same(r, want)
    ck(f"client bill {name}: every figure as on the bill", ok, got)
    ck(f"client bill {name}: the bill's own sums agree", r["checks"] and all(x["ok"] for x in r["checks"]), r["checks"])

RAIDA = [{"id": 7, "name": "Al Raida Electromechanical Services L.L.C"}, {"id": 8, "name": "Woodcraft Interiors"}]
PC = {
    "912-MEP-PC03-Raida_-_for_review_3.pdf.json": {"sub_id": 7, "seq": 3, "work_cum": 10125.0, "var_cum": 5000.0, "adv_cum": 29300.0, "adv_rec_cum": 1012.5, "ret_cum": 1512.5, "prev_cert": 34300.0, "net": 7600.0, "vat": 380.0, "total": 7980.0, "issued": "2026-10-10", "inv_ref": "912 Summary PC-01"},
    "908_-PC08_-MEP.xlsx.json": {"sub_id": 7, "seq": 8, "work_cum": 222400.0, "var_cum": 24500.0, "adv_cum": 35000.0, "adv_rec_cum": 22240.0, "ret_cum": 24690.0, "prev_cert": 155412.65, "net": 79557.35, "total": 83535.22},
    "911_-PC02_R1.xlsx.json": {"seq": 2, "work_cum": 42904.97, "ret_cum": 4290.5, "prev_cert": 23916.06, "net": 14698.41, "inv_ref": "NCSTS/411/2025", "trn": "100595215300003"},
    "915-RoyalEverest-PC12_-_For_review.pdf.json": {"seq": 12, "work_cum": 104037.5, "var_cum": 1850.0, "ret_cum": 10588.75, "ret_rel_cum": 10588.75, "other_cum": 950.0, "prev_cert": 95198.75, "net": 9738.75, "total": 10226.0, "sub_name": "ROYAL EVERST TECHNICAL SERVICES"},
    "scan_pc915.pdf.json": {"seq": 12, "work_cum": 104037.5, "var_cum": 1850.0, "ret_cum": 10588.75, "ret_rel_cum": 10588.75, "other_cum": 950.0, "prev_cert": 95198.75, "net": 9738.75, "total": 10226.0},
    "913-Shoring-PC05-OneGB_-_For_review.pdf.json": {"seq": 5, "work_cum": 257820.0, "other_cum": 14151.0, "prev_cert": 209467.0, "net": 34202.0, "total": 35912.0},
    "scan_pc913.pdf.json": {"seq": 5, "work_cum": 257820.0, "other_cum": 14151.0, "prev_cert": 209467.0, "net": 34202.0, "total": 35912.0},
    "scan_pc910.pdf.json": {"seq": 5, "work_cum": 159906.76, "var_cum": 28742.73, "ret_cum": 18864.95, "prev_cert": 136730.64, "net": 33053.9, "total": 34706.6},
}
for name, want in PC.items():
    r = read("subpc", name, RAIDA)
    ok, got = same(r, want)
    ck(f"subcontractor PC {name}: every figure as on the certificate", ok, got)
    ck(f"subcontractor PC {name}: A + B - C + D - E, VAT and total agree", r["checks"] and all(x["ok"] for x in r["checks"]), r["checks"])
r = read("subpc", "915-RoyalEverest-PC12_-_For_review.pdf.json", RAIDA)
ck("a subcontractor not on the project is offered as a new one (not matched to another)", r["fields"].get("new_sub") and "sub_id" not in r["fields"], r["fields"].get("new_sub"))
r = read("subpc", "912-MEP-PC03-Raida_-_for_review_3.pdf.json", [])
ck("the subcontractor is the other M/s. on the details line - not the client", r["fields"].get("sub_name") == "AL RAIDA ELECTROMECHANICAL SERVICES LLC", r["fields"].get("sub_name"))
# a figure misread: the check says so
lines = json.load(open(os.path.join(FX, "915-RoyalEverest-PC12_-_For_review.pdf.json")))["lines"]
for l in lines:
    if "Retention" in l.get("t", "") and "10,588.75" in l.get("t", "") and "Release" not in l.get("t", ""):
        l["c"] = [x.replace("10,588.75", "10,688.75") for x in l["c"]]; l["t"] = l["t"].replace("10,588.75", "10,688.75"); break
r = c.post("/store/est/read/subpc", json={"lines": lines, "subs": []}, headers=H).json()
# caught: a failed sum (the older reader), or - read on the server's reader (app/docread) - the misread retention is not
# taken as "ok": left out / marked check, or put right from the sums; the amount due stays the certificate's own
ret, dret = r["fields"].get("ret_cum"), (r.get("detail") or {}).get("ret_cum") or {}
caught = any(not x["ok"] and "net amount" in x["name"] for x in r["checks"]) or \
    (abs((r["fields"].get("total") or 0) - 10226.0) < 0.01 and not (ret is not None and abs(ret - 10688.75) < 0.01 and dret.get("status") == "ok"))
ck("a misread figure is caught by the certificate's own sum", caught, [ret, dret, r["fields"].get("total"), r["checks"]])
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)
