# Work report: owner's books

The work of the plan `docs/plans/owner-books.md`, written as it goes, for
the owner. Started on 17 November 2026 on branch `plan/owner-books`.

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
