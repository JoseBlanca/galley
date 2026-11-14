"""Tests of galley.text_layer (spec sections 4 and 6).

The race test replaces pdfminer's table of keywords, which every thread
shares, so it is marked thread_unsafe: `pytest --parallel-threads=8` runs
it once.
"""

import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Final, override

import pdfplumber
import pytest
from pdfminer import psparser
from pdfplumber.utils.exceptions import PdfminerException

from galley.errors import PdfError
from galley.text_layer import open_pdf

KADESH = "kadesh_8-17"
THREADS_AT_ONCE: Final[int] = 4
TRAILER: Final[bytes] = b"trailer"
# How long a thread waits for the others in the table below. Without the
# lock they all arrive within milliseconds; with it, each wait runs out.
WAIT_FOR_OTHERS_S: Final[float] = 0.2


type _Name = str | bytes


class _TrailerRaceTable(dict[_Name, psparser.PSKeyword]):
    """pdfminer's keyword table without `trailer`, in which the race of
    PSSymbolTable.intern (check, then store) happens every time it can.

    A thread that does not find `trailer` waits until every thread has not
    found it, and a thread that stores it waits until every thread has
    stored its own, so that each thread's later lookup finds the keyword
    stored last. Each wait ends after WAIT_FOR_OTHERS_S, as it does when
    the threads open one after the other.
    """

    def __init__(
        self, entries: dict[_Name, psparser.PSKeyword], thread_count: int
    ) -> None:
        super().__init__(
            (name, keyword) for name, keyword in entries.items() if name != TRAILER
        )
        self._count_lock = threading.Lock()
        self._thread_count = thread_count
        self._misses = 0
        self._stores = 0
        self._all_missed = threading.Event()
        self._all_stored = threading.Event()

    @override
    def __contains__(self, name: object) -> bool:
        found = super().__contains__(name)
        if name == TRAILER and not found:
            self._count(self._all_missed, stores=False)
        return found

    @override
    def __setitem__(self, name: _Name, keyword: psparser.PSKeyword) -> None:
        super().__setitem__(name, keyword)
        if name == TRAILER:
            self._count(self._all_stored, stores=True)

    def _count(self, everyone: threading.Event, *, stores: bool) -> None:
        with self._count_lock:
            if stores:
                self._stores += 1
                arrived = self._stores
            else:
                self._misses += 1
                arrived = self._misses
            if arrived == self._thread_count:
                everyone.set()
        everyone.wait(WAIT_FOR_OTHERS_S)


@pytest.fixture
def trailer_race() -> Iterator[None]:
    """pdfminer's keyword table replaced by a _TrailerRaceTable for the
    test, and the original put back after it, whatever its outcome."""
    original = psparser.PSKeywordTable.dict
    psparser.PSKeywordTable.dict = _TrailerRaceTable(original, THREADS_AT_ONCE)
    yield
    psparser.PSKeywordTable.dict = original


def _open_at_once(
    open_document: Callable[[Path], pdfplumber.PDF], pdf: Path
) -> tuple[str, ...]:
    """The errors of THREADS_AT_ONCE threads each opening and closing its own
    document of `pdf` with `open_document`, as `type: message`."""
    errors: list[str] = []
    errors_lock = threading.Lock()

    def open_and_close() -> None:
        # The exception is recorded so that the test can count them; a
        # thread's own exception would only reach threading.excepthook.
        try:
            with open_document(pdf):
                pass
        except (PdfminerException, PdfError) as err:
            with errors_lock:
                errors.append(f"{type(err).__name__}: {err}")

    threads = tuple(
        threading.Thread(target=open_and_close) for _ in range(THREADS_AT_ONCE)
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return tuple(errors)


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("trailer_race")
def test_pdfplumber_open_from_threads_at_once_raises_trailer_error(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    # The race the lock prevents: every thread but the one that stored the
    # keyword last fails.
    errors = _open_at_once(pdfplumber.open, excerpt_pdf[KADESH])
    assert errors == ("PdfminerException: /b'trailer'",) * (THREADS_AT_ONCE - 1)


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("trailer_race")
def test_open_pdf_from_threads_at_once_raises_nothing(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    assert _open_at_once(open_pdf, excerpt_pdf[KADESH]) == ()


def test_open_pdf_gives_the_pages_of_the_excerpt(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    with open_pdf(excerpt_pdf[KADESH]) as pdf:
        assert len(pdf.pages) == 10


def test_open_pdf_of_a_truncated_pdf_raises_pdf_error_naming_it(
    excerpt_pdf: frozendict[str, Path], tmp_path: Path
) -> None:
    whole = excerpt_pdf[KADESH].read_bytes()
    truncated = tmp_path / "truncated.pdf"
    truncated.write_bytes(whole[: len(whole) // 2])
    with pytest.raises(PdfError, match="truncated.pdf") as caught:
        open_pdf(truncated)
    assert isinstance(caught.value.__cause__, PdfminerException)


def test_open_pdf_of_a_text_file_raises_pdf_error_naming_it(tmp_path: Path) -> None:
    text_file = tmp_path / "not_a.pdf"
    text_file.write_text("This is a text file, not a PDF.\n", encoding="utf-8")
    with pytest.raises(PdfError, match="not_a.pdf") as caught:
        open_pdf(text_file)
    assert isinstance(caught.value.__cause__, PdfminerException)
