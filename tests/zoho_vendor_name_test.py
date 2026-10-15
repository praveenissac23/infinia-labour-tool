import os, sys, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, supzoho
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
supzoho._vendors = lambda db: [{"id": "V1", "name": "Enoc Retail LLC"}, {"id": "V2", "name": "Al Noor Building Materials"}, {"id": "V3", "name": "Dubai Municipality"}, {"id": "V4", "name": "Dubai Police"}]
f = []
def ok(c, m): print(("PASS " if c else "FAIL ") + m); f.append(c)
ok(Z.not_vendor("SALARY") and Z.not_vendor("Rajimol Salary 2 mnts") and Z.not_vendor("cash") and not Z.not_vendor("ENOC"), "not-a-supplier words")
ok(Z.vendor_by_name(s, "ENOC") == "V1", "ENOC finds Enoc Retail LLC")
ok(Z.vendor_by_name(s, "al noor building materials llc") == "V2", "exact name")
ok(Z.vendor_by_name(s, "Dubai") == "", "two Dubai vendors: none picked")
ok(Z.vendor_by_name(s, "ADNOC") == "", "unknown: none")
s.add_all([models.PettyCash(book="site", on_date=M._dubai_today(), description="x", supplier="SALARY", paid=50, zoho_todo="supplier"),
           models.PettyCash(book="site", on_date=M._dubai_today(), description="x", supplier="ENOC", paid=35, zoho_todo="supplier")]); s.commit()
ok(Z.clear_not_vendor_todo(s) == 2 and Z.clear_not_vendor_todo(s) == 0, "cleanup: petty cash lines off the Needs attention list, once")
print("ALL PASS" if all(f) else "FAILED")
