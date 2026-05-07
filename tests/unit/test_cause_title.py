"""Phase B6 cause-title parser tests against the real Venkateshulu PDF."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from kartavya.ingestion.cause_title import parse_cause_title

FIXTURE = Path("tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf")
META_FIXTURE = Path(
    "tests/fixtures/venkateshulu_real_pdf_wp13296_2022/expected_metadata.json"
)
RESP_FIXTURE = Path(
    "tests/fixtures/venkateshulu_real_pdf_wp13296_2022/expected_respondents.json"
)


def test_case_metadata_matches_expected() -> None:
    expected = json.loads(META_FIXTURE.read_text())
    md = parse_cause_title(FIXTURE)
    assert md.case_number == expected["case_number"]
    assert md.court == expected["court"]
    assert md.judgment_date == date.fromisoformat(expected["judgment_date"])
    assert md.petitioner_name == expected["petitioner_name"]


def test_respondent_count_is_6() -> None:
    md = parse_cause_title(FIXTURE)
    assert len(md.respondents) == 6


def test_respondent_3_is_principal_secretary_ci_karnataka() -> None:
    md = parse_cause_title(FIXTURE)
    r3 = next(r for r in md.respondents if r.respondent_no == 3)
    assert "Principal Secretary" in r3.designation
    assert "Commerce and Industries" in r3.designation
    assert r3.organization == "Government of Karnataka"


def test_respondent_1_is_ministry_of_mines_goi() -> None:
    md = parse_cause_title(FIXTURE)
    r1 = next(r for r in md.respondents if r.respondent_no == 1)
    assert "Secretary" in r1.designation
    assert "Ministry of Mines" in r1.designation
    assert r1.organization == "Government of India"


def test_respondent_organizations_partition_correctly() -> None:
    md = parse_cause_title(FIXTURE)
    by_no = {r.respondent_no: r for r in md.respondents}
    assert by_no[1].organization == "Government of India"
    assert by_no[2].organization == "Government of India"
    for n in (3, 4, 5, 6):
        assert by_no[n].organization == "Government of Karnataka", (
            f"R{n} mis-attributed: got {by_no[n].organization!r}"
        )


def test_no_respondent_has_unresolved_organization() -> None:
    md = parse_cause_title(FIXTURE)
    for r in md.respondents:
        assert r.organization != "UNRESOLVED", (
            f"R{r.respondent_no} organization unresolved"
        )


def test_respondent_designations_match_phase_a_stub() -> None:
    """The real-PDF respondents must produce designations identical to the
    Phase A stub fixture. This is the bridge from synthetic ground-truth
    (hand-typed) to real-PDF ground-truth (parsed)."""
    expected = json.loads(RESP_FIXTURE.read_text())
    md = parse_cause_title(FIXTURE)
    by_no = {r.respondent_no: r for r in md.respondents}
    for item in expected["respondents"]:
        actual = by_no[item["respondent_no"]]
        assert actual.designation == item["designation"], (
            f"R{item['respondent_no']} designation mismatch: "
            f"got {actual.designation!r}, expected {item['designation']!r}"
        )
