"""Phase B5 positive-case full-pipeline integration test.

Closes the architectural-fix demonstration on the positive half of the
problem: a "disposed with directions" judgment with three real directives
addressed to three respondents with three different time-clause units.
The full Phase B pipeline (segmentation -> voice -> section -> directives)
plus the Phase A 0.2.0 / 0.3.0 engine produces a three-card ACTIVE_OBLIGATION
plan with deadlines that match the brief's hand-computed values, and
`validate_action_plan` returns zero errors.

The fixture is synthetic but realistic: real cause-title format, real
respondents, real directive language. The PDF is hand-rolled (no reportlab
in the dependency set per §5.3) and committed to the fixture directory.
The integration test reads the PDF, not the source text.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kartavya.extraction.directives import extract_directives
from kartavya.extraction.section import classify_paragraphs
from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.cause_title import parse_cause_title
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.rules_engine.engine import generate_actions
from kartavya.rules_engine.validators import validate_action_plan
from kartavya.schemas.parsed_judgment import GroundedParagraph, ParsedJudgment

FIXTURE_DIR = Path("tests/fixtures/synthetic_disposed_with_directions")
PDF = FIXTURE_DIR / "judgment.pdf"


def _section_stub() -> MagicMock:
    """All paragraphs in this short judgment classify deterministically;
    the LLM stub is wired in for safety but is not expected to be called.
    Returns REASONING if it is called (a safe default for any UNCERTAIN
    intermediate paragraph)."""
    client = MagicMock()
    client.generate_json.return_value = {"section_class": "REASONING"}
    return client


def _directive_stub_for_p6(
    p6: GroundedParagraph,
) -> MagicMock:
    """Resolve the three directive offsets in P6 at runtime so the test does
    not bake in fragile char positions."""
    third = p6.text.index("The third respondent is directed")
    third_end = (
        p6.text.index("from the date of this order.", third)
        + len("from the date of this order.")
    )
    second = p6.text.index("The second respondent is directed")
    second_end = (
        p6.text.index("from the date of this order.", second)
        + len("from the date of this order.")
    )
    first = p6.text.index("The first respondent is directed")
    first_end = (
        p6.text.index("from the date of this order.", first)
        + len("from the date of this order.")
    )

    client = MagicMock()
    client.generate_json.return_value = {
        "directives": [
            {
                "char_start": third,
                "char_end": third_end,
                "actor_text": "the third respondent",
                "verb_token": "DIRECT",
                "time_clause_text": "within four weeks",
            },
            {
                "char_start": second,
                "char_end": second_end,
                "actor_text": "the second respondent",
                "verb_token": "DIRECT",
                "time_clause_text": "within sixty days",
            },
            {
                "char_start": first,
                "char_end": first_end,
                "actor_text": "the first respondent",
                "verb_token": "DIRECT",
                "time_clause_text": "within ninety days",
            },
        ]
    }
    return client


@pytest.fixture
def case_no_directives() -> ParsedJudgment:
    md = parse_cause_title(PDF)
    paragraphs = annotate_paragraphs(segment_judgment(PDF))
    classified = classify_paragraphs(paragraphs, llm_client=_section_stub())
    return ParsedJudgment(
        case_number=md.case_number,
        court=md.court,
        judgment_date=md.judgment_date,
        petitioner_name=md.petitioner_name,
        respondents=md.respondents,
        paragraphs=[p for p, _ in classified],
        verdict_class="DISPOSED_WITH_DIRECTIONS",
        directives=[],
    )


def test_positive_case_metadata_parsed_correctly() -> None:
    md = parse_cause_title(PDF)
    expected = json.loads(
        (FIXTURE_DIR / "expected_metadata.json").read_text(encoding="utf-8")
    )
    assert md.case_number == expected["case_number"]
    assert md.judgment_date == date.fromisoformat(expected["judgment_date"])
    assert md.petitioner_name == expected["petitioner_name"]
    assert md.court == expected["court"]
    assert len(md.respondents) == 3


def test_positive_case_paragraph_6_classified_operative(
    case_no_directives: ParsedJudgment,
) -> None:
    p6 = next(
        p for p in case_no_directives.paragraphs if p.paragraph_index == 6
    )
    assert p6.section_class == "OPERATIVE"


def test_positive_case_yields_three_active_obligations(
    case_no_directives: ParsedJudgment,
) -> None:
    p6 = next(
        p for p in case_no_directives.paragraphs if p.paragraph_index == 6
    )
    directive_client = _directive_stub_for_p6(p6)
    directives = extract_directives(
        case_no_directives, llm_client=directive_client
    )
    assert len(directives) == 3

    case = case_no_directives.model_copy(update={"directives": directives})
    plan = generate_actions(case, today=date(2026, 3, 15))

    errors = validate_action_plan(plan, case)
    assert errors == [], f"validation errors: {errors}"

    assert len(plan.actions) == 3
    assert all(a.kind == "ACTIVE_OBLIGATION" for a in plan.actions)

    by_target = {a.target_role_id: a for a in plan.actions}
    # 4 weeks from 2026-03-15 -> 2026-04-12 (28 days).
    assert by_target[3].deadline == date(2026, 4, 12)
    # 60 days from 2026-03-15 -> 2026-05-14.
    assert by_target[2].deadline == date(2026, 5, 14)
    # 90 days from 2026-03-15 -> 2026-06-13.
    assert by_target[1].deadline == date(2026, 6, 13)

    by_target_rule = {a.target_role_id: a.rule_id for a in plan.actions}
    assert by_target_rule[3] == "directive_relative_deadline:within_n_weeks"
    assert by_target_rule[2] == "directive_relative_deadline:within_n_days"
    assert by_target_rule[1] == "directive_relative_deadline:within_n_days"
    for action in plan.actions:
        assert action.source_paragraph_index == 6
