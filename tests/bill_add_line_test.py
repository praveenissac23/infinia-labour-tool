"""Work done: a new line (a variation, an added item) or a section put in to a sheet's table from the bill itself.
The line takes the row formulas of the line above (AMOUNT = QTY x RATE, Current = Total - Previous, the amounts),
starts at 0%, the section total and the summary take it in, the Excel carries it, the next bill keeps it, and a
line never billed can be taken out again.
    python3 tests/make_ipa_like_914.py /tmp/claude-0/bills/914-like.xlsx
    cp /tmp/claude-0/bn.db /tmp/claude-0/al.db && cd app && DATABASE_URL=sqlite:////tmp/claude-0/al.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_add_line_test.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import openpyxl
import main as M
c = TestClient(M.app); c.__enter__()
F = os.environ.get("BILL", "/tmp/claude-0/bills/914-like.xlsx")
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = next(p["id"] for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "904")
r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("914-like.xlsx", open(F, "rb").read(), "application/octet-stream")})
ck("format uploaded", r.status_code == 200, r.text)
bid = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": r.json()["id"]}).json()["id"]
bill = c.get(f"/store/est/ipa/bill/{bid}", headers=H).json()
sec = lambda b, n: next(t for t in b["progress"] if t["sheet"] == n)
D, C = "Division 03-Concrete Works", "APP C"
d0, due0 = sec(bill, D), bill["total_due"]
ck("Division: lines 9, 10, 12; headings 3.1.1 and 3.2.2 shown", [l["r"] for l in d0["lines"]] == [9, 10, 12] and [h["item"] for h in d0["heads"]] == ["3.1.1", "3.2.2"], (d0["lines"], d0["heads"]))
# Division 02 as 914 prints it: only the real heading over each run of lines
e0 = sec(bill, "Division 02-Site Construction")
ck("Division 02: lines 4.1-4.3 and 6.1-6.3", [l["item"] for l in e0["lines"]] == ["4.1", "4.2", "4.3", "6.1", "6.2", "6.3"], [(l["r"], l["item"]) for l in e0["lines"]])
ck("...headings: just 'Back Fill (with excavated soil)' over 4.x and '6 Anti-termite treatment' over 6.x",
   [(h["item"], h["desc"]) for h in e0["heads"]] == [("", "Back Fill (with excavated soil)"), ("6", "Anti-termite treatment")], e0["heads"])
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": "Division 02-Site Construction", "after": 35, "values": {"item": "4.4", "desc": "Pump room", "unit": "M3", "c5": 10, "c6": 46}})
e1 = sec(r.json(), "Division 02-Site Construction"); l44 = next((l for l in e1["lines"] if l["item"] == "4.4"), None)
dueA = r.json()["total_due"]
r = c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {"Division 02-Site Construction": {l44["tot_key"]: 1}}})
ck("Division 02: 4.4 added after 4.3 (page 2), 100% = +460 through the page total and the collection", l44 and l44["r"] == 36 and abs(r.json()["total_due"] - dueA - 460) < 0.01, (l44, dueA, r.json().get("total_due")))
r = c.post(f"/store/est/ipa/bill/{bid}/line/remove", headers=H, json={"sheet": "Division 02-Site Construction", "r": 36})
ck("...and taken out again", r.status_code == 200 and abs(r.json()["total_due"] - dueA) < 0.01, r.text[:200])
bill = r.json(); due0 = bill["total_due"]
f9 = {f["f"]: f for f in d0["lines"][0]["fields"]}
ck("a Division line's details: item, description, unit, QTY and RATE typed - amount worked out", set(f9) >= {"item", "desc", "unit", "c5", "c6", "amount"} and f9["c5"]["edit"] and not f9["amount"]["edit"], f9)
fv = {f["f"]: f for f in sec(bill, C)["lines"][1]["fields"]}
ck("an APP C line (V02): description and amount typed", fv["desc"]["edit"] and fv["amount"]["edit"], fv)

# ---- a new item after 3.2.2.1 (the last line): QTY x RATE
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": D, "after": 12, "values": {"item": "3.2.2.3", "desc": "Additional lintel beams", "unit": "M3", "c5": 4, "c6": 2000}})
ck("new line added", r.status_code == 200, r.text)
b1 = r.json(); t = sec(b1, D); ln = next((l for l in t["lines"] if l["r"] == 13), None)
ck("it is a line of the table: 3.2.2.3, 4 x 2,000 = 8,000, at 0%", ln and ln["item"] == "3.2.2.3" and abs(ln["amount"] - 8000) < 1e-6 and ln["prev"] == 0 and ln["total"] == 0 and ln["how"] == "tot", ln)
ck("...marked as added, can be taken out", ln and ln["added"] and ln["can_remove"], ln)
r = c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {D: {ln["tot_key"]: 0.5}}})
b2 = r.json()
ck("50% typed: 4,000 more work, total due up by 4,000", abs(b2["total_due"] - due0 - 4000) < 0.01, (due0, b2["total_due"]))

# ---- a new variation after V05 and one after the spare row (right above the Sub-Total)
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": C, "after": 10, "values": {"item": "V07", "desc": "Extra skylight", "amount": "=12000*1.0"}})
ck("variation added above the Sub-Total", r.status_code == 200, r.text)
t = sec(r.json(), C); v7 = next((l for l in t["lines"] if l["item"] == "V07"), None)
ck("V07 on row 11, 12,000, Total = Previous + Current (0)", v7 and v7["r"] == 11 and abs(v7["amount"] - 12000) < 1e-6 and v7["total"] == 0 and v7["how"] in ("cur", "tot"), v7)
key = v7["cur_key"] if v7["how"] == "cur" else v7["tot_key"]
due_b = r.json()["total_due"]
r = c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {C: {key: 0.25}}})
ck("25% on V07: the Sub-Total takes it in (+3,000 on the total due)", abs(r.json()["total_due"] - due_b - 3000) < 0.01, (due_b, r.json()["total_due"]))
# details of an existing spare line typed (V02)
v2 = next(l for l in sec(r.json(), C)["lines"] if l["item"] == "V02")
ff = {f["f"]: f for f in v2["fields"]}
r = c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {C: {ff["desc"]["k"]: "Kitchen extension", ff["amount"]["k"]: 5000}}})
v2b = next(l for l in sec(r.json(), C)["lines"] if l["item"] == "V02")
ck("V02's description and amount typed in place", r.status_code == 200 and v2b["desc"] == "Kitchen extension" and v2b["amount"] == 5000, v2b)

# ---- a section with a line under it
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": D, "kind": "head", "after": 13, "values": {"item": "3.3", "desc": "Additional works"}})
ck("section added", r.status_code == 200, r.text)
hr = r.json()["added_row"]; t = sec(r.json(), D)
ck("the section shows as a heading after 3.2.2.3", any(h["r"] == hr and h["desc"] == "Additional works" and h["added"] for h in t["heads"]), t["heads"])
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": D, "after": hr, "values": {"item": "3.3.1", "desc": "Pump room slab", "unit": "M3", "c5": 2, "c6": 1500}})
t = sec(r.json(), D); l331 = next((l for l in t["lines"] if l["item"] == "3.3.1"), None)
ck("a line under the new section: 3,000, in the table", l331 and abs(l331["amount"] - 3000) < 1e-6, [(l["r"], l["item"]) for l in t["lines"]])
due_c = r.json()["total_due"]
r = c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {D: {l331["tot_key"]: 1}}})
ck("100% on it: +3,000 (the division total and summary take it in)", abs(r.json()["total_due"] - due_c - 3000) < 0.01, (due_c, r.json()["total_due"]))
ck("blank description refused", c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": D, "after": 12, "values": {}}).status_code == 400)

# ---- out to Excel: the new lines with their formulas, totals over them
tok = c.post("/auth/download-token", headers=H).json()["token"]
x = c.get(f"/export/est/ipa/{bid}?token={tok}&format=excel")
ck("Excel comes out", x.status_code == 200 and x.content[:2] == b"PK", x.status_code)
wb = openpyxl.load_workbook(io.BytesIO(x.content)); ws = wb[D]
row = next(rr for rr in range(1, 40) if ws[f"B{rr}"].value == "3.2.2.3")
ck("Excel: 3.2.2.3 with AMOUNT = F*E and its % formulas", str(ws[f"G{row}"].value).replace("+", "") == f"=F{row}*E{row}" and ws[f"I{row}"].value == f"=J{row}-H{row}" and ws[f"M{row}"].value == f"=J{row}*G{row}", [ws[f"{cc}{row}"].value for cc in "BCDEFGHIJKLM"])
ck("...the side note column not copied", ws[f"N{row}"].value in (None, ""), ws[f"N{row}"].value)
tot = next(rr for rr in range(1, 40) if ws[f"C{rr}"].value == "TOTAL CARRIED TO COLLECTION")
ck("Excel: the division total runs over the new rows", ws[f"G{tot}"].value == f"=SUM(G9:G{tot - 1})", ws[f"G{tot}"].value)
wc = wb[C]
sub = next(rr for rr in range(1, 30) if wc[f"B{rr}"].value == "Sub - Total")
ck("Excel: APP C Sub-Total takes V07 in", wc[f"I{sub}"].value == f"=SUM(I5:I{sub - 1})" and wc[f"A{sub - 1}"].value == "V07", (wc[f"I{sub}"].value, wc[f"A{sub - 1}"].value))
wv = openpyxl.load_workbook(io.BytesIO(x.content), data_only=True)
ck("Excel: cached total due matches the app", abs((wv["IPA"]["B8"].value or 0) - r.json()["total_due"]) < 0.5, (wv["IPA"]["B8"].value, r.json()["total_due"]))
p = c.get(f"/export/est/ipa/{bid}?token={tok}&format=preview")
ck("preview shows the new line", p.status_code == 200 and "Additional lintel beams" in p.text and "Additional works" in p.text)

# ---- take one out
due_d = r.json()["total_due"]
r = c.post(f"/store/est/ipa/bill/{bid}/line/remove", headers=H, json={"sheet": D, "r": l331["r"]})
t = sec(r.json(), D)
ck("line taken out: gone, total due back down by 3,000", r.status_code == 200 and not any(l["item"] == "3.3.1" for l in t["lines"]) and abs(due_d - r.json()["total_due"] - 3000) < 0.01, (due_d, r.json().get("total_due")))
ck("...the section and the other added line stay", any(h["desc"] == "Additional works" for h in t["heads"]) and any(l["item"] == "3.2.2.3" and l["total"] == 0.5 for l in t["lines"]), (t["heads"], [(l["item"], l["total"]) for l in t["lines"]]))
r = c.post(f"/store/est/ipa/bill/{bid}/line/remove", headers=H, json={"sheet": D, "r": 9})
ck("a consultant's own line cannot be taken out", r.status_code == 400, r.text)
r = c.post(f"/store/est/ipa/bill/{bid}/line/remove", headers=H, json={"sheet": C, "r": 5})
ck("...nor one billed before", r.status_code == 400, r.text)

# ---- the next bill keeps them; a line billed before cannot be taken out there
due_now = c.get(f"/store/est/ipa/bill/{bid}", headers=H).json()
nb = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid}).json()["id"]
b9 = c.get(f"/store/est/ipa/bill/{nb}", headers=H).json()
t = sec(b9, D); l = next((l for l in t["lines"] if l["item"] == "3.2.2.3"), None)
ck("next bill: 3.2.2.3 is there with Previous 50%", l and abs((l["prev"] or 0) - 0.5) < 1e-9, l)
ck("...the section heading too", any(h["desc"] == "Additional works" for h in t["heads"]), t["heads"])
v7n = next((l for l in sec(b9, C)["lines"] if l["item"] == "V07"), None)
ck("...V07 with Previous 25%", v7n and abs((v7n["prev"] or 0) - 0.25) < 1e-9, v7n)
ck("...and it cannot be taken out any more (billed)", l and not l["can_remove"] and c.post(f"/store/est/ipa/bill/{nb}/line/remove", headers=H, json={"sheet": D, "r": l["r"]}).status_code == 400)
print("\n" + (f"{len(fails)} FAILED: {fails}" if fails else "ALL PASS"))
