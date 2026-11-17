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
`body_measures.py`.

Decisions marked "owner", with a date from 14 to 16 November 2026,
were taken by the owner in chat. The others were taken while writing,
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
                       (plate-<page index, 4 digits>.png), and cover.png
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
`blocks.json` and lost a word with no error. Edits are never overwritten by a stage. Folders of the owner's
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
| `plate_pages` | list of page indices, `[]` | pages analyze makes plates whatever its rule finds, for a plate the rule misses (Kadesh's faint relief on page 23); a page in `exclude_pages` is never a plate, so a page in both lists is accepted and excluded: `exclude_pages` wins (`docs/specs/plates.md` §2) |
| `contents_pages` | list of page indices, `[]` | the pages of the book's printed table of contents: structure makes no heading on them, so that the EPUB's table of contents does not list each chapter twice; their lines stay paragraphs (owner, 15 November 2026). Without it, the contents' lines that pass the heading rule become headings, and the EPUB lists those chapters twice (Domesday's three essays). analyze checks its page indices as it checks those of the other keys |

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
  block. Prose lines are always joined.

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
has a `format_version` int: 2 for `blocks.json`, 1 for the others.
`blocks.json` went to 2 with the second plan of structure (16 November
2026), which added `Note.kind`, `Block.label`, the block kinds `verse`
and `chapter_summary` and the removal reason `guide_words`; reading a
file of version 1 is the error below, and the owner reruns structure. Each has one pair of functions
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
  `exclude_regions: tuple[Box, ...]`.
- `PageKind`: `blank`, `text`, `plate` (mostly a picture), `excluded`.
  analyze recognises a plate from a small render of the page, with a
  text layer or without one (`docs/specs/plates.md`).
- `TextSource`: `text_layer`, `ocr`, `none` (blank and excluded pages,
  and plates without a text layer).
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
  now figures are cut from plate pages only, one per plate, and its box
  is the whole page; figures inside text pages are not detected yet. A
  plate page with a text layer also has the words of that layer, which
  structure sorts into its caption and stray words.
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

- `Block`: `id`, `kind: BlockKind`, `level: int | None` (a heading's
  level, 1 or 2; an index entry's depth, 1 for an entry and 2 for a
  sub-entry printed inside it, more if a book prints deeper ones, so that
  the EPUB can indent it as printed (owner, 16 November 2026); `None` for
  every other kind: reading a blocks.json where an index entry has no
  depth from 1, or a block that is neither a heading nor an index entry
  has a level, is an error that names the file and the block. The format stays at
  version 2: a file written before the depth has index entries without
  one, and the error says to run structure again), `label: str | None` (headings: the chapter label as printed,
  "CHAPTER III.", "V"; `None` for a heading without one and for every
  other kind: reading a blocks.json where a block that is not a heading
  has a label is an error that names the file and the block),
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
  - `figure`: a picture, with its caption as the block's text (empty when
    it has none) and its image in `figure`;
  - `margin_note`: a short heading printed beside the text (section 17);
  - `index_entry`: one entry of the book's printed index, or one
    sub-entry of it, its depth in `level` (section 11).
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
  paragraphs, and margin notes: below), `origin`, `referenced: bool`. A
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
  joined word. `hyphen_join_guessed`: the same, when neither holds it
  (structure §5), recorded so that the guessed joins can be reviewed.
  `hyphen_kept`: ("Anglo-", "Saxon") becomes ("Anglo-Saxon",), a
  compound the book prints with its hyphen. `note_marker`: ("Greece,1",)
  becomes ("Greece,", "1"), the "1" going to the note reference. A spec
  adds a reason when it needs one.
- `PageNumber`: `page_index`, `text`, `position: head | foot`.
  `page_numbers: tuple[PageNumber, ...]`, taken from the removals; the
  index stage uses it (section 11).

**Removal**, in words.json (excluded pages and regions) and blocks.json
(the rest): `page_index`, `box`, `text`,
`reason: RemovalReason`: `excluded_page`, `excluded_region`,
`running_head`, `page_number`, `signature_mark`, `plate_text`,
`stray_mark` (a line with no letter or digit above a running head, a
speck of the scan), `guide_words` (the first letters of the first and
last entries that Stubbs prints under the running head of an index
page, "BUR CON"). A stage spec adds a
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
7b, which decides each page's `text_source`. A plate is recognised from
a render of each page at 36 dpi, as a large area of ink that no word
covers on a page of few known words, or, on a page without a text
layer, as a large area of faint ink; such a page does not stop the run
(`docs/specs/plates.md`).

**extract** gives every page its words. Text-layer pages are read with
pdfplumber, one document per worker thread. OCR pages are rendered at 300
dpi by `pdfium.py` and read by Tesseract in parallel; their pixel boxes are
turned into points. A plate page is rendered whole at 300 dpi into
`images/`; its text layer, when it has one, is read as a text page's
is, so that structure can keep the caption and remove the rest. The
`cover_page` of the config is rendered whole, as `images/cover.png`,
and is never a plate.

**layout** groups each page's words into regions and lines, and orders
them for reading: a column, then the next; the margin beside the body,
and the notes Stubbs cuts into the body column; the footnote columns at
the foot. It copies the page's figures through.

**structure** turns regions and lines into blocks and notes. It first
reads the whole book to find what repeats: running heads, page numbers,
signature marks, the line heights of body and notes. Then, per page, it
removes those, decides what each region is, finds headings, chapter
summaries and verse, groups lines into paragraphs, keeps a plate's
caption and removes its stray words, and joins hyphenated words
(dropping the hyphen where the word list or the book's own words allow
it, keeping it in a compound the book prints, and dropping it as a
recorded guess where neither decides; `docs/specs/structure.md` §5).
Last, over the whole book, it joins paragraphs that run over a page
break; cuts the notes, joins those that run over a page break, finds
the endnotes, and matches each note reference to its note, splitting it
off the word it is glued to; makes the index's entries; finds quotes,
after the notes, so that a note left in the body is not taken for one;
and places each margin note just before the paragraph whose line it
sits beside (`docs/specs/structure.md` §2 gives the order).

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
footnotes with `referenced` false as ordinary blocks where they were
printed, the marker first; endnotes, referenced or not, where they were
printed, as one list in the book's order, each note a div with its id,
and each reference to one a link to it marked as a note reference
(`epub:type="noteref"`), which a Kindle can show as a pop-up (Pandoc
3.14 keeps an `epub:type` attribute on a link and a div, and points the
link into the right chapter file, checked on 16 November 2026; the
pop-up itself was not tried on a Kindle); a `verse` block with a hard
line break at each line feed; a margin note inside a note within that
note; figures as images with their caption. How each kind is written and
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
| `pdfium.py` | the one thread that calls PDFium, which is not thread-safe. It opens and closes the PDF itself for each request: `page_count(pdf)`, `page_size(pdf, page_index)`, `render(pdf, page_index, dpi) -> RenderedPage`; and `POINTS_PER_INCH` (72), which turns a DPI into pixels per point |
| `parallel.py` | `DEFAULT_WORKERS` (6); `map_pages(function, items, workers)`, which returns the results in input order; and `map_pages_with_source(open_source, function, items, workers)`, which opens one source per worker thread (a pdfplumber document) and passes it to every call on that thread. A source is closed when its thread ends, also when `function` raises; the exception propagates |
| `text_layer.py` | `open_pdf(pdf) -> pdfplumber.PDF`: the one way galley opens a pdfplumber document. It opens under a lock, because pdfminer.six (20260107) interns PDF keywords in a shared table without one and can fail, about 1 run in 100 with several workers, when two threads open documents at once; reading pages stays parallel. A PDF pdfplumber cannot read becomes a `PdfError` naming the file |
| `wordlist.py` | `is_known_word(word, lower_case_words)`, whether a word counts as known on a plate (`docs/specs/plates.md` §2); `lower_case_word_list(language, cache_dir)`, the word list in lower case, made once per language and list folder, which structure and analyze take; `word_list(language, cache_dir) -> frozenset[str]`, with the dictionary's case, extracted from Tesseract's language data with its `combine_tessdata` and `dawg2wordlist` tools, as the owner's ocr_lab does, and cached under `~/.cache/galley/`; `is_cached(language, cache_dir)`; `WORD_LIST_TOOLS` and `missing_tools(language, cache_dir)`, the tools not on the PATH when the list is not cached, which the command checks before analyze (plates, `docs/specs/plates.md`) and structure |
| `fidelity.py` | the fidelity check, section 13 |
| `body_measures.py` | the rules that measure a book's body text, which layout and structure both use, so that they are written once: `group_rows(words)`, the rows of a page's words (layout §1, "Row"); `edge_counts(edges)`, each edge rounded to the point with the number of edges within 2 pt of it, and `commonest(edges)`, the value with the most (layout §1); `median_word_height(words)`; `measured_pages(rows_by_page)`, the pages of at least 15 rows, or of 3 when none has 15, and `measured_page_positions(rows_by_page)`, their positions in `rows_by_page`; and `body_measures(rows_by_page) -> BodyMeasures \| None`, the body word height and body line pitch (layout §3), `None` when no page has 3 rows. It takes rows, not words, so that a stage groups each page once and uses the rows for its own work too |
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
  Structure links no candidate without this shape (its bracketed form
  allows two letters read as digits, "(li)" for 11, which then stays in
  its word). The span need not read as its note's `marker`: the OCR
  reads the two sides of a superscript differently (section 8; owner,
  15 November 2026). These checks run at the structure boundary, and at
  the markdown boundary on the blocks with the edits applied.
  Before, the check asked for the marker exactly, which left 1,202 of
  Domesday's 1,440 matched references linkable, 182 of Mariéjol's 676
  and none of Gierke's 205 (`docs/specs/structure.md` §11).
- It compares multisets over the whole book, not page by page, because a
  paragraph or a hyphen join can run over a page break and its words then
  belong to two pages. Order is not part of the check, because columns,
  margins and notes move between stages; order within a block is checked
  by structure's tests.
- The boundaries: layout, words.json against lines.json; structure,
  lines.json against blocks.json (the text of every body and note block,
  with a note's `marker` and a heading's `label` counted as words of
  it); markdown, blocks.json
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
  the number of references to footnotes. Any other link is an element
  galley's Markdown does not make, and an error. An endnote stays where it was printed, so its
  `marker` is written there and counted, referenced or not (section 9).
  A heading's `label` is written in `book.md`, in the form the markdown
  spec gives, and counted as words of its block.
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

## 18. Not in this document

- How each stage does its work: the page score threshold, column
  detection, running heads, paragraphs, notes, OCR settings, plate
  recognition and figure cutting. That is in the stage specs.
- The `correct` stage, with its log and how it calls the vision model; the
  `index` stage; and `edits-from`. Each is specified later, and section 8
  gains their formats then.
- The style sheet and cover of the EPUB, in the epub stage's spec.
