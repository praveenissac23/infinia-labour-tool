"""Zoho push: what each approved petty cash line becomes in Zoho (with a
stand-in for Zoho), and a line deleted in Zoho comes back cancelled."""
import os, sys, tempfile
from datetime import date
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, credentials
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
fails = 0
def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg); fails += 0 if cond else 1

# A stand-in Zoho: accounts, a project, the VAT tax; records what was posted.
ACC = {"Site Petty Cash": "S", "Jomon Petty Cash": "J", "Company Petty Cash": "C", "Current Capital - Praveen": "CP",
       "ADCB": "B", "Cash": "K", "Employee Advance": "EA", "Authority Payment": "AP", "17a. Ceramic Tiles": "T17A",
       "Office Pantry Expenses": "PAN", "Visa Expenses": "VISA", "01. Preliminaries Including Mobilization": "P01"}
POSTED, GONE = [], set()
def fake_call(db_, method, path, params=None, body=None):
    if method == "GET" and path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": k, "account_id": v} for k, v in ACC.items()], "page_context": {"has_more_page": False}}
    if method == "GET" and path == "projects":
        return {"projects": [{"project_code": "913", "project_id": "PRJ913", "customer_id": "CUS913"}]}
    if method == "GET" and path == "settings/taxes":
        return {"taxes": [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "VAT5"}]}
    if method == "POST":
        POSTED.append((path, body)); n = str(len(POSTED))
        if body.get("account_id") == "PAN" and body.get("amount") == 999:
            raise Z.ZohoError(400, "Account is inactive")
        key = {"expenses": "expense", "journals": "journal", "banktransactions": "banktransaction"}[path]
        idk = {"expense": "expense_id", "journal": "journal_id", "banktransaction": "transaction_id"}[key]
        return {key: {idk: "Z" + n, "entry_number": n}}
    if method == "GET":
        if path.split("/")[-1] in GONE:
            raise Z.ZohoError(404, "The expense does not exist.")
        return {}
    raise AssertionError(path)
Z.call = fake_call
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
ok(Z.connected(s), "connected once a refresh token is kept")

def line(**k):
    x = models.PettyCash(on_date=date(2026, 10, 9), description=k.pop("desc", "x"), supplier=k.pop("sup", ""),
                         zoho_status="approved", **k)
    s.add(x); s.commit(); return x
s.add(models.Supplier(name="Dani Building Materials", name_key=M._supplier_key("Dani Building Materials"), zoho_id="V-DANI")); s.commit()
a = line(book="site", site="913", paid=346.5, desc="Tile adhesive", sup="DANI BUILDING MATERIALS", vat=True, vat_claim="claim", receipt_no="R-5521", trn="100555666700003",
         zoho_account="17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles")
b = line(book="office", paid=260, desc="918 DM fee", zoho_account="01. Preliminaries Including Mobilization › Authority Payments")
c = line(book="pro", paid=1000, desc="To Shafique for company cash book", zoho_account="Transfer to Company Petty Cash")
d = line(book="pro", received=15000, desc="Petty cash collected", zoho_account="From ADCB (transfer / cheque cashed)")
e = line(book="site", paid=100, desc="Pradeep salary advance", zoho_account="Employee Advance (salary advance / loan)")
f = line(book="praveen", paid=956.14, desc="Etisalat bill", zoho_account="Office › Visa Expenses")
g = line(book="praveen", received=5000, desc="Repaid by bank", zoho_account="From ADCB (transfer / cheque cashed)")
h = line(book="office", paid=999, desc="Water", zoho_account="Office › Office Pantry Expenses")
i = line(book="office", received=20000, desc="Cash from Emkaan", zoho_account="Client payment received in cash")
sent, failed = Z.push_many(s, [a, b, c, d, e, f, g, h, i])
ok(sent == 7 and len(failed) == 2, f"7 sent, 2 refused ({sent}, {failed})")
EXP = [b_ for p_, b_ in POSTED if p_ == "expenses"]
va = next(b_ for b_ in EXP if b_["amount"] == 346.5)
ok(va.get("vendor_id") == "V-DANI" and va["tax_treatment"] == "vat_registered" and va["tax_reg_no"] == "100555666700003" and va["tax_id"] == "VAT5",
   "VAT bill: Paid To = linked Zoho vendor, VAT Registered, TRN, 5% tax")
ok(all(b_["tax_treatment"] == "vat_not_registered" and "tax_id" not in b_ for b_ in EXP if b_["amount"] != 346.5),
   "bills without VAT: 'Non VAT Registered', no tax claimed (as the accountant enters them)")
ok(va["description"].startswith("Rcpt R-5521 · "), "receipt number in the Zoho description")
# VAT ticked but no choice: refused, nothing posted
nc = line(book="site", site="913", paid=63, desc="Disc", sup="DANI BUILDING MATERIALS", vat=True, trn="100555666700003",
          zoho_account="17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles")
n0 = len(POSTED); Z.push_many(s, [nc]); s.refresh(nc)
ok(len(POSTED) == n0 and "Claim 5% or Not claimable" in nc.zoho_err, "VAT bill without the claim choice: refused, nothing posted")
# not claimable (bill in a person's name): VAT Registered, TRN, Zero Rate
orig = Z.call
def with_zero(db_, method, path, params=None, body=None):
    if path == "settings/taxes":
        return {"taxes": [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "VAT5"}, {"tax_name": "Zero Rate", "tax_percentage": 0, "tax_id": "VAT0"}]}
    return orig(db_, method, path, params, body)
Z.call = with_zero; Z._CACHE.pop("vat0", None)
nc.vat_claim, nc.zoho_err = "zero", ""; s.commit()
Z.push_many(s, [nc]); s.refresh(nc)
zb = POSTED[-1][1]
ok(nc.zoho_status == "sent" and zb["tax_id"] == "VAT0" and zb["tax_treatment"] == "vat_registered" and zb["vendor_id"] == "V-DANI",
   "not claimable: VAT Registered, supplier, Zero Rate - as entered today")
# supplier not in Zoho: sent anyway, put on the to-do list
nv = line(book="site", site="913", paid=50, desc="Paint", sup="Unknown Shop", vat=True, vat_claim="claim", trn="100555666700003",
          zoho_account="17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles")
Z.push_many(s, [nv]); s.refresh(nv)
ok(nv.zoho_status == "sent" and "vendor_id" not in POSTED[-1][1] and nv.zoho_todo == "supplier", "supplier not in Zoho: sent, and on the 'add supplier' list")
import zohosync
ok(any(r["id"] == nv.id for r in zohosync._todo(s)), "to-do list shows it")
zohosync.todo_done({"src": "petty", "id": nv.id}, s, None); s.refresh(nv)
ok(nv.zoho_todo == "", "Done clears it")
# split receipt: one itemised expense, parts add up
import json as _j
sp = line(book="site", site="913", paid=500, desc="Mixed materials", sup="DANI BUILDING MATERIALS",
          zoho_account="17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles",
          splits=_j.dumps([{"account": "17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles", "amount": 300},
                           {"account": "01. Preliminaries Including Mobilization", "amount": 200}]))
Z.push_many(s, [sp]); s.refresh(sp)
ib = POSTED[-1][1]
ok(sp.zoho_status == "sent" and ib.get("is_itemized_expense") and [(l["account_id"], l["amount"]) for l in ib["line_items"]] == [("T17A", 300.0), ("P01", 200.0)]
   and "account_id" not in ib and ib["project_id"] == "PRJ913", "split: one itemised expense, 300 + 200 to two cost heads, with the project")
Z.call = orig
P = {p[1].get("reference_number"): p for p in POSTED}
pa = P[f"PC-{a.id}"]
ok(pa[0] == "expenses" and pa[1]["account_id"] == "T17A" and pa[1]["paid_through_account_id"] == "S"
   and pa[1]["project_id"] == "PRJ913" and pa[1]["customer_id"] == "CUS913" and pa[1]["tax_id"] == "VAT5"
   and pa[1]["tax_reg_no"] == "100555666700003" and pa[1]["is_inclusive_tax"], "site bill with VAT: expense, sub-head account, project, VAT, TRN")
ok(P[f"PC-{b.id}"][1]["account_id"] == "AP" and P[f"PC-{b.id}"][1]["paid_through_account_id"] == "C", "office DM fee to Authority Payment, paid through Company Petty Cash")
pc = P[f"PC-{c.id}"]
ok(pc[0] == "banktransactions" and pc[1]["from_account_id"] == "J" and pc[1]["to_account_id"] == "C", "PRO to office: transfer fund Jomon -> Company")
pd = P[f"PC-{d.id}"]
ok(pd[0] == "banktransactions" and pd[1]["from_account_id"] == "B" and pd[1]["to_account_id"] == "J", "PRO top-up: transfer ADCB -> Jomon")
pe = P[f"PC-{e.id}"][1]["line_items"]
ok(pe[0]["account_id"] == "EA" and pe[0]["debit_or_credit"] == "debit" and pe[1]["account_id"] == "S", "salary advance: journal Employee Advance / Site Petty Cash")
ok(P[f"PC-{f.id}"][1]["paid_through_account_id"] == "CP", "Praveen's bill paid through Current Capital - Praveen")
pg = P[f"PC-{g.id}"][1]["line_items"]
ok(pg[0]["account_id"] == "CP" and pg[1]["account_id"] == "B", "repaid to Praveen: journal Capital / ADCB")
s.refresh(h); s.refresh(i); s.refresh(a)
ok(h.zoho_status == "approved" and "inactive" in h.zoho_err, "Zoho's refusal kept on the line to retry")
ok(i.zoho_status == "approved" and "customer payment" in i.zoho_err, "client cash not guessed - told to record against the invoice")
ok(a.zoho_status == "sent" and a.zoho_id.startswith("expense:") and "PC-" in a.zoho_ref, "sent line keeps its Zoho id")
GONE.add(a.zoho_id.split(":")[1])
n = Z.check_deleted(s, force=True)
s.refresh(a)
ok(n == 1 and a.zoho_status == "cancelled" and "Deleted in Zoho" in a.zoho_err, "deleted in Zoho -> cancelled in the portal with the reason")
# approval: VAT choice stored; split must add up
import zohosync
u = models.User(username="ca2", full_name="CA", hashed_password="x", role="admin"); s.add(u); s.commit()
q1 = models.PettyCash(book="site", on_date=date(2026, 10, 12), description="Tiles", site="913", paid=400, vat=True, trn="100555666700003", zoho_status="")
s.add(q1); s.commit()
r = zohosync.approve({"lines": [{"id": q1.id, "account": "17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles",
                                 "splits": [{"account": "17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles", "amount": 250},
                                            {"account": "01. Preliminaries Including Mobilization", "amount": 100}]}]}, s, u)
s.refresh(q1)
ok(r["refused"] and "Pick VAT" in r["refused"][0]["why"] and "add up to 400.00" in r["refused"][0]["why"] and q1.zoho_status == "",
   "approval refused: VAT not chosen and split 350 of 400 - both shown")
r = zohosync.approve({"lines": [{"id": q1.id, "account": "x", "vat_claim": "zero",
                                 "splits": [{"account": "17. Floors & Wall Tiles (Internal) › 17a. Ceramic Tiles", "amount": 300},
                                            {"account": "01. Preliminaries Including Mobilization", "amount": 100}]}]}, s, u)
s.refresh(q1)
ok(not r["refused"] and q1.vat_claim == "zero" and q1.zoho_status in ("approved", "sent"), "approval with VAT choice and a split that adds up goes through")
print("fails=", fails)
