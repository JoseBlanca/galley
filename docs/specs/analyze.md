# The analyze stage: what each page is, and the pages without a text layer

analyze is the first stage of galley. It reads the PDF and the book
config (`book.toml`, architecture §6) and writes `pages.json`, which
gives every page a **kind** (`PageKind`: text, plate, blank, excluded,
front matter or inkless) and a **text source** (`TextSource`: where
extract takes its words from, the PDF's text layer, Tesseract, or
none). Until now analyze stopped the run on any page that has no text
layer and is neither excluded by the config nor a plate
(`docs/specs/walking-skeleton.md` §6), so that most whole books needed
the owner to list such pages in `exclude_pages` before they converted,
and `galley2epub run` on a bare PDF (architecture §14) failed on them.
This spec makes analyze read each such page with Tesseract and decide
from what Tesseract reads and from the ink on the page whether it is
blank, a page of text, or a picture. It is the first half of the OCR
audit that architecture §7b decided on 14 November 2026: every
printed page reaches the EPUB, and only a page with nothing printed is
left out, recorded as blank.

Dated 26 November 2026, for the plan `docs/plans/blank-pages.md`, which
the owner approved that day. It takes over analyze
from the walking skeleton: what this spec does not change is as
`docs/specs/walking-skeleton.md` §6 gives it (the page sizes, the
config checks of `check_config_pages`, the deletion of later files),
with the plate rule of `docs/specs/plates.md` §2 and §2b, the in-page
figures of `docs/specs/figures.md` §3 and the front matter of
`docs/specs/front-matter.md`, all of them built in
`src/galley/analyze/`. The formats
are those of architecture §8: no field is added, and `pages.json` stays
at its version.

The numbers were measured on 26 November 2026 on the five whole
public-domain books of `samples/public_domain/`, with Tesseract 5.5.4
and its English data on an M5 Pro: Kadesh
(`battleofkadeshst00breauoft`), Domesday (`domesdaybook00maituoft`),
Stubbs (`earlyplantagenet01stub`), Haskins (`normansineuropea00hask`)
and Gierke (`politicaltheorie00gieruoft`). Mariéjol, which the owner
dropped, was not measured. Page means page index, from 0, in the whole
book. Each page named was looked at by eye on its render.

## 1. Terms

- **Text layer**: the invisible words an OCR program placed over each
  page of the scan (architecture §1). A **page without a text layer** is
  one on which `text_layer.layer_words` finds no word.
- **Tesseract** reads an image of a page and gives words, each with a
  box and a **confidence** from 0 to 100, how sure it is of the word.
  galley calls it through `ocr.read_image` (architecture §12).
- **Text word**: a word Tesseract reads with a confidence of 70 or
  more that holds at least one letter or digit (`str.isalnum` on one of
  its characters). "Digitized", "2007" and "0" are text words when read
  at 70 or more; "=" is not, at any confidence. The other words
  Tesseract reads on an empty page are its readings of specks, stains
  and the grain of a board: **stray marks** of the scan.
- **Ink share**: the share of a page that is ink, measured on the page's
  render as §3 says. A page that holds only paper, its stains and
  another page faintly showing through has an ink share of 0.062% or
  less on the five books; a page that holds print, writing or a picture
  has 0.114% or more.
- **Plate**: a page that is mostly a picture, given to the reader as
  an image of the whole page (`docs/specs/plates.md`): extract renders
  it at 300 dpi and structure makes it a figure. Its words, if it has a
  text layer, are its caption.
- **Front matter**: the pages before the book's text, endpapers, title
  page, the library's labels, up to the **front-matter end**, the first
  page of the preface, of the contents or of running text
  (`docs/specs/front-matter.md` §2). Their words are dropped, each
  recorded as a **removal**: an entry of `words.json` with the word's
  page, box, text and the reason it was taken out (architecture §8).
- **Inkless page**: a page whose text layer holds words where nothing
  is printed (`docs/specs/plates.md` §2b); its words are removals.
- **`ocr`**, the config key, says how far galley trusts the book's own
  text layer (architecture §7b): `verify` (the default) reads the layer
  and re-reads poor small print with Tesseract; `trust` reads the layer
  and re-reads nothing; `redo` reads every text page with Tesseract
  instead of the layer. A page whose `text_source` is `ocr` is one
  extract reads with Tesseract.
- **The audit**: what this spec adds, analyze's reading of each page
  without a text layer with Tesseract and its measure of the page's ink.
  Architecture §7b names the whole audit; its other half, a sample of
  the pages with a layer scored against Tesseract, is not in this spec
  (§9).

## 2. Which pages the audit reads, and in what order

analyze decides a page's kind by these rules, in this order; the first
that applies decides:

1. A page in `exclude_pages` is `excluded` (walking-skeleton §6).
2. A page in `plate_pages` is a `plate` (plates §2).
3. A page the inkless rule takes is `inkless`, or `front_matter` before
   the front-matter end (plates §2b). The rule needs a text layer, so it
   never takes a page without one.
4. A page without a text layer on which the audit reads 40 text words
   or more is a page of text (§3, verdict **much text**), whatever the
   plate rule finds, unless it is the config's `cover_page`.
5. A page the plate rule takes is a `plate`, unless it is the config's
   `cover_page` (plates §2). For a page without a text layer, the plate
   rule's test is that the largest patch of faint ink on its 36 dpi
   render covers at least 0.34 of the page (measured in plates §2; the
   closest page taken is Kadesh 69 at 0.355, the closest left out
   Kadesh 72, a blank leaf, at 0.319).
6. A page with a text layer is `front_matter` before the front-matter
   end and `text` after it (front-matter §2).
7. Any other page without a text layer, but the config's `cover_page`,
   takes the audit's verdict (§3, §4).

So **the audit reads every page without a text layer** that is not
excluded, not in `plate_pages` and not the cover: on the five books, all
68. Rule 4 comes before the plate rule because the plate rule's test
for a page without a layer, a large patch of faint ink, takes a page of
running text too: rendered as if they had no layer, 26 ordinary text
pages of the five books cover 0.495 to 1.0 of the page (Kadesh 10:
0.863), all above its 0.34 (measured by the spec reviewer on 26
November 2026). Rule 4 needs 40 text words because Tesseract reads a
plate's picture and caption as words too: on the 21 plates of the
books (plates §1), with or without a layer, it reads 0 to 23 text words
(23 on Domesday's map 40, 18 on Stubbs' map 54); on 28 pages with a text
layer, the six shortest of 30 words or more of each book (31 to 271
words), the plate rule's test, run as if they had no layer, takes 10,
and on those Tesseract reads 26 (Gierke 288, a short page of back
matter), 44 (Kadesh 6), then 137 to 246 text words. A page of text
with 26 to 39 text words that the plate rule takes is kept as a plate,
an image of the page: the error that keeps the page, where the other
way a map read as text would lose its picture.

**The cover.** The config's `cover_page` is not audited. extract
renders it as `images/cover.png`, the EPUB's cover, so its print reaches
the reader whatever analyze says; the plate rule does not test it
either (plates §2). Without a text layer it is `blank` with
`blank_checked_by_ocr` false. The walking skeleton stopped on such a
cover as on any page without a layer; architecture §8 said the flag is
there so that a blank page is never a page nobody looked at, and now
adds that the cover is the exception, a page the owner named
(**Open 2**, below). `galley2epub run` on a
bare PDF writes no `cover_page`, so there the first page is audited like
any other.

**Where it runs.** analyze measures the pages in its worker threads
(`map_pages_with_source`, one pdfplumber document per worker), and a
worker that finds no text layer on a page the audit reads has the PDFium
thread render the page at 300 dpi (`pdfium.render` with `ocr.OCR_DPI`;
PDFium is not thread-safe and every call into it runs in that one
thread, architecture §12). The worker then runs Tesseract on the render
and measures its ink share. Tesseract reads the render as extract reads
an `ocr` page (`docs/specs/extract.md` §9): `ocr.read_image` with origin
(0, 0), page segmentation mode 3 (Tesseract finds the blocks of the
whole page), and the book's language
(`config.tesseract_language(config.language)`). The
same mode as extract's, not one meant for sparse text, so that extract
finds on the page the words the audit found: Tesseract gives the same
words for the same image, which was checked by reading each page of the
excerpt of §11 twice.

## 3. The rule

The audit gives each page it reads one **verdict**:

- **much text**, when Tesseract reads 40 text words or more on the page
  (rule 4 of §2: it overrides the plate rule);
- else **text**, when it reads at least one text word, on a page the
  plate rule does not take;
- else **picture**, when the page's ink share is 0.08% or more;
- else **blank**.

A page of numerals only, or of a name only, is not blank (architecture
§7b) when Tesseract reads one of them: "47" or "2007" read at 70 or
more is a text word. Tesseract does not always read a lone number: the
spec reviewer pasted the printed page number of 28 text pages of four
of the books onto a blank leaf of the same book, and Tesseract in mode
3 read none of them, while their ink was 0.006% to 0.065%, under the
threshold. Such a page, printing only its page number, is blank. Nothing
of the book's text is lost with it: structure removes page numbers
from every page (architecture §8, the removal reason `page_number`). A page with ink
that Tesseract cannot read as text, a faint picture, writing, a printed
line Tesseract misses, is a picture and not blank, so that the error
the rule can make is to keep a page that holds nothing, never to drop
one that holds print.

**The ink share** of a page is measured on the 300 dpi render Tesseract
read, 8-bit gray, in four steps:

1. The render is halved with `Image.reduce(2)` (each pixel the mean of
   two by two), to 150 dpi.
2. Its **background** is `ImageFilter.BoxBlur(20)` of the halved image:
   each pixel the mean of the square of radius 20 around it, 41 by 41
   pixels, about 20 pt a side.
3. A pixel is **ink** when it is at least 15 levels (of 255) darker than
   its background (`ImageChops.subtract(background, halved)`, 15 or
   more).
4. The ink share is the number of ink pixels over the number of pixels
   looked at: the halved image without a band of 8% of its width at the
   left and at the right and of 6% of its height at the top and at the
   bottom (`int(width * 0.08)` and `int(height * 0.06)` pixels).

Measuring against the page's own background, not one gray for the whole
page, keeps out what changes slowly across a page: a stain, the shadow
of the binding, another page showing through (Kadesh 72, 0.013%), the
gray of a board. Thin strokes, print, writing and the lines of an
engraving, are far darker than the mean around them. The bands at the
edges hold the dark rim of the scan and the scanner's background
(Kadesh 75, a gray board with a black strip down its right edge: 0.050%
with bands of 8% and 6%, 1.263% with bands of 4% and 3%).

| measure | value | from |
|---|---|---|
| text word | confidence 70 or more, with a letter or digit | measured: the stray marks of the 47 pages judged blank reach 51.7 (Kadesh 73's "7"); the page read with the lowest best word, Domesday 0's library label, has "2" at 86.9; the notices of Kadesh 1 and Gierke 4 read at 95 to 97 |
| ink share | 0.08% | measured: 0.062% at most on the 47 pages judged blank (Haskins 279, a dark board), 0.114% at least on a page that holds print (Haskins 10, "TO MY WIFE", a page with a text layer measured for the comparison) |
| halving, background, ink, bands | 150 dpi, 41 px, 15 levels, 8% and 6% | measured on the blank pages and on 26 pages with a text layer of 12 words or fewer: at 10 levels, or at 15 with a background of radius 4 or 8, a faint picture (Kadesh 23 or 69) falls under a blank page; at radius 12 the faintest print (Haskins 10) is 1.3 times the highest blank page, at radius 20 (chosen) 1.8 times (Haskins 10 against Haskins 279); 20 levels gives about the margin of 15; bands of 4% and 3% let the scanner's edge in (below) |
| render | 300 dpi | extract's, so that the audit and extract read the same image |

**The margins.** Tesseract: the highest stray mark on a page judged
blank, 51.7, lies 18.3 below the threshold, and the highest on any page
the audit read, 52.1 on Stubbs' cover (a picture by its ink), 17.9;
the best word of the printed page read worst, 86.9, lies 16.9 above it.
Ink: the highest blank page, 0.062%, is 0.78 of the threshold, and the
faintest print, 0.114%, 1.4 times it. Much text: 23 text words at most
on a plate, 26 on the page of text with the fewest that the plate rule
takes; the threshold of 40 keeps such a page a plate (§2).

Why Tesseract alone would not do, shown on a page that has a layer and
so is not audited: Gierke 9, which prints "First Edition, 1900 Reprinted 1913" in two
short lines, Tesseract in mode 3 reads no word at all, and the page's
ink share is 0.587%. Without its layer that page would be a picture by
the rule; by Tesseract alone it would be blank.

## 4. What each verdict writes

| verdict | `kind` | `text_source` | `blank_checked_by_ocr` | logged |
|---|---|---|---|---|
| much text or text, page before the front-matter end | `front_matter` | `ocr` | false | WARNING |
| much text or text, any other page | `text` | `ocr` | false | WARNING |
| text or picture on a page the plate rule takes | `plate` | `none` | false | WARNING, by the plate rule |
| picture | `plate` | `none` | false | WARNING |
| blank | `blank` | `none` | true | INFO |

Every page keeps `text_layer_score` `None` (§9), and `exclude_regions`
as on any page.

**A page of text.** Its text source is `ocr`, under every value of the
config's `ocr`, and extract reads it with Tesseract as it reads every
text page under `ocr = "redo"` (`docs/specs/extract.md` §9): the page
rendered at 300 dpi, every word Tesseract gives kept with its
confidence, stray marks too, for structure's rules to see. The rules of
extract §9 that take something from the layer (note references, missed
words, word heights, caption numbers) find no layer word and change
nothing. A front-matter page whose text source is `ocr` is read so too,
and each of its words is a removal with the reason `front_matter`
(`docs/specs/front-matter.md` §3), as the layer's words of any
front-matter page are. Until now a front-matter page always had the
source `none`; architecture §8 now says that one without a text layer
has `ocr` when the audit found text on it, because its words come from
Tesseract and must be read to be recorded. extract needs no new rule
for it.

For the front-matter rule (`docs/specs/front-matter.md` §2), such a page
is a text page whose words are all the words Tesseract read on it, and
whose topmost row is the first row `body_measures.group_rows` makes of
them. For the in-page figures (`docs/specs/figures.md` §3), the figure
search runs on its 36 dpi render with its text words in place of the
layer's words: its stray marks lie on the pictures and would cover
them. No page of the five books has both text Tesseract reads and a
picture, so this is not measured.

analyze logs at WARNING each page the audit makes text, with its number
of words and its first ten, and "add it to `exclude_pages` if it is not
the book's": on the five books these are the Internet Archive's notice
and two library labels (§5), which the owner may not want in the book.

**A picture.** A `plate` without a text layer, as one the plate rule
takes (plates §2): extract renders the whole page as its image, and the
page has no words. analyze logs it at WARNING with its ink share, its
number of Tesseract words and their highest confidence, and "add it to
`exclude_pages` if it is not one", as the plate rule logs the pages it
takes.

**A blank page.** No words; extract does not read it
(walking-skeleton §6). `blank_checked_by_ocr` true says that Tesseract
read the page and found no text word on it, and that its ink share is
under the threshold (architecture §8: a blank page is never a page
nobody looked at). The stray marks Tesseract read on it are not
recorded as removals. A removal records text of the book that a stage
took out, and these are not the book's text: none is a text word, and
the page has no ink a stroke of print would leave. They are also no
word of any file: removals live in `words.json`, which extract writes,
and extract does not read a blank page. analyze logs at INFO each blank
page, with its number of Tesseract words, their highest confidence and
its ink share, so that a reader of the log sees what was found there
(Kadesh 73: 26 words, the highest 51.7, ink 0.003%).

analyze ends with one line at INFO that counts the pages the audit read
and each verdict.

## 5. What the rule gives on the five books

The audit reads all 68 pages without a text layer. None has 40 text
words or more, so 9 are plates by the plate rule, as before: Kadesh 17,
35, 43, 57 and 69 (no text word) and Stubbs' maps 9, 11, 52 and 54 (4,
3, 6 and 18). The other 59 take the audit's verdict:

| book | without a layer | plates by the plate rule | text | picture | blank |
|---|---|---|---|---|---|
| Kadesh | 14 | 5 | 1 (page 1) | 1 (23) | 7 (2, 3, 70, 71, 72, 73, 75) |
| Domesday | 12 | 0 | 1 (0) | 2 (6, 557) | 9 (1, 2, 3, 5, 7, 38, 41, 554, 555) |
| Stubbs | 19 | 4 | 1 (343) | 1 (0) | 13 (2, 3, 4, 5, 8, 10, 53, 55, 338 to 342) |
| Haskins | 11 | 0 | 0 | 1 (0) | 10 (3, 4, 5, 7, 11, 15, 265, 274, 276, 279) |
| Gierke | 12 | 0 | 1 (4) | 3 (0, 287, 289) | 8 (2, 3, 5, 51, 283, 284, 285, 286) |
| all | 68 | 9 | 4 | 8 | 47 |

What those 59 pages hold, by eye, and what the rule makes of them;
each page is in one row:

| what the page holds | pages | verdict |
|---|---|---|
| a blank leaf: endpapers and blank leaves, with stains, specks or the next page showing through | 43 | blank, all 43 |
| a board of the binding with no print: Kadesh 70, 71, 75 and Haskins 279 (smooth boards); Domesday 557 and Gierke 289 (cloth) | 6 | blank 4; picture 2, the weave of the cloth (ink 5.375% and 0.595%) |
| a cover with a printed title or a library's label: Domesday 0, Stubbs 0, Stubbs 343, Haskins 0, Gierke 0 | 5 | text 2 (Domesday 0: "2" and "E" of its label; Stubbs 343: "0 020 690 469 0", its barcode's number); picture 3 |
| a reader's writing: Domesday 6 (notes in ink), Gierke 287 (pencil strokes) | 2 | picture 2 |
| print: the Internet Archive's notice, "Digitized by the Internet Archive in 2007 with funding from Microsoft Corporation" (Kadesh 1, Gierke 4); a relief printed faintly (Kadesh 23) | 3 | text 2 (12 text words each, of the 13 words Tesseract reads); picture 1 (ink 1.441%) |

Kadesh 23, which the plate rule misses and
the whole-book configs name in `plate_pages`, becomes a plate without
being named. The most stray marks are on Kadesh 73, a blank leaf (26
words, the highest 51.7), Domesday 557 (67 words on the cloth, the
highest 49.1) and Stubbs 0 (19 words on the cover, 52.1, the highest
stray mark of the 59 pages; the cover is a picture by its ink).

Kadesh 69 prints a running head, about five lines of text and a
photograph, and has no text layer. The plate rule takes it (0.355 of
its squares), and its lines reach the reader in the plate's image. They could not reach them as text: the scan of
those lines is blurred past reading, by eye as by Tesseract, which
reads no word on the page.

**Cost.** Rendering at 300 dpi took 0.155 s a page on the PDFium thread
(Domesday's 12 pages), so about 3 s for Stubbs' 19 pages; Tesseract
read all the pages without a layer of each of the five books in 1.0 s
or less with 8 threads, most of them being empty, and takes about 1 s
a page of text (extract §9); the ink share took 6
to 39 ms a page on the 68 pages.

## 6. Under `ocr = "trust"` and `ocr = "redo"`

The audit of the pages without a text layer runs under every value of
`ocr`, with the same rule and the same verdicts. Architecture §7b
already said so for `trust` ("pages without a layer are still checked
as in the audit"), so that trusting the book's OCR never drops a
printed page that the OCR missed. Under `redo` it said that analyze
calls Tesseract on no page and that a page without a layer is blank or
a plate as before; that changes (architecture §7b is amended with this
spec). Under `redo` analyze audits the same pages with the same rule.
Every `text` page has the source `ocr` under `redo`, as before, and a
text page the audit finds has `ocr` under every value, so `redo`
changes nothing for the pages without a layer. The sample of the pages with a
layer (§9) is what `trust` and `redo` skip, and `ocr_audit` is `None`
under all three.

## 7. Tesseract before analyze, and the messages that change

analyze now needs Tesseract on any book with a page the audit reads,
under every value of `ocr`. Which books those are is known only once
the PDF has been read, page by page. So `cli.py` checks that Tesseract
is on the PATH before the first stage whenever analyze is among the
stages it runs (`galley2epub analyze`, or `run`), whatever the config's
`ocr`, and stops with `ExternalProgramError` when it is not, before any
stage deletes or writes a file:

    tesseract is not installed; analyze reads the pages without a text
    layer with it: install it with `brew install tesseract`

This check comes before every other check cli makes for Tesseract or
its tools (the word list's tools, layout's Tesseract under `verify`,
extract's under `redo`), so that a run without Tesseract names analyze,
the first stage that needs it, and the program to install. Under
`verify`, the default, it costs nothing new: layout already needs
Tesseract. Under `trust`, a book whose word list is cached needed no
Tesseract until now, and now does, also when every page has a layer;
checking always is simpler than reading the PDF first, and Tesseract
is installed wherever galley has been run once on a new language. When analyze is called
without cli (a test, another program), `ocr.read_image` raises
`ExternalProgramError` on the first page the audit reads, before
`pages.json` is written; the later stages' files are already deleted
then, as on any failed run of analyze.

The other messages:

- The `PdfError` "page indices …: these pages have no text layer, and
  the walking skeleton has no OCR; add them to `exclude_pages` once you
  have checked that they hold no text" goes, with
  `require_text_layer`, which raised it. A page without a text layer no
  longer stops the run.
- cli's message under `redo` names extract only when analyze is not
  run: 'tesseract is not installed; with ocr = "redo" extract needs it,
  as extract reads every text page with it: install it with `brew
  install tesseract`'.

## 8. Cases

- **A page of numerals only or a name only**: text, if Tesseract reads
  one of its words at 70 or more; else a picture, if it has ink; else
  blank (§3).
- **A page that prints only its page number**, which Tesseract misses:
  blank (§3); structure would remove the number anyway.
- **A page of running text without a text layer**: text, by its 40
  text words or more, although the plate rule's test takes it (§2,
  rule 4). No page of the five books is one; the test of §11 makes one.
- **A library label on a cover** (Stubbs 343, Domesday 0): text.
  Domesday 0 is front matter in the PDF form of `run` and its words
  are removals; Stubbs 343 is the book's last page, and its words, "0 020 690
  469 0" and a stray "Ae" (all of Tesseract's words are kept, §4), end
  the book's text unless the owner excludes the page
  (**Open 1**, below).
- **A cover or a cloth board with no text Tesseract reads** (Stubbs 0,
  Haskins 0, Gierke 0, Domesday 557, Gierke 289): a plate, logged, its
  image in the EPUB (**Open 1**).
- **A reader's writing or pencil strokes** (Domesday 6, Gierke 287): a
  plate, logged; Tesseract reads no word of Domesday 6's handwriting.
- **A faint picture the plate rule misses** (Kadesh 23): a plate.
- **A blank leaf with the next page showing through** (Kadesh 72): blank
  (ink 0.013%).
- **A blank leaf on which Tesseract reads stray marks** (Kadesh 73):
  blank.
- **The config's `cover_page` without a text layer**: not audited,
  `blank`, `blank_checked_by_ocr` false (§2).
- **An excluded page without a text layer**: not audited; `excluded`,
  as now.
- **A page the audit makes text, on which extract's Tesseract reads no
  word**: does not occur, since extract reads the same render in the
  same mode and language. `docs/specs/extract.md` §9, which said that a
  text page always has a layer, now says so.

## 9. Left out: the sample of the pages with a text layer

Architecture §7b's audit has a second half: a sample of pages with a
text layer, each scored by the share of its words found in the word
list, the layer's reading against Tesseract's, and a stop with
`PdfError` when the layer scores clearly worse. It is not in this spec
and not in the plan. So, as the walking skeleton left them,
`text_layer_score` is `None` on every page, `ocr_audit` is `None` in
every `pages.json` whatever `ocr` is, and a book whose layer is poor
throughout is read from that layer unless the owner sets `ocr =
"redo"`.

## 10. The public interface

The functions the pipeline and the tests call. `run` and
`check_config_pages` are as in the walking skeleton; `classify_page`
takes the audit's verdict; `require_text_layer` goes.

```python
# galley.analyze
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

class AuditVerdict(StrEnum):
    """What the audit found on a page it read (analyze spec §3), or
    NOT_AUDITED for a page it does not read."""
    MUCH_TEXT = "much_text"
    TEXT = "text"
    PICTURE = "picture"
    BLANK = "blank"
    NOT_AUDITED = "not_audited"

def ink_share(page: RenderedPage) -> float: ...
    # The share, from 0 to 1, of the page that is ink (§3); `page`
    # rendered at 300 dpi.

def audit_verdict(words: tuple[Word, ...], ink: float) -> AuditVerdict: ...
    # MUCH_TEXT, TEXT, PICTURE or BLANK by the rule of §3, given every word
    # Tesseract read on the page and its ink share, from 0 to 1.

def classify_page(
    index: int, width_pt: float, height_pt: float, layer_word_count: int,
    config: BookConfig, *, plate_rule: PlateRule, ink_rule: InkRule,
    audit: AuditVerdict, front_matter_end: int,
) -> PageInfo: ...
    # By the order of §2 and the table of §4.

def check_config_pages(config: BookConfig, page_count: int) -> None: ...
```

## 11. How it is verified

**The excerpt `kadesh_blank`**, committed under `tests/fixtures/pdf/`
and cut by `scripts/fetch_samples.py`: Kadesh pages 1, 2, 3, 23, 69,
70, 71, 72, 73 and 75, every one of them without a text layer
(pdfplumber finds no word and no character on any of the ten). The
assistant classified each page by eye on its render (§5). The test
runs analyze and extract on it with a config of only `pdf`, `title`,
`authors` and `language`, as `galley2epub run` writes for a bare PDF;
in the excerpt the front-matter end is 0 (its only text page is the
first page of running text by front-matter §2), so no page is front
matter.

| excerpt page (book page) | what it holds | expected `kind`, `text_source`, `blank_checked_by_ocr` | measured: text words, highest confidence, ink share |
|---|---|---|---|
| 0 (1) | the Internet Archive's notice | `text`, `ocr`, false | 12, 96.9, 1.178% |
| 1 (2), 2 (3) | blank endpapers | `blank`, `none`, true | 0, none, 0.031% and 0.010% |
| 3 (23) | a faint relief | `plate`, `none`, false | 0, none, 1.441% |
| 4 (69) | a photograph under blurred text | `plate`, `none`, false, by the plate rule | 0, none, 0.254% |
| 5 (70), 6 (71), 9 (75) | boards of the back cover | `blank`, `none`, true | 0, none, 0.001%, 0.039% and 0.050% |
| 7 (72) | a blank leaf, the next page showing through | `blank`, `none`, true | 0, none, 0.013% |
| 8 (73) | a blank leaf with 26 stray marks | `blank`, `none`, true | 0 of 26, 51.7, 0.003% |

and in `words.json`: excerpt page 0 has the source `ocr` and Tesseract's
13 words, the first 12 "Digitized by the Internet Archive in 2007 with
funding from Microsoft Corporation", as the page prints them, then the
link, which Tesseract misreads; the
expected text goes into `tests/fixtures/expected/blank_pages/`, read by
eye from the page; the blank pages have no words and no removal; pages
3 and 4 have one figure each, the whole page, and no words. analyze
logs WARNING for excerpt pages 0 and 3 by the audit (and 4 by the
plate rule), INFO for each of the seven blank pages. analyze with 1 worker and with 6 gives byte-identical
`pages.json`.

**Unit tests**, with values made in the test:

- `audit_verdict`: Kadesh 73's words as literals (the highest "7" at
  51.7) with ink 0.00003 give BLANK; the same with ink 0.0008 give
  PICTURE, and with 0.00079 BLANK; one word "TO" at 96 gives TEXT
  whatever the ink; "2" at 86.9 gives TEXT; "=" at 86 and no other
  word, ink 0, gives BLANK; "E" at 70.0 gives TEXT and at 69.9 not;
  40 text words give MUCH_TEXT and 39 TEXT.
- `ink_share`, on `RenderedPage` values at 300 dpi of 2000 by 3000
  pixels: a white page gives 0; a page whose gray darkens smoothly from
  255 at the top to 200 at the foot gives 0; a white page with black
  lines 2 pixels high across its middle gives the share of their pixels
  after halving, within a few percent of it; the same lines inside the
  left band of 8% give 0.
- `classify_page` with each verdict and each `ocr` value: TEXT at an
  index at or past `front_matter_end` gives `text`, `ocr`; before it
  `front_matter`, `ocr`; MUCH_TEXT with the plate rule taking the page
  gives `text`, `ocr`, and TEXT with it gives `plate`, `none`; PICTURE
  gives `plate`, `none`; BLANK gives
  `blank`, `none`, `blank_checked_by_ocr` true; NOT_AUDITED with no
  layer word (the cover) gives `blank`, `none`, false; a page in
  `exclude_pages` stays `excluded` whatever the verdict.
- cli: with a PATH that lacks `tesseract` and its tools, `galley2epub
  analyze` on a book folder under `ocr = "trust"`, with the word list
  cached and without it, raises `ExternalProgramError` with the message
  of §7, and the folder's files are untouched.

**A page of running text without a layer**, made in the test: excerpt
page 1 of `kadesh_8-17` (Kadesh 9, a page of text and footnotes)
rendered at 300 dpi and saved by Pillow as a one-page PDF, which has no
text layer. analyze makes it `text`, `ocr`, by rule 4 of §2, though the
plate rule's test takes it; extract gives it Tesseract's words.

**A `whole_book` test**: analyze on each of the five books with a
config of only `pdf`, `title`, `authors` and `language`; the kinds of
the 68 pages without a text layer are those of §5's first table, the
verdict text giving `front_matter` on the three pages that lie before
the front-matter end the rule finds (Kadesh 1, end 8; Domesday 0, end
12; Gierke 4, end 12) and `text` on Stubbs 343; each page made blank
has `blank_checked_by_ocr` true. The
whole-book configs of `tests/conftest.py` stay as they are: they
exclude these pages, so their tests do not change.

**The fidelity check** (architecture §13) is unchanged: every word of
an `ocr` page is a word of `words.json` or a removal; a blank page and a
plate without a layer have none. The stray marks of a blank page are in
no file, and the INFO line of §4 counts them.

## 12. Open points

1. **Covers, boards and library labels.** The rule keeps every page
   with ink: on the five books it makes 5 covers or cloth boards and 2
   pages of a reader's writing into plates, whose images the EPUB
   shows, and reads 2 library labels as text, one of which (Stubbs 343,
   "0 020 690 469 0") ends the book's text. The options: (a) as
   specified, each such page logged at WARNING and left in the book
   until the owner excludes it; (b) drop a picture page found by the
   audit among the first and last few pages of the PDF as front or back
   matter, which would drop the cover of a book that has no
   `cover_page` and needs a rule for where the back matter starts,
   measured on no book yet. Recommended: (a), because its error is a
   page too many, which the owner sees in the log and in the EPUB and
   removes with one line of `exclude_pages`, where (b)'s error is a page
   lost. Meanwhile, (a).

2. **The cover without a text layer.** The config's `cover_page` is
   not audited and is `blank` with `blank_checked_by_ocr` false (§2).
   Architecture §8 gives the flag "so that a blank page is never a page
   nobody looked at", and now names the cover as the one exception. The
   options: (a) as specified, the cover a blank page that the owner
   looked at; (b) audit the cover and, when it holds ink, give it a new
   kind, `cover`, which changes the format of `pages.json` for every
   stage that reads it. Recommended: (a), since the cover's picture is
   in the EPUB either way and no reader sees the difference. Meanwhile,
   (a).

## 13. Not in this spec

- The sample of the pages with a text layer, `text_layer_score` and
  `ocr_audit` (§9): architecture §7b, later.
- Pages whose text layer is poor: `ocr = "redo"` (architecture §7b,
  `docs/specs/extract.md` §9).
- How extract reads an `ocr` page: `docs/specs/extract.md` §9,
  unchanged.
- The plate, inkless, figure and front-matter rules: their own specs.
- The README's list of what galley cannot do yet, and the whole-book
  runs through the PDF form of `run`: the plan's work package 2.
