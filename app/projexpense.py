"""Project Expense - what each project has cost, from everything the app records.

Four kinds of cost are gathered per project (the site code - 906, 915 ...):

  Labour            each worker's paid salary for the cycle (final salary with
                    OT and additions/deductions) apportioned over the sites his
                    paid half-days were logged to - the same figure the Report
                    Builder's "Final Salary Cost" by site gives.
  Materials - LPO   purchase orders placed for a site. The site is read from the
                    order's project location (and the request it came from);
                    an order naming two sites is split equally. Net of VAT -
                    VAT is recovered, not a cost. Orders delivered to the store
                    are stock, not a project cost, until they are issued.
  Materials - store consumables sent from the store to a site, less what came
                    back (transfers move the cost with the goods), valued at the
                    rate last paid for that item on an LPO. Tools are not a cost.
  Petty cash        any petty cash book line spent on a site: the site box filled
                    in, or the site number written in the description. Salary
                    and wage payments are left out - labour already counts them.

What cannot be tied to a project is reported as "not linked", so nothing
spent disappears from view.
"""
import re
from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import main as M
import models, auth, export_web
import reports as rp
from database import get_db

router = APIRouter()
RIGHT = "accounts_expense"
CATS = [("labour", "Labour"), ("lpo", "Materials - LPO"), ("store", "Materials - from store"), ("petty", "Petty cash")]
CAT_LABEL = dict(CATS)
SALARY_WORDS = re.compile(r"salar|wages|payable|advance|recovery", re.I)
BOOK_LABEL = {"site": "Site", "pro": "PRO", "office": "Office", "naveen": "Naveen", "praveen": "Praveen"}


def _d(v):
    if not v:
        return None
    if isinstance(v, (date, datetime)):
        return v if isinstance(v, date) and not isinstance(v, datetime) else v.date()
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _in(dt, d1, d2):
    return dt is not None and (not d1 or dt >= d1) and (not d2 or dt <= d2)


def _projects(db):
    """Every project the app knows: the sites list and the contract list."""
    out = {}
    for s in db.query(models.Site).all():
        code = (s.code or "").strip()
        if code:
            out[code] = {"code": code, "name": (s.project_name or "").strip(), "plot": (s.plot_no or "").strip(),
                         "active": bool(s.active)}
    try:
        import projectpay as pp
        for sc in db.query(pp.ProjectScope).all():
            code = (sc.project or "").strip()
            if code and code not in out:
                out[code] = {"code": code, "name": "", "plot": "", "active": True}
    except Exception:
        pass
    return out


def _contracts(db):
    con, rec = defaultdict(float), defaultdict(float)
    try:
        import projectpay as pp
        for sc in db.query(pp.ProjectScope).all():
            con[(sc.project or "").strip()] += float(sc.contract or 0)
        for p in db.query(pp.ProjectPayment).all():
            sc = db.get(pp.ProjectScope, p.scope_id)
            if sc:
                rec[(sc.project or "").strip()] += float(p.amount or 0)
    except Exception:
        pass
    return con, rec


def _site_matcher(projects):
    codes = set(projects)
    plots = {}
    for c, p in projects.items():
        for tok in re.findall(r"\d{6,}", p["plot"] or ""):
            plots[tok] = c

    def match(*texts):
        found = []
        for t in texts:
            t = str(t or "")
            for tok in re.findall(r"(?<!\d)(\d{3})(?!\d)", t):
                if tok in codes and tok not in found:
                    found.append(tok)
            for tok in re.findall(r"\d{6,}", t):
                c = plots.get(tok)
                if c and c not in found:
                    found.append(c)
        return found
    return match


# ---- each source --------------------------------------------------------------

def _labour(db, d1, d2):
    """[(site, cycle, emp_no, name, days, ot_hours, cost)] - the payroll's own
    figure, split by the sites worked."""
    out = []
    company_by_emp = {e.emp_no: (e.company or "Infinia") for e in db.query(models.Employee).all()}
    cycles = [c for (c,) in db.query(models.EmployeeSummary.month_year).distinct().all() if c]
    for cyc in cycles:
        daily, sums, filters = M._report_source_rows(db, cyc, None, None)
        if d1 or d2:
            daily = [r for r in daily if _in(r.full_date, d1, d2)]
        if not daily:
            continue
        res = rp.build_custom_report("daily", ["site", "emp_no", "name"],
                                     ["days_present", "ot_hours", "final_salary_cost"],
                                     filters, daily, sums, company_by_emp)
        for r in res.rows:
            cost = float(r.get("final_salary_cost") or 0)
            if abs(cost) < 0.005 and not r.get("days_present"):
                continue
            out.append({"site": str(r.get("dim_0") or "").strip(), "cycle": cyc, "emp_no": r.get("dim_1") or "",
                        "name": r.get("dim_2") or "", "days": float(r.get("days_present") or 0),
                        "ot": float(r.get("ot_hours") or 0), "amount": round(cost, 2)})
    return out


def _lpos(db, match, d1, d2):
    """[(sites, line)] for every order not cancelled; sites [] = not on a project."""
    out = []
    for o in db.query(models.PurchaseOrder).all():
        if (o.status or "") == "cancelled" or not _in(o.order_date, d1, d2):
            continue
        req = db.get(models.MaterialRequest, o.request_id) if o.request_id else None
        req_site = (req.site or "").strip() if req else ""
        lines = db.query(models.PurchaseOrderLine).filter(models.PurchaseOrderLine.order_id == o.id).all()
        gross = sum(float(l.qty or 0) * float(l.rate or 0) for l in lines)
        disc = float(o.discount_pct or 0)
        net = gross * (1 - disc / 100.0)
        vat = sum(float(l.qty or 0) * float(l.rate or 0) * float(l.tax_pct or 0) / 100.0 for l in lines) * (1 - disc / 100.0)
        to_store = req_site.upper() == "STORE"
        sites = [] if to_store else (match(o.project_location, o.plot_no, o.job_scope) or match(req_site))
        out.append({"sites": sites, "to_store": to_store, "date": o.order_date, "ref": o.ref or f"LPO {o.po_no}",
                    "supplier": o.supplier_name or "", "location": o.project_location or req_site,
                    "items": ", ".join((l.description or "")[:40] for l in lines[:4]) + (" ..." if len(lines) > 4 else ""),
                    "net": round(net, 2), "vat": round(vat, 2), "id": o.id})
    return out


def _last_rates(db):
    """item_id -> (rate, date, LPO ref): the latest rate paid on an order."""
    best = {}
    for l, o in (db.query(models.PurchaseOrderLine, models.PurchaseOrder)
                   .join(models.PurchaseOrder, models.PurchaseOrder.id == models.PurchaseOrderLine.order_id).all()):
        if not l.item_id or (o.status or "") == "cancelled" or not l.rate:
            continue
        k = (o.order_date or date.min, o.id)
        if l.item_id not in best or k > best[l.item_id][0]:
            best[l.item_id] = (k, float(l.rate), o.ref)
    return {i: (v[1], v[0][0], v[2]) for i, v in best.items()}


def _store(db, projects, d1, d2):
    """Consumables issued to sites (returns and transfers netted), valued."""
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    rates = _last_rates(db)
    codes = set(projects)
    out = []
    for m in db.query(models.StoreMovement).order_by(models.StoreMovement.moved_on, models.StoreMovement.id).all():
        it = items.get(m.item_id)
        if not it or (it.item_type or "consumable") != "consumable" or not _in(m.moved_on, d1, d2):
            continue
        qty = float(m.qty or 0)
        legs = []
        to, frm = (m.location or "").strip(), (m.from_location or "").strip()
        if m.kind == "out" and to in codes:
            legs.append((to, qty))
        elif m.kind == "return" and frm in codes:
            legs.append((frm, -qty))
        elif m.kind == "transfer":
            if frm in codes:
                legs.append((frm, -qty))
            if to in codes:
                legs.append((to, qty))
        if not legs:
            continue
        rate, src = 0.0, "no price on file"
        if m.unit_cost:
            rate, src = float(m.unit_cost), "cost on the movement"
        elif it.id in rates:
            rate, src = rates[it.id][0], f"last LPO rate ({rates[it.id][2]})"
        elif it.est_price:
            rate, src = float(it.est_price), "estimated price"
        for site, q in legs:
            out.append({"site": site, "date": m.moved_on, "item": it.name, "code": it.code or "", "unit": it.unit or "",
                        "qty": q, "rate": rate, "amount": round(q * rate, 2), "priced_by": src,
                        "kind": {"out": "Issued", "return": "Returned to store"}.get(m.kind) or
                                ((f"Moved to {to}" if q < 0 else f"Moved from {frm}") if m.kind == "transfer" else m.kind),
                        "ref": m.reference or ""})
    return out


def _petty(db, match, d1, d2):
    """Every petty cash payment, with the project it belongs to (or none)."""
    out = []
    rows = db.query(models.PettyCash).all()
    for p in rows:
        paid = float(p.paid or 0)
        if paid <= 0 or not _in(p.on_date, d1, d2):
            continue
        desc = p.description or ""
        site_box = (p.site or "").strip()
        sites = match(site_box)
        how = "site box"
        if not sites:
            sites = match(desc)
            how = "site number in the description"
        salary = bool(SALARY_WORDS.search(desc))
        out.append({"sites": sites, "how": how, "salary": salary, "date": p.on_date, "book": p.book or "",
                    "description": desc, "supplier": p.supplier or "", "amount": round(paid, 2), "id": p.id})
    return out


# ---- the whole picture ---------------------------------------------------------

_CACHE = {}           # (from, to) -> (time, result): opening a project right after the list reuses the same figures
_CACHE_SECONDS = 30


def gather(db, date_from=None, date_to=None):
    import time
    key, now = (str(_d(date_from)), str(_d(date_to))), time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_SECONDS:
        return hit[1]
    g = _gather(db, date_from, date_to)
    for k in [k for k, v in _CACHE.items() if now - v[0] >= _CACHE_SECONDS]:
        _CACHE.pop(k, None)
    _CACHE[key] = (now, g)
    return g


def _gather(db, date_from=None, date_to=None):
    d1, d2 = _d(date_from), _d(date_to)
    projects = _projects(db)
    match = _site_matcher(projects)
    con, rec = _contracts(db)
    lines = defaultdict(list)                 # code -> detail lines
    unlinked = {"labour": 0.0, "lpo": 0.0, "lpo_store": 0.0, "petty": 0.0, "petty_by_book": defaultdict(float),
                "petty_salary": 0.0, "lpo_n": 0, "petty_n": 0}

    for r in _labour(db, d1, d2):
        if r["site"] in projects:
            lines[r["site"]].append({"cat": "labour", "date": None, **r})
        else:
            unlinked["labour"] += r["amount"]
    for o in _lpos(db, match, d1, d2):
        if o["sites"]:
            share = 1.0 / len(o["sites"])
            for s in o["sites"]:
                lines[s].append({"cat": "lpo", "amount": round(o["net"] * share, 2), "vat": round(o["vat"] * share, 2),
                                 "split": len(o["sites"]), **{k: v for k, v in o.items() if k not in ("net", "vat")}})
        elif o["to_store"]:
            unlinked["lpo_store"] += o["net"]
        else:
            unlinked["lpo"] += o["net"]; unlinked["lpo_n"] += 1
    for s in _store(db, projects, d1, d2):
        lines[s["site"]].append({"cat": "store", **s})
    for p in _petty(db, match, d1, d2):
        if p["salary"]:
            unlinked["petty_salary"] += p["amount"]
            continue
        if p["sites"]:
            share = 1.0 / len(p["sites"])
            for s_ in p["sites"]:
                lines[s_].append({"cat": "petty", **{**p, "amount": round(p["amount"] * share, 2), "split": len(p["sites"])}})
        else:
            unlinked["petty"] += p["amount"]; unlinked["petty_n"] += 1
            unlinked["petty_by_book"][p["book"]] += p["amount"]

    rows = []
    for code, pj in projects.items():
        ls = lines.get(code, [])
        by = {k: round(sum(l["amount"] for l in ls if l["cat"] == k), 2) for k, _ in CATS}
        total = round(sum(by.values()), 2)
        if not total and not con.get(code):
            continue
        rows.append({"code": code, "name": pj["name"], "plot": pj["plot"], "active": pj["active"],
                     "contract": round(con.get(code, 0), 2), "received": round(rec.get(code, 0), 2),
                     **by, "total": total, "lines": len(ls)})
    rows.sort(key=lambda r: (-r["total"], r["code"]))
    tot = {k: round(sum(r[k] for r in rows), 2) for k in ("contract", "received", "labour", "lpo", "store", "petty", "total")}
    unlinked["petty_by_book"] = {BOOK_LABEL.get(k, k.title() or "-"): round(v, 2) for k, v in unlinked["petty_by_book"].items()}
    for k in ("labour", "lpo", "lpo_store", "petty", "petty_salary"):
        unlinked[k] = round(unlinked[k], 2)
    return {"rows": rows, "totals": tot, "unlinked": unlinked, "lines": lines, "projects": projects,
            "from": d1.isoformat() if d1 else "", "to": d2.isoformat() if d2 else ""}


def _period(g):
    if g["from"] or g["to"]:
        f = M._dmy(M._as_date(g["from"])) if g["from"] else "the start"
        t = M._dmy(M._as_date(g["to"])) if g["to"] else "today"
        return f"{f} to {t}"
    return "All time"


def detail(g, code):
    pj = g["projects"].get(code)
    if not pj:
        raise HTTPException(status_code=404, detail="No such project.")
    row = next((r for r in g["rows"] if r["code"] == code), None) or {
        "code": code, "name": pj["name"], "plot": pj["plot"], "contract": 0, "received": 0,
        "labour": 0, "lpo": 0, "store": 0, "petty": 0, "total": 0}
    ls = g["lines"].get(code, [])
    iso = lambda d: d.isoformat() if hasattr(d, "isoformat") else (d or "")
    labour = defaultdict(lambda: {"days": 0.0, "ot": 0.0, "amount": 0.0, "workers": set()})
    for l in ls:
        if l["cat"] == "labour":
            c = labour[l["cycle"]]
            c["days"] += l["days"]; c["ot"] += l["ot"]; c["amount"] += l["amount"]; c["workers"].add(l["emp_no"])
    cyc_key = lambda c: datetime.strptime("25 " + c, "%d %B %Y") if re.match(r"^[A-Za-z]+ \d{4}$", c or "") else datetime.min
    return {"project": row,
            "labour_cycles": [{"cycle": c, "workers": len(v["workers"]), "days": round(v["days"], 1), "ot": round(v["ot"], 1),
                               "amount": round(v["amount"], 2)} for c, v in sorted(labour.items(), key=lambda kv: cyc_key(kv[0]))],
            "labour": sorted([{"cycle": l["cycle"], "emp_no": l["emp_no"], "name": l["name"], "days": l["days"], "ot": l["ot"],
                               "amount": l["amount"]} for l in ls if l["cat"] == "labour"],
                             key=lambda x: (cyc_key(x["cycle"]), -x["amount"])),
            "lpo": sorted([{"date": iso(l["date"]), "ref": l["ref"], "supplier": l["supplier"], "items": l["items"],
                            "location": l["location"], "split": l["split"], "amount": l["amount"], "vat": l["vat"], "id": l["id"]}
                           for l in ls if l["cat"] == "lpo"], key=lambda x: x["date"]),
            "store": sorted([{"date": iso(l["date"]), "kind": l["kind"], "item": l["item"], "code": l["code"], "unit": l["unit"],
                              "qty": l["qty"], "rate": l["rate"], "amount": l["amount"], "priced_by": l["priced_by"]}
                             for l in ls if l["cat"] == "store"], key=lambda x: x["date"]),
            "petty": sorted([{"date": iso(l["date"]), "book": BOOK_LABEL.get(l["book"], l["book"]), "description": l["description"],
                              "supplier": l["supplier"], "amount": l["amount"], "how": l["how"], "split": l.get("split", 1)}
                             for l in ls if l["cat"] == "petty"], key=lambda x: x["date"]),
            "period": _period(g)}


# ---- endpoints ---------------------------------------------------------------

def _reader(token, db):
    u = auth.get_download_user_from_token(token, db)
    if RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Project expense is for admin and accounts only.")
    return u


@router.get("/employees/accounts/project-expense")
def list_project_expense(date_from: str = "", date_to: str = "", db: Session = Depends(get_db),
                         user: models.User = Depends(M.require_screen(RIGHT))):
    g = gather(db, date_from, date_to)
    return {"rows": g["rows"], "totals": g["totals"], "unlinked": g["unlinked"], "period": _period(g)}


@router.get("/employees/accounts/project-expense/{code}")
def project_expense_detail(code: str, date_from: str = "", date_to: str = "", db: Session = Depends(get_db),
                           user: models.User = Depends(M.require_screen(RIGHT))):
    return detail(gather(db, date_from, date_to), code)


MONEY = ["Contract", "Received", "Labour", "Materials - LPO", "Materials - store", "Petty cash", "Total cost"]


def _summary_parts(db, date_from, date_to):
    g = gather(db, date_from, date_to)
    rows = []
    for r in g["rows"]:
        rows.append({"Project": r["code"] + (f" - {r['name']}" if r["name"] else "") + (f" (Plot {r['plot']})" if r["plot"] else ""),
                     "Contract": r["contract"], "Received": r["received"], "Labour": r["labour"],
                     "Materials - LPO": r["lpo"], "Materials - store": r["store"], "Petty cash": r["petty"],
                     "Total cost": r["total"],
                     "Cost % of contract": f"{r['total'] / r['contract'] * 100:.1f}%" if r["contract"] else "-"})
    u = g["unlinked"]
    sub = (f"{len(rows)} projects   |   {_period(g)}   |   LPO cost net of VAT   |   Not linked to a project: "
           f"petty cash {u['petty']:,.2f}, LPOs {u['lpo']:,.2f}, labour {u['labour']:,.2f}")
    return rows, "Project Expense", sub


def _detail_parts(db, code, date_from, date_to):
    d = detail(gather(db, date_from, date_to), code)
    p = d["project"]
    rows = []
    for c in d["labour_cycles"]:
        rows.append({"Category": "Labour", "Date": "", "Reference": c["cycle"],
                     "Details": f"{c['workers']} workers, {c['days']:g} days, {c['ot']:g} OT hours", "Amount": c["amount"]})
    for l in d["lpo"]:
        rows.append({"Category": "Materials - LPO", "Date": M._dmy(M._as_date(l["date"])), "Reference": l["ref"],
                     "Details": f"{l['supplier']} - {l['items']}" + (f" (split over {l['split']} sites)" if l["split"] > 1 else ""),
                     "Amount": l["amount"]})
    for s in d["store"]:
        rows.append({"Category": "Materials - store", "Date": M._dmy(M._as_date(s["date"])), "Reference": s["kind"],
                     "Details": f"{s['item']} - {abs(s['qty']):g} {s['unit']} @ {s['rate']:,.2f} ({s['priced_by']})", "Amount": s["amount"]})
    for x in d["petty"]:
        rows.append({"Category": "Petty cash", "Date": M._dmy(M._as_date(x["date"])), "Reference": x["book"],
                     "Details": x["description"] + (f" - {x['supplier']}" if x["supplier"] else "")
                                + (f" (split over {x['split']} sites)" if x.get("split", 1) > 1 else ""), "Amount": x["amount"]})
    # a subtotal line closes each category, shown in its own column so the TOTAL still adds the lines once
    out, names = [], ["Labour", "Materials - LPO", "Materials - store", "Petty cash"]
    for n in names:
        grp = [dict(r, **{"Category total": ""}) for r in rows if r["Category"] == n]
        if not grp:
            continue
        out += grp
        out.append({"Category": f"{n} - subtotal", "Date": "", "Reference": f"{len(grp)} line" + ("s" if len(grp) > 1 else ""),
                    "Details": "", "Amount": "", "Category total": round(sum(r["Amount"] or 0 for r in grp), 2)})
    rows = out
    title = f"Project Expense - {p['code']}" + (f" {p['name']}" if p.get("name") else "")
    sub = (f"{d['period']}   |   Labour {p['labour']:,.2f}   |   LPO {p['lpo']:,.2f}   |   Store {p['store']:,.2f}   |   "
           f"Petty cash {p['petty']:,.2f}   |   Total {p['total']:,.2f}"
           + (f"   |   Contract {p['contract']:,.2f}" if p.get("contract") else ""))
    return rows, title, sub


@router.get("/export/accounts/project-expense")
def export_project_expense(token: str, format: str = "pdf", code: str = "", date_from: str = "", date_to: str = "",
                           db: Session = Depends(get_db)):
    _reader(token, db)
    if code:
        rows, title, sub = _detail_parts(db, code, date_from, date_to)
        return M._hr_file(title, rows, sub, format, ["Amount", "Category total"], f"Project_Expense_{code}", totals=["Amount"])
    rows, title, sub = _summary_parts(db, date_from, date_to)
    return M._hr_file(title, rows, sub, format, MONEY, "Project_Expense")


@router.get("/export/accounts/project-expense/view")
def view_project_expense(token: str, code: str = "", date_from: str = "", date_to: str = "", db: Session = Depends(get_db)):
    from urllib.parse import quote
    u = _reader(token, db)
    t = quote(auth.create_view_token(u.username), safe="")
    q = f"code={quote(code)}&date_from={quote(date_from)}&date_to={quote(date_to)}"
    url = f"/export/accounts/project-expense?token={t}&{q}"
    if code:
        rows, title, sub = _detail_parts(db, code, date_from, date_to)
        return M._preview_page(title, sub, rows, url, url, money_cols=["Amount", "Category total"], total_cols=["Amount"])
    rows, title, sub = _summary_parts(db, date_from, date_to)
    return M._preview_page(title, sub, rows, url, url, money_cols=MONEY, total_cols=MONEY)
