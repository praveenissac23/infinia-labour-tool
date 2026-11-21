"""Fix of 21/11/2026: the email logins pasted on Credentials > Paste a list were saved three times - Save all was
pressed again while the first save was still fetching the logo, and each press saved the whole list.

Takes out the extra copies of a login that is an exact twin of an earlier one: same name, username, website,
category, admin-only setting and the same password, saved within 2 minutes of it. The first copy (lowest number)
stays. Logins that differ in anything, or that were saved apart in time (the older October entries), are left alone.

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_credential_twins_2026_11_21.py           # shows, changes nothing
    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_credential_twins_2026_11_21.py --apply   # takes them out
"""
import os, sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = os.environ.get("DATABASE_URL") or _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M                      # noqa: E402
import credentials as CRD             # noqa: E402
from database import SessionLocal     # noqa: E402


def twins(db):
    seen, gone = {}, []
    for c in db.query(CRD.Credential).order_by(CRD.Credential.id).all():
        k = (c.name or "", (c.username or "").lower(), c.domain or "", c.category or "", bool(c.admin_only), c.kind or "",
             CRD.unlock(c.secret or ""), CRD.unlock(c.notes or ""))
        first = seen.get(k)
        if first is not None and first.created_at and c.created_at and abs(c.created_at - first.created_at) <= timedelta(minutes=2):
            gone.append((c, first))
            continue
        seen[k] = c
    return gone


def run(apply):
    db = SessionLocal()
    gone = twins(db)
    for c, first in gone:
        print(f"  extra copy: #{c.id} {c.name} ({c.username}) - same as #{first.id}")
    print(f"Extra copies found: {len(gone)}." + ("" if apply else "  Nothing changed - run again with --apply to take them out."))
    if apply and gone:
        ids = [c.id for c, _ in gone]
        for c, _ in gone:
            db.delete(c)
        db.commit()
        M.log_action(db, None, "credential_deleted", f"Extra copies of pasted logins taken out: {', '.join('#' + str(i) for i in ids)}")
        print(f"Taken out: {len(ids)}.")
    db.close()


if __name__ == "__main__":
    run("--apply" in sys.argv)
