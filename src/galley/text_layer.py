"""Opening a PDF with pdfplumber, to read its text layer.

Every pdfplumber document galley reads is opened by `open_pdf`, which
opens one document at a time in the whole process. Reading the pages of
the documents it opened stays parallel, one document per worker thread.

The lock is there because pdfminer.six 20260107, which pdfplumber reads
PDFs with, is not safe to open from two threads at once. It keeps every
keyword it meets, such as `trailer`, in one dictionary that all threads
share, and adds a new one by checking for it and then storing it
(`PSSymbolTable.intern` in psparser.py), with no lock. Two threads that
meet `trailer` for the first time can each store a keyword object of
their own, the second replacing the first. Opening a PDF then checks that
the keyword it read is the stored one by identity (`assert kwd is
KWD(b"trailer")` in `PDFXRef.load_trailer`, pdfdocument.py), and that
fails in the thread whose object was replaced: `pdfplumber.open` raises
`PdfminerException: /b'trailer'`. Measured on 14 November 2026 on an M5
Pro: 3 of 450 fresh processes running analyze and extract on the whole
Kadesh book with 6, 12 and 24 workers failed so, and 0 of 150 with 1
worker. It can happen only while a process first meets the keyword, which
is while documents open, so the lock is held only then.
"""

import threading
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from galley.errors import PdfError

__all__ = ["open_pdf"]

_OPEN_LOCK = threading.Lock()


def open_pdf(pdf: Path) -> pdfplumber.PDF:
    """`pdf` opened with pdfplumber, to be closed by the caller (it is a
    context manager). Only one thread of the process opens a document at a
    time; the document is then used by the thread that opened it alone.

    A file pdfplumber cannot read as a PDF, such as a truncated one, is a
    PdfError naming it, whose cause is pdfplumber's PdfminerException.
    """
    with _OPEN_LOCK:
        try:
            return pdfplumber.open(pdf)
        except PdfminerException as err:
            message = f"{pdf}: pdfplumber cannot read it as a PDF: {err}"
            raise PdfError(message) from err
