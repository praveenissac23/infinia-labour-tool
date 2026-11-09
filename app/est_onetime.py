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


def _note(db, text):
    """Why a fix did not go in, kept in the audit log (read from the app's data, not only the server log); once a day."""
    try:
        import datetime as dt
        last = db.query(models.AuditLog).filter(models.AuditLog.action == "est_onetime").order_by(models.AuditLog.id.desc()).first()
        if last and last.details == text[:2000] and last.created_at and (dt.datetime.now(last.created_at.tzinfo) - last.created_at).days < 1:
            return
        db.add(models.AuditLog(action="est_onetime", details=text[:2000]))
        db.commit()
    except Exception:
        db.rollback()


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
            _note(db, f"Al Raida 914/915 groups NOT put in (nothing changed): {e}")
            return
        db.add(models.Setting(key=key, value="1"))
        db.add(models.AuditLog(action="est_onetime", details="Al Raida 914/915: items priced together put under their groups; "
                                                              "every certificate's figures checked unchanged"))
        db.commit()
        print("Al Raida 914 / 915: items priced together put under their groups (certificates unchanged)")
    except Exception as e:
        db.rollback()
        print("Al Raida groups:", e)
        _note(db, f"Al Raida 914/915 groups NOT put in (nothing changed): {type(e).__name__}: {e}")
    finally:
        db.close()


def abaad_whole(SessionLocal):
    """913 Al Abaad (post-tension): the schedule held one line of 21,000 - "Ground Floor Work Progress - 30% of the
    Work" - against a 70,000 subcontract, so nothing past that stage could ever be certified (6 Nov 2026, Praveen:
    21,000 is 30% of the 70,000). The line becomes the whole subcontract, 70,000, certified by %: PC-02's 100% of
    21,000 becomes 30% of 70,000 - the same 21,000. Every certificate's work to date, retention and advance recovery
    are checked unchanged, or nothing is written."""
    key = "est_onetime_abaad_whole_20261106"
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == key).first():
            return
        import estimation as E
        import est_pcsheet as S
        subs = [x for x in db.query(E.EstSub).filter(E.EstSub.name.ilike("%AL ABAAD%")).all()
                if (db.get(E.EstProject, x.project_id).code or "") == "913"]
        if len(subs) != 1:
            return                                   # not this database (a test copy): nothing to do
        sub = subs[0]
        items = db.query(S.EstSubItem).filter(S.EstSubItem.sub_id == sub.id, S.EstSubItem.is_var == False).all()  # noqa: E712
        why = None
        if abs((sub.value or 0) - 70000) > 0.01:
            why = f"subcontract value is {sub.value:,.2f}, not 70,000"
        elif len(items) != 1 or abs((items[0].amount or 0) - 21000) > 0.01:
            why = "the schedule is no longer the one 21,000 line"
        if why:
            _note(db, f"913 Al Abaad schedule NOT changed (nothing changed): {why}")
            db.add(models.Setting(key=key, value="skipped"))
            db.commit()
            return
        it = items[0]
        pcs = db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == sub.id).all()
        before = {p.id: (round(p.work_cum or 0, 2), round(p.ret_cum or 0, 2), round(p.adv_rec_cum or 0, 2)) for p in pcs}
        lines = db.query(S.EstPCLine).filter(S.EstPCLine.item_id == it.id).all()
        was = {ln.id: S.line_amount(it, ln) for ln in lines}
        for ln in lines:                                 # the same money, as a % of the whole 70,000
            if it.measure == "qty":
                worth = S.line_amount(it, ln) + (ln.deduct or 0)
                ln.qty, ln.pct = 0, 0
            else:
                worth = (it.amount or 0) * (ln.pct or 0) / 100.0
            ln.pct = round(worth / 70000 * 100, 6)
        it.measure = "pct"
        it.qty, it.unit, it.rate, it.amount = 1, it.unit or "LS", 70000.0, 70000.0
        it.description = "Post-tension works - the whole subcontract, certified by % done (Ground floor = 30%)"
        db.flush()
        for ln in lines:
            if abs(S.line_amount(it, ln) - was[ln.id]) > 0.005:
                raise SystemExit(f"a certificate line would change ({was[ln.id]:,.2f} -> {S.line_amount(it, ln):,.2f})")
        S.refresh_sub(db, sub.id)
        db.flush()
        db.expire_all()
        after = {p.id: (round(db.get(E.EstSubPC, p.id).work_cum or 0, 2), round(db.get(E.EstSubPC, p.id).ret_cum or 0, 2),
                        round(db.get(E.EstSubPC, p.id).adv_rec_cum or 0, 2)) for p in pcs}
        if after != before:
            raise SystemExit(f"certificate figures would change {before} -> {after}")
        db.add(models.Setting(key=key, value="1"))
        db.add(models.AuditLog(action="est_onetime", details="913 Al Abaad: schedule line made the whole 70,000 subcontract "
                                                              "(certified by %); every certificate's figures checked unchanged"))
        db.commit()
        print("913 Al Abaad: schedule is now the whole 70,000 (certificates unchanged)")
    except SystemExit as e:
        db.rollback()
        _note(db, f"913 Al Abaad schedule NOT changed (nothing changed): {e}")
    except Exception as e:
        db.rollback()
        _note(db, f"913 Al Abaad schedule NOT changed (nothing changed): {type(e).__name__}: {e}")
    finally:
        db.close()


def bill_signers(SessionLocal):
    """Every Draft bill nobody has signed yet: the 'Prepared, checked and approved by' lines as on 914 Interim Bill 8
    (9 Nov 2026) - names in full from each line's list (914: Anoop S -> Anoop Subramanian), 913 Interim Bill 10:
    Prepared by left for a QS to be picked, Checked by Remya Uchambally taken off, Approved by Anoop Subramanian and
    the consultant added. Bills approved or signed are not touched. Each bill's change is written to the audit log."""
    key = "est_onetime_bill_signers_20261109"
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == key).first():
            return
        import est_bills as EB
        notes = []
        for b in db.query(EB.EstBill).filter(EB.EstBill.status == "Draft").all():
            if any((v or {}).get("signed_at") for v in EB._signs(b).values()):
                continue
            fmt = db.get(EB.EstBillFormat, b.format_id)
            if not fmt:
                continue
            try:
                inputs = json.loads(json.dumps(EB._inputs(b)))
                model = EB._bill_model(fmt, inputs)
                values = EB.BE.calculate(model, inputs)
                cons = ((EB._cover(model, values) or {}).get("facts") or {}).get("consultant") or ""
                due0 = b.total_due
                EB._undo_skip()
                log = EB.apply_roles(b, model, inputs, cons)
                inputs, values = EB._calc(model, inputs)
                b.inputs = json.dumps(inputs)
                EB._save_totals(b, model, values)
                if abs((b.total_due or 0) - (due0 or 0)) > 0.005:
                    raise ValueError(f"total due would change {due0} -> {b.total_due}")
            except Exception as e:                   # one bill that cannot be read is left as it is
                db.rollback()
                notes.append(f"bill #{b.id}: left as it was ({type(e).__name__}: {e})")
                continue
            if log:
                notes.append(f"bill #{b.id} ({b.label}): " + "; ".join(log))
        db.add(models.Setting(key=key, value="1"))
        db.add(models.AuditLog(action="est_onetime", details=("Bill signers (Prepared, checked and approved by): " + ("; ".join(notes) or "none needed"))[:4000]))
        db.commit()
        if notes:
            print("Bill signers: " + "; ".join(notes))
    except Exception as e:
        db.rollback()
        _note(db, f"Bill signers NOT put in (nothing changed): {type(e).__name__}: {e}")
    finally:
        db.close()


def summary_mirror(SessionLocal):
    """Lines and sections added to a bill's sheet (913 bill 10: VI VARIATION ORDER - 04 / Construction of Swimming
    Pool 312,000 on the Cost Proposal Log) put on the Summary that copies that sheet line by line, so its totals and
    TOTAL DUE take them in (7 Nov 2026). Draft bills only; each bill's change is written to the audit log."""
    key = "est_onetime_summary_mirror_20261107"
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == key).first():
            return
        import est_bills as EB
        notes = []
        for b in db.query(EB.EstBill).filter(EB.EstBill.status == "Draft").all():
            fmt = db.get(EB.EstBillFormat, b.format_id)
            if not fmt:
                continue
            inputs = EB._inputs(b)
            try:
                new, added = EB._mirror_repair(fmt, json.loads(json.dumps(inputs)))
            except Exception as e:                   # one bill that cannot be read is left as it is
                notes.append(f"bill #{b.id}: left as it was ({type(e).__name__})")
                continue
            if not added:
                continue
            due0, wd0 = b.total_due, b.work_done
            EB._undo_skip()                          # a fix at the deploy is not anyone's step to undo
            model = EB._bill_model(fmt, new)
            new, values = EB._calc(model, new)
            b.inputs = json.dumps(new)
            EB._save_totals(b, model, values)
            notes.append(f"bill #{b.id} ({b.label}): {len(added)} added row(s) put on the Summary {[(a[0], a[1], a[2], a[3]) for a in added]}; "
                         f"total due {due0 or 0:,.2f} -> {b.total_due or 0:,.2f}, work done {wd0 or 0:,.2f} -> {b.work_done or 0:,.2f}")
        db.add(models.Setting(key=key, value="1"))
        db.add(models.AuditLog(action="est_onetime", details=("Summary copies of added lines: " + ("; ".join(notes) or "none needed"))[:4000]))
        db.commit()
        if notes:
            print("Summary copies of added lines: " + "; ".join(notes))
    except Exception as e:
        db.rollback()
        _note(db, f"Summary copies of added lines NOT put in (nothing changed): {type(e).__name__}: {e}")
    finally:
        db.close()


def run(SessionLocal):
    raida_groups(SessionLocal)
    abaad_whole(SessionLocal)
    summary_mirror(SessionLocal)
    bill_signers(SessionLocal)
