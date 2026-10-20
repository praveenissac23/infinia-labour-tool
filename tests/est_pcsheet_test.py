"""Subcontractor payment certificates made in the portal (est_pcsheet.py), checked
figure for figure against four real certificates:

    910 Aluminium PC05 (Jerasa)   - measured W x H, deduction, % done; variations; 10% retention
    912 MEP PC03 (Al Raida)       - three bills by %; advance recovered on the work only, retention on work + variations
    913 Shoring PC05 (OneGB)      - re-measured quantities; material / manpower / plant deductions (one shown, not taken)
    915 Manpower PC12 (Royal Everest) - quantities x rates; other deduction; retention released

    cd app && DATABASE_URL=sqlite:////tmp/pcs.db INFINIA_NO_SCHED=1 python3 ../tests/est_pcsheet_test.py
"""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, models, auth, estimation as E, est_pcsheet as S
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)
def eq(a, b):
    return abs((a or 0) - (b or 0)) < 0.005

db = SessionLocal()
for m in reversed(E.TABLES):
    db.query(m).delete()
for un, pw, perms, role in [("pc_qs", "qs1234567", "settings,estimation_projects", "office"), ("pc_acc", "acc123456", "settings,accounts_bank", "office"),
                            ("pc_mgr", "mgr123456", "settings,estimation_projects", "admin")]:
    u = db.query(models.User).filter_by(username=un).first() or models.User(username=un)
    u.full_name = {"pc_qs": "Arathi.S", "pc_acc": "Shafeeq", "pc_mgr": "Praveen"}[un]; u.role = role; u.permissions = perms
    u.hashed_password = auth.hash_password(pw); db.add(u)
db.commit()
def login(u, p):
    return {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": p}).json()["access_token"]}
QS, ACC, MGR = login("pc_qs", "qs1234567"), login("pc_acc", "acc123456"), login("pc_mgr", "mgr123456")
def post(path, body, h=QS):
    r = c.post(path, json=body, headers=h); assert r.status_code == 200, (path, r.status_code, r.text); return r.json()
def put(path, body, h=QS):
    r = c.put(path, json=body, headers=h); return r

def project(code):
    p = db.query(E.EstProject).filter_by(code=code).first()
    if not p:
        p = E.EstProject(code=code, name=f"Villa {code}", status="Running"); db.add(p); db.commit()
    return p.id

def typed_history(sid, cums, ret_pct=0, adv=None):
    """Earlier certificates typed before the schedule existed (as on the live app today)."""
    ids = []
    for i, w in enumerate(cums, 1):
        body = {"sub_id": sid, "inv_ref": f"OLD-{i}", "work_cum": w}
        ids.append(post("/store/est/subpcs", body)["id"])
    return ids

def item_rows(sid, rows, measure, is_var=False, bill="", bill_title="", var_ref=""):
    have = c.get(f"/store/est/subs/{sid}/items", headers=QS).json()["items"]
    new = have + [dict(no=r[0], description=r[1], ref=r[2] if len(r) > 2 else "", qty=r[3] if len(r) > 3 else 0, unit=r[4] if len(r) > 4 else "",
                       rate=r[5] if len(r) > 5 else 0, amount=r[6] if len(r) > 6 else 0, measure=measure, is_var=is_var, bill=bill,
                       bill_title=bill_title, var_ref=var_ref) for r in rows]
    r = put(f"/store/est/subs/{sid}/items", {"items": new})
    assert r.status_code == 200, r.text
    return {x["description"]: x["id"] for x in r.json()["items"]}

# ============ 910 Aluminium PC05 ============
P = project("910")
s910 = post("/store/est/subs", {"project_id": P, "name": "JERASA METAL WORKS LLC", "scope": "Aluminium", "value": 179722, "ret_pct": 10, "vat_pct": 5,
                                "agreement": "IC/910/SCA/03/25", "contract_type": "Contract progressive payment",
                                "pay_terms": "15% upon drawing submission & approval of sample\n40% against material delivery\n35% against installation\nRetention 10%"})["id"]
post("/store/est/subvos", {"sub_id": s910, "title": "Additional glass handrail + roof pergola", "amount": 37922.5})
typed_history(s910, [40000, 80000, 120000, 151922.93])          # net to date 136,730.64 after 10% retention
L910 = [("1", "Sliding door 4 shutter SD1", "SD1", 1, "No", 34920.55, 34920.55), ("2", "Sliding door 2 shutter SD2", "SD2", 2, "No", 11148.64, 22297.28),
        ("3", "Curtain wall W1", "W1", 1, "No", 34132.39, 34132.39), ("4", "Curtain wall W2", "W2", 1, "No", 8953.45, 8953.45),
        ("5", "Curtain wall W3", "W3", 3, "No", 6539.45, 19618.34), ("6", "Curtain wall W4", "W4", 1, "No", 4557.83, 4557.83),
        ("7", "Curtain wall W5", "W5", 1, "No", 3518.55, 3518.55), ("8", "Hinge window W6", "W6", 2, "No", 1163.70, 2327.40),
        ("9", "Curtain wall W7", "W7", 1, "No", 670.48, 670.48), ("10", "Hinge window W8", "W8", 1, "No", 772.12, 772.12),
        ("11", "Sandwich panel door D3", "D3", 1, "No", 1257.12, 1257.12), ("12", "Sandwich panel door D5", "D5", 2, "No", 1270.62, 2514.24),
        ("13", "Sky light", "Sky light", 1, "No", 2228.85, 2228.85), ("14", "Kitchen sliding door", "SLD-Kitchen", 1, "No", 10360.40, 10360.40),
        ("15", "Shower glass 01", "Shower Glass 01", 2, "No", 2976.00, 5952.00), ("16", "Shower glass 02", "Shower Glass 02", 2, "No", 2380.50, 4761.00),
        ("17", "Glass handrail", "Glass Handrail", 25, "m", 835.20, 20880.00)]
ids = item_rows(s910, L910, "size")
ids.update(item_rows(s910, [("1", "Additional glass handrail", "Glass Handrail", 3.5, "m", 835, 2922.5), ("2", "Alum pergola", "Roof Pergola", 1, "No", 35000, 35000)],
                     "size", is_var=True, var_ref="Var 01"))
items = c.get(f"/store/est/subs/{s910}/items", headers=QS).json()
ck("910 schedule: contract lines total 179,722.00, variations 37,922.50", eq(items["total"], 179722) and eq(items["var_total"], 37922.5), items["total"])
ck("910: an agreement's own line amount is kept (3 x 6,539.45 = 19,618.34 as printed)", any(eq(i["amount"], 19618.34) for i in items["items"]))
pc5 = post("/store/est/subpcs", {"sub_id": s910, "inv_ref": "PI04/P087 & PI05/P087", "inv_amount": 34706.6})["id"]
meas = {"Sliding door 4 shutter SD1": (5.10, 3.55, 1370.89, 95), "Sliding door 2 shutter SD2": (3.00, 3.07, 566.28, 95), "Curtain wall W1": (4.47, 7.50, 892.22, 100),
        "Curtain wall W2": (2.8, 3.55, 0, 100), "Curtain wall W3": (2.2, 3.2, 594.50, 100), "Curtain wall W4": (2, 2.35, 0, 100), "Curtain wall W5": (1.5, 2.8, 0, 100),
        "Hinge window W6": (.97, 1.17, 135.77, 100), "Curtain wall W7": (.7, 1.3, 274.29, 100), "Hinge window W8": (.7, 1.3, 315.87, 95),
        "Sandwich panel door D3": (.9, 2.4, 0, 100), "Sandwich panel door D5": (.9, 2.4, 0, 95), "Sky light": (1.5, 1.3, 0, 100), "Kitchen sliding door": (0, 0, 0, 0),
        "Shower glass 01": (0, 0, 855.60, 95), "Shower glass 02": (0, 0, 0, 95), "Glass handrail": (0, 0, 0, 95),
        "Additional glass handrail": (3.3, 0, 167, 95), "Alum pergola": (8.6, 2.2, 7500, 95)}
r = put(f"/store/est/subpcs/{pc5}/sheet", {"pc": {"measured_on": "2026-10-04", "inv_date": "2026-10-04", "remarks": "Nil"},
                                           "lines": [{"item_id": ids[k], "w": v[0], "h": v[1], "deduct": v[2], "pct": v[3]} for k, v in meas.items()]})
ck("910 sheet saved", r.status_code == 200, r.text[:300])
sh = r.json(); cc = sh["calc"]; pc = sh["pc"]
ck("910: value of work executed to date 159,906.76", eq(pc["work_cum"], 159906.76), pc["work_cum"])
ck("910: value of variations to date 28,742.73", eq(pc["var_cum"], 28742.73), pc["var_cum"])
ck("910: retention 10% = 18,864.95", eq(pc["ret_cum"], 18864.95), pc["ret_cum"])
ck("910: previously certified 136,730.64", eq(cc["prev_net"], 136730.64), cc["prev_net"])
ck("910: net amount due 33,053.90", eq(cc["this"], 33053.90), cc["this"])
ck("910: VAT 1,652.70 and total due 34,706.60", eq(cc["vat"], 1652.70) and eq(cc["payable"], 34706.60), (cc["vat"], cc["payable"]))

# ============ 912 MEP PC03 ============
P = project("912")
s912 = post("/store/est/subs", {"project_id": P, "name": "AL RAIDA ELECTROMECHANICAL SERVICES LLC", "scope": "MEP", "value": 603000, "adv_pct": 10, "ret_pct": 10})["id"]
post("/store/est/subvos", {"sub_id": s912, "title": "Amendment-01", "amount": 5000})
b = {}
b.update(item_rows(s912, [("9", "Electrical works", "", 1, "LS", 0, 150000)], "pct", bill="B1", bill_title="Electrical Works"))
b.update(item_rows(s912, [("1", "Plumbing installations", "", 1, "LS", 0, 143000)], "pct", bill="B2", bill_title="Plumbing Works"))
b.update(item_rows(s912, [("1", "AC works", "", 1, "LS", 0, 310000)], "pct", bill="B3", bill_title="Air Conditioning and Ventilation Works"))
b.update(item_rows(s912, [("1", "Amendment-01", "", 1, "LS", 0, 5000)], "pct", is_var=True, var_ref="Amendment-01"))
adv = post("/store/est/subpcs", {"sub_id": s912, "pc_type": "Advance", "adv_amount": 29300, "inv_ref": "Advance"})["id"]
pc2 = post("/store/est/subpcs", {"sub_id": s912, "inv_ref": "PC-02"})["id"]
r = put(f"/store/est/subpcs/{pc2}/sheet", {"pc": {"ret_cum": 0}, "lines": [{"item_id": b["Amendment-01"], "pct": 100}]})
ck("912 PC02: the amendment certified 5,000 (no retention taken that time)", r.status_code == 200 and eq(r.json()["calc"]["this"], 5000), r.text[:200])
pc3 = post("/store/est/subpcs", {"sub_id": s912, "inv_ref": "912 Summary PC-01", "inv_amount": 30825})["id"]
sh = c.get(f"/store/est/subpcs/{pc3}/sheet", headers=QS).json()
ck("912 PC03 starts as a copy of PC02 (the amendment at 100%)", sh["lines"].get(str(b["Amendment-01"]), {}).get("pct") == 100, sh["lines"])
r = put(f"/store/est/subpcs/{pc3}/sheet", {"pc": {"ret_auto": True, "measured_on": "2026-10-02"},
                                           "lines": [{"item_id": b["Electrical works"], "pct": 3.85}, {"item_id": b["Plumbing installations"], "pct": 100 * 4350 / 143000},
                                                     {"item_id": b["AC works"], "pct": 0}, {"item_id": b["Amendment-01"], "pct": 100}]})
sh = r.json(); cc = sh["calc"]; pc = sh["pc"]
ck("912: work to date 10,125.00 and variations 5,000.00", eq(pc["work_cum"], 10125) and eq(pc["var_cum"], 5000), (pc["work_cum"], pc["var_cum"]))
ck("912: advance recovery 10% of the work only = 1,012.50", eq(pc["adv_rec_cum"], 1012.5), pc["adv_rec_cum"])
ck("912: retention 10% of work + variations = 1,512.50", eq(pc["ret_cum"], 1512.5), pc["ret_cum"])
ck("912: previously certified 34,300 (advance 29,300 + IPC-02 5,000)", eq(cc["prev_net"], 34300), cc["prev_net"])
ck("912: net 7,600.00, VAT 380.00, total 7,980.00", eq(cc["this"], 7600) and eq(cc["vat"], 380) and eq(cc["payable"], 7980), cc)

# ============ 913 Shoring PC05 ============
P = project("913")
s913 = post("/store/est/subs", {"project_id": P, "name": "ONEGB PILING & FOUNDATION CONTRACTING L.L.C.", "scope": "Shoring", "value": 0,
                                "contract_type": "Unit rate re-measurement contract"})["id"]
typed_history(s913, [50000, 100000, 150000, 209467])
paste = "\n".join(["Bill No\tDescription\tQuantity\tUnit\tRate\tAmount",
                   "1\tDesign, shop drawings, shoring permit, mobilization\t1\tLS\t15,000.00\t15,000.00",
                   "2\tSupply and install secant piles (re-measurable)\t26.8\tL.M\t6,800.00\t182,240.00",
                   "3\tH beam and anchors (re-measurable)\t1\tLS\t60,580.00\t60,580.00"])
r = c.post(f"/store/est/subs/{s913}/items/paste", json={"text": paste, "measure": "qty"}, headers=QS)
ck("913: schedule pasted from Excel - 3 lines, 257,820.00", r.status_code == 200 and r.json()["added"] == 3 and eq(r.json()["total"], 257820), r.text[:300])
it913 = {x["description"][:12]: x for x in c.get(f"/store/est/subs/{s913}/items", headers=QS).json()["items"]}
ck("913: the units and quantities read from the paste", it913["Supply and i"]["unit"] == "L.M" and it913["Supply and i"]["qty"] == 26.8, it913["Supply and i"])
pc5 = post("/store/est/subpcs", {"sub_id": s913, "inv_ref": "1GB/585/04/2025", "inv_amount": 35912})["id"]
deds = [{"cat": "Material", "on_date": "2026-06-24", "description": "C 20/20 concrete", "qty": 7, "unit": "m3", "rate": 358},
        {"cat": "Material", "on_date": "2026-06-26", "description": "C 20/20 concrete", "qty": 5.5, "unit": "m3", "rate": 358},
        {"cat": "Material", "on_date": "2026-06-22", "description": "C 20/20 concrete", "qty": 6, "unit": "m3", "rate": 358},
        {"cat": "Manpower", "on_date": "2026-06-17", "description": "with 2 hours OT", "qty": 10, "unit": "No", "rate": 137},
        {"cat": "Manpower", "on_date": "2026-06-18", "description": "with 2 hours OT", "qty": 10, "unit": "No", "rate": 137},
        {"cat": "Manpower", "on_date": "2026-06-19", "description": "with 2 hours OT", "qty": 10, "unit": "No", "rate": 137},
        {"cat": "Manpower", "on_date": "2026-06-20", "description": "with 1 hour OT", "qty": 14, "unit": "No", "rate": 131},
        {"cat": "Plant & Equipment", "on_date": "2026-06-17", "description": "Jack hammer", "qty": 6, "unit": "No", "rate": 88},
        {"cat": "Plant & Equipment", "on_date": "2026-06-18", "description": "Jack hammer", "qty": 6, "unit": "No", "rate": 88},
        {"cat": "Plant & Equipment", "on_date": "2026-06-19", "description": "Jack hammer", "qty": 6, "unit": "No", "rate": 88},
        {"cat": "Other", "description": "Dewatering charges for 7 days", "qty": 7, "unit": "Days", "rate": 7200, "counted": False,
         "note": "Deduction for dewatering is not applied as per Management instruction."}]
r = put(f"/store/est/subpcs/{pc5}/sheet", {"pc": {"measured_on": "2026-09-26", "remarks": "Final Payment upon Hbeam retraction works"},
                                           "lines": [{"item_id": x["id"], "qty": x["qty"]} for x in it913.values()], "deds": deds})
sh = r.json(); cc = sh["calc"]; pc = sh["pc"]
ck("913: work to date 257,820.00", eq(pc["work_cum"], 257820), pc["work_cum"])
ck("913: deductions 14,151 (6,623 + 5,944 + 1,584; dewatering shown, not taken)", eq(pc["other_cum"], 14151), pc["other_cum"])
ck("913: net 34,202.00, VAT 1,710.10, total 35,912.10 (the paper copy rounded it to 35,912.00)", eq(cc["this"], 34202) and eq(cc["vat"], 1710.10) and eq(cc["payable"], 35912.10), cc)
pc6 = post("/store/est/subpcs", {"sub_id": s913, "inv_ref": "1GB/586"})["id"]
sh6 = c.get(f"/store/est/subpcs/{pc6}/sheet", headers=QS).json()
ck("913 PC06: the deductions count again (to date) without retyping", eq(sh6["pc"]["other_cum"], 14151) and len(sh6["deds"]) == 11 and not any(d["mine"] for d in sh6["deds"]), sh6["pc"]["other_cum"])
c.delete(f"/store/est/subpcs/{pc6}", headers=QS)

# ============ 915 Manpower PC12 ============
P = project("915")
s915 = post("/store/est/subs", {"project_id": P, "name": "ROYAL EVEREST TECHNICAL SERVICES", "scope": "Manpower", "kind": "Manpower", "value": 0, "ret_pct": 10,
                                "contract_type": "Unit rate re-measurement contract"})["id"]
typed_history(s915, [5000 / .9, 30000, 60000, 105776.39])
q = {}
q.update(item_rows(s915, [("1-4", "Footing, boundary wall footing, strap & tie beams", "", 0, "m3", 235, 0), ("5", "Grade slab", "", 0, "m3", 120, 0)], "qty",
                   bill="A", bill_title="Subcontractor works"))
q.update(item_rows(s915, [("6", "Column", "", 0, "m3", 235, 0), ("7", "Slab - FF", "", 0, "m3", 235, 0), ("8", "Slab - RF", "", 0, "m3", 235, 0)], "qty",
                   bill="B", bill_title="Superstructure works"))
q.update(item_rows(s915, [("8", "Manpower for additional column work", "", 0, "Nos", 130, 0), ("9", "Transportation", "", 0, "Nos", 80, 0)], "qty", is_var=True))
pc12 = post("/store/est/subpcs", {"sub_id": s915, "inv_ref": "10", "inv_amount": 11118.18})["id"]
lines = [("Footing, boundary wall footing, strap & tie beams", 141.5, 144.5), ("Grade slab", 20, 20), ("Column", 48, 52), ("Slab - FF", 115, 119), ("Slab - RF", 128, 128),
         ("Manpower for additional column work", 13, 15), ("Transportation", 2, 3)]
r = put(f"/store/est/subpcs/{pc12}/sheet", {"pc": {"ret_rel_cum": 10588.75, "remarks": "Retention release", "inv_lines": [{"d": "Retention payment 10%", "a": 10588.75}]},
                                            "lines": [{"item_id": q[k], "qty": v, "claimed_qty": cl} for k, v, cl in lines],
                                            "deds": [{"cat": "Other", "description": "Safety violation, machine & fence damage (fence 3 nos 400, machine servicing 550)", "amount": 950}]})
sh = r.json(); cc = sh["calc"]; pc = sh["pc"]
ck("915: work 104,037.50 and variations 1,850.00", eq(pc["work_cum"], 104037.5) and eq(pc["var_cum"], 1850), (pc["work_cum"], pc["var_cum"]))
ck("915: retention 10,588.75, released 10,588.75, other deductions 950", eq(pc["ret_cum"], 10588.75) and eq(pc["ret_rel_cum"], 10588.75) and eq(pc["other_cum"], 950))
ck("915: net 9,738.75, VAT 486.94, total 10,225.69 (the paper copy rounded it to 10,226.00)", eq(cc["this"], 9738.75) and eq(cc["vat"], 486.94) and eq(cc["payable"], 10225.69), cc)

# ============ sign-off ============
r = c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "chk"}, headers=QS)
ck("checked before prepared is refused", r.status_code == 400)
c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "site"}, headers=QS)
r = c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "prep"}, headers=QS).json()
ck("prepared: the QS's name and today's date", r["pc"]["prep_by"] == "Arathi.S" and r["pc"]["prep_on"] == E.today().isoformat() and r["pc"]["verified_by"] == "Arathi.S")
r = c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "rev"}, headers=QS)
ck("only Accounts signs as reviewed", r.status_code == 403)
r = c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "rev"}, headers=ACC)
ck("Accounts signs as reviewed", r.status_code == 200 and r.json()["pc"]["rev_by"] == "Shafeeq", r.text[:200])
r = c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "app"}, headers=QS)
ck("only the manager approves", r.status_code == 403)
r = c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "app"}, headers=MGR)
ck("the manager approves", r.status_code == 200 and r.json()["pc"]["app_by"] == "Praveen")
r = c.post(f"/store/est/subpcs/{pc12}/sign", json={"role": "prep", "undo": True}, headers=ACC)
ck("someone else can't take off the QS's signature", r.status_code in (400, 403))

# ============ print: certificate + appendices, preview and PDF ============
tok = c.post("/auth/download-token", headers=QS).json()
tok = tok.get("token") or tok.get("download_token")
for name, pid, want in [("910", None, ["33,053.90", "34,706.60", "159,906.76", "28,742.73", "18,864.95", "IPC - 01 to IPC - 04"]),
                        ("913", None, ["34,202.00", "35,912.10", "6,623.00", "5,944.00", "1,584.00", "Not deducted"]),
                        ("915", pc12, ["9,738.75", "10,225.69", "10,588.75", "Arathi.S", "Shafeeq", "Praveen", "Verified at site"])]:
    if pid is None:
        sid = {"910": s910, "913": s913}[name]
        pid = max(x.id for x in db.query(E.EstSubPC).filter_by(sub_id=sid).all())
    h = c.get(f"/export/est/pc/{pid}?token={tok}&format=preview")
    ck(f"{name}: preview opens with every figure", h.status_code == 200 and all(w in h.text for w in want), [w for w in want if w not in h.text])
    p_ = c.get(f"/export/est/pc/{pid}?token={tok}&format=pdf")
    ok = p_.status_code == 200 and p_.content[:4] == b"%PDF"
    txt = ""
    if ok:
        f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False); f.write(p_.content); f.close()
        txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
        open(f"/tmp/pc_{name}.pdf", "wb").write(p_.content)
    ck(f"{name}: PDF made (certificate + appendices) with every figure", ok and all(w in txt for w in want), [w for w in want if w not in txt])
pdf = open("/tmp/pc_910.pdf", "rb").read()
ck("910 PDF: Appendix A on landscape pages, B after it", b"/MediaBox [ 0 0 841.8898" in pdf and "Appendix - B" in subprocess.run(["pdftotext", "/tmp/pc_910.pdf", "-"], capture_output=True, text=True).stdout)

# ============ locks ============
s = db.query(E.EstSubPC).get(pc12); db.refresh(s); s.status = "Paid"; s.paid_amount = 10225.69; db.commit()
r = put(f"/store/est/subpcs/{pc12}/sheet", {"lines": [{"item_id": q["Column"], "qty": 60}]})
ck("a paid certificate's sheet can't be changed", r.status_code == 400)
r = put(f"/store/est/subs/{s915}/items", {"items": [x for x in c.get(f"/store/est/subs/{s915}/items", headers=QS).json()["items"] if x["description"] != "Column"]})
ck("a line on a paid certificate can't be removed from the schedule", r.status_code == 400)
pc13 = post("/store/est/subpcs", {"sub_id": s915, "inv_ref": "11"})["id"]
sh = c.get(f"/store/est/subpcs/{pc13}/sheet", headers=QS).json()
ck("PC13 starts from PC12's quantities", eq(sh["pc"]["work_cum"], 104037.5), sh["pc"]["work_cum"])
db.expire_all()
ck("PC12 (paid) kept its figures", eq(db.query(E.EstSubPC).get(pc12).work_cum, 104037.5))
c.delete(f"/store/est/subpcs/{pc13}", headers=QS)
ck("removing a certificate removes its lines", db.query(S.EstPCLine).filter_by(pc_id=pc13).count() == 0)

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
