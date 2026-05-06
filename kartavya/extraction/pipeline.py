"""Three-call extraction pipeline (§10.1) with APVC paragraph classification.

`extract(...)` runs:
  1. classify_paragraphs — APVC: anchored, sliding-window, validator + retry
  2. classify_verdict    — single constrained-JSON call
  3. extract_directions  — single constrained-JSON call over operative/decree paragraphs

Each LLM call writes paired EXTRACTION_STARTED / EXTRACTION_COMPLETED audit
events with the prompt SHA and the paragraph IDs that contributed (§3.2).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, Field

from kartavya.audit import recorder as audit
from kartavya.extraction.anchors import (
    ChunkClassifications,
    ParagraphClassificationRaw,
    anchor_token,
    build_anchor_map,
)
from kartavya.extraction.client import CallMetadata, OllamaClient
from kartavya.extraction.validator import (
    FailureReason,
    ValidationFailure,
    force_low_confidence,
    validate_chunk,
)
from kartavya.extraction.window import iter_chunks
from kartavya.schemas.audit import (
    ActorKind,
    ActorRef,
    AuditEventType,
    EntityType,
)
from kartavya.schemas.extraction import (
    ExtractionResult,
    OperativeDirection,
    ParagraphClassification,
    ParagraphLabel,
    VerdictClassification,
)
from kartavya.schemas.paragraph import Paragraph
from kartavya.schemas.provenance import ExtractionProvenance

_log = structlog.get_logger(__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

OPERATIVE_LABELS = frozenset({ParagraphLabel.OPERATIVE, ParagraphLabel.DECREE})

SYSTEM_ACTOR = ActorRef(
    kind=ActorKind.SYSTEM,
    id=UUID("00000000-0000-0000-0000-000000000001"),
    designation="kartavya.extraction",
)


# ---------- LLM-output envelopes (internal, JSON-mode shapes) ----------


class _RawVerdict(BaseModel):
    verdict: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_span: str
    source_anchor: str


class _RawDirection(BaseModel):
    anchor: str
    text: str
    source_span: str
    confidence: float = Field(ge=0.0, le=1.0)


class _RawDirections(BaseModel):
    directions: list[_RawDirection]


# ---------- Prompt loader ----------


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _load_prompt(name: str) -> tuple[dict[str, str], str]:
    """Load a versioned prompt file. Returns (frontmatter, body).

    Frontmatter is parsed as simple `key: value` pairs (no nesting, no lists).
    Body is everything after the second `---`.
    """
    path = PROMPT_DIR / name
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"prompt {name} missing YAML frontmatter")

    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        frontmatter[key.strip()] = value.strip()
    return frontmatter, match.group(2)


def _render_chunk_body(
    chunk: list[Paragraph], centre_uuids: set[UUID]
) -> str:
    """Render the paragraphs for one APVC call, marking centre vs context."""
    blocks: list[str] = []
    for p in chunk:
        marker = "[CLASSIFY]" if p.id in centre_uuids else "[CONTEXT-ONLY]"
        token = anchor_token(p)
        blocks.append(f"=== PARAGRAPH {token} {marker} ===\n{p.text.strip()}")
    return "\n\n".join(blocks)


# ---------- Paragraph classification (APVC) ----------


def classify_paragraphs(
    case_id: UUID,
    paragraphs: list[Paragraph],
    client: OllamaClient,
) -> list[ParagraphClassification]:
    """APVC: anchored, sliding-window classification with selective retry."""
    if not paragraphs:
        return []

    anchor_map = build_anchor_map(paragraphs)
    paragraphs_by_id = {p.id: p for p in paragraphs}
    _, prompt_body = _load_prompt("paragraph_classifier.v1.md")

    accepted_by_id: dict[UUID, ParagraphClassification] = {}
    failures_for_retry: list[ValidationFailure] = []

    for chunk, centre_uuids in iter_chunks(paragraphs):
        chunk_body = _render_chunk_body(chunk, centre_uuids)
        prompt = prompt_body.replace("{{CHUNK_BODY}}", chunk_body)

        chunk_paragraph_ids = [p.id for p in chunk]
        audit.record(
            event_type=AuditEventType.EXTRACTION_STARTED,
            entity_type=EntityType.CASE,
            entity_id=case_id,
            actor=SYSTEM_ACTOR,
            payload={"task": "paragraph_classifier", "chunk_size": len(chunk)},
            prompt_sha=None,  # the call hasn't happened yet; SHA bound below
            paragraph_ids=chunk_paragraph_ids,
        )

        envelope, metadata = client.generate_json(prompt, ChunkClassifications)
        accepted, failures = validate_chunk(
            envelope.classifications, anchor_map, centre_uuids, metadata
        )

        for c in accepted:
            accepted_by_id[c.paragraph_id] = c
        failures_for_retry.extend(failures)

        audit.record(
            event_type=AuditEventType.EXTRACTION_COMPLETED,
            entity_type=EntityType.CASE,
            entity_id=case_id,
            actor=SYSTEM_ACTOR,
            payload={
                "task": "paragraph_classifier",
                "accepted": len(accepted),
                "failures": len(failures),
            },
            prompt_sha=metadata.prompt_sha,
            model_id=metadata.model_id,
            temperature=metadata.temperature,
            paragraph_ids=chunk_paragraph_ids,
        )

    # Singleton retry for centre paragraphs missing or failed.
    missing_ids = [p.id for p in paragraphs if p.id not in accepted_by_id]
    failure_by_para_id = {
        f.paragraph.id: f for f in failures_for_retry if f.paragraph is not None
    }

    for paragraph_id in missing_ids:
        paragraph = paragraphs_by_id[paragraph_id]
        retry, retry_metadata, retry_raw = _retry_singleton(
            case_id, paragraph, anchor_map, client, prompt_body
        )
        if retry is not None:
            accepted_by_id[paragraph_id] = retry
            continue

        prior = failure_by_para_id.get(paragraph_id)
        # Prefer the retry's own raw output; fall back to the original chunk failure.
        forced_raw = retry_raw if retry_raw is not None else (prior.raw if prior else None)
        accepted_by_id[paragraph_id] = force_low_confidence(
            paragraph, forced_raw, retry_metadata
        )
        _log.warning(
            "paragraph_forced_low",
            case_id=str(case_id),
            paragraph_id=str(paragraph_id),
            reason=prior.reason.value if prior else "missing",
        )

    return [accepted_by_id[p.id] for p in paragraphs]


def _retry_singleton(
    case_id: UUID,
    paragraph: Paragraph,
    anchor_map: dict[str, Paragraph],
    client: OllamaClient,
    prompt_body: str,
) -> tuple[ParagraphClassification | None, CallMetadata, ParagraphClassificationRaw | None]:
    """One-paragraph retry.

    Returns `(accepted, metadata, raw)` where:
      - accepted is the validated classification, or None if validation failed
      - metadata is always the actual call's CallMetadata (so the caller can
        build a forced-LOW record with real provenance)
      - raw is the most relevant raw output for forced-LOW fallback, or None
    """
    chunk_body = _render_chunk_body([paragraph], {paragraph.id})
    prompt = prompt_body.replace("{{CHUNK_BODY}}", chunk_body)

    audit.record(
        event_type=AuditEventType.EXTRACTION_STARTED,
        entity_type=EntityType.PARAGRAPH,
        entity_id=paragraph.id,
        actor=SYSTEM_ACTOR,
        payload={"task": "paragraph_classifier", "retry": True},
        paragraph_ids=[paragraph.id],
    )
    envelope, metadata = client.generate_json(prompt, ChunkClassifications)
    accepted, failures = validate_chunk(
        envelope.classifications, anchor_map, {paragraph.id}, metadata
    )
    audit.record(
        event_type=AuditEventType.EXTRACTION_COMPLETED,
        entity_type=EntityType.PARAGRAPH,
        entity_id=paragraph.id,
        actor=SYSTEM_ACTOR,
        payload={
            "task": "paragraph_classifier",
            "retry": True,
            "accepted": len(accepted),
            "failures": len(failures),
        },
        prompt_sha=metadata.prompt_sha,
        model_id=metadata.model_id,
        temperature=metadata.temperature,
        paragraph_ids=[paragraph.id],
    )
    if accepted:
        return accepted[0], metadata, None
    # Look for any raw entry that resolved to this paragraph (even if span
    # mismatched), so the forced-LOW record carries the model's intent.
    matching_raw: ParagraphClassificationRaw | None = None
    for raw_entry in envelope.classifications:
        candidate = anchor_map.get(raw_entry.anchor)
        if candidate is not None and candidate.id == paragraph.id:
            matching_raw = raw_entry
            break
    return None, metadata, matching_raw


# ---------- Verdict ----------


def classify_verdict(
    case_id: UUID,
    paragraphs: list[Paragraph],
    client: OllamaClient,
) -> VerdictClassification:
    """Single-call verdict classification. The model is asked to identify the
    final disposition and quote a span from a specific paragraph anchor."""
    _, prompt_body = _load_prompt("verdict_classifier.v1.md")
    body = "\n\n".join(
        f"=== PARAGRAPH {anchor_token(p)} ===\n{p.text.strip()}" for p in paragraphs
    )
    prompt = prompt_body.replace("{{PARAGRAPHS}}", body)
    paragraph_ids = [p.id for p in paragraphs]

    audit.record(
        event_type=AuditEventType.EXTRACTION_STARTED,
        entity_type=EntityType.CASE,
        entity_id=case_id,
        actor=SYSTEM_ACTOR,
        payload={"task": "verdict_classifier"},
        paragraph_ids=paragraph_ids,
    )
    raw, metadata = client.generate_json(prompt, _RawVerdict)
    anchor_map = build_anchor_map(paragraphs)
    source_paragraph = anchor_map.get(raw.source_anchor, paragraphs[-1])

    audit.record(
        event_type=AuditEventType.EXTRACTION_COMPLETED,
        entity_type=EntityType.CASE,
        entity_id=case_id,
        actor=SYSTEM_ACTOR,
        payload={"task": "verdict_classifier", "verdict": raw.verdict},
        prompt_sha=metadata.prompt_sha,
        model_id=metadata.model_id,
        temperature=metadata.temperature,
        paragraph_ids=paragraph_ids,
    )

    from kartavya.schemas.extraction import Verdict  # local to avoid cycles

    return VerdictClassification(
        case_id=case_id,
        verdict=Verdict(raw.verdict.lower()),
        confidence=raw.confidence,
        provenance=ExtractionProvenance(
            source_span=raw.source_span,
            paragraph_id=source_paragraph.id,
            bounding_box=source_paragraph.bounding_box,
            confidence=raw.confidence,
            prompt_sha=metadata.prompt_sha,
            model_id=metadata.model_id,
            temperature=metadata.temperature,
            extracted_at=metadata.extracted_at,
        ),
    )


# ---------- Operative directions ----------


def extract_directions(
    case_id: UUID,
    paragraphs: list[Paragraph],
    classifications: list[ParagraphClassification],
    client: OllamaClient,
) -> list[OperativeDirection]:
    """Operative-direction extraction. Runs only on operative/decree paragraphs.

    Past-tense recitals are rejected by the prompt's instructions and by the
    validator's substring check (text must be a substring of the source paragraph).
    """
    operative_ids = {
        c.paragraph_id for c in classifications if c.label in OPERATIVE_LABELS
    }
    operative_paragraphs = [p for p in paragraphs if p.id in operative_ids]
    if not operative_paragraphs:
        return []

    _, prompt_body = _load_prompt("operative_extractor.v1.md")
    anchor_map = build_anchor_map(operative_paragraphs)
    body = "\n\n".join(
        f"=== PARAGRAPH {anchor_token(p)} ===\n{p.text.strip()}"
        for p in operative_paragraphs
    )
    prompt = prompt_body.replace("{{PARAGRAPHS}}", body)
    paragraph_ids = [p.id for p in operative_paragraphs]

    audit.record(
        event_type=AuditEventType.EXTRACTION_STARTED,
        entity_type=EntityType.CASE,
        entity_id=case_id,
        actor=SYSTEM_ACTOR,
        payload={"task": "operative_extractor", "candidate_paragraphs": len(operative_paragraphs)},
        paragraph_ids=paragraph_ids,
    )
    envelope, metadata = client.generate_json(prompt, _RawDirections)

    directions: list[OperativeDirection] = []
    rejected = 0
    for raw in envelope.directions:
        paragraph = anchor_map.get(raw.anchor)
        if paragraph is None:
            rejected += 1
            continue
        # Substring check on source_span guards against past-tense leaks copied
        # from elsewhere; the prompt already rejects them, this is defence.
        if raw.source_span.lower() not in paragraph.text.lower():
            rejected += 1
            continue
        directions.append(
            OperativeDirection(
                id=uuid4(),
                paragraph_id=paragraph.id,
                text=raw.text,
                source_span=raw.source_span,
                confidence=raw.confidence,
                provenance=ExtractionProvenance(
                    source_span=raw.source_span,
                    paragraph_id=paragraph.id,
                    bounding_box=paragraph.bounding_box,
                    confidence=raw.confidence,
                    prompt_sha=metadata.prompt_sha,
                    model_id=metadata.model_id,
                    temperature=metadata.temperature,
                    extracted_at=metadata.extracted_at,
                ),
            )
        )

    audit.record(
        event_type=AuditEventType.EXTRACTION_COMPLETED,
        entity_type=EntityType.CASE,
        entity_id=case_id,
        actor=SYSTEM_ACTOR,
        payload={
            "task": "operative_extractor",
            "accepted": len(directions),
            "rejected": rejected,
        },
        prompt_sha=metadata.prompt_sha,
        model_id=metadata.model_id,
        temperature=metadata.temperature,
        paragraph_ids=paragraph_ids,
    )
    return directions


# ---------- Top-level orchestrator ----------


def extract(
    case_id: UUID,
    paragraphs: list[Paragraph],
    client: OllamaClient,
) -> ExtractionResult:
    """Run all three extraction calls and assemble the canonical result."""
    classifications = classify_paragraphs(case_id, paragraphs, client)
    verdict = classify_verdict(case_id, paragraphs, client)
    directions = extract_directions(case_id, paragraphs, classifications, client)
    return ExtractionResult(
        case_id=case_id,
        paragraph_classifications=classifications,
        verdict=verdict,
        operative_directions=directions,
        extracted_at=datetime.now(timezone.utc),
    )


__all__ = [
    "classify_paragraphs",
    "classify_verdict",
    "extract_directions",
    "extract",
]
