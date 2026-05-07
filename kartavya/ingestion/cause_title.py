"""Cause-title parser. Phase B6.

Reads a Karnataka High Court judgment PDF and extracts case-level metadata
plus the typed `Respondent` list from the cause title block. Deterministic.
No LLM. Returns a `ParsedCauseTitle` named tuple.

This is v0.1 calibrated to the Venkateshulu PDF and KHC writ-petition format.
What is Venkateshulu-specific and may need generalization for other cases:
  * The bbox of the digital-signature block (page 1 left-margin column,
    x0 around 108 to 200 and top around 480 to 600 in the Indian Kanoon
    rendering of this judgment). Other digital signatures live at other
    positions; the bbox should ideally be detected by content match
    ("Digitally signed by") plus geometry rather than hard-coded.
  * The end-marker for the cause title block ("THIS WRIT PETITION IS FILED
    UNDER" or "ORDER WAS PRONOUNCED AS UNDER"). Other order types use
    different phrasings.
  * The known-organization phrase set ("GOVERNMENT OF INDIA",
    "GOVERNMENT OF KARNATAKA", "STATE OF KARNATAKA") is sufficient for
    Karnataka-state writs against the Union and the State; broader use
    needs a tagged corpus.

The §9 catalogue type `CaseMetadata` (a Pydantic model) is unrelated to
this module's `ParsedCauseTitle`. The cause-title parser produces a
narrow tuple; downstream code constructs `CaseMetadata` (Phase A type) or
`ParsedJudgment` (Phase A type) from it.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import NamedTuple

import pdfplumber  # type: ignore[import-untyped]

from kartavya.schemas.case import Respondent


class CauseTitleParseError(Exception):
    """Raised when a required cause-title field cannot be extracted.

    The Phase A discipline (refuse rather than guess) applies: a missing
    field is fatal, never a default.
    """


class ParsedCauseTitle(NamedTuple):
    case_number: str
    court: str
    judgment_date: date
    petitioner_name: str
    respondents: list[Respondent]


_MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11,
    "DECEMBER": 12,
}

_KNOWN_ORGS = (
    "GOVERNMENT OF INDIA",
    "GOVERNMENT OF KARNATAKA",
    "STATE OF KARNATAKA",
)

# Page 1 digital-signature bbox on the Indian Kanoon rendering: words in this
# region are part of the "Digitally signed by NIRMALA DEVI Location: HIGH
# COURT OF KARNATAKA" signature block, interleaved column-wise with the
# respondent text in pdfplumber's reading order. Signature words sit at
# x0 in [108, 147]; body-text words on the same vertical lines start at
# x0 around 180 (e.g. the "2." respondent prefix). x0_max = 150 is a
# safe boundary.
_SIG_BBOX_X0_MAX = 150.0
_SIG_BBOX_TOP_MIN = 480.0
_SIG_BBOX_TOP_MAX = 600.0

_END_MARKERS = (
    "THIS WRIT PETITION IS FILED UNDER",
    "THIS PETITION IS FILED UNDER",
    "ORDER WAS PRONOUNCED AS UNDER",
)

# Patterns that pollute the respondent block when pages 2 and 3 are
# concatenated (running header, running footer, page-number stamp, and the
# advocates line that introduces respondents). Stripped before the regex
# split on respondent number prefixes.
_RUNNING_HEADER_RE = re.compile(
    r"^.*Sri V Venkateshulu vs The Secretary on 17 April, 2026.*$",
    re.MULTILINE,
)
_RUNNING_FOOTER_RE = re.compile(
    r"^.*Indian Kanoon.*$", re.MULTILINE
)
_PAGE_NUMBER_STAMP_RE = re.compile(
    r"^\s*-\s*\d+\s*-\s*$", re.MULTILINE
)
_WP_HEADER_LINE_RE = re.compile(
    r"^\s*WP No\.\s*\d+\s+of\s+\d+\s*$", re.MULTILINE
)

# Address tokens that imply a Karnataka government respondent when the
# explicit organization phrase is absent from the body. R3 in Venkateshulu
# has its designation as "Principal Secretary to Government, Commerce and
# Industries Department (MSME and Mines)" without a literal "Government of
# Karnataka" line; the address ("Vikasa Soudha, Ambedkar Road, Bengaluru")
# carries the geography.
_KARNATAKA_ADDRESS_TOKENS = (
    "VIKASA SOUDHA",
    "VIDHANA SOUDHA",
    "KHANIJA BHAVAN",
    "BENGALURU",
    "BANGALORE",
    "BELLARY",
    "DHARWAD",
    "MYSURU",
    "MYSORE",
    "MANGALURU",
    "MANGALORE",
    "HUBLI",
    "HUBBALLI",
)
_INDIA_ADDRESS_TOKENS = (
    "SHASTRI BHAVAN",
    "NEW DELHI",
    "PARLIAMENT HOUSE",
    "RAFI MARG",
)


def parse_cause_title(pdf_path: Path) -> ParsedCauseTitle:
    text = _extract_text_until_body(pdf_path)
    case_number = _extract_case_number(text)
    judgment_date = _extract_judgment_date(text)
    court = _extract_court(text)
    petitioner_name = _extract_petitioner_name(text)
    respondents = _extract_respondents(text)
    return ParsedCauseTitle(
        case_number=case_number,
        court=court,
        judgment_date=judgment_date,
        petitioner_name=petitioner_name,
        respondents=respondents,
    )


# ---- Text extraction --------------------------------------------------------


def _extract_text_until_body(pdf_path: Path) -> str:
    """Read the first three pages, drop signature-bbox words on page 1, slice
    at the first end-of-cause-title marker."""
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages[:3], start=1):
            if page_no == 1:
                parts.append(_text_without_signature_bbox(page))
            else:
                parts.append(page.extract_text(layout=False) or "")
    full = "\n".join(parts)
    for marker in _END_MARKERS:
        idx = full.find(marker)
        if idx != -1:
            return full[:idx]
    return full  # downstream parsers will raise if a field is missing


def _text_without_signature_bbox(page: object) -> str:
    """Reconstruct page text from words that are NOT in the signature bbox.

    Words are sorted by (top, x0) so the reconstructed text follows the
    visual reading order; line breaks are inserted whenever the `top`
    value changes meaningfully (more than 3 points).
    """
    words = page.extract_words()  # type: ignore[attr-defined]
    keep: list[dict] = []
    for w in words:
        x0 = float(w["x0"])
        top = float(w["top"])
        in_sig_x = x0 < _SIG_BBOX_X0_MAX
        in_sig_y = _SIG_BBOX_TOP_MIN < top < _SIG_BBOX_TOP_MAX
        if in_sig_x and in_sig_y:
            continue
        keep.append(w)
    keep.sort(key=lambda w: (round(float(w["top"]), 1), float(w["x0"])))
    lines: list[list[str]] = []
    current_top: float | None = None
    for w in keep:
        top = round(float(w["top"]), 1)
        if current_top is None or abs(top - current_top) > 3.0:
            lines.append([w["text"]])
            current_top = top
        else:
            lines[-1].append(w["text"])
    return "\n".join(" ".join(line) for line in lines)


# ---- Field extractors -------------------------------------------------------


def _extract_case_number(text: str) -> str:
    m = re.search(
        r"WRIT\s+PETITION\s+NO\.?\s+(\d+)\s+OF\s+(\d+)", text, re.IGNORECASE
    )
    if m:
        return f"WP {m.group(1)}/{m.group(2)}"
    m = re.search(
        r"W\.?P\.?\s+No\.?\s*(\d+)\s*/\s*(\d+)", text, re.IGNORECASE
    )
    if m:
        return f"WP {m.group(1)}/{m.group(2)}"
    raise CauseTitleParseError("could not extract case number")


def _extract_judgment_date(text: str) -> date:
    m = re.search(
        r"DATED\s+THIS\s+THE\s+(\d{1,2})(?:ST|ND|RD|TH)?\s+DAY\s+OF\s+(\w+),?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        raise CauseTitleParseError("could not extract judgment date")
    day = int(m.group(1))
    month = _MONTHS.get(m.group(2).upper())
    year = int(m.group(3))
    if month is None:
        raise CauseTitleParseError(f"unknown month: {m.group(2)}")
    return date(year, month, day)


def _extract_court(text: str) -> str:
    m = re.search(
        r"IN\s+THE\s+HIGH\s+COURT\s+OF\s+KARNATAKA\s+AT\s+(\w+)",
        text,
        re.IGNORECASE,
    )
    if m:
        return f"High Court of Karnataka at {m.group(1).title()}"
    raise CauseTitleParseError("could not extract court")


def _extract_petitioner_name(text: str) -> str:
    between_idx = text.find("BETWEEN:")
    petitioner_idx = text.find("...PETITIONER")
    if between_idx == -1 or petitioner_idx == -1 or petitioner_idx < between_idx:
        raise CauseTitleParseError("could not locate petitioner block")
    block = text[between_idx + len("BETWEEN:"):petitioner_idx]
    skip_prefixes = (
        "S/O", "D/O", "W/O", "AGED", "RESIDING", "PLOT", "COLONY",
        "VILLAGE", "ROAD", "STREET", "FLAT", "FLOOR",
    )
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        if re.search(r"\b(AGED|RESIDING|PLOT|COLONY)\b", line):
            continue
        return _to_title_case_with_honorifics(line)
    raise CauseTitleParseError("could not extract petitioner name")


_ROMAN_RE = re.compile(r"^[IVX]+$")


def _to_title_case_with_honorifics(s: str) -> str:
    parts = s.split()
    out: list[str] = []
    for p in parts:
        # Bare initial like "V." stays uppercase, dot preserved.
        if re.match(r"^[A-Z]\.$", p):
            out.append(p)
            continue
        # Roman numerals like "II", "III", "IV" stay uppercase.
        upper = p.upper().rstrip(".")
        if _ROMAN_RE.match(upper) and len(upper) <= 4:
            out.append(upper + ("." if p.endswith(".") else ""))
            continue
        # Honorifics: title-case, do not invent a dot the source did not have.
        if upper in {"SRI", "SMT", "MR", "MS", "MRS", "DR"}:
            had_dot = p.endswith(".")
            out.append(upper.title() + ("." if had_dot else ""))
            continue
        # Compound initial like "V.MAREPPA" or "C.M." preserves dots.
        if "." in p:
            tokens = p.split(".")
            rebuilt = ".".join(t.title() if t else "" for t in tokens)
            out.append(rebuilt)
            continue
        out.append(p.title())
    return " ".join(out)


def _extract_respondents(text: str) -> list[Respondent]:
    petitioner_idx = text.find("...PETITIONER")
    if petitioner_idx == -1:
        raise CauseTitleParseError("could not locate petitioner marker")
    rest = text[petitioner_idx:]
    and_idx = rest.find("AND:")
    resp_end_idx = rest.find("...RESPONDENTS")
    if and_idx == -1 or resp_end_idx == -1:
        raise CauseTitleParseError("could not locate respondent block")
    block = rest[and_idx + len("AND:"):resp_end_idx]

    # Strip page-spanning noise that pdfplumber's per-page concatenation
    # leaves inside the respondent block (running header, running footer,
    # page-number stamp, WP header line).
    block = _RUNNING_HEADER_RE.sub("", block)
    block = _RUNNING_FOOTER_RE.sub("", block)
    block = _PAGE_NUMBER_STAMP_RE.sub("", block)
    block = _WP_HEADER_LINE_RE.sub("", block)
    block = re.sub(r"\n{3,}", "\n\n", block)

    splits = re.split(r"\n\s*(\d+)\.\s+", "\n" + block)
    # splits = ['', '1', 'r1 body', '2', 'r2 body', ...]
    respondents: list[Respondent] = []
    for i in range(1, len(splits), 2):
        n = int(splits[i])
        body = splits[i + 1] if i + 1 < len(splits) else ""
        respondents.append(_parse_one_respondent(n, body))
    if not respondents:
        raise CauseTitleParseError("no respondents found")
    return respondents


# Lines that look like address tail rather than role designation.
_ADDRESS_LINE_RE = re.compile(
    r"\d{6}\b"  # 6-digit postal code anywhere on the line
    r"|\bROOM\b|\bROAD\b|\bSTREET\b|\bFLOOR\b|\bWING\b"
    r"|\bBHAVAN\b|\bSOUDHA\b|\bVEEDHI\b|\bNILAYA\b"
    r"|\bBENGALURU\b|\bNEW\s+DELHI\b|\bBELLARY\b|\bDHARWAD\b|\bMUMBAI\b"
    r"|\bOPPOSITE\s+\b|\bHALL\b",
    re.IGNORECASE,
)


def _parse_one_respondent(n: int, body: str) -> Respondent:
    """Split the respondent block into designation, organization, address.

    Strategy:
      * The first line is always the role title (e.g. "THE PRINCIPAL SECRETARY").
      * Subsequent lines that match a known organization phrase are the
        organization, in priority order. The first matching organization wins.
      * Any line that contains an address marker (postal code, ROAD, etc.) is
        an address line.
      * All other non-address, non-organization lines are joined into the
        designation alongside the first line. This is what produces the
        Phase A stub designation "Principal Secretary to Government,
        Commerce and Industries Department (MSME and Mines)" rather than
        just "Principal Secretary".
    """
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        raise CauseTitleParseError(f"empty respondent body for R{n}")

    designation_lines: list[str] = [lines[0]]
    organization = ""
    address_parts: list[str] = []
    for ln in lines[1:]:
        ln_upper = ln.upper()
        matched_org = next(
            (org for org in _KNOWN_ORGS if org in ln_upper), None
        )
        if matched_org and not organization:
            organization = matched_org.title().replace("Of", "of")
            continue
        if _ADDRESS_LINE_RE.search(ln):
            address_parts.append(ln)
            continue
        designation_lines.append(ln)

    if not organization:
        # Fallback: infer from address tokens. Karnataka secretariat
        # buildings (Vikasa Soudha, Khanija Bhavan) and Karnataka cities
        # imply Government of Karnataka; Shastri Bhavan / New Delhi imply
        # Government of India. Documented as a v0.1 heuristic in
        # CLAUDE.md.
        address_text = " ".join(address_parts).upper()
        if any(t in address_text for t in _KARNATAKA_ADDRESS_TOKENS):
            organization = "Government of Karnataka"
        elif any(t in address_text for t in _INDIA_ADDRESS_TOKENS):
            organization = "Government of India"
        else:
            organization = "UNRESOLVED"

    designation_text = _join_designation_lines(designation_lines)
    designation_text = _designation_post_clean(designation_text)
    return Respondent(
        respondent_no=n,
        designation=designation_text,
        organization=organization,
        address=", ".join(address_parts) if address_parts else None,
    )


# Prepositions always continue the preceding line with a space.
_PREPOSITION_PREFIXES = ("TO ", "OF ", "FOR ", "AT ", "ON ", "IN ")

# Department/division/section nouns continue ONLY if the preceding piece is
# a noun-phrase fragment awaiting completion: it does not end with a closed
# parenthetical AND it does not end in a job-title noun. "Commerce and
# Industries" + "DEPARTMENT (MSME AND MINES)" joins with a space (fragment);
# "Director (Mines)" + "DEPARTMENT OF MINES AND GEOLOGY" joins with a comma
# (parenthetical-complete); "Senior Geologist" + "DEPARTMENT OF MINES AND
# GEOLOGY" joins with a comma (job-title-complete).
_DEPARTMENT_PREFIXES = (
    "DEPARTMENT", "DIVISION", "SECTION", "BRANCH", "OFFICE",
)
_JOB_TITLE_TAILS = (
    "Secretary", "Director", "Officer", "Engineer", "Geologist", "Inspector",
    "Commissioner", "Collector", "Pleader", "Advocate", "Judge", "Justice",
    "Manager", "Superintendent", "Registrar", "Auditor",
)


def _is_complete_role_title(piece: str) -> bool:
    stripped = piece.rstrip()
    if stripped.endswith(")"):
        return True
    if not stripped:
        return False
    last_word = stripped.split()[-1]
    return last_word in _JOB_TITLE_TAILS


def _join_designation_lines(lines: list[str]) -> str:
    """Concatenate respondent designation lines into one designation string.

    Joining rule:
      * A line starting with a preposition ("TO ", "OF ", "FOR ", ...) is
        always joined to the previous piece with a space.
      * A line starting with a department-noun ("DEPARTMENT", "DIVISION",
        "SECTION", "BRANCH", "OFFICE") joins with a space if the previous
        piece is incomplete (does not end with a closed parenthetical),
        and with a comma otherwise.
      * Any other line opens a new comma-separated piece.
    """
    if not lines:
        return ""
    pieces: list[str] = [_to_title_case_with_honorifics(lines[0])]
    for raw in lines[1:]:
        upper = raw.upper().lstrip()
        if any(upper.startswith(p) for p in _PREPOSITION_PREFIXES):
            pieces[-1] = pieces[-1] + " " + _to_title_case_with_honorifics(raw)
            continue
        if any(upper.startswith(p) for p in _DEPARTMENT_PREFIXES):
            if not _is_complete_role_title(pieces[-1]):
                pieces[-1] = pieces[-1] + " " + _to_title_case_with_honorifics(raw)
                continue
        pieces.append(_to_title_case_with_honorifics(raw))
    return ", ".join(pieces)


def _designation_post_clean(s: str) -> str:
    """Cosmetic clean-ups on a concatenated designation string.

    "The Principal Secretary, To Government, Commerce And Industries
    Department (Msme And Mines)" becomes
    "Principal Secretary to Government, Commerce and Industries Department
    (MSME and Mines)".
    """
    # Drop a leading "The ".
    s = re.sub(r"^The\s+", "", s)
    # Collapse "( Foo )" -> "(Foo)" (PDF extraction often leaves a space
    # before the closing paren).
    s = re.sub(r"\(\s*", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    # Lowercase prepositions and conjunctions when they appear in the middle.
    s = re.sub(
        r"(?<=\w),?\s+(To|Of|And|For|With|In|On|At|By)(?=\s)",
        lambda m: ", " + m.group(1).lower() if m.group(0).startswith(",") else " " + m.group(1).lower(),
        s,
    )
    # Restore "and" in compounds like "Msme And Mines" -> "MSME and Mines".
    s = re.sub(r"\bMsme\b", "MSME", s)
    s = re.sub(r"\bAnd\b", "and", s)
    s = re.sub(r"\bMmdr\b", "MMDR", s)
    # Re-fix the leading conjunction we just lowercased if it accidentally
    # became sentence-leading after the "The " strip.
    s = re.sub(r"^(\w)", lambda m: m.group(1).upper(), s)
    return s
