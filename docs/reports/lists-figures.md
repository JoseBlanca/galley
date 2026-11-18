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
