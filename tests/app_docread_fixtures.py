"""Documents the rest of the app can read: a shop receipt (PDF and phone photo), a cheque photo, a passport
and an Emirates ID photo, a delivery note (PDF and scan), a supplier quotation and an ADCB statement (PDF and scan).

    python3 tests/app_docread_fixtures.py /tmp/appdocs   -> prints {name: {file, expect}} as JSON
"""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/appdocs"
os.makedirs(out, exist_ok=True)
st = getSampleStyleSheet()
P = lambda t, s="Normal": Paragraph(t, st[s])
F = lambda n, sz: ImageFont.truetype(f"/usr/share/fonts/truetype/{n}", sz)
SANS, BOLD, MONO = "dejavu/DejaVuSans.ttf", "dejavu/DejaVuSans-Bold.ttf", "dejavu/DejaVuSansMono.ttf"
GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)])
res = {}


def pdf(name, el):
    SimpleDocTemplate(os.path.join(out, name), pagesize=A4).build(el)
    return os.path.join(out, name)


def scan(src, name, rotate=0.6):
    """print it and scan it: a picture of each page, slightly crooked and grey, put back into a PDF"""
    base = os.path.join(out, "_scan")
    subprocess.run(["pdftoppm", "-r", "200", "-gray", "-png", src, base], check=True)
    pages = sorted(p for p in os.listdir(out) if p.startswith("_scan") and p.endswith(".png"))
    imgs = []
    for p in pages:
        im = Image.open(os.path.join(out, p)).convert("L").rotate(rotate, expand=False, fillcolor=255).filter(ImageFilter.GaussianBlur(0.5))
        q = os.path.join(out, p.replace(".png", ".jpg")); im.save(q, quality=70); imgs.append(q); os.remove(os.path.join(out, p))
    subprocess.run(["img2pdf", *imgs, "-o", os.path.join(out, name)], check=True)
    for q in imgs:
        os.remove(q)
    return os.path.join(out, name)


def photo(src_pdf, name):
    """a phone photo of a printed page"""
    base = os.path.join(out, "_ph")
    subprocess.run(["pdftoppm", "-r", "140", "-png", "-singlefile", src_pdf, base], check=True)
    im = Image.open(base + ".png").convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, int(h * 0.55))).rotate(-1.0, expand=True, fillcolor=(236, 232, 224)).filter(ImageFilter.GaussianBlur(0.6))
    im.save(os.path.join(out, name), quality=78); os.remove(base + ".png")
    return os.path.join(out, name)


# 1. a shop receipt for cash -> petty cash
rc = pdf("Al Hassai receipt.pdf", [
    P("AL HASSAI BUILDING MATERIALS TRADING L.L.C", "Title"), P("Shop 4, Al Quoz Industrial 3, Dubai  Tel: 04 3388 112"),
    P("TRN: 100234567800003"), P("TAX INVOICE", "Heading2"),
    Table([["Invoice No:", "AH-55871", "Date:", "19/10/2026"], ["Customer:", "Infinia Contracting LLC", "Payment:", "Cash"]]), Spacer(1, 8),
    Table([["Description", "Qty", "Rate", "Amount"], ["Cement OPC 50kg bag", "20", "17.00", "340.00"], ["Plastering sand (bag)", "15", "8.00", "120.00"],
           ["Sub total", "", "", "460.00"], ["VAT 5%", "", "", "23.00"], ["Total amount including VAT", "", "", "483.00"]], style=GRID),
    Spacer(1, 8), P("Thank you for your business")])
res["receipt"] = {"file": rc, "expect": {"date": "2026-10-19", "supplier": "AL HASSAI BUILDING MATERIALS TRADING L.L.C", "receipt_no": "AH-55871", "amount": 483, "vat": 23, "trn": "100234567800003"}}
res["receipt_photo"] = {"file": photo(rc, "Al Hassai receipt photo.jpg"), "expect": {"date": "2026-10-19", "receipt_no": "AH-55871", "amount": 483, "trn": "100234567800003"}}

# 2. a cheque (photo) -> PDC / security cheque
im = Image.new("RGB", (1500, 680), (238, 244, 236)); d = ImageDraw.Draw(im)
d.rectangle((8, 8, 1492, 672), outline=(120, 140, 120), width=3)
d.text((50, 40), "ADCB", font=F(BOLD, 54), fill=(150, 20, 30)); d.text((50, 105), "Abu Dhabi Commercial Bank", font=F(SANS, 26), fill=(60, 60, 60))
d.text((1020, 50), "Date", font=F(SANS, 28), fill=(40, 40, 40)); d.text((1110, 44), "15/11/2026", font=F(MONO, 40), fill=(10, 10, 60))
d.text((50, 220), "Pay", font=F(SANS, 32), fill=(40, 40, 40)); d.text((140, 212), "Desarch Scaffolding LLC", font=F(SANS, 40), fill=(10, 10, 60))
d.line((130, 262, 1400, 262), fill=(120, 120, 120), width=2)
d.text((50, 300), "Dirhams", font=F(SANS, 32), fill=(40, 40, 40)); d.text((210, 292), "Twelve Thousand Five Hundred Only", font=F(SANS, 36), fill=(10, 10, 60))
d.rectangle((1080, 380, 1440, 450), outline=(80, 80, 80), width=2); d.text((1095, 392), "AED 12,500.00", font=F(BOLD, 38), fill=(10, 10, 60))
d.text((50, 420), "Account: Infinia Contracting LLC", font=F(SANS, 26), fill=(60, 60, 60))
d.text((180, 590), "000451   033012345   1234567890001", font=F(MONO, 40), fill=(20, 20, 20))
im = im.rotate(1.2, expand=True, fillcolor=(200, 196, 188)).filter(ImageFilter.GaussianBlur(0.5))
im.save(os.path.join(out, "cheque 000451.jpg"), quality=80)
res["cheque"] = {"file": os.path.join(out, "cheque 000451.jpg"), "expect": {"no": "000451", "date": "2026-11-15", "amount": 12500, "payee": "Desarch Scaffolding LLC", "bank": "ADCB"}}

# 3. passport data page (photo) -> expiry documents
im = Image.new("RGB", (1500, 1000), (232, 236, 245)); d = ImageDraw.Draw(im)
d.text((60, 40), "REPUBLIC OF INDIA", font=F(BOLD, 44), fill=(30, 30, 90)); d.text((60, 100), "PASSPORT", font=F(BOLD, 36), fill=(30, 30, 90))
d.rectangle((60, 180, 380, 600), fill=(200, 205, 215))
rows = [("Type", "P"), ("Passport No.", "Z1234567"), ("Surname", "KUMAR"), ("Given Name(s)", "RAJESH"), ("Date of Birth", "12/04/1988"),
        ("Date of Issue", "03/02/2020"), ("Date of Expiry", "02/02/2030")]
for i, (k, v) in enumerate(rows):
    d.text((430, 180 + i * 58), k, font=F(SANS, 22), fill=(80, 80, 80)); d.text((720, 176 + i * 58), v, font=F(BOLD, 30), fill=(10, 10, 10))
mrz1 = "P<INDKUMAR<<RAJESH<<<<<<<<<<<<<<<<<<<<<<<<<<"
mrz2 = "Z12345674IND8804122M3002024<<<<<<<<<<<<<<06"
d.text((60, 800), mrz1, font=F(MONO, 31), fill=(0, 0, 0)); d.text((60, 860), mrz2, font=F(MONO, 31), fill=(0, 0, 0))
im.rotate(-0.8, expand=True, fillcolor=(190, 190, 190)).filter(ImageFilter.GaussianBlur(0.4)).save(os.path.join(out, "passport Rajesh.jpg"), quality=82)
res["passport"] = {"file": os.path.join(out, "passport Rajesh.jpg"), "expect": {"kind": "passport", "number": "Z1234567", "expires_on": "2030-02-02", "issued_on": "2020-02-03"}}

# 4. Emirates ID (photo) -> expiry documents
im = Image.new("RGB", (1300, 820), (236, 242, 238)); d = ImageDraw.Draw(im)
d.text((50, 40), "United Arab Emirates", font=F(BOLD, 40), fill=(20, 60, 40)); d.text((50, 95), "Resident Identity Card", font=F(SANS, 32), fill=(20, 60, 40))
d.rectangle((50, 180, 330, 520), fill=(205, 212, 208))
for i, (k, v) in enumerate([("ID Number", "784-1988-1234567-1"), ("Name", "Rajesh Kumar"), ("Nationality", "India"),
                            ("Issuing Date", "14/03/2025"), ("Expiry Date", "13/03/2027")]):
    d.text((380, 190 + i * 70), k + ":", font=F(SANS, 26), fill=(70, 70, 70)); d.text((640, 186 + i * 70), v, font=F(BOLD, 32), fill=(10, 10, 10))
im.rotate(0.9, expand=True, fillcolor=(190, 190, 190)).filter(ImageFilter.GaussianBlur(0.4)).save(os.path.join(out, "emirates id Rajesh.jpg"), quality=82)
res["eid"] = {"file": os.path.join(out, "emirates id Rajesh.jpg"), "expect": {"kind": "eid", "number": "784-1988-1234567-1", "expires_on": "2027-03-13", "issued_on": "2025-03-14"}}

# 5. delivery note -> material arrived
dn = pdf("Gulf Steel DO 7781.pdf", [
    P("GULF STEEL TRADING LLC", "Title"), P("P.O. Box 4411, Sharjah   TRN 100398765400003"), P("DELIVERY NOTE", "Heading2"),
    Table([["DO No:", "GS-DO-7781", "Date:", "20/10/2026"], ["Customer:", "Infinia Contracting LLC", "LPO No:", "IC/LPO/0412"], ["Site:", "Villa 909, Al Barari", "", ""]]), Spacer(1, 8),
    Table([["S.No", "Description", "Unit", "Qty"], ["1", "Rebar 12mm Grade 60", "ton", "2.5"], ["2", "Rebar 16mm Grade 60", "ton", "1.75"],
           ["3", "Binding wire 1.2mm", "roll", "10"]], style=GRID),
    Spacer(1, 20), P("Received in good condition: ____________________   Driver: Asif")])
dn_exp = {"supplier": "GULF STEEL TRADING LLC", "ref": "GS-DO-7781", "date": "2026-10-20", "lpo": "IC/LPO/0412",
          "items": [["Rebar 12mm Grade 60", 2.5], ["Rebar 16mm Grade 60", 1.75], ["Binding wire 1.2mm", 10]]}
res["delivery"] = {"file": dn, "expect": dn_exp}
res["delivery_scan"] = {"file": scan(dn, "Gulf Steel DO 7781 scanned.pdf"), "expect": dn_exp}

# 6. supplier quotation -> LPO
qt = pdf("Emirates Tiles quotation.pdf", [
    P("EMIRATES TILES &amp; SANITARY WARE TRADING LLC", "Title"), P("Showroom 12, Sheikh Zayed Road, Dubai    TRN: 100456789100003"), P("QUOTATION", "Heading2"),
    Table([["Quotation No:", "ETQ/26/1184", "Date:", "16/10/2026"], ["To:", "Infinia Contracting LLC", "Attn:", "Purchase Dept."]]), Spacer(1, 8),
    Table([["S.No", "Description", "Qty", "Unit", "Rate", "Amount"],
           ["1", "Porcelain tile 600x600 matt beige", "420", "sqm", "38.00", "15,960.00"],
           ["2", "Tile adhesive grey 20kg", "180", "bag", "21.50", "3,870.00"],
           ["3", "Tile grout 5kg white", "60", "bag", "18.00", "1,080.00"],
           ["", "Total (excluding VAT)", "", "", "", "20,910.00"]], style=GRID),
    Spacer(1, 8), P("Validity: 30 days. Delivery: 3 working days from LPO.")])
res["quotation"] = {"file": qt, "expect": {"supplier": "EMIRATES TILES & SANITARY WARE TRADING LLC", "ref": "ETQ/26/1184", "date": "2026-10-16", "trn": "100456789100003",
                                           "items": [["Porcelain tile 600x600 matt beige", 420, "sqm", 38], ["Tile adhesive grey 20kg", 180, "bag", 21.5], ["Tile grout 5kg white", 60, "bag", 18]]}}

# 7. ADCB statement as PDF -> bank statement
rows = [["Posting Date", "Value Date", "Description", "Debit", "Credit", "Balance"],
        ["01/10/2026", "01/10/2026", "Opening balance", "", "", "250,000.00"],
        ["02/10/2026", "02/10/2026", "O/W TRF734975811 DESARCH SCAFFOLDING", "12,500.00", "", "237,500.00"],
        ["05/10/2026", "05/10/2026", "INWARD TT EMAAR PJSC IPC 05 VILLA 909", "", "185,000.00", "422,500.00"],
        ["08/10/2026", "08/10/2026", "CHQ 000452 AL HASSAI BUILDING", "4,830.00", "", "417,670.00"],
        ["12/10/2026", "12/10/2026", "WPS SALARY SEP 2026", "96,400.00", "", "321,270.00"]]
bs = pdf("ADCB statement Oct 2026.pdf", [P("ABU DHABI COMMERCIAL BANK", "Title"), P("Account statement - Infinia Contracting LLC - A/C 12345678920001 - AED"),
                                         P("Period: 01/10/2026 to 15/10/2026"), Spacer(1, 8), Table(rows, style=GRID)])
bs_exp = {"lines": 5, "from": "2026-10-01", "to": "2026-10-12", "breaks": 0}
res["bank"] = {"file": bs, "expect": bs_exp}
res["bank_scan"] = {"file": scan(bs, "ADCB statement Oct 2026 scanned.pdf", 0.4), "expect": bs_exp}
print(json.dumps(res))
