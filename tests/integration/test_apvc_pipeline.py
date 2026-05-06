"""End-to-end APVC pipeline test against the Venkateshulu canonical fixture.

Marked `live_ollama` — requires a local Ollama server with `llama3.1:8b-instruct-q4_K_M`
pulled. Run with:

    pytest tests/integration/test_apvc_pipeline.py -m live_ollama -q

Skipped automatically when Ollama is not reachable so the unit suite stays clean.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from kartavya.audit import recorder as audit
from kartavya.extraction import pipeline
from kartavya.extraction.client import OllamaClient
from kartavya.schemas.paragraph import Paragraph

FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "venkateshulu_wp13296_2022"
)

ACCURACY_GATE = 0.90  # CLAUDE.md §12 Day-1 gate


def _ollama_reachable() -> bool:
    """Best-effort check: does an Ollama daemon answer on localhost?"""
    import httpx

    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        httpx.get(f"{host}/api/tags", timeout=2.0)
        return True
    except Exception:
        return False


@pytest.fixture
def paragraphs() -> list[Paragraph]:
    raw = json.loads((FIXTURE_DIR / "paragraphs.json").read_text())
    return [Paragraph.model_validate(item) for item in raw]


@pytest.fixture
def expected() -> dict:
    return json.loads((FIXTURE_DIR / "expected_extraction.json").read_text())


@pytest.mark.live_ollama
@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not reachable")
def test_apvc_pipeline_meets_accuracy_gate(
    paragraphs: list[Paragraph], expected: dict
) -> None:
    case_id = uuid4()
    client = OllamaClient()

    result = pipeline.extract(case_id, paragraphs, client)

    # 1. Paragraph classification accuracy
    label_by_index = {
        p.paragraph_index: c.label.value
        for p, c in zip(paragraphs, result.paragraph_classifications, strict=True)
    }
    expected_labels = {
        item["paragraph_index"]: item["label"] for item in expected["paragraph_labels"]
    }
    matches = sum(
        1
        for idx, expected_label in expected_labels.items()
        if label_by_index.get(idx) == expected_label
    )
    accuracy = matches / len(expected_labels)
    print(f"\nparagraph accuracy: {matches}/{len(expected_labels)} = {accuracy:.2%}")

    # 2. Verdict exact match
    assert result.verdict.verdict.value == expected["verdict"], (
        f"verdict mismatch: got {result.verdict.verdict.value}, "
        f"expected {expected['verdict']}"
    )

    # 3. No directives extracted from forbidden paragraphs (Type-C past-tense check)
    forbidden_ids: set[UUID] = {
        p.id
        for p in paragraphs
        if p.paragraph_index in expected["must_not_extract_directives_from_paragraph_indices"]
    }
    leaked = [
        d for d in result.operative_directions if d.paragraph_id in forbidden_ids
    ]
    assert not leaked, (
        f"operative extractor leaked from past-tense paragraphs: "
        f"{[str(d.paragraph_id) for d in leaked]}"
    )

    # 4. Audit invariants
    events = audit.get_events()
    assert any(
        e.event_type.value == "extraction_completed" for e in events
    ), "no completion event recorded"
    for event in events:
        if event.prompt_sha is not None:
            assert event.paragraph_ids, "audit event with prompt_sha must carry paragraph_ids"

    # 5. Accuracy gate (last so failures above surface first)
    assert accuracy >= ACCURACY_GATE, (
        f"paragraph accuracy {accuracy:.2%} below gate {ACCURACY_GATE:.0%}; "
        f"see audit log for per-chunk diagnostics"
    )
