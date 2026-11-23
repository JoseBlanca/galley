# The structure stage

structure turns the regions and lines that layout gives
(`docs/specs/layout.md`) into the book's text as blocks and notes, each
of a kind that says what the text is. It removes what the printer put on
the page and the book does not hold, running heads, page numbers,
signature marks, the guide words of an index and the stray words the
text layer holds on a plate, each with a record of what was removed and
why; it joins the words that a hyphen splits at a line end; it finds
paragraphs, including those that run over a page break; it finds the
notes, links each to its reference in the text, and tells footnotes
from endnotes; it places each margin note before the paragraph it was
printed beside; and it finds headings, chapter summaries, quotes, verse,
the entries of an index and the caption of a plate.

Dated 15 November 2026, and revised on 16 November 2026 for the second
of the two plans of work into which the owner split layout and
structure on 15 November 2026. The first plan, sections 1 to 10, is
built: it removes running heads, page numbers, signature marks and stray
marks, joins hyphens, finds paragraphs and keeps the text of the margins
and of the footnotes apart from the body
(`src/galley/structure/`). The second plan, sections 11 to 19, adds
notes and their references, endnotes, margin-note placement, headings,
chapter summaries, quotes and verse, index entries and plates, and
changes the markdown stage to write them. The owner decided its open
points on 15 November 2026: the decisions are given where they apply,
marked "owner, 15 November 2026", and listed in architecture §17. The
principle behind several of them is that galley's formats are semantic:
a kind says what a text is, never how it looks, so two things that will
look alike in the EPUB still get different kinds, and how each looks is
decided by the markdown and epub stages (architecture §3). The two
points left open, how a heading keeps its chapter label and what
Haskins' bibliographical notes are, the owner decided on 16 November
2026 (section 20). Revised on 17 November 2026: section 3 gains the
running head of a section of two pages, "The head of a short section",
which the owner asked for with the changes to how the text layer is read
(`docs/specs/extract.md`) and to the pages before the preface
(`docs/specs/front-matter.md`).

Revised again on 17 November 2026 for the plan **owner-books**, which
makes galley read the owner's two modern books (section 21) as well as
the six public-domain ones, and fixes failures found in the
public-domain books (running heads, notes left in the body, words read
twice by re-reading, words glued at a case change). Its scope was approved by the owner, who decided
that an epigraph is a block kind of its own and how spaced punctuation
is treated; the points left open have a "meanwhile" (section 27). It
changes, where they stand: the head line, which takes in a short region
beside it, and a chapter label, which is never a running head (sections
2 and 3); a page number at the foot read by its value (section 4); a
hanging number and a short last line at a page break as paragraph
starts (section 6); notes at the back grouped per chapter (section 12);
headings set flush left or in large type (section 14). It adds
epigraphs (section 22), spaced punctuation (section 23), words glued at
a case change (section 24), the change to markdown (section 25), and
how all of it is verified (section 26). `blocks.json` goes to
`format_version` 4 (section 7). Layout changes too
(`docs/specs/layout.md` §3, steps 2 to 4), and so does the re-reading's
pairing of words (`docs/specs/reocr.md` §4). No code of this revision
exists.

Revised on 18 November 2026 for lists and the printed table of
contents, which the owner found joined into one paragraph each in
Haynes' EPUB: a list's items are blocks of kind `list_item` (section
29), the entries of a printed contents blocks of kind `contents_entry`,
each linked to the heading of its chapter (section 30), and markdown
writes both as lists (section 31). `blocks.json` goes to
`format_version` 5 (section 7). How it is verified is section 32, and
its two open points section 33. No code of this revision exists.

Revised on 18 November 2026 for the plan stray-text
(`docs/plans/stray-text.md`), with two rules and no format change: the
running heads compared in section 3 may differ in length by up to 14
letters, not 8, so that a head the OCR damaged is still found alike
(section 3, "Heads of different lengths"); and a sign followed by
punctuation, "servus*.", is a reference candidate (section 11,
"References"). Layout changes with it (`docs/specs/layout.md` §3,
steps 2b to 4).

Revised on 19 November 2026 for the plan ocr-redo
(`docs/plans/ocr-redo.md`): a line of low Tesseract confidence is never
a heading (section 34, for books read with `ocr = "redo"`), and the
pieces of letters that Stubbs' text layer gives as words of their own
are removed as `letter_fragment` (section 35). `blocks.json` stays at
`format_version` 5.

Revised on 19 November 2026 for the plan note-links
(`docs/plans/note-links.md`): markdown writes a footnote whose
reference is not linked at the end of its chapter, under a heading
"Notes", instead of where it was printed (section 36, the owner's
decision of that day). structure and `blocks.json` do not change.

It builds on `docs/architecture.md` (cited as "architecture §8") and
`docs/glossary.md`, and on the layout spec, whose terms (body column,
footnote band, margin note, row, body word height, body line pitch) it
uses. structure reads `pages.json` (to check that every file comes from
the same PDF), `lines.json` (each page's regions, lines and words, and
the figures extract cut, from layout) and the book config (the language
of the word list, and the pages of the printed table of contents,
`contents_pages`), and writes `blocks.json` in the format of
architecture §8 (section 7).

## 1. Terms

Besides those of the glossary and the layout spec:

- **Head line**: the region that layout puts first on a page when it
  holds one line set apart above the rest (layout §3, step 3). It is a
  running head only when structure finds it repeated or numbered
  (section 3).
- **Stray mark**: a line above the head line with no letter or digit, a
  speck of the scan that the OCR read as ";", "^" or "—". Added to the
  glossary.
- **Body stream**: the lines of a page's body regions, in their order,
  once the removed lines are taken out. Paragraphs are found in it, and
  it continues over the page break.
- **Side text**: the text of a page's margin regions and footnote band,
  kept out of the body stream.
- **Guessed join**: a hyphen join that neither the word list nor the
  book's own words support, made anyway and recorded as guessed. Added to
  the glossary, under hyphen join.
- **Line height**: the median height of a line's words. The text layer
  gives a word the height of its OCR line, so in the owner's books,
  whose OCR gives one height per line, it says what size the type is
  (section 21).
- **Epigraph**, **source line**, **note group**: sections 22 and 12;
  in the glossary.

Numbers come from the measurements described in layout §1, called "the
research" below: a script run on 15 November 2026 on the output of the
walking skeleton (galley's first build, every stage in its simplest
form) for the four books of the evaluation set and the whole Kadesh and
Gierke books. In the four, each word was labelled by **the reference
text** (glossary), the Project Gutenberg edition proofread from the same
scan, which the evaluation tool (`docs/specs/evaluation.md`) compares
galley with; sections 3 to 9 call it "the reference" for short, and from
section 11 on "reference" alone is a note reference. Page means page index, from 0. A
**page-number form** is a word of 1 to 3 digits, or a well-formed
roman numeral in lower case ("xiv", not "Ill", "CIVIL" or Mariéjol's
initial "L" of "L AVENEMENT"), with at most one "." or "," after it.
The **body column** of a page, for structure, runs from the leftmost
left edge to the rightmost right edge of its body regions (section 6
says what a region's edges are); its middle is halfway between.

The numbers of sections 11 to 19 come from **the second research**: on
15 November 2026, galley at commit fb9c8e8 (the first plan, merged) was
run from analyze to structure on the six whole books and the six
excerpts, and prototypes of the rules below were run on its output, by
scripts kept outside git. For Haskins, Stubbs, Domesday and Mariéjol
each line was checked against the reference, aligned by the evaluation
tool; Kadesh and Gierke, which have none, were checked by eye on the
pages named. Some terms are used only in one section and are defined
there; these are used in several:

- a line's **height ratio** is the median height of its words over the
  body word height (the text layer gives a word the height of its OCR
  line, so this says something about type size, not much); a block's is
  the median over its lines' words;
- a line's **character density** is its characters, spaces left out,
  per point of its width, over the book's median for full lines (lines
  of 5 words or more whose sides lie within 3 pt of their region's
  edges), so that smaller type gives more than 1;
- a **wide line** has at least 5 words and is at least 150 pt wide;
- the **book's marker form** is the form, digits, bracketed or sign
  (section 11), that the most first words of the book's band blocks
  have: bracketed in Mariéjol (746 of 752), digits in Domesday (1,268 of
  1,269), Haskins and Stubbs (its index and lists), sign in Kadesh (24
  of its band blocks start with a sign, 14 with digits and 142 with
  neither, measured on 16 November 2026). A book whose band blocks start
  with no such word has none. Gierke had none until its introduction's
  notes became band regions (section 2); it now has digits, 61 of its 71
  band blocks (measured on 19 November 2026 at the plan stray-text's
  c62dcb1, with the page's median line height taken on its full-size
  lines).

## 2. What structure does, in order

The steps run in this order, and the order matters where one step
decides what a later one sees: the notes left in the body are taken per
page, before paragraphs are joined over page breaks, so that a note at
the foot of a page is never joined to the next page's text; all notes
are found before the quotes, because a note that layout left in the body
is set in small type and the quote rules would take it for a quote (in
the second research 32 of Domesday's false quotes and 40 of Mariéjol's
were such notes); the index entries are found before the quotes,
because an index is set in small type too; and margin notes are placed
last, once the notes exist, so that a margin note beside an endnote goes
inside it.

1. **Survey the book** (one pass over every page): the head lines, the
   book's own words for the hyphen rule, the body word height and body
   line pitch, the offset between page index and printed page number,
   the pages whose lowest line is a signature line (section 4), the
   index pages (section 17), the plate pages (the pages that have a
   figure of kind `plate`; section 18), the book's marker form (section
   1), whether the book has letter fragments (section 35) and the
   endnote section (section 12), which is found from the
   lines that start a paragraph by section 6's rules. The region of an
   in-page figure takes no part in the survey (`docs/specs/figures.md`
   §5). The body word height and body line pitch are
   measured as layout measures them, by `body_measures.body_measures`
   (architecture §12) on the rows that `body_measures.group_rows` makes
   of each page's words from every region. A book for which it gives
   `None`, with no page of 3 rows, takes the median height over all its
   lines, 0 without words, and a pitch of 0. (Owner, 15 November 2026:
   the median over all lines, the first rule, found 8.1 pt on the Kadesh
   excerpt, whose note lines outnumber its body lines, against 11.0 pt
   for the whole book, and so no band; layout's rule gives 11.0 pt on
   both. The two stages kept a copy each until the second plan, which
   moves the rule to the shared module.)
2. **Per page**:
   1. decide what each region is (below; on an index page, section 17),
      a region whose box is an in-page figure's being that figure's
      region (`docs/specs/figures.md` §5);
   2. remove the running head, page numbers, signature marks and stray
      marks (sections 3 and 4), the guide words of an index page
      (section 17), the letter fragments in a book that has them
      (section 35), and on a plate page its running head and stray
      words, keeping its caption (section 18); then, on a text page with
      in-page figures, find each figure's caption, take it out of the
      body stream, and remove the figure's region as `figure_text`
      (`docs/specs/figures.md` §5). The captions are taken here,
      before step 2.3 and step 3.1, so that a caption line is never a
      heading, a list item or a contents entry: Turney's
      captions open with "13." and Haynes' contents entries with "2.",
      and both look like a list's marker line;
   3. in the body stream, find the heading lines (section 14), except on
      the config's `contents_pages`, where only a contents run's title is
      one (section 30, rule 1), then the chapter summary under a
      heading (section 15), the epigraphs under a level-1 heading
      (section 22) and the runs of verse (section 16, rule 4);
   4. group the body stream into paragraphs (section 6), each heading,
      summary, epigraph and verse run being a block of its own, and each
      side region into blocks of its own (section 6); join hyphens
      inside each block (section 5), then split the words glued at a
      case change (section 24);
   5. take the notes left at the foot of the body (section 11, "Notes
      left in the body"), except on the pages of the endnote section
      and the index.
3. **Across pages**, in page order:
   1. make the band blocks of Haskins' bibliographical notes body
      paragraphs (section 16); find the list items (section 29) and the
      entries of each contents run (section 30), whose rules replace
      section 6's inside a list and on a contents page; join the last
      paragraph of each page with
      the first of the next when it runs on, and the hyphen at that page
      break (section 6), and a verse block likewise (section 16); a note
      taken in step 2.5
      never runs on into the next page's body, and no paragraph runs on
      into the first page of the endnote section;
   2. split a paragraph at a line beside a margin note that is indented
      (section 13, rule 3), which needs the paragraphs as joined; then,
      in every block, body and side text alike, attach a spaced "?",
      ";", ":" or "!" to the word before it, or put a no-break space
      before it in a French book (section 23), before any reference is
      looked for, so that a sign glued to a reference ("subjection ;^")
      becomes a candidate;
   3. the notes (section 11): cut the band blocks and the notes taken
      from the body into notes, take their markers, join a note that
      runs over a page break, make the endnotes (section 12), and match
      the references in the text to the notes, splitting each off its
      word;
   4. the index entries (section 17), and the links of the contents
      entries to their headings (section 30, rule 9);
   5. the quotes (section 16, rules 1 to 3), among the body blocks that
      are still paragraphs;
   6. place the margin notes (section 13);
   7. put the side text, figures and notes in reading order, and number
      the blocks (section 6); an in-page figure goes after the block
      that holds the last body line printed above it
      (`docs/specs/figures.md` §5, "Where the figure block goes").

The case split of step 2.4 and the spaced signs of step 3.2 change only
the words of a block, which no step between them and the matching of
references reads: the rules of those steps look at lines and their
boxes. So both are made on each block once its words are joined, over
page breaks too, and once a note's marker is taken off its first block,
the case split first, and before the references are matched: a word
joined at a page break is split too, a sign at the top of a page is
attached to the last word of the page before, and a sign that follows a
note's marker starts its block and stays. A figure's caption, made after
the references, gets both too.

**What each region is.** lines.json says nothing of it (architecture
§8), so structure decides from where each region lies, per page:

- the **head line** is the first region, together with every **region
  beside it** (below), when together they lie wholly above every other
  region, which may reach up to 2 pt into them, and the first holds one
  line with a letter or a digit (and any number of lines of marks above
  it). The 2 pt are for a word the OCR boxed tall: Stubbs' "MAPS." (page
  17) is boxed 18 pt tall and reaches 1 pt into the region below, and
  without them it was no head line, and a margin region beside nothing,
  instead of the page's heading. Measured on 17 November 2026 on the
  eight books, they change 3 pages: that one, Domesday's page 398, whose
  running head is then removed (layout §3, step 3, names it), and
  Gierke's page 11, whose "ERRATA." becomes a body line, joined to the
  contents paragraph of page 10 because it is not centred, instead of a
  margin note. Its words are those of the first
  region's line and of the regions beside it, left to right, as one
  line. When section 3 does not make it a running head, the first
  region is the first body region and each region beside it is what
  the rules below make it. A region beside the head line holds one line
  of at most 5 characters, spaces left out, whose top lies within 4 pt
  of the top of the first region's line, and lies wholly left or wholly
  right of the first region (section 3, "A short region beside the
  head");
- a **margin region** is narrower than a quarter of the page's widest
  region other than the head line (the first, on a tie) and lies wholly
  left or wholly right of
  it, or overlaps vertically a region wider than itself (a note that
  Stubbs cuts into the body column, which layout takes out of the body
  lines into a region of its own: layout §3, step 2b), unless it is in
  small type (as a band region below) and its top lies at most 2 pt
  above that region's bottom. Margin notes are about 30
  pt wide against columns of 266 to 317 pt; each column of an index is
  about half the width, so it is not a margin region;
- a **band region** is any other region, not the head line, that is in
  **small type**, its median word height (over its words) at most 0.85
  of the body word height or at most 0.82 of the page's **median line
  height**, and whose top is at or below the bottom of another region,
  or above it by at most 2 pt, neither the head line nor a margin
  region, that is not in small type (layout's two
  thresholds for the footnote band, layout §3, step 4). The page's
  median line height is the median, over the lines of the page's
  regions other than the head line's that are at least a quarter as
  wide as the widest of them (so that no margin region counts), of
  each line's median word height, taken over the lines of at least 0.9
  of the body word height when they are at least a quarter of those
  lines: layout's median row height (layout §3, step 4, "A page whose
  notes outnumber its text"), taken on structure's lines. Gierke's page
  50 holds 13 lines of text and 25 of notes, so the median of all its
  lines is a note line's and its five footnotes were body regions;
  measured on 19 November 2026 on the eight books laid out with
  layout's rule, the blocks change on that page alone, which gets its
  five footnotes.

  The test against the page is for notes set small against their own
  page but not against the book. Gierke's introduction (pages 13 to 49)
  is set in 10 to 11 pt, its notes in 8 pt, and the book's body word
  height is 9.0 pt, set by the translation: the notes are 0.89 of it,
  so layout made them a band (layout §3, step 4, "Small against the
  page") and structure, with the book's measure alone, made them body
  regions, their text paragraphs between the text's. Measured on 19
  November 2026 on the eight books laid out at 8c18e68, the test
  against the page makes band regions on Gierke's 31 pages 15 to 18, 23
  to 31, 34 to 45, 48 and 49 (the introduction's footnotes) and 109,
  146, 147 and 156 (the translator's notes marked "*"), and on
  Mariéjol's 25, 34, 159, 245 and 323, the pages where layout's test
  against the page made or moved a band; no other region of the eight
  books changes kind. Gierke gets 67 more footnotes (2 before, 69
  after), Mariéjol 6, and the paragraphs before and after them now run
  on over the page break; on Mariéjol's 34, 159 and 323 the notes were
  already taken from the body (section 11) and no block changes. With
  the median line height taken on the full-size lines (above), Gierke
  has 74 footnotes, 5 of them on page 50 (measured again on 19
  November 2026 at the plan stray-text's c62dcb1).

  The 2 pt are for a note
  that layout starts close under the text (layout §3, step 4, the
  gapless start): Domesday's note "1 See above, p. 359." on page 535,
  one line 66 pt wide, reaches 0.8 pt into the text above it and was a
  margin region, its note lost. Measured on 18 November 2026 on the
  eight books: with them, Domesday's pages 443 and 535 get their notes
  (443's two lines were paragraphs), and Kadesh's 40, on the layout of
  before the review, three; no other block changes;
- a **one-line note region** is a band region whatever its height and
  width, and whether or not it is narrow enough to be a margin region:
  the page's last region, not the head line, that holds one line whose
  first word is "1" and whose second word starts with a capital letter,
  and whose top lies below, as above (2 pt), the bottom of every other
  region that is neither the head line nor a margin region, of which
  there is at least one. Layout makes such a line a region of its own,
  after the body's and the margins', only when it is the page's band
  (layout §3, step 4, "A note of one line boxed as tall as the body"):
  the text layer boxes the line as tall as the body, 9 to 10 pt in
  Domesday, so no test of height can find it, and on Domesday's page
  163 the line, "1 D. B. i. 141 b.", is 55 pt wide, centred, and was a
  margin region. Structure does not repeat layout's test of width per
  character: measured on 19 November 2026 on the eight books laid out
  at 8c18e68 (and again at the review's fixes, the same day), 36
  regions have the rule's form, Domesday's 26, Haskins' 7 and Gierke's
  3 (pages 28, 48 and 61), and 11 of them change kind by it, exactly
  the lines of layout's rule: Domesday's pages 163, 174, 185, 278, 303,
  308, 315, 347, 472 and 485 and Gierke's 61. The other 25 are band
  regions by their height already, so a second test would change
  nothing on these books. Domesday gets 10 more footnotes on 9 pages (185 prints two on
  its line; 472's note was already a footnote, taken from the body by
  section 11), each linked to its reference, and its notes without a
  reference stay 323;
- every other region is a **body region**, in layout's order.

## 3. Running heads and page numbers in the head

A head line is a **running head** when its top lies at most 2 body line
pitches below the median top of the head lines of the book, and either:

- its letters, lower case, with everything else dropped, are at least 4
  letters and at least 0.70 alike (`difflib.SequenceMatcher` ratio) to
  those of the head line of at least one other page within the same 2
  pitches; or
- its first or last word is a page-number form that the book's head
  numbers confirm: an arabic one whose value plus the offset (below)
  gives the page index within 2, or one whose line without it is alike,
  by the rule above, to the line of another such head without its
  number. A roman form counts only on pages before the first arabic head
  number, here too.

**A speck as the head line.** When the head line has fewer than 4
letters and is not a running head, the line below it, the topmost line of
the page's other regions, is tested: it is a running head when its top
lies within the 2 pitches of the median head top and its letters are at
least 4 and 0.70 alike to those of a running head of another page. It is
then removed as a running head is, with its page number, and the speck
above stays as it is (in the text, or as a `stray_mark` when it has no
letter or digit).

**The head of a short section.** A section of two pages has one
running head, and the rules above miss it: no other page has a head
like it, and its page number is roman or misread. The second page of
Haskins' preface keeps "vlil PREFACE" (viii misread) in the text, and
that of Domesday's keeps "vi Preface.". Its likeness is to the section's
heading on the page before ("PREFACE" on Haskins' page 12, "PREFACE."
on Domesday's), which the rules above never compare, because it sits
lower than the heads: Haskins' at 100.8 pt from the top of the page,
against a median head top of 35.7 pt, which is 4.3 body line pitches
(the pitch, the median distance from one row's top to the next, is
15.2 pt in Haskins; layout §1). So a head line that the rules above
leave in the text is a running head when all three hold:

- its top lies within 2 pitches of the median head top, as above;
- its first or last word is **number-like**: 1 to 4 characters, each a
  digit or one of the letters i, v, x, l, c, d, m in either case, with at
  most one "." or "," after them ("vi", "vlil", "xiv.", "47"); and
- the rest of the line, its letters in lower case, at least 4 of them,
  is at least 0.70 alike, as above, to the letters of the topmost line
  of one of the two pages before it.

It is then removed as a running head is, below: the number-like word as
a `page_number`, recorded in `page_numbers`, when it is a page-number
form ("vi"), and otherwise with the rest of the line ("vlil", as a
misread number is). Two pages before, not one, so that a blank page or a
plate between the heading's page and the head does not hide it; a guess,
since on the six books the heading is always on the page just before.
The number-like word is required because without it the rule takes the
first line of a title page that repeats its half-title two pages before
(Gierke's page 8, "POLITICAL THEORIES", against page 6), a line of the
book's text. Measured on 17 November 2026 on the six whole books
(`lines.json` and `blocks.json` of the structure-second build of 16
November 2026, with a prototype of this rule): it removes exactly two
lines, Haskins' page 13 "vlil PREFACE" and Domesday's page 13 "vi
Preface.", and no other in any of the six books; without the
number-like word it also took Gierke's page 8. The excerpts
`haskins_front` and `domesday_front_flow` (`docs/specs/front-matter.md`
§6) hold both pages, whose first line their tests assert is a
`running_head` removal; on the `whole_book` tests, the new rule's
removals are exactly these two. With the likeness at 0.70 (17 November
2026, below) it also takes Gierke's page 58, "Analytical Snnittniry.
liii", the running head of its analytical summary, which the rule's
likeness, 0.70 now too, finds alike to the topmost line of a page
before it: three lines on the six books, each a running head (measured
on the `lines.json` of layout §3's new steps).

A number alone does not make a running head: a top line that ends with
a word that is also a roman form ("vi", "mix", "dix", "d", "c.", "i.")
or with a number of the text stays in the text. On Stubbs' page 267 a
speck read as "d" is the head line; under the first form of this rule
it was a running head and its page number "d", and the real head below
stayed in the body. The offset is taken first, from every head line
within the 2 pitches that has an arabic page-number form at an end, so
that it does not depend on which heads are running heads.

The first condition keeps a chapter's title from being taken for a
running head on the chapter's first page, where Haskins prints it as its
running head reads ("THE COMING OF THE NORTHMEN"): heads lie at a median
top of 36 pt in Haskins, chapter titles at 101 pt or lower. Three
pitches would be too many: Haskins' page 16 prints the book's title "THE
NORMANS IN" 2.85 pitches below the median, alike to the title page, and
Kadesh's article title on page 8 is about 2.7 below; both stay in the
text with 2. Two heads
are alike although their page numbers differ ("47" against "48"),
because digits are dropped, and although the OCR misread them ("THE
BATTLE OP KADBSH" for "OF KADESH"). The research rule this follows asked
for 3 other pages alike, not 1: it found the running heads of Haskins
with precision 0.976 and recall 0.992, and of Stubbs 0.965 and 0.977,
against the pages whose first line the Gutenberg edition does not have.
Asking for 1 finds 3 more pages in Stubbs and 13 in Mariéjol, and takes
11 more words the reference has in Mariéjol (5 of paragraphs, 6 of
notes) and none in the other three; it also finds Gierke's
section heads, which run over two pages only ("The Course of
Development.", pages 88 and 90).

The likeness was 0.75 until 17 November 2026, and 0.70 since: Gierke's
running heads of pages 72 and 78, read "List of ~-l ntlioritics." and
"List of slnthoriti* ixxiii", are 0.74 and 0.70 alike to the others and
stayed in the text, where the tall line of section 14 made each a
level-1 heading. Measured on the six public-domain books and the
owner's two with section 3's rules as built (`lines.json` of layout §3's
new steps), 0.70 takes 13 more head lines for running heads, and each
is one on the page image: Gierke's 58 ("Analytical Snnittniry. liii"),
72 and 78, and 10 of Mariéjol's garbled heads (48, 63, 77, 106, 250,
296, 300, 311, 329, 409); it loses none and changes nothing on the
owner's books.

**Heads of different lengths.** Two head lines are compared only
when their letters differ in number by at most **14**: a pair further
apart is not alike, without computing its ratio. The limit was 8, set
for speed (section 9), and it left two of Gierke's running heads in
the text, each damaged by the OCR: page 16's head reads "s
Introduction.", 13 letters, where the OCR dropped "Translator'" and
the page number, against the 23 of "Translator's Introduction." on
the other pages, and page 84's reads "JH if ex to List of
slntlioritic*. Ixxix", 31 letters with the page number read with a
capital "I", which is then no roman form and stays among the letters,
against 22. Their ratios to the nearest head are 0.72 and 0.717, above
0.70. Measured on 18 November 2026 on the eight books' `lines.json` at
main a0a1675, over every head line within the 2 pitches that section 3
did not take: with 14 the rule takes Gierke's 16 and 84 and Mariéjol's
158, each a running head on the page image, and no other line. The
test of section 14 that keeps a line alike to a running head from
being a heading keeps its limit of 8, which was not measured at 14, and
so do the two other tests that compare by this likeness: the head of a
short section, below, and the topmost line of a plate page (section 18,
rule 1).

**A short region beside the head.** Some books print the page number
outside the body column, level with the running head. Layout then makes
the number a margin region of its own (layout §3, step 2), and before
this revision the head line needed a first region wholly above every
other one, so the page had no head line and its running head stayed in
the text. Turney (section 21) prints its page number 13 to 15 pt beside
the head, outside the column, on the outer side, on every ordinary page
from page 15 to 303: on 260 pages the two are separate regions, their
tops equal on 252 and within 0.8 pt on the other 8, and the head stayed
in the text 98 times, mid-sentence, while 289 numbers became margin
notes. Gierke prints its roman numbers so on its pages 69 to 79 and 66
(tops 0 to 3.9 pt apart), and Mariéjol has a speck so on page 217
(1.7 pt). So the head line takes in each region beside it (section 2,
"What each region is"): one line of at most 5 characters, its top
within 4 pt of the head's, wholly left or right of it. The rules of
this section then see one line, and a page number at either end of it
is a page number as any other (Turney's "224" at the left end on even
pages, at the right on odd ones). The 5 characters take a roman number
up to "lxxiv" and a speck; a margin note of one short word beside a
head, as "Free" would be, has its top within 4 pt of the head's on no
page of the six books (measured on 17 November 2026 on the clean-text
build's `lines.json`: the regions of one line of at most 5 characters
within 4 pt of a head line's top are Gierke's 7 numbers and Mariéjol's
speck). Gierke's page 167 has a speck 12 pt below its head's top,
which is not taken; the head stays as now.

**A chapter label is never a running head.** A head line whose first
word starts with a **chapter label word**, CHAPTER, CHAPITRE, ESSAY,
PART, PARTIE, BOOK or LIVRE, in any case, the whole word but for one
or more ".", ",", ":" or ";" after it (the same test as section 14's
chapter label), is no running head, whatever
the rules above find: it is the first line of a chapter's heading
(section 14). Haynes (section 21) sets its chapter label at a top of 56
to 74 pt, 1.5 to 2.7 pitches below the median top of its heads (34.8
pt; within the 2 pitches on most openings), and its labels, alike to each other ("CHAPTER THIRTEEN",
"CHAPTER FOURTEEN"), were removed as running heads on 3 chapter
openings, their words lost from the chapter's heading; Turney's were
removed on 9 of its 10 openings, because no ordinary page had a head
line (above), so the labels were the only head lines left. The word
must be the whole first word: Domesday's running head
"Book-land and the Land-book." starts with "Book-land" and stays a
running head (28 pages). No running head of the six public-domain books
starts with such a word (measured on the clean-text build on 17
November 2026, on its 1,724 `running_head` removals); a book that
printed "CHAPTER IV" as its running head on every page would keep it in
the text, and none of the eight books does.

**What is removed.** In a running head, the page-number form at its
first or last word is removed as `page_number` and recorded in
`page_numbers` with position `head`; the rest of the line is removed as
one `running_head` removal; each line of marks above it is removed as
`stray_mark`. Every removal holds the removed words of one line, joined
by one space, with the smallest box that holds them; a
`PageNumber.text` is the word as printed, brackets and period included
("(l93)", "47."). Above a head line that is not a running head, the
marks stay in the text. When both end words are page-number forms, the
page number is the one whose value plus the **offset** gives the page
index, where the offset is the commonest page index minus printed number
of the book's arabic head numbers (each arabic page-number form at the
first or last word of a head line within the 2 pitches, both when both
are; Haskins 15;
Stubbs 17 on pages 19 to 51 and 21 from page 56, so 21; Domesday 25; a
tie takes the smaller), or the first word when no offset is known or
neither gives the page index. A roman numeral counts as a
page number only on pages before the first page whose head has an arabic
one that the offset confirms, so that Stubbs' "The Early Plantagenets.
ch. i." gives no page number "i.". A page number the OCR misread ("ii8" for 118) is not a
page-number form: it is removed with the running head, and the page has
no `page_numbers` entry.

The OCR splits some head numbers into two words ("The Villeins. 5 1" for
51, Gierke's "1 82"; 23 heads in Gierke, 4 in Stubbs, 1 in Domesday). A
run of words of digits at the start or the end of a head line (the last
of them may end with "." or ","), is joined without spaces and tested as
one word, as a page number at the foot is (section 4): its removal holds
the words joined by a space, and its `PageNumber.text` the run joined
without, "51".

**What was measured.** With a prototype of layout's head line and this
rule, the words
removed as running heads and page numbers, by what the reference makes
of them:

Words the reference lacks were rightly removed; words it has may be
words lost.

| book | pages with a running head | removed words the reference lacks | removed words the reference has |
|---|---|---|---|
| Haskins | 219 of 269 | 993 | 89 |
| Stubbs | 304 of 325 | 1,520 | 332 |
| Domesday | 525 of 546 | 1,459 | 406 |
| Mariéjol | 355 of 449 | 592 | 707 |

Most of the words "the reference has" are not lost words: the
reference's alignment gave the running head's words to the same words in
the text nearby ("Domesday Book" is a margin note too; "Catherine de
Médicis" is in Mariéjol's text hundreds of times). How many are real
losses was not measured; the reference pages check it by eye (section
9). Mariéjol's heads are often too garbled to be alike ("C^jnrvTxr nr
ifÉDICIS"); they stay in the text.

## 4. Page numbers at the foot, signature marks

These sit on the page's **lowest line**, the line of any region whose
bottom is lowest, once the head is removed.

**A page number at the foot** is a lowest line of one or two words
whose middle lies within 0.15 of the body column's width of its middle,
and whose text, the two words joined without the space, is:

- a page-number form (Kadesh's journal numbers, "83"), or
- in brackets: an opening "(", "[", "{" or "U", then 1 to 4 letters and
  digits with at least one digit, then a closing ")", "]", "}" or "J",
  where at most one of the two brackets may be missing: "(49)", and
  Mariéjol's OCR forms "U9)", "{2)", "(i8)", "(31J", "(ao3)", "(18I)".

A year on a title page ("1907", "1915") is neither.

**A page number by its value.** A lowest line that is one word of the
arabic page-number form (section 1) is a page number at the foot
wherever it lies across the page, when its value plus the page's
**local offset** is the page index exactly. The local offset of a page
is page index minus printed number of the nearest page, before or
after it (before on a tie), that has a head page number of the arabic
form in `page_numbers` (section 3). Section 3 removes a running head's
page number whatever offset it reads with, so Turney's heads after the
plates, running heads by their likeness, give such numbers although the
book's commonest offset (13) does not confirm them. A local offset, not the book's
commonest one, because the offset changes inside a book: Turney's is
13 before its 16 pages of plates (pages 164 to 179) and 29 after
them, Stubbs' 17 on pages 19 to 51 and 21 from page 56. Turney prints
the number of a chapter's first page at the foot, aligned with the
chapter label's indent, not centred (page 26: x 82 to 92 pt in a
column from 37 to 411, its middle 0.36 of the column's width left of
the column's middle, against the 0.15 above), on its 15 opening pages
(14, 26, 39, 56, 77, 104, 134, 148, 189, 217, 229, 252, 278, 300 and
301), and each stayed in the text mid-sentence. All 15 numbers meet the
value rule (measured by the survey of 17 November 2026, section 21).
The value keeps out what the centring was set against, a lone number
on the lowest line that belongs to a note or a table (a prototype that
took any lone number on the lowest line took 330 words on Mariéjol's
pages, above): such a number gives the page index by chance only. A
roman number at the foot is not taken by
it (Turney's pages 10 and 11, whose small foot numbers layout reads as
a band: they stay notes without a marker). Not measured on the six
public-domain books, whose foot numbers the centring rule takes; the
`whole_book` tests show any change.

It is removed as `page_number` and recorded with position `foot`.
Kadesh then has two entries on the pages where the journal's number
stands alone on its line, the book's at the head and the journal's at
the foot; on some pages (40, 52, 54) the journal's number shares a row
with a note and stays in the text. The index stage chooses between the
two (architecture §11). A prototype that also took a lone number
anywhere on the lowest line took the lowest line of 329 of Mariéjol's
449 pages, 330 words, of which the reference labels 43 as note words;
the rule as written was not measured, and the reference pages check
it.

**Mariéjol's signature line** holds the page number between the
signature and its number: "MARIÉJOL. Cath. de Médicis. (49) 4", read
"UAMiàjoL. CmOl da Médidib (l93) 13" on page 210, on about 26 pages. A
lowest line of more than two words, one of which is a page number in
brackets as above whose middle lies within 0.15 of the column's width of
the column's middle, is a signature line when its words left of that
page number hold at least 4 letters and are at least 0.5 alike, by their
letters, to the words left of the page number on the lowest line of any
other page of the book. Without the 4 letters, a note's last line that
starts with its marker "(5)" would match another such line, empty
against empty: 13 of Mariéjol's pages, page 214 among them. The page number is
removed as above and every other word of the line as `signature_mark`.
The signature lines measured were 0.54 to 0.73 alike to one another
(0.5 is set below the lowest).

**A printer's signature mark** of the Cambridge kind, "M. 4" and "4—2"
in Domesday, "I — 2", "M. 2" in Gierke, is the lowest line, or the line
above it (the lowest of the lines left) when the lowest was a page
number, when it has at most 3 words
and at most 6 letters and digits in all, at least one of them a digit;
is not a page number by the rules above, nor a number alone ("1900."),
but letters and digits ("M. 4", "d2") or digits around a dash or a
space ("4—2", "12 2"); and has its middle at least 0.3 of the column
width right of the column's left edge (Domesday prints "M." near the
left edge and "4" far right on page 74, so the line's start would not
do). It is removed as `signature_mark`. The position keeps a note's
last line ("4 Ibid. 29.", "p. 83.") from being taken: such a line is
short and at the left edge, and the middles of the signature marks found
by the research lie from 0.42 to 0.83 of the page width. The research found 53 in Domesday, every 16 pages, with OCR forms
such as "1G-2", and about 19 in Gierke ("£ 2", "d2"), none in Haskins,
Stubbs and Kadesh.

**A signature mark of letters.** A line is also a printer's signature
mark, with no digit, when it is the lowest line (or the line above a
page number), has at most 6 letters and its middle at least 0.3 of the
column width right of the column's left edge, as above, and is two
words, the first a capital letter and a full stop, the second
starting at least half the column's width right of the first's left
side. Gierke signs the gatherings of its introduction with letters,
"M." at the left and "c", "d", "e" at the right (pages 38, 54 and 70),
and the OCR reads some numbered marks without their digits ("M. IT",
Gierke's page 246; "M. H", Domesday's page 234). Each stayed in the
text, in a note's last line or as a block of its own: on page 38, where
layout makes the foot a band, "M. C" became a footnote without a
marker, and the closing quotation mark of the body a reference to it.
The OCR boxes Gierke's "M." 128 pt wide on page 38, so the distance is
measured from its left side: 256 pt there, in a column of 297. A line
of text has no such gap between two words. Measured on 19 November
2026 on the eight books' `lines.json`, the rule removes those five
marks and no other line; one more lowest line of this kind, Gierke's
page 166, has its "M." read as '"^T"' and stays.

**A signature mark beside the lowest line.** When the lowest line is
none of these, the line above it (the lowest of the lines left) is
removed as a printer's signature mark when it is a printer's signature
mark by either rule above,
its bottom lies less than one body line pitch above the lowest line's
bottom, and its top lies at least 2 pitches below the top of the line
before it in its region (a line first in its region is not taken). On
Domesday's page 428 the text layer boxes
the "[0" of a table's last row, "[0 17 1]", at the foot of the page,
5.2 pt below the signature mark "26—2" beside it, so "[0" was the
lowest line and the mark stayed in the text, glued to the table's last
word, "Norfolk26—2" (the "[0" had been taken for a page number at the
foot until "A page number boxed apart", layout §3, step 3, left the
page's body the heading alone and the body column too narrow to centre
it). The mark lies 2.9 pitches below the line before it, "Norfolk".
The 2 pitches keep out the last line of an index's other column: without
them the rule took "of, 282" on Stubbs' page 315 and "204 f." on
Haskins' 268, 0.7 pitch below the lines before them. Measured on 19
November 2026 on the eight books' `lines.json`, the rule removes the
mark of Domesday's page 428 and no other line.

A word of a lowest line that is none of these stays in the text. A page
with no body region has no body column, and nothing is removed at its
foot.

## 5. Hyphens at line ends

A line whose last word ends with a hyphen, with a letter or digit
before the hyphen, is joined with the first word of the next line of the same
block, when that word starts with a letter or digit, and with a digit
when a digit is before the hyphen. A line of one word is no exception.
A digit here is one of the ASCII digits 0 to 9, and a letter a
character for which Python's `str.isalpha` is true.

A hyphen at a line's end is the ASCII hyphen-minus "-" or the not sign
"¬" (U+00AC). The OCR of two of the owner's books, modern books scanned
with the same OCR, marks every line-end hyphen with "¬" ("liter¬"
"ature"): 1,020 words in one book and 2,219 in the other stayed broken
in `book.md` while only "-" was a hyphen (measured on 17 November
2026). The text layers of the six public-domain books end 2 of their
6,000 hyphenated lines with "~" or "¬", and none with another hyphen;
"~" is not a hyphen. "¬" follows every rule of this section as "-"
does, the number before a word, the digit ranges and the three kinds of
join, and where a rule keeps the hyphen, the word it gives holds "-",
never "¬": "proto¬" "journalist" is looked up as "proto-journalist" and
"1830¬" "40" gives "1830-40". The change's `before` keeps the two words
as the text layer has them. A "¬" anywhere else, not the last character
of a line's last word, is text and stays as it is.

A **number before a
word**, a digit before the hyphen and a next word that starts with a
letter, is not joined: both words stay as they are, and no change is
recorded. In Haskins' index "136-39-" ends a line and
"Bryce," starts the next, and the page prints "136-39." (the OCR read
the full stop as a hyphen), so the join "136-39Bryce," was wrong; "37-"
in the same index is another. A digit before the hyphen and a next
word that starts with a digit are always joined with the hyphen kept,
whatever follows the digits: a range, "1066-" "1087" or "289-" "303",
and also "235-" "37-", which gives "235-37-", and "149-"
"57;insouthernItaly,", which gives "149-57;insouthernItaly,"
(Haskins' index, pages 268 and 270). "12th-" "century" has a letter
before the hyphen and is joined as any other word. This rule was set
on 15 November 2026, after the owner's check of Haskins' index. A
hyphen at the end
of a page's last body line joins with the first word of the next page's
body stream, when the paragraph runs on (section 6). Every join is a
`WordChange` whose `before` is the two words and `after` the one word,
on the page of the first; it is one of three kinds, tried in this order
on the **key** of each form (lower case, with the characters that are
not letters, digits, hyphens or apostrophes stripped from both ends):

**A lower-case end and a capital start.** When the letter before the
hyphen is in lower case and the second part starts with a capital
("half-" "Danish", "Con-" "NORMANDY", "exhaus-" "The"), the two are
joined only when the book prints the hyphenated form whole: the change
is then `hyphen_kept`. Otherwise they are not joined at all, and no
change is recorded. Measured on the six books on 15 November 2026, such
pairs were 157 of the joins, most of them a word and the first word of
another line (a head, a note, the next entry) or a compound with a
proper name ("Vice-Regent"), and 41 of them were recorded as
`hyphen_join` on keys the word list happens to hold ("beThe", "naR",
"dLa"). This rule was set on 15 November 2026. Further, the
word list is never evidence when the second part has fewer than 2
letters ("Con-" "1"): only the book's own words count then.

The other joins are of three kinds:

1. **The hyphen is kept** (`hyphen_kept`, new): the hyphenated form's key
   is among the book's own words and the joined form's key is not.
   In a book that prints "proto-journalist" whole and never
   "protojournalist", "proto-" "journalist" becomes "proto-journalist"
   (an example made up for the tests: Haskins prints it only at a line
   end, so there the join is guessed); Haskins prints "Anglo-Saxon"
   whole, so "Anglo-" "Saxon" becomes "Anglo-Saxon". A join after a
   digit, "1830-" "40" or "235-" "37-", always keeps the hyphen.
2. **The hyphen is dropped** (`hyphen_join`): the joined key is in the
   word list of the book's language (`wordlist.word_list`, a list of
   words drawn from Tesseract's language data, compared lower-cased: it
   holds "Normandy" and "Gloucester" capitalised) or among the book's own
   words. "neces-" "sary" becomes "necessary". When the first part holds
   an apostrophe ("'" or "’"), as French elision does, the part of the
   joined word after the last apostrophe is looked up too, in both:
   "d'in-" "signes" becomes "d'insignes" when "insignes" is known. The
   rule asks for the apostrophe in the first part, not for the book's
   language, which `join_hyphen` is not given; an English possessive,
   "Wil-" "liam's", has it in the second.
3. **Guessed** (`hyphen_join_guessed`, new): neither. The hyphen is
   dropped, as in 2 (owner, 15 November 2026), and the change is
   recorded as guessed, so that the correct stage, a pass by a local
   language model, or the owner can review the guessed joins one by one
   from `blocks.json`. galley may later give a local model these
   undecided cases; that is not part of this plan.

The **book's own words** are the keys of every word of every line of
`lines.json`, except the last word of a line that ends with a hyphen and
the first word of the line after it, unless the two are a number
before a word: a word counts as the book's spelling only where it was
printed whole. They are gathered in the
survey, before anything is removed; running-head words among them do no
harm.

Measured, against the Gutenberg edition, on the line-end hyphens of the
whole book whose right form the reference shows:

| book | line-end hyphens | right | wrong | guessed | of the guessed, dropping is right |
|---|---|---|---|---|---|
| Haskins | 1,139 | 954 | 3 | 35 | 22 |
| Stubbs | 1,556 | 1,193 | 0 | 33 | 28 |
| Domesday | 456 | 961 | 675 | 9 | 78 | 54 |
| Mariéjol | 2,172 | 1,219 | 0 | 192 | 181 |

The research's "wrong" ones are compounds the book also prints joined,
or prints hyphenated only at line ends: "sea-faring", "pre-eminently",
"folk-land", "land-holders", "over-rating". The rest of each book's
hyphens are lines the skeleton mixed with a margin note or a note
column, misreadings, or hyphens the reference does not show; Kadesh (110
hyphens, 71 with evidence) and Gierke (714, 483) have no reference. A
line that holds only a sign of a note reference ("^", "*" or "•",
section 11) between a line that ends with a hyphen and the next line is
passed over: the hyphen is joined with the first word of the line after
it, and the sign goes after the joined word, where section 11 finds it
as a reference (Haskins page 71: "fol-", "^", "lows:" give "follows:",
"^"). A hyphen whose next word is not in the same block, or does not
start with a letter or digit, is left as it is, with no record. A line of one word
between two line-end hyphens is joined twice: the second change has the
first join's word as its first word ("pre-" "Anglo-" then "preAnglo-"
"Saxon"), and the fidelity check, which undoes every change, still
balances.

**A hyphen read as a sign.** The text layer sometimes reads a line-end
hyphen as one of the signs of a note reference, "*", "^" or "•"
(section 11): Stubbs' "the impulse of aggres*" at the foot of page 24,
whose hyphen the scan prints as a faint dot, before "sive warfare," on
page 25; Haskins' "pil^" "grims" (page 226), checked on the page
images on 19 November 2026. The two parts stayed apart with the sign
between them in `book.md`. In every block, the last word of a line
that `join_hyphen` does not join is joined with the first word of the
next line of the block, over a page break too, when all of these hold:

- the first word ends with one such sign after a letter, and has 2
  letters or more without the sign;
- the second word starts with a lower-case letter;
- the joined word, the first without its sign followed by the second,
  has a key in the word list (with 2 letters or more in the second
  word) or among the book's own words, as for `hyphen_join`.

The join is never guessed and never keeps a hyphen: without such
evidence the words stay as they are, since a reference glued to the
last word of a line is far more common ("justice*" "or", Domesday page
106; "corpus*" "with", Gierke page 226). It is a `WordChange` of the
reason `hyphen_join` whose `before` is the two words as the OCR has
them and whose `after` is the joined word followed by the sign:
("aggres*", "sive") becomes ("aggressive", "*"). The block holds only
the joined word; the sign is removed, with the reason `misread_hyphen`
(architecture §8), its page that of the change and its box that of the
word it ended: the first line of that page in `lines.json` whose last
word is the change's first word, which the join was made on. A word
that an earlier join made ends no line of `lines.json`, so it is not
joined over a sign: in "con-" "tinu*" "ally", a line of one word between
a hyphen and the sign, the first join gives "continu*" and the sign
stays where it is. No other step before the joins changes a line's last
word; were no line found, structure stops with an error, as for any
fault of its own. The
fidelity check accepts such changes only when the `misread_hyphen`
removals of each page and sign number exactly the changes over that sign
on that page, so that a sign is never dropped without a record and no
such removal stands without its join.

Measured on 19 November 2026 on the `lines.json` of the seven books run
by the plan ocr-redo: 31 lines end with a letter and one of the signs
(Stubbs 5, Haskins 2, Domesday 8, Gierke 15, Kadesh 1, Haynes and Turney
none), and the rule joins 2 of them, "aggressive" and "pilgrims", both
right on the page images. The others give no known word ("Oar*"
"endon,", Stubbs page 97, a misreading of "Clarendon"; "inter*" "were",
Gierke page 176) or a next word in capitals.
Verified by unit tests of the join (the cases above, and "justice*"
"or", a capital, one letter before the sign, two signs and no evidence
left apart), of `join_lines` over a page break, of `make_blocks` on two
literal pages, whose removal `misread_hyphen` holds the "*" with the box
of "aggres*", and of the fidelity check, which fails when that removal
is missing or when the sign is dropped from the change's `after` too.

**A hyphen lost in a margin note.** In a margin note the OCR often
drops the line-end hyphen or reads it as a full stop, and the two parts
of the word stay apart in the EPUB: "nation" "al" and "unfree" "dom"
(Domesday pages 77 and 75), "move." "ment," (Gierke page 88) and
"posi." "tion" (Stubbs page 58), all four checked by the owner on the
page images on 17 November 2026. Within a margin-note block, the last
word of a line that does not end with a hyphen is joined with the first
word of the next line when all of these hold:

- the first word ends with a letter, or with a letter and one full stop
  (the hyphen read "."), and has 2 letters or more without the stop;
- the second word starts with a lower-case letter;
- the joined word, the first without its stop followed by the second,
  has a key in the word list (with 2 letters or more in the second
  word, as for `hyphen_join`) or among the book's own words;
- the second word is a fragment: its key is printed after the first
  word of a line of `lines.json` at most 8 times in the whole book. A
  word printed whole is printed inside lines too; "ment", "tion" and
  "dom" are not.

The join is a `WordChange` of the reason `hyphen_lost`, whose `before`
is the two words as the OCR has them and `after` the joined word, on
the page of the first: ("move.", "ment,") becomes ("movement,",). The
full stop the join drops is in `before`, so the fidelity check, which
undoes every change, finds it; and it checks that the change does no
more: the first word, less one final ".", followed by the second, is
the joined word, and the joined word is a word of a margin-note block
that starts on the change's page, the only blocks where the join is
made, or a word that a chain of `punctuation_attached` and
`case_split` changes on that page turns into such words (sections 23
and 24, made after the join: Domesday's margin note "popula- tion ?" on
page 461 gives "population", then "population?"; a join may be split
and a sign then attached to its second part). The chain is followed
back from the margin note's words, so a join is admitted only when the
words its chain ends in are words of a margin note of its page. Tried after `join_hyphen`, which a line ending with a
hyphen goes to.

Measured on 17 November 2026 on the lines of whole Stubbs, Domesday and
Gierke (galley at 89ed733), counting every pair of lines in a block
whose joined word is in the word list or among the book's own words.
The word list holds fragments and joins ("ment", "tion", "al", "dom",
and "ofthe"), so it cannot tell a fragment; the count of the second
word inside lines does. In margin notes the right joins have a second
word printed inside lines 0 to 5 times ("al" 5, "nation" "al", Domesday
page 77) and 9 times ("length" "wise.", page 409); the first wrong one
11 ("is" "defined", Gierke page 196), then "de" "facto." (12) and the
common words ("of" "the", 7,130), each 2 printed words. With 8, the
rule makes 32 joins in margin notes (Domesday 20, Gierke 11, Stubbs 1),
all right by the list in `tmp/broken-word-joins.md` of the plan's
worktree (not committed), and loses "lengthwise". In paragraphs and
quotes the same rule would make 24 joins, of which 11 join two printed
words ("de" "facto", "in" "spite", "stand" "alone", "well" "known",
"an" "ally"), since a body line ends with a whole word far more often
than a note's short line does; so the rule is for margin notes only.

## 6. Paragraphs, side text and the order of the blocks

**Paragraphs.** In the body stream, a line starts a new paragraph when:

1. **it is indented**: its left side is 5 to 40 pt right of its region's
   left edge, and the line before it in the stream ends more than 3 pt
   short of that line's region's right edge; or
2. **it is centred**, or the line before it is: both of its insets from
   the region's edges are at least 15 pt and differ by at most 10 pt. A
   line of a region of fewer than 5 lines is measured against the page's
   body column (section 1) instead, since the box of such a region is
   the box of its lines and its one line would never be centred in it:
   Mariéjol's "CHAPITRE II" to "XI", Domesday's "ESSAY I." to "III.",
   Haskins' "INDEX" and Gierke's "NOTES." ran on from the page before.
   Such a title starts a paragraph also at a page break, as rule 2 says,
   which is the chapter's first page of section 9.
3. **it starts with a hanging number**: its first word is 1 to 3 digits
   with nothing after them, its second word starts with a letter or a
   quotation mark, it is not on a page of the config's
   `contents_pages`, and its left side
   lies 5 to 20 pt left of its region's **text edge**, the commonest
   left side (layout §1) of the region's lines whose first word is not
   such a number, when the region has at least 3 of those. This is a
   note printed with its number hung in the margin and its text and
   later lines at one left edge (a hanging indent), as Turney prints
   its notes at the back (section 12): a note's first line is not
   indented against the region, so rule 1 never fired, and its notes
   and bibliography came out as four `quote` blocks of 1,193 to 13,992
   words. Measured on 17 November 2026 on the `lines.json` of the
   survey's runs (section 21): it starts 509 lines of Turney, every one
   a note's first line on its notes pages 252 to 277 (and one on page
   174, a caption), hung 8.8 to 18.8 pt; the survey measured the hang
   of all of Turney's markers at 11 to 17 pt from the text. The 115
   markers of the left columns are margin regions in that run; layout
   keeps them in their lines from now on (layout §3, step 2), and the
   rule takes them too. In the six public-domain books it starts 59
   lines: 42 rows of tables on Domesday's pages 158, 425, 479 and 499,
   13 lines of Gierke's printed contents (pages 63 to 66, which are in
   its `contents_pages`), 3 of Mariéjol's notes and 1 line of Stubbs'
   index; none of Haynes'. A start inside a table cuts the table into
   more paragraphs than before; galley has no table kind (section 28).
   The second word's letter and the contents pages were added in the
   review of the plan's work package 3 (18 November 2026): the rule as
   first written also started 39 rows of Domesday's tables (pages 158,
   425 and 479), whose number columns layout gives as regions of their
   own ("1 10", "3 0)"), and 8 lines of Gierke's printed contents
   (pages 65 and 66), and a margin note beside such a row was placed
   before it ("(?)", "E]"); Domesday had 2,420 blocks against 2,381
   without the rule. With them it starts no line of Gierke and one of
   Domesday ("235 L 3 J", page 425), 2,382 blocks; Turney's notes keep
   their 620 starts, and its page 174's caption loses one. galley-eval
   gives Domesday's paragraph precision and recall 0.860 and 0.891 with
   the rule and without it, since its reference texts do not hold the
   tables, so the cut was judged on the page images: the rows are cells
   of a table, not paragraphs.
   A line whose first word is one character that is not a digit, with
   a second word, hung so (5 to 20 pt left of the text edge), starts a
   paragraph too when the next three lines of its page that start with
   a hanging number read 2, 3 and 4: a note's "1" the OCR misread
   (section 12, the misread marker; Turney's "x", page 258). Measured on
   18 November 2026 on the eight books' `lines.json`, it starts that
   line and no other.

A line after a line that ends with a hyphen (its last word ends as
section 5 asks of a first part, "-" after a letter or digit), unless
it is a number before a word (section 5), never
starts a paragraph, at a page break too, so the hyphen is joined. The first line of a body
region after the first on a page is judged like any line, with the last
line of the region before as "the line before"; the book's first line
starts a paragraph. A region's **left and right edges** are the commonest left and right sides
of its lines, to 2 pt, or, with fewer than 5 lines, the sides of its box,
taken on the region as layout gives it, before any line is removed.
A heading is a centred line, and so a paragraph of its own; a title of
two lines makes two.

At a page break, the first line of a page's body stream continues the
last paragraph of the page before that has a body stream, unless rule 1,
2 or 3 makes it a start; for rule 1, "the line before" is the last
line of that page, measured against its own region's right edge. A page
with no body stream (a plate, a blank page) does not end the paragraph.

**A short last line at a page break.** The first line of a page's body
stream also starts a paragraph when the last line of the body stream of
the page before ends more than 20 pt short of its region's right edge
and its last word ends with ".", "?", "!" or ":", or with one of them
followed by closing quotation marks or brackets, with 1 to 3 digits
glued after all of them allowed (a note reference: "tendency.43"),
unless the first word of the page's line, past any opening quotation
marks, starts with a lower-case letter: a sentence that runs on is not
cut, whatever the line before it ends with; or unless the last line
starts with a word of a note marker's form (section 11, "The marker of
a note": digits, bracketed or a sign) followed by more words, the first
line of a footnote left in the body ("1 D. B. i. 141.", "8 Companies
Act, 1862, sec. 4.").
Rule 1 cannot see such an end when the next page's first line is not
indented: a chapter's first line set flush left, or a line set in a
measure of its own. On Turney's pages 12 and 13 (section 21), the
acknowledgements end with a short last line and the next page holds
only the book's epigraph, in its own narrower measure, so one block ran
from the acknowledgements over the epigraph into the introduction's
first paragraph. The rule is meant for page breaks only: inside a page
the same test is the "third rule" that the paragraph rules left out,
because the OCR cuts lines short (Mariéjol).

It does not apply where the rules keep a block across a page break on
purpose: a line after a hyphen (above, which a line ending with
punctuation never is), a verse block that runs on (section 16, rule 4),
the index pages (section 17); and it changes nothing where a block is
already cut (the endnote section's edges, section 12, and a note that
section 11 takes out of the body). A note that section 11 leaves in the
body is not cut off: it is often the last body line of its page, short
and ending with ".", and the text it interrupts runs on at the next
page, so that before the lower-case condition the rule cut a sentence
in two there (Domesday's pages 131 and 132, "We think it" / "highly
probable that"; Gierke's 39 and 40).

Measured first on 17 November 2026 on the survey's runs and the
clean-text build, counting the page breaks where a paragraph ran over
and the rule would cut it ("first count" below; Turney's and Haynes'
come from the survey, section 21, which counted only the breaks whose
next first line is not indented). Measured again on 18 November 2026 by
galley's code on the eight books' `lines.json` of the plan owner-books'
layout, on the pass of the paragraphs that reaches `blocks.json`
(section 12 finds the endnote section on a first pass): the breaks
where the rule holds and no other rule of this section starts the
next page's first line, before and after the lower-case condition:

| book | first count: paragraphs running over a page break | first count: last line more than 20 pt short | first count: cut by the rule | 18 November: cut, without the lower-case condition | 18 November: cut |
|---|---|---|---|---|---|
| Turney | (survey) | 29 | 15 | 26 | 24 |
| Haynes | (survey) | 22 | 18 | 28 | 28 |
| Haskins | 217 | 1 | 1 | 0 | 0 |
| Stubbs | 280 | 30 | 15, 13 of them in the publisher's lists after the text | 2 | 2 |
| Domesday | 456 | 15 | 8 | 8 | 6 |
| Mariéjol | 353 | 28 | 15 | 14 | 5 |
| Kadesh | 35 | 9 | 8 | 8 | 3 |
| Gierke | 147 | 32 | 32 | 32 | 13 |

Stubbs' publisher's lists are excluded pages since 17 November 2026
(section 27, point 4). Of the cuts without the lower-case condition, 10
were read against the page images (Stubbs' pages 27 and 151, Domesday's
28, 176, 418, 478 and 484, Gierke's 25, 41 and 146): 5 end a
paragraph, 1 falls inside a table, and 4 follow a note left in the
body, the text before it running on in lower case, which the condition
now keeps. Of the cuts with it, 5 were read (Kadesh's pages 33 and 50,
Gierke's 39 and 156, Mariéjol's 48): 1 ends a paragraph (Kadesh 50);
3 follow a note left in the body where the text runs on with a capital
("every" / "English township", Gierke 39; "the" / "People", Gierke
156; Mariéjol 48), which the condition cannot see; and Kadesh 33 cuts
"town of" / "Shabtuna", where layout gave the column beside the map
before the line that ends the stream. The marker condition then keeps
Gierke 39 and Mariéjol 48 and 281, and no other cut: Mariéjol has 3
cuts, Gierke 12, the other books as in the last column. Gierke 156
stays cut, since its note's last line is its second, which starts with
no marker. The 20 pt is the survey's and was not varied: the
justified lines of both owner's books end within about 1.3 pt of their
region's edge (section 22's opening pages), so a line 20 pt short is
not a justified line.
A plate's lines are not in the body stream: they are its running head,
its caption, which becomes a figure block, and its stray words (section
18). So a paragraph runs on over a plate, and a word split before a
plate is joined with its end after it. (In the first plan, before
analyze recognised plates, the first line of a page with a figure and
of the page after it started a paragraph, so that a plate's words were
a paragraph of their own.)

Measured on the lines of words the reference puts in the body, as if
layout had separated the regions without fault, against the
reference's paragraph starts:

| book | precision | recall | rule 1 alone, precision / recall |
|---|---|---|---|
| Haskins | 0.85 | 0.89 | 0.87 / 0.79 |
| Stubbs | 0.75 | 0.74 | 0.75 / 0.66 |
| Domesday | 0.86 | 0.82 | 0.90 / 0.77 |
| Mariéjol | 0.82 | 0.81 | 0.86 / 0.78 |

A third rule was measured and left out: a line whose top is at least 2.2
body line pitches below the line before. It added 0 to 4 points of
recall and cost up to 7 points of precision (Mariéjol, where the OCR
cuts lines). Stubbs' cut-in notes start the body lines beside them 60 pt
in, outside rule 1's 40, so they do not make false starts; in the first
plan they mixed their words into those lines, which layout's step 2b
now mostly prevents. The
starts missed are chapter openings, where the first line is not
indented and follows a centred title only when the title is on the same
page; verse and dialogue (Haskins) give false starts.

**Side text.** Each margin region becomes one block of its own; each
band region is grouped into blocks by rules 1 and 2, as the body is,
without the page-break rule, with the sides of the band's box as its
edges whatever its number of lines; hyphens are joined inside each. On a
band of 5 to 9 lines the commonest right side is often that of its
short last lines, and rule 1 then never fired: Domesday's page 83 gave
its six notes as one note, Mariéjol's page 214 its three as one. A note
whose first line is indented from the band's left side after a short
line starts a block; Domesday prints two short notes side by side on one
line (page 83, notes 1 and 2), which stay one block. What kind
of block they become was decided by the owner (section 10): a margin
region is a `margin_note` block, and each
block of a band region is a `Note` of one block, with `referenced`
false and `marker` empty (the printed marker stays as the first word of
its text); section 11 cuts these blocks into notes and takes their
markers off. No word of side text is lost or merged into the body.

**Order.** `blocks` holds the body's blocks in order. After the
paragraph that holds the last line of a page's body stream, which may
have started on an earlier page or run on to a later one, come that
page's figure block (section 18) and, in the first plan, its margin
notes, by the order of their regions; the second plan places margin
notes by section 13 instead, and only those with no line beside them
stay here. A page whose body stream is empty puts its side text after
the last block so far. So the side text of a page is read after the
paragraph in which the page's body ends, never inside it, and in page
order.

A page's notes follow in `notes`, in the order of their regions and
lines. markdown writes each note after a block chosen by the block's
**first page**, the page of its first origin, which for a paragraph
that runs over a page break is the page it starts on: after the last
block in `blocks` whose first page is the note's first page or an
earlier one, or before every block when there is none (section 10). An
example: a paragraph runs from page 3 to page 4, and page 3 has a margin
note and a note. `blocks` holds the paragraph, then page 3's margin
note; the paragraph's first page is 3, and so is the margin note's, so
page 3's note goes after the margin note, and a note of page 4 goes
there too, after page 3's note. Had the rule used the last page a block
has a line on, the note of page 4 would come between the paragraph and
page 3's margin note.

**Ids and origins.** A block's id counts the blocks that start on its
page in this reading order, body, margin-note and the blocks inside
notes together, each note's blocks counted where markdown writes the
note (architecture §7); a note's id counts the notes that start on its
page.
A block's `origin` has one entry per page it has lines on, with the box
that holds those lines. Each block has one span, its text, with emphasis
`none` and no note reference: its lines' words joined by single spaces,
and a joined word in place of its two parts.

## 7. The format it writes

`blocks.json` as architecture §8 gives it, at `format_version` 5 (4 before the revision of sections 29 to 33, 3 before the plan owner-books):

| field | in the first plan | added by the second plan |
|---|---|---|
| `blocks` | `paragraph` blocks, and `margin_note` blocks (section 10); `level` and `figure` `None` | `heading` blocks with `level` 1 or 2 and their chapter label in `label` (section 14); `chapter_summary` (15); `quote` and `verse` (16); `index_entry` (17); `figure` blocks with their image (18); margin notes placed before their paragraph (13) |
| `notes` | one note per block of a band region, `referenced` false, `marker` empty (section 10) | the notes cut and marked by section 11, each with its `kind` (`footnote`, or `endnote` by section 12), `referenced` true when its reference was found, and margin notes among its blocks (13) |
| `removals` | the running heads, page numbers, signature marks and stray marks | the guide words of an index (`guide_words`, 17); a plate's running head and stray words (`running_head`, `plate_text`, 18) |
| `word_changes` | the hyphen joins, of the four reasons of section 5 | the `note_marker` splits of section 11 |
| `page_numbers` | the head and foot page numbers removed | |

The lists are in a fixed order, so that the file does not depend on the
number of workers: `removals` by page, and on a page from the top line
down and, on one line, from left to right; `word_changes` by the page of
their first word, and on a page the body's in reading order before
those of the side text, region by region; `page_numbers` by page, the
head's before the foot's. In the second plan, `notes` is in the order
of their first page and, on a page, of their first lines in reading
order; the `note_marker` changes follow the rule of `word_changes`.

The first plan added three values to shared enums, as architecture §8 allows ("a
spec adds a reason when it needs one"); `model.py`, `fidelity.py`, the
lists of architecture §8 and the glossary changed with them:

- `RemovalReason.stray_mark`: a line with no letter or digit above the
  running head.
- `ChangeReason.hyphen_join_guessed`: a hyphen dropped without
  evidence. The fidelity check verifies it as it verifies `hyphen_join`:
  two words, the first ending with "-", and the one word after is the
  first without its hyphen followed by the second.
- `ChangeReason.hyphen_kept`: two words joined with the hyphen kept. The
  fidelity check verifies that the first ends with "-" and the one word
  after is the two words joined as they are.

The second plan adds `BlockKind.chapter_summary` and `verse`, `NoteKind`
and `Note.kind`, `Block.label`, and `RemovalReason.guide_words`, and
changes the fidelity check's rule for a reference span and counts a
heading's label as words of its block (architecture §8 and §13).

The plan owner-books adds, and so takes `blocks.json` to version 4
(architecture §8; a file of version 3 is the error that says to run
structure again):

- `BlockKind.epigraph`, a quotation set at the head of a chapter, and
  `Block.source: str | None`, its source line as printed, without the
  dash before it, the words joined by single spaces ("Thomas Hobbes,
  1651"); `None` for an epigraph printed without a
  source, which this revision never makes, and for every other kind:
  reading a block that is not an epigraph with a source is an error
  that names the file and the block, as for `label` (section 22). The
  text of an epigraph whose quotation is verse keeps its line feeds, as
  a `verse` block's does (architecture §7);
- `Note.group: str | None`: on the first note of a note group of an
  endnote section, the group's heading as printed, its lines joined by
  single spaces; `None` on every other note (section 12);
- three reasons of `ChangeReason`: `source_dash` (section 22),
  `punctuation_attached` (section 23) and `case_split` (section 24).

The fidelity check counts an epigraph's `source` as words of its block,
as it counts a heading's `label`, and a note's `group` as words of the
note, as it counts its `marker`; it verifies each new change reason as
those sections say.

The revision of sections 29 to 33 adds, and so takes `blocks.json` to
version 5 (a file of version 4 is the error that says to run structure
again):

- `BlockKind.list_item`, one item of a list, its marker as printed in
  `label` ("—", "1.", "(a)"), `level` `None` (section 29);
- `BlockKind.contents_entry`, one entry of a printed table of contents,
  its number as printed in `label` or `None`, its title in the spans,
  its depth in `level`, from 1 (section 30);
- `Block.page_number: str | None`, a contents entry's printed page
  number, words joined by single spaces ("pp. 9 — 26."), `None` when it
  has none and for every other kind;
- `Block.heading_ref: str | None`, the id of the heading block a
  contents entry names, `None` when none matches and for every other
  kind; reading a file where it names a block that is not a heading is
  an error that names the file and the block;
- `ChangeReason.list_marker`: a dash split off the word it was glued to
  ("—The" into "—" and "The"), the dash going to `label`;
- `RemovalReason.leader_dots`: the dots printed between a contents
  entry's title and its page number;
- `RemovalReason.figure_text`: the words the OCR read inside a figure
  printed on a text page (`docs/specs/figures.md` §5). It comes from
  the figures spec, written the same day, and goes into the same
  version 5, so that the owner reruns structure once.
- `RemovalReason.letter_fragment`, added on 19 November 2026 without a
  new version (section 35, architecture §8).

`label` may now be set on a heading, a list item (always) and a
contents entry; `level` on a heading, an index entry and a contents
entry (always). Reading a file that breaks one of these is an error
that names the file and the block, as for `label` today.

## 8. The public interface

The pipeline calls `run`. The other functions are public so that tests
can call them on hand-made pages.

```python
# galley.structure

@dataclass(frozen=True, slots=True, kw_only=True)
class BookSurvey:
    """What structure learns from the whole book before the per-page work."""
    running_heads: frozenset[int]          # pages whose head line is a running head
    head_page_offset: int | None           # page index minus printed number, the commonest
    first_arabic_page: int | None          # the first page with an arabic head number
    body_word_height: float
    body_line_pitch: float
    book_words: frozenset[str]             # keys of the words printed whole
    common_inner_words: frozenset[str]     # keys printed after a line's first word more than 8 times (section 5)
    signature_lines: frozenset[int]        # pages whose lowest line is a signature line
    index_pages: frozenset[int]            # section 17, rule 1
    plate_pages: frozenset[int]            # pages with a figure of kind plate (section 18)
    head_numbers: frozendict[int, int]     # page index -> its arabic head page number (section 4, local offset)

class HyphenJoin(NamedTuple):
    word: str
    reason: ChangeReason                   # hyphen_join, hyphen_join_guessed, hyphen_kept or hyphen_lost

class NoteMarker(NamedTuple):
    marker: str                            # as the OCR read it: "13", "(t)", "291."
    rest: str                              # what follows it in the word: "The" for "13The", else ""
    value: int | None                      # the number it reads, digit-like letters read as digits

class Reference(NamedTuple):
    before: str                            # "land" for "land3."
    reference: str                         # "3"
    after: str                             # "."
    form: ReferenceForm                    # glued, bracketed or sign
    value: int | None

def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def survey_book(lines: LinesFile, *, language: Language = Language.EN,
                workers: int = DEFAULT_WORKERS) -> BookSurvey: ...
def join_hyphen(first: str, second: str, book_words: frozenset[str],
                word_list: frozenset[str]) -> HyphenJoin | None: ...
def join_lost_hyphen(first: str, second: str, book_words: frozenset[str],
                     word_list: frozenset[str],
                     common_inner_words: frozenset[str]) -> HyphenJoin | None: ...
def note_marker(word: str, *, endnote: bool = False) -> NoteMarker | None: ...
def reference_candidate(word: str) -> Reference | None: ...
def attach_spaced_sign(before: str, word: str) -> str | None: ...
def split_at_case(word: str, lower_case_words: frozenset[str],
                  book_words: frozenset[str],
                  common_inner_words: frozenset[str]) -> tuple[str, str] | None: ...
def make_blocks(lines: LinesFile, lower_case_words: frozenset[str], *,
                language: Language = Language.EN,
                contents_pages: frozenset[int] = frozenset(),
                workers: int = DEFAULT_WORKERS) -> BlocksFile: ...
```

`note_marker` gives the marker of a note's first word by the forms of
section 11 (with `endnote`, also the endnote form), or `None`;
`reference_candidate` gives a candidate reference of section 11, or
`None` (for "p.12", an abbreviation, `None`). `attach_spaced_sign`
gives the word that section 23 makes of `before` and the spaced sign
`word` after it in a book not in French ("subjection" and ";" give
"subjection;"), or `None` when the sign stays apart (after a dash or a
quotation mark); `split_at_case` gives the two words section 24 makes of
a word glued at a case change ("theAvre" gives ("the", "Avre")), or
`None`. `ReferenceForm` is a
`StrEnum` of the module. `language` serves the index title of a French
book ("table alphabétique", section 17); `contents_pages` is the
config's (section 14). `join_hyphen` gives `None` when the two words are not joined (section
5), and `join_lost_hyphen` likewise for the two parts of a margin
note's word whose hyphen the OCR lost (section 5, `hyphen_lost`); both
take the word list in lower case, which `make_blocks` is given
as `wordlist.lower_case_word_list` gives it. `make_blocks` is the whole stage on values: it calls `survey_book`,
does the per-page work with `map_pages`, then the work across pages.
`run` reads `pages.json` and `lines.json` with `read_checked_input` as
now, takes the word list with
`wordlist.lower_case_word_list(config.language)`,
deletes `blocks.json` and every later file first, runs
`check_stage(FidelityBoundary.STRUCTURE, lines, blocks)` and writes
nothing on a `FidelityError`. The word list needs Tesseract's tools the
first time a language is used (architecture §12), so `galley2epub`
checks for Tesseract before structure when the cache lacks the
language.

## 9. Parallel work, cases and verification

**Parallel work.** `survey_book` takes each page's head line, words and
line measures with `map_pages`, then compares the head lines and takes
the medians in page order. The per-page work runs with `map_pages` and
needs only the survey and its page. The work across pages runs once, in
page order: in the second plan, the notes (whose book-wide form and
numbering need a first pass over every page), the endnotes, the index
entries, the quotes and the placing of margin notes. The output does not
depend on the number of workers.
Comparing every head line with every other is about 150,000 comparisons
for Domesday's 546 pages; heads whose letters differ in length by more
than 14 are not compared (section 3, "Heads of different lengths"; 8
until 18 November 2026), and its cost is measured against the speed
budget of the `coding` skill in the plan.

**The cases.**

- **A chapter's first page**: no running head; in the first plan its
  centred title lines are paragraphs of their own, in the second one
  heading (section 14); the drop capital (layout §3, step 6) is the
  first word of the first paragraph. A page number at its foot is
  removed.
- **A speck above the head**: on Stubbs' pages 28, 32, 33, 35, 36, 94,
  97, 232, 237 and 267 and Kadesh's 38 a speck read as "6", ". 5", "1 —"
  or "d" is the first row with a letter or digit, so layout makes it the
  head line, and the real head is the first line of the body. The speck
  is no running head; the line below it is, by the rule for a head line
  of fewer than 4 letters (section 3), and is removed as one, so that no
  hyphen at the page break joins into it ("Geof-" with "1", "cer-" with
  "Simon").
- **A title page**: its year, "1907", is neither a page number nor a
  signature mark, and stays.
- **Two page-number sequences** (Kadesh): one removal and one
  `page_numbers` entry each.
- **A paragraph and a hyphen over a page break**: the paragraph keeps one
  id, of its first page, and an origin per page; the join's change is on
  the first page. Haskins has 31 hyphens at the end of a page's body,
  Stubbs 30, Domesday 11, Mariéjol 54.
- **A footnote that runs on to the next page**: two notes in the first
  plan, one per page; one note in the second (section 11).
- **Small type in the body's place**: Haskins' bibliographical notes and
  a quotation in small type at a page's foot are read as a band (layout
  §3, step 4) and become notes, after the paragraph in which the page's
  body ends: their words are kept and keep their order. A quotation
  read as a band stays a note without a marker in the second plan;
  the bibliographical notes become paragraphs (section 16, "Haskins'
  bibliographical notes").
- **The index**: its columns are body regions (or, on its first page
  under a full-size title, band regions); entries become paragraphs by
  rules 1 and 2, which do not fit an index's hanging indents. The second
  plan makes them index entries (section 17).
- **A chapter summary with a hanging indent** (Stubbs page 51): its
  indented continuation lines start blocks, so the summary comes out in
  two, and its second half runs into the chapter's first paragraph,
  whose first line is not indented. The second plan makes it one
  `chapter_summary` block (section 15).
- **Plates**: in the first plan analyze recognises no plate, and their
  text-layer words run into the paragraph around them; in the second,
  section 18.
- **Known misses at the foot** (15 November 2026, with layout's
  regions): Kadesh's page 38 prints "105" at the foot, but its body
  column there runs from 191 to 452 pt, so the number is not centred on
  it and stays; Gierke's page 66 ends with a lone "302" and Domesday's
  page 428 with "[0", both centred, which are removed as page numbers
  although they are not the page's. No rule that is plain fixes them
  without losing others; the reference pages show whether they matter.

### The first plan

**Unit tests**, on `LinesFile` values written in the test:

- `survey_book` on 6 pages (page indices 10 to 15, heads at top 36 pt,
  pitch 15 pt) whose head lines read "25 THE BOOK", "THE BOOK 26"…: every
  page is a running head and the offset is −15 (page index minus printed
  number); on 6 pages whose heads
  carry no number ("THE BOOK", "THE BOKO"), the alike rule alone makes
  them running heads; a page whose first region holds the same title 70
  pt lower is not;
- the head "214 NORMANS IN EUROPEAN HISTORY" gives a `page_number`
  removal "214", a `running_head` removal of the rest, and
  `PageNumber(page, "214", head)`; a line ";" above it a `stray_mark`;
- on a column from x 25 to 299 pt: lowest lines "(49)" and "U9)"
  centred are removed as page numbers; "M." at x 37 with "4" at x 266,
  and "4—2" at x 252, as signature marks; "4 Ibid. 29." at x 28 and
  "(5) Ibid., p. 3." are kept; "1907" centred is kept; a signature line
  on two pages gives a page number and a signature mark each;
- `join_hyphen`: ("neces-", "sary") with "necessary" in the word list
  gives ("necessary", `hyphen_join`); ("Anglo-", "Saxon") with
  "anglo-saxon" among the book's words gives ("Anglo-Saxon",
  `hyphen_kept`); ("Bal-", "hazar") with neither gives ("Balhazar",
  `hyphen_join_guessed`); ("1066-", "1087") gives ("1066-1087",
  `hyphen_kept`), and ("235-", "37-") gives ("235-37-", `hyphen_kept`)
  whatever the book's words and the word list hold; ("—", "and"),
  ("rep-", "(1)"), ("136-39-", "Bryce,"), ("37-", "Abacus") and ("37-",
  "abacus") give `None`; ("12th-", "century") is joined;
- paragraphs: an indented line after a short one starts a paragraph; an
  indented line after a full one does not; a centred line is a
  paragraph of its own; an indented line after a hyphen does not start
  one, but one after a number before a word ("136-39-" "Bryce,") does,
  and so does the first line of a page with a figure after such a
  line; a page whose first line is not indented continues the last
  paragraph of the page before, across a blank page;
- side text: a page with a margin region and a band region gives a
  margin note and a note after the paragraph that ends the page, that
  paragraph running on to the next page; a page of two index columns of
  equal width gives no margin note;
- the fidelity check passes on these outputs; with a `hyphen_kept`
  change whose word drops the hyphen, or a `hyphen_join_guessed` change
  that changes a letter, it fails;
- `make_blocks` with 1 worker and with 3 gives the same value.

**Excerpt tests** on the reference pages of layout §8, and on these
pairs across a page break: Haskins excerpt pages 1 and 2 (132, 133), a
paragraph that runs over; the Stubbs excerpt's hyphen across a page
break. For each reference page the expected output is: the kind and text
of each block and note that has lines on the page, and the pages of its
origin; the reason and text of each removal; the word changes; the page
numbers, all compared exactly. The owner checks each by eye against the
page image before it becomes a test. The fidelity check runs on every
excerpt, and the `whole_book` tests on the whole books, Kadesh and
Gierke included.

**Targets measured by `galley-eval run`.** These are targets, not
tests: the plan's work report gives each book's scores before and after,
against the baseline of `docs/reports/evaluation.md` (galley at
cc481d1). The numbers are set from the measurements above, with room for
layout's own errors. An **extra token** is a word of galley's output that
the reference does not have; a **hyphen split left** is a reference word
that galley still has in two parts at a line end, as `summary.md`
counts them under structure. Scores are for the body, at blocks, unless named.

| score | Haskins | Stubbs | Domesday | Mariéjol |
|---|---|---|---|---|
| extra tokens (baseline) | 1,893 | 5,593 | 11,178 | 28,921 |
| extra tokens, target | at most 1,000 | at most 4,300 | at most 9,900 | at most 28,400 |
| hyphen splits left at markdown (the structure group of `summary.md`) (baseline) | 1,005 | 1,235 | 781 | 1,450 |
| hyphen splits left, target | at most 150 | at most 300 | at most 150 | at most 400 |
| paragraph boundaries, precision / recall (baseline) | 0.11 / 0.11 | 0.13 / 0.07 | 0.12 / 0.08 | 0.09 / 0.04 |
| paragraph boundaries, target | at least 0.75 / 0.75 | 0.55 / 0.60 | 0.70 / 0.70 | 0.55 / 0.60 |
| notes found as notes (baseline 0) | 55 of 72 | (no notes) | 1,300 of 1,729 | 900 of 1,432 |
| margin notes found as margin notes (baseline 0) | (none) | 0 of 467 (cut-in notes, layout §9) | 400 of 593 | (none) |

Stubbs' paragraph and hyphen targets allow for the cut-in notes
that stay in its body lines meanwhile. The research's guessed joins, 35,
33, 78 and 192 for the four books, counted only the line-end hyphens
whose right form the reference shows. On the whole books, with layout's
regions (15 November 2026), the stage guesses 142 joins in Haskins, 256
in Stubbs, 201 in Domesday and 738 in Mariéjol (28 in Kadesh, 185 in
Gierke). A sample of 40 guessed joins of Haskins and 40 of Mariéjol
showed 57 of the 80 to be words the OCR damaged (Haskins' text layer
runs words together, "dations" with "which"; Mariéjol's misreads
letters) and 14 right joins of words missing from Tesseract's lists
(its French list, 74,068 words, lacks most inflections: "reproduisit",
"courageusement"; the English one lacks "deposing"); 7 were compounds
whose hyphen should have stayed and 2 not one word.

### The second plan

**Unit tests**, on `LinesFile` values written in the test:

- `note_marker`: "8", "291." (with `endnote`), "(t)" (value 1), "(a)"
  (value 2), "U)", "(3J", "*" and "13The" (marker "13", rest "The") have a
  marker; "I39-" has one only with `endnote`, value 139; "The", "1907" and
  "(1907)" have none;
- `reference_candidate`: "land3." gives ("land", "3", "."), "Kadesh,12"
  ("Kadesh,", "12", ""), "(i)." a bracketed one of value 1, "rulers.^" a
  sign; "p.12", "pp.3", "1066" and a lone "'" give `None`;
- notes: a band of three notes indented 12 pt with markers "1", "2", "3"
  and a body with "land1.", "day2", "(3)" in a book whose form is the
  glued number links the first two and leaves note 3 unreferenced and
  "(3)" in the text; a reference "3" against a note whose marker reads
  "8" on a page numbered per page is linked and keeps "3"; two notes on
  one line, the second marker 14 pt after "12 b.", give two notes; a
  page whose first band line has no marker and is not indented continues
  the last note of the page before, across a blank page;
- endnotes: 12 body paragraphs starting "291." to "302.", and one
  paragraph without a marker between two of them, give 12 endnotes, that
  paragraph the second block of the note before; a paragraph before
  "291." at the top of the first page gives an endnote with no marker,
  and the paragraph ending the page before does not run on into it; 6
  such paragraphs give no endnote; a body word "Law1" before them is
  linked to endnote 1 when there is one;
- margin notes: a margin region whose top lies 0.3 pitch below a
  paragraph's first line goes before that paragraph; one beside the
  middle of a paragraph, beside a line indented 20 pt after a full line,
  starts a paragraph there; one at the top of a page whose first
  paragraph runs on goes before that paragraph, on the page before;
  one beside an endnote's line goes inside the note, before its text;
- headings: "CHAPTER III." centred above a centred title 1.5 pitches
  below gives one level-1 heading whose `label` is "CHAPTER III." and
  whose text is the title; a heading block of one line has `label`
  `None`; a centred line in lower case with gaps
  of 2.5 and 1.5 pitches gives a level-2 heading, and with a gap above of
  1.5 a paragraph; a centred "§ 1. Plan, pp. 9 — 26." is no heading; on a
  page of `contents_pages` no line is a heading;
- a chapter summary of 3 lines with a hanging indent of 9 pt and 3
  dashes, under a heading, is one `chapter_summary` block, and the
  unindented line after it starts a paragraph; the same lines with one
  dash are paragraphs;
- quotes and verse: a block of 3 wide lines at 0.85 of the body height
  and 1.10 of the density is a quote, at 1.0 a paragraph; 3 lines of 4
  words inset 40 pt on both sides are one `verse` block whose text holds
  two line feeds; a band of small type is still a note; body lines at
  0.85 of the body height at a page's foot, below lines at 1.0, whose
  markers read "(1)", "(2)", "(3)" in a book whose form is bracketed,
  are notes, and with markers "(1)", "(3)", "(2)" they stay paragraphs,
  none a quote, and the last does not run on into the next page; the
  same lines on a page whose band starts with "(1)" stay paragraphs; the same lines on a page whose lines above are
  also at 0.85 stay paragraphs;
- Haskins' bibliographical notes: after a level-2 heading
  "BIBLIOGRAPHICAL NOTE", a body block of small type that rule 1 would
  make a quote, and on the next page a band block without a marker, are
  paragraphs, the band block after that page's body blocks; after the
  next heading, the same blocks are a quote and a note;
- index: two columns of 20 lines under "INDEX", lines at the edge and
  indented 9 pt, give one `index_entry` per line at the edge, `level` 1,
  and one of `level` 2 per part after a word ending in ";"; a line
  "BUR CON" is removed as `guide_words`, and so are "BUR" and "CON" as
  the first lines of the two columns; a row read across the gutter is
  cut in two; a skew of 5 pt over the column does not start entries;
- plates: a page with a figure and the lines "DECENNIAL PUBLICATIONS, V"
  (alike to another plate's top line), "THE MODERN MOUND OF KADESH" and
  "^U;L" gives a `running_head` removal, a figure block with the second
  as its text and a `plate_text` removal; a paragraph that runs from the
  page before to the page after keeps one block, the figure after it;
- the fidelity check passes on all of these; it fails on a reference
  span "land" (a word, not a marker's shape) and on one that names no
  note.

**Reference pages.** The pages of the first plan's reference pages
(layout §8) and the new excerpts below, each checked by the owner by eye
against the page image before it becomes a test. For each, the expected
output is that of the first plan's excerpt tests, with the kinds, levels,
markers, `referenced` and note kinds, and the reference spans, compared
exactly.

| excerpt | page (excerpt page, book page index) | what it checks |
|---|---|---|
| `haskins_eval` | 0 (131) | heading "V / NORMANDY AND FRANCE", level 1, one block, `label` "V"; the first paragraph starts "IN July, 1189," with the drop capital |
| `haskins_eval` | 1 (132) | the reference "^" alone linked to the note whose marker is "*" |
| `haskins_eval` | 2 (133) | a sign glued to its word, "journalist,^" |
| `haskins_eval` | 9 (266) | heading "INDEX", level 1; the entries of the left column, then the right, one `index_entry` each, not a quote |
| `stubbs_51_56-64` | 0 (51) | heading "CHAPTER III. / THE EARLY YEARS OF HENRY II.", level 1, `label` "CHAPTER III."; the 3-line summary, one `chapter_summary`; "Very few epochs…" starts a paragraph; of the cut-in note "Importance attached… accession.", layout takes out only its last line, "accession.", which goes before that paragraph as a margin note; its words "Importance", "attachedby", "contempora-" and "toHenry's" stay in the body lines beside them (layout §3, step 2b) |
| `stubbs_51_56-64` | 3 (58) | "His great position in Christendom" (as the OCR reads it) beside the middle of a paragraph, placed before it |
| `stubbs_51_56-64` | 2 (57), 7 (62), 9 (64) | cut-in notes on the left and right (layout §8), each before its paragraph |
| `domesday_74-83` | 0 (74) | note 6 with the marker "«", linked from "would6.'"; seven glued references, "pleased1/" to "mercy7.'", linked |
| `domesday_74-83` | 1 (75) | references "day1.'", "land2.", "land3." linked to notes whose markers read "1", "2", "9"; margin notes beside paragraphs' first lines; "Can the villein be pursued?" beside the page's last line, a paragraph's first line |
| `domesday_74-83` | 2 (76) | two notes on one line ("1 Dialogus", "2 Dialogus"); note 3 with marker "z" |
| `domesday_74-83` | 9 (83) | three lines of two notes each; markers "8", "*", "e"; references "12s.2", "30d8" |
| `mariejol_210-219` | 0 (210) | five notes left in the body, missed by section 11's order test (markers read 1, 2, 3, none, 11, 5): each a paragraph of its own, not a quote, and note 5 ("(S) La thèse…") not run on into pages 211 and 212 |
| `mariejol_210-219` | 7 (217) | a note left in the body, taken as a note |
| `mariejol_210-219` | 2 (212) | two broken lines inset on both sides after "se sou-": no `verse` block, since the hyphen joins them to the text (rule 4) |
| `mariejol_210-219` | 4 (214) | a note run on from page 213, one note; markers "(t)", "(a)", "(3J"; "(» i)" not found, so note 1 unreferenced |
| `mariejol_210-219` | 6 (216) | marker "U)"; note 2 with no reference in the text |
| `kadesh_8-17` | 0 (8) | the article title, one level-1 heading of three lines with the author's name |
| `kadesh_8-17` | 2 (10) | glued marker "13The"; note 12 run on into the right column; references "Kadesh,12", ";13" and "above).'*" (note 14, marker "u"); notes 10 and 11 unreferenced |
| `kadesh_8-17` | 8 (16) | not a plate but the scan of a cover, with no plate and no text (owner, 16 November 2026): excluded in the test's config, so no block |
| `gierke_86-93_270-271` | 0 (86) | "POLITICAL THEORIES OF THE / MIDDLE AGE.", level 1; "I. The Evolution of Political Theory.", level 2 |
| `gierke_86-93_270-271` | 2 (88) | "Law1" stays unsplit (endnote 1 is outside the excerpt); margin notes before the paragraphs whose first lines they are beside; "Medieval Thought." beside the page's last line |
| `gierke_86-93_270-271` | 6 (92) | "II. Macrocosm and Microcosm.", level 2, and the known false heading "Macrocosm and Microcosm." at the top |
| `gierke_86-93_270-271` | 8 (270), 9 (271) | endnotes 291 to 302, kind `endnote`, unreferenced, each margin note inside its note before its text; the end of note 290 at the top of page 270 an endnote with no marker, not joined to the last paragraph of page 93 |
| `haskins_quotes_index` (new) | 0 (39) | a level-2 heading "BIBLIOGRAPHICAL NOTE" mid-page, paragraphs after it, not quotes (section 16) |
| `haskins_quotes_index` | 1 (41) | the heading of chapter II, which ends the bibliographical note of page 39 |
| `haskins_quotes_index` | 2 (53) | quotes in smaller type across the column (checked on the whole book; see below) |
| `haskins_quotes_index` | 3 to 5 (71 to 73) | a quote that runs over two page breaks (checked on the whole book) |
| `haskins_quotes_index` | 6 (129) | the heading "BIBLIOGRAPHICAL NOTE" above a band of small type, whose blocks are paragraphs, not notes |
| `haskins_quotes_index` | 7 (209), 8 (234) | centred Latin verse and English verse, `verse` blocks with their line breaks |
| `haskins_quotes_index` | 9 (267), 10 (269) | index rows read across both columns, cut at the gutter; "Calabria", an entry from the foot of one column to the top of the next |
| `stubbs_summaries_index` (new) | 0 (16) | a printed contents page, named in the test's `contents_pages`: no heading |
| `stubbs_summaries_index` | 1 (28) | a summary whose OCR is out of order: missed, as the first plan made it |
| `stubbs_summaries_index` | 2 (79) | a summary whose last line is centred |
| `stubbs_summaries_index` | 3 (157) | "John." in lower case under "CHAPTER VII.", one heading |
| `stubbs_summaries_index` | 4 to 9 (312, 313, 316, 318, 319, 321) | the index: guide words, columns read as a band, rows across the columns, letter initials, spaced letters |
| `domesday_headings_quotes` (new) | 0 (14) | a printed contents page, named in `contents_pages` |
| `domesday_headings_quotes` | 1 (22) | an essay's label 3.4 pitches above its title: one level-1 heading |
| `domesday_headings_quotes` | 2 (30) | a section heading in lower case mid-page, level 2 |
| `domesday_headings_quotes` | 3 (39), 4 (40) | maps as plates: strays removed, caption and the binder's note kept |
| `domesday_headings_quotes` | 5 (42) | a table's title in capitals: a known false heading |
| `domesday_headings_quotes` | 6 (47) | a table read as verse: known |
| `domesday_headings_quotes` | 7 (93) | inset quotes; the footnotes in the band, as notes |
| `domesday_headings_quotes` | 9 (274) | quotes in smaller type across the column; the footnotes in the band, as notes |
| `domesday_headings_quotes` | 10 (406) | a table read as verse: known |
| `mariejol_headings_verse` (new) | 0 (18) | a chapter opening: "CHAPITRE…" and its title, one heading |
| `mariejol_headings_verse` | 1 (51), 2 (52) | verse in the middle of each page, one `verse` block on each, the prose after it a paragraph |
| `mariejol_headings_verse` | 3 (142) | a title that fills the column, taken as a continuation |
| `mariejol_headings_verse` | 4 (229) | two verse quotes on one page |
| `mariejol_headings_verse` | 5 (430) | a heading of three lines |
| `kadesh_59-68` (new) | 5 (64), 9 (68) | plates with captions and the series head, removed as a running head on 64 and kept as a caption line on 68 |
| `kadesh_59-68` | 6 (65) | the back of a plate, which analyze takes for a plate |

The five new excerpts are added to `scripts/fetch_samples.py` with what
they cover, each from a public-domain book of the evaluation set or of
the committed excerpts, every page with a text layer:

- `haskins_quotes_index`: Haskins (`normansineuropea00hask`), page
  indices 39, 41, 53, 71, 72, 73, 129, 209, 234, 267 and 269. Page 41,
  the opening of chapter II, was added on 16 November 2026: without its
  heading the bibliographical note of page 39 ran on to page 129's, and
  the quotes of pages 53 and 71 to 73 came out as its paragraphs. The
  excerpt still cannot check those quotes: its pages are mostly small
  type (the quotes, the bibliographical notes, the index), so it
  measures a body word height of 7.60 pt and a pitch of 11.86 pt against
  the book's 8.32 and 15.19, and quotes set at 0.93 to 0.95 of the book's
  height are not smaller than the excerpt's. Six more pages of text
  (42, 43, 54, 55, 74, 130) bring it only to 7.80 and 12.66 pt; without
  the index pages and with page 42 it measures 8.05 and 13.68 pt
  (measured on 16 November 2026).
  The quotes of pages 53 and 71 to 73 are checked on the whole book.
- `stubbs_summaries_index`: Stubbs (`earlyplantagenet01stub`), page
  indices 16, 28, 79, 157, 312, 313, 316, 318, 319 and 321.
- `domesday_headings_quotes`: Domesday (`domesdaybook00maituoft`), page
  indices 14, 22, 30, 39, 40, 42, 47, 93, 272, 274 and 406. Its own
  survey must measure what the whole book's does, or pages 93 and 274
  lose their footnote band: cut on 16 November 2026 with page 546 in
  place of 47 and 272, it measured a body word height of 9.0 pt and a
  pitch of 11.15 pt against the book's 10.0 and 12.13, because the
  index page, the contents page and the two pages of quotes are mostly
  in small type, and its notes became paragraphs. Pages 47 and 272 are
  body pages whose running heads repeat those of 93 and 274, so that
  every running head of the book's pages is removed on the excerpt too;
  with them the excerpt measures 10.0 and 12.09 pt and the book's marker
  form. The first index page (546), whose page numbers overhang the
  right column, is left to the whole book: its 50 rows of 8 pt type
  pull the measures down, so that these pages with 546 as well measure
  a pitch of 11.50 pt, and without 406 a body word height of 9.0.
- `mariejol_headings_verse`: Mariéjol (`catherinedemedic00mariuoft`),
  page indices 18, 51, 52, 142, 229 and 430.
- `kadesh_59-68`: Kadesh (the book of `kadesh_8-17`), page indices 59 to
  68.

No excerpt has a margin note set between two paragraphs (Gierke page
109, "Bodies moral and politic.") or a margin note beside a footnote;
the first is checked on the whole book.

**Targets measured by `galley-eval run`**, once the tool reads the new
kinds (section 28), against the scores of the first plan's work report:

| score | Haskins | Stubbs | Domesday | Mariéjol |
|---|---|---|---|---|
| notes whose reference is right (the tool's `as_note` with a right reference) | at least 45 of 72 | (no notes) | at least 1,250 of 1,731 | at least 350 of 1,432 |
| margin notes found as margin notes (the tool's `as_margin_note`) | (none) | at least 200 of 467 (cut-in notes, layout §3, step 2b) | at least 400 of 593, as the first plan's target | (none) |
| reference headings in `heading` blocks, body range | at least 17 of 18 | at least 24 of 26 | at least 20 of 23 | at least 24 of 26 |
| index entries, the index part's paragraph boundaries, precision / recall | at least 0.90 / 0.90 | 0.85 / 0.85 | 0.90 / 0.90 | (no index) |

The tool's `as_note` counts a reference-text note as found when at
least half of its words are in one galley note, and `as_margin_note`
likewise for a margin note (`docs/specs/evaluation.md` §6). Each target
is below the second research's count for that book. The tool does not score where Domesday's margin notes are placed
(its reference text moved them, `margin_notes_moved` in
`evaluation/books.toml`), so the 317 of 328 of section 13 is not a
target; the reference pages check the placement.

## 10. Decided: margin notes and unreferenced notes, with a change to markdown

This was the first plan's one open point, decided by the owner on 15
November 2026: option (b) below. So the first plan also
changes the markdown stage, as (b) describes, and that description is
the spec of that change. What was weighed:

**What the margin and footnote text becomes in the first plan.**
The first plan keeps it out of the body's paragraphs; the question is
what kind of block holds it, because the markdown stage, as the walking
skeleton built it, refuses every block that is not a paragraph and every
note, and because the evaluation tool reads a block's kind.

- (a) **Paragraph blocks**, after the paragraph in which the page's body
  ends. Nothing changes outside structure. The EPUB shows the margin and
  footnote text as ordinary paragraphs there. The evaluation tool counts
  every such block as body: each adds paragraph boundaries that it scores
  as wrong (at least one on every page with side text, which is about
  500 of Domesday's pages, against its 754 real boundaries), and it finds no note and
  no margin note, so neither can be measured until the second plan.
- (b) **Their own kinds now**: a margin region is a `margin_note` block
  and a band paragraph is a note with `referenced` false and an empty
  marker, as section 6 says. The markdown stage writes a `margin_note`
  block as a fenced div with its id and the class `margin-note`, where
  it is in `blocks`, and a note with `referenced` false as a fenced div
  with its id and the class `note`, holding its blocks' divs, after the
  last block, in the order of `blocks`, whose first origin is on the
  note's first page or an earlier one, or first of all when there is
  none (section 6, "Order"). That is what
  architecture §9 and §17 already decide for these kinds, without the
  styling, which the epub stage's style sheet gives later, and without
  §17's placement: a margin note stands after the paragraph in which its
  page ends, not before the paragraph it was printed beside, which can
  be a page earlier, until the second plan places it. It is a change of
  some tens of lines to markdown, in the first plan. The EPUB
  shows the same text in the same place as (a); the evaluation tool
  scores notes and margin notes from the first plan on.

Chosen: (b). Since 19 November 2026 a note with `referenced` false
that is a footnote is written at the end of its chapter instead
(section 36); an endnote keeps the place (b) gives.

## 11. Notes and their references

A footnote is printed at the foot of its page with a **marker** before
it ("8", "(3)", "*"), and the same marker, often as a superscript, at
the place in the text that refers to it, the **reference**. structure
cuts the band into notes, takes each note's marker out of its text,
finds the references in the body and links each to its note. A note
whose reference is not found stays a note, unreferenced, with its
origin where it was printed (markdown writes such a footnote at the end
of its chapter, section 36); a reference whose note is not found stays
in its word.

**What the books show.** The marker and the reference are read
differently by the OCR:

| book | marker at the note | reference in the text | numbering |
|---|---|---|---|
| Haskins | "*", "^", "1": the OCR reads a superscript 1 as a sign | "^" alone or glued ("rulers.^"), sometimes "*", "'" | per page |
| Stubbs | (no notes) | | |
| Domesday | "1" to "9", misread "8" for 3 or 5, "e" for 6, "z" or "s" for 3, "*" for 4, "«" | digits glued after the word and before its punctuation: "day1.'", "land3.", "12s.2" | per page |
| Mariéjol | "(1)", misread "(t)", "(i)", "(I)", "U)", "(a)" for 2, "(3J", "(4" | a word of its own at full size: "(1)", "(i).", "{2)."; once split as "(» i)" | per page |
| Kadesh | "11", glued "13The", "10This", or a sign: '"', "u" for 14 | glued "Kadesh,12", separate ";13", or a quote mark: "north.\"" | through the article |
| Gierke | endnotes (section 12): "1." to "345.", misread "I39-", "!6o.", "n2." | glued "Law1", "Mankind3.", misread "insufficiency80." for 30 | through the book |

The size of a superscript cannot be used: the text layer gives every
character of a word the word's top and height, so a glued reference has
no box of its own, and a reference that is a word of its own has its
line's height too: the ratio of its height to its line's is 1.00 for
Domesday's 41 such words, Mariéjol's 805 and Kadesh's 9. Only Haskins' 42 "^" and "*" words are smaller,
0.50 of their line's height.

### Where a note starts

Each band region is cut into notes, in reading order. A note line starts
a note when any of these holds:

1. section 6's indent rule starts a block there, as in the first plan:
   the line is indented after a short line (section 6, rule 1). A line
   that section 6 starts only because it, or the line before, is
   centred starts no note by this rule (owner, 16 November 2026);
2. its first word has a **note marker's form** (below) and the line is
   indented 5 to 40 pt from the band's left edge, which is the smallest
   left side among the page's note lines within 60 pt of this line, so
   that each column of notes has its own. Measured: the first line of a
   note is indented 9 to 15 pt in 1,286 of the 1,511 notes of Domesday
   that the indent rule starts, and 9 to 18 pt in 769 of Mariéjol's 943.
   This rule takes the 132 lines of Mariéjol and 21 of Domesday that
   start with a marker but follow a full line, and so sat inside the
   note before;
3. its first word has a note marker's form, and what the marker reads
   as a number (below, "Its value", the reading of digit-like letters)
   is what the marker of the note before it reads plus 1, or, for a
   marker of one character, what the last marker of the page that reads
   a number reads plus the notes after it plus 1 (Domesday's page 141,
   "3", "*", "5": the "5" starts a note though the note before it has
   the sign); this uses what
   the marker reads, even in a book numbered per page, where a note's
   value is otherwise its place, since by place every marker-shaped
   line, a table's row too, would pass. On a page whose notes are each
   one line long no line is indented against another (Mariéjol's pages
   221, 310 and 409);
4. it is the first line of a band region after the page's first, and is
   indented 5 to 40 pt from the band's left edge of rule 2: the first
   note of the next column (owner, 16 November 2026). On Kadesh's page 8
   (excerpt page 0) the right column starts "'There is, however…",
   indented 12 pt against its column, a note whose marker the OCR glued
   to its first word;
5. its first word is a note marker of one character, a digit or a
   letter that reads as one ("s"), the word after it starts with a
   capital, and the line before it in its region ends more than 3 pt
   short of the region's right edge, as section 6, rule 1 asks of the
   line before an indent, and does not end with a hyphen that joins it
   to this line. A one-character sign starts a note by this rule only
   when the next line of the region starts with a marker that reads
   what rule 3's last marker plus the notes after it reads plus 2: the
   sign stands for the number between (Domesday's page 141, "*" for 4
   between "3" and "5"). Domesday sets a short note on a line of its
   own at the band's left edge, under a short line, so that neither
   indent rule sees it (page 35: "2 A good many cases…" under "1 D. B.
   i. 41…"). Added on 23 November 2026 (plan more-note-links, task 4.1):
   with rules 3 and 5, Domesday's footnotes go from 1,847 to 1,868, and
   of the 66 notes the investigation of that day found joined to the
   note before, 30 are cut off. Without the capital, the one character
   and the lookahead for a sign, the rule cut 109 notes, most of them
   rows of tables (pages 200, 426, 428, 460, 499: "7 3E] Northampton",
   "120 acres"), lines that start with a number in a note's text ("9
   furlongs", page 396) and quotations ("' Consuetudo…", page 181); a
   sign at the end of a page's notes, "* Maitland" on page 35, stands
   for 6 there and would take note 5's reference. Haskins gains one
   note, its page 116's "2 Origin of the English Constitution", which
   the page image shows as a note of its own.

A line is indented only against other note lines: on a page with one
note line, the band's left edge is that line's own left side, so the
line is never indented (owner, 16 November 2026).

**Two notes on one line.** A word inside a note line starts a note when
it has a note marker's form or is one lower-case letter (Domesday's "e"
for 6), has at most 2 characters, follows a gap of at least 10 pt from
the word before, comes after a word that ends with ".", "'", "’", ":",
";" or ")", and comes before a word that starts with a capital or a
digit. The line is cut at the word: the note before ends with the word
before it. The gap before such markers was 16 to 32 pt in Haskins (4
cases) and 13.5 pt at the median in Domesday; the other gaps of note
lines were 3.8 to 5.1 pt at the median and 14.0 pt at the 99th
percentile (Domesday). The gap alone would not do; with the punctuation
and the capital it does. Measured on 16 November 2026 on the whole
books' band lines of the first plan, against the reference text (a cut
is right when the words on either side belong to two of its notes):

| gap | Domesday: right / wrong / not in the reference text | Haskins | Kadesh, Mariéjol |
|---|---|---|---|
| none | 182 / 148 / 222 | 2 / 0 / 4 | |
| 10 pt | 176 / 3 / 12 | 2 / 0 / 2 | Kadesh 2, unchecked; Mariéjol none |
| 12 pt | 172 / 1 / 11 | 2 / 0 / 2 | |
| 15 pt | 155 / 0 / 11 | 2 / 0 / 2 | |

So 10 pt: 3 wrong cuts in Domesday for 21 more right than at 15 pt. The
punctuation test keeps a row of a table in a note ("40 2 42", Domesday
page 43) whole.

A band block whose first line starts no note is part of the note before
it on the same page (the rest of a note in the second column, whose
first line is not indented, or a table that the centring rule of
section 6 cut into rows), or, when it is the page's first, of a note of
the page before (below).

### The marker of a note

The first word of a note has a **note marker's form** when it is:

- 1 to 3 digits, with or without a "." after them ("8", "291.");
- 1 to 3 digits glued to a word that starts with a capital or a quotation
  mark ("13The", Kadesh): the marker is the digits;
- a bracketed marker: 1 or 2 letters or digits followed by ")", "]", "}"
  or "J", with "(", "[" or "{" before them or not, and an optional "."
  after ("(3)", "(t)", "U)", "(3J"); or a word of at most 4 characters,
  with at most 2 letters or digits, that starts with an opening bracket
  or ends with a closing one (Mariéjol's damaged "(4", "i»)", "(*)");
- 1 or 2 signs among `* ^ • † ‡ § » > ' "`;
- in an endnote section (section 12), 1 to 3 digits followed by "." or
  "-" (the OCR reads the full stop as a hyphen in "35-" and "I39-"), where
  "I", "l", "!" and "o" count as digits.

A note started by its indent (rule 1 or 2) whose first word has none of
these forms still takes it as its marker when it is one character and
the next word starts with a capital ("«" on Domesday page 74, "z" on
page 76), unless it is "A" or "I", which are words, and the next word
is a known word (`wordlist.is_known_word`, architecture §12): "A
Treatise", "I have" keep their first word. A lower-case "a" before a
capital is always the marker: a note's text starts a sentence, where
the article is "A". The six whole books have two such notes, each
marked with a superscript digit that the OCR read as "a": "2 In Ramses
III.'s day" on Kadesh page 8 and "3 See e.g. D. B." on Domesday page
439 (checked on the page images on 17 November 2026). Kadesh's "a" was
taken for a word once the text layer read "I n" as "In", a known word.
A note takes as its marker the signs too, when the word is 1 or 2 of the
signs above glued to a word that starts with a capital ("'There" on Kadesh page 8: the
marker is "'" and the text starts with "There"). Otherwise the note has
no marker: `marker` is empty and every word stays in its text.

The marker is taken out of the note's first block into `marker`, as the
OCR read it. A glued marker is split off by a `note_marker` word change
on the note's page: ("13The",) becomes ("13", "The"), the marker is "13"
and the text starts with "The".

**Its value.** In a book whose notes are numbered per page, the notes
that start on a page are numbered 1, 2, 3 and on, in order, and their
markers decide only where the count skips a number or leaves a note
out. The markers are too damaged to be taken as they read (Domesday's
page 83 reads "1 2 8 * 8 e 7 8" for notes 1 to 8), but a marker that
reads a number the count misses tells of a note joined to the one
before it (page 58 reads "1 3 4 s": note 2 is joined to note 1, so the
notes are 1, 3, 4 and 5), and one that reads a number the count has
passed tells of a note that is not one (page 42 cuts a table's rows
into five notes before its notes 1 and 2). Of all the numberings of a
page's notes, each note's value one more than the last value before it
or more, or the note left out, the one with the highest score is taken:

| for | score |
|---|---|
| each note whose marker reads its value | +1 |
| each note whose marker reads a number one confused digit away from its value (the pairs of "Matching", below: 8 for 3) | +0.5 |
| each number skipped, at most 2 on a page | −0.5 |
| each note left out | −0.25 |

Of two numberings with the same score, the one with fewer numbers
skipped and notes left out wins, and with no marker that reads a
number, the k-th note has the value k. A skip costs half a match, so
that two markers that read true pay for one skip and a confused digit
does not: on page 74, "1 3 3 4 6 « 7" is numbered 1 to 7, not 1, 3, 4,
… A note left out has no value and takes no reference (below,
"Matching"), not even a sign. Measured on 23 November 2026 (plan
more-note-links, task 4.1) with galley-eval on the whole Domesday,
with rule 5 above: the notes whose reference is right go from 1,410 to
1,488 (78 gained, 1 lost, page 121's note 3, which galley joins to
note 2, so that its reference now links to no note); the galley
references that lie farther than 3 words from a reference to their
note go from 114 to 52, and one is new, page 106's "justice*", a
misread quotation mark that takes the signature mark "M." the band
holds as a last note, whose value took the "5" of note 5 before.
Numbering by place but with rule 5 gave 1,426; skips and left-out
notes cost 0.4 and 0.2 gave 1,487 and lost 6 notes right before.
Haskins stays at 66. On Gierke's page 31, "Law³" moves to its note
3 from note 2, as the page image shows it should. A page's first note that has no marker
and is not indented, and that does not continue a note of the page
before (below, "A note that runs over a page break"), is the end of a
note that started elsewhere, and is not counted and has no value: on
Mariéjol's page 211 the end of page 210's note 5, which stayed in the
body, would otherwise make "(t)" note 2 (decided in task 2.3, 16
November 2026). A book is numbered per page when, on at least half of
its pages with a note whose marker reads as a number, the first such
marker reads 1 (Haskins, Domesday and Mariéjol; not Kadesh).
Otherwise a note's value is what its marker reads, once "i", "l", "I",
"|", "!" and "J" are read as 1, "o" and "O" as 0, "s" and "S" as 5 and
"z" and "Z" as 2, and, inside brackets, "a" as 2 and "t" as 1. A sign
has no value.

### Notes left in the body

Layout leaves some notes in the body when their lines are not small
enough to make a band: a fifth of Mariéjol's note words, whose OCR lines
are 9 pt high against the body's 10 (layout §6). On each page, before
any paragraph is joined over the page break (section 2, step 2.5), in
a book numbered per page (below) that has a book's marker form (section
1), the page's body lines from a **first marker line** to the last body
line of the page are notes of the page when all of these hold:

1. the first marker line is the first line of the page's body stream
   whose first word has the book's marker form and reads 1;
2. the lines from it to the page's last body line have a height ratio
   (section 1), over all their words, of at most 0.95;
3. the lines above it have a height ratio at least 0.05 higher: the
   notes are set smaller than the text above them;
4. the markers of the lines from it on that have the book's form, read
   as numbers, never decrease (an unreadable one is skipped);
5. the page's band does not already start with a note whose marker
   reads 1: then the band holds the page's notes from the first, and a
   line reading 1 in the body is something else (Domesday's page 200,
   where a table's rows "1 2 Winchcombe" read 1, 1, 10, 15 and would
   have made 4 notes of 12 rows, and the band's notes 1 to 3 values 5 to
   7, so that "Chichester3" would link to a false note).

They are cut into notes as a band is (below, "Where a note starts"),
and are band blocks from then on: they never run on into the next
page's body. The rule is not applied on the pages of the endnote
section (section 12), whose notes are all small type, nor on index
pages (section 17).

Asking for the book's form keeps Domesday's numbered quotes "(i) In
Espalle…" out (bracketed, against its digits). Condition 3 keeps out a
page whose body is all in 9-pt OCR lines (Domesday page 501, where a
table line "1 H. = 120 A. and 1 v." would otherwise take the page's
text) and a publisher's list (Stubbs page 331). Condition 4 keeps out
tables of numbers that do not rise.

Measured on 16 November 2026 on the six whole books' body lines of the
first plan, each word labelled by the reference text:

| book | pages | lines starting with a marker taken (each starts a note) | words the reference text has in notes | words it has in the body (paragraphs, tables) | words the alignment did not place (mostly OCR garble) |
|---|---|---|---|---|---|
| Domesday | 15 | 39 | 900 | 1 (of a paragraph) | 88 |
| Mariéjol | 43 | 137 | 1,474 | 32 | 1,041 |
| Haskins, Stubbs, Kadesh | 0 | | | | |
| Gierke | 0 (no marker form) | | | | |

The 32 words of Mariéjol labelled as body are in garbled note lines
that the alignment paired with body words ("(a) BmafiOM, Vil, y, 365."
on page 139); none of the 12 lines looked at is a line of text. Asking
the markers to read 1, 2, 3 in turn instead of condition 4 takes 11 of
Domesday's pages and 18 of Mariéjol's, with no body word; with no test
of order, 171 words of Domesday's paragraphs and 149 of its tables are
taken. Condition 5 skips 394 of Domesday's pages and 165 of Mariéjol's,
whose bands start at 1, and of the pages taken without it removes only
Domesday 200. Mariéjol's 1,041 words the alignment did not place are
the words of its garbled note lines; how many of them are body words
cannot be told from the alignment. The rule misses pages where a marker misread as a larger number
comes before a smaller one: Mariéjol's page 210 reads its five markers
"U)", "li)", "(S)", … as 1, 2, 3, none, 11, 5, and its notes stay in the
body (section 16 says how they are kept from being quotes).

### A note that runs over a page break

The first note of a page's band continues the last note of the page
before when it has no marker, its first line is not indented (less than
5 pt from the band's left edge), and the last page before it that has
notes is the page before, blank, plate and excluded pages aside. It is
then part of that note: the note keeps the id of its first page and has
an origin on each page, and its reference is on the first page.
Measured in Domesday: 57 pieces are joined; the reference holds the end
of the note before and the piece in one note for 37 of them, in two for
2, and 18 could not be checked (tables, pieces of a few words). Kadesh's
indented pieces without a marker, looked at on its pages 8 to 15, are
notes whose marker the OCR lost or glued into a word ("'There"), so they
stay notes of their own; so do Haskins' nine first pieces without a
marker, six of them the start of a "Bibliographical note".

### References

**Candidates.** On each page, these words of the body are candidates, in
reading order:

- a **glued number**: a letter, then any punctuation, then 1 to 3 digits,
  then only punctuation ("land3.", "Kadesh,12", "causa)27.",
  "12s.2"), unless the word starts with an abbreviation that a number
  follows in citations and has no other letters: c, p, pp, f, ff, n, nr,
  no, vol, ch, cap, art, l, ll, q, a, t, v, s, d, m, in any case, with or
  without "." ("p.12", "vol.3"); or punctuation, 1 to 3 digits and
  only punctuation after (Kadesh page 10 reads ";13"). Punctuation is
  what Unicode counts as punctuation (its categories P): "," ")" "'"
  "/", not a currency sign, so "£2" (Domesday page 83, "of this £2 is
  due") is no candidate. A number with punctuation after it only is no
  candidate either: Kadesh page 10 prints "(Nos. 1, 2, 13, 14) ;13", and
  "13," would take note 13 from ";13", which comes after it (decided in
  task 2.3, 16 November 2026). In "12s.2" and "30d8"
  (Domesday page 83) the "s" and "d" are shillings and pence after a
  number, not the start of the word, so they are candidates;
- a **bracketed number**: an opening bracket, 1 or 2 digits or letters
  read as digits (above), a closing bracket, and only punctuation after
  ("(1)", "(i).", "{2).");
- a **sign**: the word "^", "*" or "•"; or a word that has a letter,
  then any punctuation, then one of these three signs at its end
  ("rulers.^", "Normandy.*"); or such a word with punctuation only after
  the sign ("servus*.", Domesday page 55; "burh*." page 219), as a
  glued number may have. Punctuation here is Unicode's (categories P),
  as for the glued number; a word with no letter before the sign, such
  as "*.", is no candidate. A lone "'" or "t" is
  not one: in Domesday such a match was right 28 times in 82. The sign
  followed by punctuation was added on 18 November 2026: by the
  evaluation of that day, 178 of Domesday's notes were not linked to
  their reference, and at 20 of them the reference was a sign followed
  by punctuation. Words of this form, counted over every line of the
  eight books' `lines.json` at main a0a1675 (body, bands and margins
  alike, so more than the body's candidates): Domesday 53, Kadesh 42,
  Gierke 22, Haskins 4, Stubbs and Turney 1 each, Haynes none, and
  Mariéjol 413, where the book's reference form, the bracketed number,
  leaves signs out of the matching (below). Structure run on copies of
  those runs with the form (spec review, 18 November 2026), before the
  exclusion of "S*." below: Domesday's linked references go from 1,493
  to 1,516, 23 notes gained and none lost, though on page 77 note 2's
  reference moves to a "*" and note 3 takes the "8"; Kadesh, Gierke and
  Haskins do not change. A word with punctuation after the sign whose
  part before the sign holds one letter alone, "S*.", is no candidate:
  Domesday prints "St." with a raised "t", which the OCR reads "S*." 28
  times, and checked on the page images, 21 of those 23 new links were
  right and the 2 wrong were "S*." on pages 285 and 333 (18 November
  2026). With that exclusion, Domesday's linked references go from
  1,493 to 1,514: 21 notes gained, none lost, and one reference moved,
  on page 77, to the right note. A sign at the end of a
  word of one letter, "T*", stays a candidate: the rule changed on all
  eight books would also unlink a reference of Kadesh's page 39.
  An opening single quotation mark, "‘", is a sign of this kind too,
  but only after a letter and any punctuation, never a word of its own:
  a word never ends with an opening quotation mark, and Tesseract reads
  the raised 4 after "Salvolini" on Kadesh's page 9 as
  "Salvolini‘". Without it the page's two other candidates, "Lenormant,*"
  and "Chabas*", took notes 4 and 5 instead of 5 and 6, since the page's
  notes have no value. Measured on 21 November 2026 on every line of the
  `lines.json` of the seven books' runs of the note-links plan, one word
  more has this form besides "Salvolini‘": Domesday's "S‘." (page 329),
  which the rule for "S*." keeps out. Kadesh has 10 words that end
  with "“" after a letter ("Zahi“", page 27, is reference 64 by the
  references read by eye, below), which are left as they are until checked.
  A "‘" after a letter may also be a closing quotation mark misread
  ("Kings‘" for "Kings’"), so a page's "‘" candidates are kept only
  when the page's matching (below) pairs more of its notes with them
  than without them: only when a note of the page needs a reference that
  no other candidate gives. A sign against a note with no value scores
  2 whichever sign it is, and of two equal alignments the earlier
  candidate wins, so without this a "Kings‘" before a note's "*" would
  take the note. On Kadesh's page 9 the matching pairs three notes with
  "Salvolini‘" and two without it.

**The book's reference form.** A first pass of the matching below, over
every page and with every candidate, counts for each kind of candidate
its **exact matches**, pairs whose candidate reads as the note's value
(score 3 below); the kind with the most is the book's reference form:
the glued number in Domesday and Kadesh, the bracketed number in
Mariéjol, none in Haskins, which has no exact match. Then only
candidates of that form are kept, and signs too, unless the form is the
bracketed number: Mariéjol prints its references at full size, and its
141 matches to signs (its OCR is full of "*" and "^") were right 22
times.

**Matching.** On each page, the notes that start there, with their
values, and the page's candidates, in reading order, are aligned: a set
of pairs, each note with at most one candidate and each candidate with
at most one note, such that a later note is never paired with an
earlier candidate, and the total of the pairs' scores is highest. It is
found by dynamic programming over the two sequences, as in the
alignment of two strings with no cost for a gap; of two sets with the
same total, the one that pairs the first note with the earlier
candidate wins, then the second note, and so on. The scores:

| pair | score |
|---|---|
| the candidate's number is the note's value | 3 |
| the numbers differ in one digit, a pair the OCR confuses (3 and 8, 5 and 6, 1 and 7, 3 and 5, 6 and 8, 1 and 4, 8 and 9, 2 and 8) | 2 |
| a sign against a note with no value | 2 |
| a sign against a note with a value (Haskins: "^" for note 1) | 1 |

**A note without a value between two with values.** Before the
matching, a footnote with no value that lies between two notes of its
page with values a and b, k places after the first, is matched as a
note of value a + k when b − a is the number of places from the first
to the second: their markers were lost, and the numbers between follow.
A note before the page's first value or after its last keeps none.
Kadesh's page 10 prints notes 10 to 14, which Tesseract
reads as "10", "1!", none, "13The" and "1$", so the notes' values are
10, none, none, 13, none. The "*" after "(see above)." took note 11,
the first note without a value, which a sign scores 2 against 1 for a
note with one, and "Kadesh,12" matched no note. With the values 11 and
12, "Kadesh,12" takes note 12, and the sign note 14, the only note left
without a value. In a book numbered per page every note has a value but
a page's first piece that continues an earlier note, so the rule gives
values only in a book numbered through, as Kadesh is.

Measured on 21 November 2026 on the `lines.json` of the seven books'
runs of the note-links plan, with the "‘" above: Kadesh's links go from
41 to 43 and 5 change, each right by the page images of pages 9 and 10:
"Salvolini‘" takes note 4, "Lenormant," note 5 (was 4), "Chabas" note
6 (was 5), "Kadesh,12" note 12, and "(see above)." note 14 (was 11).
Page 9's three agree with the references read by eye in
`tests/fixtures/expected/kadesh_reference/note_references.json`, and no
other link of its twelve pages changes. No link of the other six books
changes.

A pair that none of these rows scores is never matched, and a note that
its page's numbering leaves out ("Its value") is in no pair. A note left
unmatched has `referenced` false; a candidate left unmatched
stays as it is. A matched pair is linked whether or not the reference
reads as the note's marker, and the reference keeps what the OCR read
(owner, 15 November 2026): the OCR reads the two sides of a superscript
differently, and of the pairs matched in the second research the
reference read exactly as the marker in only 21 of Haskins' 60, 1,202 of
Domesday's 1,440 and 182 of Mariéjol's 676. The fidelity check asks
only that a reference have a marker's shape (architecture §13); every
reference these rules split off has it.

**What is changed.** A matched glued candidate, a number or a sign at
the end of a word, is split by a `note_marker` word change, ("land3.",)
to ("land", "3", "."), ("rulers.^",) to ("rulers.", "^"), ("servus*.",)
to ("servus", "*", "."), and its block
gets two or three spans, the reference one with `note_ref` the note's
id; the spaces stay with the spans around it. A bracketed number or a
sign that is a word of its own becomes the reference span, with any
punctuation after it split off the same way ("(i).": "(i)", "."). A
candidate whose reference would hold a letter ("(i)", "(li)", read as
1 and 11) stays in its word, since the fidelity check refuses a
reference span with a letter that was a whole word of the lines
(architecture §13): only digits and signs are linked. Such a candidate
is left out before the matching, not matched and then left unlinked:
scored by the evaluation tool against Mariéjol's reference text on 16
November 2026, 543 of its notes have the right reference when it is left
out first, 521 when it is matched first, since a matched "(i)" takes the
place of a later "(1)" (pages 279 and 334). The note's `referenced`
becomes true.

### What the rules give

Measured in the second research with the prototype of these rules,
before the notes left in the body were taken:

| book | references in the reference text | notes with a marker found | matched to a reference on their page | of these, the word before agrees with the reference text |
|---|---|---|---|---|
| Haskins | 72 | 61 | 60 | 47 |
| Domesday | 1,731 | 1,607 | 1,440 | 1,366 |
| Mariéjol | 1,432 | 862 | 676 | 407 |
| Kadesh | (no reference text) | 62 | 42 | |
| Gierke, endnotes | (no reference text) | 288 | 205 across the book, 186 of them exact | |

"Agrees" compares the word that carries the reference, without the
reference, with the words before the reference text's references; it
undercounts where the OCR damaged the word ("worthy1." where the
reference text has "trustworthy", the end of a hyphenated line), and most
of Mariéjol's are damaged. On Mariéjol's pages 211 to 219, each of the
21 matched pairs links the reference whose number, digit-like letters
read as digits, is the note's place on its page. Mariéjol has 862 notes
in the band against 1,432 in the reference text because a fifth of its
note words lie in the body; the rule for notes left in the body adds
some of them.

### Where the rules fail

- **A reference the OCR split or dropped**: on Mariéjol's page 214 the
  text layer reads "(1)" as "(» i)", no candidate, so note 1 is
  unreferenced and "(»" and "i)" stay in the text. On Kadesh's page 10
  "Nations" has no "10" after it and the reference to note 11 is read as
  a quotation mark ("north.\""): 3 of the page's 5 notes are linked (12,
  13 and 14).
- **A note whose marker the OCR lost**, first on its page and not
  indented, is joined to the note of the page before (Domesday page 87,
  "sochemanni": 2 of the 39 joins checked).
- **A false candidate in the right place**: the alignment can link a
  note to a number that is no reference, a citation whose abbreviation
  the list lacks or OCR noise ("770X19", Gierke page 181); in a book
  numbered per page, a page whose reference to note 2 the OCR lost links
  note 2 to the next candidate that reads 2 or a digit confusable with
  it.
- **Kadesh's notes on pages 9, 11 and 13 to 15** are too damaged to cut
  ("*Oampagne de Kkamitf"): 94 of its band blocks after another note
  have no marker. They stay notes with no marker, unreferenced, in
  printed order.
- **Tables in Domesday's notes** (pages 43, 44, 201, 484): a row is
  joined to its note, unless its first word is a number and the row is
  indented 5 to 40 pt, which rule 2 takes for a new note.

## 12. Endnotes

Gierke prints its notes not at the foot of the page but together, after
the text: pages 186 to 282 of the whole book, under a centred "NOTES."
on page 186, set in 9 pt type against 11 pt for the text, one paragraph
each, numbered "1." to "345." through the book, with margin notes of
their own beside them (excerpt page 8, notes 291 to 294). Layout reads
them as body. They are notes of kind `endnote` (architecture §8), a
kind of their own although they are notes, as footnotes are (owner, 15
November 2026).

**The endnote section** is found from runs of consecutive body
paragraphs whose first words are endnote markers (section 11, the last
form) with rising values, with any number of paragraphs without such a
marker between them: a marker that does not rise above the one before
ends a run and starts the next. The survey finds them (section 2, step
1) from the lines that start a paragraph by section 6's rules. A
**bare number**, 1 to 3 digits with nothing after them, as Turney marks
its notes (section 21), counts as an endnote marker here too, in a run
of bare numbers whose first value is 1 and outside the config's
`contents_pages`: the first because each of Turney's groups (below)
starts at 1, the second because Gierke's printed contents, pages 63 to
66, start 13 lines with rising bare numbers from 139 (section 6, rule
3), which would otherwise begin its section 120 pages early. A bare
number that does not rise above the marker before it is no marker
unless it reads 1, so it neither starts a run nor ends one. A run of
bare numbers may start with one **misread marker**: a paragraph whose
first word is one character that is not a digit, with a word after it,
whose first line is hung as section 6, rule 3, says (5 to 20 pt left of
its region's text edge), when the next three paragraphs that start with
a bare number read 2, 3 and 4 and the nearest one before it does not
read 1. The last two tests keep a later paragraph of note 1 that opens
with "I", or one indented after it, from being a second note 1 that
would take the true note 1 for its group heading. Its marker is that character as the OCR read it, taken out as
any marker (section 11), and its value is 1, given by its place before
2, 3 and 4, as a note numbered per page takes its value from its place
(section 11, "Its value"); no word is changed. Turney's chapter Three
opens its notes with a "1" the OCR read as "x" (page 258): without this
its notes 2 to 48, which do not rise above chapter Two's last, 48, were
later blocks of that note, and its group was lost. Section 6, rule 3,
starts such a paragraph. The two forms make runs of their own: a bare
number neither goes on with nor ends a run of "N." markers, and the
section's markers are those of the forms of its runs of at least 8.
Gierke prints a bare "1" before some of the margin notes that layout
leaves in its notes' body (pages 195, 196, 225, 226, 237, 240 and 241);
read as markers in the same runs, they made 9 more endnotes and cut
the section into groups (measured on 18 November 2026). The
section runs from the first marker of the first run of at least 8 to
the last marker of the last such run, so that a damaged marker that
reads lower does not cut it in two. On its first page it reaches back
over the paragraphs before its first marker up to the first heading
block above them that is not a group heading (below), which stays out
("NOTES." on Gierke's page 186, centred; the owner's books set this
title flush left, so before this revision Haynes' was taken into the
section, as a note without a marker); it
ends with the last paragraph that starts on the page of its last
marker. A paragraph between them that starts with no such marker
belongs to it. The section's first page starts a new block: no
paragraph of the page before runs on into it; and no paragraph runs on
out of it: the first body line after its last page starts a paragraph,
so that its last endnote does not run on over pages with no body text
into a later page. A paragraph of the section before its first endnote
marker (the end of a note whose start is on an earlier page not in the
PDF or the excerpt) is an endnote with no marker, unreferenced. The end
is so that the library's card on Gierke's page 288 ("BINDING SECT. NOV
8 1967"), after five blank pages, stays out; the card is also among
Gierke's `exclude_pages`. The 8 is set between what the six
books hold, measured on the first plan's paragraphs on 16 November 2026:
the runs of at least 4 rising numbered paragraphs are one in Kadesh, of
6 (pages 20 to 40), and Gierke's, of 299; and the Gierke excerpt holds 12
endnotes, 291 to 302 (pages 270 and 271), which must make a section for
its reference page. The research's 20 would leave them paragraphs. In Gierke it
runs from "1." on page 186 to page 282: 288 paragraphs start with a
clean "N.", in rising order without exception, and about 25 more with a
damaged one ("I4I-", "!6o."). Each paragraph that starts with an endnote
marker becomes a note of kind `endnote`, its marker taken off as in
section 11, its value what the marker reads; the paragraphs after it
that do not are its later blocks. The heading "NOTES." stays a heading
in `blocks`. Every note of section 11 is of kind `footnote`.

**Note groups.** Both owner's books (section 21) collect their notes
at the back under a heading per chapter, the chapter's number and title
or "Introduction", and number them from 1 again under each heading:
Haynes in 18 groups, one column, each note "N." with a full stop and
its first line indented; Turney in 11 groups, two columns a page, each
note a bare number hung in the margin (section 6, rule 3), its group
heading starting with the chapter's number, hung the same way. A **note
group** is the endnotes from a note whose marker reads 1 (its value,
section 11) up to the next such note, or to the section's end; the
notes of the section before the first such note belong to the first
group. A section with no marker reading 1 after its first note is one
group, as Gierke's, whose numbering runs through the book.

A **group heading** is the block of the section right before a group's
first note, when it holds at most 3 lines and its first line lies at
least 1.5 body line pitches below the line before it in the body
stream, or is the first line of its region: a heading set apart, at
the top of a column too. The first line of a region is told by
position: a line on a later page than the line before it, or whose top
lies above that line's, as the top of a right column lies above the
foot of the left one. An endnote whose marker reads a number other
than 1 is never a group heading: the short last note of a group at the
top of a page, the first line of its region, would otherwise be taken
for the heading of the next group. A block or a line with no letter or digit (a
speck the OCR read as "/") is passed over here, as in the tall line's
gap of section 14: the block right before a group's first note is the
nearest before it that holds a letter or a digit, and the line before
a group heading the nearest that holds one. On Turney's page 268 a
"/" 5 pt high lies under chapter Six's heading, between it and the
group's note 1, and the heading was missed; the "/" stays a block of
the note before the heading. It may be a paragraph, a heading block
(section 14 makes some, such as Turney's first group heading, an
unindented "Introduction" 8 pitches below the title "Notes") or what
section 11 would make a note, since Turney's starts with a number. It
is no note, starts no group (Turney's chapter One heading starts with a
bare "1", page 253) and is no block of the note before it: its text, its lines
joined by single spaces, becomes the `group` of the group's first note
(section 7), and the fidelity check counts it as words of that note.
A group heading that no paragraph rule starts ends the block before
the group's first note, after that note's last line: Haynes sets four
of its eighteen (chapters 5, 6, 10 and 12, pages 343, 344, 362 and
370) flush left under the note before, which section 6's rules 1 and 2
do not cut, and section 14 does not take them for headings. So, in a section of several
groups, when the block right before a group's first note is no group
heading, its last lines from the last of them that is set apart (1.5
pitches below the line before, or the first of its region), when that
line is not the block's first and at most 3 lines remain, are cut off
into a paragraph of their own, which is then the group heading. With
it Haynes has its 18 group headings, without it 14 (measured on 18
November 2026 with the configs of section 21).
Measured by the survey: Haynes' group headings stand about 30 pt (2.1
pitches of 14.4 pt) below the last line of the note before; Turney's
30 to 32 pt (1.8 to 1.9 pitches of 16.8 pt) or at the top of a column;
the lines of a note lie 13 pt apart (0.8 pitch) in Turney and about
11.6 pt in Haynes. Any other heading block inside the section is made
a paragraph, a later block of its note: a heading in the notes would
enter the EPUB's table of contents. Not in the EPUB's table of contents
either is a group heading, which markdown writes before its note
(section 25; **Open 2**).

**Endnotes run into the note before.** Where a note starts on a line
of its own but no paragraph rule starts a paragraph there, its marker is
a word inside the paragraph of the note before: Haynes sets the first
line of a note indented, and when the note before ends with a full line
nothing tells the paragraphs apart; Turney's OCR reads the full stop
that ends a note after a page number as a hyphen, "p. 487-", and the
hyphen joins that line to the next note's. Such a note is cut off the
paragraph before it, once the section and its group headings are found,
at a line of the section's paragraph, not its first, when:

- the line's first word is the marker of the next value: the value of
  the paragraph's note plus one, plus one more for each note already cut
  off this paragraph, in the section's form (digits then "." or "-" in
  a section of "N." markers, "57." or "57-"; bare digits in a section
  whose markers are mostly bare numbers, "57");
- the line before ends a note: its last word ends with a full stop,
  with only closing brackets and quotation marks after it ("river.",
  "1987).", "p. 61.", "river.\""), or is a number and a hyphen
  ("487-");
- the section's next marker after this paragraph does not read that
  value, so that a note whose own paragraph follows is never made
  twice.

A number that is not the next value stays text: a line that starts
"12." inside note 7 ("see note 12." broken before its number) is no
note, nor is "8." in note 7 when the next paragraph starts with "8.".
The marker must start a line: of the run-on markers found inside the
notes of Haynes (searched for a word that reads the next value after a
note whose next marker skips it), 51 of 53 start a line, and the 2 that
do not have no full stop before them.

Measured on 23 November 2026, structure run on copies of the runs of
`runs/more-note-links-endnotes/`: Haynes' endnotes go from 632 to 691,
59 cut off; the line before ended with a bracket and a full stop 17
times, a letter and a full stop 17, a number and a full stop 16, a
number and a hyphen 7, and a full stop and a closing quotation mark once
(58 measured before the "N-" form was added, which added 1). Turney's
go from 613 to 618, 5 cut off, each after a number and a hyphen.
Gierke's go from 299 to 311, 12 cut off, each checked on the page
images as a note that starts its own indented line. The body gains
61 links in Haynes (2 to notes that were there before), 3 in Turney
and 10 in Gierke, by the matching or the gap rule, each checked on the
page images in Gierke; no link of before moves, and the four footnote
books do not change. Where the numbers of a group still skip, the
missing number is not in the note before as a word that starts a line:
Haynes' 11 (between 10 and 12) and Turney's 41 and 42 (between 40 and
43). Haynes' "37." between "56." and "58." is the misread marker of
note 57 (the gap rule's order, above).

**References.** Endnotes are numbered through the book, or through each
group, so they are matched as in section 11, but once over the whole
book, or once over each group, not per page: the endnotes of a group in
order of their values against the glued numbers of the body of the
group's chapter (below), in reading order, by the same scores; a book
with one group takes the body before the section, as Gierke does. The
candidates are taken only from the pages after the last of the config's
`contents_pages` (Gierke: after page 67, so pages 68 to 185), and only
those no footnote took: Maitland's introduction, before Gierke's own
table of contents, refers to its own notes, and its glued numbers took
endnotes 1 to 7 from Gierke's "Law1" (page 88), "communities2." (93)
and the rest (decided in the review of 16 November 2026). A reference that reads another number than a note's (a pair the
scores allow, digits the OCR confuses) never takes that note when
another glued number of the group reads the note's number, which is
then the note's own reference, or when the reference's own number lies
between the group's lowest and highest note numbers and no note reads
it, so that it stands for a note whose marker the OCR lost: it is left
unlinked. On Haynes the OCR lost the markers of notes 47 and 49 of
chapter 15 (page 301) and of note 18 of chapter 14, and references 48,
49 and 18 (pages 301 and 234) were linked to notes 46, 48 and 19. On the
survey's configs (18 November 2026) the rule leaves Turney's 530 links
as they are, with its 8 references the OCR read with a "3" for a printed
"5", gives Haynes 582 links instead of 584 with none to a note of
another number, and Gierke 208 instead of 215, among the 7 lost "1"
linked to note 7 (page 95) and "18" to note 19 (page 97). Gierke's markers end with "." ("1.") and its
references do not ("Law1"), so none reads as its marker; linked as
section 11 says, 215 of them are, 193 by an exact value (measured on
18 November 2026 on the layout of the plan owner-books at 4d9f1e9, the
same as the clean-text build's; the 205 and 186 written before were of
an earlier build). Maitland's
introduction (pages 0 to 85) has notes of its own, printed on pages 62
to 64; they were not studied, and stay where they are now.

**The candidates of endnotes.** Endnotes take three forms of glued
number that footnotes do not, besides the candidates of section 11:

- the glued number of section 11 without its exclusion of the
  abbreviations of citations: "art.27", "Q.19" (a word such as
  "Smart.27" is a candidate under section 11 already);
- 1 to 3 digits after a number of exactly 4 digits, a year, or after a
  closing bracket, with between them only the punctuation that ends a
  sentence, a clause or a quotation (`. , ; : ! ? ) ] ' " ’ ”`): at
  least one such mark after a year, so that "19731" is no candidate,
  and none or more after a bracket. Only punctuation may follow the
  digits: "1911.34",
  "1886,57", "(61).29", "[1862]).38", "5)16", "(1936)41". A dash or a
  hyphen is not such punctuation, so a range, "1914-18" or "(612-19)",
  is no candidate; nor is a number after 1 to 3 digits, so a time
  "10.35", a decimal "4.6" or a date "14.9.73" stays text;
- either of these, or a glued number of section 11, whose digits are
  followed straight by an em or en dash and a word, with no punctuation
  between the digits and the dash: "river20—and" reads "river", the
  reference "20", and "—and", which stays text after the link; a hyphen
  is not such a dash.

A word that section 11 reads as a candidate keeps that reading, so
"(1)." stays a bracketed number, which endnotes do not take; "(61).29"
is no candidate of section 11, since a bracketed number has only
punctuation after its bracket, so it is read by the second form. These
forms are matched like the others (**References** above): the notes of
a group in the order of their values against the candidates of its
chapter in reading order, so a candidate is linked to note N only when
it comes after the one linked to the note before N. Footnotes keep section 11's
candidates: the footnotes of the public-domain books are matched page
by page, where a year with a glued number has not been measured, and
the plan `more-note-links` changes Domesday's footnote candidates on
measurements of its own.

Measured on 23 November 2026, structure run on copies of the runs of the
small-fixes plan (`runs/small-fixes/`): Turney's endnotes without a
link go from 83 to 65 of 613, by 18 new links, 17 after a year and 1
after a bracket; Haynes' from 50 to 13 of 632, by 37 new links, 26
after a bracket, 4 after a year, 3 after an abbreviation and 4 before a
dash. Each new link reads its note's number and lies in its note
group's chapter, no link of before moves or goes, and on the five
public-domain books of that run, Gierke's endnotes among them,
`blocks.json` is the same byte for byte. The rest are taken by the
gap rule below.

**The gap between linked neighbours.** After the matching above, a
reference the candidates missed is looked for where it must lie: between
the references of the notes before and after it. In one note group, a
**run** is a set of notes of consecutive values N to N + k − 1, none of
them linked, such that the note of value N − 1 and the note of value
N + k are both linked by the matching above; its **gap** is the words
of the body's paragraphs (blocks of kind `paragraph`, not headings,
figures or quotes) after the first of those two references and before
the second, that no footnote and no link took. A link made by this rule
is never the neighbour of another run: the runs are found once, from
the matching's links only. The examples below are made up; the owner's
books are named by page and note only.

A word of the gap **reads as** a reference to note V when it is:

- **a lone number**: 1 to 3 digits alone, equal to V ("river 23" for a
  printed "river.²³" whose full stop was lost, or whose number the text
  layer put a word early); or the start or the end of V's digits when
  the word before ends with punctuation after a letter ("river. 9" for
  79). Either is none when the word before or after is the name of a
  month or its abbreviation, in English: Turney prints a date with the
  day 14 where note 14 is sought (page 81);
- **glued digits**: a word with a letter or punctuation, then 1 to 3
  digits, then no letter or digit, whose digits are V, the start or
  end of V's digits ("river!’'9" for 19, "river/0" for 30), or V with
  one digit changed by a pair the OCR confuses (section 11,
  "Matching"). The digits are none after a digit, or after a digit and
  only `. , : ;`: a time "10.35" and a number "2,718" stay text, while
  "(71-72)-46" has a bracket between;
- **a sign the book does not print**: "^" or "~" in any book, and a
  straight quotation mark (`'` or `"`) in a book whose body holds more
  of the curly forms of that mark (‘ ’ or “ ”) than of it, Turney but
  not Haynes; alone after a word that ends with punctuation after a
  letter ("river. '"), or glued after a letter and then punctuation
  ("river.\""), with only punctuation after. A sign glued straight after
  a letter is none: on Turney's page 227 such a sign is the curly
  closing quotation mark read straight, and the reference, read as a
  letter, comes after it.

The k notes of a run are linked when exactly k words of its gap read as
a reference to one of the run's notes, and the i-th of them, in reading
order, reads as a reference to the i-th note: a run of one note with
one such word links that word; with none or with two, the run stays
unlinked. A lone number or glued digits are linked as their digits, a
glued word split as section 11 says ("river!’'" and "9"); a sign as the
sign.

Before the matching, an endnote whose value is not N but which lies,
in the book's order, between a note of value N − 1 and one of value
N + 1 is matched as N: Haynes' note "37." between "56." and "58." (page
351) is note 57, whose reference reads 57 on page 103. Its marker stays
as printed.

What the gap rule does not take, measured on the notes left: a letter
read for a reference (Haynes' note 11 on page 67, Turney's 29 on page
227), since a reference span holds no letter (architecture section 13);
digits with a letter after them (Turney's 40, page 91); digits confused
outside the pairs of section 11 (0 for 9, Turney's 39; 8 for 5, its
59); a sign straight after a letter (Turney's 66, page 75, though right
there); and runs whose gap holds fewer words that read as their notes
than the run has notes (Turney's 36 to 39, with two).

Measured on 23 November 2026, structure run on copies of the runs of
the rule above, `runs/more-note-links-endnotes/`: Turney's endnotes
without a link go from 65 to 27 of 613, by 38 links: 4 lone numbers
equal to the note, 3 lone numbers that are part of it, 23 glued
digits, 8 signs. Haynes' go from 13 to 5 of 632, by 8 links: 6 lone
numbers, 1 glued number and note 57, by its order, to a lone number. Gierke, on the small-fixes run,
gains 11 links by glued digits (page 97, "supreme12.^)" for 12; page
168, "bestow2*5'" for 285); the four footnote books do not change.
Every new link was checked on the page images: each lies on the printed
reference, or, for a lone number the text layer put a word early
(Turney's pages 83 and 123), on the reference's digits one word before.
Two lone "^" that the rule took in Gierke before it asked for the word
before to end a phrase (pages 107 and 169, in lines beside a margin
note) were wrong; the rule above does not take them.

**The chapter of a group** is a level-1 heading block of the body,
after the config's `contents_pages` and before the endnote section,
found from the group heading: the heading whose spans' letters, in
lower case, are the most alike (`difflib.SequenceMatcher` ratio, at
least 0.85) to the group heading's letters in
lower case, once a first word that is a chapter label word is dropped
("Chapter" of "Chapter 1."); a number, "1." or Turney's leading "2",
falls out with every other character that is not a letter. The groups follow the chapters' order, so a
group without a heading, or whose heading is alike to none, takes its
chapter by counting from the nearest group before it that found its
chapter by its heading: the n-th level-1 heading after that chapter,
for the n-th group after that group; when there is no such group
before it, or that heading would not lie before the chapter of the
nearest group after it found by its heading, it counts back from that
one instead, the n-th heading before it for the n-th group before;
with neither, it counts from the first level-1 heading after
`contents_pages`, the first group's. A count that falls outside the
chapters, or back onto or before the chapter of the group before,
gives the group no chapter, and it reaches no block. Before this revision a group
without a heading took the heading after the chapter of the group
before, so a first group whose heading was lost took the first
level-1 heading after the contents (a preface, say) even when the
group after it named its chapter. Counting cannot tell which chapter a
group takes when another group between the counted ones was lost as
well: on Turney, before the fixes of layout §3, step 5, and of the
misread marker above, chapter Three's group was lost and chapter
Four's heading too, and chapter Four's notes took chapter Three's
references, 40 links in the wrong chapter, and the counting gives the
same. A label is not compared: Haynes' body heading has "CHAPTER ONE"
in its label and its group heading "Chapter 1.", and the titles match
("AMD" for "AND" in the body's OCR still gives a ratio above 0.9). The
0.85 is not the running heads' 0.70 (section 3), since it is set
between what was measured on 18 November 2026 on the 29 group headings
the two books' notes give (Turney 11, Haynes 18): Turney's are 1.00
alike to their own chapter's heading and at most 0.46 to another's,
Haynes' 0.94 to 1.00 to their own and at most 0.76 to another's
(Haynes' chapter 9 to chapter 11, two titles that share three of
their four words); at 0.70 or 0.75 a group whose chapter
heading the body lacked would take that other chapter. A
group's candidates are the glued numbers of the body, from the pages
after `contents_pages` and not taken by a footnote, as above, from its
chapter's heading up to the chapter heading of the next group after it
that has a chapter, or up to the endnote section when no later group
has one: a group without a chapter between them does not stretch the
reach of the group before it over the chapters after (with groups
"alpha", two without a chapter and "betagamma", the first reached to
the section's start, over "betagamma"'s chapter, before the review of
the plan's work package 3). Only the group heading loses
a label word; a body heading is compared by its spans, which never
hold its label. Before this revision the
whole book was one range and Haynes' 633 endnotes were matched in order
of their values, all the notes 1 first: 127 were linked, 120 of them
to a note of another chapter. A prototype that took each group's
chapter from the survey's list of chapter openings, not from the
headings, linked 584 of the 633, each to a reference in its own
chapter (measured on 17 November 2026 on the survey's `lines.json`).
Turney's could not be prototyped before its notes are cut (section 6,
rule 3); the survey counts about 555 glued numbers in its body pages 14
to 251 and about 620 notes. The running head of Turney's notes pages
names the printed pages their references are on; it is removed with
the other heads and not used.

**In the EPUB** (owner, 15 November 2026): every endnote stays where it
was printed, in one list in the book's order after the heading "NOTES.",
and a linked endnote is also shown as a pop-up from its reference. How
it looks is the markdown and epub stages' to decide (section 19); structure gives
the kind and the link only.

## 13. Margin notes: where each is placed

A margin note goes just before the paragraph beside whose line it was
printed, rendered as a small bold line (architecture §9 and §17; the
owner confirmed it on 15 November 2026, reading margin notes as short
summaries of their paragraph). The rules say which paragraph that is.
They apply to every margin region: Gierke's and Domesday's outer margin
notes, and the notes Stubbs cuts into the body column, which layout now
takes out of the body lines beside them (layout §3, step 2b).

1. **One printed note, one block.** A margin region is part of the
   margin region above it, on the same page and side, when its top is at
   most 2.5 pitches below that region's bottom and its first line is not
   beside a paragraph's first line (this section's rule 2). The same
   side means that the two regions overlap across the page; the margin
   region above is the nearest one above on that side, with the regions
   already joined to it. Rule 1 is applied after rule 3 has split the
   paragraphs, so a region beside an indented line that rule 3 makes a
   paragraph's first line starts a note of its own; a paragraph's first
   line here is the first line of any block, a note's too. Layout cuts a margin region
   where the next line is more than 1.5 pitches lower (a guess, layout
   §3, step 2), and Gierke sets its notes loosely: 268 of its margin
   regions that are not beside a paragraph's first line lie within 2.5
   pitches below another, against 38 that are beside one ("Bodies" /
   "politic." on page 109); in Domesday the counts are 31 and 3.
   The regions' lines are one after another in the block, but no hyphen
   is joined (section 5) where one region ends and the next begins: a
   line between them often went unread, and of the 11 joins made there
   on Domesday and Gierke, 10 made words that are not printed ("peathe"
   of "The pea-" and "the rSoyal", Domesday page 90; "Guardianvacant",
   Gierke page 127). Decided on 16 November 2026, in the review of work
   package 4.
2. **The line it is beside.** Take the top of the margin note's first
   line. When the first line of a paragraph of the page has its top
   within 0.5 pitch of it, above or below, that is the line beside;
   otherwise the body line whose top is nearest. Measured: a paragraph's
   first line lies within 0.5 pitch of the margin note's top for 519 of
   Domesday's 613 margin notes (511 within 0.25) and 379 of Gierke's 658;
   within 1 pitch, for 532 and 415. The preference for a first line
   matters where the note is set a little above its paragraph: Gierke's
   "Bodies" (page 109) overlaps the last line of the paragraph before
   more than the first line of its own.
3. **An indented line beside a margin note starts a paragraph.** When
   the line beside is not a paragraph's first line but its left side is
   at least 5 pt right of its region's left edge (section 6), it starts a
   paragraph, even after a full line. It is applied once paragraphs have
   been joined over page breaks (section 2, step 3.2), because the line
   beside may be the first line of a page whose paragraph runs on.
   In Domesday, each of the 13 margin notes beside the middle of a
   first-plan paragraph that could be checked stood beside an indented
   line (15 to 90 pt) where the reference text starts a paragraph; 27 of
   its margin notes are beside such a line.
   The line is one of a body paragraph, not of a note, and it does not
   follow a line that ends with a hyphen (section 6). Measured on 16
   November 2026 on the whole books: in Gierke 13 of the 36 indented
   lines beside a margin note printed outside the column follow one, and
   12 of them continue their word ("Univer- / sal Church", page 109).
   The margin note must be printed outside the column: the middle of its
   box lies left of the line's region's left edge or right of its right
   edge. A note cut into the column (Stubbs) indents the body lines
   beside it by its own width, about 60 pt, so their indent says
   nothing: in Stubbs 171 margin notes stand beside such a line, as
   "accession." (excerpt page 0) beside "f or instance…" in the middle
   of a paragraph. The middle of the box is taken, not the whole box,
   because Domesday prints some of its outer notes up to 5 pt into the
   column: 9 of its 24 margin notes beside an indented line are so.
4. **Before the paragraph that holds that line**, in `blocks`, after any
   margin note already placed before the same paragraph: the margin notes
   before one paragraph, or before one block of a note (rule 5), go in
   page order and, on a page, from the top down. So:
   - beside the middle of a paragraph (Stubbs' cut-in notes, several to
     a paragraph; 40 margin blocks beside a flush line on Gierke's pages
     86 to 185, many of them specks): before the paragraph, not where it
     was printed;
   - beside the last line of a paragraph: before that paragraph, unless
     rule 2 found the next paragraph's first line within 0.5 pitch;
   - at the top of a page whose first paragraph runs on from the page
     before: before that paragraph, on the earlier page, after the margin
     notes of that page that belong to it. Domesday has 39 such margin
     notes and Gierke 35 on pages 86 to 185; 18 of Domesday's 39 are
     beside an indented line, which rule 3 makes a paragraph start, and
     of the 10 that could be checked the reference text starts a
     paragraph at the line beside for 9.
5. **Beside a note.** When the line beside is a line of a note (Gierke's
   337 margin-note blocks beside its endnotes, pages 186 to 282), the
   margin note goes inside that note, as a `margin_note` block before the
   note's block that holds the line: for a note of one paragraph, before
   its text (owner, 15 November 2026). It is shown with the note, also in
   a pop-up.
6. A margin note with no body or note line on its page stays where
   section 6 puts side text.

Placing a margin note changes no word, so it needs no record; the
fidelity check does not look at order (architecture §13).

**What the rules give.** Against Domesday's reference text, whose
transcriber put each margin note before the paragraph it belongs to: of
the 328 margin notes that could be found in it, rules 2 and 4 on the
first plan's paragraphs put 304 before the paragraph the reference text
puts them before, and with rule 3, 317. Most of the other 11 are on
pages whose paragraph starts differ from the reference text's for other
reasons, or margin notes whose text matches more than one of its
("The villein", page 77). The other 312 of Domesday's 640 margin-note
blocks could not be checked: their text is too damaged or short, or
they are specks.

**Where they fail.**

- A margin note about a later part of a long paragraph goes to the
  paragraph's start, a page or more before the text it sums up: the rule
  the owner confirmed. Stubbs' cut-in notes are often like this ("His
  great position in Christendom", beside the sixth line of a paragraph
  on page 58, excerpt page 3).
- Specks read as margin notes (Haskins 15, Mariéjol 29, Kadesh 8;
  Gierke's "|", "*") are placed like margin notes, each a small bold
  line before a paragraph. Removing them is a rule of its own, not in
  this plan.
- A margin-note line that layout put in the body stays there (Gierke page
  87: the note reads "Diversity of rials.", and "mate-" stays in the body
  line).
- Two margin notes within 2.5 pitches beside one paragraph, the second
  not beside a paragraph's first line, are joined into one (this
  section's rule 1); how
  often wrongly was not measured.

## 14. Headings

The EPUB's table of contents is made from the headings, so a heading
missed, or a line made a heading by mistake, is the error a reader sees
first. structure makes a `heading` block of each chapter's and section's
title, with a level: 1 for a chapter, 2 for a section inside one.

**What the books show.** Every chapter heading of the four books with a
reference text has a centred line, and in Haskins, Stubbs and Mariéjol it is
set in capitals. Domesday's section headings are not ("§ 1. Plan of the
Survey." has 0.13 of its letters in capitals); what sets them apart is
space: the line before is 2.1 to 4.7 pitches above, the line after 1.3
to 2.8 below. Word heights do not tell headings apart: as height ratios
(section 16), Haskins' chapter titles are 1.22 to 1.37, Stubbs' 0.99 to
1.59, Domesday's section headings 1.0 to 1.2 and Mariéjol's titles 0.9
to 1.2, so the rule does not use height. Three books print a chapter
heading on two lines, a **chapter label** and a title ("CHAPITRE II" /
"DAUPHINE ET REINE"), 0.94 to 2.3 pitches apart, and Domesday 3.0 to
3.4 ("ESSAY I." above "DOMESDAY BOOK.").

Terms: a line's **capitals share** is the share of its letters
(`str.isalpha`) that are upper case. Its **gap above** is the distance
from the top of the line before it in the page's body stream to its own
top, in pitches, and its **gap below** the distance to the top of the
line after; a page's first line has no gap above, its last none below.
A **chapter label** is a line whose first word is a chapter label word
(section 3: CHAPTER, CHAPITRE, ESSAY, PART, PARTIE, BOOK or LIVRE, in
any case, with ".", ",", ":" or ";" after it or not), or is a roman
numeral alone as
the OCR reads one: 1 to 5 of the characters `IVXLCl1`, with an optional
".", ("II", "Ill" for III).

### The rule

A body line is a **heading line** when it is a tall line (below), or
when all of these hold:

1. it is centred (section 6, rule 2). On a page whose body regions hold
   fewer than 5 lines, it may instead be centred, by the same 15 pt and
   10 pt, between the leftmost and rightmost sides of the page's body and
   band lines (Haskins' page 129 prints "BIBLIOGRAPHICAL NOTE" above a
   section in small type that layout makes a band, so the body column is
   the heading itself). Or it is **flush left**: its left side lies
   within 4 pt of the left edge its centring is measured against (its
   region's, or the page's body column for a line of a region of fewer
   than 5 lines, section 6, rule 2), and its right side at least a
   quarter of that width short of the right edge, or is so between the
   sides of the page's body and band lines on a page whose body regions
   hold fewer than 5 lines, as it may be centred between them; and it is
   not a head line that section 3 left in the text in the band where it looks
   for running heads (at most 2 pitches below the median top of the
   book's head lines, or anywhere above it), unless it starts with a
   chapter label word; for a flush-left line, rule 4's second branch also asks that its last word not end
   with ".", ",", ";", ":", "?" or "!" (Turney introduces a block quote
   with a flush-left line set apart by 2.0 pitches above and below on
   its pages 93, 99, 100 and 160, each ending with such a sign).
   Domesday sets the headings "STATISTICS." and "AVERAGES." flush left
   above its tables on pages 426 and 428, which layout makes bands, so
   each heading is its page's body alone and as wide as the body column
   it is measured against; they were paragraphs, and "AVERAGES." ran on
   into the table that ends the page before. Measured on 19 November 2026 on the eight books'
   `lines.json`, flush left between the body and band lines makes these
   two lines headings and no other;
2. at least half of its characters other than spaces are letters, and
   one of its words has at least 4 letters and is not a roman numeral
   ("(VIII)", a page number of Mariéjol's preface, and the garbage of a
   map, "2»K O ) ? 4. )5", are not headings);
3. when it has more than one word, its last word is not a number or a
   range of numbers ("§ 1. Plan of the Survey, pp. 9 — 26." in a printed
   table of contents);
4. its capitals share is at least 0.7, or its gap above is at least 2.0
   pitches (or it is the page's first line) and its gap below at least
   1.3 (or it is the page's last line).

A **tall line** is a body line whose line height (section 1) is at
least 1.2 times the median line height of the page's body stream, that
has at least 4 letters, that passes rules 2 and 3, and whose gap above
is at least 1.3 pitches, or that is the page's first line or follows a
heading line: whatever its alignment, it is a heading line. The line
after a heading line needs no gap: Turney sets section headings on two
lines, the second as tall as the first and less than 1.3 pitches below
it (pages 80 and 85), and a group heading of its notes so (page 258);
without the clause the second line was a paragraph (measured on 18
November 2026: those three headings lose their last line, and
Domesday's false heading on page 481 one line, and nothing else
changes on the eight books). Turney
(section 21) sets its chapter titles flush left at 2.2 to 2.6 times the
body's line height, its chapter labels, indented 42 to 46 pt, at 1.2 to
1.4 times, and its section headings, indented the same, at 1.2 to 1.56
times, and no line of its running text that tall but one (page 40,
height 14 against 9, an OCR line made tall by an italic title and a
reference, 0.77 pitch below the line before, which the gap keeps out).
Haynes sets its chapter titles in capitals at 1.1 to 1.4 times, which
the flush-left branch of rule 1 takes. The six public-domain books' word
heights do not tell headings apart (above), so the gap and the 1.2 keep
the branch off most of their lines; what it takes there is under "What
the rule gives". The page's median, not the book's body word height:
on Gierke's endnote pages the text is smaller than the book's, and the
book's height took 941 lines there; on the notes pages of Turney, set
in 8 pt, the group headings (section 12) stand at 9 to 11 pt.

A page whose body stream holds more than 6 lines that tall, 1.2 times
its median line height, has no tall line: its median is then that of
smaller type, a table, a list or notes left in the body, and its tall
lines are its text. Domesday's page 419 sets 18 lines of text under a
table in small type (8 pt against 10), Gierke's page 50 sets 13 above
notes in small type, and on Domesday's page 136 the text layer boxes
14 lines, the last rows of a list and the paragraph under it, 11 to 28
pt tall, where the page image shows the list's small type and the
body's; without the condition each made
false headings of its text, the paragraph run into one heading block
by the lines that follow a heading line. On the pages of the eight
books where the branch finds headings, at most 4 lines are that tall
(Turney's page 39), and Domesday's page 528, the next most, has 11
and no heading. Any limit from 4 to 10 keeps the same lines out on
the eight books (measured on 17 November 2026 on the `lines.json` of
layout §3's new steps): Domesday's pages 136 and 419 and Gierke's page
50, and no other line.

For the tall line, a line of the body stream with no letter or digit
(a speck the OCR read as "#" or "/") does not count: the line before is
the nearest above that holds a letter or a digit, and the page's first
line is its first that holds one. On Turney's page 134 a speck "#" lies
0.38 pitch above the label "Chapter Six", which had then no gap above
it and was no heading; with the speck passed over, it is the page's
first line, and chapter six is found with its label. Measured on 17
November 2026 on the eight books: this changes no other heading.

A line whose top lies at most 2 pitches below the median top of the
book's head lines (or above it), and whose letters, at least 4, are at
least 0.6 alike to those of a line section 3 removed as a running head,
is never a heading line, whatever branch takes it: it is a running head
that section 3 left in the text. Layout makes no head region on
Domesday's page 159, a table, so its head "134 Domesday Book." stays in
the text, and Kadesh's page 38 has its page number "27" as head line,
with its author's name, "JAMES HENBY BREASTED", the line below; the
tall line made each a level-1 heading. Measured on 17 November 2026 on
the eight books, the rule takes away 4 heading blocks, each a running
head on its page: those two, Domesday's 552 ("Index.", under its page
number) and Mariéjol's 121 ("rcis CATIir"), and no other.

A line read by Tesseract whose words' median confidence is below 60 is
never a heading line, a chapter label or a continuation, whatever branch
takes it (section 34): under `ocr = "redo"` Tesseract reads rows of
hieroglyphs as centred junk.

A line right below such a line in the body stream is not a heading line
by rule 4's second branch, the gaps: its gap above is measured from a
row of hieroglyphs, not from text, and Kadesh prints under each row its
translation. On Kadesh's page 39 (printed 28) the translation of row 16,
"The stand which his majesty made while he was sitting on the northwest
of Kadesh." with the reference 97 (read as "”"), is one line set 22 pt
in from each side of the column, so centred, 3.2 pitches below the top
of the row and 2.0 above the paragraph after it; the gaps made it a
level-2 heading, and the unlinked notes of pages 8 to 38 (section 36)
gathered before it. The line can still be a heading line in capitals,
a tall line, a chapter label or a continuation. Measured on 21 November
2026 on the `lines.json` of the seven books' runs of the note-links
plan (Haynes and Turney among them): the gap branch takes 78 lines, and
this one alone lies below a line read poorly; the rule takes away that
heading and changes no other.

Two more kinds of line join a heading:

- a **chapter label** that is centred and whose next line is a heading
  line, although it has fewer than 4 letters ("IV", Haskins' "Ill");
- a **continuation**: the line right after a heading line, with at least
  4 letters, at most 2.6 pitches below it, that is centred, or, when it
  is not centred, whose capitals share is at least 0.9 and whose gap
  below is at least 1.5 (a line in capitals set apart from the text
  below it, but as wide as the column).
  This takes Stubbs' "John." under "CHAPTER VII." (the OCR read the small
  capitals as lower case) and Mariéjol's "L'EXPÉRIENCE ET L'ÉCHEC DE LA
  POLITIQUE MODÉRÉE", which fills the column and so is not centred.
  Below a chapter label alone, the continuation may lie up to 4.0
  pitches below it, as a title may below its label (heading blocks,
  below): Haynes' page 249 opens chapter fourteen's title with a line
  in capitals 2.87 pitches below "CHAPTER FOURTEEN", 58 pt short of the
  right edge, under a quarter of the width, and 1.09 times the page's
  median height, so neither flush left nor tall; without the 4.0 the
  label stood alone and the title's second line became a level-2
  heading of its own. Measured on 17 November 2026 on the eight books:
  this changes no other heading.

**Heading blocks.** Consecutive heading lines are one heading block when
the second is at most 2.6 pitches below the first, or at most 4.0 when
the first is a chapter label alone. So a chapter label and its title are
one heading, the label being the chapter's number and the title its
title (owner, 15 November 2026): one entry in the EPUB's table of
contents per chapter. When a heading block's first line is a chapter
label and another line follows it, the first line is the block's
`label`, its words joined by single spaces as printed ("CHAPTER III.",
"V"), and the spans hold the title, every line after the first joined
as a paragraph's are;
otherwise `label` is `None` and the spans hold every line (owner, 16
November 2026; section 20). A heading block starts a block and so does
the line after it.

**Levels.** A heading block is level 1 when its first line is a chapter
label, or starts with one of the label words (CHAPTER, CHAPITRE, ESSAY,
PART, PARTIE, BOOK, LIVRE), or when it is the first line of a page that
has no running head; any other is level 2. A heading block inside an
endnote section is a group heading or a paragraph (section 12), never a
heading. A roman numeral counts as a
label only as a line of its own, so "I. The Evolution of Political
Theory." is level 2. In the four books with a
reference text, this makes the chapters, the preface, the contents, the
index and Domesday's essays level 1, and Haskins' "BIBLIOGRAPHICAL NOTE"
sections and Domesday's "§" sections and "NOTE." level 2.

**Contents pages.** On the pages of the config's `contents_pages`, no
line is a heading line, but for the title of each contents run (section
30, rule 1); their lines were paragraphs (owner, 15 November 2026) and
are contents entries since 18 November 2026 (section 30): no chapter summary, verse (section 15 and 16, rule 4) or quote
(section 16, rules 1 to 3) is made of them either, a block counting as
on such a page when its first line is. Without that, Domesday's
contents page 14, set in small type, gives 5 quotes. A printed table of contents repeats the chapter headings, and
without the key the rule makes headings of them: Domesday's "ESSAY I. /
DOMESDAY BOOK." on pages 14, 17 and 19, Stubbs' "CHAPTER IX." and
"EDWARD I." on page 16. No rule plain enough was found to find such
pages: "a third of the page's lines end with a page number" finds
Haskins' contents page and 3 of Domesday's 7, none of Stubbs' or
Mariéjol's, and every index page and 15 of Domesday's tables.

**Drop capitals** need no rule: on all nine of Haskins' chapter openings
the text layer reads the drop capital as part of its word ("IN", 2.6 to
4.7 times the body word height), and layout places that word first on
the first line (layout §3, step 6).

### What the rule gives

Measured in the second research on the **body range** of each book,
from the page of its first chapter heading (Haskins 16, Stubbs 18,
Domesday 22, Mariéjol 18) to its end, without Stubbs' publisher's lists
after page 321, and on the whole book. The reference text makes a
heading of every line of the title pages and publisher's lists, and two
headings of a chapter label and its title in Stubbs and Mariéjol, so its
counts are larger:

| book | body range: heading blocks, right | body range: reference headings found | whole book: blocks, right | whole book: reference headings found |
|---|---|---|---|---|
| Haskins | 18 of 18 | 18 of 18 | 20 of 20 | 20 of 21 |
| Stubbs | 13 of 13 | 25 of 26 | 15 of 19 | 26 of 37 |
| Domesday | 22 of 27 | 22 of 23 | 23 of 33 | 23 of 28 |
| Mariéjol | 14 of 14 | 26 of 26 | 16 of 19 | 27 of 34 |

These counts were taken without `contents_pages`, so the whole-book
columns include the contents pages' headings.

| threshold | value | measured, each varied alone on the body ranges |
|---|---|---|
| capitals share | 0.7 | every value from 0.5 to 0.9 gives the same blocks; Mariéjol's lowest heading line, "CHAPITRE Vni", has 0.82 |
| gap above, a line not in capitals | 2.0 pitches | 1.5 adds a false block in Domesday; 2.5 loses one of its section headings, 3.0 three |
| gap below, same | 1.3 pitches | 1.0 changes nothing; 1.6 loses a Domesday section heading |
| join two heading lines | 2.6 pitches | 2.0 leaves a title apart from its label in Stubbs and in Mariéjol; 3.5 joins Haskins' half-title to the heading of chapter I below it (page 16) |
| join after a chapter label alone | 4.0 pitches | Domesday's labels stand 3.0 to 3.4 above their titles; not varied |

Neither branch of rule 4 is enough alone: without the capitals, Haskins
finds 6 of its 18 headings, its titles standing less than a pitch below
their numerals; without the gaps, Domesday finds 7 of 23.

**The flush-left and tall branches** (this revision) were measured on
17 November 2026 with a prototype of both, as written here, on the
`lines.json` of the clean-text build for the six public-domain books
and of the survey's runs for the owner's two (section 21), counting
the heading blocks `make_blocks` gives against those it gave without
them:

| book | heading blocks without | with | what is added |
|---|---|---|---|
| Haskins | 19 | 21 | two running heads that layout leaves in the text today (pages 23 and 235), which layout §3, step 3 now removes |
| Stubbs | 16 | 50 | the half-title's first line (page 18), which section 14 missed; 34 lines of the publisher's lists after the text (pages 322 to 337, one heading of the lists lost) |
| Domesday | 31 | 39 | 4 lines of text on pages 136 and 419, false; the titles of three tables, "TABLE", "TABLE II." and "AVERAGES." (425 to 428), and "(boroughs" (481) |
| Mariéjol | 15 | 21 | "BIBLIOGRAPHIE SUCCINCTE" (page 14), right; 5 garbled lines |
| Kadesh | 4 | 4 | |
| Gierke | 14 | 32 | 11 section headings of its list of authorities (pages 68 to 81), right; 7 running heads beside their page numbers, which section 3 now removes |
| Turney | 1 | 79 | not counted further: its running heads were still in the text and its chapter labels removed |
| Haynes | 0 | 46 | below |

On Haynes: Acknowledgments, Introduction, the closing chapter,
Bibliography and Index, level 1; 13 of the 16 chapters, each a level-1 heading with
its label ("CHAPTER ONE", at 0.8 of the body's height, passes rule 1
flush left and rule 4 by its capitals, and the title stands 2.6 to 2.9
pitches below it, within the 4.0 after a label); the other 3 as level-2
titles, because their labels were removed as running heads, which
section 3 now prevents; 20 section headings, level 2, one of them
(page 19, a short note before chapter one) not in the survey's count;
and 5 false ones: a picture's scraps (page 9), the two parts of the
bibliography, which start with "Part" and so are level 1 (390, 404), an
author's name in the bibliography (412) and the back cover (435). The notes' title (page 330, its head line, 14 pt against notes of 9,
flush left, in capitals) was not found: section 12's reach back, which
went up to a centred line, took it into the endnote section as a note
without a marker. As written, it is a heading line by both branches,
level 1, and the reach back stops at it; the `whole_book` test asserts
it. Turney's back matter titles are found:
Acknowledgements, Introduction, Notes, Bibliography, Illustration
Credits, Index. The survey's own prototype of the tall branch alone
took on Turney's pages 11 to 251 every chapter label, title and section
heading and no line of text but those of two newspaper front pages
reproduced as illustrations (174, 175) and a caption (170).

Three conditions were set on the way, each for a case measured. The
4 pt: Haynes' labels lie 2.9 pt left to 2.3 pt right of their region's
commonest left edge (page 117: 2.9), and its bibliography's title 3.4
pt. The
flush-left line is measured against the body column when its region
has fewer than 5 lines, as centring is: measured against its own
region's box, a title that is a region of one line is never short of
its own right edge, and Haynes' Index was missed. And a line whose top
is a head line that section 3 left in the text in the band where
section 3 looks for running heads (at most 2 pitches below the median
top of the book's head lines, or above it) is not flush left unless it starts with a
chapter label word: Mariéjol's running heads, too garbled for section
3 to find alike ("CATHI IlDICIS"), are set flush left on even pages and
became 13 false headings without it. The condition names the head line,
not any line in that band, because Haynes' first body line under a
removed running head lies at a median top of 65.2 pt, inside the band
(63.6 pt), and a section heading that opens a page would be lost; the
prototype excluded every line in the band, so it may have missed such
headings.

### Where it fails

- **Missed**: Stubbs' half-title "THE EARLY PLANTAGENETS." (page 18),
  whose second line runs nearly the full width; Domesday's "INDEX."
  (page 546), where the index columns make the page's column too narrow
  on one side for the title to be centred.
- **False**: Domesday's titles of four tables set in capitals
  ("ARMINGFORD HUNDRED.", pages 28, 42, 156, 470), and its printer's
  imprint (553). Kadesh's translation of a row of hieroglyphs on page
  39, with the text layer only (under `ocr = "redo"` the rule for a
  line below a line Tesseract read poorly keeps it out, above), and a
  garbled map label (29). Gierke's "Macrocosm and Microcosm." at the top
  of page 92 (excerpt page 6), a running head that section 3 does not
  remove, taken by the gap branch.
- **Levels**: Stubbs' "INDEX." (312) is level 2, because the guide words
  stand above it; Gierke's ten numbered sections ("I. The Evolution of
  Political Theory.") are level 2 under the book's title on page 86,
  where a reader would want level 1.
- **Tall lines that are text** (this revision): the tables' titles of
  Domesday (425 to 428) are taken, and so are the lines of the
  publisher's lists after Stubbs' text, which its config excludes.
  Domesday's pages 136 and 419, whose ordinary text stood tall against
  their page's median, are kept out by the limit of 6 tall lines a page
  (above).
- **Title pages** give a few headings (Domesday's "THREE ESSAYS…",
  Mariéjol's "A LA MÊME LIBRAIRIE"): the owner excludes such pages, or
  names them in `contents_pages`, when they matter.

## 15. Chapter summaries

Stubbs prints under 12 of its chapter headings a **chapter summary**, the
list of the chapter's topics separated by dashes ("Terms of Henry's
accession — His character — His early reforms…"), in smaller type, with
a hanging indent: the first line at the column's left edge, the next
ones about 9 pt in. It is a block of kind `chapter_summary` (owner, 15
November 2026): not a quote, which it resembles on the page, nor a
paragraph. In the first plan, section 6's rule 1 cut it where a
continuation line is indented after a short line, and its last lines
ran into the chapter's first paragraph, whose first line is not
indented.

**The rule.** The lines right after a heading block, in the body stream
of the heading's page, are a chapter summary when:

1. the first is at the left edge (indented less than 5 pt);
2. the second is indented at least 5 pt;
3. the summary is the first line and every line after it that is
   indented at least 5 pt, up to the first that is not;
4. its text holds at least 2 dashes ("—", "–", or " - ").

Rule 4 keeps out the two lines beside a drop capital or a two-line
initial (Haskins page 163, Domesday 12, Mariéjol 105, 182, 222, 299),
which pass rules 1 to 3. The summary is one block; the line after it
starts a block. The hanging indent only says where the summary ends; its
text is its lines joined, as any block's.

**Measured.** Stubbs prints 12 summaries; the reference text makes 11
of them quotes (which one it does not was not looked at). The rule
finds 10 of the 12, each whole and nothing more (pages 18, 51, 79, 106, 131, 157, 182, 233, 259, 284), and
none elsewhere in the six books' body ranges; in the front matter it
takes 2 lines of a publisher's list on Mariéjol's page 7. It misses
pages 28 and 210, where the OCR read the small type out of order ("Ste
phen — Bishops — Matilda" above "Accession of — The Anarchy…"), so the
second line is not indented: there the summary stays as in the first
plan.

## 16. Quotes and verse

A **quote** is a passage of prose quoted from another text; **verse** is
the lines of a poem, quoted or not. Both are body blocks of their own
kind, `quote` and `verse`. A verse block keeps its printed lines: its
text has a line feed between them (owner, 15 November 2026; architecture
§7), and a hyphen join at a line end makes the two lines one. These
rules change the kind of a block that the paragraph rules of section 6
made, except rule 4, which also decides where a verse block starts and
ends.

The height ratio, the character density and a wide line are defined in
section 1.

**What the books show.** The reference texts have 29 quotes in Haskins (8
of them its "Bibliographical note" sections), 56 in Stubbs (11 chapter
summaries, 2 on a title page, 43 in the publisher's lists), 31 in
Domesday and 9 in Mariéjol, all 9 verse. Haskins and Domesday set quotes
in smaller type across the column, Domesday often inset by about 17 pt
too; Mariéjol sets verse inset by 51 to 85 pt. Per line, every measure
overlaps; per block, two of them separate the kinds well:

| book | quote blocks | their median height ratio, 10th–90th percentile | their median density, 10th–90th | paragraph blocks | height ratio | density |
|---|---|---|---|---|---|---|
| Haskins | 25 | 0.78–0.94 | 1.04–1.26 | 203 | 0.99–1.02 | 0.97–1.02 |
| Stubbs | 51 | 0.87–0.97 | 1.09–1.18 | 398 | 0.99–1.04 | 0.96–1.02 |
| Domesday | 21 | 0.90–0.90 | 1.11–1.22 | 656 | 1.00–1.00 | 0.97–1.03 |
| Mariéjol | 3 | 1.00 | 1.01 | 1,042 | 1.00–1.00 | 0.96–1.04 |

(Blocks of the reference text with at least 2 wide lines, whole books.)
Height alone is not enough: Domesday has whole pages whose OCR lines are
9 pt high (page 139), so 40 of its 656 paragraph blocks have a median
height ratio of 0.95 or less; with the density as well, 1 has.

### The rules

They run after the notes and the index entries (section 2), on the body
blocks that are still paragraphs:

A body block whose first word has the book's marker form (section 1)
is never made a quote by these rules: it is a note that section 11 did
not take (Mariéjol's page 210), and stays a paragraph; such a block
never runs on into the next page's body (section 6 is not applied to
it), and the paragraph the next page starts is a block of its own,
unless it is a **numbered paragraph** (below).
Inside the endnote section (section 12) such a block does run on into
the next page, as any paragraph does: there every note starts with digits, and one that runs over a
page break is one paragraph. Gierke's endnotes start with digits ("13.")
and its marker form is digits since its introduction's notes are band
regions (section 1); with the rule applied inside the section, 79 of
its 299 endnotes were cut at a page break in mid-sentence (measured on
19 November 2026).
Measured on 16 November 2026 on the first plan's blocks of Domesday's
and Mariéjol's body ranges, against the reference text: of the quotes
rules 1 to 3 make there, the exclusion takes 28 of Domesday's 30 notes
and 35 of Mariéjol's 40 (with 3 and 15 more blocks the reference text
has as neither notes nor quotes, tables and garble), and no real quote
(Domesday's "(i) A Somersetshire manor…" are bracketed, against its
digits). False note-quotes remain: 2 in Domesday, 5 in Mariéjol. A
rule here changes a block's kind and no word, so it needs no record.

**A numbered paragraph runs on.** Such a block, led by a word of the
book's marker form, runs on into the next page as any paragraph does
(section 6) when both of these hold at the page break:

1. its lines so far are set in the body's type: their height ratio
   (section 1), the median height of all their words over the body word
   height, is above 0.95, the limit section 11 sets for a note's lines;
2. the last word of its page's last line ends no sentence: it does not
   end with ".", "?", "!" or ":", with closing quotation marks or
   brackets and 1 to 3 digits allowed after them, as for "A short last
   line at a page break" (section 6).

Kadesh (`battleofkadeshst00breauoft`) numbers its paragraphs, "1. Of
the three the most valuable is the Poem…" on page 11 and "3. The
RELIEFs furnish…" on page 12, and its marker form is digits, so before
this rule each was cut at the foot of its page in mid-sentence
("…exhaustively collated with the" / "original of the Sallier
Papyrus…"; "…by the artists of Ramses II.: Abydos, the" / "Ramesseum
(twice)…"). Since markdown writes a note after the last block whose
first page is the note's page or an earlier one (section 6, "Order"),
the page's unlinked notes, which are band blocks, came between the two
halves; once the paragraph is joined they follow it, page 11's notes
and then page 12's after the paragraph that starts on page 11. The cut
came from this rule, not from where the notes are placed: a paragraph
that does not start with a marker already ran on over the notes of its
page, so no rule of the notes' order changes.

Measured on 19 November 2026 on the `lines.json` of the seven books
run by the plan ocr-redo (`runs/ocr-redo/`): the blocks led by a
marker that the rule above stopped at a page break, outside the
endnote section, were 6 in Kadesh, 9 in Domesday, 3 in Gierke and none
in Stubbs, Haskins, Haynes or Turney (named below by their page). Their
height ratio is 0.58 to 0.91 for the notes left in the body (Kadesh's
page 36, "87So Abu Simbel…"; Domesday's 528) and the tables and contents lines (Domesday's 156, 158,
425 and 479, Gierke's 61 and 62), 1.00 for the paragraphs. Of the
paragraphs, the two conditions let run on Kadesh's 11 and 12 and
Domesday's 467 (a paragraph the OCR starts with "295", a number of the
table above it, "…No doubt, the" / "medieval sheep…"), and Gierke's 56,
a line of the analytical summary that the contents rules (section 30)
already joined, so that its output does not change; they keep cut those
that end a sentence: Kadesh's 20 ("as follows:", before rows of
hieroglyphs), 31, Domesday's 43 (a table) and 473, a line of two notes
set at the body's height ("1 D. B. i. 351. 2 D. B. i. 77.") whose next
page starts in lower case. Condition 1 alone would join that note of
Domesday's 473 into the body; condition 2 alone would join the tables
of Domesday's 156, 158, 425 and 479 and Kadesh's page number "121" of
page 60 with the next page's first line.

The paragraphs that end without a sentence's end right before an
unlinked note in `book.md` were, by book, before and after the rule:
Kadesh 7 and 5, Domesday 5 and 4, Stubbs 1 and 1, Haskins, Gierke,
Haynes and Turney 0 and 0. Each one left was looked at on the page
image: none is a paragraph cut at a page break. Kadesh's pages 38, 39 and 55
end a sentence followed by a reference the OCR read apart or as "™";
its 46 is the junk Tesseract reads in a row of hieroglyphs; its 60 is
the journal's page number "121" at the foot of page 60, left in the
body. Domesday's 92 ends "entries:" on the page, a word the OCR set
elsewhere in the line; its 479 and 489 are tables and its 497 a line cut
from its paragraph inside the page by a formula. Stubbs' is a line of
its list of maps (page 17).

**Known and left.** The count above sees only a paragraph right before
a note. On Domesday's page 473 the paragraph "…'There are 5 hides' says"
is followed by a line of two notes that layout leaves in the body at the
body's height ("1 D. B. i. 351. 2 D. B. i. 77.", a paragraph led by a
marker that ends a sentence, so it stays cut), and page 474 starts "a
Gloucestershire entry…": the sentence stays in two blocks with the
notes' line between. Counting the paragraphs followed by a block led by
a marker and then a page that starts in lower case finds that one in
Domesday (and its 158, a table, and 481, notes), none in Kadesh or
Gierke. And on a page whose OCR lines are all set small (Domesday's
page 139, above), a numbered paragraph fails condition 1 and stays cut;
none was found.

Verified by unit tests of `body_entries` with literal lines (a block
led by "1." in the body's type whose page ends "with the" is one
block over the page break; in type 0.9 of the body's, or ending "it.",
"follows:" or "it.”", it is two) and by excerpt tests: `kadesh_redo`'s
pages 3 and 4 (Kadesh's 11 and 12) give one paragraph "…collated with
the original of the Sallier Papyrus…" whose origins are pages 3 and 4,
and one "…Abydos, the Ramesseum (twice)…" on pages 4 and 5, and the
Markdown writes page 3's note "Called by de Rougé the Bulletin." after
the first; `domesday_run_on` (Domesday's pages 465 to 469) gives one
paragraph "…No doubt, the medieval sheep were wretched…" on its pages 2
and 3, and its note "2 See above, p. 76." after it in `book.md`.

1. **Smaller type.** A block with at least 2 wide lines, whose median
   height ratio over all its lines is at most 0.95 and whose median
   density over its wide lines is at least 1.04, is a quote.
2. **Inset smaller type.** A block of at least 2 lines, each starting at
   least 16 pt right of its region's left edge, whose median height
   ratio is at most 0.95, is a quote (Domesday's numbered items, "(vi) A
   Devonshire manor…", blocks of 2 lines with one wide line, which rule
   1 cannot judge).
3. **Short blocks between quotes.** A block with fewer than 2 wide lines
   and a median height ratio of at most 0.95 is a quote when the block
   before or after it is one.
4. **Verse** (per page, before the paragraphs are made: section 2, step
   2.3). A run of at least 2 consecutive body lines, each of at least 3
   words and inset at least 30 pt from both of the edges its centring is
   measured against (section 6, rule 2: its region's, or the page's body
   column for a line of a region of fewer than 5 lines), more
   than half of them starting within 12 pt of the run's median left
   side, is one `verse` block, whatever section 6 would make of it; a
   heading line is not part of a run, and a run does not start right
   after a line that ends with a hyphen, which section 6 never lets start
   a paragraph (Mariéjol page 212: two lines of garbled prose after "se
   sou-" made a false verse block; decided on 16 November 2026, in the
   review of work package 4). It costs one real verse block in the six
   books: Mariéjol page 243's two lines after "et pré-", a line the OCR
   garbled, whose word "dirent" it read earlier in the same line, so the
   two lines join the paragraph above. A verse block that is the last
   block of a page's body stream continues on the next page when that
   page's body stream starts with such a run. This was not measured,
   and no excerpt page shows it: Mariéjol's pages 51 and 52, once named
   for it, each hold their verse in the middle of the page (read in the
   text layer on 16 November 2026), so a unit test checks it.

### What they give

On the blocks of the first plan, in the body ranges (for quotes, up to
the index: Haskins 264, Stubbs 311, Domesday 545, Mariéjol 448):

| book | reference quote lines in quote or verse blocks | blocks made, mostly quote in the reference text | of the others: notes left in the body | tables | paragraphs | other |
|---|---|---|---|---|---|---|
| Haskins | 445 of 558 | 30 | 2 | 0 | 1 | 0 |
| Domesday | 235 of 286 | 66 | 32 | 11 | 2 | 1 |
| Mariéjol, rules 1 to 3 | 0 of 39 | 0 | 40 | 0 | 5 | 17 too garbled to align, most of them notes |
| Mariéjol, rule 4 | 38 of 39 | 8 runs | 1 | 0 | 3 runs | 1 garbled run |

The notes left in the body are the false quotes that the notes rules,
run first, are meant to take (section 11), and the rule above keeps out
those it misses; the counts above were taken without either, and how
many false quotes remain with them was not measured. Rule 4 also takes 2 runs of Haskins' verse (pages 209 and
234), 8 runs of Domesday's quotes (pages 136, 137, 291, 406, 407, 443,
506), which become verse blocks, and 9 runs of its tables (pages 47, 60,
66, 408, 434, 472). On Kadesh, which has no reference text, rule 1 takes
21 blocks, by their first words translations of the Egyptian texts
("Behold his majesty was in Zahi", page 27).

| threshold | value | measured |
|---|---|---|
| median height ratio | 0.95 | quote blocks' 90th percentile 0.94 to 0.97, paragraphs' 10th 0.99 to 1.00 |
| median density | 1.04 | on the reference text's blocks, 1.06 finds 18 of Haskins' 25 quote blocks against 23, and makes no fewer false ones |
| wide lines, rule 1 | 2 | 1 finds 4 more of Haskins' quote blocks and 10 more of Domesday's, and makes 3, 11 and 44 more false ones in Haskins, Domesday and Mariéjol, most of them notes left in the body |
| left inset, rule 2 | 16 pt | finds 14 more Domesday quote blocks and 7 false ones (tables); 8 or 12 pt find the same 14 with 28 more false |
| verse inset | 30 pt | 15 pt adds 3 Domesday table runs and 8 Mariéjol runs of broken lines, and no verse |

Left out after measuring: the line pitch (Haskins sets quotes closer,
0.68 to 0.86 pitches against 0.93 to 1.08, and a rule on it finds 491 of
its 558 quote lines, but Domesday's quotes keep the body's pitch and in
Stubbs it took 58 lines of running text); splitting a block where the
type changes (it finds 22 of Haskins' 36 boundaries between a quote and
the text and cuts 21 times inside text of one kind); height against each
page's median (it fails on Haskins' pages that are all quote).

### Where they fail

- **A quote inside a paragraph**: the paragraph goes on after the quote
  without an indent, so one block holds both, and its medians miss the
  thresholds (Haskins page 68: 21 quote lines among 36). Quotes set
  barely smaller (Haskins page 77: height ratio 0.96) and single lines
  of verse (Haskins 209, 221) are missed too.
- **Tables**: Domesday's tables in small type become quotes, and those
  inset on both sides verse. galley has no table kind; a table read as
  verse keeps its rows on lines of their own.
- **Broken lines**: lines the OCR cut short, inset on both sides, become
  a verse block unless the line before ends with a hyphen (Mariéjol's
  page 212, excerpt page 2, now stays prose; pages 121, 156 and 265
  still give such blocks).
- **Haskins' "Bibliographical note" sections**, set in small type at
  each chapter's end, would be quotes where layout reads them as body
  (pages 39, 40, 262 to 264) and notes without a marker where it reads
  them as a band (most of pages 65 to 67, 98, 129, 205, 231). They are
  paragraphs, by the rule below.

### Haskins' bibliographical notes

Each of Haskins' chapters ends with a section headed "BIBLIOGRAPHICAL
NOTE", a few paragraphs on the sources set in small type. They are
paragraphs of a section; their small type is how they look (owner, 16
November 2026; section 20). The blocks after a level-2 heading block
whose text is "BIBLIOGRAPHICAL NOTE", in any case, in the body or the
band of its page and of the pages after it, up to the next heading
block, are paragraphs, whatever their type:

- their band blocks, and the notes that step 2.5 took from the body on
  those pages, are not cut into notes: before the paragraphs are
  joined over page breaks (section 2, step 3.1), each becomes a body
  paragraph of its page, after the page's body blocks, in reading order,
  and is joined over a page break as any paragraph is;
- except, on the heading's own page, a band block whose first word has
  the book's marker form (section 1) and the band blocks after it: a
  footnote of the text above the heading, which stays a note (Haskins
  page 204, "^ Mont-Saint-Micheland Chartres, p. 4.", the note of
  "Adams,^"; decided on 16 November 2026, in the review of work
  package 4). No band block of a bibliographical note in Haskins starts
  with such a word;
- the quote rules (1 to 3 above) do not apply to them.

The rule names its words, so it takes nothing in another book. How many
band blocks of other books a general form of it ("band text after a
heading on its page") would take was not measured.

## 17. Index entries

A book's printed index is kept as text, one `index_entry` block per
entry (architecture §11); the index stage links its page numbers later.
An entry is its first line, at its column's left edge, and its
continuation lines, indented: a hanging indent. In the first plan the
index ran together: Haskins' eight pages gave 7 paragraphs of 8 to
1,049 words; Stubbs' columns, small type under a full-size row of guide
words, were a band, and so 101 notes; Domesday's whole index, 2,396
words, was part of the book's last paragraph.

**What the books print.**

| book | index pages | columns | continuation indent | sub-entries |
|---|---|---|---|---|
| Haskins | 266 to 273 (title "INDEX") | 2, about 130 pt wide | 7 to 11 pt, most at 9 (238 of 684 lines) | inline after ";" |
| Stubbs | 312 to 321 (title "INDEX.") | 2, small type, under full-size guide words | 6 to 10 pt, most at 8 | inline after ";" |
| Domesday | 546 to 552 (title "INDEX.") | 2 | 8 to 10 pt (39 of 832 lines) | none: each repeats its word ("Earl, Third penny of") |
| Gierke | 83 to 85 ("INDEX TO LIST OF AUTHORITIES") | 2 | none: one line per entry | none |
| Mariéjol, Kadesh | no index (Mariéjol's page 450 is its table of contents) | | | |

Between a column's edge (lines within 0 to 2 pt of it, up to 4 pt of
scan noise in Domesday) and the smallest indent (6 pt, 35 lines in
Stubbs), no line of the four indexes lies at 5 pt, so 5 pt is the
threshold. Each printed sub-entry is a block of its own, with its depth
(rule 5; owner, 16 November 2026), as the reference texts put each
inline sub-entry in an item of its own.

### The rules

1. **Index pages.** The index starts at a page whose title, the head line
   or the first line of its first body region, starts with the word
   "index", in any case ("INDEX.", "INDEX TO LIST OF AUTHORITIES"), or,
   in a French book, "table alphabétique". A page-number form at the
   start or end of the title is not part of it, so that a running head
   "252 INDEX" starts the index too: on Haskins, Stubbs, Domesday,
   Mariéjol and Gierke this adds no page (every such running head is on
   a page after the index's first; Kadesh was not checked), and
   it lets an excerpt that holds index pages without the first
   (`haskins_quotes_index`) start its index. It runs on over the
   following pages while each page that has words has two **index
   columns**: two regions that are neither margin regions nor the head
   line, each 0.3 to 0.65 of the width that all the page's regions span
   together, one wholly left of the other (its right side at or left of
   the other's left side). A row read across the columns can split each
   column into two regions or more (Stubbs' page 316 has four of that
   width): every such region that lies wholly left of another is part of
   the left column, and every one that lies wholly right of another part
   of the right; a page where one region is both has no index columns.
   The first page needs no columns. A page without words does not end
   it. Measured: this gives
   exactly the pages of the table above; Stubbs' 322 (advertisements in
   one column), Domesday's 553 (the printer's imprint) and Gierke's 86
   (the text) end them.
2. **The regions of an index page.** The head line is decided as on any
   page (section 3). A first region that lies wholly above every other
   and whose lines are only a page-number form and the word "index", in
   any case and either order, one line each, is the page's running head:
   layout makes it a region of two lines on Domesday's pages 547 ("Index."
   over "522") and 552 ("527" over "Index."), so section 3 finds no head
   line there. Its "index" line is removed as `running_head` and its
   number as `page_number`, with a head page number. The two index columns are index columns whether
   section 2 would make them body or band regions. A line of exactly two
   words of three capital letters each is the **guide words** (the first
   letters of the page's first and last entries, "BUR CON"), removed with
   the reason `guide_words` (architecture §8), as one removal. Layout
   reads the guide words as one line on 2 of Stubbs' 10 index pages (312
   and 321); on the other 8 it splits them into the first line of each
   column, so the first lines of the two columns, when each is one word
   of three capital letters and their tops are within 3 pt of each other
   (0.3 to 2.2 pt on those pages), are the guide words too. This second
   test is made on the columns once the margin regions and cut parts are
   in them; the first removes a line of two guide words anywhere on the
   page but the head line, before any region is cut. So 10 of
   Stubbs' 10 index pages have them, and no other page of the six books.
   A margin region goes into the column on its side of the gutter (below),
   by its middle, each of its lines on its own: a line that shares a row
   with a line of the column (its vertical centre within that line's top
   and bottom, layout §1, "Row") goes just before that line when it lies
   left of it and just after when it lies right of it; any other goes
   before the first line of the column whose top is below its own (at the
   column's end when none is). So a page number that overhangs the column
   ("509-515", "519", Domesday page 546) follows the line it ends, and
   each of Stubbs' letter initials read as a line "W" of its own (page
   321) goes before the line it starts. Placed as a whole by its top, a
   margin region of several lines moved Domesday's "519" from "Beer,
   Consumption of, 439," to "Bede", and gave Stubbs' 321 three entries
   for "Wallingford" and "Walter". A margin region that lies wholly above
   the top of every column region, beside the head line, is not read
   into a column and keeps its kind: Gierke's folio "lxxix" on page 84
   would otherwise end the entry "Isernia No. 108". A region that
   crosses the **gutter** (the middle between the left column's right
   edge and the right column's left edge) is cut there, each word going
   by its middle, when at least two thirds of its lines have no word over
   the gutter: its left part is read with the left column and its right
   part with the right, each part as a whole by its top, as a margin
   region is. This repairs the rows layout reads across both columns
   (below). Any other region keeps its kind: Gierke's footnote on page
   83 stays where section 2 puts it (1 of its 2 lines crosses the
   gutter).
3. **Entries.** The lines of the left column, then of the right, page
   after page, are one stream. A line starts an entry when its left side
   lies within 5 pt of its column's left edge; otherwise it continues the
   entry before it, also across a column or a page. The left edge is a
   straight line fitted, by least squares on the line's top, through the
   left sides of the lines that start within 3 pt of the column's
   **entry side**, then fitted again through those within 3 pt of the
   first fit, because scans are skewed: Gierke's page 84 drifts from 42
   to 47 pt over 41 lines. The entry side is the column's commonest left
   side (layout §1's commonest), unless at least 2 left sides lie more
   than 5 pt left of it: then it is the commonest of those. A column
   whose continuation lines outnumber its first lines has the indent as
   its commonest left side (the left columns of Stubbs' pages 314 and
   317, where John's and Edward I's entries run to 20 lines and more),
   and the commonest side alone made every continuation line an entry
   and every first line a continuation. Measured on 16 November 2026 with
   galley-eval, index paragraph boundaries at markdown, precision /
   recall, the commonest side alone against the entry side: Haskins
   0.903 / 0.698 against 0.992 / 0.723, Stubbs 0.475 / 0.314 against
   0.869 / 0.396, Domesday 0.990 / 0.986 both. A column of fewer than 5
   lines takes its smallest left side; a fit through lines whose tops are
   all one is the mean of their left sides, with no slope.
4. **Blocks.** Each entry is one `index_entry` block, or several by rule
   5, its lines joined as a paragraph's, hyphens joined by section 5 ("72-"
   "81;" gives "72-81;", "Vik-" "ing," gives "Viking,"). Its page numbers
   stay as printed, and it is not searched for note references (section
   11), as a caption is not (section 18): Stubbs' page 312 has a "^" in an
   entry, which matched a garbled region of the page made a note, in a
   book with no footnotes. Its origin has one box per page. The title is a
   heading (section 14); for its centring (section 14, rule 1), the lines
   of the index columns count as the page's body and band lines, which
   section 2 would have made them. The entries come among the body's
   blocks by page: after the blocks that start on the same page or
   earlier, before those that start on a later page. A paragraph does
   not run on into an index page or out of the last one: the first line
   of the body stream (the lines outside the index columns, such as the
   title) of each index page, and the first after the index, start a
   block.
5. **Sub-entries.** Haskins and Stubbs print an entry's sub-entries
   inline, each after a ";" ("Amari, M., 216, 248; quoted, 234."). An
   entry is cut after each of its words that ends with ";", the cut
   going between two words of a line when the ";" is inside it: the
   part up to the first such word is the entry, `level` 1, and each part
   after one a sub-entry, `level` 2; an entry without one is one block
   of `level` 1. Each part's origin has the boxes of its own words, one
   per page. No book of the six prints a sub-entry inside a sub-entry,
   so no part is deeper than 2; Domesday and Gierke print no ";" in an
   entry but a few that the OCR read into one. A cross-reference after
   a full stop ("See Odo, Turold, ...", which Haskins' reference text
   puts in an item of its own) is not cut off: nothing in print sets it
   apart from the page numbers before it.

   Measured on 16 November 2026 with galley-eval, index paragraph
   boundaries at markdown, precision / recall, with rules 1 to 5 as
   written here (the review's fixes, at e67a65c): Haskins 0.991 / 0.965
   (0.992 / 0.723 uncut), Stubbs 0.829 / 0.789 (0.869 / 0.396), Domesday
   0.993 / 0.986 (0.990 / 0.986 before the margin lines of rule 2 went
   in one by one). Stubbs' ";" are often read inside spaced letters or
   lost, and its own targets of section 9 are not met.

**Measured.** Each entry's first five letters were aligned in order with
those of the reference text's entries (not its sub-entries), with
`difflib`:

| book | reference entries | entries found | matched | precision | recall |
|---|---|---|---|---|---|
| Haskins | 470 | 476 | 461 | 0.968 | 0.981 |
| Stubbs | 443 | 432 | 413 | 0.956 | 0.932 |
| Domesday | 807 | 802 | 775 | 0.966 | 0.960 |

Without the cut at the gutter of rule 2, they were 0.935 / 0.917, 0.778 /
0.822 and 0.962 / 0.960. Most of Domesday's unmatched entries are first
words the OCR misread ("Hansa" for "Mansa"), not wrong boundaries.

**Where they fail.**

- **Rows read across both columns** (Haskins 267, 269, 271, 273: 23
  lines; Stubbs 312 to 321: 39 lines): layout cuts columns at a strip 6
  pt wide that no word of most rows crosses (layout §3, step 5); that
  strip starts at
  181.8 pt on Haskins' page 267, where the left column is justified to
  182.0, so the column's first rows cross it and are read across (layout
  §3, step 5). Rule 2 repairs this. Letting a word cross the strip by
  less than 1 pt in layout fixed 8 index pages but cut the footnote
  bands of Haskins 231, Domesday 251, 354 and 537, Mariéjol 173 and
  Kadesh 40 into two columns of prose, so layout is not changed.
- **Stubbs' letter initials**: the first entry of each letter starts with
  a capital two lines tall, which the OCR reads into the word
  ("T~\ANEGELD") or as a line "W" of its own, which becomes an entry:
  about 20 entries.
- **Spaced letters** in Stubbs' OCR ("t i o n w i t h B e c k e t"): the
  entries are found, their words are not; the correct stage's work.
- **Rows across the gutter that rule 2 does not cut**: on Stubbs' page
  312, two regions of spaced letters ("A CCURSI, Francesco, 221
  BaldwintheLeper, 104" and "B A D L E S M E R E , ...") have a word over
  the gutter on more than a third of their lines, so they keep their
  kind, a band, and come out as notes.

## 18. Plates

A plate is a page that is mostly a picture. analyze recognises it and
extract cuts its picture into `images/` (`docs/specs/plates.md`), so
lines.json gives the plate page a figure, and its words, read from the
text layer, as layout groups them. Those words are the plate's
**caption**, the text printed to name the picture ("THE MODERN MOUND OF
KADESH"), a running head, and **stray words**, what the OCR read in the
picture's lines and shading ("^U;L", "/•-„"). In the first plan they
ran into the paragraph around the plate (Kadesh's page 16 into the
paragraph of pages 15 to 18).

**The rules**, on a page that has a figure of kind `plate`; a text
page's in-page figures follow `docs/specs/figures.md` §5:

1. **Its running head.** Layout makes no head line on a page whose first
   row is its only row or is not set apart (layout §3, step 3), and the
   head that Kadesh prints on its plates stands 79 to 191 pt from the
   top, so section 3 does not find it. On a plate page, the topmost line
   is a running head when its letters are alike, by section 3's rule
   (at least 4 letters, 0.70), to the topmost line of another plate page
   or to a running head of the book, wherever it lies. Kadesh's
   "DECENNIAL PUBLICATIONS, V" on pages 34, 42, 48, 56 and 64 is then
   removed; page 68's garbled form is 0.68 alike and stays, as a
   caption line. A head line that section 3 makes a running head
   (Kadesh 19 and 24) is removed as on any page, with its page number
   and the marks above it. The topmost line is the line of the page,
   in any region, whose top is highest, the first in layout's order on
   a tie; the lines it is compared with are the topmost line, so
   found, of each other plate page, and the lines section 3 makes
   running heads, on every page of the book. Two topmost lines whose
   words differ only in numerals, roman or arabic ("PLATE II" and "PLATE
   III"), are not alike: a book that prints its plates' labels at their
   top keeps them as captions. When section 3 has
   already removed the topmost line, rule 1 removes nothing more. A
   line rule 1 removes is one `running_head` removal of the whole line:
   no page number is taken from it. Section 4 does not run on a plate
   page: a number at its foot is a line of the plate, which rule 2
   keeps or removes (Domesday 39's "17]").
2. **Caption and stray words.** The other lines are taken in rows, as
   rule 3 makes them, and every line of a row is a caption line when at
   least 2 of the row's words, or at least half of them, are **known
   words**. Taken line by line, a caption's word that the OCR garbled and
   that layout made a line of its own was lost: Kadesh 48's "LUXOR" (read
   "l.i v IK") beside "RELIEFS; THE", and the lithographer's credit of
   Kadesh 56 (orchestrator, 16 November 2026; reversible). A known word
   is by `wordlist.is_known_word`, which analyze uses too
   (`docs/specs/plates.md` §2): a word whose key (section 5: lower case,
   with what is not a letter, digit, hyphen or apostrophe stripped from
   both ends) has at least 2 letters, is made of letters, apostrophes and
   hyphens, and is in the lower-cased word list; or a number, digits with
   brackets or punctuation around them ("16", "17]"). The lines of every
   other row are removed as `plate_text`, one removal per line.
3. **The figure block.** The caption lines, from the top down in rows
   and each row from the left, are the text of one `figure` block, whose
   `figure` is the path of the image of the page's figure (a plate page
   has one, `docs/specs/plates.md` §3); a plate with no caption line, or
   with no text layer (Kadesh 17, 23, 35, 43, 57 and 69, Stubbs 9, 11,
   52 and 54), gives a figure block with no spans. Its lines are not in
   the body stream, so a paragraph runs on over the plate (section 6: a
   page with no body stream does not end the paragraph, and a hyphen
   before the plate joins the word after it). The figure block is side
   text of its page (section 6): it comes after the paragraph in which
   the body before it ends, and after the margin notes of earlier pages
   that stay there (section 13). The hyphens inside its caption are
   joined as in any block (section 5); its caption is not searched for
   note references, so it holds none. Its `origin` is one entry, the
   figure's box (the whole page, `docs/specs/plates.md` §3), so that a
   figure without a caption has a page and a place like any other block.
   A plate before any body block goes first. The rows are those layout
   makes of words (layout §1, "Row"), made of lines: by top, then left
   side, a line joins the row when its vertical centre lies within the
   top and bottom of the row's first line, so that Kadesh 64's
   "HTPOSTTLE, KJ", 0.7 pt higher than the line it ends, comes after it.
   Layout's order is not used for the caption because the stray words
   break a plate into regions that cut across it: on Domesday 39 it gave
   "Fir \.Bet^ueen pp. 16 — •'••'""' rAr A LAND OF VILLAGES On the
   border between Oxfordshire and Berks/tire. 17]", and from the top
   down "Fir •'••'""' rAr A LAND OF VILLAGES On the border between
   Oxfordshire and Berks/tire. \.Bet^ueen pp. 16 — 17]" (16 November
   2026).

**Measured** on 16 November 2026, with the rules as written here (at
e67a65c), on the 12 plates of the six books that have a text layer
(Kadesh 16, 19, 22, 24, 34, 42, 48, 56, 64, 68; Domesday 39 and 40):
section 3 removes the running heads and page numbers of Kadesh 19 and
24, and rule 1 the series head "DECENNIAL PUBLICATIONS, V" of Kadesh 34,
42, 48, 56 and 64; rule 2 removes 22 lines (77 words) as `plate_text`,
4 of Kadesh (16's two lines of strays, and 56's two lines "Lir*" and
"*t JC«,fflt>; rtC", the lithographer's credit "Lith. ... Kaeppelin et
C", which the OCR garbled beyond any known word) and 18 of Domesday 39
and 40, all strays but "Fir" (39), a known word in a row of strays. The
captions kept are Kadesh 22's "PLATE II", 48's "l.i v IK RELIEFS; THE"
(its "LUXOR" kept on its row), 56's panel labels "XXV I XXIV xxm XXXII
XXXI." (the plate prints XXV, XXIV, XXIII over its panels and XXXIII,
XXXII, XXXI under them; checked against the page image), 64's caption
and credit, 68's garbled series head with its "V" and its caption, and
Domesday's two captions with the binder's note "[Between pp. 16–17]",
read as "\.Bet^ueen pp. 16 —" and "17]", and one stray, "•'••'""' rAr",
half of whose words are known. The second research, line by line,
removed 26 lines (87 words), taking "LUXOR" and the "V" of 68 for
strays.

**Where they fail.** Captions in poor OCR are kept as read ("tlm border
between tiumersvt and Devon."), for the correct stage. Covers,
endpapers and card pockets that analyze takes for plates keep their
legible lines as captions (Mariéjol 458: "DO NOT REMOVE THE CARD FROM
THIS POCKET"); such pages belong in `exclude_pages`.

## 19. The change to markdown

markdown, as the first plan leaves it, writes paragraphs, margin notes
and unreferenced notes, and refuses every other kind, a note reference
and a referenced note, rather than write them wrongly (section 10).
The second plan changes it to write what structure now gives, as
architecture §9 says. How each kind looks, in `book.md` and in the
EPUB's style sheet, is the markdown and epub stages' to decide (owner,
15 November 2026); what structure fixes is only what each block is.
What markdown must do, and how it is checked:

- a `heading` block as a Pandoc heading of its level, with its id;
- a `quote`, `chapter_summary`, `index_entry` or `figure` block, and
  a `verse` block, each with its id and a class of its own kind, so that
  the style sheet can tell them apart; a `verse` block with a hard line
  break at each line feed of its text; an `index_entry` block's depth
  (its `level`, section 17, rule 5) as well, so that the style sheet
  sets a sub-entry in from its entry;
- a referenced footnote as a Pandoc footnote at its reference, with its
  margin notes inside it; an unreferenced footnote at the end of its
  chapter, under a heading "Notes" (section 36, since 19 November
  2026);
- the endnotes, referenced or not, where `notes` puts them (section 6,
  "Order"), as one list in the book's order, each a div with its id: a
  margin note printed beside its first block first (section 13, rule
  5), then its marker and text; each reference to an endnote as a link to it, marked
  as a note reference (`epub:type="noteref"`), which Pandoc 3.14 keeps
  and points into the right chapter file (architecture §9);
- the fidelity check at the markdown boundary (architecture §13) counts
  neither a reference span nor the marker of a referenced footnote; an
  endnote's marker is written and counted as a word.

## 20. Decided on 16 November 2026

The two points this spec left open were decided by the owner on 16
November 2026, each as recommended.

**1. A heading's chapter label is a field of its own.** `Block` has
`label: str | None`, the chapter label as printed ("CHAPTER III.",
"CHAPITRE Vni"), and the heading's spans hold the title only (section
14 says which line is the label). The fidelity check counts the label as
words of its block, as it counts a note's marker (architecture §13). It
says what the text is, the principle the owner set, and markdown can set
the number on a line of its own or leave it out of the table of
contents. The cost: an edit matches the text of the spans, so it cannot
correct a misread label until edits are allowed to name it; a damaged
label is rare (Mariéjol's "CHAPITRE Vni" was the one met in the second
research). The answer not taken was one text, the label and title
joined in the spans with nothing to mark where the label ends.

**2. Haskins' bibliographical notes are paragraphs.** The blocks after
a level-2 heading "BIBLIOGRAPHICAL NOTE", up to the next heading, are
paragraphs whatever their type (section 16, "Haskins' bibliographical
notes"), so that the same section does not come out as quotes in some
chapters and as unreferenced notes in others. The answer not taken was
to leave them as the quote and note rules make them.

## 21. The owner's two modern books

The plan owner-books makes galley read two books of the owner's, which
sit in `samples/` (ignored by git) and are copyrighted: no page of them
is cut into an excerpt or quoted in the repository, and the tests that
use them count what comes out (section 26). **Turney** is a 312-page
book of 1998 on science in popular culture, **Haynes** a 436-page book
of 1994 on the scientist in literature. Both PDFs are Internet Archive
scans of the printed books, each page a picture under an OCR text
layer, like the six public-domain books, but their type and layout are
modern. Unless said otherwise the numbers of this revision about them
come from a survey of 17 November 2026 (galley at 9715a93, both books
run to the EPUB with the configs below; its notes and scripts are kept
outside git and are not needed to read this spec), whose pages are page
indices. The numbers about the six public-domain books come from a
second survey the same day on the **clean-text build**, the run of
those books by galley at the same commit, in `runs/clean-text/build/`
(ignored by git).

What they show that the public-domain books did not:

- **The line height says the size of the type.** Every character of
  both text layers is in one font, the OCR's invisible one, so there is
  no bold or italic; but the OCR gives each line one height, rounded to
  the point (102 of Turney's 12,532 lines have words of two heights, 125
  of Haynes' 17,592). Turney's body lines are 9 pt (pitch 16.8 pt), its
  running heads and page numbers 10, section headings 11 to 14, chapter
  titles 20 to 23.5, notes 8. Haynes' body lines are 10 (pitch 14.4;
  some whole pages at 11), its chapter titles 12 to 14, chapter labels
  8, notes 9. The six old books' word heights did not separate headings
  (section 14); these do, and section 14's tall line uses it.
- **Headings flush left.** No chapter title, label or section heading
  of either book is centred. A chapter opens on a new page with no
  running head: Turney's with a label of a spelled number ("Chapter
  One") indented 42 to 46 pt, its title 1.4 to 1.6 pitches below,
  flush left, 2.2 to 2.6 times the body's line height, on one or two
  lines; Haynes' with a label in small capitals ("CHAPTER ONE") at 0.8
  of the body's height, flush left, its title 2.6 to 2.9 pitches below,
  in capitals, on two or three lines. Section headings: Turney's
  indented 43 to 46 pt in larger type; Haynes' flush left, mixed case,
  2.2 to 2.4 pitches below the text above. The introduction and the
  back matter (acknowledgements, notes, bibliography, index) are titled
  like a chapter without a label.
- **Epigraphs** open most chapters, one or two (section 22).
- **The page number outside the column** (Turney): beside the running
  head on ordinary pages, at the foot under the label's indent on a
  chapter's first page (sections 3 and 4).
- **Notes at the back, grouped per chapter, numbered from 1 in each
  group** (section 12): Haynes "1." in one column, Turney a bare number
  hung in the margin of two columns. The references in the text are
  superscript digits that the OCR glues to the word before, at the
  word's own height (Turney page 40: letters and digit both 9.0 pt).
- **A left cut-in inset** (layout §3): the indented epigraphs and
  headings give Turney one of 44.3 pt and Haynes one of 30.0 pt, so
  layout takes both books for books with cut-in notes. Step 2b moves no
  word of Haynes. It would move the labels of Turney's contents page,
  10, set smaller beside titles that start at the inset, since the cut
  row's test by size (layout §3, step 2b), and does not only because
  Turney's config names that page in `contents_pages`; a book without
  `contents_pages` set for such a page has its contents labels taken as
  margin notes (layout §6). Laid out with and without the insets, every
  page of both gave the same regions on 17 November 2026, before the
  test by size. A trap for the next change to step 2b.

**Their configs**, as the survey ran them, with `ocr = "trust"` (no
re-reading):

| book | `exclude_pages` | `contents_pages` |
|---|---|---|
| Turney | 2, 3, 5, 9, 165, 168, 171, 306, 307, 308, 309 | 10 |
| Haynes | 0, 1, 3, 7, 11, 13, 329, 389, 431, 432, 434 | 8 |

**What galley gave, and where this revision answers it:**

| failure | Turney | Haynes | section |
|---|---|---|---|
| chapter headings found | 1 | 0 | 14 |
| chapter labels removed as running heads | 9 | 3 | 3 |
| running heads left in the text | 98 times in `book.md` | | 2, 3 |
| page numbers made margin notes | 289 | | 3 |
| page numbers at the foot left in the text | 15 | | 4 |
| notes linked | 0 of about 620 (notes and bibliography: four `quote` blocks) | 127 of 633, 120 to another chapter's note | 6, 12 |
| epigraphs | 13, run into the text | 21, run into the text | 22 |
| a paragraph run over a page with an epigraph alone | pages 12 to 14 | | 6 |

**What remains wrong after this plan**: the bibliographies come out as
quotes (section 28); an epigraph over a page break is missed (section
22); some false headings (section 14 and Open 4); tables cut into
paragraphs (section 6); words glued without a case change (section
24); and
Turney's links were not prototyped, so their count is a target, not a
measurement (section 26).

The chapter openings: Turney 26, 39, 56, 77, 104, 134, 148, 189, 217
and 229 (chapters One to Ten), the introduction 14, acknowledgements
11, notes 252 (to 277), bibliography 278, illustration credits 300,
index 301; its page offset is 13 before its plates (pages 164 to 179) and 29 after.
Haynes: introduction 14, chapters 1 to 16 at 22, 36, 48, 63, 79, 87,
105, 117, 141, 156, 175, 200, 224, 249, 281 and 308, the closing
chapter 326, acknowledgments 10, notes 330 (to 388), bibliography 390,
index 422; offset 13.

## 22. Epigraphs

An **epigraph** is a quotation set at the head of a chapter, before its
text, with its **source**: the line that names the author and often
the work or year. It is a block kind of its own, `epigraph` (owner, 17
November 2026), with its source as a separate part, `Block.source`
(section 7; **Open 1**). It is not a `quote`, which is a passage quoted
inside the text, nor the chapter's first paragraph, into which both
books' epigraphs ran: each line whose two insets happened to be within
10 pt became a paragraph of one line, short lines became verse, and
each source was joined to the text after it, because the text's first
line is not indented.

**What the books show.** Turney: 13 epigraphs, on pages 13 (the book's
own, alone on its page), 14, 26, 39, 56, 134, 148, 189, 217 (two) and
229 (three; the survey counted one there, and 11 in all). Every line of the quotation is indented 32 to 46 pt from the body
column's left edge (most 42 to 46, the indent of the chapter label),
ragged right, in the body's type; the source is a line of its own set
flush right: its right side no more than 3 pt left of the quotation's
rightmost right side (on page 217 it ends 12.7 pt right of it, and
page 229's second and third sources end 4.5 pt short of it), its
left side 100.3 to 244.6 pt right of the quotation's left side; page
56's source runs over four lines set flush right, the first two
starting only 12.5 and 49.2 pt right of the quotation's left side. Haynes:
21 epigraphs, on pages 22, 36, 48, 63, 79, 87, 105, 117, 141, 156
(two), 175 (two), 200, 224 (two), 249, 281 (two), 308 and 326, indented
26.6 to 31 pt, ragged right; the source starts with a dash, at the
quotation's indent, in smaller type: its line height 0.73 to 0.90 of
the quotation's, on all 21. Two epigraphs on a page are about 2 pitches
apart; after the last comes a gap, then a section heading (Turney,
indented as the epigraph but taller) or the text, flush left. Haynes
indents its paragraphs by 29 to 30 pt, as much as its epigraphs, so the
indent alone does not tell an epigraph from a paragraph's first line;
the place does, after a chapter's heading, and the source line. Eight
of Haynes' quotations are verse (pages 22, 48, 63, 79, 87, 117, 224
the second, 326), by the survey's reading; none of Turney's. (The
survey listed Turney's page 104 for an epigraph; it has none: its text
starts at the foot of the chapter's sink.)

**The rule**, per page, after the heading lines are found (section 2,
step 2.3). Measures are those of the page's body stream. The **body
column** here runs from the left side of the stream's leftmost line
with a letter or digit that is not a heading line to the right edge of
section 1's body column. (Section 1's left edge, the commonest left
side of a region's lines, is the epigraph's own indent on a chapter's
first page whose epigraph lines outnumber its text lines, Turney's
pages 56 and 229, whose epigraphs it missed; owner's decision, 18
November 2026.)

1. **Where.** On a page whose body stream holds a heading block of
   level 1, the lines right after that block (and after its chapter
   summary, if any) are looked at, up to the first line that ends the
   epigraphs (rule 4).
2. **An epigraph run** is the consecutive lines from there, none a
   heading line, passing over any line with no letter or digit, which
   is removed as a `stray_mark` (Turney's pages 14, 26 and 148 hold a
   speck "/" between the title and the epigraph, which would otherwise
   be the quotation's first line), each with its left side at least 20 pt right of the
   body column's left edge, that end at a source line (rule 3). The
   first line after a source line starts the next run when it lies
   within 3 pt of the left side of the run before, across.
3. **A source line** is a line of the run, not its first, that either
   - starts with a dash, "—", "–" or "-", alone or several, as a word
     of its own or at the start of its first word (Haynes' OCR reads
     one as "—-"), has a letter or digit after its dashes, and has a
     line height at most 0.92 of the median line height of the run's
     lines before it (Haynes: 0.73 to 0.90). A line of dashes alone has
     no letter or digit, so rule 2 passes over it as a stray mark and it
     is never a source line: it would leave a source of no word, and its
     dash's removal, `before` "—" and `after` "", is one the fidelity
     check refuses; or
   - lies at least 60 pt right of the leftmost left side of the run's
     lines before it, and its right side lies no more than 5 pt left
     of their rightmost right side (Turney: 100.3 to 244.6 pt right,
     and up to 4.5 pt short on page 229; a verse turnover line, the end
     of a long verse line set further in, lies 32 pt right in Haynes'
     page 87 and ends short).

   **A source over several lines** (owner's decision, 18 November
   2026). The lines after the source line that keep its shape are the
   source's too, up to the first that does not: after a dashed source
   line, a line in smaller type by the same 0.92, that starts with no
   dash and no more than 3 pt left of the source line; after a
   flush-right one, a line at least 60 pt right of the quotation's
   leftmost left side whose right side lies no more than 5 pt left of
   both the quotation's rightmost right side and the source line's.
   Before a flush-right source line, the last lines of the run are the
   source's first lines while each is set flush right (within 5 pt)
   under the run's lines before it and starts at least 10 pt right of
   their leftmost left side, leaving at least one line of quotation
   (Turney's page 56: 12.5 and 49.2 pt right, its quotation's lines all
   starting within 1 pt of each other). The source's lines end the run.
   The test against the source line's own right side keeps out Turney's
   back cover (page 311), whose blurbs the OCR cut into a region at the
   right of the page.
   The lines of the run before the source are the **quotation**.
4. **The end.** The epigraphs end at the first line, after a source
   line, that does not start a run: a line within 20 pt of the body
   column's left edge, a heading line, or the end of the page's body
   stream. Lines of a run that reach the end without a source line are
   no epigraph and stay as section 6 makes them; so a chapter that
   opens with an indented paragraph (Haynes' introduction) gets none.
5. **A page of its own.** A page with no heading line whose body stream
   is one run of at most 10 lines, counting only the lines with a letter
   or digit (owner's decision, 18 November 2026), of a quotation of at
   least 1 line and its source by rule 3, last, is an epigraph too (the bound keeps out a
   preface's last page signed at the right; Turney's has 6 lines), without rule 2's indent, which a page set
   in the quotation's own measure does not show (Turney page 13: the
   source starts 169 pt right of the quotation and ends with it). Not
   measured on the six public-domain books.

**The block.** Each epigraph is one `epigraph` block, after the
heading's block in `blocks`; the line after the last epigraph starts a
block. Its spans hold the quotation, its lines joined as a paragraph's
are, with hyphens joined (section 5), or, when the quotation is verse
(below), with a line feed between its lines, as a `verse` block's
text (architecture §7; owner, 17 November 2026: a verse epigraph keeps
its line breaks). Its `source` is the source lines' words, joined by
single spaces, without its leading dash. Its `origin` holds the
quotation's and the source's lines.

**The dash is look, not text** (owner, 17 November 2026): the source's
leading dash says, in print, "this is the source"; the kind says it in
blocks.json, and the markdown stage writes it back (section 25). It
is removed with a record: a `WordChange` of the new reason
`source_dash`, on the source's page, whose `before` is the source's
first word ("—Hobbes,") or the dash word and the word after it ("—",
"Hobbes,"), and whose `after` is the one word without its leading
dashes ("Hobbes,"). The fidelity check verifies it: `before` is one
word that starts with a dash, or two words whose first is dashes only,
and `after` is one word, not empty, the last word of `before` with every
dash at its start dropped; and,
as for `hyphen_lost`, the word of `after` is the first word of the
`source` of an epigraph with a part on the change's page, so that the
reason cannot take a dash off a word of the body (review of work
package 2 of the plan owner-books, 18 November 2026). A
dash anywhere else in the source ("1873—1881") stays. Turney's sources
have no dash, and no change.

**Verse.** A quotation is verse when it has at least 2 lines, every
line after its first starts with a capital letter, once quotation
marks, full stops, ellipses and spaces at its start are passed, or
lies at least 15 pt right of the quotation's leftmost left side (a
turnover line), and either every line ends at least 80 pt short of the
body column's right edge or one of them is a turnover line. A prose
quotation is ragged right in both books but its lines run on, so a line
after the first starts in lower case in most, and its lines (but the
last) end 0 to 67 pt short of the column's edge; verse lines start with
a capital, and Haynes' end 94 to 186 pt short, but for page 87's long
lines, which end 37 to 51 pt short with a turnover line among them.
Measured on 17 November 2026 on the survey's `lines.json` of the 32
epigraphs found by rules 1 to 4 (Turney's page 13 aside): it makes
verse of the 8 that the survey read as verse and of no other; without
the length test it also took two prose quotations whose second line
happens to start a sentence (Haynes 156, the second; Turney 217, the
second). A quotation of one line is prose: its line breaks are
nothing to keep.

**What the rule gives.** Run by galley's code (task 4.1 of the plan
owner-books) on every page of the eight books' `lines.json`, made by
the layout of 18 November 2026, after the heading lines and summaries
that structure finds: Haynes 21 epigraphs of 21, with their sources,
21 dashes and 8 verse, the survey's 8; Turney 13 of 13, page 13's by
rule 5, page 56's with its four source lines, none verse, none dashed;
the six public-domain books none, rule 5 included. With section 1's
body column and one-line sources within 3 pt, the rule had found 9 of
Turney's, missing pages 56 and 229. A page whose level-1 heading is
followed by indented lines ending at a dash line or a line set flush
right is the case to watch (a dedication, a motto), and the
`whole_book` tests count `epigraph` blocks there (section 26).

**Where it fails.** An epigraph that runs over a page break is not
found (none in the two books). An epigraph whose source is neither
dashed and smaller nor set flush right, or a source line the OCR set
level with the quotation's left, is missed and stays as before. A
heading line between a quotation and its source ends the run.

## 23. Spaced punctuation

Nineteenth-century printers set a space before ";", ":", "?" and "!",
and the OCR reads it: "subjection ;". In an English book the space is a
fault of the text as galley gives it (a reader sees a sign alone at a
line's start on the Kindle); in a French book it is the language's rule,
and the sign must not be cut from its word by the line breaks of the
EPUB. The owner decided on 17 November 2026: in a French book the space
becomes a no-break space; in any other book the sign is attached to the
word before it, as a recorded word change; a sign after a dash or a
quotation mark is left alone.

**The rule.** In every block, body and side text, after the joins over
page breaks (section 2, step 3.2) and before notes are cut and
references looked for, a word that starts with "?", ";", ":" or "!"
(the **spaced sign**, followed by nothing or by characters that are not
letters: ";", ";^", ";13", "?'", "?]") and follows another word of the same block, on the same line or
the line before, is changed when the word before it ends with a letter,
a digit or a closing bracket, ")" or "]":

- in a book whose config's `language` is `fr`, the space between the
  two words becomes a no-break space, U+00A0, in the block's text, and
  each word stays as it was ("(1) ;" and "hides4 ;" keep their
  reference word, linked as before): no
  word changes, since the fidelity check splits words on white space and
  Python's `str.split` takes U+00A0 for white space, and Pandoc keeps it
  inside the word it reads, which the check splits in the same way
  ("complète ;" is one Pandoc `Str` and two words; checked with Pandoc
  3.14 on 17 November 2026);
- in any other book, the two words become one, the sign attached: a
  `WordChange` of the new reason `punctuation_attached` on the page of
  the first word, `before` the two words and `after` the one, ("subjection",
  ";") to ("subjection;",). The fidelity check verifies that `before`
  is two words, the second starting with one of the four signs, and
  that `after` is the two joined with nothing between.

After a dash or a quotation mark ("—", "'", "’", '"', "”", "»") the
sign stays apart, with its ordinary space, in both cases (owner, 17
November 2026). Between the two lines of a `verse` block or of a
verse epigraph, where a line feed separates them, nothing changes. A
sign that starts a block stays as it is.

**After a note reference.** A sign after a word that holds a reference,
"hides4 ;" (Domesday 27 times, Mariéjol 9, Gierke 2), is attached to
that word before references are looked for, "hides4;", which section
11 then splits into "hides", the reference "4" and ";": the sign
follows the reference, as print sets it. A sign that holds a reference
itself, glued after it (";13", a candidate of section 11's glued form),
is attached only when the word it makes is still a candidate: "land"
";13" give "land;13", but Kadesh's "(Nos. 1, 2, 13, 14) ;13" (page 10)
stays apart, since "14);13" is no candidate and its note would lose its
link (3 such signs in the six public-domain books, 18 November 2026:
that one and Domesday's "£21 ;...2" and "1500 ?]9"). Its two changes are recorded,
`punctuation_attached` then `note_marker`; the fidelity check, which
undoes every change, balances. A sign glued to a reference, "subjection
;^" (Haskins page 28, a sign "^" for a superscript 1), becomes
"subjection;^", a candidate of section 11's sign form, which a spaced
";^" was not; the note is then linked. In a French book the reference
reference "(1)" stays a word of its own, a no-break space after it.

**Measured** by the public-domain survey on the clean-text build (17
November 2026), words of blocks and notes that start with one of the
signs and follow a word:

| book | spaced signs | of which ; / : / ? / ! | signs already attached | share spaced | left alone (after a dash or a quotation mark) | changed by the rule |
|---|---|---|---|---|---|---|
| Haskins | 91 | 74 / 11 / 0 / 6 | 501 | 15% | under 10 | 89 |
| Stubbs | 1,039 | 973 / 53 / 12 / 1 | 589 | 64% | under 10 | 1,007 |
| Domesday | 2,181 | 1,254 / 747 / 177 / 3 | 1,095 | 67% | 75 | 2,112 |
| Gierke | 951 | 523 / 405 / 16 / 7 | 939 | 50% | 31 | 885 |
| Kadesh | 103 | 67 / 31 / 3 / 2 | 221 | 32% | under 10 | 97 |
| Mariéjol (French: no-break space) | 1,349 | 549 / 599 / 43 / 158 | 847 | 61% | 251 | 1,036 |

The last column is of the rule as it stands, measured by `make_blocks`
on the six books' `lines.json` on 18 November 2026: the signs attached,
and in Mariéjol the no-break spaces. A sign followed by letters is not a
spaced sign (review of work package 5, 18 November 2026): it is a speck
the OCR read before a word, and attaching it glued two printed words
into one with no sign printed between them, Gierke page 29's
"universitas ;is," into "universitas;is,", 6 times in the English books
(Gierke's "of ;y°ve'" and "imperatorem ;...a", Stubbs' "on ?uer",
"the !Ja?nSt" and "m ;s."); in Mariéjol it put 113 of 1,149 no-break
spaces before such a word ("landgrave !e").

The owner's two books were not counted. An edit written against a
block's text before this change no longer applies, since its checksum
changes (architecture §10); none exists for these books.

## 24. Words glued at a case change

The text layer of the old books sometimes gives two words as one with a
capital inside, "theAvre" (Haskins page 22, printed "the Avre"): the
OCR spread its characters evenly over the word's box, so the boxes
touch and extract's rule for glued words, which cuts at a gap
(`docs/specs/extract.md` §4), has nothing to measure. A word of a block
is split in two at a lower-to-upper case change when all of these hold:

- the word, with punctuation stripped from both ends, is a run of
  lower-case letters followed by a capital and at least 3 lower-case
  letters, and nothing else ("theAvre", "ofWilliam");
- the left part has at least 2 letters, is a known word (the word
  list, `wordlist.is_known_word`) and its key is among the book's
  common inner words (`BookSurvey.common_inner_words`, section 5: printed
  after a line's first word more than 8 times);
- the capital is not "U" or "H", the letters the OCR gives for "li"
  (below);
- the right part's key (section 5) is among the book's own words, the
  keys of `lines.json` of section 5: the book prints it whole elsewhere;
- the whole word's key is not a known word.

The split is a `WordChange` of the new reason `case_split`, on the
word's page: ("ofWilliam,",) to ("of", "William,"), the punctuation
going with its side. The fidelity check verifies that `before` is one
word and `after` two whose concatenation is it, the second starting
with a capital. It is made in each block once hyphens are joined
(section 2, step 2.4, and the paragraph after the steps), so that a
word joined at a line end or a page break is split too, and before
references are looked for.

The left part must be in lower case: in the owner's modern books every
glued word with a capital left part is a name ("McGibbon", "LaFollette",
"LeGuin": 6 in Turney, 30 in Haynes), and in the old ones half are
(Haskins' "LePrevost", Gierke's "MagnaCarta" are two words, Domesday's
"MacDurnan" one). The book's own words are asked of the right part
because the OCR misreads "li" as "U" or "H": Haskins' "deUver",
"miUenaire" and "estabHshed", whose right parts the book never prints,
are words the OCR damaged, and a split would leave two wrong words for
one. The word list alone does not stop them: Tesseract's lists hold
"ji", "po", "catho" and "tt", so the first rule split Domesday's
"jiEthelbert" and Mariéjol's "poUtique" (8 times) into "po" "Utique".
The book's common inner words and the capital (orchestrator, 17
November 2026) took Mariéjol from 48 splits to 12 and Domesday from 4
to 3, measured on the clean-text build's `lines.json`; the English
books lost no split that looked right. Measured on 17 November 2026 on the words of the clean-text
build's `blocks.json` and the survey's runs (the prototype took the
book's words from the blocks, an approximation of section 5's, which
the plan measures again):

| book | split | examples | kept, glued |
|---|---|---|---|
| Haskins | 2 | "theAvre", "theAngevin" | 7 misreadings ("deUver") |
| Stubbs | 9 | "ofWilliam", "ofJohn", "ofLancaster", "heBarons" (the "t" of "the" lost) | 1 |
| Domesday | 1 | "ofChatteris" | 11 |
| Kadesh, Gierke | 0 | | 12, 6 ("inSyrienund", "outsideVhe") |
| Mariéjol | 8 | "desMédicis", "deChambord", "laLigue" | the rest |
| Turney | 0 | | 0 |
| Haynes | 3 | names after "of" | 2 |

The Haskins, Stubbs, Domesday and Mariéjol rows are of the rule as it
now stands, on `lines.json`; Turney's and Haynes' are of the first rule
and were not measured again. Stubbs' row said 10 before the review of work
package 5 (18 November 2026): `make_blocks` on this branch's
`lines.json` gives 9, the same 9 with 2 letters after the capital as
with 3, so the 3-letter rule below dropped none of Stubbs' splits; the
10 was counted on the clean-text build's lines, which the reading
order and re-reading have changed since, and its tenth word was not
recorded. The capital must be followed by 3
lower-case letters, not 2 (task 5.2 of the plan owner-books, 18
November 2026): with 2, Domesday's "forSon" and "forSan" were split,
which page 339 prints "forðon" and "forðan", one Old English word each
whose "ð" the OCR read as "S", and 4 of Mariéjol's 12 splits looked
wrong ("•oaSat", "ttOat", "ftOom)", "tuAiu"); no split that the 3
letters drop looked right on the six public-domain books. Of Mariéjol's
8, 2 still look wrong from the words alone, misreadings split into
misreadings: "paJais" and "fiMent". They are an accepted cost: the scan
is not worth more effort (owner, on unreadable scans), and the fidelity
check holds, since a split loses no letter.

A lower-case pair glued without a case change ("ofone") is not found:
a test on the word list alone splits 860 to 6,600 words per book
wrongly (public-domain survey), because Tesseract's list lacks too many
words. Looking at the ink in the page's render inside the word's box
would find both; it needs the render in structure or extract and is
not part of this plan.

## 25. The change to markdown

markdown writes what this revision adds; how it looks is decided here
and in the epub stage's style sheet, `src/galley/epub/style.css`,
never by structure (architecture §3).

- **An epigraph** is a fenced div with its block id and the class
  `epigraph`, holding the quotation as a paragraph, with a hard line
  break at each line feed of a verse quotation, as a `verse` block's
  is, and then a fenced div with the class `epigraph-source` holding an
  em dash, "—", a no-break space, U+00A0, and the `source`. The dash is
  written as text, not drawn by the style sheet's generated content
  (`::before`), because generated content was not tried on a Kindle and
  the source must not depend on it (Open 3, settled); the no-break space
  keeps the dash on the source's line. The style sheet sets the
  epigraph in from both sides and the source on a line of its own
  aligned right.
- **A note group's heading** is a fenced div with the class
  `note-group`, written just before the div of the note whose `group`
  it is, in the list of endnotes. It is not a Pandoc heading, so it is
  not in the EPUB's table of contents (**Open 2**).
- **A no-break space** is written as the character, which Pandoc keeps
  (section 23).

The fidelity check at the markdown boundary (architecture §13) counts
the words of an `epigraph-source` div as words of its epigraph's block,
as it counts a heading's label, but for its first word, the dash
markdown wrote, which it takes out before comparing (blocks.json does
not hold it: the `source_dash` change removed it); and the words of a
`note-group` div as words of the note after it. Any other div inside an
epigraph's div is an element galley's Markdown does not make, and an
error.

## 26. How the owner-books changes are verified

**Unit tests**, on `LinesFile` values and words written in the test:

- head line: a head "THE BOOK" at top 36 pt with a region "224" of one
  line 14 pt left of it at the same top is one head line, the page
  number "224" and a running head; with "224" 5 pt lower, or 6
  characters long, the head stays in the text as now;
- chapter label: three pages whose first region is "CHAPTER ONE",
  "CHAPTER TWO", "CHAPTER THREE" within 2 pitches of the median head
  top keep each line in the text, and the heading has it as `label`;
- foot number: a page whose head page numbers around it give an offset
  of 29 and whose lowest line is "160" at the column's left, on page
  189, is a `page_number` at the foot; "161" there stays;
- hanging number: a region of 12 lines whose text edge is at 251 pt
  and whose lines "8 Compare…", "9 Weart…" start at 234 pt starts a
  paragraph at each; a number at 248 pt does not; a region of 2 such
  lines and 2 others does not;
- page break: a page whose last line ends 30 pt short with "it." and a
  next page whose first line is flush left starts a paragraph; the same
  with "it," or 15 pt short continues it; a verse block that runs on is
  kept;
- headings: a flush-left line in capitals with a 2.4-pitch gap above is
  a heading line; a flush-left line in lower case set apart by 2.0
  pitches and ending with ":" is not; a line 2.4 times the page's
  median height, flush left, 1.5 pitches below a label "Chapter One"
  indented 45 pt and 1.3 times as tall, gives one level-1 heading with
  the label; a tall line 0.8 pitch below the line before is no heading;
  a flush-left line within 2 pitches of the median head top is no
  heading unless it starts with "CHAPTER";
- note groups: an endnote section of two groups of 9 notes, "1" to "9"
  twice, each after a two-line group heading 1.8 pitches below the note
  before, and two level-1 headings in the body whose titles match the
  group headings, with glued references "word1." to "word9." under
  each, links each note to the reference of its own chapter; the
  group's first note has the heading as `group`; Turney's form, bare
  numbers hung 17 pt, gives the same;
- epigraphs: under a level-1 heading, three lines indented 30 pt and a
  line "—Hobbes" at 0.8 of their height give one `epigraph` whose
  `source` is "Hobbes" and a `source_dash` change; the same with a
  source line flush right 150 pt in and no dash gives one with no
  change; two such epigraphs give two blocks; the same lines with no
  source line stay paragraphs; a page holding only such a run is an
  epigraph; the verse rule on 5 lines starting with capitals and ending
  100 pt short gives line feeds, on 3 lines ending 30 pt short none;
- spaced signs: ("subjection", ";") gives ("subjection;",) with
  `punctuation_attached` in English and a no-break space in French;
  ("—", ";") and ("'", "?") stay; "hides4" ";" gives the reference "4"
  linked and the text "hides", "4", ";"; "subjection" ";^" gives a
  linked sign;
- case split: "theAvre" with "avre" among the book's words gives
  ("the", "Avre"); without it, or "LeGuin", or "deUver" (no "uver"),
  stays;
- the fidelity check passes on all of these and fails on a
  `source_dash` change that drops a letter, a `punctuation_attached`
  change whose second word is not a sign, a `case_split` change whose
  parts do not make the word, and a block not an epigraph that has a
  `source`.

**Excerpt tests.** The reference pages of section 9 keep their
expected output except where these rules change it: the plan lists
each change and the owner checks it by eye. New excerpts, each a case
the committed excerpts do not hold, are added to
`scripts/fetch_samples.py`, every page with a text layer; the owner
checks each expected output against the page image:

| excerpt | page indices | what it checks |
|---|---|---|
| `haskins_heads_notes` (Haskins, `normansineuropea00hask`) | 22, 23, 28, 29, 30, 55, 66, 195, 235 | "theAvre" split (22); running heads whose next row has a tall glyph (23, 30, 66, 235; layout §3, step 3) removed with their page numbers, and page 23's speck above as a `stray_mark`; footnotes left in the body found as a band without the gap (28, 55, 195; layout §3, step 4), and page 28's "subjection ;^" linked to its note |
| `stubbs_heads` (Stubbs, `earlyplantagenet01stub`) | 20, 100, 152, 158, 186, 202, 210 | running heads whose date the skew sets a row lower, removed with their page numbers (layout §3, step 3); spaced ";" attached |
| `gierke_intro_heads` (Gierke, `politicaltheorie00gieruoft`) | 68 to 79 | roman page numbers beside the running head (section 3), removed with it; the list of authorities' section headings, taken by the tall branch |
| `domesday_rereads` (Domesday, `domesdaybook00maituoft`) | 26, 36, 97, 136, 138, 139, 150, 160 | a word of a margin note read once, not twice, by re-reading (`docs/specs/reocr.md` §4: "tem," on 26, and 36, 139, 150, 160); footnotes left in the body found as a band (97, 138); page 136's two text lines taken for headings (a known failure) |

Each excerpt's own survey must measure what the whole book's does (the
trap of section 9 with `domesday_headings_quotes`); the plan checks the
body measures and the marker form of each when it is cut, and adds
body pages of the same book if they differ.

**Whole-book tests**, marked `whole_book`, on the owner's two books:
they find each PDF in `samples/` by a pattern of its file name given in
the test ("*Turney*.pdf", "*Haynes*.pdf"), run the pipeline to
`blocks.json` with the configs of section 21, and skip with the reason
when the PDF is absent. They assert counts only, never text:

| count | Turney | Haynes |
|---|---|---|
| level-1 headings whose label starts with "chapter", any case | 10 | 16 |
| level-1 headings without a label, among them the introduction, notes, bibliography and index | at least 5 | at least 5 |
| `running_head` removals whose first word is a chapter label word | 0 | 0 |
| `page_number` removals at the foot | at least 14 of the 15 opening pages | (none printed) |
| `margin_note` blocks that are a number of 1 to 3 digits | 0 | 0 |
| endnotes, and note groups (notes with a `group`) | at least 615, 11 | at least 685, 18 |
| endnotes linked | at least 450 | at least 550 |
| links from a reference to a note of another group's chapter | 0 | 0 |
| endnotes without a link (section 12, "The candidates of endnotes" and "The gap between linked neighbours") | at most 30 | at most 7 |
| endnotes of a group whose marker's number is not the one before plus one (section 12, "Endnotes run into the note before") | at most 2 | at most 5 |
| links whose digits are not their note's marker's number, nor the start or end of it, nor one confused digit from it (section 11, "Matching"); a marker that reads no number and a sign are not counted | 0 | 0 |
| links of a note group whose notes' numbers, in the reading order of the links, do not rise | 0 | 0 |
| `epigraph` blocks, and those with line feeds | 13, 0 | 21, 8 |
| `source_dash` changes | 0 | 21 |

The targets are set below the survey's and the prototypes' counts:
Haynes' links from the prototype's 584, Turney's from its 620 notes and
about 555 references, not prototyped. The `whole_book` tests of the six
public-domain books add: no `running_head` removal starts with a chapter
label word; the running heads of Haskins' pages 23, 30, 66 and 235,
Stubbs' 20, 100, 152, 158, 186, 202 and 210 and Gierke's 69 to 79 are
removed; at most 2 `epigraph` blocks in each book (none is printed;
the margin is for a motto the rule takes); the fidelity check on every
book.

**Measured by `galley-eval run`** on the four evaluation books, before
and after, in the plan's work report: the reference headings in
`heading` blocks and the paragraph boundaries may not fall (section 9's
targets), and the notes whose reference is right not either; the
page-break cuts of section 6 and the new headings of section 14 are
checked against the reference texts there.

## 27. Open points

The owner decides these. The owner is away while the plan starts, so
the session that carries the plan out (its orchestrator) may settle
each as recommended; until one is settled, the implementer does what
its "meanwhile" says, and the owner can reverse it later at the cost
named. The orchestrator settled all four on 17 November 2026, each
noted under it; the plan `docs/plans/owner-books.md` builds them.

1. **How an epigraph's source and a note group's heading are stored.**
   (a) As written: `Block.source` on the `epigraph` block and
   `Note.group` on a group's first note, each a string counted by the
   fidelity check, as `label` and `marker` are; an edit cannot correct
   them, and the OCR damages some sources (2 of Haynes' 21 hold a
   misread name). (b) Two block kinds, `epigraph` and
   `epigraph_source`, the second always right after the first, and the
   group heading a block of a kind of its own among the endnotes, each
   editable; a reader of blocks.json must pair the source with its
   epigraph, and markdown must place a group's block among the notes,
   which `notes`' order by page (section 6) does not allow on a page
   where a group ends and the next begins. Recommended: (a), the
   precedent of `label`, which the owner chose on 16 November 2026 at
   the same cost. Meanwhile: (a). **Settled**: (a).
2. **Note group headings outside the table of contents.** (a) As
   written: a styled line before the group's first note, not in the
   EPUB's table of contents. (b) Level-2 headings under "Notes", one
   entry per chapter, which repeats each chapter's title in the table
   of contents, as the printed contents pages did before the owner
   named them in `contents_pages` (15 November 2026). Recommended: (a).
   Meanwhile: (a). **Settled**: (a).
3. **How the dash before a source is drawn.** (a) By the style sheet,
   with CSS generated content (`::before`), which was not tried on a
   Kindle; if the Kindle drops it, the source shows without a dash,
   still on its own line set right. (b) markdown writes "—" and a
   no-break space before the source as text, and the fidelity check at
   the markdown boundary takes that one word out. **Settled**: (b),
   because the text must not depend on generated content no Kindle has
   shown; section 25 is written so.

4. **Costs accepted on the public-domain books.** The rules for the
   owner's books also make, on the six old books: 34 false headings
   from the publisher's lists after Stubbs' text (pages 322 to 337) and
   4 lines of Domesday's text taken for headings (136, 419), each an
   entry in the EPUB's table of contents (section 14); 36 splits of
   Mariéjol's garbled words into other garbled words (section 24); and
   Turney's two roman foot numbers kept as notes (section 4). The
   publisher's lists can be put in Stubbs' `exclude_pages`; Mariéjol
   is an unreadable scan on which the owner wants no effort. The other
   answer is a per-book switch, or a tighter rule not yet measured.
   Recommended: accept, and exclude Stubbs' lists in its config.
   Meanwhile: as written. **Settled**: accept on Mariéjol and on
   Turney's roman foot numbers; Stubbs' pages 322 to 337 go into its
   `exclude_pages`; Domesday's 4 lines are looked at, and fixed if a
   rule can tell them from headings, or else reported.

Decided while writing, with the reasons in their sections: the
spaced-sign rule of languages other than French is English's (no book
in Spanish, German or Italian yet); a group's chapter is found by its
heading's title; the tall line is measured against the page's median;
words glued at a case change are split in structure, recorded, with
the book's words as evidence; re-reading lets a pairing by letters win
over a word under a Tesseract word whose letters are unlike
(`docs/specs/reocr.md` §4).

## 28. Not in this spec


- How regions are found, and Stubbs' cut-in notes: the layout spec.
- How plates are recognised and their pictures cut: `docs/specs/plates.md`.
- How guessed joins are reviewed, by the correct stage or a local model:
  their specs.
- Turning page numbers into links: the index stage (architecture §11).
- How each kind is written in `book.md` and styled in the EPUB: the
  markdown and epub specs (section 19).
- The evaluation tool's matching of the new kinds with the reference
  text's (`chapter_summary` and `verse` against its quotes, `endnote`
  against its notes, one heading block against the two headings Stubbs'
  and Mariéjol's reference texts make of a label and its title): a change
  to `docs/specs/evaluation.md`, before the plan's scores are taken.
- Removing specks read as margin notes, and tables as tables: later.
  Figures inside text pages are `docs/specs/figures.md`. Domesday's tables (its pages 28, 42 to 44,
  156 to 158, 425 to 428 and others) stay as the paragraph, verse and
  note rules make them, and section 6's rule 3 cuts some of their rows
  into paragraphs; since 18 November 2026 the rows of pages 156 to 159
  are numbered lists (section 29).
- Left out of the plan owner-books, by the owner's scope of 17 November
  2026: the correct stage; Mariéjol's references read "(i)" (section
  11), which stay in their words; Kadesh's notes, too damaged to cut
  (section 11, "Where the rules fail"); the lines of Stubbs' cut-in
  notes left in the body (layout §9); merging the text layer's and
  Tesseract's readings of an index word by word (`docs/specs/reocr.md`).
- The entries of a bibliography (Turney's pages 278 to 299, Haynes' 390
  to 421), which the quote rules make quotes: a kind of their own, like
  index entries, later.

## 29. Lists

A **list** is a run of short items that the printer sets apart from the
running text, each item starting with a **list marker**: a dash, a
bullet, a number or a letter. A **list item** is a block of kind
`list_item` (decided for the owner on 18 November 2026, by the
principle that a kind says what a text is): one item, its marker in
`label` as printed, its text in the spans. markdown writes the items
as a list (section 31). Before this revision a list was never seen:
the introduction of Haynes prints, on its pages 16 and 17, a sentence
that ends with a colon, six items each
starting with a dash, and a paragraph after them, and galley made one
paragraph of 544 words of all of it.

**What the books print.** Measured on 18 November 2026 on the
`lines.json` of the plan owner-books' runs (`runs/owner-books/`, galley
at 83f2754), with a prototype of the rules below run on the body streams
that galley's `page_parts` gives (scripts kept outside git):

| book | pages | marker | layout |
|---|---|---|---|
| Haynes | 16 to 17 | "—" glued to the first word ("—The") | 6 items of 5 to 10 lines; each marker line at the column's left side, its continuation lines 12.5 pt to the right of it (a hanging indent), the last line of each item short; 2 pitches of space before the first item and after the last; item 5 runs over the page break; the paragraph after starts flush left |
| Haynes | 226 | "1." to "5." | the same, 14 pt of hang, items of 1 to 3 lines |
| Domesday | 156 to 159 | "1." to "8." | the rows of the tables of the Wetherley hundred, a holder per row, the continuation of a row 14 pt to the right of its number |

No other book of the eight prints a list so: the scan found no bullet
in any book and no other dash item. Three things look like lists and
are not taken for them:

- **Numbered paragraphs**: Kadesh's pages 11 to 13 sets out its sources
  as paragraphs "1. Of the three…", "2. The RECORD…", "3. The
  RELIEFS…" of 368, 156 and 160 words, each first line indented as any
  paragraph's. Domesday prints its enumerations so too, "(i)" to "(vi)"
  on page 141, "(ii)" to "(xv)" on 316 and 317; nothing in print tells
  them from Kadesh's paragraphs, so they all stay paragraphs, each
  starting with its marker as printed.
- **A dash in running text**: Stubbs' page 21 starts two lines with
  "—" inside a sentence ("— the only period during which…"); the next
  line lies at the same left side.
- **Notes**: Mariéjol's notes left in the body start "(3)", "(4)";
  Haynes' notes at the back start "1.", "2." and hang like list items;
  Turney's bare numbers hang left of their text (section 6, rule 3).

Terms:

- a word is a **list marker** when it is a dash, "—" or "–", alone or
  glued before a letter ("—The"); a bullet, one of "•", "·", "▪", "■",
  "●", "◦", "○" and "‣"; or a number of 1 or 2 digits, a letter a to z
  or A to Z, or a roman numeral i to xv in lower case or I to XV in
  upper case, each followed by "." or ")" or between round brackets
  ("1.", "2)", "(3)", "a.", "(b)", "iv.", "(ii)"). Its **kind** is
  dash, bullet, number, letter or roman; its **form** is the bullet
  itself, or the brackets or sign around the value ("1." and "2." have
  one form, "1." and "(1)" two); its **value** is the number, the
  letter's place in the alphabet, or the numeral's value. A marker of
  the letters i, v and x only is read as a roman numeral when it starts
  a list or follows a roman marker, and as a letter when it follows a
  letter ("h.", "i.");
- a **marker line** is a line of the body stream whose first word is a
  list marker and that holds at least one more word;
- a list's **marker column** is the left side of its first marker line
  on the page, and its **hang** the distance from the marker column to
  the left side of its first continuation line (rule 4).

### The rules

The rules run on the body stream of the book in page order, as the
paragraphs are joined over page breaks (section 2, step 3.1), because
an item can run over a page break. They take no line of a page of the
config's `contents_pages` (section 30), of an index page (section 17),
or of the endnote section (section 12), and no line of a run of section
2, step 2.3 (a heading, a chapter summary, an epigraph, verse): such a
line, or such a page, ends a list.

1. **A list starts** at a marker line whose marker is a dash, a bullet,
   or the first value of its kind ("1", "a", "A", "i", "I"), when the
   line after it is a continuation line (rule 4) or the next item's
   marker line (rule 3), and the list it starts has at least two items
   when it ends. A list of one item is no list: its marker line is given
   to the paragraph rules of section 6 as if the rules had not looked at
   it, and the search for a list starts again at the line after it, so
   that a line taken for its continuation can still start a list. On
   Domesday's page 156, "I. COMBERTON…" reads as a roman first value and
   "1. Seven sokemen…" lies 8.6 pt right of it; the "list" of "I." ends
   at the line after, and "1." then starts the vill's list of 3 items.
2. **Not after a hyphen.** A marker line after a line that ends with a
   hyphen (section 6) does not start a list or an item: the hyphen rule
   holds. Inside a list, the line after a line that ends with a hyphen
   goes on with the item, wherever its left side lies (decided while
   writing the code, 18 November 2026).
3. **The next item** starts at a marker line whose marker follows the
   item before's: the same kind and form, and for a number, a letter or
   a roman numeral the next value; and whose left side lies within 3 pt
   of the marker column.
4. **A continuation line** of the item lies, when the list has a hang,
   within 3 pt of the marker column plus the hang; before the list has
   one, 5 to 20 pt right of the marker column, and that distance is
   then the list's hang.
5. **The list ends** at the first line that is neither, or whose top
   lies more than 1.5 body line pitches below the top of the line before
   it on the same page. The line that ends a list starts a block, as
   the first marker line ends the block before it. Across an in-page
   figure, whose lines and caption are out of the body stream
   (`docs/specs/figures.md` §5), the gap is not tested, as it is not
   across a page break: a figure printed between two items does not
   end the list. The eight books print none so.
6. **Over a page break** the list goes on with the first line of the
   next page that has a body stream, and the marker column is found
   again, since it moves with the page. It is the left side of the
   page's first marker line that follows the list's last item by rule 3
   (its 3 pt aside), when the lines before that one on the page all lie
   within 3 pt of one left side, 5 to 20 pt right of it, or there are
   none; otherwise the text edge (section 6, rule 3) of the page's first
   body region. A page whose first body region has no text edge, fewer
   than 3 lines that do not start with a bare number, ends the list at
   the page break (decided while writing the code, 18 November 2026; no
   list of the eight books runs onto such a page). The page's lines are
   then tested by rules 3 to 5.
   Haynes' page 17 opens with 5 lines of item 5 at 71.8 to 72.0 pt, and
   item 6's marker line lies at 59.5 pt: the marker column of page 17,
   12.5 pt left of them, the hang measured on page 16, where the marker
   column was 37.9 pt.

Inside a list the paragraph rules of section 6 do not apply, nor the
short last line at a page break; around it they apply as before.

**Blocks.** Each item is one `list_item` block: its lines joined as a
paragraph's, hyphens joined (section 5), its `label` the marker as
printed, `level` `None`. A dash glued to the item's first word is split
off it, with the word change `list_marker`: ("—The",) becomes ("—",
"The"), the "—" going to `label`. An item over a page break has an
origin per page and the id of its first page, as a paragraph. For the
references to notes (section 11), the notes left in the body (section
11), the margin notes (section 13) and the case split and spaced signs
(sections 23 and 24) a list item is a paragraph, but a list item is
never a quote (section 16 changes only paragraphs), and section 13's
rule 3 does not cut an item where a margin note stands beside one of
its continuation lines, which are indented by the hang.

**The thresholds.**

| threshold | value | where it comes from |
|---|---|---|
| hang | 5 to 20 pt | Haynes 12.5 and 14 pt, Domesday 14 to 14.4. 30 pt would add one list of Domesday (page 157, "1. Achil…", whose next line lies 24.9 pt in) but would reach Haynes' paragraph indent, 29 pt |
| marker column | 3 pt | the five marker lines of Haynes' page 16 lie from 37.7 to 39.4 pt |
| gap | 1.5 pitches | guessed: with no limit the eight books give the same lists; it keeps a paragraph set off by space below a list out of the list's last item |
| first value | "1", "a", "i" | without it, Mariéjol's notes left in the body make 17 lists ("(3)", "(4)") and Domesday's list of abbreviations one ("D. B. = Domesday Book.", "E. = Earle…", page 21) |

### What the rules give

On the eight books, with the endnote sections, index pages and
`contents_pages` left out: Haynes 2 lists of 6 and 5 items (pages 16
to 17 and 226), each item whole; Domesday 8 lists of 40 items, the
tables of pages 156 to 159; Turney, Haskins, Stubbs, Gierke, Mariéjol
and Kadesh none. Kadesh's numbered paragraphs, Domesday's enumerations
of page 141 and Stubbs' dashes of page 21 stay paragraphs.

### Where they fail

- **Tables** (Domesday 156 to 159) come out as numbered lists, one per
  vill, with the hides and values of the row read into the item's text
  ("Seven sokemen of the King 1"); a list stops at a row whose number
  the OCR read without its "." ("4 The King 2", page 156), and at a row
  hung 24.9 pt (157). Better than the paragraphs they were, and still
  not a table (section 28).
- **A misread marker** ("l." for "1.") ends the list before it; the
  items after it are paragraphs, or a new list when the misread marker
  reads as a first value.
- **A list of one-line items followed, without space, by a paragraph
  indented 5 to 20 pt**: the paragraph's first line becomes part of the
  last item. No book of the eight prints one.
- **A list inside a list**: none in the eight books; a sub-item's marker
  line lies at neither the marker column nor the hang and ends the list.
- **No public-domain dash or bullet list**: the six public-domain books
  print none, so a dash list is checked by unit tests and by Haynes'
  `whole_book` test (section 32).

## 30. The printed table of contents

The config names the pages of the printed table of contents,
`contents_pages`, and until this revision their lines stayed paragraphs
(section 14): Haynes' contents came out as one paragraph of 123 words,
"CONTENTS Acknowledgments ix Introduction i" and then each chapter's
mark, number, title and page run together, and Turney's as one of 84. Each entry
of a printed contents is now a block of kind `contents_entry` (decided
for the owner on 18 November 2026), which keeps apart what an entry
holds:

- `label`: the chapter's number as printed before the title, "2.",
  "One", "CHAPTER II.", "§ 1.", as a heading keeps its label; `None`
  when the entry has none;
- the spans: the title;
- `page_number`: the page number printed after the title, as printed,
  "23", "xiv", "pp. 9 — 26."; `None` when the entry has none. It is
  kept and not shown in the EPUB, where printed page numbers mean
  nothing;
- `level`: the entry's depth, 1 for a chapter, as an index entry has
  one (section 17);
- `heading_ref`: the id of the heading block of the chapter the entry
  names, found by its title (rule 9), so that markdown links the entry
  to it; `None` when no heading matches.

**What the books print**, measured as in section 29:

| book | contents pages | an entry | its page number | depth |
|---|---|---|---|---|
| Haynes | 8 | one line: a number "2." to "16." in a column of its own, right-aligned, then the title; the front and back matter have no number | after the title, a space apart | 1 |
| Turney | 10 | one line or two: a spelled number "One" to "Ten", then the title at a column 42 pt to the right, where its second line continues | after the title | 1 |
| Haskins | 14 | one line: a roman numeral, the title in capitals | right-aligned at the column's edge | 1 |
| Stubbs | 14 to 16 | "CHAPTER II." and the title centred on two lines, then the chapter's topics, separated by dashes, with a hanging indent | after the topics, with leader dots | 2 |
| Domesday | 14 to 20 | the front matter on a line each; "ESSAY I." and its title centred; each section centred, "§ 1. Plan of the Survey, pp. 9 — 26."; then its topics as a paragraph with a page number after each topic ("Domesday Book and its satellites, 1.") | right-aligned with leader dots; a range for a section | 3 |
| Gierke | 10; 52 to 67 | page 10 a line each, with leader dots; pages 52 to 60 a section "I. The Evolution of Political Theory." centred and its topics as paragraphs with a page number in brackets after each, "(3)."; pages 61 to 67 a table of the notes' numbers, titles and pages in two columns | roman, read "Ivi", "Ixiii" | 2 |
| Mariéjol | 450 | "CHAPITRE II" and the title on the next line | in a column that layout makes a region of its own | 1 |

Pencil marks on Haynes' and Haskins' pages are read as words, glued to
a title or a number or apart: "(Tj" and "(^" glued to a title's
first word (made-up examples: "(TjDark", "(^Unkind"), "(' 7.",
"-^1.", "_ II,".

Terms:

- a **contents run** is a set of consecutive pages of `contents_pages`:
  Gierke has two, page 10 and pages 52 to 67, and every other book one;
- an entry's **page number** is its last word when that is a
  page-number form (section 1) or a range of two joined by a dash
  ("26—36.", or the three words "107 — 128."), together with "pp." or
  "p." before it, and when it is **set apart**: it is a range or has
  "pp." or "p." before it, or leader dots come just before it, or a
  space of 11 to 20 pt, or its right side lies within 4 pt of the right
  side of the longest contents line of its page. A number at an
  ordinary space, short of the column's edge, ends a title and is no
  page number ("Psalm 23", "Maldon, 991", the roman form "mix"), since
  markdown does not write a page number and the reader would lose it
  (review of 18 November 2026);
- **leader dots** are words made only of ".", "•", "·" and "…", printed
  between a title and its page number;
- an **inline page reference** is a word that is neither the first nor
  the last of its line and is 1 to 3 digits with any of "(", ")", "."
  and "," around them ("1.", "(3).");
- a **lone label** is a line whose first word is a chapter label word
  (section 14) and that has at most one more word ("CHAPTER II.",
  "CHAPITRE PREMIER", "ESSAY I."), or that is a roman numeral alone of
  section 14's form.

### The rules

The rules run on each contents run's body stream, its pages' in page
order: the lines that are left once the running heads and page numbers
are removed (sections 3 and 4). Margin and band regions keep their
kinds, as on any page.

1. **The title.** The lines before the run's first line with a letter
   or a digit are removed as `stray_mark` (the speck read "—" above
   Stubbs' "CONTENTS"). That first line is the run's title, unless it
   ends with a page number or is a lone label, in which case it is a
   line like the others: a `heading` of level 1, without a label
   (section 33, open point 2, settled).
   This changes section 14, which made no heading on a contents page,
   for this one line, so that the printed contents has an entry in the
   EPUB's table of contents, and Gierke's "ANALYTICAL SUMMARY." a heading
   that page 10's entry can link to (decided while writing, 18 November
   2026). Every other line of a contents page is still never a heading
   line.
2. **Pieces.** The lines after the title are cut into pieces where
   section 6's rule 1 or rule 2 starts a paragraph (an indented line
   after a short one; a centred line, or the line after one) and before
   each lone label. Rule 3 of section 6 is not applied on these pages,
   as before.
3. **An analytical summary** is a piece of at least 2 lines that holds
   at least 2 inline page references, and at least one for every five
   of its lines: Domesday's and Gierke's topics, which hold one or more
   per line. The second condition keeps a one-line-per-entry page such
   as Haynes', where the pencil mark before "7." already makes one
   inline reference, from becoming one summary when a second mark is
   read so (its 22 lines would need 5). It
   is one entry, whole, without label or page number; its page numbers
   stay in its text, where the reader sees them.
4. **Entries.** Every other piece is cut into entries after each line
   that ends with a page number, and after each line whose next line in
   the piece does not lie at least 5 pt right of the left side of the
   entry's first line: an entry runs on to a second line only when the
   printer indented it, as Turney's titles of two lines, whose second
   line starts under the first's title (42 pt) and Stubbs' topics (13 pt). Without the second
   condition Haynes' closing chapter's entry, whose page number the OCR
   read "3x3", ran into "Notes 317". A line with no letter or digit joins the
   entry before it.
5. **A lone label joins the entry after it** as its label: Stubbs',
   Domesday's and Mariéjol's labels over their titles. A lone label
   never has a page number ("CHAPITRE 11", the OCR's "II"). At the end
   of a run it is an entry with the label and an empty title.
6. **The page number** is taken off the entry's end when at least one
   word is left before it; the leader dots just before it are removed,
   with the reason `leader_dots`, one removal for the dots of each line.
7. **The label** of an entry that has none from rule 5 is its first
   word, past any words with no letter or digit, when that word is a
   number of 1 or 2 digits with "." ("2."), a roman numeral of section
   14's form with "." ("IV."), an English number word "One" to "Twenty"
   in any case, a chapter label word together with the word after it
   ("CHAPTER II."), or "§" together with the word after it ("§ 1."), and
   at least one word follows it. The words before it with no letter or
   digit are part of the label ("(' 7."). The rest of the entry, up to
   its page number, is its title.
8. **Depth.** A **topics entry**, an analytical summary or an entry of
   at least 2 lines whose title holds at least 2 dashes, "—" or "–" (the
   test of a chapter summary, section 15, rule 4), is one deeper than
   the nearest entry before it in the run that is not a topics entry,
   or 1 when there is none. An entry whose label starts with a chapter
   label word is 1. A centred entry, one whose first line is centred
   (section 6, rule 2), that comes after any entry of the run whose
   label starts with a chapter label word is 2: Domesday's "§" sections
   under its essays. Any other entry is 1.
9. **The link to the chapter.** A **candidate** is an entry that is not
   a topics entry and whose title holds at least 4 letters. Each
   candidate's title is compared with the text of every heading block
   of the book, its spans without its `label`, both made **plain**:
   case-folded, every character that is not a letter (`str.isalpha`)
   made a space, the spaces collapsed to one and stripped. Labels are
   left out because a contents and the headings print the same number
   differently: "2." against "CHAPTER TWO", "One" against "Chapter
   One". Two plain texts **match** when `difflib.SequenceMatcher(None,
   a, b, autojunk=False).ratio()` is at least 0.7. The links of a run
   are the largest set of matching pairs (candidate, heading), each
   candidate and each heading in one pair at most, in which the
   candidates and the headings come in the same order, the run's order
   and the book's; among sets of the same size, the one whose ratios
   add up to the most, and among those, the one in which the first
   candidate whose pairing differs has the earlier heading. The run's
   own title (rule 1) is a heading like any other. Each run is linked on its own,
   so that a heading can be named by an entry of each run. A paired
   entry's `heading_ref` is its heading's id. The order is what keeps
   "EDWARD I." from "EDWARD II.", whose plain texts match at 0.94.
10. **Blocks.** Each entry is one `contents_entry` block, its lines
    joined as a paragraph's, hyphens joined; its origin has one box per
    page, and its id is given as any block's. It is not searched for
    note references, as an index entry is not (section 17, rule 4). A
    paragraph does not run on into a contents page or out of the last
    page of a run: the first line of each run and the first body line
    after it start a block. No chapter summary, verse or quote is made
    of a contents page's lines, as before (section 14).

The entries and their page numbers are made in step 3.1, where the
body stream is walked over page breaks, and the links in step 3.4,
with the index entries, once every heading is known.

**The thresholds.** The 5 pt of rule 4 is the indent of section 6's
rule 1 and of the index (section 17). The 2 inline page references of
rule 3 keep out a section line such as "§ 5. Sake and Soke, pp. 80 —
107.", which holds "5." and "80" inside its one line: a summary has at
least 2 lines. One reference for every five lines was measured with the
code on 18 November 2026: Gierke's topics end many lines with their
reference, which is then no inline one, and the OCR reads "(11)" as
"(n)", so that a summary of pages 52 to 60 can hold one for every three
lines; one for every two, as first written, cut 2 of those pages' 34
summaries into an entry per line (72 entries instead of 52), four cut
some too, and five keeps them all and changes no other book. It also
makes 11 summaries of rows of the table of pages 61 to 67 against 2,
each a few of its rows run together. The ratio 0.7 was measured on the candidates of the
seven books with contents pages, linking every run as rule 9 says.
The prototype differed from the rules in three ways, corrected in the
table by the review of 18 November 2026: it did not count rule 1's
titles among the headings (with them, Gierke's "ANALYTICAL SUMMARY"
of page 10 links to the heading of page 52, one link more), it took
the "11" of Mariéjol's "CHAPITRE 11" for a page number (one entry
more), and it dropped lines with no letter or digit, which rule 4 joins
to the entry before (no count changes):

| book | entries | topics entries | with a page number | candidates | linked at 0.6 | at 0.7 | at 0.8 |
|---|---|---|---|---|---|---|---|
| Haynes | 22 | 0 | 21 | 22 | 22 | 22 | 22 |
| Turney | 16 | 0 | 16 | 16 | 16 | 16 | 16 |
| Haskins | 9 | 0 | 9 | 9 | 9 | 9 | 9 |
| Stubbs | 25 | 12 | 9 | 13 | 13 | 13 | 13 |
| Domesday | 59 | 32 | 22 | 27 | 24 | 24 | 23 |
| Gierke, page 10 | 8 | 0 | 3 | 7 | 6 | 5 | 4 |
| Gierke, pages 52 to 67 | 348 | 45 | 33 | 275 | 10 | 10 | 10 |
| Mariéjol | 16 | 0 | 1 | 16 | 13 | 12 | 9 |

The rows of Gierke's pages 52 to 67 and Mariéjol's candidates were
measured again with the code on 18 November 2026 (plan lists-figures,
task 5.4), with rule 3's one reference for every five lines, and the
page numbers of every row with the test of "set apart" ("Terms"). The
spaces before a page number were measured then: Haynes 11.5 to 12.5 pt
and Turney 13.4 to 14.9, where the other spaces of an entry reach 10.2
pt; Haskins', Stubbs' and Gierke's numbers end within 1.2 pt of the
column's right side and Domesday's within 3.7. The test leaves out
Domesday's "290." after "Note : The Angild Clause," (page 17), at an
ordinary space in the middle of the column, which stays in its title,
and on Gierke's pages 52 to 67 the "d" of a signature line "M. d"
(page 54) and 42 numbers of the table of pages 61 to 67 that the layout
moved away from their column. The
prototype had given 320 entries, 47 topics entries, 58 page numbers and
240 candidates for Gierke's pages 52 to 67, near what rule 3 gives
without its second condition (317, 47 and 61), and 15 candidates for
Mariéjol, whose 16 titles all hold at least 4 letters; the links are
the same.

Every link at 0.7 was read against its heading and is right, but one:
the column heading "NOTE" of Gierke's page 62 is linked to its endnotes'
title "NOTES.". At 0.6 the two links more are right too (Mariéjol's
"BlBUOGHArHlB SUCCINCTE" to "BIBLIOGRAPHIE SUCCINCTE" at 0.67,
Gierke's "TRANSLATOR'S INTRODUCTION" to "INTRODUCTION." at 0.65), but
the books gave no other title between 0.6 and 0.7 to judge by, and the
lowest right link in the books that matter, Haynes' chapter 1 entry,
with a pen mark glued to its first word, to its heading, is 0.94.
The candidates Domesday leaves unlinked are its front matter ("TABLE OF
CONTEXTS", "LIST OF ABBREVIATIONS"), which has no heading in the body.
Its "Statistical Tables" (page 19) links at 0.71 to "STATISTICS.", the
heading flush left above the table of page index 426 (section 14,
condition 1), the right-hand half of the title "TABLE I. STATISTICS." set across
the tables' first two pages, 400 and 401; measured on 19 November 2026,
it is unlinked at 0.8, and was unlinked at every threshold while that
line was a paragraph. Haynes' 22 entries are its 16
chapters and 6 front and back matter titles, each linked to its
heading; Turney's 16 likewise.

### What the rules give, and where they fail

Haynes' page 8 gives the title "CONTENTS" as a heading and 22 entries
of depth 1: "Acknowledgments", label `None`, page "ix", linked; "Bacon's
New Engineers", label "2.", page "23", linked to "BACON'S NEW
ENGINEERS" under "CHAPTER TWO". Stubbs gives 13 entries of depth 1
(the 12 chapters with their labels, and "Index") and 12 of depth 2, the
topics, 8 of them with their page number; Domesday 8 of depth 1, 22 of
depth 2 and 29 of depth 3. These stay wrong:

- **A misread page number** stays in the title, and the EPUB shows it:
  Haynes' "3x3", Gierke's "Ivi", "Ixiii", "lor", Stubbs' "P&ge I" (page
  14, the word "Page" and the "1" read "I"), "n", "Page58" and
  ". . .110", whose number is glued to its dots; the leader dots before
  such a number stay too.
- **Depths in Domesday**: "Note : The Angild Clause" (page 17) is not
  centred and so of depth 1, and the sections § 4 to § 6 of Essay II
  after it are written nested under it; "Statistical Tables" (page 19),
  centred, is of depth 2, and the topics of § 2 are nested under it.
- **Pencil marks** stay in the title or the label: "(TjDark Chemists
  and Master Wagner" has no label; "-^1. NORMANDY…" neither.
- **Column headings**, Domesday's "PAGE" (page 14) and Gierke's
  "PA'.R" (page 10), are entries of their own.
- **Gierke's pages 52 to 67**: on pages 52 to 60, a topics line indented
  15 pt that ends 20 pt short of the column is centred by section 6's
  rule 2, and cuts a summary into entries of a line or two; pages 61 to
  67, a table of two columns read across, give an entry per line or two,
  unlinked.
- **Mariéjol's page numbers**, a region of their own, stay margin notes,
  and its entries have none.

## 31. The change to markdown and to the fidelity check

How a list and a contents look is decided here and in the style sheet,
`src/galley/epub/style.css`, never by structure (architecture §3).

**A list** is a run of consecutive `list_item` blocks in `blocks`, each
of whose labels follows the one before by section 29's rule 3. A list
whose kind is dash or bullet is a Pandoc bullet list; a list of
numbers, letters or roman numerals is an ordered list, each item's
marker written as its label, not escaped, which Pandoc reads as an
ordered list of that style and start (Pandoc 3.14 reads "(i)" as lower roman in
two brackets). Each item holds the block's fenced div, with its id and
the class `list-item`, and its text in it:

```
-   ::: {#b-p0016-002 .list-item}
    The founder, who returns in hard times…
    :::
```

The marker is not written as text: the EPUB shows the reader's bullet
for a dash list, and Pandoc's numbers for an ordered one, which equal
the printed ones because section 29 takes only markers in sequence;
Pandoc writes `<ol type="i">` for "(i)", so the brackets are lost
(checked with Pandoc 3.14 on 18 November 2026; section 33, open point
1, settled). A
block between two items of a list, a margin note or an endnote that
markdown places there (section 6, "Order"; an unlinked footnote is
written at its chapter's end, section 36), ends the list; the next item
starts a new one, whose start is its own value. Two lists with nothing
between them (a list ended by rule 5's gap and a new "1.") are written
with an empty fenced div of class `list-break` between them, since
Pandoc 3.14 reads two lists separated by a blank line only as one list
of all their items. An ordered item's div is indented by the width of
its marker and the space after it, at least 4 characters ("(iv) " takes
5, and with 4 Pandoc read the next item as code), and a marker of a
capital letter and a period, "A.", is followed by two spaces, without
which Pandoc reads a paragraph (both checked with Pandoc 3.14 in the
review of 18 November 2026).

**A contents** is a run of consecutive `contents_entry` blocks: a
fenced div of class `contents` holding a bullet list, each item a
fenced div with the block's id and the class `contents-entry`, holding
its label as a span of class `label`, as a heading's (section 19), then
its title, as a link to `#<heading_ref>` when it has one:

```
::: contents
-   ::: {#b-p0008-005 .contents-entry}
    [2\.]{.label} [Carver's New Engineers](#b-p0036-001)
    :::
:::
```

An entry of depth 2 or 3 goes in a bullet list inside the item before
it, its depth in the Markdown being its `level`, or one more than the
entry before's when its `level` is deeper still. `page_number` is not
written. Pandoc 3.14 points each link into the chapter file of its
heading in the EPUB (checked on 18 November 2026). The style sheet sets
a contents' lists without bullets (`list-style: none`) and each depth
in from the one above; the Kindle's handling of `list-style` was not
tried.

**The fidelity check at the markdown boundary** (architecture §13)
reads Pandoc's `BulletList` and `OrderedList` elements, each item's
blocks as blocks, in the forms above only: an item holding one div of a
`list_item` block, or one div of a `contents_entry` block and, after it,
a bullet list of the same form; any other content of a list is an
element galley's Markdown does not make, and an error. An empty div of
class `list-break` holds no words and is passed over. A `list_item`'s
label is not written as text, as the marker of a referenced footnote is
not, and the number of items of all lists of `list_item` divs must equal
the number of `list_item` blocks. The marker Pandoc shows for each item
is compared with its block's label instead: a `BulletList`'s item must
have a dash or a bullet as its label, and an `OrderedList`'s item, the
list's start plus its place in the list, in the list's style and
delimiter, a label that reads so (section 29, "Terms": `Decimal` for a
number, `LowerAlpha` or `UpperAlpha` for a letter, `LowerRoman` or
`UpperRoman` for a roman numeral; `Period` for "1.", `OneParen` for
"1)", `TwoParens` for "(1)"), so that a list that starts at "7." where
the book printed "1." is an error (review of 18 November 2026). A
`contents_entry`'s label is written and compared as words of its block;
its `page_number` is not written and not compared as words, but it must
have a page number's form (section 30, "Terms"), so that no title word
leaves the book unseen. A page number's rise through a run is not
checked: Gierke's table of pages 61 to 67, read across its two columns,
gives numbers out of order. A link inside a `contents_entry` div,
with no attributes, whose target is `#` and the id of a heading block,
is read as its text, compared as words of the block; the number of
such links must equal the number of entries with a `heading_ref`. Any
other link stays an error.

**At the structure boundary**, the check counts a block's `label` as
words of the block whatever its kind, and a `contents_entry`'s
`page_number` too; it verifies a `list_marker` change: one word before,
two after, the first after a dash, "—" or "–", and the two joined equal
to the word before; and it reads `leader_dots` removals as any removal.

## 32. How lists and contents are verified

**Unit tests**, on `LinesFile` values and words written in the test:

- a dash list in Haynes' geometry: a lead-in line ending
  "…types:" 2 pitches above six marker lines "—The…" at 37.9 pt,
  each item's continuation lines at 50.4 pt, the fifth item's last
  five lines at the top of the next page at 72.0 pt and the sixth's
  marker line under them at 59.5 pt, then a line flush at 59.3 pt 2
  pitches lower: a paragraph, six `list_item` blocks with label "—" and
  six `list_marker` changes, the fifth with two origins, and a
  paragraph;
- a numbered list "1." to "5." whose third and fourth items have one
  line: five items;
- not lists: a line "— the only period…" at the left side with the next
  line at the same left side (Stubbs' page 21); one marker line with a
  hang and no second item; "2." and "3." without "1."; "1." then "3.",
  whose list is "1." alone and so no list; three paragraphs "1. Of
  the three…" whose first lines are indented 15 pt and whose other
  lines lie at the column's edge (Kadesh's page 11); a marker line
  inside a verse run; a marker line after a line ending with a hyphen;
  a numbered list whose next line after the last item is 2 pitches
  lower and indented 12 pt keeps it out;
- contents in each book's layout, with Haynes', Turney's, Stubbs' and
  Domesday's geometry as section 30's table gives it: labels, titles,
  page numbers, the leader dots removed, depths 1 to 3, an analytical
  summary kept whole, "CHAPITRE 11" over a title giving one entry with
  label "CHAPITRE 11" and no page number, and the run's title a level-1
  heading;
- links: entries "(TjDark Chemists and Master Wagner" (made up) and
  "EDWARD I." and "EDWARD II.", and headings "DARK CHEMISTS AMD MASTER
  WAGNER", "EDWARD I." and "EDWARD II." in that order, give the three
  links in order; an entry with no heading alike has none; two entries
  in the order opposite to their headings' give one link;
- the fidelity check passes on all of these and fails on a
  `list_marker` change whose first word is not a dash, a
  `contents_entry` whose `heading_ref` names a block that is not a
  heading, a link in `book.md` to anything else than a heading, a list
  item holding two divs, and a written `page_number`;
- markdown: the dash list, the numbered list and a contents with depths
  1 and 2, read back by Pandoc as a `BulletList` of 6 items, an
  `OrderedList` starting at 1 in decimal with a period, and a `Div` of
  class `contents` holding a `BulletList` whose second item holds a
  nested one; the EPUB of the end-to-end test passes epubcheck with a
  contents link into another chapter file.

**Excerpt tests**, whose expected output the owner checks against the
page images:

| excerpt | page indices | what it checks |
|---|---|---|
| `haskins_front` | 14, 16 | the title "CONTENTS" a heading; 9 entries of depth 1, labels from "IV." to "VIII." ("^ VI." with its mark), none on the first three, whose numbers are glued to marks or read "II,", page numbers "i" to "251"; none linked: the others' chapters are outside the excerpt, and the excerpt's heading on page 16 holds the half-title before chapter I's title ("THE NORMANS IN EUROPEAN HISTORY I NORMANDY AND ITS PLACE IN HISTORY", section 14), which matches the first entry at 0.66 only; the whole book links it at 1.00 |
| `stubbs_summaries_index` | 16, 312 | chapters IX to XII as entries of depth 1 with their labels, unlinked; their topics of depth 2 with pages "189", "212", "238" and "263"; "Index" with page "291" linked to the index's heading on page 312 |
| `domesday_headings_quotes` | 14, 22, 30 | the front matter's entries and leader dots; "ESSAY I." with "DOMESDAY BOOK." linked to page 22's heading; the essay's topics an analytical summary of depth 2; "§ 1." with "Plan of the Survey," and page "pp. 9 — 26.", depth 2, linked to page 30's heading; its topics of depth 3 |
| `gierke_front_flow` | 10 | 8 entries; page numbers "vii", "xlvii" and "i" taken and the leader dots before them removed; "Ivi", "Ixiii" and "lor" left in their titles with their dots; none linked |
| `kadesh_8-17` | 11 to 13 | the numbered paragraphs stay paragraphs |
| `domesday_lists` (new, Domesday, `domesdaybook00maituoft`) | 141, 156, 157, 158 and body pages the plan adds | the tables' rows as numbered lists, as section 29 gives them; page 141's "(i)" to "(vi)" six paragraphs |

The new excerpt is added to `scripts/fetch_samples.py` by the plan,
which checks its body measures against the whole book's, as section 26
asks of every new excerpt, and adds body pages of Domesday until they
agree. Its expected lists are those the prototype gives, which the
owner checks against the page images.

**Whole-book tests**, marked `whole_book`, count and never quote text;
on the owner's books, found and skipped as section 26 says:

| count | Turney | Haynes |
|---|---|---|
| `list_item` blocks; with label "—"; `list_marker` changes | 0; 0; 0 | 11; 6; 6 |
| `contents_entry` blocks on the contents page, all of depth 1 | 16 | 22 |
| of them with a `page_number`; with a `heading_ref` | 16; 16 | 21; 22 |
| headings of level 1 on the contents page (the title) | 1 | 1 |

On the public-domain books: `contents_entry` blocks with a
`heading_ref`, at least 9 in Haskins, 13 in Stubbs, 23 in Domesday,
13 in Gierke and 9 in Mariéjol; every `heading_ref` names a heading;
`list_item` blocks at least 36 in Domesday and none in Haskins, Stubbs,
Gierke, Mariéjol and Kadesh; the fidelity check on every book.

**Measured by `galley-eval run`** on the four evaluation books, before
and after, in the plan's work report: the paragraph boundaries of
Domesday, whose tables become lists (galley-eval counts a list item as
a paragraph), and the reference headings in heading blocks, which may
not fall (section 9's targets).

## 33. Open points of the lists and contents revision

Both are settled; the options are kept for whoever reopens them.

1. **How a list's markers look in the EPUB.** Settled: (a), the
   reader's own markers (orchestrator for the owner, 18 November 2026). (a) As written: a dash
   or bullet list is a bullet list, which shows the reader's bullet,
   not a dash; an ordered list shows Pandoc's numbers, which equal the
   printed ones, with "." for every form ("i." for "(i)"); the Kindle
   lays out both as lists natively. (b) Every list without the
   reader's markers (`list-style: none`), the printed marker written as
   text before the item's text in a span of class `label`, with a
   hanging indent from the style sheet; the EPUB then shows "—" and
   "(i)" as printed, but depends on the Kindle honouring `list-style`
   and the indent, which was not tried, and the fidelity check then
   compares the label. Recommended: (a), the decision taken for the
   owner on 18 November 2026, since it uses the reader's own list
   layout. Changing to (b) later is a change to markdown and the style
   sheet only.
2. **The title of a printed contents as a heading.** Settled: (a), a
   level-1 heading (orchestrator for the owner, 18 November 2026). (a) As written
   (section 30, rule 1): "CONTENTS" becomes a level-1 heading, so the
   EPUB's own table of contents gains an entry "CONTENTS" that opens the
   printed one, and Gierke's "ANALYTICAL SUMMARY", which page 10 lists,
   is a heading an entry can link to; Pandoc starts a new chapter file
   at it, as at every level-1 heading. This undoes, for that one line,
   the decision of 15 November 2026 that a contents page makes no
   heading, whose reason, each chapter listed twice in the EPUB's table
   of contents, it does not touch. (b) The title stays a paragraph, as
   now; the printed contents is then reached only by paging, and
   Gierke's page 10 has one link fewer. Recommended: (a); (b) is a
   one-line change of rule 1.

Decided while writing, with the reasons in their sections: lists
printed as paragraphs stay paragraphs (section 29); an analytical summary
keeps its page numbers in its text (section 30, rule 3); the links are
made by structure, as note references are, and kept in `heading_ref`
(section 30, rule 9).

Not in this revision: a list inside a list; tables, which some rows of
Domesday's become lists of; a public-domain excerpt with a dash or
bullet list, which none of the six books prints, to be added when such
a book is found; linking an entry whose section has no heading in the
body (Domesday's "LIST OF ABBREVIATIONS", page 21, which structure
makes a quote).

## 34. Headings from lines read by Tesseract

Added on 19 November 2026 for the plan ocr-redo
(`docs/plans/ocr-redo.md`). Under `ocr = "redo"` every text page's words
are Tesseract's (`docs/specs/extract.md` §9), and Tesseract reads a row
of hieroglyphs or Arabic printed between the lines of the text as a
line of junk: "KELP IPM DS" and "ver Sih 8 RES BME J" on Kadesh's page
32, "ialey GIN Lys pt deal Spey ope paadt ope le jell Qaalt Lang" on
page 21. The layer holds no word over most of these rows, so analyze
finds no figure there: the rows of hieroglyphs that are no figure hold
43 to 115 squares of ink, against the 120 of an in-page figure
(`docs/specs/figures.md` §3 and §8), and Tesseract's
words over it come to structure as a body line. Centred, such a line
passes the heading rule (section 14). Run on the whole Kadesh book with
Tesseract's words (measured on 19 November 2026, at main 9292b17, with
Tesseract's words in place of the layer's on every text page), structure
made 16 heading blocks, against 3 with the layer: the same 3, 12 of
junk, on pages 21 (2), 30, 32 (2), 39 (3), 41, 44, 46 and 50, and the
library's card pocket on page 74 (below).

**The rule.** A body line of which at least half the words carry a
Tesseract confidence (`Word.ocr_confidence`, 0 to 100), and whose median
confidence over those words is below **60**, is not a heading line, by
whatever branch of section 14 would take it, and is neither a chapter
label nor a continuation that joins a heading. It stays in its
paragraph, and it is still a line of the body stream for every other
rule of section 14: the line before or after another line, from which
that line's gaps are measured. A line of which more than half the words
are the layer's, whose confidence is `None`, is never kept out by this
rule. The median is `statistics.median`, the mean of the two middle
values for an even number of words. The rule holds for every line read
by Tesseract, also a line layout re-read under `ocr = "verify"`
(below), though only `redo` makes such junk lines.

A line may hold words of both readings because extract keeps, on an
`ocr` page, the layer's words that Tesseract missed
(`docs/specs/extract.md` §9, "Layer words Tesseract missed"), and some
of those are the layer's junk over the same hieroglyphs: on the whole
Kadesh book with redo, page 41's junk line "19. awe fe Resales a" holds
one layer word of 5, page 46's "PAIS IIS I IK 282 TD Bm n PST" two of 9,
and both would be headings if a layer word kept a line out of the rule
(amended on 19 November 2026, with that rule of extract). Their
Tesseract words have medians of 8.8 and 20.3.

**Where 60 comes from.** On the whole Kadesh book with Tesseract's
words, the median confidence of the lines of the 12 junk heading
blocks is 0 to 50.5 ("6. iT SS 2 APIS", page 39), and that of the
lines of the real headings 85.0 ("James Henry Breastep", page 8) to
96.2 ("ADDENDUM", page 66). Over all the book's lines, 1,775 of 2,338
have a median of 90 or more; lines of the text with a median under 60
exist (a footnote line, "Seti I.'s: sen was alew * flest chariuvteer of
his majesty", 47), but none of them is a heading. On the eight books
run with `ocr = "verify"` (the stray-text runs of 18 November 2026),
4 heading lines are Tesseract's, re-read by layout, with medians of 83
to 96 (Haskins' "BIBLIOGRAPHICAL NOTE", page 129; three lines of
Mariéjol's page 14): the rule changes no heading of those runs.

**What it gives.** On Kadesh with Tesseract's words, the 12 junk
headings are gone and the 3 of the layer stay: the article's title on
page 8, the centred caption of the battle plan on page 39 (a false
heading with the layer too, section 14, "Where it fails") and
"ADDENDUM" on page 66. One heading comes that the layer did not make:
"PLEASE DO NOT REMOVE CARDS OR SLIPS FROM THIS POCKET", the library's
card pocket on page 74, which Tesseract reads at a confidence of 96
where the layer had no line to centre. It is not the book's: the
whole book's config excludes page 74 from task 2.2 of the plan on,
which gives the config `ocr = "redo"`, as it excludes the other pages
the library added (70 to 73 and 75). The junk lines stay in the text as
paragraphs, as the layer's junk over hieroglyphs does today; removing
them is not in this plan.

**The words of an in-page figure.** analyze finds the in-page figures
from the layer's words (architecture §7b), so a page has the same
figure boxes under `redo`, and layout takes Tesseract's words whose
middle lies in a figure's box into that figure's region, which
structure removes as `figure_text` (`docs/specs/figures.md` §5), as it
does the layer's. Checked on the same run: the figures of pages 41, 44
and 50 hold Tesseract's words in their regions. The junk lines beside
them, outside the boxes ("is? a « Melo eo lb. ZnS" above page 44's
figure), are kept out of the headings by the rule above and stay
paragraphs, as the layer's junk over hieroglyphs did (page 21's "uUI
Ifi. lii JL-JI").

**How it is verified.** A unit test of the heading rule with a centred
line in capitals whose words have confidences of 8 to 49, which is not
a heading, and the same line with confidences of 90, which is, and the
same line with `None`, which is; the excerpt `kadesh_redo`, whose only
heading is page 8's title, page 32's two rows of hieroglyphs making
none; and the whole Kadesh book with `ocr = "redo"`: the 3 headings of
the layer, and none on the pages listed above.

## 35. Letter fragments in Stubbs' text layer

Added on 19 November 2026 for the plan ocr-redo. Stubbs' text layer
(`earlyplantagenet01stub`) gives the descender of a "g", "p", "y" or
"j", the dot of an "i" or the top of a letter as a word of its own,
lying inside the word it was cut from: "Swabia, . and" on page 24,
where the "." is a piece of the "i" of "Swabia", "only -' to call" on
page 29, "great °" wherever the "g" of "great" lost its tail. structure
removes such a piece, a **letter fragment**, as a removal of its own,
`letter_fragment`, so that the words around it read whole.

**The rule.** In a book with letter fragments (below), on a text page
that is not an index page (section 17), a word of a line is a letter
fragment when all of these hold:

1. it is a word of the text layer, whose `ocr_confidence` is `None`,
   and has at most 2 characters, at most 1 of them a letter;
2. another word of the same line with at least 3 letters overlaps it
   across at least half of the fragment's width, overlaps it in height
   by any length, and is at least 1/1.15 of its height (the fragment is
   at most 1.15 times as tall);
3. it is alone in its line's row: fewer than 2 other words of the line
   have a top and a bottom each within 0.2 pt of its own.

It is removed with the reason `letter_fragment`, its page, box and
text, at step 2.2 (section 2), after the stray marks and before the
captions, so that no later rule sees it. A word in an in-page figure's
region is figure text already.

**A line of fragments.** A piece that sticks out of its word's line,
the tail of a "y" or the dot of an "i" set high, can be a line of its
own in `lines.json`, which the rule above, looking only inside a line,
cannot reach: "J" under "easily," on page 24, which was read "J
nations", and "." and "m", the dots of the "i" of "English" and
"kings", on page 29, which were read "themselves . m English" (the
owner's examples, 19 November 2026). So in a book with letter
fragments, on a page that is not an index page, a line every word of
which meets condition 1, and that no other rule removed, is removed
whole when each of its words lies by a word of the nearest line above
or below it in the same region that is not itself made only of such
words (page 29's "." has the line "m" below it, then "English kings,"):
a word with at least 3 letters that
overlaps it across at least half of its width, is at least 1/1.15 of
its height, and overlaps it in height or lies at most **1.5 pt** above
or below it (page 29's "." sits 1.0 pt above "English"). Each of its
words is removed with the reason `letter_fragment`, and the line is
removed as the lines of the running heads are, so that no later rule
sees it. Condition 3 does not apply, since the line holds nothing but
pieces. The book's share of pages with fragments (below) is counted
with the rule inside a line alone, as it was measured.

Measured on 19 November 2026 on the `lines.json` of the seven books
run by the plan ocr-redo: on lines made only of such pieces, 172 words
of Stubbs' pages 21 to 307 lie by a word as above (149 with a gap of 0
pt, 168 with 1 pt, 176 with 2 pt and 193 with 3 pt), each looked at on
the page rendered at 250 dpi: all 172 are a piece of a letter of the word beside them (the dot of an
"i", the tail of a "g", "p" or "y", the top of a "d", "f", "l" or
"k") or a speck between two lines; none is a printed word or a mark
of punctuation. The rule, which asks it of every word of the line,
removes 116 of them on the whole book; the other 56 share their line
with a piece that lies by no word (page 56's "com- . . . piler"), and
stay. The other six books, where the rule does not run,
hold 71 such words in Domesday, 53 in Gierke, 4 in Turney, 2 in Haynes
and none in Haskins or Kadesh read with `ocr = "redo"`.

**A book with letter fragments** is one in which at least **0.15** of
its pages that hold 5 lines or more in all their regions, counted before
any removal, index pages left out, have a word that the rule takes. The
survey, structure's first pass over the whole book (step 1), decides it
once for the book; as for every rule of the survey, the region of an
in-page figure counts for neither (`docs/specs/figures.md` §5). The
measurement below counted them; of the eight books only Kadesh,
Turney and Haynes have such regions, with 1, 0 and 0 fragments.

**Measured** on 19 November 2026 on the `lines.json` of the eight books
run by the plan stray-text (main a0a1675 to 9292b17; the rule does not
depend on the commits between), with structure's index pages:

| book | pages of 5 lines or more | pages with a fragment | share | words the rule takes |
|---|---|---|---|---|
| Stubbs | 293 | 120 | 0.410 | 251 |
| Domesday | 532 | 16 | 0.030 | 31 |
| Gierke | 269 | 7 | 0.026 | 11 |
| Kadesh | 46 | 1 | 0.022 | 1 |
| Mariéjol | 439 | 5 | 0.011 | 7 |
| Haskins, Haynes, Turney | 252, 409, 286 | 0 | 0 | 0 |

So the rule removes Stubbs' 251 and nothing in the seven other books.
Condition 1 leaves out Tesseract's words: without it, the rule takes 29
of Tesseract's words on Kadesh read with `ocr = "redo"` (specks and the
junk of hieroglyphs, ". " in "examined", "=" in "gives"), on 9 of its
44 pages of 5 lines, a share of 0.205, which would turn the rule on for
Kadesh, since every word Tesseract reads has a box of its own and
condition 3 holds for nearly all (spec review, 19 November 2026). With
it the counts above are those of the layer's words alone: on the eight
books it leaves out 3 words of Mariéjol that layout re-read with
Tesseract, and none of Stubbs' outside its index.
Of 24 of Stubbs' 251 drawn at random and looked at on the page rendered
at 200 dpi, all 24 are pieces of a letter of the word they lie in; so
are all 14 of the 251 that hold a digit, "1", ".1", "3" and "6" (the
stem of an "h" or "l", the tail of a "g" or "y", pages 58 to 282), each
looked at. The committed excerpts,
measured on the same runs restricted to their pages: Stubbs'
`stubbs_51_56-64` 0.70, `stubbs_cut_in` 0.50, `stubbs_summaries_index`
0.25 (4 pages of 5 lines that are not index pages) and `stubbs_heads`
0.22; no other excerpt above 0.11 (`gierke_notes_heads`, 1 page of 9).

**Why each condition.**

- Conditions 1 and 2, with no other, take 261 words on 127 of Stubbs'
  pages (the investigation of 19 November 2026), but also 89 in
  Domesday, 66 in Gierke, 123 in Mariéjol and 7 in Kadesh: real words
  of a row the OCR boxed over a word of another row ("a" over
  "pluralitas" on Gierke's page 225, whose rows the layer boxes 3.7 pt
  apart), a table's numbers ("19" and "8" on Domesday's pages 42 and
  44) and the words of Domesday's page 136, whose climbing words layout
  mixes (`docs/specs/extract.md` §6).
- Condition 3 keeps out a word that is one of a row of words: in
  Domesday, Gierke, Kadesh and Mariéjol the layer gives every word of an
  OCR line the same top and bottom, and a real word of the row below
  shares them with its neighbours. A fragment is cut from its word and
  stands at its own height. It keeps 259 of Stubbs' 261 and leaves 31,
  12, 10 and 1 in the others, still with real text among them (the
  table's "19" and "8" are alone in their rows).
- Index pages are left out because the digits there are page numbers
  that the scan's skew sets inside an entry's word: "91" in "William"
  on page 314, "26" in "RANULF" on 319: of the 8 words the rule takes
  on Stubbs' pages 313 to 321, the 5 that hold a digit are each part of
  a page number printed there (the 3 words "I" the rule takes there were
not looked at).
- The share of pages, not a property of the word, is what separates
  Stubbs from the others: no condition on the word alone was found that
  keeps out Domesday's table numbers and Gierke's page 225 and keeps
  240 of Stubbs' fragments. Taking only the lines beside one of Stubbs'
  cut-in notes, the plan's first idea, keeps 233 with condition 3 and
  still takes 5 words of Domesday, 1 of Gierke and 2 of Mariéjol,
  because their margin notes inside the column count as cut-in notes
  by section 2's margin rule; and leaving out the words with a digit
  loses Stubbs' 14 fragments that hold one.

**The threshold 0.15** lies between the books' shares, 0.030 at most
for the seven books against Stubbs' 0.410, and between the committed
excerpts', 0.11 against 0.22. An excerpt is a sample of a few pages, so
its share varies: ten consecutive pages of Domesday hold at most 3 with
a fragment (0.30), which would pass. When an excerpt of a book other
than Stubbs is added, its share is measured, and one of 0.15 or more is
a reason to choose other pages.

**What it does not do.** Stubbs' garble that is not a piece of a
letter stays: page 37's "j-j^ too anc j", a misreading; page 97, two
rows the layer merged; pages 102 and 120, notes cut by the column;
page 236's "r Air ttt".

**How it is verified.** Unit tests of the rule with literal words: page
24's "." inside "Swabia," removed; a word "a" over "pluralitas" whose
top and bottom two other words of its line share (Gierke's page 225)
kept; a fragment on an index page kept; the share of 0.15 met and
missed; a Tesseract word of the form of a fragment kept; page 24's
line "J" under "easily," and page 29's lines "." and "m" over
"English kings," removed whole, and a line of pieces 1.6 pt from its
word kept. Excerpt tests
on `stubbs_51_56-64` and `stubbs_cut_in`: the fragments listed in their
expected files removed with the reason `letter_fragment`, and their
words whole. `stubbs_summaries_index` (0.25) and `stubbs_heads` (0.22)
are books with letter fragments too, so their outputs change where a
fragment is, and their expected values with them. Whole books: at least
240 of Stubbs' 251 removed, and none on the seven others, Kadesh read
with `ocr = "redo"` among them.

The format: `RemovalReason.letter_fragment`, in `blocks.json`, which
stays at version 5 (architecture §8). The fidelity check counts it as
any removal.

## 36. Unlinked footnotes at the end of their chapter

Decided by the owner on 19 November 2026, for the plan note-links
(`docs/plans/note-links.md`, work package 1), after reading Kadesh,
whose footnotes stood between its paragraphs: 142 of its 183 footnotes
have no linked reference. A footnote with `referenced` false is no
longer written where it was printed: markdown writes it at the end of
its chapter, under a heading "Notes", in the order printed, with its
marker and its page as before. This replaces, for such footnotes only,
the place section 10 (b) gave them; an endnote and a referenced
footnote are written as before (section 19). Only markdown changes:
`blocks.json` keeps each note as structure found it, and the ids
structure gives keep counting each note where it was printed (section
6, "Ids and origins"), so no id changes.

**The chapter of a note.** A chapter is the run of blocks from a
heading of level 1 or 2 to the next heading of level 1 or 2, or to the
book's end; the blocks before the first such heading are a chapter too,
which no heading starts. A footnote's chapter is the one that holds its
printed place, the place section 6, "Order", gives a note: after the
last block, in the order of `blocks`, whose first page is the note's
first page or an earlier one. Its chapter ends at the first heading of
level 1 or 2 after that place, or at the book's end. A heading of level
3 or deeper ends no chapter. A heading structure found wrongly ends a
chapter as a right one does: Kadesh's level-2 heading on page 39, "The
stand which his majesty made while he was sitting on the…", takes the
74 unlinked notes of pages 8 to 38.

**What markdown writes there.** Just before the heading that ends the
chapter, or at the end of `book.md`:

```
## Notes {#notes-n-p0008-003 .unlisted .chapter-notes}

(the unlinked footnotes of pages 8 to 10, cut here)

:::: {#n-p0011-001 .note}
::: {#b-p0011-002}
\% Called by de Rougé the Bulletin\.
:::
::::
```

then each unlinked footnote of the chapter in the order of `notes`,
which is the printed order (by page, then as section 11 cuts the band),
each written as before: a fenced div with its id and the class `note`
around its blocks' divs, its marker first in the first block that is
not a margin note, and after its div the Pandoc definitions of the
referenced footnotes its blocks refer to (Pandoc moves them to the end
of the chapter file with its other footnotes). The example is cut from
Kadesh's chapter that starts on page 8, a chapter of level 1, so its
"Notes" is of level 2 and takes the id of the chapter's first unlinked
footnote, page 8's n-p0008-003; it shows the first note of page 11,
whose printed marker "15" the OCR read as "%": the marker is written as
structure has it, as before.
The heading and its notes come last of what is written at that place:
after the endnotes that section 10 (b) places there, if any, and just
before the heading that ends the chapter. A chapter with no unlinked
footnote gets no heading.

**The heading.** It is a Pandoc heading one level below the heading
that starts its chapter, level 2 in a chapter of level 1 and level 3
in one of level 2, and level 2 in the chapter before the first
heading. It is never level 1, because Pandoc starts a new file of the
EPUB at each level-1 heading. The class `unlisted` keeps it out of the
EPUB's table of contents: checked with Pandoc 3.14 on 19 November
2026, a level-2 "Notes" without it is listed in `nav.xhtml` under its
chapter, and with it is in neither `nav.xhtml` nor `toc.ncx`. A heading
was chosen over a div of a class of its own, as a note group's heading
is (section 25): a reader's navigation and a screen reader take a
heading as the start of a part of the chapter, and the class keeps the
table of contents as it was. The class `chapter-notes` names what the
heading is, for the style sheet and the fidelity check. Its id is
`notes-` and the id of the first of the chapter's unlinked footnotes, which no block or note id can
equal, since those start with `b-` or `n-`.

The word is "Notes" in every book, whatever its language: Mariéjol, in
French, spells it the same; a book in another language is for later.
It is not a word of the book, so `galley.fidelity.read_markdown`,
which reads `book.md` for the fidelity check at the markdown boundary
and for the evaluation tool, gives no word for a heading of class
`chapter-notes` whose text is exactly "Notes", and raises an error at
one with any other text (architecture §13).

**Cases.**

- *Before the first heading.* The unlinked footnotes of the pages
  before the first heading of level 1 or 2, those of an excerpt that
  starts inside a chapter or of the front matter, go just before that
  heading, under a level-2 "Notes". A note with no block on or before
  its page (section 6, "Order": first of all) belongs to that chapter
  too; when the first block is itself such a heading, the "Notes" and
  the note come first in `book.md`, before it.
- *A chapter that starts inside a page.* The notes of the page where a
  heading of level 1 or 2 stands below the page's first line are placed
  by the page's foot, where they were printed, so they go to the
  chapter the heading starts, although some refer to the text above it.
  Without a linked reference galley cannot tell which; the rule keeps
  the printed order. Measured on 19 November 2026 on the runs of the
  plan notes-vision: 4 unlinked notes of Kadesh (pages 39 and 66) and
  12 of Domesday (pages 42, 156, 470 and 481). Kadesh's page 66's notes
  go to the end of the book, after its "ADDENDUM", whose text is below
  them on the page.
- *No heading of level 1 or 2.* Every unlinked footnote goes to the
  end of `book.md`, under one "Notes" of level 2.
- *Lists.* The notes are written before a heading or at the end, never
  between two list items. Two runs of list items that an unlinked
  footnote used to stand between are now one list when their markers
  follow each other (section 31: only an endnote ends a list now);
  none of the seven books had such a footnote on 19 November 2026.
- *A footnote inside a footnote.* An unlinked footnote is not a Pandoc
  footnote, so it may still refer to a referenced one, whose definition
  follows it under "Notes".

**How it is verified.** Unit tests of `render_markdown` with literal
blocks: two chapters each get their own notes at their end and their
own "Notes"; a chapter without unlinked footnotes gets none; the notes
before the first heading go before it at level 2; the level under a
chapter of level 2 is 3, and a level-3 heading ends no chapter; a
referenced footnote and an endnote stay where they were; the fidelity
check passes on the result, and `read_markdown` fails on a heading of
class `chapter-notes` whose text is not "Notes"; a heading in the
middle of a page takes that page's notes. Excerpt tests:
`kadesh_redo`, Kadesh's pages 11 and 12 (its excerpt pages 3 and 4,
checked on the page images on 19 November 2026): the 11 notes of the
two pages are after the last block of the body, under the one level-2
"Notes" of the excerpt (which holds the excerpt's 43 unlinked notes),
next to each other in the order printed, from "Called by de Rougé the
Bulletin." to the note of page 12 that ends "On the rear (south side)
of Ramses II.'s pylon." (printed after its label "Luxor.—", which the
test does not search); and `haskins_heads_notes`, Haskins' page 40 (excerpt page 8),
whose note "Corpus Poeticum Boreale, i, p. 265 f." (the OCR reads
"265/.") moves from after the quotations of that page to just before
the heading "BIBLIOGRAPHICAL NOTE" of Haskins' page 51 (excerpt page
10), under a level-2 "Notes", since the excerpt starts inside the
chapter; it passes the three blocks of excerpt pages 9 and 10 between. The fidelity
check runs on both, as on every excerpt. Whole books: the number of
footnotes moved in each of the seven books, and each EPUB through
epubcheck.
