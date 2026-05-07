"""Tests for kartavya/rules_engine/."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from kartavya.responsibility import MAPPING_REQUIRED
from kartavya.rules_engine import RULE_ENGINE_VERSION, generate_action_plan
from kartavya.rules_engine.calendar import add_days, add_months, add_period, add_weeks
from kartavya.schemas.action_plan import Severity
from kartavya.schemas.case import (
    AdditionalForum,
    CaseMetadata,
    Petitioner,
    Respondent,
)
from kartavya.schemas.extraction import (
    ExtractionResult,
    OperativeDirection,
    Verdict,
    VerdictClassification,
)
from kartavya.schemas.paragraph import Paragraph
from kartavya.schemas.provenance import ExtractionProvenance


# ---------- calendar ----------


def test_add_days_60_from_april_17_lands_on_june_16() -> None:
    assert add_days(date(2026, 4, 17), 60) == date(2026, 6, 16)


def test_add_weeks_4_from_april_17_lands_on_may_15() -> None:
    assert add_weeks(date(2026, 4, 17), 4) == date(2026, 5, 15)


def test_add_months_6_from_april_17_lands_on_october_17() -> None:
    assert add_months(date(2026, 4, 17), 6) == date(2026, 10, 17)


def test_add_days_90_from_april_17_lands_on_july_16() -> None:
    """Article 136 SLP window — the demo's headline deadline."""
    assert add_days(date(2026, 4, 17), 90) == date(2026, 7, 16)


def test_add_period_dispatches_on_unit() -> None:
    base = date(2026, 4, 17)
    assert add_period(base, 60, "days") == date(2026, 6, 16)
    assert add_period(base, 4, "weeks") == date(2026, 5, 15)
    assert add_period(base, 6, "months") == date(2026, 10, 17)


# ---------- engine: synthetic Venkateshulu-shaped fixture ----------


def _provenance() -> ExtractionProvenance:
    return ExtractionProvenance(
        source_span="x",
        paragraph_id=UUID(int=20),
        bounding_box=(0, 0, 1, 1),
        confidence=0.95,
        prompt_sha="a" * 64,
        model_id="llama3.1:8b-instruct-q4_K_M",
        temperature=0.0,
        extracted_at=datetime.now(timezone.utc),
    )


def _case() -> CaseMetadata:
    return CaseMetadata(
        case_id="WP_TEST",
        court="High Court of Karnataka at Bengaluru",
        case_number="WP 1/2026",
        judgment_date=date(2026, 4, 17),
        petitioner=Petitioner(name="Test", designation=None),
        respondents=[
            Respondent(
                respondent_no=1,
                name="State",
                designation="Principal Secretary X",
                organization="Government of Karnataka",
            ),
            Respondent(
                respondent_no=2,
                name="KIADB",
                designation="CEO, KIADB",
                organization="Government of Karnataka",
            ),
        ],
        primary_respondent_no=2,
        additional_forums=[
            AdditionalForum(key="reference_court", designation="Principal District Judge (Reference Court)"),
        ],
    )


def _paragraph(idx: int, text: str) -> Paragraph:
    return Paragraph(
        id=UUID(int=idx),
        page=1,
        bounding_box=(0, 0, 100, 100),
        text=text,
        paragraph_index=idx,
    )


def _direction(paragraph_id: UUID, text: str = "x") -> OperativeDirection:
    return OperativeDirection(
        id=uuid4(),
        paragraph_id=paragraph_id,
        text=text,
        source_span="x",
        confidence=0.95,
        provenance=_provenance(),
    )


def _extraction(
    *,
    case_id: UUID,
    verdict: Verdict,
    directions: list[OperativeDirection],
) -> ExtractionResult:
    return ExtractionResult(
        case_id=case_id,
        paragraph_classifications=[],
        verdict=VerdictClassification(
            case_id=case_id,
            verdict=verdict,
            confidence=0.99,
            provenance=_provenance(),
        ),
        operative_directions=directions,
        extracted_at=datetime.now(timezone.utc),
    )


def test_dismissed_verdict_produces_slp_window_action_item() -> None:
    case = _case()
    case_id = uuid4()
    paragraphs: list[Paragraph] = []
    extraction = _extraction(case_id=case_id, verdict=Verdict.DISMISSED, directions=[])

    plan = generate_action_plan(case, extraction, paragraphs)

    assert len(plan.action_items) == 1
    item = plan.action_items[0]
    assert item.rule_trace.rule_id == "dismissed_slp_window"
    assert item.severity == Severity.DEFENSIVE
    assert item.deadline is not None
    assert item.deadline.date() == date(2026, 7, 16)
    assert item.target_role == "CEO, KIADB"
    assert "Article 136" in item.rule_trace.statute
    assert plan.rule_engine_version == RULE_ENGINE_VERSION


def test_remanded_verdict_produces_informational_no_deadline() -> None:
    case = _case()
    case_id = uuid4()
    extraction = _extraction(case_id=case_id, verdict=Verdict.REMANDED, directions=[])

    plan = generate_action_plan(case, extraction, [])

    assert len(plan.action_items) == 1
    item = plan.action_items[0]
    assert item.rule_trace.rule_id == "remanded_compliance_monitoring"
    assert item.severity == Severity.INFORMATIONAL
    assert item.deadline is None


def test_directive_within_n_days_pattern_computes_deadline() -> None:
    case = _case()
    case_id = uuid4()
    para = _paragraph(
        20,
        "Accordingly, we direct the second respondent to disburse the "
        "compensation within a period of sixty days from the date of receipt "
        "of a copy of this order.",
    )
    direction = _direction(para.id)
    extraction = _extraction(
        case_id=case_id, verdict=Verdict.DISPOSED_WITH_DIRECTIONS, directions=[direction]
    )

    plan = generate_action_plan(case, extraction, [para])

    directive_items = [
        i for i in plan.action_items if i.rule_trace.rule_id.startswith("directive_")
    ]
    assert len(directive_items) == 1
    item = directive_items[0]
    assert item.severity == Severity.ACTIVE
    assert item.deadline is not None
    assert item.deadline.date() == date(2026, 6, 16)
    assert item.target_role == "CEO, KIADB"
    assert "paragraph 20" in item.rule_trace.statute


def test_directive_within_n_weeks_pattern_computes_deadline() -> None:
    case = _case()
    case_id = uuid4()
    para = _paragraph(
        21,
        "The second respondent is further directed to file a compliance "
        "affidavit before the Registrar within four weeks of disbursement.",
    )
    direction = _direction(para.id)
    extraction = _extraction(
        case_id=case_id, verdict=Verdict.DISPOSED_WITH_DIRECTIONS, directions=[direction]
    )

    plan = generate_action_plan(case, extraction, [para])
    item = next(i for i in plan.action_items if i.rule_trace.rule_id.startswith("directive_"))
    assert item.deadline is not None
    assert item.deadline.date() == date(2026, 5, 15)


def test_directive_within_n_months_pattern_wins_over_expeditiously() -> None:
    """P022-shape: 'expeditiously and, in any event, within six months' must
    bind to six months (concrete pattern wins over open-ended)."""
    case = _case()
    case_id = uuid4()
    para = _paragraph(
        22,
        "The reference court is requested to dispose of the pending reference "
        "expeditiously and, in any event, within a period of six months from "
        "the date of communication of this order.",
    )
    direction = _direction(para.id)
    extraction = _extraction(
        case_id=case_id, verdict=Verdict.DISPOSED_WITH_DIRECTIONS, directions=[direction]
    )

    plan = generate_action_plan(case, extraction, [para])
    item = next(i for i in plan.action_items if i.rule_trace.rule_id.startswith("directive_"))
    assert item.deadline is not None
    assert item.deadline.date() == date(2026, 10, 17)
    assert item.target_role == "Principal District Judge (Reference Court)"


def test_open_ended_expeditious_directive_flags_for_review_no_deadline() -> None:
    """A directive carrying ONLY 'expeditiously' (no concrete period) must
    produce an item with deadline=None and a flagged trace."""
    case = _case()
    case_id = uuid4()
    para = _paragraph(
        20,
        "The second respondent is directed to take action expeditiously.",
    )
    direction = _direction(para.id)
    extraction = _extraction(
        case_id=case_id, verdict=Verdict.DISPOSED_WITH_DIRECTIONS, directions=[direction]
    )

    plan = generate_action_plan(case, extraction, [para])
    item = next(i for i in plan.action_items if i.rule_trace.rule_id.startswith("directive_"))
    assert item.deadline is None
    assert item.severity == Severity.ACTIVE
    assert "flagged for officer review" in item.rule_trace.computation


def test_directive_with_unknown_addressee_returns_mapping_required_target() -> None:
    """§3.3 anti-pattern: never guess a designation. If the addressee is
    unrecognized, target_role is the MAPPING_REQUIRED sentinel."""
    case = _case()
    case_id = uuid4()
    para = _paragraph(
        20,
        "The Chief Minister is directed to act within sixty days.",
    )
    direction = _direction(para.id)
    extraction = _extraction(
        case_id=case_id, verdict=Verdict.DISPOSED_WITH_DIRECTIONS, directions=[direction]
    )

    plan = generate_action_plan(case, extraction, [para])
    item = next(i for i in plan.action_items if i.rule_trace.rule_id.startswith("directive_"))
    assert item.target_role == MAPPING_REQUIRED


def test_full_venkateshulu_shape_produces_four_items() -> None:
    """End-to-end synthetic: dismissed verdict + 3 directives → 4 items."""
    case = _case()
    case_id = uuid4()
    p20 = _paragraph(20, "we direct the second respondent within a period of sixty days from the date of this order")
    p21 = _paragraph(21, "the second respondent is further directed within four weeks of disbursement")
    p22 = _paragraph(
        22,
        "the reference court is requested to dispose expeditiously and, in any "
        "event, within a period of six months from the date of communication.",
    )

    directions = [_direction(p20.id), _direction(p21.id), _direction(p22.id)]
    extraction = _extraction(case_id=case_id, verdict=Verdict.DISMISSED, directions=directions)

    plan = generate_action_plan(case, extraction, [p20, p21, p22])

    assert len(plan.action_items) == 4
    deadlines = sorted(
        [i.deadline.date() for i in plan.action_items if i.deadline is not None]
    )
    assert deadlines == [
        date(2026, 5, 15),  # P21 — 4 weeks
        date(2026, 6, 16),  # P20 — 60 days
        date(2026, 7, 16),  # SLP — 90 days
        date(2026, 10, 17),  # P22 — 6 months
    ]
