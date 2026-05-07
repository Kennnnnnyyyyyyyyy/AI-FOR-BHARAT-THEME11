"""CaseMetadata — case-level inputs to the rules engine.

The extraction pipeline doesn't compute case identity, parties, or dates (§3.1).
That metadata is loaded from a separate `case.json` adjacent to `paragraphs.json`
and consumed by `rules_engine.generate_action_plan(...)` alongside the
`ExtractionResult`.

Designations on respondents and additional forums follow §3.3 — designation
strings ("Chief Executive Officer, Karnataka Industrial Areas Development
Board"), never person names. The `name` field exists to record the entity name
the case caption uses; the rules engine binds to `designation`.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Petitioner(BaseModel):
    name: str
    designation: str | None = None  # null for private petitioners


class Respondent(BaseModel):
    ordinal: int = Field(ge=1)  # 1-indexed; matches case caption ordering
    name: str
    designation: str  # §3.3 — never a person name


class AdditionalForum(BaseModel):
    """Non-respondent forum addressed by an operative direction (e.g. a
    reference court directed to dispose within a deadline). Resolved by the
    responsibility mapper from the directive's addressee text via the `key`.
    """

    key: str  # e.g. "reference_court"
    designation: str


class CaseMetadata(BaseModel):
    case_id: str
    court: str
    case_number: str
    judgment_date: date
    petitioner: Petitioner
    respondents: list[Respondent]
    primary_respondent_ordinal: int = Field(ge=1)
    additional_forums: list[AdditionalForum] = Field(default_factory=list)

    def primary_respondent(self) -> Respondent:
        for r in self.respondents:
            if r.ordinal == self.primary_respondent_ordinal:
                return r
        raise ValueError(
            f"primary_respondent_ordinal={self.primary_respondent_ordinal} "
            f"not found in respondents"
        )
