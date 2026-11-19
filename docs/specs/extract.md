# The extract stage: reading the text layer

extract gives every page of the book its words, each with its text and
its box, from the text layer of the PDF: the invisible words an OCR
program placed over the scanned page. This spec changes how a page's
words are read from that layer, in two rules decided by the owner. First,
the characters are taken in the order the PDF holds them, not sorted
left to right, which mends words that the sorting cuts or mixes ("s ome"
for "some" on Domesday's page 23, the letters of two lines mixed on
Stubbs' index pages). Second, a word in which the OCR program left no
space between two words ("Thisbookrestspartlyupon" on Haskins' page 12)
is split where the gap between two letters is wide against the size of
its letters. Both rules apply wherever galley reads a text layer, in
analyze as in extract, through one function of `text_layer.py`.

Dated 17 November 2026. It replaces the first item of
`docs/specs/walking-skeleton.md` §6, "extract" ("the words of
`page.extract_words()` with its default options, in pdfplumber's
order"), and the call to `extract_words()` in analyze; the rest of that
section, and `docs/specs/plates.md` §3, still say what extract does with
the words, the plates and the cover. What extract does with the pages
before the preface is in `docs/specs/front-matter.md`. The code that
exists is the walking skeleton's (`src/galley/extract/__init__.py`,
`_layer_words`; `src/galley/analyze/__init__.py`, `_measurer`). extract
reads the PDF, the book config and `pages.json` (analyze's file: what
each page is, text, plate, blank or excluded), and writes `words.json`
(each page's words with their boxes, and the words it removed) in the
format of `docs/architecture.md` §8 (cited as "architecture §8"), and
`images/`. It builds on the architecture and on `docs/glossary.md`. Section 9, added on 19 November 2026, says how extract reads a page
with Tesseract when the config's `ocr` is `redo`.

The numbers were measured on 17 November 2026 with pdfplumber 0.11.10
on the six public-domain books galley is developed on, whole, as
`samples/public_domain/` holds them: C. H. Haskins, *The Normans in
European History* (**Haskins**); W. Stubbs, *The Early Plantagenets*
(**Stubbs**); F. W. Maitland, *Domesday Book and Beyond* (**Domesday**);
J.-H. Mariéjol, *Catherine de Médicis* (**Mariéjol**); O. Gierke,
*Political Theories of the Middle Age* (**Gierke**); J. H. Breasted, *The
Battle of Kadesh* (**Kadesh**). Page means page index, from 0, in the whole book.

## 1. Terms

- **Character**: one glyph of the text layer, as pdfplumber gives it in
  `page.chars`: its text, one character, and its box in points. A
  **space character** is one whose text is white space.
- **The PDF's order**: the order in which the PDF draws the characters,
  which is the order the OCR program wrote them: word after word, line
  after line, as the OCR read the page. It is the reading order of the
  OCR, not necessarily of the book.
- **Gap**: the distance from the right side of one character to the left
  side of the next, in points; negative when the two overlap.
- **pdfplumber's word rule**: given characters in some order,
  `extract_words` starts a new word at a space character, which belongs
  to no word, and where the next character starts left of the previous
  one's left side, or more than 3 pt (`x_tolerance`) after its right
  side, or with a top more than 3 pt (`y_tolerance`) above or below its
  top; otherwise the character joins the word. A word's box is the
  smallest box that holds its characters.
- **Glued words**: two or more words of the book that the text layer
  gives as one, with no space character between them and a gap too
  small for pdfplumber's word rule ("UpperandLowerNormandy,").
- **Text flow**: pdfplumber's option `use_text_flow`, with which
  `extract_words` applies its word rule to the characters in the PDF's
  order (section 3). Without it, the **default options**, it first sorts
  them (section 2).

## 2. What the text layers show

**The characters of an OCR word tile its box.** In all six books the
characters inside one word of the OCR touch, one after the other: of
the consecutive characters that text flow (section 1) puts in one word,
the gap is within 0.1 pt of 0 for 98.9% in Haskins (264,623 of 267,632
pairs), 98.6% in Stubbs, 99.4% in Domesday, 99.7% in Mariéjol, 99.2% in
Gierke and 98.0% in Kadesh. Between two words of the OCR there is either
a space character or a gap.

**Haskins and Stubbs have no space character.** Their text layers hold
333,893 and 483,684 characters, none of them a space; Domesday,
Mariéjol, Gierke and Kadesh have one space character for every two or
three others (Domesday 485,035 for 1,106,082). In Haskins and Stubbs a
word ends only where the gap to the next character is above 3 pt, and
many of the gaps between their words are smaller (the 6,978 gaps
under 3 pt that section 4 splits in the two books), so the
words of many lines come out glued: on Haskins' page 12 the line
"This book rests partly upon" has gaps of 2.5 to 2.9 pt between its
words and is read as "Thisbookrestspartlyupon". Runs of 20 letters or
more, nearly all glued words, number 190 in Haskins and 137 in Stubbs
with pdfplumber's default options (table of section 4).

**Sorting by position cuts and mixes words.** With its default options,
`extract_words` first groups the characters into lines, those whose
tops lie within 3 pt of each other, and sorts each line from left to
right, before it applies its word rule. Three things then go wrong:

- **A space character whose box overlaps the next letter.** On Domesday's
  page 23 the characters of ", some" are ", ␠ ␠ s o m e" in the PDF's
  order; the second space runs from 277.62 to 280.39 pt and the "s" from
  277.2 to 281.32 pt, so sorting puts the space after the "s" and the
  word is cut, "s ome". Likewise "i t is" on Domesday's page 24, "' T
  he Medieval" on Gierke's page 13, "to h im" on Gierke's page 100.
- **Lines that slope.** On a page scanned askew, the top of a line rises
  or falls by more than 3 pt across the column, and the characters of two
  lines fall into one group and are sorted together. On Stubbs' index
  pages 312 to 321 this gives letter soup ("A A A A A A ± " A A d l l l d
  l l m m n m n q n r"): page 312 has 1,718 words with the default
  options and 324 in the PDF's order. On Domesday's page 200, a table,
  "London" and "Winchester" come out as "W L i o n n c d h o e n s ter";
  page 479, a table of places and their hides, is mixed throughout.
- **Two OCR words laid over each other.** Where the OCR read a spot twice,
  its two readings overlap, and sorting interleaves their characters:
  Domesday's page 43 "3178" for "37" printed over "18", Stubbs' page 49
  "tihe" for "the" and a stray "i".

## 3. Rule 1: the characters in the PDF's order

A page's words are those of `page.extract_words(use_text_flow=True)`,
with pdfplumber's other options at their defaults. With
`use_text_flow`, pdfplumber does not group or sort the characters: it
applies its word rule to them in the PDF's order (pdfplumber 0.11.10,
`WordExtractor.iter_extract_tuples`). The words come in that order too,
and words.json keeps it, as architecture §8 says ("in the order the
source gave them").

**Text flow joins only characters that are close.** A character joins
the word before it only when it follows the word's last character in
the PDF's order, starts at or right of that character's left side, at
most 3 pt after its right side, and with a top within 3 pt of its top.
So text flow never joins characters that are far apart on the page, nor
characters of two lines, whatever the order the OCR wrote them in: two
lines of the body are 11.5 to 15.2 pt apart (the body line pitch of
the six books, layout §1), and a margin note at least 6 pt
from the body column (Domesday, Gierke) or about 27 pt from the body
lines beside it (Stubbs' cut-in notes, layout §2). Where the PDF's order
jumps, from a margin note to the body or from one column to the next,
the word ends there.

**Where the PDF's order is not the book's.** The order of the words
matters to no later stage: layout groups each page's words into rows by
their position, top then left side (`body_measures.rows_of`), whatever
their order in words.json. Only the order of the characters inside a
word matters, and there the PDF's order is the OCR's reading of that
word.

**What it changes.** Every non-space character of the text layer is in
exactly one word with either option, on every page of the six books:
only where the words begin and end changes. Words per book:

| book | default options | text flow | difference |
|---|---|---|---|
| Haskins | 66,347 | 66,261 | −86 |
| Stubbs | 109,132 | 100,218 | −8,914 |
| Domesday | 256,339 | 251,053 | −5,286 |
| Mariéjol | 241,016 | 237,920 | −3,096 |
| Gierke | 113,996 | 112,270 | −1,726 |
| Kadesh | 25,467 | 24,188 | −1,279 |

What the differences are, counted by comparing, for each character,
the word it falls in under each option:

| book | text-flow words made of whole default words | text-flow words made of parts of default words | default words whose marks text flow sets apart | default words whose letters or digits text flow puts in two words |
|---|---|---|---|---|
| Haskins | 34 | 1 | 8 | 1 |
| Stubbs | 2,157 | 107 | 303 | 122 |
| Domesday | 3,622 | 174 | 201 | 230 |
| Mariéjol | 3,054 | 206 | 61 | 177 |
| Gierke | 1,247 | 118 | 59 | 125 |
| Kadesh | 446 | 31 | 10 | 32 |

The first column is cut words made whole ("M is s i o n" into
"Mission", Stubbs' page 147; "d 'apprendre" into "d'apprendre",
Mariéjol's page 276). The second is mixed words untangled ("Polfo
utghhe" into "Plough", Domesday's page 467). The third is a speck the
sorting put inside a word, now a word of its own after it ("obtai.n"
into "obtain" and ".", Stubbs' page 293). The fourth is mostly two
overlaid OCR words or two lines pulled apart ("Ttheem" into "The" and
"temple", Kadesh's page 11; "3178" into "37" and "18", Domesday's page
43). In random samples of 8 to 12 changes of each kind in each book, read
in the words of both options, every one was a repair or a change
between two wrong readings; none made a right word wrong.

**Stubbs' 8,914 words.** 7,614 of them are on its ten index pages, 312
to 321, whose letter soup text flow turns into glued words
("becomesarchbishopofCanterbury,"), which section 4 splits. The other
1,300 are spread over 90 pages: cut words made whole. None is a margin
note joined to the body: the cut-in notes are about 27 pt from the body
lines beside them, and text flow joins nothing more than 3 pt apart.

## 4. Rule 2: glued words split at wide gaps

A word that text flow gives is split between two consecutive characters
when both hold:

- the gap between them is at least a third of the median width of the
  word's characters, the larger of the two middle widths when their
  number is even (with the mean of the two, "A.d." on Stubbs' page 207
  is split and the book has one word more than the table); and
- either the first is a letter and the second a letter or an opening
  mark (`( [ ‘ “`), or the first is a closing mark (`, . ; : ! ? ) ] '
  " ’ ”`) and the second a letter. So no split falls between two marks
  (Stubbs' page 110 ":'", gap 1.8 pt), and a straight quote, `'` or `"`,
  is never taken for an opening mark: inside a word a letter or a mark
  always comes before it, and there it closes ("told." with its quote,
  `told."` on Stubbs' page 325; `waves"` on Haskins' page 24).

Each part is a word of its own, with the box of its characters; the
parts keep their order. A letter is a character for which Python's
`str.isalpha` is true.

**Why a third of a character's width.** Inside an OCR word the gap is 0
(section 2), so the letter spacing of a word or a line gives no scale;
the width of its characters does, and it follows the type size (4.4 to
5.9 pt on Haskins' page 12, about 3.5 pt on Stubbs' index pages). Every
gap of at least 0.1 pt inside a text-flow word of Haskins and Stubbs,
between characters of the kinds above, was judged by the word list of
`wordlist.py`: right when both parts are in the list and the two joined
are not, wrong when the joined word is in it and a part is not.

| gap, in median character widths | right | wrong | both parts and the join in the list | a part and the join not in the list |
|---|---|---|---|---|
| below 0.15 | 2 | 26 | 5 | 25 |
| 0.15 to 0.25 | 15 | 32 | 6 | 21 |
| 0.25 to 1/3 | 45 | 13 | 6 | 10 |
| 1/3 to 0.4 | 127 | 6 | 21 | 14 |
| 0.4 to 0.5 | 1,062 | 5 | 100 | 74 |
| 0.5 to 0.75 | 3,967 | 10 | 634 | 436 |
| 0.75 and more | 414 | 5 | 40 | 63 |

Below a third, the gaps are mostly inside words the OCR cut in two
("Mar|gam,", "earnes|t"); from a third up, the wrong ones are mostly
initials the OCR gave as two words, "A.|d." for "A.D.", which split
reads as "A. d.", no worse.

**Why not at digits, hyphens and dashes.** The OCR cuts numbers in two
with a gap as wide as a word space ("13|15," and "11|90," on Haskins'
pages 157 and 146, "a.d.ii|88." in Stubbs); split, a page number of the index
or a year would become two numbers. A note reference glued to its word,
"land3.", is how structure finds it (structure §11, "References"); split
off, "3." is no candidate and the reference is lost. At a hyphen or a
dash the gaps are 0.5 to 2 pt ("Mont-|Saint-Michel", "first—|came"),
and splitting there would put spaces into compounds. A glued word that
no gap of this kind cuts stays as it is.

**What it changes.** Only Haskins and Stubbs have such gaps; in the
other four books no text-flow word has a gap of 0.1 pt or more inside
it, because a space character fills every gap between their words.

| book | words split | words added | words after both rules | runs of 20 letters or more: default, text flow, both rules |
|---|---|---|---|---|
| Haskins | 1,606 | 2,767 | 69,028 | 190, 190, 2 |
| Stubbs | 3,164 | 4,211 | 104,429 | 137, 146, 0 |
| Domesday | 0 | 0 | 251,053 | 4, 4, 4 |
| Mariéjol | 0 | 0 | 237,920 | 46, 46, 46 |
| Gierke | 0 | 0 | 112,270 | 25, 24, 24 |
| Kadesh | 0 | 0 | 24,188 | 4, 4, 4 |

The runs that remain are real long words (Haskins' "Verfassungsgeschichte"
and Gierke's "Genossenschaftsrecht"), Mariéjol's unreadable OCR
("fuesàlamoridmRoyHemritroineemseamwtois") and Kadesh's, none of them
glued words with gaps.

**Checked by eye.** 60 splits drawn at random, 30 from each book, were
read on the page rendered at 216 dpi (drawn before the exceptions for a
digit or a mark after a closing mark were added; the 4 cuts before a
digit among them, "Stephen, 31" and the like, were right): 59 were right. The wrong one,
"RELA TIONS", is on Stubbs' page 324, one of the publisher's
advertisements at the end of the book (pages 322 to 328), which are
set in letter-spaced capitals; those pages hold all 9 of Stubbs' splits
between two parts in capitals, "NET RA", "A T SUCCESSIVE" among them.
The splits the table calls wrong, from a third up, were read too.
Haskins' 7 are a word before an initial ("in L.", "to P."), and right.
Of Stubbs' 18, 11 are initials the OCR gave as two words (9 "A. d." for
"A.D.", "B. C.", "N. Y."); 3 are "Henry s" (pages 127, 128 and 211),
"Henry's" whose apostrophe the OCR did not read; "By W." and "By S." are
right; "A T" is on the advertisements; "d' S" (page 149) was not read
on the page. The splits it missed are glued
words with a gap under a third of a character ("coastofSuffolk" on
Stubbs' page 307).

## 5. Where the rules live

Both rules are in one function of `text_layer.py`, which analyze and
extract call for every page they read from the text layer, so that
analyze counts, scores and tests for a plate the same words extract
writes. analyze's plate rule counts the known words of a page
(`docs/specs/plates.md` §2); more words are known once glued words are
split, which can only make a page of text look less like a plate.

```python
# galley.text_layer
def layer_words(page: pdfplumber.page.Page) -> tuple[Word, ...]:
    """The words of `page`'s text layer, in the PDF's order: those of
    pdfplumber's extract_words(use_text_flow=True), each split at a gap
    of at least a third of the median width of its characters between a
    letter and a letter or opening mark, or between a closing mark and
    a letter (extract spec sections 3 and 4). Each Word has `ocr_confidence` None."""

def split_glued(characters: tuple[Character, ...]) -> tuple[tuple[Character, ...], ...]:
    """The characters of one text-flow word, in order, cut into the
    words of section 4. `Character` is a frozen value of text_layer.py:
    `text`, one character, and `box`, in points."""
```

`split_glued` is the pure part, which the unit tests call with literal
characters. extract's `page_words` (walking skeleton §6) is unchanged:
it takes the words `layer_words` gives.

## 6. The cases

- **A page with no space character** (all of Haskins and Stubbs): its
  words come from gaps alone; section 4 splits those under 3 pt.
- **Two OCR words laid over each other**: two words, each in the OCR's
  reading, where the default options mixed their characters.
- **A word the OCR cut in two with a gap** ("Mar gam", 0.18 pt): stays
  one word, as with the default options.
- **Letter-spaced capitals**: split where the letter spacing is wide
  ("RELA TIONS"). Measured on Stubbs' advertisements only; accepted.
- **Words that climb.** On a steeply sloping line, or a word printed
  sideways, text flow keeps the word whole while each character's top
  moves by up to 3 pt from the last, so the word's box grows tall:
  Domesday has 98 words whose characters rise more than 4 pt from first
  to last, 66 on page 136, whose lower half bends, and 31 on page 481,
  whose table prints its column headings sideways; their boxes reach
  30.4 pt, against a body word height of about 9 pt. The other five
  books have 1 to 11 such words. layout's row rule
  (`body_measures.rows_of`) takes a tall word as the anchor of a row and
  pulls the words of the next line into it, so lines interleave there:
  run on page 136 with the words of text flow, layout gives "There 5
  mills shillings and fish-weir" and "and 1 one weir are which 6 renders
  of 64 nothing."; on page 481 the headings "Vespasian, Saxons," and
  "Cotton," fall among the table's numbers. With the default options
  both pages were letter soup ("8 b o r s w i t 1 v i r g"; on 481 every
  word of the body cut into letters, 874 words against 390), so the
  words are now right and their order is still wrong on those two pages.
  Mending the order is layout's, and not in this spec.
- **A glued word with no gap** (Mariéjol's unreadable OCR): stays as it
  is.
- **A number the OCR cut in two** ("13|15,"), and a note reference glued
  to its word ("land3."): stay one word. So does a page number glued to
  its index entry ("Lincoln,253" on Stubbs' page 319), the cost of not
  cutting before a digit.

## 7. How it is verified

- **Unit tests of `split_glued`**, with literal characters copied from
  the PDFs: Haskins' page 12 "Thisbookrestspartlyupon" gives "This",
  "book", "rests", "partly", "upon"; the gap of 1.8 pt in "13|15,"
  (Haskins' page 157) and the gaps of about 0.5 pt in
  "Mont-Saint-Michel" (page 206) split nothing; "land3." with a gap
  before the "3" stays one word; `told."` with a gap before the quote
  (Stubbs' page 325, gap 1.8 pt) stays one word, and so does `II.'s` (page 318);
  a word of one character comes back whole.
- **Excerpt tests.** Three new excerpts cut by `scripts/fetch_samples.py`
  carry the cases above (their pages, and the pages they share with the
  front-matter rule, are in `docs/specs/front-matter.md` §6):
  each asserts that the pieces of the cut words are gone, since the
  whole words are on those pages anyway. `domesday_front_flow` holds
  Domesday's pages 23, 24 and 200: page 23 has no word "s" or "ome",
  page 24 no "i" or "t", page 200 no "W", "L" or "ter" (with the
  default options each had one); `gierke_front_flow` holds Gierke's
  pages 13 and 100: page 13 has no word "T" (2 before), page 100 no "h"
  or "im" (1 each before); `haskins_front` holds Haskins' page 12, and
  asserts its words exactly.
- **The reference pages of the committed excerpts change.** 95 of the
  108 pages of the eleven committed excerpts get different words, in
  order, with the two rules (94 if only the multiset of words is
  compared) (every page of `stubbs_51_56-64`,
  `stubbs_summaries_index`, `domesday_74-83`, `mariejol_210-219`,
  `mariejol_headings_verse` and `haskins_quotes_index`). For each page
  whose literal changes, a script shows that every change is a join of
  pieces (section 3) or a split at a gap (section 4), and the words
  removed and added are listed in the work report and the owner's check
  sheet. The new literals are committed when the script passes; a change
  the owner rejects later is fixed in a task of its own (decided on 17
  November 2026, so that the work does not wait on the owner).
- **Whole books** (`whole_book` tests): the word counts of each book
  after both rules, exactly as in the table of section 4; every non-space
  character of each page in exactly one word; analyze's page kinds
  unchanged on the six books, against the `pages.json` of the commit
  before this change, except the pages `docs/specs/front-matter.md`
  makes front matter; and the fidelity check passing at layout,
  structure and markdown, as it does in every run.
- **galley-eval before and after**, on the four books of the evaluation
  set (`docs/specs/evaluation.md`): the scorecards of the commit before
  and of the commit that makes both rules, side by side in the work
  report. Expected: the body's token error rate falls in Haskins and
  Stubbs, where glued tokens were counted, and in Stubbs' index; the
  number of `glued` differences falls by about the words added above.
  Any score that rises is explained in the report, page by page.

## 8. Not in this spec

- The pages before the preface, which analyze marks and extract records
  as removed: `docs/specs/front-matter.md`.
- The OCR of pages without a text layer, and Tesseract re-reading small
  print: the OCR audit (architecture §7b) and its own spec. The pages
  read by Tesseract under `ocr = "redo"` are section 9.
- Plates and the cover: `docs/specs/plates.md` §3 and walking skeleton §6.

## 9. Pages read by Tesseract under `ocr = "redo"`

Added on 19 November 2026 for the plan ocr-redo
(`docs/plans/ocr-redo.md`). Under `ocr = "redo"` analyze marks every
text page `ocr` (architecture §7b), and extract reads such a page with
Tesseract instead of its text layer. Kadesh (`battleofkadeshst00breauoft`)
is the book that needs it: its layer reads page 9's "At Megiddo,
already in the sixteenth century before Christ" as "Me^iddo. already in
tli.- sixti-fiith century ln-forr Christ". Tesseract reads the page
better everywhere but at the note references, the small raised numbers
in the text that point to a footnote: it reads them as a sign or drops
them, and on the whole of Kadesh the notes linked to their reference
fell from 31 with the layer to 2 with Tesseract's words. So extract puts
back the layer's reference where Tesseract lost it (below). The numbers
of this section were measured on 19 November 2026 on the whole Kadesh
book, run up to structure at main 9292b17 once with the layer and once
with Tesseract's words in place of the layer's on every text page and
plate (`ocr = "trust"`, so that layout re-read nothing), with Tesseract
5 on an M5 Pro. That run differs from the rule on the plates, which
keep their layer under `redo`; the plates hold no note reference.

### How an `ocr` page is read

- The page is rendered at 300 dpi (`ocr.OCR_DPI`) in the PDFium
  thread, and a worker reads the render with `ocr.read_image`, origin
  (0, 0), page segmentation mode 3 (Tesseract finds the blocks of the
  whole page) and the book's language as Tesseract's code
  (`config.tesseract_language`). Its words come in Tesseract's order,
  block, paragraph, line, word, with Tesseract's confidence in
  `ocr_confidence`. Every word Tesseract gives is kept, its junk too:
  structure's rules for stray marks, figure text and headings see them
  (`docs/specs/structure.md` §34); none is dropped without a record.
  Tesseract took 0.95 s a page on Kadesh's text pages, one core each.
- The words whose middle lies in one of the page's `exclude_regions`
  are removals with the reason `excluded_region`, as on a page read
  from the layer; the in-page figures are cut as on any text page
  (`docs/specs/figures.md` §4), from the boxes analyze found with the
  layer's words.
- The page's text layer is read too, by `text_layer.layer_words`, for
  the references below, for the words Tesseract missed (below), and for
  one case: when Tesseract finds no word
  on a page whose layer has words, the page keeps the layer's words and
  its `PageWords.text_source` is `text_layer`, so that no printed word
  is lost, and extract logs a warning naming the page. None of Kadesh's
  45 text pages is such a page.
- An `ocr` page's `PageWords.text_source` is `ocr`; a text page whose
  words fell back to the layer, as above, has `text_layer`, and the
  page's `exclude_regions` apply to those words as to any. A text page
  has a layer with words by analyze's rule, so a page with neither
  Tesseract's nor the layer's words does not occur.
- Every other page is read as with `verify`, the default, which reads
  the layer: a plate page with a layer keeps the layer's words and the
  source `text_layer` (on Kadesh's 9 plates Tesseract reads 0 to 140
  words and the layer 2 to 24, and the layer reads the captions better,
  "PLATE II" where Tesseract reads "Puate II", "THE MODERN MOUND" where
  it reads "Tae Mopern Movunp"), and the words of an excluded,
  front-matter or inkless page are the layer's, each a removal with its
  reason.

### Note references put back from the layer

**What Tesseract does to a reference.** Where the layer reads
"Kadesh,12", "Greece,1" or "vizier83", Tesseract reads "Kadesh,”",
"Greece,’" and "vizier®": the raised digits become a quotation mark,
"*", "®" or "™", or vanish ("it" for the layer's "it69", "him," for
"him,88"). Of the 106 words of the layer on Kadesh's text pages that
end with a glued reference (condition 1 below), 68 lie under Tesseract
words with no digit, 8 under one with a digit, and 30 under no
Tesseract word by the test below, most of them in the layer's junk over
hieroglyphs and Greek.

**The rule.** A Tesseract word and a layer word of the same page are
**over each other** when their boxes overlap in height by at least half
the smaller of the two heights and in width by at least half the
narrower of the two widths; an overlap is the length of the
intersection of the two intervals, top to bottom or left to right, 0
when they do not meet. (The layer's boxes on Kadesh are about 11 pt tall
and sit 3 to 4 pt lower than Tesseract's, so that a box of the layer
also touches the line below; the half of the height keeps that line
out.) A Tesseract word **takes the layer's reference** when all of
these hold:

1. the layer word over it ends with a glued reference, by the form of
   `docs/specs/structure.md` §11, "Candidates": a letter, any
   punctuation or none, 1 to 3 digits and only punctuation, not after a
   citation's abbreviation ("p.12"); the test is
   `note_references.glued_reference` (architecture §12), so that
   extract puts back only what structure looks for. Its other form,
   punctuation and digits with no letter (";13"), never passes condition
   4, since the Tesseract word holds a letter;
2. the two words are over each other, and neither is over any other
   word of the other reading;
3. the Tesseract word holds no digit and at least one letter;
4. both words hold as many letters (`str.isalpha`): the layer's digits
   stand where Tesseract read a mark or nothing, never where it read a
   letter.

The Tesseract word's text then becomes its text up to its last letter,
followed by the layer word's text after its last letter: "Kadesh,”"
with "Kadesh,12" gives "Kadesh,12", "Higels.”" with "Hugels.80" gives
"Higels.80", "him," with "him,88" gives "him,88". Its box and confidence stay
Tesseract's. extract logs each change at INFO, with the page, the two
words and the result, and their number per book; words.json has no
record of it, since no format changes (architecture §8).

**What it gives.** On Kadesh the rule changes 57 words, and the notes
linked to their reference rise from 2 to 34, against 31 with the layer.
Each of the 57 was looked at on the page rendered at 200 dpi: 56 are
words the page prints with a reference after them, though the layer's
digits are often not the printed number (page 31's "Orontes,0" for 61,
page 54's 'sixth"3' for 143; structure's matching allows for such
misreadings, `docs/specs/structure.md` §11, "Matching"). The wrong one
is page 13's "find", which becomes "find1" from the layer's "flui1":
the page prints no reference there.

| variant, all else as the rule | words changed | right | notes linked |
|---|---|---|---|
| the rule | 57 | 56 | 34 |
| without condition 4 | 62 | 56 | 34 |
| an overlap in height of a third, not a half | 75 | 70 | 38 |
| also a sign the layer reads ("hieratic*"), not only digits | 170 | not counted: most are the layer's misreadings of a letter ("feat*" for "feats") | 39 |

The half of the height misses references whose two boxes overlap by
less, as page 28's "it" under "it69" (3.1 pt of 7.9); a third takes 16
more right ones, but also 4 wrong ("Kadesh"
and "seek" on page 41, where the page prints none) and loses 2, and a
wrong one leaves a digit in a word of the text. Condition 4 keeps out "campé" (page 62; the layer's "camp6" reads the
"é" as a digit), "Mon.," (page 13; the layer's "Jfem.,17" holds the
citation "Mon., 17", which Tesseract reads as two words), "XV-XVII."
and two words of the layer's junk. A note's own marker, at the start of
its line, is not put back: Tesseract reads more of them than the layer
does (108 of 159 notes with a marker against the layer's 84 of 148).

### Layer words Tesseract missed

Added on 19 November 2026, after a review of work package 2 of the plan
ocr-redo. **What Tesseract does.** It skips a printed line now and then,
most often a line of small print packed close to the next, and nothing
recorded it: on the whole Kadesh book, page 9 loses the first line of
note 8 ("CHABAS was conscious of the thoroughness of his"), page 11
"with the accession of new material made the compilation", page 15
"other engagements," which is an error for the prisoners as", page 52
"ing inscription over them:" and page 53 the line of note 134 "Simbel
and Ramesseum have first form. Since above was"; it also skips single
words, page numbers at the foot ("83" on page 10) and the scale of a
map ("5 Km."). The layer has these words, read as it reads the rest of
the page ("Ramraw-um" for "Ramesseum").

**The rule.** On an `ocr` page whose Tesseract words are kept, a layer
word is **missed by Tesseract**, and kept among the page's words, when
all of these hold:

1. it holds a letter or a digit (a layer word of signs only, "=" or
   "!", is dropped as Tesseract's reading of the page drops it);
2. no Tesseract word **covers** it: once the layer word's box is moved
   up by the page's **offset**, the two boxes overlap in width and
   overlap in height by at least a quarter of the lower of the two
   heights;
3. its box overlaps no in-page figure's box of the page (analyze's
   `figure_boxes`): what the layer reads there is the picture's ink or
   lettering, which the figure's image shows; inside the box it would
   be the figure's text, removed by structure (`docs/specs/figures.md`
   §5), and at its edge it made a note of junk, page 52's "UJ" under
   its hieroglyphs (24 layer words of Kadesh, all junk or the scales of
   maps);
4. no **unclaimed** Tesseract word with the same letters and digits
   (compared in lower case) lies within 16 pt of it, up, down or
   across (the gap between the two boxes, 0 when they overlap). A
   Tesseract word is unclaimed when no layer word with its letters and
   digits is covered by it.

The page's **offset** is the median, over the pairs of a layer word and
a Tesseract word with the same letters and digits, 3 or more, that
overlap in width and whose middles are less than 12 pt apart up or
down, of the layer word's middle less the Tesseract word's, in height;
0 when the page has no such pair. On Kadesh it is 1.2 to 5.4 pt: the
layer's boxes sit lower than Tesseract's, and are taller, so that a
layer word of a skipped line touches the Tesseract lines above and
below it.

A kept word keeps its text, has `ocr_confidence` `None`, as every word
of the layer, and its box is the layer's moved up by the offset, so
that layout rows it with the Tesseract words of its line (layout groups
words into rows by their boxes, layout spec section 1). It goes into
the page's words before the first Tesseract word whose top is lower
than its own. Its middle decides, as for any word, whether it falls in
an excluded region or an in-page figure. extract logs at INFO, for each
page, the number of words kept and their text, and the number for the
book; words.json does not say which word came from where, since no
format changes, but `ocr_confidence` `None` on an `ocr` page marks
them.

**Why these measures.** Measured on 19 November 2026 on the whole
Kadesh book with redo, on the 44 `ocr` pages, before condition 3 was
added (below):

| variant, all else as the rule | words kept | of them a copy of a word Tesseract read |
|---|---|---|
| any overlap covers, no offset, no condition 4 | 85 | none, but the lines of pages 9, 11 and 15 stay lost (their layer words touch the lines around them) |
| the rule without condition 3 (figures) | 103 | none found |
| no offset | 129 | none found, but page 15's line stays lost |
| condition 4 with any Tesseract word, claimed or not | 99 | none, but "of" and "the" of page 9's lost line go |
| no condition 4 | 126 | 2 or more: page 18's "over that", which the layer boxes 6 pt below Tesseract's, and page 41's "behind", 14 pt below |
| half the lower height, not a quarter | 167 | not counted: many layer words of lines Tesseract read |

Condition 4 keeps out the layer's copy of a word Tesseract read where
the layer misplaces its box: page 12's "of" (the layer's words of the
line lie up to 25 pt right of Tesseract's), page 41's "behind" and the
page numbers the layer boxes 10 to 12 pt off ("81" on page 8, "91" on
page 20). Its claim keeps the short words of a skipped line: the "of"
of page 9's lost line has an "of" of Tesseract's on the line above,
which covers the layer's "of" of that line.

**What it gives.** The rule keeps 79 words. Without condition 3 it
kept 103, each looked at on the page rendered at 150 dpi: 62 printed
words of the text, the notes, the maps or a page number, and 41 of the
layer's junk; the 24 that condition 3 takes out are 17 of the junk,
over hieroglyphs and maps, and the 7 words of the scales of the maps of
pages 29, 33, 36 and 45 ("5 Km."), which lie inside the maps' boxes. Of
the 79, 55 are printed words: the lost lines of pages 9, 11, 15, 52 and
53, "FRANÇOIS" (the layer's "FftAigou", page 9), "Égypte" (page 11),
"a" (page 14), "through" and "paper" (page 21), "27." and "Var." on
page 50, and the page numbers of pages 10, 11, 12, 18, 21, 28, 37 and
67; 24 are the layer's junk over hieroglyphs or Arabic outside the
figures' boxes (pages 21, 27, 33, 38, 41, 44, 45, 46) or specks (pages
15, 47, 55, 63, 66), which Tesseract read as junk of its own or not at
all. The junk stays as text, as the layer's junk does under `verify`. Some words the layer has are still
lost: page 11's "the" before "compilation" has an unclaimed "the" of
Tesseract's 9 pt below, and page 9's line keeps the layer's misreadings
("wu", "eocueiou*" for "was conscious").

### Word heights from the layer

Added on 19 November 2026 for task 3.3 of the plan ocr-redo. **What
Tesseract does.** It boxes a word sometimes to its letters and
sometimes as tall as its line, ascenders to descenders, on the same
line: on Kadesh's page 9 "Schéta" is 5.3 pt tall and "Manuscrit", beside
it in the same note line, 9.1 pt. The median word height, by which
layout and structure tell the small type of a footnote band from the
text (layout spec section 3, step 4; `docs/specs/structure.md` section
2, "band region"), then no longer tells them apart: page 9's notes have
a median of 9.12 pt against the body's 7.92, and the book's body word
height falls from the layer's 11.0 pt to 7.68. On the whole Kadesh book
with Tesseract's boxes, the pages with a footnote fell from 40 (the
layer) to 35: pages 9, 25, 27, 33, 41 and 50 lost theirs, their notes
read as body text or run into the body's region. The layer's boxes have
the height of the type, the same for every word of a line: 11 pt in
Kadesh's text, 7 to 8 pt in its notes.

**The rule.** On an `ocr` page whose Tesseract words are kept, each
Tesseract word that a layer word covers takes the height of that layer
word, about its own middle: its top and bottom move so that the box
keeps Tesseract's middle and has the layer word's height; its left and
right sides, its text and its confidence stay Tesseract's. Keeping the
middle keeps the word where Tesseract saw it, on its row and on its
side of a figure's edge: on page 33 the caption "MAP IV." lies 0.3 to
5.1 pt below the map's box by Tesseract's boxes, and the layer's box
moved by the offset would put the middle of "MAP" 0.2 pt inside it,
where it is taken for the map's lettering (`docs/specs/figures.md` §5). A layer word
covers a Tesseract word by the test of the section above (their boxes
overlap in width, and in height by at least a quarter of the lower
height, once the layer's box is moved by the offset); when several do,
the one whose overlap with it, width times height, is largest; the
cover test uses the layer's box moved by the offset, the height it
gives does not. A
Tesseract word that no layer word covers keeps its box. The rule is
applied last, after the references are put back and the missed words
kept, so that neither of those rules sees the new heights.

**What it gives.** On the whole Kadesh book with redo (measured on 19
November 2026), the rule changes the height of 23,576 of Tesseract's
24,570 words; the body word height is 11.0 pt, as with the layer; the
pages with a footnote are 42, the layer's 40 and pages 29 and 40,
whose notes ("Op. cit., p. 543", page 29; "This clause shows that the
statement…", page 40) the page images show printed small at the foot;
the notes are 184 (148 with the layer, 161 with Tesseract's boxes), 41
of them linked to their reference; the headings are still the 3 of
section 34 of the structure spec.

The notes' own markers are not taken from the layer, as the plan first
asked: the footnotes were lost by the heights, not the markers, and
where Tesseract misreads a marker ("Sin" for "⁵In" on page 9, "1%" on
pages 51 to 61) the layer word under it holds a digit for 5 of the 62
notes without a marker; for the others it is a sign ("*In", "»*Tba"), a
letter ("u", "m"), another word or nothing.

### Caption numbers from the layer

Added on 19 November 2026 for task 3.3 of the plan ocr-redo. Kadesh's
six maps are captioned "MAP III." to "MAP VIII." under the map. The
layer and Tesseract read their numbers so (the page shows "III.",
"IV.", "V.", "VI.", "VII.", "VIII."):

| page | 29 | 33 | 36 | 38 | 41 | 45 |
|---|---|---|---|---|---|---|
| layer | "111." | "IV." | "V." | "vi." | "VII." | "VIII." |
| Tesseract | "ILL." | "IV." | "Y." | "VI." | "VII." | "VIIL" |

Tesseract's "Y." is no numeral, so the map of page 36 loses its caption
(`docs/specs/figures.md` §1, "Caption label"), and its "ILL." and "VIIL"
read as no number; the layer's are the printed numbers but for the case
of "vi." and the "1" for "I" of "111.", the OCR's usual reading of a
roman numeral that figures §1 allows.

**The rule.** On an `ocr` page, a Tesseract word that follows a
**caption word**, "figure", "fig.", "fig", "plate" or "map" in any
case, in Tesseract's order, on the same line (their boxes overlap in
height), takes the text of the layer word over it, when the two are
over each other by the test of the references (above, one to one) and
the layer word is a numeral by figures §1 (1 to 6 characters, each a
digit or one of i, v, x, l, c in either case, with or without a "." or
"," after them) other than the Tesseract word's text, and the
Tesseract word holds no digit. Without that last condition the rule
took the colon of Kadesh page 62's "Plate 30:", where the layer reads
"30" and ":" as two words, and a character of the page would be lost. Its box and
confidence stay Tesseract's. extract logs each change at INFO with its
page. On Kadesh it changes the numbers of pages 29, 36, 38 and 45 into
the layer's; the text's "(Map IV)" is no caption word, for its bracket.

### Cases

- **Tesseract reads the reference as digits** ("Kadesh,12" both
  ways): the word has a digit, nothing changes.
- **The layer's word covers two of Tesseract's** ("Jfem.,17" over
  "Mon.." and "17"): condition 2, nothing changes.
- **A reference the layer missed too** ("Ramses’s" over the layer's
  "Ramses1", 7 letters against 6): nothing changes.
- **A digit of the layer inside a word** ("find" over "flui1"): the one
  wrong change measured; the reference is matched only if a note on the
  page reads 1 or a digit confused with it, otherwise "find1" stays in
  the text as the layer's "flui1" did.
- **Faint Kadesh page 69**: a plate without a layer; analyze makes it a
  plate whatever `ocr` is, and Tesseract finds no word on it.

### The public interface

`page_words` takes an `ocr` page's words as it takes a layer page's,
and two pure functions are added:

```python
# galley.extract
def with_layer_references(ocr_words: tuple[Word, ...],
                          layer_words: tuple[Word, ...]) -> tuple[Word, ...]:
    """`ocr_words`, a page's words as Tesseract read them, each that
    takes the layer's note reference (extract spec section 9) with its
    text changed, in the same order."""

def are_over_each_other(one: Box, other: Box) -> bool:
    """Whether two word boxes overlap by half the lower height and half
    the narrower width (extract spec section 9)."""

def with_missed_layer_words(ocr_words: tuple[Word, ...],
                            layer_words: tuple[Word, ...]) -> tuple[Word, ...]:
    """`ocr_words`, a page's words as Tesseract read them, with the layer
    words Tesseract missed (extract spec section 9) put among them, each
    with its box moved by the page's offset."""

def with_layer_heights(ocr_words: tuple[Word, ...],
                       layer_words: tuple[Word, ...]) -> tuple[Word, ...]:
    """`ocr_words` with each word that carries a confidence and that a
    layer word covers given that layer word's height about its own
    middle (extract spec section 9)."""
```

On an `ocr` page extract applies `with_layer_references` first, then
`with_missed_layer_words` to its result and the same layer words, then
`with_layer_heights` to that result and the same layer words; the
caption numbers are put back with the references, before the missed
words.

`run` no longer refuses an `ocr` page.

### How it is verified

- **Unit tests** of `with_layer_references` with literal words copied
  from Kadesh's two readings: page 10's "Kadesh,”" over "Kadesh,12"
  becomes "Kadesh,12"; page 36's "him," over "him,88" becomes "him,88";
  page 13's "Mon.." and "17" under "Jfem.,17", page 31's "Ramses’s" over
  "Ramses1" and page 62's "campé" over "camp6" stay as they are; a
  Tesseract word with no layer word over it stays; and of
  `are_over_each_other` with page 8's "Greece,1" against Tesseract's
  "Greece,’" (over) and "thousand" on the line below (not over).
- **Unit tests** of `with_missed_layer_words` with Kadesh's words: page
  11's skipped line ("with", "material") kept, moved by the offset, with
  the line's Tesseract words around it and their pair's offset; page
  12's "of", the layer's copy of an unclaimed "of", and page 9's "=",
  which has no letter, not kept; and a page with no pair, offset 0.
- **The excerpt `kadesh_redo`** (Kadesh pages 8 to 16, 32 and 34, with
  `ocr = "redo"`; `scripts/fetch_samples.py`): page 9's text read by
  Tesseract, page 11's skipped line kept from the layer, the plate's words the layer's, the excluded page's the
  layer's as removals, and the references after "Greece," (page 8) and
  "Kadesh," (page 10) linked to their notes. Its expected files are in
  `tests/fixtures/expected/ocr_redo/`.
- **The whole Kadesh book** with `ocr = "redo"`: at least 31 notes
  linked, the plan's target; 34 were measured with the prototype, and a
  count below 34, or a number of changed words far from 57, is explained
  in the work report page by page.
