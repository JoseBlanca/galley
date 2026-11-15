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

## Work package 2: galley's word list

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

Reviewed with work package 1 (below). Fixed after review (63cb7a6): the
parameter is now `galley.config.Language`; a cache file that is not UTF-8,
and an unexpected `tesseract --list-langs` header, are named errors; a
failed cache write leaves no temporary file; the threads test counts the
extractions, and failed when the lock was removed. 12 tests.

## Work package 1: reading the Gutenberg HTML

Tasks 1.1–1.4 in commits df373e7, fbbe212, f90eed6, db823d5; review fixes
in be4ca7b to cc93fb4; merged into `plan/evaluation`.

Deliverables, checked by the orchestrator on the merged branch:

1. `uv run galley-eval --help` lists `run`, `compare`, `summary` (stubs
   until work package 4). The galley wheel holds no `galley_eval`
   (reviewer's `uv build --wheel`: 0 entries).
2. `scripts/fetch_samples.py` run twice: the second run downloaded 0
   files. It now reads the books from `evaluation/books.toml`, and no
   longer rewrites the committed excerpts (it re-cut them with different
   bytes on every run, before this plan too).
3. `evaluation/books.toml` with the four books; each HTML pinned by its
   SHA-256.
4. The reader's unit tests pass (in the 577 below).
5. `uv run pytest -m whole_book`: 8 passed (the 4 books' counts and
   first tokens, and the Gutenberg-only words absent), in 1.6 s.

All checks: ruff and ty clean; `pytest` 577 passed, 8 deselected, in
14.98 s; with 8 threads 577 passed in 22.94 s.

The counts the reader finds, each counted by hand from the HTML:

| book | notes | margin notes | note references | page anchors | headings | body / note tokens |
|---|---|---|---|---|---|---|
| Haskins | 72 | 0 | 72 | 260 | 21 | 65,613 / 658 |
| Stubbs | 0 | 467 | 0 | 322 | 37 | 98,587 / 0 |
| Domesday | 1,729 | 593 | 1,731 | 536 + 1 among the notes | 28 | 192,258 / 48,985 |
| Mariéjol | 1,432 | 0 | 1,432 | 0 | 34 | 191,714 / 36,345 |

### What the review found

Four reviewers (spec, tests, fidelity, conventions). The reader lost no
word of any book, but it made words the print does not have, and four of
its book-specific rules could be deleted with every test passing.
Everything below was fixed, each with a test that failed first, and the
spec was settled first where it said nothing (e6e1174 for the four rules
the reader needed, 27ebb2c for the review's cases):

- Gutenberg-only text kept as words of the book: Haskins' 34 section-break
  asterisks (170 tokens; the print has a blank line), Domesday's "[Larger
  map]", and 7 words glued across Stubbs' contents ("workPage"). Now
  dropped, and a new `separate` rule splits the glued words.
- Fractions: Domesday's `2<sup>1</sup>⁄<sub>2</sub>` read as "21⁄2", 94 of
  them. Now "2½" as printed.
- A verse in Mariéjol's note 1423 moved before the prose that introduces
  it. Only margin notes are now lifted out of a paragraph.
- Tests that could not fail: deleting Mariéjol's label rule (4,296
  invented tokens), Stubbs' heading rule or Domesday's start rule left the
  whole-book tests passing; the outermost-rule-wins case (Haskins' verse,
  29 quotes against 40) and six guards were untested. The whole-book test
  now checks headings, the first five body tokens and a list of
  Gutenberg-only words per book; each guard has a test.
- Errors: a missing or non-UTF-8 HTML file, a corrupted word-list cache,
  matches with no default case. Fixed.
- A Domesday page anchor (printed page 357) sits among the notes; it is
  kept apart and not used for pages.

Not taken:

- Corrections Gutenberg made without marking them in the text (about 25
  in Stubbs, listed only in its transcriber's table), and Domesday's 13
  cross-references renumbered by Gutenberg: they will count as galley
  errors, a few dozen tokens. Tagging them means reading the correction
  tables; left for later.
- The validation helpers of `books.py` copy private ones of `config.py`,
  and three places find the samples folder: duplication, not a defect.
- A truncated word-list cache is not detected (the atomic rename makes it
  unlikely); the cache is not refreshed when Tesseract's data changes.

### For whoever next revises a skill or writes a plan

- The whole-book test of the plan checked counts only, and counts do not
  move when a rule that drops or relabels text is deleted. A check of a
  reader of text needs the text itself in it: first tokens, and words
  that must not appear.
- The fidelity reviewer, adapted to "does the reader lose or invent a
  word", found the most serious defects; its method (an independent
  parse, diffed word by word) is worth naming in the categories.
