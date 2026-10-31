"""Dates inside stored text read dd/mm/yyyy on the way out (app/dmytext.py).

Run: python3 tests/dmytext_test.py
"""
import os, sys
from datetime import date, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from dmytext import dmy_text

fails = 0
def ok(got, want, why):
    global fails
    good = got == want
    fails += 0 if good else 1
    print(("PASS " if good else "FAIL ") + why + ("" if good else f"  got {got!r}, want {want!r}"))

# activity-log text with ISO dates
ok(dmy_text("F-749 JITENDRA KUMAR Passport -> 2027-07-12"), "F-749 JITENDRA KUMAR Passport -> 12/07/2027", "ISO date in a log line")
ok(dmy_text("saved 2026-10-05T14:03:22.123+00:00"), "saved 05/10/2026 14:03", "ISO date and time")
ok(dmy_text("Daily_Report_2026-10-05.xlsx"), "Daily_Report_2026-10-05.xlsx", "a file name is left alone")
ok(dmy_text("IPA 07 - 2026-13-45"), "IPA 07 - 2026-13-45", "not a real date: left alone")
# vacation / absence notes written before dd/mm/yyyy (no year: taken from the row)
ok(dmy_text("Vacation 5 Oct - 18 Oct", date(2026, 10, 5)), "Vacation 05/10/2026 - 18/10/2026", "old vacation note")
ok(dmy_text("Vacation 5-18 Oct", "October 2026"), "Vacation 05/10/2026 - 18/10/2026", "old day run note")
ok(dmy_text("Sick 9 Sep; Absent 17 Sep (half)", "September 2026"), "Sick 09/09/2026; Absent 17/09/2026 (half)", "old absence note")
ok(dmy_text("Joined 12 oct - 11 day(s) not employed", "October 2026"), "Joined 12/10/2026 - 11 day(s) not employed", "small-letter month on a dated row")
ok(dmy_text("01 Jan", date(2026, 12, 30)), "01/01/2027", "the year nearest the row's date")
ok(dmy_text("Vacation 5-18 Oct"), "Vacation 5-18 Oct", "no year and nothing to take it from: left as written")
ok(dmy_text("pays 500 may change", "October 2026"), "pays 500 may change", "'may' the word is not a month")
# full dates
ok(dmy_text("Opening count 01-Sep-2026"), "Opening count 01/09/2026", "dd-Mon-yyyy")
ok(dmy_text("arriving 28 Oct 2026"), "arriving 28/10/2026", "d Mon yyyy")
ok(dmy_text("05 Oct - 10 Oct 2026"), "05/10/2026 - 10/10/2026", "range takes the year of its end")
ok(dmy_text("Oct 5, 2026"), "05/10/2026", "Mon d, yyyy")
ok(dmy_text("30 Oct, 2:05 PM", datetime(2026, 10, 30, 10)), "30/10/2026 14:05", "12-hour time becomes 24-hour")
ok(dmy_text("21-Oct-26"), "21/10/2026", "dd-Mon-yy")
# left alone
for t in ("October 2026", "on 22/10/2026 from", "Qty 5 Oct", "2 Marble slabs", "", None):
    ok(dmy_text(t), t, f"unchanged: {t!r}")

print("ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
