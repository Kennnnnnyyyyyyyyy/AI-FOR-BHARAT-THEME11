"""Span-only directive parser. Phase B4.

The LLM emits character offsets pointing at directives in OPERATIVE
paragraphs; the parser reconstructs `verbatim_text` from
`paragraph.text[char_start:char_end]`. Three independent grounding guards
(section_class, voice, substring/bounds) plus an actor FK guard make
hallucinated or mis-located directives structurally unreachable:

  Guard 1 (section): paragraphs with section_class != "OPERATIVE" are
    skipped before the LLM is even called. This is the upstream filter.
  Guard 2 (voice): within an OPERATIVE paragraph, only character ranges
    in COURT voice can carry directives. Statutory paraphrases, party
    contentions, and quoted holdings are excluded by `voice_in_span`.
  Guard 3 (bounds + substring): every offset range must satisfy
    0 <= s < e <= len(text); the reconstructed substring is the source
    of `verbatim_text`, so a hallucinated paraphrase cannot survive.
  Guard 4 (actor FK): the LLM-returned `actor_text` is mapped to a
    respondent_no via three resolution strategies (ordinal language,
    unique-token designation match, organization fallback). Anything
    that cannot be grounded returns the sentinel UNRESOLVED_RESPONDENT_NO
    (-1) which fails the FK validator and the directive is rejected.

For Venkateshulu (pure dismissal), this parser returns `[]`. The verdict-
gated rules engine then emits one DEFENSIVE_MONITOR card. The four
historical phantom cards are unreachable through any path: P21's
revisional-authority quote is REASONING-class (skipped at guard 1), and
P24's text contains no directive verbs at all.

The parser does not throw on per-directive validation failures. One bad
directive in a list of three should not lose the other two; the loop
catches `ValueError` / `ValidationError` per item, audit-logs the
rejection, and continues. The parser DOES propagate hard LLM failures
(client unreachable, schema rejection) because B4 is not the right
layer to decide retry-vs-fail policy. The pipeline orchestrator
(currently the test harness; in production, the FastAPI handler) owns
that decision.

v0.1 limitations (documented inline):
  * Multi-respondent directives ("respondents 1 and 2 are directed to ...")
    return the first match and audit-log the range. Splitting into N
    `OperativeDirective` instances is a v0.2 refinement.
  * `object_text` is set to the full `verbatim_text`. Extracting the
    action sub-span ("file an affidavit") separately is a v0.2 refinement.
  * The actor resolver is conservative on designation matching: if no
    distinctive token uniquely picks a single respondent, it falls
    through to organization fallback or UNRESOLVED. Soft-matching is the
    wrong default; UNRESOLVED routes to human review.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from pydantic import ValidationError

from kartavya.audit import recorder as audit
from kartavya.schemas.case import Respondent
from kartavya.schemas.parsed_judgment import (
    GroundedParagraph,
    OperativeDirective,
    ParsedJudgment,
    TimeClause,
)
from kartavya.schemas.voice import VoiceSpan

UNRESOLVED_RESPONDENT_NO: int = -1
DIRECTIVE_PARSER_PROMPT_VERSION: str = "v4"
DEFAULT_MODEL: str = "llama3.1:8b-instruct-q4_K_M"

_PROMPT_PATH = (
    Path(__file__).parent
    / "prompts"
    / f"operative_extractor.{DIRECTIVE_PARSER_PROMPT_VERSION}.md"
)


# JSON Schema used by Ollama's native `format` parameter when wired to a
# real client. Tests pass MagicMock and never trip this; production will
# enforce the schema at the LLM layer.
DIRECTIVE_PARSER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "directives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "char_start": {"type": "integer", "minimum": 0},
                    "char_end": {"type": "integer", "minimum": 1},
                    "actor_text": {"type": "string", "minLength": 1},
                    "verb_token": {
                        "type": "string",
                        "enum": [
                            "DIRECT",
                            "ORDER",
                            "QUASH",
                            "REMAND",
                            "ISSUE_NOTICE",
                            "DISPOSE_WITH_DIRECTION",
                        ],
                    },
                    "time_clause_text": {"type": ["string", "null"]},
                },
                "required": [
                    "char_start",
                    "char_end",
                    "actor_text",
                    "verb_token",
                ],
            },
        },
    },
    "required": ["directives"],
}


class DirectiveLLMClient(Protocol):
    """Minimal interface for the directive parser's LLM call. Real wiring
    uses an Ollama-backed adapter that honors `format=DIRECTIVE_PARSER_SCHEMA`
    natively; tests pass MagicMock."""

    def generate_json(self, prompt: str) -> dict[str, Any]: ...


# Actor resolver -------------------------------------------------------------


_ORDINAL_WORDS: dict[str, int] = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "1st": 1,
    "2nd": 2,
    "3rd": 3,
    "4th": 4,
    "5th": 5,
    "6th": 6,
    "7th": 7,
    "8th": 8,
    "9th": 9,
    "10th": 10,
}

_RESPONDENT_NUM_RE = re.compile(
    r"\brespondent(?:s)?\s+(?:no\.?\s*|number\s+)?(\d+)\b",
    re.IGNORECASE,
)

_DESIGNATION_STOPWORDS = {
    "government",
    "department",
    "ministry",
    "office",
    "the",
    "and",
    "of",
    "to",
    "for",
}


def _distinctive_tokens(designation: str) -> set[str]:
    """Pull noun tokens that disambiguate one respondent from another.

    Tokens of length >= 4 (so single-letter / short connective words drop
    out), then drop a small stopword set covering "Government",
    "Department", "Ministry", "Office" and similar function words that
    appear in nearly every designation.
    """
    tokens = re.findall(r"\b[a-z]{4,}\b", designation.lower())
    return {t for t in tokens if t not in _DESIGNATION_STOPWORDS}


def _unique_designation_tokens(
    me: Respondent, respondents: list[Respondent]
) -> set[str]:
    mine = _distinctive_tokens(me.designation)
    others: set[str] = set()
    for other in respondents:
        if other.respondent_no == me.respondent_no:
            continue
        others |= _distinctive_tokens(other.designation)
    return mine - others


def resolve_actor(actor_text: str, respondents: list[Respondent]) -> int:
    """Map LLM-returned actor_text to a respondent_no.

    Resolution strategy (first match wins):

      1. Ordinal language. "respondent No.3", "the second respondent",
         "respondents 1 and 2" (returns the first match for ranges; v0.2
         splits ranges into multiple directives).
      2. Unique-token designation match. A token from this respondent's
         designation that does NOT appear in any other respondent's
         designation must appear in actor_text. If exactly one respondent
         has a unique token in actor_text, return that respondent_no.
         If zero or more than one match, fall through.
      3. Organization fallback. "the State" / "State of Karnataka" -> the
         lowest-numbered Karnataka respondent; "Union of India" / "central
         government" -> the lowest-numbered Government of India respondent.

    Returns UNRESOLVED_RESPONDENT_NO (-1) if nothing grounds. The caller
    treats -1 as a hard reject; never substitute a guess.
    """
    text = actor_text.lower().strip()

    m = _RESPONDENT_NUM_RE.search(text)
    if m:
        return int(m.group(1))
    for word, n in _ORDINAL_WORDS.items():
        if re.search(rf"\bthe\s+{re.escape(word)}\s+respondent\b", text):
            return n

    matches: list[Respondent] = []
    for r in respondents:
        unique = _unique_designation_tokens(r, respondents)
        if unique and any(tok in text for tok in unique):
            matches.append(r)
    if len(matches) == 1:
        return matches[0].respondent_no

    if "state of karnataka" in text or "the state" in text:
        gok = [
            r for r in respondents if r.organization == "Government of Karnataka"
        ]
        if gok:
            return min(gok, key=lambda r: r.respondent_no).respondent_no
    if "union of india" in text or "central government" in text:
        goi = [
            r for r in respondents if r.organization == "Government of India"
        ]
        if goi:
            return min(goi, key=lambda r: r.respondent_no).respondent_no

    return UNRESOLVED_RESPONDENT_NO


# Time-clause parsing --------------------------------------------------------


_TIME_CLAUSE_RE = re.compile(
    r"within\s+([\w-]+)\s+(day|days|week|weeks|month|months|year|years)\b",
    re.IGNORECASE,
)

_WORD_TO_NUMBER: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "ninety": 90,
}

_UNIT_MAP: dict[str, str] = {
    "day": "DAYS",
    "days": "DAYS",
    "week": "WEEKS",
    "weeks": "WEEKS",
    "month": "MONTHS",
    "months": "MONTHS",
    "year": "YEARS",
    "years": "YEARS",
}


def _word_to_int(s: str) -> int | None:
    s = s.lower().strip()
    if s.isdigit():
        return int(s)
    return _WORD_TO_NUMBER.get(s)


def _parse_time_clause(raw: str | None) -> TimeClause | None:
    if not raw:
        return None
    m = _TIME_CLAUSE_RE.search(raw)
    if not m:
        return None
    quantity = _word_to_int(m.group(1))
    if quantity is None:
        return None
    unit_raw = m.group(2).lower()
    unit = cast(Literal["DAYS", "WEEKS", "MONTHS", "YEARS"], _UNIT_MAP[unit_raw])
    return TimeClause(raw=raw, unit=unit, quantity=quantity)


# Per-directive build with grounding guards ----------------------------------


class _DirectiveRejected(Exception):
    """Internal: signals one directive payload was rejected by a guard.

    Carries the rejection reason so the audit log can record it. The loop
    catches this and continues with the next candidate; one bad directive
    must not poison the rest.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _build_directive(
    case: ParsedJudgment,
    para: GroundedParagraph,
    payload: dict[str, Any],
) -> OperativeDirective:
    s_raw = payload.get("char_start")
    e_raw = payload.get("char_end")
    if not isinstance(s_raw, int) or not isinstance(e_raw, int):
        raise _DirectiveRejected(
            f"non-integer offsets: char_start={s_raw!r}, char_end={e_raw!r}"
        )
    s, e = s_raw, e_raw

    if not (0 <= s < e <= len(para.text)):
        raise _DirectiveRejected(
            f"char_span ({s}, {e}) out of bounds for paragraph "
            f"{para.paragraph_index} (len={len(para.text)})"
        )

    if para.section_class != "OPERATIVE":
        raise _DirectiveRejected(
            f"paragraph {para.paragraph_index} is "
            f"section_class={para.section_class}, not OPERATIVE"
        )

    voice = para.voice_in_span(s, e)
    if voice != "COURT":
        raise _DirectiveRejected(
            f"span ({s}, {e}) lies in voice={voice}, not COURT"
        )

    verbatim_text = para.text[s:e]

    actor_text = payload.get("actor_text")
    if not isinstance(actor_text, str) or not actor_text.strip():
        raise _DirectiveRejected(
            f"missing or empty actor_text: {actor_text!r}"
        )
    actor_resolved = resolve_actor(actor_text, case.respondents)
    respondent_nos = {r.respondent_no for r in case.respondents}
    if actor_resolved not in respondent_nos:
        raise _DirectiveRejected(
            f"actor_text {actor_text!r} resolved to {actor_resolved} which "
            f"is not in respondents {sorted(respondent_nos)}"
        )

    verb = payload.get("verb_token")
    time_clause = _parse_time_clause(payload.get("time_clause_text"))

    try:
        return OperativeDirective(
            paragraph_index=para.paragraph_index,
            char_span=(s, e),
            verbatim_text=verbatim_text,
            actor_resolved=actor_resolved,
            verb=verb,  # type: ignore[arg-type]
            object_text=verbatim_text,
            time_clause=time_clause,
        )
    except ValidationError as exc:
        raise _DirectiveRejected(
            f"OperativeDirective construction failed: {exc.errors()}"
        ) from exc


# Prompt rendering -----------------------------------------------------------


def _summarize_voice_spans(spans: list[VoiceSpan], total_chars: int) -> str:
    if not spans:
        return "(entire paragraph is COURT voice; no exclusions)"
    lines: list[str] = []
    for s in spans:
        ratio = (s.char_end - s.char_start) / total_chars if total_chars else 0.0
        lines.append(
            f"- chars [{s.char_start}, {s.char_end}) = {s.voice} "
            f"({ratio * 100:.0f}%)"
        )
    return "\n".join(lines)


def _render_prompt(case: ParsedJudgment, para: GroundedParagraph) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    body = template.split("---", 2)[-1].lstrip()
    respondent_list = "\n".join(
        f"{r.respondent_no}. {r.designation} ({r.organization})"
        for r in case.respondents
    )
    voice_summary = _summarize_voice_spans(list(para.voice_spans), len(para.text))
    return (
        body.replace("{case_number}", case.case_number)
        .replace("{verdict_class}", case.verdict_class)
        .replace("{respondent_list}", respondent_list)
        .replace("{voice_summary}", voice_summary)
        .replace("{paragraph_index}", str(para.paragraph_index))
        .replace("{paragraph_text}", para.text)
    )


# Orchestrator ---------------------------------------------------------------


def _extract_from_paragraph(
    case: ParsedJudgment,
    para: GroundedParagraph,
    llm_client: DirectiveLLMClient,
    *,
    model: str,
) -> list[OperativeDirective]:
    prompt = _render_prompt(case, para)
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    try:
        raw = llm_client.generate_json(prompt=prompt)
    except Exception as exc:
        audit.directive_extraction_failure(
            case_number=case.case_number,
            paragraph_index=para.paragraph_index,
            model=model,
            prompt_sha=prompt_sha,
            error=str(exc),
        )
        raise

    audit.directive_extraction_raw(
        case_number=case.case_number,
        paragraph_index=para.paragraph_index,
        model=model,
        prompt_sha=prompt_sha,
        raw_output=str(raw),
    )

    constructed: list[OperativeDirective] = []
    if not isinstance(raw, dict):
        return constructed
    payloads = raw.get("directives", [])
    if not isinstance(payloads, list):
        return constructed

    for payload in payloads:
        if not isinstance(payload, dict):
            audit.directive_extraction_rejected(
                case_number=case.case_number,
                paragraph_index=para.paragraph_index,
                rejected_payload={"raw": str(payload)},
                reason="payload not a dict",
            )
            continue
        try:
            directive = _build_directive(case, para, payload)
        except _DirectiveRejected as exc:
            audit.directive_extraction_rejected(
                case_number=case.case_number,
                paragraph_index=para.paragraph_index,
                rejected_payload=payload,
                reason=exc.reason,
            )
            continue
        constructed.append(directive)
        audit.directive_extraction_constructed(
            case_number=case.case_number,
            paragraph_index=para.paragraph_index,
            directive_summary={
                "actor_resolved": directive.actor_resolved,
                "verb": directive.verb,
                "verbatim_text": directive.verbatim_text,
                "char_span": list(directive.char_span),
                "time_clause": (
                    directive.time_clause.raw
                    if directive.time_clause is not None
                    else None
                ),
            },
        )
    return constructed


def extract_directives(
    case: ParsedJudgment,
    *,
    llm_client: DirectiveLLMClient,
    model: str = DEFAULT_MODEL,
) -> list[OperativeDirective]:
    """Run the span-only directive parser over every OPERATIVE paragraph
    in the case.

    Paragraphs whose section_class != "OPERATIVE" are skipped before the
    LLM is even called. Within OPERATIVE paragraphs the LLM emits
    character offsets only; the parser reconstructs `verbatim_text` from
    `paragraph.text[char_start:char_end]` and constructs OperativeDirective
    after running explicit guards (bounds, voice, section, actor FK).
    Per-directive validation failures are caught and audit-logged; the
    function continues with the next candidate. Hard LLM failures
    (unreachable, client-side schema rejection) are propagated to the
    caller.

    Returns an empty list if there are no OPERATIVE paragraphs or none
    contained directives. For Venkateshulu (pure dismissal), this is the
    expected output.
    """
    operative_paragraphs = [
        p for p in case.paragraphs if p.section_class == "OPERATIVE"
    ]
    if not operative_paragraphs:
        return []

    all_directives: list[OperativeDirective] = []
    for para in operative_paragraphs:
        all_directives.extend(
            _extract_from_paragraph(case, para, llm_client, model=model)
        )
    return all_directives


__all__ = [
    "DEFAULT_MODEL",
    "DIRECTIVE_PARSER_PROMPT_VERSION",
    "DIRECTIVE_PARSER_SCHEMA",
    "DirectiveLLMClient",
    "UNRESOLVED_RESPONDENT_NO",
    "extract_directives",
    "resolve_actor",
]
