# CLAUDE.md — Kartavya Project Rules

> Canonical source of truth for architectural decisions, coding standards, and invariants. Read at every Claude Code session start. Rules here override pattern-matching from training data. When a rule here conflicts with a "common" pattern, the rule here wins.

---

## 0. How to Read This File

Rules are stratified into three tiers. **Tier-1** rules apply in every phase forever and are non-negotiable. **Tier-2** rules apply during the production phase and are deferred during prototype with explicit deferral notes. **Tier-3** rules apply only during prototype and sunset when the prototype phase ends.

The current phase is set in §1. When the phase changes, only §1 is edited. The rest of the file stays stable. This is what makes the file solid throughout.

**Style discipline.** Invariants are stated, not implied. When a rule applies in multiple places, it is restated in each place it would naturally be looked up. Sections are read independently — by humans on a deadline and by Claude Code on a task — so repetition across sections is the cost of robustness, not a defect.

---

## 1. Current Phase

**Phase:** PROTOTYPE
**Started:** 2026-05-04
**Ends:** 2026-05-07 23:59 IST (HackerEarth submission deadline)
**Goal:** Working demo against the Sri V. Venkateshulu canonical case (and one stretch case), with rules engine, audit trail, and split-screen review functioning end-to-end. Architectural invariants are real, not aspirational. Production scaffolding is deferred.

After this phase ends, edit this section to `PRODUCTION` and Tier-3 rules deactivate automatically.

---

## 2. Project Mission

Kartavya is a compliance-operations layer over the Karnataka Court Case Management System. It converts disposed judgment PDFs into verified, deadline-bound action plans for government officers operating under contempt liability.

The user is a Deputy Secretary, not a lawyer. The output must survive court scrutiny. This is **staff assistance** — equivalent to a junior officer's notes. Kartavya never decides. The officer always decides.

---

## 3. Tier-1 Invariants (Every Phase, Forever)

These are load-bearing for the submission's credibility and for the system's defensibility in court. Violating any of these is a P0 bug regardless of how convenient the violation is. If a request would require violating one of these, refuse and surface the conflict.

**The decision rule.** If a language model could be wrong about it, it goes in `extraction/`. If it must be exactly right, it goes in `rules_engine/`. This single sentence summarizes the eight invariants below — when in doubt, apply it.

**Confidence semantics.** Defined in §10.5. The threshold table lives in `schemas/confidence.py` and exists nowhere else; do not duplicate it.

### 3.1 The LLM never computes deadlines.

The LLM extracts: verdict class, paragraph type, operative direction text, source span, confidence. **Nothing else.** Specifically the LLM must never output:

- Dates of any kind
- Deadlines, due dates, limitation periods, or windows
- Statute citations
- Officer designations or names
- Department assignments

Deadlines are computed exclusively by `kartavya/rules_engine/`, a pure-Python module that reads versioned YAML rule tables and cites exact statutes. If a prompt would ask the LLM for any of the forbidden outputs above, route through the rules engine instead.

### 3.2 Append-only audit log.

The `audit_events` table is append-only. There is no `UPDATE` and no `DELETE` path in the codebase. Every state transition on `cases`, `paragraphs`, `operative_directions`, `action_plans`, `action_items` writes an `audit_events` row in the same database transaction. Use `audit.record(...)` — never write to the table directly.

Every audit event for an LLM-touching operation must record the paragraph IDs that contributed to the extraction. This is a typed `paragraph_ids: list[UUID]` parameter on `audit.record(...)`, not an entry in `payload`. The recorder asserts non-empty `paragraph_ids` whenever `prompt_sha` is provided. See §10.3.

### 3.3 Designation, not name.

`target_role` is always a designation string ("Principal Secretary, Commerce & Industries"), never a person name. The responsibility mapper enforces this. If a respondent string can't be mapped with confidence ≥ 0.85, the result is `MAPPING_REQUIRED`, surfaced in review for officer correction. Never guess a designation.

Why: officers transfer; pending work follows the role, not the person.

### 3.4 Source-linked extraction.

Every LLM-extracted field carries an `ExtractionProvenance` object containing `source_span`, `paragraph_id`, `bounding_box`, `confidence`, `prompt_sha`, `model_id`, `temperature`, `extracted_at`. If any field is missing, the extraction is invalid. The Pydantic schema enforces this; do not bypass.

### 3.5 Versioned rules and prompts.

Rule tables live in `kartavya/rules_engine/tables/*.yaml`, each with a SemVer `version` field. Prompts live in `kartavya/extraction/prompts/<task>.v<N>.md` with YAML frontmatter. Editing either kind of file in place without bumping the version is a CI failure. Every `action_plan` row stores `rule_engine_version`. Every extraction logs `prompt_sha`. The chain of reproducibility is unbroken.

### 3.6 Constrained JSON, validated.

All Ollama calls use JSON mode with strict Pydantic schema validation. On parse failure: log the failure with prompt SHA and raw response, retry once at temperature 0, then fail loudly with status `EXTRACTION_FAILED`. Do not catch and proceed with defaults. Do not silently skip fields.

### 3.7 Data sovereignty.

Default model: local Ollama. Hosted-model paths exist behind feature flag `KARTAVYA_HOSTED_MODELS_ENABLED` and are gated by deterministic-scrambler middleware that strips PII (party names, addresses, phone numbers, case numbers) before any outbound call. Demo mode disables the flag and the network.

Calling any hosted LLM provider from any code path without the flag set is a P0 violation. There is no "just for testing" carve-out. If a test needs the flag, it sets the flag explicitly and uses the scrambler; otherwise it uses local Ollama or a cassette.

### 3.8 Schemas first.

Pydantic models in `kartavya/schemas/` are the contract between every module. They are written before the code that consumes them. Never define an inline data shape that should live in `schemas/`. When in doubt, put it in `schemas/`. The contract-bearing catalogue lives in §9 — when you add a schema there, update the catalogue.

---

## 4. Tier-2 Production Rules (Deferred During Prototype)

These apply during PRODUCTION phase. During PROTOTYPE phase they are deferred with the noted expedient. The deferral is explicit so the production direction is preserved.

### 4.1 Async job queue.

**Production:** Redis + RQ workers, separate processes for ingestion, OCR, extraction, rules.
**Prototype expedient:** FastAPI `BackgroundTasks`, single process. Orchestration logic identical; runtime substrate differs.

### 4.2 OCR pipeline.

**Production:** Surya OCR with pdfplumber routing for hybrid PDFs.
**Prototype expedient:** Pre-extracted text fixtures for canonical cases. The OCR module exists with the correct interface; the implementation reads from `tests/fixtures/<case_slug>/paragraphs.json` instead of running Surya.

### 4.3 Audit table partitioning.

**Production:** `audit_events` partitioned monthly on `created_at`.
**Prototype expedient:** Single unpartitioned table. Append-only invariant enforced regardless.

### 4.4 Static analysis.

**Production:** `mypy --strict` on `rules_engine/`, `schemas/`, `audit/`. `ruff` on everything. CI gate.
**Prototype expedient:** `mypy` on `rules_engine/` and `schemas/` only. `ruff` on everything. No CI gate; run locally before commit.

### 4.5 Test coverage.

**Production:** 95% coverage on rules engine including property-based tests via `hypothesis`.
**Prototype expedient:** Unit tests for every YAML rule. End-to-end tests against canonical case fixtures. Property-based tests deferred.

### 4.6 Frontend stack for the review screen.

**Production:** React 18 + Vite, PDF.js, Tailwind. Component-tested.
**Prototype expedient:** Alpine.js + PDF.js + Tailwind, single HTML page. Same DOM contract the production version will have. Migration path: lift Alpine state into a React component, identical behavior.

### 4.7 SSO and authentication.

**Production:** State Data Centre SSO integration.
**Prototype expedient:** Stub `current_officer` dependency that returns a fixed officer record. All API endpoints already use the dependency; swap-in is trivial.

---

## 5. Tier-3 Prototype Rules (Active Now, Sunset on 2026-05-07)

Specific to the 72-hour build. Removed when phase changes to PRODUCTION.

### 5.1 Demo-first prioritization.

When making any tradeoff, ask: does the jury see this in the 4-minute demo? If yes, full rigor. If no, minimum viable. The "minimum viable" choice is documented under §4 with the production direction stated.

### 5.2 Canonical cases are the spec.

Single source of truth for "is the system working" is the canonical case fixtures in `tests/fixtures/`:

1. `venkateshulu_wp13296_2022/` — primary, must work end-to-end live
2. `case_two_slug/` — secondary, pre-cached extraction acceptable
3. `case_three_slug/` — stretch goal, may be cut

Each fixture directory contains `original.pdf`, `paragraphs.json` (pre-segmented), `expected_extraction.json` (ground truth), `expected_action_plan.json` (ground truth). Any code change must keep all extant fixtures passing.

### 5.3 No new dependencies without justification.

If a problem can be solved with the existing dependency set, solve it that way. Adding a library costs setup time and demo-day risk. Approved dependencies are in §8.

### 5.4 No premature abstraction.

If a function is called once, it stays inline until called twice. The codebase is 72 hours old; refactoring patterns from years of accumulated complexity do not apply.

### 5.5 No production-grade error UX.

Errors during prototype show as JSON in the API and as red banners in the UI. Polished error states are deferred.

### 5.6 Demo mode is real.

A `--demo` flag (CLI) and `?demo=1` query parameter (API) load pre-cached extraction state for canonical cases, bypassing live Ollama calls. This is not fakery: it exercises the cached-state code path that production will use for replay and audit. The flag is wired through cleanly, not patched in.

### 5.7 The "network offline" indicator is real.

The dashboard shows a network-status indicator that reflects actual outbound network reachability. It is not hardcoded. During demo it shows offline because the demo machine's network is genuinely off. This is the data-sovereignty proof.

---

## 6. Architecture Overview

```
CCMS / Manual upload
  → FastAPI ingestion endpoint (sync, returns case_id + status)
  → BackgroundTask (prototype) / RQ worker (production)
  → OCR stage (cached fixtures in prototype, Surya in production)
  → Extraction stage (Ollama, three calls per case, constrained JSON)
  → Rules engine stage (pure Python, YAML tables)
  → Postgres (cases, paragraphs, directions, action_plans, action_items, audit_events)
  → FastAPI + Jinja/HTMX dashboard
  → Alpine.js review island (production: React) with PDF.js
```

Module boundary discipline:

- `kartavya/api/` — FastAPI routers, request/response schemas, no business logic
- `kartavya/workers/` — orchestration of pipeline stages
- `kartavya/extraction/` — Ollama client, prompt management, extraction pipeline
- `kartavya/ingestion/` — PDF text extraction and OCR routing
- `kartavya/rules_engine/` — pure Python, no I/O, no LLM, no DB. Importable in any context.
- `kartavya/schemas/` — Pydantic v2 models, the contract layer
- `kartavya/db/` — SQLAlchemy ORM, sessions, migrations
- `kartavya/audit/` — single audit recorder
- `kartavya/responsibility/` — designation mapper (YAML + Python), used by rules_engine
- `kartavya/ui/` — Jinja templates, static assets, Alpine review island

The rules engine is the architectural keystone. It does not import from any module that performs I/O. It can be tested in 50ms with no dependencies running.

**Layout note.** Modules live at `kartavya/<module>/`, not `kartavya/packages/<module>/`. There is no top-level `apps/` or `packages/` partition. A single Python package (`kartavya`) contains everything. If you find a `packages/` directory in the tree, it is a vestige of an earlier scaffolding instruction and should be unwound.

---

## 7. Directory Structure

```
kartavya/
├── api/
│   ├── routers/            # ingestion, cases, review, plans, audit
│   ├── deps.py             # DB session, current_officer
│   └── main.py
├── workers/
│   └── pipeline.py         # orchestrates OCR → Extraction → Rules
├── extraction/
│   ├── prompts/            # versioned prompt files
│   ├── client.py           # Ollama wrapper (JSON mode, retries, provenance)
│   └── pipeline.py
├── ingestion/
│   ├── text.py             # pdfplumber path
│   ├── ocr.py              # Surya path (prototype: fixture loader)
│   └── router.py           # text-vs-OCR routing
├── rules_engine/
│   ├── tables/             # YAML rule tables, versioned
│   ├── calendar.py         # date math, holidays
│   ├── engine.py           # generate_action_plan(extraction) -> ActionPlan
│   └── trace.py            # rule trace generation
├── responsibility/
│   ├── mapper.py           # respondent string → designation
│   └── tables/             # YAML designation map
├── schemas/                # all Pydantic v2 models
├── db/
│   ├── models.py           # SQLAlchemy ORM
│   ├── session.py
│   └── migrations/         # Alembic
├── audit/
│   └── recorder.py
├── ui/
│   ├── templates/          # Jinja
│   ├── static/             # Tailwind, Alpine, PDF.js
│   └── review.html         # the review island
├── tests/
│   ├── fixtures/           # canonical case directories
│   ├── unit/
│   └── integration/
└── pyproject.toml
```

---

## 8. Approved Dependencies

Adding outside this list requires justification.

```
fastapi, uvicorn[standard]
pydantic>=2.6
sqlalchemy>=2.0, alembic, psycopg[binary]
pdfplumber
ollama  # python client
httpx, jinja2, python-multipart
pyyaml
python-dateutil
structlog
pytest, pytest-asyncio
ruff, mypy
```

Frontend (CDN, no build step in prototype):
- Alpine.js 3
- Tailwind CSS (via Play CDN for prototype, build step in production)
- PDF.js
- HTMX

Locked LLM: `llama3.1:8b-instruct-q4_K_M` via local Ollama. Do not switch models without updating §1 and `ARCHITECTURE.md`.

---

## 9. Coding Standards

**Python.** 3.11+. Type hints everywhere in `schemas/`, `rules_engine/`, `audit/`. Type hints encouraged elsewhere.

**Naming.** `snake_case` functions and variables, `PascalCase` classes and Pydantic models. Modules are short and lowercase. Schema suffix indicates kind: `CaseRead`, `CaseCreate`, `ExtractionResult`, `ActionPlan`. Never `*DTO`, never `*Manager`, never `*Service` for a stateless function.

**Pydantic v2.** All cross-boundary data is a Pydantic model. SQLAlchemy ORM models live only in `db/models.py` and are converted to Pydantic at the API boundary, never returned directly. **Returning a SQLAlchemy ORM model from an API route is a P0 violation** — it leaks storage shape onto the wire and silently exposes columns added later. Convert at the boundary every time.

**SQLAlchemy 2.0.** `Mapped[...]` syntax. UUID primary keys generated app-side. Timestamps are `TIMESTAMP WITH TIME ZONE`.

**Errors.** Domain errors in `kartavya/errors.py`. API translates to HTTP in `api/error_handlers.py`. Never raise `Exception` or generic `ValueError` for domain conditions.

**Logging.** `structlog`, JSON output. Every log line includes `case_id` when applicable. No `print`. No stdlib `logging`.

**Functions over classes.** Prefer module-level functions and Pydantic models. Classes for stateful objects only (DB session, Ollama client).

**Imports.** Absolute imports only. Rules engine imports from `schemas/` and `errors.py` and nothing else.

**Contract-bearing schemas (catalogue).** Every schema below lives in `kartavya/schemas/` and is a contract between modules. Adding a contract-bearing schema requires adding it here in the same commit.

*Ingestion → Extraction:*
- `Paragraph` — id, page, bounding_box, text, paragraph_index

*Extraction outputs:*
- `ParagraphClassification` — paragraph_id, label, confidence, provenance
- `ParagraphLabel` — enum (`OPERATIVE`, `CONTEXTUAL`, `PROCEDURAL`); operational taxonomy per §10.1. Three labels, indexed on what the officer must do — not on the rhetorical content of the paragraph. Only `OPERATIVE` paragraphs feed the rules engine.
- `Verdict` — enum (`ALLOWED`, `DISMISSED`, `PARTLY_ALLOWED`, `DISPOSED_WITH_DIRECTIONS`, `REMANDED`)
- `VerdictClassification` — case_id, verdict, confidence, provenance
- `OperativeDirection` — id, paragraph_id, text, source_span, confidence, provenance
- `ExtractionResult` — case_id, classifications, verdict, directions, metadata
- `ExtractionProvenance` — source_span, paragraph_id, bounding_box, confidence, prompt_sha, model_id, temperature, extracted_at

*Rules engine outputs:*
- `ActionPlan` — case_id, action_items, rule_engine_version, generated_at
- `ActionItem` — id, description, target_role, deadline, severity, rule_trace
- `RuleTrace` — rule_id, rule_version, statute, triggered_by, computation

*Audit:*
- `AuditEvent` — id, event_type, entity_type, entity_id, actor, payload, prompt_sha, model_id, temperature, rule_engine_version, paragraph_ids, created_at
- `AuditEventType` — enum
- `EntityType` — enum
- `ActorRef` — kind, id, designation

*API request/response (Pydantic, not SQLAlchemy):*
- `CaseCreate`, `CaseRead`
- `ReviewFieldUpdate`
- `ActionPlanRead`

*Confidence:*
- `ConfidenceTier` — enum (`HIGH`, `MEDIUM`, `LOW`); thresholds in `schemas/confidence.py`

If you find yourself defining a data shape inline that is not on this list and crosses a module boundary, stop, put it in `schemas/`, and add it here.

---

## 10. Subsystem Rules

### 10.1 Extraction (`extraction/`)

Three Ollama calls per case, never combined:
1. Paragraph classifier (returns `ParagraphClassification[]`)
2. Verdict classifier (returns `VerdictClassification`)
3. Operative direction extractor (returns `OperativeDirection[]`, run only on paragraphs labelled `operative` by the classifier)

Each prompt file format:
```
---
task: verdict_classifier
version: 1
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: VerdictClassification
---
[prompt body]
```

The Ollama wrapper computes prompt SHA-256 at call time and persists it on the extracted record. On JSON parse failure: one retry at temperature 0, then `EXTRACTION_FAILED`.

### 10.2 Rules Engine (`rules_engine/`)

Pure Python. No imports from `api/`, `workers/`, `db/`, `extraction/`, `ingestion/`, `audit/`.

Input: `ExtractionResult`. Output: `ActionPlan` with `action_items` each carrying a `rule_trace`.

Every rule cites a statute in its YAML entry. A rule without a statute citation does not exist. Date math via `python-dateutil`; working-day and holiday handling lives in `calendar.py`.

Rule trace format:
```python
class RuleTrace(BaseModel):
    rule_id: str
    rule_version: str
    statute: str            # "Article 136, Constitution of India"
    triggered_by: dict      # {"verdict": "dismissed", "state_is_respondent": true}
    computation: str        # "judgment_date(2026-04-17) + 90 days = 2026-07-16"
```

### 10.3 Audit (`audit/`)

Single entry point:
```python
def record(
    event_type: AuditEventType,
    entity_type: EntityType,
    entity_id: UUID,
    actor: ActorRef,
    payload: dict,
    *,
    prompt_sha: str | None = None,
    model_id: str | None = None,
    temperature: float | None = None,
    rule_engine_version: str | None = None,
    paragraph_ids: list[UUID] | None = None,
    session: Session,
) -> AuditEvent: ...
```

Invariants enforced inside `record(...)`:

- When `prompt_sha` is provided, `paragraph_ids` must be non-empty. Violation raises `AuditInvariantError`. This is what makes "the LLM saw these paragraphs and produced this output" reproducible from the log alone.
- `payload` is for non-PII operational metadata only. Reference entities by ID; never stuff party names, document text, or extracted strings into `payload`.
- The recorder is the only writer to `audit_events`. CI grep check: any insert/update on tables other than `audit_events` without a corresponding `audit.record` call in the same function is flagged.

### 10.4 Review UI (`ui/review.html`)

Alpine.js for state, PDF.js for rendering, Tailwind for styling. Single page.

Bounding-box overlay: transparent canvas above the PDF canvas, coordinates transformed from PDF points to viewport pixels. Recompute on scroll and zoom.

Keyboard shortcuts:
- `j` / `k` — next / previous field
- `a` — approve current field
- `e` — edit current field
- `r` — reject current field
- `?` — help overlay

State machine: `DRAFT → IN_REVIEW → (APPROVED | MODIFIED | REJECTED) → COMMITTED`. Transitions hit the API; the UI never sets state locally without server confirmation.

### 10.5 Confidence Tiers

Three-tier, applied uniformly:
- `HIGH` (≥ 0.85): single-key approve
- `MEDIUM` (0.6 – 0.85): explicit field check required, no batch approve
- `LOW` (< 0.6): blocks plan approval until corrected

High-stakes fields (`financial_exposure`, `service_matter`, `contempt_implication`) raise `HIGH` to ≥ 0.95. Threshold table lives in `schemas/confidence.py` and exists nowhere else. Do not duplicate the numbers in prompts, in the UI, in tests, or in docs — import them.

---

## 11. Database Rules

- Forward-only migrations in deployed environments
- Every table has `created_at`; mutable tables also have `updated_at`. Both `TIMESTAMP WITH TIME ZONE`, defaulted in DB.
- Foreign keys explicit. `ON DELETE RESTRICT` by default — we don't delete cases.
- Required indexes: `audit_events(entity_type, entity_id, created_at)`, `cases(status, created_at)`, `action_items(deadline) WHERE deadline IS NOT NULL`.

---

## 12. Demo-Readiness Gates (Tier-3, Active During Prototype)

End of each day, these must pass. If any fails, the next day's first task is to fix it.

**End of Day 1 (May 4):** Extraction runs on Sri V. Venkateshulu and produces a result that matches the ground-truth fixture within tolerance — verdict class exact match, paragraph classifications ≥ 90% match, all operative directions captured.

**End of Day 2 (May 5):** Rules engine generates `expected_action_plan.json` from the extracted result. Audit events recorded for every pipeline stage. Database reflects committed state.

**End of Day 3 (May 6):** Review UI renders the canonical case end-to-end. Bounding-box overlays land on correct paragraphs. Keyboard shortcuts work. State machine transitions through to COMMITTED. Network-offline indicator reflects reality. Demo mode loads cached state in under 2 seconds.

**End of Day 4 (May 7) by 8 PM:** Submission uploaded. Demo video recorded. Buffer remaining.

---

## 13. Definition of Done

A change is done when:

1. Type checks pass on `rules_engine/` and `schemas/` (and other directories per phase)
2. `ruff check .` passes
3. All canonical case fixtures still produce expected output
4. New state-changing code paths have `audit.record` calls
5. New prompts are versioned files; no edits in place
6. New rules cite statutes in their YAML entry
7. New cross-boundary data shapes are listed in the §9 schema catalogue
8. No Tier-1 invariant is violated

---

## 14. Anti-Patterns to Refuse

When suggested, refuse and reference the rule.

- "Let the LLM compute the deadline." → §3.1
- "Skip the audit event, this is small." → §3.2
- "Map respondent to the named officer." → §3.3
- "Store the LLM-returned date directly." → §3.1, §3.4
- "One mega-prompt is more efficient." → §10.1
- "Soft-delete the case." → §11
- "Catch JSON parse error and use a default." → §3.6
- "Edit the prompt file in place, the change is small." → §3.5
- "Add a `users` table." → Use `officers`. The system serves government officers, not users.
- "Add Redux/Zustand for review state." → §4.6, Alpine + props is sufficient
- "Refactor this duplicate code now." → §5.4 during prototype
- "Add this useful library." → §5.3, justify against existing deps first
- "Call OpenAI/Anthropic/cloud LLM, just for this test." → §3.7. The flag is the only entry. No carve-outs.
- "Return the SQLAlchemy model directly, the fields match anyway." → §9 (Pydantic v2). Convert at the boundary.
- "Log the LLM event without paragraph IDs, we can backfill." → §3.2, §10.3. The recorder will reject it; do not work around the assertion.
- "Put the modules under `kartavya/packages/`." → §6, §7. Layout is `kartavya/<module>/`, single package, no `packages/` or `apps/` partition.
- "Duplicate the confidence thresholds in the prompt for clarity." → §10.5. Import them from `schemas/confidence.py`.

---

## 15. Out of Scope (Prototype Phase)

Refuse scope expansion into:
- Real authentication beyond stub `current_officer`
- Email/SMS notifications
- Mobile responsive UI
- Bulk historical-case ingestion
- Multi-tenant cross-state support
- Statute coverage beyond the five named in §3.5
- Custom OCR tuning (use fixtures)
- Internationalization beyond what's hardcoded for canonical cases

When asked, push back and ask whether it's prototype-critical. Default answer: defer to Round 2.

---

## 16. Versioning of This File

Material changes (Tier-1 invariants, module boundaries, dependency list) require a version bump and a `CHANGELOG.md` entry. Phase changes (§1) are not version bumps.

**Version:** 2.2.0
**Last updated:** 2026-05-06
**Phase set:** PROTOTYPE through 2026-05-07

**Changelog (2.1.0 → 2.2.0):**
- §9 (catalogue): replaced the implicit 6-value `ParagraphLabel` (facts/arguments/reasoning/precedent/operative/decree) with the explicit 3-value operational taxonomy (`OPERATIVE`/`CONTEXTUAL`/`PROCEDURAL`); added `Verdict` enum entry that was previously implicit.
- §10.1: operative direction extractor now runs on paragraphs labelled `operative` only — `decree` no longer exists as a separate label (verdict-statement paragraphs collapse into `operative` because they trigger limitation calculation).
- Why: 6-label scheme produced 70.83% paragraph accuracy on Venkateshulu, with the failure mode being pure semantic confusion (one paragraph routinely contains facts + arguments + reasoning). Indexing on operational role rather than rhetorical content collapses the ambiguity. Prompt re-authored as `paragraph_classifier.v2.md`; v1 retained per §3.5.

**Changelog (2.0.0 → 2.1.0):**
- §0: added style-discipline note ("invariants stated, not implied")
- §3 preamble: added the decision rule one-liner and a pointer to §10.5 for confidence semantics
- §3.2: added paragraph-IDs invariant for LLM-touching audit events
- §3.7: tightened — no carve-outs for hosted-LLM calls without the flag
- §3.8: added pointer to §9 schema catalogue
- §6: added `responsibility/` to module list; added layout note rejecting `packages/`
- §7: added `responsibility/` directory; removed `responsibility/` nesting under `rules_engine/`
- §9 (Pydantic v2): elevated "no SQLAlchemy from API routes" to P0 with explicit reasoning
- §9: new "Contract-bearing schemas (catalogue)" subsection
- §10.3: added `paragraph_ids` typed parameter; added invariants block
- §10.5: explicit "do not duplicate" rule for the confidence threshold table
- §13: added schema-catalogue update to Definition of Done
- §14: five new anti-patterns (hosted LLM without flag, SQLAlchemy from route, audit without paragraph_ids, packages/ layout, duplicating confidence thresholds)