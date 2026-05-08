"""IST clock for the prototype demo build.

The rules engine takes `today` as an input and is timezone-agnostic by
design (§10.2). This module is the canonical answer to "what's today in
the jurisdiction we operate in" — Asia/Kolkata. Use this instead of
`date.today()` anywhere a real human-facing 'today' is needed.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def today_ist() -> date:
    return datetime.now(IST).date()
