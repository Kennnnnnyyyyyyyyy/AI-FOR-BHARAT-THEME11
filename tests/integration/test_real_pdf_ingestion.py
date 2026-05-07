"""Phase B1 + B6 integration test.

Combines the cause-title parser and the segmenter to assemble a
`ParsedJudgment` from the real Venkateshulu PDF, and verifies that
paragraph 24 of the real PDF text-equals paragraph 24 of the Phase A
hand-typed stub. That equality is the bridge from synthetic to real
ground truth.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from kartavya.ingestion.cause_title import parse_cause_title
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.schemas.parsed_judgment import ParsedJudgment

FIXTURE = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf")


def test_real_pdf_assembles_into_parsed_judgment() -> None:
    md = parse_cause_title(FIXTURE)
    paragraphs = segment_judgment(FIXTURE)
    case = ParsedJudgment(
        case_number=md.case_number,
        court=md.court,
        judgment_date=md.judgment_date,
        petitioner_name=md.petitioner_name,
        respondents=md.respondents,
        paragraphs=paragraphs,
        verdict_class="DISMISSED",
        directives=[],
    )
    assert case.case_number == "WP 13296/2022"
    assert case.judgment_date == date(2026, 4, 17)
    assert len(case.respondents) == 6
    assert len(case.paragraphs) == 24
    primary = case.primary_state_respondent()
    assert primary is not None
    assert primary.respondent_no == 3


def test_real_pdf_paragraph_24_matches_phase_a_stub_text() -> None:
    """Bridge test. The real-PDF paragraph 24 text must equal the hand-typed
    Phase A stub paragraph 24 text exactly. If this passes, the synthetic
    ground truth has been validated against reality."""
    from tests.fixtures.venkateshulu_stub import PARA_24_TEXT

    paragraphs = segment_judgment(FIXTURE)
    p24 = next(p for p in paragraphs if p.paragraph_index == 24)
    assert p24.text.strip() == PARA_24_TEXT
