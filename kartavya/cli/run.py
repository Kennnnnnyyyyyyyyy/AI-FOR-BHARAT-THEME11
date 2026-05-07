"""Kartavya CLI for the hackathon demo.

Usage:
    .venv/bin/python -m kartavya.cli.run path/to/judgment.pdf
    .venv/bin/python -m kartavya.cli.run path/to/judgment.pdf --dry-run
    .venv/bin/python -m kartavya.cli.run path/to/judgment.pdf --json

Pipeline:
    cause-title parse + segment -> voice tag -> section classify ->
    directive extract -> rules-engine ActionPlan -> render-time validate.

Flags:
    --dry-run    Use stubbed LLM clients (deterministic; no Ollama
                 dependency; suitable for the negative case where the
                 deterministic classifier and the empty-directives stub
                 produce the same result a real LLM would).
    --json       Print the ActionPlan as JSON (useful for piping into
                 other tools or for the demo's "see the structured
                 output" beat).
    --today      Override "today" for risk-tier and overdue calculations
                 (default: system date). Required for reproducible
                 demos against fixed-date fixtures.

For the positive case (synthetic disposed-with-directions judgment),
real Ollama must be running; the directive parser invokes it once per
OPERATIVE paragraph. For the negative case (Venkateshulu, dismissal),
--dry-run produces the same result without touching the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from kartavya.extraction.directives import extract_directives
from kartavya.extraction.section import classify_paragraphs
from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.cause_title import parse_cause_title
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.rules_engine.engine import generate_actions
from kartavya.rules_engine.validators import validate_action_plan
from kartavya.schemas.parsed_judgment import GroundedParagraph, ParsedJudgment


def _stubbed_clients() -> tuple[Any, Any]:
    section = MagicMock()
    section.generate_json.return_value = {"section_class": "REASONING"}
    directives = MagicMock()
    directives.generate_json.return_value = {"directives": []}
    return section, directives


def _positive_demo_directive_client(
    paragraphs: list[GroundedParagraph],
) -> Any:
    """Demo-only directive stub: detects the synthetic positive-case
    paragraphs by content match and returns three canned directive offsets
    so `make demo-positive` works without requiring Ollama in the demo
    environment. Live deployments use the real Ollama-backed adapter via
    `_real_clients()`; this helper is wired only when --demo-positive is
    set on the CLI."""
    p6 = next((p for p in paragraphs if p.paragraph_index == 6), None)
    if p6 is None or "is directed to" not in p6.text:
        # Not the synthetic positive case; fall back to empty stub.
        client = MagicMock()
        client.generate_json.return_value = {"directives": []}
        return client

    third = p6.text.index("The third respondent is directed")
    third_end = (
        p6.text.index("from the date of this order.", third)
        + len("from the date of this order.")
    )
    second = p6.text.index("The second respondent is directed")
    second_end = (
        p6.text.index("from the date of this order.", second)
        + len("from the date of this order.")
    )
    first = p6.text.index("The first respondent is directed")
    first_end = (
        p6.text.index("from the date of this order.", first)
        + len("from the date of this order.")
    )

    client = MagicMock()
    client.generate_json.return_value = {
        "directives": [
            {
                "char_start": third,
                "char_end": third_end,
                "actor_text": "the third respondent",
                "verb_token": "DIRECT",
                "time_clause_text": "within four weeks",
            },
            {
                "char_start": second,
                "char_end": second_end,
                "actor_text": "the second respondent",
                "verb_token": "DIRECT",
                "time_clause_text": "within sixty days",
            },
            {
                "char_start": first,
                "char_end": first_end,
                "actor_text": "the first respondent",
                "verb_token": "DIRECT",
                "time_clause_text": "within ninety days",
            },
        ]
    }
    return client


def _real_clients() -> tuple[Any, Any]:
    """Wire to a real Ollama-backed adapter. The OllamaClient in
    extraction/client.py uses Pydantic-class schemas and returns tuples;
    the section + directive callers expect dict-returning generate_json.
    For B5 demo, we wrap OllamaClient in a thin adapter that returns dicts.
    """
    from kartavya.extraction.client import OllamaClient

    base = OllamaClient()

    class _DictAdapter:
        def __init__(self, model: str | None = None) -> None:
            self._model = model or base.model

        def generate_json(self, prompt: str) -> dict[str, Any]:
            response = base._client.generate(  # type: ignore[attr-defined]
                model=self._model,
                prompt=prompt,
                format="json",
                options={
                    "temperature": 0.0,
                    "num_ctx": base.num_ctx,
                    "num_predict": base.num_predict,
                },
            )
            raw = response["response"]
            if isinstance(raw, str):
                return json.loads(raw)
            return raw  # type: ignore[no-any-return]

    return _DictAdapter(), _DictAdapter()


def _infer_verdict(paragraphs: list[GroundedParagraph]) -> str:
    """Heuristic verdict inference from the OPERATIVE paragraph's text.

    The Phase A verdict classifier (in extraction/pipeline.py) is the right
    long-term home for this. For the demo CLI we keep it inline because
    the two demo cases are unambiguous: pure dismissal -> DISMISSED,
    "disposed of with the following directions" -> DISPOSED_WITH_DIRECTIONS.
    """
    operative = [p for p in paragraphs if p.section_class == "OPERATIVE"]
    if not operative:
        return "DISMISSED"
    text = " ".join(p.text for p in operative).lower()
    if "is dismissed" in text or "are dismissed" in text:
        return "DISMISSED"
    if "is allowed" in text or "are allowed" in text:
        return "ALLOWED"
    if "is partly allowed" in text:
        return "PARTLY_ALLOWED"
    if "is remanded" in text or "remanded for" in text:
        return "REMANDED"
    if "is directed to" in text or "are directed to" in text:
        return "DISPOSED_WITH_DIRECTIONS"
    if "disposed of" in text:
        return "DISPOSED_WITH_DIRECTIONS"
    return "DISMISSED"


def _resolve_target(target_role_id: Any, case: ParsedJudgment) -> str:
    if target_role_id == "PRIMARY_STATE_RESPONDENT":
        primary = case.primary_state_respondent()
        if primary is None:
            return "UNRESOLVED"
        return f"R{primary.respondent_no}: {primary.designation}"
    for r in case.respondents:
        if r.respondent_no == target_role_id:
            return f"R{r.respondent_no}: {r.designation}"
    return f"R{target_role_id} (unknown)"


def _days_from(deadline: date | None, today: date) -> str:
    if deadline is None:
        return "(open-ended)"
    delta = (deadline - today).days
    if delta == 0:
        return "due today"
    if delta < 0:
        return f"OVERDUE by {-delta} days"
    return f"in {delta} days"


def _render_table(
    case: ParsedJudgment, plan: Any, errors: list[Any], today: date
) -> None:
    bar = "=" * 80
    print()
    print(bar)
    print(f"Case:     {case.case_number}")
    print(f"Court:    {case.court}")
    print(f"Date:     {case.judgment_date}")
    print(f"Verdict:  {case.verdict_class}")
    print(f"Engine:   v{plan.rule_engine_version}")
    print(bar)
    print()

    if errors:
        print("VALIDATION ERRORS (plan would be routed to human review):")
        for code, action in errors:
            print(f"  [{code}] {action.title}")
        print()

    n = len(plan.actions)
    plural = "s" if n != 1 else ""
    print(f"Action plan ({n} item{plural}):")
    print()
    for i, a in enumerate(plan.actions, 1):
        target = _resolve_target(a.target_role_id, case)
        deadline_str = a.deadline.isoformat() if a.deadline else "(open-ended)"
        print(f"  [{i}] {a.kind}")
        print(f"      Title:    {a.title}")
        print(f"      Deadline: {deadline_str} ({_days_from(a.deadline, today)})")
        print(f"      Target:   {target}")
        print(f"      Rule:     {a.rule_id} ({a.rule_version})")
        print(f"      Statute:  {a.statute_citation}")
        if a.source_paragraph_index is not None:
            print(f"      Source:   paragraph {a.source_paragraph_index}")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kartavya: judgment PDF -> action plan."
    )
    parser.add_argument("pdf", type=Path, help="Path to the judgment PDF")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use stubbed LLM clients (no Ollama)",
    )
    parser.add_argument(
        "--demo-positive",
        action="store_true",
        help=(
            "Demo-only flag that injects canned directives for the synthetic "
            "positive-case fixture. Used by `make demo-positive` so the demo "
            "runs without requiring Ollama in the demo environment."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the ActionPlan as JSON instead of formatted text",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=date.today(),
        help="Override today for deadline math (ISO format YYYY-MM-DD)",
    )
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        print(f"error: {args.pdf} does not exist", file=sys.stderr)
        return 1

    section_llm, directive_llm = (
        _stubbed_clients() if args.dry_run else _real_clients()
    )

    md = parse_cause_title(args.pdf)
    paragraphs = annotate_paragraphs(segment_judgment(args.pdf))
    classified = classify_paragraphs(paragraphs, llm_client=section_llm)
    classified_paragraphs = [p for p, _ in classified]

    if args.demo_positive:
        directive_llm = _positive_demo_directive_client(classified_paragraphs)

    verdict = _infer_verdict(classified_paragraphs)
    case_no_directives = ParsedJudgment(
        case_number=md.case_number,
        court=md.court,
        judgment_date=md.judgment_date,
        petitioner_name=md.petitioner_name,
        respondents=md.respondents,
        paragraphs=classified_paragraphs,
        verdict_class=verdict,  # type: ignore[arg-type]
        directives=[],
    )

    directives = extract_directives(
        case_no_directives, llm_client=directive_llm
    )
    case = case_no_directives.model_copy(update={"directives": directives})
    plan = generate_actions(case, today=args.today)
    errors = validate_action_plan(plan, case)

    if args.json:
        print(
            json.dumps(plan.model_dump(mode="json"), indent=2, default=str)
        )
    else:
        _render_table(case, plan, errors, args.today)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
