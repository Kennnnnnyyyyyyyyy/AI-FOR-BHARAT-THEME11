---
task: paragraph_classifier
version: 1
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: ChunkClassifications
---
You are classifying paragraphs from a Karnataka High Court judgment.
For each paragraph marked `[CLASSIFY]` you must return exactly one classification entry.
Paragraphs marked `[CONTEXT-ONLY]` are provided for context only — do NOT classify them; do not include them in your output.

## Output format

Return a single JSON object with this exact shape:

```json
{
  "classifications": [
    {"anchor": "<paragraph anchor exactly as given>", "label": "<one of the six labels>", "confidence": 0.0_to_1.0, "source_span": "<verbatim excerpt from THIS paragraph>"}
  ]
}
```

Rules:
- The `anchor` field MUST be copied character-for-character from the `[CLASSIFY]` header. Do not invent, abbreviate, or reorder anchors.
- `source_span` MUST be a verbatim substring of the paragraph that carries the same anchor. Never quote text from a different paragraph.
- `confidence` is your subjective certainty in [0.0, 1.0]. Use lower values when the paragraph could plausibly fit two labels.
- Output exactly one entry per `[CLASSIFY]` paragraph, in the same order.

## Labels (decision tree)

Apply these in order. The first match wins.

1. **decree** — The paragraph announces the court's final disposition: "the writ petition is dismissed", "the appeal is allowed", "ordered accordingly". Final-sentence character. Usually at the very end.
2. **operative** — The paragraph contains a forward-looking direction the court is ISSUING NOW to a party: "the respondents are directed to refund within 60 days", "the petitioner shall file fresh objections". Verbs are imperative or future ("shall", "must", "is/are directed to"). Past-tense recitals of earlier orders ("notice was issued", "had been directed") are NOT operative — those are facts.
3. **reasoning** — The court's own analysis, weighing of arguments, application of law to facts. Phrases like "we are of the view that", "having considered", "it follows that". The court speaking in its own voice.
4. **precedent** — Discussion of prior judgments cited as authority: case names, "in [Citation], the Supreme Court held...". Even if the paragraph is partly reasoning, classify as **precedent** when its primary function is to introduce or apply a cited case.
5. **arguments** — Submissions made by counsel for either side: "learned counsel for the petitioner submits", "the respondents contend". The voice belongs to a party, not the court.
6. **facts** — Background, procedural history, who-did-what-when. Default category for narrative paragraphs that are neither arguments nor reasoning. Past-tense recitals of prior orders/notices belong here.

If a paragraph plausibly fits two labels, prefer the lower-numbered (more specific) one and lower the confidence accordingly.

## Worked example

Input:
```
=== PARAGRAPH P003-aaaa1111 [CONTEXT-ONLY] ===
The petitioner submits that the impugned notice is without jurisdiction...

=== PARAGRAPH P004-bbbb2222 [CLASSIFY] ===
Learned counsel for the State, per contra, contends that the notice was issued strictly in conformity with Section 12 of the Act and the petitioner had ample opportunity to respond.

=== PARAGRAPH P005-cccc3333 [CLASSIFY] ===
Having heard learned counsel on both sides and perused the record, we are of the view that the impugned notice is sustainable. The petitioner's grievance is, in substance, against the merits of the order, which is not the proper subject of writ jurisdiction.
```

Output:
```json
{
  "classifications": [
    {"anchor": "P004-bbbb2222", "label": "arguments", "confidence": 0.94, "source_span": "Learned counsel for the State, per contra, contends that the notice was issued strictly in conformity with Section 12"},
    {"anchor": "P005-cccc3333", "label": "reasoning", "confidence": 0.91, "source_span": "we are of the view that the impugned notice is sustainable. The petitioner's grievance is, in substance, against the merits of the order"}
  ]
}
```

Note that `P003-aaaa1111` is `[CONTEXT-ONLY]` and produces no entry.

## Now classify

{{CHUNK_BODY}}
