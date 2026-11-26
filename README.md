# galley

galley turns the PDF of a scanned, mostly-text book into an EPUB that
reflows on an e-reader: the text fills the screen at whatever font size
you choose, instead of showing a picture of each printed page. It takes
away what belonged to the printed page (the title or chapter name repeated
at the top of each page, page numbers, lines broken at the margin, words
hyphenated across lines) and keeps every word of the book, its headings,
paragraphs, footnotes and margin notes.

The name is the printer's galley: the typeset text as one continuous
column, before it is cut into pages.

## What galley reads

galley reads scanned books whose PDF has a **text layer**. A scan is a
picture of each printed page; the text layer is invisible text laid over
each picture, made by **OCR** (optical character recognition, a program
reading the letters in the picture). It is what lets you select and
search the words in a PDF viewer. The PDFs of the Internet Archive have
one. A page without a text layer, such as a blank page, a cover or a
page the scanner's OCR skipped, galley reads itself with Tesseract (below).
A PDF with no text layer on any page has not been tried.

The OCR of an old scan misreads words. galley re-reads small print with
Tesseract, an OCR program, where Tesseract reads it better, and can
have a language model on your own computer correct words (`--correct`,
below).

## Install

You need, on macOS or Linux:

- **uv**, which installs Python and galley's Python libraries
  ([install uv](https://docs.astral.sh/uv/getting-started/installation/)).
  galley needs Python 3.15 in its free-threaded build, which runs threads
  in parallel; uv downloads it by itself, so you do not install Python.
- **Pandoc**, which writes the EPUB.
- **Tesseract** with the language data of your book.

On macOS with Homebrew (`tesseract-lang` holds every language but
English, which comes with `tesseract`):

```
brew install pandoc tesseract tesseract-lang
```

On Debian or Ubuntu, with one `tesseract-ocr-<language>` package for each
language of your books (`eng`, `spa`, `fra`, `deu`, `ita`):

```
sudo apt install pandoc tesseract-ocr tesseract-ocr-eng
```

Then install galley itself, which gives you the command `galley2epub`:

```
git clone https://github.com/JoseBlanca/galley.git
uv tool install --python 3.15t ./galley
```

If your shell then cannot find `galley2epub`, run `uv tool update-shell`
and open a new terminal. Or skip the install and run `uv run galley2epub`
inside the `galley` folder.

Tested on macOS with Python 3.15.0 (free-threaded), Pandoc 3.14 and
Tesseract 5.5.4. The Debian and Ubuntu commands have not been tested.

## Convert a simple book

Give `galley2epub run` the PDF, the book's title, each author with its
own `--author`, in the order printed, and the language, one of `en`,
`es`, `fr`, `de` or `it`:

```
galley2epub run gierke.pdf --title "Political Theories of the Middle Age" \
    --author "Otto Gierke" --author "F. W. Maitland" --language en
```

galley makes a **book folder** beside the PDF, named after it
(`gierke.pdf` gets `gierke/`), and writes everything about the book
there. The EPUB is `gierke/book.epub`; the last line of the log gives its
path. Running the same command again rebuilds the book from the PDF. If
the folder already holds a `book.toml` with other settings, galley stops
and tells you to convert from the folder, as the next section shows.

A ten-page excerpt of this book took 9 s; the whole book, 290 pages,
took 69 s with the default 6 threads (`--workers` changes the number),
on an Apple M5 Pro. The first run of a language takes a few seconds
more, to unpack Tesseract's dictionary of that language into
`~/.cache/galley/`.

## When a book needs a book.toml

The command above writes `gierke/book.toml`, the book's config, with the
four things you gave it. A book that needs more settings is converted
from its folder instead, after you add them to that file:

```
galley2epub run gierke
```

galley reads every page without a text layer with Tesseract. A page
where it finds no text is left out as blank; one where it finds text
is read with Tesseract; one with ink but no text, such as a cover, a
cloth board or a library stamp, is kept as a picture. The log warns
about each page kept as a picture or as text, and about a blank page
that holds some ink, because a lone printed word or page number can
look blank to Tesseract: look at those pages in the PDF and put any
you do not want in `exclude_pages`. Five whole books from the Internet
Archive converted this way from the PDF alone, with 3 to 8 such
warnings each.

A whole book usually reads better with a few settings: its table of
contents named, so that its lines do not become headings, and the
pages the log warned about checked. For the whole Gierke book
(`politicaltheorie00gieruoft`):

```toml
pdf = "../politicaltheorie00gieruoft.pdf"
title = "Political Theories of the Middle Age"
authors = ["Otto Gierke", "F. W. Maitland"]
language = "en"
exclude_pages = [0, 2, 3, 4, 5, 51, 283, 284, 285, 286, 287, 288, 289]
contents_pages = [10, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67]
```

Pages are counted from 0: the first page of the PDF is 0, so a page your
PDF viewer shows as page 12 is 11. `pdf` is the path of the PDF, relative
to `book.toml`. The other keys are optional:

- `exclude_pages`: pages left out of the book.
- `exclude_regions`: parts of a page left out, such as a library stamp:
  `[{page = 0, box = [240, 620, 252, 632]}]`, the box in points (1/72
  inch) from the top left corner of the page, left, top, right, bottom.
- `contents_pages`: the pages of the printed table of contents. Without
  them its lines become headings, and the EPUB's table of contents lists
  those chapters twice.
- `cover_page`: the page used as the EPUB's cover.
- `plate_pages`: pages of illustrations (plates) to keep as pictures,
  for one galley takes for text.
- `front_matter_end`: the first page to keep. galley leaves out the
  front matter, the title page and other pages before the preface or the
  table of contents; set this when it guesses wrong (it logs a warning
  when unsure), or to 0 to keep every page.
- `ocr`: how far the PDF's text layer is trusted. `verify` (the default)
  compares a sample of pages with Tesseract and stops when the layer reads
  clearly worse; `redo` then reads every page again with Tesseract;
  `trust` skips the comparison.
- `reread_footnotes`: `true` to re-read footnotes with Tesseract too. Off
  by default, because Tesseract misreads note numbers.
- `correct` and the `correct_` keys: the vision model, next section.

An unknown key or a wrong value stops the run with an error that names it.

## Fixes from a vision model on your machine: --correct

`--correct` has a vision model (a language model that reads images) read
every text page. Where the model reads a word differently, galley uses
the model's word. On six pages of *The Battle of Kadesh* (1903), checked
against a transcription made by hand, this took the footnotes from 26.5
wrong words in 100 to 3.4, and the body text from 2.0 to 0.7. The cost:
about 1 word in 300 becomes another real word, a wrong one that reads
naturally, so proofreading does not catch it. It
took about 11 s a page on an Apple M5 Pro, 1 to 3 hours for a whole book.

It is off by default. It needs [LM Studio](https://lmstudio.ai), a
program that runs language models on your own computer, with its server
started, and the model `qwen/qwen3.6-35b-a3b`, about 20 GB to download.
It has been run only on an Apple M5 Pro; what smaller machines need was
not measured. `lms` is LM Studio's command:

```
lms get qwen/qwen3.6-35b-a3b
lms server start
galley2epub run gierke --correct
```

Your book's text does not leave your machine: galley only accepts an LM
Studio address on this computer (`localhost`), and refuses any other.
`correct = true` in `book.toml` turns it on for every run, and
`--no-correct` turns it off for one run. The model's answers are kept in
the book folder, under `answers/`, so a later run does not ask the model
again for the same page; delete that folder to have every page read again.
Each fix is one line of `edits/correct.jsonl`; delete a line to undo it.
The `correct_` keys of `book.toml` change the model (`correct_model`)
and LM Studio's address (`correct_server`); `docs/specs/correct.md`
describes them all.

## Proofreading

`book.md`, in the book folder, is the whole book as one Markdown text,
and the EPUB is built from it. Proofread it for words the OCR misread
("tli" for "the"), a margin note or heading cut short, and a page's title
or number left in the text. Correct `book.md` and
rebuild only the EPUB:

```
galley2epub epub gierke
```

Your corrections do not survive `galley2epub run`, which writes a new
`book.md`: keep a copy of yours. A command that saves them apart from
`book.md`, so that a rerun applies them again, is planned and not built
yet.

## What galley does not do yet

- A PDF without a text layer on any page has not been tried.
- Tables are not recognised: their cells come out as plain text.
- Italic and bold are not kept; the text layer does not record them.
- A printed index stays text; its page numbers do not link to the pages.
- Books in a language other than English, Spanish, French, German or
  Italian.

## For developers

galley runs in stages, each a subpackage of `src/galley/` that writes one
file of the book folder for the next: analyze, extract, layout,
structure, correct, markdown, epub. `docs/architecture.md` describes the
stages, the files between them and the book config; `docs/specs/` holds
the specs of the stages and `docs/glossary.md` the names of things.
`CLAUDE.md` says how the work is done in this repository, the
environment, and the samples: public-domain excerpts committed in
`tests/fixtures/pdf/`, and whole books downloaded by
`scripts/fetch_samples.py`.

The checks, from a clone:

```
uv lock --check
uv run --locked ruff format --check
uv run --locked ruff check
uv run --locked ty check
uv run --locked pytest
uv run --locked pytest --parallel-threads=8
```

`uv run pytest -m whole_book` runs the slow tests on the whole books,
after `uv run python scripts/fetch_samples.py` has downloaded them;
some tests need epubcheck (`brew install epubcheck`) and skip without it.

## Licence

MIT; see `LICENSE`.
