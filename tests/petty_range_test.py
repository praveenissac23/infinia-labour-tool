"""Petty cash register between two dates: brought forward is everything
before the first day; old month= links and 'all' still work."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
from datetime import date
from fastapi.testclient import TestClient
import main, models, pettycash
from database import SessionLocal
c = TestClient(main.app); c.__enter__()
bad = 0
def ck(n, ok, info=""):
    global bad; bad += 0 if ok else 1; print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  {info!r}"))
db = SessionLocal()
db.query(models.PettyCash).delete(); db.commit()
for d, rec, paid in [("2026-09-28", 1000, 0), ("2026-10-02", 0, 100), ("2026-10-05", 0, 50), ("2026-10-10", 500, 0), ("2026-10-15", 0, 75)]:
    db.add(models.PettyCash(book="site", on_date=date.fromisoformat(d), description="x", received=rec, paid=paid))
db.commit()
r = pettycash.register(db, "", "site", "2026-10-03", "2026-10-12")
ck("brought forward = everything before 3 Oct", r["opening"] == 900, r["opening"])
ck("only the lines inside the dates", [x["date"] for x in r["rows"]] == ["2026-10-05", "2026-10-10"], r["rows"])
ck("received / paid in period", (r["received"], r["paid"]) == (500, 50))
ck("closing follows", r["closing"] == 1350, r["closing"])
ck("label reads as dates", r["label"] == "03/10/2026 to 12/10/2026", r["label"])
ck("file name carries the dates", r["month"] == "2026-10-03_to_2026-10-12", r["month"])
r = pettycash.register(db, "", "site", "2026-10-01", "2026-10-31")
ck("a whole month still reads as the month", r["label"] == "October 2026" and r["month"] == "2026-10", (r["label"], r["month"]))
ck("old month= link unchanged", pettycash.register(db, "2026-10", "site")["opening"] == 1000)
ck("'all' still the full history", pettycash.register(db, "all", "site")["all"] and len(pettycash.register(db, "all", "site")["rows"]) == 5)
r = pettycash.register(db, "", "site", "2026-10-12", "2026-10-03")
ck("swapped dates are put right", r["from"] == "2026-10-03" and r["to"] == "2026-10-12", (r["from"], r["to"]))
r = pettycash.register(db, "", "site", "2026-10-03", "")
ck("to blank = up to today", r["from"] == "2026-10-03" and r["to"] >= "2026-10-17", (r["from"], r["to"]))
tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
j = c.get("/store/petty-cash?date_from=2026-10-03&date_to=2026-10-12&book=site", headers=H).json()
ck("API takes the dates", j["opening"] == 900 and len(j["rows"]) == 2, j.get("opening"))
vt = c.post("/auth/download-token", headers=H).json()["token"]
for fmt in ("pdf", "excel"):
    x = c.get(f"/export/store/petty-cash?date_from=2026-10-03&date_to=2026-10-12&book=site&format={fmt}&token={vt}")
    ck(f"{fmt} export for the dates", x.status_code == 200 and "2026-10-03_to_2026-10-12" in x.headers.get("content-disposition", ""), (x.status_code, x.headers.get("content-disposition")))
x = c.get(f"/export/store/petty-cash/view?date_from=2026-10-03&date_to=2026-10-12&book=site&token={vt}")
ck("preview shows the dates and keeps them on its PDF link", x.status_code == 200 and "03/10/2026 to 12/10/2026" in x.text and "date_from=2026-10-03" in x.text, x.status_code)
print("ALL PASS" if not bad else f"{bad} FAILURE(S)"); sys.exit(1 if bad else 0)
