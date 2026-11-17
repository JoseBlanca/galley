"""Tests of galley_eval.page_table: the columns of pages.tsv (spec
section 8), each on a literal page."""

from dataclasses import replace

import pytest

from galley.config import Language
from galley.model import (
    Box,
    PageWords,
    Reread,
    RereadKind,
    TextSource,
    Word,
    WordsFile,
)
from galley_eval.align import GalleyStream, GalleyToken, align, reference_places
from galley_eval.page_table import (
    PageRow,
    inner_symbol_share,
    page_rows,
    single_letter_share,
    stripped,
    wordlist_share,
)
from galley_eval.reader import (
    ReferenceBlock,
    ReferenceKind,
    ReferenceText,
    ReferenceToken,
)
from galley_eval.scores import Part


def _reference(text: str) -> ReferenceText:
    return ReferenceText(
        blocks=(
            ReferenceBlock(
                ReferenceKind.PARAGRAPH,
                tuple(
                    ReferenceToken(word, marked_correction=False)
                    for word in text.split()
                ),
            ),
        ),
        notes=(),
        note_references=(),
        page_anchors=(),
        anchors_in_notes=(),
    )


def _tokens(
    text: str, page_index: int = 0, *, edge_of_page: bool = False
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=page_index,
            stream=GalleyStream.BODY,
            edge_of_page=edge_of_page,
            block_id=None,
        )
        for word in text.split()
    )


def _words_file(
    galley: tuple[GalleyToken, ...],
    source: TextSource = TextSource.TEXT_LAYER,
    confidence: float | None = None,
) -> WordsFile:
    pages = sorted({token.page_index for token in galley})
    return WordsFile(
        source_pdf_sha256="0" * 64,
        pages=tuple(
            PageWords(
                index=page,
                text_source=source,
                words=tuple(
                    Word(token.text, Box(0.0, 0.0, 1.0, 1.0), confidence)
                    for token in galley
                    if token.page_index == page
                ),
                figures=(),
            )
            for page in pages
        ),
        removals=(),
    )


def _rows(
    reference: ReferenceText,
    galley: tuple[GalleyToken, ...],
    words_file: WordsFile | None = None,
    rereads: tuple[Reread, ...] = (),
) -> tuple[PageRow, ...]:
    places = reference_places(reference)
    alignment = align(reference, galley)
    return page_rows(
        words_file if words_file is not None else _words_file(galley),
        galley,
        alignment,
        places,
        page_indices=tuple(0 for _ in places),
        parts_of_pages=frozendict({0: Part.BODY}),
        printed_pages=frozendict({0: "7"}),
        word_list=frozenset(("the", "king", "went")),
        language=Language.EN,
        rereads=rereads,
    )


def test_ocr_recall_counts_a_split_and_a_case_change_as_read() -> None:
    reference = _reference("The king will replicate it there")
    # "replicate" split at a line end, "THE" in capitals, "thero" misread,
    # "it" lost: four of six read.
    galley = _tokens("THE king will repli- cate thero")
    (row,) = _rows(reference, galley)
    assert row.ocr_recall == 4 / 6


def test_ocr_precision_is_low_on_a_page_scrambled_into_letters() -> None:
    reference = _reference("Rollo Rouen Richard Robert")
    # Letters out of their order, so that no run of them joins into a word.
    galley = _tokens("l R o o l Rouen h c i R a r d")
    (row,) = _rows(reference, galley)
    # One galley token of thirteen is a word of the reference.
    assert row.ocr_precision == 1 / 13


def test_ocr_precision_counts_the_parts_of_a_split_as_precise() -> None:
    reference = _reference("the king went")
    galley = _tokens("the ki- ng wemt")
    (row,) = _rows(reference, galley)
    # "ki-" and "ng" are a split; "wemt" has another key than "went".
    assert row.ocr_precision == 3 / 4


def test_ocr_precision_leaves_out_tokens_on_the_edge_of_the_page() -> None:
    reference = _reference("the king went")
    galley = _tokens("RUNNING HEAD", edge_of_page=True) + _tokens("the king went")
    (row,) = _rows(reference, galley)
    assert row.ocr_precision == 1.0
    assert row.tokens == 5
    assert (row.page_index, row.printed_page, row.part) == (0, "7", Part.BODY)


def test_ocr_confidence_mean_only_on_pages_read_by_ocr() -> None:
    reference = _reference("the king went")
    galley = _tokens("the king went")
    (ocr_row,) = _rows(reference, galley, _words_file(galley, TextSource.OCR, 80.0))
    (layer_row,) = _rows(reference, galley, _words_file(galley))
    assert ocr_row.ocr_confidence_mean == 80.0
    assert ocr_row.text_source is TextSource.OCR
    assert layer_row.ocr_confidence_mean is None


def _reread(
    layer_words: tuple[Word, ...], confidences: tuple[float, ...], *, kept: bool
) -> Reread:
    return Reread(
        page_index=0,
        kind=RereadKind.MARGIN_NOTE,
        box=Box(0.0, 0.0, 10.0, 10.0),
        layer_words=layer_words,
        ocr_words=tuple(
            Word(f"word{position}", Box(0.0, 0.0, 1.0, 1.0), confidence)
            for position, confidence in enumerate(confidences)
        ),
        layer_score=0,
        ocr_score=1 if kept else -1,
        kept=kept,
    )


def test_ocr_confidence_mean_over_the_words_layout_reread_and_kept() -> None:
    reference = _reference("the king went")
    galley = _tokens("the king went")
    words_file = _words_file(galley)
    # Two regions of the text-layer page read again: one kept, whose
    # words are now the page's, and one not kept, which changes nothing.
    rereads = (
        _reread(words_file.pages[0].words[:1], (90.0, 70.0), kept=True),
        _reread(words_file.pages[0].words[1:], (10.0,), kept=False),
    )
    (row,) = _rows(reference, galley, words_file, rereads)
    assert row.ocr_confidence_mean == 80.0


def test_ocr_confidence_mean_leaves_out_ocr_words_a_kept_reread_replaced() -> None:
    reference = _reference("the king went")
    galley = _tokens("the king went")
    words_file = _words_file(galley, TextSource.OCR, 40.0)
    # The first word, read with 40, replaced by a reading of 100.
    rereads = (_reread(words_file.pages[0].words[:1], (100.0,), kept=True),)
    (row,) = _rows(reference, galley, words_file, rereads)
    assert row.ocr_confidence_mean == 60.0


def test_ocr_confidence_mean_leaves_out_a_kept_reread_of_another_page() -> None:
    reference = _reference("the king went")
    galley = _tokens("the king went")
    words_file = _words_file(galley, TextSource.OCR, 40.0)
    # A record of page 1 naming words equal to page 0's.
    other_page = replace(
        _reread(words_file.pages[0].words[:1], (100.0,), kept=True), page_index=1
    )
    (row,) = _rows(reference, galley, words_file, (other_page,))
    assert row.ocr_confidence_mean == 40.0


def test_ocr_confidence_mean_takes_out_a_word_on_the_page_twice_once() -> None:
    reference = _reference("the the went")
    galley = _tokens("the the went")
    words_file = _words_file(galley, TextSource.OCR, 40.0)
    # The two "the" are equal words; the record replaces one of them.
    rereads = (_reread(words_file.pages[0].words[:1], (100.0,), kept=True),)
    (row,) = _rows(reference, galley, words_file, rereads)
    assert row.ocr_confidence_mean == 60.0


def test_page_with_no_reference_token_has_no_recall() -> None:
    reference = _reference("the king")
    galley = _tokens("the king") + _tokens("Plate", 1)
    rows = _rows(reference, galley)
    assert rows[1].ocr_recall is None
    assert rows[1].part is Part.BODY


def test_stripped_lowers_and_strips_punctuation_at_both_ends() -> None:
    assert stripped("“Serfs,”") == "serfs"
    assert stripped("t*e") == "t*e"
    assert stripped("—") == ""


def test_wordlist_share_counts_only_alphabetic_tokens() -> None:
    # "1066" and "t*e" are not alphabetic; "King," and "the" are listed.
    texts = ("King,", "the", "kinq", "1066", "t*e")
    assert wordlist_share(texts, frozenset(("king", "the"))) == 2 / 3
    assert wordlist_share(("1066",), frozenset()) is None


def test_single_letter_share_leaves_out_the_words_of_one_letter() -> None:
    texts = ("a", "I", "O", "s", "t,", "word", "1")
    assert single_letter_share(texts, Language.EN) == 2 / 7
    # In French "i" is not a word, "y" and "à" are.
    assert single_letter_share(("y", "à", "i"), Language.FR) == 1 / 3


def test_inner_symbol_share_counts_symbols_inside_a_word() -> None:
    texts = ("t*e", "Anglo-Saxon", "king,", "1066", "541-90", "w0rd", "a-")
    # t*e, 541-90 and w0rd have a symbol inside; the hyphen of
    # Anglo-Saxon is between letters; "a-" is stripped to "a".
    assert inner_symbol_share(texts) == pytest.approx(3 / 7)
    assert inner_symbol_share(()) is None


def test_ocr_recall_counts_convention_case_punctuation_but_not_letters() -> None:
    # convention, case, punctuation are read; diacritic and letters not.
    reference = _reference("aaa “two” bbb Three ccc four, ddd Léon eee house fff")
    galley = _tokens('aaa "two" bbb THREE ccc four ddd Leon eee honse fff')
    (row,) = _rows(reference, galley)
    assert row.ocr_recall == 9 / 11


def test_part_column_is_that_of_the_page() -> None:
    reference = _reference("Rollo")
    galley = _tokens("Rollo")
    places = reference_places(reference)
    (row,) = page_rows(
        _words_file(galley),
        galley,
        align(reference, galley),
        places,
        page_indices=(0,),
        parts_of_pages=frozendict({0: Part.INDEX}),
        printed_pages=frozendict(),
        word_list=frozenset(),
        language=Language.EN,
        rereads=(),
    )
    assert (row.part, row.printed_page) == (Part.INDEX, None)
