"""Extraction outputs — paragraph classifications, verdict, operative directions, and aggregate result."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from kartavya.schemas.provenance import ExtractionProvenance


class ParagraphLabel(str, Enum):
    FACTS = "facts"
    ARGUMENTS = "arguments"
    REASONING = "reasoning"
    PRECEDENT = "precedent"
    OPERATIVE = "operative"
    DECREE = "decree"


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
    id: UUID
    paragraph_id: UUID
    text: str
    source_span: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: ExtractionProvenance


class ExtractionResult(BaseModel):
    case_id: UUID
    paragraph_classifications: list[ParagraphClassification]
    verdict: VerdictClassification
    operative_directions: list[OperativeDirection]
    extracted_at: datetime
