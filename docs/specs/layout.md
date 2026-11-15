# The layout stage

layout takes the words of each page, as extract read them, and groups
them into the parts of the page that are read one after the other, the
**regions**: the running-head line, the body column (or its two columns,
on a page of the index), the notes printed in the margins, and the
footnotes at the foot of the page (or their two columns). Inside each
region it groups the words into lines, left to right, and it gives the
regions in reading order. It removes nothing: every word of `words.json`
ends in exactly one line of `lines.json`. What each region is, a running
head or a footnote, is left to structure (`docs/specs/structure.md`),
which reads the result.

Dated 15 November 2026. This spec serves the first of the two plans of
work on layout and structure that the owner set on 15 November 2026: the
first finds the regions, removes running heads, page numbers and
signature marks, joins hyphens and finds paragraphs; the second finds
notes and their references, places margin notes, finds headings, quotes
and index entries. It builds on `docs/architecture.md` (cited as
"architecture §8") and `docs/glossary.md`. The code that exists is the
walking skeleton's (`docs/specs/walking-skeleton.md` §7,
`src/galley/layout/__init__.py`): one region per page, holding every
word, grouped into lines by the vertical centre of each word. A row of
the page then becomes one line across everything it crosses: a margin
note goes into the body line beside it, and two footnote columns are
read across. This spec replaces that.

layout reads `pages.json` (what each page is: its size, whether it is
text, a plate or blank) and `words.json` (each page's words, each with
its text and its box in points, as extract read them from the text
layer), and writes `lines.json` (each page's regions, each a list of
lines, each a list of words), in the format of architecture §8,
unchanged. The **walking skeleton** is galley's first build, every stage
in its simplest form; its code is what exists now. Stubbs' notes cut into
the text column are left to the second plan, as the owner decided on 15
November 2026 (section 9).

## 1. Terms

Besides those of the glossary, this spec uses these; the first four are
added to the glossary.

- **Body column**: the rectangle of the page that the main text fills,
  from its **left edge** to its **right edge**. Its width is the same on
  every page of a book (within 3 pt in Haskins, Stubbs, Domesday and
  Mariéjol, between the 5th and 95th percentile of pages); its position
  moves by 10 to 25 pt from page to page with the scan.
- **Margin note**: (glossary) a short heading printed beside the body.
  An **outer margin note** is printed outside the body column, as in
  Domesday and Gierke; a **cut-in note** is printed inside it, at its
  outer side, with the body lines beside it shortened, as in Stubbs.
- **Footnote band**: the footnotes at the foot of a page, set in smaller
  type below the body.
- **Drop capital**: the large first letter of a chapter, two or three
  lines tall, as in Haskins.
- **Row**: the words that the walking skeleton's rule puts in one line.
  The words are taken in order of their top, then their left side; the
  first starts a row and is its anchor; each next word joins the current
  row when its vertical centre lies within the anchor's top and bottom,
  edges included, and otherwise starts a new row as its anchor. A row
  may cross several regions; a **line** is the same grouping done inside
  one region. The box of a row, a line or a region is the smallest box
  that holds its words.
- **Commonest** value of a set of edges: each edge rounded to the point;
  the value with the most edges within 2 pt of it; on a tie, the
  smallest such value.
- **Body word height** and **body line pitch** of a book: the median
  height of a line's words, and the median distance from the top of one
  row to the top of the next, over the book (section 3). "Pitch" alone
  means the body line pitch.
- **The reference**: the Project Gutenberg edition of an evaluation
  book, proofread by people from the same scan, against which the
  evaluation tool (`docs/specs/evaluation.md`) compares galley's output.
- **Letter or digit**: a character for which Python's `str.isalnum` is
  true.

The books named here are those of the evaluation set
(`docs/specs/evaluation.md` §3: Haskins, Stubbs, Domesday, Mariéjol) and
the two of the committed excerpts (Kadesh, Gierke). Unless it says
otherwise, a number below was measured on 15 November 2026 by a
research script on the whole book: on galley's output for the evaluation
set in `runs/evaluation/` (the walking skeleton, commit cc481d1), with
every word labelled by what the Gutenberg edition makes of it (body,
note, margin note, or absent, such as a running head), and on galley's
output for the whole Kadesh and Gierke books, which have no reference.
A page is given by its page index, from 0, in the whole book.

## 2. What the books show

What a reader of words.json would not expect, and what the rules below
are built on:

- **Word heights tell type sizes apart, roughly.** The text layer gives
  each word the height of its OCR line. The median height of a line's
  words, over the book's median, is at most 0.85 for 57 of Haskins' 57
  lines of notes and 8 of its 6,144 lines of body; for 4,007 of
  Domesday's 4,020 lines of notes and 18 of its 15,986 of body; for 769
  of Mariéjol's 911 lines of notes (its notes are 8 or 9 pt high against
  10) and 3 of its 13,909 of body. Stubbs' word heights vary from 5 to
  11 pt inside one line.
- **The running head is apart.** On pages that have one, the top of the
  next line is 1.43 body line pitches below the top of the head or more
  on 95% of Haskins' pages (median 1.62), 1.59 in Stubbs, 1.90 in
  Domesday, 1.42 in Mariéjol. Above the head, a line of specks read as
  text (";", "^", "—") is on 24 of Haskins' 263 pages and 88 of Stubbs'
  324.
- **Margin notes share rows with the body.** In the skeleton's lines,
  Domesday's margin notes sit on a row with body words in 1,000 of their
  1,360 line pieces, Stubbs' in 585 of 968, and words outside Gierke's
  body column share a row with body words in 1,417 of 1,488 lines.
  Domesday's and Gierke's notes are about 6 pt outside the body column,
  on the outer side (Gierke: right on even page indices 687 times, left
  on odd 662). Stubbs' cut-in notes are about 31 pt wide, inside the
  column on its outer side (left on odd page indices 480 times, right on
  even 339), and the body lines beside them start, or end, 58 to 62 pt
  inside the column's edge.
- **Two columns where one is expected.** Kadesh prints its footnotes in
  two columns on 22 of the 41 pages that have notes; Gierke on 9 pages.
  The index is in two columns in Haskins, Stubbs and Domesday: in the
  skeleton, 282 of Haskins' 352 index lines hold words of two entries.
  Domesday prints short notes side by side in one row (page 76: notes 1
  and 2), which reads correctly left to right.
- **A drop capital spans lines.** Haskins opens its chapters with a drop
  capital that the text layer reads together with the rest of the first
  word: on page 41, "THE" is one word 33 pt tall (the body's are 8 pt),
  from the drop capital "T" to "HE" on the first line. As the anchor of a
  row, it pulls the first two lines into one.

## 3. What layout does

layout first measures three numbers over the whole book, then lays out
each page on its own, in this order: the body column's position; the
outer margin notes; the running-head line; the footnote band; columns;
lines. Each step takes words out of what the later steps see, so a word
goes to one region only.

### The book's measures

From the rows of every page with at least 15 rows (the skeleton's rule
applied to all the page's words):

- **column width**: the median, over those pages, of the page's
  commonest right edge of a row minus its commonest left edge. An edge
  is counted to the nearest point, and "commonest" means the value with
  the most rows within 2 pt of it. Measured: Haskins 266 pt, Stubbs 267,
  Domesday 274, Mariéjol 317.
- **body word height**: the median, over all the rows of those pages
  pooled, of the median height of the row's words. Haskins 8.3 pt, Stubbs 8.1, Domesday
  10.0, Mariéjol 10.0.
- **body line pitch**: the median, over all consecutive pairs of rows of
  those pages pooled, of the distance from the top of a row to the top of
  the next. Haskins 15.1 pt, Stubbs 12.8,
  Domesday 12.1, Mariéjol 11.5.
- **usual left edge** for odd and for even page indices: the median of
  the left edge found by step 1 below on the pages of that parity that
  place their column themselves; it serves pages with no row wide enough to place the column.
  A parity with no such page takes the other parity's; when no page of
  the book has one, both take the median of the measured pages'
  commonest left edges.

A book with no page of 15 rows is measured on its pages of at least 3
rows; a book with none of those has no measures, and each of its pages
is laid out as one region, as the skeleton did.

### Per page

1. **Body column.** The page's rows are made from all its words,
   margin notes included. Its **wide rows** are those whose width (from
   the left side of their first word to the right side of their last) is
   at least 0.8 of the column width. A page with at least 3 wide rows
   places its column itself. The **common edges** of a set of sides are
   found as peaks: the commonest value (as defined in section 1), then
   the commonest of the values more than 4 pt from every peak found, and
   so on, keeping each peak that has at least a third as many sides
   within 2 pt of it as the first. Of the common edges of the wide rows'
   left sides and those of their right sides, the left and right edges
   are the pair whose distance is nearest the column width; a tie takes
   the smaller left edge, then the smaller right. A page with fewer than
   3 wide rows takes the usual left edge of its parity, and that plus the
   column width as its right edge.

   Why the page's own edges, and the pair: a row with a margin note is
   wider than the column and starts, or ends, outside it. Such rows are a
   minority in most books (Domesday: 1,000 of about 16,600), but not on
   every page: on Gierke's endnote pages (216 to 280) the notes are
   joined to as many rows as the body alone makes, and on Domesday's page
   28 a table's rows start 13 pt right of the body's. And some pages are
   set wider than the book's column: Gierke's introduction (page 13, 296
   pt against 273). With the left edge alone and the book's width, the
   column's right edge fell 40 pt inside Gierke's text, and about 470
   body words became margin words.
2. **Outer margin notes.** A word whose right side is at least 2 pt left
   of the left edge, or whose left side is at least 2 pt right of the
   right edge, is a margin word. A word that crosses an edge stays in the
   column, so a quotation mark hung outside the edge stays with its line
   (in the measurement, 64 of Domesday's 181,400 body words and 11 of
   Haskins' 60,900 fell outside by this rule).

   One exception, at the left edge only: the text layer sometimes gives
   a word of an outer margin note a box that runs on into the empty
   indent of the body line beside it (Domesday's page 75, "land." from
   52.6 to 80.0 pt against the edge at 73, beside "Free"; page 83,
   "Eng-" from 46.3 to 73.4 pt against 69). Kept in the body line, it
   makes the line start left of the column, and structure, which finds
   a paragraph's first line by its indent from the column's edge, does
   not see the indent: in the evaluation of 15 November 2026, 135 of the
   286 paragraph starts of Domesday that structure missed had such a
   word at the start of their first line. The rows here are those of
   the words the 2 pt test leaves in the column, grouped by the rule of
   section 1. The first word of such a row (the one with the smallest
   left side) is a margin word too when all four of these hold:

   - it holds a letter or a digit, so that a quotation mark or a
     semicolon hung outside the edge stays in its line;
   - its middle lies at least 2 pt left of the left edge: more of it
     lies in the margin than in the column;
   - the row has a second word, and it starts at least one body line
     pitch right of the left edge: the box ran into an empty stretch of
     the column. This keeps the words of a list whose numbers hang
     outside the column ("13. Ivo Carnotensis", Gierke's page 69), and
     boxes that join a note's text to the body's ("TheFrank-ha",
     Domesday's page 303). A row of one word stays: on Gierke's page
     123 the OCR read the note's "State." and the body's "form." as one
     word, "Stfoarm." (27 to 93 pt against the edge at 66), and it is
     the only such row the rule would move in the six books;
   - a margin word of the left side with at least two letters lies
     within one body line pitch of the first word, above or below: the
     margin word's top lies above the first word's bottom plus a pitch,
     and its bottom below the first word's top minus a pitch.
     The margin then holds a note, not numbers: on Gierke's page 62, a
     table of contents, "The Celestial Head gives" is set wide beside
     its number "44", which has no letter. One letter instead of two
     would move one more word in the six books, "31" beside "U" on
     Kadesh's cover (page 0).

   Run on the six whole books on 15 November 2026, the rule moves 176
   of Domesday's words and 95 of Gierke's, and none of Haskins',
   Stubbs', Mariéjol's or Kadesh's. Of 23 of them compared with the
   page image (one each on Domesday's pages 65, 75, 83, 91, 167, 193,
   211, 281, 363, 375 and 503, and Gierke's 87, 101, 115, 123, 153,
   171, 173, 195, 217, 233, 239 and 255), each is a word of a margin
   note. The same rule at the right edge moved 8 words: one a note's ("Bonds", Domesday's page
   92), six a body word and a note word read as one ("ofdemesne-",
   Domesday's page 90), and one a body word ("the", Domesday's page
   270), so it is not applied there.

   Each side's margin words are grouped into lines, and the lines into
   regions: a region ends where the next line's top is more than 1.5
   body line pitches below the top of the line before (a guess, so that each printed note is a
   region of its own).
3. **Running-head line.** Of the remaining words, grouped into rows,
   take the first row that holds a letter or a digit. It and every row
   above it (specks) form the running-head region when the next row's
   top is at least 1.3 body line pitches below its top. A page whose
   first such row is not that far apart, or is its only row, has no such
   region, and the specks above stay with the body. This region is a
   candidate; structure decides whether it is a running head. On
   Haskins' chapter pages (41, 67, 100, 131, 163, 233) the chapter number
   is less than 1.3 pitches above the title (0.98 on page 41), so they
   have no such region; Kadesh's article title on page 8 is set apart
   and makes one, which structure keeps in the text (structure §3).
4. **Footnote band.** Of the rows left after step 3, the band begins at
   the first row, other than the first of them, that is small (the
   median height of its words is at most 0.85 of the body word height),
   whose top is at least 1.1 body line pitches below the top of the row
   before, and from which on at least two thirds of the rows down to the
   last, that row and the last included, are small. A page number or
   signature mark at the foot counts as a row. The
   band runs to the foot of the page; the rows above it are the body.
   On a page whose every row is small, such as a page of the index, there
   is no band: the rows are the body.
5. **Columns.** The body, and the band apart from it, are each cut into
   two columns at a **gutter**: a vertical strip at least 6 pt wide,
   whose middle lies in the middle third of the body column. A row is
   **open** at a strip when no word box of the row crosses it and the
   row has words on both sides; a row is **compatible** when it is open,
   or has words on one side only, or has one word crossing the strip
   whose middle lies more than 6 pt from the strip's middle on either
   side (an OCR word that ran over the gutter, Kadesh page 10's
   "ancient"). The gutter is the strip of 6 pt, moved in steps of 1 pt
   across the middle third, at which the most rows are open; a tie takes
   the leftmost. A **run** is a longest stretch of consecutive compatible
   rows that, in the body, starts and ends at an open row: there a row
   with words on one side only, or with a word across the strip, belongs
   to a run only between two of its open rows. (A justified line of prose
   has one word across the strip; counted at the edge of a run, it joined
   the run, and on Kadesh's page 28 and Domesday's 43, 388 and 477 lines
   of prose above or below a table or figure were read as their left
   halves, then their right halves.) In the band a run may start or end
   at any compatible row: the first row of Kadesh's two columns of notes
   on page 8 has an OCR word that runs over the gutter ("Ori-", 227 to
   252 pt, the strip 245.5 to 251.5), and as the edge of the run it would
   be read across both columns. Word spaces do not tell the two apart:
   Kadesh's prose has gaps of 6 pt or more within 12 pt of the gutter on
   19 of the 26 rows of page 28 with a word across it. A run is cut
   when it holds at least 8 open rows in the body, or 3
   in the band, and in the band only when the gutter's middle lies within
   10 pt of the middle of the body column (two columns of notes are set
   on either side of the middle; Domesday's short notes printed side by
   side in a row are not, and must be read row by row, 1, 2, 3, 4, not 1,
   3, 2, 4). A cut run becomes two regions: each word goes
   left or right of the strip's middle by its own middle. The rows
   before and after it stay regions of their own: an index page whose
   title spans the column gives the title, then the left column, then
   the right.
6. **Drop capital.** A word of the body taller than 2.2 times the body
   word height, whose left side is within 3 pt of the left edge, is set
   aside before the rows of steps 3 to 5 and the lines of step 7 are
   made. Once the regions' lines are made, the lines beside it are those,
   of any region but a margin region, whose box overlaps the word's box
   vertically and lies to its right, that is whose left side is at or
   right of the word's middle. Its region is the one holding the line
   beside it whose left side is nearest it (the smallest left side), so
   that beside a column cut the left column's lines win over the right's;
   it is placed first in the topmost line beside it in that region, and
   the line's box then holds the word. (Haskins' "IN" on page 163 has its top 0.5 pt below the
   first line's centre, so a rule on the line's centre would put it on
   the second line.) A word with no such line is not set aside: the
   page is laid out again with it as a word of the body.
7. **Lines.** Inside each region, words are grouped into lines by the
   skeleton's rule, the lines ordered by their top and the words of each
   line by their left side.

The regions of a page are given in this order, "top" meaning the top of
the region's box: the running-head region;
the body regions from top to bottom, and within a run of columns the
left before the right; the margin regions by their top, the left side
before the right at the same top; the band regions in the same order as
the body's. A page with no word has no region; the figures are copied
from `words.json`, as now.

Where the thresholds come from:

| threshold | value | from |
|---|---|---|
| a row wide enough to place the column | 0.8 of the column width | guessed; a full line is the column width |
| wide rows for a page to place its column | 3 | guessed |
| a common edge | a third of the commonest edge's rows, peaks more than 4 pt apart | guessed; measured below |
| rows that measure a book | 15 rows a page | guessed: enough rows for a commonest edge |
| commonest edge | within 2 pt | measured: body lines start within 2.2 pt of the edge on 99% of Haskins' lines |
| margin word | 2 pt outside the column edge | measured, above |
| a word reaching into the column from the left margin | middle 2 pt outside, next word a pitch inside, a margin word of two letters within a pitch | measured on the six books, step 2: with one letter, Kadesh's cover also moves "31" beside "U" |
| margin region split | 1.5 body line pitches | guessed |
| running-head gap | 1.3 body line pitches | measured: the 5th percentile of the head's gap is 1.42 or more in the four evaluation books |
| small row | 0.85 of the body word height | measured, section 2 |
| band rows small | two thirds | guessed: Mariéjol's note lines are small on 769 of 911 |
| gap above the band | 1.1 body line pitches | measured: the 10th percentile of the gap from the last body line to the first note line is 1.16 pitches in Haskins, 1.24 in Domesday, 1.39 in Mariéjol |
| gutter | 6 pt wide, middle third, 8 open rows in the body, 3 in the band | measured, below |
| band gutter off the column's middle | 10 pt | measured, below |
| drop capital | 2.2 times the body word height, within 3 pt of the edge | measured: Haskins' are 2.67 ("IN", page 163) to 4 times |

An earlier form of the column rule, which asked every row of a run to
be open, was run on the skeleton's rows of whole pages (not on the body
left by steps 1 to 4) of the six books. It fires in
the body on all 8 pages of Haskins' index, 9 of Stubbs' 10 (312 to
321, and one page of advertisements after them),
Domesday's index and its tables (24 pages), Gierke's two-column lists (9
pages) and Mariéjol's two-column bibliography (2 pages), and on no page
of running text. With 5 rows instead of 8 it fires on 14 pages of
Mariéjol's running text, in runs of 5 to 11 rows, where the text layer
leaves wide gaps; with 3 rows, on 230 of Domesday's pages. Asking every
row to be open broke the columns: a blank line in one column or one
word over the gutter ended a run, so Haskins' index page 269 was cut
only on rows 9 to 19 of 55, Stubbs' page 312 into 8 runs, and only 198
of Kadesh's 398 note rows on pages with a gutter fell in a run. The
compatible rows above are the answer; the rule as written here was not
measured, and its reference pages (section 8) test it. Run in order, on
Stubbs' index pages a full-size catchword row under the head ("BUR
CON") makes the small-type columns below it a band, so the band's
3-row rule applies there. The band needs only 3 rows because two
columns of notes are often short, as in Kadesh; with 3 rows and no
further test, the band rule cut Domesday's side-by-side notes
into columns on 19 pages (83 and 139 among them) and Mariéjol's on 10.

The further test was first that at least half of the open rows have
their left part ending within 3 pt of the strip's left side (the left
column justified to the gutter). Run on the six whole books on 15
November 2026, it failed on two reference pages. On Domesday's page 83,
notes 3 and 5 end within 2 pt of the strip, being of the same length, so
two of its three open rows passed and the notes were cut into columns.
On Kadesh's page 10, the text layer's word boxes end 4 to 12 pt short of
the gutter, so three of its seven open rows passed and its two columns
of notes were read across. The gutter's position tells them apart: in
the band runs of 3 open rows or more, its middle lies within 8 pt of the
column's middle on all 30 of Kadesh's, and 13 to 46 pt from it in the
nine of Domesday's short notes side by side (pages 83, 111, 122, 139,
236, 240, 404, 504, 506). With the 10 pt test, the band is cut into
columns on 30 of Kadesh's pages, Stubbs' 10 index pages (312 to 321),
four of Domesday's (354, two columns of notes; 418, a table; 547 and 552,
the index) and four of Mariéjol's (14, the bibliography; 71, two columns
of notes; 169 and 261, pages whose OCR is garbled), and on no page of
Haskins or Gierke.

The column's edges of step 1 were changed on 15 November 2026, from
the commonest left side of the wide rows plus the book's column width
to the pair of common edges. Run on the six whole books with every
other rule as before, the words in each kind of region:

| book | rule | head | body | left margin | right margin | band |
|---|---|---|---|---|---|---|
| Haskins | before | 1,218 | 63,186 | 14 | 4 | 1,925 |
| | after | 1,218 | 63,173 | 11 | 20 | 1,925 |
| Stubbs | before | 1,879 | 95,326 | 9 | 9 | 11,909 |
| | after | 1,880 | 95,328 | 8 | 6 | 11,910 |
| Domesday | before | 1,890 | 198,212 | 793 | 1,065 | 54,379 |
| | after | 1,890 | 198,209 | 763 | 1,079 | 54,398 |
| Mariéjol | before | 1,630 | 208,149 | 10 | 34 | 31,193 |
| | after | 1,632 | 208,153 | 10 | 26 | 31,195 |
| Kadesh | before | 212 | 18,075 | 3 | 13 | 7,164 |
| | after | 212 | 18,076 | 3 | 12 | 7,164 |
| Gierke | before | 1,439 | 109,014 | 940 | 2,547 | 56 |
| | after | 1,444 | 110,261 | 1,163 | 1,072 | 56 |

Gierke's margin words fall from 32 to 1 on page 13 (the introduction),
and on page 235 from 65 words, mostly body-line ends ("est", "the popu-",
"similis;") to the 21 words of its margin notes ("Convey- / ance",
"Nullity"). On Domesday's page 28, "is" and "a" return to their lines.
The new margin words of Haskins are on two pages of specks (2, 278).

### What the rules give, measured

The steps 1 to 4 were run by a research script on the four evaluation
books, with the words labelled by the reference. Where the words of each
kind went (quotes counted with paragraphs):

| book | note words in the band | body words in the band | margin-note words in a margin region | body words in a margin region |
|---|---|---|---|---|
| Haskins | 485 of 523 | 1,945 of 60,900 | (none) | 11 |
| Stubbs | (none) | 141 of 90,100 | 0 of 1,521 (cut-in notes, section 9) | 7 |
| Domesday | 48,085 of 49,650 | 521 of 181,400 | 1,190 of 1,890 | 64 |
| Mariéjol | 20,049 of 25,784 | 593 of 184,100 | (none) | 1 |

Haskins' body words in the band are its "Bibliographical note" sections,
set in small type at the end of each chapter. Structure puts a band's
text after the paragraph in which the page's body ends (structure §6),
so they keep their order on the page; when such a section continues on
the next page as body (Haskins 263 to 264), the next page's first
paragraph may come before it. Of Domesday's margin-note words outside a margin region, 330 are
running-head words that the reference labels as margin notes ("Domesday
Book" is both), so the share is nearer 1,190 of 1,560. A fifth of
Mariéjol's note words stay in the body: their OCR lines are 9 pt high
against the body's 10.

## 4. The public interface

The pipeline calls `run`, as every stage (architecture §9). The other
functions are public so that tests can call them on hand-made pages.

```python
# galley.layout

@dataclass(frozen=True, slots=True, kw_only=True)
class BookMeasures:
    """The measures of section 3, in points."""
    column_width: float
    body_word_height: float
    body_line_pitch: float
    usual_left_edge: frozendict[int, float]   # by page index parity, 0 and 1

def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def measure_book(words: WordsFile, *, workers: int = DEFAULT_WORKERS) -> BookMeasures | None: ...
def layout_page(page: PageWords, measures: BookMeasures | None) -> PageLayout: ...
def group_lines(words: tuple[Word, ...]) -> tuple[Line, ...]: ...
```

`measure_book` gives `None` for a book with no page of 3 rows, and
`layout_page` with `None` lays the page out as the skeleton did.
`group_lines` keeps its present rule and signature; `layout_page` takes
a drop capital out of the words before it calls `group_lines`, and puts
it into the line step 6 names afterwards.

`run` is unchanged in what it reads, deletes, checks and writes
(walking-skeleton spec §7): it reads both files with
`read_checked_input`, deletes `lines.json` and every later file first,
runs the fidelity check before writing, and writes nothing on a
`FidelityError`.

## 5. How it runs in parallel

`measure_book` computes each page's rows and its numbers with
`map_pages`, in `workers` threads, then takes the medians over the pages
in page order. Then
`layout_page` runs on every page with `map_pages`. A page needs nothing
from the others but the book's measures, so the output does not depend
on the number of workers. The measures pass adds one grouping of rows
per page. Measured on 15 November 2026 on Domesday's 558 pages, on an
Apple M5 Pro with 6 workers (1 worker in brackets): the measures pass
takes 0.07 s (0.17 s) and the layout of the pages 0.19 s (0.62 s);
reading words.json takes 1.1 s, and `galley2epub layout`, which also
runs the fidelity check and writes lines.json, 2.5 s in all.

## 6. The cases

- **A page with no running head**, a chapter's first page: its first row
  is the chapter number or title. It is a running-head region only when
  set apart by 1.3 pitches; structure returns it to the body.
- **Specks above the running head**: in the running-head region, before
  the head line. Structure removes them (structure §4).
- **A page number alone at the foot** (Mariéjol's "(49)"; Kadesh's
  second sequence, the page numbers of the journal it was printed in) and **signature marks**
  ("M. 4", "4—2"): layout looks for no region of their own. The gap
  above a page's last line does not tell them from the last line of
  text: it is below 0.9 body line pitches for a tenth of the page numbers
  and signature marks of the four books. They end as the last line of
  the body or the band, and structure finds them there; below a column
  cut, as on Kadesh's page 10 ("83"), they are the row after the run and
  so a region of their own, which structure reads the same way.
- **A margin note level with the running head**: its words are margin
  words (step 2) and never join the head.
- **Domesday's short notes side by side**: one line per row, read left
  to right, which is their order; the gutter test of step 5 keeps
  three or more such rows from being cut into columns (page 83, a
  reference page).
- **Index pages**: two columns, each read top to bottom (step 5). An
  index set in small type under a full-size title has the title in the
  body and the columns as the band, which keeps their order.
- **Tables** (Domesday, 52 pages): a table with an empty strip in the
  middle third over 8 rows is read as two columns; otherwise row by row,
  as now. Tables are not otherwise handled.
- **Small type in the body**: Stubbs' quotations (0.75 of the body word
  height) are inside the body when body rows follow them; at the foot
  of a page they are read as a band. Their words keep their place in the
  reading order either way (structure §6).
- **Plate pages, blank pages**: no words, no region, as now.
- **Stubbs' cut-in notes**: they stay in the body rows beside them, as
  now, until the second plan (section 9).
- **Mariéjol's notes in 9-pt OCR lines**: a fifth of its note words
  (5,735 of 25,784) stay in the body, at the foot of
  their page, because their lines are not small by step 4. A reader of
  the EPUB sees them as body text there. A height measured per book for
  the notes, rather than the 0.85 ratio, may catch them; that is left
  until the first plan's evaluation shows how much it matters.
- **A margin region beside a column cut**: it is placed by its own top,
  after all the body regions, whatever columns it lies beside.
- **A margin word whose box reaches into the column**: the text layer
  sometimes gives a margin note's word a box that runs on into the body
  column, past its edge (Domesday's page 75, "land." from 52.6 to 80.0 pt
  against the edge at 73; page 83, "Eng-" from 46.3 to 73.4 pt against
  69). At the left edge, such a word goes to the margin note beside it
  when most of it lies in the margin and the body line beside it leaves
  the column empty for a pitch (step 2): page 75's body line reads "The
  idea of freedom…" and its note "Free land.". At the right edge it
  stays in the body line beside it, as a hung quotation mark does: there
  such boxes were mostly a body word and a note word read as one.
- **A margin note cut in two**: where the OCR lost a line of a note, the
  gap between its lines passes 1.5 pitches and the note becomes two
  margin regions (Gierke's page 270). Structure reads them one after the
  other.
- **A table of contents** (Mariéjol's page 450): titles on the left and
  page numbers on the right, with an empty strip between them over 8
  rows, are cut into a column of titles and a column of numbers. Reading
  them as entries is left to structure's second plan.

## 7. Fidelity

Every word of `words.json` is in exactly one line of `lines.json`
(architecture §8 and §13); layout removes nothing. The check runs in
`run`, as now. Each step of section 3 moves a word from what is left to
one region; a test asserts, on every reference page, that the words of
the regions are those of the page.

## 8. How it is verified

**Unit tests** on pages written in the test, each a few `Word` values
with their boxes, with a `BookMeasures` given in the test:

- a body of 20 rows and a margin word 6 pt right of the right edge on
  row 3 give a body region of 20 lines and a margin region of 1 line;
  the word 1 pt outside stays in the body line;
- a left margin note "Free" beside a body row that starts with "land.",
  whose box runs from 20 pt left of the left edge to 7 pt right of it,
  and whose next word starts 17 pt inside the edge, with a pitch of 12
  pt: "land." joins "Free" in the margin region's line, and so it does
  with its middle exactly 2 pt left of the edge, or with "Free" a line
  above. The same row keeps "land." in the body line with its next
  word 6 pt inside the edge, with no next word, with the margin word
  "44" or "U" instead of "Free", with "Free" 1.1 pitches above or below
  it, or with the middle of "land." 1.9 pt left of the edge; so does a
  ";" whose middle lies 3 pt left of the edge;
- a head row 1.4 pitches above the body gives a running-head region
  first; at 1.2 pitches, no such region; a row of ";" above it goes into
  the head region;
- 5 rows of words of height 0.7 under 20 rows of height 1.0, 1.5 pitches
  apart, give a band region; the same rows without the gap give no band;
  a page of small rows only gives no band;
- 10 rows with an empty strip 8 pt wide at the middle give two regions,
  left then right; 7 such rows give one region; in a band, 3 rows give
  two regions;
- a word 3 times the body height at the left edge spanning two rows is
  the first word of the upper line, and the two rows stay two lines; so
  is a drop capital whose top lies 0.5 pt below the upper line's centre;
- in the body, 10 open rows, a blank row in the left column and one word
  crossing the gutter keep one run and give two regions; in a band,
  three rows of two short notes whose gutter lies more than 10 pt from
  the column's middle stay three rows;
- `measure_book` on 20 hand-made pages gives the medians, and `None` on
  pages of 2 rows;
- `run` on a hand-made `words.json` of 8 pages with 1 worker and with 3
  gives the same bytes.

**Excerpt tests** on reference pages: the expected output of each is
the list of its regions, each as the text of its lines (words joined by
one space) in order, compared exactly; boxes are not compared. The owner
checks each by eye against the page image before it becomes a test. The
excerpt is measured on its own pages with `measure_book`, so its numbers
differ slightly from the whole book's.

| excerpt | page (excerpt page, book page index) | what it shows |
|---|---|---|
| `kadesh_8-17` (committed) | 2 (10) | running head, two footnote columns, the journal's page number alone at the foot |
| `kadesh_8-17` | 0 (8) | the article's first page: its title set apart as a head-line region |
| `gierke_86-93_270-271` (committed) | 2 (88) | margin notes outside the column; the signature mark "I — 2" as the last line |
| `gierke_86-93_270-271` | 8 (270) | endnotes, with margin notes beside them |
| `haskins_eval` (committed) | 0 (131) | a chapter's first page: chapter number, title, drop capital ("IN") |
| `haskins_eval` | 1 (132) | footnotes in the band |
| `haskins_eval` | 9 (266) | the first index page: title, two columns |
| `stubbs_51_56-64` (new) | 0 (51) | a cut-in note at the left; specks above the head |
| `stubbs_51_56-64` | 9 (64) | a cut-in note at the right |
| `domesday_74-83` (new) | 2 (76) | an outer margin note on the right, short notes side by side, signature "4—2" |
| `domesday_74-83` | 0 (74) | an outer margin note on the right, signature "M. 4" |
| `domesday_74-83` | 1 (75) | outer margin notes on the left; one word of a note, "land.", whose box reaches into the column, goes to its note, "Free land." |
| `domesday_74-83` | 9 (83) | short notes side by side in three rows, read row by row |
| `mariejol_210-219` (new) | 0 (210) | footnotes of 9-pt OCR lines; a foot line holding the signature and the page number "(l93)" |
| `mariejol_210-219` | 4 (214) | a foot line the OCR garbled |

The three new excerpts are added to `scripts/fetch_samples.py` with
what they cover, ten pages each, all with a text layer:

- `stubbs_51_56-64`: Stubbs (`earlyplantagenet01stub`), page indices 51
  and 56 to 64 (52 to 55 are maps and blank pages without a text layer):
  a chapter opening with a summary in small type, cut-in margin notes on
  both sides, running heads with dates, specks above the head, a hyphen
  across a page break.
- `domesday_74-83`: Domesday (`domesdaybook00maituoft`), page indices
  74 to 83: outer margin notes on both sides, footnotes, short notes side
  by side, the signature marks "M. 4" (74) and "4—2" (76).
- `mariejol_210-219`: Mariéjol (`catherinedemedic00mariuoft`), page
  indices 210 to 219: page numbers at the foot in parentheses, a
  signature line with the page number (210), footnotes in poor OCR.

The excerpt tests also run the fidelity check on each excerpt, and the
`whole_book` tests on the whole books.

**Measured by `galley-eval run`** (the evaluation tool of
`docs/specs/evaluation.md`). The tool compares
`lines.json` as one stream of words per page, so layout's regions do not
show in its scores at lines. They show at blocks, through structure's
targets (structure §9): paragraph breaks that margin and note text no
longer cause, notes and margin notes found as such. The table of section
3 is what layout's rules gave on a prototype; it is not a target.

## 9. Decided: Stubbs' cut-in notes wait for the second plan

There are no open points. The one this spec had, how layout finds
Stubbs' notes cut into the text column, was decided by the owner on 15
November 2026: option (c) below, so they stay in the body lines beside
them in the first plan. Option (a) is the one to try in the second
plan, which places margin notes and may render pages for other uses
too. What was measured and weighed:

**How layout finds Stubbs' cut-in notes.** The text layer does
not show them reliably. Five rules were tried on Stubbs' words, each
against the reference's labels; the best one that takes few body words
looks for an empty strip at least 6 pt wide, 20 to 100 pt inside the
column edge, over at least 2 rows, with a line of only note words among
them. It finds 139 of Stubbs' 1,521 cut-in note words and takes 75 body
words; looser forms find up to 798 and take up to 2,166 body words. The
text layer's boxes are the cause: 25% of the gaps between a cut-in note
and the body word beside it are under 5.7 pt, where the word spaces of
the body are 4.5 pt (median) and 8.1 pt (95th percentile), and some note
words are glued to body words ("toHenry's").

- (a) layout renders each page at 72 dpi with `pdfium.render` and looks
  for the empty strip in the picture, at the offset the book's pages
  share (58 to 62 pt in Stubbs). Layout then reads the PDF and the
  config, which changes architecture §4 and §9, and costs a render per
  page (about 6 s for Stubbs' 344 pages, a guess). Not measured: the
  plan's first task would measure it on Stubbs and keep it only if at
  least 95 of every 100 words it takes are note words.
- (b) the best text-layer rule above: little gain (a tenth of the notes)
  for 75 body words moved out of their paragraphs.
- (c) leave cut-in notes to the second plan, with margin-note placement:
  they stay in the body lines beside them, as now, and keep breaking
  Stubbs' paragraphs.

The spec recommended (a), with (c) if it failed the bar; the owner
chose (c), because the cut-in notes are in one of the six books and (a)
changes what layout reads. Whatever the second plan tries, the bar is
on precision: a body word moved into a margin note breaks the text a
reader reads.

## 10. Not in this spec

- What each region is, and what is removed: structure's spec.
- Figures inside text pages, tables as tables, the order of notes inside
  a band: later.
- OCR of pages without a text layer: analyze and extract.
