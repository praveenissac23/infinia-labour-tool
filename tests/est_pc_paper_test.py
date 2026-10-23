"""Subcontractor payment certificate paper: client and plot from the project (else the site / invoices), the IPC
issued date (today unless set), the subcontractor's address, phone, mobile and TRN, and the retention %.
    cd app && rm -f /tmp/epp.db && DATABASE_URL=sqlite:////tmp/epp.db INFINIA_NO_SCHED=1 python3 ../tests/est_pc_paper_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M, models, estimation as E, est_pcsheet as PS
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
s = SessionLocal()
if not s.query(models.Site).filter(models.Site.code == "977").first():
    s.add(models.Site(code="977", plot_no="6457380", project_name="B+G+1 Villa", active=True)); s.commit()
s.close()
r = c.post("/store/est/projects", json={"code": "977", "client": "Mr. Mohammed Al Hammadi"}, headers=H); pid = r.json().get("id")
ck("project made", r.status_code == 200, r.text)
p = next(x for x in c.get("/store/est/meta", headers=H).json()["projects"] if x["id"] == pid)
b = c.get(f"/store/est/projects/{pid}", headers=H).json()["project"]
ck("plot no. filled from the site", b.get("plot_no") == "6457380", b.get("plot_no"))
sub = c.post("/store/est/subs", json={"project_id": pid, "name": "Smart Roof Insulation Contracting", "scope": "Thermal & Moisture Protection",
                                      "address": "Office 12, Al Qusais\nDubai, UAE", "phone": "04 2345678", "mobile": "050 1234567", "trn": "100555666700003",
                                      "value": 10500, "ret_pct": 10, "vat_pct": 5}, headers=H).json()
pc = c.post("/store/est/subpcs", json={"sub_id": sub["id"], "inv_ref": "SRIC-INV-AR-0193-1", "inv_amount": 11025, "work_cum": 10500, "ret_auto": True}, headers=H).json()
s = SessionLocal(); x = s.get(E.EstSubPC, pc["id"])
d = PS.build_doc(s, x) if hasattr(PS, "build_doc") else None
s.close()
hl = dict(d["head_l"]); hr = dict(d["head_r"])
ck("client printed", hl.get("Client") == "Mr. Mohammed Al Hammadi", hl.get("Client"))
ck("plot no. printed", hl.get("Plot No.") == "6457380", hl.get("Plot No."))
ck("IPC issued date printed (today when not set)", bool(hr.get("IPC Issued Date")), hr)
sc = " | ".join(d["subc"])
ck("subcontractor address, tel, mobile and TRN printed", "Al Qusais" in sc and "Tel: 04 2345678" in sc and "Mobile: 050 1234567" in sc and "TRN No.: 100555666700003" in sc, sc)
ret = next(r for r in d["C"] if r[0] == "Retention")
ck("retention printed as 10%", ret[1] == "10%", ret)
# a phone of "0" is not printed
s = SessionLocal(); ss = s.get(E.EstSub, sub["id"]); ss.phone = "0"; s.commit(); x = s.get(E.EstSubPC, pc["id"]); d2 = PS.build_doc(s, x); s.close()
ck("a phone of 0 is not printed", "Tel:" not in " | ".join(d2["subc"]), d2["subc"])
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)
