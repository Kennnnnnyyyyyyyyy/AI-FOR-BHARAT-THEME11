"""Paragraph segmentation. Phase B1.

Reads a Karnataka High Court judgment PDF and returns a list of
`GroundedParagraph` keyed on the judgment's own `\\d+\\.` paragraph
numbering. Page boundaries are stitched, running headers and footers are
stripped, page-number stamps are removed, and the end-of-document
signature block is dropped from the last paragraph.

Phase B1 outputs paragraphs with `section_class="FACTS"` as a placeholder.
The Phase B2 section classifier overwrites this. `voice_spans` is empty
on every paragraph; the Phase B3 voice tagger populates it.

What is Venkateshulu-specific and may need generalization:
  * The body-start marker. Karnataka High Court writ judgments use
    "ORDER WAS PRONOUNCED AS UNDER" or "JUDGMENT" or "this writ petition
    is filed". The default marker is "ORDER WAS PRONOUNCED AS UNDER" with
    a fallback to the first `\\n1.\\s+[A-Z]` heading anywhere in the text.
    Other order types may use "ORDER" or "OPERATIVE PORTION" markers.
  * The signature-block tail patterns ("SD/-", "(NAME) JUDGE",
    "BS/Vmb/ND" initials) are KHC-specific; other courts use different
    conventions.

Running headers are auto-detected by frequency: any line that appears on
every page is treated as a running header and stripped. This avoids
hard-coding the literal "Sri V Venkateshulu vs The Secretary on 17 April,
2026" string the brief used.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber  # type: ignore[import-untyped]

from kartavya.schemas.parsed_judgment import GroundedParagraph


class SegmentationError(Exception):
    """Raised when segmentation cannot produce a contiguous 1..N paragraph list."""


_HEADING_RE = re.compile(r"\n(\d+)\.\s+(?=[A-Z\"])")
_PAGE_NUM_STAMP_RE = re.compile(r"^\s*-\s*\d+\s*-\s*$", re.MULTILINE)
_RUNNING_FOOTER_RE = re.compile(r"^\s*Indian Kanoon.*$", re.MULTILINE)
_DEFAULT_BODY_MARKERS = (
    "ORDER WAS PRONOUNCED AS UNDER:",
    "ORDER WAS PRONOUNCED AS UNDER",
    "ORDER PRONOUNCED",
    "JUDGMENT",
)


def segment_judgment(
    pdf_path: Path,
    *,
    running_header: str | None = None,
    body_start_markers: tuple[str, ...] = _DEFAULT_BODY_MARKERS,
) -> list[GroundedParagraph]:
    """Segment a judgment PDF into numbered `GroundedParagraph` objects.

    `running_header` overrides the auto-detected per-page running header.
    `body_start_markers` is tried in order; the first marker found
    determines where the cause-title block ends and the body begins. If
    none match, the segmenter falls back to the first `\\n1.\\s+[A-Z]`
    heading anywhere in the text.
    """
    text = _extract_clean_text(pdf_path, running_header=running_header)
    body = _slice_body(text, body_start_markers=body_start_markers)
    return _split_into_paragraphs(body)


# ---- Page-level extraction --------------------------------------------------


def _extract_clean_text(
    pdf_path: Path,
    *,
    running_header: str | None,
) -> str:
    page_texts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_texts.append(page.extract_text(layout=False) or "")
    detected_header = running_header or _detect_running_header(page_texts)
    cleaned_pages = [
        _clean_page(raw, running_header=detected_header) for raw in page_texts
    ]
    return "\n".join(cleaned_pages)


def _detect_running_header(page_texts: list[str]) -> str | None:
    """A line that appears on every page is the running header.

    Returns the longest such line if any exists, else None. The longest
    rule disambiguates when both a header line and a short noise line
    happen to repeat across pages.
    """
    if not page_texts:
        return None
    per_page_lines: list[set[str]] = []
    for text in page_texts:
        lines = {ln.strip() for ln in text.splitlines() if ln.strip()}
        per_page_lines.append(lines)
    common = set.intersection(*per_page_lines) if per_page_lines else set()
    if not common:
        return None
    candidates = [c for c in common if len(c) >= 20]  # avoid short noise
    if not candidates:
        return None
    return max(candidates, key=len)


def _clean_page(raw: str, *, running_header: str | None) -> str:
    if running_header:
        # Strip every line that contains the header substring (handles cases
        # where the header is duplicated on the first page).
        raw = re.sub(
            r"^.*" + re.escape(running_header) + r".*$",
            "",
            raw,
            flags=re.MULTILINE,
        )
    raw = _RUNNING_FOOTER_RE.sub("", raw)
    raw = _PAGE_NUM_STAMP_RE.sub("", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


# ---- Body slicing -----------------------------------------------------------


def _slice_body(text: str, *, body_start_markers: tuple[str, ...]) -> str:
    for marker in body_start_markers:
        idx = text.find(marker)
        if idx != -1:
            return text[idx + len(marker):]
    m = re.search(r"\n1\.\s+[A-Z]", text)
    if m is None:
        raise SegmentationError(
            "could not locate body start (no marker, no '1.' heading)"
        )
    return text[m.start():]


# ---- Paragraph splitting ----------------------------------------------------


def _split_into_paragraphs(body: str) -> list[GroundedParagraph]:
    body = "\n" + body  # ensure heading regex matches paragraph 1
    raw_matches = list(_HEADING_RE.finditer(body))
    if not raw_matches:
        raise SegmentationError("no numbered paragraphs found in body")

    # The heading regex over-matches inside block quotes that quote other
    # judgments by paragraph number ("39. We make it clear..." inside a
    # supreme court quote, "46.", "47." inside a revisional authority
    # quote, etc.). Real paragraph numbers are strictly monotonically
    # increasing by 1. Anything that breaks that sequence is a quote
    # internal heading and is folded back into its enclosing paragraph.
    accepted_matches: list[tuple[int, int, int]] = []
    # Each tuple: (heading_number, start_offset, end_offset_of_heading_match)
    expected = 1
    for m in raw_matches:
        idx = int(m.group(1))
        if idx == expected:
            accepted_matches.append((idx, m.start(), m.end()))
            expected += 1
        # else: spurious heading inside a quoted block; ignore. The text
        # under that heading stays inside the previous accepted paragraph
        # because we delimit by the next accepted heading.

    if not accepted_matches:
        raise SegmentationError(
            "no monotonically increasing paragraph headings found"
        )

    paragraphs: list[GroundedParagraph] = []
    for i, (idx, _start, head_end) in enumerate(accepted_matches):
        start = head_end
        if i + 1 < len(accepted_matches):
            end = accepted_matches[i + 1][1]
        else:
            end = len(body)
        text = body[start:end].strip()
        if i == len(accepted_matches) - 1:
            text = _strip_signature_lines_from_last_paragraph(text)
        text = _normalize_whitespace(text)
        paragraphs.append(
            GroundedParagraph(
                paragraph_index=idx,
                text=text,
                section_class="FACTS",  # B2 overwrites
                voice_spans=[],
            )
        )

    _assert_contiguous(paragraphs)
    return paragraphs


_SIGNATURE_NAME_LINE_RE = re.compile(
    r"^\([A-Z][A-Z\.\s]+\)\s+(CHIEF\s+JUSTICE|JUDGE)", re.IGNORECASE
)
_INITIALS_LINE_RE = re.compile(
    r"^[A-Za-z]{2,4}/[A-Za-z]{2,4}/[A-Za-z]{1,4}\s*$"
)


def _strip_signature_lines_from_last_paragraph(text: str) -> str:
    """Truncate the last paragraph at the first signature-block line.

    Signature lines on a Karnataka High Court order:
      * `SD/-` (or `Sd/-`) standing alone or starting a line
      * `(NAME) CHIEF JUSTICE` / `(NAME) JUDGE` patterns, possibly with
        further `SD/-` text trailing
      * Initials block like `BS/Vmb/ND` (court file initials)
    """
    lines = text.splitlines()
    cleaned: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.upper().startswith("SD/-"):
            break
        if _SIGNATURE_NAME_LINE_RE.match(s):
            break
        if _INITIALS_LINE_RE.match(s):
            break
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


def _normalize_whitespace(text: str) -> str:
    """Collapse all whitespace including newlines to single spaces.

    Indian Kanoon's pdfplumber output line-wraps prose mid-sentence, so
    preserving newlines fragments the text into apparent multi-line
    structure that reflects PDF layout, not semantic structure. Block
    quotes are recovered by B3 from the `"..."` markers that the original
    judgment uses, not from newline shape.
    """
    return re.sub(r"\s+", " ", text).strip()


def _assert_contiguous(paragraphs: list[GroundedParagraph]) -> None:
    actual = [p.paragraph_index for p in paragraphs]
    expected = list(range(1, len(paragraphs) + 1))
    if actual == expected:
        return
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    raise SegmentationError(
        f"paragraph numbering not contiguous. expected {expected}, got "
        f"{actual}. missing={missing} extra={extra}"
    )
