# Order tracker - how the purchasing cycle works (guide for Arun, Amal and Shafeeq), 02 Nov 2026
import sys
sys.path.insert(0, "/home/claude/infinia-labour-tool/app")
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak, Image
from PIL import Image as PI
RED, DARK, MAROON, GREY, LIGHT = colors.HexColor("#C0392B"), colors.HexColor("#2E3238"), colors.HexColor("#7B1F1A"), colors.HexColor("#6B6B6B"), colors.HexColor("#F6F1EF")
LOGO = "/home/claude/infinia-labour-tool/app/logo.png"; G = "/tmp/claude-0/guide/"
OUT = "/tmp/claude-0/Order_Tracker_Guide_02Nov2026.pdf"
def S(size=9.5, bold=False, color=DARK, lead=None, align=0, space=0):
    return ParagraphStyle("x", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size, leading=lead or size * 1.35, textColor=color, alignment=align, spaceAfter=space)
P = lambda t, **k: Paragraph(t, S(**k))
doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm, title="Order tracker - how it works", author="Infinia Contracting L.L.C.")
W = doc.width
el = []
def footer(c, d):
    c.saveState(); c.setFont("Helvetica", 7.5); c.setFillColor(GREY)
    c.drawString(14 * mm, 8 * mm, "Infinia Contracting L.L.C. - Order tracker, how it works - 02/11/2026")
    c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {d.page}"); c.restoreState()
def pic(name, width=W):
    im = PI.open(G + name + ".png"); w, h = im.size; wd = min(width, W); ht = wd * h / w
    if ht > 105 * mm: ht = 105 * mm; wd = ht * w / h
    t = Table([[Image(G + name + ".png", width=wd, height=ht)]], colWidths=[wd])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D2CE")), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t
def section(n, t, who):
    s = Table([[P(f"{n}", size=11, bold=True, color=colors.white, align=1), P(t, size=11, bold=True, color=colors.white), P(who, size=9, color=colors.white, align=2)]], colWidths=[10 * mm, W - 50 * mm, 40 * mm])
    s.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MAROON), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el.append(Spacer(1, 5)); el.append(s); el.append(Spacer(1, 4))
def step(n, title, who, text, shot=None, width=W):
    block = [section(n, title, who) or el.pop(), el.pop(), el.pop()]   # section() appended 3 items; pull them back in order
    block = block[::-1]
    items = block + [P(text, size=9.5, lead=13, space=4)]
    if shot: items += [pic(shot, width), Spacer(1, 2)]
    el.append(KeepTogether(items))

# ---- cover
head = Table([[Image(LOGO, width=50 * mm, height=50 * mm * 0.27),
               [P("ORDER TRACKER", size=16, bold=True, color=MAROON, align=2), P("How the purchasing cycle works - one screen for everyone", size=9.5, color=MAROON, bold=True, align=2)]]], colWidths=[W * 0.45, W * 0.55])
head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, RED), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
el += [head, Spacer(1, 6)]
el.append(Table([[P("<b>For</b>  Arun (purchaser), Amal (store keeper), Shafeeq (accounts), site engineers", size=9), P("<b>From</b>  Praveen Isaac Shaji", size=9), P("<b>Date</b>  02/11/2026", size=9)]],
                colWidths=[W * 0.52, W * 0.28, W * 0.2], style=[("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
el.append(Spacer(1, 8))
el.append(P("From today every request and LPO is followed on <b>one screen</b>: <b>Store &amp; Purchasing &gt; Order tracker</b>. "
            "The old Approvals and Order follow-up tabs are gone - every button they had is on the tracker, so nobody has to look in three places. "
            "Each order is one line, and the coloured strip shows the step it has reached:", size=9.5, lead=13.5, space=6))
steps = [("Requested", "the site asked for it", "Arun"), ("Approved", "Arun approved it (all, less, or some materials rejected)", "Arun"),
         ("Ordered", "an LPO is raised - the supplier, contact and phone are on the line", "Amal"), ("Arrived", "Amal booked the delivery (all or part)", "Arun"),
         ("Bill checked", "Arun checked the supplier's bill against the LPO and the DN", "Shafeeq"), ("Done", "sent to Zoho", "-")]
t = Table([[P("<b>Step</b>", size=9, color=colors.white), P("<b>Means</b>", size=9, color=colors.white), P("<b>Next is</b>", size=9, color=colors.white)]] + [[P(f"<b>{a}</b>", size=9), P(b, size=9), P(c, size=9)] for a, b, c in steps], colWidths=[28 * mm, W - 58 * mm, 30 * mm])
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), MAROON), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CFC6C2")), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
el += [t, Spacer(1, 6)]
el.append(P("<b>Colours on the strip:</b> green = on time, <font color='#C0392B'><b>red</b></font> = late (past the needed-by / delivery date), "
            "<font color='#E09A1A'><b>orange</b></font> = only part came (<b>Short</b> = the supplier sent less, <b>On hold</b> = the site asked to hold the rest). "
            "<b>Buttons on a line:</b> one red button = the next step (Approve, Raise LPO, Book delivery, Check bill, Send to Zoho) and <b>More</b> = everything else. "
            "Tapping the line opens the same pop-up. <b>My turn</b> shows only what is waiting on you; <b>Late</b>, <b>All open</b> and <b>Done &amp; closed</b> the rest. "
            "Preview / Export PDF / Export Excel / Share print exactly what is on screen.", size=9.5, lead=13.5))
el.append(Spacer(1, 4))

step("1", "The site raises a request", "Site engineer / Amal",
     "Store &amp; Purchasing &gt; Requests &gt; Material requests, as before: site, who is asking, needed by, the materials with quantity and what for. It then shows on the tracker at <b>Requested</b>, with Arun to approve.", "01_request", W * 0.85)
step("2", "Arun approves - all, less, or some rejected", "Arun",
     "On the tracker (My turn) press <b>Approve</b>. Each material has its own choice: <b>Approve</b>, <b>Approve less</b> (type how many - the request then asks for that many, the reason is kept) or <b>Reject</b> (say why). Approve all / Reject all do the whole request. Save decision.", "03_approve", W * 0.8)
step("3", "One material at a time, any time", "Arun / Amal",
     "<b>More &gt; Materials one by one</b> opens the request in full. Every material has its own buttons: <b>Reduce</b>, <b>Not needed</b> (only that material is taken off - the rest of the request goes on; MR-0061: the solid blocks stay, the hollow ones go), "
     "<b>It arrived</b> (Amal - it came another way: delivered direct, petty cash, from the store, already on Rentals; a note is asked; no stock is added here), <b>Add to item list</b> for a material not on the list yet. "
     "If a material is already on a live LPO the button says <b>Change LPO</b> instead - it is taken off or reduced there, so nothing stays ordered by mistake.", "05_materials", W * 0.8)
step("4", "Arun raises the LPO", "Arun",
     "Press <b>Raise LPO</b>: Purchase orders opens with those materials already ticked and the order filled in - check the supplier, the rates and Save &amp; Generate. "
     "Materials from several requests going to one supplier: tick them together on the Purchase orders screen as before. The order then reads <b>Ordered</b>, with the supplier's contact and number (tap to ring), and Amal is next.", "07_ordered", W * 0.85)
step("5", "Amal books the delivery", "Amal",
     "<b>Book delivery</b>: DN number, DN date, delivered to, how much of each line came. Everything: 'Everything still to come arrived'. "
     "<b>Only part came: say why</b> - <b>Supplier sent less</b> or <b>Site asked to hold the rest</b>, with a note (balance next week...). The tracker then shows <b>Short</b> or <b>On hold</b> with the note, so everyone knows whether to chase the supplier or wait for the site. "
     "Tick 'rest not coming' when the rest will never come - it is closed, not left to come.", "10_delivery", W * 0.8)
step("6", "What the tracker shows after a part delivery", "Everyone",
     "The line reads <b>On hold</b> (or <b>Short</b>), what is still to come, and the note. <b>More</b> has <b>Close - rest not needed</b> when the site's requirement changed: the rest is closed with a reason, no stock moves, and the bill to expect is what came.", "11_on_hold", W * 0.85)
step("7", "Arun checks the bill", "Arun",
     "<b>Check bill</b>: bill number, date and amount. The difference to the LPO total is shown at once (round off included). Tick 'Checked against the LPO and the delivery note' and Save. The order reads <b>Bill checked</b> and Shafeeq is next. A bill that differs is still saved - write why in the note.", "14_bill", W * 0.55)
step("8", "Shafeeq sends it to Zoho", "Shafeeq",
     "<b>Send to Zoho</b> opens Accounts &gt; Send to Zoho, as before. Once sent, the order reads <b>Done</b>. Done &amp; closed lists everything finished, closed or cancelled, with the reason.", "15_shafeeq", W * 0.85)
step("9", "Old orders from before Arun joined", "Arun",
     "<b>Close old orders</b>: tick the ones nobody knows about, choose <b>Came earlier - no stock added</b> (it arrived and was used, but was never booked) or <b>Not coming / not needed</b>, tick 'Also close the bill check' if the bill is already with accounts, give the reason, Close ticked. "
     "<b>Delete ticked requests</b> deletes the requests nothing was ever done on. One order at a time: <b>More &gt; Close as it stands</b>. Nothing moves in stock, no amount changes - paperwork only, and it is all in the activity log.", "13_close_old", W * 0.85)

el.append(PageBreak())
section("", "Where did the old buttons go?", "")
rows = [["Approvals: Approve / Reject a line", "Tracker: Approve (waiting request), or More > Materials one by one"],
        ["Approvals: Record delivery (petty cash / no LPO)", "More > Record what arrived, or It arrived on the material"],
        ["Approvals: Add to item list", "More > Materials one by one > Add to item list"],
        ["Approvals: Delete / Delete selected", "More > Delete the request; Close old orders > Delete ticked requests"],
        ["Approvals: Request PDF / Preview", "More > Request PDF"],
        ["Approvals: Show all (closed, rejected)", "Done & closed chip"],
        ["Order follow-up: who to call, late", "Supplier column (tap the number), Late chip, red step"],
        ["Order follow-up: It arrived / Already booked in", "More > Materials one by one > It arrived (with a note)"],
        ["Order follow-up: Edit my request", "More > Materials one by one > Edit request (while untouched)"],
        ["Purchase orders: Generate LPO from ticked", "Unchanged - and Raise LPO on the tracker opens it filled"]]
t = Table([[P("<b>Before</b>", size=9, color=colors.white), P("<b>Now</b>", size=9, color=colors.white)]] + [[P(a, size=9), P(b, size=9)] for a, b in rows], colWidths=[W * 0.42, W * 0.58])
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), MAROON), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CFC6C2")), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
el += [t, Spacer(1, 10)]
el.append(P("<b>Three rules that keep the figures right.</b> Nothing on the tracker changes stock or money by itself: stock moves only when Amal books a delivery on Material arrived / Book delivery; "
            "'It arrived', 'Not needed', 'Close as it stands' and 'Close old orders' change the paperwork only. A reason is always asked and kept. Anything you cannot find: send me a screenshot and I will point to it.", size=9.5, lead=13.5))
el.append(Spacer(1, 14))
el.append(KeepTogether([Table([[P("Praveen Isaac Shaji<br/>Managing Partner", size=9)]], colWidths=[70 * mm], style=[("LINEABOVE", (0, 0), (0, 0), 0.6, DARK), ("TOPPADDING", (0, 0), (-1, -1), 4)])]))
doc.build(el, onFirstPage=footer, onLaterPages=footer)
print("ok", OUT)
