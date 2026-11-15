# Work report: the evaluation tool

The report of `docs/plans/evaluation.md`, which builds the evaluation
tool of `docs/specs/evaluation.md` and galley's word list, and ends with
the baseline scores of galley on four books. Written as the work goes,
for the owner. Started on 15 November 2026.

## Summary

The plan is done, on branch `plan/evaluation`, not merged. Finished on
15 November 2026.

**What exists now.**

- `galley-eval`, a development tool beside galley. `uv run galley-eval
  run` runs galley on the four books of `evaluation/books.toml` and
  compares its words, lines, blocks and `book.md` with the Project
  Gutenberg edition made from the same scan, in 74 s for the four. Each
  book gets a scorecard, a file of differences (each with its PDF page
  and the stage to blame), a table of pages and a summary;
  `runs/evaluation/summary.md` puts the books side by side.
- galley's word list, `wordlist.py`, which analyze will use.
- An excerpt test on ten pages of Haskins, with the eight differences
  the owner checked, in 0.22 s.
- The baseline of galley as it is (the walking skeleton), below. The
  whole suite, galley's and the tool's, is 781 tests in 15.8 s.

**What the baseline says**, in the order of what it would gain:

- The error rate is the share of the book's words (66,000 in Haskins to
  241,000 in Domesday, by Gutenberg's text) that galley loses, adds or
  gets wrong: 11% to 17% in the English books, 34% in Mariéjol. It is
  the same after every stage, because no stage after extract changes
  the words yet: all of it is in the words read from the page, or is
  text that structure should have removed.
- Structure has the most to gain: 1,243–1,841 running-head and
  page-number words per book that galley keeps and the book does not
  have (1.9% of Haskins' words, 0.8% of Domesday's), 985–3,600 hyphens left split, and
  no paragraph, note or margin note found: about 1 in 10 of galley's
  paragraph breaks is one the book has.
- Extract's spacing: text run together is the commonest error of
  Haskins (1,328 runs) and common in Stubbs (2,315).
- Mariéjol's text layer misreads a third of its words (error rate
  0.343): the case for galley's own OCR.
- For detecting bad OCR without a reference, the share of dictionary
  words follows the real error (Spearman +0.59 to +0.84) and the share of
  stray single letters catches scrambled pages (−0.67 to −0.73 in three
  books).

**What is left open**, each written where the next person will look:

- Three kinds of word are counted as galley's errors when they are not,
  or not of that kind: a word run together with the next, when a running
  head sits just before it, is counted lost rather than run together;
  the notes of a book whose notes galley leaves in the body score worse
  than they are (Haskins' notes, 0.409); and Gutenberg's unmarked
  corrections (about 25 in Stubbs) count as galley's errors. Each is a
  few hundred words at most, and the first two go away once structure
  removes running heads and finds notes. Spec §5 and below.
- The comparison takes 3–13 s per book, mostly reading galley's JSON.

**What is asked of the owner:** to read the baseline, to decide whether
to merge `plan/evaluation` into `main`, and then which stage to work on
first. The next step, with the owner, is to go through the commonest
differences of each book and turn them into the work of a stage spec.
The baseline suggests structure (running heads, hyphens, paragraphs,
notes) first.

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

## Work package 5: the excerpt test and the baseline

Task 5.1 in 861d2bf, task 5.2 in 0b8c758 and cc481d1.

1. The excerpt `haskins_eval`: 10 PDF pages of Haskins, page indices
   131–138 (printed 116–123: the start of chapter V, footnotes 40–42,
   line-end hyphens, running heads, a section break), 265 (a blank page,
   kept so that the index follows the right page) and 266 (printed 251,
   the first page of the index). With it, under
   `tests/fixtures/evaluation/`: the matching part of Gutenberg's HTML,
   25 KB, with no licence (`grep -ci gutenberg`: 0), and galley's output
   files, 957 KB in all.
2. The owner checked the eight chosen differences by eye against the
   page images on 15 November 2026; all eight hold. One of them is not
   galley's error: chapter V opens "IN" in capitals, galley read "IN",
   and Gutenberg wrote "In". It stays in the test, counted as `case`,
   with a comment.
3. `tools/galley-eval/tests/test_excerpt.py`: 8 tests, 0.22 s. With the
   stage attribution broken, all 8 failed.
4. The baseline, below.

A last defect of the tool, found while choosing the differences, was
fixed in 0b8c758: the leftover passes now offer a word the galley tokens
of its own page first. It lowered the error rates by up to 1.3 points
(Mariéjol, 0.356 to 0.343). Two limits remain and are written in spec §5:
a word on the right page that is not alike enough still pairs with one
on the page before ("VII," with "ii8"), and a glued word behind a run of
extras, such as a running head, is reported missing ("Giraldus" before
"GiraldusCambrensis").

### The baseline

galley at commit cc481d1 (the walking skeleton), the four books run by
`uv run galley-eval run` from a clean `runs/evaluation/`: 74 s in all,
on the M5 Pro. Rerun after the last commit, the scores were the same.
Error rates are the share of the reference's tokens that are wrong, in
the body unless named; lower is better.

| book | error rate: words / lines / blocks / markdown | notes error rate | extras on the page edge | paragraph breaks right / found | notes as notes / in body / missing | margin notes as margin notes / in body / missing |
|---|---|---|---|---|---|---|
| Haskins | 0.123 / 0.124 / 0.124 / 0.124 | 0.409 | 1,243 | 0.113 / 0.110 | 0 / 71 / 1 | (none) |
| Stubbs | 0.179 / 0.174 / 0.174 / 0.174 | (none) | 1,598 | 0.131 / 0.074 | (none) | 0 / 448 / 19 |
| Domesday | 0.114 / 0.112 / 0.112 / 0.112 | 0.104 | 1,841 | 0.120 / 0.082 | 0 / 1,729 / 0 | 0 / 587 / 6 |
| Mariéjol | 0.342 / 0.343 / 0.343 / 0.343 | 0.700 | 1,538 | 0.092 / 0.037 | 0 / 1,428 / 4 | (none) |

What the baseline says about galley:

- The error rate is the same at every stage, because the walking
  skeleton removes nothing and joins nothing: every error comes from
  the words read from the page, or is something structure should remove.
- Running heads and page numbers: 1,243 to 1,841 extra tokens per book
  on the page edge, all to be removed by structure.
- Words run together by the text layer ("ThekingsofFrance,"): the
  commonest error of Haskins, 1,328, and 2,315 in Stubbs; extract's
  spacing.
- Hyphens at line ends left split: 985 in Haskins, 1,918 in Stubbs,
  3,600 in Domesday; structure's hyphen join.
- Scrambled text: Stubbs' two-column index gives most of its 10,903
  extra tokens; Domesday's tables most of its 11,077.
- Mariéjol's text layer is poor: 26,257 misread words and 21,526 missing
  ones. It is the case for galley's own OCR.
- Paragraphs: one per page, so about 10% of galley's breaks are real.
  Notes and margin notes are all left in the body, as the skeleton does.

The ten commonest kinds of difference per book, with an example of each,
are in the run's `summary.md` files; the counts above are from them.

### The candidates for detecting bad OCR

Spearman correlation over pages (scored pages with 50 tokens or more)
of each statistic galley can compute alone with the two measures of real
OCR error of spec §8. Each cell gives the correlation with `ocr_recall`
(words misread or lost), then with `ocr_precision` (pages scrambled).

| book | pages | share of dictionary words | share of stray single letters | share of words with a symbol inside |
|---|---|---|---|---|
| Haskins | 260 | +0.81 / +0.80 | −0.24 / −0.29 | −0.36 / −0.34 |
| Stubbs | 320 | +0.78 / +0.84 | −0.41 / −0.71 | −0.19 / −0.22 |
| Domesday | 538 | +0.59 / +0.68 | −0.49 / −0.67 | −0.50 / −0.46 |
| Mariéjol | 438 | +0.76 / +0.84 | −0.67 / −0.73 | −0.24 / −0.22 |

On the tool's own definitions the share of dictionary words follows
the real error better than the first look of spec §8 found in the three
English books (Domesday 0.59–0.68 against 0.40, Stubbs 0.78–0.84 against
0.46) and a little less in Mariéjol (0.76–0.84 against 0.87); the cause
was not measured (the definitions, the word list and the page edges all
changed). The share of stray single letters is the
best second statistic for scrambled pages (−0.67 to −0.73 with
`ocr_precision` in three books). These are the numbers analyze's spec
starts from.
