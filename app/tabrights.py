"""Settings > Access, tab by tab.

A role is ticked page by page, tab by tab and down to the tabs inside a
tab. Each tick is a "leaf" with an id - page.tab or page.tab.sub - read
from access_tree.json, which deploy/build_temporary_pages.py writes from
the same list of pages and tabs the app is drawn from.

How a login's ticks are kept: in the same comma list as its rights, the
leaf ids beside the broad rights they bring with them (a dot tells them
apart). A login whose list holds no leaf ids at all has never been ticked
tab by tab: it is shown every tab its broad rights opened before - so
nothing changed for anybody the day this arrived.

The broad rights still guard every endpoint as before. On top of that,
GATES below names the endpoints that belong to one tab of a page that
shares a broad right with other tabs (Material list and Stock on hand are
both "store"; Loans and Gratuity are both "hrpayroll") - those are
refused to a ticked login unless that tab is ticked. A login never ticked
tab by tab is not checked here at all: it keeps exactly what it had.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "access_tree.json"), encoding="utf-8") as _f:
    TREE = json.load(_f)

LEAVES = {}          # id -> {"id", "label", "right", "grant", "page"}
PAGE_LABEL = {}      # page id -> label
PATH_LABEL = {}      # leaf id -> "Store & Purchasing > Stock > Material list"


def _walk(node, page, trail):
    trail = trail + [node["label"]]
    if "right" in node:
        LEAVES[node["id"]] = dict(node, page=page)
        PATH_LABEL[node["id"]] = " > ".join(trail)
    for c in node.get("children", []):
        _walk(c, page, trail)


for _p in TREE:
    PAGE_LABEL[_p["id"]] = _p["label"]
    for _c in _p.get("children", []):
        _walk(_c, _p["id"], [_p["label"]])


def is_leaf(key):
    return key in LEAVES


def split(raw):
    """A stored list -> (broad rights, leaf ids, has leaf ids)."""
    keys = [k.strip() for k in (raw or "").split(",") if k.strip()]
    leaves = [k for k in keys if k in LEAVES]
    return [k for k in keys if "." not in k], leaves, any("." in k for k in keys)


def from_rights(rights):
    """The tabs a list of broad rights opened before ticks existed."""
    have = set(rights or [])
    return sorted(i for i, l in LEAVES.items() if any(r in have for r in l["right"]))


def rights_for(tabs):
    """The broad rights a set of ticks brings with it."""
    out = {"settings"}
    for t in tabs or []:
        if t in LEAVES:
            out.update(LEAVES[t]["grant"])
    return out


def stored(tabs, all_screens):
    """What is written for a set of ticks: the broad rights (in the app's
    own order) and then the ticks themselves."""
    rights = rights_for(tabs)
    return ",".join([s for s in all_screens if s in rights] + sorted(set(t for t in tabs if t in LEAVES)))


def tabs_of(raw, rights):
    """The ticks of a stored list: its own leaf ids, or - never ticked tab
    by tab - every tab its broad rights open."""
    _, leaves, fine = split(raw)
    return sorted(set(leaves)) if fine else from_rights(rights)


# ---- Endpoints that belong to one tab ------------------------------------
# path (as the app declares it) and method -> the tabs that may use it (any
# one is enough). A function instead of a list decides from the request:
# fn(params, body, db) -> list, or None for "no extra check".
STORE_WRITE = ["store.store.items", "store.store.arrive", "store.store.give", "store.store.other",
               "store.requests.approvals", "store.purchasing.purchase"]
REQ_ANY = ["store.requests.requests", "store.requests.approvals", "store.requests.followup"]


def _movement(params, body, db):
    kind = (body or {}).get("kind")
    return {"in": ["store.store.arrive"],
            "out": ["store.store.give"], "transfer": ["store.store.give"],
            "return": ["store.store.give", "store.store.other"],
            "lost": ["store.store.other"], "adjust": ["store.store.other"],
            "hire_return": ["store.rentals.hire", "store.store.other"]}.get(kind)


def _item_save(params, body, db):
    """Changing a material on the list is the Material list's; adding a new
    one happens wherever it is first met (a delivery, a request, an LPO)."""
    import models
    code = str((body or {}).get("code") or "").strip()
    if code and db.query(models.StoreItem).filter(models.StoreItem.code == code).first():
        return ["store.store.items"]
    return STORE_WRITE


def _store_report(params, body, db):
    kind = (params.get("kind") or "stock")
    if kind.startswith("mr_history"):
        return ["reports.storerep.mr_history"] + REQ_ANY
    if kind == "stock":
        return ["reports.storerep.stock", "store.store.home"]
    leaf = f"reports.storerep.{kind}"
    return [leaf] if leaf in LEAVES else None


def _invoice_kind(params, body, db):
    kind = (body or {}).get("kind") or params.get("kind") or "tax"
    return ["accounts.proforma"] if kind == "proforma" else ["accounts.taxinv"]


def _invoice_by_id(params, body, db):
    from accounts import Invoice
    try:
        iid = int(params.get("iid"))
    except (TypeError, ValueError):
        return None
    x = db.query(Invoice).filter(Invoice.id == iid).first()
    if not x:
        return None
    return ["accounts.proforma"] if x.kind == "proforma" else ["accounts.taxinv"]


CARDS = ["payroll.labourpay.combine", "reports.labour.cards"]
HR = lambda s: [f"payroll.hrpayroll.{s}"]   # noqa: E731

GATES = {
    # Store > Stock
    ("POST", "/store/movements"): _movement,
    ("DELETE", "/store/movements/{movement_id}"): ["store.store.give", "store.store.arrive", "store.store.other"],
    ("POST", "/store/items"): _item_save,
    ("DELETE", "/store/items/{item_id}"): ["store.store.items"],
    ("POST", "/store/items/apply-units"): ["store.store.items"],
    ("POST", "/store/items/opening"): ["store.store.items"],
    ("POST", "/store/items/opening-import"): ["store.store.items"],
    # Store > Rentals
    ("POST", "/store/hire/in"): ["store.rentals.hire"],
    ("POST", "/store/hire/reassign"): ["store.rentals.hire"],
    ("POST", "/store/returns"): ["store.rentals.returns"],
    ("PUT", "/store/returns/{return_id}"): ["store.rentals.returns"],
    ("POST", "/store/returns/{return_id}/issue"): ["store.rentals.returns"],
    ("POST", "/store/returns/{return_id}/confirm"): ["store.rentals.returns"],
    ("POST", "/store/returns/{return_id}/cancel"): ["store.rentals.returns"],
    # Store > Requests
    ("POST", "/store/requests"): ["store.requests.requests"],
    ("POST", "/store/request-lines/{line_id}/decision"): ["store.requests.approvals"],
    ("POST", "/store/requests/{req_id}/status"): ["store.requests.approvals"],
    ("DELETE", "/store/requests/{req_id}"): ["store.requests.approvals"],
    # Store > Purchasing
    ("POST", "/store/purchase/orders"): ["store.purchasing.purchase"],
    ("PUT", "/store/purchase/orders/{order_id}"): ["store.purchasing.purchase"],
    ("POST", "/store/purchase/orders/{order_id}/cancel"): ["store.purchasing.purchase"],
    ("POST", "/store/suppliers"): ["store.purchasing.suppliers", "store.purchasing.purchase", "store.store.arrive",
                                   "store.requests.approvals", "store.requests.requests", "store.store.items"],
    ("PUT", "/store/suppliers/{supplier_id}"): ["store.purchasing.suppliers"],
    ("POST", "/store/suppliers/import"): ["store.purchasing.suppliers"],
    # Reports > Store & purchasing (Stock on hand reads the stock report too)
    ("GET", "/store/report"): _store_report,
    ("GET", "/export/store/report"): _store_report,
    ("GET", "/export/store/report/view"): _store_report,
    # Payroll > Labour payroll and Reports > Labour
    ("POST", "/summaries/{month_year}/full-cycle"): ["payroll.labourpay.combine"],
    ("GET", "/export/{month_year}/excel"): CARDS, ("GET", "/export/{month_year}/pdf"): CARDS,
    ("GET", "/export/{month_year}/cards/view"): CARDS,
    ("GET", "/export/{month_year}/excel-separate"): CARDS, ("GET", "/export/{month_year}/pdf-separate"): CARDS,
    ("POST", "/reports/monthly-notes/{month_year}"): ["reports.labour.monthly"],
    ("GET", "/reports/builder-catalog"): ["reports.labour.builder"],
    ("GET", "/reports/custom"): ["reports.labour.builder"],
    ("GET", "/export/{month_year}/custom-report"): ["reports.labour.builder"],
    ("GET", "/export/{month_year}/custom-report/view"): ["reports.labour.builder"],
    # Payroll > Office payroll, section by section
    ("POST", "/employees/payroll/full-month"): HR("cycle"),
    ("POST", "/employees/payroll/runs"): HR("cycle"),
    ("PUT", "/employees/payroll/runs/{run_id}"): HR("cycle"),
    ("DELETE", "/employees/payroll/runs/{run_id}"): HR("cycle"),
    ("POST", "/employees/payroll/runs/{run_id}/approve"): HR("cycle"),
    ("POST", "/employees/payroll/runs/{run_id}/reopen"): HR("cycle"),
    ("GET", "/export/payroll/statement"): HR("cycle"), ("GET", "/export/payroll/statement/view"): HR("cycle"),
    ("GET", "/export/payroll/consolidated"): HR("cycle"), ("GET", "/export/payroll/consolidated/view"): HR("cycle"),
    ("POST", "/employees/leave"): HR("leave"),
    ("PUT", "/employees/leave/entry/{batch}"): HR("leave"),
    ("DELETE", "/employees/leave/entry/{batch}"): HR("leave"),
    ("DELETE", "/employees/leave/{leave_id}"): HR("leave"),
    ("GET", "/export/payroll/leave"): HR("leave"), ("GET", "/export/payroll/leave/view"): HR("leave"),
    ("POST", "/employees/pay-items"): HR("items"),
    ("PUT", "/employees/pay-items/{item_id}"): HR("items"),
    ("DELETE", "/employees/pay-items/{item_id}"): HR("items"),
    ("GET", "/export/payroll/items"): HR("items"), ("GET", "/export/payroll/items/view"): HR("items"),
    ("POST", "/employees/loans"): HR("loans"),
    ("POST", "/employees/loans/{loan_id}/repay"): HR("loans"),
    ("PUT", "/employees/loans/{loan_id}"): HR("loans"),
    ("DELETE", "/employees/loans/{loan_id}"): HR("loans"),
    ("PUT", "/employees/loans/repayments/{rep_id}"): HR("loans"),
    ("DELETE", "/employees/loans/repayments/{rep_id}"): HR("loans"),
    ("GET", "/export/payroll/loans"): HR("loans"), ("GET", "/export/payroll/loans/view"): HR("loans"),
    ("POST", "/employees/staff"): HR("staff"),
    ("PUT", "/employees/staff/{emp_no}"): HR("staff"),
    ("GET", "/export/payroll/staff"): HR("staff"), ("GET", "/export/payroll/staff/view"): HR("staff"),
    ("POST", "/employees/increments"): HR("increments"),
    ("PUT", "/employees/increments/{change_id}"): HR("increments"),
    ("DELETE", "/employees/increments/{change_id}"): HR("increments"),
    ("GET", "/export/payroll/increments"): HR("increments"), ("GET", "/export/payroll/increments/view"): HR("increments"),
    ("GET", "/employees/staff/{emp_no}/settlement"): HR("gratuity"),
    ("GET", "/export/payroll/settlement"): HR("gratuity"), ("GET", "/export/payroll/settlement/view"): HR("gratuity"),
    ("GET", "/export/payroll/gratuity"): HR("gratuity"), ("GET", "/export/payroll/gratuity/view"): HR("gratuity"),
    # Expiry reminder: people's documents, and the company's own
    ("GET", "/employees/documents"): ["expiry.expiry.people", "payroll.hrpayroll.staff"],
    ("POST", "/employees/documents"): ["expiry.expiry.people", "payroll.hrpayroll.staff"],
    ("DELETE", "/employees/documents/{doc_id}"): ["expiry.expiry.people", "payroll.hrpayroll.staff"],
    ("GET", "/employees/expiries"): ["expiry.expiry.company", "payroll.hrpayroll.staff"],
    ("POST", "/employees/expiries"): ["expiry.expiry.company", "payroll.hrpayroll.staff"],
    ("DELETE", "/employees/expiries/{xid}"): ["expiry.expiry.company", "payroll.hrpayroll.staff"],
    # Accounts: tax and proforma invoices
    ("GET", "/employees/accounts/invoices"): _invoice_kind,
    ("GET", "/employees/accounts/invoices/next"): _invoice_kind,
    ("POST", "/employees/accounts/invoices"): _invoice_kind,
    ("PUT", "/employees/accounts/invoices/{iid}"): _invoice_by_id,
    ("POST", "/employees/accounts/invoices/{iid}/cancel"): _invoice_by_id,
    ("POST", "/employees/accounts/invoices/{iid}/convert"): ["accounts.taxinv"],
}


def need_for(method, path, params, body, db):
    rule = GATES.get((method, path))
    if rule is None:
        return None
    return rule(params, body, db) if callable(rule) else rule


def needs_body(method, path):
    return callable(GATES.get((method, path))) and method in ("POST", "PUT")
