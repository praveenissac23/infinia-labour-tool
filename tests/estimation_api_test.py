"""Estimation > Dashboard / Projects / Tenders (estimation.py): every call the page makes.

    cd app && DATABASE_URL=sqlite:////tmp/est.db INFINIA_NO_SCHED=1 python3 ../tests/estimation_api_test.py

The money above all: certificate chains (advance, recovery, retention,
release, other deductions, VAT), editing an old certificate, paid lock;
then the invoice steps and delays, client certificates, variations, BOQ
paste, logs with due dates, approvals / finalization templates, tenders
-> project, files, the dashboard and every Preview / PDF / Excel.
"""
import io, os, sys
sys.path.insert(0, os.getcwd())
from datetime import date, timedelta
from fastapi.testclient import TestClient
import main, models, auth, estimation as E
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)

db = SessionLocal()
for m in reversed(E.TABLES):
    db.query(m).delete()
db.query(models.Setting).filter(models.Setting.key == E.RULES_KEY).delete()
for code, name in [("912", "B+G+1 Villa Jumeirah"), ("915", "G+2 Villa")]:
    if not db.query(models.Site).filter_by(code=code).first():
        db.add(models.Site(code=code, project_name=name))
for un, pw, perms in [("es_qs", "qs1234567", "settings,estimation_projects"),
                      ("es_acc", "acc123456", "settings,accounts_bank"),
                      ("es_site", "site12345", "attendance,settings")]:
    u = db.query(models.User).filter_by(username=un).first()
    if not u:
        u = models.User(username=un, full_name=un.replace("es_", "").title(), role="office",
                        hashed_password=auth.hash_password(pw), permissions=perms)
        db.add(u)
    else:
        u.permissions = perms; u.hashed_password = auth.hash_password(pw)
sup = db.query(models.Supplier).filter_by(name_key="testmetalworks").first()
if not sup:
    sup = models.Supplier(name="TEST METAL WORKS LLC", name_key="testmetalworks"); db.add(sup)
db.commit()
SUP = sup.id

def tok(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p})
    return {"Authorization": "Bearer " + r.json()["access_token"]}
A, ACC, S = tok("es_qs", "qs1234567"), tok("es_acc", "acc123456"), tok("es_site", "site12345")
def get(p, h=A): return c.get(p, headers=h)
def post(p, j=None, h=A): return c.post(p, json=j or {}, headers=h)
def patch(p, j, h=A): return c.patch(p, json=j, headers=h)
def dele(p, h=A): return c.delete(p, headers=h)

ck("a login without the tick is refused", get("/store/est/meta", S).status_code == 403)
m = get("/store/est/meta").json()
ck("meta: sites and suppliers to pick from", any(s["code"] == "912" for s in m["sites"]) and any(s["id"] == SUP for s in m["suppliers"]))

r = post("/store/est/projects", {"code": "912", "contract_value": 4500000, "adv_pct": 10, "ret_pct": 10})
ck("project from a site code", r.status_code == 200, r.text); P = r.json()["id"]
ck("the same code twice is refused", post("/store/est/projects", {"code": "912"}).status_code == 400)
b = get(f"/store/est/projects/{P}").json()
ck("name filled from the site", b["project"]["name"] == "B+G+1 Villa Jumeirah", b["project"])
ck("approvals list loaded once", len([l for l in b["logs"] if l["kind"] == "approval"]) == len(E.APPROVALS))
ck("finalization log loaded once", len(b["finals"]) == sum(len(v) for v in E.FINAL_ITEMS.values()))
b = get(f"/store/est/projects/{P}").json()
ck("...and not twice", len(b["finals"]) == sum(len(v) for v in E.FINAL_ITEMS.values()))

# ---- a subcontract and its certificates ----------------------------------------------------
r = post("/store/est/subs", {"project_id": P, "supplier_id": SUP, "scope": "Metal Doors", "value": 120897.40, "adv_pct": 10, "ret_pct": 10})
ck("subcontract from a supplier", r.status_code == 200, r.text); SB = r.json()["id"]
r = post("/store/est/subpcs", {"sub_id": SB, "pc_type": "Advance", "inv_ref": "ADV-1"})
ck("advance PC", r.status_code == 200, r.text); PC1 = r.json()["id"]
r = post("/store/est/subpcs", {"sub_id": SB, "inv_ref": "INV-2", "inv_amount": 26614.62, "work_cum": 26614.62}); PC2 = r.json()["id"]
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
p1, p2 = s["pcs"]
ck("name taken from the supplier", s["name"] == "TEST METAL WORKS LLC")
ck("advance = 10% of the value", p1["adv_amount"] == 12089.74 and p1["this"] == 12089.74, p1)
ck("PC numbers follow", p1["seq"] == 1 and p2["seq"] == 2)
ck("recovery and retention 10% of work done", p2["adv_rec_cum"] == 2661.46 and p2["ret_cum"] == 2661.46, p2)
ck("net to date", p2["net_cum"] == round(26614.62 + 12089.74 - 2661.46 - 2661.46, 2), p2["net_cum"])
ck("this certificate = net now - net before", p2["this"] == round(p2["net_cum"] - 12089.74, 2), p2["this"])
ck("VAT 5% and payable", p2["vat"] == round(p2["this"] * .05, 2) and p2["payable"] == round(p2["this"] * 1.05, 2), p2)

r = post("/store/est/subpcs", {"sub_id": SB, "inv_ref": "INV-3"}); PC3 = r.json()["id"]
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
ck("a new PC carries the work to date on", s["pcs"][2]["work_cum"] == 26614.62 and s["pcs"][2]["this"] == 0, s["pcs"][2])
patch(f"/store/est/subpcs/{PC3}", {"work_cum": 150247.02, "other_cum": 500, "other_note": "Back-charge"})
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
p3 = s["pcs"][2]
ck("recovery stops at the advance paid", p3["adv_rec_cum"] == 12089.74, p3["adv_rec_cum"])
ck("retention 10% of 150,247.02", p3["ret_cum"] == 15024.70, p3["ret_cum"])
exp = round(150247.02 + 12089.74 - 12089.74 - 15024.70 - 500, 2)
ck("net to date with other deduction", p3["net_cum"] == exp, (p3["net_cum"], exp))
ck("sum of all certificates = net to date", round(sum(x["this"] for x in s["pcs"]), 2) == p3["net_cum"])
ck("subcontract certified / balance", s["certified"] == exp and s["balance"] == round(120897.40 - 150247.02, 2), (s["certified"], s["balance"]))

# Editing an old certificate moves the later ones.
patch(f"/store/est/subpcs/{PC2}", {"work_cum": 30000})
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
ck("old PC edited: later PC follows, total unchanged", s["pcs"][1]["work_cum"] == 30000 and s["pcs"][2]["net_cum"] == exp
   and round(s["pcs"][1]["this"] + s["pcs"][2]["this"], 2) == round(exp - 12089.74, 2), [x["this"] for x in s["pcs"]])
# Typed retention switches the automatic one off.
patch(f"/store/est/subpcs/{PC3}", {"ret_cum": 14000})
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
ck("typed retention kept", s["pcs"][2]["ret_cum"] == 14000 and s["pcs"][2]["ret_auto"] is False)
patch(f"/store/est/subpcs/{PC3}", {"ret_auto": True})
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
ck("back to automatic", s["pcs"][2]["ret_cum"] == 15024.70)
ck("silly work figure refused", patch(f"/store/est/subpcs/{PC3}", {"work_cum": 9999999}).status_code == 400)
ck("letters in a number refused", patch(f"/store/est/subpcs/{PC3}", {"work_cum": "abc"}).status_code == 400)

# Variation to the subcontract
post("/store/est/subvos", {"sub_id": SB, "title": "Extra doors", "amount": 35000, "on_date": "2026-10-01"})
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
ck("revised value with the VO", s["revised"] == round(120897.40 + 35000, 2) and s["vo_total"] == 35000)

# An advance with no % on the subcontract is recovered pro rata to the value.
r = post("/store/est/subs", {"project_id": P, "name": "PRO RATA LLC", "scope": "Shoring", "value": 211400})
S2 = r.json()["id"]
post("/store/est/subpcs", {"sub_id": S2, "pc_type": "Advance", "adv_amount": 52100})
post("/store/est/subpcs", {"sub_id": S2, "work_cum": 105700})
r = post("/store/est/subpcs", {"sub_id": S2, "work_cum": 211400})
s2 = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == S2)
ck("pro-rata recovery: half at 50%", s2["pcs"][1]["adv_rec_cum"] == 26050, s2["pcs"][1]["adv_rec_cum"])
ck("pro-rata recovery: all back at 100%, certified = value", s2["pcs"][2]["adv_rec_cum"] == 52100 and s2["certified"] == 211400, (s2["pcs"][2]["adv_rec_cum"], s2["certified"]))
dele(f"/store/est/subs/{S2}")

# ---- invoice steps, delays, paid -------------------------------------------------------------
old = (date.today() - timedelta(days=20)).isoformat()
patch(f"/store/est/subpcs/{PC3}", {"received": old})
for st in ["At site", "Back from site", "Certified", "PC issued", "With Accounts"]:
    r = post(f"/store/est/subpcs/{PC3}/step", {"step": st})
    ck("step " + st, r.status_code == 200 and r.json()["status"] == st, r.text)
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
p3 = s["pcs"][2]
ck("PC delay counted from received + 10 days", p3["pc_delay"] >= 9, p3["pc_delay"])
ck("dates stamped", p3["to_site"] and p3["site_back"] and p3["issued"] and p3["to_accounts"])
ck("site cannot mark paid", post(f"/store/est/subpcs/{PC3}/step", {"step": "Paid"}, S).status_code == 403)
ck("accounts cannot move other steps", post(f"/store/est/subpcs/{PC3}/step", {"step": "At site"}, ACC).status_code == 403)
r = post(f"/store/est/subpcs/{PC3}/step", {"step": "Paid", "ref": "CHQ 1001"}, ACC)
ck("accounts marks paid", r.status_code == 200, r.text)
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
ck("paid amount = payable", s["pcs"][2]["paid_amount"] == s["pcs"][2]["payable"], s["pcs"][2])
ck("paid PC figures locked", patch(f"/store/est/subpcs/{PC3}", {"work_cum": 1}).status_code == 400)
ck("paid PC cannot be removed", dele(f"/store/est/subpcs/{PC3}").status_code == 400)
r = post(f"/store/est/subpcs/{PC3}/step", {"step": "Paid", "undo": True})
ck("undo paid", r.json()["status"] == "With Accounts")
s = next(x for x in get(f"/store/est/projects/{P}").json()["subs"] if x["id"] == SB)
ck("undo clears the payment", s["pcs"][2]["paid_amount"] == 0 and not s["pcs"][2]["paid_on"])

# ---- client certificates ---------------------------------------------------------------------
r = post("/store/est/clientpcs", {"project_id": P, "pc_type": "Advance"}); C1 = r.json()["id"]
r = post("/store/est/clientpcs", {"project_id": P, "claimed_cum": 500000, "submitted": "2026-10-05"}); C2 = r.json()["id"]
b = get(f"/store/est/projects/{P}").json()
c1, c2 = b["clientpcs"]
ck("client advance 10% of contract", c1["adv_amount"] == 450000 and c1["this"] == 450000, c1)
ck("claimed used until certified", c2["work"] == 500000 and c2["ret_cum"] == 50000 and c2["adv_rec_cum"] == 50000, c2)
patch(f"/store/est/clientpcs/{C2}", {"certified_cum": 480000, "status": "Certified"})
c2 = get(f"/store/est/projects/{P}").json()["clientpcs"][1]
bs = get(f"/store/est/projects/{P}").json()["summary"]
ck("summary: only certified PCs count as certified", bs["client_work"] == 480000, bs)
ck("certified figure takes over", c2["work"] == 480000 and c2["ret_cum"] == 48000 and c2["this"] == round(480000 - 48000 - 48000, 2), c2)

# ---- variations, BOQ, logs -----------------------------------------------------------------
ck("VO needs a title", post("/store/est/variations", {"project_id": P}).status_code == 400)
post("/store/est/variations", {"project_id": P, "title": "Pergola added", "submitted_amount": 80000})
r = post("/store/est/variations", {"project_id": P, "title": "Pool deck", "submitted_amount": 50000}); V2 = r.json()["id"]
patch(f"/store/est/variations/{V2}", {"status": "Approved", "approved_amount": 45000})
b = get(f"/store/est/projects/{P}").json()
ck("VO numbers follow", [v["seq"] for v in b["variations"]] == [1, 2])
ck("approved VOs in the revised contract", b["summary"]["approved_vo"] == 45000 and b["summary"]["revised"] == 4545000)
r = post(f"/store/est/projects/{P}/boq-paste", {"text": "SUBSTRUCTURE\n1.1\tExcavation\tm3\t120\t25\n1.2\tBlinding concrete\tm3\t40\t310.50\n\nFINISHES\n2.1\tPorcelain tiles\tm2\t1,200\t95"})
ck("BOQ pasted from Excel", r.status_code == 200 and r.json()["added"] == 3, r.text)
b = get(f"/store/est/projects/{P}").json()
ck("BOQ sections and amounts", [x["section"] for x in b["boq"]] == ["SUBSTRUCTURE", "SUBSTRUCTURE", "FINISHES"]
   and b["summary"]["boq_value"] == round(120 * 25 + 40 * 310.5 + 1200 * 95, 2), b["boq"])
r = post("/store/est/logs", {"project_id": P, "kind": "rfi", "title": "Slab level at entrance", "party": "Consultant"})
ck("RFI added", r.status_code == 200); R1 = r.json()["id"]
l = next(x for x in get(f"/store/est/projects/{P}").json()["logs"] if x["id"] == R1)
ck("RFI dated today, due in 7 days, numbered", l["sent"] and l["due"] == (date.fromisoformat(l["sent"]) + timedelta(days=7)).isoformat() and l["seq"] == 1, l)
r = c.put("/store/est/rules", json={"rfi_days": 3}, headers=A)
r = post("/store/est/logs", {"project_id": P, "kind": "rfi", "title": "Door schedule"})
l = next(x for x in get(f"/store/est/projects/{P}").json()["logs"] if x["id"] == r.json()["id"])
ck("rules change the due date", l["due"] == (date.fromisoformat(l["sent"]) + timedelta(days=3)).isoformat() and l["seq"] == 2, l)
ck("unknown log refused", post("/store/est/logs", {"project_id": P, "kind": "zzz", "title": "x"}).status_code == 400)
fin = get(f"/store/est/projects/{P}").json()["finals"][0]
ck("finalization cell saved", patch(f"/store/est/finals/{fin['id']}", {"sc": "C", "rt": "✔", "st": "✔", "sub_id": SB}).status_code == 200)

# ---- tenders -> project --------------------------------------------------------------------
r = post("/store/est/tenders", {"name": "G+2 Villa Al Barsha", "client": "Mr Rashid", "value": 3200000, "due": "2026-11-01"})
ck("tender added", r.status_code == 200); T1 = r.json()["id"]
r = post(f"/store/est/tenders/{T1}/won", {"code": "915"})
ck("won -> project", r.status_code == 200, r.text)
pid2 = r.json()["project_id"]
b2 = get(f"/store/est/projects/{pid2}").json()
ck("project carries the tender's value and client", b2["project"]["contract_value"] == 3200000 and b2["project"]["client"] == "Mr Rashid")
ck("tender marked won", get("/store/est/tenders").json()["tenders"][0]["status"] == "Won")

# ---- files ------------------------------------------------------------------------------------
r = c.post("/store/est/files/upload", headers=A, data={"project_id": str(P), "kind": "doc", "category": "Drawings"},
           files={"file": ("plan.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")})
ck("file uploaded", r.status_code == 200, r.text)
url = r.json()["url"]
ck("signed link opens without a login", c.get(url).status_code == 200 and c.get(url).content.startswith(b"%PDF"))
ck("a forged link is refused", c.get(url.replace(url.split("/")[-2], "0" * 24)).status_code == 403)

# ---- dashboard and exports --------------------------------------------------------------------
d = get("/store/est/dash").json()
ck("dashboard: both projects", len(d["projects"]) == 2)
ck("dashboard KPI: with accounts", d["kpi"]["with_accounts"] == 1 and d["kpi"]["pc_delays"] >= 1, d["kpi"])
ck("dashboard queue lists unpaid invoices", any(x["pc_id"] == PC3 for x in d["queue"]))
t = c.post("/auth/download-token", headers=A).json()["token"]
for what in ["subs", "invoices", "clientpcs", "variations", "boq", "rfi", "approval", "submittal", "doc", "finals"]:
    for f in ["preview", "pdf", "excel"]:
        r = c.get(f"/export/est/{what}?token={t}&pid={P}&format={f}")
        ck(f"export {what} {f}", r.status_code == 200 and len(r.content) > 300, r.text[:200])
for what in ["tenders", "dash"]:
    for f in ["preview", "pdf", "excel"]:
        r = c.get(f"/export/est/{what}?token={t}&format={f}")
        ck(f"export {what} {f}", r.status_code == 200, r.text[:200])
r = c.get(f"/export/est/subpcs?token={t}&pid={P}&sub_id={SB}&format=excel")
ck("one subcontract's PC sheet", r.status_code == 200)
r = c.get(f"/export/est/subs?token={t}&pid={P}&format=preview&q=nothingmatches")
ck("filters carried into the export", r.status_code == 200 and "Nothing to show" in r.text)
r = c.get(f"/export/est/pc/{PC3}?token={t}")
ck("payment certificate page", r.status_code == 200 and "Payment Certificate No. 03" in r.text and "Amount payable" in r.text, r.text[:300])
r = c.get(f"/export/est/pc/{PC3}?token={t}&format=pdf")
ck("payment certificate PDF", r.status_code == 200 and r.content.startswith(b"%PDF"))
t2 = c.post("/auth/download-token", headers=ACC).json()["token"]
ck("accounts can print the PC", c.get(f"/export/est/pc/{PC3}?token={t2}").status_code == 200)
ck("accounts cannot open the registers", c.get(f"/export/est/subs?token={t2}&pid={P}").status_code == 403)

# ---- removing -------------------------------------------------------------------------------
ck("non-admin cannot remove a project", dele(f"/store/est/projects/{pid2}").status_code == 403)
ck("remove an RFI", dele(f"/store/est/logs/{R1}").status_code == 200)
print("\n%d failed" % len(fails) if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
