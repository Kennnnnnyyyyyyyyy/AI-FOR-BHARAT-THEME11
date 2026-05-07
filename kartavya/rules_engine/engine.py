"""Rules engine orchestrator (§10.2).

Pure Python. No I/O at call-time except YAML table loads at import-time.
No imports from `api/`, `workers/`, `db/`, `extraction/`, `ingestion/`, or
`audit/`. Consumes `ExtractionResult` + `CaseMetadata` + `paragraphs`,
produces an `ActionPlan`.

The engine has two stages, joined into one ActionPlan:

  1. Verdict-driven items — `slp_window.yaml` maps the verdict to a
     limitation window (Article 136 SLP for `dismissed`, CPC Order 47
     review for `allowed` / `partly_allowed`, informational monitoring
     for `remanded` / `disposed_with_directions`).

  2. Directive-driven items — for each `OperativeDirection`, parse the
     paragraph text against `directive_relative_deadlines.yaml` patterns;
     compute an absolute deadline if a concrete period matches, or flag
     for officer review if only an open-ended phrase ("expeditiously",
     "forthwith") matches.

Statute citations are loaded from YAML; the engine does not hardcode
statute strings (§3.5). Severity values are validated against the
`Severity` enum at table-load time so a typo in YAML fails loudly.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml  # type: ignore[import-untyped]

from kartavya.responsibility import (
    MAPPING_REQUIRED,
    map_addressee,
    primary_respondent_designation,
)
from kartavya.rules_engine import RULE_ENGINE_VERSION
from kartavya.rules_engine.calendar import add_period
from kartavya.rules_engine.trace import directive_trace, verdict_trace
from kartavya.schemas.action_plan import ActionItem, ActionPlan, Severity
from kartavya.schemas.case import CaseMetadata
from kartavya.schemas.extraction import ExtractionResult, OperativeDirection
from kartavya.schemas.paragraph import Paragraph

_TABLE_DIR = Path(__file__).parent / "tables"
_SLP_TABLE = _TABLE_DIR / "slp_window.yaml"
_DIRECTIVE_TABLE = _TABLE_DIR / "directive_relative_deadlines.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


_SLP_RULES_CACHE: dict[str, Any] | None = None
_DIRECTIVE_TABLE_CACHE: dict[str, Any] | None = None


def _slp_table() -> dict[str, Any]:
    global _SLP_RULES_CACHE
    if _SLP_RULES_CACHE is None:
        _SLP_RULES_CACHE = _load_yaml(_SLP_TABLE)
    return _SLP_RULES_CACHE


def _directive_table() -> dict[str, Any]:
    global _DIRECTIVE_TABLE_CACHE
    if _DIRECTIVE_TABLE_CACHE is None:
        _DIRECTIVE_TABLE_CACHE = _load_yaml(_DIRECTIVE_TABLE)
    return _DIRECTIVE_TABLE_CACHE


# ---------- Verdict-driven action items ----------


def _verdict_action_item(
    verdict_value: str,
    case: CaseMetadata,
) -> ActionItem | None:
    table = _slp_table()
    rule_version: str = table["version"]
    for rule in table["rules"]:
        if rule["verdict"] != verdict_value:
            continue

        period_days: int | None = rule.get("period_days")
        deadline: date | None
        if period_days is None:
            deadline = None
        else:
            deadline = add_period(case.judgment_date, period_days, "days")

        target_role_source = rule["target_role_source"]
        if target_role_source == "primary_respondent":
            target_role = primary_respondent_designation(case)
        else:
            raise ValueError(
                f"unknown target_role_source: {target_role_source!r}"
            )

        severity = Severity(rule["severity"])

        trace = verdict_trace(
            rule_id=rule["rule_id"],
            rule_version=rule_version,
            statute=rule["statute"],
            verdict=verdict_value,
            judgment_date=case.judgment_date,
            period_days=period_days,
            deadline=deadline,
        )

        deadline_dt: datetime | None = (
            datetime.combine(deadline, datetime.min.time(), tzinfo=timezone.utc)
            if deadline is not None
            else None
        )

        return ActionItem(
            id=uuid4(),
            description=rule["description_template"].strip(),
            target_role=target_role,
            deadline=deadline_dt,
            severity=severity,
            rule_trace=trace,
        )
    return None


# ---------- Directive-driven action items ----------


_ADDRESSEE_PATTERNS = [
    re.compile(r"the\s+(first|second|third|fourth|fifth)\s+respondents?", re.I),
    re.compile(r"the\s+petitioner", re.I),
    re.compile(r"the\s+reference\s+court", re.I),
    re.compile(r"the\s+(appellate\s+authority|district\s+court|city\s+civil\s+court)", re.I),
]


def _extract_addressee(paragraph_text: str) -> str | None:
    """Best-effort extraction of the addressee phrase from a directive paragraph.

    Returns the first matching phrase verbatim (lowercased, leading "the "
    preserved) or None if no known addressee is found. Never guesses.
    """
    for pat in _ADDRESSEE_PATTERNS:
        m = pat.search(paragraph_text)
        if m:
            return m.group(0).lower()
    return None


def _resolve_target_role(
    direction: OperativeDirection,
    paragraph_text: str,
    case: CaseMetadata,
) -> str:
    addressee = _extract_addressee(paragraph_text)
    if addressee is None:
        return MAPPING_REQUIRED
    return map_addressee(addressee, case)


def _parse_period(
    paragraph_text: str,
    table: dict[str, Any],
) -> tuple[str, str, int | None, str | None, bool] | None:
    """First-match-wins parse against the directive_relative_deadlines table.

    Returns `(pattern_id, matched_phrase, period_value, period_unit,
    flagged_for_review)` or None if no pattern matched.
    """
    word_to_number: dict[str, int] = table["word_to_number"]

    for pattern in table["patterns"]:
        pattern_id: str = pattern["pattern_id"]
        regex = re.compile(pattern["regex"], re.IGNORECASE | re.DOTALL)
        match = regex.search(paragraph_text)
        if match is None:
            continue

        unit = pattern["unit"]
        flagged = bool(pattern.get("flag_for_officer_review", False))

        if unit is None or flagged:
            return (pattern_id, match.group(0), None, None, True)

        token = match.group(1).strip().lower()
        if token.isdigit():
            period_value = int(token)
        else:
            mapped = word_to_number.get(token)
            if mapped is None:
                # Token not in the table; flag for review rather than guess.
                return (pattern_id, match.group(0), None, unit, True)
            period_value = mapped

        return (pattern_id, match.group(0), period_value, unit, False)

    return None


def _directive_action_item(
    direction: OperativeDirection,
    paragraph: Paragraph,
    case: CaseMetadata,
) -> ActionItem | None:
    table = _directive_table()
    rule_version: str = table["version"]
    statute_template: str = table["statute_template"]

    parsed = _parse_period(paragraph.text, table)
    if parsed is None:
        # No deadline pattern at all — emit an item flagged for review so the
        # officer doesn't lose track of the directive. Severity ACTIVE.
        statute = statute_template.format(paragraph_index=paragraph.paragraph_index)
        target_role = _resolve_target_role(direction, paragraph.text, case)
        trace = directive_trace(
            rule_id="directive_no_deadline_pattern",
            rule_version=rule_version,
            statute=statute,
            paragraph_index=paragraph.paragraph_index,
            matched_phrase="",
            judgment_date=case.judgment_date,
            period_value=None,
            period_unit=None,
            deadline=None,
            flagged_for_review=True,
        )
        return ActionItem(
            id=uuid4(),
            description=direction.text,
            target_role=target_role,
            deadline=None,
            severity=Severity.ACTIVE,
            rule_trace=trace,
        )

    pattern_id, matched_phrase, period_value, period_unit, flagged = parsed

    deadline: date | None
    if flagged or period_value is None or period_unit is None:
        deadline = None
    else:
        deadline = add_period(case.judgment_date, period_value, period_unit)

    statute = statute_template.format(paragraph_index=paragraph.paragraph_index)
    target_role = _resolve_target_role(direction, paragraph.text, case)

    trace = directive_trace(
        rule_id=f"directive_relative_deadline:{pattern_id}",
        rule_version=rule_version,
        statute=statute,
        paragraph_index=paragraph.paragraph_index,
        matched_phrase=matched_phrase,
        judgment_date=case.judgment_date,
        period_value=period_value,
        period_unit=period_unit,
        deadline=deadline,
        flagged_for_review=flagged,
    )

    deadline_dt: datetime | None = (
        datetime.combine(deadline, datetime.min.time(), tzinfo=timezone.utc)
        if deadline is not None
        else None
    )

    return ActionItem(
        id=uuid4(),
        description=direction.text,
        target_role=target_role,
        deadline=deadline_dt,
        severity=Severity.ACTIVE,
        rule_trace=trace,
    )


# ---------- Top-level orchestrator ----------


def generate_action_plan(
    case: CaseMetadata,
    extraction: ExtractionResult,
    paragraphs: list[Paragraph],
) -> ActionPlan:
    """Compose verdict-driven and directive-driven items into one ActionPlan."""
    paragraph_by_id: dict[UUID, Paragraph] = {p.id: p for p in paragraphs}

    items: list[ActionItem] = []

    verdict_value = extraction.verdict.verdict.value
    verdict_item = _verdict_action_item(verdict_value, case)
    if verdict_item is not None:
        items.append(verdict_item)

    for direction in extraction.operative_directions:
        paragraph = paragraph_by_id.get(direction.paragraph_id)
        if paragraph is None:
            # Should not happen — extraction.operative_directions are anchored
            # by paragraph_id from the same extraction result. Skip rather
            # than crash if the invariant is ever violated upstream.
            continue
        item = _directive_action_item(direction, paragraph, case)
        if item is not None:
            items.append(item)

    return ActionPlan(
        id=uuid4(),
        case_id=extraction.case_id,
        action_items=items,
        rule_engine_version=RULE_ENGINE_VERSION,
        generated_at=datetime.now(timezone.utc),
    )


__all__ = ["generate_action_plan"]
