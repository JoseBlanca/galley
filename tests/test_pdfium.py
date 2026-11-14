"""Tests of galley.pdfium (spec section 4, architecture sections 8 and 12).

Every test that calls PDFium is marked thread_unsafe, so that
`pytest --parallel-threads=8` runs it once: the module runs one request
at a time, and eight copies would only cost eight times as long.
"""

import gc
import logging
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import FrameType

import pypdfium2_cfg
import pytest

from galley.errors import PdfError
from galley.model import RenderedPage
from galley.pdfium import PageSize, page_count, page_size, render, strip_stride

KADESH = "kadesh_8-17"
GIERKE = "gierke_86-93_270-271"
THREADS_AT_ONCE = 6


@pytest.fixture
def text_file(tmp_path: Path) -> Path:
    path = tmp_path / "not_a.pdf"
    path.write_text("This is a text file, not a PDF.\n", encoding="utf-8")
    return path


@pytest.mark.thread_unsafe
@pytest.mark.parametrize("name", [KADESH, GIERKE])
def test_page_count_of_each_excerpt_is_10(
    excerpt_pdf: frozendict[str, Path], name: str
) -> None:
    assert page_count(excerpt_pdf[name]) == 10


@pytest.mark.thread_unsafe
def test_page_size_of_kadesh_page_0_is_the_crop_box_clipped_to_the_media_box(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    assert page_size(excerpt_pdf[KADESH], 0) == PageSize(
        width_pt=508.29998779296875, height_pt=728.1599731445312
    )


@pytest.mark.thread_unsafe
def test_render_of_gierke_page_0_at_300_dpi_is_1568_by_2590_gray_pixels(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    page = render(excerpt_pdf[GIERKE], 0, 300)

    assert (page.page_index, page.dpi, page.width_px, page.height_px) == (
        0,
        300,
        1568,
        2590,
    )
    assert len(page.pixels) == page.width_px * page.height_px
    # A scanned page is mostly white paper with dark print: both must be there,
    # or the render drew nothing.
    assert max(page.pixels) > 200
    assert min(page.pixels) < 50


@pytest.mark.thread_unsafe
def test_render_of_another_page_gives_its_index_and_other_pixels(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    page_0 = render(excerpt_pdf[GIERKE], 0, 72)
    page_1 = render(excerpt_pdf[GIERKE], 1, 72)

    assert page_1.page_index == 1
    assert page_1.pixels != page_0.pixels


@pytest.mark.thread_unsafe
def test_render_from_6_threads_at_once_gives_6_times_the_bytes_of_one_call(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    pdf = excerpt_pdf[GIERKE]
    alone = render(pdf, 0, 300)
    barrier = threading.Barrier(THREADS_AT_ONCE)

    def render_after_barrier(_: int) -> RenderedPage:
        barrier.wait()
        return render(pdf, 0, 300)

    with ThreadPoolExecutor(THREADS_AT_ONCE) as executor:
        pages = tuple(executor.map(render_after_barrier, range(THREADS_AT_ONCE)))

    assert pages == (alone,) * THREADS_AT_ONCE


@pytest.fixture
def pypdfium2_callers() -> Iterator[set[int]]:
    """The idents of the threads that run any Python function of pypdfium2
    while the test runs, recorded by a profile function on every thread."""
    callers: set[int] = set()

    def record(frame: FrameType, event: str, _: object) -> None:
        if event == "call" and "pypdfium2" in frame.f_code.co_filename:
            callers.add(threading.get_ident())

    threading.setprofile_all_threads(record)
    yield callers
    threading.setprofile_all_threads(None)


@pytest.mark.thread_unsafe
def test_every_pypdfium2_call_from_6_threads_runs_in_one_other_thread(
    excerpt_pdf: frozendict[str, Path], pypdfium2_callers: set[int]
) -> None:
    pdf = excerpt_pdf[GIERKE]
    barrier = threading.Barrier(THREADS_AT_ONCE)

    def call_each_function(page_index: int) -> int:
        barrier.wait()
        render(pdf, page_index, 72)
        page_size(pdf, page_index)
        return page_count(pdf)

    with ThreadPoolExecutor(THREADS_AT_ONCE) as executor:
        counts = tuple(executor.map(call_each_function, range(THREADS_AT_ONCE)))

    assert counts == (10,) * THREADS_AT_ONCE
    assert len(pypdfium2_callers) == 1
    assert threading.get_ident() not in pypdfium2_callers


@pytest.fixture
def pypdfium2_close_log(
    capfd: pytest.CaptureFixture[str],
) -> Iterator[Callable[[], str]]:
    """What pypdfium2 writes to stderr each time it closes an object, with
    `(explicit)` or `(by_parent)` for a close our code made and `(auto)` for
    one made by a finalizer."""
    level = pypdfium2_cfg.DEBUG_AUTOCLOSE.value
    pypdfium2_cfg.DEBUG_AUTOCLOSE.value = logging.DEBUG

    def read() -> str:
        gc.collect()
        return capfd.readouterr().err

    yield read
    pypdfium2_cfg.DEBUG_AUTOCLOSE.value = level


@pytest.mark.thread_unsafe
def test_every_page_bitmap_and_document_is_closed_explicitly(
    excerpt_pdf: frozendict[str, Path],
    text_file: Path,
    pypdfium2_close_log: Callable[[], str],
) -> None:
    pdf = excerpt_pdf[GIERKE]
    page_count(pdf)
    page_size(pdf, 0)
    render(pdf, 0, 72)
    with pytest.raises(PdfError):
        render(pdf, 10, 72)
    with pytest.raises(PdfError):
        page_count(text_file)

    log = pypdfium2_close_log()

    # Four documents (the text file opens none), one page and one bitmap.
    assert log.count("Close (explicit) <PdfDocument") == 4
    assert log.count("Close (explicit) <PdfPage") == 1
    assert log.count("Close (explicit) <PdfBitmap") == 1
    assert "(auto)" not in log


@pytest.mark.thread_unsafe
@pytest.mark.parametrize("page_index", [10, -1])
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda pdf, index: page_size(pdf, index), id="page_size"),
        pytest.param(lambda pdf, index: render(pdf, index, 72), id="render"),
    ],
)
def test_page_index_outside_the_document_raises_pdf_error_naming_file_index_and_count(
    excerpt_pdf: frozendict[str, Path],
    call: Callable[[Path, int], object],
    page_index: int,
) -> None:
    pdf = excerpt_pdf[KADESH]
    with pytest.raises(PdfError) as raised:
        call(pdf, page_index)

    message = str(raised.value)
    assert str(pdf) in message
    assert f"page index {page_index}" in message
    assert "10 pages" in message


@pytest.mark.thread_unsafe
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(page_count, id="page_count"),
        pytest.param(lambda pdf: page_size(pdf, 0), id="page_size"),
        pytest.param(lambda pdf: render(pdf, 0, 72), id="render"),
    ],
)
def test_text_file_given_as_pdf_raises_pdf_error_naming_it(
    text_file: Path, call: Callable[[Path], object]
) -> None:
    with pytest.raises(PdfError, match="not_a.pdf") as raised:
        call(text_file)

    assert raised.value.__cause__ is not None


def test_strip_stride_drops_the_padding_after_each_row() -> None:
    buffer = bytes([1, 2, 3, 0, 4, 5, 6, 0])

    assert strip_stride(buffer, width_px=3, height_px=2, stride=4) == bytes(
        [1, 2, 3, 4, 5, 6]
    )


def test_strip_stride_without_padding_gives_the_buffer() -> None:
    buffer = bytes([1, 2, 3, 4, 5, 6])

    assert strip_stride(buffer, width_px=3, height_px=2, stride=3) == buffer


@pytest.mark.parametrize(
    ("buffer", "width_px", "height_px", "stride"),
    [
        pytest.param(bytes(8), 5, 2, 4, id="stride_below_width"),
        pytest.param(bytes(7), 3, 2, 4, id="buffer_short_of_last_padding"),
        pytest.param(bytes(12), 3, 2, 4, id="buffer_of_three_rows"),
    ],
)
def test_strip_stride_refuses_a_buffer_that_does_not_fit_its_shape(
    buffer: bytes, width_px: int, height_px: int, stride: int
) -> None:
    with pytest.raises(ValueError, match="stride"):
        strip_stride(buffer, width_px, height_px, stride)
