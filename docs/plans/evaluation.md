# Plan: the evaluation tool

This plan builds the evaluation tool of `docs/specs/evaluation.md`: the
development tool `galley-eval`, which compares galley's output for a
book with the Project Gutenberg edition made from the same scan, and
galley's word list, `wordlist.py` (architecture §12), which the tool and
later the analyze stage need. It ends with the tool's first run on the
four books of the evaluation set, whose scores are the baseline that
every later plan is measured against. Dated 15 November 2026. State:
under way, approved by the owner on 15 November 2026.

The five work packages are the breakdown the owner approved in chat on
15 November 2026. "Spec §5" below is section 5 of
`docs/specs/evaluation.md`; "architecture §12" is section 12 of
`docs/architecture.md`.

## In and out

In: the tool as spec §3 to §10 give it, with its tests; `wordlist.py`
and its tests; `scripts/fetch_samples.py` extended to the four books, their
Gutenberg HTML and a new Haskins excerpt; the baseline scorecards.

Out:

- any change to galley's stages. The baseline measures galley as it is
  (the walking skeleton); a difference the tool finds is not fixed here;
- choosing the statistic that detects bad OCR (analyze's spec);
- the other three books of spec §3;
- sorting the baseline's differences into bugs and new features, which
  is done with the owner after this plan.

The spec has no open point.

## What must be in place

Checked by the orchestrator before task 1.1, in the plan's worktree:

- `pandoc --version` prints `pandoc 3.14`; `tesseract --version` prints
  5.5.4; `which combine_tessdata dawg2wordlist epubcheck` prints three
  paths; `tesseract --list-langs` lists `eng` and `fra`. All were so on
  15 November 2026.
- `uv run --locked pytest` passes on the starting commit (461 tests on
  `main` at 636b104).
- The four PDFs of spec §3 are in `samples/public_domain/` of the main
  checkout, put there by hand during the research on 15 November 2026.
  Task 1.2 makes `fetch_samples.py` fetch them; until then they are used
  as they are.
- The Gutenberg HTML of the four books, downloaded during the research
  to the session's scratchpad, is not relied on: task 1.2 downloads it
  to `samples/public_domain/gutenberg/`.

## Streams and the files they may change

Work packages 1 and 2 run side by side; work packages 3, 4 and 5 run in
order, each after the one before is merged into `plan/evaluation` and
reviewed.

| WP | stream | tasks | may change |
|---|---|---|---|
| 1 | `reader` | 1.1–1.4 | `pyproject.toml`, `uv.lock`; `tools/galley-eval/` (everything in it); `evaluation/books.toml`; `scripts/fetch_samples.py` |
| 2 | `wordlist` | 2.1 | `src/galley/wordlist.py`; `tests/test_wordlist.py` |
| 3 | `align` | 3.1–3.2 | `tools/galley-eval/src/galley_eval/` (new modules only), `tools/galley-eval/tests/` |
| 4 | `report` | 4.1–4.3 | `tools/galley-eval/`; `.gitignore` if needed |
| 5 | `baseline` | 5.1–5.2 | `scripts/fetch_samples.py`; `tests/fixtures/pdf/`; `tests/fixtures/evaluation/`; `tools/galley-eval/tests/`; `docs/reports/evaluation.md` |

`pyproject.toml` and `uv.lock` are changed only by the `reader` stream
in work package 1, and by work package 4 if the command needs it. The
`wordlist` stream adds no dependency: it calls Tesseract's tools by
subprocess, as architecture §12 says.

The tool's tests live in `tools/galley-eval/tests/`, with a `conftest.py`
of their own that finds the whole books as `tests/conftest.py` does
(`GALLEY_SAMPLES`, or `samples/` of the main checkout), and skips when
they are missing.

## 1. Reading the Gutenberg HTML

**What it gives.** `uv run galley-eval --help` works from the root of
the repository. `uv run python scripts/fetch_samples.py` downloads the
four books and their HTML. The reader turns each book's HTML into the
reference text of spec §4, and finds in each the counts written in
`books.toml`.

This work package comes first because the reading rules are the part of
the spec that was weakest under review: run on Domesday, an earlier
version of the rules gave 1,730 notes for 1,729 and 590 margin notes for
593.

**Deliverables.**

1. The workspace: `uv run galley-eval --help` exits 0 and lists `run`,
   `compare` and `summary` (the subcommands may say "not built yet" until
   work package 4). `uv build` in the root makes a galley wheel with no
   `galley_eval` in it (`unzip -l` on the wheel). Fails on the starting
   commit: no such command.
2. `uv run python scripts/fetch_samples.py` downloads the four PDFs and
   the four HTML files to the paths of spec §3, and skips files already
   there. Checked by running it twice: the second run downloads nothing.
3. `evaluation/books.toml` with the four entries of spec §3, each field
   filled. The `exclude_pages` of each book are those in
   `runs/evaluation/<name>/book.toml`, made during the research, and
   `galley2epub run` succeeds on each book with them. The
   `expected_counts` are counted by hand from the HTML (spec §3), and the
   commit message says how each was counted.
4. The unit tests of the reader, one per case listed in spec §10's "the
   reader on small pieces of HTML", pass, and so do the cases that
   reviews of the spec found: a note label that holds the pairing `id`
   (Haskins), a note continued by an element without an `id` (Domesday's
   formula), a link from one note to another, a `p` holding only a page
   anchor, Gutenberg's text before the `start` element.
5. `uv run pytest -m whole_book tools/galley-eval/tests -k expected_counts`
   passes 4 tests, one per book. Fails on the starting commit: no tests
   (pytest exits with 5).

**Stands on.** Nothing before it.

**Tasks.**

- [x] 1.1 The workspace and the package skeleton: `tools/galley-eval/`
  with its `pyproject.toml`, the empty `galley_eval` package, the
  `galley-eval` command with its three subcommands as stubs, the root
  `pyproject.toml` changes of spec §9, the tests' `conftest.py`. Spec
  §9. Deliverable 1.
- [x] 1.2 `scripts/fetch_samples.py` downloads the four PDFs and the
  Gutenberg HTML (from `https://www.gutenberg.org/cache/epub/<n>/pg<n>-images.html`),
  slowly, as it does now. The excerpt comes in task 5.1. Spec §3.
  Deliverable 2.
- [x] 1.3 `evaluation/books.toml` and the code that reads it into
  `EvaluationBook`, with its malformed-input tests (the `coding` skill).
  The reading rules of each entry are written while doing 1.4, and the
  expected counts before it. Spec §3, §4 "The rules". Deliverable 3.
  Needs 1.1.
- [x] 1.4 The reader of spec §4: the rules, which rule wins, notes,
  paragraphs, tokens, marked corrections, page anchors. Deliverables 4
  and 5. Needs 1.3.

**What could go wrong.** The counts of deliverable 5 may not come out
for one book with the rules the spec gives. If a book needs a kind of
rule spec §4 does not have, the stream stops and the orchestrator
changes the spec first, as the `writing-specs` skill says.

## 2. galley's word list

**What it gives.** `word_list("en")` and `word_list("fr")` return the
words of Tesseract's English and French dictionaries, extracted once and
cached under `~/.cache/galley/`.

**Deliverables.**

1. The tests of `tests/test_wordlist.py` pass: the English list has
   between 300,000 and 400,000 words and holds "replicate"; the French
   list between 60,000 and 90,000 and holds "médicis" or another word with
   an accent; a second call reads the cache without running Tesseract's
   tools (checked by a cache folder given to the function in the test);
   an unknown language is an error. The research measured 338,080 and
   74,068 words. Marked `tesseract`. Fails on the starting commit: no
   module.

**Stands on.** Nothing. It runs beside work package 1.

**Tasks.**

- [x] 2.1 `src/galley/wordlist.py` as architecture §12 gives it,
  adapted from ocr_lab's `setup.sh` (the commit says from which file),
  with its tests. Architecture §12 and §6 (the language codes of
  `config.py`). Deliverable 1.

## 3. Aligning and finding differences

**What it gives.** The pure functions of spec §5, on token lists: the
three anchored passes, the states and subkinds, the pages, and the stage
each difference belongs to. Nothing reads galley's files yet; work
package 4 runs these on books.

**Deliverables.**

1. The unit tests of spec §5 "Alignment" and "Differences" pass: one per
   state and per subkind, the order of the subkinds (a pair that differs
   only in punctuation is `punctuation`, not `diacritic`), a split of 2
   and a glued of 3, a note moved to the end found by the second pass, a
   margin note found by the third.
2. The unit tests of spec §5 "Pages" pass: an unaligned body token takes
   the page of the anchor before it; an unaligned note token takes the
   page of its note's aligned tokens; a token between two anchors with
   an excluded page between them is unplaced; an anchor mismatch; a book
   with no anchors.
3. The unit tests of spec §5 "The stage a difference belongs to" pass,
   with the two examples of the spec as literal cases: the six tokens of
   "THE NORMANS IN THE SOUTH 199" attributed to words, and "replicate"
   repaired by blocks and not written as a difference.
4. Aligning Domesday's words with its reference takes under 2 s
   (spec §2 measured 0.26 s for two passes), timed once on the whole
   book and written in the report. Not a test.

**Stands on.** Work package 1: the reference text's types.

**Tasks.**

- [x] 3.1 The alignment key, the anchored pass and the three passes;
  the states, `split` and `glued`, and the subkinds. Spec §1 "Alignment
  key", §5 "Alignment" and "Differences". Deliverable 1.
- [x] 3.2 Pages, unplaced tokens, anchor mismatches, and the stage of a
  difference, repaired tokens and extra tokens. Spec §5 "Pages" and "The
  stage a difference belongs to". Deliverables 2–4. Needs 3.1.

**What could go wrong.** The page rule of spec §5 for unaligned tokens
was revised after review and not run on a book. Deliverable 4's timing
run also prints the counts of unplaced tokens and anchor mismatches per
book; more than a few hundred in a book is a sign to stop and look.

## 4. Scores, output files and the command

**What it gives.** `uv run galley-eval run` runs galley on the four
books and writes, for each, the files of spec §7; `galley-eval summary`
puts the books side by side.

**Deliverables.**

1. The unit tests of the token streams of galley's side (spec §5
   "galley's tokens") pass, on small hand-made `words.json`,
   `lines.json`, `blocks.json` and `book.md`: a block over two pages, a
   hyphen-joined word, a note reference span that is not a token, the
   `edge_of_page` flag.
2. The unit tests of spec §6 pass: `token_error_rate` on a literal case,
   paragraph boundary precision and recall, block kinds, notes
   `as_note`, `in_body` and `missing`, margin notes with and without
   `margin_notes_moved`, the part of an extra token.
3. The unit tests of spec §8's columns pass, each on a literal page:
   `ocr_recall` counting a split as read, `ocr_precision` on a scrambled
   page, `single_letter_share` leaving out "a" and "I",
   `inner_symbol_share`, `wordlist_share` with a small word list given
   to the function.
4. `uv run galley-eval run` exits 0 and writes, for each of the four
   books, `scorecard.json`, `differences.jsonl`, `pages.tsv` and
   `summary.md` under `runs/evaluation/<name>/evaluation/`, and
   `runs/evaluation/summary.md` with four rows. `galley-eval compare
   haskins` alone rewrites Haskins' files without running galley. A
   stage failure on one book is reported and the others go on, checked
   with a test on a book folder made to fail. Fails on the starting
   commit: no command.

**Stands on.** Work packages 1, 2 and 3.

**Tasks.**

- [ ] 4.1 galley's side: the token streams of the four outputs, from
  `galley.model`, `galley.book_folder` and `galley.fidelity.read_markdown`.
  Spec §5 "galley's tokens". Deliverable 1.
- [ ] 4.2 The scores of spec §6 and the page table of spec §8, as the
  frozen `Evaluation` of spec §9's `evaluate`. Deliverables 2 and 3.
  Needs 4.1.
- [ ] 4.3 Writing the files of spec §7, and the `run`, `compare` and
  `summary` subcommands of spec §9. Deliverable 4. Needs 4.2.

## 5. The excerpt test and the baseline

**What it gives.** A test that runs the whole comparison on ten pages of
Haskins in about a second, and the first scores of galley on the four
books.

**Deliverables.**

1. The excerpt `haskins_eval` is cut by `scripts/fetch_samples.py`
   (spec §10), with its HTML and galley's output files committed under
   `tests/fixtures/evaluation/`. The HTML holds no Gutenberg licence
   (`grep -ci gutenberg` prints 0 on it).
2. **The owner's check.** A file under `tests/fixtures/evaluation/`
   lists 5 to 8 differences on the excerpt, each with its page, tokens,
   state and stage, at least a running head, a hyphen at a line end and
   a footnote left in the body; the orchestrator renders those pages to
   PNG and shows them to the owner, who checks each difference by eye.
   The plan waits here for the owner.
3. The excerpt test asserts the differences the owner checked, and
   passes in under 2 s (`--durations`). Fails if `evaluate` is broken:
   checked once by breaking the attribution of stages and seeing it fail
   (the `coding` skill).
4. `docs/reports/evaluation.md` gives the baseline: for each book, the
   scorecard's text scores per stage and part, the structure scores,
   the counts of unplaced tokens and anchor mismatches, and the ten
   commonest kinds of difference with an example of each; and the
   Spearman correlations of spec §8's candidate statistics with
   `ocr_recall` and `ocr_precision`, measured on the tool's own
   definitions, beside the first look of spec §8.

**Stands on.** Work package 4.

**Tasks.**

- [ ] 5.1 The excerpt, its HTML and galley's outputs; a subagent chooses
  the 5 to 8 differences from what the tool reports on it and from the
  page images, and writes them down. Spec §10. Deliverables 1 and 2.
- [ ] 5.2 After the owner's check: the excerpt test; then `galley-eval
  run` on the four books and the baseline in the report. Spec §10, §8.
  Deliverables 3 and 4. Needs 5.1 and the owner.

## The check of the whole plan

At the end, on the plan's branch:

- every check of the `coding` skill, including `uv run --locked pytest
  -m whole_book`, passes;
- `uv run galley-eval run` from a clean `runs/evaluation/` writes the
  files of every book, and its scores equal those in the report;
- the report's baseline is read by the owner, which starts the sorting
  of differences into bugs and new features.
