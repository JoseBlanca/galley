# galley's architecture

This document describes how galley turns the PDF of a mostly-text book
into an EPUB: the stages of the pipeline, the files they pass to each
other, the data formats of those files, how edits to the text are kept,
and the rules every stage follows so that no word of the book is lost or
invented. The specs of the stages, `docs/specs/<stage>.md`, build on it,
and the names of the things of the domain are those of `docs/glossary.md`.
Dated 14 November 2026; revised on 16 November 2026 for the second plan
of structure (`docs/specs/structure.md` §11 to §19), which adds kinds to
section 8 for chapter summaries, verse and endnotes, a heading's chapter
label, plates as figures, the config key `contents_pages` and the module
`body_measures.py`. Revised on 17 November 2026 for how the text layer
is read (`docs/specs/extract.md`) and the pages before the preface
(`docs/specs/front-matter.md`), which add the page kind and the removal
reason `front_matter`, the config key `front_matter_end` and
`text_layer.layer_words`; and the same day for re-reading small print
with Tesseract (`docs/specs/reocr.md`), which gives layout the PDF and
the config as inputs, adds the record `Reread` to `lines.json` (version
2), the module `ocr.py` and the config key `reread_footnotes`. Revised
again the same day for the plan owner-books, which makes galley read
the owner's two modern books (`docs/specs/structure.md` §21 to §27):
it adds the block kind `epigraph` with `Block.source`, `Note.group`,
and the word change reasons `source_dash`, `punctuation_attached` and
`case_split`, which take `blocks.json` to version 4; no other file
changes format. Revised on 18 November 2026 for lists and the printed
table of contents (`docs/specs/structure.md` §29 to §33): the block
kinds `list_item` and `contents_entry`, `Block.page_number` and
`Block.heading_ref`, the change reason `list_marker` and the removal
reason `leader_dots` take `blocks.json` to version 5, and markdown
writes lists and links (sections 9 and 13). Revised the same day for
the figures printed inside text pages (`docs/specs/figures.md`):
`PageInfo.figure_boxes` takes `pages.json` to version 3, `Figure.kind`
takes `words.json` to 3 and `lines.json` to 4, and the removal reason
`figure_text` goes into `blocks.json` version 5 with the lists' changes,
one version for both. Revised again the same day for the plan
stray-text (`docs/plans/stray-text.md`): the page kind `inkless`, a page
that prints nothing although its text layer holds words
(`docs/specs/plates.md` §2b), takes `pages.json` to version 4, and the
removal reason `inkless_page` records those words in `words.json`.
Revised on 19 November 2026 for the plan ocr-redo
(`docs/plans/ocr-redo.md`): `ocr = "redo"` is accepted, and makes
analyze mark every text page `ocr` and extract read it with Tesseract,
putting back the note references Tesseract loses from the text layer
(sections 6, 7b, 9 and 16, and `docs/specs/extract.md` §9); structure
keeps a line of low Tesseract confidence from being a heading, and
removes the pieces of letters that Stubbs' text layer gives as words of
their own, with the removal reason `letter_fragment`
(`docs/specs/structure.md` §34 and §35). No file changes its
`format_version` (section 8). Revised the same day for the correct stage
(`docs/specs/correct.md`, plan notes-vision): a local vision model,
served by LM Studio, reads each text page, and its words replace
galley's where the two line up, as edits; the edit format goes to
version 2 with `page_index`, `model` and `second_reading`; markdown
applies the edits files; the config gains `correct_model`,
`correct_server` and `correct_second_model` (sections 4 to 6, 8 to 10,
12 and 16).

Decisions marked "owner", with a date from 14 to 17 November 2026,
were taken by the owner in chat; those of 18 November 2026 were taken
for the owner, who asked the work to go on without waiting, and are
listed in section 17. The others were taken while writing,
from what the committed excerpts show (section 2), and can be questioned.

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
Where the scan is sharp but its text layer poor in small print, the
margin notes and the pages printed wholly in small type, layout reads
that print again with Tesseract and keeps, region by region,
Tesseract's reading only where it scores higher than the layer's by
known words minus unknown words, or ties with more known words; on any
other tie the layer stays (`docs/specs/reocr.md`).

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

So galley's formats are semantic (owner, 15 November 2026): a kind says
what a text is, never how it looks. Two things that will look alike in
the EPUB still get different kinds: Stubbs' chapter summaries are
`chapter_summary` blocks, not quotes, although the printed page sets both
in small type, and an endnote is not a footnote, although both are notes.
How each kind looks is decided by the markdown and epub stages, never by
the stage that finds it.

## 4. The pipeline

Seven stages, each a subpackage of `src/galley/`. A stage reads the files
listed for it, writes one file, and imports no other stage, so that each
can be built and tested on its own.

| stage | reads | writes | work |
|---|---|---|---|
| analyze | PDF, config | `pages.json` | what each page is and where its words come from |
| extract | PDF, config, `pages.json` | `words.json`, `images/` | the words of each page with their boxes; figures and the cover cut out |
| layout | PDF, config, `pages.json`, `words.json` | `lines.json` | each page's words grouped into regions and lines, in reading order; small print re-read with Tesseract where that reads better (`docs/specs/reocr.md`); the figures carried over |
| structure | `pages.json`, `lines.json`, config | `blocks.json` | the book as ordered blocks and notes; what was removed |
| correct | PDF, config, `pages.json`, `words.json`, `blocks.json` | `edits/correct.jsonl` | the words a local vision model reads otherwise than galley, as edits (optional; `docs/specs/correct.md`) |
| markdown | `blocks.json`, `edits/`, config | `book.md` | Pandoc Markdown with the edits applied |
| epub | `book.md`, `images/`, config | `book.epub` | built by Pandoc, checked by epubcheck |

analyze, extract and layout work page by page, in parallel threads.
structure first reads the whole book to find what repeats on every page,
then works page by page, then joins what runs over page breaks. correct
works page by page, in parallel threads that wait on the vision model. markdown and epub run once.

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
                       (plate-<page index, 4 digits>.png,
                       figure-<page index, 4 digits>-<n>.png), and cover.png
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
edits. Every other file is generated. A stage, before it reads its
inputs, deletes its own file and the files of every later stage
(`book_folder.delete_stage_outputs`), so that no file of a later stage
can survive from an earlier run: in the review of the walking skeleton,
markdown run alone after analyze and extract built `book.md` from a stale
`blocks.json` and lost a word with no error. The correct stage's file,
`edits/correct.jsonl`, is deleted with the files of structure and of
every stage before it, since its edits name blocks by their text as
structure wrote it. No other edits file is ever written or deleted by a
stage. Folders of the owner's
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
| `language` | string, required | ISO 639-1 code: `en`, `es`, `fr`, `de`, `it`. `config.py` maps it to Tesseract's code (`eng`, `spa`…) and to the word list; structure treats spaced punctuation by it (`docs/specs/structure.md` §23) |
| `ocr` | `verify` / `trust` / `redo`, `verify` | how far the book's own OCR is trusted (section 7b), and whether layout re-reads small print: not with `trust` or `redo` (`docs/specs/reocr.md`). With `redo`, every text page is read again with Tesseract and its words replace the text layer's (section 7b; `docs/specs/extract.md` §9): for a book whose layer is bad throughout, as Kadesh's, the only one of the eight books that needs it |
| `correct` | bool, `false` | whether `galley2epub run` runs the correct stage |
| `correct_model` | string, `"qwen/qwen3.6-35b-a3b"` | the vision model the correct stage asks, as LM Studio names it (`docs/specs/correct.md` §3) |
| `correct_server` | string, `"http://localhost:1234"` | LM Studio's address; only `http` on `localhost`, `127.0.0.1` or `[::1]`, so that a book's text never leaves the machine |
| `correct_second_model` | string, none | a second model whose reading of each page's notes marks the correct stage's doubtful edits; none by default |
| `correct_links` | bool, true | whether the correct stage also links footnotes to their references from the model's reading (`docs/specs/correct.md` §9b) |
| `exclude_pages` | list of page indices, `[]` | pages left out, as removals |
| `exclude_regions` | list of `{page, box}`, `[]` | a library stamp, a label |
| `cover_page` | page index, none | rendered as the EPUB's cover |
| `plate_pages` | list of page indices, `[]` | pages analyze makes plates whatever its rule finds, for a plate the rule misses (Kadesh's faint relief on page 23); a page in `exclude_pages` is never a plate, so a page in both lists is accepted and excluded: `exclude_pages` wins (`docs/specs/plates.md` §2) |
| `contents_pages` | list of page indices, `[]` | the pages of the book's printed table of contents: layout takes no cut-in notes from them (`docs/specs/layout.md` §3, step 2b), since a contents' chapter labels set small beside titles at the cut-in inset look like one (Turney's page 10); structure makes no heading on them but the title of each run of consecutive contents pages, a level-1 heading (`docs/specs/structure.md` §30, rule 1; settled for the owner on 18 November 2026), so that the EPUB's table of contents does not list each chapter twice (owner, 15 November 2026); their lines are contents entries, linked to the chapters' headings (`docs/specs/structure.md` §30; 18 November 2026). Without it, the contents' lines that pass the heading rule become headings, and the EPUB lists those chapters twice (Domesday's three essays). analyze checks its page indices as it checks those of the other keys |
| `front_matter_end` | page index, found by analyze | the first page after the front matter: the pages before it that would be text pages are dropped, each word recorded as a removal (owner, 17 November 2026: "drop the pages before the preface, with a record of what was dropped"). Without the key, analyze finds it: the first preface page or contents page among the book's first pages, else the first page of running text (`docs/specs/front-matter.md` §2). 0 keeps every page |
| `reread_footnotes` | bool, `false` | whether layout re-reads each page's footnote band with Tesseract (`docs/specs/reocr.md` §3); off by default because Tesseract misreads note markers and loses note links (Domesday) |

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
  spaces it needs. Edits match against this text. The printed lines of a
  block are joined by one space, except in a `verse` block, where they
  are separated by a line feed, `"\n"`, so that a poem keeps its printed
  line breaks (owner, 15 November 2026); a line feed is in no other
  block but an `epigraph` whose quotation is verse (`docs/specs/structure.md`
  §22; owner, 17 November 2026). Prose lines are always joined. In a
  book whose `language` is `fr`, structure puts a no-break space,
  U+00A0, before a spaced "?", ";", ":" or "!" (§23 of the same spec);
  it is white space to the fidelity check.

## 7b. Trusting the book's own OCR

Most scanned books already have a text layer, made by whoever scanned
them. galley trusts it, but checks it (owner, 14 November 2026). The
config's `ocr` key sets how far:

| `ocr` | analyze does |
|---|---|
| `verify` (default) | the audit below |
| `trust` | no audit of the text layer; pages without a layer are still checked as in the audit; layout re-reads nothing |
| `redo` | marks every text page for OCR; the text layer still decides what each page is |

**`redo`** (decided for the owner on 19 November 2026, plan ocr-redo).
analyze classifies the pages from the text layer as it does with
`verify`: the plate, inkless, front-matter and in-page figure rules use
the layer's word boxes, and a page without a layer is blank or a plate
as before. Then every page that ends as a `text` page gets the text
source `ocr`; every other page keeps the source it has with `verify`. A
plate keeps its layer, because Tesseract reads its picture as junk and
the layer reads its caption better: on Kadesh's 9 plates Tesseract
reads 0 to 140 words, the layer 2 to 24, and "PLATE II" where
Tesseract reads "Puate II" (measured on 19 November 2026 on the whole
book). analyze runs no audit and writes
`ocr_audit` `None`. extract reads each `ocr` page with Tesseract
(`docs/specs/extract.md` §9), and keeps the layer's words where
Tesseract read none, a line or a word it skipped, so that no printed
word is lost (on Kadesh 45 words, each a printed word as the layer reads it); the words of an excluded, front-matter or
inkless page are the layer's, recorded as removals, as with `verify`.
layout re-reads nothing. `cli.py` looks for Tesseract before analyze or
extract starts under `redo` and stops when it is missing (sections 12
and 16), so that a run does not stop at extract after analyze has
written its file; analyze itself calls Tesseract on no page. An excluded region
drawn against the layer's boxes is checked on the page's render under
`redo`, since Tesseract boxes a word where it is printed and the layer
may box it elsewhere (Kadesh's "81" on page 8, 12 pt apart). Measured
on 19 November 2026 on the whole Kadesh book, 45 text pages before page
74 was excluded (44 since): Tesseract took 0.95 s a page and the 54 pages it was tried
on about 11 s with 6 threads, on an M5 Pro; page 9, whose layer reads
"Me^iddo. already in tli.- sixti-fiith century ln-forr Christ", reads
"At Megiddo, already in the sixteenth century before Christ".

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

Besides the audit, layout re-reads small print where the layer is poor
(`docs/specs/reocr.md`): the outer margin notes, Stubbs' notes cut into
the column, the pages printed wholly in small type (Stubbs' index), and
the footnotes when the config asks. It chooses region by region and
keeps the layer wherever Tesseract's reading scores no higher, so it
replaces OCR that exists only where Tesseract reads better, and records
every word it replaces (owner, 17 November 2026: re-read small print
where the scan is good and the layer poor). `ocr = "trust"` turns it
off.

The sample size and the thresholds are set in analyze's spec. ocr_lab's
triage re-OCRed below a word-list share of 0.70 and checked between 0.70
and 0.80, which tracked the measured gain closely (ρ = 0.90, as ocr_lab's notes report it)
but was fitted on 16 books only.

## 8. The formats

The formats are frozen dataclasses in `src/galley/model.py`, with tuples
for sequences, `frozendict` (a built-in type of Python 3.15) for
mappings, `StrEnum` for finite sets, and floats for positions. Each file
has a `format_version` int: 5 for `blocks.json`, 4 for `lines.json` and
`pages.json`, 3 for `words.json`, 1 for the others.
`blocks.json` went to 2 with the second plan of structure (16 November
2026), which added `Note.kind`, `Block.label`, the block kinds `verse`
and `chapter_summary` and the removal reason `guide_words`; reading a
file of version 1 is the error below, and the owner reruns structure.
`pages.json` and `words.json` went to 2 on 17 November 2026, with the
page kind and the removal reason `front_matter`
(`docs/specs/front-matter.md`); the owner reruns analyze. `lines.json`
went to 2 the same day, with `rereads` (`docs/specs/reocr.md`); the
owner reruns layout. `blocks.json` went to 3 the same day, with the word
change reason `hyphen_lost` (`docs/specs/structure.md` §5); the owner
reruns structure. `blocks.json` went to 4 the same day, for the plan
owner-books, with the block kind `epigraph`, `Block.source`,
`Note.group` and the change reasons `source_dash`,
`punctuation_attached` and `case_split` (`docs/specs/structure.md` §7);
the owner reruns structure. `lines.json` went to 3 on 18 November 2026,
with `Reread.junk_words` (`docs/specs/reocr.md` §4, the review of work
package 2 of the plan owner-books); the owner reruns layout.
`blocks.json` went to 5 the same day, with the block kinds `list_item`
and `contents_entry`, `Block.page_number`, `Block.heading_ref`, the
change reason `list_marker` and the removal reason `leader_dots`
(`docs/specs/structure.md` §7), and the removal reason `figure_text`
(`docs/specs/figures.md` §7); the owner reruns structure. `pages.json`
went to 3 the same day, with `PageInfo.figure_boxes`, and `words.json`
to 3 and `lines.json` to 4, with `Figure.kind` (`docs/specs/figures.md`
§7); the owner reruns analyze, which deletes every later file.
`pages.json` went to 4 the same day, with the page kind `inkless`
(`docs/specs/plates.md` §2b); the owner reruns analyze. `words.json`
stays at 3 although its removals gain the reason `inkless_page`: a
words.json of version 3 is made from a pages.json of version 3, which
layout refuses, so a book run before the change is run again from
analyze either way. `blocks.json` stays at 5 although its removals gain
the reason `letter_fragment` (19 November 2026,
`docs/specs/structure.md` §35): a file of version 5 written before has
no such removal and is read as it was, and only the code that writes the
reason reads it. Under `ocr = "redo"` no file changes: an `ocr` page's
words in words.json are Tesseract's, with their confidences, as on any
page read by OCR. Each has
one pair of functions
in `model.py`, `write_<file>(path, value)` and `read_<file>(path)`:
`write_pages` and `read_pages`, `write_words` and `read_words`, and so on.
Reading a file whose `format_version` is not the current one is an error
that names both, and the stage to run again (`galley2epub structure`
for blocks.json). In JSON, a dataclass is an object with its field names,
a tuple a list, an enum its string value, a `Box` a list of four numbers,
and a `frozendict` with int keys an object whose keys are the ints as
strings.

Every file's top-level object has `format_version` and `source_pdf_sha256`.

**pages.json**, `PagesFile(pages: tuple[PageInfo, ...])`:

- `PageInfo`: `index`, `width_pt`, `height_pt`, `kind: PageKind`,
  `text_source: TextSource`, `text_layer_score: float | None`,
  `exclude_regions: tuple[Box, ...]`, `figure_boxes: tuple[Box, ...]`:
  the boxes of the figures analyze finds inside a text page, in points,
  from the top down and then from the left; empty on any other page
  (`docs/specs/figures.md` §3).
- `PageKind`: `blank`, `text`, `plate` (mostly a picture), `excluded`,
  `front_matter` (a page before the book's text that would otherwise be
  a text page: `docs/specs/front-matter.md`), `inkless` (a page that
  prints nothing, or only another page showing through or a patterned
  endpaper, while its text layer holds words the OCR invented there:
  at least half of those words have no ink under them on analyze's 36
  dpi render; `docs/specs/plates.md` §2b). analyze recognises a plate
  from a small render of the page, with a text layer or without one
  (`docs/specs/plates.md`). An inkless page is not `blank`: a blank page
  has no text layer.
- `TextSource`: `text_layer`, `ocr`, `none` (blank, excluded,
  front-matter and inkless pages, and plates without a text layer).
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
  0-100, for a word galley read with Tesseract, on an OCR page or in a
  region layout re-read; `None` for the text layer). In the order the source gave them:
  for the text layer, the order in which the PDF draws the characters,
  as `text_layer.layer_words` reads them (`docs/specs/extract.md`).
- `Figure`: `box`, `image` (path relative to the book folder), `dpi`,
  `kind: FigureKind`. A plate page has one figure, whose box is the
  whole page (`docs/specs/plates.md`); a text page has one for each box
  of its `figure_boxes`, cut to that box (`docs/specs/figures.md`).
  `kind: FigureKind` says which, `plate` or `in_page`: extract sets it
  when it cuts the image, layout copies it to lines.json, and structure
  reads it to send a plate's page to the plate rules and an in-page
  figure to those of `docs/specs/figures.md` §5. A plate page with a text layer also has the words of that layer, which
  structure sorts into its caption and stray words.
- A word inside an excluded region is a removal, one per word, with reason
  `excluded_region`; the words of an excluded page likewise, with
  `excluded_page`, those of a front-matter page with
  `front_matter`, and those of an inkless page with `inkless_page`. Such
  a page has no word in `PageWords.words`, so layout gives it no region
  and structure no block.

**lines.json**, `LinesFile(pages: tuple[PageLayout, ...], rereads:
tuple[Reread, ...])`:

- `PageLayout`: `index`, `regions: tuple[Region, ...]`, in reading order,
  and `figures`, copied from words.json so that structure need not read it.
- `Region`: `box`, `lines: tuple[Line, ...]`. A region is a part of the
  page whose lines are read one after the other: the body column, a
  margin, a column of footnotes, the running head. layout does not say
  what a region is; structure does. On a page with in-page figures, the
  words whose middle lies inside a figure's box, but for those of the
  page's first row, which may be its running head, are taken out of the
  regions the page's layout made with them and are a region of their
  own whose box is the figure's box (`docs/specs/figures.md` §5).
- `Line`: `box`, `words: tuple[Word, ...]`, left to right.

- `Reread`: a region of a page that layout read again with Tesseract
  (`docs/specs/reocr.md` §4): `page_index`, `kind: RereadKind`, `box`
  (the crop, in points), `layer_words` (the words of words.json it
  replaces, each the same printed word as one of its `ocr_words` by
  the rules of `docs/specs/reocr.md` §4),
  `ocr_words` (Tesseract's, without its junk), `layer_score` and `ocr_score`
  (ints, known words minus unknown words of each reading, the layer's
  as `docs/specs/reocr.md` §3 scores it), `kept`
  (whether `ocr_words` took the place of `layer_words`: `ocr_score`
  higher, or equal with more known words, and, where `layer_words` is empty, at least 2 known words or
  one sure single word, `docs/specs/reocr.md` §3), and
  `dropped_junk_count` (Tesseract's words of no letter or digit, not
  punctuation or a printed sign, dropped from `ocr_words`, and its words
  stripped of an underscore at either end, `docs/specs/reocr.md` §4),
  and `junk_words` (those of `layer_words` that layout replaced as the
  layer's junk under a Tesseract word paired with the layer's copy of
  its word, by its word list; reocr §4, the exception in (a)). Every region read is recorded, kept or not, in page order.
- `RereadKind`: `small_print_page` (a page printed wholly in small
  type, read below its running head), `margin_note` (one note of an
  outer margin), `cut_in_note` (one crop of Stubbs' notes cut into the
  column), `footnote_band` (a page's footnotes, when the config's
  `reread_footnotes` asks).

layout regroups words and re-reads small print: every word of
words.json is in exactly one line of lines.json or among the
`layer_words` of exactly one kept `Reread`, and every word of a line is
a word of words.json or among the `ocr_words` of a kept `Reread`. It
removes nothing. The removals of words.json are not
repeated in lines.json or blocks.json: each file lists only the removals
its own stage made.

**blocks.json**, `BlocksFile(blocks, notes, removals, word_changes,
page_numbers)`:

- `Block`: `id`, `kind: BlockKind`, `level: int | None` (a heading's
  level, 1 or 2; an index entry's depth, 1 for an entry and 2 for a
  sub-entry printed inside it, more if a book prints deeper ones, so that
  the EPUB can indent it as printed (owner, 16 November 2026); a contents
  entry's depth, 1 for a chapter and more for what the contents prints
  under it; `None` for every other kind: reading a blocks.json where an
  index entry or a contents entry has no depth from 1, or a block of
  another kind than these and a heading has a level, is an error that
  names the file and the block. The depth was added without a new
  version, at version 2: a file written before it has index entries without
  one, and the error says to run structure again), `label: str | None` (headings: the chapter label as printed,
  "CHAPTER III.", "V"; list items: the list marker as printed, "—",
  "1.", "(a)", never `None`; contents entries: the chapter's number as
  printed before the title, "2.", "One", "CHAPTER II."; `None` for a
  heading or a contents entry without one and for every other kind:
  reading a blocks.json where a block of another kind has a label, or a
  list item has none, is an error that names the file and the block),
  `source: str | None` (epigraphs: the source line as printed, without
  its leading dash, words joined by single spaces; `None` for every
  other kind: reading a blocks.json where a block that is not an
  epigraph has a source is an error that names the file and the block),
  `page_number: str | None` (contents entries: the page number printed
  after the title, words joined by single spaces, "23", "pp. 9 — 26.",
  kept and not shown in the EPUB; `None` when the entry has none and for
  every other kind), `heading_ref: str | None` (contents entries: the id
  of the heading block of the chapter the entry names, so that markdown
  links the entry to it; `None` when no heading matches and for every
  other kind; a blocks.json where another kind has one of these two
  fields, or a `heading_ref` names a block that is not a heading, is an
  error that names the file and the block),
  `spans: tuple[Span, ...]`, `figure: str | None` (figure blocks),
  `origin: tuple[Origin, ...]`.
- `BlockKind`, each value what the text is:
  - `heading`: a chapter's or a section's heading. A chapter label and
    the title under it ("CHAPTER III." / "THE EARLY YEARS OF HENRY II.")
    are one heading, the label being the chapter's number and the title
    its title (owner, 15 November 2026); the label is in `label` and the
    spans hold the title (owner, 16 November 2026), so that markdown can
    set the number apart. An edit matches the spans' text, so it cannot
    correct a label;
  - `paragraph`: a paragraph of running text;
  - `quote`: a passage quoted from another text, in prose;
  - `verse`: lines of a poem, quoted or not; its text keeps the printed
    line breaks (section 7);
  - `chapter_summary`: the list of a chapter's topics printed under its
    heading, as Stubbs prints one under each chapter (owner, 15 November
    2026);
  - `epigraph`: a quotation set at the head of a chapter, before its
    text; its spans hold the quotation, with a line feed between its
    lines when it is verse, and `source` its source (owner, 17 November
    2026);
  - `figure`: a picture, with its caption as the block's text (empty when
    it has none) and its image in `figure`;
  - `margin_note`: a short heading printed beside the text (section 17);
  - `index_entry`: one entry of the book's printed index, or one
    sub-entry of it, its depth in `level` (section 11);
  - `list_item`: one item of a list the book prints, its marker in
    `label` (`docs/specs/structure.md` §29);
  - `contents_entry`: one entry of the book's printed table of contents:
    its number in `label`, its title in the spans, its page number in
    `page_number`, its depth in `level` and the heading it names in
    `heading_ref` (`docs/specs/structure.md` §30).
- `Span`: `text`, `emphasis: Emphasis`, `note_ref: str | None`. A span
  with a `note_ref` is a note reference: `note_ref` is the id of the
  note, and its `text` is the reference as printed, or as the OCR read
  it, which may differ from the note's `marker` ("3" against "8", "^"
  against "*"): a reference is linked when it has a marker's shape and
  falls in the right order, and the text keeps what the OCR read (owner,
  15 November 2026). Section 13 says what the fidelity check asks of it.
- `Emphasis`: `none`, its only value for now (owner, 14 November 2026:
  no italics yet; the field is kept for them).
- `Note`: `id`, `kind: NoteKind`, `marker` (as printed at the start of
  the note: "8", "*", "291.", or as OCR misread it; empty when it has
  none), `blocks: tuple[Block, ...]` (a note may have several
  paragraphs, and margin notes: below), `origin`, `referenced: bool`,
  `group: str | None` (on the first note of a note group of an endnote
  section, the group's heading as printed, "Chapter 1." and the
  chapter's title; `None` on every other note:
  `docs/specs/structure.md` §12). A
  note whose reference structure could not find (in Gierke's excerpt,
  endnotes 291 to 294, whose references are on pages outside it) has
  `referenced` false. A reference in the text
  whose note was not found is left in its word, unsplit.
- `NoteKind`: `footnote`, a note printed at the foot of its page;
  `endnote`, a note printed with the others in a section of their own,
  at the end of the book or of a chapter (Gierke's "NOTES.", pages 186
  to 282 of the whole book). They are kinds of their own although both
  are notes (owner, 15 November 2026): in the EPUB a referenced footnote
  becomes a pop-up at its reference and leaves the page it was printed
  on, while every endnote stays in the list where it was printed and a
  referenced one is also shown as a pop-up from its reference (section
  9).
- A note's blocks are paragraphs, quotes or verse, and the margin notes
  printed beside them: a margin note beside a note's line is a
  `margin_note` block inside that note, before the note's block that
  holds the line (owner, 15 November 2026; Gierke prints them beside its
  endnotes).
- `Origin`: `page_index`, `box`. A paragraph that runs over a page break
  has two.
- `WordChange`: `page_index`, `before: tuple[str, ...]`, `after:
  tuple[str, ...]`, `reason: ChangeReason`: a word that structure changed
  without losing any letter. `hyphen_join`: ("repli-", "cate") becomes
  ("replicate",), because the word list or the book's own words hold the
  joined word; when the OCR read the hyphen as a sign of a note
  reference, ("aggres*", "sive") becomes ("aggressive", "*"), the sign
  last, and a removal `misread_hyphen` of that sign on the change's page
  records it (structure §5). `hyphen_join_guessed`: the same, when neither holds it
  (structure §5), recorded so that the guessed joins can be reviewed.
  `hyphen_kept`: ("Anglo-", "Saxon") becomes ("Anglo-Saxon",), a
  compound the book prints with its hyphen. `hyphen_lost`: ("move.",
  "ment,") becomes ("movement,",), two parts of a word in a margin note
  whose line-end hyphen the OCR dropped or read as "." (structure §5).
  `note_marker`: ("Greece,1",)
  becomes ("Greece,", "1"), the "1" going to the note reference.
  `source_dash`: ("—Hobbes",) becomes ("Hobbes",), the dash before an
  epigraph's source, which markdown writes back. `punctuation_attached`:
  ("subjection", ";") becomes ("subjection;",), a spaced sign attached
  in a book not in French. `case_split`: ("theAvre",) becomes ("the",
  "Avre"), a word the OCR glued at a case change
  (`docs/specs/structure.md` §22 to §24); also a contents entry's
  junk glued to a word that starts with a capital, split off and
  removed (§30, rule 11). `list_marker`: ("—The",)
  becomes ("—", "The"), a list item's dash split off its first word,
  the dash going to the item's `label` (§29 of the same spec). A spec
  adds a reason when it needs one.
- `PageNumber`: `page_index`, `text`, `position: head | foot`.
  `page_numbers: tuple[PageNumber, ...]`, taken from the removals; the
  index stage uses it (section 11).

**Removal**, in words.json (excluded pages and regions, the front
matter and inkless pages) and blocks.json (the rest): `page_index`, `box`, `text`,
`reason: RemovalReason`: `excluded_page`, `excluded_region`,
`front_matter` (a word of a page before the book's text, where analyze's
rule or the config's `front_matter_end` puts the end of the front
matter; a reason apart from `excluded_page`, whose pages the owner names
one by one),
`inkless_page` (a word of an inkless page, which the OCR read in what
shows through the paper or in an endpaper's pattern; a reason apart
from `excluded_page` because analyze's rule, not the owner, chose the
page), `running_head`, `page_number` (a page's own number, or a
contents entry's page number that its title kept, misread or at an
ordinary space, structure §30 rule 11), `signature_mark`, `plate_text`,
`stray_mark` (a line with no letter or digit above a running head or
above the title of a printed contents, a speck of the scan; and a
reader's pen mark or a speck read as text before a contents entry's
label, at the start of its title with any number read together with
it, or at its end, structure §30 rules 7 and 11),
`guide_words` (the first letters of the first and last entries that
Stubbs prints under the running head of an index page, "BUR CON"),
`leader_dots` (the dots printed between a contents entry's title and
its page number, `docs/specs/structure.md` §30), `figure_text` (the
words the OCR read inside a figure printed on a text page: its
lettering, labels and shading, which its image shows;
`docs/specs/figures.md` §5), `letter_fragment` (a piece of a letter, a
descender or the dot of an "i", that the text layer gives as a word of
its own inside a word of the line, in a book where such pieces are
common: Stubbs; `docs/specs/structure.md` §35), `misread_hyphen` (a
line-end hyphen the OCR read as "*", "^" or "•", taken off when
structure joins the two parts of the word, Stubbs' "aggres*" "sive";
structure §5). A stage spec adds a
reason when it removes a new kind of text, and the reason names what the
text is, never "noise": a plate's stray text-layer characters are removed
as `plate_text` by structure, which the owner can review.

**Edit**, one JSON object per line of a file under `edits/`:
`format_version` (2), `block_id`, `block_sha256` (the first 12 hex digits
of the SHA-256 of the block's text as structure wrote it), `old`, `new`,
`author`, `reason`, and, since version 2 (19 November 2026, the correct
stage), `page_index` (the page the changed word is printed on), `model`
(the vision model that read the new text) and `second_reading` (what a
second model read there, `docs/specs/correct.md` §9), each `null` for an
edit made by a person or an agent. Only version 2 is read; no file of
version 1 was ever applied. The version is on every line, not in a header, so that
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
`exclude_pages` and `exclude_regions`; finds where the front matter
ends and makes the text pages before it `front_matter`
(`docs/specs/front-matter.md`); marks a page whose text layer holds
words with no ink under them `inkless` (`docs/specs/plates.md` §2b);
and runs the OCR audit of section
7b, which decides each page's `text_source`. A plate is recognised from
a render of each page at 36 dpi, as a large area of ink that no word
covers on a page of few known words, or, on a page without a text
layer, as a large area of faint ink; such a page does not stop the run
(`docs/specs/plates.md`). On a text page it also finds the figures
printed among the lines, from the same render, as groups of ink that no
word covers (`docs/specs/figures.md`).

**extract** gives every page its words. Text-layer pages are read with
pdfplumber, one document per worker thread, by
`text_layer.layer_words`: the characters in the order the PDF draws
them, and words the OCR left glued split at wide gaps
(`docs/specs/extract.md`). OCR pages are rendered at 300
dpi by `pdfium.py` and read by Tesseract in parallel; their pixel boxes are
turned into points. Under `ocr = "redo"` a text page's layer is read
too, and where Tesseract lost a note reference the layer reads, the
layer's reference is put back on Tesseract's word
(`docs/specs/extract.md` §9). A plate page is rendered whole at 300 dpi into
`images/`; its text layer, when it has one, is read as a text page's
is, so that structure can keep the caption and remove the rest. The
`cover_page` of the config is rendered whole, as `images/cover.png`,
and is never a plate. A figure inside a text page is cut from a render
at 300 dpi to its box.

**layout** groups each page's words into regions and lines, and orders
them for reading: a column, then the next; the margin beside the body,
and the notes Stubbs cuts into the body column; the footnote columns at
the foot. Where small print reads better with Tesseract than in the text
layer, it re-reads it, region by region, with renders from `pdfium.py`
(`docs/specs/reocr.md`). It copies the page's figures through, and
keeps the words read inside a figure in a region of their own.

**structure** turns regions and lines into blocks and notes. It first
reads the whole book to find what repeats: running heads, page numbers,
signature marks, the line heights of body and notes. Then, per page, it
removes those, decides what each region is, finds headings, chapter
summaries and verse, groups lines into paragraphs, keeps a plate's
caption and removes its stray words; removes the words read inside a
figure on a text page, keeps its caption as the figure block's text,
and places the block after the paragraph printed before it, or after
the whole list when the text before it is a list item
(`docs/specs/figures.md` §5); and joins hyphenated words
(dropping the hyphen where the word list or the book's own words allow
it, keeping it in a compound the book prints, and dropping it as a
recorded guess where neither decides; `docs/specs/structure.md` §5);
finds the epigraphs under a chapter's heading and splits words glued at
a case change. On the pages of `contents_pages` it makes each entry of
the printed contents a block, with its number, title, page number and
depth (`docs/specs/structure.md` §30). It attaches a spaced "?", ";", ":" or "!" to the word
before it, or, in French, puts a no-break space before it, each change
recorded (§22 to §24 of the same spec). A figure's caption is taken
out of the body stream before headings, list items and contents
entries are looked for, so a caption that opens like a numbered item
("13. The…") is never one, and a list goes on across a figure printed
between two of its items (`docs/specs/structure.md` §2, step 2.2, and
§29, rule 5).
Last, over the whole book, it joins paragraphs that run over a page
break and finds the items of lists, since an item too can run over a
page break (§29 of the same spec); cuts the notes, joins those that run over a page break, finds
the endnotes, and matches each note reference to its note, splitting it
off the word it is glued to; makes the index's entries and links each contents entry to the
heading of its chapter, found by its title; finds quotes,
after the notes, so that a note left in the body is not taken for one;
and places each margin note just before the paragraph whose line it
sits beside (`docs/specs/structure.md` §2 gives the order).

**correct** has a local vision model, through LM Studio, read each text
page rendered at 300 dpi; lines the model's words up with galley's words
of the page, taken from blocks.json in the order they were printed; and,
where two words that line up differ, writes the model's word as an edit
in `edits/correct.jsonl`, and in the notes also the model's words galley
lacks. It never changes a note marker or reference, a label, the order of
blocks, or a page that is not a text page. It is optional
(`docs/specs/correct.md`).

**markdown** applies the edits files (section 10) to the blocks and writes `book.md`: a
metadata header from the config; headings with their block id as anchor;
every other block as a Pandoc fenced div with its id (`::: {#b-p0012-003}`);
notes with `referenced` true as Pandoc footnotes, each of their blocks a
fenced div with its id inside the footnote, which Pandoc puts at the end
of each chapter and the Kindle shows as pop-ups (section 17);
footnotes with `referenced` false, each a div with its id and its
marker first, at the end of their chapter (the blocks up to the next
heading of level 1 or 2, or the book's end), after a heading "Notes"
one level below the chapter's, of class `unlisted`, which keeps it out
of the EPUB's table of contents, and `chapter-notes`
(`docs/specs/structure.md` §36; owner, 19 November 2026); endnotes, referenced or not, where they were
printed, as one list in the book's order, each note a div with its id,
and each reference to one a link to it marked as a note reference
(`epub:type="noteref"`), which a Kindle can show as a pop-up (Pandoc
3.14 keeps an `epub:type` attribute on a link and a div, and points the
link into the right chapter file, checked on 16 November 2026; the
pop-up itself was not tried on a Kindle); a `verse` block with a hard
line break at each line feed; an `epigraph` as a div holding its
quotation, with hard line breaks when it is verse, and a div of class
`epigraph-source` holding a dash and its source, the dash written as text;
a note group's heading as a div of class `note-group` before its first
note, not a heading (`docs/specs/structure.md` §25); a margin note inside a note within that
note; figures as images with their caption; consecutive list items as
a Pandoc list, bullet for dashes and bullets and ordered for numbers
and letters, each item the div of its block, the printed marker not
written; the entries of a printed contents as a bullet list inside a
div of class `contents`, nested by depth, each entry's title a link to
its heading when it has one, its page number not written (§31 of the
same spec). How each kind is written and
styled is the markdown and epub specs' to decide. Pandoc runs with
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
  name, then `owner.jsonl` last, each from its first line to its last,
  whatever the config's `correct` says: that key decides only whether
  `run` runs the correct stage.
  The owner's edits come last because `edits-from` finds them on a
  `book.md` that already had every other edit applied. A missing file is
  simply no edits.
- An edit applies when its block exists, the checksum matches the block's
  text as structure wrote it, `old` appears exactly once in the block's
  text as edited so far, and that occurrence lies inside one span that is
  not a note reference, so that no edit changes a note reference or joins
  two spans (`docs/specs/correct.md` §10). Then `old` becomes `new` in
  that span. An edit whose `new` ends with a link to a note,
  `[x](#n-p0008-004)`, puts a note reference after the new text, or in
  place of the reference that follows it (`docs/specs/correct.md` §9b
  and §10). Otherwise markdown stops with an error
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
- The correct stage writes `edits/correct.jsonl` whole on each run, and
  each of its edits applies whether or not its others do, so that the
  owner can undo one by deleting its line (`docs/specs/correct.md` §8
  and §11).

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
| `model.py` | the formats of section 8, with their read and write functions; and the rules of re-reading (`docs/specs/reocr.md` §4) that layout and the fidelity check share: `replaced_layer_words(layer_words, ocr_words, is_known=..., is_junk=...)`, the layer words a kept `Reread` replaces, and `matched_ocr_positions`, the Tesseract words that read them; `junk_layer_words`, those of them replaced as the layer's junk, a `Reread`'s `junk_words`; `scored_layer_words`, the layer words whose reading score is set against Tesseract's (reocr §3); `is_junk_beside_its_copy(junk, copy, ocr_word)`, the one pair of layer words of two lines a Tesseract word may read (section 13); `is_under_ocr_word` and `may_read`, the tests of rule (a) and of any one rule alone; `words_after_rereads(words, rereads)`, a page's words as lines.json holds them; `take_out_once(groups, taken)`, `word_middle(word)` and `folded_letters_and_digits(text)`; `every_block(blocks)`, the body's blocks then the notes', and `only_occurrence(text, part)`, where an edit's `old` occurs once, which the correct stage and markdown share (`docs/specs/correct.md` §8 and §10) |
| `config.py` | `BookConfig`, `read_config(path)`, the language codes |
| `book_folder.py` | `BookFolder` |
| `errors.py` | `GalleyError` and its subclasses: `ConfigError`, `InputFileError` (missing, stale or of another format version), `PdfError`, `ExternalProgramError` (missing or failed Tesseract or Pandoc, or LM Studio not answering or without the model), `EditError`, `FidelityError` |
| `pdfium.py` | the one thread that calls PDFium, which is not thread-safe. It opens and closes the PDF itself for each request: `page_count(pdf)`, `page_size(pdf, page_index)`, `render(pdf, page_index, dpi) -> RenderedPage`; and `POINTS_PER_INCH` (72), which turns a DPI into pixels per point |
| `parallel.py` | `DEFAULT_WORKERS` (6); `map_pages(function, items, workers)`, which returns the results in input order; and `map_pages_with_source(open_source, function, items, workers)`, which opens one source per worker thread (a pdfplumber document) and passes it to every call on that thread. A source is closed when its thread ends, also when `function` raises; the exception propagates |
| `text_layer.py` | `open_pdf(pdf) -> pdfplumber.PDF`: the one way galley opens a pdfplumber document. It opens under a lock, because pdfminer.six (20260107) interns PDF keywords in a shared table without one and can fail, about 1 run in 100 with several workers, when two threads open documents at once; reading pages stays parallel. A PDF pdfplumber cannot read becomes a `PdfError` naming the file. `layer_words(page) -> tuple[Word, ...]`: the one way galley reads a page's words from the text layer, in analyze and extract alike; `Character`, a frozen value (`text`, one character, and `box`), one glyph of the text layer; and `split_glued(characters)`, which cuts one word's characters into the words the OCR glued (`docs/specs/extract.md` §4 and §5) |
| `wordlist.py` | `is_known_word(word, lower_case_words)`, whether a word counts as known on a plate (`docs/specs/plates.md` §2); `lower_case_word_list(language, cache_dir)`, the word list in lower case, made once per language and list folder, which structure, analyze and layout take; `word_list(language, cache_dir) -> frozenset[str]`, with the dictionary's case, extracted from Tesseract's language data with its `combine_tessdata` and `dawg2wordlist` tools, as the owner's ocr_lab does, and cached under `~/.cache/galley/`; `is_cached(language, cache_dir)`; `WORD_LIST_TOOLS` and `missing_tools(language, cache_dir)`, the tools not on the PATH when the list is not cached, which the command checks before analyze (plates, `docs/specs/plates.md`), layout (re-reading, `docs/specs/reocr.md`) and structure |
| `ocr.py` | Tesseract: `read_image(image, origin, dpi, psm, language)`, the words of an image cropped from a page, with boxes in points and Tesseract's confidence, and `words_of_tsv`, its pure part; `read_image_lines` and `lines_of_tsv`, the same words grouped by Tesseract's lines; `point_box(box, origin, dpi)`, a box in pixels of a crop as a box in points on the page; `OCR_DPI` (300). Tesseract runs with `OMP_THREAD_LIMIT=1`, one core each, so that the parallelism is galley's; output without Tesseract's tsv header is an `ExternalProgramError` (`docs/specs/reocr.md` §5). layout uses it now, extract for the text pages under `ocr = "redo"` (`docs/specs/extract.md` §9), analyze's audit later |
| `fidelity.py` | the fidelity check, section 13 |
| `list_markers.py` | the readings of a list marker (`docs/specs/structure.md` §29, "Terms"): `marker_readings(word)`, its kind, form and value, a roman numeral before a letter; `starts_a_list`, `follows` and `is_bulleted`; and `DASHES`, which structure's list rules, markdown's lists and the fidelity check share, so that the three read a marker alike |
| `caption_labels.py` | the caption labels of `docs/specs/figures.md` §1: `LABEL_NAMES` ("figure", "fig.", "fig", "plate", "map"), `is_numeral(text)`, a numeral as the OCR reads one, and `is_well_formed_numeral(text)`, one as printed (1 to 3 digits or a well-formed roman numeral in capitals). Moved from `structure/_figures.py` on 19 November 2026, so that structure's caption labels and extract's caption numbers under `redo` (`docs/specs/extract.md` §9) read a numeral alike |
| `note_references.py` | `glued_reference(word) -> Reference \| None`: the glued number of `docs/specs/structure.md` §11, "Candidates", both its forms, a letter, any punctuation or none, 1 to 3 digits and only punctuation, not after a citation's abbreviation ("land3.", "Kadesh,12"; not "p.12"), and punctuation, 1 to 3 digits and only punctuation (";13"), with its parts; `Reference` and `ReferenceForm`, the values it gives; and the helpers structure's other reference forms share with it, `PUNCTUATION`, `is_punctuation` and `after_last_letter`. Moved whole from `structure/_markers.py` on 19 November 2026 (its private `_glued` and the two values), and structure's `reference_candidate` calls it, so that extract puts back under `redo` exactly the references structure looks for (`docs/specs/extract.md` §9) |
| `hyphens.py` | `LINE_END_HYPHENS`, "-" and "¬", the hyphens that end a printed line in the OCR's text, which layout's reading score, structure's hyphen joins and the fidelity check share (`docs/specs/structure.md` §5) |
| `body_measures.py` | the rules that measure a book's body text, which layout and structure both use, so that they are written once: `group_rows(words)`, the rows of a page's words (layout §1, "Row"); `edge_counts(edges)`, each edge rounded to the point with the number of edges within 2 pt of it, and `commonest(edges)`, the value with the most (layout §1); `median_word_height(words)`; `measured_pages(rows_by_page)`, the pages of at least 15 rows, or of 3 when none has 15, and `measured_page_positions(rows_by_page)`, their positions in `rows_by_page`; and `body_measures(rows_by_page) -> BodyMeasures \| None`, the body word height and body line pitch (layout §3), `None` when no page has 3 rows. It takes rows, not words, so that a stage groups each page once and uses the rows for its own work too |
| `cli.py` | the `galley2epub` command. Before any work it finds, with `shutil.which`, the external programs the requested stages need (Pandoc; Tesseract, which layout needs unless the config's `ocr` is `trust` or `redo`, and analyze and extract when it is `redo`) and stops naming any that is missing; and, when the command runs correct, LM Studio's server and its models (`correct.check_server`) |

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
- A note reference span must name a note of the file and have a
  **marker's shape**: 1 to 4 characters, at most 3 of them letters or
  digits, no white space, no "&" and no dash; a letter only in a span
  that holds a round bracket, and then at most one ("8", "^", "345",
  "(12)", "(i)", "(t)", "U)", "(3J"). Moreover a span with a letter must
  have been split off a word by a `note_marker` word change: a span that
  was a whole word in lines.json holds only digits and symbols. A word
  of the book cannot hide in it: "the", "and" are too long, "a", "à",
  "I,", "&c." and "—" have no shape, and "(a)" printed as a word of its
  own stays one (decided in the review of the plan structure-second, 16
  November 2026: Mariéjol has 18,247 block words of the earlier shape
  with a letter).
  One letter is accepted outside round brackets: a span "V" that names a
  footnote and that a `note_marker` word change split off the end of a
  word whose part before it ends with two lower-case letters
  ("adquesieritV" to "adquesierit" and "V"). Domesday's OCR reads a
  raised number glued to its word so, and structure links it only
  between two linked neighbours where the page's numbering expects the
  reference (`docs/specs/structure.md` §11, "A trailing V"; owner, 23
  November 2026). A roman numeral, "IV" or "XV", and a capital word keep
  their "V": the part before it does not end with two lower-case
  letters. A "V" to an endnote, a "V" that was a word of its own, and
  any other letter are refused as before.
  Structure links no candidate without this shape (its bracketed form
  allows two letters read as digits, "(li)" for 11, which then stays in
  its word). The span need not read as its note's `marker`: the OCR
  reads the two sides of a superscript differently (section 8; owner,
  15 November 2026). These checks run at the structure boundary, and at
  the markdown boundary on the blocks with the edits applied.
  Before, the check asked for the marker exactly, which left 1,202 of
  Domesday's 1,440 matched references linkable, 182 of Mariéjol's 676
  and none of Gierke's 205 (`docs/specs/structure.md` §11).
- At the structure boundary each word change must do what its reason
  allows and no more (a `hyphen_join` drops only the hyphen ending its
  first part, a `note_marker` keeps every character), since the
  multiset comparison takes a change on trust. A `hyphen_join` over a
  sign read in place of the hyphen, ("aggres*", "sive") to
  ("aggressive", "*"), is accepted only when the `misread_hyphen`
  removals of each page and sign number exactly such joins over that
  sign on that page (`docs/specs/structure.md` §5), so that the sign
  cannot vanish without a record and no such removal stands alone.
- It compares multisets over the whole book, not page by page, because a
  paragraph or a hyphen join can run over a page break and its words then
  belong to two pages. Order is not part of the check, because columns,
  margins and notes move between stages; order within a block is checked
  by structure's tests.
- The boundaries: layout, words.json against lines.json, with the
  `layer_words` of each kept `Reread` taken out of words.json's side and
  its `ocr_words` added, and each kept record's `layer_words` required
  to be words of its page in words.json, none in two records, each the same
  printed word as one of the record's `ocr_words`: its middle inside the
  box of one of them widened by 2 pt up and down and 1 pt across and of
  that word's printed line, or glued over two or three of them, or its letters and digits equal to
  those of the nearest one within 16 pt above or below that no other
  layer word matched, or, for a word of 3 letters or more, its letters
  alike to those of the nearest one within 16 pt that neither rule
  matched (difflib's ratio 0.6 or more: the layer's garbled copy of a
  word Tesseract read) (`model.replaced_layer_words`,
  `docs/specs/reocr.md` §4). Because that pairing is layout's own, a
  second test does not use it: no Tesseract word of a kept record may
  be the only one of the record that can read two of its `layer_words`
  of different printed lines, whose boxes do not overlap up and down
  (a Tesseract word can read a layer word that lies under it, or whose
  letters and digits it holds, or whose letters are alike to its own,
  within 16 pt, as the three rules say). One Tesseract word then
  stands for two printed words, and one of them is lost (Domesday page
  548, review of 17 November 2026). The one pair allowed is a word of the
  record's `junk_words` under the word, with letters unlike its own, and
  the layer's copy of the word beside it, not under it, with its letters
  or letters alike (`model.is_junk_beside_its_copy`; reocr §4, the
  exception in (a)). The check has no word list, so it takes as junk
  only the words the record names, which must be among its
  `layer_words`: a word under such a Tesseract word that the record does
  not name is matched by no rule, and the check fails; structure,
  lines.json against blocks.json (the text of every body and note block,
  with a note's `marker` and `group`, a block's `label`, an epigraph's
  `source` and a contents entry's `page_number` counted as words of
  it; a contents entry's label that structure §30 rule 12 inferred, a
  number between two in sequence, is admitted, §31 of that spec); markdown, blocks.json
  with the edits applied against `book.md` as Pandoc reads it (`pandoc -f
  markdown-smart -t json`): a reference to a footnote is matched to
  Pandoc's note element and its marker is not compared as a word, because
  Pandoc writes its own numbers (section 17); likewise the `marker` of a
  referenced footnote. A reference to an endnote is a link marked as a
  note reference (section 9), which Pandoc reads as a `Link` element with
  the attribute `epub:type="noteref"`. Its text is the reference span's
  and is compared as a word of its own, so that a word put into the link
  is found; an element galley's Markdown does not make is an error inside
  a link as anywhere else. The number of such links must equal the number
  of references to endnotes, as the number of Pandoc's notes must equal
  the number of references to footnotes. A link from a contents entry
  to its heading is the one other link (below). Any other link is an element
  galley's Markdown does not make, and an error. An endnote stays where it was printed, so its
  `marker` is written there and counted, referenced or not (section 9).
  A heading's `label` is written in `book.md`, in the form the markdown
  spec gives, and counted as words of its block; so are an epigraph's
  `source`, in its `epigraph-source` div after the dash markdown writes
  there, which is not compared, and a note's `group`, in the
  `note-group` div before the note (`docs/specs/structure.md` §25).
  A heading of class `chapter-notes`, the "Notes" markdown writes
  before a chapter's unlinked footnotes, holds no word of the book:
  `read_markdown` gives no word for it when its text is exactly
  "Notes", and raises an error with any other text (§36 of the same
  spec).
  A list in `book.md` is read item by item, each item's blocks as
  blocks, and holds only the forms markdown writes: an item of one div
  of a list item, or of one div of a contents entry followed by a
  nested list of the same form. A list item's `label` is not written
  and not compared, as a referenced footnote's marker is not, and the
  items of the lists of list items must number the list items of
  blocks.json. A contents entry's `label` is written and counted; its
  `page_number` is not written and not compared. A link inside a
  contents entry's div, with no attributes, whose target is the id of
  a heading block, is read as its text, compared as words of the
  entry; such links must number the entries with a `heading_ref`
  (§31 of the same spec).
- A figure's image is the one place `book.md` holds an image. Pandoc
  reads a figure block with a caption as a `Figure` element whose
  caption holds the caption's words and whose body is one `Image`, and
  copies the caption into the image's alt text (Pandoc 3.14, checked on
  16 November 2026); without a caption, as a paragraph that holds only
  an `Image` with no alt text. The check counts the caption's words
  once, as words of the figure's block, and reads the alt text only to
  require that it is the caption, word for word, or empty without one;
  the image's title and attributes must be empty. Any other `Image` or
  `Figure`, an image inside a sentence, an alt text of its own, is an
  element galley's Markdown does not make, and an error, so that no word
  hides where the check does not count it.
- extract is where the words enter galley, so it has no boundary to check:
  its excerpt tests compare its words with literals. Under `ocr =
  "redo"` its words are Tesseract's, which skips a printed line now and
  then; no check could see that, since nothing before extract holds the
  words, so extract keeps every layer word with a letter or a digit
  that no Tesseract word covers, and logs their number per page
  (`docs/specs/extract.md` §9, "Layer words Tesseract missed").
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
| Tesseract | analyze (the OCR audit), extract (OCR pages, every text page under `ocr = "redo"`), layout (re-reading small print), `wordlist.py` | runs that need OCR: layout unless `ocr` is `trust` or `redo`, and extract on every text page when it is `redo`, which `cli.py` checks before analyze starts; the word list, once per language | OCR is not something to rebuild |
| epubcheck | the tests of the epub stage and the `whole_book` tests | development only | it is the reference validator of EPUB, and needs Java, which a run of galley should not |
| LM Studio | correct, through HTTP on the local machine only | runs with `correct = true`; `cli.py` checks that it answers and has the model before the first stage | serving a vision model on the Mac's GPU is a large body of work; galley sends it a page and reads its text (`docs/specs/correct.md` §4) |

The epub stage does not run epubcheck: an EPUB is checked while
developing, on the excerpts and the whole books, and the tests that need
it are marked `epubcheck` and skip when it is missing. It is installed
with `brew install epubcheck` (5.4.0) before the epub stage is built.

## 17. Decided by the owner

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

On 15 November 2026, for the second plan of structure:

- **Formats are semantic** (section 3): a kind says what a text is, and
  the markdown and epub stages decide how it looks.
- **A chapter label and its title are one heading** (section 8).
- **Chapter summaries** are a kind of their own, `chapter_summary`.
- **Verse keeps its printed line breaks**; prose lines are still
  joined (section 7). That verse is a block kind of its own, `verse`,
  rather than a quote with line breaks, was decided while writing, by
  the first point.
- **Printed contents pages make no headings**; the config names them
  (`contents_pages`, section 6).
- **A reference that reads differently from its note's marker** is
  linked when it has a marker's shape and falls in the right order
  (sections 8 and 13).
- **Endnotes** are a kind of note of their own; a linked one shows as a
  pop-up, and all stay in a list where they were printed (sections 8 and
  9). A margin note beside an endnote goes inside it, before its text.
- **Plates** are recognised by analyze from a small render; extract cuts
  the picture; the caption becomes the plate's figure block, and the
  stray words of the text layer are removed as `plate_text`
  (`docs/specs/plates.md`). A plate without a text layer is a figure
  too.
- **Stubbs' cut-in margin notes** are found by layout from the text
  layer, not from a render (`docs/specs/layout.md` §9).
- **The body measures** are one module of the package root,
  `body_measures.py` (section 12).

On 16 November 2026, for the same plan:

- **Stubbs' cut-in rule is kept as written**, below the bar set for it:
  precision 0.913 against 0.95, recall 0.52 on Stubbs' whole book
  (`docs/specs/layout.md` §9).
- **A heading's chapter label is a field of its own**, `Block.label`,
  and the spans hold the title; the fidelity check counts the label as
  words of its block (sections 8 and 13).
- **Haskins' bibliographical notes are paragraphs**: the blocks after a
  level-2 heading "BIBLIOGRAPHICAL NOTE", up to the next heading,
  whatever their type (`docs/specs/structure.md` §16).

On 17 November 2026:

- **The text layer is read in the PDF's order**, not sorted by position,
  and words the OCR left glued are split at wide gaps
  (`docs/specs/extract.md`).
- **The pages before the preface are dropped, with a record**: a page
  kind and a removal reason `front_matter`, and the config key
  `front_matter_end` to correct the rule (`docs/specs/front-matter.md`).
  That the record is a reason of its own, and the rule for books
  without a preface, were decided while writing.
- **The running head of a section of two pages** is removed (structure
  spec §3, "The head of a short section").
- **Small print is re-read** with Tesseract where it reads better than
  the text layer, region by region, every replaced word recorded
  (`docs/specs/reocr.md`). That layout does it, the rule that chooses,
  and footnotes only when the config asks were decided while writing.
- **The plan owner-books**: its scope (running heads and page numbers,
  flush-left and tall headings, notes grouped per chapter, epigraphs, a
  paragraph ended at a page break, spaced punctuation, three fixes from
  the public-domain books); an **epigraph** is a block kind of its own
  with its source as a separate part; the dash before a source is look,
  removed with a record and written back by markdown; a verse epigraph keeps
  its line breaks; a spaced "?", ";", ":" or "!" is attached to its
  word in an English book, with a record, and preceded by a no-break
  space in a French one, and left alone after a dash or a quotation
  mark (`docs/specs/structure.md` §22 and §23). The source and a note
  group's heading are strings on the block and the note, the group
  heading is not in the table of contents, and markdown writes the
  dash as text, not the style sheet (§27 of the same spec, settled by
  the plan's orchestrator the same day).

On 18 November 2026, taken for the owner, who asked the work to go on
without waiting (`docs/specs/structure.md` §29 to §33 and
`docs/specs/figures.md`; the last four by the orchestrator of the plan
lists-figures):

- **A list item is a block kind of its own**, `list_item`, its marker
  apart from its text in `label`; markdown writes an unordered list for
  dashes and bullets and an ordered one for numbers and letters.
- **An entry of a printed contents is a block kind of its own**,
  `contents_entry`: its number in `label`, as a heading's, its title,
  its depth in `level`, as an index entry's, and its printed page
  number, kept and not shown in the EPUB. markdown writes the contents
  as a list, an entry per line, each linked to its chapter's heading
  when its title matches one, OCR errors allowed.
- **A list shows the reader's own markers**: a dash list is a bullet
  list, an ordered list shows Pandoc's numbers ("i." for a printed
  "(i)"), and the printed marker is kept in `label`, not written
  (`docs/specs/structure.md` §33, open point 1).
- **The title of a printed contents is a level-1 heading**, so the
  EPUB's table of contents opens the printed one (§33, open point 2).
- **A figure inside a text page without a caption is kept**, as an
  image, when it is large enough to be found: 11 of Kadesh's
  quotations in hieroglyphs or Arabic become images
  (`docs/specs/figures.md` §11, open point 1).
- **The four format changes of figures are accepted**, with an explicit
  `Figure.kind` rather than a figure's kind read from its box
  (`docs/specs/figures.md` §11, open point 2).
- **An inkless page is a page kind of its own**, `inkless`, and its
  words removals with the reason `inkless_page`, which takes
  `pages.json` to version 4; books run before the change are run again
  from analyze (`docs/specs/plates.md` §2b; decided by the plan
  stray-text, `docs/plans/stray-text.md`).

On 19 November 2026 the owner asked for `ocr = "redo"` on Kadesh, for
Stubbs' letter fragments to go, and for Mariéjol to leave the tests and
the evaluation, and said to go on without waiting; these were decided
for the owner by the plan ocr-redo (`docs/plans/ocr-redo.md`):

- **Under `redo` the text layer still decides what a page is**, and a
  plate keeps its layer (section 7b).
- **A note reference Tesseract lost is taken from the layer** where the
  layer's word under it holds one (`docs/specs/extract.md` §9).
- **A line of low Tesseract confidence is never a heading**
  (`docs/specs/structure.md` §34).
- **Stubbs' letter fragments are removals of their own**,
  `letter_fragment`, in a book where they are common
  (`docs/specs/structure.md` §35).

On 19 November 2026, after reading Kadesh, the owner decided:

- **A footnote with no linked reference goes to the end of its
  chapter**, under a heading "Notes", in the order printed, with its
  marker; endnotes and linked footnotes stay as they were
  (`docs/specs/structure.md` §36).

## 18. Not in this document

- How each stage does its work: the page score threshold, column
  detection, running heads, paragraphs, notes, OCR settings, plate
  recognition and figure cutting. That is in the stage specs.
- The `correct` stage's rules, in `docs/specs/correct.md`; the `index`
  stage and `edits-from`, specified later, and section 8 gains their
  formats then.
- The style sheet and cover of the EPUB, in the epub stage's spec.
