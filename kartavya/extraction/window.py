"""Sliding-window chunker for APVC paragraph classification.

Each chunk holds `center` paragraphs whose labels we accept, plus up to
`overlap` paragraphs of context on each side. Boundary chunks have one-sided
overlap. Centres tile exactly — every paragraph appears in the centre of
exactly one chunk.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from kartavya.schemas.paragraph import Paragraph

CENTER_SIZE = 5
OVERLAP = 1


def iter_chunks(
    paragraphs: list[Paragraph],
    *,
    center: int = CENTER_SIZE,
    overlap: int = OVERLAP,
) -> Iterator[tuple[list[Paragraph], set[UUID]]]:
    """Yield (chunk_paragraphs, center_uuids) pairs.

    `chunk_paragraphs` is the full window (centre + overlap on either side).
    `center_uuids` is the set of paragraph UUIDs whose labels should be accepted
    from this chunk; overlap paragraphs are present for context only and their
    labels are discarded by the validator.
    """
    if center < 1:
        raise ValueError("center must be >= 1")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")

    n = len(paragraphs)
    if n == 0:
        return

    for centre_start in range(0, n, center):
        centre_end = min(centre_start + center, n)
        chunk_start = max(0, centre_start - overlap)
        chunk_end = min(n, centre_end + overlap)
        chunk = paragraphs[chunk_start:chunk_end]
        centre_uuids = {p.id for p in paragraphs[centre_start:centre_end]}
        yield chunk, centre_uuids
