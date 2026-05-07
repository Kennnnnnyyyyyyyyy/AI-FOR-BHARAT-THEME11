"""Pydantic v2 contract layer. Every cross-module data shape lives here (§3.8, §9).

Phase A added (`Action`, `ActionPlan`, `ActionKind`, `TargetRoleId`,
`ParsedJudgment`, `GroundedParagraph`, `OperativeDirective`, `TimeClause`,
`VerdictClass`, `Voice`, `SectionClass`, `VoiceSpan`) for the 0.2.0 rules
engine path. The legacy 0.1.0 types (`ActionItem`, `LegacyActionPlan`,
`OperativeDirection`) coexist for one cycle.
"""

from kartavya.schemas.action_plan import (
    Action,
    ActionItem,
    ActionKind,
    ActionPlan,
    LegacyActionPlan,
    RuleTrace,
    Severity,
    TargetRoleId,
)
from kartavya.schemas.audit import (
    ActorKind,
    ActorRef,
    AuditEvent,
    AuditEventType,
    EntityType,
)
from kartavya.schemas.case import (
    AdditionalForum,
    CaseMetadata,
    Petitioner,
    Respondent,
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
from kartavya.schemas.parsed_judgment import (
    GroundedParagraph,
    OperativeDirective,
    ParsedJudgment,
    TimeClause,
    VerdictClass,
)
from kartavya.schemas.provenance import ExtractionProvenance
from kartavya.schemas.voice import SectionClass, Voice, VoiceSpan

__all__ = [
    "Action",
    "ActionItem",
    "ActionKind",
    "ActionPlan",
    "ActorKind",
    "ActorRef",
    "AdditionalForum",
    "AuditEvent",
    "AuditEventType",
    "CaseMetadata",
    "ConfidenceTier",
    "EntityType",
    "ExtractionProvenance",
    "ExtractionResult",
    "GroundedParagraph",
    "HIGH_STAKES_FIELDS",
    "LegacyActionPlan",
    "OperativeDirection",
    "OperativeDirective",
    "Paragraph",
    "ParagraphClassification",
    "ParagraphLabel",
    "ParsedJudgment",
    "Petitioner",
    "Respondent",
    "RuleTrace",
    "SectionClass",
    "Severity",
    "TargetRoleId",
    "TimeClause",
    "Verdict",
    "VerdictClass",
    "VerdictClassification",
    "Voice",
    "VoiceSpan",
    "confidence_thresholds",
    "high_stakes_confidence_thresholds",
    "is_high_stakes_field",
]
