"""Tests of the correct stage (docs/specs/correct.md) and of markdown's
application of edits (its section 10), with the model's answers recorded:
no model runs here but in the test marked vision_model."""

import base64
import hashlib
import json
import shutil
import socket
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import override

import pytest

from galley import correct, pdfium
from galley.book_folder import BookFolder
from galley.config import BookConfig, read_config
from galley.correct import _png, edits_of
from galley.correct._align import Pair, align, align_free_tail
from galley.correct._lmstudio import (
    PROMPT,
    check_models,
    read_image,
    request_body,
)
from galley.correct._merge import answer, cased, page_changes
from galley.correct._reading import page_reading, split_counts
from galley.correct._tokens import clean_answer, comparison_form, tokens
from galley.errors import EditError, ExternalProgramError
from galley.markdown import FiledEdit, apply_edits
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Edit,
    Emphasis,
    Note,
    NoteKind,
    Origin,
    PageWords,
    Removal,
    RemovalReason,
    Span,
    TextSource,
    Word,
    WordsFile,
    block_sha256,
    block_text,
    read_blocks,
    read_edits,
    read_words,
)

FIXTURES = Path(__file__).parent / "fixtures" / "correct"
MODEL = "qwen/qwen3.6-35b-a3b"
SECOND = "qwen/qwen3.6-27b"


def _cores(text: str) -> list[str]:
    return [text[token.start : token.end] for token in tokens(text)]


# Section 6: the words compared.


def test_tokens_have_the_cores_of_section_6() -> None:
    assert _cores("struphes.”") == ["struphes"]
    assert _cores("Greece,1") == ["Greece"]
    assert _cores("3%)") == ["3%"]
    assert _cores("—") == []
    assert _cores("3There") == ["There"]
    assert _cores("1X,") == ["1X"]
    assert _cores("A1") == ["A1"]
    assert _cores("Kadesh—the end--of") == ["Kadesh", "the", "end", "of"]


def test_tokens_know_where_their_core_is() -> None:
    text = "a “puem ia”"
    assert [(token.start, token.end) for token in tokens(text)] == [
        (0, 1),
        (3, 7),
        (8, 10),
    ]


def test_case_accents_quotes_and_hyphens_do_not_change_the_comparison_form() -> None:
    assert comparison_form("Rougé") == comparison_form("ROUGE") == "rouge"
    assert comparison_form("temple-reliefs") == comparison_form("templereliefs")
    assert comparison_form("491–513") == "491513"
    assert comparison_form("ﬁrst") == "first"


def test_a_line_end_hyphen_is_joined_only_before_lower_case_or_capitals_in_capitals() -> (
    None
):
    assert clean_answer("col-\nlated") == "collated"
    assert clean_answer("MARI-\nETTE") == "MARIETTE"
    # The last body line before the first note (section 6, step 1).
    assert clean_answer("com-\nCalled by") == "com-\nCalled by"
    assert clean_answer("**Poem** <b>x</b> Greece¹") == "  Poem    x  Greece"


# Section 7: the alignment.


def test_alignment_pairs_tokens_at_the_same_place_whatever_their_letters() -> None:
    assert align(["a", "puem", "ia"], ["a", "poem", "in"]) == (
        Pair(0, 0),
        Pair(1, 1),
        Pair(2, 2),
    )
    assert align(["a", "c"], ["a", "b", "c"]) == (Pair(0, 0), Pair(None, 1), Pair(1, 2))
    assert align(["a", "b", "c"], ["a", "c"]) == (Pair(0, 0), Pair(1, None), Pair(2, 1))


def test_alignment_with_a_free_tail_leaves_the_rest_of_the_first_out() -> None:
    assert align_free_tail(["a", "b", "c", "d", "e"], ["a", "b"]) == (
        Pair(0, 0),
        Pair(1, 1),
    )


def test_small_capitals_take_galleys_case() -> None:
    assert cased("MASPERO's", "Masrvuo's") == "Maspero's"
    assert cased("POEM", "porm") == "poem"
    assert cased("II.", "Il.") == "II."
    assert cased("Poem", "Porm") == "Poem"
    assert cased("BREASTED", "BREASTEP") == "BREASTED"


# Section 5: galley's reading of a page.


def _span(text: str, note_ref: str | None = None) -> Span:
    return Span(text, Emphasis.NONE, note_ref)


def _block(block_id: str, *spans: Span, origin: tuple[Origin, ...] = ()) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=spans,
        figure=None,
        origin=origin or (Origin(1, Box(60, 100, 460, 300)),),
    )


def _note(note_id: str, marker: str, *blocks: Block) -> Note:
    return Note(
        id=note_id,
        kind=NoteKind.FOOTNOTE,
        marker=marker,
        blocks=blocks,
        origin=blocks[0].origin,
        referenced=False,
    )


def _blocks(blocks: tuple[Block, ...], notes: tuple[Note, ...] = ()) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256="a" * 64,
        blocks=blocks,
        notes=notes,
        removals=(
            Removal(
                page_index=1,
                box=Box(60, 40, 400, 52),
                text="THE BATTLE OF KADESH 6",
                reason=RemovalReason.RUNNING_HEAD,
            ),
        ),
        word_changes=(),
        page_numbers=(),
    )


NOTE_ORIGIN = (Origin(1, Box(60, 400, 460, 500)),)
PAGE = _blocks(
    (
        _block(
            "b-p0001-001",
            _span("Tue Poem, which"),
            _span("1", "n-p0001-001"),
            _span(" is a puem."),
        ),
    ),
    (
        _note(
            "n-p0001-001",
            "%",
            _block("b-p0001-002", _span("Called by de Rouge the."), origin=NOTE_ORIGIN),
        ),
        _note(
            "n-p0001-002",
            "",
            _block("b-p0001-003", _span("Struggle of Nations, p."), origin=NOTE_ORIGIN),
        ),
    ),
)


def _changes_and_edits(
    blocks: BlocksFile, raw: str, second: str | None = None
) -> tuple[Edit, ...]:
    reading = page_reading(blocks, 1, {})
    cores = {
        token.place: next(
            b
            for b in (*blocks.blocks, *(x for n in blocks.notes for x in n.blocks))
            if b.id == token.place.block_id
        )
        .spans[token.place.span_index]
        .text[token.place.start : token.place.end]
        for token in reading
        if token.place is not None
    }
    changes = page_changes(
        1, reading, answer(raw), cores, None if second is None else answer(second)
    )
    return edits_of(blocks, changes, MODEL)


def test_reading_holds_running_head_body_then_notes_with_fixed_markers_and_references() -> (
    None
):
    reading = page_reading(PAGE, 1, {})
    assert [(token.form, token.place is None) for token in reading] == [
        ("the", True),
        ("battle", True),
        ("of", True),
        ("kadesh", True),
        ("6", True),
        ("tue", False),
        ("poem", False),
        ("which", False),
        ("1", True),
        ("is", False),
        ("a", False),
        ("puem", False),
        ("called", False),
        ("by", False),
        ("de", False),
        ("rouge", False),
        ("the", False),
        ("struggle", False),
        ("of", False),
        ("nations", False),
        ("p", False),
    ]
    assert [token.starts_note for token in reading].count(True) == 2


def test_differing_words_are_replaced_and_words_missing_from_a_note_put_in() -> None:
    raw = (
        "6\nTHE BATTLE OF KADESH\nThe POEM, which is a poem.\n"
        "15 Called by de Rougé the Bulletin.\n16 Struggle of the Nations, p. 421.\n82"
    )
    edits = _changes_and_edits(PAGE, raw)
    assert [(edit.old, edit.new, edit.reason) for edit in edits] == [
        ("Tue", "The", "vision_word"),
        ("puem.", "poem.", "vision_word"),
        ("the.", "the. Bulletin", "vision_missing_words"),
        ("of", "of the", "vision_missing_words"),
    ]
    # The model's note numbers "15" and "16" are digits; "421." and "82"
    # come after the page's last token, where nothing is put in. Rougé and
    # Rouge are one form.
    assert {edit.page_index for edit in edits} == {1}
    assert {edit.model for edit in edits} == {MODEL}
    assert {edit.second_reading for edit in edits} == {None}


def test_no_words_are_put_in_the_body() -> None:
    raw = (
        "THE BATTLE OF KADESH 6 Tue Poem, which is truly a poem. "
        "Called by de Rouge the. Struggle of Nations, p."
    )
    edits = _changes_and_edits(PAGE, raw)
    assert [(edit.old, edit.new) for edit in edits] == [("puem.", "poem.")]


def test_a_pair_less_alike_than_0_3_is_no_edit() -> None:
    raw = "THE BATTLE OF KADESH 6 Tue Poem, which is a city."
    assert _changes_and_edits(PAGE, raw) == ()


def test_a_note_marker_and_a_reference_are_never_changed() -> None:
    raw = (
        "THE BATTLE OF KADESH 6 Tue Poem, which 7 is a puem. 8 Called by de Rouge the."
    )
    edits = _changes_and_edits(PAGE, raw)
    assert all("1" not in edit.old and "%" not in edit.old for edit in edits)


def test_second_reading_is_recorded_on_note_edits_only() -> None:
    raw = "THE BATTLE OF KADESH 6 The Poem, which is a puem. Called by de Rouge thee. Struggle of Nations, p."
    second = "Called by de Rouge them. Struggle of Nations, p."
    edits = _changes_and_edits(PAGE, raw, second)
    assert [(edit.old, edit.new, edit.second_reading) for edit in edits] == [
        ("Tue", "The", None),
        ("the.", "thee.", "them"),
    ]


def test_a_word_twice_in_its_block_gets_the_words_beside_it() -> None:
    block = _block("b-p0001-001", _span("the ia and the ia here"))
    blocks = _blocks((block,))
    edits = _changes_and_edits(blocks, "THE BATTLE OF KADESH 6 the in and the ia here")
    assert [(edit.old, edit.new) for edit in edits] == [("ia and", "in and")]


def test_a_word_another_edit_changes_is_never_context() -> None:
    block = _block("b-p0001-001", _span("ia ib x ia"))
    edits = _changes_and_edits(_blocks((block,)), "THE BATTLE OF KADESH 6 in in x ia")
    # The first "ia" occurs twice alone, and its one neighbour, "ib", is
    # changed too: it is not proposed. "ib" occurs once.
    assert [(edit.old, edit.new) for edit in edits] == [("ib", "in")]


def test_each_correct_edit_applies_whether_or_not_the_others_do() -> None:
    block = _block("b-p0001-001", _span("one puem, tvo puem; three puem."))
    blocks = _blocks((block,))
    edits = _changes_and_edits(
        blocks, "THE BATTLE OF KADESH 6 one poem, two poem; three poem."
    )
    assert len(edits) == 4
    for left_out in range(len(edits)):
        kept = edits[:left_out] + edits[left_out + 1 :]
        applied = apply_edits(
            blocks, [FiledEdit(edit, Path("correct.jsonl"), 1) for edit in kept]
        )
        assert block_text(applied.blocks[0]).count("poem") >= 2


def test_a_block_on_two_pages_is_split_where_the_page_begins() -> None:
    block = _block(
        "b-p0000-001",
        _span("the first page ends here and the second goes on"),
        origin=(Origin(0, Box(60, 500, 460, 560)), Origin(1, Box(60, 100, 460, 130))),
    )

    def word(text: str, x: float, top: float) -> Word:
        return Word(text, Box(x, top, x + 30, top + 10), 90.0)

    page0 = (
        word("the", 60, 500),
        word("first", 100, 500),
        word("pagc", 140, 500),
        word("ends", 60, 520),
        word("here", 100, 520),
    )
    page1 = (word("and", 60, 100), word("the", 100, 100))
    words = WordsFile(
        source_pdf_sha256="a" * 64,
        pages=(
            PageWords(index=0, text_source=TextSource.OCR, words=page0, figures=()),
            PageWords(index=1, text_source=TextSource.OCR, words=page1, figures=()),
        ),
        removals=(),
    )
    assert split_counts(block, words) == (5, 5)


# Kadesh page 11, with the 35B model's recorded answer (section 14).


def _kadesh_page_11(second: bool) -> tuple[BlocksFile, tuple[Edit, ...]]:
    blocks = read_blocks(FIXTURES / "kadesh_p011_blocks.json")
    first = blocks.blocks[0]
    text = block_text(first)
    on_page_10 = len(tokens(text[: text.index("(Newaey.")]))
    splits = {first.id: (on_page_10, len(tokens(text)) - on_page_10)}
    reading = page_reading(blocks, 11, splits)
    every = {
        block.id: block
        for block in (*blocks.blocks, *(b for n in blocks.notes for b in n.blocks))
    }
    cores = {
        token.place: every[token.place.block_id]
        .spans[token.place.span_index]
        .text[token.place.start : token.place.end]
        for token in reading
        if token.place is not None
    }
    raw = (FIXTURES / "kadesh_p011_35b.txt").read_text(encoding="utf-8")
    second_answer = (
        answer((FIXTURES / "kadesh_p011_27b_band.txt").read_text(encoding="utf-8"))
        if second
        else None
    )
    changes = page_changes(11, reading, answer(raw), cores, second_answer)
    return blocks, edits_of(blocks, changes, MODEL)


def test_kadesh_page_11_note_is_corrected_as_section_14_says() -> None:
    blocks, edits = _kadesh_page_11(second=False)
    note = "n-p0011-002"
    note_block = next(n for n in blocks.notes if n.id == note).blocks[0]
    mine = [(edit.old, edit.new) for edit in edits if edit.block_id == note_block.id]
    assert mine == [
        ("Masrvuo's", "Maspero's"),
        ("3%)", "305)"),
        ("puem", "poem"),
        ("ia", "in"),
        ("struphes.”", "strophes.”"),
    ]
    applied = apply_edits(
        blocks,
        [FiledEdit(edit, Path("correct.jsonl"), n) for n, edit in enumerate(edits, 1)],
    )
    assert block_text(next(n for n in applied.notes if n.id == note).blocks[0]) == (
        "Maspero's statement (Struggle, p. 305) that it is “a poem in rhymed "
        "strophes.” is totally without foundation."
    )
    # Every edit applies, and none changes a marker or a reference.
    assert next(n for n in applied.notes if n.id == "n-p0011-001").marker == "%"


def test_kadesh_page_11_body_is_corrected_on_page_11_only() -> None:
    _, edits = _kadesh_page_11(second=False)
    body = [(edit.old, edit.new) for edit in edits if edit.block_id == "b-p0011-001"]
    assert ("suber", "sober") in body
    assert all(edit.page_index == 11 for edit in edits)
    # The words of the paragraph printed on page 10 are not lined up.
    first = [edit for edit in edits if edit.block_id == "b-p0010-001"]
    assert all("com-" not in edit.old for edit in first)


def test_kadesh_page_11_second_reading_flags_the_citation() -> None:
    _, edits = _kadesh_page_11(second=True)
    citation = next(edit for edit in edits if edit.old == "3%)")
    # The 27B model read "395" on the band, the 35B "305" on the page.
    assert citation.second_reading == "395"
    assert next(edit for edit in edits if edit.old == "puem").second_reading == "poem"


# Markdown's four rules (section 10).

BLOCKS = _blocks(
    (
        _block(
            "b-p0001-001",
            _span("Tue Poem, which"),
            _span("1", "n-p0001-001"),
            _span(" is a puem."),
        ),
    )
)
SHA = block_sha256(BLOCKS.blocks[0])


def _edit(old: str, new: str, *, block_id: str = "b-p0001-001", sha: str = SHA) -> Edit:
    return Edit(
        block_id=block_id,
        block_sha256=sha,
        old=old,
        new=new,
        author="owner",
        reason="r",
    )


def test_edits_apply_in_order_inside_their_span() -> None:
    edits = [
        FiledEdit(_edit("Tue", "The"), Path("edits/correct.jsonl"), 1),
        FiledEdit(_edit("puem", "poem"), Path("edits/correct.jsonl"), 2),
        FiledEdit(_edit("The Poem", "The Song"), Path("edits/owner.jsonl"), 1),
    ]
    applied = apply_edits(BLOCKS, edits)
    assert [span.text for span in applied.blocks[0].spans] == [
        "The Song, which",
        "1",
        " is a poem.",
    ]
    assert applied.blocks[0].spans[1].note_ref == "n-p0001-001"


@pytest.mark.parametrize(
    ("edit", "broken"),
    [
        (_edit("Tue", "The", block_id="b-p0009-001"), "is not in blocks.json"),
        (_edit("Tue", "The", sha="0" * 12), "block_sha256"),
        (_edit("e", "x"), "exactly once"),
        (_edit("which1 is", "which is"), "not a note reference"),
        (_edit("1", "2"), "not a note reference"),
    ],
    ids=["no_block", "checksum", "not_once", "across_spans", "a_reference"],
)
def test_an_edit_that_breaks_a_rule_is_an_error_naming_file_line_and_rule(
    edit: Edit, broken: str
) -> None:
    edits = [
        FiledEdit(_edit("puem", "poem"), Path("edits/correct.jsonl"), 1),
        FiledEdit(edit, Path("edits/owner.jsonl"), 3),
    ]
    with pytest.raises(EditError, match="1 edits do not apply") as raised:
        apply_edits(BLOCKS, edits)
    assert "edits/owner.jsonl, line 3" in str(raised.value)
    assert broken in str(raised.value)


# The calls to LM Studio (section 4), with a server inside the test.


@dataclass
class _FakeLmStudio:
    """A stand-in for LM Studio on localhost: it lists `models` and answers
    each page from `answers`, by the SHA-256 of the image it is sent, or
    with `status` when that is not 200."""

    models: tuple[str, ...]
    answers: dict[str, str] = field(default_factory=dict)
    finish: str = "stop"
    status: int = 200
    bodies: list[dict[str, object]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _image_key(png: bytes) -> str:
    return hashlib.sha256(png).hexdigest()


def _handler(fake: _FakeLmStudio) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _send(self, status: int, content: object) -> None:
            data = json.dumps(content).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._send(200, {"data": [{"id": model} for model in fake.models]})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with fake.lock:
                fake.bodies.append(body)
            if fake.status != 200:
                self._send(fake.status, {"error": "Model is not loaded"})
                return
            url = body["messages"][0]["content"][1]["image_url"]["url"]
            png = base64.b64decode(url.removeprefix("data:image/png;base64,"))
            text = fake.answers.get(_image_key(png), "")
            self._send(
                200,
                {
                    "choices": [
                        {"message": {"content": text}, "finish_reason": fake.finish}
                    ]
                },
            )

    return Handler


@pytest.fixture
def lm_studio() -> Iterator[Callable[..., tuple[_FakeLmStudio, str]]]:
    servers: list[ThreadingHTTPServer] = []

    def start(
        models: tuple[str, ...] = (MODEL,), *, finish: str = "stop", status: int = 200
    ) -> tuple[_FakeLmStudio, str]:
        fake = _FakeLmStudio(models, finish=finish, status=status)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(fake))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return fake, f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_request_body_is_the_measurements() -> None:
    body = request_body(MODEL, b"png")
    assert body["temperature"] == 0
    assert body["reasoning_effort"] == "none"
    assert body["max_tokens"] == 6000
    assert body["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,cG5n"},
                },
            ],
        }
    ]


def test_no_server_is_an_error_that_says_to_start_it() -> None:
    server = f"http://127.0.0.1:{_closed_port()}"
    with pytest.raises(ExternalProgramError, match="not running at .*lms server start"):
        check_models(server, (MODEL,))


def test_a_model_lm_studio_lacks_is_an_error_that_says_how_to_get_it(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    _, server = lm_studio(models=(SECOND,))
    with pytest.raises(
        ExternalProgramError,
        match=f"no model {MODEL}: download it with `lms get {MODEL}`; it has {SECOND}",
    ):
        check_models(server, (MODEL,))


def test_an_http_error_names_the_page_and_lm_studios_message(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    _, server = lm_studio(status=400)
    with pytest.raises(
        ExternalProgramError, match="page 11.*HTTP 400.*Model is not loaded"
    ):
        read_image(server, MODEL, b"png", "page 11")


def test_an_answer_cut_short_is_marked(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    fake, server = lm_studio(finish="length")
    reading = read_image(server, MODEL, b"png", "page 11")
    assert reading.cut_short
    assert fake.bodies[0]["model"] == MODEL


# The stage on the excerpt kadesh_redo, the model's answers recorded.

KADESH_REDO = "kadesh_redo"


def _excerpt_folder(
    tmp_path: Path, redo_excerpt_run: Callable[[str], BookFolder], server: str
) -> tuple[BookFolder, BookConfig]:
    source = redo_excerpt_run(KADESH_REDO)
    tmp_path.mkdir(parents=True, exist_ok=True)
    folder = BookFolder(tmp_path)
    for name in ("pages.json", "words.json", "lines.json", "blocks.json"):
        (tmp_path / name).write_bytes((source.root / name).read_bytes())
    shutil.copytree(source.images_dir, folder.images_dir)
    toml = source.book_toml.read_text(encoding="utf-8")
    folder.book_toml.write_text(
        toml + f'correct = true\ncorrect_server = "{server}"\n', encoding="utf-8"
    )
    return folder, read_config(folder.book_toml)


def _recorded_answers(pdf: Path) -> dict[str, str]:
    answers = {}
    for path in sorted((FIXTURES / KADESH_REDO).glob("p*.txt")):
        page = int(path.stem[1:])
        answers[_image_key(_png(pdfium.render(pdf, page, 300), None))] = path.read_text(
            encoding="utf-8"
        )
    return answers


# Renders with PDFium, and the run is about 10 s.
@pytest.mark.thread_unsafe
@pytest.mark.tesseract
@pytest.mark.pandoc
def test_excerpt_edits_are_the_same_with_1_and_8_workers_and_markdown_applies_them(
    tmp_path: Path,
    redo_excerpt_run: Callable[[str], BookFolder],
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    from galley import markdown

    fake, server = lm_studio()
    written = {}
    for workers in (1, 8):
        folder, config = _excerpt_folder(
            tmp_path / str(workers), redo_excerpt_run, server
        )
        if not fake.answers:
            fake.answers.update(_recorded_answers(config.pdf))
        correct.run(folder, config, workers=workers)
        written[workers] = folder.correct_jsonl.read_bytes()
    assert written[1] == written[8]
    edits = read_edits(folder.correct_jsonl)
    assert len(edits) > 100
    assert {edit.author for edit in edits} == {"correct"}
    assert ("puem", "poem") in {(edit.old, edit.new) for edit in edits}
    markdown.run(folder, config)
    assert "a poem in rhymed" in folder.book_md.read_text(encoding="utf-8")


# One page of Kadesh read by the model in LM Studio (section 15).


# The model takes about 25 s on the page, more when LM Studio loads it.
@pytest.mark.vision_model
@pytest.mark.timeout(600)
@pytest.mark.thread_unsafe
@pytest.mark.tesseract
def test_lm_studio_reads_kadesh_page_11_and_its_edits_fix_the_note(
    tmp_path: Path, redo_excerpt_run: Callable[[str], BookFolder]
) -> None:
    folder, config = _excerpt_folder(
        tmp_path, redo_excerpt_run, "http://localhost:1234"
    )
    correct.check_server(config)
    blocks = read_blocks(folder.blocks_json)
    words = read_words(folder.words_json)
    splits = {
        block.id: split_counts(block, words)
        for block in (*blocks.blocks, *(b for n in blocks.notes for b in n.blocks))
        if len(block.origin) > 1
    }
    reading = page_reading(blocks, 3, splits)
    every = {
        block.id: block
        for block in (*blocks.blocks, *(b for n in blocks.notes for b in n.blocks))
    }
    cores = {
        token.place: every[token.place.block_id]
        .spans[token.place.span_index]
        .text[token.place.start : token.place.end]
        for token in reading
        if token.place is not None
    }
    raw = read_image(
        config.correct_server,
        MODEL,
        _png(pdfium.render(config.pdf, 3, 300), None),
        "page 3",
    )
    edits = edits_of(blocks, page_changes(3, reading, answer(raw.text), cores), MODEL)
    pairs = {(edit.old, edit.new) for edit in edits}
    assert ("puem", "poem") in pairs
    assert ("Masrvuo's", "Maspero's") in pairs
    references = {
        span.text
        for block in every.values()
        for span in block.spans
        if span.note_ref is not None
    }
    assert not any(edit.old in references for edit in edits)
