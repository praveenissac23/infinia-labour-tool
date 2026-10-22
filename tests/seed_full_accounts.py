"""Accounts / finance part of the full, live-like test database (see seed_full.py).

    run(c, H)   c = an entered fastapi TestClient, H = admin auth headers

Everything goes in through the app's own API, the way the accountants enter it (Sep - Oct 2026,
today 22-Oct-2026):

  * tax + proforma invoices, invoice terms, a proforma converted, the PAID stamp, one cancelled
  * receipts against them: paid in full, part paid, an advance, one cancelled (cheque returned)
  * project payment tracker: two new projects with scopes and payments
  * petty cash in every book (site, pro, office, naveen, praveen): cash received and bills paid,
    some with VAT + supplier TRN + receipt no., several sites
  * bank: supplier payments, client receipts (one tied to Project payments), charges, a transfer,
    a VAT expense, a post-dated cheque; and an ADCB-style statement upload (xlsx) - some lines
    match, some do not
  * PDCs: overdue, due this week / fortnight, future, cleared, a 6-month rent series, a cancelled one
  * security cheques: undated, dated, a deposit, reminders due / soon / none, returned, encashed
  * credentials (test values only) and the password-locked cash register
  * visa files and payments for a few workers (held payments, completed -> PRO petty cash, paid
    through petty cash)
"""
import io
from datetime import date

TODAY = date(2026, 10, 22)
VAT = 0.05


class SeedError(RuntimeError):
    pass


def _mk(c, H):
    def call(method, url, expect=200, **kw):
        h = dict(H)
        h.update(kw.pop("headers", {}) or {})
        r = c.request(method, url, headers=h, **kw)
        if r.status_code != expect:
            try:
                body = r.json()
            except Exception:
                body = r.text[:500]
            raise SeedError(f"{method} {url} -> {r.status_code} (wanted {expect}): {body}\n  sent: {kw.get('json')}")
        try:
            return r.json()
        except Exception:
            return r.content
    return call


def v(net):
    """net -> (vat, gross) at 5%."""
    t = round(net * VAT, 2)
    return t, round(net + t, 2)


TRN = {  # suppliers' 15-digit TRNs (all start 100)
    "Danube Building Materials": "100248551200003",
    "ACE Hardware Al Quoz": "100371984500003",
    "ENOC Al Khail": "100066114200003",
    "Emirates Transport": "100059731800003",
    "Union Coop Al Barsha": "100236925700003",
    "Carrefour Mall of Emirates": "100038764100003",
    "du Telecom": "100027620200003",
    "Sharaf DG": "100054231300003",
    "Al Futtaim Plant Hire": "100318209100003",
    "Paint Master Trading": "100492011700003",
}


def run(c, H):
    call = _mk(c, H)
    S = {}          # summary counts

    # ---------------------------------------------------------------- invoices
    call("POST", "/employees/accounts/invoice-terms", json={
        "tax": "Payment is due within 30 days of the invoice date.\n"
               "Payment by bank transfer to ADCB account below, or by cheque in favour of Infinia Contracting L.L.C.\n"
               "Please quote the invoice number on your payment.",
        "proforma": "This proforma is valid for 15 days from the date above.\n"
                    "Work starts on receipt of the advance payment.",
        "note": "Thank you for your business."})

    CLIENTS = {
        "914": dict(client="Al Safa Real Estate Holdings LLC", client_trn="100382716400003",
                    client_address="Office 1204, Bay Square 7, Business Bay, Dubai",
                    project="(G+1+R) Villa", project_no="914", plot="6457829", location="Sobha Hartland, Dubai"),
        "915": dict(client="Emkaan Design LLC", client_trn="100471923300003",
                    client_address="Al Quoz Industrial 3, Dubai",
                    project="(G+1+R) Villa", project_no="915", plot="347-4803", location="Sobha Hartland, Dubai"),
        "909": dict(client="Mr. Rakesh Menon", client_trn="",
                    client_address="Villa 12, Meadows 4, Dubai",
                    project="(G+1+R) Villa", project_no="909", plot="VE233", location="Sobha Hartland, Dubai"),
        "920": dict(client="Horizon Living Properties LLC", client_trn="100517342900003",
                    client_address="Office 506, Opal Tower, Business Bay, Dubai",
                    project="(G+1) Villa", project_no="920", plot="VE240", location="Sobha Hartland, Dubai"),
        "916": dict(client="Sunit & Arunkumar Jain", client_trn="",
                    client_address="Keturah Reserve, Meydan, Dubai",
                    project="(B+G+1+R) Villa", project_no="916", plot="631-11274", location="Keturah Reserve, Meydan"),
    }

    def nxt(kind, pno):
        return call("GET", f"/employees/accounts/invoices/next?kind={kind}&project_no={pno}")["number"]

    def invoice(kind, pno, d, work, lines, **extra):
        body = dict(CLIENTS[pno], kind=kind, number=nxt(kind, pno), date=d, work=work, lines=lines, **extra)
        r = call("POST", "/employees/accounts/invoices", json=body)
        return r["id"], r["number"]

    INV = {}
    INV["914a"] = invoice("tax", "914", "2026-09-05", "Core & Shell - Progress Claim 1",
                          [{"description": "Core & Shell works - progress claim no. 1 (substructure complete)", "amount": 300000, "vat": 5}])
    INV["915a"] = invoice("tax", "915", "2026-09-12", "Mobilization & Excavation",
                          [{"description": "Mobilization", "amount": 47000, "vat": 5},
                           {"description": "Excavation and backfilling", "amount": 55380, "vat": 5}])
    INV["909p"] = invoice("proforma", "909", "2026-09-18", "Phase 2 Works - Advance",
                          [{"description": "Advance payment for Phase 2 works (20%)", "amount": 400000, "vat": 5}])
    INV["916a"] = invoice("tax", "916", "2026-09-25", "Villa Design - Stage 1",
                          [{"description": "Concept & schematic design (50% of design fee)", "amount": 70000, "vat": 5}])
    INV["914b"] = invoice("tax", "914", "2026-10-02", "Core & Shell - Progress Claim 2",
                          [{"description": "Core & Shell works - progress claim no. 2 (ground floor slab)", "amount": 250000, "vat": 5}])
    INV["915b"] = invoice("tax", "915", "2026-10-08", "MEP - Progress Claim 1",
                          [{"description": "MEP first fix - progress claim no. 1", "amount": 200000, "vat": 5},
                           {"description": "Dubai Municipality / DEWA authority fees (reimbursement at cost)", "amount": 8500, "vat": 0}])
    INV["920p"] = invoice("proforma", "920", "2026-10-10", "Design - Advance",
                          [{"description": "Design advance (50% of design fee)", "amount": 45000, "vat": 5}])
    INV["920px"] = invoice("proforma", "920", "2026-10-12", "Construction Phase 1 - Advance",
                           [{"description": "Construction phase 1 advance (10%)", "amount": 280000, "vat": 5}])
    # the 916 invoice went out with the wrong client name spelling - cancelled and issued again
    call("POST", f"/employees/accounts/invoices/{INV['916a'][0]}/cancel", json={"reason": "Client name misspelt - reissued as next number"})
    INV["916b"] = invoice("tax", "916", "2026-09-26", "Villa Design - Stage 1",
                          [{"description": "Concept & schematic design (50% of design fee)", "amount": 70000, "vat": 5}])
    # the second 920 proforma was superseded
    call("POST", f"/employees/accounts/invoices/{INV['920px'][0]}/cancel", json={"reason": "Superseded - scope revised by client"})
    # the 909 advance was agreed: the proforma becomes a tax invoice (dated today by the app)
    r = call("POST", f"/employees/accounts/invoices/{INV['909p'][0]}/convert")
    INV["909t"] = (r["id"], r["number"])
    S["invoices"] = 9

    # ---------------------------------------------------------------- receipts
    def rnext(pno):
        return call("GET", f"/employees/accounts/receipts/next?project_no={pno}")["number"]

    def receipt(pno, d, amount, allocs, mode="Bank transfer", reference="", bank="ADCB", cheque_date=None, notes="", stamp=True):
        cl = CLIENTS[pno]
        body = {"number": rnext(pno), "date": d, "client": cl["client"], "client_trn": cl["client_trn"],
                "client_address": cl["client_address"], "project_no": pno, "project": cl["project"],
                "location": cl["location"], "mode": mode, "reference": reference, "bank": bank,
                "cheque_date": cheque_date, "amount": amount, "notes": notes, "stamp_paid": stamp,
                "allocations": [{"invoice_id": INV[k][0], "amount": a} for k, a in allocs]}
        r = call("POST", "/employees/accounts/receipts", json=body)
        return r["id"]

    REC = {}
    REC["914a"] = receipt("914", "2026-09-20", 315000.00, [("914a", 315000.00)], reference="PHUB0092001455", bank="Emirates NBD")
    REC["915a"] = receipt("915", "2026-09-28", 107499.00, [("915a", 107499.00)], mode="Cheque", reference="000781",
                          bank="Mashreq Bank", cheque_date="2026-09-28")
    REC["916b"] = receipt("916", "2026-10-01", 80000.00, [("916b", 73500.00)], reference="PHUB0092001877", bank="HSBC",
                          notes="AED 6,500 kept as advance against design stage 2")
    REC["914b"] = receipt("914", "2026-10-15", 150000.00, [("914b", 150000.00)], reference="PHUB0092002311", bank="Emirates NBD",
                          notes="Part payment of claim 2")
    REC["915b_bounced"] = receipt("915", "2026-10-18", 100000.00, [("915b", 100000.00)], mode="Cheque", reference="000802",
                                  bank="Mashreq Bank", cheque_date="2026-10-18")
    call("POST", f"/employees/accounts/receipts/{REC['915b_bounced']}/cancel", json={"reason": "Cheque returned unpaid - insufficient funds"})
    REC["909t"] = receipt("909", "2026-10-21", 200000.00, [("909t", 200000.00)], mode="PDC", reference="100234",
                          bank="ADCB", cheque_date="2026-11-05", notes="Post-dated cheque, part of the Phase 2 advance")
    # 920's design proforma: paid by the client before the tax invoice - stays a proforma; the PAID stamp
    # is put by hand on the 914 claim 1 to make sure (already stamped by the receipt - re-stamped same date)
    call("POST", f"/employees/accounts/invoices/{INV['914a'][0]}/paid", json={"paid": True, "paid_on": "2026-09-20"})
    S["receipts"] = 6

    # ---------------------------------------------------------------- project payments tracker
    PP = {}
    r = call("POST", "/employees/accounts/projects", json={"project": "929", "scope": "DESIGN", "contract": 135000,
             "remarks": "Villa design - Dubai Hills plot", "payments": [{"date": "2026-09-08", "amount": 40500, "note": "Design advance 30%"}]})
    PP["929d"] = r["id"]
    r = call("POST", "/employees/accounts/projects", json={"project": "929", "scope": "CORE & SHELL", "contract": 2150000,
             "remarks": "", "payments": []})
    PP["929c"] = r["id"]
    r = call("POST", "/employees/accounts/projects", json={"project": "930", "scope": "SWIMMING POOL", "contract": 186000,
             "remarks": "Pool division - Arabian Ranches 3", "payments": [
                 {"date": "2026-09-15", "amount": 55800, "note": "Advance 30%"},
                 {"date": "2026-10-12", "amount": 74400, "note": "Shell complete 40%"}]})
    PP["930p"] = r["id"]
    # the 929 design scope's remarks corrected on the tracker (its 2nd payment comes from the Bank tab below)
    call("PUT", f"/employees/accounts/projects/{PP['929d']}", json={"project": "929", "scope": "DESIGN", "contract": 135000,
         "remarks": "Villa design - Dubai Hills plot 2, client Mr. K. Sharma", "payments": [
             {"date": "2026-09-08", "amount": 40500, "note": "Design advance 30%"}]})
    S["project scopes"] = 3

    # ---------------------------------------------------------------- petty cash
    def pc(book, d, desc, received=0, paid=0, supplier="", site="", vat=False, trn="", receipt_no="", **extra):
        body = {"book": book, "date": d, "description": desc, "received": received, "paid": paid, "supplier": supplier,
                "site": site, "vat": vat, "trn": trn, "receipt_no": receipt_no, **extra}
        return call("POST", "/store/petty-cash", json=body)["id"]

    def bill(book, d, desc, net, supplier, site="", receipt_no="", vat=True):
        """A bill: with VAT the paid figure is net + 5% and the supplier's TRN is kept."""
        gross = v(net)[1] if vat else round(net, 2)
        return pc(book, d, desc, paid=gross, supplier=supplier, site=site, vat=vat,
                  trn=TRN.get(supplier, "") if vat else "", receipt_no=receipt_no)

    n0 = 0
    # site box (store keeper)
    pc("site", "2026-09-01", "Cash received from office (cheque encashed)", received=10000, supplier="Office")
    bill("site", "2026-09-03", "Binding wire 20 rolls + nails", 640.00, "Danube Building Materials", "914", "DBM-55120")
    bill("site", "2026-09-06", "Diesel for generator 200 L", 590.00, "ENOC Al Khail", "915", "ENC-778412")
    bill("site", "2026-09-10", "Drinking water 5 gal x 40", 220.00, "Union Coop Al Barsha", "909", "UC-201988", vat=False)
    bill("site", "2026-09-14", "PVC conduits 25mm and boxes", 1180.00, "ACE Hardware Al Quoz", "915", "ACE-30451")
    bill("site", "2026-09-17", "Pick-up hire 1 day - shuttering transfer", 450.00, "Emirates Transport", "920", "ET-11984")
    pc("site", "2026-09-20", "Cash received from office", received=8000, supplier="Office")
    bill("site", "2026-09-22", "Paint primer 10 drums", 2350.00, "Paint Master Trading", "909", "PMT-0921")
    bill("site", "2026-09-26", "Labour tea & snacks - concrete pour night", 185.00, "Carrefour Mall of Emirates", "914", "", vat=False)
    bill("site", "2026-09-29", "Plate compactor hire 2 days", 700.00, "Al Futtaim Plant Hire", "914", "AFP-77301")
    pc("site", "2026-10-05", "Cash received from office", received=10000, supplier="Office")
    bill("site", "2026-10-06", "Tie wire, spacers, cover blocks", 860.00, "Danube Building Materials", "920", "DBM-56002")
    bill("site", "2026-10-09", "Diesel for generator 180 L", 531.00, "ENOC Al Khail", "915", "ENC-781190")
    bill("site", "2026-10-13", "Safety tape, barricade, cones", 415.00, "ACE Hardware Al Quoz", "909", "ACE-31077")
    bill("site", "2026-10-16", "Truck hire - debris removal 3 trips", 1350.00, "Emirates Transport", "914", "ET-12230")
    bill("site", "2026-10-19", "Drinking water 5 gal x 40", 220.00, "Union Coop Al Barsha", "920", "", vat=False)
    bill("site", "2026-10-21", "Masking tape, rollers, brushes", 296.00, "Paint Master Trading", "909", "PMT-1007")
    n0 += 18
    # PRO box (Jomon)
    pc("pro", "2026-09-02", "Cash received from office for PRO expenses", received=6000, supplier="Office")
    bill("pro", "2026-09-04", "Typing charges - labour contracts x 4", 240.00, "Tasheel Al Barsha", "", "TSH-88120", vat=False)
    bill("pro", "2026-09-09", "Trade licence renewal - DED knowledge & innovation fees", 20.00, "Dubai Economy", "", "DED-4471", vat=False)
    bill("pro", "2026-09-15", "RTA fine - company pick-up (parking)", 300.00, "RTA", "", "RTA-F-99211", vat=False)
    bill("pro", "2026-09-23", "Attestation of tenancy contract (Ejari)", 220.00, "Ejari Centre Al Quoz", "", "EJ-30018", vat=False)
    pc("pro", "2026-10-01", "Cash received from office for PRO expenses", received=6000, supplier="Office")
    bill("pro", "2026-10-07", "Courier - documents to Sobha Hartland site office", 60.00, "Emirates Transport", "", "ET-12101")
    bill("pro", "2026-10-14", "Municipality NOC fees - 920 hoarding", 1050.00, "Dubai Municipality", "920", "DM-NOC-5521", vat=False)
    n0 += 8
    # office box (chief accountant)
    pc("office", "2026-09-01", "Cash withdrawn for office petty cash", received=4000, supplier="ADCB")
    bill("office", "2026-09-03", "Office stationery - A4 paper, files, toner", 412.00, "Sharaf DG", "", "SDG-2209-114")
    bill("office", "2026-09-08", "du internet - office (Aug)", 499.00, "du Telecom", "", "DU-8812345")
    bill("office", "2026-09-11", "Pantry - tea, coffee, sugar", 168.50, "Union Coop Al Barsha", "", "UC-202417")
    bill("office", "2026-09-24", "Office cleaning materials", 96.00, "Carrefour Mall of Emirates", "", "", vat=False)
    pc("office", "2026-10-01", "Cash withdrawn for office petty cash", received=3000, supplier="ADCB")
    bill("office", "2026-10-08", "du internet - office (Sep)", 499.00, "du Telecom", "", "DU-8899102")
    bill("office", "2026-10-12", "Printer cartridges x 2", 620.00, "Sharaf DG", "", "SDG-2210-087")
    bill("office", "2026-10-20", "Pantry - water, tea, cups", 142.00, "Union Coop Al Barsha", "", "UC-205530")
    n0 += 9
    # directors' books: "paid" = the director paid for the company, "received" = repaid to him
    bill("naveen", "2026-09-05", "Client meeting lunch - 914 Al Safa", 380.00, "Carrefour Mall of Emirates", "914", "", vat=False)
    bill("naveen", "2026-09-12", "Fuel - site visits Sep", 450.00, "ENOC Al Khail", "", "ENC-779001")
    bill("naveen", "2026-09-27", "Tile samples for 909 client selection", 1240.00, "Danube Building Materials", "909", "DBM-55871")
    pc("naveen", "2026-09-30", "Repaid to Naveen - Sep expenses", received=2000, supplier="Office")
    bill("naveen", "2026-10-10", "Fuel - site visits Oct", 410.00, "ENOC Al Khail", "", "ENC-781455")
    bill("naveen", "2026-10-17", "Laptop charger replacement", 285.00, "Sharaf DG", "", "SDG-2210-201")
    bill("praveen", "2026-09-07", "Trade licence activity add - consultant fee", 1500.00, "Dubai Economy", "", "DED-4512", vat=False)
    bill("praveen", "2026-09-19", "Site visit taxi + Salik - 916 Keturah", 165.00, "Emirates Transport", "916", "")
    pc("praveen", "2026-10-02", "Repaid to Praveen - Sep expenses", received=1650, supplier="Office")
    bill("praveen", "2026-10-11", "Design software subscription (monthly)", 920.00, "Sharaf DG", "", "SDG-2210-099")
    bill("praveen", "2026-10-18", "Client gift - 920 handover of design", 600.00, "Carrefour Mall of Emirates", "920", "", vat=False)
    n0 += 11
    S["petty cash lines (direct)"] = n0

    # ---------------------------------------------------------------- visa files & payments
    emps = call("GET", "/employees?active_only=true")
    labour = [e for e in emps if not e.get("staff")]
    if len(labour) < 3:
        raise SeedError("need 3 labour employees for visa files")
    e1, e2, e3 = labour[0], labour[1], labour[2]
    f1 = call("POST", "/store/visa/files", json={"kind": "renewal", "employee_id": e1["id"], "started": "2026-09-14",
                                                  "note": "Residency expires 30-Oct-2026"})
    f2 = call("POST", "/store/visa/files", json={"kind": "new_out", "employee_id": e2["id"], "started": "2026-10-02",
                                                  "note": "New hire from Nepal - mason"})
    f3 = call("POST", "/store/visa/files", json={"kind": "cancel", "employee_id": e3["id"], "started": "2026-10-15",
                                                  "note": "Resigned - final settlement done"})
    # renewal: payments held on the Visa tab until completed
    p1 = f1["person"]
    call("POST", "/store/visa/payments", json={"person": p1, "date": "2026-09-15", "amount": 250.00, "step": "Labour contract renewal",
                                               "supplier": "MOHRE & GDRFA", "description": "Contract renewal typing + fee", "receipt_no": "MOH-7781201"})
    call("POST", "/store/visa/payments", json={"person": p1, "date": "2026-09-18", "amount": 685.00, "step": "WPP insurance",
                                               "supplier": "MOHRE & GDRFA", "description": "WPP insurance 2 yrs", "receipt_no": "WPP-55102"})
    call("POST", "/store/visa/payments", json={"person": p1, "date": "2026-09-25", "amount": 1530.00,
                                               "step": "Work permit renewal and contract submission", "supplier": "MOHRE & GDRFA",
                                               "description": "Work permit renewal", "receipt_no": "MOH-7790344"})
    call("POST", "/store/visa/payments", json={"person": p1, "date": "2026-10-06", "amount": 320.00, "step": "Medical and EID",
                                               "supplier": "MOHRE & GDRFA", "description": "Medical fitness + EID", "receipt_no": "EHS-301122"})
    call("POST", "/store/visa/payments", json={"person": p1, "date": "2026-10-13", "amount": 650.00, "step": "Residency renewal",
                                               "supplier": "MOHRE & GDRFA", "description": "Residency stamping", "receipt_no": "GDR-912201"})
    call("POST", f"/store/visa/files/{f1['id']}/complete")      # -> one PRO petty cash line, dated today
    # new visa: two held payments, still ongoing
    p2 = f2["person"]
    call("POST", "/store/visa/payments", json={"person": p2, "date": "2026-10-03", "amount": 300.00, "step": "Quota modification",
                                               "supplier": "MOHRE & GDRFA", "receipt_no": "MOH-7799102"})
    call("POST", "/store/visa/payments", json={"person": p2, "date": "2026-10-08", "amount": 1150.00, "step": "New work permit",
                                               "supplier": "MOHRE & GDRFA", "receipt_no": "MOH-7801977"})
    # ... and one stage paid straight from PRO petty cash, tied to the file
    call("POST", f"/store/visa/files/{f2['id']}/pay", json={"stage": "New entry permit", "date": "2026-10-16", "amount": 1265.00,
                                                         "supplier": "MOHRE & GDRFA", "receipt_no": "GDR-915020"})
    # cancellation: paid through the PRO petty cash form ("Visa related expense?" yes)
    pc("pro", "2026-10-17", f"{f3['person']} - labour contract cancellation", paid=150.00, supplier="MOHRE & GDRFA",
       receipt_no="MOH-7811230", visa_file_id=f3["id"], visa_stage="Labour contract cancellation")
    pc("pro", "2026-10-20", f"{f3['person']} - visa cancellation", paid=210.00, supplier="MOHRE & GDRFA",
       receipt_no="GDR-916610", visa_file_id=f3["id"], visa_stage="Visa cancellation", visa_complete=True)
    S["visa files"] = 3
    S["visa payments (held)"] = 7

    # ---------------------------------------------------------------- bank
    def bank(kind, d, amount, party="", mode="Bank Transfer", reference="", **extra):
        body = {"kind": kind, "date": d, "amount": amount, "party": party, "mode": mode, "reference": reference, **extra}
        r = call("POST", "/store/bank", json=body)
        return r["id"]

    B = {}
    B["s1"] = bank("vendor", "2026-09-04", 48300.00, "Danube Building Materials", reference="PHUB0091004412",
                   docs=[{"id": "", "number": "DBM/INV/2026/8812", "amount": 48300.00}], notes="Blockwork & cement Aug")
    B["s2"] = bank("transfer", "2026-09-01", 10000.00, account="Site Petty Cash", reference="PHUB0091000205", notes="Site petty cash top-up")
    B["s3"] = bank("customer", "2026-09-20", 315000.00, CLIENTS["914"]["client"], reference="PHUB0092001455",
                   docs=[{"id": "", "number": INV["914a"][1], "amount": 315000.00}])
    B["s4"] = bank("vendor", "2026-09-24", 26250.00, "Al Futtaim Plant Hire", mode="Cheque", reference="000512",
                   notes="Excavator hire Aug - cheque")
    B["s5"] = bank("charge", "2026-09-30", 52.50, reference="CHG-SEP-26", notes="ADCB account maintenance + VAT")
    B["s6"] = bank("customer", "2026-09-28", 107499.00, CLIENTS["915"]["client"], mode="Cheque", reference="000781",
                   docs=[{"id": "", "number": INV["915a"][1], "amount": 107499.00}])
    B["o1"] = bank("transfer", "2026-10-05", 10000.00, account="Site Petty Cash", reference="PHUB0101000311", notes="Site petty cash top-up")
    B["o2"] = bank("customer", "2026-10-01", 80000.00, CLIENTS["916"]["client"], reference="PHUB0092001877",
                   docs=[{"id": "", "number": INV["916b"][1], "amount": 73500.00}], notes="incl. AED 6,500 advance")
    B["o3"] = bank("vendor", "2026-10-07", 63525.00, "Emirates Steel Industries", reference="PHUB0101002290",
                   notes="Rebar 16mm/12mm - 914")
    B["o4"] = bank("expense", "2026-10-09", 3150.00, "du Telecom", reference="PHUB0101002533", account="Telephone Expense",
                   vat=True, trn=TRN["du Telecom"], vat_claim="claim", notes="Office lines + mobile Sep")
    B["o5"] = bank("customer", "2026-10-06", 56700.00, "Dubai Hills Villa Owner (929)", reference="PHUB0101002101",
                   scope_id=PP["929d"], net_amount=54000.00, notes="929 schematic design 40% + VAT")
    B["o6"] = bank("vendor", "2026-10-12", 18900.00, "Paint Master Trading", mode="Cheque", reference="000519",
                   notes="Paint supply 909 - cheque")
    B["o7"] = bank("customer", "2026-10-15", 150000.00, CLIENTS["914"]["client"], reference="PHUB0092002311",
                   docs=[{"id": "", "number": INV["914b"][1], "amount": 150000.00}])
    B["o8"] = bank("charge", "2026-10-15", 26.25, reference="CHG-TT-1015", notes="Outward TT charge + VAT")
    B["o9"] = bank("expense", "2026-10-18", 7350.00, "Al Futtaim Plant Hire", reference="PHUB0101003012",
                   account="Equipment Hire", site="914", vat=True, trn=TRN["Al Futtaim Plant Hire"], vat_claim="claim",
                   notes="Plate compactor + mixer hire Oct")
    B["o10"] = bank("vendor", "2026-11-05", 42000.00, "Al Quoz Steel Fabrication", mode="Cheque", reference="000527",
                    notes="Post-dated cheque - structural steel 920")
    B["o11"] = bank("customer", "2026-10-20", 74400.00, "Arabian Ranches Pool Client (930)", reference="PHUB0101003390",
                    notes="930 pool - not tied to tracker (entered there by hand)")
    S["bank entries"] = len(B)

    # ---------------------------------------------------------------- ADCB statement (xlsx)
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Statement"
    ws.append(["ABU DHABI COMMERCIAL BANK"])
    ws.append(["Account Statement", "", "Account No: XXXXXXXX0001", "Currency: AED"])
    ws.append(["Period: 01/10/2026 to 21/10/2026"])
    ws.append([])
    ws.append(["Posting Date", "Value Date", "Cheque No", "Customer Reference", "Transaction Description",
               "Debit Amount", "Credit Amount", "Running Balance"])
    bal = 1250000.00
    ws.append(["01/10/2026", "01/10/2026", "", "", "Opening Balance", "", "", bal])
    lines = [
        # date, cheque no, cust ref, description, debit, credit
        ("01/10/2026", "", "916 DESIGN", "I/W TRF PHUB0092001877 SUNIT JAIN HSBC", 0, 80000.00),           # ref match
        ("05/10/2026", "", "PETTY CASH", "O/W TRF PHUB0101000311 OWN A/C TRANSFER", 10000.00, 0),          # ref match
        ("06/10/2026", "", "", "I/W TRF DUBAI HILLS VILLA PROJECT 929", 0, 56700.00),                     # amount match (no ref on line)
        ("07/10/2026", "", "REBAR 914", "O/W TRF PHUB0101002290 EMIRATES STEEL", 63525.00, 0),             # ref match
        ("09/10/2026", "", "", "O/W TRF PHUB0101002533 DU", 3150.00, 0),                                  # ref match
        ("13/10/2026", "000512", "", "CHQ PAID 000512 AL FUTTAIM", 26250.00, 0),                          # cheque of 24-Sep, in text
        ("14/10/2026", "000519", "", "CLEARING CHEQUE PAID", 18900.00, 0),                               # cheque no only in its column
        ("15/10/2026", "", "", "I/W TRF PHUB0092002311 AL SAFA", 0, 150000.00),                           # ref match
        ("15/10/2026", "", "", "TT CHARGES INCL VAT", 26.25, 0),                                          # amount match
        ("16/10/2026", "", "", "SALARY WPS TRANSFER OCT", 148250.00, 0),                                  # not entered
        ("18/10/2026", "", "", "O/W TRF PHUB0101003012 AL FUTTAIM PLANT", 7350.00, 0),                    # ref match
        ("19/10/2026", "", "", "I/W TRF UNKNOWN REMITTER REF 88120031", 0, 12500.00),                     # not entered
        ("20/10/2026", "", "", "I/W TRF PHUB0101003390 ARABIAN RANCHES", 0, 74400.00),                    # ref match
        ("21/10/2026", "", "", "DEWA DIRECT DEBIT 2001544781", 1890.40, 0),                               # not entered
    ]
    for d, chq, cref, desc, dr, cr in lines:
        bal = round(bal - dr + cr, 2)
        ws.append([d, d, chq, cref, desc, dr or "", cr or "", bal])
    buf = io.BytesIO(); wb.save(buf)
    st = call("POST", "/store/bank/stmt/upload",
              files={"file": ("ADCB_Statement_Oct2026.xlsx", buf.getvalue(),
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    S["statement"] = f"{st['lines']} lines, {st['matched']} matched on upload, breaks {st['breaks']}"
    # the WPS salary line: ignored with a reason (entered through payroll, not the Bank tab); DEWA given a note
    chk = call("GET", "/store/bank/stmt?month=2026-10")
    for l in chk["lines"]:
        if "SALARY WPS" in l["bank_text"]:
            call("POST", f"/store/bank/stmt/{l['id']}/ignore", json={"reason": "October salaries - paid through WPS payroll, booked by payroll"})
        if "DEWA" in l["bank_text"]:
            call("POST", f"/store/bank/stmt/{l['id']}/note", json={"note": "DEWA office - to be entered as expense"})

    # ---------------------------------------------------------------- PDCs
    def pdc(payee, no, d, amount, notes="", repeat=1, status="pending", bank_="ADCB"):
        return call("POST", "/employees/pdc", json={"payee": payee, "cheque_no": no, "bank": bank_, "date": d,
                                                     "amount": amount, "notes": notes, "repeat": repeat, "status": status})["ids"]
    P = {}
    P["rent"] = pdc("Al Quoz Warehouse Landlord LLC", "000451", "2026-09-01", 12500.00, "Warehouse rent - 6 monthly cheques", repeat=6)
    P["steel_over"] = pdc("Emirates Steel Industries", "000514", "2026-10-10", 38750.00, "Rebar balance - 915")
    P["ready_over"] = pdc("Unimix Ready Mix Concrete", "000516", "2026-10-15", 52480.00, "Concrete Sep pours")
    P["week"] = pdc("Danube Building Materials", "000521", "2026-10-25", 27300.00, "Blocks & cement Oct")
    P["week2"] = pdc("Al Futtaim Plant Hire", "000522", "2026-10-29", 15750.00, "Equipment hire Sep")
    P["fortnight"] = pdc("Paint Master Trading", "000523", "2026-11-03", 9450.00, "Paint 909")
    P["future"] = pdc("Al Quoz Steel Fabrication", "000527", "2026-11-05", 42000.00, "Structural steel 920")
    P["future2"] = pdc("Cordoba Interior Factory", "000530", "2026-12-15", 86000.00, "Joinery advance - Downtown")
    P["cleared1"] = pdc("Emirates Transport", "000505", "2026-09-15", 6800.00, "Transport Aug")
    P["cleared2"] = pdc("Union Coop Al Barsha", "000508", "2026-09-30", 2150.00, "Camp provisions Sep")
    P["cancelled"] = pdc("Gulf Scaffolding LLC", "000510", "2026-10-05", 11200.00, "Replaced by bank transfer", status="cancelled")
    for pid in P["rent"][:2] + P["cleared1"] + P["cleared2"]:
        r = call("POST", f"/employees/pdc/{pid}/clear")
        if r["status"] != "cleared":
            raise SeedError(f"PDC {pid} did not clear: {r}")
    S["PDCs"] = sum(len(x) for x in P.values())

    # ---------------------------------------------------------------- security cheques
    def sec(**kw):
        return call("POST", "/employees/security-cheques", json=kw)["id"]
    SC = {}
    SC["bid"] = sec(party="Sobha Realty", purpose="Tender / bid bond", project="VE278 (T252) tender", bank="ADCB",
                    cheque_no="000498", amount=50000, undated=True, given_on="2026-09-29", remind_on="2026-11-30",
                    notes="Collect back if tender not awarded")
    SC["perf"] = sec(party="Emkaan Design LLC", purpose="Performance guarantee", project="915", bank="ADCB", cheque_no="000470",
                     amount=150000, cheque_date="2027-06-30", given_on="2026-09-02", remind_on="2026-10-27",
                     notes="10% performance - release on handover")
    SC["adv"] = sec(party="Al Safa Real Estate Holdings LLC", purpose="Advance payment guarantee", project="914", bank="ADCB",
                    cheque_no="000466", amount=95000, undated=True, given_on="2026-09-01", remind_on="2026-10-15",
                    notes="Against advance - return when advance recovered")
    SC["ten"] = sec(kind="deposit", party="Al Quoz Warehouse Landlord LLC", purpose="Tenancy / rent", project="", bank="",
                    cheque_no="", amount=12500, given_on="2026-09-01", notes="Refundable security deposit - warehouse")
    SC["auth"] = sec(party="Dubai Municipality", purpose="Authority / permit", project="920", bank="ADCB", cheque_no="000489",
                     amount=10000, undated=True, given_on="2026-09-10", notes="Hoarding permit guarantee")
    SC["sup"] = sec(party="Danube Building Materials", purpose="Supplier credit", project="", bank="ADCB", cheque_no="000455",
                    amount=100000, undated=True, given_on="2026-09-03", remind_on="2026-10-20", notes="Credit facility security")
    SC["enc"] = sec(party="Gulf Scaffolding LLC", purpose="Supplier credit", project="", bank="ADCB", cheque_no="000440",
                    amount=8000, undated=True, given_on="2026-09-05", status="encashed", returned_on="2026-10-03",
                    notes="Encashed against overdue hire invoice")
    call("POST", f"/employees/security-cheques/{SC['sup']}/returned")          # collected back today
    S["security cheques"] = len(SC)

    # ---------------------------------------------------------------- credentials (test values only)
    LOGO = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAMklEQVR4nGP8z8Dwn4ECwESJ5lEDRg0YNWDUgFED"
            "Rg0YNWDUgFEDRg0YNWDUAAAAAP//AwBkHgUfSm5ZUAAAAABJRU5ErkJggg==")
    CR = {}
    for body in (
        {"name": "ADCB ProCash (TEST)", "url": "https://procash.adcb.com", "kind": "login", "category": "Bank",
         "username": "test.infinia", "secret": "Test-Only-Pass-1!", "notes": "TEST DATA - not a real login", "logo": LOGO},
        {"name": "MOHRE Tasheel (TEST)", "url": "https://www.mohre.gov.ae", "kind": "login", "category": "Government",
         "username": "test.pro", "secret": "Test-Only-Pass-2!", "notes": "", "logo": LOGO},
        {"name": "DEWA (TEST)", "url": "https://www.dewa.gov.ae", "kind": "login", "category": "Utilities",
         "username": "test.dewa", "secret": "Test-Only-Pass-3!", "logo": LOGO},
        {"name": "Office alarm PIN (TEST)", "url": "", "kind": "pin", "category": "Office",
         "username": "", "secret": "0000", "notes": "TEST DATA", "logo": LOGO, "admin_only": True},
        {"name": "Zoho Books (TEST)", "url": "https://books.zoho.com", "kind": "login", "category": "Software",
         "username": "test@example.com", "secret": "Test-Only-Pass-4!", "logo": LOGO},
    ):
        r = call("POST", "/employees/accounts/credentials", json=body)
        CR[body["name"]] = r["id"]
    got = call("POST", f"/employees/accounts/credentials/{CR['ADCB ProCash (TEST)']}/reveal", json={"how": "show"})
    if got["secret"] != "Test-Only-Pass-1!":
        raise SeedError(f"credential did not read back: {got}")
    S["credentials"] = len(CR)

    # ---------------------------------------------------------------- cash register (password)
    key = call("POST", "/employees/accounts/register/unlock", json={"password": "Infinia2022!"})["key"]
    RK = {"X-Register-Key": key}
    call("GET", "/employees/accounts/register", expect=423)          # locked without the key
    regs = [
        ("received", "2026-09-01", "Cash withdrawn from ADCB - office cash", 20000, "CHQ 000501"),
        ("paid", "2026-09-02", "Office petty cash float", 4000, ""),
        ("paid", "2026-09-05", "Site petty cash float (store keeper)", 10000, ""),
        ("received", "2026-09-14", "Cash received - scrap steel sale 914", 3850, "Receipt SC-0091"),
        ("paid", "2026-09-20", "Site petty cash top-up", 8000, ""),
        ("paid", "2026-09-30", "Repaid to Naveen - Sep expenses", 2000, ""),
        ("received", "2026-10-01", "Cash withdrawn from ADCB - office cash", 25000, "CHQ 000517"),
        ("paid", "2026-10-01", "Office petty cash float", 3000, ""),
        ("paid", "2026-10-01", "PRO petty cash float", 6000, ""),
        ("paid", "2026-10-02", "Repaid to Praveen - Sep expenses", 1650, ""),
        ("paid", "2026-10-05", "Site petty cash top-up", 10000, ""),
        ("received", "2026-10-19", "Cash received - client 930 token for pool variation", 5000, "Receipt SC-0102"),
    ]
    for kind, d, desc, amt, rem in regs:
        call("POST", "/employees/accounts/register", headers=RK, json={"kind": kind, "date": d, "description": desc,
                                                                        "amount": amt, "remarks": rem})
    S["cash register lines"] = len(regs)

    # ---------------------------------------------------------------- summary
    print("  accounts seed:")
    for k, val in S.items():
        print(f"    {k:28s} {val}")
    return S
