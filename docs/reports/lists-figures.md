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
