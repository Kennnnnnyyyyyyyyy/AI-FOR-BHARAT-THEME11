"""ExtractionProvenance — required metadata on every LLM-extracted field (§3.4)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractionProvenance(BaseModel):
    source_span: str
    paragraph_id: UUID
    bounding_box: tuple[int, int, int, int]
    confidence: float = Field(ge=0.0, le=1.0)
    prompt_sha: str
    model_id: str
    temperature: float
    extracted_at: datetime
