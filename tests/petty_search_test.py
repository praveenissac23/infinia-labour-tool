"""Petty cash search (14 Nov 2026): a word anywhere - description, supplier, site, receipt no., visa person,
amount - in every book this login opens (or the one open), for the dates shown; totals at the bottom; preview,
PDF and Excel of the search."""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
from datetime import date
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal
c = TestClient(main.app); c.__enter__()
bad = 0
def ck(n, ok, info=""):
    global bad; bad += 0 if ok else 1; print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  {str(info)[:500]!r}"))
db = SessionLocal()
db.query(models.PettyCash).delete(); db.commit()
L = lambda **k: models.PettyCash(**k)
db.add_all([
    L(book="site", on_date=date(2026, 10, 2), description="Advance to GUDDU (mason) for food - site 906", site="906", paid=200),
    L(book="site", on_date=date(2026, 10, 5), description="Cement 10 bags", supplier="Guddu Building Materials Trading LLC", paid=350.5),
    L(book=None, on_date=date(2026, 11, 3), description="Taxi guddu to camp", paid=45),                     # old line, no book = site
    L(book="office", on_date=date(2026, 11, 4), description="Salary advance - Guddu Kumar, labour no. 1123, returned part", received=100, paid=500),
    L(book="pro", on_date=date(2026, 11, 6), description="Medical for Guddu", paid=320, receipt_no="R-77"),
    L(book="praveen", on_date=date(2026, 11, 7), description="Paid Guddu overtime", paid=150),
    L(book="site", on_date=date(2026, 11, 8), description="Diesel jar", paid=60, receipt_no="GUD-1"),
    L(book="site", on_date=date(2026, 11, 9), description="Gloves", paid=1234.5),
])
db.commit()
tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
S = lambda **p: c.get("/store/petty-cash/search", headers=H, params=p)
j = S(q="guddu", month="all").json()
ck("every book: description, supplier, old lines with no book - any case", len(j["rows"]) == 6, [(r["book"], r["description"]) for r in j["rows"]])
ck("...a receipt no. 'GUD-1' is not 'guddu'", not any(r["description"] == "Diesel jar" for r in j["rows"]))
ck("totals at the bottom", j["paid"] == round(200 + 350.5 + 45 + 500 + 320 + 150, 2) and j["received"] == 100, (j["paid"], j["received"]))
ck("by book", {b["book"]: b["lines"] for b in j["by_book"]} == {"site": 3, "office": 1, "pro": 1, "praveen": 1}, j["by_book"])
j = S(q="guddu", scope="site", month="all").json()
ck("this book only", len(j["rows"]) == 3 and all(r["book"] == "site" for r in j["rows"]), j["rows"])
j = S(q="guddu", date_from="2026-11-01", date_to="2026-11-30").json()
ck("the dates shown", len(j["rows"]) == 4, [r["date"] for r in j["rows"]])
ck("two words: both on the line", [r["description"] for r in S(q="guddu advance", month="all").json()["rows"]] ==
   ["Advance to GUDDU (mason) for food - site 906", "Salary advance - Guddu Kumar, labour no. 1123, returned part"])
ck("an amount", len(S(q="1,234.50", month="all").json()["rows"]) == 1 and len(S(q="350.5", month="all").json()["rows"]) == 1)
ck("a receipt no.", len(S(q="R-77", month="all").json()["rows"]) == 1)
ck("a site", len(S(q="906", month="all").json()["rows"]) == 1)
ck("nothing typed: asked for a word", S(q="  ").status_code == 400)
# a login with the site book only sees the site book's lines
u = models.User(username="storek", full_name="Store keeper", role="office", hashed_password=auth.hash_password("pw123456"), permissions="petty_site")
db.add(u); db.commit()
H2 = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "storek", "password": "pw123456"}).json()["access_token"]}
j2 = c.get("/store/petty-cash/search", headers=H2, params={"q": "guddu", "month": "all"}).json()
ck("site login: only the site book", len(j2["rows"]) == 3 and j2["books"] == ["Site petty cash"], j2.get("books"))
ck("site login cannot pick the office book", c.get("/store/petty-cash/search", headers=H2, params={"q": "guddu", "scope": "office"}).status_code == 403)
# exports
vt = c.post("/auth/download-token", headers=H).json()["token"]
x = c.get(f"/export/store/petty-cash/search/view?q=guddu&month=all&token={vt}")
ck("preview: the lines, TOTAL, links keep the search", x.status_code == 200 and "TOTAL · 6 lines" in x.text and "1,565.50" in x.text and "q=guddu" in x.text, x.status_code)
x = c.get(f"/export/store/petty-cash/search?q=guddu&month=all&format=pdf&token={vt}")
ck("PDF", x.status_code == 200 and x.content[:4] == b"%PDF" and "Petty_cash_search_guddu" in x.headers.get("content-disposition", ""))
x = c.get(f"/export/store/petty-cash/search?q=guddu&month=all&format=excel&token={vt}")
from openpyxl import load_workbook
ws = load_workbook(io.BytesIO(x.content)).active
tot = [r for r in ws.iter_rows(values_only=True) if r[0] and str(r[0]).startswith("TOTAL")]
ck("Excel: lines and a SUM total row", x.status_code == 200 and tot and str(tot[0][-1]).startswith("=SUM("), tot)
x = c.get(f"/export/store/petty-cash/search?q=zzzz&month=all&format=pdf&token={vt}")
ck("nothing found still makes a PDF", x.status_code == 200 and x.content[:4] == b"%PDF")
html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app.html"), encoding="utf-8").read()
ck("the search box on the page", 'id="pc-q"' in html and "function pcDrawSearch" in html)
print("ALL PASS" if not bad else f"{bad} FAILURE(S)"); sys.exit(1 if bad else 0)
