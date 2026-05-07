"""Phase B3 voice tagger sweep against the real Venkateshulu PDF.

Loads the PDF, runs segmentation, runs the voice tagger, asserts that
each paragraph carries the right kinds of spans. Substring-keyed
expectations live in expected_voice_spans.json; this test resolves
substrings to char offsets at runtime so that re-segmentation
whitespace shifts do not invalidate the fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.schemas.parsed_judgment import GroundedParagraph

FIXTURE_DIR = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022")
PDF = FIXTURE_DIR / "original.pdf"
EXPECTED = FIXTURE_DIR / "expected_voice_spans.json"


@pytest.fixture(scope="module")
def by_idx() -> dict[int, GroundedParagraph]:
    paragraphs = annotate_paragraphs(segment_judgment(PDF))
    return {p.paragraph_index: p for p in paragraphs}


@pytest.fixture(scope="module")
def expected() -> dict[str, list[dict[str, Any]]]:
    data = json.loads(EXPECTED.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def test_p11_has_one_supreme_court_quote_span(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    p = by_idx[11]
    sc_spans = [s for s in p.voice_spans if s.voice == "SUPREME_COURT_QUOTE"]
    assert len(sc_spans) == 1
    quoted = p.text[sc_spans[0].char_start : sc_spans[0].char_end]
    assert "We make it clear" in quoted
    assert "by any body or authority" in quoted


def test_p13_has_one_other_court_quote_span(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    p = by_idx[13]
    spans = [s for s in p.voice_spans if s.voice == "OTHER_COURT_QUOTE"]
    assert len(spans) == 1
    quoted = p.text[spans[0].char_start : spans[0].char_end]
    assert "In substance, the prayer" in quoted
    assert "Petition is therefore rejected" in quoted


def test_p17_has_statute_paraphrase_span(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    p = by_idx[17]
    spans = [s for s in p.voice_spans if s.voice == "STATUTE_QUOTE"]
    assert len(spans) >= 1
    text = p.text[spans[0].char_start : spans[0].char_end]
    assert text.startswith("Section 4A(4)")


def test_p18_has_three_statute_paraphrase_spans(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    """P18 paraphrases Section 8A(3), 8A(6), and 8A(9). Each is its own span.

    The brief's outline only named the first two; verifying against the
    real PDF surfaces the third (the lapse-and-rejected exclusion clause)
    which the deterministic regex correctly catches.
    """
    p = by_idx[18]
    spans = [s for s in p.voice_spans if s.voice == "STATUTE_QUOTE"]
    assert len(spans) == 3
    starts = [p.text[s.char_start : s.char_start + 14] for s in spans]
    assert any("Section 8A(3)" in s for s in starts)
    assert any("Section 8A(6)" in s for s in starts)
    assert any("Section 8A(9)" in s for s in starts)


def test_p20_has_supreme_court_quote_span(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    """P20's quote is the Common Cause case quote with embedded straight
    quotes around 'first renewal'. The tagger must absorb the inner pair
    rather than terminating the outer span at the first inner quote."""
    p = by_idx[20]
    spans = [s for s in p.voice_spans if s.voice == "SUPREME_COURT_QUOTE"]
    assert len(spans) == 1
    quoted = p.text[spans[0].char_start : spans[0].char_end]
    assert "Based on the considerations" in quoted
    assert "amended MMDR Act" in quoted
    assert "first renewal" in quoted


def test_p21_has_revisional_authority_quote_span(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    p = by_idx[21]
    spans = [s for s in p.voice_spans if s.voice == "REVISIONAL_AUTHORITY_QUOTE"]
    assert len(spans) == 1
    quoted = p.text[spans[0].char_start : spans[0].char_end]
    assert "Admittedly, Revisionist" in quoted
    assert "since 18.04.2013" in quoted


def test_p24_has_no_voice_spans(by_idx: dict[int, GroundedParagraph]) -> None:
    p = by_idx[24]
    assert p.voice_spans == []


def test_p9_party_contention_tagged(by_idx: dict[int, GroundedParagraph]) -> None:
    p = by_idx[9]
    spans = [s for s in p.voice_spans if s.voice == "PARTY_CONTENTION"]
    assert len(spans) == 1


def test_no_paragraph_has_overlapping_spans(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    for p in by_idx.values():
        sorted_spans = sorted(p.voice_spans, key=lambda s: s.char_start)
        for a, b in zip(sorted_spans, sorted_spans[1:]):
            assert a.char_end <= b.char_start, (
                f"overlap in paragraph {p.paragraph_index}: {a} and {b}"
            )


def test_phantom_directive_paragraph_21_is_non_court(
    by_idx: dict[int, GroundedParagraph],
) -> None:
    """The architectural-fix demonstration. Paragraph 21 (the revisional
    authority quote) is structurally non-COURT, so any directive whose
    char span lies inside it would fail the voice_in_span(s, e) == "COURT"
    grounding check on OperativeDirective. This is the structural defense
    against the original phantom-cards bug."""
    p = by_idx[21]
    spans = sorted(p.voice_spans, key=lambda s: s.char_end - s.char_start, reverse=True)
    longest = spans[0]
    mid = (longest.char_start + longest.char_end) // 2
    assert p.voice_in_span(mid, mid + 5) == "REVISIONAL_AUTHORITY_QUOTE"


def test_expected_fixture_substrings_resolve(
    by_idx: dict[int, GroundedParagraph],
    expected: dict[str, list[dict[str, Any]]],
) -> None:
    """Every entry in expected_voice_spans.json must resolve to a real
    span in the corresponding paragraph: the substring opens an actual
    span of the named voice, and the same span ends with the recorded
    closing substring."""
    for idx_str, entries in expected.items():
        idx = int(idx_str)
        p = by_idx[idx]
        for entry in entries:
            voice = entry["voice"]
            starts_with = entry["starts_with"]
            ends_with = entry["ends_with"]
            matches = [
                s
                for s in p.voice_spans
                if s.voice == voice
                and p.text[s.char_start : s.char_end].startswith(starts_with)
                and p.text[s.char_start : s.char_end].endswith(ends_with)
            ]
            assert len(matches) == 1, (
                f"paragraph {idx} ({voice}): expected exactly one span "
                f"starting with {starts_with!r} and ending with {ends_with!r}, "
                f"got {len(matches)} matches; voice_spans={p.voice_spans}"
            )
