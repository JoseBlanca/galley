# Work report: clean text

The work of the plan `docs/plans/clean-text.md`, written as it goes, for
the owner. Started on 17 November 2026 on branch `plan/clean-text`.

## Before the first task

- **Specs.** `docs/specs/extract.md` and `docs/specs/front-matter.md`
  and the two-page running head of `docs/specs/structure.md` §3 were
  read by the first-reader and the spec-reviewer once; the reviewer's six
  findings were taken (straight quotes split off "told.", a split between
  two marks, excerpt checks that could not fail, the front matter's
  silent dependence on `contents_pages`, the evaluation tool hiding a
  lost preface start, two smaller ones). One answer of the writer was
  accepted against the reviewer: "introduction" is not a preface name,
  because without `contents_pages` it would end Stubbs' front matter at
  its page 20 and drop 1,182 words. `docs/specs/reocr.md` went through
  the spec-reviewer twice. The second review found that re-reading
  Stubbs' cut-in notes still replaced body words with Tesseract's junk
  (at least 34, "change" read "NE" on page 49) and took the page number
  on 8 pages; the spec now replaces no word of a body row, at a cost of
  margin notes found on Stubbs (326 → 293 of 467 in the writer's
  simulation).
- **One change to a spec by the orchestrator** (9e65986): a changed
  reference page is accepted when a script shows each change is a join,
  a split or a regrouping, and listed for the owner's sheet, instead of
  the owner checking each page before the commit.
- **The baseline**: `uv run galley-eval run` at b24b3e2 (code equal to
  `main` at 4542207), 2 min 1 s on the Mac17,9, copied to
  `runs/clean-text-baseline/` of the main checkout. It equals the final
  scores of `docs/reports/structure-second.md` on every figure the
  report gives there (notes whose reference is right 59, 1,277, 543;
  margin notes 241 and 519; index .829/.789, .991/.965, .993/.986;
  headings 18, 25, 23, 26).
- **Open points** of the specs, put to the owner in chat on 17
  November 2026, unanswered so far; the plan builds their meanwhiles.
