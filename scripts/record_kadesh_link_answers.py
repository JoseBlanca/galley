"""Record the vision model's answers to the note links' prompt (correct
spec section 9b) on Kadesh's pages where a footnote starts in the three
excerpts kadesh_8-17, kadesh_29-38 and kadesh_59-68, for the tests of
plan more-note-links task 5.2.

Needs LM Studio running at http://localhost:1234 with qwen/qwen3.6-35b-a3b
loaded (this script loads nothing). One request per page, in one thread,
about 50 s each. Writes tests/fixtures/correct/kadesh_links/kNNN.txt, NNN
the page index in the whole book; a page already recorded is skipped. The
book is read from GALLEY_SAMPLES or the main checkout's samples/, as
fetch_samples.py finds it, so the script runs from a worktree too.

All 22 pages were recorded on 24 November 2026. Pages 8, 9, 11 and 15 are
also in tests/fixtures/correct/kadesh_redo_links/ (p000, p001, p003,
p007), recorded earlier; the two answers of each page differ.

    uv run python scripts/record_kadesh_link_answers.py
"""

import logging
from pathlib import Path

from fetch_samples import _samples_dir

from galley import pdfium
from galley.correct import _DPI, page_png
from galley.correct._lmstudio import LINKS_PROMPT, read_image

BOOK = "public_domain/battleofkadeshst00breauoft.pdf"
SERVER = "http://localhost:1234"
MODEL = "qwen/qwen3.6-35b-a3b"
# Pages of the three excerpts where a footnote starts (the whole book's
# structure, plan more-note-links task 5.1).
PAGES = (
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    29,
    30,
    31,
    32,
    33,
    36,
    37,
    38,
    59,
    60,
    61,
    62,
    63,
    66,
)
OUT = Path(__file__).parent.parent / "tests/fixtures/correct/kadesh_links"

_logger = logging.getLogger(__name__)


def main() -> None:
    pdf = _samples_dir() / BOOK
    OUT.mkdir(parents=True, exist_ok=True)
    for page in PAGES:
        path = OUT / f"k{page:03d}.txt"
        if path.exists():
            continue
        png = page_png(pdfium.render(pdf, page, _DPI), None)
        reading = read_image(
            SERVER, MODEL, png, f"the note references of page {page}", LINKS_PROMPT
        )
        if reading.cut_short:
            _logger.warning("page %d: answer cut short, not written", page)
            continue
        path.write_text(reading.text, encoding="utf-8")
        _logger.info("page %d: %d characters", page, len(reading.text))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
