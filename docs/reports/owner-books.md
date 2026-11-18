# Work report: owner's books

The work of the plan `docs/plans/owner-books.md`, written as it goes, for
the owner. Started on 17 November 2026 on branch `plan/owner-books`.

## Summary

**The plan is done** on branch `plan/owner-books` (18 November 2026)
and waits for the owner's order to merge it into `main`. The owner
asked that it be written and carried out without their review; every
decision taken in their absence is listed below. Every check passes at
9672288: 2,494 quick tests in about 68 s, 106 slow tests on whole books
(the owner's two included) in 515 s, and the EPUBs of all eight books
with 0 errors and 0 warnings from epubcheck.

**What changed for the owner's two books** (Turney's book; Haynes' book), counted on galley's
output and checked against the page images:

| | before the plan | now |
|---|---|---|
| chapter headings with their label ("Chapter One") | Turney 1, Haynes 0 headings in all | 10 of 10, 16 of 16 |
| Turney's running heads left in the text | 98 | 0 |
| Turney's page numbers taken for margin notes | 329 | 0 |
| notes at the back linked to their reference | Turney 0; Haynes 127, 120 of them to another chapter's note | Turney 530 of 613; Haynes 582 of 632 (584 before review 3 refused 2 doubtful links); none to a wrong note |
| epigraphs, with their source apart | run into the text | Turney 13, Haynes 21 (8 in verse) |

Also, in every book: a page break ends a paragraph after a short last
line that ends a sentence; in English books "pursued ?" is "pursued?"
(Domesday 2,112 signs, Stubbs 1,007); in French the space before a
sign no longer breaks a line; words glued at a capital ("theAvre") are
split; and words read twice by re-reading fell (Domesday 30 to 5,
Gierke 12 to 0).

**The public-domain books**, scored against their online editions by
the project's scoring tool (`galley-eval`), against its run at the
plan's start: the share of wrong words in the body fell on Stubbs from
0.053 to 0.033 and on Domesday from 0.075 to 0.058; Haskins' notes
whose reference is right rose from 61 to 66. Three scores fell by
amounts beyond the plan's tolerances, none by a lost word: Mariéjol's
paragraph precision by 0.005 (three garbled lines of that scan taken
for headings), and two Domesday counts by 1 and 2, where galley's
output is the same and only the scorer's alignment moved (task 7.1).

**Decided in the owner's absence**, each with its measurement in the
sections below: the epigraph's source is a field of the block, its
dash written by the Markdown step, so Turney's sources, printed without
a dash, get one in the EPUB as Haynes' do; group headings of the notes
stay out of the table of contents; Stubbs' publisher's lists are left
out of its book (config); the running heads' likeness threshold went
from 0.75 to 0.70; the page-break rule does not cut when the next page
goes on in lower case or the last line is a footnote's first. Each is a
rule in a spec and a few lines of code; any can be changed after the
merge by a spec change and its code, as a later task.

**Format changes**: blocks.json goes to version 4 (the epigraph, its
source, a note's group, three new kinds of recorded word change), and
lines.json to version 3 (re-reading records the junk words it
replaced). A run made before the merge must run layout and structure
again: galley refuses to read the old files and says which stage to
run.

**Still wrong**, for later plans:

- A footnote left in the main text at a page's foot still cuts the
  sentence that runs on over the page when it resumes with a capital
  (Gierke 156), and a few footnotes stay in the text (Gierke, Kadesh,
  Mariéjol).
- A note reference set after a year ("1959.²") is not linked: about 5
  in the owner's books.
- Turney's two newspaper pages reproduced as plates (174-175) become a
  heading; one Haynes verse epigraph keeps a turnover line apart.
- Gierke's section heading "II. LEGISTS." is not found; tables are not
  handled; the OCR's own misreadings stay ("AMD" for "AND").
- The quick tests take about 68 s against the minute asked: the four
  new excerpts' setup costs about 10 s.

**Asked of the owner:**

1. The order to merge into `main`.
2. A look at the two EPUBs, `runs/owner-books/turney/book.epub` and
   `runs/owner-books/haynes/book.epub` in the main checkout, built from
   the plan's final code: the table
   of contents, a chapter opening with its epigraph, and a note
   followed from the text to the back and back.
3. Whether Turney's sources should keep the book's look (no dash)
   rather than one look for every book.

## Before the first task

The owner approved the scope in chat on 17 November 2026 and asked that
the specs and the plan be written and carried out without waiting for
their review, since they were away. The specs' open points (structure
§27) were settled by the orchestrator: the epigraph's source and the
note group heading are text fields of their block; group headings stay
out of the table of contents; the markdown step writes the source's
dash as text (a Kindle's support for CSS generated text is untested);
the heading rule's costs on Mariéjol are accepted, Stubbs' publisher's
lists are excluded in its config, and Domesday's 4 false headings are
looked at in task 1.6.

Two surveys ground the specs; their notes are outside the repository
because they quote the owner's books.

**The baseline**, `uv run galley-eval run` on `main` at 9715a93 (3 min
41 s), copied to `runs/owner-books-baseline/` of the main checkout. It
equals Review 3's scores of clean-text: Stubbs' margin notes 291 as
margin notes (error rate 0.244), Domesday's 579 (0.138), Stubbs' index
.984 / .963, Domesday's .995 / .998, body error rates .023 / .055 /
.075 / .310 (Haskins, Stubbs, Domesday, Mariéjol), Domesday's notes
whose reference is right 1,278.

## Task 1.1: the four excerpts

b6c75e7: haskins_heads_notes (13 pages), stubbs_heads (18),
gierke_intro_heads (13) and domesday_rereads (11), with the expected
output of their 36 case pages in `tests/fixtures/expected/owner_books_wp1/`
(the removals, page numbers, headings and note-band starts WP1's rules
must give; each with the printed text read from the 300-dpi render by
the assistant). Pages were added beyond the spec's case pages so that
each excerpt's measures equal its whole book's (Stubbs' line pitch was
7.68 pt against 12.87 without them). The default run went from 46.4 s
to 56.1 s (2,127 passed), 21.4 s of it the excerpts' setup.

Left to work package 1: Gierke pages 72 and 78, whose damaged heads are
0.74 and 0.70 alike, under the spec's 0.75, so they stay in the text
under the rules as written; Stubbs 186 and Gierke 73 record a wrong
page number ("5" for 165, "xviii" for lxviii).

## Task 2.1: the format

418c726: blocks.json version 4 in `model.py` (the epigraph kind, a
block's `source`, a note's `group`, the reasons `source_dash`,
`punctuation_attached` and `case_split`), and the fidelity check's rules
for them at both boundaries. Changed beyond the task's files, with the
orchestrator's leave: the epigraph kind in markdown's two `match`
statements (a plain div until task 6.1) and in galley-eval's two kinds,
whose tests failed and which would have crashed on a real epigraph.
`source` and `group` default to None, so no other stream's code had
to change. Default run 60.4 s, measured while other streams ran pytest
on the same machine.

## Task 5.1: spaced signs and case splits (stream `words`)

12c38a4, 76d3db2, 6b33a5d, f99da27, merged into the plan's branch. The
pure functions `attach_spaced_sign`, `split_at_case` and their passes
over a block, not yet wired into structure (task 5.2). Counts on the
six books' clean-text lines (signs attached / case splits): Haskins
90 / 2, Stubbs 1,022 / 10, Domesday 2,115 / 3, Gierke 888 / 0, Kadesh
98 / 0; Mariéjol 1,150 no-break spaces and 12 splits.

**Changed from the spec (76d3db2).** As first written, the case split
took 48 Mariéjol words, at least 30 of them misreadings cut in two
("poUtique" for "politique"), and Domesday's "jiEthelbert": Tesseract's
word lists hold "po" and "ji". Now the left part must also be one of
the book's common inner words, and no split is made before a capital U
or H (a misread "li"). Mariéjol's 6 remaining wrong splits are an
accepted cost (the owner's decision on that scan); Domesday's "forSon"
and "forSan" are to be checked on the page in WP 5's review.

## Task 6.1: the epigraph and the note group in Markdown (stream `markdown`)

00f8f1d, merged. An epigraph is a div of class `epigraph` holding the
quotation (a verse epigraph's lines end in hard line breaks), then a
div of class `epigraph-source` holding "—", a no-break space and the
source. A note's group heading is a div of class `note-group` before
its endnote, not a heading, so it stays out of the table of contents.
The style sheet sets the epigraph in from both sides with its source
on its own line at the right, and the group heading in bold. An EPUB
built by hand from blocks with a verse epigraph and two note groups
passes epubcheck. Not in the spec, decided by the writer: an epigraph
with no source is written as its quotation alone.

## Tasks 1.2 to 1.6: running heads, page numbers, headings (stream `edges`)

Merged at 11f3afe. The decision point passes: on the owner's books
every chapter is a level-1 heading with its label, Turney 10 of 10 and
Haynes 16 of 16 (before the plan, 1 and 0 headings in all). Turney has
60 headings (17 level 1, 43 level 2), Haynes 46 (23 and 23).

At the first count Turney gave 9 and Haynes 15, and the heading rule
made four false level-1 headings in the public-domain books. Decided by
the orchestrator and fixed, each with a spec commit first:

- the gap above a tall line skips lines with no letter or digit (a
  speck above a Turney label); a title's first line may start up to 4.0
  pitches below a chapter label that stands alone (a Haynes title);
- the running heads' likeness threshold goes from 0.75 to 0.70, which
  changes no line of text on the eight books and removes 13 more heads
  (Gierke 58, 72, 78, ten of Mariéjol's, checked on renders);
- a line in the head band at least 0.6 alike to the book's running
  heads is never a heading (Domesday 159 and 552, Kadesh 38, Mariéjol
  121);
- the region below the head line may reach 2 pt into it (Stubbs 17
  keeps "MAPS."; Domesday 398 loses its head and page number, rightly).

Changed by the writer, outside its files: the layout spec (4e080f5,
the head row's lines), accepted. The hanging-number counts of layout
§3 corrected to those measured (Turney 99, Gierke 30 of which 2 are
specks, Domesday 2 of which 1). Page 163 added to the Haskins excerpt
so that page 195's notes find their chapter.

Checks at 11f3afe: 2,300 passed, 8 xfailed in 60.3 s; the whole-book
set gave 79 passed and 1 failed, a test fixed in 39e14a8 and rerun
alone.

## Task 4.1: the epigraph rule (stream `epigraphs`)

96339c7, 21914ae, 1d0aaa0, merged. The rule as pure functions over a
page's body lines, not yet wired into structure (task 4.2). It finds
Haynes' 21 epigraphs (8 of them verse, all 21 with a dash) and Turney's
13 (three on one page; the survey had counted 12), and none on the six
public-domain books. Changed in the spec by the orchestrator's decision
(21914ae): the page's left edge is its leftmost body line that is not a
heading, because on two Turney pages the epigraph has more lines than
the text; a source may end 5 pt short of the quotation (3 pt before);
a source may run over several lines, each ending within 5 pt of the
first's right side (without that, Turney's back cover was an epigraph).
The plan's and §26's count for Turney goes from 11 to 13.

## Review 1: work package 1

Of 11f3afe, by three reviewers (fidelity; spec and tests; conventions),
the fidelity one against ee36969, the commit before work package 1.
Structure's fidelity check passed on all eight books: no word was lost
without a record. What mattered, all fixed (merged at ef1d766):

- **Notes cut in the wrong place.** Starting a note band at a marker row
  without a gap cut Kadesh's two-column bands (pages 14, 28, 40), so a
  note's continuation ended another note. Now only when the row above
  is not small print (a speck passed over: Domesday 406 keeps its note).
- **A footnote taken for a margin note**, Domesday 535 and 443: a small
  region may reach 2 pt into the one above and stay a band.
- **Specks moved into sentences** by the hanging-number rule (Domesday
  443 "6", Gierke 160 "9", Domesday 39's plate caption): a number is
  kept in its line only with no margin word between and on a page with
  at least 2 hanging numbers. Turney's 99 and Gierke's 28 contents
  numbers stay.
- **Domesday 159's running head back in the text**, from a low page
  number: the head row's top leaves out page-number words.
- The new whole-book tests timed out run alone; four conditions had no
  test that failed when broken; one chapter-label rule was written twice
  with different punctuation; other names and constants.

Not fixed, known:

- Gierke 66: the contents number "279" sits in a line the 0.70 rule
  takes as a running head, and is removed with it (recorded).
- Gierke's section heading "II. LEGISTS." (page 78, damaged in the
  scan) is not found, so deliverable 4's list of that book's section
  headings misses one; no text is lost.
- Stubbs 186 and Gierke 73 record wrong page numbers ("5", "xviii").

Checks at ef1d766: 2,342 passed and 8 xfailed in 61.0 s (58.6 s on the
stream's tree); whole_book 80 passed in 487 s.

## Task 2.2: re-reading's pairing

e4c04ed, fe90c37, c710589, 5e0a27f. A Tesseract word whose letters
match a layer word (equal or alike) pairs with it even when an unlike
junk word lies under it too; that junk is then replaced with the rest,
and a layer word duplicated under one Tesseract word counts once in the
layer's score. Words read twice, before → after, recomputed from the
same Tesseract readings: Domesday 30 → 4, Gierke 12 → 0, Stubbs 6 → 5,
Haskins 0 → 0; no record changed its choice of reading on the four
books. The first version (fe90c37) had left junk in the text on four
Domesday pages and flipped eight records to the layer's worse reading
through a tie; the second commit put both right. Reference page
domesday_rereads page 0 (book page 26) loses the "tem<" of the
owner's report; pages 2, 6, 8 and 10 lose their doubled words.

Known: Gierke 63 keeps the layer's "14." beside Tesseract's "146", and
Domesday 107 keeps Tesseract's "th" for the layer's right "the".
Default run 69.4 s while the notes stream ran its tests.

## Review 2: work package 2

Of c928f76, by two reviewers (fidelity; spec, tests and conventions).
What mattered, all fixed (c09fc7c to 2305891):

- **A printed word lost**, Domesday page 90: the layer glued the body's
  last "of" to the margin note's "demesne", and the new pairing replaced
  the glued word whole. An alike layer word with 2 or more letters more
  than the Tesseract word is no longer paired that way ("ofdemesne-"
  and Domesday 333's "imgmen." stay in the layer beside Tesseract's
  reading, as before the plan).
- **The fidelity check could not tell junk from a word**: it accepted a
  known word ("the", "Ælfric", Gierke's "vacant") dropped as junk. Each
  record now names the layer words it replaced as junk (`Reread.junk_words`;
  **lines.json goes to version 3**, so layout must run again on older
  runs), and the check accepts only those.
- The check did not tie a `source_dash` change to an epigraph's source,
  a group on a footnote gave a misleading error, and 8 guards had no
  test that failed when broken.
- Gierke 63's junk "14." beside Tesseract's "146" is now replaced (a
  layer number whose digits begin the Tesseract number's).
- The count of words read twice is defined in reocr §4 and counted by
  `scripts/count_read_twice.py`: Domesday 30 → 5, Gierke 12 → 0, Stubbs
  6 → 5, Haskins 0 (4d9f1e9 → 2305891). A wider definition (any box
  within 4 pt) gives 40 → 11, 32 → 18, 11 → 10: its extra words are
  mostly body words at the column's edge beside the same word in a
  note.

Checks at 2305891: 2,382 passed and 8 xfailed in 66.8 s; whole_book 80
passed in 644 s. No record's choice of reading changed on the four
books.

## Tasks 3.1 to 3.3: notes collected at the back (stream `notes`)

Merged at 74253e2 (9b375a2 to 887685e). A hanging number starts a
paragraph; a bare number is an endnote marker in a run from 1; notes
are grouped per chapter, numbering restarting, each group's heading
kept as `Note.group`, and references matched within their chapter's
group. On the owner's books:

| | endnotes | groups with a heading | linked | linked to the wrong chapter |
|---|---|---|---|---|
| Turney | 613 (target 580) | 11 of 11 | 530 (target 450; 0 before) | 0 |
| Haynes | 632 | 18 | 584 (127 before) | 0 (120 before) |

Decided by the orchestrator on the stream's measurements: the group
headings' likeness to their chapter's title is 0.85, not 0.75 (a heading
is 0.94 to 1.00 alike to its own chapter, up to 0.76 to another); a
group without a heading takes the chapter after the previous group's;
three Turney causes fixed with rules that fire nowhere else on the
eight books: page 262, where the right column's note numbers fell into
the left column's lines; page 258, where the OCR read the first "1" as
"x" (a misread marker takes value 1 from its place, keeping its printed
reading); page 268, a stray "/" under a heading. The public-domain
books' notes scores did not change (Domesday 1,279, Haskins 65, Mariéjol
567); §12's count of Gierke's linked endnotes was corrected to 215, the
number before this work.

## Review 3: work package 3

Of 887685e, by two reviewers (fidelity; spec, tests and conventions).
No word was lost or added on the eight books. What mattered, all fixed
(1201131 to ab79cbb):

- **References linked to a note of another number**, on Haynes pages
  234 and 301-302, where the OCR merged a note into the one before: a
  reference is now refused when its number differs from the note's and
  another reference reads the note's number, or when no note of the
  group reads its own number. Haynes: 582 linked (584 before), 0 to a
  note of another number (3 before). Turney keeps its 530, whose 8
  differing numbers are OCR misreadings of the reference ("3" for a
  printed "5"). Gierke links 208 (215 before): 2 of the 7 lost were
  wrong; the other 5 were not checked against the page.
- **A paragraph of a note could become a new note 1**, and a short note
  a group heading (on built pages; no book does it today): the
  misread-marker rule now needs a hung line, and only note 1 can be
  taken as a group heading.
- **Table rows split into paragraphs** by the hanging-number rule
  (Domesday 158, 425, 479; Gierke's contents): the word after the
  number must start with a letter or a quotation mark, and contents
  pages are left out. Domesday has 2,382 blocks (2,381 before the plan);
  its paragraph scores stay 0.860 / 0.891 (baseline 0.860 / 0.889).
- Nine rules had no test that failed when broken; dead code; a group's
  reach could run into a later group's chapter; constants written
  twice.

Checks: 2,423 passed and 8 xfailed in 62 s; whole_book 88 passed;
galley-eval's notes scores unchanged (Domesday 1,279, Haskins 65,
Mariéjol 567).

## Tasks 4.2 and 4.3: epigraphs and page breaks in structure

1e7c2b7, 36f1561. Epigraphs are found after each level-1 heading, or
as a page of their own. On the owner's books: Turney 13 epigraph blocks
(page 13 holds only one), Haynes 21, 8 of them verse, each with its
source and the dash recorded; none on the public-domain books. A page
break now ends a paragraph after a short last line that ends a
sentence: Haskins 0, Stubbs 2, Domesday 10, Gierke 32, Mariéjol 24 such
cuts. Of 10 read against the page images, 5 are right paragraph ends,
1 is inside a table, and 4 follow a footnote that structure left in the
body, where the text above the note runs on to the next page: the
continuation, before glued to the note, is now a paragraph of its own.
Neither is right; taking those notes out of the body is structure §11's
work, not this plan's.

galley-eval's paragraph precision / recall, before → after: Haskins
0.908 / 0.902 unchanged; Stubbs 0.809 / 0.632 → 0.805 / 0.632 (its 2
cuts are right on the page); Domesday 0.860 / 0.891 → 0.859 / 0.897;
Mariéjol 0.729 / 0.753 → 0.721 / 0.754 (footnotes its OCR left in the
body). Stubbs' recall had already fallen from the baseline's 0.733 in
the earlier work packages: being looked into.

## Stubbs' paragraph recall, and the evaluation's reference cut

After task 4.3 Stubbs' paragraph recall read 0.632 against the
baseline's 0.733. Bisected, it fell at 6008a0e, which excluded Stubbs'
publisher's lists (pages 322-337) from galley's run: the reference text
still held them, and the paragraph score, unlike the word scores, does
not skip excluded pages, so the lists' 81 boundaries counted as missed.
galley got no worse. The evaluation now ends Stubbs' reference at the
lists (`reference_ends_at`, 6c29627 and 5c1b394), and the baseline was
scored again with it, galley at 9715a93, into
`runs/owner-books-baseline-cut/` of the main checkout. Against it, at
5c1b394: Stubbs 0.811 / 0.801 → 0.809 / 0.801; Haskins 0.885 / 0.902 →
0.908 / 0.902; Domesday 0.860 / 0.889 → 0.859 / 0.897; Mariéjol 0.732 /
0.753 → 0.721 / 0.754, a fall beyond the plan's 0.005 that comes from
the page-break cuts of task 4.2 (review 4). Haskins' notes as notes
66 → 72, with the right reference 61 → 65, none left in the body (6
before).

## Review 4: work package 4

Of 36f1561, by two reviewers. No word lost or added on the eight books;
all 13 of Turney's epigraphs match the page images. What mattered,
fixed (18780a1 to d7e1973, merged at c9263f0):

- **The page-break rule cut sentences in two** where a footnote left in
  the body was the page's last line (Domesday 131: "We think it" /
  "highly probable that"). No cut now when the next page goes on in
  lower case, nor when the last line is a footnote's first (it starts
  with a note marker). Cuts on the pass that writes blocks.json: Turney
  24, Haynes 28, Haskins 0, Stubbs 2, Domesday 6, Mariéjol 3, Kadesh 3,
  Gierke 12. Still wrong, read on the images: Gierke 156 (a two-line
  footnote) and Kadesh 33 (layout's order beside a map).
- The counts first reported were taken on structure's first pass;
  nine epigraph and page-break conditions had no test that failed when
  broken; a dashed source line needs a letter or digit.

Paragraph scores against the cut baseline: Mariéjol's precision is back
to 0.727 (0.732 at the start; within the 0.005 tolerance), the others
as before.

## Task 5.2: spaced signs and case splits in structure

8a63a8f, 72c7959, 13f7433. In English books a "?", ";", ":" or "!" set
apart by a space is attached to the word before; in French the space
becomes a no-break space. Three rules the wiring needed (72c7959): a
case split needs 3 lower-case letters after the capital (Domesday's
"forðon" and "forðan", one Old English word each on the page, are no
longer split); a sign holding a note reference (";13") is attached only
if the word stays a reference; the fidelity check accepts a margin-note
word joined at a lost hyphen and then given a sign.

| book | signs attached | no-break spaces | case splits |
|---|---|---|---|
| Haskins | 89 | 0 | 2 |
| Stubbs | 1,010 | 0 | 9 |
| Domesday | 2,112 | 0 | 1 |
| Gierke | 888 | 0 | 0 |
| Kadesh | 97 | 0 | 0 |
| Mariéjol | 0 | 1,149 | 8 |

Body error rates at blocks fell (the reference text attaches its
signs): Haskins 0.023 → 0.020, Stubbs 0.053 → 0.033, Domesday 0.075 →
0.058; Mariéjol 0.310. Domesday's notes whose reference is right went
from 1,279 to 1,277 although galley's links are the same before and
after: the scorer's alignment of a note's reference word changes when
a sign is attached to it. The reference literals changed only by
attached signs (73) and no-break spaces (16). Haskins 22's "theAvre" is
split on the whole book; its excerpt never prints "Avre" whole, so the
excerpt's test stays a strict xfail.

## Review 5: work packages 5 and 6

Of caa422c, by two reviewers. The text of the six public-domain books,
read without white space, is the same before and after; Domesday's
1,493 note links are the same set before and after task 5.2, so its
notes whose reference is right, 1,279 → 1,277, is the scorer's
alignment of a reference word with a sign now attached, not a link
lost. Haynes' EPUB was read: 21 epigraphs with their sources, 8 in
verse, 18 note-group headings each before its own endnote. What
mattered, fixed (0f07802 to 1611288):

- **Two printed words glued into one** where the OCR read a speck as a
  sign before a word (Gierke 29 "universitas;is,"; 6 in the six books):
  a sign is attached, or given a no-break space, only when no letter
  follows it. Counts now: signs attached Haskins 89, Stubbs 1,007,
  Domesday 2,112, Gierke 885, Kadesh 97; Mariéjol 1,036 no-break spaces.
- Four rules had no test that failed when broken (the H half of the case
  split, captions, the order checks of both passes); the fidelity check
  followed only one change after a lost-hyphen join; a rule written
  twice; a stale count.

The default run is 67.9 s (2,494 tests) against 51.7 s at the plan's
base: the four new excerpts of task 1.1, whose setup runs every stage
on each, grew the excerpt fixture from 14.6 s to about 25 s; the rules
of this plan cost about 2 s.

Turney's epigraph sources are printed without a dash; the EPUB writes
one before every source (structure §25), so all epigraphs look the
same.

## Task 7.1: the final measurement

At f5cdf4e. `uv run galley-eval run` (574 s), in `runs/owner-books-final/`
of the main checkout, against the cut baseline (galley at 9715a93,
Stubbs' reference ended at its publisher's lists on both sides):

| book | body error rate, blocks | paragraph precision / recall | headings in heading blocks | notes whose reference is right | margin notes as margin notes |
|---|---|---|---|---|---|
| Haskins | 0.023 → 0.020 | 0.885 / 0.902 → 0.908 / 0.902 | 18 → 18 | 61 → 66 | – |
| Stubbs | 0.053 → 0.033 | 0.811 / 0.801 → 0.809 / 0.801 | 25 → 26 | – | 291 → 291 |
| Domesday | 0.075 → 0.058 | 0.860 / 0.889 → 0.861 / 0.897 | 23 → 23 | 1,278 → 1,277 | 579 → 577 |
| Mariéjol | 0.310 → 0.310 | 0.733 / 0.753 → 0.727 / 0.753 | 26 → 26 | 567 → 567 | – |

reocr §9's targets all hold (Stubbs' index 0.985 / 0.964; margin notes
291 and 577; body error rates 0.033 and 0.058; Haskins' index 0.094).
Three scores fall beyond the plan's tolerances, none by a lost word:

- Mariéjol's paragraph precision, by 0.0051: the heading rule makes 4
  more headings there, three of them lines the OCR garbled (pages 57,
  194, 402), one splitting the bibliography's title (page 14). Accepted:
  Mariéjol is the unreadable scan.
- Domesday's notes whose reference is right, by 1: galley's links are
  the same set as before plus two on page 443; the scorer's alignment
  of a reference word with a sign now attached moved.
- Domesday's margin notes found as margin notes, by 2: galley's margin
  notes are the same on every page but 156, which gained one; see task
  7.2.

`uv run pytest -m whole_book` with the owner's PDFs present: 106
passed in 515 s. The eight EPUBs in `runs/owner-books/` of the main
checkout, each with 0 errors and 0 warnings from epubcheck: Haskins
175 s, Stubbs 317 s, Domesday 359 s, Mariéjol 28 s, Kadesh 5 s, Gierke
65 s, Turney 11 s, Haynes 15 s (the first three far slower than in the
last plan; see task 7.2).

## Task 7.2: the checks by eye

Read by a subagent against the pages rendered at 150 dpi, on the
EPUBs' `book.md` built at f5cdf4e.

- **Turney's chapter openings**: 11 of 11 right (10 chapters and the
  Introduction: heading, label, epigraphs with their sources). Its
  note groups: 11 headings right; of 22 first notes, 21 linked right.
- **Haynes' chapter openings**: 18 checked (16 chapters, Introduction,
  closing chapter), heading and label right on all, all epigraphs found
  with their sources; one verse epigraph on page 87 keeps a turnover
  line as a line of its own, and two lose their stanza breaks. Its
  note groups: 18 headings right; of 36 first notes, 35 linked right.
- The two unlinked notes have the same cause: the reference is a
  superscript after a year ("1959.²"), which §12's glued-number rule
  does not take (it needs a letter before the digits). About 5 such
  references in the two books.
- **Reference pages changed by the plan**: 43 changes checked, 42 right.
  Wrong: Stubbs 51, a ";" attached to the word before it in the layer's
  order, which was already wrong around a cut-in margin note.
- **Domesday's 2 margin notes**: galley's blocks for them (pages 161 and
  357) are the same before and after; the scorer now aligns two of
  their words with the same words in body paragraphs. galley did not
  get worse.
- **The slow builds were load**: Haskins rebuilt alone took 17 s
  (analyze 6.4, extract 1.2, layout 7.8, structure 0.7, markdown 0.3,
  epub 0.4), byte-identical to the 175 s build made while the
  whole-book tests ran.

Seen, outside the plan: Turney's two newspaper pages reproduced as
plates (174-175) become a level-1 heading; the OCR misreads some of
Haynes' heading words ("AMD" for "AND").

## For whoever next revises a skill or writes a plan

- Committing in a worktree where a subagent works swept the subagent's
  unfinished file into the orchestrator's commit (`git commit -a`).
  Commit only named paths, and only in a tree no agent works in.
- A tolerance checked against a baseline must use the same reference
  text on both sides: excluding pages from galley's run without cutting
  them from the reference made Stubbs' recall fall by 0.10 with no
  change in galley.
- Counts reported by a task were twice taken on an intermediate pass
  (structure runs its body pass twice); a count should be taken on the
  file the stage writes.
- Three times a fix made a measured side effect elsewhere (junk back in
  the text, a tie flipped, a sentence cut): measuring the whole books
  before and after each rule change, in the task, caught them before
  review only when the task asked for it.
- Running the slow tests and the EPUB builds at once made builds ten
  times slower; time builds on an idle machine.
