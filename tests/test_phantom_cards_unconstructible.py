"""Phase A regression: the four historical phantom cards must fail render.

This is the architectural-fix proof. Before Phase A, the 0.1.0 pipeline
produced four "active obligation" cards on Venkateshulu (compliance
affidavit within 4 weeks, compensation disbursement within 60 days,
reference court within 6 months, plus a wrong-target SLP card) where the
target was free-form text "CEO, KIADB" and no respondent FK existed. Three
problems made them constructible:

  1. target_role was a free string, so "KIADB CEO" was accepted.
  2. The engine had no verdict gate, so DISMISSED + ACTIVE_OBLIGATION was
     accepted.
  3. There were no render-time validators, so a plan with no source
     directive could still be rendered.

Phase A fixes all three. This test replays the four phantom cards as
`Action` objects against the real respondent list and confirms every card
trips at least one validator. If any card passes, the architectural fix
has regressed.

The synthetic respondent_no=999 used here represents the historical
phantom target. In the real bug it was a free-text "CEO, KIADB" string;
under Phase A's FK contract, any respondent_no not in the case's
respondents list trips TARGET_NOT_IN_RESPONDENTS, so the regression check
is structurally equivalent.
"""

from __future__ import annotations

from datetime import date

from kartavya.rules_engine.validators import validate_action_plan
from kartavya.schemas.action_plan import Action, ActionPlan
from tests.fixtures.venkateshulu_stub import VENKATESHULU_STUB


def _historical_phantom_plan() -> ActionPlan:
    return ActionPlan(
        case_number="WP 13296/2022",
        rule_engine_version="0.2.0",
        actions=[
            Action(
                kind="ACTIVE_OBLIGATION",
                title="File compliance affidavit within 4 weeks",
                description="phantom",
                deadline=date(2026, 5, 15),
                target_role_id=999,
                rule_id="directive_relative_deadline:within_n_weeks",
                rule_version="0.2.0",
                statute_citation="Article 226",
                source_directive_id=None,
                source_paragraph_index=21,  # legacy synthetic index
            ),
            Action(
                kind="ACTIVE_OBLIGATION",
                title="Disburse compensation within 60 days",
                description="phantom",
                deadline=date(2026, 6, 16),
                target_role_id=999,
                rule_id="directive_relative_deadline:within_n_days",
                rule_version="0.2.0",
                statute_citation="Article 226",
                source_directive_id=None,
                source_paragraph_index=20,
            ),
            Action(
                kind="ACTIVE_OBLIGATION",
                title="Reference court to dispose within 6 months",
                description="phantom",
                deadline=date(2026, 10, 17),
                target_role_id=999,
                rule_id="directive_relative_deadline:within_n_months",
                rule_version="0.2.0",
                statute_citation="Article 226",
                source_directive_id=None,
                source_paragraph_index=22,
            ),
            Action(
                kind="DEFENSIVE_MONITOR",
                title="SLP window",
                description="phantom; wrong target",
                deadline=date(2026, 7, 16),
                target_role_id=999,
                rule_id="dismissed_slp_window",
                rule_version="0.2.0",
                statute_citation="Article 136",
                source_directive_id=None,
                source_paragraph_index=None,
            ),
        ],
    )


def test_all_four_phantom_cards_fail_validation() -> None:
    plan = _historical_phantom_plan()
    errors = validate_action_plan(plan, VENKATESHULU_STUB)

    error_codes = {code for code, _ in errors}
    assert "TARGET_NOT_IN_RESPONDENTS" in error_codes
    assert "OBLIGATION_WITHOUT_SOURCE" in error_codes
    assert "DISMISSED_WITH_OBLIGATION" in error_codes

    actions_with_errors = {id(a) for _, a in errors}
    for a in plan.actions:
        assert id(a) in actions_with_errors, (
            f"phantom card slipped through validators: {a.title}"
        )


def test_phantom_paragraph_indices_trip_source_paragraph_missing() -> None:
    """The three ACTIVE_OBLIGATION phantoms cite paragraphs 20, 21, 22, none of
    which exist in the stub fixture (which only has paragraph 24). Each must
    trip SOURCE_PARAGRAPH_MISSING in addition to the other validators."""
    plan = _historical_phantom_plan()
    errors = validate_action_plan(plan, VENKATESHULU_STUB)
    missing_para_errors = [(c, a) for c, a in errors if c == "SOURCE_PARAGRAPH_MISSING"]
    assert len(missing_para_errors) == 3
