"""Store & purchasing part of the full live-like database (see seed_full.py).

    run(c, H)   c = an entered fastapi TestClient, H = admin auth headers

Everything goes in through the app's own endpoints, the way the staff use
them: the store keeper (Amal, login amaltest) adds materials, counts the
opening stock, raises requests, books deliveries and gives material out;
the office (Shafeeq, login chiefacc) approves or rejects and raises the
LPOs. If either login is missing the admin login is used instead.

Story, Sep-Oct 2026 (today 2026-10-22, Dubai):
  - 42 materials (cement, rebar, blocks, aggregates, timber, paint,
    chemicals, PPE, consumables, owned tools, hired scaffolding)
  - 8 suppliers with TRN / contact / phone / email / terms
  - opening stock counted into the central store on 01 Sep (and two
    items counted by hand today through Materials > Add stock)
  - 11 material requests from sites 901-910 and the store (+1 the app
    opens itself for the store-stock LPO), between them:
      delivered, part delivered, ordered, approved-not-ordered, pending,
      one with a line rejected, one rejected outright, one whose LPO was
      cancelled and re-raised with another supplier
  - 11 LPOs with 5% VAT (one corrected after issue, one cancelled, one
    raised for store stock with no request)
  - issues to sites, returns from site, transfers between sites, a tool
    written off, a count correction
  - scaffolding hired in from Skyline, sent to site, part returned on a
    signed return note (with 2 planks short), a second note in draft
Every amount is qty x rate, VAT 5%, and the script checks the app's own
figures against what it put in before it finishes.
"""

SEED_MARK = "CEM-OPC50"     # first material; if it exists the store is already seeded

# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
SUPPLIERS = [
    # key, name, contact, phone, trn, email, terms, address
    ("noor", "Al Noor Building Materials Trading LLC", "Rashid Khan", "+971 50 412 7731",
     "100234567800003", "sales@alnoorbm.ae", "30 Days Credit",
     "Warehouse 14, Al Quoz Industrial Area 3, Dubai"),
    ("hamad", "Bin Hamad Building Materials LLC", "Suresh Menon", "+971 55 238 9014",
     "100318845200003", "orders@binhamadbm.ae", "45 Days Credit",
     "Plot 597-112, Ras Al Khor Industrial 2, Dubai"),
    ("rebar", "Gulf Rebar Steel Trading LLC", "Imran Siddiqui", "+971 52 671 4402",
     "100457712900003", "imran@gulfrebar.ae", "30 Days PDC",
     "Shed 7, Jebel Ali Industrial Area 1, Dubai"),
    ("qudra", "Al Qudra Block Factory LLC", "Mohammed Saleem", "+971 50 993 2157",
     "100562390100003", "dispatch@alqudrablocks.ae", "Cash on Delivery",
     "Al Qudra Road, Dubai Industrial City, Dubai"),
    ("falcon", "Falcon Timber & Plywood Trading LLC", "Joseph Mathew", "+971 56 104 8823",
     "100689124500003", "joseph@falcontimber.ae", "30 Days Credit",
     "Warehouse 3, Al Khabaisi, Deira, Dubai"),
    ("paints", "Desert Paints Trading LLC", "Anil Kumar", "+971 54 552 6619",
     "100734581200003", "anil@desertpaints.ae", "60 Days Credit",
     "Shop 9, Al Qusais Industrial Area 4, Dubai"),
    ("safe", "SafeGuard Safety & Tools Trading LLC", "Faisal Ahmed", "+971 50 318 4470",
     "100812673400003", "sales@safeguardtools.ae", "Due on Receipt",
     "Shop 22, Naif Road, Deira, Dubai"),
    ("sky", "Skyline Scaffolding Rental LLC", "Ramesh Pillai", "+971 55 760 3381",
     "100945218700003", "rental@skylinescaffold.ae", "Monthly Invoice - 30 Days",
     "Yard 11, Al Jaddaf, Dubai"),
]

# code, name, category, unit, type, reorder, est_price, opening (01 Sep, central)
ITEMS = [
    ("CEM-OPC50", "Cement OPC 50kg", "Cement", "bag", "consumable", 100, 17.50, 320),
    ("CEM-SRC50", "Cement SRC 50kg", "Cement", "bag", "consumable", 50, 19.00, 120),
    ("CEM-WHT25", "White Cement 25kg", "Cement", "bag", "consumable", 5, 32.00, 20),
    ("STL-T10", "Rebar 10mm (T10)", "Steel", "t", "consumable", 1, 2650.00, 2.5),
    ("STL-T12", "Rebar 12mm (T12)", "Steel", "t", "consumable", 1, 2620.00, 4),
    ("STL-T16", "Rebar 16mm (T16)", "Steel", "t", "consumable", 1, 2600.00, 3),
    ("STL-BW", "Binding Wire 1.2mm", "Steel", "kg", "consumable", 50, 6.50, 180),
    ("BLK-H15", "Hollow Block 15cm", "Blocks", "pcs", "consumable", 300, 2.85, 1500),
    ("BLK-H20", "Hollow Block 20cm", "Blocks", "pcs", "consumable", 300, 3.40, 1200),
    ("BLK-S10", "Solid Block 10cm", "Blocks", "pcs", "consumable", 200, 2.40, 600),
    ("AGG-WSD", "Washed Sand", "Aggregates", "m3", "consumable", 5, 95.00, 18),
    ("AGG-DSD", "Dune Sand", "Aggregates", "m3", "consumable", 5, 55.00, 12),
    ("AGG-20", "Aggregate 20mm", "Aggregates", "m3", "consumable", 4, 110.00, 10),
    ("PLY-18", "Plywood 18mm Shuttering", "Timber", "sheet", "consumable", 40, 48.00, 140),
    ("PLY-12", "Plywood 12mm", "Timber", "sheet", "consumable", 20, 36.00, 60),
    ("TMB-2X4", "Timber 2x4 Inch 4.8m", "Timber", "pcs", "consumable", 50, 22.00, 200),
    ("NAIL-3", "Nails 3 Inch", "Fixings", "kg", "consumable", 20, 5.50, 75),
    ("PNT-EMW", "Emulsion Paint White 18L", "Paint", "pail", "consumable", 4, 145.00, 12),
    ("PNT-PRS", "Primer Sealer 18L", "Paint", "pail", "consumable", 3, 120.00, 8),
    ("PNT-THN", "Paint Thinner", "Paint", "L", "consumable", 10, 9.00, 40),
    ("WPF-BIT", "Bitumen Primer 20L", "Chemicals", "drum", "consumable", 2, 165.00, 6),
    ("CHM-CUR", "Curing Compound 20L", "Chemicals", "drum", "consumable", 2, 140.00, 5),
    ("PPE-HLM", "Safety Helmet", "PPE", "pcs", "consumable", 20, 12.00, 60),
    ("PPE-GLV", "Cotton Gloves", "PPE", "pair", "consumable", 100, 2.50, 300),
    ("PPE-VST", "Reflective Safety Vest", "PPE", "pcs", "consumable", 20, 8.00, 80),
    ("PPE-SHO", "Safety Shoes", "PPE", "pair", "consumable", 10, 65.00, 35),
    ("PPE-GOG", "Safety Goggles", "PPE", "pcs", "consumable", 15, 7.00, 50),
    ("PPE-MSK", "Dust Mask N95 (20/Box)", "PPE", "box", "consumable", 5, 45.00, 15),
    ("PPE-EAR", "Ear Plugs (200/Box)", "PPE", "box", "consumable", 2, 30.00, 0),   # counted today
    ("CON-TAP", "Barricade Tape", "Consumables", "roll", "consumable", 10, 18.00, 25),
    ("CON-POL", "Polythene Sheet 1000g", "Consumables", "roll", "consumable", 3, 210.00, 8),
    ("CON-DSC", "Cutting Disc 4.5 Inch", "Consumables", "pcs", "consumable", 50, 4.50, 150),
    ("TL-DRL", "Hammer Drill SDS 800W", "Tools", "pcs", "asset", 0, 650.00, 6),
    ("TL-GRD", "Angle Grinder 4.5 Inch", "Tools", "pcs", "asset", 0, 280.00, 8),
    ("TL-MIX", "Concrete Mixer 1 Bag", "Tools", "pcs", "asset", 0, 3200.00, 2),
    ("TL-VIB", "Concrete Vibrator", "Tools", "pcs", "asset", 0, 1450.00, 3),
    ("TL-LSR", "Laser Level", "Tools", "pcs", "asset", 0, 950.00, 2),
    ("TL-WBR", "Wheelbarrow", "Tools", "pcs", "asset", 0, 165.00, 15),
    ("TL-LAD", "Aluminium Ladder 8 Step", "Tools", "pcs", "asset", 0, 320.00, 0),       # counted today
    # Hired, not bought - rate per day goes on the material.
    ("RN-SCF", "Scaffolding Frame 1.7m", "Scaffolding", "pcs", "rental", 0, None, 0),
    ("RN-PLK", "Scaffolding Steel Plank", "Scaffolding", "pcs", "rental", 0, None, 0),
    ("RN-BJK", "Scaffolding Base Jack", "Scaffolding", "pcs", "rental", 0, None, 0),
]
RENTAL_RATES = {"RN-SCF": 1.50, "RN-PLK": 0.75, "RN-BJK": 0.30}
COUNTED_TODAY = {"PPE-EAR": 12, "TL-LAD": 6}       # through /store/items/opening

ENGINEER_MOBILE = {"Gopan": "+971 50 771 2045", "Harsha": "+971 52 330 8812",
                   "John Joseph": "+971 55 914 6630", "Amal": "+971 56 228 4419"}


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------
class SeedError(RuntimeError):
    pass


def _r2(x):
    return round(x + 1e-9, 2)


def run(c, H):
    def call(method, url, H_=None, ok=(200,), **kw):
        r = c.request(method, url, headers=H_ or H, **kw)
        if r.status_code not in ok:
            body = r.text[:800]
            print(f"!! {method} {url} -> {r.status_code}: {body}")
            raise SeedError(f"{method} {url} -> {r.status_code}: {body}")
        try:
            return r.json()
        except Exception:
            return r.text

    def login(un, pw):
        r = c.post("/auth/login", data={"username": un, "password": pw})
        if r.status_code == 200 and "access_token" in r.json():
            return {"Authorization": "Bearer " + r.json()["access_token"]}
        print(f"   (login {un} unavailable - using admin)")
        return H

    # Already seeded? (idempotent enough for one run on a fresh DB)
    existing = call("GET", "/store/items", params={"active_only": False})
    if any(i["code"] == SEED_MARK for i in existing):
        print("store already seeded - nothing done")
        return

    KEEPER = login("amaltest", "amal12345")      # store keeper
    OFFICE = login("chiefacc", "chief12345")     # approvals / purchasing

    sites = {s["code"] for s in call("GET", "/sites")}
    for need in ("901", "902", "903", "904", "905", "906", "907", "908", "909", "910"):
        if need not in sites:
            raise SeedError(f"site {need} missing - run the base seed first")

    # ------------------------------------------------------------------ suppliers
    SUP = {}
    for key, name, contact, phone, trn, email, terms, addr in SUPPLIERS:
        out = call("POST", "/store/suppliers", H_=OFFICE, json={
            "name": name, "contact_person": contact, "phone": phone, "trn": trn,
            "email": email, "payment_terms": terms, "address": addr,
            "notes": "Approved vendor"})
        SUP[key] = {"id": out["id"], "name": out["name"], "contact": contact, "phone": phone,
                    "trn": trn, "email": email, "terms": terms, "address": addr}

    # ------------------------------------------------------------------ materials
    IT = {}
    for code, name, cat, unit, typ, reorder, price, _open in ITEMS:
        body = {"code": code, "name": name, "category": cat, "unit": unit, "item_type": typ,
                "reorder_level": reorder, "notes": ""}
        if price is not None:
            body["est_price"] = price
        if typ == "rental":
            body.update({"rental_supplier": SUP["sky"]["name"], "rental_rate": RENTAL_RATES[code],
                         "rental_period": "day"})
        out = call("POST", "/store/items", H_=KEEPER, json=body)
        IT[code] = {"id": out["id"], "unit": out["unit"], "name": out["name"], "type": out["item_type"]}

    # Expected ledger, kept beside the real one for the checks at the end.
    # central[code] = qty in the central store; site[(code, site)] for assets/rentals.
    central = {code: 0.0 for code in IT}
    at_site = {}
    received_total = {code: 0.0 for code in IT}     # all receipts anywhere
    counts = {"movements": 0}

    def site_add(code, where, q):
        at_site[(code, where)] = at_site.get((code, where), 0) + q

    # Opening stock - counted into the central store on the day the store went live.
    for code, *_rest, opening in ITEMS:
        if opening:
            call("POST", "/store/movements", H_=KEEPER, json={
                "item_id": IT[code]["id"], "kind": "in", "qty": opening, "from_location": "",
                "location": "", "incharge": "Amal", "reference": "Opening stock",
                "notes": "Opening count 01-Sep-2026", "moved_on": "2026-09-01"})
            central[code] += opening
            received_total[code] += opening
            counts["movements"] += 1
    # Two found on the shelf later, put in by hand (this endpoint dates them today).
    call("POST", "/store/items/opening", H_=KEEPER, json={
        "location": "",
        "lines": [{"item_id": IT[c_]["id"], "qty": q} for c_, q in COUNTED_TODAY.items()]})
    for c_, q in COUNTED_TODAY.items():
        central[c_] += q
        received_total[c_] += q

    # ------------------------------------------------------------------ helpers
    def move(kind, code, qty, on, frm="", to="", incharge="Amal", ref="", notes="", owner_id=None):
        body = {"item_id": IT[code]["id"], "kind": kind, "qty": qty, "from_location": frm,
                "location": to, "incharge": incharge, "reference": ref, "notes": notes,
                "moved_on": on}
        if owner_id is not None:
            body["owner_id"] = owner_id
        call("POST", "/store/movements", H_=KEEPER, json=body)
        counts["movements"] += 1
        held = IT[code]["type"] in ("asset", "rental")
        if kind == "out":
            central[code] -= qty
            if held:
                site_add(code, to, qty)
        elif kind == "return":
            central[code] += qty
            if held:
                site_add(code, frm, -qty)
        elif kind == "transfer":
            if held:
                site_add(code, frm, -qty)
                site_add(code, to, qty)
        elif kind == "lost":
            if frm == "":
                central[code] -= qty
            elif held:
                site_add(code, frm, -qty)
        elif kind == "adjust":
            if to == "":
                central[code] += qty
        elif kind == "in":
            if to == "":
                central[code] += qty
            elif held:
                site_add(code, to, qty)
            received_total[code] += qty

    REQ = {}          # name -> {"id", "ref", "lines": {code: line_id}, "site", "qty": {code: q}}

    def request(name, site, by, on, needed, lines, urgency="normal", notes=""):
        out = call("POST", "/store/requests", H_=KEEPER, json={
            "site": site, "requested_by": by, "requested_on": on, "needed_by": needed,
            "urgency": urgency, "notes": notes,
            "lines": [{"item_id": IT[code]["id"], "qty_requested": q, "unit": IT[code]["unit"],
                       "purpose": purpose, "item_type": IT[code]["type"]}
                      for code, q, purpose in lines]})
        if out.get("duplicate_of"):
            raise SeedError(f"request {name} came back as a duplicate of {out['duplicate_of']}")
        ids = {}
        for ln in out["lines"]:
            code = next(k for k, v in IT.items() if v["id"] == ln["item_id"])
            ids[code] = ln["id"]
        REQ[name] = {"id": out["id"], "ref": out["ref"], "lines": ids, "site": site, "by": by,
                     "qty": {code: q for code, q, _ in lines}}
        return REQ[name]

    def decide(name, code, decision, reason=""):
        return call("POST", f"/store/request-lines/{REQ[name]['lines'][code]}/decision", H_=OFFICE,
                    json={"decision": decision, "reason": reason})

    LPO = {}          # name -> {"id", "ref", "lines": [(code, qty, rate)], "status"}

    def lpo(name, sup, on, delivery, lines, req=None, job="", quote="", notes="", site=None):
        s = SUP[sup]
        r = REQ[req] if req else None
        loc = site or (r["site"] if r else "STORE")
        by = r["by"] if r else "Amal"
        body = {
            "order_date": on, "delivery_date": delivery, "terms": s["terms"],
            "supplier_ref": quote, "supplier_name": s["name"], "supplier_address": s["address"],
            "supplier_trn": s["trn"], "supplier_email": s["email"],
            "supplier_contact": s["contact"], "supplier_phone": s["phone"],
            "request_id": r["id"] if r else None,
            "contact_person": by, "mobile": ENGINEER_MOBILE.get(by, ""),
            "email": "purchase@infinia.ae", "job_scope": job,
            "project_location": "Central store" if loc == "STORE" else loc,
            "discount_pct": 0, "notes": notes,
            "request_line_ids": [r["lines"][code] for code, _q, _rt in lines] if r else [],
            "lines": [{"item_id": IT[code]["id"], "description": IT[code]["name"], "qty": q,
                       "unit": IT[code]["unit"], "rate": rt, "tax_pct": 5.0}
                      for code, q, rt in lines]}
        out = call("POST", "/store/purchase/orders", H_=OFFICE, json=body)
        LPO[name] = {"id": out["id"], "ref": out["ref"], "lines": list(lines), "status": "issued",
                     "body": body, "request_id": out["request_id"]}
        return out

    def receive(name, on, lines, ref, deliver_to=None, notes=""):
        r = REQ[name]
        body = {"lines": [{"line_id": r["lines"][code], "qty": q} for code, q in lines],
                "reference": ref, "received_on": on, "notes": notes}
        if deliver_to is not None:
            body["deliver_to"] = deliver_to
        out = call("POST", f"/store/requests/{r['id']}/receive-bulk", H_=KEEPER, json=body)
        if out.get("warnings"):
            raise SeedError(f"receive {name}: {out['warnings']}")
        where = r["site"] if deliver_to is None else deliver_to
        if where.upper() == "STORE":
            where = ""
        for code, q in lines:
            received_total[code] += q
            if where == "":
                central[code] += q
            elif IT[code]["type"] in ("asset", "rental"):
                site_add(code, where, q)
        return out

    # ------------------------------------------------------------------ September
    # Issues from the opening stock to sites already running.
    move("out", "CEM-OPC50", 40, "2026-09-02", to="901", incharge="Gopan", ref="GP-0901", notes="Blockwork ground floor")
    move("out", "PLY-18", 30, "2026-09-02", to="902", incharge="Gopan", ref="GP-0902", notes="Slab shuttering")
    move("out", "BLK-H15", 400, "2026-09-02", to="902", incharge="Gopan", ref="GP-0903", notes="Partition walls")
    move("out", "PPE-GLV", 60, "2026-09-02", to="901", incharge="Gopan", ref="GP-0904", notes="Labour issue")
    move("out", "PPE-HLM", 10, "2026-09-03", to="903", incharge="Harsha", ref="GP-0905", notes="New labour batch")
    move("out", "TL-DRL", 2, "2026-09-04", to="901", incharge="Gopan", ref="GP-0906", notes="MEP chasing")
    move("out", "TL-GRD", 2, "2026-09-04", to="903", incharge="Harsha", ref="GP-0907", notes="Rebar cutting")
    move("out", "TL-MIX", 1, "2026-09-05", to="902", incharge="Gopan", ref="GP-0908", notes="Plaster works")
    move("out", "TL-VIB", 1, "2026-09-05", to="904", incharge="John Joseph", ref="GP-0909", notes="Column casting")
    move("out", "TL-WBR", 4, "2026-09-05", to="903", incharge="Harsha", ref="GP-0910", notes="Site handling")
    move("out", "TL-LSR", 1, "2026-09-07", to="905", incharge="Gopan", ref="GP-0911", notes="Setting out")

    # MR1 - 901 structure: cement + rebar + wire, split over two suppliers, delivered.
    request("MR1", "901", "Gopan", "2026-09-03", "2026-09-07", [
        ("CEM-OPC50", 80, "First floor slab"), ("STL-T12", 1.5, "First floor slab"),
        ("STL-BW", 40, "First floor slab")])
    call("POST", f"/store/requests/{REQ['MR1']['id']}/status", H_=OFFICE,
         json={"status": "approved", "office_remark": "Approved - order today"})
    lpo("LPO1", "noor", "2026-09-04", "2026-09-06", [("CEM-OPC50", 80, 17.50)], req="MR1",
        job="Structure - first floor slab", quote="ANB/Q/2291")
    lpo("LPO2", "rebar", "2026-09-04", "2026-09-06", [("STL-T12", 1.5, 2620.00), ("STL-BW", 40, 6.50)],
        req="MR1", job="Structure - first floor slab", quote="GRS-5512")
    receive("MR1", "2026-09-06", [("CEM-OPC50", 80)], "DN-AN-77120")
    receive("MR1", "2026-09-06", [("STL-T12", 1.5), ("STL-BW", 40)], "DN-GR-30418")

    # MR2 - 903 blockwork: timber rejected, rest ordered from two suppliers, delivered.
    request("MR2", "903", "Harsha", "2026-09-08", "2026-09-11", [
        ("BLK-H20", 1000, "External walls"), ("AGG-WSD", 6, "Mortar"),
        ("PLY-18", 40, "Lintel shuttering"), ("TMB-2X4", 60, "Lintel shuttering")])
    decide("MR2", "BLK-H20", "approved")
    decide("MR2", "AGG-WSD", "approved")
    decide("MR2", "PLY-18", "approved")
    decide("MR2", "TMB-2X4", "rejected", "Enough timber in store - collect from central store")
    lpo("LPO3", "noor", "2026-09-09", "2026-09-11", [("BLK-H20", 1000, 3.40), ("AGG-WSD", 6, 95.00)],
        req="MR2", job="Blockwork - external walls", quote="ANB/Q/2307")
    lpo("LPO4", "falcon", "2026-09-09", "2026-09-11", [("PLY-18", 40, 48.00)],
        req="MR2", job="Blockwork - lintels", quote="FTP-1180")
    receive("MR2", "2026-09-11", [("BLK-H20", 1000), ("AGG-WSD", 6)], "DN-AN-77245")
    receive("MR2", "2026-09-12", [("PLY-18", 40)], "DN-FT-4410")
    # ...and the rejected timber is collected from the store instead.
    move("out", "TMB-2X4", 60, "2026-09-12", to="903", incharge="Harsha", ref="GP-0912",
         notes="In place of rejected line on " + REQ["MR2"]["ref"])

    # MR3 - 904 rebar: ordered, only part delivered.
    request("MR3", "904", "John Joseph", "2026-09-15", "2026-09-18", [
        ("STL-T16", 3, "Raft foundation"), ("STL-T10", 1, "Raft foundation"),
        ("STL-BW", 60, "Raft foundation")], urgency="urgent")
    call("POST", f"/store/requests/{REQ['MR3']['id']}/status", H_=OFFICE, json={"status": "approved"})
    lpo("LPO5", "rebar", "2026-09-16", "2026-09-18",
        [("STL-T16", 3, 2600.00), ("STL-T10", 1, 2650.00), ("STL-BW", 60, 6.50)],
        req="MR3", job="Substructure - raft", quote="GRS-5580")
    receive("MR3", "2026-09-20", [("STL-T16", 2), ("STL-BW", 60)], "DN-GR-30561",
            notes="Balance T16 and all T10 to follow")

    # Returns and transfers in the middle of the month.
    move("return", "CEM-OPC50", 5, "2026-09-20", frm="901", incharge="Gopan", ref="RT-0901",
         notes="Unused bags back to store")
    move("out", "PNT-THN", 10, "2026-09-21", to="905", incharge="Gopan", ref="GP-0913", notes="Cleaning")

    # MR4 - 905 painting: delivered; LPO rate corrected after issue.
    request("MR4", "905", "Gopan", "2026-09-22", "2026-09-25", [
        ("PNT-EMW", 10, "Internal painting"), ("PNT-PRS", 6, "Internal painting"),
        ("PNT-THN", 20, "Internal painting")])
    call("POST", f"/store/requests/{REQ['MR4']['id']}/status", H_=OFFICE, json={"status": "approved"})
    lpo("LPO6", "paints", "2026-09-23", "2026-09-25",
        [("PNT-EMW", 10, 150.00), ("PNT-PRS", 6, 120.00), ("PNT-THN", 20, 9.00)],
        req="MR4", job="Finishes - internal painting", quote="DP-QT-0934")
    # Supplier's quote said 145 for the emulsion - the officer corrects the LPO.
    corrected = dict(LPO["LPO6"]["body"])
    corrected["ref"] = LPO["LPO6"]["ref"]
    corrected["lines"] = [dict(l) for l in corrected["lines"]]
    corrected["lines"][0]["rate"] = 145.00
    corrected["notes"] = "Emulsion rate corrected to quotation DP-QT-0934"
    call("PUT", f"/store/purchase/orders/{LPO['LPO6']['id']}", H_=OFFICE, json=corrected)
    LPO["LPO6"]["lines"] = [("PNT-EMW", 10, 145.00), ("PNT-PRS", 6, 120.00), ("PNT-THN", 20, 9.00)]
    receive("MR4", "2026-09-26", [("PNT-EMW", 10), ("PNT-PRS", 6), ("PNT-THN", 20)], "DN-DP-11872")

    # Scaffolding hired from Skyline into the yard, then sent to 903.
    call("POST", "/store/hire/in", H_=KEEPER, json={
        "supplier_name": SUP["sky"]["name"], "received_on": "2026-09-10", "location": "",
        "incharge": "Amal", "reference": "SKY-DN-4471", "notes": "Hire per day as quotation SKY-Q-118",
        "lines": [{"item_id": IT["RN-SCF"]["id"], "qty": 120}, {"item_id": IT["RN-PLK"]["id"], "qty": 80},
                  {"item_id": IT["RN-BJK"]["id"], "qty": 60}]})
    for code, q in (("RN-SCF", 120), ("RN-PLK", 80), ("RN-BJK", 60)):
        central[code] += q
        received_total[code] += q
    sky = SUP["sky"]["id"]
    move("out", "RN-SCF", 80, "2026-09-11", to="903", incharge="Harsha", ref="GP-0914", notes="Facade scaffold", owner_id=sky)
    move("out", "RN-PLK", 50, "2026-09-11", to="903", incharge="Harsha", ref="GP-0914", notes="Facade scaffold", owner_id=sky)
    move("out", "RN-BJK", 40, "2026-09-11", to="903", incharge="Harsha", ref="GP-0914", notes="Facade scaffold", owner_id=sky)
    move("transfer", "RN-SCF", 20, "2026-09-28", frm="903", to="904", incharge="John Joseph",
         ref="TR-0901", notes="Lift shaft scaffold", owner_id=sky)

    # ------------------------------------------------------------------ October
    # MR5 - 906: LPO to Al Noor cancelled (rate), re-raised with Bin Hamad, part delivered.
    request("MR5", "906", "Harsha", "2026-10-01", "2026-10-05", [
        ("CEM-SRC50", 60, "Footings - sulphate exposure"), ("AGG-20", 8, "Footings")])
    call("POST", f"/store/requests/{REQ['MR5']['id']}/status", H_=OFFICE, json={"status": "approved"})
    lpo("LPO7", "noor", "2026-10-02", "2026-10-05", [("CEM-SRC50", 60, 21.00), ("AGG-20", 8, 118.00)],
        req="MR5", job="Substructure - footings", quote="ANB/Q/2388")
    call("POST", f"/store/purchase/orders/{LPO['LPO7']['id']}/cancel", H_=OFFICE)
    LPO["LPO7"]["status"] = "cancelled"
    lpo("LPO8", "hamad", "2026-10-04", "2026-10-07", [("CEM-SRC50", 60, 19.00), ("AGG-20", 8, 110.00)],
        req="MR5", job="Substructure - footings", quote="BH-2026-771",
        notes="Replaces cancelled " + LPO["LPO7"]["ref"] + " (better rate)")
    receive("MR5", "2026-10-08", [("CEM-SRC50", 60), ("AGG-20", 4)], "DN-BH-90314",
            notes="Aggregate balance next trip")

    move("return", "TL-DRL", 1, "2026-10-05", frm="901", incharge="Gopan", ref="RT-1001", notes="Not needed at site")
    move("out", "CEM-OPC50", 60, "2026-10-05", to="905", incharge="Gopan", ref="GP-1001", notes="Plastering")
    move("transfer", "TL-MIX", 1, "2026-10-03", frm="902", to="906", incharge="Harsha", ref="TR-1001", notes="Footing concrete")
    move("out", "STL-BW", 30, "2026-10-06", to="906", incharge="Harsha", ref="GP-1002", notes="Footing cages")

    # MR6 - store top-up of PPE, delivered into the central store.
    request("MR6", "STORE", "Amal", "2026-10-06", "2026-10-10", [
        ("PPE-HLM", 40, "Store stock"), ("PPE-GLV", 300, "Store stock"), ("PPE-VST", 50, "Store stock"),
        ("PPE-GOG", 40, "Store stock"), ("PPE-MSK", 10, "Store stock")])
    call("POST", f"/store/requests/{REQ['MR6']['id']}/status", H_=OFFICE, json={"status": "approved"})
    lpo("LPO9", "safe", "2026-10-07", "2026-10-10",
        [("PPE-HLM", 40, 12.00), ("PPE-GLV", 300, 2.50), ("PPE-VST", 50, 8.00),
         ("PPE-GOG", 40, 7.00), ("PPE-MSK", 10, 45.00)],
        req="MR6", job="PPE stock", quote="SG-Q-6620")
    receive("MR6", "2026-10-11", [("PPE-HLM", 40), ("PPE-GLV", 300), ("PPE-VST", 50),
                                   ("PPE-GOG", 40), ("PPE-MSK", 10)], "DN-SG-20871")

    # LPO10 - blocks for the store, raised on its own (the app opens a STORE request for it).
    out = lpo("LPO10", "qudra", "2026-10-09", "2026-10-12",
              [("BLK-H15", 2000, 2.80), ("BLK-S10", 1000, 2.35)],
              job="Block stock for store", quote="AQB-4471")
    auto_req = out["request_id"]
    if not auto_req:
        raise SeedError("standalone LPO did not open a store request")
    auto = call("GET", f"/store/requests/{auto_req}/summary", H_=OFFICE)
    full = [m for m in call("GET", "/store/requests", H_=OFFICE) if m["id"] == auto_req][0]
    REQ["MR-AUTO"] = {"id": auto_req, "ref": auto["ref"], "site": "STORE", "by": auto["requested_by"],
                      "lines": {next(k for k, v in IT.items() if v["id"] == ln["item_id"]): ln["id"]
                                for ln in full["lines"]},
                      "qty": {"BLK-H15": 2000, "BLK-S10": 1000}}
    receive("MR-AUTO", "2026-10-13", [("BLK-H15", 2000), ("BLK-S10", 1000)], "DN-AQ-55190")

    # MR7 - 907 rejected outright, line by line.
    request("MR7", "907", "John Joseph", "2026-10-12", "2026-10-15", [
        ("BLK-H15", 800, "Boundary wall"), ("CEM-OPC50", 50, "Boundary wall")])
    decide("MR7", "BLK-H15", "rejected", "Site on hold - client payment pending")
    decide("MR7", "CEM-OPC50", "rejected", "Site on hold - client payment pending")

    # Issues from the fresh PPE and blocks.
    move("out", "PPE-HLM", 20, "2026-10-13", to="908", incharge="Gopan", ref="GP-1003", notes="New labour batch")
    move("out", "PPE-VST", 20, "2026-10-13", to="909", incharge="Harsha", ref="GP-1004", notes="New labour batch")
    move("out", "BLK-H15", 900, "2026-10-14", to="902", incharge="Gopan", ref="GP-1005", notes="Partition walls - 1st floor")
    move("out", "CON-DSC", 40, "2026-10-14", to="904", incharge="John Joseph", ref="GP-1006", notes="Rebar cutting")
    move("out", "TL-GRD", 1, "2026-10-15", to="907", incharge="John Joseph", ref="GP-1007", notes="Boundary wall repairs")
    move("transfer", "TL-GRD", 1, "2026-10-15", frm="903", to="907", incharge="John Joseph", ref="TR-1002", notes="Second grinder")
    move("lost", "TL-GRD", 1, "2026-10-16", frm="903", incharge="Harsha", ref="WO-1001", notes="Damaged - motor burnt out")
    move("return", "TL-WBR", 1, "2026-10-10", frm="903", incharge="Harsha", ref="RT-1002", notes="Wheel broken - for repair")

    # MR8 - 908 approved, waiting for an order.
    request("MR8", "908", "Gopan", "2026-10-14", "2026-10-20", [
        ("PLY-12", 30, "Formwork"), ("NAIL-3", 25, "Formwork"), ("CON-POL", 4, "Curing cover")])
    call("POST", f"/store/requests/{REQ['MR8']['id']}/status", H_=OFFICE,
         json={"status": "approved", "office_remark": "Approved - get two quotes for plywood"})

    # MR11 - 902 rebar ordered, not yet delivered.
    request("MR11", "902", "Gopan", "2026-10-15", "2026-10-21", [
        ("STL-T12", 2, "First floor columns"), ("STL-BW", 50, "First floor columns")])
    call("POST", f"/store/requests/{REQ['MR11']['id']}/status", H_=OFFICE, json={"status": "approved"})
    lpo("LPO11", "rebar", "2026-10-16", "2026-10-23", [("STL-T12", 2, 2580.00), ("STL-BW", 50, 6.50)],
        req="MR11", job="Superstructure - columns", quote="GRS-5719")

    # Scaffolding part returned on a signed note, 2 planks short.
    rn1 = call("POST", "/store/returns", H_=KEEPER, json={
        "supplier_id": sky, "return_date": "2026-10-18", "from_location": "903",
        "driver": "Shahid", "vehicle": "Dubai L 48213", "notes": "Facade scaffold dismantled",
        "lines": [{"item_id": IT["RN-SCF"]["id"], "qty_returned": 40},
                  {"item_id": IT["RN-PLK"]["id"], "qty_returned": 30, "qty_short": 2,
                   "short_reason": "damaged", "notes": "Bent planks, kept for charge"}]})
    call("POST", f"/store/returns/{rn1['id']}/issue", H_=KEEPER)
    call("POST", f"/store/returns/{rn1['id']}/confirm", H_=KEEPER, json={
        "received_by": "Ramesh Pillai", "confirmed_on": "2026-10-20", "notes": "Signed copy received"})
    site_add("RN-SCF", "903", -40)
    site_add("RN-PLK", "903", -32)
    rn2 = call("POST", "/store/returns", H_=KEEPER, json={
        "supplier_id": sky, "return_date": "2026-10-22", "from_location": "",
        "driver": "Shahid", "vehicle": "Dubai L 48213", "notes": "Spare base jacks from yard",
        "lines": [{"item_id": IT["RN-BJK"]["id"], "qty_returned": 20}]})

    # MR9, MR10 - fresh, still waiting on the office.
    request("MR9", "909", "Harsha", "2026-10-19", "2026-10-24", [
        ("CEM-OPC50", 100, "Blockwork ground floor"), ("BLK-H20", 1500, "Blockwork ground floor"),
        ("AGG-WSD", 10, "Mortar")])
    request("MR10", "910", "John Joseph", "2026-10-21", "2026-10-22", [
        ("CHM-CUR", 4, "Slab curing"), ("CON-TAP", 10, "Edge protection")], urgency="urgent",
        notes="Slab pour on 22nd - please arrange today")

    # A count correction in the store: 20 pairs of gloves short.
    move("adjust", "PPE-GLV", -20, "2026-10-20", incharge="Amal", ref="COUNT-1020",
         notes="Monthly count - 20 pairs short")

    # ------------------------------------------------------------------ checks
    problems = []

    def check(cond, msg):
        if not cond:
            problems.append(msg)
            print("   MISMATCH:", msg)

    stock = {r["code"]: r for r in call("GET", "/store/stock", H_=KEEPER)}
    for code in IT:
        row = stock.get(code)
        check(row is not None, f"{code} missing from /store/stock")
        if not row:
            continue
        check(abs(row["central"] - central[code]) < 1e-6,
              f"{code} central {row['central']} != expected {_r2(central[code])}")
        if IT[code]["type"] in ("asset", "rental"):
            want_sites = {s: _r2(q) for (c_, s), q in at_site.items() if c_ == code and abs(q) > 1e-9}
            got_sites = {k: v for k, v in row["by_site"].items() if abs(v) > 1e-9}
            check(got_sites == want_sites, f"{code} by_site {got_sites} != expected {want_sites}")

    # Request statuses
    want_status = {"MR1": "delivered", "MR2": "delivered", "MR3": "partial", "MR4": "delivered",
                   "MR5": "partial", "MR6": "delivered", "MR-AUTO": "delivered", "MR7": "rejected",
                   "MR8": "approved", "MR9": "pending", "MR10": "pending", "MR11": "ordered"}
    reqs = {m["id"]: m for m in call("GET", "/store/requests", H_=OFFICE)}
    for name, st in want_status.items():
        got = reqs[REQ[name]["id"]]["status"]
        check(got == st, f"{name} {REQ[name]['ref']} status {got} != {st}")

    # LPO totals: register and report against qty x rate + 5%
    reg = {o["id"]: o for o in call("GET", "/store/purchase/orders", H_=OFFICE)}
    issued_sub = issued_vat = 0.0
    for name, o in LPO.items():
        sub = sum(q * rt for _c, q, rt in o["lines"])
        vat = sub * 0.05
        tot = _r2(sub + vat)
        o["sub"], o["vat"], o["total"] = _r2(sub), _r2(vat), tot
        got = reg[o["id"]]
        check(abs(got["total"] - tot) < 0.006, f"{name} {o['ref']} register total {got['total']} != {tot}")
        check(got["status"] == o["status"], f"{name} status {got['status']} != {o['status']}")
        if o["status"] == "issued":
            issued_sub += sub
            issued_vat += vat
    rep = call("GET", "/store/purchase/report", H_=OFFICE,
               params={"group_by": "order", "measures": "orders,sub_total,vat,total"})
    check(abs(rep["totals"]["sub_total"] - _r2(issued_sub)) < 0.011,
          f"purchase report sub_total {rep['totals']['sub_total']} != {_r2(issued_sub)}")
    check(abs(rep["totals"]["vat"] - _r2(issued_vat)) < 0.011,
          f"purchase report VAT {rep['totals']['vat']} != {_r2(issued_vat)}")
    check(rep["totals"]["orders"] == sum(1 for o in LPO.values() if o["status"] == "issued"),
          f"purchase report counts {rep['totals']['orders']} orders")

    hire = call("GET", "/store/hire", H_=KEEPER)
    on_hire = {i["code"]: i["qty"] for g in hire["suppliers"] for i in g["items"]}
    for code in ("RN-SCF", "RN-PLK", "RN-BJK"):
        want = _r2(central[code] + sum(q for (c_, _s), q in at_site.items() if c_ == code))
        check(abs(on_hire.get(code, 0) - want) < 1e-6, f"{code} on hire {on_hire.get(code)} != {want}")

    # ------------------------------------------------------------------ summary
    n_lines = sum(len(o["lines"]) for o in LPO.values())
    print(f"store: {len(SUP)} suppliers, {len(IT)} materials, {counts['movements']} stock movements "
          f"(+ hire-in, 1 confirmed return note {rn1['ref']}, 1 draft {rn2['ref']})")
    print(f"requests: {len(REQ)} - " + ", ".join(f"{REQ[n]['ref']} {reqs[REQ[n]['id']]['status']}"
                                                  for n in REQ))
    print(f"LPOs: {len(LPO)} ({n_lines} lines) - issued sub-total AED {issued_sub:,.2f} + VAT "
          f"{issued_vat:,.2f} = {issued_sub + issued_vat:,.2f}; cancelled {LPO['LPO7']['ref']}")
    for name, o in LPO.items():
        print(f"   {o['ref']:<16} {o['status']:<9} {o['sub']:>11,.2f} + {o['vat']:>9,.2f} = {o['total']:>11,.2f}")
    if problems:
        raise SeedError(f"{len(problems)} figure(s) did not come out as intended: " + "; ".join(problems))
    print("store seed OK - all stock, status and LPO figures agree")
    return {"suppliers": SUP, "items": IT, "requests": REQ, "lpos": LPO}
