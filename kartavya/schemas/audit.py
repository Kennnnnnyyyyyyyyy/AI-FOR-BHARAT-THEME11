"""AuditEvent and supporting types — the append-only audit trail (§3.2)."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditEventType(str, Enum):
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_COMPLETED = "extraction_completed"
    EXTRACTION_FAILED = "extraction_failed"
    ACTION_PLAN_GENERATED = "action_plan_generated"
    ACTION_PLAN_REVIEWED = "action_plan_reviewed"
    ACTION_PLAN_COMMITTED = "action_plan_committed"


class EntityType(str, Enum):
    CASE = "case"
    PARAGRAPH = "paragraph"
    OPERATIVE_DIRECTION = "operative_direction"
    ACTION_PLAN = "action_plan"
    ACTION_ITEM = "action_item"


class ActorKind(str, Enum):
    OFFICER = "officer"
    SYSTEM = "system"


class ActorRef(BaseModel):
    kind: ActorKind
    id: UUID
    designation: str | None


class AuditEvent(BaseModel):
    id: UUID
    event_type: AuditEventType
    entity_type: EntityType
    entity_id: UUID
    actor: ActorRef
    payload: dict[str, Any]
    prompt_sha: str | None
    model_id: str | None
    temperature: float | None
    rule_engine_version: str | None
    paragraph_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
