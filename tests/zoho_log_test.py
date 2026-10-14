"""Sent to Zoho: every change the portal makes in Zoho is logged with where
the money went (from -> to), Check compares with the live Zoho record, and
Reverse deletes it in Zoho and puts the portal line back to waiting."""
import os, sys, tempfile, json
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, zoholog as ZL, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

ACC = [("Site Petty Cash", "S", "cash", ""), ("Company Petty Cash", "C", "cash", ""), ("Cash", "K", "cash", ""), ("ADCB", "B", "bank", ""),
       ("Block Purchase", "BP", "cost_of_goods_sold", "05. Blockworks"), ("Office Pantry Expenses", "PAN", "expense", "")]
M.put_setting(s, "zoho_accfull", json.dumps({"at": 1, "rows": [{"id": i, "name": n, "type": t, "parent": p} for n, i, t, p in ACC]}))
Z._CACHE.pop("chart_full", None)
STORE, CALLS = {}, []
def fake(db_, method, path, params=None, body=None):
    CALLS.append((method, path))
    if method == "GET" and path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": n, "account_id": i, "account_type": t, "parent_account_name": p} for n, i, t, p in ACC],
                "page_context": {"has_more_page": False}}
    if method == "GET" and path == "projects":
        return {"projects": [{"project_code": "913", "project_id": "PRJ913", "customer_id": "C913"}]}
    if method == "GET" and "/" in path:
        if path not in STORE:
            raise Z.ZohoError(404, "The expense does not exist.")
        return STORE[path]
    if method == "POST":
        n = str(len(CALLS))
        if path == "expenses":
            STORE[f"expenses/E{n}"] = {"expense": {"expense_id": "E" + n, "total": body.get("amount"), "paid_through_account_name": "Site Petty Cash",
                                                     "line_items": [{"account_name": "Block Purchase"}], "project_name": "913"}}
            return {"expense": {"expense_id": "E" + n}}
        if path == "banktransactions":
            STORE[f"banktransactions/T{n}"] = {"banktransaction": {"transaction_id": "T" + n, "amount": body["amount"],
                                                                     "from_account_name": "Site Petty Cash", "to_account_name": "Cash"}}
            return {"banktransaction": {"transaction_id": "T" + n}}
        return {}
    if method == "DELETE":
        if path not in STORE:
            raise Z.ZohoError(404, "The transaction does not exist.")
        STORE.pop(path, None); return {"message": "deleted"}
    return {}
Z._call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()

admin = models.User(username="boss", full_name="Praveen", hashed_password="x", role="admin", permissions="")
clerk = models.User(username="clerk", full_name="Clerk", hashed_password="x", role="office", permissions="accounts_zoho_view")
s.add_all([admin, clerk]); s.commit()

def line(**k):
    x = models.PettyCash(on_date=date(2026, 10, 15), description=k.pop("desc"), supplier="", zoho_status="approved", **k)
    s.add(x); s.commit(); return x
a = line(book="site", site="913", paid=420, desc="Blocks 6 inch", zoho_account="05. Blockworks › Block Purchase")
b = line(book="site", paid=500, desc="Back to cash box", zoho_account="Transfer to Cash")
sent, failed = Z.push_many(s, [a, b], admin); s.commit()
ok(sent == 2 and not failed, f"two lines sent ({sent}, {failed})")
logs = s.query(models.ZohoLog).order_by(models.ZohoLog.id).all()
ok(len(logs) == 2, f"each change logged ({len(logs)})")
la, lb = logs
ok(la.source == "petty" and la.item_id == a.id and la.ref == f"PC-{a.id}" and la.user_id == admin.id, "log knows the portal line and who sent it")
ok(la.kind == "expense" and la.from_acc == "Site Petty Cash" and la.to_acc == "05. Blockworks › Block Purchase" and la.amount == 420,
   f"expense: Site Petty Cash -> 05. Blockworks › Block Purchase, 420 ({la.from_acc} -> {la.to_acc})")
ok(json.loads(la.detail).get("project") in ("913", ""), "project carried")
ok(lb.kind == "banktransaction" and lb.from_acc == "Site Petty Cash" and lb.to_acc == "Cash", "transfer: Site Petty Cash -> Cash")

d = ZL.sent("2026-10-01", "2026-12-31", "", 0, s, admin)
ok(d["counts"]["sent"] == 2 and d["counts"]["amount"] == 920 and all(r["can_reverse"] for r in d["rows"]), f"Sent to Zoho lists both, total 920 ({d['counts']})")
ok(d["rows"][0]["web"].startswith("https://books.zoho.com/app/"), "each has a link into Zoho")

c = ZL.check(la.id, s, admin)
ok(c["exists"] and not c["diffs"], f"Check: Zoho agrees ({c.get('diffs')})")
STORE[f"expenses/{la.zoho_id}"]["expense"]["line_items"] = [{"account_name": "Office Pantry Expenses"}]
c = ZL.check(la.id, s, admin)
ok(c["diffs"] and "Office Pantry" in c["diffs"][0], f"Check: an account changed in Zoho is shown ({c['diffs']})")

def refused(fn, *a_):
    try:
        fn(*a_); return ""
    except HTTPException as e:
        return e.detail
ok("reason" in refused(ZL.reverse, la.id, {"reason": ""}, s, admin).lower(), "reverse needs a reason")
ok("only" in refused(ZL.reverse, la.id, {"reason": "wrong account"}, s, clerk).lower(), "only the chief accountant or admin reverses")
r = ZL.reverse(la.id, {"reason": "wrong account"}, s, admin)
s.refresh(a); s.refresh(la)
ok(r["ok"] and ("DELETE", f"expenses/{la.zoho_id}") in CALLS, "reverse deletes it in Zoho")
ok(a.zoho_status == "" and a.zoho_id == "" and "Reversed" in a.zoho_ref and "wrong account" in a.zoho_ref, "the line is back waiting, with the reason")
ok(la.reversed_at is not None and la.reverse_reason == "wrong account", "the log shows it reversed")
dl = s.query(models.ZohoLog).filter_by(action="delete").first()
ok(dl is not None and dl.source == "reverse", "the delete in Zoho is logged too")
ok("already" in refused(ZL.reverse, la.id, {"reason": "again"}, s, admin).lower(), "cannot reverse twice")
d = ZL.sent("2026-10-01", "2026-12-31", "", 0, s, admin)
ok(d["counts"]["sent"] == 1 and d["counts"]["reversed"] == 1, f"counts after reverse ({d['counts']})")
d = ZL.sent("2026-10-01", "2026-12-31", "", 1, s, admin)
ok(any(r["action"] == "delete" for r in d["rows"]), "All changes shows the delete as well")
# sent again after correction: a fresh log row
a.zoho_status, a.zoho_account = "approved", "Office Pantry Expenses"; s.commit()
Z.push_many(s, [a], admin); s.commit()
ok(s.query(models.ZohoLog).filter_by(item_id=a.id, action="create").count() == 2, "corrected and sent again: logged again")
# already deleted in Zoho by hand: reverse still frees the line
STORE.pop(f"banktransactions/{lb.zoho_id}", None)
c = ZL.check(lb.id, s, admin)
ok(not c["exists"], "Check: deleted in Zoho is shown")
r = ZL.reverse(lb.id, {"reason": "deleted in Zoho"}, s, admin); s.refresh(b)
ok(r["gone"] and b.zoho_status == "", "reverse of one already gone in Zoho: line freed")
# a refused send is logged as failed
def boom(db_, method, path, params=None, body=None):
    if method == "POST":
        raise Z.ZohoError(400, "Account is inactive")
    return fake(db_, method, path, params, body)
Z._call = boom
c2 = line(book="site", paid=10, desc="Water", zoho_account="Office Pantry Expenses")
Z.push_many(s, [c2], admin); s.commit()
f = s.query(models.ZohoLog).filter_by(item_id=c2.id).first()
ok(f is not None and not f.ok and "inactive" in f.error, "a refusal is logged with Zoho's reason")
print("fails=", fails)
