---
task: operative_extractor
version: 3
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: _RawDirections
---
You are extracting **operative directions** issued by a Karnataka High Court.

An operative direction is a forward-looking order the court is issuing **right now** to a party, requiring the party to do or refrain from doing something.

## Polite imperatives are still directives

When a court directs an inter-court or inter-agency action using softer language — "the reference court is requested to...", "the second respondent may be pleased to...", "the appellate authority may consider..." — the softness is judicial courtesy, not lack of force. If the court is the speaker, the action is forward-looking, and an obligation with a temporal trigger is created (a deadline, a due date, "expeditiously"), it is a directive regardless of phrasing politeness. Do not confuse courtesy with optionality.

Example:
> The reference court is requested to dispose of the pending reference under Section 30 of the Act expeditiously and, in any event, within a period of six months from the date of communication of this order.

This is a directive. Speaker: the court. Action: forward-looking ("dispose of the pending reference"). Obligation with deadline: yes ("within a period of six months"). The "is requested to" form does not negate directive status.

## Dispositions are out of scope

The verdict itself — whether the writ petition is dismissed, allowed, partly allowed, disposed of with directions, or remanded — is captured by the verdict classifier as a verdict statement, not by this extractor. Dispositions generate their downstream deadline obligations (for example, the Article 136 SLP window after a dismissal) through the verdict signal, not through a directive.

If a paragraph's primary content is announcing the writ petition's fate, it belongs to the verdict classifier. **Do not emit a directive object for a disposition**, even when the disposition appears in a paragraph that also contains operative-style language ("Ordered accordingly").

The two stages are complementary, not overlapping: the directive extractor produces forward-looking actor obligations; the verdict classifier produces the disposition. One signal each, no double-counting.

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
- "the reference court is requested to dispose of the pending reference within six months" (polite imperative — see above)
- "the impugned order is set aside" (operative remedy directed by this court)

## What IS NOT an operative direction (do NOT extract these)

**Past-tense recitals** of orders issued by other authorities or earlier in the proceedings. Test: if the paragraph describes something that already happened (using "was", "were", "had been"), it is a fact recital, not a current directive.

Reject patterns:
- "Notice was issued for implementation of..." → factual recital, NOT a directive
- "The respondents had been directed to..." → past order from another forum, NOT this court's current directive
- "The Land Acquisition Officer was instructed by the State to..." → narrative of past events
- "An order had previously been passed..." → background fact

**Counsel's submissions** ("the petitioner prays that..."), **statutory text** quoted as authority, and **the court's reasoning** ("we are of the view that...") are also not operative directions.

## Negative examples (out of scope)

These paragraphs say something that *sounds* dispositive but the directive extractor must NOT emit a directive for them. They are captured elsewhere or by other stages.

> "Subject to the directions issued in the preceding paragraphs, the writ petition is dismissed. There shall be no order as to costs. Ordered accordingly."

This is a **disposition**, not a directive. The verdict classifier captures this signal as `dismissed` and feeds it to deadline calculation. The "Ordered accordingly" tail does not make the paragraph a directive — it confirms the disposition that precedes it. Emit no directive for this paragraph.

> "The appeal is allowed and the impugned order of the Tribunal is set aside."

The first clause ("the appeal is allowed") is a disposition — captured by the verdict classifier, not here. The second clause ("the impugned order of the Tribunal is set aside") is the operative remedy and IS a directive of this court. Emit a directive for the set-aside; do not emit one for the allowance. When a paragraph carries both, scope each clause separately.

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
