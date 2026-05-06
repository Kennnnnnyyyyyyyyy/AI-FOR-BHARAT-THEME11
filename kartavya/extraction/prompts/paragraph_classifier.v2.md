---
task: paragraph_classifier
version: 2
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: ParagraphClassification
---
You are classifying paragraphs from a Karnataka High Court (KHC) judgment.
For each paragraph marked `[CLASSIFY]` you must return exactly one classification entry.
Paragraphs marked `[CONTEXT-ONLY]` are provided for context only — do NOT classify them; do not include them in your output.

## Output format

Return a single JSON object with this exact shape:

```json
{
  "classifications": [
    {"anchor": "<paragraph anchor exactly as given>", "label": "<one of: operative, contextual, procedural>", "confidence": 0.0_to_1.0, "source_span": "<verbatim excerpt from THIS paragraph>"}
  ]
}
```

Rules:
- The `anchor` field MUST be copied character-for-character from the `[CLASSIFY]` header. Do not invent, abbreviate, or reorder anchors.
- `source_span` MUST be a verbatim substring of the paragraph that carries the same anchor. Never quote text from a different paragraph.
- `confidence` is your subjective certainty in [0.0, 1.0]. Use lower values when the paragraph could plausibly fit two labels.
- Output exactly one entry per `[CLASSIFY]` paragraph, in the same order.

## Operational taxonomy

You are not classifying by what the paragraph *talks about*; you are classifying by what the government officer reading the judgment must *do* with it. Indian judgments routinely braid facts, arguments, precedents, and reasoning into one block, so a content-based scheme misfires. Three labels suffice for the operational question.

- **operative** — The paragraph either (a) issues a forward-looking direction the court is making NOW to a party (verbs like "shall", "is/are directed to", "we direct", "is requested to dispose of"), or (b) states the court's final disposition — the verdict that triggers limitation calculation ("the writ petition is dismissed", "the appeal is allowed", "ordered accordingly", "disposed of with directions", "remanded"). This is the only label that feeds the rules engine. Past-tense recitals of EARLIER orders ("notice was issued", "an award came to be passed") are not operative — they describe history, they do not direct anything.
- **contextual** — The paragraph supports understanding of the case but generates no officer action. This single bucket subsumes what older taxonomies split into facts, arguments by counsel, discussion of precedents, and the court's own reasoning. If a careful reader could remove the paragraph and the action plan would be unchanged, it is contextual.
- **procedural** — Case metadata: cause-title, party listings ("PETITIONER: ... / RESPONDENTS: ..."), signature blocks, page headers/footers, footnote-only paragraphs, court letterhead, certificate-of-service blocks. These are skipped in officer review.

**If a paragraph contains both contextual material and an operative direction, label it OPERATIVE — operational role dominates.** A reasoning paragraph that culminates in "we therefore direct the second respondent to refund within sixty days" is operative; the upstream reasoning is along for the ride.

## Examples

### operative

POSITIVE 1:
> While declining to interfere with the acquisition itself, we direct the second respondent to ensure that the compensation amount along with all statutory benefits is disbursed to the petitioner within sixty days from the date of receipt of a copy of this order.

→ `operative`. Forward-looking direction ("we direct"), addressed to a respondent, with a concrete obligation.

POSITIVE 2:
> Subject to the directions issued in the preceding paragraphs, the writ petition is dismissed. There shall be no order as to costs. Ordered accordingly.

→ `operative`. Final disposition — the verdict that starts the limitation clock.

NEGATIVE (not operative):
> Notice dated 04.08.2015 was issued by the second respondent for implementation of the rehabilitation plan, and an award under Section 29(2) of the Act came to be passed on 17.12.2015 fixing compensation at a stated rate per acre.

→ `contextual`, not operative. Past-tense recital of an earlier administrative act. The court is not directing anything here.

### contextual

POSITIVE 1:
> The petitioner is the absolute owner of land measuring two acres and twenty guntas in Devanahalli Taluk, having purchased the same under a registered sale deed of 2007. A preliminary notification under Section 28(1) of the KIAD Act, 1966, was thereafter issued by the Board proposing to acquire the said land for an industrial area.

→ `contextual`. Background facts — necessary to follow the case, generates no officer obligation.

POSITIVE 2:
> Learned counsel for the petitioner submits that the impugned acquisition is vitiated by non-application of mind inasmuch as the objections under Section 28(2) were never considered on merits, and the final notification merely repeats the preliminary notification verbatim.

→ `contextual`. Counsel's submission. The court has not adopted it as a direction; it is part of the argumentative texture only.

NEGATIVE (not contextual):
> The reference court is requested to dispose of the pending reference under Section 30 of the Act expeditiously and, in any event, within six months from the date of communication of this order.

→ `operative`, not contextual. Even though it is brief and softly phrased ("requested to"), it imposes a forward-looking obligation on a named forum with a deadline. That is the operational signature.

### procedural

POSITIVE 1:
> IN THE HIGH COURT OF KARNATAKA AT BENGALURU
> WRIT PETITION No. 13296 of 2022
> BETWEEN: Sri V. Venkateshulu … PETITIONER
> AND: The State of Karnataka and others … RESPONDENTS

→ `procedural`. Cause-title and party listing — pure metadata.

POSITIVE 2:
> Sd/-
> JUDGE
> KMS

→ `procedural`. Signature block with judge initials. No legal content.

NEGATIVE (not procedural):
> The factual matrix giving rise to the present petition is that the petitioner is the absolute owner of land measuring two acres and twenty guntas, having purchased the same under a registered sale deed dated 18.06.2007.

→ `contextual`, not procedural. This sentence does name the petitioner and a survey detail, but it is body prose narrating facts. Procedural is reserved for structural/formatting blocks (cause-title, parties listing, signatures, headers), not for narrative prose that happens to mention a party.

## Worked example

Input:
```
=== PARAGRAPH P003-aaaa1111 [CONTEXT-ONLY] ===
The petitioner submits that the impugned notice is without jurisdiction...

=== PARAGRAPH P004-bbbb2222 [CLASSIFY] ===
Learned counsel for the State, per contra, contends that the notice was issued strictly in conformity with Section 12 of the Act and the petitioner had ample opportunity to respond.

=== PARAGRAPH P005-cccc3333 [CLASSIFY] ===
Having heard learned counsel on both sides, we are of the view that the impugned notice is sustainable. Accordingly, the second respondent is directed to issue a fresh speaking order within thirty days, and the writ petition stands disposed of in the above terms.
```

Output:
```json
{
  "classifications": [
    {"anchor": "P004-bbbb2222", "label": "contextual", "confidence": 0.93, "source_span": "Learned counsel for the State, per contra, contends that the notice was issued strictly in conformity with Section 12"},
    {"anchor": "P005-cccc3333", "label": "operative", "confidence": 0.92, "source_span": "the second respondent is directed to issue a fresh speaking order within thirty days, and the writ petition stands disposed of"}
  ]
}
```

Note that `P003-aaaa1111` is `[CONTEXT-ONLY]` and produces no entry. Note also that P005 mixes reasoning ("we are of the view that") with a direct order — the operative role dominates and the label follows the order, not the reasoning.

## Now classify

{{CHUNK_BODY}}
