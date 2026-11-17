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

## Work package 1: foundations

Done as planned. Task 1.1 (79cb64b): `pages.json`, `words.json` and
`lines.json` at version 2, the page kind and removal reason
`front_matter`, the `Reread` record (layout writes none yet), the
config keys `front_matter_end` and `reread_footnotes`, and the fidelity
check at layout that swaps a kept record's words. It also added
extract's case for a `front_matter` page (each word a removal), which
the type checker required once the page kind existed; analyze makes no
such page until work package 3. Task 1.2 (36e0e79): the excerpts
`haskins_front` (11 pages, 314 KB), `domesday_front_flow` (10, 487 KB)
and `gierke_front_flow` (10, 919 KB); every page has a text layer.

Checked by the orchestrator at the merge: deliverable 1's command passes
and lists 13 tests; deliverable 2, 8; deliverable 3, 6; deliverable 4
prints nothing; the evaluation tool's 346 tests pass; the default run
1,731 passed in 30.6 s, with 8 threads 53.7 s; `-m whole_book` 32
passed (task 1.1's run, 254.8 s). The excerpt fixture's setup went from
about 4.5 s to 6.0 s.

Review: this package is reviewed together with work package 2, which
first reads what it defines.

## Task 6.1: the evaluation tool (stream `eval`)

Done (8bbfe10), merged. The tool counts the dropped front pages and the
reference words before galley's first word as `front_matter_not_scored`
(the spec now says it counts both; 0 on every book until work package
3); scores the margin notes as a part of their own; and gives
`ocr_confidence_mean` over the words galley outputs, kept re-readings
included. Deliverable 1: 10 tests collected.

What changes the comparison with the baseline: with galley unchanged,
taking the margin notes out of the body moves 1,350 differences on
Stubbs and 1,510 on Domesday from the body to the new part. The body's
error rate at blocks falls from 0.142 to 0.129 on Stubbs and from
0.100 to 0.093 on Domesday, and the margin notes' own rate is 0.728
and 0.600. Later body rates are compared with these, not with the
baseline's. Haskins and Mariéjol are unchanged.
