"""Render-time validators for the Phase A action plan path.

Construction-time validators on `ParsedJudgment` ensure every
`OperativeDirective` is grounded in a paragraph span, in court voice, in
an OPERATIVE section, and points to a respondent FK. These validators run
at construction.

The render-time validators here run on the assembled `ActionPlan` and
catch contradictions that span multiple actions or that depend on case-
level state the schema validator cannot see, such as:

  TARGET_NOT_IN_RESPONDENTS
    target_role_id is an int that is not any respondent_no in the case.

  UNGROUNDED_PRIMARY_STATE_TARGET
    target_role_id is the sentinel "PRIMARY_STATE_RESPONDENT" but the
    case has no respondent whose organization is a Karnataka state body.

  OBLIGATION_WITHOUT_SOURCE
    An ACTIVE_OBLIGATION action has no source_directive_id. By the
    architectural principle (extraction is quotation), every active
    obligation must trace to a directive grounded in the source PDF.

  DISMISSED_WITH_OBLIGATION
    The case verdict is DISMISSED but an ACTIVE_OBLIGATION action is
    present. A pure dismissal cannot create active obligations.

  SOURCE_PARAGRAPH_MISSING
    source_paragraph_index is set but no paragraph in the case has that
    index.

  SOURCE_PARAGRAPH_NOT_OPERATIVE
    source_paragraph_index points to a paragraph whose section_class is
    not OPERATIVE.

If `validate_action_plan` returns any errors, the renderer must NOT show
the plan. The UI shows a single human-review banner instead. A blank plan
is a safe failure; a wrong card is an unsafe failure.
"""

from __future__ import annotations

from kartavya.schemas.action_plan import Action, ActionPlan
from kartavya.schemas.parsed_judgment import ParsedJudgment

ValidationError = tuple[str, Action]


def validate_action_plan(
    plan: ActionPlan,
    case: ParsedJudgment,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    respondent_nos = {r.respondent_no for r in case.respondents}
    para_by_index = {p.paragraph_index: p for p in case.paragraphs}

    for a in plan.actions:
        # Target grounding. Either the FK is a real respondent_no, or the
        # sentinel resolves to a Karnataka state respondent.
        if a.target_role_id == "PRIMARY_STATE_RESPONDENT":
            if case.primary_state_respondent() is None:
                errors.append(("UNGROUNDED_PRIMARY_STATE_TARGET", a))
        elif isinstance(a.target_role_id, int):
            if a.target_role_id not in respondent_nos:
                errors.append(("TARGET_NOT_IN_RESPONDENTS", a))
        else:
            # The Pydantic Literal restricts to int or the sentinel; the
            # else branch is unreachable in correct code but flagged here
            # so any future widening of TargetRoleId surfaces loudly.
            errors.append(("TARGET_NOT_IN_RESPONDENTS", a))

        # Active obligations require a citing directive.
        if a.kind == "ACTIVE_OBLIGATION" and a.source_directive_id is None:
            errors.append(("OBLIGATION_WITHOUT_SOURCE", a))

        # Pure DISMISSED cannot have ACTIVE_OBLIGATION.
        if (
            case.verdict_class == "DISMISSED"
            and a.kind == "ACTIVE_OBLIGATION"
        ):
            errors.append(("DISMISSED_WITH_OBLIGATION", a))

        # Source paragraph must exist and be OPERATIVE when set.
        if a.source_paragraph_index is not None:
            if a.source_paragraph_index not in para_by_index:
                errors.append(("SOURCE_PARAGRAPH_MISSING", a))
            else:
                para = para_by_index[a.source_paragraph_index]
                if para.section_class != "OPERATIVE":
                    errors.append(("SOURCE_PARAGRAPH_NOT_OPERATIVE", a))

    return errors


__all__ = ["ValidationError", "validate_action_plan"]
