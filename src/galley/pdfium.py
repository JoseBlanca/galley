"""The one thread that calls PDFium: page counts, page sizes and renders.

PDFium is not thread-safe, not even across two documents (pypdfium2
documentation), so every call into pypdfium2 in galley is made here, in a
single thread that lives as long as the process. Each public function sends
its request to that thread and waits for the answer, so it can be called
from any thread; calls from several threads run one after the other. Each
request opens the PDF, does its work and closes every page, bitmap and
document it opened before it returns, so that no pypdfium2 finalizer is left
to run PDFium later from another thread's garbage collection.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pypdfium2

from galley.errors import PdfError
from galley.model import RenderedPage

# A PDF point is 1/72 of an inch.
POINTS_PER_INCH: Final[int] = 72

# One worker: a ThreadPoolExecutor keeps its thread for the life of the
# process and takes submissions from any thread.
_PDFIUM_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="galley-pdfium")


@dataclass(frozen=True, slots=True)
class PageSize:
    """A page's width and height in PDF points, as pypdfium2 gives them: the
    crop box clipped to the media box, as 32-bit floats."""

    width_pt: float
    height_pt: float


def page_count(pdf: Path) -> int:
    """The number of pages of `pdf`. A file that is not a PDF, or a path
    that is no file, is a PdfError."""
    return _in_pdfium_thread(_page_count, pdf)


def page_size(pdf: Path, page_index: int) -> PageSize:
    """The size of page `page_index` (from 0) of `pdf`, in points.

    These numbers can differ from pdfplumber's in the last decimals, so a
    stage that places pdfplumber's word boxes takes its sizes from
    pdfplumber. A file that is not a PDF, a path that is no file, or a page
    index outside the document, is a PdfError.
    """
    return _in_pdfium_thread(_page_size, pdf, page_index)


def render(pdf: Path, page_index: int, dpi: int) -> RenderedPage:
    """Page `page_index` (from 0) of `pdf` rendered at `dpi` dots per inch:
    8-bit grayscale pixels, row by row with no padding.

    A file that is not a PDF, a path that is no file, or a page index
    outside the document, is a PdfError; a `dpi` below 1 is a ValueError.
    """
    if dpi < 1:
        message = f"dpi must be at least 1, not {dpi}"
        raise ValueError(message)
    return _in_pdfium_thread(_render, pdf, page_index, dpi)


def strip_stride(buffer: bytes, width_px: int, height_px: int, stride: int) -> bytes:
    """The pixels of a grayscale bitmap whose rows are `stride` bytes apart,
    row by row, with the padding after each row's `width_px` bytes dropped.

    A stride below `width_px`, or a buffer whose length is not
    `stride * height_px`, is a ValueError.
    """
    if stride < width_px:
        message = (
            f"a stride of {stride} bytes is shorter than a row of {width_px} pixels"
        )
        raise ValueError(message)
    if len(buffer) != stride * height_px:
        message = (
            f"a buffer of {len(buffer)} bytes is not {height_px} rows "
            f"of a stride of {stride} bytes"
        )
        raise ValueError(message)
    return b"".join(
        buffer[row * stride : row * stride + width_px] for row in range(height_px)
    )


def _in_pdfium_thread[**P, R](
    request: Callable[P, R], *args: P.args, **kwargs: P.kwargs
) -> R:
    return _PDFIUM_THREAD.submit(request, *args, **kwargs).result()


# The functions below run only in the PDFium thread. Each object pypdfium2
# gives is entered in a `with closing(...)`, so that it is closed, in the
# reverse order of opening, before the function returns or raises.


def _open(pdf: Path) -> pypdfium2.PdfDocument:
    try:
        return pypdfium2.PdfDocument(pdf)
    except pypdfium2.PdfiumError as err:
        message = f"{pdf}: PDFium cannot read it as a PDF: {err}"
        raise PdfError(message) from err
    except (FileNotFoundError, IsADirectoryError) as err:
        # pypdfium2 raises FileNotFoundError for a directory too.
        message = f"{pdf}: no such PDF file (missing, or a directory)"
        raise PdfError(message) from err


def _check_page_index(
    pdf: Path, document: pypdfium2.PdfDocument, page_index: int
) -> None:
    count = len(document)
    if not 0 <= page_index < count:
        message = (
            f"{pdf}: page index {page_index} is outside the document of {count} pages"
        )
        raise PdfError(message)


def _page_count(pdf: Path) -> int:
    with closing(_open(pdf)) as document:
        return len(document)


def _page_size(pdf: Path, page_index: int) -> PageSize:
    with closing(_open(pdf)) as document:
        _check_page_index(pdf, document, page_index)
        width_pt, height_pt = document.get_page_size(page_index)
        return PageSize(width_pt=width_pt, height_pt=height_pt)


def _render(pdf: Path, page_index: int, dpi: int) -> RenderedPage:
    with closing(_open(pdf)) as document:
        _check_page_index(pdf, document, page_index)
        with (
            closing(document[page_index]) as page,
            closing(page.render(scale=dpi / POINTS_PER_INCH, grayscale=True)) as bitmap,
        ):
            # Grayscale is one byte per pixel; anything else would make the
            # stripped rows a slice of each pixel's channels.
            assert bitmap.n_channels == 1, bitmap.mode
            pixels = strip_stride(
                bytes(bitmap.buffer), bitmap.width, bitmap.height, bitmap.stride
            )
            return RenderedPage(
                page_index=page_index,
                dpi=dpi,
                width_px=bitmap.width,
                height_px=bitmap.height,
                pixels=pixels,
            )
