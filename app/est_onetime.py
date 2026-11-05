"""One-time data fixes that run by themselves when the app starts (after `git pull` + restart) - so a fix reaches the
live data with the normal deploy, without a separate command on the server. Each runs once (a Setting marks it done)
and only when every one of its checks passes; otherwise it writes nothing, says why in the log, and tries again at
the next start.
"""
import importlib.util
import json
import os

import models

HERE = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.join(HERE, "..", "deploy")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(DEPLOY, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def raida_groups(SessionLocal):
    """914 / 915 Al Raida: the items priced together as one lump sum put under their group (5 Nov 2026) - the same work
    and the same checks as deploy/sub_raida_groups_2026_11_05.py: every certificate's work to date, every bill's
    total and every line's certified figure must stay exactly as they are, or nothing is written."""
    key = "est_onetime_raida_groups_20261105"
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == key).first():
            return
        import estimation as E
        import est_pcsheet as S
        found = [x for x in db.query(E.EstSub).filter(E.EstSub.name.ilike("%AL RAIDA%")).all()
                 if (db.get(E.EstProject, x.project_id).code or "") in ("914", "915")]
        if len(found) != 2:
            return                                   # not this database (a test copy): nothing to do
        mod = _load("sub_raida_groups_2026_11_05")
        try:
            for code, jf in mod.FILES:
                mod.one(db, E, S, code, json.load(open(os.path.join(DEPLOY, jf))), True)
        except SystemExit as e:                      # a check did not pass: nothing written, tried again next start
            db.rollback()
            print(f"Al Raida groups not put in: {e}")
            return
        db.add(models.Setting(key=key, value="1"))
        db.commit()
        print("Al Raida 914 / 915: items priced together put under their groups (certificates unchanged)")
    except Exception as e:
        db.rollback()
        print("Al Raida groups:", e)
    finally:
        db.close()


def run(SessionLocal):
    raida_groups(SessionLocal)
