# The walking skeleton

The walking skeleton is the first build of galley: every stage of the
pipeline in its simplest form, run end to end on the two committed
excerpts, the Kadesh excerpt (`tests/fixtures/pdf/kadesh_8-17.pdf`) and
the Gierke excerpt (`tests/fixtures/pdf/gierke_86-93_270-271.pdf`), so
that each gives an EPUB and the fidelity check passes at every stage
boundary. Its purpose is to try the file formats between stages on real
books before several sessions build the real stages on them. The EPUB it
makes is poor on purpose: one paragraph per page, running heads, page
numbers and footnotes left in the text, but every word of the text layer
in it. Each later spec, one per stage, replaces the simplest behaviour
given here with the real one.

Dated 14 November 2026. It builds on `docs/architecture.md` and
`docs/glossary.md`, and uses their names; a section number such as "§8"
refers to the architecture. No code exists yet besides
`src/galley/__init__.py`, which imports gilguard, and the empty stage
subpackages. Every number in it was measured on that date (section 11
says how to reproduce them).

The plan made from this spec has four work packages, approved by the
owner on 14 November 2026. The sections below follow them:

| work package | modules | section |
|---|---|---|
| 1, data formats | `errors.py`, `model.py`, `config.py`, `book_folder.py` | 3 |
| 2a, PDFium and threads | `pdfium.py`, `parallel.py` | 4 |
| 2b, fidelity | `fidelity.py` | 5 |
| 3a, analyze and extract | `analyze/`, `extract/` | 6 |
| 3b, layout and structure | `layout/`, `structure/` | 7 |
| 3c, markdown and epub | `markdown/`, `epub/` | 8 |
| 4, end to end | `cli.py`, `[project.scripts]`, the excerpt tests of section 9 | 9 |

`wordlist.py`, the correct stage, `galley2epub edits-from` and the index
stage are not in the skeleton (section 13).

## 1. What the skeleton does, stage by stage

| stage | the skeleton's rule | what the real spec adds |
|---|---|---|
| analyze | page size from pdfplumber; a page with text-layer words is `text`; a page without, unless the config excludes it, stops the run; the config's excluded pages and regions applied | the layer's score, blank pages, plates, OCR decisions |
| extract | pdfplumber's `extract_words()` on `text` pages; excluded words become removals; the cover page rendered | OCR with Tesseract, figures cut from plates |
| layout | one region per page; lines grouped by the vertical centre of each word (section 7) | columns, margins, footnote columns, reading order |
| structure | one paragraph block per region, its words joined by single spaces; nothing removed, no notes, no hyphen joins | running heads, page numbers, headings, notes, joins |
| markdown | a metadata header and one fenced div per block, every ASCII punctuation character escaped; stops if any edit exists | headings, footnotes, margin notes, figures, edits, lighter escaping |
| epub | Pandoc with an empty style sheet and the cover | the style sheet, epubcheck-clean details |

The fidelity check (§13) runs at the three boundaries, layout, structure
and markdown, inside the `run` of each of those stages (section 5).

## 2. The excerpts as the skeleton reads them

Both excerpts are scans whose every page carries a picture of the page
and an invisible text layer in `GlyphLessFont`, made by an OCR program.
Each has 10 pages, indexed 0 to 9. Counts are of pdfplumber 0.11.10's
`page.extract_words()` with its default options, on 14 November 2026:

| page index | Kadesh words | Kadesh lines | Gierke words | Gierke lines |
|---|---|---|---|---|
| 0 | 584 | 41 | 192 | 24 |
| 1 | 641 | 45 | 311 | 37 |
| 2 | 671 | 45 | 297 | 37 |
| 3 | 904 | 52 | 325 | 36 |
| 4 | 822 | 51 | 319 | 36 |
| 5 | 764 | 50 | 309 | 36 |
| 6 | 909 | 52 | 292 | 34 |
| 7 | 822 | 49 | 273 | 30 |
| 8 | 4 | 2 | 547 | 43 |
| 9 | 0 | 0 | 541 | 53 |
| total | 6,121 | 387 | 3,406 | 366 |

"Lines" are the lines of the skeleton's layout rule (section 7).

What the skeleton meets on these pages, and a reader of the formats would
not expect:

- **Kadesh page 9 has no text layer at all**: 0 characters. It is a blank
  page of the book. The skeleton has no OCR, so the excerpt's config
  excludes it (section 6 says why).
- **Kadesh page 8 is a plate** (a full-page drawing of the battle reliefs)
  whose layer holds 4 stray words, `,`, `'`, `..` and `^U;L`. The skeleton
  does not detect plates, so these 4 words reach the EPUB as a paragraph.
  The real structure stage removes them as `plate_text` (§8).
- **Kadesh page 0 has two columns of footnotes**, and the skeleton's lines
  run across both: the line at top 584.8 pt reads `•Pa per read before the
  International Congress of Ori- 'There is, however, much material for
  studying the`, the end of one note and the start of another. The page
  number `81` at the foot (box 241.68, 622.509, 249.07648, 629.509) falls
  in the line `fighting by groups of four (CHAMP., Man., 220-220 6i» =
  ROB., 81 against the interior …`. Every word is kept, in a bad order,
  which is all the skeleton asks.
- **Gierke prints headings in the margin**, and the skeleton's lines take
  them in: on page 1, "Diversity of materials." in the left margin comes
  out as `Diversity In tnjs manner elements that derived from the`, then
  `of mate- .`, then `rials. most diverse sources were fused …`.
- **Page sizes differ between pdfplumber and pypdfium2.** pdfplumber gives
  Gierke's pages as 376.128 × 621.504 pt (the media box); pypdfium2's
  `get_size()` gives 376.1000061035156 × 621.5 (the crop box, in 32-bit
  floats). On Kadesh, 508.32 × 728.16 against 508.32000732421875 ×
  728.1599731445312. Word boxes come from pdfplumber, so `pages.json`
  takes its sizes from pdfplumber too.
- **The words of one printed row do not share a `top`.** A line cannot
  be "the words with the same `top`": with exact equality, Kadesh page 3
  gives 524 lines instead of the 52 of the skeleton's rule.
- **Pandoc changes words that are not escaped.** Written as plain text in
  Markdown and read back, Kadesh loses `*Oampagne`, `me*ure`, `admits*`
  and other words with an asterisk (taken as emphasis) and words with a
  backslash; Gierke loses `jj^J^jjJJ` (a caret starts a superscript).
  With every ASCII punctuation character escaped, both excerpts come back
  word for word (6,121 and 3,406 words, none missing, none extra).

## 3. Data formats: `errors.py`, `model.py`, `config.py`, `book_folder.py` (work package 1)

These four modules are written first, and everything else is built on
them. They are complete, not simplified: the formats of §8 in full,
including the fields the skeleton leaves empty (notes, word changes, page
numbers), because the purpose of the skeleton is to try them.

### errors.py

The exception classes of §12, each a subclass of `GalleyError`, with no
behaviour of their own except `FidelityError`, which keeps what it found
so a test can assert on it.

```python
class GalleyError(Exception): ...
class ConfigError(GalleyError): ...
class InputFileError(GalleyError): ...
class PdfError(GalleyError): ...
class ExternalProgramError(GalleyError): ...
class EditError(GalleyError): ...

class FidelityError(GalleyError):
    def __init__(
        self,
        boundary: str,
        missing: frozendict[str, int],
        invented: frozendict[str, int],
        detail: str,
    ) -> None: ...
    # boundary: "layout", "structure" or "markdown"; missing and invented
    # map a word to how many times it is missing from, or extra in, the
    # output; detail is the rest of the message (pages, note counts).
    # The attributes of the same names are set; the message lists them.
```

Tests: each subclass is a `GalleyError`; a `FidelityError` built with one
missing and one invented word has them as attributes and names both, with
their counts, in `str(error)`.

### model.py

The formats of §8, written once. Every dataclass and enum of §8 is
here, with the field names, types and order §8 gives: `Box`, `PageKind`,
`TextSource`, `PageInfo`, `PagesFile`, `Word`, `Figure`, `PageWords`,
`WordsFile`, `Line`, `Region`, `PageLayout`, `LinesFile`, `BlockKind`,
`Emphasis`, `Span`, `Origin`, `Block`, `Note`, `ChangeReason`,
`WordChange`, `PageNumberPosition` (the `head | foot` of `PageNumber`),
`PageNumber`, `RemovalReason`, `Removal`, `BlocksFile`, `Edit` and
`RenderedPage`. They are not copied here.

What §8 leaves to this spec:

- Each of the four top-level dataclasses, `PagesFile`, `WordsFile`,
  `LinesFile` and `BlocksFile`, has `format_version: int` and
  `source_pdf_sha256: str` as its first two fields, keyword-only, with
  `format_version` defaulting to the module constant of its file:
  `PAGES_FORMAT_VERSION`, `WORDS_FORMAT_VERSION`, `LINES_FORMAT_VERSION`,
  `BLOCKS_FORMAT_VERSION`, each 1. One constant per file, so that one
  format can change without the others.
- `Box(x0: float, top: float, x1: float, bottom: float)` is a frozen
  dataclass of four floats, written in JSON as a list of four numbers.
- `Figure.image` is a `str`, the path relative to the book folder with
  `/` as separator, so that a `words.json` is the same on every system.
- `Removal(page_index, box, text, reason)` and the other dataclasses use
  `kw_only=True` when they have more than three fields, as the coding
  skill says.

The write and read functions, one pair per file:

```python
def write_pages(path: Path, pages: PagesFile) -> None: ...
def read_pages(path: Path) -> PagesFile: ...
def write_words(path: Path, words: WordsFile) -> None: ...
def read_words(path: Path) -> WordsFile: ...
def write_lines(path: Path, lines: LinesFile) -> None: ...
def read_lines(path: Path) -> LinesFile: ...
def write_blocks(path: Path, blocks: BlocksFile) -> None: ...
def read_blocks(path: Path) -> BlocksFile: ...
def write_edits(path: Path, edits: tuple[Edit, ...]) -> None: ...
def read_edits(path: Path) -> tuple[Edit, ...]: ...
```

Writing: one JSON object, UTF-8, `ensure_ascii=False`, `indent=1`, keys
in the order of the dataclass fields, a newline at the end. A tuple is a
list, an enum its value, `None` is `null`, a float Python's shortest
repr (what `json.dumps` writes). The same value gives the same bytes,
whatever made it. The edits file is JSON Lines: one object per edit, with
no indent, one per line.

Reading checks everything and stops at the first problem with an
`InputFileError` (an `EditError` for edits) whose message names the file
and, for a field, its path in the JSON, `pages[3].words[12].box`:

- the file is missing: the message says which stage writes it ("run
  `galley2epub extract`");
- the JSON is not valid (a truncated file): the line and column;
- `format_version` is missing, not an int, or not the current one: both
  versions are named;
- a field is missing, or a field is there that the dataclass does not
  have;
- a value has the wrong JSON type, an enum value is not a member, a `Box`
  is not four numbers. A JSON integer is accepted where a float is
  expected and becomes a float, so `81` and `81.0` read the same; `true`
  is not accepted as a number.

The reader rebuilds the tuples and enums, so `read_x(write_x(value))`
gives a value equal to `value`.

Three more functions, which several stages and `fidelity.py` call:

```python
def pdf_sha256(pdf: Path) -> str: ...
    # The SHA-256 of the file's bytes, 64 lowercase hex digits.

def check_source_pdf(path: Path, file_pdf_sha256: str, pdf_sha256: str) -> None: ...
    # Raises InputFileError when a file read from `path` was made from
    # another PDF than the config's; the message names the file and the
    # stage to rerun (pages.json: analyze, words.json: extract, ...).

def block_text(block: Block) -> str: ...
    # The text of a block (§7): the concatenation of its spans' text.

def block_sha256(block: Block) -> str: ...
    # The first 12 hex digits of the SHA-256 of block_text(block), UTF-8:
    # the checksum an Edit carries (§8).
```

The tests, all unit tests with literal values written in the test:

- for each of the four JSON files, a value that fills every field,
  including a `Note` with two blocks, a `WordChange`, a `PageNumber` and a
  `Removal` in `blocks.json`, written and read back equal; written twice,
  the same bytes;
- the JSON of a `Box` is a list of four numbers, of an enum its string;
- for each reader: a truncated file (the first half of a valid one), a
  `format_version` of 2, a missing field (`box` deleted from one word), an
  unknown field, an enum value that is not a member (`"kind": "cover"`),
  a `Box` of three numbers, a missing file, each an `InputFileError` whose
  message holds the file name and the field path;
- `read_edits` on a file with a line that is not JSON, and on a line that
  lacks `old`: an `EditError` that names the file and the line number;
- `check_source_pdf` with two different hashes raises and names the stage;
- `block_sha256` of a block with two spans, against a literal computed by
  hand with `hashlib`.

### config.py

Reads `book.toml` (§6) into a frozen `BookConfig`. The skeleton reads
every key of §6, and honours them as sections 6 and 9 say; `correct =
true` is read but `galley2epub run` refuses it (section 9).

```python
class Language(StrEnum):
    EN = "en"; ES = "es"; FR = "fr"; DE = "de"; IT = "it"

class OcrMode(StrEnum):
    AUTO = "auto"; NEVER = "never"; ALWAYS = "always"

@dataclass(frozen=True, slots=True)
class ExcludedRegion:
    page_index: int
    box: Box

@dataclass(frozen=True, slots=True, kw_only=True)
class BookConfig:
    pdf: Path                                  # absolute, resolved
    title: str
    authors: tuple[str, ...]
    language: Language
    ocr: OcrMode = OcrMode.AUTO
    correct: bool = False
    exclude_pages: tuple[int, ...] = ()
    exclude_regions: tuple[ExcludedRegion, ...] = ()
    cover_page: int | None = None

def read_config(path: Path) -> BookConfig: ...
def tesseract_language(language: Language) -> str: ...
    # en -> eng, es -> spa, fr -> fra, de -> deu, it -> ita
```

In TOML an excluded region is `{page = 0, box = [240, 620, 252, 632]}`;
the key `page` becomes the field `page_index`. `pdf` is resolved against
the folder of `book.toml` when it is relative and kept when it is
absolute; tests write absolute paths to the excerpts.

`read_config` raises `ConfigError`, naming the file and the key, when: the
file is missing or is not valid TOML; a key is unknown, at the top level
or inside a region; a required key (`pdf`, `title`, `authors`,
`language`) is missing; a value has the wrong type (`authors = "Breasted"`
instead of a list); `language` or `ocr` is not one of its values; a page
index is negative; a box is not four numbers or has `x0 >= x1` or `top >=
bottom`; the PDF does not exist. A page index past the end of the book
cannot be seen here, without opening the PDF; analyze checks it
(section 6).

Tests: a config with every key at a value other than its default, read
into the literal `BookConfig` it should give; a config with only the
required keys, read with the defaults; one test for each `ConfigError`
above; `tesseract_language` for the five languages.

### book_folder.py

```python
@dataclass(frozen=True, slots=True)
class BookFolder:
    root: Path
    # properties, each a Path under root, as §5 lists them:
    # book_toml, pages_json, words_json, images_dir, cover_png
    # (images/cover.png), lines_json, blocks_json, edits_dir, book_md,
    # book_epub
```

One test: every property is the path §5 gives, under `root`.

## 4. PDFium and threads: `pdfium.py`, `parallel.py` (work package 2a)

### pdfium.py

Every call into pypdfium2 happens in one thread, the same for the life of
the process, because PDFium is not thread-safe even across two documents.
Each public function sends its request to that thread and waits for the
answer, so it can be called from any thread; calls from several threads
run one after the other. Each request opens the PDF, does its work and
closes every page, bitmap and document it opened before it returns.

```python
@dataclass(frozen=True, slots=True)
class PageSize:
    width_pt: float
    height_pt: float

def page_count(pdf: Path) -> int: ...
def page_size(pdf: Path, page_index: int) -> PageSize: ...
def render(pdf: Path, page_index: int, dpi: int) -> RenderedPage: ...
```

`render` gives 8-bit grayscale pixels, row by row with no padding: when
PDFium's bitmap has a stride larger than its width, the padding is
dropped. `width_px` and `height_px` are PDFium's bitmap size at `scale =
dpi / 72`. A file that is not a PDF, or a page index outside the
document, is a `PdfError` that names the file and, for the page, the
index and the page count. `page_size` gives PDFium's numbers, which differ
from pdfplumber's (section 2); the skeleton's stages do not use it.

In the skeleton only extract calls `render`, for the cover.

Tests, each marked `thread_unsafe`: `page_count` of both excerpts is 10;
`page_size` of Kadesh page 0 is 508.32000732421875 × 728.1599731445312;
`render` of Gierke page 0 at 300 dpi is 1568 × 2590 pixels, at 72 dpi 377
× 622, with `len(pixels) == width_px * height_px` (377 is not a multiple
of 4, so a stride with padding would show here); the same render called
from 6 threads at once gives the same bytes 6 times as one call alone; a
page index of 10 and a text file given as PDF each raise `PdfError`.

### parallel.py

```python
DEFAULT_WORKERS: Final[int]   # min(6, os.process_cpu_count() or 1), with
                              # the measurement of the coding skill in its comment

def map_pages[T, R](
    function: Callable[[T], R],
    items: Sequence[T],
    workers: int = DEFAULT_WORKERS,
) -> tuple[R, ...]: ...

def map_pages_with_source[S, T, R](
    open_source: Callable[[], AbstractContextManager[S]],
    function: Callable[[S, T], R],
    items: Sequence[T],
    workers: int = DEFAULT_WORKERS,
) -> tuple[R, ...]: ...
```

`map_pages` runs `function` on every item in a thread pool of `workers`
threads and returns the results in the order of `items`.
`map_pages_with_source` does the same, but each worker thread first opens
one source with `open_source()` (a pdfplumber document), passes it to
`function` with each item it takes, and closes it when no item is left.
The second function is not in §12; it is there because opening a
pdfplumber document per page costs more than once per thread: analyze
and extract together on the Kadesh excerpt took 1.36 s with one document
per page against 0.91 s with one per thread (1 worker), and 0.67 s
against 0.55 s with 6 workers. Opening the whole Gierke book takes 27 ms,
which would be paid on each of its 290 pages.

When `function` raises, the exception of the first failing item in input
order, among those that ran, is raised in the calling thread; items not
yet started may not run. `workers` below 1 is a `ValueError`. With more
workers than items, the extra workers do nothing.

Tests: results come back in input order when later items finish first
(the function sleeps less for later items); 1, 3 and 8 workers give the
same tuple on 20 items; an exception raised for item 5 reaches the
caller; with `map_pages_with_source`, a source counts how often it is
opened and closed, and with 3 workers on 20 items it is opened at most 3
times and closed as often as opened; `workers=0` raises.

## 5. The fidelity check: `fidelity.py` (work package 2b)

The check of §13, complete, not simplified: it handles removals, word
changes, notes and note references although the skeleton's stages make
none, because the real stages will, and its unit tests can build those
values by hand.

```python
class Boundary(StrEnum):
    LAYOUT = "layout"; STRUCTURE = "structure"; MARKDOWN = "markdown"

@dataclass(frozen=True, slots=True)
class MarkdownWord:
    text: str
    block_id: str | None     # the id of the innermost div or heading it is in

@dataclass(frozen=True, slots=True)
class MarkdownWords:
    words: tuple[MarkdownWord, ...]
    note_count: int          # Pandoc's Note elements

def read_markdown(markdown: str) -> MarkdownWords: ...

@overload
def check_stage(stage: Literal[Boundary.LAYOUT], before: WordsFile, after: LinesFile) -> None: ...
@overload
def check_stage(stage: Literal[Boundary.STRUCTURE], before: LinesFile, after: BlocksFile) -> None: ...
@overload
def check_stage(stage: Literal[Boundary.MARKDOWN], before: BlocksFile, after: MarkdownWords) -> None: ...
```

`check_stage` is pure; it raises `FidelityError` or returns. For the
markdown boundary, `before` is the `BlocksFile` with the edits already
applied, which in the skeleton is the file as structure wrote it
(section 8).

**The words of each side.** A text is split on white space
(`str.split()`), nothing normalised.

- `WordsFile`: the `text` of every word of every page. Its removals are
  extract's, which no boundary checks.
- `LinesFile`: the words of every line of every region.
- `BlocksFile`, at the structure boundary: for each block, of the body and
  of every note, the text of its spans with each note reference span
  replaced by a space, split; plus the `text` of each note reference span
  as a word of its own; plus each note's `marker` as a word. A note
  reference is taken apart from its neighbours because the block's text
  joins it to the word before it: spans `"…Greece,"` and `"1"` concatenate
  to `Greece,1`, while the word change made it `Greece,` and `1`. Then the
  removals of `blocks.json` are added to this side, and each word change
  is undone: its `after` words are taken out and its `before` words put
  in.
- `BlocksFile`, at the markdown boundary: the same, but without the
  note reference spans and without the `marker` of a note whose
  `referenced` is true, because Pandoc numbers notes itself (§17); the
  marker of an unreferenced note is printed as text and counted. No
  removals or word changes: markdown makes none.
- `MarkdownWords`: the `text` of each word.

The check compares the two sides as multisets. A difference is a
`FidelityError` with the words missing from the output and the words it
invented, each with its count, and in `detail` the pages where each came
from: page indices for words and lines, the `origin` pages of the block
for blocks, the block id for Markdown. At the markdown boundary it also
compares the number of note references in the blocks with `note_count`,
and a difference is a `FidelityError` with that in `detail`.

**Reading the Markdown.** `read_markdown` runs `pandoc --from
markdown-smart --to json --fail-if-warnings`, with the Markdown on
standard input, a timeout of 60 s and `check=True`; a missing `pandoc`,
a non-zero exit or a timeout is an `ExternalProgramError` with Pandoc's
standard error. It walks the `blocks` of Pandoc's JSON, not its `meta`,
so the title and authors of the header are not words of the book. It
joins the text of adjacent `Str` elements and starts a new word at
`Space`, `SoftBreak`, `LineBreak`, and at the start and end of every
block element and of every `Note`. That last rule matters: without it the
last word of one paragraph and the first of the next come back glued,
`Egypt.THE` on Kadesh, and the content of a footnote glues to the word
its reference follows. `Emph`, `Strong` and `Span` do not separate words,
so a word half in italics stays one word.

Tests, unit tests with literal values:

- each boundary with equal sides passes;
- a word lost between words and lines, and one invented, give a
  `FidelityError` that names both with their counts and their pages;
- the same word twice in the input and once in the output is a
  difference (multisets, not sets);
- at the structure boundary: a removal (`running_head`) makes the
  missing words pass; a hyphen join `("repli-", "cate") → ("replicate",)`
  passes; the same join without its word change fails; a note reference
  span `"1"` after `"…Greece,"` with the word change `("Greece,1",) →
  ("Greece,", "1")` passes; a note's marker counts as a word;
- at the markdown boundary: a referenced note's marker and the reference
  span are not counted, an unreferenced note's marker is; two references
  against one Pandoc note is a difference;
- `read_markdown`, marked `pandoc`: two paragraphs `a b` and `c` give the
  words `a`, `b`, `c`, not `bc`; a word `*x*y` written escaped as `\*x\*y`
  comes back as `*x*y`; a footnote's words are words; `note_count` of a
  text with two footnotes is 2; a div `::: {#b-p0000-001}` gives its words
  that block id; a note definition that no reference uses makes Pandoc
  warn and exit with 3, so it raises `ExternalProgramError`. A reference
  with no definition does not warn (Pandoc 3.13 keeps `[^1]` as text,
  exit 0); the word check sees it as an invented word `[^1]`.

## 6. analyze and extract (work package 3a)

### analyze

analyze measures every page with pdfplumber, in parallel, one document
per worker thread (`map_pages_with_source`): its width and height, and
how many words `extract_words()` finds. Then, per page, in this order:

1. A page in `exclude_pages` is `excluded`, `text_source` `none`.
2. A page with at least one text-layer word is `text`, `text_source`
   `text_layer`.
3. A page with no text-layer word is `blank`, `text_source` `none`.

Then, when any page is `blank`, analyze stops with a `PdfError` that
lists every such page and says: "these pages have no text layer, and the
walking skeleton has no OCR; add them to `exclude_pages` once you have
checked that they hold no text". It writes no `pages.json`. So the
skeleton never writes a `blank` page: a blank page of the book is
excluded by the config, as Kadesh page 9 is in the test of section 9.
`text_layer_score` is `None` on every page, with a layer or not: the
score needs the word list, which the skeleton does not have (**Open 3**,
below). `exclude_regions` holds the boxes of the config's regions for that
page, in the config's order. Width and height are pdfplumber's
`page.width` and `page.height` (section 2).

Rule 3 is the skeleton's answer to a page with no layer (**Open 2**,
below). Reading such a page as blank would lose its text with only a
warning, and the whole books have such a page: page index 69 of the whole
Kadesh book has a running head, about five lines of text and a captioned figure,
and no text layer. Telling a blank page from a printed one by the ink on
a render does not work either. Of the 26 pages without a layer in the two
whole books, 13 are blank; the others are 5 plates, that Kadesh page 69,
2 Internet Archive notice pages and 5 covers or black pages. At 50 dpi,
Kadesh page 69 has 0.00003 of its pixels darker than 128, within the
range of the blank pages (0 to 0.00006), and the blank Gierke page 51, of grey paper,
has 0.32 of its pixels darker than 200, more than any of the plates
(0.04 to 0.23). Telling them apart is the analyze spec's work, with OCR.

Before any page is measured, analyze raises `ConfigError` when `ocr` is
`always` ("ocr = always needs OCR, which the walking skeleton does not
have; use auto"), and when a page index of `exclude_pages`,
`exclude_regions` or `cover_page` is not below the page count, naming the
key, the index and the count. `auto` and `never` both mean the text
layer.

```python
# galley.analyze
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def classify_page(
    index: int, width_pt: float, height_pt: float, layer_word_count: int, config: BookConfig
) -> PageInfo: ...

def check_config_pages(config: BookConfig, page_count: int) -> None: ...

def require_text_layer(pages: tuple[PageInfo, ...]) -> None: ...
    # Raises the PdfError of rule 3, listing every blank page.
```

`run` deletes `pages.json` first, so that a failed run leaves no old
file behind, and writes it with `source_pdf_sha256 = pdf_sha256(config.pdf)`.
The `workers` keyword is not in §9; every stage that works in parallel
takes it, so the tests and the command can set it.

### extract

extract reads `pages.json`, checks that it was made from the config's PDF,
and gives each page its words, in parallel with one pdfplumber document
per worker thread:

- `text` page: the words of `page.extract_words()` with its default
  options, in the order pdfplumber gives them, each as `Word(text,
  Box(x0, top, x1, bottom), ocr_confidence=None)`. A word whose centre,
  `((x0 + x1) / 2, (top + bottom) / 2)`, is inside one of the page's
  `exclude_regions` (edges included) is not a word of the page but a
  `Removal` with its box, its text and the reason `excluded_region`.
- `excluded` page: no words; every word of its layer is a `Removal` with
  the reason `excluded_page`.
- `blank` page (which the skeleton's analyze never writes, but a
  `pages.json` may hold): no words, and the PDF page is not read.

Every `PageWords` has `figures=()`: the skeleton cuts no figure. The
removals are in page order, then in pdfplumber's order.

When the config has a `cover_page`, extract renders it at 300 dpi with
`pdfium.render` and saves it as an 8-bit grayscale PNG at
`images/cover.png`. On the Kadesh excerpt, page 0, this is 2118 × 3034
pixels, a 2.36 MB file, and took 140 ms to render and 100 ms to save.
extract deletes `words.json` and `images/` first.

The centre rule, rather than "the box touches the region", is decided so
that a word half inside a region the owner drew is not lost: in the test
of section 9, the region `[240, 620, 252, 632]` on Kadesh page 0 holds
the page number `81` and touches `ROB.,` (x0 223.9, x1 244.8), which
stays.

```python
# galley.extract
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def page_words(page: PageInfo, layer_words: tuple[Word, ...]) -> tuple[PageWords, tuple[Removal, ...]]: ...
```

`page_words` is the pure part: given the page and the words pdfplumber
read (empty for a blank page), it gives the page's words and removals.

### Their tests

Unit tests of `classify_page`, `check_config_pages`, `require_text_layer`
and `page_words`, with literal values: each of the three kinds;
`require_text_layer` naming both blank pages of four; `ocr = always`; an
`exclude_pages`, a region and a `cover_page` index equal to the page
count; a word inside a region, one touching it with its centre outside,
one with its centre on the edge; an excluded page with three words gives
three removals and no words.

Excerpt tests, which read the PDFs and so are in this work package:

- analyze on Kadesh with the default config raises `PdfError` naming
  page 9 and only it; with `exclude_pages = [9]`, pages 0 to 8 are
  `text`, page 9 `excluded`, every page 508.32 × 728.16 pt and
  `text_layer_score` `None`; on Gierke with the default config, 10
  `text` pages of 376.128 × 621.504 pt.
- extract on both, Kadesh with `exclude_pages = [9]` (as in every
  Kadesh test below): the word counts per page of section 2, as literals;
  Kadesh page 0 starts `THE BATTLE OF KADESH A STUDY`; Kadesh page 8 is
  exactly `,`, `'`, `..`, `^U;L`; Gierke page 9 starts `1 86 Political
  Theories of the`.
- extract on Kadesh with `exclude_regions = [{page = 0, box = [240, 620,
  252, 632]}]`: page 0 has 583 words, and the only removal is `81`, box
  (241.68, 622.509, 249.07648, 629.509), `excluded_region`. With
  `exclude_pages = [8, 9]`: page 8 has no words, and its 4 words are
  the only removals, `excluded_page`.
- analyze and extract on Kadesh with 1 worker and with 6 give byte-identical
  `pages.json` and `words.json` (10 pages, more than 6 workers). This test
  takes about 1.5 s (section 10) and is marked `thread_unsafe`, so the
  8-thread run does not repeat it.
- a `pages.json` made from the Gierke PDF, given to extract with the
  Kadesh config, raises `InputFileError` naming analyze.

## 7. layout and structure (work package 3b)

### layout

layout puts all the words of a page in one region and groups them into
lines by this rule, which needs no threshold:

1. Sort the page's words by `(top, x0)`, keeping pdfplumber's order for
   equal keys.
2. Go through them in that order. The first word starts a line and is its
   anchor. A later word joins the current line when its vertical centre,
   `(top + bottom) / 2`, lies within the anchor's `top` and `bottom`
   (edges included); otherwise it starts a new line and becomes its
   anchor.
3. Sort the words of each line by `x0`, keeping the order of step 1 for
   equal `x0`.

A line's box, and the region's, is the smallest box that holds its words.
A page with no words has no region. `figures` is copied from
`words.json`.

On the excerpts the nearest call, the distance from a word's centre to the
edge of its anchor's band, is 0.075 pt on Kadesh and 0.138 pt on Gierke,
so the counts of section 2 do not hang on rounding. A rule with a fixed
tolerance on `top` was tried and dropped: the counts kept changing with
the tolerance between 1 and 4 pt (Kadesh page 3: 114 lines at 1 pt, 63 at
3, 54 at 4), and at pdfplumber's default of 3 pt the page number `81` of
Kadesh page 0 is 3.019 pt below its row.

What the rule does with columns: a row of the page becomes one line across
every column it crosses, so Kadesh's two footnote columns are read row by
row, left note then right note, and Gierke's margin headings are read
into the body line beside them (section 2). No word is lost; the order
is wrong, and the real layout spec fixes it.

layout runs per page with `map_pages` and writes `lines.json`. Before
writing, it runs `check_stage(Boundary.LAYOUT, words, lines)`; on a
`FidelityError` it writes nothing. It deletes `lines.json` first.

```python
# galley.layout
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def group_lines(words: tuple[Word, ...]) -> tuple[Line, ...]: ...
def layout_page(page: PageWords) -> PageLayout: ...
```

### structure

structure makes one block of each region, in page order: a `paragraph`
whose id is `b-p<page index>-001`, `level` `None`, `figure` `None`, one
span whose text is the words of the region, line after line, joined by
single spaces, `emphasis` `none`, `note_ref` `None`, and one `Origin`
with the page index and the region's box. `notes`, `removals`,
`word_changes` and `page_numbers` are empty. A page with no region gives
no block, and its page index is simply absent from the ids.

structure reads `pages.json` and `lines.json` and checks that both come
from the config's PDF; it uses only `lines.json`. Before writing, it runs
`check_stage(Boundary.STRUCTURE, lines, blocks)`; on a `FidelityError`
it writes nothing. It deletes `blocks.json` first.

```python
# galley.structure
def run(folder: BookFolder, config: BookConfig) -> None: ...

def page_blocks(page: PageLayout) -> tuple[Block, ...]: ...
def make_blocks(lines: LinesFile) -> BlocksFile: ...
```

### Their tests

Unit tests, with `Word` and `PageLayout` values written in the test (they
need no output of extract, so this work package runs beside 3a):

- `group_lines`: two rows of three words, given in a shuffled order, come
  out as two lines left to right; a word whose `top` is 2 pt below the
  anchor's but whose centre is inside its band joins it; a word whose
  centre is 0.01 pt below the anchor's `bottom` starts a new line; two
  columns of two rows each give two lines, each across both columns (the
  skeleton's known bad reading, asserted so that the real layout spec
  sees it change); no words gives no lines.
- `layout_page`: the region's box holds every line; a page with no words
  has no region; figures are copied.
- layout `run` on a hand-made `words.json` of 8 pages with 1 worker and
  with 3 gives the same bytes.
- `page_blocks`: a region of two lines gives one paragraph with the words
  joined by single spaces and the id `b-p0012-001` on page 12; no region,
  no block.
- the fidelity check passes on the hand-made inputs and outputs of both
  stages, and fails on a `LinesFile` made by `layout_page` with one word
  then dropped from a line.

The excerpt tests of layout and structure need `words.json` from extract,
so they are in work package 4 (section 9).

## 8. markdown and epub (work package 3c)

### markdown

markdown writes `book.md`: a metadata header, then one fenced div per
block, in the order of `blocks.json`:

```markdown
---
title: "The Battle of Kadesh"
author:
- "J. H. Breasted"
lang: en
---

::: {#b-p0000-001}
THE BATTLE OF KADESH A STUDY IN THE EARLIEST KNOWN MILITARY STRATEGY\* JAMES …
:::

::: {#b-p0008-001}
\, \' \.\. \^U\;L
:::
```

- The header's values are written as JSON strings (`json.dumps(value,
  ensure_ascii=False)`), which YAML reads as double-quoted strings.
- The text of a block is written on one line, with a backslash before
  every ASCII punctuation character (`string.punctuation`) and nothing
  else changed. Pandoc's Markdown takes any escaped ASCII punctuation as
  itself, so no word can turn into emphasis, a list number, a superscript
  or a div fence. Measured: the round trip through Pandoc keeps all 6,121
  Kadesh and 3,406 Gierke words, and without escaping it loses words
  (section 2). The escaping makes `book.md` hard to proofread
  (`remarks\.`); the markdown spec chooses a lighter one with the same
  guarantee.
- The skeleton writes no heading, no footnote, no margin note and no
  figure: structure gives only paragraphs. It raises `GalleyError` with
  the block id if it meets any other kind, a note, or a note reference,
  rather than write it wrongly.
- A blank line separates the header and every div.

Edits: the skeleton does not apply them. When any file `edits/*.jsonl`
holds a line, markdown raises `EditError` that names the file and says
edits are applied from the markdown spec on (**Open 1**, below). An
absent `edits/` folder, or empty files, is no edits.

markdown reads `blocks.json` and checks its PDF hash, makes the Markdown,
runs `read_markdown` on it and `check_stage(Boundary.MARKDOWN, blocks,
words)`, and only then writes `book.md`. It deletes `book.md` first.

```python
# galley.markdown
def run(folder: BookFolder, config: BookConfig) -> None: ...

def escape_markdown(text: str) -> str: ...
def render_markdown(blocks: BlocksFile, config: BookConfig) -> str: ...
```

### epub

epub runs

```
pandoc <book.md> --from markdown-smart --to epub3 --output <book.epub>
       --css <style.css> --fail-if-warnings [--epub-cover-image <images/cover.png>]
```

with absolute paths, a timeout of 120 s and `check=True`. `style.css` is a
file of the package, `src/galley/epub/style.css`, empty in the skeleton,
found with `importlib.resources`; it is passed so that the path through
which the real style sheet will travel is tried now. With `--css`, Pandoc
uses that sheet instead of its own. The cover is passed when the config
has a `cover_page`; a missing `images/cover.png` then is an
`InputFileError` naming extract. A missing `pandoc`, a non-zero exit or a
timeout is an `ExternalProgramError` with Pandoc's standard error. epub
deletes `book.epub` first. It does not run epubcheck (§16).

With no heading in `book.md`, Pandoc 3.13 makes one chapter file,
`EPUB/text/ch001.xhtml`, and puts the title as its first heading; each
div keeps its id (`<div id="b-p0000-001">`). On the Kadesh excerpt with
the cover, Pandoc took 0.10 s; on Gierke without, 0.04 s.

```python
# galley.epub
def run(folder: BookFolder, config: BookConfig) -> None: ...

def pandoc_arguments(folder: BookFolder, config: BookConfig, style_sheet: Path) -> tuple[str, ...]: ...
```

### Their tests

Unit tests:

- `escape_markdown`: `*x*` gives `\*x\*`; `1. Of` gives `1\. Of`; `«` and
  `—` are unchanged; a text holding every ASCII punctuation character,
  escaped and read back with `read_markdown` (marked `pandoc`), comes back
  equal.
- `render_markdown` on a literal `BlocksFile` of two paragraphs gives a
  literal Markdown text, header included; a heading block or a note
  raises.
- `run` with a non-empty `edits/owner.jsonl` raises `EditError` naming
  the file; with an empty one it writes `book.md`.
- `pandoc_arguments` with and without a cover, against literal tuples.
- epub `run` on a hand-written `book.md` of two divs (marked `pandoc`):
  `book.epub` is a zip whose first entry is `mimetype` holding
  `application/epub+zip`, whose `EPUB/content.opf` has the title and
  `<dc:language>en</dc:language>`, and whose chapter holds both div ids.
- the same EPUB passes epubcheck (marked `epubcheck`; it skips until
  epubcheck is installed, which §16 asks for before the epub stage is
  built).

## 9. The command and the end-to-end test (work package 4)

### cli.py

```python
# galley.cli
def main(argv: Sequence[str] | None = None) -> None: ...
```

```
galley2epub run <book folder> [--workers N]
galley2epub analyze | extract | layout <book folder> [--workers N]
galley2epub structure | markdown | epub <book folder>
```

`pyproject.toml` gains `[project.scripts] galley2epub = "galley.cli:main"`.
`main` parses the arguments with argparse, sets logging to `INFO` on
standard error, reads `book.toml` from the folder with `read_config`, and
calls the stage's `run`. `run` calls analyze, extract, layout, structure,
markdown and epub in that order; the fidelity check runs inside layout,
structure and markdown, so it runs whether a stage is called alone or by
`run`. That is a step past §13, which names only `galley2epub run`: after
`edits-from`, the owner reruns markdown alone, and that is where edits
enter the text.

Before any stage runs, `main` raises `ExternalProgramError` when `pandoc`
is not found by `shutil.which` and the command is `run`, `markdown` or
`epub`, with "install it with `brew install pandoc`"; and `run` raises
`ConfigError` when the config has `correct = true`, since the skeleton
has no correct stage. The subcommands `correct` and `edits-from` do not
exist yet; argparse rejects them. Errors propagate to `main`, which logs
them and raises them again (§14).

### The end-to-end test

A session-scoped fixture builds a book folder for each excerpt under
pytest's temporary directory, writes its `book.toml`, and runs
`main(["run", folder])` once; the excerpt tests of every stage read the
files it made. Running the pipeline once per session keeps the
8-thread run (`--parallel-threads=8`) from running it 8 times.

- Kadesh: title "The Battle of Kadesh", authors ["J. H. Breasted"],
  language `en`, `cover_page = 0`, `exclude_pages = [9]` (the blank
  page with no text layer), `exclude_regions = [{page = 0, box = [240,
  620, 252, 632]}]`.
- Gierke: title "Political Theories of the Middle Age", authors ["O.
  Gierke", "F. W. Maitland"], language `en`, every other key at its
  default.

What the tests assert, as literals:

- every file of §5 but `edits/` exists, and `images/cover.png` only for
  Kadesh;
- `pages.json`, `words.json`: as section 6, with Kadesh page 9
  `excluded`, page 0 at 583 words, and one removal;
- `lines.json`: the line counts per page of section 2 (Kadesh page 0
  still has 41 lines without `81`, which shared a line); every page has
  one region but Kadesh page 9, which has none; Kadesh page 0 has the line
  `•Pa per read before the International Congress of Ori- 'There is,
  however, much material for studying the`;
- `blocks.json`: Kadesh has 9 blocks, `b-p0000-001` to `b-p0008-001`, the
  last with the text `, ' .. ^U;L`; Gierke has 10, `b-p0000-001` to
  `b-p0009-001`; each block has as many words as its page in
  `words.json`; no notes, removals, word changes or page numbers;
- `book.md`, read with `read_markdown`: 6,120 Kadesh words and 3,406
  Gierke words, the same multiset as the words of `words.json`, end to
  end, since nothing after extract removes a word; `note_count` 0;
- `book.epub`: as in section 8, with the cover image in the Kadesh one;
  epubcheck passes (marked `epubcheck`);
- `check_stage` at the three boundaries, called by the test on the files
  read back, passes.

Other tests of this work package:

- `galley2epub` is an entry point of the installed package, and the
  script next to `sys.executable` runs `--help` with exit code 0;
- the stages run one by one through `main` on a fresh Kadesh folder give
  the same `blocks.json` and `book.md` bytes as `run`;
- `main(["layout", folder])` on a folder with no `words.json` raises
  `InputFileError` naming extract; `main(["run", folder])` with `correct
  = true` raises `ConfigError` before `pages.json` exists; a `words.json`
  from the other excerpt raises `InputFileError`;
- the fidelity check failing inside a stage cannot be caused from
  outside with correct code; it is held by the unit tests of sections 5
  and 7.

## 10. How it runs in parallel, and the speed budget

analyze, extract and layout run per page with `parallel.py`; the
output does not depend on the number of workers, which the 1-against-6
test of section 6 and the 1-against-3 test of section 7 hold. structure,
markdown and epub run once.

Measured on 14 November 2026 on an Apple M5 Pro (6 performance cores),
Python 3.15.0 free-threading, pdfplumber 0.11.10 (pdfminer.six
20260107), pypdfium2 5.15.2, Pillow 13.0.0, Pandoc 3.13; the median of 5
runs, with a prototype of analyze and extract that does what section 6
says (one `extract_words()` pass each, one document per worker thread):

| work | Kadesh, 1 worker | Kadesh, 6 workers | Gierke, 1 worker | Gierke, 6 workers |
|---|---|---|---|---|
| analyze + extract | 0.91 s | 0.55 s | 0.54 s | 0.41 s |
| same, one document per page | 1.36 s | 0.67 s | 0.98 s | 0.52 s |
| cover render, 300 dpi, and PNG save | 0.24 s | | | |
| Pandoc, `book.md` to JSON | 0.05 s | | | |
| Pandoc, `book.md` to EPUB | 0.10 s (with cover) | | 0.04 s | |
| `words.json` write and read (1.05 MB) | 0.01 s | | | |

So `galley2epub run` takes about 1.0 s on the Kadesh excerpt and 0.5 s on
the Gierke excerpt with 6 workers. The skeleton adds to `uv run pytest`
about 1.5 s for the session fixture, 1.5 s for the 1-against-6 worker
test, a few tenths of a second for the Pandoc unit tests, and
milliseconds for the rest: about 4 s of the 30 s budget. The suite ran in
0.15 s before the skeleton. A test that runs the pipeline outside the
session fixture is marked `thread_unsafe`, or the 8-thread run repeats
it 8 times.

## 11. How the numbers were obtained

Every count and box above comes from pdfplumber and pypdfium2 run
directly on the excerpts, not from galley's code, so the tests that
assert them can fail. To reproduce the word and line counts:

```python
import pdfplumber

def lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        centre = (word["top"] + word["bottom"]) / 2
        if lines and lines[-1][0]["top"] <= centre <= lines[-1][0]["bottom"]:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines

for name in ["kadesh_8-17", "gierke_86-93_270-271"]:
    with pdfplumber.open(f"tests/fixtures/pdf/{name}.pdf") as pdf:
        pages = [page.extract_words() for page in pdf.pages]
    print(name, [len(w) for w in pages], [len(lines(w)) for w in pages])
```

run with `uv run python` in the repository. The page sizes are
`page.width` and `page.height` of pdfplumber and `get_size()` of a
pypdfium2 page; the render sizes come from `page.render(scale=dpi / 72,
grayscale=True)`. The Markdown round trip escaped each word as section 8
says, wrote one div per page, ran `pandoc -f markdown-smart -t json
--fail-if-warnings`, and compared word multisets with the separator rule
of section 5. The ink shares of section 6 are the share of pixels darker
than 128 and than 200 in a 50 dpi grayscale render of each page of the
whole books in `samples/public_domain/` with no text-layer word.

The pages these numbers come from have not been checked by eye by the
owner; they are counts, not reference pages, and the stage specs that
follow name the reference pages.

## 12. Open points

1. **Whether the skeleton's markdown applies edits.** (a) It does not:
   any edit in `edits/` stops markdown with an `EditError`, and the
   markdown spec specifies applying them, with `edits-from` (§10). (b) It
   applies them as §10 says, which on one-span blocks is a search and a
   replace per edit, checked against `block_sha256`. (a) keeps the
   skeleton to what tests the formats, and no edit can exist before
   `edits-from` is built; (b) would try the edits format end to end now,
   about half a day more in work package 3c, and the markdown spec would
   still rework it for blocks of several spans. Recommended: (a).
   Meanwhile (a), as section 8 says.
2. **What the skeleton does with a page that has no text layer.** (a)
   analyze stops with a `PdfError` that lists every such page and asks
   for them in `exclude_pages` (section 6). (b) It reads such a page as
   `blank` and logs a warning naming it. (a) never hides text: page 69
   of the whole Kadesh book has about five lines of text and a caption with no
   layer, which (b) would drop behind a warning. Its cost is that a book
   runs only once its pages without a layer are excluded: Kadesh page 9
   in the excerpt's config, 14 pages of the whole Kadesh book and 12 of
   Gierke's. The skeleton runs only on the excerpts, and the extract spec
   brings OCR for those pages. Recommended: (a). Meanwhile (a).
3. **`text_layer_score` without the word list.** §8 says the score is
   `None` only for a page without a layer; the skeleton has no word list,
   so it writes `None` on every page. (a) Accept that for the skeleton;
   the analyze spec fills the score, and until then no stage reads it.
   (b) Bring `wordlist.py` into the skeleton, which needs Tesseract's
   `combine_tessdata` and `dawg2wordlist` and a cache under
   `~/.cache/galley/`. Recommended: (a); nothing in the skeleton uses the
   score. Meanwhile (a).

## 13. Not in this spec

- `wordlist.py`, the correct stage, `galley2epub edits-from`, the index
  stage, OCR with Tesseract, figures cut from plates: later specs.
- Running heads, page numbers, signature marks, headings, quotes, margin
  notes, notes and hyphen joins: structure's spec. The skeleton removes
  nothing after extract.
- Columns, margins and reading order: layout's spec.
- The style sheet, the title page Pandoc adds, and a smaller cover: the
  epub spec.
- A stage that notices its input is older than the config (an
  `exclude_pages` added after analyze ran): not handled; the owner reruns
  from analyze.
