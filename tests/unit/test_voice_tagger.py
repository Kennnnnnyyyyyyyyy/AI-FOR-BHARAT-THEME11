"""Phase B3 voice tagger unit tests.

Pure unit tests against synthetic short strings. These pin algorithm
behavior without depending on the real Venkateshulu PDF; the real-PDF
sweep lives in tests/integration/test_voice_real_pdf.py.

The synthetic strings use curly quotes (U+201C / U+201D) where the algorithm
cares about distinct open/close pairing. The real-PDF integration tests
exercise the straight-quote branch separately.
"""

from __future__ import annotations

from kartavya.extraction.voice import tag_voice_spans


def test_supreme_court_block_quote_tagged() -> None:
    text = (
        "The Supreme Court vide judgment dated 18.04.2013 held as under: "
        "“We make it clear that we have not understood the above "
        "statement as an admission.” (emphasis supplied)"
    )
    spans = tag_voice_spans(text)
    assert len(spans) == 1
    assert spans[0].voice == "SUPREME_COURT_QUOTE"
    quoted = text[spans[0].char_start : spans[0].char_end]
    assert quoted.startswith("“We make it clear")
    assert quoted.endswith("admission.”")


def test_this_court_block_quote_tagged_as_other_court() -> None:
    text = (
        "The relevant portion of the order dated 25.08.2015 passed by this "
        "Court is as under: “The Petition is therefore rejected.”"
    )
    spans = tag_voice_spans(text)
    assert len(spans) == 1
    assert spans[0].voice == "OTHER_COURT_QUOTE"


def test_revisional_authority_quote_tagged() -> None:
    text = (
        "The revisional authority considering the revision filed by the "
        "petitioner inter alia held as under: “45. Admittedly, "
        "Revisionist has not filed any application.”"
    )
    spans = tag_voice_spans(text)
    assert len(spans) == 1
    assert spans[0].voice == "REVISIONAL_AUTHORITY_QUOTE"


def test_statute_paraphrase_tagged() -> None:
    text = (
        "Section 4A(4) of the MMDR Act stipulates that, if a holder of a "
        "mining lease fails to undertake mining activity for a period of "
        "two years, the lease shall lapse on the expiry of the said period."
    )
    spans = tag_voice_spans(text)
    assert len(spans) == 1
    assert spans[0].voice == "STATUTE_QUOTE"
    assert text[spans[0].char_start :].startswith("Section 4A(4)")


def test_two_statute_paraphrases_tagged_separately() -> None:
    text = (
        "Section 8A(3) of the MMDR Act stipulates that mining leases shall "
        "be deemed for fifty years. However, Section 8A(6) of the MMDR Act "
        "states that the renewal is subject to compliance."
    )
    spans = tag_voice_spans(text)
    voices = [s.voice for s in spans]
    assert voices == ["STATUTE_QUOTE", "STATUTE_QUOTE"]


def test_party_contention_tagged() -> None:
    text = (
        "It is the primary contention of the petitioner that the lease has "
        "not lapsed. The petitioner relies on Section 8A(3) for a deemed "
        "extension of fifty years."
    )
    spans = tag_voice_spans(text)
    assert len(spans) == 1
    assert spans[0].voice == "PARTY_CONTENTION"
    assert text[spans[0].char_start :].startswith("The petitioner relies")


def test_per_contra_contention_tagged() -> None:
    text = (
        "Per contra, the learned Additional Government Advocate justifies "
        "the order. The order is in conformity with Section 8A(9) of the Act."
    )
    spans = tag_voice_spans(text)
    assert len(spans) >= 1
    assert any(s.voice == "PARTY_CONTENTION" for s in spans)


def test_pure_court_voice_paragraph_yields_no_spans() -> None:
    text = "Accordingly, the present petition is dismissed as being devoid of merit."
    spans = tag_voice_spans(text)
    assert spans == []


def test_unattributed_block_quote_defaults_to_other_court() -> None:
    text = "The earlier order reads as under: “The lease is cancelled.”"
    spans = tag_voice_spans(text)
    assert len(spans) == 1
    assert spans[0].voice == "OTHER_COURT_QUOTE"


def test_spans_do_not_overlap() -> None:
    """A statute paraphrase nested inside a block quote is absorbed by the
    outer block quote span, not double-tagged."""
    text = (
        "The Supreme Court held as under: “Section 8A(3) of the MMDR "
        "Act stipulates that leases are deemed extended.”"
    )
    spans = tag_voice_spans(text)
    assert len(spans) == 1
    assert spans[0].voice == "SUPREME_COURT_QUOTE"


def test_voice_in_span_helper_returns_court_for_uncovered_regions() -> None:
    from kartavya.schemas.parsed_judgment import GroundedParagraph

    text = (
        "Court reasoning. Section 4A(4) of the MMDR Act stipulates that "
        "leases lapse after two years."
    )
    spans = tag_voice_spans(text)
    p = GroundedParagraph(
        paragraph_index=1, text=text, section_class="REASONING", voice_spans=spans
    )
    assert p.voice_in_span(0, 15) == "COURT"
    statute_start = text.index("Section")
    assert p.voice_in_span(statute_start, statute_start + 10) == "STATUTE_QUOTE"
