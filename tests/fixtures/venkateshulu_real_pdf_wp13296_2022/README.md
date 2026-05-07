# Venkateshulu real PDF fixture

The actual Karnataka High Court judgment in WP 13296/2022 (Sri V. Venkateshulu
vs The Secretary), 17 April 2026, as published by Indian Kanoon. Ground truth
for Phase B1 (paragraph segmentation) and Phase B6 (cause title parser).

This fixture supersedes the synthetic placeholder fixture at
`tests/fixtures/legacy/synthetic_venkateshulu_wp13296_2022/`. The synthetic
fixture's paraphrased text contained directives ("within sixty days", "within
six months") that do not exist in the real judgment, and entities (KIADB,
the Karnataka Industrial Areas Development Board) that are not parties to
the case. The real judgment is a pure dismissal under the MMDR Act with
zero operative directives.

## Files

- `original.pdf` — the source PDF (9 pages, ~263 KB).
- `expected_metadata.json` — case_number, court, judgment_date, petitioner_name.
- `expected_respondents.json` — six respondents with respondent_no, designation,
  organization. Designation strings match `tests/fixtures/venkateshulu_stub.py`
  (the Phase A canonical fixture) exactly. Address fields are produced by the
  parser but are PDF-formatting-dependent and not part of the contract.
- `expected_paragraph_24_text.txt` — verbatim text of paragraph 24 after
  segmentation and whitespace normalization. The dismissal sentence.
- `expected_paragraph_count.txt` — `24`. The judgment has paragraphs 1
  through 24 inclusive, no gaps.

## What the real judgment is about

A mining-lease dispute under the Mines and Minerals (Development and
Regulation) Act, 1957 (MMDR Act) and its 2015 Amendment. The petitioner
held ML No. 2368 in Janekunta Village, Ballari Taluk for iron ore, ochre,
and quartzite. The Supreme Court's 18 April 2013 order in Samaj
Parivartana directed boundary surveys via a Joint Team. The petitioner's
deemed-extension application was rejected because of non-resumption of
mining beyond two years and non-payment of compensation under monitoring
committee directions. The Karnataka High Court dismissed the writ
petition holding the revisional authority's order non-erroneous. No
operative directives are issued; only a defensive SLP-window monitor
follows from the dismissal verdict.

## Bridge to Phase A

`tests/integration/test_real_pdf_ingestion.py` includes a bridge test that
asserts paragraph 24 from this real PDF text-equals the hand-typed
paragraph 24 in `tests/fixtures/venkateshulu_stub.py`. This is the
acceptance signal for B1 + B6: the real-PDF pipeline produces the same
ground truth the Phase A stub assumed by hand.
