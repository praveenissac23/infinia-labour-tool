"""Subcontractor payment certificate - the new certificate page (20/11/2026, Praveen): details in ruled tables, one
numbered payment summary (additions green, deductions red), deductions shown only when not zero, and the money
beside the advance and retention % in the payment terms. Checked on the real IPC-10 of project 906 (AL RAIDA, HVAC)
and on the same certificate with deductions, an advance certificate, variations and material on site."""
import os, sys, types, tempfile, subprocess
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
import main  # noqa: F401  (loads the app in its usual order)
import est_pcsheet as S

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  {x}'))
    if not ok: FAIL.append(l)

NS = types.SimpleNamespace
TERMS = ("Lumpsum contract:\n•10% Advance payment against undated company guarantee cheque upon signing agreement\n"
         "–AED10,000/- of the advance payment shall be released upon signed of agreement for preparation of shop drawings.\n"
         "•100% progressive payment will be released after certification issued from project engineer with recovery of advance and retention.\n"
         "•10% Retention")
sub = NS(value=560000.0, adv_pct=10.0, ret_pct=10.0, vat_pct=5.0, adv_rec_mode="", adv_rec_pct=None, adv_rec_from=1, pay_terms=TERMS,
         contract_type="Lumpsum contract", agreement="IC/906/SCA/03/24", lpo="", agreement_date=date(2024, 10, 7), start_date=date(2024, 10, 23),
         scope="HEATING, VENTILATION & AIR CONDITIONING (HVAC) WORKS")
proj = NS(name="CONSTRUCTION OF B+G+1+R RESIDENTIAL VILLA, PLOT NO.: 1340717, AL MAMZAR, DUBAI, UAE", code="906")


def ipc10(**kw):
    pc = NS(seq=10, measured_on=date(2026, 11, 19), inv_ref="INV/ALA/AREMS-1098 /26", inv_date=date(2026, 11, 17), received=date(2026, 11, 18),
            issued=date(2026, 11, 20), remarks="Progressive Payment + 5% Retention release", adv_rec_cum=54880.0, ret_cum=54880.0,
            ret_rel_cum=27440.0, other_note="", work_cum=548800.0, other_cum=0.0, adv_amount=0.0)
    for k, v in kw.items():
        setattr(pc, k, v)
    return pc


rest = [NS(seq=n) for n in range(4, 10)]
calc = {"vat": 2044.0, "payable": 42924.0}
cats0 = {k: 0.0 for k in S.DED_CATS}
cv = S.cover_page(sub, ipc10(), proj, ("", ""), {"sub": {"vo_total": 0, "revised": 560000.0}}, 548800.0, 0.0, 548800.0, 56000.0, 56000.0, rest,
                  481600.0, cats0, [], 0.0, 0.0, calc, 3)
rows = cv["rows"]
lab = [r[1] for r in rows]
amt = {r[1]: r[3] for r in rows}
ck("IPC-10: 8 lines, as on the approved preview", lab == ["Value of work executed to date", "Less: Advance payment recovery", "Less: Retention, net",
   "Net value certified to date", "Less: Previously certified", "Net amount due for this IPC", "VAT", "TOTAL AMOUNT DUE FOR PAYMENT"], lab)
ck("no deductions line when there are none", "Less: Deductions" not in lab)
ck("figures: 548,800 - 54,880 - 27,440 = 466,480; - 425,600 = 40,880; VAT 2,044; total 42,924",
   (amt["Value of work executed to date"], amt["Less: Advance payment recovery"], amt["Less: Retention, net"], amt["Net value certified to date"],
    amt["Less: Previously certified"], amt["Net amount due for this IPC"], amt["VAT"], amt["TOTAL AMOUNT DUE FOR PAYMENT"])
   == (548800.0, -54880.0, -27440.0, 466480.0, -425600.0, 40880.0, 2044.0, 42924.0), amt)
ck("each line adds up (net = sum of lines above it)", abs(sum(r[3] for r in rows[:3]) - rows[3][3]) < .005 and abs(rows[3][3] + rows[4][3] - rows[5][3]) < .005)
ck("references: 1 - 2 - 3, 4 - 5, 5% of line 6, 6 + 7", [r[2] for r in rows[3:]] == ["1 - 2 - 3", "IPC-04 to IPC-09 excl. advance (Appendix B)", "4 - 5", "5% of line 6", "6 + 7"], [r[2] for r in rows[3:]])
ck("basis of line 1: 98% of contract value, as on 19/11/2026", rows[0][2] == "98% of contract value · as on 19/11/2026", rows[0][2])
ck("retention basis shows held and released", rows[2][2] == "10% held (54,880.00) - 5% released (27,440.00)", rows[2][2])
ck("kinds: additions green, deductions red, totals", [r[0] for r in rows] == ["add", "less", "less", "sub", "less", "sub", "plain", "total"])
t = " ".join(cv["terms"])
ck("payment terms: 10% (AED 56,000.00) beside the advance", "10% (AED 56,000.00) Advance payment" in t, t[:200])
ck("payment terms: 10% (AED 54,880.00 held to date) beside the retention", "10% (AED 54,880.00 held to date) Retention" in t, t[-80:])
ck("payment terms: 100% progressive left as written; AED 10,000 line untouched", "•100% progressive" in t and "–AED10,000/-" in t)
ck("details: dates DD/MM/YYYY, agreement date beside the ref",
   (("Agreement Ref.", "IC/906/SCA/03/24"), ("Agreement Date", "07/10/2024")) in cv["grid"] and (("Commencement Date", "23/10/2024"), ("Measurement Date", "19/11/2026")) in cv["grid"])
ck("details: empty client / plot pair left off", not any(a[0] == "Client" for a, b in cv["grid"]))

# the same certificate with deductions: line 4, numbers move on
cats = dict(cats0, Material=1150.0, Other=500.0)
calc2 = {"vat": 1961.5, "payable": 41191.5}
cv2 = S.cover_page(sub, ipc10(other_cum=1650.0), proj, ("", ""), {"sub": {"vo_total": 0, "revised": 560000.0}}, 548800.0, 0.0, 548800.0, 56000.0, 56000.0, rest,
                   481600.0, cats, [{"x": 1}], 0.0, 0.0, calc2, 3)
r2 = cv2["rows"]
ck("with deductions: 'Less: Deductions' is line 4, above the net value", r2[3][1] == "Less: Deductions" and r2[3][3] == -1650.0 and r2[4][1] == "Net value certified to date", [x[1] for x in r2])
ck("... basis names Appendix C and the kinds", r2[3][2] == "Appendix C · Material, Other", r2[3][2])
ck("... net 464,830, due 39,230, total 41,191.50; references renumbered",
   r2[4][3] == 464830.0 and r2[6][3] == 39230.0 and r2[-1][3] == 41191.5 and r2[4][2] == "1 - 2 - 3 - 4" and r2[6][2] == "5 - 6" and r2[-1][2] == "7 + 8", [(x[2], x[3]) for x in r2])
# typed "other" deduction on an old certificate (no deduction lines)
cv3 = S.cover_page(sub, ipc10(other_note="Fence damage", other_cum=300.0), proj, ("", ""), {"sub": {"vo_total": 0, "revised": 560000.0}}, 548800.0, 0.0, 548800.0, 56000.0, 56000.0,
                   rest, 481600.0, cats0, [], 300.0, 0.0, calc, 3)
ck("an old typed deduction shows too, with its note", any(r[1] == "Less: Deductions" and r[3] == -300.0 and "Fence damage" in r[2] for r in cv3["rows"]))

# an advance certificate (nothing before it): the advance is an addition, previously paid 0
pcA = ipc10(seq=1, adv_rec_cum=0.0, ret_cum=0.0, ret_rel_cum=0.0, work_cum=0.0, remarks="", adv_amount=10000.0)
cvA = S.cover_page(sub, pcA, proj, ("", ""), {"sub": {"vo_total": 0, "revised": 560000.0}}, 0.0, 0.0, 0.0, 10000.0, 0.0, [], 0.0, cats0, [], 0.0, 0.0,
                   {"vat": 500.0, "payable": 10500.0}, 0)
la = [(r[1], r[3]) for r in cvA["rows"]]
ck("advance certificate: 'Add: Advance payment' 10,000, nothing previously paid, total 10,500",
   ("Add: Advance payment", 10000.0) in la and ("Less: Previously certified", -0.0) in la or ("Less: Previously certified", 0.0) in la, la)
ck("advance certificate: due 10,000", ("Net amount due for this IPC", 10000.0) in la, la)
# variations and material on site: green additions, revised contract value shown
cvV = S.cover_page(sub, ipc10(), proj, ("Mr. X", "1340717"), {"sub": {"vo_total": 20000.0, "revised": 580000.0}}, 548800.0, 12000.0, 560800.0, 56000.0, 56000.0,
                   rest, 481600.0, cats0, [], 0.0, 3000.0, calc, 3)
k = [(r[0], r[1]) for r in cvV["rows"]]
ck("variations and material on site: green 'Add' lines 2 and 3, net reads 1 + 2 + 3 - 4 - 5",
   k[1] == ("add", "Add: Approved variations executed to date") and k[2] == ("add", "Add: Material on site") and cvV["rows"][5][2] == "1 + 2 + 3 - 4 - 5", cvV["rows"][:6])
ck("variations: approved variations and revised contract value in the contract table",
   (("Approved Variations", "AED 20,000.00"), ("Revised Contract Value", "AED 580,000.00")) in cvV["contract"], cvV["contract"])
ck("client and plot shown when known", (("Client", "Mr. X"), ("Plot No.", "1340717")) in cvV["grid"])
# deductions come from the certificate's own figure (a paid PC keeps it even if a line was moved later)
cvP = S.cover_page(sub, ipc10(other_cum=400.0), proj, ("", ""), {"sub": {"vo_total": 0, "revised": 560000.0}}, 548800.0, 0.0, 548800.0, 56000.0, 56000.0, rest,
                   481600.0, dict(cats0, Material=1150.0), [{"x": 1}], 0.0, 0.0, calc, 3)
ck("deductions line = the certificate's own deducted figure, not re-added from the lines", any(r[1] == "Less: Deductions" and r[3] == -400.0 for r in cvP["rows"]), cvP["rows"])
# advance read from a previous bill onto an interim PC: no 'Add: Advance payment' on later certificates
cvI = S.cover_page(sub, ipc10(), proj, ("", ""), {"sub": {"vo_total": 0, "revised": 560000.0}}, 548800.0, 0.0, 548800.0, 56000.0, 56000.0, [NS(seq=n) for n in range(1, 10)],
                   481600.0, cats0, [], 0.0, 0.0, calc, 0)
ck("advance carried in from an earlier interim PC: no advance line now, previously certified 425,600, due 40,880",
   not any(r[1] == "Add: Advance payment" for r in cvI["rows"]) and any(r[1] == "Less: Previously certified" and r[3] == -425600.0 for r in cvI["rows"])
   and any(r[1] == "Net amount due for this IPC" and r[3] == 40880.0 for r in cvI["rows"]), cvI["rows"])
ck("Appendix B figures for the carried line", cv["prev_certified"] == 425600.0 and cv["adv_before"] == 56000.0 and cv["prev_line"] == 5, (cv["prev_certified"], cv["adv_before"], cv["prev_line"]))
# terms: several percentages on one line - each gets the money of its own clause
T = lambda x: S.terms_with_values(x, 10, 56000, 10, 54880)
ck("terms: '10% Advance, 10% Retention' each with its own amount", T("10% Advance, 10% Retention, balance against progress") == ["10% (AED 56,000.00) Advance, 10% (AED 54,880.00 held to date) Retention, balance against progress"], T("10% Advance, 10% Retention, balance against progress"))
ck("terms: 'Retention 10% of each bill; Advance 10% upfront'", T("Retention 10% of each bill; Advance 10% upfront") == ["Retention 10% (AED 54,880.00 held to date) of each bill; Advance 10% (AED 56,000.00) upfront"], T("Retention 10% of each bill; Advance 10% upfront"))
ck("terms: VAT next to retention is left alone", S.terms_with_values("5% Retention, 5% VAT extra", 0, 0, 5, 1000) == ["5% (AED 1,000.00 held to date) Retention, 5% VAT extra"], S.terms_with_values("5% Retention, 5% VAT extra", 0, 0, 5, 1000))
ck("terms: recovery clause untouched, the advance clause after it gets the amount", T("Advance recovery 10% from each bill; 10% advance on signing") == ["Advance recovery 10% from each bill; 10% (AED 56,000.00) advance on signing"], T("Advance recovery 10% from each bill; 10% advance on signing"))
ck("terms: a decimal % (10.5%) is not split as a clause end", S.terms_with_values("10.5% advance", 10.5, 1000, 0, 0) == ["10.5% (AED 1,000.00) advance"], S.terms_with_values("10.5% advance", 10.5, 1000, 0, 0))
ck("terms: retention release clause untouched", T("5% retention release on handover") == ["5% retention release on handover"])
# terms: other wordings
tw = S.terms_with_values("Advance 20% against bank guarantee\nRetention: 5%\nRecovery of advance 20% from each bill", 20, 50000, 5, 1234.5)
ck("terms: 'Advance 20%' and 'Retention: 5%' get their values", tw[0] == "Advance 20% (AED 50,000.00) against bank guarantee" and tw[1] == "Retention: 5% (AED 1,234.50 held to date)", tw)
ck("terms: no value is added twice when the text already has one", S.terms_with_values("10% (AED 56,000.00) advance", 10, 56000, 0, 0) == ["10% (AED 56,000.00) advance"])
ck("terms: empty terms stay empty", S.terms_with_values("", 10, 1, 10, 1) == [])
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED'))
sys.exit(1 if FAIL else 0)
