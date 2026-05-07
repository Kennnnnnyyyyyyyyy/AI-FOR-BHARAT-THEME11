"""Append-only audit recorder — the single writer to `audit_events` (§3.2, §10.3).

In PROTOTYPE phase the events live in an in-memory list and are also emitted to
structlog. The §10.3 contract (signature, invariants, return shape) is preserved
so the production swap-in to a SQLAlchemy session is mechanical.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_OID, UUID, uuid4, uuid5

import structlog

from kartavya.errors import AuditInvariantError
from kartavya.schemas.audit import (
    ActorKind,
    ActorRef,
    AuditEvent,
    AuditEventType,
    EntityType,
)

_log = structlog.get_logger(__name__)
_events: list[AuditEvent] = []


def record(
    event_type: AuditEventType,
    entity_type: EntityType,
    entity_id: UUID,
    actor: ActorRef,
    payload: dict[str, Any],
    *,
    prompt_sha: str | None = None,
    model_id: str | None = None,
    temperature: float | None = None,
    rule_engine_version: str | None = None,
    paragraph_ids: list[UUID] | None = None,
    session: Any | None = None,
) -> AuditEvent:
    """Record one audit event. Single entry point per §10.3.

    Invariants enforced here:
    - When `prompt_sha` is provided, `paragraph_ids` must be non-empty (§3.2).
    - `payload` is for non-PII operational metadata only — callers must reference
      entities by ID, not by extracted text.
    """
    if prompt_sha is not None and not paragraph_ids:
        raise AuditInvariantError(
            "audit event with prompt_sha must carry non-empty paragraph_ids (§3.2)"
        )

    now = datetime.now(timezone.utc)
    event = AuditEvent(
        id=uuid4(),
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        payload=payload,
        prompt_sha=prompt_sha,
        model_id=model_id,
        temperature=temperature,
        rule_engine_version=rule_engine_version,
        paragraph_ids=list(paragraph_ids or []),
        created_at=now,
        updated_at=now,
    )
    _events.append(event)
    _log.info(
        "audit_event",
        event_id=str(event.id),
        event_type=event_type.value,
        entity_type=entity_type.value,
        entity_id=str(entity_id),
        prompt_sha=prompt_sha,
        paragraph_count=len(event.paragraph_ids),
        payload=event.payload,
    )
    return event


def get_events() -> list[AuditEvent]:
    """Read-only view of the in-memory audit log. Test-only convenience."""
    return list(_events)


def clear_events() -> None:
    """Reset the in-memory store. Test-only."""
    _events.clear()


# Phase B4: directive extraction event helpers ------------------------------
#
# Four event kinds, all routed through the single `record(...)` writer per
# §10.3 invariant. The `payload["stage"]` key distinguishes them in the log
# and on the wire. Helpers exist so the directive parser does not have to
# rebuild ActorRef + UUIDv5 plumbing on every call.

_DIRECTIVE_AUDIT_ACTOR = ActorRef(
    kind=ActorKind.SYSTEM, id=uuid4(), designation=None
)


def _directive_entity_uuid(case_number: str, paragraph_index: int) -> UUID:
    return uuid5(
        NAMESPACE_OID, f"{case_number}/p{paragraph_index}/directive"
    )


def directive_extraction_raw(
    *,
    case_number: str,
    paragraph_index: int,
    model: str,
    prompt_sha: str,
    raw_output: str,
) -> AuditEvent:
    """Audit one raw LLM response for directive extraction. The raw output
    is captured verbatim so the rejection path below can be reconstructed
    even if the parser code changes."""
    entity = _directive_entity_uuid(case_number, paragraph_index)
    return record(
        AuditEventType.EXTRACTION_COMPLETED,
        EntityType.OPERATIVE_DIRECTION,
        entity,
        _DIRECTIVE_AUDIT_ACTOR,
        {
            "stage": "directive_extraction_raw",
            "case_number": case_number,
            "paragraph_index": paragraph_index,
            "raw_output": raw_output,
        },
        prompt_sha=prompt_sha,
        model_id=model,
        temperature=0.0,
        paragraph_ids=[entity],
    )


def directive_extraction_constructed(
    *,
    case_number: str,
    paragraph_index: int,
    directive_summary: dict[str, Any],
) -> AuditEvent:
    """Audit one successfully constructed directive. The summary captures
    actor_resolved, verb, verbatim_text, and time_clause for downstream
    reproducibility — no PII beyond what the source paragraph already
    contains."""
    entity = _directive_entity_uuid(case_number, paragraph_index)
    return record(
        AuditEventType.EXTRACTION_COMPLETED,
        EntityType.OPERATIVE_DIRECTION,
        entity,
        _DIRECTIVE_AUDIT_ACTOR,
        {
            "stage": "directive_extraction_constructed",
            "case_number": case_number,
            "paragraph_index": paragraph_index,
            "directive": directive_summary,
        },
    )


def directive_extraction_rejected(
    *,
    case_number: str,
    paragraph_index: int,
    rejected_payload: dict[str, Any],
    reason: str,
) -> AuditEvent:
    """Audit one rejected directive payload. `reason` is the guard message
    (substring/voice/section/actor/verb). The full rejected payload is
    preserved so the prompt+model+payload triple is fully reconstructible."""
    entity = _directive_entity_uuid(case_number, paragraph_index)
    return record(
        AuditEventType.EXTRACTION_COMPLETED,
        EntityType.OPERATIVE_DIRECTION,
        entity,
        _DIRECTIVE_AUDIT_ACTOR,
        {
            "stage": "directive_extraction_rejected",
            "case_number": case_number,
            "paragraph_index": paragraph_index,
            "rejected_payload": rejected_payload,
            "reason": reason,
        },
    )


def directive_extraction_failure(
    *,
    case_number: str,
    paragraph_index: int,
    model: str,
    prompt_sha: str,
    error: str,
) -> AuditEvent:
    """Audit a hard LLM failure (unreachable, schema rejection at the client
    layer). Distinct from `directive_extraction_rejected` which captures
    per-directive grounding failures after a successful LLM response."""
    entity = _directive_entity_uuid(case_number, paragraph_index)
    return record(
        AuditEventType.EXTRACTION_FAILED,
        EntityType.OPERATIVE_DIRECTION,
        entity,
        _DIRECTIVE_AUDIT_ACTOR,
        {
            "stage": "directive_extraction_failure",
            "case_number": case_number,
            "paragraph_index": paragraph_index,
            "error": error,
        },
        prompt_sha=prompt_sha,
        model_id=model,
        temperature=0.0,
        paragraph_ids=[entity],
    )
