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
reads the PDF, the book config and `pages.json`, and writes `words.json`
in the format of `docs/architecture.md` §8 (cited as "architecture §8")
and `images/`. It builds on the architecture and on `docs/glossary.md`.

The numbers were measured on 17 November 2026 with pdfplumber 0.11.10
on the six public-domain books galley is developed on, whole, as
`samples/public_domain/` holds them: C. H. Haskins, *The Normans in
European History* (**Haskins**); W. Stubbs, *The Early Plantagenets*
(**Stubbs**); F. W. Maitland, *Domesday Book and Beyond* (**Domesday**);
J.-H. Mariéjol, *Catherine de Médicis* (**Mariéjol**); O. Gierke,
*Political Theories of the Middle Age* (**Gierke**); J. H. Breasted, *The
Battle of Kadesh* (**Kadesh**). The scripts that measured them are not
kept. Page means page index, from 0, in the whole book.

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
the consecutive characters that text flow (section 3) puts in one word,
the gap is within 0.1 pt of 0 for 98.9% in Haskins (264,623 of 267,632
pairs), 98.6% in Stubbs, 99.4% in Domesday, 99.7% in Mariéjol, 99.2% in
Gierke and 98.0% in Kadesh. Between two words of the OCR there is either
a space character or a gap.

**Haskins and Stubbs have no space character.** Their text layers hold
333,893 and 483,684 characters, none of them a space; Domesday,
Mariéjol, Gierke and Kadesh have one space character for every two or
three others (Domesday 485,035 for 1,106,082). In Haskins and Stubbs a
word ends only where the gap to the next character is above 3 pt, and
many of the gaps between their words are smaller (the 7,002 gaps
under 3 pt that rule 2 splits in the two books, section 4), so the
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
("becomesarchbishopofCanterbury,"), which rule 2 splits. The other
1,300 are spread over 90 pages: cut words made whole. None is a margin
note joined to the body: the cut-in notes are about 27 pt from the body
lines beside them, and text flow joins nothing more than 3 pt apart.

## 4. Rule 2: glued words split at wide gaps

A word that text flow gives is split between two consecutive characters
when both hold:

- the gap between them is at least a third of the median width of the
  word's characters; and
- the first is a letter or a closing mark (`, . ; : ! ? ) ] ' " ’ ”`),
  and the second a letter or an opening mark (`( [ ' " ‘ “`).

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
| below 0.15 | 2 | 26 | 6 | 26 |
| 0.15 to 0.25 | 15 | 32 | 7 | 26 |
| 0.25 to 1/3 | 45 | 13 | 6 | 12 |
| 1/3 to 0.4 | 127 | 6 | 25 | 16 |
| 0.4 to 0.5 | 1,062 | 5 | 111 | 77 |
| 0.5 to 0.75 | 3,968 | 10 | 634 | 437 |
| 0.75 and more | 414 | 5 | 40 | 65 |

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
| Haskins | 1,609 | 2,772 | 69,033 | 190, 190, 2 |
| Stubbs | 3,177 | 4,230 | 104,448 | 137, 146, 0 |
| Domesday | 0 | 0 | 251,053 | 4, 4, 4 |
| Mariéjol | 0 | 0 | 237,920 | 46, 46, 46 |
| Gierke | 0 | 0 | 112,270 | 25, 24, 24 |
| Kadesh | 0 | 0 | 24,188 | 4, 4, 4 |

The runs that remain are real long words (Haskins' "Verfassungsgeschichte"
and Gierke's "Genossenschaftsrecht"), Mariéjol's unreadable OCR
("fuesàlamoridmRoyHemritroineemseamwtois") and Kadesh's, none of them
glued words with gaps.

**Checked by eye.** 60 splits drawn at random, 30 from each book, were
read on the page rendered at 216 dpi (drawn before the exception for a
digit after a closing mark was added; the 4 cuts before a digit among
them, "Stephen, 31" and the like, were right): 59 were right. The wrong one,
"RELA TIONS", is on Stubbs' page 324, one of the publisher's
advertisements at the end of the book (pages 322 to 328), which are
set in letter-spaced capitals; those pages hold all 9 of Stubbs' splits
between two parts in capitals, "NET RA", "A T SUCCESSIVE" among them.
The splits the table calls wrong, from a third up, were read too.
Haskins' 7 are a word before an initial ("in L.", "to P."), and right.
Of Stubbs' 17, 11 are initials the OCR gave as two words (9 "A. d." for
"A.D.", "B. C.", "N. Y."); 3 are "Henry s" (pages 127, 128 and 211),
"Henry's" whose apostrophe the OCR did not read; "By W." and "By S." are
right; "A T" is on the advertisements. The splits it missed are glued
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
    letter or closing mark and a letter or opening mark (extract spec
    sections 3 and 4). Each Word has `ocr_confidence` None."""

def split_glued(characters: tuple[Character, ...]) -> tuple[tuple[Character, ...], ...]:
    """The characters of one text-flow word, in order, cut into the
    words of rule 2. `Character` is a frozen value of text_layer.py:
    `text` and `box`."""
```

`split_glued` is the pure part, which the unit tests call with literal
characters. extract's `page_words` (walking skeleton §6) is unchanged:
it takes the words `layer_words` gives.

## 6. The cases

- **A page with no space character** (all of Haskins and Stubbs): its
  words come from gaps alone; rule 2 splits those under 3 pt.
- **Two OCR words laid over each other**: two words, each in the OCR's
  reading, where the default options mixed their characters.
- **A word the OCR cut in two with a gap** ("Mar gam", 0.18 pt): stays
  one word, as with the default options.
- **Letter-spaced capitals**: split where the letter spacing is wide
  ("RELA TIONS"). Measured on Stubbs' advertisements only; accepted.
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
  before the "3" stays one word; a word of one character comes back
  whole.
- **Excerpt tests.** Three new excerpts cut by `scripts/fetch_samples.py`
  carry the cases above (their pages, and the pages they share with the
  front-matter rule, are in `docs/specs/front-matter.md` §6):
  `domesday_front_flow` holds Domesday's pages 23, 24 and 200, and
  asserts "some" and "it" (not "s", "ome", "i", "t") and "London" and
  "Winchester" in the words of page 200; `gierke_front_flow` holds
  Gierke's pages 13 and 100, and asserts "The" and "him"; `haskins_front`
  holds Haskins' page 12, and asserts its words exactly.
- **The reference pages of the committed excerpts change.** 94 of the
  108 pages of the eleven committed excerpts get different words with
  the two rules (every page of `stubbs_51_56-64`,
  `stubbs_summaries_index`, `domesday_74-83`, `mariejol_210-219`,
  `mariejol_headings_verse` and `haskins_quotes_index`). The plan lists,
  for each page whose literal changes, the words removed and added, and
  the owner checks that they are of the kinds of sections 3 and 4 before
  the new literals are committed.
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
  print: the OCR audit (architecture §7b) and its own spec.
- Plates and the cover: `docs/specs/plates.md` §3 and walking skeleton §6.
