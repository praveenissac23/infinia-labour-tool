"""Account names as Zoho really answers: the list leaves out sub-accounts
(found by asking for the name), and an income account never takes a cost."""
import os, sys, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
ALL = [("ADCB", "B", "bank", True), ("Office Pantry Expenses", "PAN", "expense", True),
       ("17a. Ceramic Tiles", "T17A", "cost_of_goods_sold", False), ("Visa Expenses", "VISA", "cost_of_goods_sold", False),
       ("Design & Supervision Fee", "INCOME1", "income", True), ("Design and Supervision Charges", "DSC", "cost_of_goods_sold", False),
       ("Authority Payment", "AP", "cost_of_goods_sold", True), ("Current Capital - Praveen", "CCP", "equity", True)]
KIND = {"Asset": ("bank",), "Equity": ("equity",), "Expense": ("expense", "cost_of_goods_sold"), "Liability": (), "Income": ("income",)}
CALLS = []
def fake(db_, method, path, params=None, body=None):
    p = params or {}; CALLS.append(p)
    if path != "chartofaccounts":
        return {}
    rows = [{"account_name": n, "account_id": i, "account_type": t, "is_active": True} for n, i, t, top in ALL]
    if "account_name" in p:
        return {"chartofaccounts": [r for r in rows if r["account_name"].lower() == p["account_name"].lower()]}
    if "search_text" in p:
        return {"chartofaccounts": [r for r in rows if p["search_text"].lower() in r["account_name"].lower()]}
    kind = p.get("filter_by", "").split(".")[-1]
    # the plain list: top-level accounts only, as Zoho does
    return {"chartofaccounts": [r for (n, i, t, top), r in zip(ALL, rows) if top and t in KIND.get(kind, ())], "page_context": {"has_more_page": False}}
Z.call = fake; Z._CACHE.clear()
ok(Z.account_id(s, "Office › Office Pantry Expenses") == "PAN", "top-level account found from the list")
ok(Z.account_id(s, "17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles") == "T17A", "sub-account missing from the list is found by its name")
ok(Z.account_id(s, "Office › Visa Expenses") == "VISA", "Visa Expenses found")
ok(Z.account_id(s, "Design & Supervision Fee") == "DSC", "a cost never goes to the INCOME account of the same name")
ok(Z.account_id(s, "01. Preliminaries Including Mobilization › Authority Payments") == "AP", "Authority Payments -> Zoho 'Authority Payment'")
ok(Z.account_id(s, "Current Capital - Praveen") == "CCP", "Praveen's book account found")
ok(Z.account_id(s, "Something Zoho Lacks") == "", "a name Zoho lacks stays unfound - the line is refused, not guessed")
ok(not any(c.get("filter_by") == "AccountType.Income" for c in CALLS), "income accounts are never read for costs")
print("fails=", fails)
