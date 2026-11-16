# Plan: structure, the second part

This plan builds the rest of the book's structure on top of the first
plan (`docs/plans/regions-and-paragraphs.md`, merged into `main`):

- note markers and references, linked; notes over a page break; notes
  left in the body; Gierke's endnotes;
- margin notes placed before the paragraph they stand beside, and
  Stubbs' notes cut into the text column taken out of the body lines;
- headings with their level and chapter label, chapter summaries, quotes
  and verse, Haskins' bibliographical notes as paragraphs;
- the entries of a printed index, and its guide words removed;
- plates: analyze recognises them, extract cuts the page's picture,
  structure keeps the caption and removes the stray words;
- markdown and the EPUB writing every new kind.

It is built from `docs/specs/structure.md` §11 to §20,
`docs/specs/layout.md` §3 (the book's measures, step 2b) and §9,
`docs/specs/plates.md`, and `docs/architecture.md` §6, §8, §9, §12,
§13 and §17, settled by the owner on 15 and 16 November 2026. It ends
with the six books' EPUBs and the evaluation tool's scores against the
targets of structure §9, "The second plan". Dated 16 November 2026.
State: under way (approved by the owner on 16 November 2026).

The seven work packages are the breakdown the owner approved in chat on
16 November 2026. "Structure §11" below is section 11 of
`docs/specs/structure.md`, "layout §3" of `docs/specs/layout.md`,
"plates §2" of `docs/specs/plates.md`.

## In and out

In: everything structure §11 to §19 and plates §2 to §6 describe; layout
§3 step 2b and the cut-in insets; the shared module `body_measures.py`
and `wordlist.is_known_word` (architecture §12); the format changes of
architecture §6 and §8; five new excerpts and their reference pages;
the configs of the six sample books; one measurement for the owner,
with nothing built: what re-reading Gierke's small-print margin notes
with Tesseract would cost and give.

Out: the correct stage, and the review of guessed hyphen joins; the
index's page numbers as links (the index stage); galley's own OCR of
pages and the OCR audit; the text quality of Mariéjol, whose scan is
poor (it is tested for structure only); removing specks read as margin
notes; tables; figures inside text pages; italics.

The specs have no open point: the owner decided the last three on 16
November 2026 (layout §9; structure §20). Two things the specs leave to
this plan's tasks are named where they fall: how markdown writes each
kind (structure §19 leaves it to the markdown stage; task 7.1), and the
evaluation tool's reading of the new kinds, which structure §21 says is
a change to `docs/specs/evaluation.md` before the scores are taken
(task 7.4).

## What must be in place

Checked on 16 November 2026 at c8d7863 (`spec/structure-2`), and checked
again by the orchestrator before task 1.1, in the plan's worktree:

- `which pandoc tesseract combine_tessdata dawg2wordlist epubcheck`
  prints five paths (Pandoc 3.14), and `tesseract --list-langs` lists
  `eng` and `fra`.
- `uv run --locked pytest` passes: 1049 passed, 16 deselected, in 23.3 s.
- The six whole books are in `samples/public_domain/` of the main
  checkout, with the four Gutenberg HTML files under `gutenberg/`.
- The baseline: `uv run galley-eval run` on the starting commit, whose
  code is that of `main` (fb9c8e8, the first plan merged). Run on 16
  November 2026 in this worktree (75 s); the orchestrator runs it again
  in the plan's worktree before task 1.1 and copies `runs/evaluation/`
  to `runs/structure-second-baseline/` of the main checkout. Its numbers
  for the targets, at blocks:

  | score | Haskins | Stubbs | Domesday | Mariéjol |
  |---|---|---|---|---|
  | notes whose reference is right (`reference_right`) | 0 of 72 | (no notes) | 0 of 1,731 | 0 of 1,432 |
  | margin notes as margin notes | (none) | 0 of 467 | 514 of 593 | (none) |
  | reference headings in `heading` blocks | 0 | 0 | 0 | 0 |
  | index, paragraph boundaries, precision / recall | 0.17 / 0.00 | 0 / 0 | 1.0 / 0.00 | (no index) |

The plan's branch, `plan/structure-second`, is made from
`spec/structure-2`, not from `main`, because the specs it is built from
are on that branch and the owner has not ordered it merged. Merging the
plan's branch into `main` brings them in.

## The order of the work, and the streams

The work packages are numbered by what they give; they do not all run in
that order. Work package 1 changes the shared files and runs first, on
the plan's branch. Then three streams run side by side, each in a
worktree of its own (the `following-plans` skill, "Parallel streams"):

| stream | tasks | starts | may change |
|---|---|---|---|
| `markdown` | 7.1, 7.2 | after WP 1 | `src/galley/markdown/`; `src/galley/epub/` (the style sheet); `tests/test_markdown.py`; `tests/test_epub.py`; `tests/fixtures/epub/` |
| `plates` | 6.1, 6.2 | after WP 1 | `src/galley/analyze/`; `src/galley/extract/`; `src/galley/cli.py`; `tests/test_analyze.py`; `tests/test_extract.py`; `tests/test_cli.py`; `tests/conftest.py`; `evaluation/books.toml`; `tests/test_layout.py` and `tests/test_structure.py` for the whole-book configs only |
| `layout` | 3.1 | after WP 1 | `src/galley/layout/`; `tests/test_layout.py` except the whole-book configs; `tests/fixtures/expected/stubbs_51_56-64_*.json` |
| `notes` | 2.1 to 2.5 | when `markdown` is merged | `src/galley/structure/`; `tests/test_structure.py` except the whole-book configs; `tests/test_excerpts.py`; `tests/fixtures/expected/` except Stubbs' files while `layout` runs |

`markdown` goes first among the structure work because markdown today
refuses every kind it does not write, a referenced note among them, and
every excerpt test runs `galley2epub run` through markdown: a structure
that links a note before markdown writes one fails the excerpt tests.
So `notes` starts when `markdown` is merged, and runs beside `plates`
if `plates` is still running, as the owner asked, and beside `layout`.
No more than three streams run at once.

After the streams are merged and reviewed, the rest runs on the plan's
branch in this order, because each changes `src/galley/structure/`:
3.2, 4.1 to 4.3, 5.1 and 5.2, 6.3, then 7.3 to 7.6.

`model.py`, `fidelity.py`, `config.py`, `pyproject.toml`,
`docs/architecture.md` and `docs/glossary.md` are changed in work
package 1 only. A stream that finds it needs one of them stops and asks
the orchestrator, who makes the change on the plan's branch and merges
it into the streams.

Each task keeps every check passing. A task whose change alters the
output on a committed reference page (`tests/fixtures/expected/`)
updates that file in the same commit, and the commit names each change
and the spec part that causes it; the orchestrator checks each against
the page image before ticking the task.

## 1. Foundations

**What it gives.** The formats of the second plan exist and are read
and written: `blocks.json` at version 2 with the new kinds, note kinds,
heading labels and guide-word removals; the config keys
`contents_pages` and `plate_pages`. layout and structure measure the
body text with one module, and analyze and structure tell known words
with one function. The five new excerpts are committed, and the six
sample books' configs name their contents pages and the pages that are
not plates. Nothing a reader sees changes yet.

**Deliverables.**

1. The format changes of architecture §8, as structure §7 lists them
   (`BlockKind.chapter_summary` and `verse`, `NoteKind` and `Note.kind`,
   `Block.label`, `RemovalReason.guide_words`, margin-note blocks among
   a note's blocks, `blocks.json` version 2), with their read and write
   functions: `uv run python -c "from galley.model import
   BLOCKS_FORMAT_VERSION, NoteKind; assert BLOCKS_FORMAT_VERSION == 2"`
   passes (fails at c8d7863: no `NoteKind`); `uv run pytest
   tests/test_model.py -k "label or note_kind or chapter_summary or verse
   or guide_words" --collect-only -q` lists at least 6 tests (0 at
   c8d7863), and the test of an unsupported `format_version`
   (`tests/test_model.py`, line 588 at c8d7863) no longer uses 2 for
   `blocks.json`.
2. The fidelity changes of architecture §13: a heading's label counted
   as words of its block at structure and at markdown; a reference
   span with a marker's shape that names a note of the file; an
   endnote's marker counted at markdown. The two failing cases of
   structure §9, "The second plan" (a reference span "land"; one that
   names no note) are tests that pass, and `uv run pytest
   tests/test_fidelity.py -k "label or endnote" --collect-only -q` lists
   at least 4 (0 at c8d7863).
3. The config keys `contents_pages` and `plate_pages` (architecture §6),
   and analyze's check of their page indices: `uv run pytest
   tests/test_config.py tests/test_analyze.py -k "contents_pages or
   plate_pages" --collect-only -q` lists at least 4 (0 at c8d7863).
4. `src/galley/body_measures.py` as architecture §12 gives it, used by
   layout and structure: `uv run python -c "import
   galley.body_measures"` passes (fails at c8d7863), its tests are in
   `tests/test_body_measures.py`, and `grep -rnE "def
   (_?commonest|_rows|_body_measures)\b" src/galley/layout
   src/galley/structure` prints nothing (4 lines at c8d7863). layout's
   output on the six excerpts is unchanged: the committed expected
   outputs pass untouched.
5. `wordlist.is_known_word` (plates §4) on the word key of structure §5,
   which structure's hyphen rule then takes from the same place: `uv run
   pytest tests/test_wordlist.py -k known_word --collect-only -q` lists
   at least 5, the cases of plates §6 (0 at c8d7863).
6. The five excerpts of structure §9, "The second plan", committed and
   cut by `scripts/fetch_samples.py` with what each covers: `uv run
   pytest tests/test_excerpts.py --collect-only -q | grep -cE
   "haskins_quotes_index|stubbs_summaries_index|domesday_headings_quotes|mariejol_headings_verse|kadesh_59-68"`
   gives at least 5 (0 at c8d7863), and `uv run pytest
   tests/test_excerpts.py` passes with their configs in
   `EXCERPT_CONFIGS` (`tests/conftest.py`), `contents_pages` among them
   for `stubbs_summaries_index` (excerpt page 0) and
   `domesday_headings_quotes` (excerpt page 0).
7. The six sample books' configs, in one place in `tests/conftest.py`
   that the whole-book tests of layout and structure share, and in
   `evaluation/books.toml`: `contents_pages` Haskins [14], Stubbs [14,
   15, 16], Domesday [14 to 20], Mariéjol [450], Gierke [10], Kadesh
   none (found on 16 November 2026 by the word "CONTENTS" or "TABLE DES
   MATIERES" at the top of the page, and checked by reading each page's
   text layer); `exclude_pages` adding the pages plates §2 lists as
   taken wrongly, Kadesh 0, 49, 65 and Mariéjol 1, 2, 457, 458; Kadesh's
   `plate_pages` [23]. `grep -c contents_pages evaluation/books.toml`
   gives 4 (0 at c8d7863), and galley-eval passes the key to the
   `book.toml` it writes. `uv run pytest -m whole_book` passes.
8. `uv run --locked pytest` stays within the `coding` skill's 30 s.

**Stands on:** the first plan, merged; the whole books.

**What could go wrong.** The five new excerpts add five runs of the
whole pipeline to the session's `excerpt_books` fixture, about 1 s
each; the default run is at 23.3 s of its 30 s. If it goes over, the
new excerpts' end-to-end tests are the first to move to a fixture of
their own scope, and the report says so. The plates without a text
layer stay in `exclude_pages` until task 6.1, because analyze refuses
them until then.

- [x] 1.1 The format changes in `model.py`, the config keys in
  `config.py` and analyze's check of their page indices, and the
  fidelity changes in `fidelity.py`, with their tests. Spec:
  architecture §6, §8 and §13; structure §7. Deliverables 1 to 3. A
  commit of its own, first: every other task stands on it.
- [ ] 1.2 `body_measures.py`, replacing layout's and structure's
  copies, and `wordlist.is_known_word` with the word key. Spec:
  architecture §12; layout §3, "The book's measures"; structure §2,
  step 1; plates §2 and §4. Deliverables 4, 5, 8.
- [ ] 1.3 The five excerpts and their configs. Spec: structure §9, "The
  second plan", the list of new excerpts. Needs 1.1 for
  `contents_pages`. Deliverables 6, 8.
- [ ] 1.4 The six books' configs in one place, and galley-eval passing
  `contents_pages` through. Spec: plates §2, "The configs of the sample
  books"; architecture §6. Needs 1.1. Deliverable 7.

## 2. Footnotes and endnotes

**What it gives.** `galley2epub structure` cuts each footnote band into
notes, takes each note's marker out of its text, joins a note that runs
over a page break, takes the notes that layout left at the foot of the
body, and links each reference in the text to its note, split off the
word it is glued to. Gierke's endnotes are notes of kind `endnote`,
linked across the book, with the margin notes printed beside them
inside them.

**Deliverables.**

1. The unit tests of structure §9, "The second plan", for `note_marker`,
   `reference_candidate`, notes, endnotes and the margin note beside an
   endnote's line: one test or more per case named there. `uv run pytest
   tests/test_structure.py -k "note_marker or reference_candidate or
   footnote or endnote or referenced" --collect-only -q` lists at least
   20 (0 at c8d7863).
2. On the excerpts, tests in `tests/test_excerpts.py` with the literals
   of structure §9's reference table, before the owner checks the whole
   pages in task 7.3: Domesday excerpt page 0 (74) has seven references
   linked, "pleased1/" to "mercy7.'", and note 7's marker is "«"; page 2
   (76) has two notes on one line; Gierke's pages 8 and 9 (270, 271) give
   12 notes of kind `endnote`, 291 to 302, unreferenced, with the end
   of note 290 an endnote without a marker; Mariéjol excerpt page 4
   (214) has one note run on from page 213; Mariéjol excerpt page 0
   (210) has five marker-led paragraphs, none run on into page 211.
   `uv run pytest tests/test_excerpts.py -k "footnote or endnote or
   referenced" --collect-only -q` lists at least 5 (0 at c8d7863).
3. `make_blocks` with 1 worker and with 3 gives the same value on pages
   with notes, references and endnotes.
4. The fidelity check passes on the six excerpts and, with `uv run
   pytest -m whole_book`, on the six books.

**Stands on:** work package 1; the `markdown` stream merged, so that
`galley2epub run` writes the linked notes.

**What could go wrong.** The matching of references is the part of the
spec measured only on a prototype (structure §11, "What the rules
give"); its scores are known only in task 7.5. Kadesh's notes on pages
9, 11 and 13 to 15 are too damaged to cut, and stay notes without a
marker (structure §11, "Where the rules fail").

- [ ] 2.1 Where a note starts, its marker and value, two notes on one
  line, and a note that runs over a page break; `note_marker`. Spec:
  structure §11, "Where a note starts", "The marker of a note", "A note
  that runs over a page break". Deliverables 1, 3.
- [ ] 2.2 Notes left in the body (structure §2, step 2.5), and the
  marker-led body block that is never run on into the next page and
  that the quote rules of task 4.3 will skip. Spec: structure §11,
  "Notes left in the body"; §16, the paragraph before rule 1. Needs 2.1.
  Deliverables 1, 2.
- [ ] 2.3 References: the candidates, the book's reference form, the
  matching, and the `note_marker` splits; `reference_candidate`. Spec:
  structure §11, "References". Needs 2.1. Deliverables 1 to 3.
- [ ] 2.4 The endnote section, its notes, and their references matched
  over the whole book. Spec: structure §12; §2, steps 1 and 3.1. Needs
  2.3. Deliverables 1, 2.
- [ ] 2.5 The line a margin note stands beside (structure §13, rule 2),
  and a margin note beside a note's line placed inside that note (rule
  5); `make_blocks` and `run` with the steps of structure §2 in their
  order. Spec: structure §13, rules 2 and 5; §2. Needs 2.4.
  Deliverables 1 to 4.

## 3. Margin notes

**What it gives.** layout takes Stubbs' notes cut into the text column
out of the body lines beside them (layout §3, step 2b), so that they
become margin notes; structure places every margin note before the
paragraph whose line it stands beside, and starts a paragraph at an
indented line beside a margin note.

**Deliverables.**

1. The unit tests of layout §8 for the cut-in notes and the cut-in
   insets, two bullets: `uv run pytest tests/test_layout.py -k cut_in
   --collect-only -q` lists at least 6 (0 at c8d7863); and the excerpt
   test of layout §8 that `measure_book` gives no inset for the five
   excerpts other than `stubbs_51_56-64`, and both insets for it.
2. On the Stubbs excerpt, page 2 (57) of `lines.json` has the margin
   regions "Characterof Henry II." and "Hisfamily policy." (layout §8),
   in a test of `tests/test_layout.py`; the expected outputs of
   `stubbs_51_56-64` pages 0 and 9 are updated by the words layout §8's
   table says each loses to its margin notes, and the orchestrator
   checks each against the page image.
3. The unit tests of structure §9 for margin notes, the four cases
   (task 2.5 built the fifth): `uv run pytest tests/test_structure.py -k
   "margin_note_before or margin_note_inside or beside" --collect-only
   -q` lists at least 5 (0 at c8d7863).
4. On the Domesday excerpt page 1 (75), each margin note is before the
   paragraph whose first line it stands beside, and "Can the villein be
   pursued?" before the paragraph that starts on the page's last line; on
   the Stubbs excerpt page 3 (58), "His great position in Christendom"
   (as the OCR reads it) is before its paragraph. Tests in
   `tests/test_excerpts.py`.
5. Layout's fidelity check passes on Stubbs' whole book, and the number
   of words step 2b moves there is in the report against layout §3's
   1,314.

**Stands on:** work package 1; for task 3.2, work package 2.

**What could go wrong.** Step 2b's precision is 0.913 by the measure of
layout §3, below the bar of 0.95 that the owner set aside: about 50
body words of Stubbs move into margin notes. The excerpt is measured on
its own ten pages, and its insets (60.3 and 58.2 pt) differ a little
from the book's (60.4 and 59.0).

- [ ] 3.1 The cut-in insets in `measure_book` and step 2b in
  `layout_page`. Spec: layout §3, "The book's measures" and step 2b;
  §4; §6, "Stubbs' cut-in notes"; §8. Stream `layout`. Deliverables 1,
  2, 5.
- [ ] 3.2 Placing margin notes: one printed note one block, the indented
  line beside a margin note, before the paragraph that holds the line,
  and a margin note alone on its page. Spec: structure §13, rules 1, 3,
  4 and 6. Needs 2.5 and 3.1. Deliverables 3, 4.

## 4. Headings, chapter summaries, quotes and verse

**What it gives.** Chapter and section headings become `heading` blocks
of level 1 or 2, the chapter label in `label`; no heading is made on
the config's contents pages; Stubbs' chapter summaries are
`chapter_summary` blocks; quotes in smaller or inset type are `quote`
blocks, verse is `verse` blocks with their line breaks; Haskins'
bibliographical notes are paragraphs.

**Deliverables.**

1. The unit tests of structure §9, "The second plan", for headings,
   chapter summaries, quotes and verse, and Haskins' bibliographical
   notes, one test or more per case: `uv run pytest
   tests/test_structure.py -k "heading or label or chapter_summary or
   bibliographical or quote or verse" --collect-only -q` lists at least
   18 (0 at c8d7863).
2. On the excerpts, tests with the literals of structure §9's reference
   table: Haskins excerpt page 0 (131), one level-1 heading, label "V",
   text "NORMANDY AND FRANCE"; Stubbs excerpt page 0 (51), label
   "CHAPTER III.", one `chapter_summary` block of the 3 lines, "Very few
   epochs…" starting a paragraph; `stubbs_summaries_index` page 0, no
   heading; `mariejol_headings_verse` pages 1 and 2 (51, 52), one `verse`
   block; `haskins_quotes_index` page 0 (39), the level-2 heading
   "BIBLIOGRAPHICAL NOTE" and paragraphs after it, page 5 (129), its band
   blocks paragraphs. `uv run pytest tests/test_excerpts.py -k "heading
   or summary or verse or quote or bibliographical" --collect-only -q`
   lists at least 6 (0 at c8d7863).
3. `make_blocks` with 1 worker and with 3 gives the same value on these
   pages, and the whole-book fidelity check passes.

**Stands on:** work packages 1 and 2 (the quote rules skip the notes and
marker-led blocks of tasks 2.2 and 2.3).

**What could go wrong.** The heading rule's false headings are known
(structure §14, "Where it fails"): Domesday's table titles, Gierke's
"Macrocosm and Microcosm." at the top of excerpt page 6. They are
expected, not fixed. Rule 4 of verse takes Domesday's tables inset on
both sides.

- [ ] 4.1 Heading lines, chapter labels, continuations, heading blocks
  with `label` and levels, and `contents_pages`. Spec: structure §14;
  §2, step 2.3. Deliverables 1 to 3.
- [ ] 4.2 Chapter summaries and verse (rule 4), per page, and a verse
  block over a page break. Spec: structure §15; §16, rule 4; §2, steps
  2.3, 2.4 and 3.1. Needs 4.1. Deliverables 1 to 3.
- [ ] 4.3 Quotes (rules 1 to 3), the marker-led exclusion, and Haskins'
  bibliographical notes. Spec: structure §16, "The rules" and "Haskins'
  bibliographical notes"; §2, steps 3.1 and 3.5. Needs 4.2.
  Deliverables 1 to 3.

## 5. Index entries and guide words

**What it gives.** A printed index comes out as one `index_entry` block
per entry, its sub-entries inside it as printed, the rows layout read
across both columns cut at the gutter, and Stubbs' guide words removed
as `guide_words`.

**Deliverables.**

1. The unit tests of structure §9 for the index: `uv run pytest
   tests/test_structure.py -k "index_entr or guide_words or gutter"
   --collect-only -q` lists at least 4 (0 at c8d7863).
2. On the excerpts: Haskins excerpt page 9 (266) has the heading "INDEX"
   and one `index_entry` per entry of the left column, then the right;
   `stubbs_summaries_index` pages 4 to 9 have one `guide_words` removal
   each; `haskins_quotes_index` page 9 (269) has "Calabria" as one entry
   from the foot of one column to the top of the next. `uv run pytest
   tests/test_excerpts.py -k "index" --collect-only -q` lists at least 3
   (0 at c8d7863).
3. The whole-book fidelity check passes.

**Stands on:** work package 4 (the index title is a heading; quotes run
after the index entries, structure §2).

- [ ] 5.1 Index pages, the regions of an index page, the cut at the
  gutter, and guide words. Spec: structure §17, rules 1 and 2.
  Deliverables 1 to 3.
- [ ] 5.2 Entries over columns and pages, with the skewed left edge, and
  the `index_entry` blocks. Spec: structure §17, rules 3 and 4. Needs
  5.1. Deliverables 1 to 3.

## 6. Plates

**What it gives.** analyze marks plate pages, with or without a text
layer, and names in its log each page its rule took; extract saves each
plate's page as an image and gives the page its figure; structure keeps
a plate's caption as the text of a `figure` block, removes its running
head and stray words, and lets the paragraph around the plate run on.

**Deliverables.**

1. The unit tests of plates §6 for `is_plate`: `uv run pytest
   tests/test_analyze.py -k "plate_pages or is_plate" --collect-only -q`
   lists at least 7 (0 at c8d7863).
2. On the excerpts, with the owner's check of each image in task 7.3:
   `kadesh_8-17` page 8 (16) is a `plate` with
   `images/plate-0008.png`, and page 9 (17), no longer excluded in its
   config, a `plate` without a text layer; `kadesh_59-68` pages 5 (64),
   6 (65) and 9 (68) and `domesday_headings_quotes` pages 3 and 4 (39,
   40) are plates. Tests in `tests/test_analyze.py` and
   `tests/test_extract.py`.
3. `galley2epub` checks for Tesseract's word-list tools before analyze
   when the language is not cached: a test in `tests/test_cli.py`.
4. A `whole_book` test asserts the 22 plates of plates §1 with the
   configs of task 1.4, from which the plates without a text layer have
   been taken out of `exclude_pages`.
5. The unit tests of structure §9 for plates: `uv run pytest
   tests/test_structure.py -k "plate_text or caption or figure_block"
   --collect-only -q` lists at least 2 (0 at c8d7863); on `kadesh_8-17`
   page 8, two `plate_text` removals and a figure block with no text
   after the paragraph that runs over the page.
6. The time analyze takes on Domesday's 558 pages, against plates §2's
   12.6 s for the renders, is in the report.

**Stands on:** work package 1 (`plate_pages`, `is_known_word`); for task
6.3, work packages 2 to 5.

**What could go wrong.** The thresholds have thin margins (plates §2):
Kadesh 16's largest group is 70 squares against 50, Mariéjol 265's 26
known words against 20. A render of every page adds about 12.6 s to
analyze on Domesday.

- [ ] 6.1 analyze: the render, `is_plate`, `plate_pages`, the warning
  log, the word list taken by analyze and the CLI's check for it; the
  plates without a text layer out of the six books' `exclude_pages` and
  the excerpt configs; the `whole_book` test of the 22 plates. Spec:
  plates §2, §4 and §5. Stream `plates`. Deliverables 1, 3, 4, 6.
- [ ] 6.2 extract: a plate page's image and figure, its text layer read
  as a text page's, and the refusal of a plate page removed. Spec:
  plates §3. Stream `plates`. Needs 6.1. Deliverable 2.
- [ ] 6.3 structure: a plate's running head, caption lines and stray
  words, and the figure block as side text of its page. Spec: structure
  §18; §2, step 2.2; §6. Needs 6.2 and work package 5. Deliverable 5.

## 7. Markdown, the EPUBs and the measurement

**What it gives.** `book.md` and the EPUB carry every new kind, written
by what it is (owner, 15 November 2026: a kind says what a text is, and
markdown and epub decide how it looks): headings with their label, each
other kind with a class of its own, verse with its line breaks, margin
notes as a small bold line, referenced footnotes as pop-ups, endnotes
in one list where they were printed and as pop-ups from their
references. The six books' EPUBs are built and pass epubcheck. The
evaluation scores are measured against the baseline and the targets.
The owner gets the numbers to decide on re-reading Gierke's margin
notes with Tesseract.

**Deliverables.**

1. markdown's unit tests of structure §19, one or more per bullet:
   `uv run pytest tests/test_markdown.py -k "verse or chapter_summary or
   endnote or noteref or label or footnote" --collect-only -q` lists at
   least 10 (0 at c8d7863); the refusal test refuses no kind of
   architecture §8.
2. An EPUB built from a hand-made `blocks.json` with every kind, a
   referenced footnote with a margin note, and two endnotes, one
   referenced, passes epubcheck, and its chapter files hold a link with
   `epub:type="noteref"` to the endnote and a `<br />` inside the verse:
   `uv run pytest tests/test_epub.py -k "every_kind or endnote or verse"
   --collect-only -q` lists at least 1 (0 at c8d7863), and it passes.
3. The reference pages of structure §9, "The second plan", and the
   updated ones of the first plan, as exact tests after the owner's
   check: `uv run pytest tests/test_excerpts.py -k reference
   --collect-only -q` lists at least 66 (33 at c8d7863), and all pass.
4. galley-eval reads `blocks.json` version 2 and the new kinds as the
   change to `docs/specs/evaluation.md` says: `uv run pytest
   tools/galley-eval/tests/test_galley_side.py -k "verse or
   chapter_summary or endnote or heading_label" --collect-only -q` lists
   at least 4 (0 at c8d7863).
5. The targets of structure §9, "The second plan", in the report, each
   with its baseline (above) and this plan's value, and for each missed
   one its cause found in `differences.jsonl`:

   | score | Haskins | Stubbs | Domesday | Mariéjol |
   |---|---|---|---|---|
   | notes whose reference is right | at least 45 of 72 | (no notes) | at least 1,250 of 1,731 | at least 350 of 1,432 |
   | margin notes as margin notes | (none) | at least 200 of 467 | at least 400 of 593 | (none) |
   | reference headings in `heading` blocks, body range | at least 17 of 18 | at least 24 of 26 | at least 20 of 23 | at least 24 of 26 |
   | index, paragraph boundaries, precision / recall | at least 0.90 / 0.90 | 0.85 / 0.85 | 0.90 / 0.90 | (no index) |

   And the first plan's scores (paragraph boundaries, extra tokens,
   hyphen splits left, notes as notes) beside its report's values, with
   any that fell below the first plan's target explained.
6. `uv run pytest -m whole_book` passes; the six EPUBs are built from
   the whole books with the configs of task 1.4 and pass epubcheck, in
   `runs/structure-second/epubs/` of the main checkout.
7. A section of the report for the owner: what re-reading Gierke's
   margin notes with Tesseract costs (seconds per page, the machine and
   threads) and gives (on 30 margin notes of pages 86 to 185 of the
   whole book, read by eye against the page image: the words right in
   the text layer and in Tesseract's reading), with no code added under
   `src/`. Absent at c8d7863.

**Stands on:** tasks 7.1 and 7.2: work package 1. Tasks 7.3 to 7.6: work
packages 1 to 6.

**What could go wrong.** Pandoc places footnotes at the end of each
chapter file and an endnote list must stay where it was printed; a
link into another chapter file was checked with Pandoc 3.14 but the
pop-up itself was never tried on a Kindle (architecture §9). The
heading target is for the body range, which the tool does not score
today; the change of task 7.4 has to give it.

- [ ] 7.1 markdown: headings with their label, the classes of
  `quote`, `verse`, `chapter_summary`, `index_entry` and `figure`
  blocks, verse line breaks, figures as images with their caption, and
  the style sheet for each class, margin notes as a small bold line.
  How each is written is this task's to decide, within structure §19
  and architecture §9; the task writes it into a section of the
  markdown stage's docstring and the report. Stream `markdown`.
  Deliverables 1, 2.
- [ ] 7.2 markdown: referenced footnotes as Pandoc footnotes with their
  margin notes inside, unreferenced footnotes as now, endnotes as one
  list where `notes` puts them with `epub:type="noteref"` links. Spec:
  structure §19; architecture §9 and §13. Stream `markdown`. Needs 7.1.
  Deliverables 1, 2.
- [ ] 7.3 The reference pages: a sheet for the owner, one section per
  page of structure §9's reference table and layout §8's Stubbs pages,
  with the page image, then layout's regions and structure's output on
  the page; after the owner's answer, the expected outputs under
  `tests/fixtures/expected/` and their tests. The plan's one pause for
  the owner; 7.4 and 7.6 run while waiting. Spec: structure §9, "The
  second plan", "Reference pages"; plates §6, "Excerpt tests".
  Deliverable 3.
- [ ] 7.4 The change to `docs/specs/evaluation.md` that structure §21
  names (`chapter_summary` and `verse` against the reference text's
  quotes, `endnote` against its notes, one heading block with a label
  against the two headings Stubbs' and Mariéjol's reference texts make,
  a heading's label as tokens, and the headings of the body range), a
  commit of its own reviewed by the `spec-reviewer`, then the tool.
  Deliverable 4.
- [ ] 7.5 The measurement: galley-eval on the four books against the
  baseline, the whole-book tests, the six EPUBs. Spec: structure §9,
  "Targets measured by `galley-eval run`"; `docs/specs/evaluation.md`
  §9. Needs 7.3 and 7.4. Deliverables 5, 6.
- [ ] 7.6 The Gierke measurement: Tesseract on the margin regions of
  Gierke's pages 86 to 185, cropped from a 300-dpi render, by a script
  kept outside `src/` and not committed; the numbers in the report.
  Spec: architecture §7b and §16 for how Tesseract is called; nothing is
  built. Deliverable 7.

A missed target does not stop the plan: it is reported with its cause,
and what fixing it would take goes to the owner as a proposal.

## How the whole plan is checked at the end

- The checks of the `coding` skill on the plan's branch, with pytest
  once normally and once with 8 threads, and `uv run pytest -m
  whole_book`.
- Work package 7's deliverables 5 and 6, run again after the last fix.
- For the owner on the Kindle: Gierke's EPUB at its endnotes (a pop-up
  from "Law1" on book page 88, the list after "NOTES."), Domesday's
  around book page 76 (footnote pop-ups, margin notes before their
  paragraphs), Stubbs' chapter III (the heading with its label, the
  chapter summary, the cut-in notes), Mariéjol's verse around page 51,
  and Kadesh's plates on pages 16 and 64.
