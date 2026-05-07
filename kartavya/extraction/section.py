"""Section classifier. Phase B2.

Two-stage classifier. Stage 1 is deterministic, voice-density-aware (consumes
the GroundedParagraph.voice_spans populated by the Phase B3 voice tagger),
runs over precomputed features, and produces a SectionVerdict with a
confidence score. Stage 2 is an LLM fallback invoked only when stage 1
confidence falls below the configured threshold; it is schema-constrained
and cannot return UNCERTAIN.

The threshold gap is intentional. P21 of the canonical Venkateshulu fixture
is the worked-example UNCERTAIN case: a revisional-authority quote dominates
the paragraph (~94% non-COURT) but the surrounding paragraphs (P22 picks up
"the finding of the revisional authority ... cannot be faulted with") show
the court is endorsing the quoted material as its own conclusion. A naive
voice-density rule would call PRECEDENT_CITATION; the right answer is
REASONING. The deterministic stage's gap between rule 5 (court-quote-dominant
with court_voice_ratio < 0.30) and rule 10 (court-quote with moderate court
voice 0.40 to 0.70) catches the P21 shape, falls through to UNCERTAIN, and
hands off to the LLM with prev/next paragraph context. Pre-flight measurement
of P21 in this fixture gave court_voice_ratio == 0.06 (94% revisional quote);
the fall-through is structural for any quote-dominant paragraph regardless
of where the exact ratio lands.

LLM unavailability degrades gracefully: a stage-1 UNCERTAIN with no LLM (or
a failing LLM) propagates up to the caller as UNCERTAIN with stage
DETERMINISTIC_LOW_CONFIDENCE. Downstream consumers (B4 directive parser)
treat UNCERTAIN as "do not extract directives from this paragraph; route
to human review."

Audit logging: callers pass an optional `case_number` to `classify_paragraphs`.
When provided, every classification (deterministic and LLM fallback) emits one
audit event via `kartavya.audit.recorder.record(...)` with the deterministic
class, confidence, reason, final stage, and the LLM model+prompt_sha when the
LLM path ran. Without `case_number` the classifier is hermetic — useful for
unit tests that don't want to touch the audit store.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple, Optional, Protocol
from uuid import NAMESPACE_OID, UUID, uuid4, uuid5

import structlog

from kartavya.audit import recorder as audit
from kartavya.schemas.audit import ActorKind, ActorRef, AuditEventType, EntityType
from kartavya.schemas.parsed_judgment import GroundedParagraph
from kartavya.schemas.voice import SectionClass, Voice, VoiceSpan

SECTION_CONFIDENCE_THRESHOLD: float = 0.70
LLM_FALLBACK_CONFIDENCE: float = 0.80

_LOG = structlog.get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "section_classifier_v1.md"

# Stage labels are part of the public contract: tests assert on the value.
Stage = Literal["DETERMINISTIC", "LLM_FALLBACK", "DETERMINISTIC_LOW_CONFIDENCE"]


class SectionVerdict(NamedTuple):
    section_class: SectionClass | Literal["UNCERTAIN"]
    confidence: float
    reason: str
    stage: Stage = "DETERMINISTIC"


@dataclass(frozen=True)
class SectionFeatures:
    paragraph_index: int
    text: str
    voice_spans: tuple[VoiceSpan, ...]
    total_chars: int
    court_voice_chars: int
    non_court_chars_by_voice: dict[Voice, int]
    court_voice_ratio: float
    starts_with_operative_cue: bool
    contains_decree_verb: bool
    starts_with_facts_cue: bool
    starts_with_argument_cue: bool
    starts_with_reasoning_cue: bool
    has_statute_quote: bool
    has_court_quote: bool
    has_revisional_quote: bool
    has_party_contention: bool
    is_last_body_paragraph: bool


# Cue regexes -----------------------------------------------------------------

_OPERATIVE_CUE = re.compile(
    r"^\s*(?:Accordingly|In\s+the\s+result|In\s+view\s+of\s+the\s+foregoing|"
    r"For\s+the\s+(?:reasons|foregoing)(?:\s+(?:stated|recorded))?"
    r"(?:\s+(?:above|hereinabove))?|Hence|Therefore|"
    r"This\s+(?:writ\s+)?[Pp]etition\b|The\s+(?:writ\s+)?[Pp]etition\b|"
    r"We\s+(?:allow|dismiss|partly\s+allow|hold|direct))",
    re.IGNORECASE,
)

_DECREE_VERB = re.compile(
    r"\b(?:is\s+(?:hereby\s+)?(?:dismissed|allowed|partly\s+allowed)|"
    r"stands\s+(?:disposed|remanded|allowed|dismissed)|"
    r"is\s+remanded|are\s+(?:hereby\s+)?(?:dismissed|allowed))\b",
    re.IGNORECASE,
)

_FACTS_CUE = re.compile(
    r"^\s*(?:The\s+relevant\s+facts|The\s+facts\s+of\s+the\s+case|"
    r"It\s+is\s+the\s+case\s+of|The\s+brief\s+facts|Brief\s+facts)",
    re.IGNORECASE,
)

_REASONING_CUE = re.compile(
    r"^\s*(?:In\s+view\s+of|Having\s+considered|"
    r"With\s+regard\s+to|It\s+is\s+relevant\s+to\s+note|"
    r"We\s+find|We\s+are\s+of\s+the\s+(?:view|opinion))",
    re.IGNORECASE,
)

# Court endorsement / reasoning markers that can appear anywhere in the
# paragraph. Distinct from the start-of-paragraph cues; these signal the
# court is reasoning even when the paragraph opens with neutral narrative
# framing. Calibrated to fire on Venkateshulu P23 ("appropriately noticed",
# "cannot be stated to be erroneous", "warranting interference") and to
# NOT fire on Venkateshulu P15 ("untenable and liable to be rejected") so
# P15 stays FACTS per the brief's center-of-gravity ruling.
_REASONING_MARKER = re.compile(
    r"(?:warranting\s+interference"
    r"|cannot\s+be\s+(?:stated|said)\s+to\s+be\s+erroneous"
    r"|cannot\s+be\s+faulted"
    r"|appropriately\s+(?:noticed|considered|held)"
    r"|do\s+not\s+find\s+(?:any\s+)?merit"
    r"|find(?:ing)?\s+no\s+merit)",
    re.IGNORECASE,
)

_CONTENTION_OPENER = re.compile(
    r"^\s*(?:It\s+is\s+(?:the\s+)?(?:primary\s+)?contention|"
    r"The\s+learned\s+counsel|"
    r"Per\s+contra|"
    r"The\s+learned\s+Additional\s+Government\s+Advocate)",
    re.IGNORECASE,
)


# Feature extraction ----------------------------------------------------------


def build_features(
    p: GroundedParagraph, *, is_last_body_paragraph: bool
) -> SectionFeatures:
    text = p.text
    total = len(text)

    by_voice: dict[Voice, int] = {}
    covered = 0
    for span in p.voice_spans:
        length = span.char_end - span.char_start
        by_voice[span.voice] = by_voice.get(span.voice, 0) + length
        covered += length
    court_chars = total - covered
    court_ratio = court_chars / total if total > 0 else 1.0

    starts_with_argument_cue = any(
        s.voice == "PARTY_CONTENTION" and s.char_start <= 80 for s in p.voice_spans
    ) or bool(_CONTENTION_OPENER.match(text))

    return SectionFeatures(
        paragraph_index=p.paragraph_index,
        text=text,
        voice_spans=tuple(p.voice_spans),
        total_chars=total,
        court_voice_chars=court_chars,
        non_court_chars_by_voice=by_voice,
        court_voice_ratio=court_ratio,
        starts_with_operative_cue=bool(_OPERATIVE_CUE.match(text)),
        contains_decree_verb=_decree_verb_in_court_voice(text, p.voice_spans),
        starts_with_facts_cue=bool(_FACTS_CUE.match(text)),
        starts_with_argument_cue=starts_with_argument_cue,
        starts_with_reasoning_cue=bool(_REASONING_CUE.match(text)),
        has_statute_quote=any(s.voice == "STATUTE_QUOTE" for s in p.voice_spans),
        has_court_quote=any(
            s.voice in ("SUPREME_COURT_QUOTE", "OTHER_COURT_QUOTE")
            for s in p.voice_spans
        ),
        has_revisional_quote=any(
            s.voice == "REVISIONAL_AUTHORITY_QUOTE" for s in p.voice_spans
        ),
        has_party_contention=any(
            s.voice == "PARTY_CONTENTION" for s in p.voice_spans
        ),
        is_last_body_paragraph=is_last_body_paragraph,
    )


def _decree_verb_in_court_voice(text: str, spans: list[VoiceSpan]) -> bool:
    for m in _DECREE_VERB.finditer(text):
        if not _overlaps_any(m.start(), m.end(), spans):
            return True
    return False


def _overlaps_any(s: int, e: int, spans: list[VoiceSpan]) -> bool:
    return any(
        not (e <= span.char_start or s >= span.char_end) for span in spans
    )


# Stage 1: deterministic classifier -------------------------------------------


def classify_deterministic(f: SectionFeatures) -> SectionVerdict:
    if (
        f.starts_with_operative_cue
        and f.contains_decree_verb
        and f.court_voice_ratio >= 0.95
    ):
        return SectionVerdict("OPERATIVE", 0.99, "cue+decree+court")

    if (
        f.starts_with_operative_cue
        and f.contains_decree_verb
        and f.is_last_body_paragraph
    ):
        return SectionVerdict("OPERATIVE", 0.92, "cue+decree+last")

    if f.starts_with_argument_cue:
        return SectionVerdict("ARGUMENTS", 0.97, "contention-opener")

    if f.has_statute_quote and not f.has_party_contention:
        statute_chars = f.non_court_chars_by_voice.get("STATUTE_QUOTE", 0)
        if f.total_chars > 0 and statute_chars / f.total_chars >= 0.50:
            return SectionVerdict("PRECEDENT_CITATION", 0.92, "statute-dominant")

    sc_chars = f.non_court_chars_by_voice.get("SUPREME_COURT_QUOTE", 0)
    if (
        f.total_chars > 0
        and sc_chars / f.total_chars >= 0.70
        and f.court_voice_ratio < 0.30
    ):
        return SectionVerdict(
            "PRECEDENT_CITATION", 0.85, "supreme-court-dominant"
        )

    # Other-court quote dominance signals the court is quoting its own prior
    # order or another High Court order. Treated as REASONING (adoption of
    # prior reasoning) rather than PRECEDENT_CITATION because in KHC writs
    # these passages are almost always followed by an endorsement clause.
    # P13 of Venkateshulu is the canonical example: KHC quotes its 2015
    # order at length, then proceeds to use that order to reject the
    # petitioner's resurvey argument.
    oc_chars = f.non_court_chars_by_voice.get("OTHER_COURT_QUOTE", 0)
    if (
        f.total_chars > 0
        and oc_chars / f.total_chars >= 0.70
        and f.court_voice_ratio < 0.30
    ):
        return SectionVerdict(
            "REASONING", 0.80, "this-court-prior-order-adopted"
        )

    if f.starts_with_reasoning_cue and f.court_voice_ratio >= 0.50:
        return SectionVerdict("REASONING", 0.85, "reasoning-cue")

    if (
        f.text.lstrip().startswith("In the present case")
        and f.court_voice_ratio >= 0.60
    ):
        return SectionVerdict("REASONING", 0.90, "applies-to-facts")

    if f.starts_with_facts_cue and f.court_voice_ratio >= 0.80:
        return SectionVerdict("FACTS", 0.92, "facts-cue")

    # Pure court voice with explicit endorsement / reasoning markers anywhere
    # in the paragraph. Catches paragraphs that open with neutral narrative
    # ("The second respondent has appropriately noticed ...") but conclude
    # with reasoning. Must precede the high-court-no-quotes FACTS rule
    # because otherwise endorsement paragraphs would default to FACTS.
    if (
        f.court_voice_ratio >= 0.85
        and not f.has_court_quote
        and not f.has_revisional_quote
        and not f.has_party_contention
        and _REASONING_MARKER.search(f.text)
    ):
        return SectionVerdict("REASONING", 0.80, "court-endorsement-marker")

    if (
        f.court_voice_ratio >= 0.90
        and not f.has_court_quote
        and not f.has_revisional_quote
        and not f.has_party_contention
        and not f.starts_with_reasoning_cue
        and not f.starts_with_operative_cue
    ):
        return SectionVerdict("FACTS", 0.75, "high-court-no-quotes")

    if f.has_court_quote and 0.40 <= f.court_voice_ratio < 0.70:
        return SectionVerdict("REASONING", 0.65, "reasoning-with-quote")

    return SectionVerdict("UNCERTAIN", 0.0, "no-rule-matched")


# Stage 2: LLM fallback -------------------------------------------------------


class SectionLLMClient(Protocol):
    """Minimal interface for the section LLM fallback. Real wiring uses an
    Ollama-backed adapter; tests pass a MagicMock."""

    def generate_json(self, prompt: str) -> dict[str, Any]: ...


_VALID_SECTION_CLASSES = {
    "FACTS",
    "ARGUMENTS",
    "PRECEDENT_CITATION",
    "REASONING",
    "OPERATIVE",
    "DECREE",
}


def _voice_summary(f: SectionFeatures) -> str:
    if not f.voice_spans:
        return "- 100% court voice (no quotes, no contentions detected)"
    lines: list[str] = []
    pct_court = (
        f"{f.court_voice_ratio * 100:.0f}% court voice"
        if f.total_chars
        else "100% court voice"
    )
    lines.append(f"- {pct_court}")
    for voice, chars in sorted(
        f.non_court_chars_by_voice.items(), key=lambda kv: -kv[1]
    ):
        if chars == 0:
            continue
        ratio = chars / f.total_chars if f.total_chars else 0.0
        lines.append(f"- {ratio * 100:.0f}% {voice}")
    lines.append(
        f"- decree verb in court voice: "
        f"{'yes' if f.contains_decree_verb else 'no'}"
    )
    lines.append(
        f"- operative cue at start: "
        f"{'yes' if f.starts_with_operative_cue else 'no'}"
    )
    lines.append(
        f"- reasoning cue at start: "
        f"{'yes' if f.starts_with_reasoning_cue else 'no'}"
    )
    return "\n".join(lines)


def _render_prompt(
    f: SectionFeatures,
    total_paragraphs: int,
    prev_preview: str | None,
    next_preview: str | None,
) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    body = template.split("---", 2)[-1].lstrip()
    return (
        body.replace("{paragraph_index}", str(f.paragraph_index))
        .replace("{total_paragraphs}", str(total_paragraphs))
        .replace("{is_last}", "yes" if f.is_last_body_paragraph else "no")
        .replace("{voice_summary}", _voice_summary(f))
        .replace("{prev_preview}", prev_preview or "(none — first body paragraph)")
        .replace("{next_preview}", next_preview or "(none — last body paragraph)")
        .replace("{paragraph_text}", f.text)
    )


def _llm_classify(
    f: SectionFeatures,
    *,
    total_paragraphs: int,
    prev_preview: str | None,
    next_preview: str | None,
    client: SectionLLMClient,
) -> tuple[str, str, str]:
    """Call the LLM. Returns (section_class, prompt_sha, model_id).

    Raises if the LLM call fails for any reason. Caller handles fallback.
    """
    prompt = _render_prompt(f, total_paragraphs, prev_preview, next_preview)
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    raw = client.generate_json(prompt)
    if not isinstance(raw, dict):
        raise ValueError(f"LLM returned non-dict: {type(raw).__name__}")
    section_class = raw.get("section_class")
    if section_class not in _VALID_SECTION_CLASSES:
        raise ValueError(f"LLM returned invalid section_class: {section_class!r}")
    model_id = getattr(client, "model_id", "unknown")
    return section_class, prompt_sha, model_id


# Pipeline orchestrator -------------------------------------------------------


def classify_with_fallback(
    f: SectionFeatures,
    *,
    total_paragraphs: int,
    prev_preview: str | None,
    next_preview: str | None,
    confidence_threshold: float = SECTION_CONFIDENCE_THRESHOLD,
    llm_client: SectionLLMClient | None = None,
) -> tuple[SectionVerdict, SectionVerdict, Optional[tuple[str, str]]]:
    """Run both stages. Return (final_verdict, deterministic_verdict, llm_meta).

    `llm_meta` is `(prompt_sha, model_id)` when the LLM path ran, else None.
    """
    deterministic = classify_deterministic(f)
    if deterministic.confidence >= confidence_threshold:
        return deterministic, deterministic, None

    if llm_client is None:
        return (
            SectionVerdict(
                deterministic.section_class,
                deterministic.confidence,
                deterministic.reason,
                "DETERMINISTIC_LOW_CONFIDENCE",
            ),
            deterministic,
            None,
        )

    try:
        llm_class, prompt_sha, model_id = _llm_classify(
            f,
            total_paragraphs=total_paragraphs,
            prev_preview=prev_preview,
            next_preview=next_preview,
            client=llm_client,
        )
    except Exception as exc:
        _LOG.warning(
            "section_llm_fallback_failed",
            paragraph_index=f.paragraph_index,
            deterministic_class=deterministic.section_class,
            error=str(exc),
        )
        return (
            SectionVerdict(
                deterministic.section_class,
                deterministic.confidence,
                deterministic.reason,
                "DETERMINISTIC_LOW_CONFIDENCE",
            ),
            deterministic,
            None,
        )

    final = SectionVerdict(
        llm_class,  # type: ignore[arg-type]
        LLM_FALLBACK_CONFIDENCE,
        f"llm-fallback (deterministic={deterministic.section_class}/"
        f"{deterministic.reason})",
        "LLM_FALLBACK",
    )
    return final, deterministic, (prompt_sha, model_id)


_SYSTEM_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id=uuid4(), designation=None)


def _paragraph_uuid(case_number: str, paragraph_index: int) -> UUID:
    return uuid5(NAMESPACE_OID, f"{case_number}/p{paragraph_index}")


def _record_audit(
    case_number: str,
    paragraph_index: int,
    final: SectionVerdict,
    deterministic: SectionVerdict,
    llm_meta: tuple[str, str] | None,
) -> None:
    para_uuid = _paragraph_uuid(case_number, paragraph_index)
    payload: dict[str, Any] = {
        "stage": "section_classification",
        "case_number": case_number,
        "paragraph_index": paragraph_index,
        "section_class": final.section_class,
        "confidence": final.confidence,
        "reason": final.reason,
        "final_stage": final.stage,
        "deterministic_class": deterministic.section_class,
        "deterministic_confidence": deterministic.confidence,
        "deterministic_reason": deterministic.reason,
    }
    prompt_sha: str | None = None
    model_id: str | None = None
    if llm_meta is not None:
        prompt_sha, model_id = llm_meta
        payload["llm_prompt_sha"] = prompt_sha
        payload["llm_model_id"] = model_id

    audit.record(
        AuditEventType.EXTRACTION_COMPLETED,
        EntityType.PARAGRAPH,
        para_uuid,
        _SYSTEM_ACTOR,
        payload,
        prompt_sha=prompt_sha,
        model_id=model_id,
        temperature=0.0 if prompt_sha is not None else None,
        paragraph_ids=[para_uuid] if prompt_sha is not None else None,
    )


def classify_paragraphs(
    paragraphs: list[GroundedParagraph],
    *,
    llm_client: SectionLLMClient | None = None,
    confidence_threshold: float = SECTION_CONFIDENCE_THRESHOLD,
    case_number: str | None = None,
) -> list[tuple[GroundedParagraph, SectionVerdict]]:
    """Classify each paragraph and overwrite section_class on successful calls.

    UNCERTAIN paragraphs retain their input section_class (typically the FACTS
    placeholder set by B1's segmenter). Callers must check verdict.section_class
    against UNCERTAIN before treating the paragraph as classified.
    """
    out: list[tuple[GroundedParagraph, SectionVerdict]] = []
    n = len(paragraphs)
    for i, p in enumerate(paragraphs):
        prev_preview = paragraphs[i - 1].text[:200] if i > 0 else None
        next_preview = paragraphs[i + 1].text[:200] if i + 1 < n else None
        f = build_features(p, is_last_body_paragraph=(i == n - 1))
        final, deterministic, llm_meta = classify_with_fallback(
            f,
            total_paragraphs=n,
            prev_preview=prev_preview,
            next_preview=next_preview,
            confidence_threshold=confidence_threshold,
            llm_client=llm_client,
        )
        if final.section_class != "UNCERTAIN":
            classified = p.model_copy(
                update={"section_class": final.section_class}
            )
        else:
            classified = p
        if case_number is not None:
            _record_audit(
                case_number, p.paragraph_index, final, deterministic, llm_meta
            )
        out.append((classified, final))
    return out


__all__ = [
    "SECTION_CONFIDENCE_THRESHOLD",
    "LLM_FALLBACK_CONFIDENCE",
    "SectionFeatures",
    "SectionLLMClient",
    "SectionVerdict",
    "build_features",
    "classify_deterministic",
    "classify_paragraphs",
    "classify_with_fallback",
]


# `json` is imported for prompt rendering future-proofing; touch the symbol so
# `ruff` does not flag the import as unused. The LLM contract may grow to ship
# the voice spans as a JSON blob alongside the rendered summary.
_ = json
