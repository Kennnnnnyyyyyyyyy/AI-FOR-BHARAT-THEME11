"""Tests for kartavya/responsibility/mapper.py."""

from __future__ import annotations

from datetime import date

from kartavya.responsibility import (
    MAPPING_REQUIRED,
    map_addressee,
    primary_respondent_designation,
)
from kartavya.schemas.case import (
    AdditionalForum,
    CaseMetadata,
    Petitioner,
    Respondent,
)


def _make_case() -> CaseMetadata:
    return CaseMetadata(
        case_id="TEST_001",
        court="High Court of Karnataka at Bengaluru",
        case_number="WP 1/2026",
        judgment_date=date(2026, 4, 17),
        petitioner=Petitioner(name="Test Petitioner", designation=None),
        respondents=[
            Respondent(
                respondent_no=1,
                name="The State of Karnataka",
                designation="Principal Secretary, Department X",
                organization="Government of Karnataka",
            ),
            Respondent(
                respondent_no=2,
                name="KIADB",
                designation="Chief Executive Officer, KIADB",
                organization="Government of Karnataka",
            ),
        ],
        primary_respondent_no=2,
        additional_forums=[
            AdditionalForum(
                key="reference_court",
                designation="Principal District Judge (Reference Court)",
            )
        ],
    )


def test_second_respondent_resolves_to_ordinal_two_designation() -> None:
    case = _make_case()
    assert (
        map_addressee("the second respondent", case)
        == "Chief Executive Officer, KIADB"
    )


def test_first_respondent_resolves_to_ordinal_one_designation() -> None:
    case = _make_case()
    assert (
        map_addressee("the first respondent", case)
        == "Principal Secretary, Department X"
    )


def test_reference_court_resolves_via_additional_forums() -> None:
    case = _make_case()
    assert (
        map_addressee("the reference court", case)
        == "Principal District Judge (Reference Court)"
    )


def test_unknown_addressee_returns_mapping_required() -> None:
    case = _make_case()
    assert map_addressee("the chief minister of karnataka", case) == MAPPING_REQUIRED


def test_primary_respondent_designation_uses_ordinal_field() -> None:
    case = _make_case()
    assert (
        primary_respondent_designation(case) == "Chief Executive Officer, KIADB"
    )


def test_reference_court_falls_back_when_case_lacks_specific_entry() -> None:
    """When the addressee phrase is known but the case has no specific entry,
    the mapper falls back to the designations.yaml table."""
    case = _make_case()
    case.additional_forums = []  # remove specific entry
    designation = map_addressee("the reference court", case)
    assert "Reference Court" in designation
    assert designation != MAPPING_REQUIRED


def test_ordinal_with_no_matching_respondent_returns_mapping_required() -> None:
    """The case has only ordinals 1 and 2; "the third respondent" must not
    silently resolve."""
    case = _make_case()
    assert map_addressee("the third respondent", case) == MAPPING_REQUIRED


def test_ordinal_match_is_case_insensitive() -> None:
    case = _make_case()
    assert (
        map_addressee("THE SECOND RESPONDENT", case)
        == "Chief Executive Officer, KIADB"
    )
