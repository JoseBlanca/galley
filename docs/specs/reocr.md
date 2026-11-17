# Re-reading small print with Tesseract

galley takes the words of a scanned book from the PDF's text layer, the
invisible words an OCR program placed over each page image when the book
was scanned (architecture §1). In small print that layer is often poor
while the scan itself is sharp: in 30 of Gierke's margin notes the layer
has 52 of 139 printed words right and Tesseract, run by galley on the
same notes, 133. This spec says which small print galley reads again with
Tesseract, how it decides, region by region, that Tesseract's reading is
the better one, which stage does it, how the words it replaces stay
accounted for, how it runs, and how it is verified.

Dated 17 November 2026. The owner approved re-reading small print where
the scan is good and the layer poor (in chat, before this spec), and
decided that no effort goes to unreadable scans such as Mariéjol's: the
re-reading is not aimed at them, and on a page where Tesseract reads
worse than the layer no word may be lost. No code of it exists. It
builds on `docs/architecture.md` ("architecture §8"), `docs/glossary.md`
and the layout spec (`docs/specs/layout.md`, "layout §3"), and assumes
the change to extract specified in parallel: extract reads characters in
the PDF's order (pdfplumber's `use_text_flow=True`) and splits words
glued together by the gap between their characters. Every measurement
below was taken on the layer as extract reads it today, before that
change (section 9 says what is measured again).

What it decides, in short: the **layout** stage re-reads four kinds of
text, each region on its own, and keeps Tesseract's words for a region
only when they score higher than the layer's by a count of dictionary
words; it records every region it read, with both readings, in
`lines.json`, and the fidelity check of layout counts the replaced words.

## 1. Terms

Besides those of the glossary:

- **Re-reading**: rendering a part of a page at 300 dpi and reading it
  with Tesseract, then keeping, for that part, either the layer's words
  or Tesseract's.
- **Region read**: the part of a page that is re-read as one, and on
  which the choice between the two readings is made: one printed margin
  note, one cut-in note, one page's footnote band, or a whole page.
- **Page segmentation mode** (psm): Tesseract's setting for what an image
  holds. Mode 3 finds columns and blocks on a whole page; mode 6 reads
  the image as one block of lines of the same type.
- **tsv output**: Tesseract's table of what it read, one row per word
  with its box in pixels, its confidence (0 to 100) and the numbers of
  its block, paragraph and line.
- **Known word**: a word `wordlist.is_known_word` accepts (architecture
  §12): its key has at least 2 letters and is in the word list of the
  book's language, or it is a number. A typographic apostrophe, "’", is
  taken as "'" first, because the word list writes "henry's" and
  Tesseract writes "Henry’s"; without that, the rule below rejects 78
  of Stubbs' 417 regions instead of 65.
- **Unknown word**: a word that holds a letter or a digit and is not
  known. A word of punctuation only is neither.
- **Reading score** of a set of words: known words minus unknown words.
- **Single-letter share** of a page: among the keys of its words
  (`wordlist.word_key`) that are not empty, the share made of one letter
  that is not a word of one letter of the book's language (English a, i,
  o; French a, à, y), as the evaluation tool counts it
  (`docs/specs/evaluation.md` §8).
- **Scrambled page**: a page whose layer holds at least 50 such keys and
  whose single-letter share is at least 0.20 (section 3).

The books are those of the evaluation set (Haskins, Stubbs, Domesday,
Mariéjol; `docs/specs/evaluation.md` §3) and of the excerpts (Kadesh,
Gierke). Page numbers are page indices of the whole PDF, from 0.
Measurements were taken on 17 November 2026 on a Mac17,9 with 18 cores
(6 performance, 12 efficiency), Tesseract 5.5.4 with its `eng` data,
pypdfium2 5.15.2, galley at commit 4542207, 6 worker threads unless
said; Gierke's on 16 November 2026 on the same machine.

## 2. What the books show

**Margin notes**, read by eye against the page image: a word is right
when its letters are (case and punctuation ignored); a word broken over
two lines counts once and is right only when both parts are; two words
read as one are both wrong.

| book | notes, how chosen | printed words | layer right | Tesseract right |
|---|---|---|---|---|
| Gierke, outer notes | 30, spread over pages 86–185 (16 November) | 139 | 52 (37%) | 133 (96%) |
| Stubbs, cut-in notes | 46 crops of the cut-in zones of 40 pages spread over the book, the note words wholly inside each crop | 126 | 29 (23%) | 123 (98%) |
| Domesday, outer notes | 25 notes on the 18 pages with notes among 24 pages spread over 22–552 | 113 | 56 (50%) | 102 (90%) |

What the layer does to these notes: it spaces a word out into letters
("M e s s in a ." for "Messina.", Stubbs page 141), glues words
("revoltofthe", page 124), drops lines ("Moral" for "Moral lessons.",
page 22), and garbles ("JK^L" for "March of the barons.", page 178).
Tesseract's errors in the same notes: a misread letter ("tiseal" for
"fiscal", Domesday page 415), two words glued ("towitesand", page 300),
a date read as letters ("LIQI" for "1191", Stubbs page 141), and junk
from a pencil mark, a tick or the edge of a body line beside the note
("~", "Sy AM").

**Stubbs' index** (pages 312–321), scored by the evaluation tool against
the Gutenberg edition after a whole-page re-read with psm 3 (section 9
has the run): the index's token error rate at blocks goes from 1.543
(galley gives 11,620 tokens against the reference's 4,750, most of them
single letters) to 0.096, and the precision and recall of its entry
boundaries from 0.829 / 0.789 to 0.983 / 0.953. Of the 6,865 differences
the structure-second report counts on these pages, 94% came from the
layer as read.

**Footnotes** read better too, but their markers do not
(section 9 has the runs):

| book | note tokens matched, before → after | note error rate at blocks | notes whose reference is right |
|---|---|---|---|
| Domesday | 43,296 → 44,965 of 48,985 | 0.101 → 0.081 | 1,277 → 1,140 |
| Haskins | 376 → 554 of 658 | 0.404 → 0.141 | 59 → 56 |

Tesseract reads Haskins' superscript markers as digits where the layer
has "^" and "*", but on Domesday it reads a marker together with the
next word ("3D.", "1K.") or as a symbol ("®" for "3"), and then
structure finds no marker to start the note at or to link. That is why
footnotes are re-read only when the book's config asks (section 3 and
**Open 1**).

**Body text** is not re-read. ocr_lab found the scanner's layer better
than a fresh Tesseract run on 19th-century roman type in all three of
its control books (architecture §7b), and re-reading every page would
cost a full-page Tesseract run per page: 0.61 to 0.88 s per page on
Stubbs' index pages, in one thread.

## 3. What is re-read, and the rule that picks it

Four kinds of region are read. For each region read, galley computes the
reading score of the layer's words that the region replaces (section 4
says which) and of Tesseract's words, and **keeps Tesseract's words only
when their score is higher**; on a tie, or lower, the layer's words stay.
The choice is made per region, so that a page where Tesseract reads one
note worse keeps the layer for that note and loses no word, and a
book that Tesseract reads worse throughout keeps its layer throughout.

The rule was measured against two others on Stubbs (cut-in notes and
index), counting the reference's margin-note words found in galley's
margin notes, each reference note matched to the galley note sharing
most of its words, each galley word used once (a research script; the
evaluation tool has no such score yet, section 10):

| rule | regions where Tesseract's words are kept | margin-note words right, of 1,908 | body error rate at blocks |
|---|---|---|---|
| none (the layer) | 0 | 357 | 0.142 |
| always Tesseract | 417 of 417 | 1,115 | 0.126 |
| Tesseract when it has more known words | 336 of 417 | 1,067 | 0.128 |
| Tesseract when its reading score is higher (chosen) | 351 of 417 | 1,100 | 0.126 |

Counting known words alone rejects regions where the layer spaced a note
into letters ("S Bl t o e i p s h . en of" against "Stephen of Blois.",
page 31, both with 3 known words, since the word list holds "bl" and
"en"); subtracting unknown words takes them. The chosen rule keeps the
layer where Tesseract read nothing ("accordance" against nothing, page
152), dropped words ("doctrine of Conquest." against "Conquest.", page
248), or read a body line as junk. On Gierke it kept the layer on 53 of
the 233 page sides read; in the 25 of them read by eye the layer was
the better reading or both were nothing worth keeping: the numbered lists of the notes' contents (pages
61 to 80, "PAGE 192 193 193…" against "16 I 136. F a 138. C") and
pencil marks.

The four kinds, each with what is cropped and how it is read:

1. **A scrambled page** is read whole: rendered at 300 dpi, psm 3.
   Single-letter shares over the pages of 50 keys or more:

   | book | pages at 0.20 or more | highest below 0.20 |
   |---|---|---|
   | Stubbs | the 10 index pages, 312–321 (0.239 to 0.634) | 0.186 (page 106) |
   | Domesday | 136, 92, 481, 428 (0.498 to 0.256) | 0.185 |
   | Gierke | 63, 65 (contents lists) | 0.132 |
   | Kadesh | 61 | 0.191 |
   | Haskins, Mariéjol | none | 0.096; Mariéjol 0.189 |

   The score rule then took all 10 of Stubbs' pages, Domesday's 136, 92
   and 481 (on 481, prose beside a table that the layer spelled out
   letter by letter) and left 428 (a table of
   figures that Tesseract read as "HKOoOOrFOOOHKFHrFrF"); it took Gierke's
   63 and 65 and Kadesh's 61. Mariéjol's highest page, 0.189, is close
   to the threshold; the owner's decision leaves it alone, and when it
   is a candidate the score rule decides as on any page. The threshold
   0.20 is set from this table: it takes every index page of Stubbs and
   no page of the two books with the cleanest layers.

2. **Outer margin notes**, on each side of the book that has them: a
   side has them when at least 10% of the book's pages with 50 words or
   more have at least 2 known words among that side's margin words
   (layout §3, step 2). Measured, pages with 2 known margin words, left
   and right: Gierke 97 and 88 of 271, Domesday 152 and 160 of 538;
   Haskins 0 and 0, Stubbs 0 and 1, Mariéjol 0 and 3, Kadesh 0 and 0.
   On every page whose column layout places, galley crops that side's
   **strip**: from 4 pt inside the page's edge to 4 pt outside the
   column's edge, and from 4 pt above the top of the column's first
   word to 4 pt below the page's lowest word. In the strip it finds the
   **note bands** by rows of ink, as the Gierke measurement did: a pixel
   is ink below 140 (of 255); a pixel row with more than one ink pixel
   is inked; inked rows separated by at most 18 px (4.3 pt) of blank rows
   are one band; a band less than 12 px high, with fewer than 150 ink
   pixels, or less than 25 px wide is a speck or the scan's edge, and
   dropped; each band is cropped to its ink plus 6 px and read with psm
   6. Each band is a region read. Read as one strip with psm 6 instead,
   Domesday's notes came out as junk ("!@ J , } j" for a whole page side,
   page 71): the empty strip and the clipped ends of body letters
   confuse Tesseract's line finding.

3. **Cut-in notes**, on each side where the book has a cut-in inset
   (layout §3, "The book's measures"; only Stubbs): each cut-in zone of
   layout §3 step 2b, widened by 2.5 body line pitches above and below,
   and from 3 pt outside the column's edge to 3 pt short of the inset
   (on the left, from L − 3 to L + I − 3 pt), read with psm 6. Zones
   whose widened crops overlap are read as one crop. The zone alone
   clips notes, since layout trims it to its shortened rows ("Importance"
   without its second line "of Eng-", page 22). Measured with
   Tesseract's words always kept and an earlier form of the replacement
   of section 4: with the zone widened by half a pitch, 980 of the
   reference's 1,908 margin-note words were right; by 2.5 pitches,
   1,113; by 4.5, 1,095. The widened crop holds
   pieces of the full body lines above and below the note, so a line of
   Tesseract's output (its block, paragraph and line numbers) is dropped
   when one of its words ends within 3 pt of the crop's side toward the
   inset: a body line runs on past it, a note line stops 4 pt short of
   it (layout §3, step 2b). A whole strip down the column's side, with
   the body lines blanked where ink touches the inset, was tried and
   dropped: it made 2,062 margin notes of Stubbs' 467, and would replace
   the layer's body words that lie in the strip.

4. **Footnote bands**, only when the book's config has
   `reread_footnotes = true` (**Open 1**): the words of the page's
   footnote band (layout §3, step 4) cropped from 3 pt outside the
   column's left edge to 3 pt outside its right edge and from 3 pt above
   the band's highest word to 3 pt below its lowest, read with psm 6.
   One region per page.

Nothing else is re-read: not the body, not an index whose layer is not
scrambled (Haskins' index error rate is 0.270 at blocks; of its 3,047
reference tokens, 284 are glued, 219 missing and 154 differ in
punctuation, and the parallel change to extract splits glued words; a
re-read of it was not measured), not Stubbs' chapter summaries.

The config's `ocr` key (architecture §7b) turns it off: with `ocr =
"trust"` layout re-reads nothing, so that a book whose owner trusts its
layer, or a run that must be fast, has no Tesseract in layout. With
`verify`, the default, it re-reads as above; with `redo`, every page is
already Tesseract's, and layout re-reads nothing.

## 4. Which stage, and how words are replaced

**layout does it**, because layout is where the regions are known: the
margins, the cut-in zones, the footnote band. A stage after it would
need these written into `lines.json`, which says nothing of what a
region is (architecture §8); a stage before it would have to find them
again. Doing it in layout also keeps `words.json` the text layer as
read, so that one run of the evaluation tool shows the layer at its
`words` output and the re-reading at `lines`.

layout then reads, besides `pages.json` and `words.json`, the PDF,
through `pdfium.render`, and the config, for `ocr`, `reread_footnotes`
and the language; it runs Tesseract and uses the word list. It writes
`lines.json` as before, with one new field (section 6).

The order inside layout, around the steps of layout §3:

1. **Scrambled pages first.** Before the book is measured, each
   scrambled page is read whole; when Tesseract's words are kept, they
   are the page's words for everything after, the measures included.
   On Stubbs this changes 10 of 344 pages; the measures are medians over
   the pages, so 10 pages move them little, but the order is fixed so
   that the output does not depend on it.
2. **The book's measures**, as layout §3, then the outer-margin sides of
   the book (section 3).
3. **Per page**, layout §3's steps, with the re-reading inserted where
   each step has found its words: after step 2 the outer margin bands,
   after step 2b the cut-in zones, after step 4 the footnote band. The
   words kept from a region go to the same group the replaced words were
   in (that side's margin words, that side's cut-in words, the band),
   and the later steps group them into lines and regions as they group
   the layer's.

**The words a region replaces** are:

- for a whole page, all its words;
- for a note band, the words of that side's margin (layout §3, step 2)
  whose vertical middle lies within the band's top and bottom, whatever
  their horizontal place;
- for a cut-in crop, the words layout §3 step 2b took out of the column
  as cut-in words whose middle lies in the zones the crop was made from;
- for a footnote band, the band's words;

and in every case also every word of the page, wherever layout had put
it, whose middle lies inside the box of one of Tesseract's kept words
widened by 1 pt: it is the same printed word read twice, typically the
layer's single letters of a note that layout left in the body ("G ca e l
og s r u a m p" beside "Geographi- cal sum- mary.", Stubbs page 23). A
body word never lies inside a note word's box, so the body keeps its
words: an earlier form that replaced every word in the crop lost body
words ("Republican north", Stubbs page 24).

**Tesseract's words** become `Word`s with:

- the text of the tsv row, stripped of spaces;
- a box in points: the left and right of the word's pixel box, and the
  top and bottom of its tsv line's box, divided by 300/72 and moved by
  the crop's place on the page. The line's height, not the word's,
  because the text layer gives each word the height of its OCR line
  (architecture §1), and layout's row and band rules were measured on
  such heights. (The measurements of section 9 used each word's own
  box; the plan measures again with line heights.)
- `ocr_confidence`, the tsv confidence, a float from 0 to 100; the
  layer's words keep `None`;

in Tesseract's order: block, paragraph, line, word. No word of
Tesseract's is dropped for a low confidence (**Open 2**).

**The record.** Every region read is a `Reread` in `lines.json`, whether
its words were kept or not (a change to a shared format, **Open 3**):

```python
class RereadKind(StrEnum):
    PAGE = "page"                     # a scrambled page, read whole
    MARGIN_NOTE = "margin_note"       # one note band of an outer margin
    CUT_IN_NOTE = "cut_in_note"       # one cut-in crop
    FOOTNOTE_BAND = "footnote_band"   # one page's footnote band

@dataclass(frozen=True, slots=True)
class Reread:
    page_index: int
    kind: RereadKind
    box: Box                          # the crop, in points
    layer_words: tuple[Word, ...]     # the words it replaces (section 4)
    ocr_words: tuple[Word, ...]       # Tesseract's, as above
    layer_score: int
    ocr_score: int
    kept: bool                        # ocr_score > layer_score
```

A region where both readings are empty is not recorded. `LinesFile`
gains `rereads: tuple[Reread, ...]`, in page order and, within a page,
in the order above (page, margin bands top to bottom with the left side
first at the same top, cut-in crops likewise, footnote band). Measured
sizes: Stubbs 417 records, Domesday 451 (margins only), Gierke 233.

**The fidelity check** at layout's boundary becomes: the words of
`words.json`, minus the `layer_words` of every kept `Reread`, plus their
`ocr_words`, equal the words of `lines.json` as multisets, compared as
strings (architecture §13); and the `layer_words` of each kept `Reread`
are words of its page in `words.json`, so that a record cannot name a
word the layer never had. Every word of the layer is then either in
`lines.json` or in a kept record, with its page and box; a record not
kept changes nothing.

## 5. How Tesseract is called

One module of the package root, `ocr.py`, calls Tesseract, for layout
now and for analyze's audit and extract's OCR pages later (architecture
§7b). It is adapted from ocr_lab's `tesseract_words`
(`lib/common.py`), as the coding skill asks, without its cache:

- `tesseract stdin stdout --psm <n> -l <code> tsv`, the PNG of the crop
  on standard input, with `OMP_THREAD_LIMIT=1` in the environment, so
  that one Tesseract uses one core and the parallelism is galley's;
  `check=True` and a timeout of 120 s (guessed: 10 times the slowest
  whole page measured, 0.88 s, with room for a slow machine).
- Inherited from ocr_lab: a missing language model, or a Tesseract that
  prints plain text, exits with 0; output that does not start with the
  tsv header `level\t` is an `ExternalProgramError` naming the program,
  the language and the start of its error output, never a reading with
  no words.
- Only rows of level 5 (words) with text that is not blank are words; a
  row of level 4 gives its line's box.
- The language is `config.tesseract_language(config.language)`.

Tesseract's output does not depend on how many run at once: Stubbs'
417 regions read with 1 worker and with 12 gave byte-identical records.

## 6. The public interface

```python
# galley.ocr

OCR_DPI: Final[int] = 300

def read_image(image: Image.Image, *, origin: tuple[float, float], dpi: int,
               psm: int, language: str) -> tuple[Word, ...]: ...
    # Tesseract's words of `image`, a crop whose top left lies at `origin`
    # on the page, in points, with boxes in points (section 4).

def words_of_tsv(tsv: str, *, origin: tuple[float, float], dpi: int) -> tuple[Word, ...]: ...
    # The pure part of read_image: the words of Tesseract's tsv output.
```

```python
# galley.layout, besides layout §4's functions

def reading_score(words: Iterable[Word], lower_case_words: frozenset[str]) -> int: ...
def is_scrambled(words: tuple[Word, ...], language: Language) -> bool: ...
def note_bands(strip: Image.Image) -> tuple[tuple[int, int, int, int], ...]: ...
    # The note bands of a margin strip, as pixel boxes (section 3, kind 2).
```

`layout_page` takes the page's renders through a function it is given,
so that its tests can pass a fixed image and no PDF; `run` gives it one
that calls `pdfium.render` at 300 dpi. `run` keeps its signature
(architecture §9). The new config key, in `config.py` and architecture
§6:

| key | type, default | meaning |
|---|---|---|
| `reread_footnotes` | bool, `false` | whether layout re-reads each page's footnote band (section 3, **Open 1**) |

## 7. How it runs

layout works page by page in worker threads, as now (layout §5). A
page with a region to read asks the one PDFium thread for a render of
the whole page at 300 dpi (`pdfium.render`), turns it into a Pillow
image in the worker, crops it, and runs Tesseract as a subprocess per
region; workers wait on their subprocesses in parallel. A cropped render
would save little: PDFium took 0.079 s per Domesday page for a 60 pt
strip against 0.102 s for the whole page (40 pages, 100–139). The
renders are made one at a time, so they bound the time:

| book | pages | regions read | Tesseract calls | renders, one thread | re-reading in all, 6 workers |
|---|---|---|---|---|---|
| Stubbs (cut-in notes, index) | 344 | 417 | 418 | 25.3 s | 27.8 s (40.8 s with 1 worker, 28.8 s with 12) |
| Domesday (outer margins) | 558 | 451 with words | 638 | 63.7 s | 64.9 s |
| Gierke (outer margins) | 290 | 233 with words | 772 | 50.7 s | 51.4 s |

These times are the re-reading alone; layout without it took 2.5 s on
Domesday (layout §5). A book with nothing to re-read (Haskins and
Mariéjol without `reread_footnotes`) renders nothing and costs nothing.
Pages are rendered whole, once each, only when they have a region; the
note bands of a margin are found in the render, so every page whose
column is placed is rendered in a book with outer margin notes.

The output does not depend on the number of workers: the scrambled pages
are decided before the measures, each page's regions use only its own
render and the book's measures, and Tesseract's output does not depend
on what runs beside it (section 5).

## 8. Cases

- **A pencil mark, a tick, a stain in the margin** is a band (7 of 30 of
  Gierke's sample were). Tesseract reads it as short junk ("id i ;"),
  the layer has nothing there, the score is negative, and the layer's
  nothing is kept. Junk beside a real note ("~" after "The Hilde-",
  Stubbs page 83) is kept with the note when the note wins (**Open 2**).
- **A note the layer did not read at all** ("Medieval Thought.", Gierke
  page 88; "Fall of Bristol.", Stubbs page 308): the region replaces no
  word, Tesseract's words score above 0, and they are kept.
- **A list of numbers in a margin** (Gierke's contents, pages 61–80):
  Tesseract reads the column of page numbers worse, the score keeps the
  layer.
- **A hyphen at a line end** stays a word's last character in both
  readings ("satel-" "lites."), and structure joins it (structure §5).
- **Two notes in one band**, when less than 4.3 pt apart: one region,
  one choice; layout's own rule then splits them into regions by the
  1.5-pitch gap (layout §3, step 2) as it splits the layer's.
- **A note set in the body column's edge**: a word of the note within 4
  pt of the column lies outside the strip, but its band takes it by its
  height (section 4), so it is not read twice.
- **A scrambled page that is a table** (Domesday 428): kept as the layer
  by the score.
- **A page with no render to make** (blank, plate, excluded): nothing is
  read; a plate's caption is not small print here.

## 9. How it is verified

**What was measured for this spec.** The runs behind sections 2 and 3:
galley at 4542207 ran on Stubbs, Domesday and Haskins through
`galley-eval run` (the "before"). For each, a research script under
`tmp/` (not committed) replaced words in `words.json` with Tesseract's,
by the rules of sections 3 and 4 applied to the layer's words before
layout, and `galley2epub layout`, `structure` and `markdown` ran again,
then `galley-eval compare`. Scores at blocks; markdown gives the same:

| score | Stubbs before → after | Domesday before → after |
|---|---|---|
| body token error rate | 0.142 → 0.126 | 0.100 → 0.084 |
| margin notes found as margin notes | 241 → 295 of 467 | 519 → 575 of 593 |
| margin notes missing | 37 → 8 | 40 → 8 |
| margin-note words right (research script, section 3) | 357 → 1,100 of 1,908 | 1,025 → 2,109 of 2,487 |
| index entry boundaries, precision / recall | 0.829 / 0.789 → 0.983 / 0.953 | 0.993 / 0.986 → 0.993 / 0.986 |
| index token error rate | 1.543 → 0.096 | 0.047 → 0.049 |
| notes whose reference is right | – | 1,277 → 1,273 |

Stubbs' run re-read the cut-in notes and the 10 index pages; Domesday's
the outer margins and the scrambled pages 136, 92, 481 and 428, without
`reread_footnotes`. The margin bands of Domesday were chosen per page
side, not per band as section 3 gives. The footnote figures of section 2
are from the same runs with footnote bands added.

**Unit tests**, with literal inputs, no PDF and no Tesseract:

- `words_of_tsv` on a tsv string of two lines of three words, with the
  origin (100, 200) pt and 300 dpi: the boxes in points, the line's top
  and bottom on every word of it, the confidences, the order; a row of
  blank text skipped; output without the `level` header raises.
- `reading_score`: "Stephen of Blois." scores 3, "S Bl t o e i p s h .
  en of" scores lower (its value written in the test from the word
  list); "Henry’s" counts as known; "." counts as neither.
- `is_scrambled`: a page of 49 single letters is not, of 50 is; a page
  of 80 keys with 16 single letters (0.20) is, with 15 is not; "a" and
  "I" are not counted in English, "à" not in French.
- `note_bands` on a Pillow image drawn in the test: two blocks of ink 30
  px apart give two bands, 15 px apart one; a block 10 px high, and one
  20 px wide, give none.
- The replacement and the fidelity check on a hand-made page: a margin
  note of three layer words replaced by two Tesseract words, a body
  word beside it kept, the layer's single letters inside a Tesseract
  word's box replaced; `check_stage` passes, and fails when a kept
  record names a word the page does not have.
- A config with `reread_footnotes = true`, and one with a string there,
  an error.

**Excerpt tests**, marked `tesseract`, on the committed excerpts. Each
expected reading is a literal of the words galley keeps, written into
the test once the owner has checked it against the page image, as for
every reference page (the coding skill, "Tests"); the literals hold for
Tesseract 5.5.4 with its `eng` data, which the test checks first and
skips, saying so, on another version:

- `gierke_86-93_270-271`, excerpt page 2 (book page 88, the owner's
  page): its four margin notes, the last of which the layer did not
  read ("Medieval Thought.").
- `stubbs_51_56-64`: every cut-in note of the excerpt, as kept, and the
  body lines beside them unchanged from the run without re-reading.
- `stubbs_summaries_index`, excerpt pages 4 to 9 (book pages 312, 313,
  316, 318, 319, 321): each is a scrambled page whose Tesseract reading
  is kept; on page 312 the entry "Acre, siege of, 116; the English at,
  118;" has both ";" (Tesseract's text output of the page has "116 ;"
  and "118;"; the layer has neither, structure-second report).
- `domesday_74-83`: the margin notes of two pages, one of which the
  layer garbles.
- `haskins_eval` with `reread_footnotes = true`: a footnote whose
  marker the layer reads "^" is read "1"; and the same excerpt with the
  default re-reads nothing and runs no Tesseract in layout.
- Any excerpt with `ocr = "trust"`: `rereads` is empty and `lines.json`
  is what layout gave before this spec.
- The fidelity check passes on every excerpt, and layout with 1 worker
  and with 6 gives byte-identical `lines.json` on the Stubbs excerpt.

These tests make `uv run pytest` slower: re-reading the Domesday
excerpt's 10 pages costs about 1 s of renders. The excerpt fixture of
`tests/conftest.py` runs the pipeline once per excerpt, so the cost is
paid once.

**Whole-book tests**, marked `whole_book` and `tesseract`: the fidelity
check passes with re-reading on the six books; Stubbs with 1 and 6
workers gives byte-identical `lines.json`.

**The measurement of the plan**, by `galley-eval run` on the four
evaluation books before and after, quoted in its report: the scores of
the table above, with the margin-note words scored by the tool (section
10). Targets at blocks, set below what the research run gave so that
the line-height boxes of section 4 and the parallel change to extract
may move them a little: Stubbs' index boundaries at least 0.95 / 0.93;
Stubbs' margin notes as margin notes at least 280 of 467, Domesday's at
least 560 of 593; body error rate at most 0.130 on Stubbs and 0.090 on
Domesday; Domesday's notes whose reference is right at least 1,270; and
Haskins and Mariéjol unchanged, since nothing of theirs is re-read.
Gierke has no Gutenberg edition: its margin notes are checked by eye on
the 30 notes of the 16 November measurement, which must stay at 130
words right of 139 or more.

## 10. Changes to the architecture

For the orchestrator to apply to `docs/architecture.md`,
`docs/glossary.md` and `src/galley/model.py`, which this spec does not
edit. Section numbers are the architecture's.

1. **§1, last paragraph**, after "plus a confidence.": "Where a page's
   scan is good but its text layer poor in small print, layout reads
   that print again with Tesseract and keeps whichever reading has more
   dictionary words (`docs/specs/reocr.md`)."
2. **§4, the table**: layout reads "PDF, config, `pages.json`,
   `words.json`"; its work adds "small print re-read with Tesseract
   where that reads better (`docs/specs/reocr.md`)". Below the table,
   "analyze, extract and layout work page by page" is unchanged.
3. **§6, the config table**: the `ocr` row's meaning becomes "how far
   the book's own OCR is trusted (section 7b), and whether layout
   re-reads small print (`docs/specs/reocr.md`): not with `trust`".
   A new row: `reread_footnotes` | bool, `false` | "whether layout
   re-reads each page's footnote band with Tesseract
   (`docs/specs/reocr.md` §3)".
4. **§7b**, a new paragraph at its end: "Besides the audit, layout
   re-reads small print where the layer is poor (`docs/specs/reocr.md`):
   whole pages whose layer is scrambled into single letters, margin
   notes, and footnotes when the config asks. It chooses region by
   region and keeps the layer wherever Tesseract's reading scores no
   higher, so it replaces OCR only where it reads better (owner, 17
   November 2026). `ocr = "trust"` turns it off." The table's `trust`
   row adds "and layout re-reads nothing".
5. **§8, lines.json**: "`LinesFile(pages: tuple[PageLayout, ...],
   rereads: tuple[Reread, ...])`" with the `Reread` and `RereadKind` of
   this spec's section 4 and their meaning in a bullet each;
   `format_version` 2 for `lines.json` (the list "2 for `blocks.json`,
   1 for the others" becomes "2 for `blocks.json` and `lines.json`"),
   and reading a version 1 file is the error that says to run `galley2epub
   layout` again. The paragraph "layout only regroups words: every word
   of words.json is in exactly one line of lines.json. It removes
   nothing." becomes: "layout regroups words and re-reads small print:
   every word of words.json is in exactly one line of lines.json or is
   among the `layer_words` of a kept `Reread`, and every word of a line
   is a word of words.json or among the `ocr_words` of a kept `Reread`.
   It removes nothing." `Word`'s bullet: "`ocr_confidence`: Tesseract's,
   0–100, for a word galley read with Tesseract, on an OCR page or in a
   re-read region; `None` for the text layer."
6. **§9, layout**: add "Where small print reads better with Tesseract
   than in the text layer, it re-reads it: scrambled pages whole, the
   bands of the outer margin notes, Stubbs' cut-in notes, and the
   footnote band when the config asks (`docs/specs/reocr.md`); renders
   go through `pdfium.py`."
7. **§12, shared modules**: a row `ocr.py` | "Tesseract: `read_image`
   and `words_of_tsv`, the words of an image crop with boxes in points
   and Tesseract's confidence; `OCR_DPI` (300). Run with
   `OMP_THREAD_LIMIT=1`; an output without the tsv header is an
   `ExternalProgramError` (`docs/specs/reocr.md` §5)". In the
   `wordlist.py` row, layout joins analyze and structure among the
   stages that take the word list, and the command checks the word
   list's tools before layout too. In the `cli.py` row: the command
   finds Tesseract before layout when the config's `ocr` is `verify`.
8. **§13**, the bullet of the boundaries: "layout, words.json against
   lines.json, with the `layer_words` of each kept `Reread` taken out of
   words.json's side and its `ocr_words` added; each kept record's
   `layer_words` must be words of its page in words.json."
9. **§16, the table**: Tesseract is used by "analyze (the OCR audit),
   extract (OCR pages), layout (re-reading small print),
   `wordlist.py`", "when": "runs that need OCR, and layout unless `ocr =
   "trust"`".
10. **§17**, a list "On 17 November 2026": "**Small print is re-read**
    with Tesseract where it reads better than the text layer, region by
    region (`docs/specs/reocr.md`)."
11. **`docs/glossary.md`**: new entries **re-reading** ("reading a
    region of a page again with Tesseract, and keeping Tesseract's
    words only where they score higher than the text layer's; done by
    layout"), **reading score** ("known words minus unknown words of a
    reading; how re-reading chooses"), **scrambled page** ("a page whose
    text layer is mostly single letters: at least 0.20 of its words, on
    a page of 50 or more; Stubbs' index"), and **note band** ("the rows
    of ink of one margin note in a render of the margin").
12. **`src/galley/model.py`**: `RereadKind`, `Reread`, the field
    `LinesFile.rereads`, `LINES_FORMAT_VERSION = 2`, and the reading and
    writing of the new field, as section 4.

Other specs, which the plan changes in the same commits as the code:

- **layout spec**: §3 gains the re-reading after steps 2, 2b and 4 and
  the scrambled pages before the measures, pointing here; §4 the new
  public functions; §5 the renders and their time; §7 the fidelity
  rule above; "It removes nothing" stays true.
- **evaluation spec**: the text scores (§6) gain a part `margin_notes`,
  the reference's margin-note tokens apart from the body's, so that
  the re-reading's effect on them is a score of the tool and not of a
  research script; §8's `ocr_confidence_mean` is computed over the
  words that have a confidence, on any page.

## 11. Open points

1. **Footnote bands: re-read by default or not.** Re-reading them makes
   their words right far more often (Haskins: 0.404 → 0.141 error rate)
   but loses linked notes where Tesseract reads a marker together with
   the next word or as a symbol (Domesday: 137 of 1,277 references lost
   for 1,669 more note words right; Haskins: 3 of 59). The options:
   (a) off by default, `reread_footnotes = true` for the books whose
   owner wants it, at no cost to the others; (b) on by default,
   accepting the lost pop-ups; (c) on, but keeping the layer's word at
   the start of each note line where it has a marker's shape, which may
   keep the links and was not measured. Recommended: (a) now, and (c)
   measured in the plan; if (c) keeps the references within 10 of the
   layer's on Domesday, it becomes the default. Meanwhile: (a).
2. **Tesseract's junk in a kept region.** A kept region brings with it
   the junk Tesseract read beside the note ("~", "|", "Sy AM"; on
   Stubbs' cut-in notes, 74 such tokens among 2,213, picked by eye from
   the list of readings, not checked against the images). Dropping kept words under a confidence of 30 removes 51 of
   those 74 and 120 of the other 2,139, of which nobody has checked how
   many are real words. Options: keep every word (the reader sees the
   junk; the correct stage can use the confidence); or drop words under
   30 as removals with a new reason, `ocr_junk`, which the owner can
   review (the reader loses a few real words). Recommended: keep every
   word until a sample of the 120 has been read by eye. Meanwhile:
   keep every word.
3. **The new field of lines.json and the change to §7b** (section 10,
   items 4 and 5): a shared format changes, and layout now replaces OCR
   that exists, which §7b had left to the owner's choice, though only
   where Tesseract reads better and with every replaced word recorded.
   Meanwhile: the plan builds against section 4.

## 12. Not in this spec

- **analyze's audit and extract's OCR pages** (architecture §7b): pages
  without a text layer, and the sample that scores the layer against
  Tesseract, are analyze's spec. They use `ocr.py`.
- **Correcting single words** with the vision model, from the
  confidences: the correct stage.
- **Small print in the body column**, Stubbs' chapter summaries and
  quotes: not measured.
- **Finding more of Stubbs' cut-in notes**: layout's zones find about
  half (layout §9); the re-reading reads what they find. Of the
  reference's 1,908 margin-note words, 1,100 were right after it.
- **Mariéjol**: no effort, by the owner's decision; nothing of it is
  re-read (no margin notes, no scrambled page, footnotes only with
  `reread_footnotes`).
