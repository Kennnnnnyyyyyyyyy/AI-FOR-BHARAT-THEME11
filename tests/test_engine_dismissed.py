"""Phase A integration test for the verdict-gated engine path.

Loads the canonical Venkateshulu stub (a pure dismissal with no directives,
real respondents) and asserts the engine produces exactly one action: the
SLP defensive monitor. Render-time validators must accept the plan with
no errors. The PRIMARY_STATE_RESPONDENT sentinel must resolve to the
lowest-numbered Karnataka respondent (R3).
"""

from __future__ import annotations

from datetime import date

from kartavya.rules_engine.engine import generate_actions
from kartavya.rules_engine.validators import validate_action_plan
from tests.fixtures.venkateshulu_stub import EXPECTED_PLAN, VENKATESHULU_STUB


def test_pure_dismissal_yields_only_slp_monitor() -> None:
    plan = generate_actions(VENKATESHULU_STUB, today=date(2026, 5, 7))
    assert plan == EXPECTED_PLAN


def test_pure_dismissal_plan_passes_validators() -> None:
    plan = generate_actions(VENKATESHULU_STUB, today=date(2026, 5, 7))
    assert validate_action_plan(plan, VENKATESHULU_STUB) == []


def test_primary_state_respondent_resolves_to_respondent_3() -> None:
    primary = VENKATESHULU_STUB.primary_state_respondent()
    assert primary is not None
    assert primary.respondent_no == 3
    assert primary.organization == "Government of Karnataka"
