"""Phase B4 directive parser sweep against the real Venkateshulu PDF.

Runs the full Phase B pipeline (segmentation -> voice -> section) and then
asks the directive parser to produce directives. Venkateshulu is a pure
dismissal: no OPERATIVE paragraph contains directive verbs, so the parser
returns []. The architectural-fix demonstration in its final form: P21
(the revisional-authority quote that was the source of the original
phantom-cards bug) is REASONING-class and never reaches the directive
parser at all.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kartavya.extraction.directives import extract_directives
from kartavya.extraction.section import classify_paragraphs
from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.cause_title import parse_cause_title
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.schemas.parsed_judgment import ParsedJudgment

PDF = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf")


def _section_stub_llm() -> MagicMock:
    """For B2: P21 needs LLM fallback. The deterministic classifier returns
    UNCERTAIN for P21; the stub commits to REASONING."""
    client = MagicMock()
    client.generate_json.return_value = {"section_class": "REASONING"}
    return client


def _directive_stub_llm() -> MagicMock:
    """For B4: paragraph 24 has no directives. The LLM returns empty list."""
    client = MagicMock()
    client.generate_json.return_value = {"directives": []}
    return client


@pytest.fixture
def case() -> ParsedJudgment:
    md = parse_cause_title(PDF)
    paragraphs = annotate_paragraphs(segment_judgment(PDF))
    classified = classify_paragraphs(paragraphs, llm_client=_section_stub_llm())
    return ParsedJudgment(
        case_number=md.case_number,
        court=md.court,
        judgment_date=md.judgment_date,
        petitioner_name=md.petitioner_name,
        respondents=md.respondents,
        paragraphs=[p for p, _ in classified],
        verdict_class="DISMISSED",
        directives=[],
    )


def test_real_pdf_dismissal_yields_no_directives(case: ParsedJudgment) -> None:
    client = _directive_stub_llm()
    directives = extract_directives(case, llm_client=client)
    assert directives == []


def test_only_paragraph_24_queried_for_directives(case: ParsedJudgment) -> None:
    client = _directive_stub_llm()
    extract_directives(case, llm_client=client)
    assert client.generate_json.call_count == 1
    call_args = client.generate_json.call_args
    prompt = call_args.kwargs.get("prompt", "")
    assert "(index 24)" in prompt


def test_p21_revisional_quote_not_queried(case: ParsedJudgment) -> None:
    """The original phantom-cards bug extracted directives from paragraph 21.
    After Phase B, paragraph 21 is REASONING-class (B2's LLM fallback
    commits it there) and is never even shown to the directive parser.
    Triple defense in depth (section, voice, substring) plus the verdict
    gate at the engine make the bug structurally unreachable; this test
    asserts the section guard."""
    client = _directive_stub_llm()
    extract_directives(case, llm_client=client)
    for call in client.generate_json.call_args_list:
        prompt = call.kwargs.get("prompt", "")
        assert "(index 21)" not in prompt
