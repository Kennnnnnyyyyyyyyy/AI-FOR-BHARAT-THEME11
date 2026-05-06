"""Paragraph — a single segmented unit from an ingested judgment PDF; input to extraction."""

from uuid import UUID

from pydantic import BaseModel


class Paragraph(BaseModel):
    id: UUID
    page: int
    bounding_box: tuple[int, int, int, int]
    text: str
    paragraph_index: int
