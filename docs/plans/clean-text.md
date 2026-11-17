# Plan: clean text

This plan makes the words galley takes from a scanned book cleaner, in
five changes the owner asked for on 17 November 2026:

- the text layer (the invisible words the scanner's OCR placed over each
  page) read in the order the PDF holds its characters, which mends
  words the sorting cut ("s ome") or mixed (Stubbs' index);
- words the OCR left glued ("Thisbookrestspartlyupon") split at wide
  gaps;
- the pages before the preface (endpapers, title page, copyright)
  dropped, each word recorded as a removal;
- the running head of a two-page section removed ("vlil PREFACE" on the
  second page of Haskins' preface);
- small print re-read with Tesseract where it reads better than the
  text layer: outer margin notes, Stubbs' notes cut into the column,
  pages printed wholly in small type such as Stubbs' index.

It is built from `docs/specs/extract.md`, `docs/specs/front-matter.md`,
`docs/specs/structure.md` §3 ("The head of a short section"),
`docs/specs/reocr.md`, and the changes they made to
`docs/architecture.md`, `docs/glossary.md`, `docs/specs/layout.md` and
`docs/specs/evaluation.md`, all on branch `plan/clean-text` (commits
d22d250 to f40bda3). It ends with the evaluation tool's scores on the
four evaluation books against the last plan's, and the six books' EPUBs
passing epubcheck. Dated 17 November 2026. State: under way since 17
November 2026 (approved by the owner on 17 November 2026).

"Extract §4" below is section 4 of `docs/specs/extract.md`, "front
matter §2" of `docs/specs/front-matter.md`, "reocr §9" of
`docs/specs/reocr.md`, "structure §3" of `docs/specs/structure.md`.
Page means page index of the whole PDF, from 0, unless "excerpt page"
or "book page" says otherwise.

## In and out

In: everything the four specs describe, with the formats of
architecture §8 (`pages.json`, `words.json` and `lines.json` at version
2), the config keys `front_matter_end` and `reread_footnotes`, the
module `ocr.py`, the evaluation tool's changes of evaluation §5
("Front matter"), §6 (the margin notes' part) and §8
(`ocr_confidence_mean`), three new excerpts, and the measurement.

Out: re-reading the body text, Stubbs' chapter summaries, or any page
of Mariéjol on purpose (reocr §12); OCR of pages without a text layer
and analyze's OCR audit (architecture §7b); mending the order of
Domesday's climbing words on pages 136 and 481 (extract §6, layout's);
pages at the end of a book that are not its text (front matter §9);
the correct stage.

Open points of the specs, each with its meanwhile, which this plan
builds:

| open point | meanwhile, built here | what an answer would change |
|---|---|---|
| front matter Open 1: the EPUB keeps a subtitle or a dedication | (a) neither: both are dropped with the front pages | (b) adds a config key `subtitle` (a task after 3.2, changing `config.py` and markdown); (c) also a dedication rule, to be measured first |
| reocr Open 1: footnote bands re-read by default | (a) off; `reread_footnotes = true` turns it on | (b) changes the default in task 1.1 and the targets of task 6.3 (Domesday's linked notes fall); (c) adds a task to work package 5 and its measurement |
| reocr Open 2: Tesseract's junk in a kept region | every word kept | dropping words under confidence 30 as `ocr_junk` changes task 1.1 (a removal reason) and task 5.1 (the replacement) |
| reocr Open 3: `lines.json` gains `rereads`, and layout replaces OCR that exists | built as reocr §4 says | a refusal removes work package 5 and the `Reread` format of task 1.1; the plan would stop |

Two parts of the specs that changed while the plan was written:

- Changed reference pages: as extract §7 now says (corrected on 17
  November 2026), this plan commits a changed literal
  when every change on it is shown, by a script, to be a join of
  pieces, a split at a gap, or the same characters regrouped (section
  "Changed reference pages" below), lists each change in the report,
  and puts the list on the owner's sheet of task 6.2; a change the
  owner rejects is fixed in task 6.4.
- Small-print pages: reocr §3 (answered on 17 November 2026) reads
  whole every index page of Stubbs, Domesday and Haskins, Haskins'
  chapter bibliographies and Mariéjol's bibliography (pages 14 to 16),
  each kept or not by its score.

## What must be in place

Checked on 17 November 2026 at 9f012ac, in this worktree, and checked
again by the orchestrator before task 1.1:

- `which pandoc tesseract combine_tessdata dawg2wordlist epubcheck`
  prints five paths; `tesseract --version` says 5.5.4 (the version the
  re-reading literals hold for, reocr §9); `tesseract --list-langs`
  lists `eng` and `fra`; Pandoc 3.14; EPUBCheck 5.4.0.
- `uv run --locked pytest`: 1692 passed, 32 deselected, in 28.6 s.
- The six whole books in `samples/public_domain/` of the main checkout,
  and the four Gutenberg HTML files under `gutenberg/`.
- The plan's worktree and branch exist: `.claude/worktrees/clean-text`,
  branch `plan/clean-text`, made from `main` at 4542207 and holding the
  specs. The orchestrator works there and makes no new one.
- **The baseline**: `uv run galley-eval run` at 9f012ac, whose code is
  that of `main`, copied to `runs/clean-text-baseline/` of the main
  checkout. Its scores must equal the final ones of
  `docs/reports/structure-second.md` ("The final measurement"); if
  they do not, the orchestrator stops and tells the owner.
- **Gierke's 30 margin notes** of the measurement of 16 November 2026,
  which task 6.3 reads again, are in the appendix of this plan (the
  only other copy is in a session's scratch folder).

## The order of the work, and the streams

Work package 1 changes the shared files and runs first, on the plan's
branch. Then streams run side by side, each in a worktree of its own
(the `following-plans` skill, "Parallel streams"), no more than three at
once:

| stream | tasks | starts | may change |
|---|---|---|---|
| `text-layer` | 2.1 to 2.3 | after WP 1 | `src/galley/text_layer.py`; in `src/galley/analyze/__init__.py`, only where the measurer reads the layer; `src/galley/extract/`; `tests/test_text_layer.py`; `tests/test_extract.py`; `tests/test_analyze.py`; `tests/test_excerpts.py`; `tests/fixtures/expected/`; in `tests/test_layout.py`, `tests/test_structure.py`, `tests/test_end_to_end.py` and `tests/test_markdown.py`, only literals the new reading changes |
| `ocr` | 5.1 | after WP 1 | `src/galley/ocr.py`; `src/galley/layout/_reread.py` (new) and one export line in `src/galley/layout/__init__.py`; `tests/test_ocr.py`; `tests/test_reread.py`; `tests/fixtures/ocr/` |
| `eval` | 6.1 | after WP 1 | `tools/galley-eval/` |
| `front-matter` | 3.1, 3.2 | when `text-layer` is merged | `src/galley/analyze/`; `src/galley/extract/`; `tests/test_analyze.py`; `tests/test_extract.py`; `tests/test_excerpts.py` |
| `running-head` | 4.1 | after WP 1, when fewer than three streams run | `src/galley/structure/`; `tests/test_structure.py`; `tests/fixtures/structure/` |

`front-matter` waits for `text-layer` because both change analyze and
extract, and because front matter §4 counts the dropped words as the new
reading gives them. The `ocr` stream builds only what needs no change to
layout's output; wiring it into layout changes the reference pages, and
waits for the others.

After the streams are merged and reviewed, the rest runs on the plan's
branch in this order: 4.2; the orchestrator's run of `uv run galley-eval
run`, copied to `runs/clean-text-before-reread/` of the main checkout
(the "before" of reocr §9's targets); 5.2 to 5.4; 6.2, the owner's
sheet, with 6.3 running while the owner reads it; 6.4.

`model.py`, `config.py`, `fidelity.py`, `pyproject.toml`,
`docs/architecture.md` and `docs/glossary.md` are changed in work
package 1 only. A stream that finds it needs one of them stops and asks
the orchestrator, who changes it on the plan's branch and merges it into
the streams.

**Changed reference pages.** A reference page is a page of an excerpt
whose expected output the owner checked by eye; its literals are in
`tests/fixtures/expected/` and in tests. A task whose change alters one
updates it in the same commit, and:

- in work package 2, a script kept outside the repository compares, for
  each changed literal, the old and new words in order, and names each
  change a **join** (several old words are one new word), a **split**
  (one old word is several new ones) or a **regrouping** (the same
  characters in other words: two overlaid OCR words pulled apart, a mark
  set apart). A change of words of any other kind stops the task and
  goes to the orchestrator. A change to blocks or notes, not to words,
  is listed with the word change that causes it. The list, page by
  page, goes into the report;
- in work packages 3 to 5, the commit names each change and the spec
  part that causes it, and the orchestrator checks each against the
  page image before ticking the task; re-reading's changes also go on
  the owner's sheet (task 6.2).

Each task keeps every check of the `coding` skill passing.

Every command check of the deliverables below was run once at 9f012ac
on 17 November 2026 and failed as each says. The evaluation runs
(work package 2, deliverable 6; work package 6, deliverable 3) were
not: their values at 9f012ac are the last plan's final ones, which the
baseline must equal.

## 1. Foundations

**What it gives.** The formats of this plan exist and are read and
written: the page kind and removal reason `front_matter`, `pages.json`
and `words.json` at version 2; the record `Reread` in `lines.json`, at
version 2, which layout writes empty for now; the config keys
`front_matter_end` and `reread_footnotes`; layout's fidelity check that
counts the words a kept re-reading replaced. The three new excerpts are
committed. Nothing a reader sees changes yet.

**Deliverables.**

1. The format changes of architecture §8, with their read and write
   functions and the error for a file of version 1 that names the stage
   to run again: `uv run python -c "from galley.model import
   PAGES_FORMAT_VERSION as P, WORDS_FORMAT_VERSION as W,
   LINES_FORMAT_VERSION as L, PageKind, RemovalReason, Reread,
   RereadKind; assert (P, W, L) == (2, 2, 2);
   PageKind('front_matter'); RemovalReason('front_matter')"` passes
   (fails at 9f012ac: no `Reread`); `uv run pytest tests/test_model.py
   -k "front_matter or reread" --collect-only -q` lists at least 6 (0
   at 9f012ac).
2. The two config keys of architecture §6, each read, defaulted and
   refused with a wrong type: `uv run pytest tests/test_config.py -k
   "front_matter_end or reread_footnotes" --collect-only -q` lists at
   least 4 (0 at 9f012ac).
3. The fidelity check at layout's boundary of architecture §13 and
   reocr §4, "The fidelity check": a kept record's words swapped, a
   record not kept changing nothing, a record naming a word its page
   does not have failing, a word in two kept records failing: `uv run
   pytest tests/test_fidelity.py -k reread --collect-only -q` lists at
   least 4 (0 at 9f012ac).
4. The three excerpts of front matter §6 and extract §7,
   `haskins_front`, `domesday_front_flow` and `gierke_front_flow`, cut
   by `scripts/fetch_samples.py` with what each covers, committed, and
   in `EXCERPT_CONFIGS` with the configs front matter §6 gives
   (`contents_pages = [7]` for `haskins_front`, `[5]` for
   `gierke_front_flow`): `for e in haskins_front domesday_front_flow
   gierke_front_flow; do test -f tests/fixtures/pdf/$e.pdf && grep -q
   "\"$e\"" tests/conftest.py && grep -q "\"$e\""
   scripts/fetch_samples.py || echo "missing $e"; done` prints nothing
   (3 lines at 9f012ac), and `uv run pytest tests/test_excerpts.py`
   passes with them.
5. Kept true, not new work, so it passes at 9f012ac too: the
   evaluation tool reads the new versions (`uv run pytest
   tools/galley-eval/tests` passes), and `uv run --locked pytest` stays
   within the `coding` skill's minute.

**Stands on:** what must be in place.

**What could go wrong.** The three excerpts add three runs to the
excerpt fixture of `tests/conftest.py`, about half a second each with
six at once; work package 5 then adds Tesseract to every run. The
front excerpts hold endpapers and labels: a page without a text layer
among them needs `exclude_pages` in its config, as analyze refuses it.

- [x] 1.1 The format changes in `model.py` (layout writing an empty
  `rereads`), the config keys in `config.py`, the layout boundary in
  `fidelity.py`, and the evaluation tool's fixtures at the new
  versions, with their tests. Spec: architecture §6, §8 and §13; front
  matter §3; reocr §4, "The record" and "The fidelity check", and §6,
  the config key. Deliverables 1 to 3, 5. A commit of its own, first.
- [x] 1.2 The three excerpts and their configs. Spec: front matter §6,
  "Excerpt tests"; extract §7, "Excerpt tests". Deliverables 4, 5.

## 2. Reading the text layer

**What it gives.** analyze and extract read each page's words through
one function, `text_layer.layer_words`: the characters in the PDF's
order (extract §3), and glued words split at gaps of at least a third of
a character's width (extract §4). On Haskins and Stubbs 1,606 and 3,164
glued words are split; on all six books words the sorting cut or mixed
are whole again.

**Deliverables.**

1. `uv run python -c "from galley.text_layer import Character,
   layer_words, split_glued"` passes (fails at 9f012ac), and `grep -rn
   "extract_words(" src/galley/analyze src/galley/extract` prints
   nothing (3 lines at 9f012ac).
2. The unit tests of extract §7, first bullet, one or more per case:
   `uv run pytest tests/test_text_layer.py -k "split_glued or
   layer_words" --collect-only -q` lists at least 7 (0 at 9f012ac).
3. The excerpt tests of extract §7: `domesday_front_flow` (pages 23, 24,
   200) and `gierke_front_flow` (pages 13, 100) without the pieces
   named there, and `haskins_front` excerpt page 5 (book page 12) with
   its words exactly, each split checked against the page image: `uv
   run pytest tests/test_extract.py -k "front_flow or haskins_front"
   --collect-only -q` lists at least 3 (0 at 9f012ac), and they pass.
4. The reference pages under the new reading: `uv run pytest
   tests/test_excerpts.py` passes; every changed literal is in the
   report, page by page, each change a join, split or regrouping as
   "Changed reference pages" says; `git diff --stat 9f012ac --
   tests/fixtures/expected` names the same files as the report (none at
   9f012ac).
5. The whole-book tests of extract §7: `uv run pytest -m whole_book
   tests/test_text_layer.py --collect-only -q` lists at least 12 (0 at
   9f012ac): each book's word count after both rules as extract §4's
   table gives it (Haskins 69,028; Stubbs 104,429; Domesday 251,053;
   Mariéjol 237,920; Gierke 112,270; Kadesh 24,188), and every non-space
   character of each page in exactly one word. `uv run pytest -m
   whole_book tests/test_analyze.py -k page_kinds --collect-only -q`
   lists at least 6 (0 at 9f012ac): each book's page kinds equal to
   those analyze gave at 9f012ac. `uv run pytest -m whole_book` passes.
6. Run by the orchestrator when the stream is merged: `uv run
   galley-eval run` against the baseline, in the report with both
   scorecards side by side. At blocks, the body's token error rate is
   lower than the baseline's on Haskins and Stubbs, and that of
   Stubbs' index too; the `glued` differences fall by about the words
   added (Haskins 2,767, Stubbs 4,211); any score that rises is
   explained page by page. At 9f012ac the two runs are equal, so the
   check fails.

**Stands on:** work package 1.

**What could go wrong.** 95 of the 108 pages of the eleven committed
excerpts get different words (extract §7), so most reference literals
change, some through structure (a paragraph or note boundary that
followed a cut word). Domesday's pages 136 and 481 get words whose
boxes climb, and layout's rows interleave there (extract §6); that is
expected, not fixed.

- [ ] 2.1 `Character`, `split_glued` and `layer_words` in
  `text_layer.py`, with the unit tests. Spec: extract §3, §4 and §5;
  §7, first bullet. Stream `text-layer`. Deliverables 1, 2.
- [ ] 2.2 analyze's measurer and extract reading through `layer_words`;
  the excerpt tests; the changed reference literals and their list.
  Spec: extract §5, §6 and §7, "Excerpt tests" and "The reference
  pages of the committed excerpts change". Needs 2.1. Stream
  `text-layer`. Deliverables 1, 3, 4.
- [ ] 2.3 The whole-book tests. The page kinds at 9f012ac come from
  running analyze at that commit on the six books in a scratch
  worktree, written into the test as literal lists of each book's pages
  that are not `text`. Spec: extract §7, "Whole books". Needs 2.2.
  Stream `text-layer`. Deliverable 5.

## 3. The front matter

**What it gives.** analyze finds where the front matter ends (front
matter §2) and makes the text pages before it `front_matter`, logging
the end, the step that gave it and the pages; extract records each of
their words as a `front_matter` removal. The EPUB starts at the preface,
or at the contents when they come first.

**Deliverables.**

1. The unit tests of front matter §6, first bullet, with the
   `ConfigError` cases of §2 (`front_matter_end` not below the page
   count; a contents page before it) and the INFO and WARNING logs:
   `uv run pytest tests/test_analyze.py -k front_matter --collect-only
   -q` lists at least 9 (0 at 9f012ac).
2. extract's `page_words` on a `front_matter` page: no words, every
   layer word a removal with that reason: `uv run pytest
   tests/test_extract.py -k front_matter --collect-only -q` lists at
   least 1 (0 at 9f012ac).
3. The excerpt tests of front matter §6: `haskins_front` excerpt pages
   0 to 4 `front_matter`, their words the only `front_matter` removals,
   and layout's first two lines of excerpt page 5 "PREFACE" and "THE
   eight lectures which are here published"; `domesday_front_flow`
   pages 0 to 4; `gierke_front_flow` pages 0 to 4, and 5 and 6 not;
   each of the eleven committed excerpts without a `front_matter` page.
   `uv run pytest tests/test_excerpts.py -k front_matter --collect-only
   -q` lists at least 4 (0 at 9f012ac), and they pass.
4. The whole-book tests of front matter §6: on each book exactly the
   pages of front matter §4's table are `front_matter`, with 108, 370,
   99, 95, 100 and 91 removals (Haskins, Stubbs, Domesday, Mariéjol,
   Gierke, Kadesh): `uv run pytest -m whole_book -k front_matter
   --collect-only -q` lists at least 6 (0 at 9f012ac), and they pass;
   the page-kinds test of task 2.3 now allows exactly those pages.

**Stands on:** work packages 1 and 2.

**What could go wrong.** The running-text step's threshold, half the
median word count, was measured on Kadesh alone (front matter §2).

- [ ] 3.1 `PageStart`, `front_matter_end`, `classify_page`'s new
  argument, analyze's checks of the key and its logs, with the unit
  tests. Spec: front matter §1, §2 and §7. Stream `front-matter`.
  Deliverable 1.
- [ ] 3.2 extract's removals for a `front_matter` page; the excerpt and
  whole-book tests. Spec: front matter §3, §4 and §6. Needs 3.1. Stream
  `front-matter`. Deliverables 2 to 4.

## 4. The running head of a short section

**What it gives.** structure removes the running head of a section of
two pages, which no other page repeats: "vlil PREFACE" on Haskins' page
13 and "vi Preface." on Domesday's, with "vi" recorded as a page number.

**Deliverables.**

1. The unit tests of structure §3, "The head of a short section", one
   or more per condition and per outcome (a misread number removed with
   its line; a page-number form recorded in `page_numbers`; Gierke's
   title line without a number-like word kept; the heading two pages
   before with a blank page between; fewer than 4 letters, a likeness
   under 0.75, a top more than 2 pitches from the median head top, each
   kept): `uv run pytest tests/test_structure.py -k "short_section or
   number_like" --collect-only -q` lists at least 7 (0 at 9f012ac).
2. On the excerpts: the first line of `haskins_front` excerpt page 6
   and of `domesday_front_flow` excerpt page 6 (book page 13 of each)
   is a `running_head` removal, and Domesday's "vi" a page number: `uv
   run pytest tests/test_excerpts.py -k short_section --collect-only
   -q` lists at least 2 (0 at 9f012ac), and they pass.
3. On the six books the rule removes exactly those two lines: `uv run
   pytest -m whole_book -k short_section --collect-only -q` lists at
   least 1 (0 at 9f012ac), and it passes.

**Stands on:** work package 1; for task 4.2, work packages 2 and 3.

**What could go wrong.** The rule was measured on the old reading of
the text layer (structure §3); Haskins has no space characters, so its
line 13 may come out with other words under the new one.

- [x] 4.1 The rule, in structure's running-head pass, with the unit
  tests. Spec: structure §3, "The head of a short section". Stream
  `running-head`. Deliverable 1.
- [ ] 4.2 The excerpt and whole-book tests. Spec: structure §3, the
  same part, its last paragraph. On the plan's branch, after
  `front-matter` is merged. Needs 4.1. Deliverables 2, 3.

## 5. Re-reading small print

**What it gives.** layout re-reads, with Tesseract at 300 dpi, the
outer margin notes of Gierke and Domesday, Stubbs' cut-in notes, and the
pages printed wholly in small type, and keeps Tesseract's words for a
region only when their reading score (known words minus unknown words)
is higher than the layer's. Every region read is a `Reread` in
`lines.json`. With `ocr = "trust"` nothing is re-read; with
`reread_footnotes = true` the footnote bands are read too.

**Deliverables.**

1. `uv run python -c "from galley.ocr import OCR_DPI, read_image,
   words_of_tsv"` passes (fails at 9f012ac); the unit tests of reocr
   §9 ("Unit tests", all but the config, which task 1.1 wrote), with
   no PDF and no Tesseract: `uv run pytest tests/test_ocr.py
   tests/test_reread.py --collect-only -q` lists at least 18 (the
   files do not exist at 9f012ac).
2. The excerpt tests of reocr §9, marked `tesseract`, each skipping
   with the reason on a Tesseract other than 5.5.4: Gierke's book page
   88 with "Medieval Thought." read; Stubbs' cut-in notes kept and the
   body lines beside them as without re-reading; the six index pages of
   `stubbs_summaries_index` re-read and kept, their running heads the
   layer's, the entry "Acre, siege of, 116; the English at, 118;" with
   both ";"; two Domesday pages' margin notes; `haskins_eval` with
   `reread_footnotes = true` reading "1" where the layer has "^", and
   with the default running no Tesseract in layout; `ocr = "trust"`
   giving no record and the lines of a run without re-reading; the
   fidelity check on every excerpt; the Stubbs excerpt with 1 and 6
   workers byte for byte. `uv run pytest tests/test_layout.py -k reread
   --collect-only -q` lists at least 8 (0 at 9f012ac), and they pass.
3. `galley2epub` stops before layout naming Tesseract, or the word
   list's tools, when they are missing and `ocr` is `verify`, and not
   with `trust`: `uv run pytest tests/test_cli.py -k reread
   --collect-only -q` lists at least 2 (0 at 9f012ac).
4. layout §3 and §4 gain the steps and functions of reocr §3, §4 and
   §6 (reocr §10): `grep -n "is_small_print_page\|note_bands\|reading_score"
   docs/specs/layout.md` prints at least 3 lines (none at 9f012ac).
5. The whole-book tests of reocr §9: `uv run pytest -m whole_book -k
   reread --collect-only -q` lists at least 7 (0 at 9f012ac): the
   fidelity check with re-reading on each of the six books, and Stubbs
   with 1 and 6 workers byte for byte; they pass.
6. In the report, per book: regions read, regions kept, and layout's
   time with 6 workers, beside reocr §7's table (Stubbs 365 / 262 /
   30.7 s, Domesday 630 / 443 / 69.9 s, Gierke 762 / 490 / 52.0 s,
   Haskins 17 / 8 / 3.5 s), with the machine.

**Stands on:** work package 1; for tasks 5.2 to 5.4, work packages 2 to
4 merged, because the reference pages and the reading scores rest on
the new reading of the text layer.

**What could go wrong.** The default test run grows: every excerpt run
now re-reads (about 1 s of renders for the Domesday excerpt, 0.6 to
0.9 s of Tesseract per Stubbs index page), and pytest's limit is 30 s a
test, the excerpt fixture's setup included. Tesseract's readings are
those of 5.5.4 only. The note bands are found in pure Python over a
300-dpi strip; numpy is not a dependency.

- [x] 5.1 `ocr.py`, and in `layout/_reread.py` the pure parts of
  re-reading: `reading_score`, `is_small_print_page`, `note_bands`, the
  crop of each kind of region, the two filters of the cut-in crops, the
  words a region replaces, one record at most per word, and the order
  of the records. Spec: reocr §3, §4, §5 and §6; §9, "Unit tests".
  Stream `ocr`. Deliverable 1.
- [ ] 5.2 layout re-reading: the render function `layout_page` is
  given, the steps where each region is read, a small-print page laid
  out from Tesseract's words, `rereads` written, `ocr` and
  `reread_footnotes` obeyed; the command's checks before layout; the
  excerpt fixture skipping without Tesseract; layout §3 and §4; the
  changed reference pages. Spec: reocr §3, §4, §6, §7 and §10; layout
  §3. Needs 5.1. Deliverables 3, 4.
- [ ] 5.3 The excerpt tests, with the literals reocr §9 gives; the full
  reading of each region waits for the owner's sheet (task 6.2). Spec:
  reocr §9, "Excerpt tests". Needs 5.2. Deliverable 2.
- [ ] 5.4 The whole-book tests and the timings. Spec: reocr §7; §9,
  "Whole-book tests". Needs 5.2. Deliverables 5, 6.

## 6. The evaluation tool, the owner's check and the measurement

**What it gives.** The evaluation tool leaves the dropped front matter
unscored and scores the margin notes as a part of their own. The owner
checks the reference pages this plan changed. The scores of the four
evaluation books are measured against the baseline and the last plan's,
and the six EPUBs are built.

**Deliverables.**

1. The tool's changes: `front_matter_not_scored` in the scorecard
   (evaluation §5, "Front matter"), the part `margin_notes` (§6), and
   `ocr_confidence_mean` over the words layout re-read (§8): `uv run
   pytest tools/galley-eval/tests -k "front_matter or margin_notes_part
   or reread" --collect-only -q` lists at least 3 (0 at 9f012ac).
2. The owner's sheet, one section per page with its image: Haskins'
   book page 12 (task 2.2's exact words); the changes of work package
   2, by page and kind; each region of task 5.3's tests with the
   layer's and Tesseract's readings and which was kept; each reference
   page re-reading changed. The owner's answers are in the report. No
   command checks it: the owner's answer is the check, and deliverable
   6 turns it into tests.
3. The scores, at blocks, in the report, each with its value in the
   baseline, in `runs/clean-text-before-reread/` and now:
   - reocr §9's targets: Stubbs' index boundaries at least 0.97 / 0.94;
     margin notes as margin notes at least 285 of 467 on Stubbs and 560
     of 593 on Domesday; body token error rate at most 0.062 on Stubbs
     and 0.080 on Domesday; Domesday's notes whose reference is right
     at least 1,275; Haskins' index error rate at most 0.13; Mariéjol as
     before re-reading but for its bibliography, pages 14 to 16; on
     Stubbs, no column word layout did not take as a cut-in word among
     the replaced words of a kept cut-in record, but "heBarons" (page
     226);
   - extract §7's expectations, as in deliverable 6 of work package 2;
   - every score of the tables "The targets of structure §9" and "The
     first plan's scores, then and now" of
     `docs/reports/structure-second.md`, beside the values there, with
     any that falls explained;
   - the tokens left unscored as front matter, per book.
   The command is `uv run galley-eval run`; at 9f012ac it gives Stubbs'
   index 0.829 / 0.789 and 241 margin notes as margin notes, below
   reocr §9's targets. A missed target does not stop the plan: it is reported with its
   cause found in `differences.jsonl`, and what fixing it would take
   goes to the owner as a proposal.
4. Gierke's 30 margin notes of the appendix, read by eye in the EPUB's
   text against the page image: at least 130 of the 139 words right
   (reocr §9), in the report note by note. Read by eye, as reocr §9
   asks, so no command; the text layer gave 52 of 139.
5. `uv run pytest -m whole_book` passes; the six EPUBs, built from the
   whole books with `WHOLE_BOOK_CONFIGS`, pass epubcheck, in
   `runs/clean-text/epubs/` of the main checkout, with each book's
   time.
6. After the owner's answer, the readings the owner accepted are exact
   literals: `uv run pytest tests/test_layout.py -k "reread and
   owner_checked" --collect-only -q` lists one test or more per page
   the owner checked (0 at 9f012ac), and they pass.

**Stands on:** task 6.1: work package 1. Tasks 6.2 to 6.4: work packages
1 to 5.

- [x] 6.1 The evaluation tool's three changes. Spec: evaluation §5,
  "Front matter"; §6, the parts; §8, `ocr_confidence_mean`. Stream
  `eval`. Deliverable 1.
- [ ] 6.2 The owner's sheet, published privately; the plan's one pause
  for the owner, with 6.3 running while they read it. Spec: extract §7,
  "The reference pages"; reocr §9, "Excerpt tests". Deliverable 2.
- [ ] 6.3 The measurement: `uv run galley-eval run`, the whole-book
  tests, the six EPUBs, Gierke's 30 notes. Spec: reocr §9, "The
  measurement of the plan"; extract §7, "galley-eval before and after";
  `docs/specs/evaluation.md` §9. Needs 6.1 and work package 5.
  Deliverables 3 to 5.
- [ ] 6.4 The owner's answers: accepted readings as literals, rejected
  changes fixed or sent back to the owner as a question. Needs 6.2.
  Deliverable 6.

## How the whole plan is checked at the end

- The checks of the `coding` skill on the plan's branch, with pytest
  once normally and once with 8 threads, and `uv run pytest -m
  whole_book`; the default run's time against the minute.
- Work package 6's deliverables 3 to 5 run again after the last fix.
- For the owner on the Kindle, in `runs/clean-text/epubs/`: Haskins'
  EPUB opening at its preface, with no endpaper garbage before it and
  no "vlil PREFACE" on the preface's second page; Domesday's preface
  likewise ("vi Preface."); Stubbs' index (pages 312 to 321), its
  entries cut at each ";"; Stubbs' chapter III, its cut-in notes as
  Tesseract read them; Gierke's book page 88, the four margin notes
  with "Medieval Thought."; Domesday's margin notes around book page
  76.

## Appendix: Gierke's 30 margin notes

The sample of 16 November 2026 (`docs/reports/structure-second.md`,
"Task 7.6"): 30 notes chosen evenly among 160 found on pages 86 to 185
of Gierke's whole book, as printed, with their words (139 in all). A
word is right when its letters are (case and punctuation ignored); a
word broken over two lines counts once and is right only when both parts
are; two words read as one are both wrong. Then: the text layer 52
right, Tesseract (psm 6) 133.

| page | note as printed | words |
|---|---|---|
| 86 | The beginning of Political Theory. | 5 |
| 88 | Medieval and Antique-Modern Thought. | 5 |
| 92 | Medieval Thought and the Universe | 5 |
| 95 | Mankind as one Community. | 4 |
| 98 | The Pope has both swords. | 5 |
| 101 | The theory of two co-ordinate powers. | 6 |
| 105 | Imperial theory contested. | 3 |
| 107 | Mankind as one Organism. | 4 |
| 112 | Ideas of Membership, Differentiation, Function, and the like. | 8 |
| 115 | Medieval preference for a Monarchy. | 5 |
| 118 | The Monarch's position. | 3 |
| 120 | The idea of Sovereignty. | 4 |
| 123 | Popular sovereignty in the State. | 5 |
| 125 | Reversion of power to the People. | 6 |
| 128 | The system of Ruler's Sovereign. | 5 |
| 131 | Republicanism of Marsilius. | 3 |
| 135 | Supremacy of the Council. | 4 |
| 139 | Theory of Cusanus. | 3 |
| 144 | Ockham and the Laity. | 4 |
| 148 | Representation in Assemblies. | 3 |
| 153 | Failure of political theory. | 4 |
| 156 | The People's Personality. | 3 |
| 159 | The idea of Natural Law. | 5 |
| 162 | The Prince not bound by Law. | 6 |
| 166 | Innate Rights and Acquired Rights. | 5 |
| 169 | Void acts of State. | 4 |
| 173 | Origin of the State in Contract. | 6 |
| 177 | Revolutionary elements in Natural Law. | 5 |
| 181 | Definition of the State. | 4 |
| 184 | Philosophic theory and the Rights of Fellowships. | 7 |
