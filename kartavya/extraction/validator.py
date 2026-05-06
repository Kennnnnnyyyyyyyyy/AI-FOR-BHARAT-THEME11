"""Non-LLM validator for APVC outputs (§3.4, §3.6).

Checks each `ParagraphClassificationRaw` against three deterministic conditions:

1. The echoed anchor exists in the chunk's anchor map.
2. The resolved paragraph belongs to the chunk's centre set
   (overlap-paragraph entries are silently discarded — expected leakage).
3. The `source_span` is a verbatim substring of the resolved paragraph.

Failures are returned as `ValidationFailure` records, NOT raised — the pipeline
queues them for selective singleton retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from kartavya.extraction.anchors import (
    ParagraphClassificationRaw,
    normalize,
)
from kartavya.extraction.client import CallMetadata
from kartavya.schemas.extraction import ParagraphClassification
from kartavya.schemas.paragraph import Paragraph
from kartavya.schemas.provenance import ExtractionProvenance


class FailureReason(str, Enum):
    ANCHOR_NOT_FOUND = "anchor_not_found"
    SPAN_MISMATCH = "span_mismatch"


@dataclass(frozen=True)
class ValidationFailure:
    """A raw output the validator could not accept; queued for singleton retry."""

    reason: FailureReason
    raw: ParagraphClassificationRaw
    paragraph: Paragraph | None  # None when anchor doesn't resolve at all


def _build_provenance(
    paragraph: Paragraph,
    confidence: float,
    source_span: str,
    metadata: CallMetadata,
) -> ExtractionProvenance:
    return ExtractionProvenance(
        source_span=source_span,
        paragraph_id=paragraph.id,
        bounding_box=paragraph.bounding_box,
        confidence=confidence,
        prompt_sha=metadata.prompt_sha,
        model_id=metadata.model_id,
        temperature=metadata.temperature,
        extracted_at=metadata.extracted_at,
    )


def _span_in_paragraph(span: str, paragraph_text: str) -> bool:
    """Substring check tolerant to whitespace normalisation.

    Accept a span if its normalised form occurs in the normalised paragraph
    text. This keeps trivial whitespace/casing differences from triggering a
    retry while still catching real cross-paragraph leaks.
    """
    return normalize(span) in normalize(paragraph_text)


def validate_chunk(
    raw_outputs: list[ParagraphClassificationRaw],
    anchor_map: dict[str, Paragraph],
    centre_uuids: set[UUID],
    metadata: CallMetadata,
) -> tuple[list[ParagraphClassification], list[ValidationFailure]]:
    """Resolve raw outputs into validated `ParagraphClassification` records.

    Outputs whose anchor is in `anchor_map` but whose paragraph is NOT in
    `centre_uuids` are silently discarded (the model classified an overlap
    paragraph; the centre chunk it belongs to will handle it).
    """
    accepted: list[ParagraphClassification] = []
    failures: list[ValidationFailure] = []

    for raw in raw_outputs:
        paragraph = anchor_map.get(raw.anchor)
        if paragraph is None:
            failures.append(
                ValidationFailure(
                    reason=FailureReason.ANCHOR_NOT_FOUND,
                    raw=raw,
                    paragraph=None,
                )
            )
            continue

        if paragraph.id not in centre_uuids:
            continue  # overlap leak — discard silently

        if not _span_in_paragraph(raw.source_span, paragraph.text):
            failures.append(
                ValidationFailure(
                    reason=FailureReason.SPAN_MISMATCH,
                    raw=raw,
                    paragraph=paragraph,
                )
            )
            continue

        accepted.append(
            ParagraphClassification(
                paragraph_id=paragraph.id,
                label=raw.label,
                confidence=raw.confidence,
                provenance=_build_provenance(
                    paragraph, raw.confidence, raw.source_span, metadata
                ),
            )
        )

    return accepted, failures


def force_low_confidence(
    paragraph: Paragraph,
    raw: ParagraphClassificationRaw | None,
    metadata: CallMetadata,
) -> ParagraphClassification:
    """Build a `ParagraphClassification` with confidence forced to 0.0 (LOW tier).

    Used when a paragraph fails validation twice. The label falls back to
    `contextual` (the §10.1 default non-actionable category) if the model
    never returned a usable raw entry; otherwise we keep the model's label
    so the reviewer sees what the model thought, and the LOW tier blocks
    plan approval per §10.5.
    """
    from kartavya.schemas.extraction import ParagraphLabel

    label = raw.label if raw is not None else ParagraphLabel.CONTEXTUAL
    return ParagraphClassification(
        paragraph_id=paragraph.id,
        label=label,
        confidence=0.0,
        provenance=ExtractionProvenance(
            source_span=raw.source_span if raw is not None else paragraph.text[:120],
            paragraph_id=paragraph.id,
            bounding_box=paragraph.bounding_box,
            confidence=0.0,
            prompt_sha=metadata.prompt_sha,
            model_id=metadata.model_id,
            temperature=metadata.temperature,
            extracted_at=metadata.extracted_at,
        ),
    )
