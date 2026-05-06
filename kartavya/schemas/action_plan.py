"""ActionPlan and supporting schemas — outputs of the rules engine; deadlines computed deterministically (§3.1)."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class Severity(str, Enum):
    ACTIVE = "active"
    DEFENSIVE = "defensive"
    INFORMATIONAL = "informational"


class RuleTrace(BaseModel):
    rule_id: str
    rule_version: str
    statute: str
    triggered_by: dict[str, Any]
    computation: str


class ActionItem(BaseModel):
    id: UUID
    description: str
    target_role: str
    deadline: datetime | None
    severity: Severity
    rule_trace: RuleTrace


class ActionPlan(BaseModel):
    id: UUID
    case_id: UUID
    action_items: list[ActionItem]
    rule_engine_version: str
    generated_at: datetime
