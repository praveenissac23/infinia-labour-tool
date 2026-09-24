"""
Database models - the web equivalent of master_data.py (file-based JSON)
and the in-memory dataclasses in data_engine.py (DailyRow, EmployeeSummary,
SalaryAdjustment). Field names match those dataclasses closely on purpose,
so the calculation functions in data_engine.py/daily_attendance.py can be
reused with minimal translation - only the storage layer changes, not the
payroll logic itself.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey,
    UniqueConstraint, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    """
    A staff login. Roles are deliberately simple to start: 'admin' can
    edit Master Data and everything else; 'staff' can enter attendance
    and view reports but not edit Master Data or salary figures. More
    granular roles can be added later without a schema rewrite, since
    this is just a string column, not a fixed enum baked into the DB.
    """
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="staff")
    # Comma-separated list of screens this user may open, e.g.
    # "dashboard,store,reports". Empty means "use the role default",
    # so existing users keep working unchanged. Admin ignores it and
    # always has everything.
    permissions = Column(Text, default="")  # "admin" | "staff"
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    emp_no = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    trade = Column(String, default="")
    # Workers are employed by one of two companies. Everyone already on
    # the books is Infinia, which is why that is the default - nobody
    # has to go back and set it on hundreds of existing records.
    company = Column(String, default="Infinia")
    # How the man is paid. "daily": a labourer, paid per paid day, and
    # an absence is both a day not earned and a day deducted. "fixed":
    # a foreman or driver on a monthly figure, paid the whole salary
    # less one day's rate per absence. Everyone starts daily.
    pay_type = Column(String, default="daily")
    # The day the man left. Empty for anyone still employed. He keeps
    # his card for the cycle he left in - the days he worked still have
    # to be paid - and drops off from the next cycle onwards, while
    # every past cycle still shows him exactly as he was.
    terminated_on = Column(Date, nullable=True)
    total_salary = Column(Float, default=0.0)
    basic_salary = Column(Float, default=0.0)

    # ---- The office side of the same record --------------------------
    # A labourer and an accountant are both people: the same joining
    # date, the same documents, the same end of service. What differs is
    # how they are paid, which is what `staff` marks.
    staff = Column(Boolean, default=False)         # monthly office staff
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    joined_on = Column(Date, nullable=True)        # service runs from here
    designation = Column(String, default="")       # QS, Accounts, Project Engineer
    # Basic and allowance are two independent figures, not a ratio. New
    # joiners start 40/60; an increment goes to the allowance and leaves
    # basic where it is, so the gratuity liability does not climb.
    allowance = Column(Float, default=0.0)
    # What the registered MOHRE contract says the basic is. As
    # increments accumulate in the allowance the two drift apart, and
    # that gap is what a dispute turns on - so it is on screen rather
    # than discovered later.
    contract_basic = Column(Float, default=0.0)
    pay_route = Column(String, default="wps")      # wps | bank | cash
    iban = Column(String, default="")
    # Nationals contribute to GPSSA and accrue no end-of-service
    # gratuity; everyone else accrues gratuity and pays no pension.
    scheme = Column(String, default="gratuity")    # gratuity | pension
    pension = Column(Float, default=0.0)           # the monthly GPSSA figure
    # Which statement the person is paid on. "staff" is the monthly office
    # payroll; "local" is the separate one processed early in the month -
    # the nationals and the household staff. Kept apart from `scheme`
    # because a maid is on the local statement but earns gratuity.
    pay_group = Column(String, default="staff")    # staff | local
    probation_end = Column(Date, nullable=True)
    notice_days = Column(Integer, default=30)

    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    daily_rows = relationship("DailyRow", back_populates="employee", cascade="all, delete-orphan")
    summaries = relationship("EmployeeSummary", back_populates="employee", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    # What a purchase order needs printed about the project. Typed once
    # here, so raising an order for site 907 does not mean typing its
    # plot number and its engineer again every time.
    plot_no = Column(String, default="")
    project_name = Column(String, default="")
    incharge = Column(String, default="")          # our man on site
    incharge_mobile = Column(String, default="")
    # Where the lorry actually goes. A plot number means nothing to a
    # driver who has not been there; a map link does.
    address = Column(Text, default="")
    map_url = Column(String, default="")
    active = Column(Boolean, default=True)


class Setting(Base):
    """Small company-wide values that are not worth a table each - the
    store in-charge whose name goes on a purchase order, and whatever
    comes after it."""
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text, default="")


class Engineer(Base):
    __tablename__ = "engineers"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    # The number a supplier rings when this man's request becomes an
    # order. Kept here so it is typed once, not on every order.
    mobile = Column(String, default="")
    active = Column(Boolean, default=True)


class DailyRow(Base):
    """
    One worker's attendance for one day - the web equivalent of
    data_engine.DailyRow. emp_no/trade/emp_name are deliberately
    duplicated onto this row (not just looked up via employee_id) so a
    day's record stays historically accurate even if the employee's
    name or trade changes later - matches how the desktop app's own
    DailyRow already works.
    """
    __tablename__ = "daily_rows"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    emp_no = Column(String, nullable=False, index=True)
    emp_name = Column(String, default="")
    trade = Column(String, default="")
    month_year = Column(String, nullable=False, index=True)
    full_date = Column(Date, nullable=False, index=True)
    day = Column(Integer)
    am = Column(String, default="")
    pm = Column(String, default="")
    ot = Column(Float, default=0.0)
    bh = Column(Float, default=0.0)
    site = Column(String, default="")
    engineer = Column(String, default="")
    comments = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", back_populates="daily_rows")

    __table_args__ = (
        UniqueConstraint("emp_no", "full_date", name="uix_emp_date"),
    )


class EmployeeSummary(Base):
    """
    One worker's derived payroll figures for one cycle - the web
    equivalent of data_engine.EmployeeSummary. Every derived field here
    (present_days, final_salary, etc.) is recomputed via the SAME
    recalculate_from_daily_rows() function the desktop app uses,
    whenever that worker's daily rows change for this cycle - never
    hand-edited directly, so there's one single source of truth for the
    formula, matching the desktop app's own design principle exactly.
    """
    __tablename__ = "employee_summaries"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    emp_no = Column(String, nullable=False, index=True)
    emp_name = Column(String, default="")
    trade = Column(String, default="")
    month_year = Column(String, nullable=False, index=True)
    total_salary = Column(Float, default=0.0)
    present_days = Column(Float, default=0.0)
    absent_days = Column(Float, default=0.0)
    sick_days = Column(Float, default=0.0)
    medical_days = Column(Float, default=0.0)
    friday_days = Column(Float, default=0.0)
    # A paid rest day, treated exactly as Friday is: it counts toward
    # the salary component and is never deducted.
    sunday_days = Column(Float, default=0.0)
    holiday_days = Column(Float, default=0.0)
    leave_days = Column(Float, default=0.0)
    # Days after the man left. Unpaid and never deducted - he simply
    # was not employed, which is not the same as failing to turn up.
    terminated_days = Column(Float, default=0.0)
    ot_hours = Column(Float, default=0.0)
    bh_hours = Column(Float, default=0.0)
    basic_pay_input = Column(Float, default=0.0)
    total_salary_component = Column(Float, default=0.0)
    deduction = Column(Float, default=0.0)
    ot_amount = Column(Float, default=0.0)
    bh_amount = Column(Float, default=0.0)
    allowances = Column(Float, default=0.0)
    other_deduction = Column(Float, default=0.0)
    final_salary = Column(Float, default=0.0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", back_populates="summaries")
    adjustments = relationship("SalaryAdjustment", back_populates="summary", cascade="all, delete-orphan")

    def adjusted_final_salary(self):
        """final_salary plus/minus every adjustment on this cycle's
        summary - the same calculation done inline everywhere else in
        the app (Reports preview, Salary Adjustments totals, exports),
        exposed as a method here so the Report Builder's generic
        aggregation engine (build_custom_report) can call it uniformly
        alongside plain columns like final_salary."""
        return self.final_salary + sum(
            -a.amount if a.is_deduction else a.amount for a in self.adjustments
        )

    __table_args__ = (
        UniqueConstraint("emp_no", "month_year", name="uix_emp_cycle"),
    )


class SalaryAdjustment(Base):
    __tablename__ = "salary_adjustments"
    id = Column(Integer, primary_key=True)
    summary_id = Column(Integer, ForeignKey("employee_summaries.id"), nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    is_deduction = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    summary = relationship("EmployeeSummary", back_populates="adjustments")


class AuditLog(Base):
    """
    A lightweight, append-only record of who changed what and when -
    something the single-user desktop app never needed, but a
    multi-staff web app genuinely does. Not used to gate or block
    anything, purely for visibility if a figure is ever questioned
    later.
    """
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # e.g. "save_attendance", "add_adjustment"
    details = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Backup(Base):
    """
    Stores full-database snapshots (as JSON text) so previous backups
    stay available to download or restore from later, not just at the
    moment they were taken. trigger is 'manual' (someone clicked the
    button) or 'auto' (created automatically once per calendar month).
    """
    __tablename__ = "backups"
    id = Column(Integer, primary_key=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    trigger = Column(String, nullable=False, default="manual")
    data = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------
# STORE / INVENTORY
# ---------------------------------------------------------------------
class Supplier(Base):
    """
    Who the company buys from. Built up as the store keeper works rather
    than typed into a separate master screen first: the first delivery
    from "Al Raha Trading" creates the record, and every later mention
    finds it again and fills in the phone number and contact person.

    name_key holds the name folded to lower case with punctuation and
    spacing stripped, so "AL RAHA TRADING", "Al Raha Trading" and
    "al-raha  trading" are recognised as one supplier instead of three.
    """
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    name_key = Column(String, unique=True, index=True, nullable=False)
    contact_person = Column(String, default="")
    phone = Column(String, default="")
    # Everything a purchase order needs printed on it. Kept on the
    # supplier so it is typed once and fetched every time after - the
    # TRN especially, which nobody remembers and everybody mistypes.
    trn = Column(String, default="")
    address = Column(Text, default="")
    email = Column(String, default="")
    payment_terms = Column(String, default="")
    notes = Column(Text, default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HireReturn(Base):
    """
    The paper that goes with the lorry when hired material goes back.

    A hire is only ever settled at the trader's gate, and settled once:
    what was on hire, what is physically going back, and what is not
    coming back at all. Without a document both sides signed, the
    argument happens weeks later against an invoice, with nothing to put
    against it but memory - which is how a shortage of four becomes a
    claim for twelve.

    status walks the journey of the paper itself:
      draft     - being prepared, nothing has left the yard
      issued    - printed and gone with the driver
      confirmed - signed by the trader and back with us. ONLY at this
                  point does the stock move, because until the trader
                  has signed, the material is still ours to account for.
      cancelled - abandoned; the numbering keeps the gap
    """
    __tablename__ = "hire_returns"

    id = Column(Integer, primary_key=True)
    ref = Column(String, unique=True, nullable=False, index=True)    # RN-0001
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    supplier_name = Column(String, default="")      # as printed, even if renamed later
    return_date = Column(Date, nullable=False, index=True)
    # Where it is going back from - the yard, or straight off a site.
    from_location = Column(String, default="")
    driver = Column(String, default="")
    vehicle = Column(String, default="")
    status = Column(String, default="draft", index=True)
    notes = Column(Text, default="")
    # Filled when the signed copy comes back, so the register can show
    # at a glance which returns are still unacknowledged.
    received_by = Column(String, default="")        # who signed at the trader's end
    confirmed_on = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lines = relationship("HireReturnLine", back_populates="ret",
                         cascade="all, delete-orphan", order_by="HireReturnLine.id")
    supplier = relationship("Supplier")


class HireReturnLine(Base):
    """
    One material on a return note.

    Three quantities, because three is what an argument needs: what was
    on hire, what is going back on this lorry, and what is not coming
    back. They do not have to add up - a partial return leaves the rest
    on hire, which is normal and should not look like a loss.

    qty_short is the only figure that costs money, so it carries a
    reason: lost, damaged, or still standing on a site.
    """
    __tablename__ = "hire_return_lines"

    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("hire_returns.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=True, index=True)
    description = Column(String, default="")        # as printed
    unit = Column(String, default="pcs")
    qty_on_hire = Column(Float, default=0.0)        # the position when the note was written
    qty_returned = Column(Float, default=0.0)       # physically going back
    qty_short = Column(Float, default=0.0)          # not coming back at all
    short_reason = Column(String, default="")       # lost | damaged | on site
    notes = Column(String, default="")

    ret = relationship("HireReturn", back_populates="lines")
    item = relationship("StoreItem")


class PurchaseOrder(Base):
    """A local purchase order - the paper the supplier works from.

    Raised from the approved lines of a material request, or on its own
    when the office buys something nobody asked for through the system.
    One per supplier: a request split across two traders becomes two
    orders, which is how the office already works.

    Every line's rate is kept for good, because the rate history is the
    point - it is what stops the same cement being bought at 16.00 one
    week and 16.50 the next without anyone noticing.
    """
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True)
    po_no = Column(Integer, unique=True, nullable=False, index=True)   # 20260100
    ref = Column(String, unique=True, nullable=False, index=True)      # IC/LPO/20260100
    order_date = Column(Date, nullable=False)
    terms = Column(String, default="Due on Receipt")
    delivery_date = Column(Date, nullable=True)
    supplier_ref = Column(String, default="")        # the trader's own quote number

    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    supplier_name = Column(String, default="")       # as printed, even if the record is renamed later
    supplier_address = Column(Text, default="")
    supplier_trn = Column(String, default="")
    # The vendor block as it was on the day. A trader's man moves on and
    # his number changes; an order raised last March must still show who
    # was rung about it, so these are copied onto the order rather than
    # read live off the supplier record every time it is printed.
    supplier_email = Column(String, default="")      # printed in the vendor block
    supplier_contact = Column(String, default="")    # their man, not ours
    supplier_phone = Column(String, default="")      # their number, not ours

    request_id = Column(Integer, ForeignKey("material_requests.id"), nullable=True, index=True)
    plot_no = Column(String, default="")
    contact_person = Column(String, default="")
    mobile = Column(String, default="")
    email = Column(String, default="purchase@infinia.ae")
    job_scope = Column(String, default="")
    project_location = Column(String, default="")

    discount_pct = Column(Float, default=0.0)
    tax_pct = Column(Float, default=5.0)
    notes = Column(Text, default="")
    terms_text = Column(Text, default="")
    status = Column(String, default="issued")        # issued | cancelled

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lines = relationship("PurchaseOrderLine", back_populates="order",
                         cascade="all, delete-orphan", order_by="PurchaseOrderLine.id")
    supplier = relationship("Supplier")


class PurchaseOrderLine(Base):
    """One material on an order, with the rate actually paid."""
    __tablename__ = "purchase_order_lines"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=True, index=True)
    description = Column(String, default="")         # as printed
    description2 = Column(String, default="")        # the small second line: "price/week"
    qty = Column(Float, default=0.0)
    unit = Column(String, default="")
    rate = Column(Float, default=0.0)
    tax_pct = Column(Float, default=5.0)

    order = relationship("PurchaseOrder", back_populates="lines")
    item = relationship("StoreItem")


class StoreItem(Base):
    """
    A material or tool the store holds. item_type drives the whole
    behaviour downstream:
      'consumable' - cement, sand, nails. Issued to a site and gone;
                     stock only ever goes down when issued.
      'returnable' - drills, ladders, scaffolding. Issued to a site and
                     expected back, so the quantity currently out is
                     tracked and can be returned to the central store.
    Stock is never stored on this row - it is derived from movements, so
    the ledger and the balance can never disagree.
    """
    __tablename__ = "store_items"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="")
    unit = Column(String, default="pcs")          # bags, m, pcs, kg...
    # consumable | returnable | asset | rental
    #   asset  - owned equipment tracked individually (mixer, generator)
    #   rental - hired in from a supplier, so it has a daily/monthly rate
    #            and a date it must go back, and never counts as owned stock
    item_type = Column(String, default="consumable")
    reorder_level = Column(Float, default=0.0)
    # Rental-only fields, ignored for other types
    rental_supplier = Column(String, default="")
    rental_rate = Column(Float, default=0.0)
    rental_period = Column(String, default="day")     # day | week | month
    rental_start = Column(Date, nullable=True)
    rental_due = Column(Date, nullable=True)
    notes = Column(Text, default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class StoreMovement(Base):
    """
    Every stock change, as an append-only ledger. Current stock is the
    sum of these rather than a stored number, so there is one source of
    truth and no chance of a balance drifting away from its history.

    kind:
      'in'          - received into the central store (purchase/delivery)
      'out'         - issued from central store to a site
      'return'      - returnable item coming back from a site
      'adjust'      - correction after a stock count (qty may be negative)
      'transfer'    - moved between two sites
      'lost'        - written off where it stood: lost or damaged
      'hire_return' - hired material handed back to the trader it came
                      from, so it leaves our books entirely rather than
                      moving to another location of ours
    location is where the stock ENDS UP; from_location is where it came
    from (used by 'out', 'return' and 'transfer').
    """
    __tablename__ = "store_movements"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    qty = Column(Float, nullable=False, default=0.0)
    from_location = Column(String, default="")     # "" = central store
    location = Column(String, default="")          # "" = central store
    incharge = Column(String, default="")          # who took responsibility
    # WHOSE this stock is, which is a different question from who it was
    # bought from. Empty means ours. A supplier here means the quantity
    # is hired in from that trader and has to go back to him - the same
    # scaffold standard can stand in the yard under both, and without
    # this column the two are indistinguishable, which is how hired kit
    # gets lost in the owned pile and argued over on return.
    owner_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    supplier = Column(String, default="")
    unit_cost = Column(Float, default=0.0)
    reference = Column(String, default="")         # DO / invoice number
    notes = Column(Text, default="")
    moved_on = Column(Date, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("StoreItem")


class MaterialRequest(Base):
    """
    A request from the store keeper to the office for materials to be
    ordered. The office orders in their own system; this tracks what was
    asked for, what was approved, and what has actually arrived, so the
    store keeper can see what is still outstanding.

    status walks the real-life path a request takes:
      pending    - sent by the store keeper, office hasn't looked yet
      approved   - office agrees to buy it
      arranging  - office is getting quotes / choosing a supplier
      lpo_sent   - purchase order raised with the supplier
      partial    - some of it has arrived
      delivered  - everything has arrived at the store
      closed     - finished and filed away
      rejected   - office declined
    """
    __tablename__ = "material_requests"
    id = Column(Integer, primary_key=True)
    ref = Column(String, unique=True, nullable=False, index=True)   # MR-0001
    site = Column(String, default="")
    requested_by = Column(String, default="")
    needed_by = Column(Date, nullable=True)
    urgency = Column(String, default="normal")      # low | normal | urgent
    status = Column(String, default="pending", index=True)
    notes = Column(Text, default="")
    office_remark = Column(Text, default="")
    # Who the office ordered it from, captured at "mark as ordered", so
    # the keeper chasing a late delivery has a name and a number in
    # front of them instead of asking the office who bought it.
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    expected_on = Column(Date, nullable=True)
    requested_on = Column(Date, nullable=False, index=True)
    closed_on = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lines = relationship("MaterialRequestLine", back_populates="request",
                          cascade="all, delete-orphan")
    supplier = relationship("Supplier")


class MaterialRequestLine(Base):
    """
    One material on a request. qty_received is filled as deliveries come
    in, so outstanding = qty_requested - qty_received and a request can
    sit at 'partial' honestly rather than being all-or-nothing.
    """
    __tablename__ = "material_request_lines"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("material_requests.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=True)
    description = Column(String, default="")     # free text if not a known item
    qty_requested = Column(Float, nullable=False, default=0.0)
    qty_approved = Column(Float, default=0.0)
    qty_received = Column(Float, default=0.0)
    unit = Column(String, default="pcs")
    est_cost = Column(Float, default=0.0)
    # The office often splits one request across traders on price: the
    # cement from one, the rebar from another. Supplier therefore lives
    # on the line, and the request-level supplier is just a shortcut for
    # the common case where every line went to the same place.
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    # The office prices a request line by line and may turn down one
    # material while approving the rest - so a decision belongs on the
    # line, not only on the request.
    status = Column(String, default="pending")   # pending | approved | rejected
    reject_reason = Column(String, default="")
    notes = Column(Text, default="")
    # What the material is actually for - the office needs this to judge
    # whether to order, and it stops "200 bags of cement" arriving with
    # nobody remembering which job it was for.
    purpose = Column(String, default="")

    request = relationship("MaterialRequest", back_populates="lines")
    item = relationship("StoreItem")
    supplier = relationship("Supplier")


# ======================================================================
# OFFICE HR & PAYROLL
# ======================================================================
# The labour side of this app pays men by the day, from attendance.
# Office staff are paid a monthly figure and only the exceptions are
# entered - a day missed, a taxi bill, a loan instalment. Both kinds of
# worker are the same Employee row: a man promoted from labourer to
# storekeeper keeps his joining date, his service and his loan balance
# instead of being entered again with the gratuity clock restarted.


class Company(Base):
    """One of the companies the group employs through.

    Infinia and Prime Infinia today, more to come. Each pays its own
    people, files its own WPS and prints its own letterhead, so this is
    a record rather than a switch between two names in code.
    """
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)      # INFINIA CONTRACTING L.L.C.
    short_name = Column(String, default="")                 # Infinia
    code_prefix = Column(String, default="")                # IC -> IC001
    trn = Column(String, default="")
    wps_id = Column(String, default="")                     # MOHRE establishment id
    address = Column(Text, default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SalaryChange(Base):
    """A joining figure or an increment, with the split it landed on.

    Gratuity is calculated on the basic in force when a man leaves, so
    an increment that touches basic revalues every year already served.
    Keeping each change means the figure can be explained rather than
    only asserted, and an increment agreed for a future month can sit
    here until its cycle arrives.
    """
    __tablename__ = "salary_changes"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    effective_on = Column(Date, nullable=False, index=True)
    kind = Column(String, default="increment")     # joining | increment | correction
    basic = Column(Float, default=0.0)             # after this change
    allowance = Column(Float, default=0.0)         # after this change
    amount = Column(Float, default=0.0)            # the rise itself
    reason = Column(String, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee")


class EmployeeDocument(Base):
    """A document that expires, and the date it does.

    The visa, the Emirates ID, the labour card, the passport. A missed
    renewal is a fine and a man who cannot work, and it is the labour
    force - seventy-odd men - where most of that risk sits. Renewing
    means changing the expiry date here, so the warning list can never
    disagree with what was actually renewed.
    """
    __tablename__ = "employee_documents"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)   # eid | visa | passport | labour_card | insurance
    number = Column(String, default="")
    issued_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True, index=True)
    notes = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee")


class StaffLoan(Base):
    """Money lent to a worker, and what is left of it.

    The balance is never stored: it is the amount lent less everything
    recovered, so the ledger and the balance cannot drift apart. On the
    day somebody leaves, what is outstanding settles against the
    gratuity - which is the moment this has to be right.
    """
    __tablename__ = "staff_loans"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    taken_on = Column(Date, nullable=False)
    terms = Column(String, default="")             # "Monthly 500 reimbursement"
    instalment = Column(Float, default=0.0)        # what the run proposes each cycle
    closed = Column(Boolean, default=False)
    notes = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee")
    repayments = relationship("LoanRepayment", back_populates="loan",
                               cascade="all, delete-orphan")


class LoanRepayment(Base):
    """One recovery against a loan - normally a payroll deduction."""
    __tablename__ = "loan_repayments"
    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("staff_loans.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    paid_on = Column(Date, nullable=False)
    month_year = Column(String, default="", index=True)    # the cycle it came off
    source = Column(String, default="payroll")             # payroll | cash | settlement
    notes = Column(String, default="")

    loan = relationship("StaffLoan", back_populates="repayments")


class StaffLeave(Base):
    """A day or half-day somebody was not at work.

    Whether it costs the man money is a judgement - a sick day with a
    certificate is paid, one without may not be - so the register
    records what happened and the payroll run proposes the deduction
    from it. Unpaid days are also the ones that do not count towards
    gratuity, which is the other reason this is kept rather than
    remembered.
    """
    __tablename__ = "staff_leave"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    on_date = Column(Date, nullable=False, index=True)
    portion = Column(Float, default=1.0)           # 1.0 a day, 0.5 a half day
    reason = Column(String, default="")            # sick | annual | unpaid | company
    paid = Column(Boolean, default=True)           # paid: no deduction, counts as service
    certificate = Column(Boolean, default=False)
    notes = Column(String, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # What kind of day off it was. The kind decides whether it is paid:
    # absent, unpaid leave and vacation cost the day; a company holiday
    # or other paid leave costs nothing; a sick day is paid up to one a
    # month and the rest count as absent.
    kind = Column(String, nullable=True)           # absent|sick|vacation|unpaid|holiday|paid_leave
    # "auto" follows the rule above. "paid" / "unpaid" is the accountant
    # overriding it for this entry. No default on purpose: rows from
    # before this existed are given the decision they were actually
    # paid on, so a signed month does not change.
    pay_rule = Column(String, nullable=True)
    # A range of days entered once - a week's vacation - shares a batch,
    # so it is shown, edited and removed as the one entry it was.
    batch = Column(String, nullable=True, index=True)

    employee = relationship("Employee")


class PayItem(Base):
    """An addition to or a deduction from one person's month.

    Taxi bills, a fee paid on his behalf, leave salary, an air ticket -
    or an ILOE premium, a fine, an advance recovered. Entered here, once,
    and the salary cycle for that month picks them up by itself.
    """
    __tablename__ = "pay_items"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    month_year = Column(String, nullable=False, index=True)    # "September 2026"
    direction = Column(String, nullable=False)                 # add | deduct
    category = Column(String, nullable=False)                  # taxi | leave_salary | iloe | ...
    amount = Column(Float, nullable=False)
    on_date = Column(Date, nullable=True)
    notes = Column(String, default="")
    # Set when the item was raised by something else - a vacation's
    # leave salary - so it follows that entry when it is changed.
    source = Column(String, default="")                        # "" | leave:<batch>
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee")


class PayrollRun(Base):
    """One company's office payroll for one cycle.

    Approving it locks the figures. After that a correction is a
    recorded amendment rather than a quiet edit, which is what stops
    two documents covering the same month disagreeing.
    """
    __tablename__ = "payroll_runs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    month_year = Column(String, nullable=False, index=True)     # "August 2026"
    group = Column(String, default="staff")        # staff | local - printed separately
    status = Column(String, default="draft")       # draft | approved
    notes = Column(Text, default="")
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_on = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company")
    lines = relationship("PayrollLine", back_populates="run", cascade="all, delete-orphan")


class PayrollLine(Base):
    """One worker's month.

    Net = fixed - deduction - loan + allowance + leave salary + pension.
    The basic and allowance behind the fixed figure are copied onto the
    line as they stood, so a statement reprinted next year still shows
    the month as it was rather than as the staff record is today.
    """
    __tablename__ = "payroll_lines"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("payroll_runs.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    basic = Column(Float, default=0.0)             # as it stood that month
    allowance = Column(Float, default=0.0)
    fixed_salary = Column(Float, default=0.0)      # basic + allowance
    # The accountant typed over the proposed instalment or remark, so a
    # refresh of the draft keeps his figure instead of the proposal.
    loan_edited = Column(Boolean, default=False)
    remark_edited = Column(Boolean, default=False)

    deduction = Column(Float, default=0.0)         # absence and unpaid leave
    deduction_note = Column(String, default="")
    statutory = Column(Float, default=0.0)         # ILOE, SOE and the like
    other_allowance = Column(Float, default=0.0)   # taxi, bills, reimbursements
    loan_deduction = Column(Float, default=0.0)
    leave_salary = Column(Float, default=0.0)
    air_ticket = Column(Float, default=0.0)
    pension = Column(Float, default=0.0)           # GPSSA, for nationals
    net_pay = Column(Float, default=0.0)
    remarks = Column(String, default="")

    run = relationship("PayrollRun", back_populates="lines")
    employee = relationship("Employee")
