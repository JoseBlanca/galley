# Work report: the evaluation tool

The report of `docs/plans/evaluation.md`, which builds the evaluation
tool of `docs/specs/evaluation.md` and galley's word list, and ends with
the baseline scores of galley on four books. Written as the work goes,
for the owner. Started on 15 November 2026.

## Before the first task

Checked on 15 November 2026 in `.claude/worktrees/evaluation`, branch
`plan/evaluation` (from the spec and plan commits, not yet on `main`):

- `pandoc 3.14`, `tesseract 5.5.4`; `combine_tessdata`, `dawg2wordlist`
  and `epubcheck` installed.
- The four PDFs of the evaluation set and the two earlier whole books are
  in `samples/public_domain/` of the main checkout.
- `uv run --locked pytest`: 461 passed in 15.26 s.
