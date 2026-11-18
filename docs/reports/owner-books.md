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
`source` and `group` default to empty, so no other stream's code had
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
