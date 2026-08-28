"""
Pydantic schemas - what the API actually accepts and returns, separate
from the SQLAlchemy models (which describe the database, not the wire
format). Keeping these separate means a column can be renamed in the
DB, or a field hidden from the API (e.g. hashed_password), without one
change silently breaking the other.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


# ---- Auth ----
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserIn(BaseModel):
    username: str
    password: str
    # Kept on the model (existing users have one, and it's shown in the
    # Activity Monitor) but no longer asked for when creating a login -
    # it defaults to the username so nothing downstream sees a blank.
    full_name: str = ""
    role: str = "staff"


class ResetPasswordRequest(BaseModel):
    new_password: str


class PermissionsIn(BaseModel):
    permissions: str = ""


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    active: bool
    permissions: Optional[str] = ""

    class Config:
        from_attributes = True


# ---- Employees ----
class EmployeeIn(BaseModel):
    emp_no: str
    name: str
    trade: str = ""
    total_salary: float = 0.0
    basic_salary: float = 0.0
    active: bool = True


class EmployeeOut(EmployeeIn):
    id: int

    class Config:
        from_attributes = True


# ---- Sites / Engineers ----
class SiteIn(BaseModel):
    code: str
    active: bool = True


class SiteOut(SiteIn):
    id: int

    class Config:
        from_attributes = True


class EngineerIn(BaseModel):
    name: str
    active: bool = True


class EngineerOut(EngineerIn):
    id: int

    class Config:
        from_attributes = True


# ---- Daily attendance ----
class DailyRowIn(BaseModel):
    emp_no: str
    full_date: date
    am: str = ""
    pm: str = ""
    ot: float = 0.0
    bh: float = 0.0
    site: str = ""
    engineer: str = ""
    comments: str = ""


class DailyRowOut(BaseModel):
    id: int
    emp_no: str
    emp_name: str
    trade: str
    month_year: str
    full_date: date
    day: Optional[int]
    am: str
    pm: str
    ot: float
    bh: float
    site: str
    engineer: str
    comments: str
    # Exposed so the frontend can tell whether a locally-saved draft is
    # older than the server's data and should therefore be discarded
    # rather than restored over it.
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BulkSaveRequest(BaseModel):
    rows: list[DailyRowIn]


# ---- Salary adjustments ----
class SalaryAdjustmentIn(BaseModel):
    description: str
    amount: float
    is_deduction: bool = True


class SalaryAdjustmentOut(SalaryAdjustmentIn):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Employee summary (derived payroll figures) ----
class EmployeeSummaryOut(BaseModel):
    id: int
    emp_no: str
    emp_name: str
    trade: str
    month_year: str
    total_salary: float
    present_days: float
    absent_days: float
    sick_days: float
    medical_days: float
    friday_days: float
    holiday_days: float
    leave_days: float
    ot_hours: float
    bh_hours: float
    basic_pay_input: float
    total_salary_component: float
    deduction: float
    ot_amount: float
    bh_amount: float
    allowances: float
    other_deduction: float
    final_salary: float
    adjustments: list[SalaryAdjustmentOut] = []
    sites: str = ""

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------
# STORE / INVENTORY
# ---------------------------------------------------------------------
class StoreItemIn(BaseModel):
    code: str
    name: str
    category: str = ""
    unit: str = "pcs"
    item_type: str = "consumable"
    reorder_level: float = 0.0
    notes: str = ""
    rental_supplier: str = ""
    rental_rate: float = 0.0
    rental_period: str = "day"
    rental_start: Optional[date] = None
    rental_due: Optional[date] = None


class StoreItemOut(BaseModel):
    id: int
    code: str
    name: str
    category: str
    unit: str
    item_type: str
    reorder_level: float
    notes: str
    active: bool
    # Optional because rows created before these columns existed have
    # NULL in them - a plain str/float would reject those outright.
    rental_supplier: Optional[str] = ""
    rental_rate: Optional[float] = 0.0
    rental_period: Optional[str] = "day"
    rental_start: Optional[date] = None
    rental_due: Optional[date] = None

    class Config:
        from_attributes = True


class StoreMovementIn(BaseModel):
    item_id: int
    kind: str
    qty: float
    from_location: str = ""
    location: str = ""
    incharge: str = ""
    supplier: str = ""
    unit_cost: float = 0.0
    reference: str = ""
    notes: str = ""
    moved_on: date


class StoreMovementOut(BaseModel):
    id: int
    item_id: int
    kind: str
    qty: float
    from_location: str
    location: str
    incharge: str
    supplier: str
    unit_cost: float
    reference: str
    notes: str
    moved_on: date
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    unit: Optional[str] = None

    class Config:
        from_attributes = True


class MaterialRequestLineIn(BaseModel):
    item_id: Optional[int] = None
    description: str = ""
    qty_requested: float
    qty_approved: float = 0.0
    unit: str = "pcs"
    est_cost: float = 0.0
    notes: str = ""


class MaterialRequestIn(BaseModel):
    site: str = ""
    requested_by: str = ""
    needed_by: Optional[date] = None
    urgency: str = "normal"
    notes: str = ""
    requested_on: Optional[date] = None
    lines: list[MaterialRequestLineIn] = []


class MaterialRequestLineOut(BaseModel):
    id: int
    item_id: Optional[int] = None
    description: str
    qty_requested: float
    qty_approved: float
    qty_received: float
    unit: str
    est_cost: float
    notes: str
    item_code: Optional[str] = None
    item_name: Optional[str] = None

    class Config:
        from_attributes = True


class MaterialRequestOut(BaseModel):
    id: int
    ref: str
    site: str
    requested_by: str
    needed_by: Optional[date] = None
    urgency: str
    status: str
    notes: str
    office_remark: str
    requested_on: date
    closed_on: Optional[date] = None
    lines: list[MaterialRequestLineOut] = []

    class Config:
        from_attributes = True


class MaterialRequestStatusIn(BaseModel):
    status: str
    office_remark: str = ""
