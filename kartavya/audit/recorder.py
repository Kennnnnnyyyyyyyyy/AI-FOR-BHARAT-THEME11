"""Append-only audit recorder — the single writer to `audit_events` (§3.2, §10.3).

In PROTOTYPE phase the events live in an in-memory list and are also emitted to
structlog. The §10.3 contract (signature, invariants, return shape) is preserved
so the production swap-in to a SQLAlchemy session is mechanical.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import structlog

from kartavya.errors import AuditInvariantError
from kartavya.schemas.audit import (
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
    )
    return event


def get_events() -> list[AuditEvent]:
    """Read-only view of the in-memory audit log. Test-only convenience."""
    return list(_events)


def clear_events() -> None:
    """Reset the in-memory store. Test-only."""
    _events.clear()
