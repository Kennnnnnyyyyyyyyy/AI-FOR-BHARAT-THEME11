"""Extraction outputs — paragraph classifications, verdict, operative directions, and aggregate result.

Phase B7 status: `OperativeDirection` (without the trailing 'e') is the
legacy 0.1.0 directive type. It coexisted with `OperativeDirective` (in
schemas/parsed_judgment.py) through Phase B for backwards compatibility
with the v3 prompt path. As of 0.3.0, runtime call sites all consume
`OperativeDirective`; `OperativeDirection` is retained on disk per §3.5
(prompt files reference it by name) and is scheduled for removal in
0.4.0. Importing it now emits a DeprecationWarning.
"""

import warnings
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from kartavya.schemas.provenance import ExtractionProvenance


class ParagraphLabel(str, Enum):
    """Operational taxonomy (§10.1). Three labels indexed on what the officer
    must do, not on the rhetorical content of the paragraph.

    - OPERATIVE: contains a court direction the government must act on, or
      the verdict statement that triggers limitation calculation. Sole input
      to the rules engine.
    - CONTEXTUAL: supports understanding of the case but generates no officer
      action. Subsumes the prior facts/arguments/precedent/reasoning labels.
    - PROCEDURAL: case metadata, cause-title, party listings, signature
      blocks, page headers, footnote-only paragraphs. Skipped in review.
    """

    OPERATIVE = "operative"
    CONTEXTUAL = "contextual"
    PROCEDURAL = "procedural"


class Verdict(str, Enum):
    ALLOWED = "allowed"
    DISMISSED = "dismissed"
    PARTLY_ALLOWED = "partly_allowed"
    DISPOSED_WITH_DIRECTIONS = "disposed_with_directions"
    REMANDED = "remanded"


class ParagraphClassification(BaseModel):
    paragraph_id: UUID
    label: ParagraphLabel
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: ExtractionProvenance


class VerdictClassification(BaseModel):
    case_id: UUID
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: ExtractionProvenance


class OperativeDirection(BaseModel):
    """DEPRECATED: legacy 0.1.0 directive shape.

    Use `kartavya.schemas.parsed_judgment.OperativeDirective` instead.
    Removal scheduled for 0.4.0. Retained on disk per §3.5 because the
    v3 prompt files still reference this class by name in their
    frontmatter; the v3 path is no longer dispatched at runtime but the
    files are part of the reproducibility chain.
    """

    id: UUID
    paragraph_id: UUID
    text: str
    source_span: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: ExtractionProvenance

    def __init__(self, **data: object) -> None:
        warnings.warn(
            "OperativeDirection is deprecated. Use OperativeDirective "
            "(kartavya.schemas.parsed_judgment). Removal in 0.4.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(**data)


class ExtractionResult(BaseModel):
    case_id: UUID
    paragraph_classifications: list[ParagraphClassification]
    verdict: VerdictClassification
    operative_directions: list[OperativeDirection]
    extracted_at: datetime
