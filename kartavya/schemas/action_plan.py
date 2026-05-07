"""Action plan schemas. Outputs of the rules engine.

Phase A introduces a new (`Action`, `ActionPlan`) pair alongside the legacy
(`ActionItem`, `LegacyActionPlan`) pair. Both pairs coexist for one cycle:

  * Legacy 0.1.0 path. `generate_action_plan(case, extraction, paragraphs)`
    returns a `LegacyActionPlan` of `ActionItem` entries. Used by the
    integration test that ran against the synthetic Venkateshulu fixture
    (now quarantined to tests/fixtures/legacy/) and by the unit tests in
    tests/unit/test_rules_engine.py. Untouched in Phase A.

  * New 0.2.0 path. `generate_actions(case, today)` returns the new
    `ActionPlan` of `Action` entries. Used by the Phase A stub fixture
    integration test in tests/test_engine_dismissed.py. The new path adds
    an FK target_role_id (replacing free-form target_role), a verdict gate,
    and render-time validators.

The new `Action` keeps an optional legacy `target_role: str` field for
backward compatibility with any 0.1.0-produced rows that may exist in the
database. The renderer prefers `target_role_id` when present and falls back
to the legacy field. Legacy field is marked deprecated; remove in 0.3.0.

§3.1 (deadlines computed deterministically) and §3.3 (target is a role
designation, never a person name) hold for both paths.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel


# ---- Shared severity / rule trace (used by both paths) ----------------------


class Severity(str, Enum):
    ACTIVE = "active"
    DEFENSIVE = "defensive"
    INFORMATIONAL = "informational"


class RuleTrace(BaseModel):
    rule_id: str
    rule_version: str
    statute: str
    triggered_by: dict[str, Any]
    computation: str


# ---- Legacy 0.1.0 types (untouched) -----------------------------------------


class ActionItem(BaseModel):
    """Legacy action shape, used by the 0.1.0 engine path. Will be deprecated
    when the v4 directive extractor lands and the 0.1.0 path retires.
    """

    id: UUID
    description: str
    target_role: str
    deadline: datetime | None
    severity: Severity
    rule_trace: RuleTrace


class LegacyActionPlan(BaseModel):
    """Legacy plan shape, returned by `generate_action_plan(...)`.

    Was named `ActionPlan` in 0.1.0; renamed in Phase A to free the canonical
    name for the new shape. Database rows persisted under the old name remain
    structurally compatible with this class.
    """

    id: UUID
    case_id: UUID
    action_items: list[ActionItem]
    rule_engine_version: str
    generated_at: datetime


# ---- New 0.2.0 types (canonical Phase A) ------------------------------------


ActionKind = Literal["ACTIVE_OBLIGATION", "DEFENSIVE_MONITOR", "HUMAN_REVIEW"]

# An FK into ParsedJudgment.respondents[*].respondent_no, OR the sentinel
# string "PRIMARY_STATE_RESPONDENT" which the renderer resolves to the
# lowest-numbered respondent whose organization is a Karnataka state body.
TargetRoleId = Union[int, Literal["PRIMARY_STATE_RESPONDENT"]]


class Action(BaseModel):
    """Phase A canonical action.

    target_role_id is the FK or sentinel; the legacy free-form `target_role`
    is preserved as an optional field for back-compat with 0.1.0-persisted
    rows but the 0.2.0 engine never writes it. Render-time validators
    require target_role_id to resolve to a respondent or a state respondent.

    source_directive_id is None for verdict-driven actions (SLP monitor,
    review-window monitor, human-review flags) and is required for
    ACTIVE_OBLIGATION actions per the validators.
    """

    kind: ActionKind
    title: str
    description: str
    deadline: Optional[date] = None
    target_role_id: TargetRoleId
    rule_id: str
    rule_version: str
    statute_citation: str
    source_directive_id: Optional[int] = None
    source_paragraph_index: Optional[int] = None
    target_role: Optional[str] = None  # deprecated, remove in 0.3.0


class ActionPlan(BaseModel):
    """Phase A canonical plan.

    Differs from LegacyActionPlan: case is identified by `case_number` (the
    cause-title number, e.g. "WP 13296/2022") rather than by a UUID, and the
    list field is `actions` rather than `action_items`.
    """

    case_number: str
    rule_engine_version: str
    actions: list[Action]
