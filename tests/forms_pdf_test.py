"""Admin > Forms: each blank form is one A4 page with its number, and its
pictures (card and preview) are there."""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import forms_pdf as F
from pypdf import PdfReader
fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
nos = set()
for k in F.ORDER:
    r = PdfReader(io.BytesIO(F.build(k).read()))
    t = r.pages[0].extract_text()
    ok(len(r.pages) == 1, f"{k}: one page")
    ok(F.FORMS[k]["no"] in t and F.FORMS[k]["title"] in t, f"{k}: number and title printed")
    ok(all(s.split(" (")[0] in t for s in F.FORMS[k]["sign"]), f"{k}: every signature printed")
    nos.add(F.FORMS[k]["no"])
    for suf in ("", "_page"):
        ok(os.path.exists(os.path.join(os.path.dirname(F.__file__), "form_thumbs", k + suf + ".png")), f"{k}{suf}: picture there")
ok(len(nos) == len(F.ORDER), "every form has its own number (the old passport forms shared IC/HR/001)")
print("fails=", fails)
