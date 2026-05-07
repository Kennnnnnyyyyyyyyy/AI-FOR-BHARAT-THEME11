---
task: operative_extractor
version: 2
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: _RawDirections
---
You are extracting **operative directions** issued by a Karnataka High Court.

An operative direction is a forward-looking order the court is issuing **right now** to a party, requiring the party to do or refrain from doing something.

## Output format

```json
{
  "directions": [
    {
      "anchor": "<paragraph anchor exactly as given>",
      "text": "<your concise rephrasing of the directive>",
      "source_span": "<verbatim substring of THAT paragraph that contains the directive>",
      "confidence": 0.0_to_1.0
    }
  ]
}
```

If a paragraph contains no operative direction, do not produce an entry for it.

## What IS an operative direction

Forward-looking imperatives issued by THIS court in THIS judgment:

- "the respondents are directed to refund within 60 days"
- "the petitioner shall file fresh objections within four weeks"
- "the second respondent is required to pass a reasoned order within three months"
- "the impugned order is set aside"
- "the writ petition is dismissed with costs"

## What IS NOT an operative direction (do NOT extract these)

**Past-tense recitals** of orders issued by other authorities or earlier in the proceedings. Test: if the paragraph describes something that already happened (using "was", "were", "had been"), it is a fact recital, not a current directive.

Reject patterns:
- "Notice was issued for implementation of..." → factual recital, NOT a directive
- "The respondents had been directed to..." → past order from another forum, NOT this court's current directive
- "The Land Acquisition Officer was instructed by the State to..." → narrative of past events
- "An order had previously been passed..." → background fact

**Counsel's submissions** ("the petitioner prays that..."), **statutory text** quoted as authority, and **the court's reasoning** ("we are of the view that...") are also not operative directions.

## Rules

- The `anchor` field MUST be copied character-for-character from the `=== PARAGRAPH ...` header above the paragraph body. The anchor is an identifier of the form `P###-XXXXXXXX` (three-digit paragraph index, dash, eight hex characters). Do not invent, abbreviate, paraphrase, reorder, or concatenate anchor strings. The literal text `<paragraph anchor exactly as given>` shown in the JSON shape above is a placeholder marker, NOT the value to emit — replace it with the actual anchor from the paragraph header.
- `source_span` MUST be a verbatim substring of the paragraph identified by `anchor`. The `text` field is your own concise summary; the `source_span` is the proof. The two are different fields and serve different purposes — `anchor` says which paragraph, `source_span` says which words inside that paragraph.
- When in doubt about past-tense vs current, leave the direction out and note lower confidence elsewhere — false positives are worse than false negatives here.

## Worked example

Input (illustrative — these anchor and paragraph values are fabricated for demonstration):

```
=== PARAGRAPH P042-1a2b3c4d ===
Having considered the rival contentions, we direct the third respondent to refund the excess fee of Rs. 4,500 to the petitioner within a period of thirty days from the date of receipt of a copy of this order, failing which interest at 6% per annum shall accrue.

=== PARAGRAPH P043-9f8e7d6c ===
Notice dated 12.03.2018 was issued by the second respondent for resumption of the unauthorised allotment, and the matter is stated to be pending consideration before the appellate authority.
```

Expected output:

```json
{
  "directions": [
    {
      "anchor": "P042-1a2b3c4d",
      "text": "Third respondent to refund Rs. 4,500 to petitioner within 30 days; 6% interest on default.",
      "source_span": "we direct the third respondent to refund the excess fee of Rs. 4,500 to the petitioner within a period of thirty days from the date of receipt of a copy of this order",
      "confidence": 0.95
    }
  ]
}
```

Notes on the example:
- `P042-1a2b3c4d` is the literal value of the anchor — copied character-for-character from the paragraph header — not a placeholder.
- `P043-9f8e7d6c` produces no output entry: it is a past-tense recital of a prior administrative act, not a current directive of this court.
- `text` is a concise officer-readable summary; `source_span` is a verbatim quote that proves the directive is in the paragraph body.

## Paragraphs

{{PARAGRAPHS}}
