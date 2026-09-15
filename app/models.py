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
    supplier_email = Column(String, default="")      # printed in the vendor block

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
      'in'       - received into the central store (purchase/delivery)
      'out'      - issued from central store to a site
      'return'   - returnable item coming back from a site
      'adjust'   - correction after a stock count (qty may be negative)
      'transfer' - moved between two sites
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
