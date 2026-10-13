"""Suppliers: portal master, exact names linked, others never guessed;
a linked supplier's changes are copied to Zoho on save."""
import os, sys, tempfile
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, supzoho, schemas, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
u = models.User(username="ca", full_name="CA", hashed_password="x", role="office", permissions="accounts_zoho,approvals")
s.add(u); s.commit()
def sup(name, trn=""):
    x = models.Supplier(name=name, name_key=M._supplier_key(name), trn=trn, active=True); s.add(x); s.commit(); return x
a = sup("Al Raida Electromechanical Services", "100111222300003")
b = sup("Dani Trading")
c = sup("Brand New Shop")
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
CALLS = []
VEND = [{"contact_id": "V1", "contact_name": "AL RAIDA ELECTROMECHANICAL SERVICES L.L.C"},
        {"contact_id": "V2", "contact_name": "Dani Trading LLC"}, {"contact_id": "V3", "contact_name": "Dani Building Materials"}]
def fake(db_, method, path, params=None, body=None):
    CALLS.append((method, path, body))
    if method == "GET" and path == "contacts":
        return {"contacts": VEND, "page_context": {"has_more_page": False}}
    if method == "POST" and path == "contacts":
        return {"contact": {"contact_id": "NEW9"}}
    return {}
Z.call = fake
d = supzoho.listing(match=1, db=s, user=u)
s.refresh(a); s.refresh(b); s.refresh(c)
ok(a.zoho_id == "V1", "exact name (case, L.L.C ignored) linked by itself")
ok(b.zoho_id == "V2", "'Dani Trading' linked to 'Dani Trading LLC', not to 'Dani Building Materials'")
ok(c.zoho_id == "" , "a supplier with no exact match is not guessed")
supzoho.create(c.id, db=s, user=u); s.refresh(c)
posted = [x for x in CALLS if x[0] == "POST"][-1][2]
ok(c.zoho_id == "NEW9" and posted["contact_type"] == "vendor" and posted["tax_treatment"] == "vat_not_registered", "Create in Zoho makes a vendor and links it")
try:
    supzoho.link(b.id, {"zoho_id": "V1"}, db=s, user=u); ok(False, "double link refused")
except HTTPException:
    ok(True, "one Zoho vendor cannot be linked to two suppliers")
CALLS.clear()
M.update_supplier(a.id, schemas.SupplierIn(name="Al Raida Electromechanical Services", contact_person="Ali", phone="0501234567",
                  trn="100111222300003", email="a@b.ae", payment_terms="30 days", address="Al Quoz"), db=s, user=u)
put = [x for x in CALLS if x[0] == "PUT"]
ok(put and put[0][1] == "contacts/V1" and put[0][2]["tax_reg_no"] == "100111222300003" and put[0][2]["billing_address"]["address"] == "Al Quoz",
   "editing a linked supplier copies the change to its Zoho vendor")
def boom(*a, **k): raise Z.ZohoError(400, "Zoho down")
Z.call = boom
M.update_supplier(a.id, schemas.SupplierIn(name="Al Raida Electromechanical Services", contact_person="Ali", phone="0501234567",
                  trn="100111222300003", email="a@b.ae", payment_terms="45 days", address="Al Quoz"), db=s, user=u)
s.refresh(a)
ok(a.payment_terms == "45 days" and "Zoho down" in a.zoho_err, "if Zoho refuses, the supplier still saves and the reason is kept")
print("fails=", fails)
