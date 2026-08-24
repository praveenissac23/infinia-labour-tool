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
