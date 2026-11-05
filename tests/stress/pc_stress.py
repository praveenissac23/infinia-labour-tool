"""Subcontractor payment certificates made in the app, at volume (5 Nov 2026): each difficult schedule of
tests/stress/boq_gen.py --pc is brought in through the upload (Excel), then four certificates are made on it with
random progress (lump sums by %, re-measured lines by quantity, items priced together by their group's %),
deductions, an advance and retention. Every figure on every certificate is worked out again here, independently,
from the lines; the printed certificate (preview and PDF) must show the same amount due.

    cd app && DATABASE_URL=sqlite:////tmp/pcs.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/stress/pc_stress.py DIR [--n 10]
"""
import argparse
import os
import random
import re
import sys

sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import auth  # noqa: E402
import estimation as E  # noqa: E402
from database import SessionLocal, engine  # noqa: E402

R2 = lambda x: round(x + 1e-9, 2)
fails = []


def ck(name, ok, extra=""):
    if not ok:
        fails.append(name)
        print("FAIL " + name + f"  -> {str(extra)[:300]}")


def main_():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=4)
    a = ap.parse_args()
    main._add_missing_columns()
    E.create_tables(engine)
    c = TestClient(main.app)
    c.__enter__()
    db = SessionLocal()
    u = db.query(models.User).filter_by(username="stress_qs").first() or models.User(username="stress_qs")
    u.full_name, u.role, u.permissions = "Stress QS", "admin", "settings,estimation_projects"
    u.hashed_password = auth.hash_password("stress12345")
    db.add(u)
    db.commit()
    H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "stress_qs", "password": "stress12345"}).json()["access_token"]}
    books = sorted(f for f in os.listdir(a.dir) if f.endswith(".xlsx"))[:a.n]
    checked = 0
    for bi, b in enumerate(books):
        rng = random.Random(a.seed * 1000 + bi)
        p = E.EstProject(code=f"S{bi:03d}", name=f"Stress {b}", status="Running")
        db.add(p)
        db.commit()
        ret, adv_pct, vat = rng.choice([5, 10]), rng.choice([0, 10]), 5
        r = c.post("/store/est/subs", json={"project_id": p.id, "name": f"STRESS SUB {bi}", "scope": "MEP", "value": 0, "ret_pct": ret,
                                             "adv_pct": adv_pct, "vat_pct": vat}, headers=H)
        sid = r.json()["id"]
        r = c.post(f"/store/est/subs/{sid}/items/import", headers=H, files={"file": (b, open(os.path.join(a.dir, b), "rb"))},
                   data={"save": "1", "mode": "replace", "force": "1"})
        if r.status_code != 200:
            ck(f"{b}: schedule brought in", False, r.text)
            continue
        items = c.get(f"/store/est/subs/{sid}/items", headers=H).json()["items"]
        contract = R2(sum(x["amount"] for x in items if x["grp"] != "in" and not x.get("is_var")))
        db.get(E.EstSub, sid).value = contract
        db.commit()
        priced = [x for x in items if x["grp"] != "in" and (x["amount"] or (x["qty"] and x["rate"]))]
        state = {x["id"]: 0.0 for x in priced}
        qstate = {x["id"]: 0.0 for x in priced}
        adv_paid = 0.0
        if adv_pct:
            adv_paid = R2(contract * adv_pct / 100.0)
            c.post("/store/est/subpcs", json={"sub_id": sid, "pc_type": "Advance", "adv_amount": adv_paid, "inv_ref": "ADV"}, headers=H)
        prev_net = 0.0
        if adv_pct:
            prev_net = adv_paid                      # the advance certificate pays the advance
        ded_total = 0.0
        for k in range(1, 5):
            pc = c.post("/store/est/subpcs", json={"sub_id": sid, "inv_ref": f"PC-{k:02d}"}, headers=H).json()["id"]
            lines = []
            for x in priced:
                if rng.random() < 0.5:
                    continue
                if x["measure"] == "qty":
                    qstate[x["id"]] = round(min((x["qty"] or 1) * 1.1, qstate[x["id"]] + rng.uniform(0, (x["qty"] or 1) / 3)), 2)
                    lines.append({"item_id": x["id"], "qty": qstate[x["id"]]})
                else:
                    state[x["id"]] = round(min(100.0, state[x["id"]] + rng.choice([5, 10, 12.5, 20, 33.33, 50])), 2)
                    lines.append({"item_id": x["id"], "pct": state[x["id"]]})
            deds = []
            if rng.random() < 0.6:
                q_, rt_ = rng.choice([(0, 0), (rng.randint(1, 40), R2(rng.uniform(5, 300)))])
                amt = R2(q_ * rt_) if q_ else R2(rng.uniform(100, 9000))
                deds.append({"cat": rng.choice(["Material", "Manpower", "Plant", "Other"]), "description": f"Supplied by main contractor {k}",
                             "qty": q_, "rate": rt_, "amount": amt if not q_ else 0, "counted": True})
                ded_total = R2(ded_total + amt)
            body = {"pc": {"ret_auto": True, "adv_auto": True, "measured_on": "2026-11-05"}, "lines": lines, "deds": deds}
            r = c.put(f"/store/est/subpcs/{pc}/sheet", json=body, headers=H)
            if r.status_code != 200:
                ck(f"{b} PC{k}: saved", False, r.text)
                break
            sh = c.get(f"/store/est/subpcs/{pc}/sheet", headers=H).json()
            cc, pcd = sh["calc"], sh["pc"]
            # independently: every line to date, the work, retention, advance recovery, net, this, VAT
            work = 0.0
            for x in priced:
                if x["measure"] == "qty":
                    work += R2(qstate[x["id"]] * (x["rate"] or 0))
                else:
                    work += R2((x["amount"] or 0) * state[x["id"]] / 100.0)
            work = R2(work)
            ret_ = R2(work * ret / 100.0)
            rec = R2(min(adv_paid, work * adv_pct / 100.0)) if adv_pct else 0.0
            other = R2(pcd.get("other_cum") or 0)
            net = R2(work + adv_paid - rec - ret_ - other)
            this = R2(net - prev_net)
            vat_ = R2(this * vat / 100.0)
            ok = all(abs(u_ - v_) < 0.011 for u_, v_ in ((pcd["work_cum"], work), (pcd["ret_cum"], ret_), (pcd["adv_rec_cum"] or 0, rec),
                                                        (cc["net_cum"], net), (cc["this"], this), (cc["vat"], vat_), (cc["payable"], R2(this + vat_))))
            ck(f"{b} PC{k}: every figure as worked out from the lines", ok,
               dict(work=(pcd["work_cum"], work), ret=(pcd["ret_cum"], ret_), rec=(pcd["adv_rec_cum"], rec), net=(cc["net_cum"], net),
                    this=(cc["this"], this), vat=(cc["vat"], vat_)))
            ck(f"{b} PC{k}: deductions to date on the certificate", abs(other - ded_total) < 0.011, (other, ded_total))
            tok = c.post("/auth/download-token", headers=H).json()
            tok = tok.get("token") if isinstance(tok, dict) else tok
            hv = c.get(f"/export/est/pc/{pc}?token={tok}&format=preview")
            pv = c.get(f"/export/est/pc/{pc}?token={tok}&format=pdf")
            ck(f"{b} PC{k}: preview and PDF made", hv.status_code == 200 and pv.status_code == 200 and pv.content[:4] == b"%PDF", (hv.status_code, pv.status_code))
            due = f"{cc['payable']:,.2f}"
            ck(f"{b} PC{k}: the printed certificate shows the amount due {due}", due in re.sub(r"<[^>]+>", " ", hv.text), due)
            prev_net = net
            checked += 1
    print(f"\n{checked} certificates checked on {len(books)} schedules")
    print(f"{len(fails)} FAILED" if fails else "ALL PASS")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main_()
