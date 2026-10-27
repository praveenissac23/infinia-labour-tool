"""Subcontractor payment certificate - the approval way, each step by the person whose turn it is:
invoice received -> site -> certified -> prepared (QS) -> approved (contracts manager) -> verified (Accounts) ->
approved (Managing Director = admin) -> paid (Accounts). Stamps with name and time, send back with a note, the bell,
the approval page, the old steps moved over, the printed stamps.
    cp /tmp/full_base.db /tmp/pf.db && cd app && DATABASE_URL=sqlite:////tmp/pf.db INFINIA_NO_SCHED=1 python3 ../tests/sub_pc_flow_test.py
"""
import os, sys, re
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
import estimation as E
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
login = lambda u, p: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": p}).json().get("access_token", "")}
H = login("admin", "changeme123")
def user(name, full, perms):
    r = c.post("/users", headers=H, json={"username": name, "password": name + "12345", "full_name": full, "role": "office"})
    uid = r.json()["id"] if r.status_code in (200, 201) else next(u["id"] for u in c.get("/users", headers=H).json() if u["username"] == name)
    c.post(f"/users/{uid}/permissions", headers=H, json={"permissions": perms})
    return login(name, name + "12345")
HQ = user("arathiq", "Arathi Sajeendran", "estimation_projects")
HC = user("anoopc", "Anoop S", "estimation_projects")
HA = user("shafeeqa", "Shafeeq", "accounts_bank")
c.put("/store/est/rules", headers=H, json={"pc_cm": "Anoop", "stuck_days": 2})

pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "909")["id"]
sid = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Flow Joinery", "value": 500000, "adv_pct": 10, "ret_pct": 5, "vat_pct": 5}).json()["id"]
pc = c.post("/store/est/subpcs", headers=HQ, json={"sub_id": sid, "inv_ref": "FJ/1", "inv_amount": 50000, "received": "2026-10-20"}).json()["id"]
step = lambda h, body: c.post(f"/store/est/subpcs/{pc}/step", headers=h, json=body)
row = lambda h=H: next(x for x in next(s for s in c.get(f"/store/est/projects/{pid}", headers=h).json()["subs"] if s["id"] == sid)["pcs"] if x["id"] == pc)

meta = lambda h: c.get("/store/est/meta", headers=h).json()["me"]
ck("roles: Anoop is the contracts manager", meta(HC)["pc_mine"] == ["cm"], meta(HC))
ck("roles: the QS sends, certifies, prepares - not approve", set(meta(HQ)["pc_can"]) == {"qs", "site"}, meta(HQ))
ck("roles: the admin is the Managing Director", "md" in meta(H)["pc_mine"], meta(H))

r = step(HQ, {"step": "At site"})
ck("QS sends it to site", r.status_code == 200 and row()["status"] == "At site", r.text)
ck("waiting on: the site engineer", row()["flow"]["turn"] == "site" and row()["flow"]["waiting"] == "Site engineer", row()["flow"])
r = step(HQ, {"step": "Prepared"})
ck("cannot skip ahead to Prepared", r.status_code == 400, r.text)
r = step(HQ, {"step": "Certified", "by": "Akhil"})
ck("certified at site, stamped with the site engineer's name", r.status_code == 200 and row()["verified_by"] == "Akhil", row()["verified_by"])
r = step(HQ, {"step": "Prepared"})
ck("Prepared needs the figures first", r.status_code == 400 and "Fill in" in r.text, r.text)
c.patch(f"/store/est/subpcs/{pc}", headers=HQ, json={"work_cum": 100000})
r = step(HQ, {"step": "Prepared"})
ck("QS presses Prepared - stamped with her name", r.status_code == 200 and row()["prep_by"] == "Arathi Sajeendran", r.text)
ck("now waiting on Anoop, to approve", row()["flow"]["turn"] == "cm" and row()["flow"]["waiting"] == "Anoop" and row()["flow"]["task"] == "to approve", row()["flow"])
r = step(HQ, {"step": "CM approved"})
ck("the QS cannot approve as contracts manager", r.status_code == 403, r.text)
bell = lambda h: [n for n in c.get("/notifications", headers=h).json()["notifications"] if n.get("kind") == "subpc"]
ck("Anoop's bell: the certificate to approve", any(n["subpc"] == pc for n in bell(HC)), [n["title"] for n in bell(HC)])
ck("Shafeeq's bell: nothing yet", not any(n["subpc"] == pc for n in bell(HA)))
r = step(HC, {"step": "CM approved"})
ck("Anoop approves - his name on it", r.status_code == 200 and row()["chk_by"] == "Anoop S", r.text)
q = c.get("/store/est/payqueue", headers=HA).json()
mine = next((x for x in q["rows"] if x["pc_id"] == pc), None)
ck("Accounts' Payments page: to verify, with the checks", mine and mine["status"] == "CM approved" and mine["checks"]["prev_n"] == 0, mine)
ck("Shafeeq's bell: to verify", any(n["subpc"] == pc and "to verify" in n["title"] for n in bell(HA)), [n["title"] for n in bell(HA)])
r = step(HA, {"back": True, "to": "Prepared", "note": "Previous PC not in the bank"})
ck("Accounts sends it back to Anoop with a note", r.status_code == 200 and row()["status"] == "Prepared" and row()["chk_by"] == "", r.text)
ck("...the note shows on the row", row()["flow"]["note"] == "Previous PC not in the bank", row()["flow"])
r = step(HA, {"back": True, "to": "Certified", "note": "x"})
ck("not Accounts' turn now: cannot send back", r.status_code == 403, r.text)
step(HC, {"step": "CM approved"})
r = step(HA, {"step": "Verified"})
ck("Shafeeq verifies - his name on it, it stays with Accounts to send", r.status_code == 200 and row()["rev_by"] == "Shafeeq" and row()["flow"]["turn"] == "acc" and row()["flow"]["md_sent"] is False and row()["flow"]["task"] == "to send to the MD", r.text)
ck("...not on the MD's bell yet", not [n for n in bell(H) if n["subpc"] == pc and n.get("url")], [n["title"] for n in bell(H)])
ck("...on Shafeeq's bell: to send to the MD", any(n["subpc"] == pc and "to send to the MD" in n["title"] for n in bell(HA)), [n["title"] for n in bell(HA)])
q2 = next(x for x in c.get("/store/est/payqueue", headers=HA).json()["rows"] if x["pc_id"] == pc)
ck("...Payments page: verified, not sent", q2["status"] == "Verified" and q2["flow"]["md_sent"] is False, q2["flow"])
r = step(HA, {"step": "Sent to MD"})
ck("Send to MD: now with the MD", r.status_code == 200 and row()["flow"]["turn"] == "md" and row()["flow"]["md_sent"] and row()["flow"]["md_sent_at"], (r.text, row()["flow"]))
r = step(HA, {"step": "Sent to MD", "undo": True})
ck("...taken back (not approved yet): with Accounts again", r.status_code == 200 and row()["flow"]["turn"] == "acc", row()["flow"])
step(HA, {"step": "Sent to MD"})
ck("Accounts cannot approve as MD", step(HA, {"step": "MD approved"}).status_code == 403)
mb = [n for n in bell(H) if n["subpc"] == pc]
ck("the admin's notification opens the approval page itself", mb and mb[0]["url"] == f"/portal/approve.html?pc={pc}", mb)
import push
ck("...and the phone notification goes straight there", mb and push.message_for(mb[0])["url"] == f"/portal/approve.html?pc={pc}")
a = c.get(f"/store/est/subpcs/{pc}/approval", headers=H).json()
ck("approval page: the admin may approve now", a["can_act"] and a["next"] == "MD approved" and a["payable"] > 0, a)
ck("approval page: the stamps so far, with the note sent back", [x["s"] for x in a["stamps"] if not x["back"]][:4] == ["Sent to site", "Certified at site", "Prepared", "Approved"] and any(x["back"] for x in a["stamps"]), a["stamps"])
ck("approval page: Accounts sees it but may not approve", not c.get(f"/store/est/subpcs/{pc}/approval", headers=HA).json()["can_act"])
tok = c.post("/auth/download-token", headers=H).json()["token"]
ck("the PDF opens for the approval page", c.get(f"/export/est/pc/{pc}?token={tok}&format=pdf").headers.get("content-type", "").startswith("application/pdf"))
r = step(H, {"step": "MD approved"})
ck("MD approves digitally", r.status_code == 200 and row()["status"] == "MD approved" and row()["flow"]["turn"] == "acc", r.text)
tok = c.post("/auth/download-token", headers=H).json()["token"]
html = c.get(f"/export/est/pc/{pc}?token={tok}&format=preview").text
ck("printed: the stamps - prepared, approved, verified, MD approved (no name)", all(w in html for w in ("ARATHI SAJEENDRAN", "ANOOP S", "SHAFEEQ", "MANAGING DIRECTOR", "Digitally approved")), "")
ck("printed: the time each was done", re.search(r"\d\d-[A-Z][a-z]{2}-\d{4} \d\d:\d\d", html) is not None)
ck("Shafeeq's bell: to pay", any(n["subpc"] == pc and "to pay" in n["title"] for n in bell(HA)))
r = step(HA, {"step": "Paid", "ref": "ADCB TT 4471"})
ck("Shafeeq marks it paid - his name, the reference", r.status_code == 200 and row()["status"] == "Paid" and row()["paid_by"] == "Shafeeq" and row()["paid_ref"] == "ADCB TT 4471", r.text)
ck("paid: no one's turn, nothing in any bell", row()["flow"]["turn"] == "" and not any(n["subpc"] == pc for n in bell(HA) + bell(H) + bell(HC)))
html = c.get(f"/export/est/pc/{pc}?token={c.post('/auth/download-token', headers=H).json()['token']}&format=preview").text
ck("printed: the paid line", "Paid on" in html and "ADCB TT 4471" in html)
r = step(HA, {"step": "Paid", "undo": True})
ck("undo paid: back to pay, the reference gone", r.status_code == 200 and row()["status"] == "MD approved" and row()["paid_ref"] == "", r.text)

# an advance: no site step
pa = c.post("/store/est/subpcs", headers=HQ, json={"sub_id": sid, "pc_type": "Advance", "adv_amount": 50000}).json()["id"]
r = c.post(f"/store/est/subpcs/{pa}/step", headers=HQ, json={"step": "Prepared"})
ra = next(x for x in next(s for s in c.get(f"/store/est/projects/{pid}", headers=H).json()["subs"] if s["id"] == sid)["pcs"] if x["id"] == pa)
ck("an advance goes straight to Prepared - no site step", r.status_code == 200 and ra["status"] == "Prepared", r.text)
# stuck after 2 days
from datetime import timedelta
db = M.SessionLocal()
o = db.query(E.EstSubPC).get(pa); o.stage_at = E.dubai_now() - timedelta(days=3); db.commit(); db.close()
ra = next(x for x in next(s for s in c.get(f"/store/est/projects/{pid}", headers=H).json()["subs"] if s["id"] == sid)["pcs"] if x["id"] == pa)
ck("3 days at one step: stuck", ra["flow"]["stuck"] and ra["flow"]["hours"] >= 72, ra["flow"])
ck("...and Anoop's bell says stuck", any(n["subpc"] == pa and "stuck" in n["title"] and n["level"] == "warn" for n in bell(HC)))

# the old steps moved over once
db = M.SessionLocal()
old = [E.EstSubPC(sub_id=sid, status=s_, received=E.today()) for s_ in ("Back from site", "Certified", "PC issued", "With Accounts")]
db.add_all(old); db.query(M.models.Setting).filter(M.models.Setting.key == "est_pcflow2").delete(); db.commit()
ids = [x.id for x in old]; db.close()
E.migrate_pc_flow(M.SessionLocal)
db = M.SessionLocal()
got = [db.query(E.EstSubPC).get(i).status for i in ids]; db.close()
ck("old steps: back from site -> certified, certified/PC issued -> prepared, with Accounts -> MD approved (to pay)", got == ["Certified", "Prepared", "Prepared", "MD approved"], got)

print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
