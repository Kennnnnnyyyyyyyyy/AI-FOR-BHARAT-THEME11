"""Pydantic v2 contract layer — every cross-module data shape lives here (§3.8, §9)."""

from kartavya.schemas.action_plan import (
    ActionItem,
    ActionPlan,
    RuleTrace,
    Severity,
)
from kartavya.schemas.audit import (
    ActorKind,
    ActorRef,
    AuditEvent,
    AuditEventType,
    EntityType,
)
from kartavya.schemas.confidence import (
    HIGH_STAKES_FIELDS,
    ConfidenceTier,
    confidence_thresholds,
    high_stakes_confidence_thresholds,
    is_high_stakes_field,
)
from kartavya.schemas.extraction import (
    ExtractionResult,
    OperativeDirection,
    ParagraphClassification,
    ParagraphLabel,
    Verdict,
    VerdictClassification,
)
from kartavya.schemas.paragraph import Paragraph
from kartavya.schemas.provenance import ExtractionProvenance

__all__ = [
    "ActionItem",
    "ActionPlan",
    "ActorKind",
    "ActorRef",
    "AuditEvent",
    "AuditEventType",
    "ConfidenceTier",
    "EntityType",
    "ExtractionProvenance",
    "ExtractionResult",
    "HIGH_STAKES_FIELDS",
    "OperativeDirection",
    "Paragraph",
    "ParagraphClassification",
    "ParagraphLabel",
    "RuleTrace",
    "Severity",
    "Verdict",
    "VerdictClassification",
    "confidence_thresholds",
    "high_stakes_confidence_thresholds",
    "is_high_stakes_field",
]
