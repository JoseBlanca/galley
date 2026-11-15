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

## Work package 2: galley's word list (merged, review pending)

Task 2.1 done in commit 4a662a7, merged into `plan/evaluation`.
`word_list(language, cache_dir=...)` extracts Tesseract's dictionary with
`combine_tessdata -u` and `dawg2wordlist` (adapted from ocr_lab's
`setup.sh`) and caches it under `~/.cache/galley/wordlist/`.

- Deliverable 1: `uv run --locked pytest tests/test_wordlist.py`: 10
  passed (4 marked `tesseract`). English 338,080 words, French 74,068,
  as in the research. First call 0.29 s (en), cached 0.035 s, on the M5
  Pro. Whole suite after the merge: 471 passed in 15.82 s.
- Departures: the function takes the language code as a string, so that
  an unknown code can be tested; an unknown code is `ConfigError`, since
  `errors.py` has no closer subclass.
- Left open: the cache is keyed by language only, so an update of
  Tesseract's language data is not seen until the cache file is deleted.

It is reviewed together with work package 1, whose stream runs beside it.
