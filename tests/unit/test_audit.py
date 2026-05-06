"""Tests for kartavya/audit/recorder.py — invariants only (no DB in prototype)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from kartavya.audit import recorder as audit
from kartavya.errors import AuditInvariantError
from kartavya.schemas.audit import (
    ActorKind,
    ActorRef,
    AuditEventType,
    EntityType,
)


def _actor() -> ActorRef:
    return ActorRef(kind=ActorKind.SYSTEM, id=uuid4(), designation="test")


def test_record_appends_event() -> None:
    case_id = uuid4()
    para_id = uuid4()
    event = audit.record(
        event_type=AuditEventType.EXTRACTION_STARTED,
        entity_type=EntityType.CASE,
        entity_id=case_id,
        actor=_actor(),
        payload={"task": "test"},
        paragraph_ids=[para_id],
    )
    assert event.entity_id == case_id
    assert audit.get_events()[-1] is event


def test_prompt_sha_requires_paragraph_ids() -> None:
    with pytest.raises(AuditInvariantError):
        audit.record(
            event_type=AuditEventType.EXTRACTION_COMPLETED,
            entity_type=EntityType.CASE,
            entity_id=uuid4(),
            actor=_actor(),
            payload={},
            prompt_sha="a" * 64,
            paragraph_ids=[],  # empty — invariant violation
        )


def test_prompt_sha_with_paragraph_ids_succeeds() -> None:
    audit.record(
        event_type=AuditEventType.EXTRACTION_COMPLETED,
        entity_type=EntityType.CASE,
        entity_id=uuid4(),
        actor=_actor(),
        payload={},
        prompt_sha="a" * 64,
        paragraph_ids=[uuid4()],
    )


def test_no_prompt_sha_no_invariant() -> None:
    audit.record(
        event_type=AuditEventType.EXTRACTION_STARTED,
        entity_type=EntityType.CASE,
        entity_id=uuid4(),
        actor=_actor(),
        payload={},
        paragraph_ids=[],
    )
