"""RuleTrace builders — small constructors that produce the §10.2 trace shape.

Each ActionItem carries a RuleTrace whose `computation` field is a
human-readable, single-line string suitable for the audit log and the
review UI ("judgment_date(2026-04-17) + 90 days = 2026-07-16"). The
trace is the rules engine's audit signal; keep it stable across rule
revisions so reviewers can compare outputs across versions.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from kartavya.schemas.action_plan import RuleTrace


def verdict_trace(
    *,
    rule_id: str,
    rule_version: str,
    statute: str,
    verdict: str,
    judgment_date: date,
    period_days: int | None,
    deadline: date | None,
) -> RuleTrace:
    if period_days is None or deadline is None:
        computation = (
            f"verdict({verdict}); no fixed limitation period — flagged for "
            f"officer review"
        )
    else:
        computation = (
            f"judgment_date({judgment_date.isoformat()}) + {period_days} days "
            f"= {deadline.isoformat()}"
        )
    return RuleTrace(
        rule_id=rule_id,
        rule_version=rule_version,
        statute=statute,
        triggered_by={"verdict": verdict},
        computation=computation,
    )


def directive_trace(
    *,
    rule_id: str,
    rule_version: str,
    statute: str,
    paragraph_index: int,
    matched_phrase: str,
    judgment_date: date,
    period_value: int | None,
    period_unit: str | None,
    deadline: date | None,
    flagged_for_review: bool,
) -> RuleTrace:
    triggered_by: dict[str, Any] = {
        "paragraph_index": paragraph_index,
        "matched_phrase": matched_phrase,
    }
    if flagged_for_review or period_value is None or period_unit is None or deadline is None:
        computation = (
            f"directive matched open-ended pattern {matched_phrase!r}; "
            f"no fixed period — flagged for officer review"
        )
    else:
        computation = (
            f"judgment_date({judgment_date.isoformat()}) + "
            f"{period_value} {period_unit} = {deadline.isoformat()}"
        )
    return RuleTrace(
        rule_id=rule_id,
        rule_version=rule_version,
        statute=statute,
        triggered_by=triggered_by,
        computation=computation,
    )
