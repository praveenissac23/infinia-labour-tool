"""Undo / redo on a bill (7 Nov 2026): one history per bill for every step and sheet, only the cells a change made,
totals worked out again, never past a signing, never the signatures, Draft bills only, each person their own.
    python3 tests/make_ipa_like_913.py /tmp/claude-0/bills/913-like.xlsx
    cp /tmp/full.db /tmp/claude-0/un.db && cd app && DATABASE_URL=sqlite:////tmp/claude-0/un.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_undo_test.py"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = c.get("/store/est/meta", headers=H).json()["projects"][0]["id"]
r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("913-like.xlsx", open("/tmp/claude-0/bills/913-like.xlsx", "rb").read(), "application/octet-stream")})
bid = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": r.json()["id"]}).json()["id"]
h = c.get(f"/store/est/ipa/bill/{bid}/history", headers=H).json()
ck("a new bill: nothing to undo", h["undo"] is None and h["redo"] is None, h)
b0 = c.get(f"/store/est/ipa/bill/{bid}", headers=H).json()
cp = next(t for t in b0["progress"] if t["sheet"] == "Cost Proposal Log"); ln = next(l for l in cp["lines"] if "Interior" in l["desc"])
due0 = b0["total_due"]
r = c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {"Cost Proposal Log": {ln["tot_key"]: 0.8}}, "why": {"page": "work"}})
due1 = r.json()["total_due"]
ck("80% on Interior design: total due up 15,000", abs(due1 - due0 - 15000) < 0.01, (due0, due1))
r = c.post(f"/store/est/ipa/bill/{bid}/fmt", headers=H, json={"sheet": "Summary", "cells": [[4, 2], [4, 3], [4, 4]], "set": {"b": True}})
h = c.get(f"/store/est/ipa/bill/{bid}/history", headers=H).json()
ck("Undo names the last change: Bold on 3 cells (Summary)", h["undo"] and h["undo"]["label"] == "Bold on 3 cells" and h["undo"]["where"] == "Summary", h)
r = c.post(f"/store/est/ipa/bill/{bid}/undo", headers=H, json={})
inp = json.loads(next(x for x in [r.json()]) and "{}")
db_inp = lambda: json.loads(c.get(f"/store/est/ipa/bill/{bid}/sheet/0", headers=H).status_code and __import__("sqlite3").connect(os.environ["DATABASE_URL"].split("///")[1]).execute("select inputs from est_bills where id=?", (bid,)).fetchone()[0])
ck("undo: the bold goes, the 80% stays", "_fmt" not in (db_inp().get("Summary") or {}) and abs(r.json()["total_due"] - due1) < 0.01 and r.json()["undone"]["label"] == "Bold on 3 cells", (db_inp().get("Summary"), r.json()["total_due"]))
r = c.post(f"/store/est/ipa/bill/{bid}/undo", headers=H, json={})
ck("undo again (a Work done change, from anywhere): 80% back to what it was, total due back", abs(r.json()["total_due"] - due0) < 0.01 and r.json()["undone"]["page"] == "work", (r.json()["total_due"], r.json().get("undone")))
r = c.post(f"/store/est/ipa/bill/{bid}/undo", headers=H, json={"redo": True})
ck("redo: the 80% again", abs(r.json()["total_due"] - due1) < 0.01, r.json()["total_due"])
h = c.get(f"/store/est/ipa/bill/{bid}/history", headers=H).json()
ck("... and Redo offers the bold next", h["redo"] and h["redo"]["label"] == "Bold on 3 cells", h)
c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {"Summary": {"4,8": 1}}})
h = c.get(f"/store/est/ipa/bill/{bid}/history", headers=H).json()
ck("a new change: the redo is gone", h["redo"] is None, h)
# a signing: nothing before it can be undone
import est_bills as EB
from database import SessionLocal
db = SessionLocal(); bb = db.get(EB.EstBill, bid); sg = EB._signs(bb) or {}
sg["prepared"] = {"name": "Preenu", "signed_at": "2999-01-01T10:00:00", "signed_by_name": "Preenu"}; bb.signs = json.dumps(sg); EB._undo_skip(); db.commit(); db.close()
h = c.get(f"/store/est/ipa/bill/{bid}/history", headers=H).json()
ck("signed: Undo says it cannot go back past the signing", h["undo"] is None and h["blocked"].startswith("Can't undo - bill was signed by Preenu"), h)
r = c.post(f"/store/est/ipa/bill/{bid}/undo", headers=H, json={})
ck("... and refuses", r.status_code == 400, r.text)
db = SessionLocal(); bb = db.get(EB.EstBill, bid); ck("the signature is untouched", "prepared" in (EB._signs(bb) or {})); db.close()
r = c.post(f"/store/est/ipa/bill/{bid}/status", headers=H, json={"status": "Approved"})
h = c.get(f"/store/est/ipa/bill/{bid}/history", headers=H).json()
ck("approved: no undo, history gone", h["undo"] is None and "Approved" in h["blocked"], h)
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
