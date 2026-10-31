"""Office pay to the fils, never a fraction of a fils extra (owner's rule, 31/10/2026).

"I don't want to give anything extra even if it's fils." From the November 2026 office month onward (and for any
final settlement worked out now, since a settlement is never stored until it is paid), every office figure is worked
out in exact decimals - a day's rate is never rounded before it is multiplied by the days - and only the amount that
results is brought to two decimals:

  * an amount paid TO him (salary to date, leave encashment, gratuity, salary for the last days, notice pay) is
    rounded DOWN to the fils (towards minus infinity, so a negative stays exact or goes the company's way);
  * an amount taken FROM him (absence, days not employed, notice not served) is rounded UP to the fils.

So every line still adds up exactly on paper (net = gross - deductions + additions, all to two decimals) and the net
is never more than the exact figure. October 2026 and earlier months keep the old rule (a day is gross / 30 dropped
to whole dirhams) so what was approved or paid is not touched.
"""
from datetime import date, datetime
from decimal import Decimal

import payroll_cycle as pcyc       # the rounding helpers shared with labour (fils_down / fils_up)

EXACT_FROM = date(2026, 11, 1)          # the November 2026 office month (calendar month) onward
_C = Decimal("0.01")


def exact_month(month_year):
    """Is this office month (e.g. "November 2026") on the to-the-fils rule?"""
    try:
        return datetime.strptime(f"1 {month_year}", "%d %B %Y").date() >= EXACT_FROM
    except (TypeError, ValueError):
        return False


def D(v):
    return Decimal(str(v or 0))


def pay_down(v):
    """An amount paid to him: exact, then DOWN to the fils (the labour side's payroll_cycle.fils_down, ROUND_FLOOR)."""
    return pcyc.fils_down(v if not isinstance(v, (int, float)) else D(v)) + 0.0      # (never -0.0)


def take_up(v):
    """An amount taken from him: exact, then UP to the fils (payroll_cycle.fils_up)."""
    return float(pcyc.fils_up(v if not isinstance(v, (int, float)) else D(v))) + 0.0


def days_cost(gross, days):
    """Days off at gross / 30 a day, exact: Decimal(gross) * days / 30 (no rounded day rate)."""
    return D(gross) * D(days) / Decimal(30)


def add2(*vals):
    """Sum of two-decimal figures, without float drift."""
    return float(sum((D(v) for v in vals), Decimal(0)).quantize(_C))
