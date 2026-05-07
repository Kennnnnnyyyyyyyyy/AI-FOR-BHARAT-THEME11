---
task: paragraph_classifier
version: 3
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: ParagraphClassification
---
You are classifying paragraphs from a Karnataka High Court (KHC) judgment.
For each paragraph marked `[CLASSIFY]` you must return exactly one classification entry.
Paragraphs marked `[CONTEXT-ONLY]` are provided for context only — do NOT classify them; do not include them in your output.

The labels are `operative`, `contextual`, and `procedural`. The boundary that matters most — and the boundary the model usually misreads — is between `operative` and `contextual`. Read the gate below before you label anything. Do not skip it.

## The three-check gate (read this first)

Label a paragraph `operative` if and only if **all three** of the following are true. If any one fails, the paragraph is `contextual` (or `procedural` per the metadata rules below). Walk the checks in order; the first failure decides.

1. **Speaker check — is the speaker the court itself?**
   The court speaks in voices like "we direct", "we hold", "the writ petition is dismissed", "ordered accordingly". Counsel ("learned counsel for the petitioner submits", "counsel urges that"), parties ("the petitioner submitted a representation", "the State has narrated"), witnesses, and quoted precedents are NOT the court. Counsel cannot direct anyone. A party cannot direct anyone. Only the court directs.

2. **Speech-act check — is the act directing or disposing, not reasoning or evaluating?**
   *Directing* uses imperative or future-imperative voice: "we direct", "the second respondent shall", "is requested to dispose of within six months". *Disposing* announces the final outcome: "the writ petition is dismissed", "the appeal is allowed", "ordered accordingly", "set aside", "remanded".
   *Reasoning* and *evaluating* are NOT directing or disposing — even though they often precede a direction in the judgment, and even though they often sound forceful. The following surface markers are evaluative voice and FAIL this check on their own: "we find merit", "we are of the view", "we are not persuaded", "we have considered", "in our considered view", "such conduct disentitles", "warrants interference", "is unsustainable". The court is reasoning toward a verdict; it has not yet announced one.

3. **Obligation check — does this paragraph create a current obligation, or announce a final disposition?**
   A *current* obligation is forward-looking: someone must do something from this point onward. A *final disposition* ends the matter ("the writ petition is dismissed").
   Past-tense narration of earlier acts FAILS this check, even when the underlying act was itself a direction or order at the time. Examples that fail: "notice dated 04.08.2015 was issued", "an award came to be passed", "the petitioner submitted a representation seeking exclusion", "the second respondent had been directed", "the earlier writ petition was disposed of with liberty". These describe history; the present paragraph is not directing or disposing of anything now.

**Tie-breaker.** When uncertain, label `contextual`. False-positive `operative` creates phantom obligations downstream and is the failure mode this prompt was rewritten to fix; false-negative is recoverable in officer review.

**Anti-cue.** Surface forcefulness alone — words like "merit", "persuaded", "disentitles", "urges", "barred", "warrants", "vitiated", "colourable" — does not satisfy any check. These are rhetorical intensity, not legal force.

## Mixed-content paragraphs

A paragraph that contains both reasoning *and* a current direction or disposition in the same block is `operative`. The operational role dominates. But this rule applies only when the operative role is *actually present per the three checks above*, not merely implied by reasoning that is heading toward a verdict in a later paragraph.

Concretely: "Having considered the matter, we direct the second respondent to refund within sixty days" is `operative` (check 1 ✓ court speaking, check 2 ✓ "we direct", check 3 ✓ current obligation with deadline). "We are not persuaded that interference is warranted" is `contextual` even if the formal "writ petition is dismissed" follows in the next paragraph (check 2 fails — this is evaluation, not disposition; the disposition lives in its own paragraph).

## Procedural

`procedural` covers structural metadata only:
- Cause-title blocks ("IN THE HIGH COURT OF KARNATAKA AT BENGALURU", "WP No. 13296 of 2022")
- Party listings ("BETWEEN: ... PETITIONER / AND: ... RESPONDENTS")
- Signature blocks ("Sd/- JUDGE")
- Page headers/footers, footnote-only paragraphs, certificate-of-service blocks

A narrative paragraph that happens to mention a party or a case number is NOT procedural — it's `contextual`.

## Output format

Return a single JSON object with this exact shape:

```json
{
  "classifications": [
    {"anchor": "<paragraph anchor exactly as given>", "label": "<operative | contextual | procedural>", "confidence": 0.0_to_1.0, "source_span": "<verbatim excerpt from THIS paragraph>"}
  ]
}
```

Rules:
- The `anchor` field MUST be copied character-for-character from the `[CLASSIFY]` header. Do not invent, abbreviate, or reorder anchors.
- `source_span` MUST be a verbatim substring of the paragraph that carries the same anchor. Never quote text from a different paragraph.
- `confidence` is your subjective certainty in [0.0, 1.0]. Use lower values when the paragraph could plausibly fit two labels.
- Output exactly one entry per `[CLASSIFY]` paragraph, in the same order.

## Worked positive examples (operative)

**P-EX-OP-1** — direction with deadline:
> Accordingly, while declining to interfere with the acquisition itself, we direct the second respondent to ensure that the compensation amount along with all statutory benefits is disbursed to the petitioner within a period of sixty days from the date of receipt of a copy of this order, subject to the outcome of the pending reference.

→ `operative`. Speaker ✓ (the court, "we direct"). Speech-act ✓ (directing). Obligation ✓ (current obligation on the second respondent with a sixty-day deadline). The opening "while declining to interfere" is reasoning along for the ride — the operative role dominates.

**P-EX-OP-2** — directive to a forum:
> The reference court is requested to dispose of the pending reference under Section 30 of the Act expeditiously and, in any event, within a period of six months from the date of communication of this order.

→ `operative`. Speaker ✓ (court). Speech-act ✓ (directing — the polite "is requested to" is still a directive when it imposes a deadline on a named forum). Obligation ✓ (six-month deadline).

**P-EX-OP-3** — final disposition / verdict trigger:
> Subject to the directions issued in the preceding paragraphs, the writ petition is dismissed. There shall be no order as to costs. Ordered accordingly.

→ `operative`. Speaker ✓ (court). Speech-act ✓ (disposing — "is dismissed", "ordered accordingly"). Obligation ✓ (final disposition; this is the paragraph that triggers limitation).

## Worked negative examples (NOT operative — these are the boundary cases that flipped on prior runs)

**P-EX-NEG-1** — past party representation:
> The petitioner thereafter submitted a representation on 21.04.2015 reiterating his earlier objections and seeking exclusion of his land from the acquisition proceedings.

→ `contextual`, NOT operative.
- Speaker check FAILS — the speaker is the petitioner, not the court.
- Obligation check FAILS — past-tense narration ("submitted", "seeking"). The petitioner is not creating a current obligation by having asked something in the past.
- The phrase "seeking exclusion" sounds dispositive; it is not. Asking is not directing.

**P-EX-NEG-2** — counsel urging an outcome:
> Learned counsel for the second respondent adopts the submissions of the State and additionally urges that the writ petition is barred by delay and laches inasmuch as it was filed nearly seven years after the final notification.

→ `contextual`, NOT operative.
- Speaker check FAILS — the speaker is counsel for a respondent, not the court. Counsel cannot direct anyone or dispose of anything.
- The surface form "the writ petition is barred" mimics the actual disposition "the writ petition is dismissed", which lives in a separate paragraph. The look-alike does NOT make this an operative paragraph. Read the speaker first.

**P-EX-NEG-3** — court's evaluative reasoning:
> Insofar as the plea of delay and laches is concerned, we find merit in the submission of the State. The petitioner accepted the award proceedings, participated in the reference, and only thereafter chose to question the underlying acquisition. Such conduct disentitles him to discretionary relief under Article 226.

→ `contextual`, NOT operative.
- Speaker check ✓ (court).
- Speech-act check FAILS — "we find merit", "such conduct disentitles" are evaluative voice. The court is reasoning toward a verdict, not yet announcing one.
- Forceful rhetoric ("disentitles", "merit") is the anti-cue. Do not promote on intensity.

**P-EX-NEG-4** — court's conclusion paragraph that stops short of the disposition:
> On the totality of the circumstances, we are not persuaded that the impugned acquisition warrants interference. The petitioner's substantive grievance, if any, lies in the pending reference proceedings, where the question of compensation can be agitated on its merits.

→ `contextual`, NOT operative.
- Speaker check ✓ (court).
- Speech-act check FAILS — "we are not persuaded", "warrants interference" are the court's view. The court has reached a conclusion in its own mind; it has not yet announced the disposition. The disposition is in the dedicated dismissal paragraph that follows.
- This is the paragraph most likely to be misread as operative because it sounds final. The discipline is: announcing a *view* is not announcing a *disposition*. Wait for the actual "is dismissed / is allowed / is remanded" sentence.

## Worked procedural example

**P-EX-PROC-1**:
> IN THE HIGH COURT OF KARNATAKA AT BENGALURU
> WRIT PETITION No. 13296 of 2022
> BETWEEN: Sri V. Venkateshulu … PETITIONER
> AND: The State of Karnataka and others … RESPONDENTS

→ `procedural`. Cause-title and party listing — pure metadata.

## Worked walkthrough on a chunk

Input:
```
=== PARAGRAPH P003-aaaa1111 [CONTEXT-ONLY] ===
The petitioner submits that the impugned notice is without jurisdiction...

=== PARAGRAPH P004-bbbb2222 [CLASSIFY] ===
Learned counsel for the State, per contra, contends that the notice was issued strictly in conformity with Section 12 of the Act and the petitioner had ample opportunity to respond.

=== PARAGRAPH P005-cccc3333 [CLASSIFY] ===
Having heard learned counsel on both sides, we are of the view that the impugned notice is sustainable. Accordingly, the second respondent is directed to issue a fresh speaking order within thirty days, and the writ petition stands disposed of in the above terms.
```

Walkthrough:
- P003 is `[CONTEXT-ONLY]` — no entry.
- P004: speaker is counsel — speaker check FAILS. → `contextual`.
- P005: speaker is the court ✓; speech-act includes "is directed to issue a fresh speaking order" (directing) and "the writ petition stands disposed of" (disposing) ✓; obligation is current with a thirty-day deadline ✓. Mixed-content rule applies — the upstream "we are of the view" reasoning is along for the ride. → `operative`.

Output:
```json
{
  "classifications": [
    {"anchor": "P004-bbbb2222", "label": "contextual", "confidence": 0.95, "source_span": "Learned counsel for the State, per contra, contends that the notice was issued strictly in conformity with Section 12"},
    {"anchor": "P005-cccc3333", "label": "operative", "confidence": 0.93, "source_span": "the second respondent is directed to issue a fresh speaking order within thirty days, and the writ petition stands disposed of"}
  ]
}
```

## Now classify

{{CHUNK_BODY}}
