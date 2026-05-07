"""Phase A canonical Venkateshulu fixture.

Reflects the real WP 13296/2022 judgment as a pure dismissal: paragraph 24
contains only the disposition sentence and no operative directives. The
synthetic placeholder fixture that historically produced four phantom
"active obligation" cards is quarantined at
tests/fixtures/legacy/synthetic_venkateshulu_wp13296_2022/.

Respondents reflect the real cause title: R1 and R2 are Government of India
(Ministry of Mines), R3 through R6 are Government of Karnataka (Commerce
and Industries Department, Department of Mines and Geology). The primary
state respondent resolver picks R3 as the lowest-numbered Karnataka body.

EXPECTED_PLAN is the one-card output the engine must produce for this case:
SLP defensive monitor with deadline 2026-07-16 (90 days from judgment).
"""

from __future__ import annotations

from datetime import date

from kartavya.schemas.action_plan import Action, ActionPlan
from kartavya.schemas.case import Respondent
from kartavya.schemas.parsed_judgment import GroundedParagraph, ParsedJudgment

PARA_24_TEXT = (
    "Accordingly, the present petition is dismissed as being devoid of merit."
)

VENKATESHULU_STUB = ParsedJudgment(
    case_number="WP 13296/2022",
    court="High Court of Karnataka at Bengaluru",
    judgment_date=date(2026, 4, 17),
    petitioner_name="Sri V. Venkateshulu",
    respondents=[
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
            designation=(
                "Principal Secretary to Government, Commerce and Industries "
                "Department (MSME and Mines)"
            ),
            organization="Government of Karnataka",
        ),
        Respondent(
            respondent_no=4,
            designation=(
                "Secretary II (Mines), Commerce and Industries Department"
            ),
            organization="Government of Karnataka",
        ),
        Respondent(
            respondent_no=5,
            designation=(
                "Director (Mines), Department of Mines and Geology"
            ),
            organization="Government of Karnataka",
        ),
        Respondent(
            respondent_no=6,
            designation=(
                "Senior Geologist, Department of Mines and Geology"
            ),
            organization="Government of Karnataka",
        ),
    ],
    paragraphs=[
        # Phase A stub: only the operative paragraph is populated. Phase B
        # populates all 24 paragraphs with section_class and voice_spans.
        GroundedParagraph(
            paragraph_index=24,
            text=PARA_24_TEXT,
            section_class="OPERATIVE",
        ),
    ],
    verdict_class="DISMISSED",
    directives=[],
)

EXPECTED_PLAN = ActionPlan(
    case_number="WP 13296/2022",
    rule_engine_version="0.3.0",
    actions=[
        Action(
            kind="DEFENSIVE_MONITOR",
            title="Monitor SLP window",
            description=(
                "Petitioner has 90 days from 2026-04-17 to file a Special "
                "Leave Petition under Article 136 of the Constitution. "
                "Respondent should be prepared to defend if filed."
            ),
            deadline=date(2026, 7, 16),
            target_role_id="PRIMARY_STATE_RESPONDENT",
            rule_id="dismissed_slp_window",
            rule_version="0.3.0",
            statute_citation=(
                "Article 136, Constitution of India; "
                "Limitation Act, 1963, Article 133"
            ),
            source_directive_id=None,
            source_paragraph_index=None,
        ),
    ],
)
