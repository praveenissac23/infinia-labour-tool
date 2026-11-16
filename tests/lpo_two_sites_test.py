"""LPO for two sites (16 Nov 2026): Project location '912,925' prints every site's plot and delivery address, each
with its site; a plot typed by hand wins; one site prints as before."""
import os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
import main as M, models
from database import SessionLocal
from types import SimpleNamespace as NS
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x!r}"))
    if not ok: fails.append(n)
db = SessionLocal()
for code, plot, addr in (("T912", "3473253", "SOBHA HARTLAND-WS37"), ("T925", "3471006", "SOBHA HARTLAND-VE225"), ("T926", "", "")):
    db.add(models.Site(code=code, plot_no=plot, address=addr))
db.commit()
O = lambda loc, plot="": NS(project_location=loc, plot_no=plot)
ck("two sites: both plots, each with its site", M.lpo_plot_text(O("T912,T925", "3473253")) == "T912: 3473253 / T925: 3471006", M.lpo_plot_text(O("T912,T925", "3473253")))
ck("...also when the plot box is empty", M.lpo_plot_text(O("T912, T925")) == "T912: 3473253 / T925: 3471006")
ck("...written with / or &", M.lpo_plot_text(O("T912 / T925")) == M.lpo_plot_text(O("T912 & T925")) == "T912: 3473253 / T925: 3471006")
ck("a plot typed by hand wins", M.lpo_plot_text(O("T912,T925", "Plots 3473253 & 3471006")) == "Plots 3473253 & 3471006")
ck("one site: as typed", M.lpo_plot_text(O("T912", "3473253")) == "3473253")
ck("second site has no plot: as typed", M.lpo_plot_text(O("T912,T926", "3473253")) == "3473253")
ck("an unknown site: as typed", M.lpo_plot_text(O("T912,XYZ", "3473253")) == "3473253")
ck("delivery address: both, each with its site", M.lpo_address_text(O("T912,T925")) == "T912: SOBHA HARTLAND-WS37 / T925: SOBHA HARTLAND-VE225", M.lpo_address_text(O("T912,T925")))
ck("delivery address: one site", M.lpo_address_text(O("T912")) == "SOBHA HARTLAND-WS37")
ck("delivery address: none", M.lpo_address_text(O("")) == "" and M.lpo_address_text(O("T926")) == "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "app-classic.html"), encoding="utf-8").read()
ck("the form fills every site's plot", "function lpoPlotFor" in html and "lpoPlotFor(sites.join" in html)
print("\nFAILED: " + ", ".join(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
