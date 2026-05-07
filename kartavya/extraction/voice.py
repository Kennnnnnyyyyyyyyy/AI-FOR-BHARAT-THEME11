"""Voice tagger. Phase B3.

Walks each paragraph and identifies non-COURT spans. Output feeds two
downstream consumers:

  * Phase B2 section classifier uses voice density as a feature
    (paragraphs that are >50% non-court are PRECEDENT_CITATION or
    REASONING-with-quote; OPERATIVE paragraphs must be >=80% COURT).
  * Phase B4 directive parser refuses extraction from any non-COURT span,
    which structurally rules out the phantom-directive failure mode that
    started this whole architectural thread (paragraph 21 of Venkateshulu
    is a revisional-authority quote; directives extracted from it were
    the source of the original four phantom action cards).

Four passes, in order. Each pass identifies one class of non-court span;
later passes do not tag inside spans already tagged by earlier passes.

  Pass 1: block quotes ("<introducer>: \\u201c...\\u201d"), classified by
          attribution from the 200-char preamble.
  Pass 2: statutory paraphrase ("Section <N> of the <Act> stipulates
          that ...").
  Pass 3: party contention (paragraphs whose first sentence is a
          contention opener).
  Pass 4: sort by char_start, verify no overlap, emit.

No LLM. Pure pattern matching. The introducer phrases, attribution
clauses, and statutory-paraphrase verbs are stable enough across
Karnataka High Court judgments to handle deterministically.

v0.1 limitations (documented in CLAUDE.md changelog):
  * Nested quotes are not handled. Outer span covers everything inside;
    B4 refuses extraction from the entire region anyway.
  * Unattributed block quotes default to OTHER_COURT_QUOTE rather than
    COURT. Conservative by design: a non-court tag suppresses a real
    directive (false negative, recoverable in human review); a court
    tag would let through a phantom directive (false positive, the
    failure mode this whole layer exists to prevent).
  * Statutory-paraphrase pattern is restricted to "Section <N> of the
    <Act> stipulates|states|provides|prescribes|mandates|requires|
    empowers|defines that". Other paraphrase verbs are not matched.
  * Contention paragraphs that contain an inner block quote yield zero
    PARTY_CONTENTION spans rather than a wrap-around span list.
    Acceptable for the canonical cases at hand.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from kartavya.schemas.parsed_judgment import GroundedParagraph
from kartavya.schemas.voice import Voice, VoiceSpan

_QUOTE_OPEN_CHARS = "“\""
_QUOTE_CLOSE_BY_OPEN: dict[str, str] = {"“": "”", '"': '"'}

_BLOCK_INTRODUCER = re.compile(
    r"(?:reads|read|stated|states|observed|observes|held|holds|reproduced|"
    r"extracted|noted|notes|is|are|was|were)"
    r"\s+(?:as\s+under|hereunder|thus|as\s+follows)\s*:",
    re.IGNORECASE,
)

_STATUTE_PARAPHRASE = re.compile(
    r"Section\s+\S+?\s+of\s+the\s+[A-Z][\w\s\-]*?\b(?:Act|Rules|Regulations)"
    r"[^.]*?\b(?:stipulates|states|provides|prescribes|mandates|requires|"
    r"empowers|defines)\s+that\b",
    re.IGNORECASE,
)

_CONTENTION_OPENERS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*It\s+is\s+(?:the\s+)?(?:primary\s+)?contention"
        r"\s+of\s+the\s+(?:petitioner|respondent|appellant)",
        r"^\s*The\s+learned\s+counsel\s+for\s+the"
        r"\s+(?:petitioner|respondent|appellant)"
        r"\s+(?:submits|contends|argues)",
        r"^\s*Per\s+contra,?\s+the\s+learned"
        r"\s+(?:Additional\s+Government\s+Advocate|counsel|Government\s+Pleader)",
        r"^\s*The\s+learned\s+Additional\s+Government\s+Advocate"
        r"\s+(?:submits|contends|justifies)",
    )
]

_ATTRIBUTION_SUPREME_COURT = re.compile(r"\bSupreme\s+Court\b", re.IGNORECASE)
_ATTRIBUTION_THIS_COURT = re.compile(
    r"\b(?:this\s+Court|High\s+Court)\b", re.IGNORECASE
)
_ATTRIBUTION_REVISIONAL = re.compile(
    r"\b(?:revisional\s+authority|revisional\s+order"
    r"|second\s+respondent.{0,80}revision)\b",
    re.IGNORECASE,
)

ATTRIBUTION_LOOKBACK = 200


def tag_voice_spans(text: str) -> list[VoiceSpan]:
    """Return non-overlapping VoiceSpans covering the non-COURT regions of `text`.

    Empty list means the entire paragraph is COURT voice (the common case).
    """
    spans: list[VoiceSpan] = []
    spans.extend(_pass_block_quotes(text))
    spans.extend(_pass_statutory_paraphrase(text, existing=spans))
    spans.extend(_pass_party_contention(text, existing=spans))
    return _normalize(spans)


def annotate_paragraph(p: GroundedParagraph) -> GroundedParagraph:
    """Return a copy of `p` with voice_spans populated by the tagger."""
    return p.model_copy(update={"voice_spans": tag_voice_spans(p.text)})


def annotate_paragraphs(ps: Iterable[GroundedParagraph]) -> list[GroundedParagraph]:
    return [annotate_paragraph(p) for p in ps]


# Pass 1 ----------------------------------------------------------------------


def _pass_block_quotes(text: str) -> list[VoiceSpan]:
    """Find block quotes following an introducer.

    Curly quotes (U+201C / U+201D) have distinct open/close characters, so the
    span runs from the open to the matching close. Straight quotes (U+0022)
    are ambiguous — Indian Kanoon's PDF rendering uses straight quotes
    throughout, including for inner paraphrase tokens like 'first renewal'
    embedded inside a Supreme Court block quote. For straight quotes we treat
    the first quote after the introducer as the open and the *last* quote
    before the next introducer (or end of text) as the close, so embedded
    pairs are absorbed by the outer span.
    """
    introducers = list(_BLOCK_INTRODUCER.finditer(text))
    out: list[VoiceSpan] = []
    for i, m in enumerate(introducers):
        intro_end = m.end()
        bound = introducers[i + 1].start() if i + 1 < len(introducers) else len(text)
        open_idx = _find_next_any(text, _QUOTE_OPEN_CHARS, intro_end)
        if open_idx == -1 or open_idx >= bound:
            continue
        open_char = text[open_idx]
        if open_char == '"':
            close_idx = _last_index(text, '"', open_idx + 1, bound)
            if close_idx == -1:
                continue
        else:
            close_char = _QUOTE_CLOSE_BY_OPEN[open_char]
            close_idx = text.find(close_char, open_idx + 1, bound)
            if close_idx == -1:
                continue
        voice = _classify_attribution(text, m.start())
        out.append(
            VoiceSpan(char_start=open_idx, char_end=close_idx + 1, voice=voice)
        )
    return out


def _find_next_any(text: str, chars: str, start: int) -> int:
    candidates = [text.find(c, start) for c in chars]
    candidates = [i for i in candidates if i != -1]
    return min(candidates) if candidates else -1


def _last_index(text: str, ch: str, start: int, end: int) -> int:
    last = -1
    i = start
    while i < end:
        j = text.find(ch, i, end)
        if j == -1:
            break
        last = j
        i = j + 1
    return last


def _classify_attribution(text: str, introducer_start: int) -> Voice:
    window_start = max(0, introducer_start - ATTRIBUTION_LOOKBACK)
    window = text[window_start:introducer_start]
    if _ATTRIBUTION_SUPREME_COURT.search(window):
        return "SUPREME_COURT_QUOTE"
    if _ATTRIBUTION_REVISIONAL.search(window):
        return "REVISIONAL_AUTHORITY_QUOTE"
    if _ATTRIBUTION_THIS_COURT.search(window):
        return "OTHER_COURT_QUOTE"
    return "OTHER_COURT_QUOTE"


# Pass 2 ----------------------------------------------------------------------


def _pass_statutory_paraphrase(
    text: str, *, existing: list[VoiceSpan]
) -> list[VoiceSpan]:
    out: list[VoiceSpan] = []
    for m in _STATUTE_PARAPHRASE.finditer(text):
        s = m.start()
        e = _end_of_sentence(text, m.end())
        if _overlaps(s, e, existing):
            continue
        out.append(VoiceSpan(char_start=s, char_end=e, voice="STATUTE_QUOTE"))
    return out


def _end_of_sentence(text: str, from_idx: int) -> int:
    i = from_idx
    while i < len(text):
        if text[i] == "." and (i + 1 == len(text) or text[i + 1] in " \n\t"):
            return i + 1
        i += 1
    return len(text)


def _overlaps(start: int, end: int, existing: list[VoiceSpan]) -> bool:
    for s in existing:
        if not (end <= s.char_start or start >= s.char_end):
            return True
    return False


# Pass 3 ----------------------------------------------------------------------


def _pass_party_contention(
    text: str, *, existing: list[VoiceSpan]
) -> list[VoiceSpan]:
    for opener in _CONTENTION_OPENERS:
        m = opener.match(text)
        if not m:
            continue
        sentence_end = _end_of_sentence(text, m.end())
        if sentence_end >= len(text):
            return []
        start = sentence_end
        while start < len(text) and text[start] in " \n\t":
            start += 1
        if start >= len(text):
            return []
        end = len(text)
        while end > start and text[end - 1] in " \n\t":
            end -= 1
        if _overlaps(start, end, existing):
            return []
        return [VoiceSpan(char_start=start, char_end=end, voice="PARTY_CONTENTION")]
    return []


# Pass 4 ----------------------------------------------------------------------


def _normalize(spans: list[VoiceSpan]) -> list[VoiceSpan]:
    spans = sorted(spans, key=lambda s: s.char_start)
    for a, b in zip(spans, spans[1:]):
        if a.char_end > b.char_start:
            raise ValueError(f"voice spans overlap: {a} and {b}")
    return spans
