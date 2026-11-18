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
in its simplest form. The first plan's layout is built
(`src/galley/layout/`).

Revised on 16 November 2026 for the second plan, which changes layout in
two ways. Stubbs' notes cut into the text column are taken out of the
body lines by a rule on the text layer (section 3, step 2b), which
replaces the render of each page that section 9 was to try (owner, 15
November 2026). And the rules that measure the body text, the row rule,
the commonest edge, the body word height and body line pitch, move to
the module `body_measures.py` of the package root (architecture §12),
which structure uses too, so that the two stages stop keeping a copy
each (owner, 15 November 2026). The cut-in rule does not reach the bar
on precision set in section 9; the owner kept it as written on 16
November 2026 (section 9).

Revised on 17 November 2026: layout also re-reads small print with
Tesseract where it reads better than the text layer
(`docs/specs/reocr.md`). It then reads the PDF, through
`pdfium.render`, and the config, besides `pages.json` and `words.json`;
the re-reading comes in after steps 2, 2b and 4 of section 3, a page
printed wholly in small type is read whole after the book's measures,
and every region read is recorded in `lines.json`, whose format goes to
version 2. That spec gives the rules, the record and the fidelity rule;
this one points to it where they meet.

Revised again on 17 November 2026 for the plan owner-books
(`docs/specs/structure.md`, from its section 21), which changes three
steps of section 3 and no format: a number hung in the margin before a
line stays in that line (step 2); the running-head row is measured by
its words' median top, takes in the rows of a skewed head and passes
over rows of marks (step 3); the footnote band also starts, without a
gap, at a small row that opens with a note marker and a capital (step
4).

## 1. Terms

Besides those of the glossary, this spec uses these; the first four, and
the cut-in inset, are in the glossary.

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
- **Cut-in inset**: how far inside the body column's edge the body lines
  beside a cut-in note start (on the left) or end (on the right):
  Stubbs' is about 60 pt on both sides (section 3, step 2b).

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
  on the outer side (Gierke: in 687 of those lines on the right, on even
  page indices, and in 662 on the left, on odd ones). Stubbs' cut-in notes are about 31 pt wide, inside the
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
outer margin notes; the cut-in notes; the running-head line; the
footnote band; columns; lines. Each step takes words out of what the
later steps see, so a word goes to one region only. The cut-in notes
need the book's cut-in inset, which is measured on every page's column
(step 1), so step 1 runs on every page before the rest of the per-page
work.

### The book's measures

The row rule, the commonest edge, the choice of the pages to measure and
the body word height and body line pitch are those of `body_measures.py`
(architecture §12): `group_rows`, `commonest`, `measured_pages` and
`body_measures`, which structure calls too. layout keeps the column
width, the usual left edges and the cut-in insets, which only it uses.
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

- **cut-in inset**, for the left side and for the right, measured after
  step 1 has placed every page's column: over the rows of the measured
  pages, made of the words that step 2 leaves in the column, take each
  row's **inset**, the distance from the column's left edge to the row's
  left side (on the right, from the row's right side to the column's
  right edge), to 0.1 pt. Each inset that a row has, between 30 and 100
  pt, is tried as the peak, and the peak is the one with the most rows
  whose inset lies within 2 pt of it, the smaller on a tie. Only the rows'
  own insets are tried, not every 0.1 pt of the range: tried at every 0.1
  pt, the peak of the excerpt `stubbs_51_56-64` on the right moves to 58.1
  pt with 15 rows, and the excerpt `mariejol_headings_verse` gets a left
  inset of 71.5 pt (14 rows at it, 1 beside), where it has none. The book has cut-in notes on
  that side when those rows are at least 10, and at least 4 times as
  many as the rows whose inset is 6 to 12 pt smaller than the peak's,
  and 4 times as many as those 6 to 12 pt larger; otherwise it has no
  inset on that side. Measured on 16 November 2026 on the six whole
  books and the six excerpts:

  | | left: peak, rows at it, rows 6–12 pt smaller, rows 6–12 pt larger | right: the same |
  |---|---|---|
  | Stubbs | 60.4 pt, 394, 31, 20 | 59.0 pt, 359, 40, 32 |
  | Haskins | 43.5, 28, 31, 20 | 79.2, 30, 31, 29 |
  | Domesday | 30.2, 191, 152, 165 | 97.8, 155, 96, 87 |
  | Mariéjol | 30.1, 286, 452, 175 | 31.9, 80, 149, 85 |
  | Kadesh | 30.0, 13, 134, 10 | 42.0, 8, 8, 12 |
  | Gierke | 30.0, 111, 221, 98 | 35.7, 54, 73, 49 |
  | excerpt `stubbs_51_56-64` | 60.3, 17, 1, 0 | 58.2, 13, 1, 0 |
  | the five other excerpts | at most 11 rows at the peak, and Mariéjol's 11 against 9 | at most 8 |

  Stubbs' peaks are 12.7 times (left) and 9.0 times (right) the larger of
  their neighbours; no other book's is more than 1.3 times. So only
  Stubbs has cut-in notes, on both sides, and so does its excerpt. The
  floor of 10 rows lets the excerpt of ten pages pass (17 and 13); the
  first form of this rule asked for 50, which the excerpt does not
  reach, and which none of the other books came near deciding, since the
  ratio of 4 rejects them all.

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
     moves the same words in the six books; with no test of letters,
     3 more move: that "The", Gierke's "Monarchy" beside "''" (page
     119) and Domesday's "^X.^" beside "--,." (page 39).

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

   **A hanging number stays in its line.** A margin word of the left
   side that is 1 to 3 digits with nothing after them stays in the
   column, in the line of the word right of it on its row, when the gap
   from its right side to that word's left side is at most 15 pt and
   the row is not the page's first row with a letter or digit (the
   running head's, step 3). Turney (structure §21) prints its notes at
   the back in two columns with each note's number hung 6 to 14 pt left
   of its text; in the left column the numbers lie left of the page's
   usual left edge, and without this rule they were margin regions, a
   column of "1 2 3 4" read apart from the notes. The head row is left
   out because Turney prints its page number 13.4 to 15.1 pt beside the
   running head (261 pages, measured on 17 November 2026 on the
   survey's `lines.json`), which structure takes into the head line
   instead (structure §2). The numbers the rule keeps in their lines,
   counted with the rule as built on the `words.json` of the clean-text
   build and of the owner's two books (17 November 2026; the counts
   first given here, Gierke 26, Domesday 1 and Turney 115, were taken
   another way, as regions of `lines.json`): Turney 99, on 13 of its
   notes pages, each with its note (read on page 268); Gierke 30, 28 the
   numbers of the entries of its printed contents (23 on page 62, 5 on
   65), which then stay with their entries, and 2 specks the OCR read
   as "6" (page 115) and "9" (160) beside a margin note, which now
   start a body line instead of a margin region; Domesday 2, the "16"
   of a plate's caption "[Between pp. 16—17]" (page 39), right, and a
   speck read "6" beside a margin note (443); none in Haskins, Stubbs,
   Mariéjol, Kadesh or Haynes. The two pages above were read on their
   renders.

   Each side's margin words are grouped into lines, and the lines into
   regions: a region ends where the next line's top is more than 1.5
   body line pitches below the top of the line before (a guess, so that each printed note is a
   region of its own).

   **2b. Cut-in notes.** Only in a book with a cut-in inset on a side
   (above), and on that side. Stubbs prints its margin notes inside the
   body column at its outer side, in small type, and shortens the body
   lines beside them. The note's own words are hard to tell from the
   body's (a quarter of the gaps between a note word and the body word
   beside it are under 5.7 pt, and some are one word with it,
   "toHenry's"), but the shortened lines are not: they are body lines
   with nothing beside them. The rows are those of the words left in the
   column after step 2. On the left, with the left edge L and the inset
   I:

   1. a row is **cut** when one of its words has its left side within 3
      pt of L + I, is the row's first word or follows a gap of at least
      8 pt (the body's word spaces are 8.1 pt at the 95th percentile,
      section 9), and the row's words from it on span at least half the
      column width. The last condition keeps out a speck that happens to
      stand at the inset (";" on Stubbs' page 51);
   2. cut rows whose tops lie within 1.6 body line pitches of the one
      before form a chain. A **shortened** row has no word whose right
      side lies at most L + I − 4 pt: nothing stands in the strip beside
      it. A chain of at least 2 cut rows that holds a shortened row is
      trimmed at both ends to its first and last shortened rows, and is
      then a **cut-in zone**, from the top of its first row to the
      bottom of its last, even when one row remains.
      A full body line with a wide space at the inset by chance is a cut
      row too ("of John. The same year Johanna", page 120; "averted open
      war. Henry was", 125); at a chain's end it is trimmed off, and a
      chain of such lines alone, with no shortened row, is no zone
      (Stubbs' page 31: "England. Whilst the");
   3. a word of a row whose vertical middle lies between the zone's top
      less 1 pt and its bottom plus 1 pt, and whose right side lies at
      most L + I − 4 pt, is a margin word, unless it lies less than 5 pt
      from a body word of its row (the gap between their boxes, or their
      overlap): a word of the row that rule 3 does not take is a body
      word, and so is a word kept by this guard, so that the words before
      it are tested again. The body's word spaces are 4.5 pt at the
      median (section 9), so a word of a sentence that lies in a zone
      mostly stays with the word before it (Stubbs' page 33, "issued as his", "as" 4.1 pt after "issued",
      in a zone beside a cut-in note; page 317, an index entry "Langton,
      Walter, 249, 255, 266, 274" whose last numbers lie in a zone),
      while three quarters of the gaps between a note word and the body
      word beside it are 5.7 pt or more (page 58's "tendom.", 7.0 pt, still
      moves). The guard keeps one note word of the book in the body:
      page 226's "heBarons", the OCR's reading of "the Barons.", the last
      line of the note "Battle of Lewes. Victory of the Barons.", whose
      "t" the text layer gives as a word of its own 0.2 pt away and
      outside the zone.

   On the right the same, mirrored: a word's right side within 3 pt of
   R − I, the gap after it, the words up to it spanning half the column,
   and note words whose left side lies at least R − I + 4 pt. The margin
   words of each side are grouped into lines and regions as in step 2,
   and placed with the outer margin notes; structure makes such a region
   a margin region, since it overlaps vertically a region wider than
   itself (structure §2).

   **Measured** on 16 November 2026 on Stubbs' whole book, on step 1's
   edges and the rows of the words step 2 leaves in the column, with the
   insets above. Each moved word was labelled by where the evaluation
   tool's alignment puts it in the reference text (a margin note or the
   body), the same labels as the evaluation's scores; all words count,
   short ones too:

   | rule | words moved | aligned to a margin note | aligned to the body | not aligned | share of the aligned that are note words | the reference text's margin-note words found |
   |---|---|---|---|---|---|---|
   | zone from the first to the last cut row (the first form) | 1,977 | 1,070 | 132 | 775 | 0.89 | 1,070 of 1,469 |
   | zone trimmed to its shortened rows, and at least 2 rows left | 1,230 | 701 | 70 | 459 | 0.909 | 701 of 1,469 |
   | zone trimmed to its shortened rows, one row enough (as written) | 1,314 | 767 | 73 | 474 | 0.913 | 767 of 1,469 (0.52) |

   The label is a lower bound on precision: of the 28 words of 3 letters
   or more that the alignment puts in the body, 24 are words of the
   margin note printed on their page ("Hisfamily", "Breach", "Bishops."),
   which the alignment paired with the same word in the body text; with
   those counted as note words, 791 of 840, 0.94. The 474 words not
   aligned are 394 of fewer than 3 letters, nearly all single letters of
   notes the OCR spaced out ("B an i s h m e n t"), and 80 longer, mostly
   OCR damage ("Chanceiior."). The reviewer's full lines on pages 96,
   120, 125 and 139 lose no word with the trimmed zone. The rule as
   written does not reach section 9's bar of 95 in 100 on this measure:
   0.91 by the labels, 0.94 with the 24 words corrected; the owner kept
   the rule as written (section 9).
   With the 5 pt guard of rule 3 (added on 16 November 2026 after the
   review of the second plan), the rule moves 1,318 words, 6 fewer: "as
   his" on page 33, "255, 266, 274" on page 317 and "heBarons" on page
   226. Measured the same day by the evaluation tool of that day, whose
   reference counts 1,908 margin-note words of Stubbs (the counts above
   were taken with an earlier version of it): without the guard, 692 of
   the moved words are aligned to a margin note, 47 to the body and 585
   to nothing (0.936 of the aligned are note words); with it, 691, 44
   and 583 (0.940).
   Each condition was added for a case measured: without a shortened
   row, 56 words found only in the body were moved; with chains of one
   cut row, 47; with chains up to 2.6 pitches, 53 (counted, in the first
   research, by the words of 3 letters or more found only in the body
   text of the page).
3. **Running-head line.** Of the remaining words, grouped into rows,
   take the first row that holds a letter or a digit, the **head row**.
   It, every row above it (specks), and every row below it whose top
   lies less than half a body line pitch below its top (the rest of a
   head that the scan's skew set lower) form the running-head region
   when the next row that holds a letter or a digit has its top at
   least 1.3 body line pitches below the head row's top; rows of marks
   between them (no letter or digit) go with the body. A row's **top**
   here is the median of its words' tops, not the top of its box. A
   page whose head row is not that far apart, or has no row with a
   letter or digit below it, has no such region, and the specks above
   stay with the body. In the region, the head row and the rows of its
   skew are one line, their words left to right, and each row above
   them a line of its own (step 7 does not regroup them): the head is
   one printed line, and structure takes a head line that holds one
   line with a letter or a digit (structure §2). Grouped by step 7,
   Stubbs' date was a line of its own and the region no head line
   (decided on 17 November 2026 while building the plan owner-books;
   the spec had left it open).

   The three changes of 17 November 2026, each for a case measured by
   the public-domain survey on the clean-text build: a row's box top is
   its tallest word's, and an em dash or a word the OCR boxed 18 pt
   tall in the row below the head (Haskins' pages 23, 30, 66 and 235)
   made the gap read 1.08 pitches where the words' median tops are
   1.53 to 1.64 apart, as on Haskins' other pages; Stubbs prints a date
   at the outer end of its head that the skew sets 4 to 5 pt lower, a
   row of its own 0.2 to 0.5 pitch below (pages 20, 100, 152, 158, 186,
   202 and 210); Domesday's page 398 has a row of specks between head
   and body. In each case the page had no head region and its running
   head and page number stayed in the text, about 25 pages in the six
   books. Simulated on the whole books' `words.json` (17 November
   2026): the rule gains a head region on Haskins' pages 12, 23, 30,
   66, 235 and 278, Stubbs' 17, 20, 100, 152, 158, 186, 202 and 210,
   Domesday's 40 and 398, Kadesh's 68 and Gierke's 11, and loses it on
   Domesday's page 159, a table whose head stands 1.43 pitches above the
   next row by box tops and 1.30 by median tops, and Turney's 175, a
   newspaper front page reproduced as an illustration; none on Mariéjol
   or Haynes. A head region is a candidate: structure keeps the lines
   that are no running head (structure §3). This region is a
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
   signature mark at the foot counts as a row. The band also begins,
   whatever its gap, at a row that meets every other condition and
   opens with a **note marker**: its first word is 1 to 3 digits, with
   an optional "." after them, or 1 or 2 of the signs `* ^ • † ‡ §`,
   and its second word starts with a capital letter; the first such row
   wins when it comes before the row the gap rule finds. The
   band runs to the foot of the page; the rows above it are the body.

   The gapless start is for notes set close under the text: Haskins'
   page 28, whose note row is small (median word height 5.6 pt against
   a limit of 7.1) but only 1.06 pitches below the row above (1.18 by
   median word tops, which would recover 2 of Haskins' 5 such pages
   only), so the note stayed in the body and cut the paragraph that
   runs on to page 29. Measured on 17 November 2026 with a prototype on
   the whole books' `words.json`, pages whose band it starts: Haskins
   5 (28, 55, 173, 195, 258), Domesday 15 (each a note "1 …" or "3 …":
   90, 97, 138, 142, 156, 232, 247, 313, 342, 360, 406, 409, 443, 534
   and 535), Kadesh 3 (14, 28, 40, notes numbered through the
   article), Haynes 2 (its index pages 422 and 423, where a page number
   overhangs a row: structure reads the index's columns whether they
   are body or band, structure §17), and none in Stubbs, Mariéjol,
   Gierke or Turney. This form is narrower than structure's note
   marker (structure §11): layout needs only the forms that start the
   notes found, and keeps none of structure's code.
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

### Re-reading small print

Where the text layer reads small print poorly and the scan is sharp,
layout reads that print again with Tesseract, the OCR program, at 300
dpi, and keeps Tesseract's words for a region only when their **reading
score**, the count of their known words (in the word list of the book's
language) less their unknown words, is higher than that of the layer's
words they replace, region by region (`reading_score`,
`docs/specs/reocr.md` §1 and §3).
The rules of what is read, how each region is cropped, which layer
words a reading replaces and the record of each region read are
reocr's (§3 and §4); here is where they come into the steps above.

It is done only when the config's `ocr` is `verify`, the default (with
`trust` or `redo` nothing is read), and only on text pages whose words
are the text layer's (`pages.json` gives the page's kind and its text
source: the page is read only when its text source is `text_layer`,
not `ocr` or `none`). The book's measures are taken from the layer's words, before
anything is read. Then, over the whole book, layout finds the sides
whose outer margins hold notes: a side has them when at least 10 in 100
of the book's pages with 50 words or more have at least 2 known words
among that side's margin words of step 2 (Gierke and Domesday have both
sides, the other four books neither).

Per page, steps 1, 2 and 2b run on the layer's words, and then:

- **A small-print page**, printed wholly in small type such as a page
  of an index (`is_small_print_page`: at least 50 words, and at least 85
  in 100 of the column's rows of two words or more, below the running
  head of step 3, small rows as step 4 counts them), is read whole below
  its running-head region. When Tesseract's words are kept, the page's
  words become the layer's words less those the reading replaces, plus
  Tesseract's (`model.words_after_rereads`), and steps 1 to 7 lay them
  out again; the running-head region keeps the layer's words. No other region of such
  a page is read.
- On any other page, the regions are read where the steps have found
  their words: after step 2, the note bands of each side with margin
  notes, found by rows of ink in the side's margin strip of the render
  (`note_bands`); after step 2b, the crops around the cut-in zones;
  after step 4, when the config has `reread_footnotes = true`, the
  footnote band. The steps sort a page's words into groups: each side's
  margin words (step 2), each side's cut-in words (step 2b), the words
  left in the column, and among them the footnote band's (step 4). Each
  kept region's layer words are taken out of the group that holds them,
  and Tesseract's words put into the group of the region's kind: that
  side's margin words for a note band, that side's cut-in words for a
  cut-in crop, the footnote band's for the band. The later steps lay them out as they lay out the
  layer's, except that a band read by Tesseract is not looked for again
  by step 4: it is the band, and the rows above it the body.

A page is rendered once, in the one PDFium thread, and only when it has
a region to read: it is a small-print page, the book has a side with
margin notes, the page has a cut-in zone, or its footnote band is to be
read. Every region read is a record in `lines.json`, kept or not
(`Reread`, architecture §8), in page order and, within a page, in the
order reocr §4 gives.

Where the thresholds come from:

| threshold | value | from |
|---|---|---|
| a row wide enough to place the column | 0.8 of the column width | guessed; a full line is the column width |
| wide rows for a page to place its column | 3 | guessed |
| a common edge | a third of the commonest edge's rows, peaks more than 4 pt apart | guessed; measured below |
| rows that measure a book | 15 rows a page | guessed: enough rows for a commonest edge |
| commonest edge | within 2 pt | measured: body lines start within 2.2 pt of the edge on 99% of Haskins' lines |
| margin word | 2 pt outside the column edge | measured, above |
| a word reaching into the column from the left margin | middle 2 pt outside, next word a pitch inside, a margin word of two letters within a pitch | measured on the six books, step 2: one letter moves the same words, none 3 more |
| margin region split | 1.5 body line pitches | guessed |
| running-head gap | 1.3 body line pitches | measured: the 5th percentile of the head's gap is 1.42 or more in the four evaluation books |
| small row | 0.85 of the body word height | measured, section 2 |
| band rows small | two thirds | guessed: Mariéjol's note lines are small on 769 of 911 |
| gap above the band | 1.1 body line pitches | measured: the 10th percentile of the gap from the last body line to the first note line is 1.16 pitches in Haskins, 1.24 in Domesday, 1.39 in Mariéjol |
| gutter | 6 pt wide, middle third, 8 open rows in the body, 3 in the band | measured, below |
| band gutter off the column's middle | 10 pt | measured, below |
| drop capital | 2.2 times the body word height, within 3 pt of the edge | measured: Haskins' are 2.67 ("IN", page 163) to 4 times |
| cut-in inset | the most rows within 2 pt, 30 to 100 pt in; 10 rows and 4 times the rows 6 to 12 pt to each side | measured on the six books and excerpts, "The book's measures" |
| cut row | within 3 pt of the inset, after 8 pt, spanning half the column | measured on Stubbs, step 2b |
| cut-in zone | chain within 1.6 pitches, trimmed to its shortened rows, 2 rows | measured on Stubbs, step 2b |
| cut-in note word | 4 pt short of the inset | measured on Stubbs, step 2b |
| cut-in note word apart from the body | 5 pt from a body word of its row | measured on Stubbs, step 2b: the body's word spaces are 4.5 pt at the median, three quarters of the gaps beside a note word 5.7 pt or more |

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
    cut_in_inset_left: float | None           # None: no cut-in notes on that side
    cut_in_inset_right: float | None

def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def measure_book(words: WordsFile, *, workers: int = DEFAULT_WORKERS) -> BookMeasures | None: ...
def layout_page(page: PageWords, measures: BookMeasures | None) -> PageLayout: ...

class Side(StrEnum):
    """The side of the body column a margin note stands at."""
    LEFT = "left"
    RIGHT = "right"

class ReadLines(Protocol):
    """Tesseract run on a crop of a page rendered at 300 dpi, whose top
    left lies at `origin` on the page, in points: its words grouped by its
    lines, with boxes in points on the page (`ocr.read_image_lines`)."""
    def __call__(self, image: Image.Image, *, origin: tuple[float, float],
                 psm: int) -> tuple[tuple[Word, ...], ...]: ...

@dataclass(frozen=True, slots=True, kw_only=True)
class Rereading:
    """What layout needs to re-read a page's small print."""
    render: Callable[[int], Image.Image]   # a page index -> the page at 300 dpi, grayscale
    read_lines: ReadLines
    lower_case_words: frozenset[str]       # the word list of the book's language, in lower case
    margin_note_sides: frozenset[Side]     # the sides whose outer margins hold notes
    footnote_bands: bool                   # the config's reread_footnotes: the footnote band is read too

def layout_page_with_rereads(page: PageWords, measures: BookMeasures | None,
                             rereading: Rereading | None
                             ) -> tuple[PageLayout, tuple[Reread, ...]]: ...

def reading_score(words: Iterable[Word], lower_case_words: frozenset[str]) -> int: ...
def is_small_print_page(page: PageWords, measures: BookMeasures) -> bool: ...
def note_bands(strip: Image.Image, *, dpi: int) -> tuple[tuple[int, int, int, int], ...]: ...
```

`layout_page_with_rereads` lays the page out as `layout_page` does,
with its small print re-read as section 3 says, and gives the records
of the regions it read; with `rereading` None, with `measures` None, or
on a page whose words are not the text layer's, it reads nothing and
gives `layout_page`'s layout and no record. It takes the page's render
and Tesseract through `rereading`, so that its tests pass a drawn image
and Tesseract's words written by hand, with no PDF and no Tesseract;
`run` gives it a render by `pdfium.render` at 300 dpi and a reader by
`ocr.read_image_lines` in the book's language. `reading_score` is the
reading score of section 3; `is_small_print_page` decides a small-print
page on the layer's words; `note_bands` finds the note bands of a
margin strip rendered at 300 dpi, as pixel boxes, and raises ValueError
at any other resolution. The other steps of re-reading, the crops and
the choice of each region, are in the private module
`layout/_reread.py`, and steps 1 to 3, which both use, in
`layout/_column.py`.

`measure_book` gives `None` for a book with no page of 3 rows, and
`layout_page` with `None` lays the page out as the skeleton did.
layout groups words into lines with `body_measures.group_rows`, the
walking skeleton's rule, and keeps no copy of it under another name
(the skeleton's `group_lines` is gone); `layout_page` takes a drop
capital out of the words before it calls `group_rows`, and puts
it into the line step 6 names afterwards. `measure_book` places every
page's column (step 1) to measure the cut-in insets; `layout_page`
places it again, which costs one more grouping of rows per page.

`run` reads both files with `read_checked_input`, deletes `lines.json`
and every later file first, runs the fidelity check before writing, and
writes nothing on a `FidelityError` (walking-skeleton spec §7). Since
re-reading it also reads the config's `ocr`, `reread_footnotes` and
language, the word list of that language and the PDF, and writes each
region read into `lines.json`'s `rereads`. The command checks, before
any stage runs, that Tesseract is installed when layout runs and `ocr`
is not `trust`, and that Tesseract's word-list tools (`combine_tessdata`
and `dawg2wordlist`) are, when the word list is not cached and `ocr` is
`verify`, as it checks for Pandoc (walking-skeleton spec §9).

## 5. How it runs in parallel

`measure_book` computes each page's rows and its numbers with
`map_pages`, in `workers` threads, then takes the medians over the pages
in page order. Then
`layout_page` runs on every page with `map_pages`. The cut-in insets
add a pass that places every page's column (step 1), also with
`map_pages`, between the two; its time was not measured. A page needs nothing
from the others but the book's measures, so the output does not depend
on the number of workers. The measures pass adds one grouping of rows
per page. Measured on 15 November 2026 on Domesday's 558 pages, on an
Apple M5 Pro with 6 workers (1 worker in brackets): the measures pass
takes 0.07 s (0.17 s) and the layout of the pages 0.19 s (0.62 s);
reading words.json takes 1.1 s, and `galley2epub layout`, which also
runs the fidelity check and writes lines.json, 2.5 s in all.

With re-reading, a page with a region to read asks the PDFium thread
for its render and runs Tesseract in its worker, one subprocess per
region; since the renders are made one at a time, their sum is the
least the stage can take. Measured on 17 November 2026 on the same
machine with 6 workers, `galley2epub layout` on the whole book, against
2.5 s for Domesday without re-reading (above): Stubbs 29.9 s (359 regions read, 228 kept), Domesday
68.5 s (623, 441), Gierke 50.1 s (758, 428), Haskins 4.0 s (17, 9).

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
- **Indented epigraphs and headings taken for cut-in notes**: the
  owner's two modern books give a left cut-in inset (Turney 44.3 pt,
  from the indent of its epigraphs, chapter labels and section
  headings; Haynes 30.0 pt, from its epigraphs and paragraph indents),
  so step 2b runs on them; it moves no word in either, since no row
  beside those lines is shortened with words left of the inset
  (measured on 17 November 2026: every page laid out with and without
  the insets gives the same regions; structure §21).
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
- **Blank pages, and plates without a text layer**: no words, no
  region. A plate with a text layer (`docs/specs/plates.md`) has its
  words, laid out as any page's; its figure is copied from `words.json`.
- **Stubbs' cut-in notes** (step 2b): a note whose words are taken
  becomes a margin region. A note word glued to a body word
  ("inChris- tendom.") stays in its body line, since layout moves words
  and does not split them; so does a note beside which no line is
  shortened, or whose shortened lines are more than 1.6 pitches apart,
  which is most of the 48% of the notes' words not found (section 3,
  step 2b: 1,314 words moved, 767 aligned to notes, 73 to the body, 474
  not aligned; precision 0.913, recall 0.52; with the 5 pt guard of rule
  3, 1,318 moved by this code and 0.940 by the later tool); and when the
  OCR set a note's first letter or word off at the column's edge ("f
  reform" on page 60, "Plan of reform."), the part in the zone moves
  and the rest stays.
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
  rows, are cut into a column of titles and a column of numbers.
  structure reads them as two runs of paragraphs and makes no heading of
  them when the config names the page in `contents_pages` (structure
  §14); reading them as entries is not planned.

## 7. Fidelity

Every word of `words.json` is in exactly one line of `lines.json`, or is
among the replaced words of exactly one kept record of re-reading
(architecture §8 and §13, `docs/specs/reocr.md` §4); layout removes
nothing. The check runs in
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
  the head region; a head row 1.6 pitches above the body by its words'
  median tops, whose next row holds an em dash boxed 10 pt taller than
  its words, still gives one; a head whose last word lies 4 pt lower, a
  row of its own, gives one region whose one line holds both rows'
  words; a row of "^ _" between
  head and body is passed over and stays with the body;
- a left margin word "12" 9 pt left of a line's first word on a row
  below the head stays at the start of that line; at 16 pt, or on the
  head row, it is a margin word;
- a small row "1 Ibid. 29." 1.0 pitch below the body's last row, with
  small rows after it, starts the band; a small row "35 52 26" there
  does not;
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
  gives the same bytes;
- cut-in notes, with a cut-in inset of 60 pt on the left: three rows
  whose body words start 60 pt in, two of them with nothing left of
  that, and the note words "Character", "of" and "Henry" 5 pt in, give a
  margin region of those words; the same rows with a word starting at 60
  pt after a gap of 4 pt, or two such rows 2 pitches apart, give none; a
  full body line at the end of such a chain, with a word at 60 pt after
  a 9-pt space, keeps its words; a
  ";" at the inset on a row whose words from it span a quarter of the
  column is no cut row;
- `measure_book` on pages whose rows start 60 pt in on 60 rows and 0 to
  2 pt in on the rest gives a left inset of 60, and on pages whose rows
  start 30 pt in as often as 38 pt in gives none.

An excerpt test asserts that `measure_book` gives no cut-in inset on
either side for the five excerpts other than `stubbs_51_56-64`: the
nearest is Mariéjol's, 11 rows at 30.3 pt on the left against 9 at 6 to
12 pt smaller, and 8 rows at 37.4 pt on the right, below the floor of
10.

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
| `stubbs_51_56-64` | 0 (51) | a cut-in note at the left of which only its last line, "accession.", is taken, the rest beside lines that are not shortened; "Youth and education of Henry." left in the body; specks above the head |
| `stubbs_51_56-64` | 2 (57) | two cut-in notes at the left, "Characterof Henry II." and "Hisfamily policy." |
| `stubbs_51_56-64` | 3 (58) | a cut-in note at the right, "Hisgreatposi. tion inChris- tendom." |
| `stubbs_51_56-64` | 7 (62) | cut-in notes at the right, "Arrival of successor tep en i°54. '" taken, the rest of its five notes left |
| `stubbs_51_56-64` | 9 (64) | cut-in notes at the right, "B an i s h m e n t" and "Cti°n °£ J^tE." taken |

The words each page loses to its margin notes were listed by running
the rule as written on the whole book (16 November 2026); the owner
checks them against the page images before they become the test.
| `domesday_74-83` (new) | 2 (76) | an outer margin note on the right, short notes side by side, signature "4—2" |
| `domesday_74-83` | 0 (74) | an outer margin note on the right, signature "M. 4" |
| `domesday_74-83` | 1 (75) | outer margin notes on the left; one word of a note, "land.", whose box reaches into the column, goes to its note, "Free land." |
| `domesday_74-83` | 9 (83) | short notes side by side in three rows, read row by row |
| `mariejol_210-219` (new) | 0 (210) | footnotes of 9-pt OCR lines; a foot line holding the signature and the page number "(l93)" |
| `mariejol_210-219` | 4 (214) | a foot line the OCR garbled |

The plan owner-books adds the excerpts `haskins_heads_notes`,
`stubbs_heads` and `domesday_rereads` (`docs/specs/structure.md` §26),
whose reference pages check steps 3 and 4 here: Haskins' pages 23, 30,
66 and 235 and Stubbs' 20, 100, 152, 158, 186, 202 and 210 give a
running-head region first, Haskins' 28, 55 and 195 and Domesday's 97
and 138 a band holding their notes.

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

## 9. Stubbs' cut-in notes: decided

How layout finds Stubbs' notes cut into the text column was decided
twice by the owner. On 15 November 2026, for the first plan, they
stayed in the body lines (option (c) below), and option (a), a render
of each page, was to be tried in the second plan. Later the same day,
on the second research, the owner chose instead the rule on the text
layer of section 3, step 2b, which looks at the shortened body lines
rather than at the note's words and keeps layout reading only
`pages.json` and `words.json`. The bar set here, at least 95 of every
100 moved words being note words, was then thought met (96%, counted on
words of 3 letters or more, found by their letters in the note or body
text of the page); measured on all words by their alignment, it is not
(section 3, step 2b).

**Decided: step 2b is kept as written, below the bar** (owner, 16
November 2026). The rule moves 1,314 words in Stubbs, of which 767 are
aligned to margin notes and 73 to the body (precision 0.913; 0.94 once
24 note words the alignment misplaced are counted as notes), and 474
are not aligned, mostly single letters of spaced-out notes. It finds 767
of the reference text's 1,469 margin-note words (recall 0.52). After
the review of the second plan, rule 3 keeps a word less than 5 pt from
a body word of its row, which a word of a sentence is: on 16 November
2026 the rule then moved 1,318 words, and by the evaluation tool of that
day 0.940 of those aligned are note words (0.936 without the guard on
the same tool; section 3, step 2b). The
owner accepted the precision below the bar of 95 in 100: at most about
50 body words of Stubbs' 90,100 (0.06%) move into margin notes, and
every cut-in note left in the body breaks a paragraph a reader reads.
The two other answers weighed were a render of each page (option (a)
below), at the cost of a render per page and of layout reading the PDF,
and leaving the cut-in notes in the body lines, as the first plan does.
The rule runs only on a side where the book has a cut-in inset (section
3), so a book without one is laid out as before.

What was weighed for the first plan. The text layer does not show the
note's words reliably. Five rules were tried on Stubbs' words, each
against the reference's labels; the best one that took few body words
looked for an empty strip at least 6 pt wide, 20 to 100 pt inside the
column edge, over at least 2 rows, with a line of only note words among
them. It found 139 of Stubbs' 1,521 cut-in note words and took 75 body
words; looser forms found up to 798 and took up to 2,166 body words.
The text layer's boxes are the cause: 25% of the gaps between a cut-in
note and the body word beside it are under 5.7 pt, where the word
spaces of the body are 4.5 pt (median) and 8.1 pt (95th percentile), and
some note words are glued to body words ("toHenry's").

- (a) render each page at 72 dpi with `pdfium.render` and look for the
  empty strip in the picture, at the offset the book's pages share (58
  to 62 pt in Stubbs). Layout would then read the PDF, which changes
  architecture §4 and §9, at the cost of a render per page. Not
  measured.
- (b) the best of those five rules: a tenth of the notes for 75 body
  words moved out of their paragraphs.
- (c) leave cut-in notes in the body lines beside them, breaking Stubbs'
  paragraphs, until the second plan.

Whatever is tried, the bar is on precision: a body word moved into a
margin note breaks the text a reader reads.

## 10. Not in this spec

- What each region is, and what is removed: structure's spec.
- Figures inside text pages, tables as tables, the order of notes inside
  a band: later.
- OCR of pages without a text layer: analyze and extract.
- The rules of re-reading small print with Tesseract, the crops, the
  filters of a cut-in crop, the words a reading replaces and the
  record: `docs/specs/reocr.md`; section 3 says where they come in.
