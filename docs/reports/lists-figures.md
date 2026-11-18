# Work report: lists, printed contents and figures inside text pages

The report of the plan `docs/plans/lists-figures.md`, kept as the work
goes, for the owner. Started on 18 November 2026.

## Before the first task

The plan was written from `docs/specs/figures.md` and sections 29 to 33
of `docs/specs/structure.md`, both written on 18 November 2026 after the
owner reported three problems in the EPUB of Haynes' book: a list of six
dash items run into one paragraph, the printed contents run into one
paragraph, and a picture inside a page lost with its caption left in the
text. The owner said to go on without waiting, so four open points were
settled by the orchestrator for the owner: the reader's own list
markers; the contents title as a heading; pictures without a caption
kept; the format changes of the figures spec, with `Figure.kind`.

Starting point: `main` at 83f2754, 2,494 tests passing in 62 to 64 s.
The evaluation baseline is `runs/owner-books-final/` of the main
checkout (same code).

## Tasks 1.1 and 1.2

Done as planned: two excerpts, `kadesh_29-38` (10 pages) and
`domesday_lists` (11 pages, 7 of them body pages for its measures), with
15 expected files transcribed from the page images at 300 dpi; the
formats at pages.json 3, words.json 3, lines.json 4, blocks.json 5.
Checks at 49abd8c: 2,535 passed in 64.25 s, and with 8 threads in 102.6 s
(orchestrator's run). Changes outside the listed files: per-excerpt
literals in five test files; markdown refuses list items and contents
entries until work package 6 rather than dropping their labels;
galley-eval's kind enums. The excerpts differ from their whole books in
small ways that the test literals record: on `domesday_lists` a few table
numbers of pages 157 and 158 become margin notes; on `kadesh_29-38` two
blocks of page 38 are quotes.

The 15 expected files were checked against the pages rendered at 300 dpi
by a second subagent: 14 match. In the file of Domesday page 143 the
description of the printed page listed an item "(iii)" that the page
does not print; it is removed. The files leave out, by design, text
their tests do not measure (page 143's margin note and footnotes, page
156's opening paragraph, the engraver's credit on Kadesh page 34).

## Tasks 6.1 and 6.2 (stream `markdown`)

Done as planned and merged at 475eafb: markdown writes list items as
Pandoc lists and the printed contents as one entry per line, nested and
linked to its heading; the fidelity check at the markdown boundary reads
both. 23 tests of markdown lists, 21 of the fidelity check (one added on
the orchestrator's request: each contents link must go to its own
entry's heading, not only to some heading). epubcheck accepts a book
with both. Two choices not in the plan: footnotes of a list's items are
defined after the whole list, so that their definitions do not split
it; Pandoc reads a list starting at "v." or "x." as letters, which the
reader shows the same way, so it is documented and left.

The default run grew past a minute while three streams ran tests at once
(78 to 89 s at a load of 9 to 13, with the shared excerpt fixture
passing its 30 s timeout); the base commit did the same under that
load. It is measured again on an idle machine at the end.

## Tasks 2.1 to 2.3 and 3.1 (stream `figures`)

Done and merged at a14924e. analyze finds exactly the spec's 56 in-page
figures on the eight books, and nothing else: Kadesh 17 (6 maps, 11
blocks of hieroglyphs or Arabic), Haynes 25, Turney 14; none in Haskins,
Stubbs, Domesday, Mariéjol or Gierke (whole_book tests, 9 passed in
71 s). The search adds 6.8 s on one thread to Haynes' 436 pages, as the
spec measured, so WP 2's decision point holds. extract cuts each figure
at 300 dpi; layout keeps the words inside a figure's box in a region of
their own, never re-read.

Two files outside the stream's list, approved by the orchestrator: a
one-line guard in `structure/__init__.py` (the plate rules run only on a
page whose figure is a plate; without it five Kadesh text pages became
plates and lost their paragraphs, and structure stopped on whole Kadesh
and Turney), and the hook in `layout/__init__.py` that calls the new
`layout/_figures.py`.

Settled by the rule as written, against what the expected files of
`kadesh_29-38` guessed: the boxes of the maps on pages 33 and 36 take in
their scale bars and the words on them ("JO Km.", "icM", "SM."); on page
37 one of three "Var." labels falls inside the box of its hieroglyphs (its
middle 0.5 pt inside), so it is removed from the text with a record and
still shows in the picture. On page 33 the box starts 9.1 pt below the
map's frame, because the line of text just above hides the frame's top
row from the 12 pt squares; the picture loses a strip of its frame. Left
as it is, and listed among the known defects. The expected files are
updated in task 3.4.

The default run, at the merge, under the load of the lists stream: 2,613
passed in 79 s with a 120 s per-test limit.

## Review of work packages 1 and 2, with task 3.1

Four reviewers (spec, tests, fidelity, conventions) on 55128c4. Every
finding held and was fixed (6dc6aec to afc757d, spec commits first). What
mattered:

- **A figure in the footnotes rearranged the notes.** Layout took the
  figure's words out before laying out the page, so the rest of the page
  was laid out differently: on Kadesh page 52, 7 footnotes became 4 and
  note text ran out of order. Layout now lays the page out with all its
  words and then moves the figure's words into the figure's region. On
  Kadesh, Turney and Haynes every region outside a figure now equals
  main's less the figure's words. Kadesh has 149 notes against main's 152:
  main made 4 notes out of map labels and hieroglyph junk on pages 33 and
  52; page 51's junk makes one note until task 3.2 removes figure words.
- **A re-read could read a figure's words a second time** into the
  footnotes (shown with a stand-in for Tesseract). Every re-read now drops
  Tesseract's words inside a figure.
- **Boxes took in nearby ink** on Kadesh 41, 44 and 51 (a quotation
  number and a third of its hieroglyphs; the rule under a running head).
  A group is now cut at a 6 pt band without ink beside a run of 72 pt of
  ink (a rule or a frame's edge: these measure 96 to 154 pt; runs beside
  bands inside pictures, at most 30 pt). Boxes changed on Kadesh 40, 41,
  44, 50, 51, 53 and Turney 173 only, checked by eye; the counts stay 56.
- **An untested fidelity condition** (a list marker change must rejoin
  to the word it replaced) now has failing cases.
- Untested branches of the box rule, tests that ran no galley code, a
  duplicated word-in-box test, names and docstrings: fixed.

Left: Kadesh 44's first box stops 4 pt above its last row of hieroglyphs
(the next line's words touch those squares; an overhang rule moved 12
other boxes and was reverted). Kadesh 33's box starts 9 pt below the
map's frame (the spec's table now says so).

Checks at afc757d: 2,633 passed in 88 s with a 120 s per-test limit, the
machine loaded by the lists stream; figure whole_book tests 10 passed.
