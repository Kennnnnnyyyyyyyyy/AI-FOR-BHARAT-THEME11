"""Phase B2 deterministic section classifier unit tests.

Synthetic feature-vector tests that exercise each rule in isolation. No
PDF, no LLM. The real-PDF sweep lives in tests/integration/test_section_real_pdf.py.

The most load-bearing test in this file is test_p21_shape_routes_to_uncertain:
the deterministic rule set has a deliberate gap between rule 5 (court-quote
dominant with court_voice_ratio < 0.30, returns PRECEDENT_CITATION) and rule
10 (court-quote with moderate court voice 0.40 to 0.70, returns REASONING).
Paragraphs that fall in the gap (high non-court density but no clear
endorsement / citation signals) route to UNCERTAIN by design. If a future
rule modification accidentally collapses the gap, this test fails and forces
a reckoning.
"""

from __future__ import annotations

from typing import Any

from kartavya.extraction.section import (
    SectionFeatures,
    classify_deterministic,
)


def _f(**overrides: Any) -> SectionFeatures:
    """Build a SectionFeatures with safe defaults — pure court voice paragraph
    with no quotes, no contentions, no cues."""
    defaults = dict(
        paragraph_index=1,
        text="",
        voice_spans=(),
        total_chars=1000,
        court_voice_chars=1000,
        non_court_chars_by_voice={},
        court_voice_ratio=1.0,
        starts_with_operative_cue=False,
        contains_decree_verb=False,
        starts_with_facts_cue=False,
        starts_with_argument_cue=False,
        starts_with_reasoning_cue=False,
        has_statute_quote=False,
        has_court_quote=False,
        has_revisional_quote=False,
        has_party_contention=False,
        is_last_body_paragraph=False,
    )
    defaults.update(overrides)
    return SectionFeatures(**defaults)  # type: ignore[arg-type]


def test_rule_1_operative_cue_decree_court() -> None:
    v = classify_deterministic(
        _f(
            starts_with_operative_cue=True,
            contains_decree_verb=True,
            court_voice_ratio=1.0,
            is_last_body_paragraph=True,
        )
    )
    assert v.section_class == "OPERATIVE"
    assert v.confidence >= 0.95


def test_rule_2_operative_cue_decree_last_lower_court_ratio() -> None:
    v = classify_deterministic(
        _f(
            starts_with_operative_cue=True,
            contains_decree_verb=True,
            court_voice_ratio=0.85,
            is_last_body_paragraph=True,
        )
    )
    assert v.section_class == "OPERATIVE"
    assert 0.85 <= v.confidence < 0.99


def test_rule_3_arguments_opener() -> None:
    v = classify_deterministic(
        _f(
            starts_with_argument_cue=True,
            court_voice_ratio=0.30,
            has_party_contention=True,
        )
    )
    assert v.section_class == "ARGUMENTS"


def test_rule_4_precedent_citation_statute_dominant() -> None:
    v = classify_deterministic(
        _f(
            has_statute_quote=True,
            non_court_chars_by_voice={"STATUTE_QUOTE": 700},
            total_chars=1000,
            court_voice_chars=300,
            court_voice_ratio=0.30,
        )
    )
    assert v.section_class == "PRECEDENT_CITATION"


def test_rule_5_precedent_citation_supreme_court_dominant() -> None:
    """Supreme Court quote dominates the paragraph: external precedent."""
    v = classify_deterministic(
        _f(
            has_court_quote=True,
            non_court_chars_by_voice={"SUPREME_COURT_QUOTE": 800},
            total_chars=1000,
            court_voice_chars=200,
            court_voice_ratio=0.20,
        )
    )
    assert v.section_class == "PRECEDENT_CITATION"


def test_other_court_quote_dominant_is_reasoning_not_precedent() -> None:
    """OTHER_COURT_QUOTE dominance signals this court quoting its own prior
    order. KHC writs follow such quotes with adoption clauses, so this is
    REASONING, not PRECEDENT_CITATION. Canonical example: P13 of
    Venkateshulu, where KHC quotes its 2015 order and proceeds to use that
    order to reject the petitioner's resurvey argument."""
    v = classify_deterministic(
        _f(
            has_court_quote=True,
            non_court_chars_by_voice={"OTHER_COURT_QUOTE": 800},
            total_chars=1000,
            court_voice_chars=200,
            court_voice_ratio=0.20,
        )
    )
    assert v.section_class == "REASONING"


def test_rule_6_reasoning_cue() -> None:
    v = classify_deterministic(
        _f(starts_with_reasoning_cue=True, court_voice_ratio=0.70)
    )
    assert v.section_class == "REASONING"


def test_rule_7_in_the_present_case() -> None:
    v = classify_deterministic(
        _f(
            text="In the present case, the petitioner has not carried out mining...",
            court_voice_ratio=0.95,
        )
    )
    assert v.section_class == "REASONING"
    assert v.confidence >= 0.85


def test_rule_8_facts_cue() -> None:
    v = classify_deterministic(
        _f(starts_with_facts_cue=True, court_voice_ratio=0.95)
    )
    assert v.section_class == "FACTS"


def test_court_endorsement_marker_pure_court_voice_yields_reasoning() -> None:
    """Pure court voice with explicit endorsement markers anywhere in the
    paragraph. Canonical example: P23 of Venkateshulu, which opens
    neutrally ("The second respondent ... has appropriately noticed ...")
    and closes with reasoning ("cannot be stated to be erroneous warranting
    interference"). Without this rule the paragraph would default to FACTS."""
    v = classify_deterministic(
        _f(
            text=(
                "The second respondent has appropriately noticed the matrix. "
                "The order cannot be stated to be erroneous warranting "
                "interference by this Court in the present petition."
            ),
            court_voice_ratio=1.0,
        )
    )
    assert v.section_class == "REASONING"
    assert v.reason == "court-endorsement-marker"


def test_rule_9_facts_high_court_voice() -> None:
    v = classify_deterministic(_f(court_voice_ratio=0.95))
    assert v.section_class == "FACTS"


def test_rule_10_reasoning_with_quote_moderate_court() -> None:
    v = classify_deterministic(
        _f(
            has_court_quote=True,
            court_voice_ratio=0.55,
            non_court_chars_by_voice={"SUPREME_COURT_QUOTE": 450},
        )
    )
    assert v.section_class == "REASONING"


def test_uncertain_when_no_rule_fires() -> None:
    """Court-quote-dominant but court_voice_ratio is too high for rule 5
    (needs <0.30) and too low for rule 10 (needs >=0.40). Falls into the
    deliberate gap and routes to UNCERTAIN."""
    v = classify_deterministic(
        _f(
            has_court_quote=True,
            court_voice_ratio=0.32,
            non_court_chars_by_voice={"REVISIONAL_AUTHORITY_QUOTE": 680},
        )
    )
    assert v.section_class == "UNCERTAIN"
    assert v.confidence == 0.0


def test_p21_shape_routes_to_uncertain() -> None:
    """Synthetic feature vector approximating Venkateshulu's paragraph 21:
    revisional-authority quote dominates, court voice ratio in the 0.05 to
    0.30 range, no operative cue, no reasoning cue at start. The rule set
    is intentionally constructed so this shape reaches UNCERTAIN. If a
    future rule modification accidentally collapses the gap, this test
    fails and the modification has to justify catching P21 deterministically
    instead of routing it to LLM."""
    v = classify_deterministic(
        _f(
            has_revisional_quote=True,
            court_voice_ratio=0.05,
            non_court_chars_by_voice={"REVISIONAL_AUTHORITY_QUOTE": 950},
            total_chars=1000,
            court_voice_chars=50,
        )
    )
    assert v.section_class == "UNCERTAIN"
