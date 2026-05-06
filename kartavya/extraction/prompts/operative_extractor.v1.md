---
task: operative_extractor
version: 1
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
      "anchor": "<paragraph anchor copied verbatim>",
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

- `source_span` MUST be a verbatim substring of the paragraph identified by `anchor`.
- The `text` field is your own concise summary; the `source_span` is the proof.
- When in doubt about past-tense vs current, leave the direction out and note lower confidence elsewhere — false positives are worse than false negatives here.

## Paragraphs

{{PARAGRAPHS}}
