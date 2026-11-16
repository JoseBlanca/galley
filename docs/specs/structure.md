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
2026 (section 20).

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
  with no such word, as Gierke's 11, has none.

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
   figure; section 18), the book's marker form (section 1) and the
   endnote section (section 12), which is found from the lines that
   start a paragraph by section 6's rules. The body word height and body line pitch are
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
   1. decide what each region is (below; on an index page, section 17);
   2. remove the running head, page numbers, signature marks and stray
      marks (sections 3 and 4), the guide words of an index page
      (section 17), and on a plate page its running head and stray
      words, keeping its caption (section 18);
   3. in the body stream, find the heading lines (section 14), except on
      the config's `contents_pages`, then the chapter summary under a
      heading (section 15) and the runs of verse (section 16, rule 4);
   4. group the body stream into paragraphs (section 6), each heading,
      summary and verse run being a block of its own, and each side
      region into blocks of its own (section 6); join hyphens inside
      each block (section 5);
   5. take the notes left at the foot of the body (section 11, "Notes
      left in the body"), except on the pages of the endnote section
      and the index.
3. **Across pages**, in page order:
   1. make the band blocks of Haskins' bibliographical notes body
      paragraphs (section 16); join the last paragraph of each page with
      the first of the next when it runs on, and the hyphen at that page
      break (section 6), and a verse block likewise (section 16); a note
      taken in step 2.5
      never runs on into the next page's body, and no paragraph runs on
      into the first page of the endnote section;
   2. split a paragraph at a line beside a margin note that is indented
      (section 13, rule 3), which needs the paragraphs as joined;
   3. the notes (section 11): cut the band blocks and the notes taken
      from the body into notes, take their markers, join a note that
      runs over a page break, make the endnotes (section 12), and match
      the references in the text to the notes, splitting each off its
      word;
   4. the index entries (section 17);
   5. the quotes (section 16, rules 1 to 3), among the body blocks that
      are still paragraphs;
   6. place the margin notes (section 13);
   7. put the side text, figures and notes in reading order, and number
      the blocks (section 6).

**What each region is.** lines.json says nothing of it (architecture
§8), so structure decides from where each region lies, per page:

- the **head line** is the first region when it lies wholly above every
  other region and holds one line with a letter or a digit (and any
  number of lines of marks above it). When section 3 does not make it a
  running head, it is the first body region;
- a **margin region** is narrower than a quarter of the page's widest
  region other than the head line (the first, on a tie) and lies wholly
  left or wholly right of
  it, or overlaps vertically a region wider than itself (a note that
  Stubbs cuts into the body column, which layout takes out of the body
  lines into a region of its own: layout §3, step 2b). Margin notes are about 30
  pt wide against columns of 266 to 317 pt; each column of an index is
  about half the width, so it is not a margin region;
- a **band region** is any other region, not the head line, whose
  median word height (over its words) is at most 0.85 of the body word
  height and whose top is at or below the bottom of another region,
  neither the head line nor a margin region, whose median word height is
  above that (layout's threshold for the footnote band, layout §3,
  step 4);
- every other region is a **body region**, in layout's order.

## 3. Running heads and page numbers in the head

A head line is a **running head** when its top lies at most 2 body line
pitches below the median top of the head lines of the book, and either:

- its letters, lower case, with everything else dropped, are at least 4
  letters and at least 0.75 alike (`difflib.SequenceMatcher` ratio) to
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
least 4 and 0.75 alike to those of a running head of another page. It is
then removed as a running head is, with its page number, and the speck
above stays as it is (in the text, or as a `stray_mark` when it has no
letter or digit).

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

A word of a lowest line that is none of these stays in the text. A page
with no body region has no body column, and nothing is removed at its
foot.

## 5. Hyphens at line ends

A line whose last word ends with "-" (the ASCII hyphen-minus; the text
layers measured end 2 of their 6,000 hyphenated lines with "~" or "¬",
and none with another hyphen), with a letter or digit before the
hyphen, is joined with the first word of the next line of the same
block, when that word starts with a letter or digit, and with a digit
when a digit is before the hyphen. A line of one word is no exception.
A digit here is one of the ASCII digits 0 to 9, and a letter a
character for which Python's `str.isalpha` is true. A **number before a
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
| Domesday | 961 | 675 | 9 | 78 | 54 |
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
last paragraph of the page before that has a body stream, unless rule 1
or rule 2 makes it a start; for rule 1, "the line before" is the last
line of that page, measured against its own region's right edge. A page
with no body stream (a plate, a blank page) does not end the paragraph.
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

`blocks.json` as architecture §8 gives it, at `format_version` 2:

| field | in the first plan | added by the second plan |
|---|---|---|
| `blocks` | `paragraph` blocks, and `margin_note` blocks (section 10); `level` and `figure` `None` | `heading` blocks with `level` 1 or 2 and their chapter label in `label` (section 14); `chapter_summary` (15); `quote` and `verse` (16); `index_entry` (17); `figure` blocks with their image (18); margin notes placed before their paragraph (13) |
| `notes` | one note per block of a band region, `referenced` false, `marker` empty (section 10) | the notes cut and marked by section 11, each with its `kind` (`footnote`, or `endnote` by section 12), `referenced` true when its reference was found, and margin notes among its blocks (13) |
| `removals` | the running heads, page numbers, signature marks and stray marks | the guide words of an index (`guide_words`, 17); a plate's running head and stray words (`running_head`, `plate_text`, 18) |
| `word_changes` | the hyphen joins, of the three reasons of section 5 | the `note_marker` splits of section 11 |
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
    signature_lines: frozenset[int]        # pages whose lowest line is a signature line
    index_pages: frozenset[int]            # section 17, rule 1
    plate_pages: frozenset[int]            # pages with a figure (section 18)

class HyphenJoin(NamedTuple):
    word: str
    reason: ChangeReason                   # hyphen_join, hyphen_join_guessed or hyphen_kept

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
def note_marker(word: str, *, endnote: bool = False) -> NoteMarker | None: ...
def reference_candidate(word: str) -> Reference | None: ...
def make_blocks(lines: LinesFile, lower_case_words: frozenset[str], *,
                language: Language = Language.EN,
                contents_pages: frozenset[int] = frozenset(),
                workers: int = DEFAULT_WORKERS) -> BlocksFile: ...
```

`note_marker` gives the marker of a note's first word by the forms of
section 11 (with `endnote`, also the endnote form), or `None`;
`reference_candidate` gives a candidate reference of section 11, or
`None` (for "p.12", an abbreviation, `None`). `ReferenceForm` is a
`StrEnum` of the module. `language` serves the index title of a French
book ("table alphabétique", section 17); `contents_pages` is the
config's (section 14). `join_hyphen` gives `None` when the two words are not joined (section
5); it takes the word list in lower case, which `make_blocks` is given
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
than 8 are not compared, and its cost is measured against the speed
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
  indented 9 pt, give one `index_entry` per line at the edge; a line
  "BUR CON" is removed as `guide_words`; a row read across the gutter is
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
| `stubbs_51_56-64` | 0 (51) | heading "CHAPTER III. / THE EARLY YEARS OF HENRY II.", level 1, `label` "CHAPTER III."; the 3-line summary, one `chapter_summary`; "Very few epochs…" starts a paragraph; the cut-in note "Importance attached… accession." before its paragraph |
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
| `kadesh_8-17` | 8 (16) | a plate with no caption: its two lines removed as `plate_text`, a figure block with no text after the paragraph that runs over it |
| `gierke_86-93_270-271` | 0 (86) | "POLITICAL THEORIES OF THE / MIDDLE AGE.", level 1; "I. The Evolution of Political Theory.", level 2 |
| `gierke_86-93_270-271` | 2 (88) | "Law1" stays unsplit (endnote 1 is outside the excerpt); margin notes before the paragraphs whose first lines they are beside; "Medieval Thought." beside the page's last line |
| `gierke_86-93_270-271` | 6 (92) | "II. Macrocosm and Microcosm.", level 2, and the known false heading "Macrocosm and Microcosm." at the top |
| `gierke_86-93_270-271` | 8 (270), 9 (271) | endnotes 291 to 302, kind `endnote`, unreferenced, each margin note inside its note before its text; the end of note 290 at the top of page 270 an endnote with no marker, not joined to the last paragraph of page 93 |
| `haskins_quotes_index` (new) | 0 (39) | a level-2 heading "BIBLIOGRAPHICAL NOTE" mid-page, paragraphs after it, not quotes (section 16) |
| `haskins_quotes_index` | 1 (53) | quotes in smaller type across the column |
| `haskins_quotes_index` | 2 to 4 (71 to 73) | a quote that runs over two page breaks |
| `haskins_quotes_index` | 5 (129) | the heading "BIBLIOGRAPHICAL NOTE" above a band of small type, whose blocks are paragraphs, not notes |
| `haskins_quotes_index` | 6 (209), 7 (234) | centred Latin verse and English verse, `verse` blocks with their line breaks |
| `haskins_quotes_index` | 8 (267), 9 (269) | index rows read across both columns, cut at the gutter; "Calabria", an entry from the foot of one column to the top of the next |
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
  indices 39, 53, 71, 72, 73, 129, 209, 234, 267 and 269.
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
kinds (section 21), against the scores of the first plan's work report:

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

Chosen: (b).

## 11. Notes and their references

A footnote is printed at the foot of its page with a **marker** before
it ("8", "(3)", "*"), and the same marker, often as a superscript, at
the place in the text that refers to it, the **reference**. structure
cuts the band into notes, takes each note's marker out of its text,
finds the references in the body and links each to its note. A note
whose reference is not found stays a note, unreferenced, where it was
printed; a reference whose note is not found stays in its word.

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
   is what the marker of the note before it reads plus 1; this uses what
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
   to its first word.

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
page 76), unless it is "A", "I" or "a", which are words, and the next
word is a known word (`wordlist.is_known_word`, architecture §12):
"A Treatise", "I have" keep their first word, and the signs when the word is 1 or 2 of the signs above glued
to a word that starts with a capital ("'There" on Kadesh page 8: the
marker is "'" and the text starts with "There"). Otherwise the note has
no marker: `marker` is empty and every word stays in its text.

The marker is taken out of the note's first block into `marker`, as the
OCR read it. A glued marker is split off by a `note_marker` word change
on the note's page: ("13The",) becomes ("13", "The"), the marker is "13"
and the text starts with "The".

**Its value.** In a book whose notes are numbered per page, the k-th
note that starts on a page has the value k, whatever its marker reads:
the markers are too damaged to count on (Domesday's page 83 reads "1 2 8
* 8 e 7 8" for notes 1 to 8). A page's first note that has no marker
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
- a **sign**: the word "^", "*" or "•", or a letter, any punctuation and
  one of them at the word's end ("rulers.^", "Normandy.*"). A lone "'"
  or "t" is not one: in Domesday such a match was right 28 times in 82.

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

A pair that none of these rows scores is never matched. A note left
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
to ("land", "3", "."), ("rulers.^",) to ("rulers.", "^"), and its block
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
1) from the lines that start a paragraph by section 6's rules. The
section runs from the first marker of the first run of at least 8 to
the last marker of the last such run, so that a damaged marker that
reads lower does not cut it in two. On its first page it reaches back
over the paragraphs before its first marker up to the first centred
line above them, which stays out ("NOTES." on Gierke's page 186); it
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

**References.** Endnotes are numbered through the book, so they are
matched as in section 11, but once over the whole book, not per page:
the endnotes in order of their values against the glued numbers of the
body before the section, in reading order, by the same scores. The
candidates are taken only from the pages after the last of the config's
`contents_pages` (Gierke: after page 67, so pages 68 to 185), and only
those no footnote took: Maitland's introduction, before Gierke's own
table of contents, refers to its own notes, and its glued numbers took
endnotes 1 to 7 from Gierke's "Law1" (page 88), "communities2." (93)
and the rest (decided in the review of 16 November 2026). Gierke's markers end with "." ("1.") and its
references do not ("Law1"), so none reads as its marker; linked as
section 11 says, 205 of them are, 186 by an exact value. Maitland's
introduction (pages 0 to 85) has notes of its own, printed on pages 62
to 64; they were not studied, and stay where they are now.

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
A **chapter label** is a line that starts with CHAPTER, CHAPITRE, ESSAY,
PART, PARTIE, BOOK or LIVRE, in any case, or is a roman numeral alone as
the OCR reads one: 1 to 5 of the characters `IVXLCl1`, with an optional
".", ("II", "Ill" for III).

### The rule

A body line is a **heading line** when all of these hold:

1. it is centred (section 6, rule 2). On a page whose body regions hold
   fewer than 5 lines, it may instead be centred, by the same 15 pt and
   10 pt, between the leftmost and rightmost sides of the page's body and
   band lines (Haskins' page 129 prints "BIBLIOGRAPHICAL NOTE" above a
   section in small type that layout makes a band, so the body column is
   the heading itself);
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
has no running head; any other is level 2. A roman numeral counts as a
label only as a line of its own, so "I. The Evolution of Political
Theory." is level 2. In the four books with a
reference text, this makes the chapters, the preface, the contents, the
index and Domesday's essays level 1, and Haskins' "BIBLIOGRAPHICAL NOTE"
sections and Domesday's "§" sections and "NOTE." level 2.

**Contents pages.** On the pages of the config's `contents_pages`, no
line is a heading line; their lines stay paragraphs (owner, 15 November
2026): no chapter summary, verse (section 15 and 16, rule 4) or quote
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

### Where it fails

- **Missed**: Stubbs' half-title "THE EARLY PLANTAGENETS." (page 18),
  whose second line runs nearly the full width; Domesday's "INDEX."
  (page 546), where the index columns make the page's column too narrow
  on one side for the title to be centred.
- **False**: Domesday's titles of four tables set in capitals
  ("ARMINGFORD HUNDRED.", pages 28, 42, 156, 470), and its printer's
  imprint (553). Kadesh's centred caption of a battle plan (39) and a
  garbled map label (29). Gierke's "Macrocosm and Microcosm." at the top
  of page 92 (excerpt page 6), a running head that section 3 does not
  remove, taken by the gap branch.
- **Levels**: Stubbs' "INDEX." (312) is level 2, because the guide words
  stand above it; Gierke's ten numbered sections ("I. The Evolution of
  Political Theory.") are level 2 under the book's title on page 86,
  where a reader would want level 1.
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
it), and the paragraph the next page starts is a block of its own.
Measured on 16 November 2026 on the first plan's blocks of Domesday's
and Mariéjol's body ranges, against the reference text: of the quotes
rules 1 to 3 make there, the exclusion takes 28 of Domesday's 30 notes
and 35 of Mariéjol's 40 (with 3 and 15 more blocks the reference text
has as neither notes nor quotes, tables and garble), and no real quote
(Domesday's "(i) A Somersetshire manor…" are bracketed, against its
digits). False note-quotes remain: 2 in Domesday, 5 in Mariéjol. A
book whose form is digits and whose paragraphs start with a number
("1. Of the three…") would have such a paragraph cut at a page break,
since it never runs on (how often the six books do so was not
measured). A
rule here changes a block's kind and no word, so it needs no record.

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
   words and inset at least 30 pt from both of its region's edges, more
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
threshold. The reference texts put each inline sub-entry on a line of
its own; galley keeps an entry with its sub-entries as printed, one
block.

### The rules

1. **Index pages.** The index starts at a page whose title, the head line
   or the first line of its first body region, starts with the word
   "index", in any case ("INDEX.", "INDEX TO LIST OF AUTHORITIES"), or,
   in a French book, "table alphabétique". It runs on over the following
   pages while each page that has words has two **index columns**: two
   regions that are not margin regions, each 0.3 to 0.65 of the width
   that the page's regions span, one left of the other. A page without
   words does not end it. Measured: this gives exactly the pages of the
   table above; Stubbs' 322 (advertisements in one column), Domesday's
   553 (the printer's imprint) and Gierke's 86 (the text) end them.
2. **The regions of an index page.** The head line is decided as on any
   page (section 3). The two index columns are index columns whether
   section 2 would make them body or band regions. A line of exactly two
   words of three capital letters each is the **guide words** (the first
   letters of the page's first and last entries, "BUR CON"), removed with
   the reason `guide_words` (architecture §8); 10 of Stubbs' 10 index
   pages have one, and no other page of the six books. A margin region
   goes into the column on its side, by its top, so that a page number
   that overhangs the column ("509-515", Domesday page 546) follows the
   line it ends. A region that crosses the **gutter** (the middle between
   the left column's right edge and the right column's left edge) is cut
   there, each word going by its middle, when at least two thirds of its
   lines have no word over the gutter: its left part is read with the
   left column and its right part with the right, by their tops. This
   repairs the rows layout reads across both columns (below). Any other
   region keeps its kind: Gierke's footnote on page 83 stays a note (1 of
   its 2 lines crosses the gutter).
3. **Entries.** The lines of the left column, then of the right, page
   after page, are one stream. A line starts an entry when its left side
   lies within 5 pt of its column's left edge; otherwise it continues the
   entry before it, also across a column or a page. The left edge is a
   straight line fitted, by least squares on the line's top, through the
   left sides of the lines that start within 3 pt of the column's
   commonest left side, then fitted again through those within 3 pt of
   the first fit, because scans are skewed: Gierke's page 84 drifts from
   42 to 47 pt over 41 lines. A column of fewer than 5 lines takes its
   smallest left side.
4. **Blocks.** Each entry is one `index_entry` block, `level` `None`, its
   lines joined as a paragraph's, hyphens joined by section 5 ("72-"
   "81;" gives "72-81;", "Vik-" "ing," gives "Viking,"). Its page numbers
   stay as printed. Its origin has one box per page. The title is a
   heading (section 14).

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
- **A head line that is a number alone** (Domesday 547: "522") is no
  running head (section 3) and becomes an entry "522".

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

**The rules**, on a page that has a figure:

1. **Its running head.** Layout makes no head line on a page whose first
   row is its only row or is not set apart (layout §3, step 3), and the
   head that Kadesh prints on its plates stands 79 to 191 pt from the
   top, so section 3 does not find it. On a plate page, the topmost line
   is a running head when its letters are alike, by section 3's rule
   (at least 4 letters, 0.75), to the topmost line of another plate page
   or to a running head of the book, wherever it lies. Kadesh's
   "DECENNIAL PUBLICATIONS, V" on pages 34, 42, 48, 56 and 64 is then
   removed; page 68's garbled form is 0.68 alike and stays, as a
   caption line. A head line that section 3 makes a running head
   (Kadesh 19 and 24) is removed as on any page.
2. **Caption and stray words.** Every other line is a caption line when
   at least 2 of its words, or at least half of them, are **known
   words**, by `wordlist.is_known_word`, which analyze uses too
   (`docs/specs/plates.md` §2): a word whose key (section 5: lower case,
   with what is not a letter, digit, hyphen or apostrophe stripped from
   both ends) has at least 2 letters, is made of letters, apostrophes and
   hyphens, and is in the lower-cased word list; or a number, digits with
   brackets or punctuation around them ("16", "17]"). Every other line is
   removed as `plate_text`, one removal per line.
3. **The figure block.** The caption lines, in order, are the text of
   one `figure` block, whose `figure` is the path of the image of the
   page's figure; a plate with no caption line, or with no text layer
   (Kadesh 17, 23, 35, 43, 57 and 69, Stubbs 9, 11, 52 and 54), gives a
   figure block with no spans. Its lines are not in the body stream, so a paragraph runs
   on over the plate (section 6: a page with no body stream does not end
   the paragraph, and a hyphen before the plate joins the word after
   it). The figure block is side text of its page (section 6): it comes
   after the paragraph in which the body before it ends.

**Measured** in the second research on the 12 plates of the six books
that have a text layer (Kadesh 16, 19, 22, 24, 34, 42, 48, 56, 64, 68;
Domesday 39 and 40) and two backs of plates (Kadesh 49 and 65), with
the running heads of rule 1: 26 lines (87 words) removed, all stray
(one, Kadesh 68's "V", the end of the plate's head); 24 lines (95 words)
kept: the running heads of 19 and 24, which section 3 removes first, the
captions, the plates' labels ("PLATE II", "XXV I XXIV xxm"), the series
heads, Domesday's binder's note "[Between pp. 16–17]", read as "\.Bet^ueen
pp. 16 —" and "17]", and 2 strays of Domesday 39, "Fir" and "•'••'""'
rAr", with one known word each, so half their words.

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
  break at each line feed of its text;
- a referenced footnote as a Pandoc footnote at its reference, with its
  margin notes inside it;
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

## 21. Not in this spec

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
- Removing specks read as margin notes, figures inside text pages,
  tables as tables: later.
