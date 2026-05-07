"""ParsedJudgment. The Phase A canonical case input to the rules engine.

Coexists with the legacy `ExtractionResult` + `CaseMetadata` pair. The legacy
0.1.0 engine path consumes that pair; the new 0.2.0 `generate_actions(...)`
path consumes `ParsedJudgment` directly.

The grounding validator on `ParsedJudgment.directives` enforces the
architectural principle: extraction is quotation, not generation. Every
`OperativeDirective` must (1) cite a paragraph that exists, (2) carry a
char_span within that paragraph, (3) carry a verbatim_text equal to
paragraph.text[char_start:char_end], (4) come from an OPERATIVE paragraph,
(5) sit in COURT voice, (6) name an actor that is an FK into respondents.
A directive that does not satisfy all six cannot be constructed.

`OperativeDirective` (with the trailing 'e') is the new type. `OperativeDirection`
(without 'e', in schemas/extraction.py) is the legacy type used by the v3
directive extractor pipeline. Both coexist for one cycle; Phase B migrates
the extractor to emit OperativeDirective and deprecates OperativeDirection.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from kartavya.schemas.case import Respondent
from kartavya.schemas.voice import SectionClass, Voice, VoiceSpan

VerdictClass = Literal[
    "ALLOWED",
    "PARTLY_ALLOWED",
    "DISMISSED",
    "DISMISSED_WITH_COSTS",
    "DISPOSED_WITH_DIRECTIONS",
    "REMANDED",
]


class GroundedParagraph(BaseModel):
    """A paragraph with section_class and voice_spans annotations.

    Phase A: voice_spans is empty on every paragraph and voice_in_span returns
    COURT for any query range. The Phase B voice tagger populates voice_spans.
    """

    paragraph_index: int
    text: str
    section_class: SectionClass
    voice_spans: list[VoiceSpan] = Field(default_factory=list)

    def voice_in_span(self, s: int, e: int) -> Voice:
        """Return the dominant voice for the range [s, e).

        If voice_spans is empty, return COURT. Otherwise scan spans by
        char_start; the first non-COURT span that overlaps [s, e) wins.
        If no span overlaps, the range is implicitly COURT.
        """
        if not self.voice_spans:
            return "COURT"
        for span in sorted(self.voice_spans, key=lambda x: x.char_start):
            if span.char_end <= s or span.char_start >= e:
                continue
            if span.voice != "COURT":
                return span.voice
        return "COURT"


class TimeClause(BaseModel):
    """A relative-period expression extracted verbatim from a directive span.

    `raw` is the exact substring of the source paragraph; the rules engine
    converts (unit, quantity) to an absolute deadline using judgment_date.
    """

    raw: str
    unit: Literal["DAYS", "WEEKS", "MONTHS", "YEARS"]
    quantity: int


class OperativeDirective(BaseModel):
    """Phase A canonical directive type.

    Coexists with legacy `OperativeDirection` (in schemas/extraction.py).
    Grounding invariants are enforced at the `ParsedJudgment` level, where
    the source paragraphs and respondent list are visible.
    """

    paragraph_index: int
    char_span: tuple[int, int]
    verbatim_text: str
    actor_resolved: int  # FK into Respondent.respondent_no
    verb: Literal[
        "DIRECT",
        "ORDER",
        "QUASH",
        "REMAND",
        "ISSUE_NOTICE",
        "DISPOSE_WITH_DIRECTION",
    ]
    object_text: str
    time_clause: Optional[TimeClause] = None


class ParsedJudgment(BaseModel):
    """Canonical Phase A case input.

    Construction is rejected by `validate_directive_grounding` if any
    directive fails any of six grounding invariants. The validator runs in
    `mode="after"` so all fields have been parsed before grounding is
    checked.
    """

    case_number: str
    court: str
    judgment_date: date
    petitioner_name: str
    respondents: list[Respondent]
    paragraphs: list[GroundedParagraph]
    verdict_class: VerdictClass
    directives: list[OperativeDirective] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_directive_grounding(self) -> "ParsedJudgment":
        para_by_index = {p.paragraph_index: p for p in self.paragraphs}
        respondent_nos = {r.respondent_no for r in self.respondents}
        for d in self.directives:
            if d.paragraph_index not in para_by_index:
                raise ValueError(
                    f"directive paragraph_index {d.paragraph_index} not in paragraphs"
                )
            para = para_by_index[d.paragraph_index]
            s, e = d.char_span
            if not (0 <= s < e <= len(para.text)):
                raise ValueError(
                    f"directive char_span {(s, e)} out of bounds for paragraph "
                    f"{d.paragraph_index} (len={len(para.text)})"
                )
            if para.text[s:e] != d.verbatim_text:
                raise ValueError(
                    f"directive verbatim_text not a substring of paragraph "
                    f"{d.paragraph_index}"
                )
            if para.section_class != "OPERATIVE":
                raise ValueError(
                    f"directive must come from OPERATIVE paragraph, got "
                    f"{para.section_class}"
                )
            voice = para.voice_in_span(s, e)
            if voice != "COURT":
                raise ValueError(
                    f"directive must be in court voice, got {voice}"
                )
            if d.actor_resolved not in respondent_nos:
                raise ValueError(
                    f"actor_resolved={d.actor_resolved} not in case respondents "
                    f"{sorted(respondent_nos)}"
                )
        return self

    def primary_state_respondent(self) -> Optional[Respondent]:
        """Lowest-numbered respondent whose organization is a Karnataka state body.

        Returns None if no Karnataka respondent is present, in which case any
        plan that targets PRIMARY_STATE_RESPONDENT will fail render-time
        validation with code UNGROUNDED_PRIMARY_STATE_TARGET.
        """
        karnataka_orgs = {"Government of Karnataka", "State of Karnataka"}
        candidates = [r for r in self.respondents if r.organization in karnataka_orgs]
        if not candidates:
            return None
        return min(candidates, key=lambda r: r.respondent_no)
