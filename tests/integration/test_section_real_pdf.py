"""Phase B2 section classifier sweep against the real Venkateshulu PDF.

Loads the PDF, runs segmentation + voice tagging + section classification,
asserts that every paragraph's section_class and stage match
expected_sections.json. The LLM client is stubbed to a deterministic
response for hermetic test runs; a separate test exercises LLM unavailability
and verifies graceful degradation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from kartavya.audit import recorder as audit
from kartavya.extraction.section import classify_paragraphs
from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.schemas.parsed_judgment import GroundedParagraph

FIXTURE_DIR = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022")
PDF = FIXTURE_DIR / "original.pdf"
EXPECTED = FIXTURE_DIR / "expected_sections.json"


def _stubbed_llm_client() -> MagicMock:
    """Fake LLM client that classifies P21 (and any other UNCERTAIN
    paragraph the deterministic stage emits) as REASONING."""
    client = MagicMock()
    client.generate_json.return_value = {"section_class": "REASONING"}
    client.model_id = "stub-section-llm"
    return client


def _expected_sections() -> dict[str, dict[str, str]]:
    data: dict[str, Any] = json.loads(EXPECTED.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@pytest.fixture
def paragraphs() -> list[GroundedParagraph]:
    return annotate_paragraphs(segment_judgment(PDF))


def test_every_paragraph_classified(paragraphs: list[GroundedParagraph]) -> None:
    classified = classify_paragraphs(paragraphs, llm_client=_stubbed_llm_client())
    assert len(classified) == 24


def test_sections_match_expected(paragraphs: list[GroundedParagraph]) -> None:
    classified = classify_paragraphs(paragraphs, llm_client=_stubbed_llm_client())
    expected = _expected_sections()
    by_idx = {p.paragraph_index: (p.section_class, v.stage) for p, v in classified}
    for k, exp in expected.items():
        idx = int(k)
        actual_class, actual_stage = by_idx[idx]
        assert actual_class == exp["section_class"], (
            f"P{idx}: expected {exp['section_class']}, got {actual_class}"
        )
        assert actual_stage == exp["expected_stage"], (
            f"P{idx}: expected stage {exp['expected_stage']}, got {actual_stage}"
        )


def test_only_p21_routes_to_llm(paragraphs: list[GroundedParagraph]) -> None:
    client = _stubbed_llm_client()
    classify_paragraphs(paragraphs, llm_client=client)
    assert client.generate_json.call_count == 1


def test_p24_is_operative(paragraphs: list[GroundedParagraph]) -> None:
    classified = classify_paragraphs(paragraphs, llm_client=_stubbed_llm_client())
    p24, v24 = next((p, v) for p, v in classified if p.paragraph_index == 24)
    assert p24.section_class == "OPERATIVE"
    assert v24.confidence >= 0.92
    assert v24.stage == "DETERMINISTIC"


def test_p21_uncertain_in_deterministic_stage_then_resolved_to_reasoning(
    paragraphs: list[GroundedParagraph],
) -> None:
    classified = classify_paragraphs(paragraphs, llm_client=_stubbed_llm_client())
    p21, v21 = next((p, v) for p, v in classified if p.paragraph_index == 21)
    assert v21.stage == "LLM_FALLBACK"
    assert "deterministic=UNCERTAIN" in v21.reason
    assert p21.section_class == "REASONING"


def test_no_paragraph_remains_uncertain_after_llm_fallback(
    paragraphs: list[GroundedParagraph],
) -> None:
    classified = classify_paragraphs(paragraphs, llm_client=_stubbed_llm_client())
    for p, v in classified:
        assert v.section_class != "UNCERTAIN", (
            f"P{p.paragraph_index} remained UNCERTAIN: {v.reason}"
        )


def test_llm_unavailable_yields_low_confidence_not_failure(
    paragraphs: list[GroundedParagraph],
) -> None:
    """If the LLM client raises, the classifier returns the deterministic
    UNCERTAIN result with stage DETERMINISTIC_LOW_CONFIDENCE rather than
    propagating the exception. Downstream consumers (B4) treat UNCERTAIN
    as 'do not extract directives; route to human review.'"""
    failing_client = MagicMock()
    failing_client.generate_json.side_effect = RuntimeError("ollama down")
    classified = classify_paragraphs(paragraphs, llm_client=failing_client)
    _, v21 = next((p, v) for p, v in classified if p.paragraph_index == 21)
    assert v21.stage == "DETERMINISTIC_LOW_CONFIDENCE"
    assert v21.section_class == "UNCERTAIN"


def test_audit_log_records_one_event_per_paragraph(
    paragraphs: list[GroundedParagraph],
) -> None:
    """When case_number is provided, every classification (deterministic or
    LLM fallback) emits one audit event. The LLM-fallback event additionally
    carries prompt_sha and model_id."""
    audit.clear_events()
    classify_paragraphs(
        paragraphs,
        llm_client=_stubbed_llm_client(),
        case_number="WP 13296/2022",
    )
    events = audit.get_events()
    assert len(events) == 24
    llm_events = [e for e in events if e.prompt_sha is not None]
    assert len(llm_events) == 1
    assert llm_events[0].model_id == "stub-section-llm"
    assert llm_events[0].payload["paragraph_index"] == 21
    assert llm_events[0].payload["section_class"] == "REASONING"
    assert llm_events[0].payload["deterministic_class"] == "UNCERTAIN"
    audit.clear_events()
