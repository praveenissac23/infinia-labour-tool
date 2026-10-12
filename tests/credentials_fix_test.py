"""The 12 Oct fix of the saved logins: the first feed's rows come out, the
sheet goes in row by row (no borrowed names), hand-made logins stay."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deploy"))
os.environ.setdefault("INFINIA_NO_PUSH", "1"); os.environ["INFINIA_NO_LOGO"] = "1"
os.environ.setdefault("INFINIA_CRED_KEY_FILE", "/tmp/cred_fix_test.key")
import main, credentials as CR
from database import SessionLocal
import fix_credentials_oct12 as F
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)
db = SessionLocal()
for x in F.OLD:   # what the first feed made
    db.add(CR.Credential(name=x["name"], url=x["url"], domain=CR.domain_of(x["url"]), kind="login", category=x["category"],
                         username=x["username"], secret=CR.lock(x["secret"]), notes=CR.lock(x["notes"])))
db.add(CR.Credential(name="My bank", kind="login", category="Bank", username="me", secret=CR.lock("x")))
db.commit(); db.close()
F.main(); F.main()
db = SessionLocal(); rows = db.query(CR.Credential).all()
by = lambda n: [r for r in rows if r.name == n]
ck("hand-made login kept", len(by("My bank")) == 1)
ck("no Wi-Fi / PO Box under Synology", not [r for r in rows if r.name.startswith("SYNOLOGY") or (r.name.startswith("Synology") and r.username in ("OFFICE WIFI PASSWORD", "PO Box"))])
w = by("Office Wi-Fi"); ck("Wi-Fi on its own, Office", w and w[0].category == "Office" and CR.unlock(w[0].secret) == "p@infinia", [(r.name, r.category) for r in w])
p = by("PO Box"); ck("PO Box as a note", p and p[0].kind == "note" and "85567" in CR.unlock(p[0].notes))
c = by("cPanel (BigRock hosting)"); ck("cPanel: address as website, no username", len(c) == 2 and all(r.url.startswith("https://sh003") and not r.username for r in c))
wf = by("Webflow (website hosting)"); ck("Webflow: email as username, password as password", wf and wf[0].username == "infiniacontracting@gmail.com" and CR.unlock(wf[0].secret) == "infi@UAE25")
z = by("Zoho Books"); ck("Zoho under Software", z and z[0].category == "Software")
ck("no 'Name carried' notes", not any("carried" in CR.unlock(r.notes) for r in rows))
ck("run twice: no doubles", len(rows) == len(F.NEW) + 1, (len(rows), len(F.NEW)))
ck("Salik our car once", len([r for r in rows if r.username == "35630592"]) == 1)
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")
