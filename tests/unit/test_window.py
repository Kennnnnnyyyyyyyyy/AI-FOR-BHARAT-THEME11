"""Tests for kartavya/extraction/window.py."""

from __future__ import annotations

from uuid import UUID

import pytest

from kartavya.extraction.window import iter_chunks
from kartavya.schemas.paragraph import Paragraph


def _make_paragraph(idx: int) -> Paragraph:
    return Paragraph(
        id=UUID(f"00000000-0000-0000-0000-{idx:012d}"),
        page=1,
        bounding_box=(0, 0, 100, 100),
        text=f"text {idx}",
        paragraph_index=idx,
    )


def test_empty_input_yields_nothing() -> None:
    assert list(iter_chunks([])) == []


def test_single_paragraph() -> None:
    p = _make_paragraph(0)
    chunks = list(iter_chunks([p]))
    assert len(chunks) == 1
    chunk, centre = chunks[0]
    assert chunk == [p]
    assert centre == {p.id}


def test_centres_tile_exactly_with_24_paragraphs() -> None:
    paragraphs = [_make_paragraph(i) for i in range(24)]
    chunks = list(iter_chunks(paragraphs, center=5, overlap=1))
    seen_centres: set[UUID] = set()
    for _, centre in chunks:
        assert centre.isdisjoint(seen_centres), "centres must not overlap"
        seen_centres |= centre
    assert seen_centres == {p.id for p in paragraphs}


def test_overlap_provides_context_paragraphs() -> None:
    paragraphs = [_make_paragraph(i) for i in range(24)]
    chunks = list(iter_chunks(paragraphs, center=5, overlap=1))

    # Middle chunk: 5 centre + 1 left overlap + 1 right overlap = 7
    middle = chunks[2]
    chunk, centre = middle
    assert len(chunk) == 7
    assert len(centre) == 5

    # First chunk: only right overlap
    first_chunk, first_centre = chunks[0]
    assert len(first_chunk) == 6  # 5 centre + 1 right
    assert paragraphs[0].id in first_centre

    # Last chunk: only left overlap
    last_chunk, last_centre = chunks[-1]
    assert paragraphs[-1].id in last_centre


def test_n_equal_to_center_yields_one_chunk() -> None:
    paragraphs = [_make_paragraph(i) for i in range(5)]
    chunks = list(iter_chunks(paragraphs, center=5, overlap=1))
    assert len(chunks) == 1
    chunk, centre = chunks[0]
    assert chunk == paragraphs
    assert centre == {p.id for p in paragraphs}


def test_n_less_than_center() -> None:
    paragraphs = [_make_paragraph(i) for i in range(3)]
    chunks = list(iter_chunks(paragraphs, center=5, overlap=1))
    assert len(chunks) == 1
    chunk, centre = chunks[0]
    assert chunk == paragraphs
    assert centre == {p.id for p in paragraphs}


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        list(iter_chunks([_make_paragraph(0)], center=0))
    with pytest.raises(ValueError):
        list(iter_chunks([_make_paragraph(0)], overlap=-1))


def test_zero_overlap_still_works() -> None:
    paragraphs = [_make_paragraph(i) for i in range(7)]
    chunks = list(iter_chunks(paragraphs, center=3, overlap=0))
    assert [len(c) for c, _ in chunks] == [3, 3, 1]
    for chunk, centre in chunks:
        assert {p.id for p in chunk} == centre
