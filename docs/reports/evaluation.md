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

## Work package 3: aligning and finding differences

Tasks 3.1 and 3.2 in c1967bb and 0eeeabc; review fixes in f4ce70e,
1cbf9d8, 6098098, 28c8709, after the spec was settled in a334ddf.

Deliverables, checked on the branch: the unit tests of spec §5's
alignment, differences, pages and stages pass, the spec's two worked
examples among them (in `pytest`: 659 passed, 8 deselected, 15.3 s;
`-m whole_book`: 8 passed). Deliverable 4, timed by the author's script
on galley's words of each book, M5 Pro, one thread, after the fixes:

| book | three passes | reference tokens aligned to an equal key | unplaced | anchor mismatches | changed / missing / extra |
|---|---|---|---|---|---|
| Haskins | 0.33 s | 90.4% | 1 | 0 of 260 | 2,225 / 1,617 / 2,310 |
| Stubbs | 0.59 s | 87.6% | 17 | 0 of 322 | 4,303 / 3,600 / 15,467 |
| Domesday | 1.29 s | 95.3% | 3 | 2 of 536 | 12,450 / 2,613 / 14,258 |
| Mariéjol | 1.75 s | 76.6% | 0 | no anchors | 33,211 / 24,091 / 33,404 |

Domesday's two anchor mismatches are real gaps in Gutenberg's anchors
(no anchor for printed page 132; 357 sits among the notes).

### What the review found

Every token had exactly one state and the counts added up on all four
books. What mattered:

- The leftover passes paired words pages apart (200–540 per book), and a
  replaced stretch paired every token in order whatever it was: 10,175 of
  Mariéjol's 21,769 changed pairs had nothing alike ("son" with "'"), and
  half of Mariéjol's running heads stopped being extras. The spec now
  aligns the leftovers within a page of where they belong, and pairs only
  tokens that are alike (a key similarity of at least 0.5, a guess to
  check on the baseline). Changed pairs fell by a third in Mariéjol and
  missing and extra rose: closer to what a person would call them.
- Punctuation-only tokens anchored alignments and paired with words; now
  they are never anchors and pair only with each other.
- A margin note inside a note could be aligned twice (no book has one).
  `align` now raises an error if any token is in no pairing or in two,
  and a test checks it on 300 generated inputs.
- "Serfs." against "serfs" was a diacritic difference; it is now
  punctuation, which the OCR table counts as read.
- Fifteen rules could be broken with every test passing (the tests
  reviewer ran 62 mutations); each now has a test that fails.

Not taken: the `repaired` score is noisy when the alignment moves
between outputs (a test that only damaged the text gave 123 "repairs");
to be watched on the baseline. The alignment is quadratic when a text
has almost no word that occurs once (a synthetic uniform vocabulary);
real prose is far from that.

The fixes were checked by the orchestrator, not reviewed again; the
review of work package 4 also covers them, since it runs them on whole
books.

## Work package 4: scores, output files and the command

Tasks 4.1–4.3 in a64378a, c6dec6d, ce315ec; review fixes in 608d52d,
1971691, ec1b4e3, after the spec was settled in b47dd68.

Deliverables, checked on the branch: the unit tests of galley's token
streams, the scores and the page table pass (`pytest`: 767 passed, 8
deselected, 15.4 s; with 8 threads 767 passed; `-m whole_book` 8
passed). `uv run galley-eval run` from the worktree root ran galley on
the four books and wrote every book's `scorecard.json`,
`differences.jsonl`, `pages.tsv` and `summary.md`, and
`runs/evaluation/summary.md` with four rows. A failing book is reported
and the others go on, with exit status 1 (tested).

The scores of galley as it is (the walking skeleton), after the fixes,
body unless named:

| book | error rate: words / lines / blocks / markdown | extras on the page edge | notes error rate | glued / missing at markdown | comparison |
|---|---|---|---|---|---|
| Haskins | 0.123 / 0.124 / 0.124 / 0.124 | 1,250 | 0.412 | 3,424 / 347 | 2.9 s |
| Stubbs | 0.180 / 0.176 / 0.176 / 0.176 | 1,594 | (none) | 4,974 / 1,264 | 5.0 s |
| Domesday | 0.115 / 0.114 / 0.114 / 0.114 | 1,833 | 0.104 | 18 / 1,088 | 11.2 s |
| Mariéjol | 0.355 / 0.356 / 0.356 / 0.356 | 1,706 | 0.705 | 515 / 11,520 | 12.7 s |

These are not the baseline yet; work package 5 gives it, after the
owner's check.

### What the review found

The tool reads every word of galley's four outputs exactly once, each
with a page, and the scorecard, the differences and the page table add
up on the four books. What mattered:

- Words the text layer runs together, as "Thelandisnotthewholeofnature's
  gifttoNormandy;" (eleven words), were reported as missing, because the
  spec joined at most 4 tokens: a third of Haskins' missing words. Now up
  to 12; Haskins' missing at markdown fell from 902 to 347 and its glued
  rose. This is the extract stage's spacing, and the summary now sends it
  there.
- A speck on the scan, a "!" or ";" above the running head, hid the
  running head from the page-edge flag on 93 of Stubbs' 324 pages.
- Each difference mixed its state in the final text with the stage it is
  blamed on; both are now written. The summary sends hyphen splits to
  structure, glued words to extract.
- Errors: a missing `book.md` stopped every book; a failed galley run was
  reported without the stage; a failed book kept stale numbers in the
  summary; a bug in the alignment read like a fault of the book. All
  fixed.
- About 40 of 115 mutations survived the tests; each has a test now.

Not taken, or open:

- Haskins' notes error rate stays 0.412. Its notes sit in the body at
  the foot of their pages, as the walking skeleton leaves them; aligned
  against Gutenberg's notes, a long leftover stretch drops a glued word
  ("Mont-Saint-Micheland") before reaching it. Once structure finds
  notes, galley's notes come in a stream of their own and this stretch
  no longer forms; the case is left until then, and the notes rate of a
  book whose notes galley leaves in the body is overstated.
- The comparison takes 2.9–12.7 s per book, most of it reading galley's
  JSON (about 4 s for Domesday, in `galley.model`), not the 1.5 s the
  spec first estimated. Acceptable for a run at the end of a plan.
- `compare` refuses a book folder that `run` did not make, since the
  commit of galley that made the files is unknown.

### For whoever next revises a skill or writes a plan

- Reviews of the tool kept finding the same thing in different places:
  a rule that pairs or joins without a limit of distance or similarity
  (leftovers across the book, any two tokens of a stretch, joins far
  apart, joins of at most 4). A spec of an alignment should say, for
  each pairing rule, how near and how alike two things must be.
