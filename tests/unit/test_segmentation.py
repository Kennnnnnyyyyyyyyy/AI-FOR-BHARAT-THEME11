"""Phase B1 segmentation tests against the real Venkateshulu PDF."""

from __future__ import annotations

import re
from pathlib import Path

from kartavya.ingestion.segmentation import segment_judgment

FIXTURE = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf")
P24_FIXTURE = Path(
    "tests/fixtures/venkateshulu_real_pdf_wp13296_2022/expected_paragraph_24_text.txt"
)


def test_paragraph_count_is_24() -> None:
    paragraphs = segment_judgment(FIXTURE)
    assert len(paragraphs) == 24


def test_paragraph_indices_contiguous_1_to_24() -> None:
    paragraphs = segment_judgment(FIXTURE)
    assert [p.paragraph_index for p in paragraphs] == list(range(1, 25))


def test_paragraph_24_text_is_only_dismissal_line() -> None:
    paragraphs = segment_judgment(FIXTURE)
    p24 = next(p for p in paragraphs if p.paragraph_index == 24)
    expected = P24_FIXTURE.read_text().strip()
    assert p24.text.strip() == expected


def test_paragraph_24_does_not_contain_signature_block() -> None:
    paragraphs = segment_judgment(FIXTURE)
    p24 = next(p for p in paragraphs if p.paragraph_index == 24)
    assert "SD/-" not in p24.text
    assert "VIBHU BAKHRU" not in p24.text
    assert "POONACHA" not in p24.text
    assert "BS/Vmb/ND" not in p24.text


def test_paragraph_11_contains_supreme_court_quote() -> None:
    paragraphs = segment_judgment(FIXTURE)
    p11 = next(p for p in paragraphs if p.paragraph_index == 11)
    assert "boundaries of leases fixed by the Joint Team" in p11.text


def test_no_running_footer_in_any_paragraph() -> None:
    paragraphs = segment_judgment(FIXTURE)
    for p in paragraphs:
        assert "Indian Kanoon" not in p.text
        assert "indiankanoon.org" not in p.text


def test_no_page_number_stamps_in_any_paragraph() -> None:
    paragraphs = segment_judgment(FIXTURE)
    stamp_re = re.compile(r"^\s*-\s*\d+\s*-\s*$")
    for p in paragraphs:
        for line in p.text.splitlines():
            assert not stamp_re.match(line), (
                f"page stamp leaked into paragraph {p.paragraph_index}: {line!r}"
            )


def test_section_class_default_is_facts_placeholder() -> None:
    paragraphs = segment_judgment(FIXTURE)
    assert all(p.section_class == "FACTS" for p in paragraphs)


def test_voice_spans_default_empty() -> None:
    paragraphs = segment_judgment(FIXTURE)
    assert all(p.voice_spans == [] for p in paragraphs)
