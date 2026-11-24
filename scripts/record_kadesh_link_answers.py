"""Record the vision model's answers to the note links' prompt (correct
spec section 9b) on Kadesh's pages where a footnote starts in the three
excerpts kadesh_8-17, kadesh_29-38 and kadesh_59-68, for the tests of
plan more-note-links task 5.2.

Needs LM Studio running at http://localhost:1234 with qwen/qwen3.6-35b-a3b
loaded (this script loads nothing). One request per page, in one thread,
about 50 s each. Writes tests/fixtures/correct/kadesh_links/kNNN.txt, NNN
the page index in the whole book; a page already recorded is skipped.

    uv run python scripts/record_kadesh_link_answers.py
"""

import sys
from pathlib import Path

from galley import pdfium
from galley.correct import page_png
from galley.correct._lmstudio import LINKS_PROMPT, read_image

PDF = Path("samples/public_domain/battleofkadeshst00breauoft.pdf")
SERVER = "http://localhost:1234"
MODEL = "qwen/qwen3.6-35b-a3b"
# Pages of the three excerpts where a footnote starts (the whole book's
# structure, plan more-note-links task 5.1). 8, 9, 11 and 15 are recorded
# already in tests/fixtures/correct/kadesh_redo_links/ and are copied.
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
OUT = Path("tests/fixtures/correct/kadesh_links")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for page in PAGES:
        path = OUT / f"k{page:03d}.txt"
        if path.exists():
            continue
        png = page_png(pdfium.render(PDF, page, 300), None)
        reading = read_image(
            SERVER, MODEL, png, f"the note references of page {page}", LINKS_PROMPT
        )
        if reading.cut_short:
            sys.stderr.write(f"page {page}: answer cut short, not written" + "\n")
            continue
        path.write_text(reading.text, encoding="utf-8")
        sys.stderr.write(f"page {page}: {len(reading.text)} characters" + "\n")


if __name__ == "__main__":
    main()
