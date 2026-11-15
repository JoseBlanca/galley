# The structure stage

structure turns the regions and lines that layout gives
(`docs/specs/layout.md`) into the book's text as blocks. In the first
plan this spec serves, it removes what the printer put on the page and
the book does not hold, running heads, page numbers and signature marks,
each with a record of what was removed and why; it joins the words that
a hyphen splits at a line end; it finds paragraphs, including those that
run over a page break; and it keeps the text of the margins and of the
footnotes apart from the body, so that it no longer breaks the body's
paragraphs. The second plan finds notes and their references, places
margin notes, and finds headings, quotes and index entries (section 11).

Dated 15 November 2026. The owner split the work on layout and
structure into these two plans on 15 November 2026 and decided, the same
day, how hyphens that the evidence cannot decide are treated (section
5). It builds on `docs/architecture.md` (cited as "architecture §8") and
`docs/glossary.md`, and on the layout spec, whose terms (body column,
footnote band, margin note, row, body word height, body line pitch) it
uses. The code that exists is the walking skeleton's
(`docs/specs/walking-skeleton.md` §7, `src/galley/structure/__init__.py`):
one paragraph per region, nothing removed, nothing joined. This spec
replaces it.

structure reads `pages.json` (only to check that every file comes from
the same PDF), `lines.json` (each page's regions, lines and words, from
layout) and the book config (for the language of the word list), and
writes `blocks.json` (the book as blocks and notes, with what was removed
and every word changed) in the format of architecture §8, with three values
added to its enums (section 7). The margin and footnote text becomes
`margin_note` blocks and unreferenced notes, which needs a small change
to the markdown stage, as the owner decided on 15 November 2026
(section 10).

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
Gierke books. In the four, each word was labelled by **the reference**,
the Project Gutenberg edition proofread from the same scan, which the
evaluation tool (`docs/specs/evaluation.md`) compares galley with. Page means page index, from 0. A
**page-number form** is a word of 1 to 3 digits, or a well-formed
roman numeral in lower case ("xiv", not "Ill", "CIVIL" or Mariéjol's
initial "L" of "L AVENEMENT"), with at most one "." or "," after it.
The **body column** of a page, for structure, runs from the leftmost
left edge to the rightmost right edge of its body regions (section 6
says what a region's edges are); its middle is halfway between.

## 2. What structure does, in order

1. **Survey the book** (one pass over every page): the head lines, the
   book's own words for the hyphen rule, the body word height and body
   line pitch, and the offset between page index and printed page
   number. The body word height and body line pitch are measured as
   layout measures them (layout §3, "The book's measures"), on the same
   words: each page's words, from every region, are grouped into rows by
   the row rule of layout §1; on the pages of at least 15 rows (of 3 rows
   when no page has 15), the body word height is the median, over all
   their rows pooled, of the median height of a row's words, and the
   pitch the median distance from the top of a row to the top of the
   next. A book with no page of 3 rows takes the median over all its
   lines for the height, 0 without words, and 0 for the pitch. (Owner,
   15 November 2026: the median over all lines, the first rule, found
   8.1 pt on the Kadesh excerpt, whose note lines outnumber its body
   lines, against 11.0 pt for the whole book, and so no band; layout's
   rule gives 11.0 pt on both. structure imports no stage, so it repeats
   the rule.) The survey
   also finds the pages whose lowest line is a signature line (section
   4), which takes the other pages' lowest lines.
2. **Per page**: decide what each region is (below); remove the running
   head, page numbers, signature marks and stray marks (sections 3 and
   4); group the body stream into paragraphs, and each side region into
   blocks of its own (section 6); join hyphens inside each block
   (section 5).
3. **Across pages**: join the last paragraph of each page with the first
   of the next when it runs on, and the hyphen at that page break; then
   put the side text after the paragraph in which its page's body ends,
   and number the blocks (section 6).

**What each region is.** lines.json says nothing of it (architecture
§8), so structure decides from where each region lies, per page:

- the **head line** is the first region when it lies wholly above every
  other region and holds one line with a letter or a digit (and any
  number of lines of marks above it). When section 3 does not make it a
  running head, it is the first body region;
- a **margin region** is narrower than a quarter of the page's widest
  region other than the head line (the first, on a tie) and lies wholly
  left or wholly right of
  it, or overlaps vertically a region wider than itself (a cut-in note,
  once layout finds them, in the second plan, layout §9). Margin notes are about 30
  pt wide against columns of 266 to 317 pt; each column of an index is
  about half the width, so it is not a margin region;
- a **band region** is any other region, not the head line, whose
  median word height (over its words) is at most 0.85 of the body word
  height and whose top is at or below the bottom of another region,
  neither the head line nor a margin region, whose median word height is
  above that (the threshold of layout §3, step 4);
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
hyphen whose next word is not in the same block, or does not start with
a letter or digit, is left as it is, with no record. A line of one word
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
A plate whose text layer has words has a body stream; so that those
words are a paragraph of their own (section 9, "Plates"), the first line
of a page that has a figure (lines.json copies the figures) starts a
paragraph, and so does the first line of the page after it. The hyphen
rule above comes first: a line after a line that ends with a hyphen
does not start a paragraph, on a plate's page or after it either, so
that a word split before a plate and finished on it is joined.

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
in, outside rule 1's 40, so they do not make false starts; they do mix
their words into those lines until the second plan (layout §9). The
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
its text, until the second plan splits it off). No word of side text is
lost or merged into the body.

**Order.** `blocks` holds the body's paragraphs in order. After the
paragraph that holds the last line of a page's body stream, which may
have started on an earlier page or run on to a later one, come that
page's margin notes, by the order of their regions. A page's notes
follow in `notes`, in the order of their regions and lines; markdown
writes a note after the last block, in the order of `blocks`, whose
first origin is on the note's first page or an earlier one, or first of
all when there is none (section 10). A paragraph that runs over a page
break counts for the page it starts on. With a paragraph from page 3 to
page 4, then page 3's margin note, a note of page 4 comes after that
margin note and after page 3's notes, not between the paragraph and page
3's side text, as it would if a note followed the last block with a line
on its page. So the side
text of a page is read after the paragraph in which the page's body
ends, never inside it, and in page order. A page whose body stream is
empty puts its side text after the last block so far.

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

`blocks.json` as architecture §8 gives it:

| field | in the first plan |
|---|---|
| `blocks` | `paragraph` blocks, and `margin_note` blocks (section 10); `level` and `figure` `None` |
| `notes` | one note per block of a band region, `referenced` false, `marker` empty (section 10) |
| `removals` | the running heads, page numbers, signature marks and stray marks |
| `word_changes` | the hyphen joins, of the three reasons of section 5 |
| `page_numbers` | the head and foot page numbers removed |

The lists are in a fixed order, so that the file does not depend on the
number of workers: `removals` by page, and on a page from the top line
down and, on one line, from left to right; `word_changes` by the page of
their first word, and on a page the body's in reading order before
those of the side text, region by region; `page_numbers` by page, the
head's before the foot's.

Three values are added to shared enums, as architecture §8 allows ("a
spec adds a reason when it needs one"); `model.py`, `fidelity.py`, the
lists of architecture §8 and the glossary change with them:

- `RemovalReason.stray_mark`: a line with no letter or digit above the
  running head.
- `ChangeReason.hyphen_join_guessed`: a hyphen dropped without
  evidence. The fidelity check verifies it as it verifies `hyphen_join`:
  two words, the first ending with "-", and the one word after is the
  first without its hyphen followed by the second.
- `ChangeReason.hyphen_kept`: two words joined with the hyphen kept. The
  fidelity check verifies that the first ends with "-" and the one word
  after is the two words joined as they are.

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

class HyphenJoin(NamedTuple):
    word: str
    reason: ChangeReason                   # hyphen_join, hyphen_join_guessed or hyphen_kept

def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None: ...

def survey_book(lines: LinesFile, *, workers: int = DEFAULT_WORKERS) -> BookSurvey: ...
def join_hyphen(first: str, second: str, book_words: frozenset[str],
                word_list: frozenset[str]) -> HyphenJoin | None: ...
def make_blocks(lines: LinesFile, word_list: frozenset[str], *,
                workers: int = DEFAULT_WORKERS) -> BlocksFile: ...
```

`join_hyphen` gives `None` when the two words are not joined (section
5); it takes the word list in lower case, which `make_blocks` makes once
from the list `wordlist.word_list` gives. `make_blocks` is the whole stage on values: it calls `survey_book`,
does the per-page work with `map_pages`, then the work across pages.
`run` reads `pages.json` and `lines.json` with `read_checked_input` as
now, takes the word list with `wordlist.word_list(config.language)`,
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
page order. The output does not depend on the number of workers.
Comparing every head line with every other is about 150,000 comparisons
for Domesday's 546 pages; heads whose letters differ in length by more
than 8 are not compared, and its cost is measured against the speed
budget of the `coding` skill in the plan.

**The cases.**

- **A chapter's first page**: no running head; its centred title lines
  are paragraphs of their own; the drop capital (layout §3, step 6) is
  the first word of the first paragraph. A page number at its foot is
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
  plan, one per page.
- **Small type in the body's place**: Haskins' bibliographical notes and
  a quotation in small type at a page's foot are read as a band (layout
  §3, step 4) and become notes, after the paragraph in which the page's
  body ends: their words are kept and keep their order, with the wrong
  kind until the second plan.
- **The index**: its columns are body regions (or, on its first page
  under a full-size title, band regions); entries become paragraphs by
  rules 1 and 2, which do not fit an index's hanging indents. The second
  plan makes them index entries.
- **A chapter summary with a hanging indent** (Stubbs page 51): its
  indented continuation lines start blocks, so the summary comes out in
  two, and its second half runs into the chapter's first paragraph,
  whose first line is not indented. The second plan's chapter summaries
  (section 11) change it.
- **Plates**: their text-layer words become a paragraph, as now.
- **Known misses at the foot** (15 November 2026, with layout's
  regions): Kadesh's page 38 prints "105" at the foot, but its body
  column there runs from 191 to 452 pt, so the number is not centred on
  it and stays; Gierke's page 66 ends with a lone "302" and Domesday's
  page 428 with "[0", both centred, which are removed as page numbers
  although they are not the page's. No rule that is plain fixes them
  without losing others; the reference pages show whether they matter.

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

## 10. Decided: margin notes and unreferenced notes, with a change to markdown

There are no open points. The one this spec had was decided by the
owner on 15 November 2026: option (b) below. So the first plan also
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

Chosen: (b). It costs one small change outside the two stages, and
without it the first plan's work on notes and margins cannot be
measured and its paragraph scores are wrong.

## 11. Later: what the second plan adds

The first plan leaves these for the second, each a change to the steps
of section 2 that keeps the region decisions of section 2 as they are:

- **Notes and their references**: split each note's printed marker off
  its text into `marker`; find the marker in the body ("Greece,1",
  "^", "(2)") and split it off as a `note_marker` word change and a
  note-reference span; set `referenced`; join a note that runs over a
  page break; Gierke's endnotes.
- **Margin-note placement**: each margin note goes just before the
  paragraph beside whose line it was printed (architecture §9), rendered
  as a small bold line (architecture §17).
- **Headings**: centred lines, mostly capitals, low on the page, 1.1 to
  1.26 times the body height ("CHAPITRE II" above a title), become
  `heading` blocks with levels; Haskins' drop capitals and Stubbs'
  chapter summaries in small type.
- **Quotes**: Domesday's inset by about 14 pt, Stubbs' and Haskins' in
  smaller type, Mariéjol's centred verse.
- **Index entries**: `index_entry` blocks, by hanging indent.
- **Plates**: their stray text-layer words removed as `plate_text`
  (architecture §8), their captions kept.

## 12. Not in this spec

- How regions are found: the layout spec.
- How guessed joins are reviewed, by the correct stage or a local model:
  their specs.
- Turning page numbers into links: the index stage (architecture §11).
- The style of margin notes and notes in the EPUB: the epub stage.
