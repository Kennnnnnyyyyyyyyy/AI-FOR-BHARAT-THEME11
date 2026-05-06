"""Anchor tokens for APVC paragraph classification.

Each paragraph is assigned a deterministic token of the form `P{idx:03d}-{sha8}`
where `sha8` is the first 8 hex chars of SHA-256 over the normalised paragraph
text. The model must echo this token verbatim; the validator rejects anything
that doesn't resolve in the chunk's anchor map.

The token is derived, not stored — re-running classification on the same input
paragraphs yields bit-identical anchors.
"""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from kartavya.errors import AnchorMismatch
from kartavya.schemas.extraction import ParagraphLabel
from kartavya.schemas.paragraph import Paragraph

_ANCHOR_RE = re.compile(r"^P(\d{3})-([0-9a-f]{8})$")
_WHITESPACE_RE = re.compile(r"\s+")


class ParagraphClassificationRaw(BaseModel):
    """LLM-output shape for APVC. Internal to extraction (not a cross-boundary contract).

    The validator resolves `anchor` → `Paragraph` via the anchor map and constructs
    the canonical `ParagraphClassification` with full provenance.
    """

    anchor: str
    label: ParagraphLabel
    confidence: float = Field(ge=0.0, le=1.0)
    source_span: str


class ChunkClassifications(BaseModel):
    """JSON-mode envelope returned by the paragraph classifier — a list of raw classifications."""

    classifications: list[ParagraphClassificationRaw]


def normalize(text: str) -> str:
    """Collapse whitespace and lowercase for hash stability across whitespace noise."""
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def anchor_token(paragraph: Paragraph) -> str:
    """Build the deterministic anchor token for a paragraph."""
    digest = hashlib.sha256(normalize(paragraph.text).encode("utf-8")).hexdigest()
    return f"P{paragraph.paragraph_index:03d}-{digest[:8]}"


def build_anchor_map(paragraphs: list[Paragraph]) -> dict[str, Paragraph]:
    """Build {anchor → paragraph} for the paragraphs in this case.

    Collisions on the 8-char hash prefix would mean two paragraphs share both
    `paragraph_index` *and* normalised text — which would already violate the
    `paragraph_index` uniqueness invariant. The check here is belt-and-braces.
    """
    anchor_map: dict[str, Paragraph] = {}
    for p in paragraphs:
        token = anchor_token(p)
        if token in anchor_map:
            raise AnchorMismatch(f"duplicate anchor token: {token}")
        anchor_map[token] = p
    return anchor_map


def parse_anchor(token: str) -> tuple[int, str]:
    """Return (paragraph_index, sha8) for a well-formed anchor; raise otherwise."""
    match = _ANCHOR_RE.match(token)
    if not match:
        raise AnchorMismatch(f"malformed anchor token: {token!r}")
    return int(match.group(1)), match.group(2)
