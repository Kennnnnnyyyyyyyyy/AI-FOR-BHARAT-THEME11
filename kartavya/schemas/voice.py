"""Voice and SectionClass enums + VoiceSpan model.

Phase A introduces the Voice taxonomy that the Phase B voice tagger will
populate. In Phase A, GroundedParagraph.voice_spans is empty on every
paragraph; the voice_in_span helper defaults to COURT when no span covers
a query range, which is correct for the Phase A stub fixture (paragraph 24
is unambiguously court voice).

The directive grounding validator on ParsedJudgment requires every
OperativeDirective char_span to resolve to COURT voice. This is a future
defense: in Phase B, statutory text quoted as authority, prior judgments,
party contentions, and quoted lower-tribunal reasoning will be tagged
non-COURT, and any directive whose span overlaps a non-COURT region will
fail validation rather than feed the action plan.
"""

from typing import Literal

from pydantic import BaseModel

Voice = Literal[
    "COURT",
    "SUPREME_COURT_QUOTE",
    "OTHER_COURT_QUOTE",
    "REVISIONAL_AUTHORITY_QUOTE",
    "STATUTE_QUOTE",
    "PARTY_CONTENTION",
]

SectionClass = Literal[
    "CAUSE_TITLE",
    "APPEARANCES",
    "PRAYER",
    "FACTS",
    "ARGUMENTS",
    "PRECEDENT_CITATION",
    "REASONING",
    "OPERATIVE",
    "DECREE",
]


class VoiceSpan(BaseModel):
    """A character range within a paragraph and the voice that owns it."""

    char_start: int
    char_end: int
    voice: Voice
