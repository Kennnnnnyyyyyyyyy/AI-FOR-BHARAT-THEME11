"""Tests for kartavya/extraction/anchors.py."""

from __future__ import annotations

import pytest
from uuid import UUID

from kartavya.errors import AnchorMismatch
from kartavya.extraction.anchors import (
    anchor_token,
    build_anchor_map,
    normalize,
    parse_anchor,
)
from kartavya.schemas.paragraph import Paragraph


def _make_paragraph(idx: int, text: str) -> Paragraph:
    return Paragraph(
        id=UUID(f"00000000-0000-0000-0000-{idx:012d}"),
        page=1,
        bounding_box=(0, 0, 100, 100),
        text=text,
        paragraph_index=idx,
    )


def test_normalize_collapses_whitespace_and_lowercases() -> None:
    assert normalize("  Hello\nWorld\t") == "hello world"


def test_anchor_token_format() -> None:
    p = _make_paragraph(6, "The petitioner approached this Court...")
    token = anchor_token(p)
    assert token.startswith("P006-")
    assert len(token) == 4 + 1 + 8  # "P006" + "-" + 8 hex


def test_anchor_token_deterministic() -> None:
    p = _make_paragraph(6, "Some text")
    assert anchor_token(p) == anchor_token(p)


def test_anchor_token_stable_under_whitespace_noise() -> None:
    p1 = _make_paragraph(6, "Hello world")
    p2 = _make_paragraph(6, "  Hello\nworld\t")
    assert anchor_token(p1) == anchor_token(p2)


def test_anchor_token_changes_with_index() -> None:
    p1 = _make_paragraph(6, "Same text")
    p2 = _make_paragraph(7, "Same text")
    assert anchor_token(p1) != anchor_token(p2)


def test_build_anchor_map_round_trip() -> None:
    paragraphs = [_make_paragraph(i, f"text {i}") for i in range(3)]
    anchor_map = build_anchor_map(paragraphs)
    assert len(anchor_map) == 3
    for p in paragraphs:
        assert anchor_map[anchor_token(p)] is p


def test_parse_anchor_valid() -> None:
    idx, sha = parse_anchor("P006-ab12cd34")
    assert idx == 6
    assert sha == "ab12cd34"


def test_parse_anchor_malformed_raises() -> None:
    with pytest.raises(AnchorMismatch):
        parse_anchor("not-an-anchor")
    with pytest.raises(AnchorMismatch):
        parse_anchor("P6-ab12cd34")  # idx not zero-padded
    with pytest.raises(AnchorMismatch):
        parse_anchor("P006-XYZ")  # sha too short / non-hex
