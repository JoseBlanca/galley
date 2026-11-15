"""Tests of galley_eval.reader, the reader of the reference text (spec
section 4), on small pieces of HTML written after the four books' HTML,
one per rule and per case the reviews of the spec found (spec section 10,
plan work package 1)."""

import hashlib
import re
from pathlib import Path

import pytest

from galley_eval.errors import ReferenceReadError
from galley_eval.reader import (
    Gap,
    NoteReference,
    PageAnchor,
    ReferenceBlock,
    ReferenceKind,
    ReferenceNote,
    ReferenceText,
    ReferenceToken,
    Stream,
    read_reference,
    read_reference_file,
)
from galley_eval.rules import DEFAULT_RULES, ReadingRules, RuleChange, change_rules

HEADER = '<header class="pg-boilerplate pgheader"><p>The Project Gutenberg eBook</p></header>'
FOOTER = (
    '<footer class="pg-boilerplate"><p>THE FULL PROJECT GUTENBERG LICENSE</p></footer>'
)

HASKINS_RULES = change_rules(DEFAULT_RULES, RuleChange.ADD, "note", ("div.footnote",))
DOMESDAY_RULES = change_rules(
    DEFAULT_RULES, RuleChange.ADD, "notes_section", ("div.footnote",)
)
MARIEJOL_RULES = change_rules(
    change_rules(
        change_rules(DEFAULT_RULES, RuleChange.ADD, "note", ("blockquote.footnote",)),
        RuleChange.ADD,
        "drop_text",
        (r"Note \d+:?", r"\(retour\)"),
    ),
    RuleChange.REPLACE,
    "note_reference",
    (r"#footnote\d+",),
)


def _read(body: str, rules: ReadingRules = DEFAULT_RULES) -> ReferenceText:
    return read_reference(f"<html><body>{HEADER}{body}{FOOTER}</body></html>", rules)


def _block(kind: ReferenceKind, text: str) -> ReferenceBlock:
    return ReferenceBlock(
        kind,
        tuple(ReferenceToken(word, marked_correction=False) for word in text.split()),
    )


def _paragraph(text: str) -> ReferenceBlock:
    return _block(ReferenceKind.PARAGRAPH, text)


def _body(position: int) -> Gap:
    return Gap(Stream.BODY, position)


def test_page_anchor_inside_a_word_is_placed_after_the_word() -> None:
    reference = _read(
        '<p>ten house<a class="pagenum" title="21" id="Page_21"></a>holders will</p>'
    )
    assert reference.blocks == (_paragraph("ten householders will"),)
    assert reference.page_anchors == (PageAnchor("21", _body(2)),)


def test_page_anchor_text_is_dropped_and_its_number_comes_from_its_id() -> None:
    reference = _read(
        '<p>end of <span class="pagenum" id="Page_47">[Pg 47]</span>one page</p>'
    )
    assert reference.blocks == (_paragraph("end of one page"),)
    assert reference.page_anchors == (PageAnchor("47", _body(2)),)


def test_page_anchor_without_page_id_takes_its_number_from_its_title() -> None:
    reference = _read('<p>Cambridge: <a class="pagenum" title="528"></a>PRINTED</p>')
    assert reference.page_anchors == (PageAnchor("528", _body(1)),)


def test_page_anchor_with_neither_page_id_nor_title_is_an_error() -> None:
    with pytest.raises(ReferenceReadError, match="neither id=Page_N nor a title"):
        _read('<p>one <span class="pagenum"></span>two</p>')


def test_p_holding_only_a_page_anchor_is_no_block_and_its_anchor_stays() -> None:
    reference = _read(
        '<div class="chapter"><p><span class="pagenum" id="Page_vii">vii</span></p>'
        "<h2>PREFACE</h2></div><p>The eight lectures</p>"
    )
    assert reference.blocks == (
        _block(ReferenceKind.HEADING, "PREFACE"),
        _paragraph("The eight lectures"),
    )
    assert reference.page_anchors == (PageAnchor("vii", _body(0)),)


def test_note_label_is_dropped_and_its_reference_text_is_no_token() -> None:
    # Domesday: one notes section; the label is a span.label inside the a
    # that holds the note's id.
    reference = _read(
        '<p>Meitzen<a class="fnanchor" href="#Footnote_1" id="FNanchor_1">[1]</a>,'
        " Siedelung</p>"
        '<div class="footnotes"><h2>NOTES</h2><div class="footnote">'
        '<p><a href="#FNanchor_1" id="Footnote_1"><span class="label">[1]</span></a>'
        "\nHist. Eng. Law, i. 53.</p></div></div>",
        DOMESDAY_RULES,
    )
    assert reference.blocks == (_paragraph("Meitzen, Siedelung"),)
    assert reference.notes == (
        ReferenceNote("Footnote_1", (_paragraph("Hist. Eng. Law, i. 53."),)),
    )
    assert reference.note_references == (NoteReference("Footnote_1", _body(1)),)


def test_note_label_that_holds_the_pairing_id_is_dropped_and_pairs_the_note() -> None:
    # Haskins: one div.footnote per note; the id is on the dropped a.label.
    reference = _read(
        '<p>So wrote Michelet<a class="fnanchor" href="#Footnote_1" id="FNanchor_1">1</a>.</p>'
        # As in pg72514: Gutenberg's heading inside div.chapter.footnotes,
        # after a p holding only a page anchor.
        '<div class="chapter footnotes">'
        '<p><span class="pagenum" id="Page_250">250</span></p>'
        '<h2 class="nobreak" id="FOOTNOTES">FOOTNOTES</h2>'
        '<div class="footnote"><p class="fn1"><a class="label" href="#FNanchor_1"'
        ' id="Footnote_1">1</a> <i>La France</i>, p. 161.</p></div></div>',
        HASKINS_RULES,
    )
    assert reference.blocks == (_paragraph("So wrote Michelet."),)
    assert reference.notes == (
        ReferenceNote("Footnote_1", (_paragraph("La France, p. 161."),)),
    )
    assert reference.note_references == (NoteReference("Footnote_1", _body(3)),)


def test_drop_text_leaves_out_only_a_whole_run_of_text() -> None:
    rules = change_rules(DEFAULT_RULES, RuleChange.ADD, "drop_text", ("FOOTNOTES",))
    reference = _read("<h2>FOOTNOTES</h2><p>FOOTNOTES are gathered</p>", rules)
    assert reference.blocks == (_paragraph("FOOTNOTES are gathered"),)


def test_note_continued_by_an_element_without_an_id_is_one_note() -> None:
    # Domesday's note 1569 has a second paragraph, a centred formula.
    reference = _read(
        '<p>one<a href="#Footnote_1569">[1569]</a> two<a href="#Footnote_1570">[1570]</a></p>'
        '<div class="footnote">'
        '<p><a href="#FNanchor_1569" id="Footnote_1569"><span class="label">[1569]</span></a>'
        " the statement:</p>\n"
        '<p class="center">16½ <span class="fakesc">H.</span> = 20 H.</p>\n'
        '<p><a href="#FNanchor_1570" id="Footnote_1570"><span class="label">[1570]</span></a>'
        " D. B. ii. 3.</p></div>",
        DOMESDAY_RULES,
    )
    assert reference.notes == (
        ReferenceNote(
            "Footnote_1569",
            (_paragraph("the statement:"), _paragraph("16½ H. = 20 H.")),
        ),
        ReferenceNote("Footnote_1570", (_paragraph("D. B. ii. 3."),)),
    )


def test_text_left_between_notes_runs_on_into_the_note_before() -> None:
    # Domesday's note 101 ends `interlined</em></p>.’]`: no space before
    # punctuation, a space before a word.
    reference = _read(
        '<p>one<a href="#Footnote_101">[101]</a> two<a href="#Footnote_102">[102]</a></p>'
        '<div class="footnote">'
        '<p><a id="Footnote_101"><span class="label">[101]</span></a>'
        " [vel bures <em>interlined</em></p>.\u2019]\n"
        '<p><a id="Footnote_102"><span class="label">[102]</span></a> Hist.</p>Eng. Law'
        "\n</div>",
        DOMESDAY_RULES,
    )
    assert reference.notes == (
        ReferenceNote("Footnote_101", (_paragraph("[vel bures interlined.\u2019]"),)),
        ReferenceNote("Footnote_102", (_paragraph("Hist. Eng. Law"),)),
    )


def test_page_anchor_between_notes_is_kept_apart_from_the_body_anchors() -> None:
    # Domesday's anchor of printed page 357, between notes 1198 and 1199.
    reference = _read(
        '<p>one<a href="#Footnote_1">1</a> two<a href="#Footnote_2">2</a></p>'
        '<div class="footnote"><p><a id="Footnote_1"><span class="label">[1]</span></a>'
        " mark-men.</p>"
        '<a class="pagenum" title="357" id="Page_357"></a>'
        '<p><a id="Footnote_2"><span class="label">[2]</span></a> D. B. ii.</p></div>',
        DOMESDAY_RULES,
    )
    assert reference.page_anchors == ()
    assert reference.anchors_in_notes == (PageAnchor("357", Gap(Stream.NOTES, 1)),)


def test_link_from_one_note_to_another_is_text_not_a_note_reference() -> None:
    reference = _read(
        '<p>one<a href="#Footnote_1">[1]</a> two<a href="#Footnote_2">[2]</a></p>'
        '<div class="footnote"><p><a id="Footnote_1"><span class="label">[1]</span></a> Meitzen.</p>'
        '<p><a id="Footnote_2"><span class="label">[2]</span></a> See above <a href="#Footnote_1">p. 54, note 1</a>.</p>'
        "</div>",
        DOMESDAY_RULES,
    )
    assert reference.note_references == (
        NoteReference("Footnote_1", _body(1)),
        NoteReference("Footnote_2", _body(2)),
    )
    assert reference.notes[1] == ReferenceNote(
        "Footnote_2", (_paragraph("See above p. 54, note 1."),)
    )


def test_mariejol_back_link_is_not_a_note_reference_and_its_label_goes() -> None:
    reference = _read(
        '<p>famille<a id="footnotetag2"></a><a href="#footnote2"><sup class="sml">2</sup>'
        "</a>. Léon X</p>"
        '<blockquote class="footnote"><div><a id="footnote2"><b>Note 2: </b></a>'
        '<a href="#footnotetag2">(retour) </a> A. de Reumont, p.\n247.</div></blockquote>',
        MARIEJOL_RULES,
    )
    assert reference.blocks == (_paragraph("famille. Léon X"),)
    assert reference.notes == (
        ReferenceNote("footnote2", (_paragraph("A. de Reumont, p. 247."),)),
    )
    assert reference.note_references == (NoteReference("footnote2", _body(1)),)


def test_note_that_no_reference_points_to_is_an_error() -> None:
    with pytest.raises(
        ReferenceReadError, match="no id that a note reference points to"
    ):
        _read(
            '<div class="footnote"><p><a class="label" id="Footnote_9">9</a> Orphan.</p></div>',
            HASKINS_RULES,
        )


def test_margin_note_with_br_is_one_block_of_separate_words() -> None:
    reference = _read('<div class="sidenote">Various<br>views.</div><p>Of all</p>')
    assert reference.blocks == (
        _block(ReferenceKind.MARGIN_NOTE, "Various views."),
        _paragraph("Of all"),
    )


def test_p_inside_a_margin_note_is_part_of_the_margin_note() -> None:
    reference = _read('<div class="sidenote"><p>The epoch</p><p>of Henry</p></div>')
    assert reference.blocks == (
        _block(ReferenceKind.MARGIN_NOTE, "The epoch of Henry"),
    )


def test_margin_note_inside_a_paragraph_comes_before_it_and_the_text_runs_on() -> None:
    reference = _read(
        '<p>less explicit. <span class="sidenote">The community.</span> When, for</p>'
    )
    assert reference.blocks == (
        _block(ReferenceKind.MARGIN_NOTE, "The community."),
        _paragraph("less explicit. When, for"),
    )


def test_other_block_inside_a_paragraph_ends_it_and_the_rest_is_a_new_one() -> None:
    # Mariéjol's note 1423, pg36315 lines 23460-23476: a verse inside the
    # div of the note, between two runs of prose.
    reference = _read(
        '<p>one<a href="#footnote1423">1423</a></p>'
        '<blockquote class="footnote"><div><a id="footnote1423"><b>Note 1423: </b></a>'
        '<a href="#footnotetag1423">(retour) </a> ne contredit pas ce témoin:\n'
        '<div class="poem"><div class="stanza"><p class="i14"><i>Cor junctum</i></p>'
        '<p class="i14"><i>Ante homines</i></p></div></div>\n'
        "<p><i>Amor</i>, en langage poétique.</p></div></blockquote>",
        MARIEJOL_RULES,
    )
    assert reference.notes == (
        ReferenceNote(
            "footnote1423",
            (
                _paragraph("ne contredit pas ce témoin:"),
                _block(ReferenceKind.QUOTE, "Cor junctum Ante homines"),
                _paragraph("Amor, en langage poétique."),
            ),
        ),
    )


def test_poetry_holding_verse_lines_is_one_quote() -> None:
    # Haskins, pg72514 lines 6483-6492: div.poetry and div.verse are both
    # quotes, and the outermost owns the verses.
    reference = _read(
        "<p>pilgrim\u2019s chorus:\u2014</p>"
        '<div class="poetry-container"><div class="poetry"><div class="stanza">'
        '<div class="verse indent2">O Roma nobilis, orbis et domina,</div>'
        '<div class="verse indent0">Cunctarum urbium excellentissima,</div>'
        "</div></div></div>"
    )
    assert reference.blocks == (
        _paragraph("pilgrim\u2019s chorus:\u2014"),
        _block(
            ReferenceKind.QUOTE,
            "O Roma nobilis, orbis et domina, Cunctarum urbium excellentissima,",
        ),
    )


def test_marked_correction_keeps_the_corrected_text_and_tags_its_tokens() -> None:
    reference = _read(
        '<p>on the <ins class="correction" title="original: roial">royal</ins>'
        ' demesne, <ins class="correction" title="original: Demesne">demesne</ins>,'
        " held</p>"
    )
    assert reference.blocks == (
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            (
                ReferenceToken("on", marked_correction=False),
                ReferenceToken("the", marked_correction=False),
                ReferenceToken("royal", marked_correction=True),
                ReferenceToken("demesne,", marked_correction=False),
                # The correction covers part of the token.
                ReferenceToken("demesne,", marked_correction=True),
                ReferenceToken("held", marked_correction=False),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("html", "text"),
    [
        ("54<sup>1</sup>\u2044<sub>2</sub> teams", "54\u00bd teams"),
        ("2<sup>1</sup>\u2044<sub>7</sub> hides", "2\u2150 hides"),
        ("2<sup>5</sup>\u2044<sub>7</sub> hides", "2 5\u20447 hides"),
        ("<sup>2</sup>\u2044<sub>3</sub>", "\u2154"),
        ("M<sup>r</sup> Round", "Mr Round"),
    ],
)
def test_fraction_is_written_as_printed(html: str, text: str) -> None:
    assert _read(f"<p>{html}</p>").blocks == (_paragraph(text),)


def test_soft_hyphen_is_removed_and_zero_width_space_separates_words() -> None:
    reference = _read("<p>house\u00adholders and\u200btheir</p>")
    assert reference.blocks == (_paragraph("householders and their"),)


def test_typographic_markup_gives_its_text_only() -> None:
    reference = _read(
        '<p>M<sup>r</sup> Round, <span class="smcap">Feudal</span> <span lang="la">'
        "England</span></p>"
    )
    assert reference.blocks == (_paragraph("Mr Round, Feudal England"),)


def test_gutenberg_text_before_the_start_element_is_left_out() -> None:
    rules = change_rules(DEFAULT_RULES, RuleChange.REPLACE, "start", ("h1",))
    reference = _read(
        "<p>The Project Gutenberg eBook, Domesday Book and Beyond</p>"
        "<table><tr><td>Note:</td><td>Images of the original pages</td></tr></table>"
        '<div class="transnote"><p class="sidenote">Marginal descriptions</p></div>'
        "<h1>DOMESDAY BOOK AND BEYOND</h1><p>Text</p>",
        rules,
    )
    assert reference.blocks == (
        _block(ReferenceKind.HEADING, "DOMESDAY BOOK AND BEYOND"),
        _paragraph("Text"),
    )


def test_start_that_matches_nothing_is_an_error() -> None:
    rules = change_rules(DEFAULT_RULES, RuleChange.REPLACE, "start", ("h1",))
    with pytest.raises(ReferenceReadError, match=re.escape("start rule (h1)")):
        _read("<p>Text</p>", rules)


def test_html_without_gutenberg_header_is_an_error_under_the_default_start() -> None:
    with pytest.raises(ReferenceReadError, match="header.pg-boilerplate"):
        read_reference("<html><body><p>Text</p></body></html>", DEFAULT_RULES)


def test_licence_and_transcribers_note_are_dropped() -> None:
    reference = _read(
        '<p>Text</p><div class="chapter transnote"><h2>Transcriber’s Notes</h2>'
        "<p>Punctuation was made consistent.</p></div>"
    )
    assert reference.blocks == (_paragraph("Text"),)


def test_each_li_of_the_index_is_an_index_entry() -> None:
    reference = _read(
        '<h2>INDEX</h2><div class="index"><ul class="index">'
        '<li class="indx">Acre, siege of, <a href="#Page_116">116</a>;</li>'
        '<li class="isub1">taken, <a href="#Page_120">120</a></li></ul></div>'
    )
    assert reference.blocks == (
        _block(ReferenceKind.HEADING, "INDEX"),
        _block(ReferenceKind.INDEX_ENTRY, "Acre, siege of, 116;"),
        _block(ReferenceKind.INDEX_ENTRY, "taken, 120"),
    )


def test_quote_table_and_figure_caption_are_blocks_of_their_kind() -> None:
    reference = _read(
        '<div class="blockquot"><p>Edited by Rev. G. W. Cox</p><p>Eleven volumes</p></div>'
        "<table><tr><td>Hides</td><td>16½</td></tr></table>"
        '<figure class="figcenter"><img src="i.jpg"><figcaption>MEDIEVAL EUROPE'
        "</figcaption></figure>"
        '<figure class="figcenter"><img src="logo.png"></figure>'
    )
    assert reference.blocks == (
        _block(ReferenceKind.QUOTE, "Edited by Rev. G. W. Cox Eleven volumes"),
        _block(ReferenceKind.TABLE, "Hides 16½"),
        _block(ReferenceKind.FIGURE, "MEDIEVAL EUROPE"),
    )


def test_div_with_text_of_its_own_is_a_paragraph() -> None:
    reference = _read(
        '<div class="titlepage"><div class="xlarge">THREE ESSAYS<br> IN THE</div>'
        '<div class="small">[<em>All rights reserved.</em>]</div></div>'
    )
    assert reference.blocks == (
        _paragraph("THREE ESSAYS IN THE"),
        _paragraph("[All rights reserved.]"),
    )


def test_added_heading_rule_makes_a_heading_of_a_p() -> None:
    rules = change_rules(DEFAULT_RULES, RuleChange.ADD, "heading", ("p.ph3",))
    reference = _read('<p class="ph3">INTRODUCTION.</p><p>Text</p>', rules)
    assert reference.blocks == (
        _block(ReferenceKind.HEADING, "INTRODUCTION."),
        _paragraph("Text"),
    )


def test_text_outside_every_block_is_an_error() -> None:
    with pytest.raises(ReferenceReadError, match="text outside every block"):
        _read("<p>Text</p>stray words<p>More</p>")


def test_end_tag_that_closes_nothing_is_an_error() -> None:
    with pytest.raises(ReferenceReadError, match="closes no open element"):
        _read("<p>Text</p></div>")


def test_section_break_asterisks_and_map_links_are_dropped() -> None:
    reference = _read(
        '<p>several periods</p><div class="tb">* * * * *</div><p>The interest</p>'
        '<div class="larger-version">[<a href="images/map1_large.jpg">Larger map</a>]'
        "</div>"
    )
    assert reference.blocks == (
        _paragraph("several periods"),
        _paragraph("The interest"),
    )


def test_separate_rule_makes_an_inline_element_separate_words() -> None:
    # Stubbs' table of contents, pg70828 line 453.
    html = (
        '<p>years\u2019 work<span class="float-right"><i>Page</i> '
        '<a href="#Page_34">34</a></span></p>'
    )
    assert _read(html).blocks == (_paragraph("years\u2019 workPage 34"),)
    rules = change_rules(
        DEFAULT_RULES, RuleChange.ADD, "separate", ("span.float-right",)
    )
    assert _read(html, rules).blocks == (_paragraph("years\u2019 work Page 34"),)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_reference_file_is_read_when_its_sha256_is_the_expected_one(
    tmp_path: Path,
) -> None:
    html = f"<html><body>{HEADER}<p>Text</p></body></html>".encode()
    path = tmp_path / "pg1-images.html"
    path.write_bytes(html)
    reference = read_reference_file(path, DEFAULT_RULES, _sha256(html))
    assert reference.blocks == (_paragraph("Text"),)


def test_reference_file_of_another_sha256_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "pg1-images.html"
    path.write_bytes(f"<html><body>{HEADER}<p>Text</p></body></html>".encode())
    with pytest.raises(ReferenceReadError, match=f"{re.escape(str(path))}.*SHA-256"):
        read_reference_file(path, DEFAULT_RULES, _sha256(b"another version"))


def test_missing_reference_file_is_an_error_naming_the_fetch_command(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pg1-images.html"
    with pytest.raises(ReferenceReadError, match="fetch_samples.py") as raised:
        read_reference_file(path, DEFAULT_RULES, _sha256(b""))
    assert str(path) in str(raised.value)


def test_reference_file_that_is_not_utf8_is_an_error(tmp_path: Path) -> None:
    data = "<p>Médicis</p>".encode("latin-1")
    path = tmp_path / "pg1-images.html"
    path.write_bytes(data)
    with pytest.raises(ReferenceReadError, match="not UTF-8"):
        read_reference_file(path, DEFAULT_RULES, _sha256(data))
