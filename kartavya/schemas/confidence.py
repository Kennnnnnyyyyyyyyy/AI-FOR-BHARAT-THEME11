"""Confidence tiering — three-tier thresholds with high-stakes overrides; canonical home per §10.5."""

from enum import Enum


class ConfidenceTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


HIGH_STAKES_FIELDS: frozenset[str] = frozenset(
    {
        "financial_exposure",
        "service_matter",
        "contempt_implication",
    }
)


confidence_thresholds: dict[ConfidenceTier, tuple[float, float]] = {
    ConfidenceTier.HIGH: (0.85, 1.0),
    ConfidenceTier.MEDIUM: (0.6, 0.85),
    ConfidenceTier.LOW: (0.0, 0.6),
}


high_stakes_confidence_thresholds: dict[ConfidenceTier, tuple[float, float]] = {
    ConfidenceTier.HIGH: (0.95, 1.0),
    ConfidenceTier.MEDIUM: (0.6, 0.95),
    ConfidenceTier.LOW: (0.0, 0.6),
}


def is_high_stakes_field(field_name: str) -> bool:
    return field_name in HIGH_STAKES_FIELDS
