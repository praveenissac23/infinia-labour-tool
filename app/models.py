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
    role = Column(String, nullable=False, default="staff")  # "admin" | "staff"
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    emp_no = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    trade = Column(String, default="")
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
    active = Column(Boolean, default=True)


class Engineer(Base):
    __tablename__ = "engineers"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
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
    holiday_days = Column(Float, default=0.0)
    leave_days = Column(Float, default=0.0)
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
