"""Subcontract advance not recovered: 'Advance recovery %' on the subcontract - empty = the advance %,
0 = not recovered (the certificate shows 0% and nothing taken back), another figure = recovered at that %.
    cp /tmp/full_base.db /tmp/ar.db && cd app && DATABASE_URL=sqlite:////tmp/ar.db INFINIA_NO_SCHED=1 python3 ../tests/sub_adv_recovery_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "909")["id"]
sid = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Woodcraft Test", "value": 534000, "adv_pct": 50, "ret_pct": 10, "vat_pct": 5}).json()["id"]
sub = lambda: next(s for s in c.get(f"/store/est/projects/{pid}", headers=H).json()["subs"] if s["id"] == sid)
ck("a new subcontract: recovery empty = the advance %", sub()["adv_rec_pct"] is None, sub()["adv_rec_pct"])
c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "pc_type": "Advance"})
pc = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "work_cum": 100000}).json()["id"]
row = lambda: next(x for x in sub()["pcs"] if x["id"] == pc)
ck("as the advance %: 50% of 100,000 recovered = 50,000", row()["adv_rec_cum"] == 50000, row()["adv_rec_cum"])
r = c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_pct": 0})
ck("set to 0 (not recovered)", r.status_code == 200 and sub()["adv_rec_pct"] == 0, r.text)
ck("the certificate takes nothing back: recovery 0", row()["adv_rec_cum"] == 0, row()["adv_rec_cum"])
tok = c.post("/auth/download-token", headers=H).json()["token"]
html = c.get(f"/export/est/pc/{pc}?token={tok}&format=preview").text
import re
m = re.search(r"Advance payment Recovery</td>\s*<td[^>]*>([^<]*)<", html)
ck("the printed certificate shows 0% on Advance payment Recovery", m and m.group(1).strip() == "0%", m.group(1) if m else html[html.find("Recovery"):html.find("Recovery") + 200])
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_pct": 20})
ck("set to 20%: 20,000 recovered", row()["adv_rec_cum"] == 20000, row()["adv_rec_cum"])
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_pct": ""})
ck("emptied: back to the advance % (50,000)", sub()["adv_rec_pct"] is None and row()["adv_rec_cum"] == 50000, [sub()["adv_rec_pct"], row()["adv_rec_cum"]])
# the modes: in step with the work done / fixed % / not recovered / typed, and from which PC
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_mode": "", "adv_rec_pct": ""})
c.patch(f"/store/est/subpcs/{pc}", headers=H, json={"work_cum": 106800})        # 20% of 534,000 done
ck("in step with the work done: 20% done = 20% of the 267,000 advance back (53,400)", row()["adv_rec_cum"] == 53400, row()["adv_rec_cum"])
pc3 = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "work_cum": 213600}).json()["id"]   # 40% done
row3 = lambda: next(x for x in sub()["pcs"] if x["id"] == pc3)
ck("next certificate at 40% done: 40% of the advance back to date (106,800)", row3()["adv_rec_cum"] == 106800, row3()["adv_rec_cum"])
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_from": 3})
ck("recovery from PC 3: PC 2 takes nothing back", row()["adv_rec_cum"] == 0, row()["adv_rec_cum"])
ck("...and PC 3 catches up with the work done (106,800)", row3()["adv_rec_cum"] == 106800, row3()["adv_rec_cum"])
html = c.get(f"/export/est/pc/{pc}?token={c.post('/auth/download-token', headers=H).json()['token']}&format=preview").text
m = re.search(r"Advance payment Recovery</td>\s*<td[^>]*>([^<]*)<", html)
ck("PC 2 prints 0% (recovery not started)", m and m.group(1).strip() == "0%", m and m.group(1))
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_from": 1, "adv_rec_mode": "pct", "adv_rec_pct": 10})
ck("a fixed 10% of the work done: PC 3 = 21,360", row3()["adv_rec_cum"] == 21360, row3()["adv_rec_cum"])
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_mode": "manual"})
pc4 = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "work_cum": 300000}).json()["id"]
row4 = lambda: next(x for x in sub()["pcs"] if x["id"] == pc4)
ck("typed on each certificate: a new PC starts from the last figure, not worked out", row4()["adv_rec_cum"] == 21360, row4()["adv_rec_cum"])
c.patch(f"/store/est/subpcs/{pc4}", headers=H, json={"adv_rec_cum": 75000})
ck("...and keeps what is typed", row4()["adv_rec_cum"] == 75000, row4()["adv_rec_cum"])
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_mode": "pct", "adv_rec_pct": 10})
c.patch(f"/store/est/subs/{sid}", headers=H, json={"adv_rec_mode": "", "adv_rec_pct": 10, "adv_rec_from": 1})   # the form sends the hidden box too
ck("switched back to 'in step with the work done' (a left-over % in the hidden box ignored)", sub()["adv_rec_pct"] is None and row3()["adv_rec_cum"] == 106800, [sub()["adv_rec_pct"], row3()["adv_rec_cum"]])
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)
