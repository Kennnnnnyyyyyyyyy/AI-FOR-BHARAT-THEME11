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

*Case metadata (input to rules engine):*
- `CaseMetadata` — case_id, court, case_number, judgment_date, petitioner, respondents, primary_respondent_ordinal, additional_forums. Loaded from per-case `case.json` adjacent to `paragraphs.json`. The judgment_date is authoritative input; the LLM never extracts it (§3.1).
- `Petitioner` — name, designation (designation null for private petitioners)
- `Respondent` — ordinal (1-indexed, matches case caption), name, designation (per §3.3, never a person name)
- `AdditionalForum` — key, designation. Non-respondent forum addressed by an operative direction (e.g. a reference court). Resolved by the responsibility mapper from the directive's addressee text via the `key`.

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

**Paragraph classifier — three-check gate.** A paragraph is `OPERATIVE` only if all three hold; otherwise `CONTEXTUAL` (or `PROCEDURAL` per the metadata rules):

1. *Speaker is the court itself* — not counsel, not a party, not a quoted precedent. Counsel cannot direct anyone; only the court does.
2. *Speech act is directing or disposing*, not evaluative — phrases like "we find merit", "we are of the view", "we are not persuaded", "such conduct disentitles", "warrants interference" are evaluation, not direction. The court is reasoning toward a verdict; it has not yet announced one.
3. *A current obligation is created or a final disposition is announced* — past-tense narration of earlier acts ("notice was issued", "an award came to be passed", "petitioner submitted a representation seeking exclusion") fails. Asking is not directing; describing history is not disposing.

When uncertain, label `CONTEXTUAL`. False-positive `OPERATIVE` creates phantom obligations downstream; false-negative is recoverable in officer review. Surface forcefulness ("merit", "persuaded", "disentitles", "urges", "barred", "warrants") does not satisfy any check — rhetorical intensity is not legal force. The `paragraph_classifier.v3.md` prompt is the canonical formulation; this subsection is the contract.

### 10.2 Rules Engine (`rules_engine/`)

Pure Python. No imports from `api/`, `workers/`, `db/`, `extraction/`, `ingestion/`, `audit/`.

Inputs: `CaseMetadata` + `ExtractionResult` + `paragraphs`. Output: `ActionPlan` with `action_items` each carrying a `rule_trace` and the `rule_engine_version` stamped on the plan.

Every rule cites a statute in its YAML entry. A rule without a statute citation does not exist. Date math via `python-dateutil`; working-day and holiday handling lives in `calendar.py` (deferred to Round 2 — calendar-day arithmetic for now).

Entry point: `kartavya.rules_engine.generate_action_plan(case, extraction, paragraphs) -> ActionPlan`. The function is pure; it loads YAML once at first call, caches per process, and is safe to call repeatedly.

`RULE_ENGINE_VERSION` is a module-level constant in `rules_engine/__init__.py`. Bump it on any change to engine code or to YAML rule tables under `tables/`. Every emitted `ActionPlan` carries this version per §3.5 — the chain of reproducibility is unbroken.

Rule trace format:
```python
class RuleTrace(BaseModel):
    rule_id: str
    rule_version: str       # SemVer of the YAML rule table
    statute: str            # "Article 136, Constitution of India"
    triggered_by: dict      # {"verdict": "dismissed"} or {"paragraph_index": 20, "matched_phrase": "..."}
    computation: str        # "judgment_date(2026-04-17) + 90 days = 2026-07-16"
```

**Rule tables.** All rules live in versioned YAML under `rules_engine/tables/`. Two table families today; both validated at table-load time (severity strings against the `Severity` enum, regex patterns compile-checked).

- `slp_window.yaml` — verdict-driven limitation rules. One rule per `Verdict` enum value:
  - `dismissed` → 90-day Article 136 SLP window, severity `defensive`
  - `allowed` → 30-day CPC Order XLVII review window, severity `defensive`
  - `partly_allowed` → 30-day CPC Order XLVII review window, severity `defensive`
  - `remanded` → no fixed period; ongoing monitoring, severity `informational`
  - `disposed_with_directions` → no fixed period; the issued directions are captured as ACTIVE items via the directive extractor, severity `informational`
- `directive_relative_deadlines.yaml` — period-pattern parser for operative directions. First-match-wins ordering:
  1. `within_n_days`, `within_n_weeks`, `within_n_months` — concrete patterns, compute an absolute deadline as `judgment_date + N`. Numeric word tokens (`sixty`, `four`, `six`) are mapped via `word_to_number`.
  2. `open_ended_expeditious` — fallback for "expeditiously" / "forthwith" / "as soon as possible" / "without delay" / "at the earliest". Sets `flag_for_officer_review: true` and produces an ActionItem with `deadline=null`. The rules engine never guesses a deadline the court did not specify.

  Concrete patterns precede open-ended ones so a directive carrying both ("expeditiously and, in any event, within six months") binds to the hard deadline.

**Responsibility mapping (`responsibility/`).** A directive's addressee text (e.g. "the second respondent", "the reference court") is resolved to a designation string via `kartavya.responsibility.map_addressee(addressee, case_metadata)`. Two-stage resolution:

1. Look up the addressee in the case's respondents (via ordinal — "the second respondent" → `respondents[ordinal=2].designation`) or `additional_forums` (via key alias — "the reference court" → `forums[key="reference_court"].designation`). This is the authoritative source for the case at hand.
2. Fall back to `responsibility/tables/designations.yaml` for well-known forum patterns when the case metadata doesn't carry the addressee.

If neither path produces a confident match, the function returns the sentinel string `MAPPING_REQUIRED` per §3.3. Callers must surface `MAPPING_REQUIRED` to the reviewer for officer correction; never substitute a guess. Verdict-driven action items use `primary_respondent_designation(case)`, which reads the `primary_respondent_ordinal` field on `CaseMetadata`.

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

**Version:** 2.4.0
**Last updated:** 2026-05-07
**Phase set:** PROTOTYPE through 2026-05-07

**Changelog (2.3.4 → 2.4.0):**
- Rules engine activated for the first time (`kartavya/rules_engine/`). Pure Python, YAML-driven, deterministic deadline calculation per §3.1 / §3.5 / §10.2. Entry point: `generate_action_plan(case, extraction, paragraphs) -> ActionPlan`. `RULE_ENGINE_VERSION = "0.1.0"` stamped on every emitted plan.
- Two YAML rule tables, each with SemVer per §3.5:
  - `tables/slp_window.yaml` — all five `Verdict` enum values mapped to limitation windows (Article 136 SLP for dismissals, CPC Order XLVII review for allowed / partly_allowed, ongoing monitoring for remanded / disposed_with_directions).
  - `tables/directive_relative_deadlines.yaml` — period-pattern parser for operative directions; concrete `within_n_{days,weeks,months}` patterns precede open-ended `expeditiously` / `forthwith` patterns; open-ended hits flag for officer review with `deadline=null` rather than guessing.
- Responsibility mapper activated (`kartavya/responsibility/`). Resolves directive addressee text to a designation (§3.3) via two-stage lookup (case-specific respondents/forums first, `tables/designations.yaml` fallback second). Returns the `MAPPING_REQUIRED` sentinel when neither path is confident — never guesses a designation.
- New schemas (added to §9 catalogue): `CaseMetadata`, `Petitioner`, `Respondent`, `AdditionalForum`. Loaded from per-case `case.json` adjacent to `paragraphs.json`. Carries `judgment_date` — the LLM still never extracts dates (§3.1); the rules engine receives the date as authoritative input.
- New fixture files for Venkateshulu: `case.json` (KIADB as second respondent, reference court as additional forum, judgment_date 2026-04-17) and `expected_action_plan.json` (4 expected items with the deadline math 60d → 2026-06-16, 4w → 2026-05-15, 6mo → 2026-10-17, 90d-SLP → 2026-07-16). Per §5.2.
- Integration test now runs the rules engine after extraction, writes the `ActionPlan` to the debug dump, and asserts (rule_id, target_role, deadline_date, severity, statute_substring) against `expected_action_plan.json`.
- Why minor bump (2.3.4 → 2.4.0, not patch): new module-boundary activation (rules_engine + responsibility populated for the first time), new schemas in §9 catalogue, new fixture file family per §5.2, new YAML rule tables per §3.5. This is the largest single addition since 2.0.0. Patch bumps were appropriate for the v2/v3 directive prompt revisions (within an existing module); this expands the architecture proper.

**Changelog (2.3.3 → 2.3.4):**
- Directive extractor prompt re-authored as `operative_extractor.v3.md`; v1 and v2 retained per §3.5. Two coupled defects fixed in one revision because they share the same boundary ("what counts as a directive"):
  - **Polite imperatives are still directives.** Inter-court / inter-agency phrasings such as "the reference court is requested to … within six months" are directives when the court is the speaker, the act is forward-looking, and an obligation with a temporal trigger is created. Softness is judicial courtesy, not optionality. v2 missed P022 on this; v3 names the boundary explicitly with P022 as a worked positive example.
  - **Dispositions are out of scope for the directive extractor.** Dismissal / allowance / partly-allowed / disposed-with-directions / remanded are captured by the verdict classifier as a verdict statement; downstream deadlines (e.g. Article 136 SLP window) flow from that signal, not from a directive. v2's positive-example list included "the writ petition is dismissed with costs", which led the model to emit a directive for P023; v3 removes that from the positive list and adds it as a worked negative example. Two stages, one signal each, no double-counting.
- Why bumped to 2.3.4 (not appended to 2.3.3): the prior 2.3.3 entry is observability plumbing; this is a discrete prompt revision with a new scope ruling. Separate entries keep next-run attribution clean.
- Note: the scope ruling lives in the prompt body for now. If we want to elevate it to a CLAUDE.md §10.1 contract block (paralleling the three-check gate that lives there for the paragraph classifier), that is a separate edit not authorized in this round.

**Changelog (2.3.2 → 2.3.3):**
- `extraction/pipeline.py` (`extract_directions`): operative_extractor `EXTRACTION_COMPLETED` audit event payload now carries `accepted_paragraph_ids: list[str]` — the deduplicated, insertion-ordered list of paragraph IDs that produced ≥1 accepted directive. `accepted` and `rejected` counters unchanged. The `paragraph_ids` audit-event field continues to carry the candidate input list per §3.2; `accepted_paragraph_ids` is a new payload key, not a redefinition of an existing one.
- `tests/integration/test_apvc_pipeline.py`: same list now written to `_debug_extraction.json` under `operative_direction_paragraph_ids`. Test assertions unchanged.
- Why bumped to 2.3.3 (not appended to 2.3.2): the prior 2.3.2 entry is a discrete prompt revision; this is telemetry plumbing on the same stage. Separate entries keep next-run attribution clean. No contract change beyond the new payload key.
- Why this exists: the v2 directive-extractor run reported `accepted: 3, rejected: 0` against expected sources `[20, 21, 22]` with `missing: [22]`. The on-disk artifacts could not distinguish "3 directives from {P020, P021, P023}" from "3 directives from {P020, P021} with one duplicate". `accepted_paragraph_ids` is the smallest signal that disambiguates — needed before any further prompt revision.

**Changelog (2.3.0 → 2.3.2):**
- Directive extractor prompt re-authored as `operative_extractor.v2.md`; v1 retained per §3.5. Single-defect fix: anchor instruction. Why bumped to 2.3.2 (skipping 2.3.1): 2.3.0 absorbed both the v3 classifier and the follow-on observability work; this is a discrete prompt revision on a different pipeline stage and deserves its own attribution boundary.
- Failure mode pinned by the observability run (2.3.0 appendix telemetry): model emitted directives with the literal placeholder string `<paragraph anchor copied verbatim>` as the anchor field, all 4/4 dropped at the anchor-mismatch guard. v1's prompt presented the placeholder syntax in the JSON shape but had no Rules entry naming the anchor format and no end-to-end worked example.
- v2 changes: (1) added an explicit Rules entry naming the `P###-XXXXXXXX` anchor format and stating that the placeholder marker is not the value to emit; (2) added a worked example with a fabricated but realistic anchor (`P042-1a2b3c4d`) and a complete output JSON; (3) tightened the placeholder wording in the JSON shape to `<paragraph anchor exactly as given>` matching the v3 classifier's wording. The opening definition (v1 line 10), the example list (v1 lines 36–37), the disposition contradiction, and the conservative-bias instruction (v1 line 55) are all preserved verbatim — single-defect fix to keep next-run attribution clean.

**Changelog (2.2.0 → 2.3.0):**
- §10.1: codified the three-check gate (speaker / speech-act / obligation) for the paragraph classifier. Names the boundary the v2 taxonomy left implicit between court reasoning and court directing — counsel cannot direct, evaluative voice is not disposition, past-tense narration is not a current obligation.
- Why: v2 ran 83.33% on Venkateshulu against the 90% gate. All four misses were CONTEXTUAL→OPERATIVE on a single boundary — court evaluative voice ("we find merit", "we are not persuaded"), counsel urging an outcome, and past party representations being read as dispositive. Confidence on misses (0.92–0.98) was higher than on correct OPERATIVE classifications, so a confidence threshold could not rescue the gate.
- Prompt re-authored as `paragraph_classifier.v3.md`; v1 and v2 retained per §3.5.
- Follow-on observability (no contract change; appended rather than 2.3.1 because tightly coupled to the same diagnostic arc):
  - `audit/recorder.py`: structlog emission now includes `payload` so per-call counters (`accepted`, `rejected`, etc.) reach the run log. Previously dropped on the floor — surfaced when investigating why the directive extractor silently produced zero directives on the v3 run.
  - `extraction/pipeline.py` (`extract_directions`): per-item rejection at the anchor and span checks now emits a structured `operative_direction_rejected` warning (reason, paragraph_id, anchor, truncated source_span). Rejection behavior unchanged.
  - `tests/integration/test_apvc_pipeline.py`: positive lower-bound assertion added — every paragraph in the fixture's `operative_direction_paragraph_indices` must produce at least one directive. The negative leak assertion stays. Catches silent-zero regressions that previously passed.

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