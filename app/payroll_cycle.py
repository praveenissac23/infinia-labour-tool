"""
Infinia Labour Tool - Payroll Cycle Utilities
=================================================
Attendance/payroll cycles run the 26th of one month through the 25th of
the next (e.g. 26 July - 25 August is the "August" cycle). This module is
the single source of truth for that logic - anything that needs to know
"what cycle is today in" or "what are the boundaries of the cycle
containing date X" should call these functions rather than reimplementing
the 26th/25th math inline, to guarantee it's always calculated the same
way everywhere in the app.
"""

from datetime import date


def cycle_bounds_for(d):
    """
    Returns (start_date, end_date, cycle_label) for the payroll cycle that
    contains date `d`.
    - If d.day >= 26: the cycle runs from the 26th of d's month through the
      25th of the FOLLOWING month, and is labelled after that following
      month (since that's the month the salary is processed/paid for).
    - If d.day <= 25: the cycle runs from the 26th of the PREVIOUS month
      through the 25th of d's month, labelled after d's month.
    """
    if d.day >= 26:
        start = date(d.year, d.month, 26)
        if d.month == 12:
            end_year, end_month = d.year + 1, 1
        else:
            end_year, end_month = d.year, d.month + 1
        end = date(end_year, end_month, 25)
        label_year, label_month = end_year, end_month
    else:
        end = date(d.year, d.month, 25)
        if d.month == 1:
            start_year, start_month = d.year - 1, 12
        else:
            start_year, start_month = d.year, d.month - 1
        start = date(start_year, start_month, 26)
        label_year, label_month = d.year, d.month

    label = date(label_year, label_month, 1).strftime("%B %Y")
    return start, end, label


def current_cycle():
    """Returns (start_date, end_date, cycle_label) for the cycle containing today."""
    return cycle_bounds_for(date.today())


def is_date_in_cycle(d, cycle_start, cycle_end):
    return cycle_start <= d <= cycle_end


# ---- Money to the fils, never a fraction extra (owner, 31 Oct 2026) ---------------------------------------------------
# "I don't want to give anything extra even if it's fils." From the November 2026 cycle (26 Oct - 25 Nov 2026) on, a
# labour card's salary is worked out in exact fractions and cut to the fils only at the very end - never rounded up to
# the dirham. The cut is always DOWN (towards minus infinity, Decimal ROUND_FLOOR): a positive amount loses the part of
# a fil (1,472.508 -> 1,472.50), and a negative card (a man who owes) is never let off part of a fil (-175.501 ->
# -175.51). October 2026 and every cycle before it keep the old rule - rounded to the whole dirham - and their stored
# figures are never rewritten.
FILS_FROM_CYCLE_END = date(2026, 11, 25)


# ---- The payable amount to the nearest dirham (owner, 28/11/2026) ---------------------------------------------------
# Accounts: "the payroll amounts are displaying decimal values ... round all final payable salary amounts to the nearest
# whole AED: below 50 fils down, 50 fils and above up (Excel =ROUND(x,0))". From the same November 2026 cycle the
# figures are still worked out exactly (no rounding on the way), but the amount PAYABLE - a labour card's final salary
# and what is paid after its additions/deductions, an office line's net pay and salary to date, a final settlement's
# net - is brought to the nearest whole dirham once, at the end: 2,500.49 -> 2,500; 2,500.50 -> 2,501; a negative
# half goes away from zero (-175.50 -> -176), as Excel's ROUND. The lines above it keep their fils; the difference is
# shown as its own "Round off" line so every slip still adds up. (This replaces the cut down to the fils of 31/10.)
def dirham(x):
    """An exact amount (Fraction, Decimal, int, or a float read as written) to the nearest whole dirham, a half away
    from zero (Excel ROUND(x,0)). Returns a float (never -0.0)."""
    from decimal import Decimal, ROUND_HALF_UP
    from fractions import Fraction
    if isinstance(x, float):
        x = Decimal(str(x))
    elif isinstance(x, Fraction):
        x = Decimal(x.numerator) / Decimal(x.denominator)
    elif not isinstance(x, Decimal):
        x = Decimal(str(x or 0))
    return float(x.quantize(Decimal(1), rounding=ROUND_HALF_UP)) + 0.0


ROUND_OFF_LABEL = "Round off"


def cycle_end_of(month_year):
    from datetime import datetime
    try:
        return datetime.strptime(f"25 {month_year}", "%d %B %Y").date()
    except (TypeError, ValueError):
        return None


def exact_fils(month_year):
    """True for a cycle paid to the exact fils (November 2026 onwards)."""
    ce = cycle_end_of(month_year)
    return bool(ce and ce >= FILS_FROM_CYCLE_END)


def fils_down(x):
    """An exact amount (Fraction, Decimal, int, or a float read as written) cut to the fils, never up:
    Decimal quantize to 0.01 with ROUND_FLOOR. Returns a float with exactly two decimals."""
    from decimal import Decimal, ROUND_FLOOR
    from fractions import Fraction
    if isinstance(x, float):
        x = Fraction(str(x))
    if isinstance(x, Fraction):
        cents = (x * 100).__floor__()
        return float(Decimal(cents) / 100)
    return float(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_FLOOR))


def fils_up(x):
    """The same, cut UP - for a deduction shown on its own line, so less is never shown taken than is."""
    from fractions import Fraction
    if isinstance(x, float):
        x = Fraction(str(x))
    return -fils_down(-Fraction(x))
