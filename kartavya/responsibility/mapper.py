"""Responsibility mapper — addressee text → designation string (§3.3).

Two-stage resolution:
  1. Look up the addressee text in the case's respondents / additional_forums
     (provided by `CaseMetadata`). This is the authoritative source for the
     specific case and is preferred when it matches.
  2. Fall back to `tables/designations.yaml` for well-known forum patterns
     (e.g. "reference court" → Principal District Judge) when the case
     metadata doesn't carry the addressee.

Returns the sentinel `MAPPING_REQUIRED` (a constant string) when neither path
produces a confident match. Callers must surface `MAPPING_REQUIRED` to the
reviewer and never substitute a guess (§3.3 anti-pattern).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import yaml  # type: ignore[import-untyped]

from kartavya.schemas.case import CaseMetadata

MAPPING_REQUIRED: Final[str] = "MAPPING_REQUIRED"

_TABLE_PATH = Path(__file__).parent / "tables" / "designations.yaml"
_ORDINAL_RE = re.compile(
    r"\b(first|second|third|fourth|fifth)\s+respondents?\b", re.IGNORECASE
)


def _load_table() -> dict[str, object]:
    with _TABLE_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def map_addressee(addressee_text: str, case: CaseMetadata) -> str:
    """Resolve a directive's addressee phrase to a designation string.

    `addressee_text` is free text from the directive (e.g. "the second
    respondent", "the reference court", "the petitioner"). The function is
    intentionally narrow: it recognizes the small set of phrases that appear
    in Karnataka High Court directive language and returns `MAPPING_REQUIRED`
    for anything else.
    """
    text = addressee_text.lower().strip()

    table = _load_table()
    ordinal_aliases: dict[str, int] = table.get("ordinal_aliases", {})  # type: ignore[assignment]
    forum_aliases: dict[str, str] = table.get("forum_aliases", {})  # type: ignore[assignment]
    fallback_designations: dict[str, str] = table.get("fallback_designations", {})  # type: ignore[assignment]

    # 1. Ordinal-respondent match: "the second respondent" → respondents[ordinal=2].
    ordinal_match = _ORDINAL_RE.search(text)
    if ordinal_match:
        word = ordinal_match.group(1).lower()
        ordinal = ordinal_aliases.get(word)
        if ordinal is not None:
            for r in case.respondents:
                if r.ordinal == ordinal:
                    return r.designation

    # 2. Forum alias: "the reference court" → additional_forums[key="reference_court"].
    for alias, key in forum_aliases.items():
        if alias in text:
            for forum in case.additional_forums:
                if forum.key == key:
                    return forum.designation
            # Forum alias known but case has no specific entry → fall back to table.
            fallback = fallback_designations.get(key)
            if fallback is not None:
                return fallback
            break  # alias matched but no resolution available; don't keep scanning

    # 3. Catch-all phrasings the prototype doesn't aim to disambiguate.
    return MAPPING_REQUIRED


def primary_respondent_designation(case: CaseMetadata) -> str:
    """Designation for verdict-driven action items (SLP / review windows)."""
    return case.primary_respondent().designation
