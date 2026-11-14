# galley's architecture

This document describes how galley turns the PDF of a mostly-text book
into an EPUB: the stages of the pipeline, the files they pass to each
other, the data formats of those files, how edits to the text are kept,
and the rules every stage follows so that no word of the book is lost or
invented. The specs of the stages, `docs/specs/<stage>.md`, build on it,
and the names of the things of the domain are those of `docs/glossary.md`.
Dated 14 November 2026.

Decisions marked "owner, 14 November 2026" were taken by the owner in chat.
The others were taken while writing, from what the two committed excerpts
show (section 2), and can be questioned.

## 1. The scanned books galley reads

galley is written for PDFs in which every page is a picture of the printed
page with an invisible **text layer** on top: the words an OCR program read,
each placed over its picture, in a font that draws nothing. In both
excerpts that font is `GlyphLessFont`. The layer gives each word's text and
box, and nothing about italic, bold or font size: the height of a word's
box is the height of the OCR line it was in, not the size of its type.

The layer gives words, not the lines of the book. pdfplumber groups words
into lines by height alone, so a row that crosses two columns comes out as
one line: on page 0 of the Kadesh excerpt, the two columns of footnotes
give "Ori- 'There is, however, much material…", the end of one note and
the start of another. Gierke prints short headings in the margin beside
the body text, on the same rows, on the left of some pages and the right
of others, and inside its endnotes too. Finding columns, margins and lines is
therefore a stage of its own (layout, section 9).

When a page has no text layer, or a poor one, galley makes its own with
Tesseract, which gives the same thing: words with boxes, plus a confidence.

## 2. The samples

Development and tests use two public-domain books from the Internet
Archive and a ten-page excerpt of each, committed under
`tests/fixtures/pdf/` and cut by `scripts/fetch_samples.py`:

- **Kadesh**: J. H. Breasted, *The Battle of Kadesh* (1903), excerpt of
  pages 8-17. Running heads alternate between the author and the title;
  footnotes in two columns at the foot; two printed page-number sequences
  (the book's in the running head, a journal's at the foot); a plate; a
  blank page.
- **Gierke**: O. Gierke, *Political Theories of the Middle Age*, tr. F. W.
  Maitland (1900), pages 86-93 and 270-271. Running heads alternate
  between the book title and the section; headings in the margin; a
  signature mark (a printer's "I — 2" at a page foot); endnotes.

## 3. Text and meaning, not typography

galley extracts the text of a book and what each part of it is (a
heading, a paragraph, a note, a margin heading), and then lays it out in
its own way. It keeps nothing of the book's typography: fonts, sizes,
margins and the place of things on the page are evidence for structure
to read, never something to reproduce. A kind of block is rendered the
same way in every book, by markdown and the style sheet of the epub stage
(owner, 14 November 2026). The books are mostly text, so little is lost.

## 4. The pipeline

Seven stages, each a subpackage of `src/galley/`. A stage reads the files
listed for it, writes one file, and imports no other stage, so that each
can be built and tested on its own.

| stage | reads | writes | work |
|---|---|---|---|
| analyze | PDF, config | `pages.json` | what each page is and where its words come from |
| extract | PDF, config, `pages.json` | `words.json`, `images/` | the words of each page with their boxes; figures and the cover cut out |
| layout | `pages.json`, `words.json` | `lines.json` | each page's words grouped into regions and lines, in reading order; the figures carried over |
| structure | `pages.json`, `lines.json`, config | `blocks.json` | the book as ordered blocks and notes; what was removed |
| correct | PDF, `words.json`, `blocks.json` | `edits/correct.jsonl` | proposed fixes to OCR errors (optional) |
| markdown | `blocks.json`, `edits/`, config | `book.md` | Pandoc Markdown with the edits applied |
| epub | `book.md`, `images/`, config | `book.epub` | built by Pandoc, checked by epubcheck |

analyze, extract and layout work page by page, in parallel threads.
structure first reads the whole book to find what repeats on every page,
then works page by page, then joins what runs over page breaks. correct
works per block. markdown and epub run once.

Every file a stage writes carries the SHA-256 of the PDF it came from.
Only analyze computes it, from the PDF; every later stage copies it from
its input file and checks it against `pages.json`. A stage that reads a
file made from another PDF stops with an error that says which stage to
rerun.

## 5. The book folder

Everything about one book lives in one folder, given to the command:

```
kadesh/
  book.toml            the config, written by the owner
  pages.json           analyze
  words.json           extract
  images/              extract: figures, grayscale PNG at 300 dpi
  lines.json           layout
  blocks.json          structure
  edits/
    correct.jsonl      correct
    owner.jsonl        the owner's edits (section 10)
    <agent>.jsonl      edits proposed by an agent
  book.md              markdown
  book.epub            epub
```

The owner writes `book.toml` and, through `galley2epub edits-from`, the
edits. Every other file is generated and is overwritten when its stage
runs again. Edits are never overwritten by a stage. Folders of the owner's
books live outside the repository or under `runs/`, which git ignores;
tests make theirs under pytest's temporary directory.

## 6. The book config

`book.toml` is read in one place, `config.py`, into a frozen `BookConfig`.
An unknown key or a wrong type is an error.

| key | type, default | meaning |
|---|---|---|
| `pdf` | path, required | relative to `book.toml` |
| `title` | string, required | |
| `authors` | list of strings, required | |
| `language` | string, required | ISO 639-1 code: `en`, `es`, `fr`, `de`, `it`. `config.py` maps it to Tesseract's code (`eng`, `spa`…) and to the word list |
| `ocr` | `verify` / `trust` / `redo`, `verify` | how far the book's own OCR is trusted (section 7b) |
| `correct` | bool, `false` | whether `galley2epub run` runs the correct stage |
| `exclude_pages` | list of page indices, `[]` | pages left out, as removals |
| `exclude_regions` | list of `{page, box}`, `[]` | a library stamp, a label |
| `cover_page` | page index, none | rendered as the EPUB's cover |

A stage spec adds the keys it needs, here and in `config.py` together.

## 7. Units, identifiers and the text of a block

- Positions are in PDF points (1/72 inch), as floats, with the origin at
  the top left of the page and `top` growing downwards, as pdfplumber
  gives them. `Box(x0, top, x1, bottom)`.
- A **page index** counts the pages of the PDF from 0, an int. A **page
  number** is what is printed on a page, a string ("47", "xiv").
- An image rendered from a page carries its DPI. A box in pixels never
  travels without it.
- A **block id** is `b-p<page index, 4 digits>-<n, 3 digits>`, for the n-th
  block (from 1) that starts on that page, counting body blocks and note
  blocks together in reading order: `b-p0012-003`. A paragraph that runs
  from page 12 to page 13 has the id of page 12. A **note id** is
  `n-p<page index, 4 digits>-<n, 3 digits>` in the same way, for the n-th
  note that starts on the page.
- The **text of a block** is the concatenation of the `text` of its spans.
  Spans of one block are separated by nothing, so a span carries the
  spaces it needs. Edits match against this text.

## 7b. Trusting the book's own OCR

Most scanned books already have a text layer, made by whoever scanned
them. galley trusts it, but checks it (owner, 14 November 2026). The
config's `ocr` key sets how far:

| `ocr` | analyze does |
|---|---|
| `verify` (default) | the audit below |
| `trust` | no audit of the text layer; pages without a layer are still checked as in the audit |
| `redo` | ignores the text layer and marks every page for OCR |

The audit runs Tesseract on two sets of pages:

- **Every page without a text layer.** In the two whole public-domain
  books, 26 pages have none: 13 are blank, and 13 have something printed
  that the scanner's OCR left out (Kadesh page index 69: a running head,
  about five lines of text and a captioned figure). A page where
  Tesseract finds no text at all is blank, recorded with
  `blank_checked_by_ocr`; a page of numerals or names only is not blank.
  The threshold for stray marks is set in analyze's spec. A page where it finds text gets `text_source`
  `ocr`, and extract reads it with Tesseract: the gap is filled, the run
  goes on.
- **A sample of pages with a text layer**, spread through the book. Each
  is scored twice, the layer's words and Tesseract's, by the share found
  in the word list. Tesseract is not taken as the truth: on
  19th-century roman type the scanner's layer was better than a fresh
  Tesseract run on all three control books of the owner's ocr_lab. When
  the layer scores clearly below Tesseract, analyze stops with
  `PdfError`, giving the scores, and the owner reruns with `ocr =
  "redo"`. Replacing OCR that exists is the owner's choice; filling a gap
  is not.

The sample size and the thresholds are set in analyze's spec. ocr_lab's
triage re-OCRed below a word-list share of 0.70 and checked between 0.70
and 0.80, which tracked the measured gain closely (ρ = 0.90, as ocr_lab's notes report it)
but was fitted on 16 books only.

## 8. The formats

The formats are frozen dataclasses in `src/galley/model.py`, with tuples
for sequences, `frozendict` (a built-in type of Python 3.15) for
mappings, `StrEnum` for finite sets, and floats for positions. Each file
has a `format_version` int, 1 for every file now, and one pair of functions
in `model.py`, `write_<file>(path, value)` and `read_<file>(path)`:
`write_pages` and `read_pages`, `write_words` and `read_words`, and so on.
Reading a file whose `format_version` is not the current one is an error
that names both. In JSON, a dataclass is an object with its field names,
a tuple a list, an enum its string value, a `Box` a list of four numbers,
and a `frozendict` with int keys an object whose keys are the ints as
strings.

Every file's top-level object has `format_version` and `source_pdf_sha256`.

**pages.json**, `PagesFile(pages: tuple[PageInfo, ...])`:

- `PageInfo`: `index`, `width_pt`, `height_pt`, `kind: PageKind`,
  `text_source: TextSource`, `text_layer_score: float | None`,
  `exclude_regions: tuple[Box, ...]`.
- `PageKind`: `blank`, `text`, `plate` (mostly a picture), `excluded`.
- `TextSource`: `text_layer`, `ocr`, `none` (blank and excluded pages).
- `text_layer_score`: the share of the layer's words found in the word
  list (section 12), from 0 to 1; `None` without a layer.
- `blank_checked_by_ocr: bool`: true for a page without a text layer that
  the OCR audit read and found blank (section 7b), so that a blank page is
  never a page nobody looked at.
- `PagesFile` also has `ocr_audit: OcrAudit | None`: the pages sampled,
  the score of the text layer and of Tesseract on each, and the verdict
  (section 7b). `None` when `ocr` is `trust` or `redo`, and in the walking
  skeleton, which has no audit.
- Page sizes are pdfplumber's (the media box). pypdfium2 reports the crop
  box, which can differ slightly (Gierke: 376.128 pt against
  376.1000061), so no stage takes a page size from pypdfium2.

**words.json**, `WordsFile(pages: tuple[PageWords, ...], removals)`:

- `PageWords`: `index`, `text_source`, `words: tuple[Word, ...]`,
  `figures: tuple[Figure, ...]`. A page whose source is `none` has no
  words.
- `Word`: `text`, `box`, `ocr_confidence: float | None` (Tesseract's,
  0-100; `None` for the text layer). In the order the source gave them.
- `Figure`: `box`, `image` (path relative to the book folder), `dpi`. For
  now figures are cut from plate pages only; figures inside text pages
  are not detected yet.
- A word inside an excluded region is a removal, one per word, with reason
  `excluded_region`; the words of an excluded page likewise, with
  `excluded_page`.

**lines.json**, `LinesFile(pages: tuple[PageLayout, ...])`:

- `PageLayout`: `index`, `regions: tuple[Region, ...]`, in reading order,
  and `figures`, copied from words.json so that structure need not read it.
- `Region`: `box`, `lines: tuple[Line, ...]`. A region is a part of the
  page whose lines are read one after the other: the body column, a
  margin, a column of footnotes, the running head. layout does not say
  what a region is; structure does.
- `Line`: `box`, `words: tuple[Word, ...]`, left to right.

layout only regroups words: every word of words.json is in exactly one
line of lines.json. It removes nothing. The removals of words.json are not
repeated in lines.json or blocks.json: each file lists only the removals
its own stage made.

**blocks.json**, `BlocksFile(blocks, notes, removals, word_changes,
page_numbers)`:

- `Block`: `id`, `kind: BlockKind`, `level: int | None` (headings, from
  1), `spans: tuple[Span, ...]`, `figure: str | None` (figure blocks),
  `origin: tuple[Origin, ...]`.
- `BlockKind`: `heading`, `paragraph`, `quote`, `figure`, `margin_note`
  (section 17), `index_entry`.
- `Span`: `text`, `emphasis: Emphasis`, `note_ref: str | None`. A span
  with a `note_ref` is a note reference: its `text` is the marker as
  printed ("1", "*") and `note_ref` is the id of the note.
- `Emphasis`: `none`, its only value for now (owner, 14 November 2026:
  no italics yet; the field is kept for them).
- `Note`: `id`, `marker` (as printed at the start of the note: "8", "*",
  or as OCR misread it), `blocks: tuple[Block, ...]` (a note may have
  several paragraphs), `origin`, `referenced: bool`. A note whose
  reference structure could not find (in Gierke's excerpt, endnotes whose
  text is outside it) has `referenced` false. A marker in the text whose
  note was not found is left in its word, unsplit.
- `Origin`: `page_index`, `box`. A paragraph that runs over a page break
  has two.
- `WordChange`: `page_index`, `before: tuple[str, ...]`, `after:
  tuple[str, ...]`, `reason: ChangeReason`: a word that structure changed
  without losing any letter. `hyphen_join`: ("repli-", "cate") becomes
  ("replicate",). `note_marker`: ("Greece,1",) becomes ("Greece,", "1"),
  the "1" going to the note reference. A spec adds a reason when it needs
  one.
- `PageNumber`: `page_index`, `text`, `position: head | foot`.
  `page_numbers: tuple[PageNumber, ...]`, taken from the removals; the
  index stage uses it (section 11).

**Removal**, in words.json (excluded pages and regions) and blocks.json
(the rest): `page_index`, `box`, `text`,
`reason: RemovalReason`: `excluded_page`, `excluded_region`,
`running_head`, `page_number`, `signature_mark`. A stage spec adds a
reason when it removes a new kind of text, and the reason names what the
text is, never "noise": a plate's stray text-layer characters are removed
as `plate_text` by structure, which the owner can review.

**Edit**, one JSON object per line of a file under `edits/`:
`format_version` (1), `block_id`, `block_sha256` (the first 12 hex digits
of the SHA-256 of the block's text as structure wrote it), `old`, `new`,
`author`, `reason`. The version is on every line, not in a header, so that
`edits-from` and agents can append to a file. A missing `edits/` folder or
file is no edits; a blank or malformed line is an error that names the
file and line.

**RenderedPage**, not a file but what `pdfium.render` returns:
`page_index`, `dpi`, `width_px`, `height_px`, `pixels: bytes` (8-bit
grayscale, row by row). Frozen, so it can go to a worker thread, which
makes a Pillow image from it.

## 9. The stages

Each stage is called as `run(folder: BookFolder, config: BookConfig, *,
workers: int = DEFAULT_WORKERS) -> None` from its subpackage. layout,
structure and markdown run their own fidelity check (section 13) before
writing, so a stage rerun alone is checked as well as a full run. `BookFolder(root: Path)` gives the paths of
section 5 as properties: `folder.pages_json`, `folder.edits_dir`, and so
on. Everything else a stage does is pure functions over the frozen values
it read (the `coding` skill, "Functional style").

**analyze** measures each page: size, text layer, the layer's score,
whether it is blank, text or a plate; applies the config's
`exclude_pages` and `exclude_regions`; and runs the OCR audit of section
7b, which decides each page's `text_source`.

**extract** gives every page its words. Text-layer pages are read with
pdfplumber, one document per worker thread. OCR pages are rendered at 300
dpi by `pdfium.py` and read by Tesseract in parallel; their pixel boxes are
turned into points. Plate pages are rendered and their figure cut into
`images/`, and so is the `cover_page` of the config, as `images/cover.png`.

**layout** groups each page's words into regions and lines, and orders
them for reading: a column, then the next; the margin beside the body;
the footnote columns at the foot. It copies the page's figures through.

**structure** turns regions and lines into blocks and notes. It first
reads the whole book to find what repeats: running heads, page numbers,
signature marks, the line heights of body and notes. Then, per page, it
removes those, decides what each region is, groups lines into
paragraphs, headings, quotes, margin notes and notes (a margin note goes
just before the paragraph whose line it sits beside), joins hyphenated
words where the word list or the book's own words allow it, and splits
note markers off the words they are glued to. Last, it joins paragraphs
and notes that run over a page break and matches each note reference to
its note.

**correct** proposes fixes to OCR errors as edits in
`edits/correct.jsonl`, using the words' boxes and confidences in
words.json and, possibly, the local vision model reading a word on the
page image. It is optional. Its spec is written later.

**markdown** applies the edits (section 10) and writes `book.md`: a
metadata header from the config; headings with their block id as anchor;
every other block as a Pandoc fenced div with its id (`::: {#b-p0012-003}`);
notes with `referenced` true as Pandoc footnotes, each of their blocks a
fenced div with its id inside the footnote, which Pandoc puts at the end
of each chapter and the Kindle shows as pop-ups (section 17);
notes with `referenced` false as ordinary blocks where they were printed,
the marker first; figures as images. Pandoc runs with
`--fail-if-warnings`, so that a note it would drop is an error (checked
with Pandoc 3.13: an unused note definition is dropped with only a
warning, and the option makes it exit with 3). A reference with no note
is not a warning: Pandoc prints it as text, `Greece,[^1]`, and exits with
0 (checked the same way). The fidelity check catches it, as an invented
word `Greece,[^1]` and a missing `Greece,`. Text is escaped so that Pandoc reads
it back as written: "1. Of the three" at the start of a paragraph must
not become a numbered list. `book.md` is read by Pandoc with smart quotes
off (`-f markdown-smart`), so `"` stays `"`.

**epub** runs Pandoc on `book.md` with the cover and a style sheet.
epubcheck validates the result in the tests, not in a run (section 16). The cover is
`images/cover.png` when the config has a `cover_page`.

## 10. Edits

Edits are how anything that is not a stage changes the text of the book:
the correct stage, the owner proofreading, an agent. They are kept outside
the generated files, so rerunning the pipeline keeps them (owner, 14
November 2026: patches, usable by agents too).

- An edit names a block (of the body or of a note) by id, carries the
  checksum of the block's text, and gives the text it replaces, `old`,
  and the new text, `new`, with who made it and why.
- markdown applies `correct.jsonl` first, then the agents' files by file
  name, then `owner.jsonl` last, each from its first line to its last.
  The owner's edits come last because `edits-from` finds them on a
  `book.md` that already had every other edit applied. A missing file is
  simply no edits.
- An edit applies when its block exists, the checksum matches the block's
  text as structure wrote it, and `old` appears exactly once in the
  block's text as edited so far. Otherwise markdown stops with an error
  that lists every edit that did not apply, with its file, line and
  reason. Nothing is skipped.
- When edits stop applying because structure changed, the owner reruns
  `edits-from` on their corrected copy of `book.md` against the new
  blocks, or deletes the edits that no longer apply.
- The owner makes edits by copying `book.md`, correcting the copy, and
  running `galley2epub edits-from <book folder> <corrected copy>`. The
  copy keeps the block ids, since they are written in it as anchors, so
  the command compares the two block by block and appends the differences
  to `edits/owner.jsonl`. After that, only markdown and epub need to run
  again. The spec of `edits-from` is part of the markdown stage's.
- An agent writes edits the same way, from blocks.json, into
  `edits/<agent name>.jsonl`.

## 11. The book's index

An index printed in the book points to page numbers, which mean nothing in
an EPUB. For now it is kept as text: its entries are `index_entry` blocks
and no word is lost. Later, an `index` stage between structure and markdown
will turn each page number of an entry into a link to the block on that
page that holds the term, through `page_numbers` and the blocks' `origin`.
Pandoc keeps such links across chapter files (checked with Pandoc 3.13: a
link to `#b-p0008-002` written in another chapter became
`ch001.xhtml#b-p0008-002`). An index built from the blocks, for books that
have none, comes after that (owner, 14 November 2026).

## 12. Shared modules

Besides the stages, the package root holds the modules every stage uses.
A stage imports these and nothing else of galley.

| module | gives |
|---|---|
| `model.py` | the formats of section 8, with their read and write functions |
| `config.py` | `BookConfig`, `read_config(path)`, the language codes |
| `book_folder.py` | `BookFolder` |
| `errors.py` | `GalleyError` and its subclasses: `ConfigError`, `InputFileError` (missing, stale or of another format version), `PdfError`, `ExternalProgramError` (missing or failed Tesseract or Pandoc), `EditError`, `FidelityError` |
| `pdfium.py` | the one thread that calls PDFium, which is not thread-safe. It opens and closes the PDF itself for each request: `page_count(pdf)`, `page_size(pdf, page_index)`, `render(pdf, page_index, dpi) -> RenderedPage` |
| `parallel.py` | `DEFAULT_WORKERS` (6); `map_pages(function, items, workers)`, which returns the results in input order; and `map_pages_with_source(open_source, function, items, workers)`, which opens one source per worker thread (a pdfplumber document) and passes it to every call on that thread. A source is closed when its thread ends, also when `function` raises; the exception propagates |
| `wordlist.py` | `word_list(language) -> frozenset[str]`, extracted from Tesseract's language data with its `combine_tessdata` and `dawg2wordlist` tools, as the owner's ocr_lab does, and cached under `~/.cache/galley/` |
| `fidelity.py` | the fidelity check, section 13 |
| `cli.py` | the `galley2epub` command. Before any work it finds, with `shutil.which`, the external programs the requested stages need (Pandoc, Tesseract) and stops naming any that is missing |

`src/galley/__init__.py` imports gilguard first: a library that stops a
program at any import that turns Python's global lock back on, and names
the module. galley needs the lock off to run pages in parallel.

## 13. The fidelity check

galley's first goal is that no word of the book is lost or invented. The
fidelity check, `fidelity.check_stage(stage, before, after)`, makes that
testable at each stage boundary. It works on the whole book: the words of
a stage's input must equal, as a multiset, the words of its output plus
the removals that stage made, once the stage's word changes are applied
(and, for markdown, the edits). A difference is a `FidelityError` that
lists the words, with the pages they came from where the origins say.

- Words are compared as strings, split on white space, with nothing
  normalised: a changed letter or a lost accent is a difference.
- A block's spans are split into words one by one, not joined first: a
  note reference span is a word of its own. Joined, "Greece," and the
  reference "1" would become "Greece,1" again and hide the word change.
- It compares multisets over the whole book, not page by page, because a
  paragraph or a hyphen join can run over a page break and its words then
  belong to two pages. Order is not part of the check, because columns,
  margins and notes move between stages; order within a block is checked
  by structure's tests.
- The boundaries: layout, words.json against lines.json; structure,
  lines.json against blocks.json (the text of every body and note block,
  with a note's `marker` counted as a word of it); markdown, blocks.json
  with the edits applied against `book.md` as Pandoc reads it (`pandoc -f
  markdown-smart -t json`): a note reference is matched to Pandoc's note
  element and its marker is not compared as a word, because Pandoc writes
  its own numbers (section 17); likewise the `marker` of a
  referenced note.
- extract is where the words enter galley, so it has no boundary to check:
  its excerpt tests compare its words with literals.
- The check stops at `book.md`: turning it into an EPUB is Pandoc's work,
  and epubcheck checks the EPUB's form.
- The excerpt tests of every stage run the check, and the `whole_book`
  tests run it on whole books. layout, structure and markdown run it
  inside their `run` before writing (section 9), which costs one pass
  over the words.

## 14. The command

```
galley2epub run <book folder>          every stage in order (correct only if the config says)
galley2epub <stage> <book folder>      one stage: analyze, extract, layout, structure, correct, markdown, epub
galley2epub edits-from <book folder> <corrected book.md>
```

Errors propagate to `cli.main`, the one place that catches broadly, which
logs the error and raises it again. The `[project.scripts]` entry is added
by the first plan, with `cli.py`.

## 15. Tests

The three tiers of tests (unit, excerpt, whole book), the excerpts and the
pytest markers are in the `coding` skill, "Tests", and in
`pyproject.toml`.

## 16. External programs

galley prefers to be self-contained (owner, 14 November 2026). An external
program is adopted when it gives a large amount of well-tested work that
would be costly to rebuild; when what it gives is small, galley does it
itself. A program needed only while developing or testing is a smaller
cost than one every run of `galley2epub` needs.

| program | used by | when | why it is not rebuilt |
|---|---|---|---|
| Pandoc | markdown (to read `book.md` back for the fidelity check), epub | every run | writing a valid EPUB 3 with navigation, notes and metadata is a large, well-tested body of work |
| Tesseract | analyze (the OCR audit), extract (OCR pages), `wordlist.py` | runs that need OCR; the word list, once per language | OCR is not something to rebuild |
| epubcheck | the tests of the epub stage and the `whole_book` tests | development only | it is the reference validator of EPUB, and needs Java, which a run of galley should not |

The epub stage does not run epubcheck: an EPUB is checked while
developing, on the excerpts and the whole books, and the tests that need
it are marked `epubcheck` and skip when it is missing. It is installed
with `brew install epubcheck` (5.4.0) before the epub stage is built.

## 17. Decided by the owner on 14 November 2026

- **Margin headings** are a kind of block, `margin_note`, which markdown
  renders in galley's own way: for now a small bold line before the
  paragraph whose line it was beside. Their printed form is not kept
  (section 3).
- **epubcheck** is a development tool, not a requirement of a run
  (section 16).
- **The book's own OCR** is trusted but checked (section 7b): pages
  without a text layer are read by Tesseract and filled or recorded as
  blank; a text layer that scores clearly worse than Tesseract stops the
  run, and the owner decides whether to redo the OCR.
- **Note markers** in the EPUB are Pandoc's numbers, 1, 2, 3 in each
  chapter. The printed markers stay in blocks.json and are not shown.
- Earlier the same day, in chat: no italics yet (the `emphasis` field is
  kept for them); edits as patch files, usable by agents too; the book's
  index kept as text now, linked to blocks later.

## 18. Not in this document

- How each stage does its work: the page score threshold, column
  detection, running heads, paragraphs, notes, OCR settings, figure
  cutting. That is in the stage specs.
- What happens to a hyphen that structure cannot join safely ("neces-" and
  "sary" with no evidence): structure's spec, as an open point.
- The `correct` stage, with its log and how it calls the vision model; the
  `index` stage; and `edits-from`. Each is specified later, and section 8
  gains their formats then.
- The style sheet and cover of the EPUB, in the epub stage's spec.
