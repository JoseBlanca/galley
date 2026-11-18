# Work report: lists, printed contents and figures inside text pages

The report of the plan `docs/plans/lists-figures.md`, kept as the work
goes, for the owner. Started on 18 November 2026.

## Summary

**Done**, on 18 November 2026, on branch `plan/lists-figures`, not
merged. It answers the three problems the owner found in the EPUB of
Haynes' book: a list run into one paragraph, the printed contents run
into one paragraph, and pictures inside a page of text lost with their
captions left in the text.

What exists now:

- **Lists.** A run of items that start with a dash, a bullet, a number or
  a letter, set with a hanging indent, is a list: the EPUB shows the
  reader's own bullets or numbers. Haynes has 11 items in 2 lists;
  Domesday's tables become 8 lists of 40 items until tables are handled;
  no other book has one. Numbered paragraphs stay paragraphs.
- **Contents.** The printed contents is one entry per line, nested by
  depth, each linked to its chapter; printed page numbers are kept in
  galley's files but not shown. Haynes 22 entries, Turney 16, all linked
  to the right chapter; 72 links on the public-domain books, one wrong
  (Gierke's "NOTE" to its "NOTES.").
- **Figures inside a page.** A picture printed among the text is cut out
  at 300 dpi and placed where it was printed, with its caption under it;
  the words the OCR read inside it leave the text, with a record. Haynes
  25 figures, all whole, captioned and in place; Kadesh 17 (6 maps with
  captions, 11 blocks of hieroglyphs or Arabic as images); Turney 14.
- **Scores** of the four public-domain books: no fall beyond the plan's
  tolerances; Stubbs' and Mariéjol's paragraph scores rose slightly.
  Every test passes: 2,777 in 69 s, and 144 on whole books. The eight
  EPUBs in `runs/lists-figures/` of the main checkout pass epubcheck with
  no error or warning.

Settled for the owner while they were away, each easy to change: the
reader's own list markers rather than the printed ones; the contents
title as a heading; pictures without a caption kept; a dash before
epigraph sources in every book (the owner's choice).

Still wrong:

- **Turney's insert of reproduced pages (164 to 179).** A reproduced
  newspaper page or cartoon is full of printed words, and the rule finds
  a picture as ink with no words: three pictures are cut short, one
  caption is merged into a paragraph, two figures are placed after page
  180's first paragraph, which gains 9 words of a cartoon. Until a rule
  for such pages exists, `exclude_regions` in Turney's config fixes them.
- Haynes' contents: pen circles on the scan cost two entries their
  chapter number; one page number misread "3x3" stays in its title.
- Gierke's table of the titles of its notes (pages 61 to 67) comes out
  in 75 pieces, as messy as before: tables are not handled.
- Kadesh 44's first box stops 4 pt above its last row of hieroglyphs;
  Kadesh 33's map loses a 9 pt strip of its frame.
- The default run is 69 s, under a minute and a bit, by under a second
  under the plan's limit.

What is asked of the owner:

1. The order to merge `plan/lists-figures` into `main`. After it, runs
   made before must redo analyze and the stages after it: four file
   formats changed (pages.json 3, words.json 3, lines.json 4,
   blocks.json 5), and galley refuses the old files, naming the stage to
   run.
2. A look on the Kindle at `runs/lists-figures/haynes/book.epub`: the
   list of six stereotypes in the introduction, the contents with each
   entry opening its chapter, and two figures (one with its caption below,
   one beside); at Turney's insert; at Kadesh's maps; and whether the
   Kindle shows the contents without bullets (never tried on one).

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

## Work packages 4 and 5 (stream `lists`), and the review of 4 to 6

Done and merged. Haynes has 11 list items in 2 lists (the six dash
descriptions and a numbered list of five); Domesday 40 items in 8 lists
on pages 156 to 159 (its tables, as lists until tables are handled); no
other book has a list. Every printed contents page is cut into entries,
linked to their chapters: 72 links on the public-domain books, all right
but Gierke's "NOTE" → "NOTES.", as the spec expects; Haynes 22, Turney 16.

**Decision point of WP 5.** The re-check of task 5.4 failed on Gierke's
analytical summaries (pages 52 to 60): the rule of one reference per two
lines cut 2 of its 34 summaries into one entry per line, worse than the
paragraph a reader had before. The rule is now one per five lines, the
smallest value that keeps all 34 whole; no other book changes. Gierke's
pages 61 to 67, a two-column table of the titles of its notes, stay
messy: margin notes cut them into 75 pieces and page numbers sit out of
place. That is no worse than before, and is left with tables.

**Review** (four reviewers on 1f9b89a, all findings held and were fixed):

- **A title's last word could be taken for its page number** ("Maldon,
  991"), and page numbers are not shown or checked, so the word would be
  lost silently. A page number is now taken only when it is a range,
  follows "p."/"pp.", leader dots or a space of 11 to 20 pt, or ends
  within 4 pt of the page's longest contents line (measured: Haynes and
  Turney print 11.5 to 14.9 pt spaces, other spaces in entries reach
  10.2; the other books' numbers end within 3.7 pt of the edge). Domesday
  keeps one "290." in its title; Gierke's table loses 43 doubtful page
  numbers, which stay in the text. The rise check the reviewer suggested
  was not added: Gierke's two-column table gives numbers out of order.
- **Nothing checked the numbers a numbered list shows**: the check now
  compares each Pandoc list's start, style and delimiter with its first
  item's label.
- Contents entries are no longer searched for note references; a figure
  between two items no longer ends a list; the list-marker rules live in
  one module, `src/galley/list_markers.py`, used by structure, markdown
  and the fidelity check; tests that pinned nothing now fail when their
  rule breaks (each seen to fail), and the whole-book tests assert exact
  counts.
- The four contents pages whose expected output changed were checked
  against their images by a second subagent: all match.

**The per-test time limit** now counts a test's own body only
(`timeout_func_only`): the session fixture that runs every excerpt takes
about 30 s alone, and under the load of parallel streams it errored
hundreds of tests on setup.

Checks after the merge: 2,723 passed in 71.6 s, and with 8 threads in
114 s (120 s limit).

## Tasks 3.2 to 3.4 (stream `figure-blocks`)

Done at a7f931b. Each in-page figure becomes a figure block at its place
in the text, its caption taken out of the paragraph; the words the OCR
read inside the picture are removed with the reason `figure_text`.
Haynes 25 figures, all 25 captioned; Turney 14, 11 captioned, and page
174 no longer gives a false heading; Kadesh 17, its 6 maps captioned.
Kadesh has 148 notes: main's 152 less 4 made of picture junk. The EPUBs
of Kadesh, Haynes and Turney pass epubcheck with no error or warning,
each figure with its image and caption.

One spec change (c9f2665): a caption is looked for outside the figures'
regions. A mark read inside the picture on the same row as a caption
line cut three captions short (Haynes 310, Turney 174 and 176).

The default run: 72.3 s on 2,761 tests (orchestrator's run, idle
machine), past the plan's 70 s. It is dealt with in work package 7.

## Review of work package 3

Four reviewers on 3d272e1; fixed in 8818d42 to e5c58ea, spec commits
first. What mattered:

- **Turney's captions beside its newspaper pages (175, 176) were cut
  short**, because layout put a caption's last row in one line with the
  picture's lettering; the leftover words then ran across pages into page
  180's first paragraph, and the figures of pages 175 to 179 were placed
  after it. Beside a figure, each next row now gives the caption only its
  words on the caption's side. Captions 15 and 17 are whole (41 and 33
  words). Left: the cartoon's lettering under figure 17 lies 3.7 pt below
  the figure's box, so it stays text and still opens page 180's first
  paragraph; no structure rule separates it, an `exclude_regions` entry
  in Turney's config would.
- A number printed beside the first row of a figure (Kadesh 40, "18.")
  came after the image: a line beside a figure now counts as above it
  when it is the only body line beside it (the wider rule moved Kadesh
  33's map after its side paragraph, which the page contradicts).
- Words of a caption's label row past the figure's side now join the
  caption (none in the three books).
- Nine rules that no test guarded have tests, each seen to fail with its
  rule removed; the whole-book tests assert each caption's word count.
- One figure type, one block builder, figure placement in a module of its
  own.
- Not fixed: the head-line comparison that a caption could upset; no
  caption takes words from a head line in the three books.

Whole books against 3d272e1: Kadesh one block moved (page 40); Haynes
identical; Turney captions 15 and 17 whole. epubcheck passes on the
three EPUBs; all 56 figures have their image and caption.

Checks at e5c58ea: 2,776 passed in 72.9 s; with 8 threads in 116 s;
figure whole_book tests 21 passed.

## Task 7.1: the measurement

Scores at blocks (`galley-eval run`, galley at eaed36b, whose `src` is
the final code's) against `runs/owner-books-final/`:

| book | body error rate | paragraph precision / recall | headings in heading blocks | notes whose reference is right | margin notes as margin notes |
|---|---|---|---|---|---|
| Haskins | 0.020 → 0.020 | 0.908 / 0.902 → same | 18 → 18 | 66 → 66 | – |
| Stubbs | 0.033 → 0.033 | 0.809 / 0.801 → 0.818 / 0.848 | 26 → 26 | – | 291 → 291 |
| Domesday | 0.058 → 0.058 | 0.861 / 0.897 → same | 23 → 23 | 1,277 → 1,277 | 577 → 577 |
| Mariéjol | 0.310 → 0.310 | 0.727 / 0.753 → 0.730 / 0.765 | 26 → 26 | 567 → 567 | – |

Every tolerance of the plan holds, and every target of reocr §9.
Domesday's tables (page indices 156 to 159) show only in the scorer's
tables part, as expected. Two smaller falls, both by design:

- Haskins and Stubbs lose 9 and 10 tokens: printed page numbers of their
  contents pages, which the EPUB no longer shows (structure §31).
- "Blocks of the right kind" fell on Stubbs (424 → 386) and Mariéjol
  (1,104 → 1,090) because the scorer had no kind for a contents entry. A
  row was added to `docs/specs/evaluation.md` and to galley-eval (a
  contents entry holding a reference paragraph or quote is of the right
  kind); rescored, Stubbs gives 427 and Mariéjol 1,105.

`uv run pytest -m whole_book`, the owner's PDFs present: 144 passed in
585 s. The eight EPUBs in `runs/lists-figures/` of the main checkout
pass epubcheck 5.4.0 with 0 errors and 0 warnings; build times Haskins
18 s, Stubbs 52 s, Domesday 99 s, Mariéjol 27 s, Kadesh 6 s, Gierke 66 s,
Turney 12 s, Haynes 16 s.

The default run: 2,777 passed in 69.0 to 69.8 s (three runs, idle
machine), under the plan's 70 s by less than a second; 62.6 s on `main`
for 2,494 tests. The 7 s of growth is spread out: the excerpt runs take
2.9 s more, about 280 new tests about 4 s. Cutting the two new excerpts
would save under 1 s (Kadesh's tests use 9 of its 10 pages), so they
were not cut; two epubcheck calls were merged into the one-call checks
instead (8198ec4, 129caaf), saving about 2.5 s.

## Task 7.2: the checks by eye

A subagent rendered every figure page of Kadesh, Haynes and Turney with
the figure's box drawn on it, and read the lists and the contents
against their pages. Counts only for the owner's books.

| book | picture whole | caption | place | lists | contents entries / links |
|---|---|---|---|---|---|
| Kadesh | 17 / 17 | 17 / 17 (6 maps; 11 uncaptioned by design) | 17 / 17 | – | – |
| Haynes | 25 / 25 | 25 / 25 | 25 / 25 | 11 / 11 items | 22 / 22, 22 / 22 |
| Turney | 11 / 14 | 13 / 14 | 12 / 14 | none printed | 16 / 16, 16 / 16 |

Wrong, and not fixed in this plan:

- **Turney's insert of reproduced pages (164 to 179).** The rule finds a
  picture as ink no word touches, and a reproduced newspaper or cartoon
  is full of printed words. On page 175 the masthead, headline and photo
  caption fall outside the picture and become a paragraph, two headings,
  a margin note and a quote; on 167 a film still's label and on 176 a
  cartoon's caption line are cut off the image; caption 5 on page 167 is
  merged into one 163-word paragraph with the captions of facing plates;
  the second figure of 176 and the figure of 179 come after page 180's
  first paragraph, which gains 9 words from the cartoon. A rule that
  takes printed text inside a picture's frame into the figure is a plan
  of its own; until then the owner can fix these pages with
  `exclude_regions` in Turney's config.
- **Haynes' contents**: pen circles on the scan around chapter numbers
  1, 6 and 7 are read as text, and the first two numbers are lost into
  the title; "Implications"' page number, read "3x3", stays in its
  title.

Nothing lost, gained or reordered next to a figure in Kadesh or Haynes;
the garbled text of Kadesh pages 38 and 51 is the same in the previous
run.
