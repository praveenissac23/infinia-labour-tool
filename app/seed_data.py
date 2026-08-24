"""
One-time setup script: creates an initial admin login, and migrates the
real Master Data (employees, sites, engineers) from the desktop app's
master_data.json into the database. Safe to re-run - upserts rather
than duplicating.
"""
import json
import sys

from database import SessionLocal, engine, Base
import models
import auth


def run(master_data_json_path=None):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ---- Initial admin user ----
        existing_admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not existing_admin:
            admin = models.User(
                username="admin",
                hashed_password=auth.hash_password("changeme123"),
                full_name="Administrator",
                role="admin",
            )
            db.add(admin)
            db.commit()
            print("Created admin user - username: admin, password: changeme123 (CHANGE THIS)")
        else:
            print("Admin user already exists, skipping.")

        # ---- Master Data migration ----
        if master_data_json_path:
            with open(master_data_json_path) as f:
                store = json.load(f)

            emp_count = 0
            for emp_no, rec in store.get("employees", {}).items():
                existing = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
                if existing:
                    existing.name = rec.get("name", "")
                    existing.trade = rec.get("trade", "")
                    existing.total_salary = rec.get("total_salary", 0.0)
                    existing.basic_salary = rec.get("basic_salary", 0.0)
                    existing.active = rec.get("active", True)
                else:
                    db.add(models.Employee(
                        emp_no=emp_no, name=rec.get("name", ""), trade=rec.get("trade", ""),
                        total_salary=rec.get("total_salary", 0.0), basic_salary=rec.get("basic_salary", 0.0),
                        active=rec.get("active", True),
                    ))
                emp_count += 1
            db.commit()
            print(f"Migrated {emp_count} employees.")

            # sites/engineers are dicts of {code_or_name: {"active": bool}},
            # not flat lists - confirmed directly against the real
            # master_data.json structure.
            site_count = 0
            for code, rec in store.get("sites", {}).items():
                existing = db.query(models.Site).filter(models.Site.code == code).first()
                if existing:
                    existing.active = rec.get("active", True)
                else:
                    db.add(models.Site(code=code, active=rec.get("active", True)))
                    site_count += 1
            db.commit()
            print(f"Migrated {site_count} new sites.")

            eng_count = 0
            for name, rec in store.get("engineers", {}).items():
                existing = db.query(models.Engineer).filter(models.Engineer.name == name).first()
                if existing:
                    existing.active = rec.get("active", True)
                else:
                    db.add(models.Engineer(name=name, active=rec.get("active", True)))
                    eng_count += 1
            db.commit()
            print(f"Migrated {eng_count} new engineers.")
    finally:
        db.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    run(path)
