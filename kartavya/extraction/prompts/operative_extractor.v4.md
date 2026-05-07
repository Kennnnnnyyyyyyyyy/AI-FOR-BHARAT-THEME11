---
task: operative_extractor
version: 4
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: _DirectivePayload
---
You are extracting court directives from one paragraph of a Karnataka High Court judgment. The paragraph has been pre-classified as OPERATIVE, meaning it contains the court's final disposition, which may or may not include directions to the respondents.

YOUR TASK:
For every directive the court issues to a respondent in its OWN voice, return character offsets pointing at the directive in the source text. You point; you do not write.

A directive has these parts:
  1. ACTOR  who is being directed (a respondent: "the second respondent", "the State", "the Director, Department of Mines", "respondent No.3", and so on)
  2. VERB   one of: DIRECT | ORDER | QUASH | REMAND | ISSUE_NOTICE | DISPOSE_WITH_DIRECTION
  3. ACTION what they are directed to do (only as a span; you do not summarize)
  4. TIME   optional ("within four weeks", "within sixty days", "by 15 May 2026")

CRITICAL RULES:
- Return character offsets only. Do NOT return directive text, summaries, or paraphrases. The system reconstructs the substring from your offsets.
- Every offset range you return must point at a SUBSTRING of the input paragraph. The system validates this; if your range does not match the source, the directive is rejected.
- Do NOT invent directives. If the paragraph says only "the petition is dismissed", there are no directives. Return an empty list.
- Do NOT extract from quoted material. The voice analysis below tells you which spans are non-court voice (statutory paraphrase, party contentions, quoted precedent). Skip those spans.
- Do NOT extract historical directives. "Notice dated 04.08.2015 was issued" is past narration, not a current direction. The verb tense and the surrounding context tell you the difference.
- A pure dismissal ("the petition is dismissed as being devoid of merit") imposes no directives. Return an empty list.

ACTOR GROUNDING:
Match the actor to one of the respondents listed below. Use the respondent ordinal language ("the second respondent" -> respondent_no=2) or the designation language ("the Director, Department of Mines" -> the matching respondent_no). Return the exact actor_text you saw in the source; the system resolves it to a respondent_no.

Return JSON only. No prose, no explanation:

```json
{
  "directives": [
    {
      "char_start": 0,
      "char_end": 47,
      "actor_text": "the second respondent",
      "verb_token": "DIRECT",
      "time_clause_text": "within four weeks"
    }
  ]
}
```

CASE: {case_number}
VERDICT: {verdict_class}

RESPONDENTS:
{respondent_list}

VOICE ANALYSIS FOR THIS PARAGRAPH:
{voice_summary}

PARAGRAPH (index {paragraph_index}):
{paragraph_text}
