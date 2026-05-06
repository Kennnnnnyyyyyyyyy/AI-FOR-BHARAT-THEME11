---
task: verdict_classifier
version: 1
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: _RawVerdict
---
You are identifying the final verdict of a Karnataka High Court judgment.

The verdict is the court's overall disposition of the petition, typically stated near the end of the judgment in the decree paragraph(s).

## Output format

Return a single JSON object:

```json
{
  "verdict": "<one of: allowed | dismissed | partly_allowed | disposed_with_directions | remanded>",
  "confidence": 0.0_to_1.0,
  "source_span": "<verbatim excerpt from the judgment that announces the verdict>",
  "source_anchor": "<the anchor of the paragraph the source_span was taken from>"
}
```

## Verdict definitions

- **allowed** — The petition succeeds: the impugned action is set aside, quashed, or struck down; relief is granted to the petitioner.
- **dismissed** — The petition fails: the impugned action stands; no relief is granted.
- **partly_allowed** — The petition succeeds on some grounds but not others; some relief is granted, some refused.
- **disposed_with_directions** — The petition is closed without an outright allow/dismiss verdict, with the court issuing directions to the parties (often a settlement-style resolution).
- **remanded** — The matter is sent back to a lower court or tribunal for reconsideration.

## Rules

- The `source_span` MUST be a verbatim substring of the paragraph identified by `source_anchor`.
- Prefer a span that contains the operative verb of disposition ("dismissed", "allowed", "set aside", "quashed", "remanded for fresh consideration").
- If multiple paragraphs announce parts of the disposition, pick the one with the clearest top-level verdict.

## Paragraphs

{{PARAGRAPHS}}
