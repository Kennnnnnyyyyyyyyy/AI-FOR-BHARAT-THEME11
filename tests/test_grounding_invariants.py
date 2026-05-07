"""Phase A schema-level grounding tests.

Each test attempts to construct a `ParsedJudgment` whose directives violate
one of the six grounding invariants. Pydantic's `@model_validator(mode="after")`
on `ParsedJudgment.validate_directive_grounding` must raise ValidationError.
These are negative tests: success means construction is rejected.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kartavya.schemas.parsed_judgment import (
    GroundedParagraph,
    OperativeDirective,
    ParsedJudgment,
)
from tests.fixtures.venkateshulu_stub import VENKATESHULU_STUB


def _stub_with(
    *,
    paragraphs: list[GroundedParagraph] | None = None,
    directives: list[OperativeDirective] | None = None,
) -> ParsedJudgment:
    base = VENKATESHULU_STUB.model_dump()
    if paragraphs is not None:
        base["paragraphs"] = [p.model_dump() for p in paragraphs]
    if directives is not None:
        base["directives"] = [d.model_dump() for d in directives]
    return ParsedJudgment.model_validate(base)


def test_directive_with_nonexistent_paragraph_rejected() -> None:
    with pytest.raises(ValidationError, match="paragraph_index"):
        _stub_with(
            directives=[
                OperativeDirective(
                    paragraph_index=99,  # not in stub paragraphs
                    char_span=(0, 5),
                    verbatim_text="Accor",
                    actor_resolved=3,
                    verb="DIRECT",
                    object_text="placeholder",
                )
            ]
        )


def test_directive_verbatim_text_must_be_substring() -> None:
    with pytest.raises(ValidationError, match="not a substring"):
        _stub_with(
            directives=[
                OperativeDirective(
                    paragraph_index=24,
                    char_span=(0, 5),
                    verbatim_text="WRONG",
                    actor_resolved=3,
                    verb="DIRECT",
                    object_text="placeholder",
                )
            ]
        )


def test_directive_char_span_out_of_bounds_rejected() -> None:
    with pytest.raises(ValidationError, match="out of bounds"):
        _stub_with(
            directives=[
                OperativeDirective(
                    paragraph_index=24,
                    char_span=(0, 99999),  # past end of paragraph 24
                    verbatim_text="anything",
                    actor_resolved=3,
                    verb="DIRECT",
                    object_text="placeholder",
                )
            ]
        )


def test_directive_actor_must_be_in_respondents() -> None:
    with pytest.raises(ValidationError, match="not in case respondents"):
        _stub_with(
            directives=[
                OperativeDirective(
                    paragraph_index=24,
                    char_span=(0, 12),
                    verbatim_text="Accordingly,",
                    actor_resolved=99,  # not a respondent
                    verb="DIRECT",
                    object_text="placeholder",
                )
            ]
        )


def test_directive_must_come_from_operative_paragraph() -> None:
    facts_only = [
        GroundedParagraph(
            paragraph_index=24,
            text="Some facts narrative.",
            section_class="FACTS",
        )
    ]
    with pytest.raises(ValidationError, match="OPERATIVE"):
        _stub_with(
            paragraphs=facts_only,
            directives=[
                OperativeDirective(
                    paragraph_index=24,
                    char_span=(0, 4),
                    verbatim_text="Some",
                    actor_resolved=3,
                    verb="DIRECT",
                    object_text="placeholder",
                )
            ],
        )


def test_directive_must_be_in_court_voice() -> None:
    """Phase A: voice_in_span returns COURT when voice_spans is empty, so this
    test constructs a paragraph where a non-COURT span covers the directive's
    char range. Phase B will populate voice_spans from the voice tagger.
    """
    from kartavya.schemas.voice import VoiceSpan

    quoted_para = [
        GroundedParagraph(
            paragraph_index=24,
            text="The Supreme Court held that the petitioner shall pay costs.",
            section_class="OPERATIVE",
            voice_spans=[
                VoiceSpan(char_start=0, char_end=59, voice="SUPREME_COURT_QUOTE"),
            ],
        )
    ]
    with pytest.raises(ValidationError, match="court voice"):
        _stub_with(
            paragraphs=quoted_para,
            directives=[
                OperativeDirective(
                    paragraph_index=24,
                    char_span=(32, 42),  # "petitioner"
                    verbatim_text="petitioner",
                    actor_resolved=3,
                    verb="DIRECT",
                    object_text="pay costs",
                )
            ],
        )
