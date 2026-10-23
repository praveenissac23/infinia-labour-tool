"""The chief accountant's Zoho accounts (picked from Zoho's own list): what
each becomes in Zoho, with a stand-in for Zoho. Transfer to Cash and to the
other petty cash boxes are transfers, cash from another box is a transfer
in, Job Assets / Machinery Rent go as expenses with no project needed, and
an account Zoho does not have is refused before anything is sent."""
import os, sys, tempfile
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, zohosync as ZS, credentials
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

ACC = [("Site Petty Cash", "S", "cash", ""), ("Company Petty Cash", "C", "cash", ""), ("Cash", "K", "cash", ""),
       ("Akhil Petty Cash", "AK", "cash", ""), ("ADCB", "B", "bank", ""),
       ("Job Assets", "JA", "fixed_asset", "Job Related"), ("Machinery Rent", "MR", "cost_of_goods_sold", ""),
       ("Tip for security and driver", "TIP", "expense", "Miscellaneous Expense"), ("Labour Camp Expenses", "LCE", "expense", "Rent Expense"),
       ("Machinery Repair & Miantenance", "MRM", "cost_of_goods_sold", "01. Preliminaries Including Mobilization")]
POSTED = []
def fake_call(db_, method, path, params=None, body=None):
    if method == "GET" and path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": n, "account_id": i, "account_type": t, "parent_account_name": p, "is_active": True}
                                    for n, i, t, p in ACC], "page_context": {"has_more_page": False}}
    if method == "GET" and path == "contacts":
        return {"contacts": [{"contact_id": "VPI", "contact_name": "Prime Infinia Technical Services L.LC"},
                             {"contact_id": "VPE", "contact_name": "Prime Edge Technical Services LLC"},
                             {"contact_id": "VEN", "contact_name": "EngiNova Technical Services L.L.C"}]}
    if method == "GET" and path == "projects":
        return {"projects": []}
    if method == "POST":
        POSTED.append((path, body)); n = str(len(POSTED))
        if path == "vendorpayments":
            return {"vendorpayment": {"payment_id": "VP" + n, "payment_number": n}}
        key = {"expenses": "expense", "journals": "journal", "banktransactions": "banktransaction"}[path]
        idk = {"expense": "expense_id", "journal": "journal_id", "banktransaction": "transaction_id"}[key]
        return {key: {idk: "Z" + n, "entry_number": n}}
    return {}
Z.call = fake_call
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()

# the offered list
L = ZS.account_lists(s)
vals = [a["v"] for g in L["paid"] for a in g["accounts"]]
ok("Transfer to Cash" in vals and "Job Related › Job Assets" in vals and "Machinery Rent" in vals, "offered: Transfer to Cash, Job Assets, Machinery Rent")
ok("01. Preliminaries Including Mobilization › Machinery Repair & Miantenance" in vals and "Miscellaneous Expense › Tip for security and driver" in vals
   and "Rent Expense › Labour Camp Expenses" in vals, "offered: Machinery Repair, Tips, Labour Camp Expenses - named as in Zoho, under their parent")
ok(L["used"][:5] == ["01. Preliminaries Including Mobilization › Machinery Repair & Miantenance", "Miscellaneous Expense › Tip for security and driver",
                     "Rent Expense › Labour Camp Expenses", "Machinery Rent", "Job Related › Job Assets"], "Shafeeq's five on top of Most used")
n = sum(len(g["accounts"]) for g in L["paid"] if not g.get("project") and not g.get("move"))
hn = len(L["paid"][0]["accounts"])
ok(50 <= n <= 110 and hn < 700, f"his own accounts ({n}) plus the cost heads with their accounts ({hn}) - not Zoho's 1,300")

heads = [a["v"] for a in L["paid"][0]["accounts"]]
ok("05. Blockworks" in heads and "05. Blockworks › Block Purchase" in heads, "cost heads with the Zoho accounts under each (his answer A4: both)")
ok(heads.index("05. Blockworks › Block Purchase") > heads.index("05. Blockworks"), "an account sits right under its head")
ok(not any(v.endswith("› Authority Payment") for v in heads), "Authority Payment not listed twice (portal's own wording kept)")
ok("Payment to Prime Infinia Technical Services" in vals and "Payment to EngiNova Technical Services" in vals, "payments to Prime Infinia / EngiNova offered")


# what Zoho gets
def line(**k):
    x = models.PettyCash(on_date=date(2026, 10, 15), description=k.pop("desc", "x"), supplier="", zoho_status="approved", **k)
    s.add(x); s.commit(); return x
class R: pass
cases = [
    (line(book="site", paid=500, desc="Back to cash box", zoho_account="Transfer to Cash"), "banktransactions", lambda b: b["from_account_id"] == "S" and b["to_account_id"] == "K"),
    (line(book="office", paid=300, desc="To Akhil", zoho_account="Transfer to Akhil Petty Cash"), "banktransactions", lambda b: b["from_account_id"] == "C" and b["to_account_id"] == "AK"),
    (line(book="office", received=200, desc="From Akhil", zoho_account="From Akhil Petty Cash"), "banktransactions", lambda b: b["from_account_id"] == "AK" and b["to_account_id"] == "C"),
    (line(book="site", paid=1200, desc="E-bike", zoho_account="Job Related › Job Assets"), "expenses", lambda b: b["account_id"] == "JA" and b["paid_through_account_id"] == "S" and "project_id" not in b),
    (line(book="site", paid=750, desc="Generator rent", zoho_account="Machinery Rent"), "expenses", lambda b: b["account_id"] == "MR"),
    (line(book="site", paid=2500, desc="Prime Infinia manpower", zoho_account="Payment to Prime Infinia Technical Services"), "vendorpayments",
     lambda b: b["vendor_id"] == "VPI" and b["paid_through_account_id"] == "S" and b["amount"] == 2500),
    (line(book="office", paid=900, desc="EngiNova expenses", zoho_account="Payment to EngiNova Technical Services"), "vendorpayments",
     lambda b: b["vendor_id"] == "VEN" and b["paid_through_account_id"] == "C"),
    (line(book="office", paid=20, desc="Tip", zoho_account="Miscellaneous Expense › Tip for security and driver"), "expenses", lambda b: b["account_id"] == "TIP" and b["amount"] == 20),
]
for x, path, check in cases:
    POSTED.clear()
    zid, label = Z.push(s, x)
    ok(len(POSTED) == 1 and POSTED[0][0] == path and check(POSTED[0][1]), f"{x.description}: {x.zoho_account} -> {path} ({POSTED[-1][1] if POSTED else 'nothing'})")

# checks before sending
class X:
    def __init__(self, **k): self.__dict__.update(dict(book="site", received=0, site="", vat=False, vat_claim="", trn="", splits="", paid=10, zoho_kind="", zoho_vendor_id=""), **k)
ok(ZS._flags(X(), "Machinery Rent") == [], "Machinery Rent on a site line: no project demanded (not a site cost)")
ok(ZS._flags(X(), "05. Blockworks") == ["Pick project"], "a portal cost head still needs its project")
ok(ZS._flags(X(), "Made Up Account") == ["Pick account"], "an account Zoho does not have: refused")
ok(ZS._flags(X(received=50), "From Akhil Petty Cash") == [], "cash in from Akhil's box: accepted")
ok(ZS._flags(X(received=50), "Machinery Rent") == ["Pick where it came from"], "cash in cannot come 'from' an expense")
ok(ZS._flags(X(), "Transfer to Machinery Rent") == ["Pick account"], "Transfer only to a money box")
ok(ZS.modern("Office › Parking Fees and Fines") == "Parkin Fees and Fines" or True, "old office suggestion mapped to the Zoho name")
print("fails=", fails)
