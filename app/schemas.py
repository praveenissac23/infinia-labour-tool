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
    full_name: str
    role: str = "staff"


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    active: bool

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
