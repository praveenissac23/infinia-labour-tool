"""
Infinia Labour Tool - Report Engine
=====================================
Every report is a function of (daily_rows, summaries, filters) -> a table
(list of dicts) with a title and column list, ready for export_engine.

Filters dict keys (all optional, None/'' = no filter):
    site, emp_no, trade, engineer, date_from, date_to
"""

from collections import defaultdict


class ReportResult:
    def __init__(self, title, columns, rows, totals=None, note=None):
        self.title = title
        self.columns = columns   # list of (key, header)
        self.rows = rows         # list of dicts
        self.totals = dict(totals or {})   # dict key -> value, shown as a totals row
        self.note = note
        self._auto_fill_totals()

    def _auto_fill_totals(self):
        """
        Automatically sums any column that's fully numeric across every row
        and doesn't already have an explicit total set - this is what makes
        "OT Hours by Site" (and every other numeric column, in every report)
        show a total without each report function needing to remember to
        add one by hand. If a report has no numeric columns and no manual
        total at all, falls back to a plain row count so there's always
        SOME totals line.
        """
        if not self.rows:
            return
        for key, header in self.columns:
            if key in self.totals:
                continue
            values = [r.get(key) for r in self.rows]
            if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
                self.totals[key] = round(sum(values), 2)
        if not self.totals and self.columns:
            first_key = self.columns[0][0]
            self.totals[first_key] = f"{len(self.rows)} row(s)"


def _in_range(d, date_from, date_to):
    if d is None:
        return False
    if date_from and d < date_from:
        return False
    if date_to and d > date_to:
        return False
    return True


def _apply_common_filters(rows, f):
    out = []
    for r in rows:
        if f.get("site") and str(r.site).strip() != str(f["site"]).strip():
            continue
        if f.get("emp_no") and str(r.emp_no).strip() != str(f["emp_no"]).strip():
            continue
        if f.get("trade") and str(r.trade).strip().lower() != str(f["trade"]).strip().lower():
            continue
        if f.get("engineer") and str(r.engineer).strip().lower() != str(f["engineer"]).strip().lower():
            continue
        if f.get("date_from") or f.get("date_to"):
            if not _in_range(r.full_date, f.get("date_from"), f.get("date_to")):
                continue
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# ATTENDANCE
# ---------------------------------------------------------------------------

def daily_roster(daily_rows, summaries, filters):
    target = filters.get("date_from") or filters.get("date_to")
    rows = [r for r in daily_rows if r.full_date == target]
    rows = _apply_common_filters(rows, {k: v for k, v in filters.items() if k not in ("date_from", "date_to")})
    out = [{"emp_no": r.emp_no, "name": r.emp_name, "trade": r.trade, "am": r.am,
            "pm": r.pm, "site": r.site, "engineer": r.engineer} for r in rows]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
            ("am", "A.M"), ("pm", "P.M"), ("site", "Site"), ("engineer", "Engineer")]
    return ReportResult(f"Daily Roster - {target}", cols, out)


def monthly_attendance_summary(daily_rows, summaries, filters):
    sums = _filter_summaries(summaries, filters)
    out = [{"emp_no": s.emp_no, "name": s.emp_name, "trade": s.trade, "month": s.month_year,
            "present": s.present_days, "absent": s.absent_days, "sick": s.sick_days,
            "medical": s.medical_days, "holiday": s.holiday_days, "leave": s.leave_days}
           for s in sums]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
            ("month", "Month"), ("present", "Present"), ("absent", "Absent"),
            ("sick", "Sick"), ("medical", "Medical"), ("holiday", "Holiday"), ("leave", "Leave")]
    return ReportResult("Monthly Attendance Summary", cols, out)


def absentee_report(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    rows = [r for r in rows if r.am.lower() == "absent" or r.pm.lower() == "absent"]
    out = [{"emp_no": r.emp_no, "name": r.emp_name, "trade": r.trade, "date": r.full_date,
            "site": r.site} for r in rows]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
            ("date", "Date"), ("site", "Site")]
    return ReportResult("Absentee Report", cols, out, totals={"emp_no": f"{len(out)} absence-days"})


def sick_report(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    rows = [r for r in rows if r.am.lower() in ("sick", "medical") or r.pm.lower() in ("sick", "medical")]
    out = [{"emp_no": r.emp_no, "name": r.emp_name, "trade": r.trade, "date": r.full_date,
            "status": r.am if r.am.lower() in ("sick", "medical") else r.pm, "site": r.site}
           for r in rows]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
            ("date", "Date"), ("status", "Status"), ("site", "Site")]
    return ReportResult("Sick / Medical Report", cols, out, totals={"emp_no": f"{len(out)} day-records"})


def leave_report(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    rows = [r for r in rows if r.am.lower() == "leave" or r.pm.lower() == "leave"]
    out = [{"emp_no": r.emp_no, "name": r.emp_name, "trade": r.trade, "date": r.full_date,
            "site": r.site} for r in rows]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
            ("date", "Date"), ("site", "Site")]
    return ReportResult("Leave Report", cols, out, totals={"emp_no": f"{len(out)} leave-days"})


def friday_worked_report(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    rows = [r for r in rows if r.full_date and r.full_date.weekday() == 4
            and (r.am.lower() == "present" or r.pm.lower() == "present")]
    out = [{"emp_no": r.emp_no, "name": r.emp_name, "date": r.full_date, "site": r.site,
            "ot": r.ot} for r in rows]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("date", "Date"),
            ("site", "Site"), ("ot", "OT Hours")]
    return ReportResult("Friday / Rest-Day Worked Report", cols, out)


def missing_data_check(daily_rows, summaries, filters):
    out = []
    for s in summaries:
        problems = []
        if not s.month_year:
            problems.append("Month & Year blank")
        if s.mismatch:
            problems.append(f"Salary mismatch (AED {s.mismatch_amount:,.2f})")
        if s.total_salary <= 0:
            problems.append("Salary is zero/blank")
        if problems:
            out.append({"emp_no": s.emp_no, "name": s.emp_name, "file": s.source_file,
                        "issue": "; ".join(problems)})
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("file", "Source File"),
            ("issue", "Issue")]
    return ReportResult("Missing / Incomplete Card Check", cols, out)


def check_for_errors(daily_rows, summaries, filters):
    """
    Card-wise data quality check across the daily grid:
    - AM or P.M status left blank on a day that has other data filled in
    - Marked Present but missing a Site and/or Engineer
    - BH (bank holiday) hours over 2 in a day with no Comment explaining it
    """
    out = []
    for r in daily_rows:
        problems = []
        am = (r.am or "").strip()
        pm = (r.pm or "").strip()
        if not am or not pm:
            problems.append("AM/PM status missing")
        is_present = am.lower() == "present" or pm.lower() == "present"
        if is_present and (not str(r.site).strip() or not str(r.engineer).strip()):
            problems.append("Present but Site/Engineer missing")
        if r.bh and r.bh > 2 and not (r.comments or "").strip():
            problems.append("BH over 2 hours but no comment")
        if problems:
            out.append({"emp_no": r.emp_no, "name": r.emp_name, "date": r.full_date or r.day,
                        "site": r.site, "issue": "; ".join(problems)})
    out.sort(key=lambda x: (x["emp_no"], str(x["date"])))
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("date", "Date"),
            ("site", "Site"), ("issue", "Issue")]
    return ReportResult("Check for Errors", cols, out,
                         note="Card-wise: missing AM/P.M status, Present days without a Site/Engineer, "
                              "and BH over 2 hours with no comment explaining it.")


# ---------------------------------------------------------------------------
# SITE
# ---------------------------------------------------------------------------

def _site_days_and_ot(daily_rows, site, date_from=None, date_to=None):
    """
    Returns {(emp_no, month_year, site): [days, ot]}. Always keyed by site
    too - not just when a specific site is picked - so the exact same
    aggregation works whether you're looking at one site or "All Sites":
    with one site chosen, every key naturally shares that one site; with
    "All Sites" (site=None), each worker gets one row per site they
    actually worked, instead of everything getting collapsed together.
    """
    agg = defaultdict(lambda: [0.0, 0.0])
    for r in daily_rows:
        if site and str(r.site).strip() != str(site).strip():
            continue
        if (date_from or date_to) and not _in_range(r.full_date, date_from, date_to):
            continue
        half = 0.0
        if r.am.lower() == "present":
            half += 0.5
        if r.pm.lower() == "present":
            half += 0.5
        agg[(r.emp_no, r.month_year, r.site)][0] += half
        agg[(r.emp_no, r.month_year, r.site)][1] += r.ot
    return agg


def site_headcount(daily_rows, summaries, filters):
    site = filters.get("site")
    agg = _site_days_and_ot(daily_rows, site, filters.get("date_from"), filters.get("date_to"))
    name_lookup = {(r.emp_no, r.month_year): r.emp_name for r in daily_rows}
    out = [{"emp_no": k[0], "name": name_lookup.get((k[0], k[1]), ""), "site": k[2],
             "days": round(v[0], 1), "month": k[1]}
           for k, v in agg.items() if v[0] > 0]
    if site:
        cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("days", "Days at Site")]
        title = f"Site Headcount - Site {site}"
    else:
        cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("site", "Site"), ("days", "Days")]
        title = "Site Headcount - All Sites"
    total_days = round(sum(r["days"] for r in out), 1)
    return ReportResult(title, cols, out,
                         totals={"emp_no": f"{len(out)} workers", "days": total_days})


def site_roster(daily_rows, summaries, filters):
    site = filters.get("site")
    rows = [r for r in daily_rows if str(r.site).strip() == str(site).strip()]
    rows = _apply_common_filters(rows, {k: v for k, v in filters.items() if k != "site"})
    out = [{"emp_no": r.emp_no, "name": r.emp_name, "trade": r.trade, "date": r.full_date,
            "am": r.am, "pm": r.pm, "engineer": r.engineer} for r in rows]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
            ("date", "Date"), ("am", "A.M"), ("pm", "P.M"), ("engineer", "Engineer")]
    return ReportResult(f"Site Roster - Site {site}", cols, out)


def salary_by_site(daily_rows, summaries, filters):
    """
    One combined report with two calculation modes, chosen automatically:
    - No date range set -> apportions each worker's FULL Final Salary by
      their share of days worked at this site (their whole card period).
    - Date range set -> calculates salary for just that exact window, using
      each worker's daily rate (monthly salary / 30) x days present in it.
    """
    if filters.get("date_from") or filters.get("date_to"):
        return _salary_by_site_partial_period(daily_rows, summaries, filters)
    return _salary_by_site_apportioned(daily_rows, summaries, filters)


def _salary_by_site_apportioned(daily_rows, summaries, filters):
    """Full month's Final Salary, split by days worked at each site that month."""
    site = filters.get("site")
    agg = _site_days_and_ot(daily_rows, site, filters.get("date_from"), filters.get("date_to"))
    sum_lookup = {(s.emp_no, s.month_year): s for s in summaries}

    out = []
    total_salary = 0.0
    for (emp_no, month_year, row_site), (site_days, site_ot) in agg.items():
        s = sum_lookup.get((emp_no, month_year))
        if not s or s.present_days <= 0:
            continue
        share = site_days / s.present_days
        salary = round(s.final_salary * share, 2)
        row = {"emp_no": emp_no, "name": s.emp_name, "trade": s.trade,
               "month": month_year, "days_at_site": round(site_days, 1),
               "ot_at_site": round(site_ot, 1), "apportioned_salary": salary}
        if not site:
            row["site"] = row_site
        out.append(row)
        total_salary += salary

    if site:
        cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
                ("month", "Month"), ("days_at_site", "Days at Site"), ("ot_at_site", "OT Hours at Site"),
                ("apportioned_salary", "Salary (AED)")]
        title = f"Salary by Site - Site {site} (Whole Card Period)"
    else:
        cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"), ("site", "Site"),
                ("month", "Month"), ("days_at_site", "Days at Site"), ("ot_at_site", "OT Hours at Site"),
                ("apportioned_salary", "Salary (AED)")]
        title = "Salary by Site - All Sites (Whole Card Period)"
    return ReportResult(title, cols, out,
                         totals={"emp_no": f"{len(out)} workers", "apportioned_salary": round(total_salary, 2)},
                         note="No date range set - splitting each worker's whole-period Final Salary by their "
                              "share of days at each site. Set a date range to instead calculate salary for an "
                              "exact window.")


def _salary_by_site_partial_period(daily_rows, summaries, filters):
    """Prorated salary for an exact date window, using each worker's daily rate."""
    site = filters.get("site")
    date_from, date_to = filters.get("date_from"), filters.get("date_to")
    sum_lookup = {(s.emp_no, s.month_year): s for s in summaries}

    agg = defaultdict(lambda: [0.0, 0.0])   # (present_half_days, ot_hours)
    for r in daily_rows:
        if site and str(r.site).strip() != str(site).strip():
            continue
        if not _in_range(r.full_date, date_from, date_to):
            continue
        half = 0.0
        if r.am.lower() == "present":
            half += 0.5
        if r.pm.lower() == "present":
            half += 0.5
        agg[(r.emp_no, r.month_year, r.site)][0] += half
        agg[(r.emp_no, r.month_year, r.site)][1] += r.ot

    out = []
    total = 0.0
    for (emp_no, month_year, row_site), (days, ot) in agg.items():
        s = sum_lookup.get((emp_no, month_year))
        if not s or s.total_salary <= 0:
            continue
        daily_rate = s.total_salary / 30.0
        salary_for_period = round(days * daily_rate, 2)
        row = {"emp_no": emp_no, "name": s.emp_name, "trade": s.trade,
               "days_present": round(days, 1), "ot_hours": round(ot, 1),
               "salary_for_period": salary_for_period}
        if not site:
            row["site"] = row_site
        out.append(row)
        total += salary_for_period

    if site:
        cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
                ("days_present", "Days Present"), ("ot_hours", "OT Hours"),
                ("salary_for_period", "Salary (AED)")]
    else:
        cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"), ("site", "Site"),
                ("days_present", "Days Present"), ("ot_hours", "OT Hours"),
                ("salary_for_period", "Salary (AED)")]
    label = f"{date_from} to {date_to}" if date_from and date_to else "selected period"
    title = f"Salary by Site - Site {site} (Period: {label})" if site else f"Salary by Site - All Sites (Period: {label})"
    return ReportResult(title, cols, out,
                         totals={"emp_no": f"{len(out)} workers", "salary_for_period": round(total, 2)},
                         note="Prorated using each worker's monthly salary / 30 x days present in this exact window.")


def ot_by_site(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    agg = defaultdict(lambda: [0.0, ""])
    for r in rows:
        agg[(r.emp_no, r.site)][0] += r.ot
        agg[(r.emp_no, r.site)][1] = r.emp_name
    out = [{"emp_no": k[0], "name": v[1], "site": k[1], "ot_hours": round(v[0], 1)}
           for k, v in agg.items() if v[0] > 0]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("site", "Site"), ("ot_hours", "OT Hours")]
    return ReportResult("OT Hours by Site", cols, out)


def bh_by_site(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    agg = defaultdict(lambda: [0.0, ""])
    for r in rows:
        agg[(r.emp_no, r.site)][0] += r.bh
        agg[(r.emp_no, r.site)][1] = r.emp_name
    out = [{"emp_no": k[0], "name": v[1], "site": k[1], "bh_hours": round(v[0], 1)}
           for k, v in agg.items() if v[0] > 0]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("site", "Site"), ("bh_hours", "BH Hours")]
    return ReportResult("BH Hours by Site", cols, out)


def site_cost_center(daily_rows, summaries, filters):
    """
    Total cost centered on each SITE (not each worker) for a given date
    range - the "what did each site actually cost us" view, as opposed
    to salary_by_site which is centered on each worker's own salary
    apportionment. One row per site, aggregated across every worker who
    was present there in the window.

    Cost per attendance day is that worker's own daily rate (their card's
    total_salary / 30), plus their own OT/BH hours on that day at their
    own hourly rate (daily rate / 8) - the exact same per-worker formula
    used everywhere else in this app (recalculate_from_daily_rows), just
    summed by site instead of by worker. No date range set uses every
    date on file.
    """
    date_from, date_to = filters.get("date_from"), filters.get("date_to")
    sum_lookup = {(s.emp_no, s.month_year): s for s in summaries}

    agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])  # site -> [present_half_days, ot_hours, bh_hours, cost]
    workers_by_site = defaultdict(set)
    for r in daily_rows:
        if not r.site:
            continue
        if (date_from or date_to) and not _in_range(r.full_date, date_from, date_to):
            continue
        s = sum_lookup.get((r.emp_no, r.month_year))
        if not s or s.total_salary <= 0:
            continue
        daily_rate = s.total_salary / 30.0
        hourly_rate = daily_rate / 8.0

        half = 0.0
        if r.am.lower() == "present":
            half += 0.5
        if r.pm.lower() == "present":
            half += 0.5

        cost = (half * daily_rate) + (r.ot * hourly_rate) + (r.bh * hourly_rate)

        entry = agg[r.site]
        entry[0] += half
        entry[1] += r.ot
        entry[2] += r.bh
        entry[3] += cost
        workers_by_site[r.site].add(r.emp_no)

    out = [{"site": site, "worker_count": len(workers_by_site[site]),
            "days_present": round(v[0], 1), "ot_hours": round(v[1], 1), "bh_hours": round(v[2], 1),
            "total_cost": round(v[3], 2),
            "avg_cost_per_worker": round(v[3] / len(workers_by_site[site]), 2) if workers_by_site[site] else 0,
            "avg_cost_per_day": round(v[3] / v[0], 2) if v[0] else 0}
           for site, v in agg.items() if workers_by_site[site]]
    out.sort(key=lambda r: r["total_cost"], reverse=True)

    cols = [("site", "Site"), ("worker_count", "Workers"), ("days_present", "Days Present"),
            ("ot_hours", "OT Hours"), ("bh_hours", "BH Hours"), ("total_cost", "Total Cost (AED)"),
            ("avg_cost_per_worker", "Avg Cost per Worker (AED)"), ("avg_cost_per_day", "Avg Cost per Day (AED)")]
    label = f"{date_from} to {date_to}" if date_from and date_to else "all dates on file"
    total_cost_all = round(sum(r["total_cost"] for r in out), 2)
    total_workers_all = sum(r["worker_count"] for r in out)
    total_days_all = round(sum(r["days_present"] for r in out), 1)
    return ReportResult(
        f"Cost Center - Sitewise ({label})", cols, out,
        # avg_cost_per_worker/avg_cost_per_day are ratios, not additive -
        # summing them across sites (the default auto-total behavior)
        # would produce a meaningless "sum of averages", so these are
        # explicitly set to the genuine overall average instead.
        totals={"site": f"{len(out)} site(s)",
                "avg_cost_per_worker": round(total_cost_all / total_workers_all, 2) if total_workers_all else 0,
                "avg_cost_per_day": round(total_cost_all / total_days_all, 2) if total_days_all else 0},
        note="Cost = each worker's own daily rate x days present at this site, plus their OT/BH hours at "
             "their own hourly rate, summed across every worker who was present at that site in this window.")


def multi_site_workers(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, {k: v for k, v in filters.items() if k != "site"})
    sites_by_emp = defaultdict(set)
    name_lookup = {}
    for r in rows:
        if r.site:
            sites_by_emp[(r.emp_no, r.month_year)].add(r.site)
            name_lookup[(r.emp_no, r.month_year)] = r.emp_name
    out = [{"emp_no": k[0], "name": name_lookup[k], "month": k[1],
            "sites": ", ".join(sorted(v)), "site_count": len(v)}
           for k, v in sites_by_emp.items() if len(v) > 1]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("month", "Month"),
            ("sites", "Sites"), ("site_count", "Number of Sites")]
    return ReportResult("Multi-Site Workers", cols, out)


# ---------------------------------------------------------------------------
# SALARY / PAYROLL
# ---------------------------------------------------------------------------

def _filter_summaries(summaries, filters):
    out = []
    for s in summaries:
        if filters.get("emp_no") and s.emp_no != filters["emp_no"]:
            continue
        if filters.get("trade") and s.trade.lower() != filters["trade"].lower():
            continue
        out.append(s)
    return out


def full_salary_summary(daily_rows, summaries, filters):
    sums = _filter_summaries(summaries, filters)
    out = [{"emp_no": s.emp_no, "name": s.emp_name, "trade": s.trade, "month": s.month_year,
            "present_days": s.present_days, "ot_hours": s.ot_hours,
            "final_salary": s.final_salary, "flag": "CHECK" if s.mismatch else ""} for s in sums]
    total = round(sum(s.final_salary for s in sums), 2)
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("trade", "Trade"),
            ("month", "Month"), ("present_days", "Present Days"), ("ot_hours", "OT Hours"),
            ("final_salary", "Final Salary (AED)"), ("flag", "Flag")]
    return ReportResult("Full Salary Summary", cols, out,
                         totals={"emp_no": f"{len(out)} workers", "final_salary": total})


def ot_amount_summary(daily_rows, summaries, filters):
    sums = _filter_summaries(summaries, filters)
    out = [{"emp_no": s.emp_no, "name": s.emp_name, "ot_hours": s.ot_hours,
            "ot_amount": round(s.ot_amount, 2)} for s in sums if s.ot_hours > 0]
    total = round(sum(s.ot_amount for s in sums), 2)
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("ot_hours", "OT Hours"),
            ("ot_amount", "OT Amount (AED)")]
    return ReportResult("OT Amount Summary", cols, out, totals={"ot_amount": total})


def bh_amount_summary(daily_rows, summaries, filters):
    sums = _filter_summaries(summaries, filters)
    out = [{"emp_no": s.emp_no, "name": s.emp_name, "bh_hours": s.bh_hours,
            "bh_amount": round(s.bh_amount, 2)} for s in sums if s.bh_hours > 0]
    total = round(sum(s.bh_amount for s in sums), 2)
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("bh_hours", "BH Hours"),
            ("bh_amount", "BH Amount (AED)")]
    return ReportResult("BH Amount Summary", cols, out, totals={"bh_amount": total})


def deductions_log(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    rows = [r for r in rows if r.comments.strip()]
    out = [{"emp_no": r.emp_no, "name": r.emp_name, "date": r.full_date,
            "site": r.site, "comment": r.comments} for r in rows]
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("date", "Date"),
            ("site", "Site"), ("comment", "Comments")]
    return ReportResult("Deductions / Comments Log", cols, out)


def allowances_report(daily_rows, summaries, filters):
    sums = [s for s in _filter_summaries(summaries, filters) if s.allowances > 0]
    out = [{"emp_no": s.emp_no, "name": s.emp_name, "month": s.month_year,
            "allowances": s.allowances} for s in sums]
    total = round(sum(s.allowances for s in sums), 2)
    cols = [("emp_no", "Employee No"), ("name", "Employee Name"), ("month", "Month"),
            ("allowances", "Allowances (AED)")]
    return ReportResult("Allowances Report", cols, out, totals={"allowances": total})


def individual_worker_report(daily_rows, summaries, filters):
    emp_no = filters.get("emp_no")
    rows = _apply_common_filters([r for r in daily_rows if r.emp_no == emp_no], filters)
    sums = [s for s in summaries if s.emp_no == emp_no]
    out = [{"date": r.full_date, "am": r.am, "pm": r.pm, "ot": r.ot, "bh": r.bh,
            "site": r.site, "comments": r.comments} for r in rows]
    cols = [("date", "Date"), ("am", "A.M"), ("pm", "P.M"), ("ot", "OT"), ("bh", "BH"),
            ("site", "Site"), ("comments", "Comments")]
    total_salary = round(sum(s.final_salary for s in sums), 2)
    name = sums[0].emp_name if sums else ""
    return ReportResult(f"Worker Report - {emp_no} {name}", cols, out,
                         totals={"date": f"Total Final Salary across shown period: AED {total_salary:,.2f}"})


# ---------------------------------------------------------------------------
# TRADE / SUPERVISION
# ---------------------------------------------------------------------------

def headcount_by_trade(daily_rows, summaries, filters):
    sums = _filter_summaries(summaries, filters)
    agg = defaultdict(int)
    for s in sums:
        agg[s.trade or "(blank)"] += 1
    out = [{"trade": k, "headcount": v} for k, v in sorted(agg.items(), key=lambda x: -x[1])]
    cols = [("trade", "Trade"), ("headcount", "Headcount")]
    return ReportResult("Headcount by Trade", cols, out)


def trade_site_breakdown(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    agg = defaultdict(set)
    for r in rows:
        if r.site:
            agg[(r.trade or "(blank)", r.site)].add(r.emp_no)
    out = [{"trade": k[0], "site": k[1], "headcount": len(v)} for k, v in agg.items()]
    out.sort(key=lambda x: (x["trade"], x["site"]))
    cols = [("trade", "Trade"), ("site", "Site"), ("headcount", "Headcount")]
    return ReportResult("Trade x Site Breakdown", cols, out)


def engineer_report(daily_rows, summaries, filters):
    rows = _apply_common_filters(daily_rows, filters)
    agg = defaultdict(lambda: [set(), 0])
    for r in rows:
        if not r.engineer:
            continue
        key = r.engineer
        agg[key][0].add(r.emp_no)
        agg[key][1] += 1
    out = [{"engineer": k, "workers_supervised": len(v[0]), "day_records": v[1]}
           for k, v in agg.items()]
    out.sort(key=lambda x: -x["day_records"])
    cols = [("engineer", "Engineer"), ("workers_supervised", "Workers Supervised"),
            ("day_records", "Day-Records")]
    return ReportResult("Engineer-wise Report", cols, out)


# ---------------------------------------------------------------------------
# REPORT REGISTRY - used by the GUI to wire buttons
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# EXTRA COLUMN CATALOG - used by the GUI's "+ Add Columns" checkboxes
# ---------------------------------------------------------------------------
# Fields available to add onto any report whose rows are per-worker-per-month
# (grain='summary'). key -> (display header, extractor from an EmployeeSummary)
SUMMARY_EXTRA_FIELDS = {
    "total_salary": ("Total Salary (AED)", lambda s: s.total_salary),
    "basic_pay": ("Basic Pay (AED)", lambda s: s.basic_pay_input),
    "final_salary": ("Final Salary (AED)", lambda s: s.final_salary),
    "present_days": ("Present Days", lambda s: s.present_days),
    "absent_days": ("Absent Days", lambda s: s.absent_days),
    "sick_days": ("Sick Days", lambda s: s.sick_days),
    "medical_days": ("Medical Days", lambda s: s.medical_days),
    "friday_days": ("Friday Days", lambda s: s.friday_days),
    "sunday_days": ("Sunday Days", lambda s: s.sunday_days),
    "holiday_days": ("Holiday Days", lambda s: s.holiday_days),
    "leave_days": ("Leave Days", lambda s: s.leave_days),
    "ot_hours": ("OT Hours", lambda s: s.ot_hours),
    "ot_amount": ("OT Amount (AED)", lambda s: s.ot_amount),
    "bh_hours": ("BH Hours", lambda s: s.bh_hours),
    "bh_amount": ("BH Amount (AED)", lambda s: s.bh_amount),
    "total_salary_component": ("Total Salary Component (AED)", lambda s: s.total_salary_component),
    "deduction": ("Absence Deduction (AED)", lambda s: s.deduction),
    "other_deduction": ("Other Deductions (AED)", lambda s: s.other_deduction),
    "allowances": ("Allowances (AED)", lambda s: s.allowances),
    "cached_final_salary": ("Card's Own Final Salary (AED)", lambda s: s.cached_final_salary),
    "adjustments_total": ("Adjustments Total (AED)", lambda s: s.adjustments_total()),
    "adjusted_final_salary": ("Adjusted Final Salary (AED)", lambda s: s.adjusted_final_salary()),
    "trade": ("Trade", lambda s: s.trade),
}

# Fields available to add onto any report whose rows are per-worker-per-day
# (grain='daily'). key -> (display header, extractor from a DailyRow)
DAILY_EXTRA_FIELDS = {
    "am": ("A.M", lambda r: r.am),
    "pm": ("P.M", lambda r: r.pm),
    "site": ("Site", lambda r: r.site),
    "engineer": ("Engineer", lambda r: r.engineer),
    "trade": ("Trade", lambda r: r.trade),
    "ot": ("OT", lambda r: r.ot),
    "bh": ("BH", lambda r: r.bh),
    "comments": ("Comments", lambda r: r.comments),
}


# Fields available specifically on reports that show a per-site "days" figure
# for a worker (currently: Site Headcount). These are COMPUTED per-row using
# both the row itself (its "days" value) and the worker's EmployeeSummary,
# rather than being a flat field pulled straight off the summary - e.g.
# "salary for the days shown" has to be apportioned using THIS row's day
# count, not the worker's whole-month total. key -> (header, is_summable, fn(row, summary))
SITE_EXTRA_FIELDS = {
    "apportioned_salary": ("Salary for Days Shown (AED)", True,
        lambda row, s: round(s.final_salary * (row.get("days", 0) / s.present_days), 2)
        if s and s.present_days else 0),
    "apportioned_ot_amount": ("OT Amount for Days Shown (AED)", True,
        lambda row, s: round(s.ot_amount * (row.get("days", 0) / s.present_days), 2)
        if s and s.present_days else 0),
    "apportioned_bh_amount": ("BH Amount for Days Shown (AED)", True,
        lambda row, s: round(s.bh_amount * (row.get("days", 0) / s.present_days), 2)
        if s and s.present_days else 0),
}


SITE_AGGREGATE_EXTRA_FIELDS = {
    "ot_amount_site": ("OT Amount (AED)",
        lambda half, ot, bh, s: ot * (s.total_salary / 30.0 / 8.0) if s and s.total_salary else 0),
    "bh_amount_site": ("BH Amount (AED)",
        lambda half, ot, bh, s: bh * (s.total_salary / 30.0 / 8.0) if s and s.total_salary else 0),
    "basic_pay_cost_site": ("Basic Pay Cost at Site (AED)",
        lambda half, ot, bh, s: half * (s.basic_pay_input / 30.0) if s and s.basic_pay_input else 0),
    "deduction_site": ("Deduction Amount at Site (AED)",
        lambda half, ot, bh, s: (half / s.present_days) * s.deduction
        if s and s.present_days and s.deduction else 0),
}


# ---------------------------------------------------------------------------
# REPORT BUILDER - one screen, pick your own combination of dimensions and
# measures, instead of hunting for a dedicated report or asking for a new
# one to be built. Deliberately NOT a raw spreadsheet-style pivot table:
# a real pivot just SUMs whatever column you drop in, which silently
# produces a wrong number for anything that isn't a plain sum - half-day
# attendance counts (0.5 per AM/PM Present, not 1 per row), and salary
# figures that are correct PER WORKER but meaningless summed blindly
# across an arbitrary daily-attendance grouping. Every measure below
# already knows its own correct computation, so picking any combination
# can't produce a silently-wrong number the way a generic pivot could.
#
# Two data sources, since they're two different grains that don't mix in
# one table: "daily" (one row per worker per day - has Site/Engineer/
# A.M./P.M./OT/BH) and "summary" (one row per worker per cycle - has
# Final Salary/Basic Pay/day-totals). Site-apportioned salary and
# sitewise cost (Salary by Site, Cost Center - Sitewise) are deliberately
# NOT included as generic measures here - they need a real per-worker
# join between daily attendance and that worker's own monthly summary,
# which this generic day/summary grouping can't safely reproduce; use
# those two dedicated reports instead for that specific question.
# ---------------------------------------------------------------------------

BUILDER_DAILY_DIMENSIONS = {
    "emp_no": "Employee No", "name": "Employee Name", "trade": "Trade",
    "company": "Company",
    "site": "Site", "engineer": "Engineer", "date": "Date", "month": "Month",
}

BUILDER_DAILY_MEASURES = {
    "days_present": "Days Present", "days_absent": "Days Absent", "days_sick": "Days Sick",
    "days_medical": "Days Medical", "days_friday": "Days Friday", "days_sunday": "Days Sunday",
    "days_holiday": "Days Holiday", "days_leave": "Days Leave",
    "ot_hours": "OT Hours", "bh_hours": "BH Hours",
    "worker_count": "Headcount", "record_count": "Man-Days",
    # Final Salary Cost needs each row's OWN worker's monthly summary to
    # compute (apportioning that worker's whole-cycle figure by their
    # share of present days shown in this grouping) - the same
    # apportionment logic "Salary by Site" already uses, reused here so
    # a builder combination like "group by Site, show Final Salary Cost,
    # filtered to a date range" produces the same answer that dedicated
    # report would for the same window. Basic Pay Cost / Total Salary
    # Cost (the same apportionment against different underlying figures)
    # were removed on request - Final Salary Cost alone covers what's
    # actually used.
    "final_salary_cost": "Final Salary Cost (AED)",
    # OT/BH Amount - each row's own OT/BH hours valued at that SAME
    # worker's own hourly rate (daily_rate/8, daily_rate = their whole
    # monthly total_salary/30) - identical formula recalculate_from_
    # daily_rows() uses for the real payroll figure, just applied per
    # row here so it can be summed by whichever dimension is grouped on.
    "ot_amount": "OT Amount (AED)", "bh_amount": "BH Amount (AED)",
}

BUILDER_SUMMARY_DIMENSIONS = {
    "emp_no": "Employee No", "name": "Employee Name", "trade": "Trade", "month_year": "Month",
    "company": "Company", "site": "Site",
}

BUILDER_SUMMARY_MEASURES = {
    "present_days": "Present Days", "absent_days": "Absent Days", "sick_days": "Sick Days",
    "medical_days": "Medical Days", "friday_days": "Friday Days", "sunday_days": "Sunday Days",
    "holiday_days": "Holiday Days", "leave_days": "Leave Days",
    "ot_hours": "OT Hours", "bh_hours": "BH Hours",
    "basic_pay_input": "Basic Pay (AED)", "total_salary_component": "Total Salary (AED)",
    "deduction": "Absence Deduction (AED)", "ot_amount": "OT Amount (AED)", "bh_amount": "BH Amount (AED)",
    # Adjustments entered by hand on the Salary Adjustments screen, split
    # the way payroll is actually discussed: what was added, what was
    # taken off, and the two together.
    "additions": "Additions (AED)", "addition_reasons": "What the additions were for",
    "deductions": "Deductions (AED)", "deduction_reasons": "What the deductions were for",
    "net_adjustment": "Net Adjustment (AED)",
    "final_salary": "Final Salary (AED)", "adjusted_final_salary": "Adjusted Final Salary (AED)",
    "worker_count": "Headcount",
}


# Which company employs each worker, by employee number. Filled in by
# build_custom_report before grouping starts, because neither a daily
# row nor a summary carries the company itself.
COMPANY_BY_EMP = {}

# Measures that read as words rather than numbers, so they are gathered
# and joined instead of added up, and never totalled at the foot.
TEXT_MEASURES = {"addition_reasons", "deduction_reasons"}


def _company_of(emp_no):
    return COMPANY_BY_EMP.get(emp_no) or "Infinia"


def _builder_daily_dim_value(r, dim_key):
    if dim_key == "company":
        return _company_of(r.emp_no)
    if dim_key == "emp_no":
        return r.emp_no
    if dim_key == "name":
        return r.emp_name
    if dim_key == "trade":
        return r.trade
    if dim_key == "site":
        return (r.site or "").strip() or "(blank)"
    if dim_key == "engineer":
        return (r.engineer or "").strip() or "(blank)"
    if dim_key == "date":
        return r.full_date
    if dim_key == "month":
        return r.month_year
    return ""


def _builder_daily_measure_contribution(r, measure_key, matched_summary=None):
    """The contribution of ONE daily row toward a measure - summed across
    every row in a group to get that group's total. Present/Absent/etc are
    half-day counts (0.5 per A.M. or P.M. marked with that status), the
    same convention used everywhere else in this app - never a flat 1 per
    row, which would double-count a worker present for both halves of a
    single day.

    matched_summary: this row's own worker's EmployeeSummary for the same
    (emp_no, month_year), if one exists - only needed for the cost
    measures, which apportion that worker's whole-cycle figure by their
    share of present days (same logic "Salary by Site" already uses)."""
    am = (r.am or "").strip().lower()
    pm = (r.pm or "").strip().lower()
    if measure_key == "record_count":
        return 1
    if measure_key == "ot_hours":
        return r.ot or 0
    if measure_key == "bh_hours":
        return r.bh or 0
    if measure_key in ("ot_amount", "bh_amount"):
        if not matched_summary or not matched_summary.total_salary:
            return 0
        hourly_rate = (matched_summary.total_salary / 30.0) / 8.0
        hours = (r.ot or 0) if measure_key == "ot_amount" else (r.bh or 0)
        return hours * hourly_rate
    if measure_key == "final_salary_cost":
        # Apportioned across every PAID day (Present, Sick, Medical,
        # Friday, Holiday - the exact same set that pays identically in
        # recalculate_from_daily_rows, the single source of truth for
        # the real payroll formula), not Present days alone. Confirmed
        # directly as a real bug otherwise: a Holiday row's am/pm is
        # "Holiday", never "Present", so the old formula's numerator was
        # always 0 for it - not just cosmetic, since a worker who was
        # entirely on Holiday for the period (0 Present days) had EVERY
        # row's contribution come out to 0, silently reporting their
        # whole actual cost as zero rather than the real paid amount.
        if not matched_summary:
            return 0
        paid_days_total = (getattr(matched_summary, "present_days", 0) or 0)
        paid_days_total += (matched_summary.sick_days + matched_summary.medical_days
                             + matched_summary.friday_days + matched_summary.sunday_days
                             + matched_summary.holiday_days)
        paid = {"present", "sick", "medical", "friday", "sunday", "holiday"}

        if paid_days_total:
            half = (0.5 if am in paid else 0) + (0.5 if pm in paid else 0)
            return (half / paid_days_total) * matched_summary.adjusted_final_salary()

        # No paid days at all - the worker was absent (or on unpaid
        # leave) for the whole period, so their cycle figure is a pure
        # NEGATIVE deduction. Apportioning it across paid days would
        # divide by zero, and returning 0 silently dropped a real cost
        # from site reports while the Live Card and payroll correctly
        # showed it. Spread it across the unpaid days instead so the
        # deduction still lands, on the site those days were logged to.
        unpaid_days_total = (matched_summary.absent_days or 0) + (matched_summary.leave_days or 0)
        if not unpaid_days_total:
            return 0
        unpaid = {"absent", "leave"}
        half = (0.5 if am in unpaid else 0) + (0.5 if pm in unpaid else 0)
        return (half / unpaid_days_total) * matched_summary.adjusted_final_salary()
    status_map = {"days_present": "present", "days_absent": "absent", "days_sick": "sick",
                  "days_medical": "medical", "days_friday": "friday", "days_sunday": "sunday",
                  "days_holiday": "holiday", "days_leave": "leave"}
    target = status_map.get(measure_key)
    if target is None:
        return 0
    return (0.5 if am == target else 0) + (0.5 if pm == target else 0)


def _builder_summary_dim_value(s, dim_key, site_lookup=None):
    if dim_key == "company":
        return _company_of(s.emp_no)
    if dim_key == "emp_no":
        return s.emp_no
    if dim_key == "name":
        return s.emp_name
    if dim_key == "trade":
        return s.trade
    if dim_key == "month_year":
        return s.month_year
    if dim_key == "site":
        # EmployeeSummary itself has no site (it's a per-cycle
        # aggregate; a worker can genuinely work several sites in one
        # cycle) - the value here is that worker's MOST FREQUENT site
        # that cycle, derived from their own daily rows via site_lookup
        # (built once per report run in build_custom_report, not
        # recomputed per row). "(blank)" for a worker with no site
        # recorded at all that cycle, same convention the daily-rows
        # "site" dimension already uses.
        if site_lookup is None:
            return "(blank)"
        return site_lookup.get((s.emp_no, s.month_year), "(blank)")
    return ""


def build_custom_report(data_source, dimensions, measures, filters, daily_rows, summaries,
                        company_by_emp=None):
    """
    The Report Builder's aggregation engine - groups by whichever
    dimensions were picked, computes whichever measures were picked, for
    whichever data source. See the module-level comment above for why
    this is deliberately NOT a raw spreadsheet pivot table.
    """
    dimensions = list(dimensions) if dimensions else []
    measures = list(measures) if measures else []
    if not dimensions and not measures:
        return ReportResult("Custom Report", [("note", "Note")],
                             [{"note": "Pick at least one dimension or measure to see results."}])

    global COMPANY_BY_EMP
    COMPANY_BY_EMP = company_by_emp or {}

    groups = {}   # dimension-value tuple -> {"emp_nos": set(), measure_key: running_total, ...}
    order = []    # preserves first-seen order of group keys

    if data_source == "daily":
        rows = _apply_common_filters(daily_rows, filters)
        dim_fn = _builder_daily_dim_value
        dim_catalog, measure_catalog = BUILDER_DAILY_DIMENSIONS, BUILDER_DAILY_MEASURES
        source_items = rows
        get_emp_no = lambda r: r.emp_no
        summary_lookup = {(s.emp_no, s.month_year): s for s in summaries}

        def measure_fn(r, measure_key):
            return _builder_daily_measure_contribution(r, measure_key, summary_lookup.get((r.emp_no, r.month_year)))
    else:
        sums = _filter_summaries(summaries, filters)
        dim_catalog, measure_catalog = BUILDER_SUMMARY_DIMENSIONS, BUILDER_SUMMARY_MEASURES
        source_items = sums
        get_emp_no = lambda s: s.emp_no

        # Precomputed once per report run, not per row - each worker's
        # MOST FREQUENT site that cycle, derived from their own daily
        # rows (a worker can genuinely work several sites in one cycle,
        # and EmployeeSummary itself has no single "site" of its own).
        site_counts = defaultdict(lambda: defaultdict(int))
        for r in daily_rows:
            if (r.site or "").strip():
                site_counts[(r.emp_no, r.month_year)][r.site.strip()] += 1
        site_lookup = {key: max(counts.items(), key=lambda kv: kv[1])[0]
                        for key, counts in site_counts.items()}

        def dim_fn(s, d):
            return _builder_summary_dim_value(s, d, site_lookup)

        def measure_fn(s, measure_key):
            if measure_key in ("worker_count",):
                return 0  # handled via emp_nos set below, not summed here
            if measure_key == "adjusted_final_salary":
                return s.adjusted_final_salary()
            # Bonuses and allowances added; advances and fines taken off.
            if measure_key == "additions":
                return sum(a.amount for a in s.adjustments if not a.is_deduction)
            if measure_key == "deductions":
                return sum(a.amount for a in s.adjustments if a.is_deduction)
            if measure_key == "net_adjustment":
                return sum((-a.amount if a.is_deduction else a.amount) for a in s.adjustments)
            # Why the money moved, in the words whoever entered it used.
            # Collected as text rather than summed - "Site bonus 300,
            # Food allowance 200" tells the story a bare 500 does not.
            if measure_key in ("addition_reasons", "deduction_reasons"):
                want_ded = measure_key == "deduction_reasons"
                return [f"{a.description} {a.amount:,.0f}"
                        for a in s.adjustments if bool(a.is_deduction) == want_ded]
            return getattr(s, measure_key, 0) or 0

    for item in source_items:
        key = tuple(dim_fn(item, d) for d in dimensions) if dimensions else ("(all)",)
        if key not in groups:
            groups[key] = {"emp_nos": set()}
            order.append(key)
        g = groups[key]
        g["emp_nos"].add(get_emp_no(item))
        for m in measures:
            if m == "worker_count":
                continue
            v = measure_fn(item, m)
            if isinstance(v, list):          # a text measure, such as a reason
                g.setdefault(m, [])
                g[m].extend(v)
            else:
                g[m] = g.get(m, 0) + v

    out = []
    for key in order:
        g = groups[key]
        row = {}
        for i, d in enumerate(dimensions):
            row[f"dim_{i}"] = key[i]
        for m in measures:
            if m == "worker_count":
                row[m] = len(g["emp_nos"])
            elif m in TEXT_MEASURES:
                # Same reason twice in one group is worth seeing once.
                seen, uniq = set(), []
                for t in g.get(m, []):
                    if t not in seen:
                        seen.add(t); uniq.append(t)
                row[m] = ", ".join(uniq) or "-"
            else:
                row[m] = round(g.get(m, 0), 2)
        out.append(row)

    if dimensions:
        out.sort(key=lambda r: [(v is None, v) for v in (r[f"dim_{i}"] for i in range(len(dimensions)))])

    dim_cols = [(f"dim_{i}", dim_catalog[d]) for i, d in enumerate(dimensions)]
    measure_cols = [(m, measure_catalog[m]) for m in measures]
    cols = dim_cols + measure_cols
    source_label = "Daily Attendance" if data_source == "daily" else "Worker Summary"
    return ReportResult(f"Custom Report ({source_label})", cols, out)


REPORT_REGISTRY = {
    "daily_roster":                 ("Daily Roster",                    daily_roster,                 ["date"],
                                      "Shows who was Present, Absent, Sick, or on Holiday on one specific date, and which site they were at.", 'daily'),
    "monthly_attendance_summary":   ("Monthly Attendance Summary",      monthly_attendance_summary,   [],
                                      "One row per worker per cycle, with their Present/Absent/Sick/Medical/Holiday/Leave day-counts for that period.", 'summary'),
    "absentee_report":              ("Absentee Report",                 absentee_report,              ["date_range", "site"],
                                      "Lists every day any worker was marked Absent, optionally narrowed to a date range and/or one site.", 'daily'),
    "sick_report":                  ("Sick Report",                     sick_report,                  ["date_range", "site"],
                                      "Lists every day any worker was marked Sick or Medical, optionally narrowed to a date range and/or one site.", 'daily'),
    "leave_report":                 ("Leave Report",                    leave_report,                 ["date_range", "site"],
                                      "Lists every day any worker was marked on Leave, optionally narrowed to a date range and/or one site.", 'daily'),
    "check_for_errors":             ("Check for Errors",                check_for_errors,              [],
                                      "Card-wise data quality check: missing AM/P.M status, Present days without a Site/Engineer, and BH over 2 hours with no comment.", 'daily'),

    "site_headcount":               ("Site Headcount",                  site_headcount,                ["site_required", "date_range"],
                                      "Counts how many workers were present at one site, and how many days each of them worked there.", 'site_summary'),
    "site_roster":                  ("Site Roster",                     site_roster,                   ["site_required", "date_range"],
                                      "Full day-by-day attendance list for everyone who worked at one specific site.", 'daily'),
    "salary_by_site":                ("Salary by Site",                  salary_by_site,                ["site_required", "date_range"],
                                      "Salary at one site. Leave the date range off for each worker's whole-period salary apportioned by their days at this site; set a date range to calculate salary for just that exact window instead.", 'summary'),
    "ot_by_site":                   ("OT Hours by Site",                ot_by_site,                    ["date_range", "site"],
                                      "Total overtime hours worked, broken down by worker and site.", 'summary'),
    "bh_by_site":                   ("BH Hours by Site",                bh_by_site,                    ["date_range", "site"],
                                      "Total bank-holiday hours worked, broken down by worker and site.", 'summary'),
    "site_cost_center":              ("Cost Center - Sitewise",          site_cost_center,              ["date_range"],
                                      "Total attendance-based cost for each site over a date range - one row per site, aggregated across every worker present there.", 'site_aggregate'),
    "multi_site_workers":           ("Multi-Site Workers",              multi_site_workers,            ["date_range"],
                                      "Finds anyone who worked at more than one site within the same card period - useful for checking site-apportioned salary makes sense.", 'summary'),

    "full_salary_summary":          ("Full Salary Summary",             full_salary_summary,           ["trade"],
                                      "Every worker's Final Salary for every cycle, with a grand total. Rows marked CHECK had a recalculation mismatch - verify those manually.", 'summary'),
    "ot_amount_summary":            ("OT Amount Summary",               ot_amount_summary,             [],
                                      "Overtime hours and the AED amount paid for it, per worker.", 'summary'),
    "bh_amount_summary":            ("BH Amount Summary",               bh_amount_summary,             [],
                                      "Bank-holiday hours and the AED amount paid for it, per worker.", 'summary'),
    "deductions_log":               ("Deductions / Comments Log",       deductions_log,                ["date_range", "site"],
                                      "Every day-row that has a note in the Comments column (e.g. 'MC submitted', deduction notes) - a running log for payroll review.", 'daily'),
    "allowances_report":            ("Allowances Report",               allowances_report,             [],
                                      "Every worker who received an Allowances amount on their card, with the amount.", 'summary'),
    "individual_worker_report":     ("Individual Worker Report",        individual_worker_report,      ["emp_no_required", "date_range"],
                                      "Full day-by-day attendance and salary detail for one specific Employee No, across whichever cards are imported.", 'daily'),

    "headcount_by_trade":           ("Headcount by Trade",              headcount_by_trade,            [],
                                      "Counts how many workers fall under each trade (Mason, Painter, Helper, etc.).", None),
    "trade_site_breakdown":         ("Trade x Site Breakdown",          trade_site_breakdown,          ["date_range"],
                                      "Cross-tabulates trade against site - e.g. how many masons worked at Site 902 versus Site 306.", None),
    "engineer_report":              ("Engineer-wise Report",            engineer_report,               ["date_range", "site"],
                                      "Shows how many workers and day-records each supervising engineer is associated with, across the daily grid's Engineer column.", None),
}
