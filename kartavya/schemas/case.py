"""CaseMetadata. Case-level inputs to the rules engine.

The extraction pipeline does not compute case identity, parties, or dates (per
§3.1). That metadata is loaded from a separate case.json adjacent to
paragraphs.json and consumed by rules_engine.generate_action_plan(...) and
rules_engine.generate_actions(...) alongside the extraction result.

Designations on respondents and additional forums follow §3.3: a designation
is a role string ("Chief Executive Officer, KIADB"), never a person name. The
optional `name` field records the entity name as it appears in the case
caption; the rules engine binds to `designation`. The `organization` field
classifies the respondent's level of government, which the rules engine uses
to pick the primary state respondent for verdict-driven actions.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Petitioner(BaseModel):
    name: str
    designation: str | None = None  # null for private petitioners


class Respondent(BaseModel):
    """A respondent in the cause title.

    Phase A reshape: `ordinal` was renamed to `respondent_no`; `organization`
    was added (required) so the engine can pick the primary state respondent;
    `name` was demoted to optional so legacy fixtures still validate while
    Phase A stub fixtures need not provide it.
    """

    respondent_no: int = Field(ge=1)  # 1-indexed; matches case caption ordering
    designation: str  # §3.3, never a person name
    organization: str  # e.g. "Government of Karnataka", "Government of India"
    address: str | None = None
    name: str | None = None  # legacy field, optional


class AdditionalForum(BaseModel):
    """Non-respondent forum addressed by an operative direction (e.g. a
    reference court directed to dispose within a deadline). Resolved by the
    responsibility mapper from the directive's addressee text via `key`.
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
    primary_respondent_no: int = Field(ge=1)
    additional_forums: list[AdditionalForum] = Field(default_factory=list)

    def primary_respondent(self) -> Respondent:
        for r in self.respondents:
            if r.respondent_no == self.primary_respondent_no:
                return r
        raise ValueError(
            f"primary_respondent_no={self.primary_respondent_no} "
            f"not found in respondents"
        )
