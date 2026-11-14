# book2epub

Turns a PDF of a mostly-text book into an EPUB that reflows on a Kindle.
The stages run in order and pass files to each other:

    analyze → extract → structure → correct (optional) → markdown → epub

Each stage is a subpackage of `src/book2epub/`. The formats of the files
between stages are defined once, in `src/book2epub/model.py`, and described
in `docs/architecture.md` (both still to be written). A stage reads only its
input file and writes only its output file, so each one can be built and
tested on its own, with fixture files in `tests/`.

## Environment

- uv for everything: `uv run`, `uv add`, `uv run pytest`, `uv run ruff`.
- Python 3.15 free-threaded (`3.15t`, pinned in `.python-version`). A new
  dependency must install on it as a wheel; check with
  `uv pip install --only-binary :all: <pkg>` before adding it. PyMuPDF and
  PyYAML do not, which is why the project uses pypdfium2, pdfplumber and
  TOML.
- Work is parallel by threads. PDFium (pypdfium2) is not thread-safe: every
  call into it runs in one thread, and the rendered images go to the workers.
- Pandoc builds the EPUB; Tesseract does the OCR. Both are Homebrew binaries.

## Samples

`samples/` holds PDFs of copyrighted books and is ignored by git. Short
excerpts used as test fixtures stay in this private repository and must not
be published.

Earlier OCR and constrained-correction code worth reusing is in
`~/devel/tomato_history_web_site/tools/ocr_lab/` (`lib/common.py`,
`reocr.py`, `triage.py`, `folio.py`, and `results/NOTE.md` for what failed).
