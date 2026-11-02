"""912's PC 09: lines 8 and 9 added later to bill 1-1 showed after bill 2-2 - each bill's lines now stay together;
and a deduction from an earlier certificate can be edited from the open one (logged, old and new figures).
    cd app && DATABASE_URL=sqlite:////tmp/pb.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/pc_bill_order_dedit_test.py
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
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "912")["id"]
sid = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Order Test Manpower", "value": 200000}).json()["id"]
L = lambda bill, no, desc, sec="A MANPOWER SUPPLY": {"bill": bill, "section": sec, "no": no, "description": desc, "qty": 10, "unit": "M3", "rate": 100, "measure": "qty"}
items = [L("1", str(n), f"Line {n}") for n in range(1, 8)] + [L("2", "1", "Labour supply", "LABOUR SUPPLY")]
r = c.put(f"/store/est/subs/{sid}/items", headers=H, json={"items": items})
ck("schedule saved: bill 1 lines 1-7, bill 2 line 1", r.status_code == 200, r.text)
have = c.get(f"/store/est/subs/{sid}/items", headers=H).json()["items"]
# lines 8 and 9 of bill 1 added at the end, as the schedule screen does with + line
r = c.put(f"/store/est/subs/{sid}/items", headers=H, json={"items": have + [L("1", "8", "Line 8"), L("1", "9", "Line 9")]})
order = [(x["bill"], x["no"]) for x in c.get(f"/store/est/subs/{sid}/items", headers=H).json()["items"]]
ck(f"bill 1 stays together: 1-9 then bill 2 ({order})", order == [("1", str(n)) for n in range(1, 10)] + [("2", "1")], order)

# two certificates; a deduction on PC 01, edited from PC 02
pc1 = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "inv_ref": "OT/1", "inv_amount": 1000, "received": "2026-10-01"}).json()["id"]
sh1 = c.get(f"/store/est/subpcs/{pc1}/sheet", headers=H).json()
order_sheet = [(x["bill"], x["no"]) for x in sh1["items"]]
ck("the certificate sheet lists bill 1 lines 1-9 before bill 2", order_sheet == order, order_sheet)
r = c.put(f"/store/est/subpcs/{pc1}/sheet", headers=H, json={"deds": [{"cat": "Manpower", "on_date": "2026-10-01", "description": "Manpower supplied", "qty": 39, "unit": "No", "rate": 90}]})
ck("PC 01 deduction 39 x 90 = 3,510", r.status_code == 200 and r.json()["deds"][0]["amount"] == 3510, r.text)
did = r.json()["deds"][0]["id"]
pc2 = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "inv_ref": "OT/2", "inv_amount": 1000, "received": "2026-10-15"}).json()["id"]
sh2 = c.get(f"/store/est/subpcs/{pc2}/sheet", headers=H).json()
ck("PC 02 shows PC 01's deduction (not its own)", any(x["id"] == did and not x["mine"] for x in sh2["deds"]), sh2["deds"])
r = c.patch(f"/store/est/subpcs/{pc2}/deducts/{did}", headers=H, json={"cat": "Manpower", "on_date": "2026-10-01", "description": "Manpower supplied (corrected)", "qty": 40, "unit": "No", "rate": 90, "counted": True})
d2 = next((x for x in r.json()["deds"] if x["id"] == did), {}) if r.status_code == 200 else {}
ck("edited from PC 02: 40 x 90 = 3,600, new description", d2.get("amount") == 3600 and "corrected" in d2.get("description", ""), r.text)
r = c.patch(f"/store/est/subpcs/{pc2}/deducts/{did}", headers=H, json={"description": "", "amount": 0})
ck("cannot empty it (no description, no amount)", r.status_code == 400, r.text)
other = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Other Sub", "value": 1}).json()["id"]
opc = c.post("/store/est/subpcs", headers=H, json={"sub_id": other, "inv_ref": "X/1", "inv_amount": 1, "received": "2026-10-01"}).json()["id"]
r = c.patch(f"/store/est/subpcs/{opc}/deducts/{did}", headers=H, json={"description": "x", "amount": 1})
ck("must be edited from an open certificate of the same subcontract", r.status_code == 400, r.text)
pc3 = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "inv_ref": "OT/3", "inv_amount": 1000, "received": "2026-10-30"}).json()["id"]
r = c.patch(f"/store/est/subpcs/{pc2}/deducts/{did}", headers=H, json={"pc_id": pc3, "description": "Manpower supplied (corrected)", "qty": 40, "rate": 90})
ck("cannot move it to a later certificate than the one open", r.status_code == 400, r.text)
r = c.patch(f"/store/est/subpcs/{pc2}/deducts/{did}", headers=H, json={"pc_id": pc2, "cat": "Manpower", "description": "Manpower supplied (corrected)", "qty": 40, "unit": "No", "rate": 90})
mv = next((x for x in r.json()["deds"] if x["id"] == did), {}) if r.status_code == 200 else {}
ck("PC number changed: PC 01 -> PC 02 (now on the open certificate)", mv.get("pc_seq") == 2 and mv.get("mine") is True, r.text)
sh1 = c.get(f"/store/est/subpcs/{pc1}/sheet", headers=H).json()
ck("PC 01 no longer carries it", not any(x["id"] == did for x in sh1["deds"]), sh1["deds"])
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
