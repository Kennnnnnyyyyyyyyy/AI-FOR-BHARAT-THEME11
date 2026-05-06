# Venkateshulu canonical fixture (WP 13296/2022)

This is the **primary** canonical case per CLAUDE.md §5.2 — it must work end-to-end for
the demo on 2026-05-07.

## Files

- `paragraphs.json` — pre-segmented paragraphs (the §4.2 prototype expedient that
  bypasses Surya OCR). Each entry matches `kartavya.schemas.paragraph.Paragraph`.
- `expected_extraction.json` — ground truth used by integration tests. Schema:

  ```jsonc
  {
    "paragraph_labels": [{"paragraph_index": 0, "label": "contextual"}, ...],
    "verdict": "dismissed",
    "operative_direction_paragraph_indices": [20, 21, 22]
  }
  ```

  Labels follow the operational taxonomy in `ParagraphLabel` (§10.1):
  `operative` / `contextual` / `procedural`.

## Provenance of this fixture

The text below is a **structural placeholder** that mirrors the 24-paragraph layout
of the real Venkateshulu judgment described in `KARTAVYA_DRIFT_ANALYSIS.md`
(20 contextual, 4 operative — the operative bucket subsumes both forward-looking
directions and the verdict-statement paragraph). The exact wording is paraphrased.

Before the demo gate run, replace `paragraphs.json` with text extracted from the
real PDF (`original.pdf`) using `kartavya/ingestion/text.py`. The integration test
will continue to pass against the real text as long as `expected_extraction.json`
is updated to match.

UUIDs are deterministic: `00000000-0000-0000-0000-{paragraph_index:012d}` so
re-running gives bit-identical anchors.
