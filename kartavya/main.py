from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from kartavya.cli.run import (
    _infer_verdict,
    _positive_demo_directive_client,
    _resolve_target,
    _stubbed_clients,
)
from kartavya.extraction.directives import extract_directives
from kartavya.extraction.section import classify_paragraphs
from kartavya.extraction.voice import annotate_paragraphs
from kartavya.ingestion.cause_title import parse_cause_title
from kartavya.ingestion.segmentation import segment_judgment
from kartavya.rules_engine.engine import generate_actions
from kartavya.rules_engine.validators import validate_action_plan
from kartavya.schemas.parsed_judgment import ParsedJudgment

app = FastAPI(
    title="Kartavya",
    description="Compliance-operations layer for Karnataka High Court judgments",
    version="0.3.0",
)

origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PKG = Path(__file__).resolve().parent
_REPO = _PKG.parent
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PKG / "ui" / "templates")),
    autoescape=select_autoescape(["html"]),
)


CASES: dict[str, dict[str, Any]] = {
    "venkateshulu": {
        "label": "WP 13296/2022 — Sri V. Venkateshulu (DISMISSED)",
        "pdf": _REPO
        / "tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf",
        "today": date(2026, 5, 7),
        "demo_positive": False,
    },
    "synthetic-positive": {
        "label": "WP 8472/2025 — Synthetic (DISPOSED WITH DIRECTIONS)",
        "pdf": _REPO
        / "tests/fixtures/synthetic_disposed_with_directions/judgment.pdf",
        "today": date(2026, 3, 15),
        "demo_positive": True,
    },
}

_PLAN_CACHE: dict[str, dict[str, Any]] = {}


def _build_plan(case_slug: str) -> dict[str, Any]:
    if case_slug in _PLAN_CACHE:
        return _PLAN_CACHE[case_slug]
    cfg = CASES[case_slug]

    section_llm, directive_llm = _stubbed_clients()
    md = parse_cause_title(cfg["pdf"])
    paragraphs = annotate_paragraphs(segment_judgment(cfg["pdf"]))
    classified = classify_paragraphs(paragraphs, llm_client=section_llm)
    classified_paragraphs = [p for p, _ in classified]

    if cfg["demo_positive"]:
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
    directives = extract_directives(case_no_directives, llm_client=directive_llm)
    case = case_no_directives.model_copy(update={"directives": directives})
    plan = generate_actions(case, today=cfg["today"])
    errors = validate_action_plan(plan, case)

    actions_view = []
    for a in plan.actions:
        target = _resolve_target(a.target_role_id, case)
        delta = (a.deadline - cfg["today"]).days if a.deadline else None
        source_text = None
        if a.source_paragraph_index is not None:
            for p in case.paragraphs:
                if p.paragraph_index == a.source_paragraph_index:
                    source_text = p.text
                    break
        actions_view.append(
            {
                "kind": a.kind,
                "title": a.title,
                "description": a.description,
                "deadline": a.deadline.isoformat() if a.deadline else None,
                "days_from_today": delta,
                "target": target,
                "rule_id": a.rule_id,
                "rule_version": a.rule_version,
                "statute": a.statute_citation,
                "source_paragraph_index": a.source_paragraph_index,
                "source_text": source_text,
            }
        )

    result = {
        "case_number": case.case_number,
        "court": case.court,
        "judgment_date": case.judgment_date.isoformat(),
        "petitioner": case.petitioner_name,
        "respondents": [
            {"no": r.respondent_no, "designation": r.designation}
            for r in case.respondents
        ],
        "verdict_class": case.verdict_class,
        "engine_version": plan.rule_engine_version,
        "today": cfg["today"].isoformat(),
        "actions": actions_view,
        "errors": [
            [code, getattr(action, "title", str(action))] for code, action in errors
        ],
    }
    _PLAN_CACHE[case_slug] = result
    return result


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    cases_view = [{"slug": k, "label": v["label"]} for k, v in CASES.items()]
    template = _jinja_env.get_template("review.html")
    return HTMLResponse(template.render(cases=cases_view))


@app.get("/api/plan/{case_slug}")
def get_plan(case_slug: str) -> dict[str, Any]:
    if case_slug not in CASES:
        raise HTTPException(status_code=404, detail="unknown case")
    return _build_plan(case_slug)


@app.get("/pdf/{case_slug}")
def get_pdf(case_slug: str) -> FileResponse:
    if case_slug not in CASES:
        raise HTTPException(status_code=404, detail="unknown case")
    return FileResponse(CASES[case_slug]["pdf"], media_type="application/pdf")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
