"""Phase B4 span-only directive parser unit tests.

Synthetic cases with a stubbed LLM client. Two test families:

  * Actor resolver. Six tests covering ordinal language, designation
    matching (unique-token success and ambiguous-fallthrough), and
    organization fallback.
  * End-to-end with stubbed LLM. Five tests covering pure dismissal,
    well-grounded directive construction, the three guard rejections
    (substring/voice/actor) plus the section guard at the loop level,
    and the one-bad-does-not-poison-good loop discipline.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

from kartavya.extraction.directives import (
    UNRESOLVED_RESPONDENT_NO,
    extract_directives,
    resolve_actor,
)
from kartavya.schemas.case import Respondent
from kartavya.schemas.parsed_judgment import GroundedParagraph, ParsedJudgment
from kartavya.schemas.voice import VoiceSpan


def _respondents() -> list[Respondent]:
    return [
        Respondent(
            respondent_no=1,
            designation="The Secretary, Ministry of Mines",
            organization="Government of India",
        ),
        Respondent(
            respondent_no=2,
            designation="The Joint Secretary, Ministry of Mines",
            organization="Government of India",
        ),
        Respondent(
            respondent_no=3,
            designation="Principal Secretary, Commerce and Industries",
            organization="Government of Karnataka",
        ),
        Respondent(
            respondent_no=5,
            designation="Director, Department of Mines and Geology",
            organization="Government of Karnataka",
        ),
        Respondent(
            respondent_no=6,
            designation="Senior Geologist, Department of Mines and Geology",
            organization="Government of Karnataka",
        ),
    ]


def _stub_llm(directives_payload: list[dict[str, Any]]) -> MagicMock:
    client = MagicMock()
    client.generate_json.return_value = {"directives": directives_payload}
    return client


# Actor resolver -------------------------------------------------------------


def test_resolve_actor_ordinal_word() -> None:
    assert resolve_actor("the second respondent", _respondents()) == 2


def test_resolve_actor_ordinal_number() -> None:
    assert resolve_actor("respondent No.3", _respondents()) == 3


def test_resolve_actor_designation_unique() -> None:
    """'director' is unique to R5 (R6 is Senior Geologist), so 'the Director
    of Mines' resolves unambiguously to R5 even though 'mines' is shared."""
    assert resolve_actor("the Director of Mines", _respondents()) == 5


def test_resolve_actor_designation_ambiguous_returns_unresolved() -> None:
    """'mines' and 'geology' are both shared between R5 and R6; no token
    uniquely picks one. Falls through to organization fallback, which has
    no signal here ('the State' / 'union of india' not present), so
    UNRESOLVED."""
    assert (
        resolve_actor("the Department of Mines and Geology", _respondents())
        == UNRESOLVED_RESPONDENT_NO
    )


def test_resolve_actor_state_of_karnataka_resolves_to_lowest_gok_no() -> None:
    assert resolve_actor("the State of Karnataka", _respondents()) == 3


def test_resolve_actor_unknown_returns_unresolved() -> None:
    assert (
        resolve_actor("the Election Commission", _respondents())
        == UNRESOLVED_RESPONDENT_NO
    )


# End-to-end with stubbed LLM ------------------------------------------------


def _case_with_operative(
    text: str, *, respondents: list[Respondent] | None = None
) -> ParsedJudgment:
    return ParsedJudgment(
        case_number="WP TEST/2026",
        court="High Court of Karnataka at Bengaluru",
        judgment_date=date(2026, 4, 17),
        petitioner_name="Test Petitioner",
        respondents=respondents or _respondents(),
        paragraphs=[
            GroundedParagraph(
                paragraph_index=24,
                text=text,
                section_class="OPERATIVE",
            ),
        ],
        verdict_class="DISPOSED_WITH_DIRECTIONS",
        directives=[],
    )


def test_pure_dismissal_yields_no_directives() -> None:
    case = _case_with_operative(
        "Accordingly, the present petition is dismissed as being devoid of merit."
    )
    case = case.model_copy(update={"verdict_class": "DISMISSED"})
    client = _stub_llm([])
    directives = extract_directives(case, llm_client=client)
    assert directives == []


def test_well_grounded_directive_constructs_successfully() -> None:
    text = (
        "The second respondent is directed to dispose of the application "
        "within four weeks."
    )
    case = _case_with_operative(text)
    payload = [
        {
            "char_start": 0,
            "char_end": len(text) - 1,
            "actor_text": "the second respondent",
            "verb_token": "DIRECT",
            "time_clause_text": "within four weeks",
        }
    ]
    client = _stub_llm(payload)
    directives = extract_directives(case, llm_client=client)
    assert len(directives) == 1
    d = directives[0]
    assert d.paragraph_index == 24
    assert d.actor_resolved == 2
    assert d.verb == "DIRECT"
    assert d.time_clause is not None
    assert d.time_clause.unit == "WEEKS"
    assert d.time_clause.quantity == 4


def test_substring_mismatch_rejects_directive() -> None:
    """Out-of-bounds char_end fails the bounds guard. The directive is
    rejected without exception; the parser returns []."""
    text = "The respondent is directed to file an affidavit."
    case = _case_with_operative(text)
    payload = [
        {
            "char_start": 0,
            "char_end": len(text) + 100,
            "actor_text": "the respondent",
            "verb_token": "DIRECT",
            "time_clause_text": None,
        }
    ]
    client = _stub_llm(payload)
    directives = extract_directives(case, llm_client=client)
    assert directives == []


def test_unresolved_actor_rejects_directive() -> None:
    text = "The Election Commission is directed to act."
    case = _case_with_operative(text)
    payload = [
        {
            "char_start": 0,
            "char_end": len(text) - 1,
            "actor_text": "the Election Commission",
            "verb_token": "DIRECT",
            "time_clause_text": None,
        }
    ]
    client = _stub_llm(payload)
    directives = extract_directives(case, llm_client=client)
    assert directives == []


def test_non_court_voice_rejects_directive() -> None:
    """Within an OPERATIVE paragraph, a directive whose char range falls
    inside a non-COURT voice span (here, a STATUTE_QUOTE) is rejected by
    the voice guard."""
    text = (
        "The Court has considered Section 8A which states that "
        "the holder shall file an application within thirty days."
    )
    statute_start = text.index("the holder")
    statute_end = len(text) - 1
    para = GroundedParagraph(
        paragraph_index=24,
        text=text,
        section_class="OPERATIVE",
        voice_spans=[
            VoiceSpan(
                char_start=statute_start,
                char_end=statute_end,
                voice="STATUTE_QUOTE",
            )
        ],
    )
    case = ParsedJudgment(
        case_number="WP TEST/2026",
        court="High Court of Karnataka at Bengaluru",
        judgment_date=date(2026, 4, 17),
        petitioner_name="Test",
        respondents=_respondents(),
        paragraphs=[para],
        verdict_class="DISPOSED_WITH_DIRECTIONS",
        directives=[],
    )
    payload = [
        {
            "char_start": statute_start,
            "char_end": statute_end,
            "actor_text": "the holder",
            "verb_token": "DIRECT",
            "time_clause_text": "within thirty days",
        }
    ]
    client = _stub_llm(payload)
    directives = extract_directives(case, llm_client=client)
    assert directives == []


def test_non_operative_paragraph_skipped() -> None:
    """A non-OPERATIVE paragraph never reaches the LLM. P21 of the
    canonical case (REASONING-class revisional-authority quote) is the
    real-world load-bearing example; here we use a synthetic REASONING
    paragraph alongside a real OPERATIVE one and assert exactly one LLM
    call."""
    case = ParsedJudgment(
        case_number="WP TEST/2026",
        court="High Court of Karnataka at Bengaluru",
        judgment_date=date(2026, 4, 17),
        petitioner_name="Test",
        respondents=_respondents(),
        paragraphs=[
            GroundedParagraph(
                paragraph_index=21,
                text="...quoted reasoning...",
                section_class="REASONING",
            ),
            GroundedParagraph(
                paragraph_index=24,
                text="Accordingly, the petition is dismissed.",
                section_class="OPERATIVE",
            ),
        ],
        verdict_class="DISMISSED",
        directives=[],
    )
    client = _stub_llm([])
    extract_directives(case, llm_client=client)
    assert client.generate_json.call_count == 1
    call_kwargs = client.generate_json.call_args.kwargs
    prompt = call_kwargs.get("prompt", "")
    assert "(index 24)" in prompt
    assert "(index 21)" not in prompt


def test_one_bad_directive_does_not_poison_a_good_one() -> None:
    text = (
        "The second respondent is directed to file an affidavit within four weeks. "
        "The Election Commission is directed to act within ten days."
    )
    case = _case_with_operative(text)
    good_end = text.index("within four weeks") + len("within four weeks")
    bad_start = text.index("The Election Commission")
    payload = [
        {
            "char_start": 0,
            "char_end": good_end,
            "actor_text": "the second respondent",
            "verb_token": "DIRECT",
            "time_clause_text": "within four weeks",
        },
        {
            "char_start": bad_start,
            "char_end": len(text) - 1,
            "actor_text": "the Election Commission",
            "verb_token": "DIRECT",
            "time_clause_text": "within ten days",
        },
    ]
    client = _stub_llm(payload)
    directives = extract_directives(case, llm_client=client)
    assert len(directives) == 1
    assert directives[0].actor_resolved == 2
