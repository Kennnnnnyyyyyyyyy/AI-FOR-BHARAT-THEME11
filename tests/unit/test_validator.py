"""Tests for kartavya/extraction/validator.py."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from kartavya.extraction.anchors import (
    ParagraphClassificationRaw,
    anchor_token,
    build_anchor_map,
)
from kartavya.extraction.client import CallMetadata
from kartavya.extraction.validator import (
    FailureReason,
    force_low_confidence,
    validate_chunk,
)
from kartavya.schemas.extraction import ParagraphLabel
from kartavya.schemas.paragraph import Paragraph


def _make_paragraph(idx: int, text: str) -> Paragraph:
    return Paragraph(
        id=UUID(f"00000000-0000-0000-0000-{idx:012d}"),
        page=1,
        bounding_box=(0, 0, 100, 100),
        text=text,
        paragraph_index=idx,
    )


def _make_metadata() -> CallMetadata:
    return CallMetadata(
        prompt_sha="a" * 64,
        model_id="llama3.1:8b-instruct-q4_K_M",
        temperature=0.0,
        extracted_at=datetime.now(timezone.utc),
    )


def test_happy_path_accepts_valid_classification() -> None:
    p = _make_paragraph(0, "The petitioner approached this Court.")
    anchor_map = build_anchor_map([p])
    raw = ParagraphClassificationRaw(
        anchor=anchor_token(p),
        label=ParagraphLabel.CONTEXTUAL,
        confidence=0.9,
        source_span="petitioner approached this Court",
    )

    accepted, failures = validate_chunk(
        [raw], anchor_map, {p.id}, _make_metadata()
    )

    assert len(accepted) == 1
    assert not failures
    assert accepted[0].paragraph_id == p.id
    assert accepted[0].label == ParagraphLabel.CONTEXTUAL
    assert accepted[0].provenance.prompt_sha == "a" * 64


def test_unknown_anchor_fails_validation() -> None:
    p = _make_paragraph(0, "Real paragraph text.")
    anchor_map = build_anchor_map([p])
    raw = ParagraphClassificationRaw(
        anchor="P999-deadbeef",
        label=ParagraphLabel.CONTEXTUAL,
        confidence=0.9,
        source_span="anything",
    )

    accepted, failures = validate_chunk([raw], anchor_map, {p.id}, _make_metadata())

    assert not accepted
    assert len(failures) == 1
    assert failures[0].reason == FailureReason.ANCHOR_NOT_FOUND
    assert failures[0].paragraph is None


def test_overlap_paragraph_silently_discarded() -> None:
    centre_p = _make_paragraph(0, "Centre paragraph text.")
    overlap_p = _make_paragraph(1, "Overlap paragraph text.")
    anchor_map = build_anchor_map([centre_p, overlap_p])
    raw_overlap = ParagraphClassificationRaw(
        anchor=anchor_token(overlap_p),
        label=ParagraphLabel.CONTEXTUAL,
        confidence=0.9,
        source_span="overlap paragraph",
    )

    accepted, failures = validate_chunk(
        [raw_overlap], anchor_map, {centre_p.id}, _make_metadata()
    )

    assert not accepted
    assert not failures, "overlap leaks should be silent, not failures"


def test_span_mismatch_caught() -> None:
    p1 = _make_paragraph(0, "Petitioner challenges acquisition.")
    p2 = _make_paragraph(1, "Court analyses statutory scheme.")
    anchor_map = build_anchor_map([p1, p2])
    # Model returns p1's anchor but copies span from p2
    raw = ParagraphClassificationRaw(
        anchor=anchor_token(p1),
        label=ParagraphLabel.CONTEXTUAL,
        confidence=0.9,
        source_span="statutory scheme",
    )

    accepted, failures = validate_chunk(
        [raw], anchor_map, {p1.id}, _make_metadata()
    )

    assert not accepted
    assert len(failures) == 1
    assert failures[0].reason == FailureReason.SPAN_MISMATCH
    assert failures[0].paragraph is p1


def test_span_substring_check_tolerant_to_whitespace() -> None:
    p = _make_paragraph(0, "The   petitioner\nfiled  a writ.")
    anchor_map = build_anchor_map([p])
    raw = ParagraphClassificationRaw(
        anchor=anchor_token(p),
        label=ParagraphLabel.CONTEXTUAL,
        confidence=0.9,
        source_span="petitioner filed a writ",
    )

    accepted, _ = validate_chunk([raw], anchor_map, {p.id}, _make_metadata())
    assert len(accepted) == 1


def test_force_low_confidence_returns_zero_confidence() -> None:
    p = _make_paragraph(0, "Some text.")
    raw = ParagraphClassificationRaw(
        anchor=anchor_token(p),
        label=ParagraphLabel.OPERATIVE,
        confidence=0.4,
        source_span="some text",
    )
    forced = force_low_confidence(p, raw, _make_metadata())
    assert forced.confidence == 0.0
    assert forced.label == ParagraphLabel.OPERATIVE  # preserved for reviewer
    assert forced.provenance.confidence == 0.0


def test_force_low_confidence_without_raw_defaults_to_contextual() -> None:
    p = _make_paragraph(0, "Some text.")
    forced = force_low_confidence(p, None, _make_metadata())
    assert forced.label == ParagraphLabel.CONTEXTUAL
    assert forced.confidence == 0.0
