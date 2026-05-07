"""Phase B end-to-end pipeline integration test.

The closing bridge for Phase B: segmentation → cause title → voice tagger →
section classifier → assembled `ParsedJudgment` → Phase A engine. The Phase A
engine has not been touched since 0.2.0; this test proves the full B
pipeline plugs cleanly into it and produces the same one-card SLP plan that
the Phase A stub fixture produced. The architectural fix holds end-to-end.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from kartavya.extraction.section import classify_paragraphs
from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.cause_title import parse_cause_title
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.rules_engine.engine import generate_actions
from kartavya.rules_engine.validators import validate_action_plan
from kartavya.schemas.parsed_judgment import ParsedJudgment

PDF = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf")


def _stubbed_llm() -> MagicMock:
    client = MagicMock()
    client.generate_json.return_value = {"section_class": "REASONING"}
    client.model_id = "stub-section-llm"
    return client


def _build_case() -> ParsedJudgment:
    md = parse_cause_title(PDF)
    paragraphs = annotate_paragraphs(segment_judgment(PDF))
    classified = classify_paragraphs(paragraphs, llm_client=_stubbed_llm())
    classified_paragraphs = [p for p, _ in classified]
    return ParsedJudgment(
        case_number=md.case_number,
        court=md.court,
        judgment_date=md.judgment_date,
        petitioner_name=md.petitioner_name,
        respondents=md.respondents,
        paragraphs=classified_paragraphs,
        verdict_class="DISMISSED",
        directives=[],
    )


def test_full_phase_b_pipeline_produces_valid_parsed_judgment() -> None:
    case = _build_case()

    assert case.case_number == "WP 13296/2022"
    assert case.judgment_date == date(2026, 4, 17)
    assert len(case.paragraphs) == 24
    assert len(case.respondents) == 6

    section_counts: dict[str, int] = {}
    for p in case.paragraphs:
        section_counts[p.section_class] = section_counts.get(p.section_class, 0) + 1
    assert section_counts.get("OPERATIVE", 0) == 1
    assert section_counts.get("FACTS", 0) >= 8
    assert section_counts.get("REASONING", 0) >= 4
    assert section_counts.get("PRECEDENT_CITATION", 0) >= 2
    assert section_counts.get("ARGUMENTS", 0) == 2

    operative = [p for p in case.paragraphs if p.section_class == "OPERATIVE"]
    assert len(operative) == 1
    assert operative[0].paragraph_index == 24


def test_phase_a_engine_runs_against_phase_b_pipeline_output() -> None:
    """Phase A engine, untouched since 0.2.0, consumes the Phase B pipeline
    output and produces the expected one-card SLP plan."""
    case = _build_case()
    plan = generate_actions(case, today=date(2026, 5, 7))
    assert validate_action_plan(plan, case) == []
    assert len(plan.actions) == 1
    assert plan.actions[0].rule_id == "dismissed_slp_window"
    assert plan.actions[0].deadline == date(2026, 7, 16)
