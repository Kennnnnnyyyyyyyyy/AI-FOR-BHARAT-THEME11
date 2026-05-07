"""Date math for the rules engine — pure functions, python-dateutil only (§10.2).

No imports from `api/`, `workers/`, `db/`, `extraction/`, `ingestion/`, or
`audit/`. The rules engine is the architectural keystone and must be testable
with no I/O dependencies (§6).

Holiday and working-day handling is deliberately out of scope for the
prototype. The §10.2 contract reserves this module for that future addition.
"""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]


def add_days(base: date, n: int) -> date:
    return base + relativedelta(days=n)


def add_weeks(base: date, n: int) -> date:
    return base + relativedelta(weeks=n)


def add_months(base: date, n: int) -> date:
    """Calendar-month addition (e.g. 2026-04-17 + 6 months = 2026-10-17).

    Uses `dateutil.relativedelta`'s month arithmetic which handles
    end-of-month edge cases (Jan 31 + 1 month = Feb 28/29) per the
    library's documented semantics.
    """
    return base + relativedelta(months=n)


def add_period(base: date, n: int, unit: str) -> date:
    """Dispatch on a unit string from the YAML pattern table."""
    if unit == "days":
        return add_days(base, n)
    if unit == "weeks":
        return add_weeks(base, n)
    if unit == "months":
        return add_months(base, n)
    raise ValueError(f"unknown period unit: {unit!r}")
