---
task: section_classifier
version: 1
model: llama3.1:8b-instruct-q4_K_M
temperature: 0
schema: _SectionResponse
---
You are classifying a paragraph from a Karnataka High Court writ judgment.
Your job is to assign exactly one section class from this list:

  FACTS               narrative recital of events, prior proceedings, undisputed background.
  ARGUMENTS           paraphrase of what a party (petitioner / respondent / Government Advocate) contended.
  PRECEDENT_CITATION  paragraph dominantly quotes or recites a statute, prior judgment, or another tribunal's order without the court's own reasoning.
  REASONING           court's own analysis applying law to facts, including paragraphs that QUOTE precedent or a lower tribunal AND ENDORSE / ADOPT the quoted material as the court's own conclusion.
  OPERATIVE           final disposition: "Accordingly, the petition is dismissed" and similar. Usually the last numbered paragraph.
  DECREE              formal decree language (rare in writ judgments).

The distinction between PRECEDENT_CITATION and REASONING is often subtle:
  A paragraph that JUST quotes a precedent, with one introducer sentence and no further court commentary, is PRECEDENT_CITATION.
  A paragraph that quotes a precedent OR a lower tribunal AND the surrounding context (especially the next paragraph) shows the court ADOPTING the quoted reasoning as its own conclusion is REASONING.

You will see the paragraph, plus a voice analysis that tells you which spans are quotes and from whom, plus the previous and next paragraph previews for context. The voice analysis is descriptive, not authoritative; it tells you what the paragraph contains structurally, but you decide the section class.

Return a single JSON object:

```json
{ "section_class": "FACTS" | "ARGUMENTS" | "PRECEDENT_CITATION" | "REASONING" | "OPERATIVE" | "DECREE" }
```

Return only the JSON. No prose, no explanation.

PARAGRAPH INDEX: {paragraph_index} of {total_paragraphs}
IS LAST BODY PARAGRAPH: {is_last}

VOICE ANALYSIS:
{voice_summary}

PREVIOUS PARAGRAPH (preview):
{prev_preview}

PARAGRAPH:
{paragraph_text}

NEXT PARAGRAPH (preview):
{next_preview}
