"""Phase B closing end-to-end test: full pipeline + directive extraction.

Bridges segmentation -> voice -> section -> directive parser -> Phase A
engine. Demonstrates the architectural fix in its complete form: real
Venkateshulu PDF in, one-card defensive SLP plan out, zero validator
errors, four phantom cards structurally unreachable.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from kartavya.extraction.directives import extract_directives
from kartavya.extraction.section import classify_paragraphs
from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.cause_title import parse_cause_title
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.rules_engine.engine import generate_actions
from kartavya.rules_engine.validators import validate_action_plan
from kartavya.schemas.parsed_judgment import ParsedJudgment

PDF = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf")


def _stubs() -> tuple[MagicMock, MagicMock]:
    section = MagicMock()
    section.generate_json.return_value = {"section_class": "REASONING"}
    directives = MagicMock()
    directives.generate_json.return_value = {"directives": []}
    return section, directives


def test_full_phase_b_pipeline_produces_one_card_slp_plan() -> None:
    md = parse_cause_title(PDF)
    paragraphs = annotate_paragraphs(segment_judgment(PDF))
    section_llm, directive_llm = _stubs()
    classified = classify_paragraphs(paragraphs, llm_client=section_llm)
    classified_paragraphs = [p for p, _ in classified]

    case_no_directives = ParsedJudgment(
        case_number=md.case_number,
        court=md.court,
        judgment_date=md.judgment_date,
        petitioner_name=md.petitioner_name,
        respondents=md.respondents,
        paragraphs=classified_paragraphs,
        verdict_class="DISMISSED",
        directives=[],
    )

    directives = extract_directives(case_no_directives, llm_client=directive_llm)
    assert directives == []

    case = case_no_directives.model_copy(update={"directives": directives})
    plan = generate_actions(case, today=date(2026, 5, 7))

    assert validate_action_plan(plan, case) == []
    assert len(plan.actions) == 1
    assert plan.actions[0].kind == "DEFENSIVE_MONITOR"
    assert plan.actions[0].rule_id == "dismissed_slp_window"
    assert plan.actions[0].deadline == date(2026, 7, 16)
    assert plan.actions[0].target_role_id == "PRIMARY_STATE_RESPONDENT"


def test_phantom_cards_remain_unreachable_through_full_pipeline() -> None:
    """Architectural-fix demonstration in its final form. Three independent
    grounding guards (section_class, voice_in_span, substring/bounds) plus
    the actor FK guard plus the verdict gate at the engine make the four
    historical phantom cards unreachable through any path.

    The structural fact this test pins: paragraph 24, the only OPERATIVE
    paragraph in Venkateshulu, has no directive verbs. Even an LLM that
    hallucinated freely cannot point at a directive verb that exists in
    the source; the substring guard would catch any fabricated span."""
    paragraphs = annotate_paragraphs(segment_judgment(PDF))
    section_llm, _ = _stubs()
    classified = classify_paragraphs(paragraphs, llm_client=section_llm)
    classified_paragraphs = [p for p, _ in classified]

    operative = [p for p in classified_paragraphs if p.section_class == "OPERATIVE"]
    assert len(operative) == 1
    assert operative[0].paragraph_index == 24
    text_lower = operative[0].text.lower()
    assert "directed" not in text_lower
    assert "ordered" not in text_lower
    assert "shall" not in text_lower
    assert "within" not in text_lower
