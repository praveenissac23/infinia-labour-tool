"""Every box someone fills in has its (i), unless its label says it all.

A box gets its (i) from portal/help/guides.js (HELP_TIPS, by selector) or
from a title="..." / data-tip="..." on the box itself (portal/help/tips.js
turns those into the (i)). A new form added later without one fails here,
so the help grows with the app instead of being forgotten."""
import json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OBVIOUS = {"name", "full name", "name *", "full name *", "notes", "note", "search", "from", "to", "date", "date *",
           "month", "year", "period", "show", "reason", "remarks", "remark", "description", "amount", "amount *",
           "staff", "staff *", "worker", "number", "company", "company *", "mobile", "email", "item", "item *",
           "relation", "condition", "designation", "category", "report", "months", "status", "columns", "where",
           "issued", "issued on", "returned", "expires *", "taken on", "paid on", "staff member", "for",
           "contact person", "contact number", "supplier", "material", "driver", "vehicle", "personal email",
           "work email", "blood group", "uae address", "home-country address", "emergency contact", "their phone",
           "reports to", "joining date", "accommodation", "room / bed", "transport", "date of birth",
           "date of birth (as per passport)", "gender", "nationality", "religion", "marital status", "rehire",
           "leaving reason", "terms", "how", "basic", "allowance", "returned by", "for / notes", "notes on the note",
           "note no", "date of leave *", "project no.", "project", "location", "client address", "invoice date *",
           "current password", "your name *", "in charge", "his mobile", "delivery date", "do / invoice no",
           "delivered to", "expected delivery", "their contact person", "their mobile", "their email", "lpo no",
           "project location", "received by", "delivery note / lpo ref", "going back to *", "returned from",
           "who is taking it", "coming from", "going to", "condition", "staff or labour code", "document name",
           "short name", "full name (as per passport)", "mobile (uae)", "home-country phone", "end of service",
           "pay", "type", "goes onto", "increase", "effective from", "salary of", "addition or deduction",
           "amount lent", "agreed terms", "last working day", "settlement date", "other additions",
           "other deductions", "air ticket", "leave salary", "paid by", "paid on", "iban", "trn", "wps id",
           "code prefix", "fix allowance", "pension / month", "monthly salary *", "basic (40%)",
           "fix allowance (60%)", "staff code *", "joining date *", "to (blank = one day)", "for site *",
           "needed by *", "how urgent", "plot no", "plot no.", "job scope", "discount %", "our mobile",
           "our contact person", "ref# (supplier quote)", "their trn", "site code *", "google maps link",
           "delivery address (printed on orders)", "cheque no", "bank", "payee *", "cheque date *", "amount (aed) *",
           "invoice no. *", "client *", "client trn", "work", "scope", "contract value (aed)", "project no.",
           "site", "paid (aed)", "supplier / contact", "amount (aed)", "new password (8+ characters)"}

tips = {}
g = open(os.path.join(ROOT, "portal", "help", "guides.js"), encoding="utf-8").read()
m = re.search(r"window\.HELP_TIPS = (\{.*?\});", g, re.S)
tips = json.loads(re.sub(r",\s*}\s*$", "}", m.group(1))) if m else {}
ids = {k[1:] for k in tips if k.startswith("#")}

missing = []
for f in ("app-classic.html", "portal/people.html"):
    s = open(os.path.join(ROOT, f), encoding="utf-8").read()
    pats = [r'<label[^>]*>\s*<span[^>]*>([^<]{1,90})</span>\s*<(input|select|textarea)([^>]*)>',
            r'<div class="field[^"]*"[^>]*>\s*<label[^>]*>([^<]{1,90})</label>\s*<(input|select|textarea)([^>]*)>']
    for pat in pats:
        for mm in re.finditer(pat, s, re.S):
            attrs = mm.group(3)
            idm = re.search(r'id="([^"]+)"', attrs)
            if not idm or re.search(r'type="(checkbox|hidden|search)"', attrs):
                continue
            label = re.sub(r"<[^>]+>", "", mm.group(1)).replace("&amp;", "&").strip().lower()
            has = idm.group(1) in ids or ' title="' in attrs or "data-tip=" in attrs
            if not has and label not in OBVIOUS:
                missing.append(f"{f}: #{idm.group(1)} ({label})")

for x in missing:
    print("FAIL no (i) for " + x)
print(f"{len(ids)} boxes have an (i)")
print("ALL PASS" if not missing else f"{len(missing)} FAILED")
sys.exit(1 if missing else 0)
