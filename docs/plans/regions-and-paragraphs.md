# Plan: regions and paragraphs

This plan builds the first part of the book's structure:

- layout cuts each page into regions: the body column, outer margin
  notes, the running-head line, the footnote band, columns and the drop
  capital;
- structure removes running heads, page numbers, signature marks and
  stray marks, joins hyphens, and builds paragraphs across page breaks,
  with side text as margin notes and unreferenced notes;
- the markdown stage writes those margin notes and notes.

It is built from `docs/specs/layout.md` and `docs/specs/structure.md`,
both settled by the owner on 15 November 2026. It ends with the
evaluation tool's scores on the four evaluation books against the
targets of structure §9. Dated 15 November 2026. State: under way
(approved by the owner on 15 November 2026).

The six work packages are the breakdown the owner approved in chat on
15 November 2026. "Layout §3" below is section 3 of `docs/specs/layout.md`,
"structure §5" section 5 of `docs/specs/structure.md`.

## In and out

In: layout as layout §3 to §8 give it; structure as structure §2 to §9
give it, with the three new enum values of structure §7; the markdown
change of structure §10, option (b); three new excerpts; the reference
pages of layout §8 and structure §9 as exact tests, once the owner has
checked them; the first evaluation run after the baseline.

Out, for the second plan (structure §11): note markers and references,
notes that run over a page, margin notes placed beside their paragraph,
Stubbs' cut-in notes (layout §9), headings, quotes, index entries, plate
text. Also out: the review of guessed hyphen joins, by the correct stage
or a local model, and the style of margin notes and notes in the EPUB.

The specs have no open point.

## What must be in place

Checked by the orchestrator before task 1.1, in the plan's worktree:

- `which pandoc tesseract combine_tessdata dawg2wordlist epubcheck`
  prints five paths, and `tesseract --list-langs` lists `eng` and `fra`.
- `uv run --locked pytest` passes on the starting commit (781 passed, 8
  deselected, on `spec/structure` at 4efdea1, 15 November 2026).
- The six whole books are in `samples/public_domain/` of the main
  checkout, with the Gutenberg HTML of the four evaluation books under
  `gutenberg/`; `uv run galley-eval --help` works.
- The baseline scorecards of `docs/reports/evaluation.md` can be
  regenerated: `galley-eval compare` reads the old run's folder, or the
  baseline numbers of that report are used as they stand.

## Streams and the files they may change

Work packages 1, 2 and 3 run side by side as three streams; work package
4 runs in the `excerpts` stream after work package 1. Work packages 5
and 6 run on the plan's branch after the three streams are merged and
reviewed.

| WP | stream | tasks | may change |
|---|---|---|---|
| 1 | `excerpts` | 1.1 | `scripts/fetch_samples.py`; `tests/fixtures/pdf/`; `tests/test_excerpts.py` |
| 2 | `layout` | 2.1–2.4 | `src/galley/layout/`; `tests/test_layout.py` |
| 3 | `structure` | 3.1–3.5 | `src/galley/structure/`; `tests/test_structure.py`; `src/galley/model.py`, `tests/test_model.py`; `src/galley/fidelity.py`, `tests/test_fidelity.py`; `src/galley/cli.py`, `tests/test_cli.py`; `docs/architecture.md`; `docs/glossary.md` |
| 4 | `excerpts` | 4.1 | `src/galley/markdown/`; `tests/test_markdown.py` |
| 5 | (plan branch) | 5.1–5.2 | `tests/test_excerpts.py`, `tests/test_layout.py`, `tests/test_structure.py`; `tests/conftest.py` (the new excerpts' configs); `tests/fixtures/expected/` (new) |
| 6 | (plan branch) | 6.1 | `docs/reports/regions-and-paragraphs.md`; `tests/` for `whole_book` tests only |

The `structure` stream is the only one that changes the shared files.
Work package 4 reads the enum values the `structure` stream adds only
through `BlockKind.MARGIN_NOTE` and `Note.referenced`, which `model.py`
already has; it writes its own blocks in its tests. The `layout` and
`structure` streams meet only through the format of `lines.json`
(architecture §8), which does not change: structure's tests build
`LinesFile` values by hand, and structure runs on layout's real output
only in work package 5.

## 1. Three new excerpts

**What it gives.** `uv run python scripts/fetch_samples.py` cuts the
excerpts `stubbs_51_56-64`, `domesday_74-83` and `mariejol_210-219`
from the whole books and they are committed under `tests/fixtures/pdf/`,
with the pages and contents layout §8 lists.

**Deliverables.**

1. The three PDFs are committed, ten pages each, every page with a text
   layer: `uv run pytest tests/test_excerpts.py -q` passes, and its
   parametrized tests list the three new names
   (`--collect-only -q | grep -c "stubbs_51_56-64\|domesday_74-83\|mariejol_210-219"`
   gives at least 3; 0 on the starting commit).
2. The whole pipeline runs on each of them: `uv run galley2epub` writes
   an EPUB for each, and `epubcheck` passes on it.

**Stands on:** the whole books in `samples/public_domain/`.

- [x] 1.1 Add the three excerpts to `scripts/fetch_samples.py`, with
  what each covers, cut and commit them. Spec: layout §8, the list of
  new excerpts. Deliverables 1, 2.

## 2. Layout cuts pages into regions

**What it gives.** `uv run galley2epub layout <folder>` writes a
`lines.json` whose pages hold several regions: the running-head line,
the body column (in two regions where it has columns), each outer margin
note, and the footnote band. Same format as today.

**Deliverables.**

1. The unit tests of layout §8 pass: one test or more per bullet of its
   "Unit tests" list, eight bullets; `uv run pytest tests/test_layout.py
   -k "measure_book or margin or band or head or column or drop_capital"
   --collect-only -q` lists at least 8 new tests.
2. Layout's output on 1 worker and on 3 is the same bytes, on a
   hand-made `words.json` of 8 pages (layout §8).
3. The fidelity check at layout's boundary passes on the six excerpts
   and on the six whole books (`uv run pytest -m whole_book -k layout`).
4. On the reference pages of layout §8, the regions look as the spec
   says, checked by the orchestrator against the page image before work
   package 5; the owner checks them in work package 5.
5. The default `uv run pytest` stays within the `coding` skill's time
   budget.

**Stands on:** nothing of this plan; the six excerpts of work package 1
for deliverables 3 and 4, from when it is merged.

**What could go wrong.** The book's measures are taken over every page;
on a ten-page excerpt they are near the whole book's but not equal
(layout §8), so a threshold that sits close to a page's values may cut
the excerpt and the book differently. The footnote band's 0.85 ratio
leaves a fifth of Mariéjol's notes in the body (layout §6); that is
expected and not fixed here.

- [ ] 2.1 The book's measures, `measure_book`, and the body column's
  position. Spec: layout §3, "The book's measures" and step 1.
  Deliverables 1, 5.
- [ ] 2.2 Outer margin notes and the running-head line. Spec: layout §3,
  steps 2 and 3. Deliverable 1.
- [ ] 2.3 The footnote band, columns in the body and in the band, and the
  drop capital. Spec: layout §3, steps 4 to 6, and layout §6. Deliverable
  1.
- [ ] 2.4 `run` with the measures pass before the per-page work, the
  order of regions, and the fidelity check on the excerpts and whole
  books. Spec: layout §4, §5 and §7. Needs 2.1 to 2.3. Deliverables 2,
  3, 4.

## 3. Structure: removals, hyphens, paragraphs and side text

**What it gives.** `uv run galley2epub structure <folder>` writes a
`blocks.json` without running heads, page numbers, signature marks or
stray marks, each kept as a removal with its reason; with hyphens joined
and each join recorded; with paragraphs that run across page breaks;
and with margin regions as `margin_note` blocks and band regions as
notes with `referenced` false.

**Deliverables.**

1. The three enum values of structure §7 are in `model.py`, the lists of
   architecture §8 and the glossary, and the fidelity check verifies
   `hyphen_join_guessed` and `hyphen_kept`: the two failing cases of
   structure §9 ("with a `hyphen_kept` change whose word drops the
   hyphen…") are tests that pass.
2. The unit tests of structure §9 pass, one test or more per bullet of
   its "Unit tests" list, eight bullets; `uv run pytest
   tests/test_structure.py -k "survey or page_number or signature or
   join_hyphen or paragraph or side_text or make_blocks" --collect-only
   -q` lists at least 15 new tests.
3. `make_blocks` with 1 worker and with 3 gives the same value.
4. `galley2epub` checks for Tesseract before structure when the word
   list of the book's language is not cached (structure §8): a test in
   `tests/test_cli.py`.
5. Structure's survey of Domesday's 546 pages takes no more than the
   `coding` skill's budget allows for one stage on a whole book; the
   time is in the report.

**Stands on:** `wordlist.word_list` (merged with the evaluation plan).
Not on work package 2: its tests are on hand-made `LinesFile` values.

**What could go wrong.** The research's rules were measured with the
research's own regions, not layout's; some rules were revised after the
spec's review and not measured again (the spec's targets say so).
Work package 6 shows it.

- [ ] 3.1 The three enum values in `model.py`, architecture §8, the
  glossary and `fidelity.py`. Spec: structure §7. Deliverable 1. A
  commit of its own, first, because the other tasks stand on it.
- [ ] 3.2 `survey_book`, running heads and page numbers in the head,
  stray marks. Spec: structure §1 to §3. Deliverable 2.
- [ ] 3.3 Page numbers at the foot and signature marks. Spec: structure
  §4. Deliverable 2.
- [ ] 3.4 `join_hyphen` and the hyphen joins, inside a page and across a
  page break. Spec: structure §5. Deliverable 2.
- [ ] 3.5 Paragraphs, side text, the order of blocks and notes, ids and
  origins; `make_blocks` and `run`; the Tesseract check in the CLI.
  Spec: structure §6, §8 and §9. Needs 3.1 to 3.4. Deliverables 2 to 5.

## 4. Markdown writes margin notes and unreferenced notes

**What it gives.** The markdown stage accepts `margin_note` blocks and
notes with `referenced` false, and writes them as structure §10, option
(b), says: a fenced div with the class `margin-note` where the block is,
and a fenced div with the class `note` after the last block whose origin
includes the note's first page.

**Deliverables.**

1. Markdown's unit tests of the two new kinds pass: a margin note's div
   with its id and class; a note's div after the right block; a note
   whose page no block covers, after the last block of an earlier page,
   or first of all. The test that the skeleton refuses these is changed
   to refuse only what is still not written (headings, quotes, figures,
   index entries, referenced notes).
2. The fidelity check at markdown's boundary passes on these blocks.
3. An EPUB built from a hand-made `blocks.json` with both kinds passes
   `epubcheck`.

**Stands on:** nothing of this plan.

- [x] 4.1 The two kinds in `src/galley/markdown/`. Spec: structure §10,
  option (b), and architecture §9 and §17 for the div's form. Deliverables
  1 to 3.

## 5. The reference pages, checked by the owner

**What it gives.** The reference pages of layout §8 (14 pages) and of
structure §9 (the same pages, and the two page-break pairs) become exact
tests, after the owner has checked them against the page images.

**Deliverables.**

1. A sheet for the owner, one section per reference page: the page image
   at a readable size, then layout's regions as text, then structure's
   blocks, notes, removals, word changes and page numbers on that page.
   It is published as a private page or written to `tmp/`, whichever the
   owner prefers.
2. After the owner's answer, the expected outputs are committed under
   `tests/fixtures/expected/`, and `uv run pytest tests/test_excerpts.py
   -k reference --collect-only -q` lists one layout and one structure
   test per reference page, and one test per page-break pair; all pass.
3. The fidelity check runs on every excerpt, at every boundary.

**Stands on:** work packages 1 to 4, merged and reviewed.

This is the plan's one pause for the owner. While waiting, work package
6 runs, because it does not depend on the answer; a correction from the
owner that changes code goes back to the stream's code with a test that
fails first, and work package 6 is run again.

- [ ] 5.1 Build the sheet from the six excerpts' outputs, and check each
  page against the spec before it goes to the owner. Spec: layout §8 and
  structure §9, "Excerpt tests". Deliverable 1.
- [ ] 5.2 Turn the owner's answer into the expected outputs and the
  tests. Deliverables 2, 3.

## 6. Measurement

**What it gives.** The scores of the four evaluation books after this
plan, against the baseline and against the targets of structure §9, in
the work report; the whole-book tests on the six books; the EPUBs of the
six books for the owner to look at on the Kindle.

**Deliverables.**

1. `uv run galley-eval run` on the four books, and `galley-eval compare`
   against the baseline; the report has the table of structure §9 with a
   third row per score, this plan's value, and for each missed target its
   cause, found in `differences.jsonl`.
2. `uv run pytest -m whole_book` passes, Kadesh and Gierke included.
3. The six EPUBs are built and pass `epubcheck`; their paths are in the
   report.
4. The number of guessed hyphen joins per book is in the report, against
   the research's 35, 33, 78 and 192.

A missed target does not stop the plan: it is reported with its cause,
and what fixing it would take goes to the owner as a proposal.

**Stands on:** work packages 1 to 4, merged and reviewed.

- [ ] 6.1 Run the evaluation, the whole-book tests and the six EPUBs;
  write the results into the report. Spec: structure §9, "Targets", and
  `docs/specs/evaluation.md` §9. Deliverables 1 to 4.

## How the whole plan is checked at the end

- The checks of the `coding` skill on the plan's branch, with pytest
  once normally and once with 8 threads.
- Work package 6's deliverables, run again after the last fix.
- For the owner on the Kindle: Domesday's EPUB around book page 76
  (margin notes and notes after a paragraph), Haskins' around 132 to 133
  (a paragraph over a page break, footnotes), and Mariéjol's around 214
  (notes in poor OCR).
