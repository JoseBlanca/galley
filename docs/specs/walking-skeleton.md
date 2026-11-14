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
`docs/glossary.md` and uses their names. "Architecture §8" is a section
of `docs/architecture.md`; "section 6" is a section of this spec. No code
exists yet besides `src/galley/__init__.py`, which imports gilguard (a
library that stops the program at any import that turns Python's global
lock back on), and the empty stage subpackages. Sections 3 to 9 follow
the plan's four work packages, approved by the owner on 14 November
2026, and each heading names its work package. `wordlist.py`, the
correct stage, `galley2epub edits-from` and the index stage are not in
the skeleton (section 12). Nothing is left open for the owner.

## 1. What the skeleton does, stage by stage

| stage | the skeleton's rule |
|---|---|
| analyze | page size from pdfplumber; a page with text-layer words is `text`; a page without stops the run unless the config excludes it; no OCR audit |
| extract | pdfplumber's `extract_words()` on `text` pages; words of excluded pages and regions become removals; the cover page rendered |
| layout | one region per page; lines grouped by the vertical centre of each word |
| structure | one paragraph block per region, its words joined by single spaces; nothing removed, no notes, no hyphen joins |
| markdown | a metadata header and one fenced div per block, every ASCII punctuation character escaped; refuses edits |
| epub | Pandoc with an empty style sheet and the cover |

The fidelity check (architecture §13) runs at the three boundaries,
layout, structure and markdown, inside the `run` of each of those stages
(section 5).

## 2. The excerpts as the skeleton reads them

Both excerpts are scans whose every page carries a picture of the page
and an invisible text layer made by an OCR program, in `GlyphLessFont`,
a font that draws nothing. Each has 10 pages, indexed 0 to 9. Counts are
of pdfplumber 0.11.10's `page.extract_words()` with its default options:

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

"Lines" are the lines of the skeleton's layout rule (section 7). What
these pages hold that a reader of the formats would not expect:

- **Kadesh page 9 has no text layer**: 0 characters. It is a blank page
  of the book. The skeleton has no OCR to confirm that, so the Kadesh
  config of every test excludes it (section 6).
- **Kadesh page 8 is a plate**, a full-page drawing, whose layer holds 4
  stray words, `,`, `'`, `..` and `^U;L`. The skeleton does not detect
  plates, so these words reach the EPUB as a paragraph. The real
  structure stage removes them with the reason `plate_text`, which
  architecture §8 gives for stray text-layer characters on a plate.
- **Kadesh page 0 has two columns of footnotes**, and the skeleton's lines
  run across both: the line at top 584.8 pt reads `•Pa per read before the
  International Congress of Ori- 'There is, however, much material for
  studying the`, the end of one note and the start of another. The page
  number `81` (box 241.68, 622.509, 249.07648, 629.509) falls in the line
  that starts `fighting by groups of four`.
- **Gierke prints headings in the margin**, and the skeleton's lines take
  them in: on page 1, "Diversity of materials." in the left margin comes
  out as `Diversity in tnjs manner elements that derived from the`, then
  `of mate- .`, then `rials. most diverse sources were fused …`.

In each case every word is kept, in a bad order, which is all the
skeleton asks.

## 3. Data formats: errors, model, config, book folder (work package 1)

These four modules are written first. They are complete, not simplified:
the formats of architecture §8 in full, including the fields the
skeleton leaves empty (notes, word changes, page numbers), because the
skeleton is there to try them.

### errors.py

The exception classes of architecture §12, each a subclass of
`GalleyError`, with no behaviour of their own except `FidelityError`,
which keeps what it found so that a test can assert on it.

```python
class GalleyError(Exception): ...
class ConfigError(GalleyError): ...
class InputFileError(GalleyError): ...
class PdfError(GalleyError): ...
class ExternalProgramError(GalleyError): ...
class EditError(GalleyError): ...

class FidelityBoundary(StrEnum):
    LAYOUT = "layout"; STRUCTURE = "structure"; MARKDOWN = "markdown"

class FidelityError(GalleyError):
    def __init__(
        self,
        boundary: FidelityBoundary,
        missing: frozendict[str, int],
        invented: frozendict[str, int],
        detail: str,
    ) -> None: ...
    # boundary: where the check ran; missing and invented
    # map a word to how many times it is missing from, or extra in, the
    # output; detail is the rest of the message (pages, note counts).
    # The attributes of the same names are set; the message lists them.
```

`FidelityBoundary` is defined here, not in `fidelity.py`, because
`FidelityError` needs it and `errors.py` imports no other module of
galley; `fidelity.py` imports it from here.

Tests: each subclass is a `GalleyError`; a `FidelityError` built with one
missing and one invented word has them as attributes and names both, with
their counts, in `str(error)`.

### model.py

Every dataclass and enum of architecture §8 is here, with the field
names, types and order it gives: `Box`, `PageKind`, `TextSource`,
`PageInfo`, `PagesFile`, `Word`, `Figure`, `PageWords`, `WordsFile`,
`Line`, `Region`, `PageLayout`, `LinesFile`, `BlockKind`, `Emphasis`,
`Span`, `Origin`, `Block`, `Note`, `ChangeReason`, `WordChange`,
`PageNumberPosition` (the `head | foot` of `PageNumber`), `PageNumber`,
`RemovalReason`, `Removal`, `BlocksFile`, `Edit` and `RenderedPage`,
with `PageInfo.blank_checked_by_ocr: bool` and `PagesFile.ocr_audit:
OcrAudit | None`.

What architecture §8 leaves to this spec:

- `Box(x0, top, x1, bottom)` is positional: four floats, written in JSON
  as a list of four numbers. Every other dataclass with more than three
  fields is `kw_only=True`, as the coding skill says, so a removal is
  written `Removal(page_index=0, box=..., text="81",
  reason=RemovalReason.EXCLUDED_REGION)`.
- Each of the four top-level dataclasses, `PagesFile`, `WordsFile`,
  `LinesFile` and `BlocksFile`, has `format_version: int` and
  `source_pdf_sha256: str` as its first two fields, keyword-only, with
  `format_version` defaulting to the constant of its file,
  `PAGES_FORMAT_VERSION`, `WORDS_FORMAT_VERSION`, `LINES_FORMAT_VERSION`
  or `BLOCKS_FORMAT_VERSION`, each 1, so that one format can change
  without the others.
- `Figure.image` is a `str`, the path relative to the book folder with
  `/` as separator, so that `words.json` is the same on every system.
- `OcrAudit`, the record of the audit of architecture §7b, which the
  skeleton never fills (section 6). Its fields are the smallest set that
  architecture §7b describes; analyze's spec may add to them, as a change to
  this format:

  ```python
  class OcrVerdict(StrEnum):
      LAYER_KEPT = "layer_kept"          # the layer scored as well as Tesseract
      LAYER_DOUBTFUL = "layer_doubtful"  # below, but not clearly; the run goes on

  @dataclass(frozen=True, slots=True)
  class SampledPage:
      page_index: int
      layer_score: float       # share of the layer's words in the word list, 0 to 1
      tesseract_score: float   # the same share for Tesseract's words of the page

  @dataclass(frozen=True, slots=True)
  class OcrAudit:
      sampled: tuple[SampledPage, ...]
      verdict: OcrVerdict
  ```

  A layer clearly worse than Tesseract has no verdict here: analyze stops
  with `PdfError` and writes no `pages.json` (architecture §7b).

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
list, an enum its value, `None` is `null`, a float what `json.dumps`
writes, and a `frozendict` with int keys an object whose keys are the
ints as strings (architecture §8; no field has one yet). The same value
gives the same bytes, whatever made it: a float field is written as a
float when it holds an int, and `-0.0` as `0.0`.

Every number must be finite: a NaN or an infinity is not JSON, and the
writer refuses it (`json.dumps(..., allow_nan=False)` raises
`ValueError`). A string that cannot be encoded as UTF-8, one holding a
lone surrogate, makes the writer raise `ValueError` naming the field
path: it is a defect, or bad input, of the stage that made the value,
and extract's spec decides what a surrogate in a text layer becomes. The
writer makes all the bytes before it touches the file, then writes them
to a temporary file in the same folder and moves it over the old one
(`os.replace`), so a failed write leaves the old file as it was. An edits
file is JSON Lines, one object per edit and per line, with no indent,
each with `format_version` 1 first (architecture §8).

Reading checks everything and stops at the first problem with an
`InputFileError` whose message names the file and, for a field, its path
in the JSON, `pages[3].words[12].box`:

- the file is missing: the message names the stage that writes it ("run
  `galley2epub extract`");
- the JSON is not valid (a truncated file): the line and column;
- `format_version` is missing, not an int, or not the current one: both
  versions are named;
- a field is missing, or there is a field the dataclass does not have;
- a value has the wrong JSON type, an enum value is not a member, a `Box`
  is not four numbers. A JSON integer is accepted where a float is
  expected and becomes a float, so `81` and `81.0` read the same; `true`
  is not accepted as a number;
- a number is not finite (`NaN`, `Infinity`, which Python's `json`
  reads although JSON has no such values);
- a string holds a surrogate (written `\udc00` in the JSON), which no
  writer of galley makes;
- an object has the same key twice ("given twice").

`read_edits` raises `EditError` instead, naming the file and the line,
for a line that is not JSON, an object with a missing or unknown field
or a key given twice, a value of the wrong type or a string holding a
surrogate, a `format_version` other than 1, or a blank line; and,
naming the file, for a file that is not UTF-8. A file that starts with
a byte-order mark is refused with a message that asks for it to be
saved as UTF-8 without one, since the owner may write edits by hand. A missing edits file is not its concern: the caller
lists the files that exist (architecture §10: a missing file is no
edits).

The reader rebuilds the tuples and enums, so reading what was written
gives an equal value.

Four more functions, which several stages and `fidelity.py` call:

```python
def pdf_sha256(pdf: Path) -> str: ...
    # The SHA-256 of the file's bytes, 64 lowercase hex digits.

def check_source_pdf(path: Path, file_pdf_sha256: str, expected_pdf_sha256: str) -> None: ...
    # Raises InputFileError when the file at `path` was made from another
    # PDF; the message names the file and the stage to rerun
    # (pages.json: analyze, words.json: extract, ...).

def block_text(block: Block) -> str: ...
    # The text of a block (architecture §7): its spans' text concatenated.

def block_sha256(block: Block) -> str: ...
    # The first 12 hex digits of the SHA-256 of block_text(block), UTF-8:
    # the checksum an Edit carries.
```

Only analyze computes the hash, from the PDF. Every later stage copies
`source_pdf_sha256` from its input file into its output, and checks each
file it reads against the hash in `pages.json`; extract, which also reads
the PDF, checks `pages.json` against `pdf_sha256(config.pdf)`.

Tests, all unit tests with literal values written in the test:

- for each of the four JSON files, a value that fills every field,
  including an `OcrAudit` of two sampled pages and a page with
  `blank_checked_by_ocr` true in `pages.json`, and a `Note` with two
  blocks, a `WordChange`, a `PageNumber` and a `Removal` in
  `blocks.json`, written and read back equal; written twice, the same
  bytes; `ocr_audit` `None` is written as `null` and read back;
- the JSON of a `Box` is a list of four numbers, of an enum its string;
- for each reader: a truncated file (the first half of a valid one), a
  `format_version` of 2, a missing field (`box` deleted from one word), an
  unknown field, an enum value that is not a member (`"kind": "cover"`),
  a `Box` of three numbers, a missing file, each an `InputFileError` whose
  message holds the file name and the field path;
- `read_pages` with `blank_checked_by_ocr` missing, or `0` instead of a
  boolean; with an `ocr_audit` whose verdict is `"redo"`, and one whose
  sampled page lacks `tesseract_score`: each an `InputFileError` with the
  field path (`ocr_audit.sampled[0].tesseract_score`);
- `read_edits` on a line that is not JSON, a line that lacks `old`, a
  line with `format_version` 2, and a blank line: an `EditError` naming
  the file and the line number;
- `check_source_pdf` with two different hashes raises and names the stage;
- `block_sha256` of a block with two spans, against a literal computed
  with `hashlib` in the test;
- the rules above that the list does not name: a non-finite number, a
  surrogate and a duplicate key in each reader, a file of edits that is
  not UTF-8 or starts with a byte-order mark, a writer given a surrogate
  or a NaN leaving the old file as it was, `-0.0` and an int in a float
  field written as `0.0` and the float, a `frozendict` round trip, and
  the value of every enum member as architecture §8 lists it.

### config.py

Reads `book.toml` (architecture §6) into a frozen `BookConfig`. Every key
of architecture §6 is read; `correct = true` is read, but `galley2epub
run` refuses it (section 9).

```python
class Language(StrEnum):
    EN = "en"; ES = "es"; FR = "fr"; DE = "de"; IT = "it"

class OcrMode(StrEnum):
    VERIFY = "verify"; TRUST = "trust"; REDO = "redo"

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
    ocr: OcrMode = OcrMode.VERIFY
    correct: bool = False
    exclude_pages: tuple[int, ...] = ()
    exclude_regions: tuple[ExcludedRegion, ...] = ()
    cover_page: int | None = None

def read_config(path: Path) -> BookConfig: ...
def tesseract_language(language: Language) -> str: ...
    # en -> eng, es -> spa, fr -> fra, de -> deu, it -> ita
```

In TOML an excluded region is `{page = 0, box = [240, 620, 252, 632]}`;
the key `page` becomes the field `page_index`. A relative `pdf` is taken
against the folder of `book.toml`; relative or absolute, it is then
resolved (`Path.resolve`: made absolute, symbolic links followed). Tests
write absolute paths to the excerpts.

`read_config` raises `ConfigError`, naming the file and the key, when: the
file is missing or is not valid TOML; a key is unknown, at the top level
or inside a region; a required key (`pdf`, `title`, `authors`,
`language`) is missing; `title` is empty or `authors` an empty list
("must not be empty"); a value has the wrong type (`authors =
"Breasted"` instead of a list); `language` or `ocr` is not one of its
values; a page index is negative; a box is not four finite numbers (TOML
has `nan` and `inf`) or does not have `x0 < x1` and `top < bottom`; the
PDF does not exist or is not a file. A page index past the end
of the book needs the PDF opened, so analyze checks it (section 6).

Tests: a config with every key at a value other than its default, read
into the literal `BookConfig` it should give; a config with only the
required keys, read with the defaults; one test for each `ConfigError`
above; `tesseract_language` for the five languages.

### book_folder.py

```python
@dataclass(frozen=True, slots=True)
class BookFolder:
    root: Path
    # properties, each a Path under root, as architecture §5 lists them:
    # book_toml, pages_json, words_json, images_dir, cover_png
    # (images/cover.png), lines_json, blocks_json, edits_dir, book_md,
    # book_epub
```

One test: every property is the path architecture §5 gives, under
`root`.

## 4. PDFium and threads: pdfium.py, parallel.py (work package 2a)

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

def strip_stride(buffer: bytes, width_px: int, height_px: int, stride: int) -> bytes: ...
    # The pixels of a grayscale bitmap whose rows are `stride` bytes apart,
    # row by row with the padding after each row's `width_px` bytes dropped.
    # A stride below width_px, or a buffer whose length is not
    # stride * height_px, is a ValueError.
```

`render` gives 8-bit grayscale pixels at `scale = dpi / 72`, row by row
with no padding, through `strip_stride`. A file that is not a PDF, a path
that does not exist or is a directory, or a page index outside the
document, is a `PdfError` naming the path and, for a page, the index and
the page count. A `dpi` below 1 is a `ValueError`, checked before PDFium
is called.

`page_size` gives pypdfium2's numbers, those of `PdfPage.get_size()`:
the crop box clipped to the media box, as 32-bit floats, which is the
area `render` draws. They can differ from pdfplumber's: Gierke's pages
are 376.1000061 × 621.5 pt in pypdfium2 and 376.128 × 621.504 in
pdfplumber. Kadesh's crop box (508.3 × 728.2) is taller than its media
box (508.32 × 728.16), so its pages are 508.3 × 728.16 pt in pypdfium2. Word boxes
come from pdfplumber, so `pages.json` takes its sizes from pdfplumber
(section 6) and no stage of the skeleton calls `page_size`. Only extract
calls `render`, for the cover.

Tests that call PDFium are marked `thread_unsafe`, the marker of
pytest-run-parallel for a test that must run once rather than in 8
threads at once under `pytest --parallel-threads=8`: `page_count` of
both excerpts is 10; `page_size` of Kadesh page 0 is 508.29998779296875 ×
728.1599731445312; `render` of Gierke page 0 at 300 dpi is 1568 × 2590
pixels with `len(pixels) == width_px * height_px`; the same render called
from 6 threads at once gives 6 times the bytes of one call alone; page
index 10, and a text file given as PDF, each raise `PdfError`. A unit
test of `strip_stride` gives it a literal buffer of 2 rows of 3 pixels
with a stride of 4 and expects the 6 pixels without the 2 padding bytes.
It is a test of its own because pypdfium2 5.15.2 gives no padding on the
excerpts (stride 377 for a width of 377 on Gierke at 72 dpi), so no
render test can show the padding.

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

`map_pages` runs `function` on every item in a pool of `workers` threads
and returns the results in the order of `items`. `map_pages_with_source`
does the same, but each worker thread first opens one source with
`open_source()`, a pdfplumber document, passes it to `function` with each
item it takes, and closes it when no item is left. One document per
thread rather than per page: analyze and extract together on the Kadesh
excerpt took 0.91 s that way against 1.36 s with one document per page,
with 1 worker.

When `function` raises, the worker's source is closed and the exception
of the first failing item in input order, among those that ran, is
raised in the calling thread; items not yet started may not run. When
`open_source` raises, that exception is raised in the calling thread, and
the sources other workers opened are closed; when `open_source` raises in
one worker and `function` in another, the exception of `open_source` is
the one raised. `workers` below 1 is a `ValueError`. With more workers
than items, the extra workers do nothing: a worker opens its source only
when it has taken an item, so no more sources are opened than there are
items. When no worker failed but the results do not cover every item
exactly once (a source whose closing swallowed an exception of
`function`), that is a `RuntimeError` naming the missing item indices,
raised whatever Python's `-O` flag, never a shorter tuple.

Tests: results come back in input order when later items finish first
(the function sleeps less for later items); 1, 3 and 8 workers give the
same tuple on 20 items; an exception raised for item 5 reaches the
caller and every opened source is closed; an `open_source` that raises
reaches the caller; a source that counts its openings and closings, with
3 workers on 20 items, is opened at most 3 times and closed as often;
`workers=0` raises.

## 5. The fidelity check: fidelity.py (work package 2b)

The check of architecture §13, complete, not simplified: it handles
removals, word changes, notes and note references although the
skeleton's stages make none, because the real stages will, and its unit
tests build those values by hand.

```python
# FidelityBoundary (layout, structure, markdown) is imported from
# errors.py (section 3), since FidelityError carries it.

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
def check_stage(stage: Literal[FidelityBoundary.LAYOUT], before: WordsFile, after: LinesFile) -> None: ...
@overload
def check_stage(stage: Literal[FidelityBoundary.STRUCTURE], before: LinesFile, after: BlocksFile) -> None: ...
@overload
def check_stage(stage: Literal[FidelityBoundary.MARKDOWN], before: BlocksFile, after: MarkdownWords) -> None: ...
```

`check_stage` is pure; it raises `FidelityError` or returns. At the
markdown boundary, `before` is the `BlocksFile` with the edits applied,
which in the skeleton is the file as structure wrote it (section 8).

**The words of each side.** A text is split on white space
(`str.split()`), nothing normalised.

- `WordsFile`: the `text` of every word of every page, split like any
  other text, so that a word holding a no-break space, `10\xa0000`,
  counts as the same two words on both sides. Its removals are extract's,
  which no boundary checks.
- `LinesFile`: the `text` of the words of every line of every region,
  split the same way.
- `BlocksFile`, at the structure boundary: for each block of the body and
  of every note, the text of its spans with each note reference span
  replaced by a space, split; plus the `text` of each note reference span
  as a word of its own; plus each note's `marker` as a word. A note
  reference is a word of its own because concatenating the spans would
  glue it to the word before: `"…Greece,"` and `"1"` would read
  `Greece,1`, while structure's word change made it `Greece,` and `1`.
  The removals of `blocks.json` are added to this side, and each word
  change is undone: its `after` words are taken out and its `before`
  words put in.
- `BlocksFile`, at the markdown boundary: the same, without the note
  reference spans and without the `marker` of a note whose `referenced`
  is true, because Pandoc numbers notes itself (architecture §17); the
  marker of an unreferenced note is printed as text and counted. No
  removals or word changes: markdown makes none.
- `MarkdownWords`: the `text` of each word.

Before the words are compared, the structure boundary checks what
structure recorded, because a wrong record would hide a lost or invented
word. Each fails with a `FidelityError` that has no missing or invented
word and names, in `detail`, the block and span or the word change:

- A note reference span's `text` must be exactly the `marker` of the
  note its `note_ref` names, and that note must exist. At the markdown
  boundary the whole span becomes Pandoc's note and its text is not
  counted, so a span `"1 and"` would lose `and` there unseen.
- A word change must have words in `before` and in `after`, so that it
  neither deletes nor invents words, and must say what its reason
  allows: for `note_marker`, `before` and `after` joined are the same
  text (`Greece,1` and `Greece,` `1`); for `hyphen_join`, `before` is two
  words, the first ending with `-`, and the first without its hyphen
  followed by the second is `after` joined (`repli-` `cate` and
  `replicate`). A change outside these rules, `Greece` to `Greek`, is
  the invented word the check is there to catch.

The two sides are compared as multisets. A difference is a
`FidelityError` with the words missing from the output and the words it
invented, each with its count, and in `detail` where each came from: the
page index for words and lines, the `origin` pages for a block, the block
id for Markdown. At the markdown boundary the number of note references
in the blocks is also compared with `note_count`; when only the counts
differ, the error has no missing or invented word and gives both counts
in `detail`. A removal's `text` is split into words like any other, so a
running head removed as one line counts each of its words.

**Reading the Markdown.** `read_markdown` runs `pandoc --from
markdown-smart-auto_identifiers --to json --fail-if-warnings` with the Markdown on
standard input, a timeout of 60 s and `check=True`; a missing `pandoc`,
a non-zero exit or a timeout is an `ExternalProgramError` with Pandoc's
standard error. It walks the `blocks` of Pandoc's JSON, not its `meta`,
so the title and authors are not words of the book. It joins the text of
adjacent `Str` elements and starts a new word at `Space`, `SoftBreak`,
`LineBreak`, and at the start and end of every block element and of
every `Note`. Without the last rule, the last word of one paragraph and
the first of the next come back glued, `Egypt.THE` on Kadesh pages 0 and
1. `Emph`, `Strong` and `Span` do not separate words, so a word half in
italics stays one word.

The elements read are those galley's Markdown makes: the blocks `Para`,
`Plain`, `Div`, `Header` and `BlockQuote`, and the inlines `Str`,
`Space`, `SoftBreak`, `LineBreak`, `Emph`, `Strong`, `Span` and `Note`.
Any other element, such as a list or a table that an unescaped character
let through, is an `ExternalProgramError` that names it and the block id
it is in ("outside any block" when there is none), rather than words
dropped or read wrongly; a later spec adds the elements its Markdown
makes, such as an image for a figure. A div or heading without an id
gives its words the id of the div or heading around it, or `None`.
Pandoc's `auto_identifiers` extension, on by default, would give every
heading an id made from its text (`chapter-one`), which is no block of
`book.md`; `-auto_identifiers` turns it off so that this rule holds for
headings too.

Some unescaped constructs make no element at all: a link reference
definition (`[1]: beta gamma` on a line of its own) or a title block
(`% Alpha beta` on the first line) leave their words out of Pandoc's
`blocks`. An unescaped construct therefore either raises in
`read_markdown`, as an element it does not read, or leaves its words to
`check_stage`, which reports them missing.

`read_markdown` is two functions: one runs Pandoc and returns its JSON
as text, and a pure one walks the JSON, which unit tests call on literal
JSON without Pandoc.

`--fail-if-warnings` makes a note definition that no reference uses an
error (Pandoc 3.13 warns and drops it; the option makes it exit with 3).
A reference with no definition is not a warning: Pandoc 3.13 keeps
`Text.[^zz]` as the text `Text.[^zz]` and exits with 0. The word check
catches it, as an invented `Greece,[^1]` and a missing `Greece,`.

Tests, unit tests with literal values:

- each boundary with equal sides passes;
- a word lost between words and lines, and one invented, give a
  `FidelityError` that names both with their counts and pages;
- the same word twice in the input and once in the output is a
  difference (multisets, not sets);
- at the structure boundary: a removal (`running_head`) accounts for the
  missing words; a hyphen join `("repli-", "cate") → ("replicate",)`
  passes, and fails without its word change; a note reference span `"1"`
  after `"…Greece,"`, with the word change `("Greece,1",) → ("Greece,",
  "1")`, passes; a note's marker counts as a word; a reference span
  whose text is not its note's marker (`"1 and"`) or names no note
  fails; a word change that deletes, invents, or does not follow its
  reason (`Greece` to `Greek`) fails; a word holding a tab or no-break space splits the
  same on both sides;
- at each boundary, a word twice on one side and once on the other is a
  difference; a wrong pair of files is a `TypeError`;
- at the markdown boundary: a referenced note's marker and its reference
  span are not counted, an unreferenced note's marker is; two references
  against one Pandoc note is a difference, and note references inside
  note blocks are counted; a word of the Markdown the blocks lack is
  invented;
- `read_markdown`, marked `pandoc` (a marker of `pyproject.toml` that
  skips the test when the program is missing): two paragraphs `a b` and
  `c` give `a`, `b`, `c`, not `bc`; `\*x\*y` comes back as `*x*y`; a
  footnote's words are words; `note_count` of a text with two footnotes
  is 2; the words of a div `::: {#b-p0000-001}` carry that id; an unused
  note definition raises `ExternalProgramError`; `Greece,[^1]` with no
  definition comes back as the one word `Greece,[^1]`; a heading inside
  a div carries the div's id;
- the walk of Pandoc's JSON, on literal JSON without Pandoc: the words of
  nested divs carry the innermost id; an element it does not read
  outside any div raises, saying "outside any block".

## 6. analyze and extract (work package 3a)

### analyze

analyze measures every page with pdfplumber, with
`map_pages_with_source`: its width and height (`page.width`,
`page.height`) and how many words `extract_words()` finds. Then, per
page:

1. A page in `exclude_pages` is `excluded`, `text_source` `none`.
2. Else a page with at least one text-layer word is `text`, `text_source`
   `text_layer`.
3. Else the page is `blank`, `text_source` `none`.

Then, when any page is `blank`, analyze stops with a `PdfError` that
lists every such page and says: "these pages have no text layer, and the
walking skeleton has no OCR; add them to `exclude_pages` once you have
checked that they hold no text". It writes no `pages.json`. So the
skeleton never writes a `blank` page. Decided by the owner on 14
November 2026: the real analyze reads such a page with Tesseract and
fills it or records it as blank (the audit of architecture §7b, in
analyze's own spec); without that audit, stopping is the only answer
that cannot drop a printed page. Page index 69 of the whole Kadesh book
has a running head, about five lines of text and a captioned figure, and
no text layer.

The skeleton runs no part of the audit, with `verify` or `trust` alike:
`blank_checked_by_ocr` is false on every page and `ocr_audit` is `None`,
although architecture §8 gives `None` only for `trust` and `redo`.
`text_layer_score` is `None` on every page, with a layer or not: the
score needs the word list, which is not in the skeleton, and no stage of
the skeleton reads it. The analyze spec fills all three.
`exclude_regions` holds the boxes of the config's regions for that page,
in the config's order.

Before any page is measured, analyze raises `ConfigError` when `ocr` is
`redo` ("ocr = redo needs OCR, which the walking skeleton does not have;
use verify or trust"), and when a page index of `exclude_pages`,
`exclude_regions` or `cover_page` is not below the page count, naming the
key, the index and the count. `check_config_pages` makes both checks, the
`ocr` one first.

```python
# galley.analyze
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def classify_page(
    index: int, width_pt: float, height_pt: float, layer_word_count: int, config: BookConfig
) -> PageInfo: ...

def check_config_pages(config: BookConfig, page_count: int) -> None: ...

def require_text_layer(pages: tuple[PageInfo, ...]) -> None: ...
    # Raises the PdfError above, listing every blank page.
```

`run` deletes `pages.json` first, so that a failed run leaves no old file
behind, and writes it with `source_pdf_sha256 = pdf_sha256(config.pdf)`.
Every stage's `run` takes the keyword `workers`, which the tests and the
command set; a stage that works in one thread ignores it.

### extract

extract reads `pages.json`, checks its hash against the PDF's, and gives
each page its words, with `map_pages_with_source`:

- `text` page: the words of `page.extract_words()` with its default
  options, in pdfplumber's order, each `Word(text, Box(x0, top, x1,
  bottom), None)` (the `None` is `ocr_confidence`). A word whose centre,
  `((x0 + x1) / 2, (top + bottom) / 2)`, is inside one of the page's
  `exclude_regions`, edges included, is not a word of the page but a
  `Removal` with its box, its text and the reason `excluded_region`.
- `excluded` page: no words; every word of its layer is a `Removal` with
  the reason `excluded_page`. These two reasons are architecture §8's for
  the words of a page or a region the config excludes.
- `blank` page, which the skeleton's analyze never writes but a
  `pages.json` may hold: no words, and the PDF page is not read.
- `plate` page, or a page whose `text_source` is `ocr`, which a
  `pages.json` may hold but the skeleton cannot read (it cuts no figure
  and has no OCR): extract raises `InputFileError` before reading any
  page, naming `pages.json`, those pages, and analyze to run again.

Every `PageWords` has `figures=()`: the skeleton cuts no figure. The
removals are in page order, then in pdfplumber's order.

When the config has a `cover_page`, extract renders it at 300 dpi with
`pdfium.render` and saves it as an 8-bit grayscale PNG,
`images/cover.png`: 2118 × 3034 pixels and 2.36 MB for Kadesh page 0.
extract deletes `words.json` and `images/` first, and always creates
`images/`, empty when there is no cover, so that every book folder has
the same files after a run.

A word is excluded by its centre, not by touching the region, so that a
word half inside a region the owner drew is not lost: the region `[240,
620, 252, 632]` on Kadesh page 0 holds the page number `81` and touches
`ROB.,` (x0 223.9, x1 244.8), which stays.

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
`require_text_layer` naming both blank pages of four; `ocr = redo`; an
`exclude_pages`, a region and a `cover_page` index equal to the page
count; a word inside a region, one touching it with its centre outside,
one with its centre on the edge; an excluded page with three words gives
three removals and no words.

The excerpt tests read from a session-scoped fixture, `excerpt_books` in
`tests/conftest.py`, which makes a book folder for each excerpt under
pytest's temporary directory with the configs of section 9. This work
package introduces it running analyze and extract; work package 4
changes it to run the whole pipeline (section 9). Reading:

- Kadesh `pages.json`: pages 0 to 8 `text`, page 9 `excluded`, every page
  508.32 × 728.16 pt, `text_layer_score` `None`; Gierke: 10 `text` pages
  of 376.128 × 621.504 pt.
- `words.json`: the word counts per page of section 2, as literals, but
  Kadesh page 0 at 583 words and Kadesh page 9 at 0; the only Kadesh
  removal is `81`, box (241.68, 622.509, 249.07648, 629.509),
  `excluded_region`; Kadesh page 0 starts `THE BATTLE OF KADESH A STUDY`;
  Kadesh page 8 is exactly `,`, `'`, `..`, `^U;L`; Gierke page 9 starts
  `1 86 Political Theories of the`; Gierke has no removal.

Tests that need a run of their own, each marked `thread_unsafe` so that
the 8-thread run does it once:

- analyze on Kadesh without `exclude_pages` raises `PdfError` naming page
  9 and only it;
- analyze and extract on Kadesh with `exclude_pages = [8, 9]`: page 8 has
  no words, and its 4 words are the only removals, `excluded_page`;
- analyze and extract on Kadesh with 1 worker and with 6 give
  byte-identical `pages.json` and `words.json` (10 pages, more than 6
  workers);
- extract on a Kadesh folder holding the Gierke `pages.json` raises
  `InputFileError` naming analyze.

## 7. layout and structure (work package 3b)

### layout

layout puts all the words of a page in one region and groups them into
lines by this rule:

1. Sort the page's words by `(top, x0)`, keeping pdfplumber's order for
   equal keys.
2. Go through them in that order. The first word starts a line and is its
   anchor. A later word joins the current line when its vertical centre,
   `(top + bottom) / 2`, lies within the anchor's `top` and `bottom`,
   edges included; otherwise it starts a new line and becomes its
   anchor.
3. Sort the words of each line by `x0`, keeping the order of step 1 for
   equal `x0`.

A line's box, and the region's, is the smallest box that holds its words.
A page with no words has no region. `figures` is copied from
`words.json`.

The rule has no threshold to tune. A fixed tolerance on `top` gives
counts that depend on the tolerance chosen: at pdfplumber's default of
3 pt, the page number `81` of Kadesh page 0 (top 622.509) is 3.038 pt
below its row (top 619.471) and gets a line of its own. With the centre
rule, the word centre closest to the edge of its anchor's band is 0.075
pt from it on Kadesh and 0.138 pt on Gierke, so the counts of section 2
do not depend on rounding.

A row of the page becomes one line across every column it crosses, so
Kadesh's footnote columns are read row by row, left note then right
note, and Gierke's margin headings go into the body line beside them.
No word is lost; the real layout spec fixes the order.

layout reads `pages.json` and `words.json` and checks both hashes
(section 3): `pages.json` against `pdf_sha256(config.pdf)`, as extract
does, then `words.json` against `pages.json`. A stale `pages.json` then
names analyze and a stale `words.json` names extract; compared only with
each other, the two files could not say which one is stale. Hashing the
1 MB Kadesh excerpt took 0.4 ms. layout runs per page with `map_pages`,
and runs
`check_stage(FidelityBoundary.LAYOUT, words, lines)` before writing `lines.json`;
on a `FidelityError` it writes nothing. It deletes `lines.json` first.

```python
# galley.layout
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def group_lines(words: tuple[Word, ...]) -> tuple[Line, ...]: ...
def layout_page(page: PageWords) -> PageLayout: ...
```

### structure

structure makes one block of each region, in page order: a `paragraph`
whose id is `b-p<page index, 4 digits>-001`, or `-002` and on for the
second region of a page and after (architecture §7; the skeleton's layout
makes one region per page), `level` `None`, `figure`
`None`, one span whose text is the words of the region, line after line,
joined by single spaces, with `emphasis` `none` and `note_ref` `None`,
and one `Origin` with the page index and the region's box. `notes`,
`removals`, `word_changes` and `page_numbers` are empty. A page with no
region gives no block.

structure reads `pages.json` and `lines.json` and checks both hashes as
layout does, `lines.json` naming layout; it uses only `lines.json`. It runs `check_stage(FidelityBoundary.STRUCTURE, lines,
blocks)` before writing `blocks.json`; on a `FidelityError` it writes
nothing. It deletes `blocks.json` first.

```python
# galley.structure
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def page_blocks(page: PageLayout) -> tuple[Block, ...]: ...
def make_blocks(lines: LinesFile) -> BlocksFile: ...
```

### Their tests

Unit tests, with `Word` and `PageLayout` values written in the test; they
need no output of extract, so this work package runs beside 3a:

- `group_lines`: two rows of three words, given shuffled, come out as two
  lines left to right; a word whose `top` is 2 pt below the anchor's but
  whose centre is inside its band joins it; a word whose centre is 0.01 pt
  below the anchor's `bottom` starts a new line; two columns of two rows
  give two lines, each across both columns (the skeleton's known bad
  reading, asserted so that the real layout spec sees it change); no
  words, no lines.
- `layout_page`: the region's box holds every line; a page with no words
  has no region; figures are copied.
- layout `run` on a hand-made `words.json` of 8 pages with 1 worker and
  with 3 gives the same bytes; with a `pages.json` of another hash it
  raises `InputFileError` naming analyze.
- `page_blocks`: a region of two lines gives one paragraph with the words
  joined by single spaces and the id `b-p0012-001` on page 12; no region,
  no block.
- the fidelity check passes on the hand-made inputs and outputs of both
  stages, and fails on a `LinesFile` made by `layout_page` with one word
  then dropped from a line.

The excerpt tests of layout and structure need extract's output, so they
are in work package 4 (section 9).

## 8. markdown and epub (work package 3c)

### markdown

markdown writes `book.md`: a metadata header, then one fenced div (a
Pandoc block `::: {#id}` … `:::` that gives its content an id) per block,
in the order of `blocks.json`:

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
  ensure_ascii=False)`), which YAML reads as double-quoted strings, of
  the title and each author escaped as a block's text is (the next
  point), since Pandoc reads metadata values as Markdown: unescaped,
  `The Life of *Gargantua*` loses its asterisks to emphasis and
  `C:\Windows` its backslash and the word after it.
- The text of a block is written on one line, with a backslash before
  every ASCII punctuation character (`string.punctuation`) and nothing
  else changed but the white space of the next point. Pandoc's Markdown reads any escaped ASCII punctuation as
  itself. Unescaped, Pandoc 3.13 changes words of both excerpts: Kadesh's
  `*Oampagne`, `me*ure` and `admits*` lose their asterisks to emphasis,
  Gierke's `jj^J^jjJJ` its carets to a superscript. Escaped, all 6,121
  Kadesh and 3,406 Gierke words come back from a round trip. The
  escaping makes `book.md` hard to proofread (`remarks\.`); the markdown
  spec chooses a lighter one with the same guarantee.
- The white space that Pandoc's Markdown reads as layout is made plain:
  each tab, line feed and carriage return in the text becomes a space,
  and so do the vertical tab, the form feed and U+001C to U+001F, which
  XML 1.0 does not allow; then the spaces at the start and end of the
  text are dropped. No word changes, since `str.split()`,
  which the fidelity check splits words with, splits at each of these
  characters. Left as they are, Pandoc 3.14 drops a carriage return
  inside a word (`ab\rcd` reads as the one word `abcd`), and reads a
  line that starts with a tab or four spaces, at the start of the text
  or after a blank line, as a code block. Every other character is kept:
  checked on 14 November 2026 with Pandoc 3.14 through `read_markdown`,
  each of the other 19 characters `str.split()` splits at (U+0085 and
  the Unicode spaces and line separators) and each C0 and C1 control
  character came back
  as written, inside a word, at the start of the text and four times
  before a word.
- A character that XML 1.0 does not allow and that is not made a space
  above, which is every other C0 control character, U+FFFE, U+FFFF and
  a lone surrogate, makes markdown raise `InputFileError` naming
  `blocks.json`, the block id and the code point (`U+FFFE`). Pandoc
  copies such a character into the EPUB's XHTML, which is then not
  well-formed (epubcheck: `FATAL(RSC-016)`), while the word check
  passes; the text pdfium gives of both whole books holds U+FFFE
  hundreds of times. What such a character becomes is for extract's
  spec. The C1 control characters (U+007F to U+009F) and the other
  noncharacters (U+FDD0 to U+FDEF, U+nFFFE and U+nFFFF of planes 1 to
  16) are written as they are: checked on 14 November 2026 with Pandoc
  3.14, Python's XML parser and epubcheck 5.4.0, an EPUB holding all of
  them is well-formed and passes, while one holding the characters
  above is not and fails.
- The skeleton writes no heading, footnote, margin note or figure:
  structure gives only paragraphs. markdown raises `InputFileError`
  naming `blocks.json` and the block or note when it meets another kind,
  a note, or a note reference, rather than write it wrongly.
- A blank line separates the header and every div.

Edits: decided, the skeleton does not apply them, because no edit can
exist before `edits-from` is built. markdown reads every `edits/*.jsonl`
with `read_edits`, and when any holds an edit it raises `EditError`
naming the file and saying that edits are applied from the markdown spec
on. A missing `edits/` folder, or empty files, is no edits.

markdown reads `pages.json` and `blocks.json` and checks the hash of
`blocks.json` against `pages.json`'s, as every stage after analyze does, makes the Markdown,
runs `read_markdown` on it and `check_stage(FidelityBoundary.MARKDOWN, blocks,
words)`, and only then writes `book.md`. It deletes `book.md` first.

```python
# galley.markdown
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def escape_markdown(text: str) -> str: ...
def render_markdown(blocks: BlocksFile, config: BookConfig) -> str: ...
```

### epub

epub runs

```
pandoc <book.md> --from markdown-smart-auto_identifiers --to epub3 --output <book.epub>
       --css <style.css> --fail-if-warnings [--epub-cover-image <images/cover.png>]
```

with absolute paths, a timeout of 120 s and `check=True`. The input
format is the one `read_markdown` reads with (section 5), so that the
EPUB is made from the same reading of `book.md` that the word check
passed. Making the paths absolute (`Path.resolve`) is a safety
measure with no effect a test can see while Pandoc runs in the caller's
directory, where relative paths also work. `style.css` is a
file of the package, `src/galley/epub/style.css`, empty in the skeleton,
found with `importlib.resources`; passing it tries now the path the real
style sheet will take. With `--css`, Pandoc uses that sheet instead of
its own. The cover is passed when the config has a `cover_page`. A
missing `book.md` is an `InputFileError` naming markdown, and a missing
`images/cover.png` when the config has a `cover_page` one naming extract.
A missing `pandoc`, a non-zero exit or a timeout is an
`ExternalProgramError` with Pandoc's standard error. epub deletes
`book.epub` first. It does not run epubcheck (architecture §16).

With no heading in `book.md`, Pandoc 3.13 makes one chapter file,
`EPUB/text/ch001.xhtml`, puts the title as its first heading, and keeps
each div's id (`<div id="b-p0000-001">`).

```python
# galley.epub
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def pandoc_arguments(folder: BookFolder, config: BookConfig, style_sheet: Path) -> tuple[str, ...]: ...
```

### Their tests

Unit tests:

- `escape_markdown`: `*x*` gives `\*x\*`; `1. Of` gives `1\. Of`; `«` and
  `—` are unchanged; `ab\rcd` and `ab\tcd` give `ab cd`, and `\tab` and
  `    ab` give `ab`; `string.punctuation` gives a literal with a
  backslash before each character; a text holding every ASCII
  punctuation character, escaped and read back with `read_markdown`
  (marked `pandoc`), comes back equal, and so do `jj^J^jjJJ`, `H~2~O`,
  `a\\b`, `# 1 Of`, `see @doe`, `*x*`, `_x_`, `` `x` ``, `[x](y)`,
  `$x$`, `<i>x</i>`, `<!--x-->`, `{x}` and `|a|b|`; markdown `run` on a
  block holding the vertical tab, the form feed and U+001C to U+001F,
  inside a word and four times before one, writes a `book.md` whose
  words are the block's; so do the words of texts holding each character `str.split()`
  splits at and each control character, inside a word, at the start of
  the text and four times before a word, and of texts with a tab or
  four spaces after a blank line.
- `render_markdown` on a literal `BlocksFile` of two paragraphs gives a
  literal Markdown text, header included; a heading block, a note or a
  note reference raises `InputFileError`; a block holding a character
  XML does not allow raises `InputFileError` naming its code point, and
  one holding a C1 control character or U+FDD0 does not.
- a title and an author holding `*`, `_`, `\`, `<`, `[x](y)` and a
  non-ASCII letter come back unchanged in `content.opf`'s `dc:title`
  and `dc:creator` (marked `pandoc`).
- markdown `run` (marked `pandoc`, since it calls `read_markdown`) with an
  edit in `edits/owner.jsonl` raises `EditError` naming the file; with an
  empty `edits/owner.jsonl`, and with no `edits/` folder, it writes
  `book.md`; when the Markdown loses a word (`render_markdown` replaced
  by one that drops it), `run` raises `FidelityError` and writes no
  `book.md`.
- `pandoc_arguments` with and without a cover, against literal tuples.
- epub `run` on a hand-written `book.md` of two divs (marked `pandoc`):
  `book.epub` is a zip whose first entry is `mimetype` holding
  `application/epub+zip`, whose `EPUB/content.opf` has the title and
  `<dc:language>en</dc:language>`, and whose chapter holds both div ids;
  with no `book.md`, it raises `InputFileError` naming markdown; the
  style sheet `EPUB/styles/stylesheet1.css` is there and empty; a
  `book.md` with `![](missing.png)` gives
  `ExternalProgramError` with Pandoc's "Could not fetch resource" and no
  `book.epub`; with no `pandoc` on the `PATH`, the error says it is not
  installed.
- the same EPUB passes epubcheck (marked `epubcheck`; it skips until
  epubcheck is installed, which architecture §16 asks for before the
  epub stage is built).

## 9. The command and the end-to-end test (work package 4)

### cli.py

```python
# galley.cli
def main(argv: Sequence[str] | None = None) -> None: ...
```

```
galley2epub run <book folder> [--workers N]
galley2epub analyze | extract | layout | structure | markdown | epub <book folder> [--workers N]
```

`pyproject.toml` gains `[project.scripts] galley2epub = "galley.cli:main"`.
`main` parses the arguments with argparse, sets logging to `INFO` on
standard error, reads `book.toml` from the folder with `read_config`, and
calls the stage's `run`. `run` calls analyze, extract, layout, structure,
markdown and epub in that order. The fidelity check runs inside layout,
structure and markdown, so it runs whether a stage is called alone or by
`run`: after `edits-from`, the owner reruns markdown alone, and that is
where edits enter the text.

Before any stage runs, `main` finds the programs the command needs with
`shutil.which`: for `run`, `markdown` and `epub`, a missing `pandoc` is an
`ExternalProgramError` saying "install it with `brew install pandoc`".
`run` raises `ConfigError` when the config has `correct = true`, since
the skeleton has no correct stage. The subcommands `correct` and
`edits-from` do not exist yet; argparse rejects them. Errors propagate to
`main`, which logs them and raises them again (architecture §14).

### The end-to-end test

Work package 4 changes the session fixture `excerpt_books` (section 6)
to run `main(["run", str(folder)])` once for each excerpt, so that the
excerpt tests of every stage read the files of one run. The configs:

- Kadesh: title "The Battle of Kadesh", authors ["J. H. Breasted"],
  language `en`, `cover_page = 0`, `exclude_pages = [9]` (the blank
  page with no text layer), `exclude_regions = [{page = 0, box = [240,
  620, 252, 632]}]`.
- Gierke: title "Political Theories of the Middle Age", authors ["O.
  Gierke", "F. W. Maitland"], language `en`, every other key at its
  default.

The tests that read the fixture assert, as literals:

- the tests of section 6 still pass;
- every file of architecture §5 but `edits/` exists, and
  `images/cover.png` only for Kadesh;
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
  Gierke words, the same multiset as the words of `words.json`, since
  nothing after extract removes a word; `note_count` 0;
- `book.epub`: as in section 8, with the cover image in the Kadesh one;
  epubcheck passes (marked `epubcheck`).

Other tests of this work package:

- `galley2epub` is an entry point of the installed package, and the
  script next to `sys.executable` runs `--help` with exit code 0;
- the stages run one by one through `main` on a fresh Kadesh folder give
  the same `blocks.json` and `book.md` bytes as `run` (marked
  `thread_unsafe`);
- `main(["layout", str(folder)])` on a folder with no `words.json` raises
  `InputFileError` naming extract; `main(["run", str(folder)])` with
  `correct = true` raises `ConfigError` before `pages.json` exists; a
  `words.json` from the other excerpt raises `InputFileError`.

## 10. The speed budget

analyze, extract and layout run per page with `parallel.py`, and their
output does not depend on the number of workers (the tests of sections 6
and 7). structure, markdown and epub run once.

`uv run pytest` must stay under 30 s (coding skill). A prototype that
does what sections 6 to 8 say ran the expensive tests of the skeleton in
4.8 s, on 14 November 2026, on an Apple M5 Pro (6 performance cores),
Python 3.15.0 free-threading, pdfplumber 0.11.10, pypdfium2 5.15.2,
Pandoc 3.13, 3 runs of 4.75 to 4.79 s: the session fixture on both
excerpts 1.5 s, analyze raising on Kadesh 0.3 s, the `exclude_pages =
[8, 9]` run 0.6 s, the 1-against-6-worker run 1.5 s, the stages one by
one 1.0 s. The unit tests, the Pandoc ones included, add tenths of a
second. The suite ran in 0.15 s before the skeleton. A test that runs a
stage on an excerpt reads the session fixture's folders when it can and
is marked `thread_unsafe` when it cannot, or the 8-thread run repeats it
8 times.

## 11. How the numbers were obtained

Every count, size and box of this spec comes from pdfplumber and
pypdfium2 run directly on the excerpts with `uv run python`, not from
galley's code, so the tests that assert them can fail. The lines are
those of the rule of section 7 applied to `page.extract_words()`, and
the Markdown round trip escaped the words as section 8 says, ran `pandoc
-f markdown-smart -t json --fail-if-warnings`, and compared word
multisets split as section 5 says. These pages have not been checked by
eye by the owner: they are counts, not reference pages.

## 12. Not in this spec

- `wordlist.py`, the correct stage, `galley2epub edits-from`, the index
  stage, OCR with Tesseract, figures cut from plates: later specs.
- Running heads, page numbers, signature marks, headings, quotes, margin
  notes, notes and hyphen joins: structure's spec.
- Columns, margins and reading order: layout's spec.
- The style sheet, the title page Pandoc adds, and a smaller cover: the
  epub spec.
- A stage that notices its input is older than the config (an
  `exclude_pages` added after analyze ran): not handled; the owner reruns
  from analyze.
