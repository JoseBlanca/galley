# Plan: lists, printed contents and figures inside text pages

This plan builds three things the owner found missing in the EPUB of
Haynes' book on 18 November 2026:

- **list items**: a list the book prints, each item starting with a
  dash, a bullet, a number or a letter and its other lines hung to the
  right, becomes one block per item and a list in the EPUB, instead of
  one long paragraph (Haynes' six items of pages 16 and 17 were one
  paragraph of 544 words);
- **contents entries**: each entry of the book's printed table of
  contents becomes a block with its number, title, depth and printed
  page number, its title a link to the chapter's heading, and the
  contents' title ("CONTENTS") a level-1 heading;
- **in-page figures**: a picture printed on a text page among its lines
  (Haynes' 25 figures, Turney's insert, Kadesh's maps) is found by
  analyze, cut into `images/` by extract, kept apart by layout, and
  placed by structure as a figure block with its caption, the words the
  OCR read inside the picture removed with a record.

It is built from `docs/specs/structure.md` §29 to §33 (lists and
contents; cited "structure §n") and `docs/specs/figures.md` (cited
"figures §n"), and the formats they give in `docs/architecture.md` §8
and §13 ("architecture §n") and `docs/glossary.md`, all reconciled in
commit 2ec7143 of branch `plan/lists-figures`. Dated 18 November 2026.
State: under way since 18 November 2026; approved (the owner said to go
on without waiting) the same day.

Page means page index of the whole PDF, from 0.

## In and out

In: structure §29 to §32 and the steps of structure §2 that name them;
figures §3 to §6 and §10; the format changes of architecture §8 (pages.json
3, words.json 3, lines.json 4, blocks.json 5); two new excerpts,
`kadesh_29-38` and `domesday_lists`; counts on the owner's books; the
EPUBs of the eight books.

Out: a list inside a list; tables (Domesday's rows become numbered
lists, structure §29, "Where they fail"); a smaller image for the EPUB;
links from "see fig. 2" to its figure; a public-domain excerpt with a
dash list, since none of the six books prints one (structure §33);
config keys to refuse a figure (figures §8). markdown writes figure
blocks already and does not change for figures (figures §6).

Every open point of both specs is settled (structure §33, figures
§11, architecture §17): lists show the reader's own markers; a
contents' title is a level-1 heading; a picture without a caption is
kept; `Figure.kind` is a field.

**The owner's books are copyrighted.** No page of Turney or Haynes is
cut into an excerpt, and no committed file (test, report, commit
message) quotes their text beyond a few words naming a case: their
tests count, compare page indices and at most a caption's first two
words, which are "figure" and a number (figures §10). They are found in
`samples/` of the main checkout and skipped with the reason when
absent, as `tests/test_owner_books.py` does today.

## What must be in place

Checked on 18 November 2026 in this worktree at 2ec7143 (code of
83f2754, `main`):

- `which pandoc tesseract epubcheck combine_tessdata dawg2wordlist`
  prints five paths; Pandoc 3.14, EPUBCheck 5.4.0.
- `uv run --locked pytest -q`: 2,494 passed, 106 deselected, 8 xfailed
  in 64.4 s on the Apple M5 Pro (62 s on `main` by the orchestrator's
  run).
- The six whole books in `samples/public_domain/` of the main checkout,
  their Gutenberg HTML under `gutenberg/`, and the owner's two PDFs in
  `samples/`.
- **The evaluation baseline** is `runs/owner-books-final/` of the main
  checkout, galley at f5cdf4e; `git diff f5cdf4e 83f2754 -- src tools
  evaluation` is empty, so it stands for this plan's starting code and
  is not run again.
- The worktree `.claude/worktrees/lists-figures`, branch
  `plan/lists-figures`; no other session works in the repository (`git
  worktree list`).

## The order of the work, and the streams

Work package 1 runs first on the plan's branch: every later task needs
the formats, and the excerpts' expected output must exist before the
rules are written. Work package 2, figure detection on the eight books'
real pages, is the part whose failure would change the plan (its
thresholds were measured with a prototype), so its stream starts at
once after work package 1 and ends at a decision point.

| stream | tasks | starts | may change |
|---|---|---|---|
| plan's branch | 1.1, 1.2 | first | `src/galley/model.py`; the structure boundary of `src/galley/fidelity.py`; `tests/test_model.py`; `tests/test_fidelity.py`; `tests/conftest.py`; `tests/test_owner_books.py` (its fixture moved to `conftest.py`); `scripts/fetch_samples.py`; `tests/fixtures/pdf/`; `tests/fixtures/expected/lists_figures/` (new); `tests/fixtures/evaluation/`; `tools/galley-eval/tests/` |
| `figures` | 2.1 to 2.3, 3.1 | after 1.2 | `src/galley/analyze/`; `src/galley/extract/`; `src/galley/layout/_page.py` and `src/galley/layout/_figures.py` (new); `tests/test_figures.py` (new); `tests/test_owner_figures.py` (new); in `tests/test_analyze.py`, `tests/test_extract.py` and `tests/test_layout.py`, only literals its rules change |
| `lists` | 4.1 to 4.3, 5.1 to 5.4 | after 1.2 | `src/galley/structure/`; `tests/test_structure_lists.py` and `tests/test_structure_contents.py` (new); `tests/test_owner_lists.py` (new); in `tests/test_excerpts.py`, `tests/test_structure*.py`, `tests/test_end_to_end.py` and `tests/fixtures/expected/`, only literals its rules change |
| `markdown` | 6.1, 6.2 | after 1.2 | `src/galley/markdown/`; the markdown boundary of `src/galley/fidelity.py`; `src/galley/epub/style.css`; `tests/test_markdown_lists.py` and `tests/test_fidelity_markdown_lists.py` (new) |
| `figure-blocks` | 3.2 to 3.4 | after `lists` and `figures` are merged, and WP 2's decision point passed | `src/galley/structure/`; `tests/test_figures.py`; `tests/test_owner_figures.py`; reference literals as for `lists` |

`lists` and `figure-blocks` both change `src/galley/structure/` and
the reference literals, so `figure-blocks` waits for `lists` to be
merged. `fidelity.py` is changed by task 1.2 at the structure boundary
and then only by `markdown`. `model.py`, `pyproject.toml`,
`docs/architecture.md` and `docs/glossary.md` change in task 1.2 only;
the architecture and the glossary already say what the specs want. A
task that finds it needs one of them stops and asks the orchestrator,
who changes it on the plan's branch and merges it into the streams.

After the streams, WP 7 runs on the plan's branch. Each work package
is reviewed (the `reviewing-code` skill) once its stream is merged.

**Changed reference pages.** A reference page is an excerpt page whose
expected output was checked against its image; its literals are in
`tests/fixtures/expected/` and in tests. The contents rules change
those of `haskins_front`, `stubbs_summaries_index`,
`domesday_headings_quotes` and `gierke_front_flow`. A task whose change
alters one updates it in the same commit, names each change and the
spec part that causes it, and the orchestrator has a subagent check it
against the page rendered at 300 dpi before ticking the task (the
owner's order of 17 November 2026, `docs/reports/clean-text.md`, "Task
6.4"). The same holds for the expected output of the two new excerpts.

**The default run** stays near a minute: 64.4 s at 2ec7143. Each
task's report gives its time; past 70 s, the orchestrator finds which
tests grew and cuts the new excerpts to the pages their tests use and
the body pages their measures need.

Every command check below was run on 18 November 2026 at 2ec7143 and
failed as each says, but those marked "kept true".

## 1. The excerpts and the formats

**What it gives.** The two excerpts cut, with their expected output;
pages.json at version 3, words.json at 3, lines.json at 4 and
blocks.json at 5, read and written with every new field, kind and
reason, and a file of an earlier version refused naming the stage to
run; the fidelity check at structure's boundary counting the new
fields and verifying the new change and removals. Nothing writes the
new values yet.

**Deliverables.**

1. The excerpts, cut by `scripts/fetch_samples.py` with what each covers,
   and in `EXCERPT_CONFIGS`: `for e in kadesh_29-38 domesday_lists; do
   test -f tests/fixtures/pdf/$e.pdf && grep -q "\"$e\""
   tests/conftest.py && grep -q "\"$e\"" scripts/fetch_samples.py ||
   echo "missing $e"; done` prints nothing (2 lines at 2ec7143). Their
   expected output in `tests/fixtures/expected/lists_figures/`: `ls
   tests/fixtures/expected/lists_figures | wc -l` prints at least 2
   (no folder at 2ec7143).
2. The formats: `uv run python -c "from galley.model import
   PAGES_FORMAT_VERSION as P, WORDS_FORMAT_VERSION as W,
   LINES_FORMAT_VERSION as L, BLOCKS_FORMAT_VERSION as B, BlockKind,
   ChangeReason, RemovalReason, FigureKind, Block, PageInfo, Figure;
   assert (P, W, L, B) == (3, 3, 4, 5); [BlockKind(k) for k in
   ('list_item', 'contents_entry')]; ChangeReason('list_marker');
   [RemovalReason(r) for r in ('leader_dots', 'figure_text')];
   [FigureKind(k) for k in ('plate', 'in_page')]; assert {'page_number',
   'heading_ref'} <= Block.__dataclass_fields__.keys(); assert
   'figure_boxes' in PageInfo.__dataclass_fields__ and 'kind' in
   Figure.__dataclass_fields__"` passes (fails at 2ec7143: no
   `FigureKind`). `uv run pytest tests/test_model.py -k "figure_boxes or
   figure_kind or list_item or contents_entry or heading_ref or
   page_number" --collect-only -q` lists at least 8 (0 at 2ec7143): a
   round trip of each new field; a label missing on a list item, a
   level on a list item, a `page_number` or `heading_ref` on another
   kind, and a `heading_ref` naming a block that is not a heading, each
   refused naming the file and block; a file of the old version of each
   of the four refused naming the stage.
3. The fidelity check at the structure boundary (structure §31, its
   last paragraph): `uv run pytest tests/test_fidelity.py -k
   "list_marker or leader_dots or figure_text or page_number or
   any_label" --collect-only -q` lists at least 5 (0 at 2ec7143),
   among them a `list_marker` change whose first word is not a dash,
   refused.
4. Kept true: `uv run pytest tools/galley-eval/tests` passes, its
   fixtures at the new versions.

**Stands on:** what must be in place.

**What could go wrong.** `domesday_lists` must give the whole book's
body measures (structure §32); Domesday's body pages near 156 are
tables, so the body pages to add may lie further away.

- [x] 1.1 The two excerpts and their configs. `kadesh_29-38`: Kadesh's
  pages 29 to 38, with the whole book's config; its expected output as
  figures §10's table gives it, each page read from its 300-dpi render
  by a subagent. `domesday_lists`: Domesday's pages 141, 156, 157 and
  158 and the body pages that make its body measures equal the whole
  book's; its expected lists as structure §29, "What the rules give",
  and §32's table give them, read likewise. The owner-books fixture
  `owner_book_run` moved from `tests/test_owner_books.py` to
  `tests/conftest.py`, unchanged, so that the streams' owner tests can
  use it. Spec: figures §10, "Reference pages"; structure §32,
  "Excerpt tests" and the paragraph after its table. Plan's branch.
  Deliverable 1.
- [x] 1.2 The formats of architecture §8 in `model.py` (`PageInfo.figure_boxes`,
  `FigureKind` and `Figure.kind`, the two block kinds, `Block.page_number`
  and `heading_ref`, the change and removal reasons, the four versions,
  the readers' errors); every writer of these files that exists sets
  the new fields to their empty values (`figure_boxes` empty, `kind`
  `plate`); the fidelity check at the structure boundary; the
  evaluation fixtures rewritten at the new versions. Spec: architecture
  §8 and §13; structure §7, the revision of §29 to §33; figures §7.
  Plan's branch. Deliverables 2 to 4. A commit of its own.
- [x] Review of work package 1.

## 2. Finding and cutting in-page figures

**What it gives.** `galley2epub analyze` writes each text page's figure
boxes into pages.json, and `galley2epub extract` cuts each into
`images/figure-<page>-<n>.png` with `kind` `in_page`, on the eight
books as figures §2 says: 56 figures, none elsewhere.

**Deliverables.**

1. The unit tests of figures §10's `figure_boxes` bullet: `uv run
   pytest tests/test_figures.py -k figure_boxes --collect-only -q`
   lists at least 8 (the file does not exist at 2ec7143).
2. extract's cut: unit tests (a text page with two boxes gives two
   figures, in pages.json's order, `kind` `in_page`, dpi 300, the box
   rounded outwards; a plate's figure `kind` `plate`) and the excerpt:
   `uv run pytest tests/test_figures.py -k "cut or kadesh_29_38_boxes"
   --collect-only -q` lists at least 3 (as above), and they pass:
   `kadesh_29-38` has the boxes of figures §10's table, to 1 pt, and
   an image for each.
3. On the eight books (figures §10, "Whole-book tests", analyze's
   part): Kadesh's 17 figures on the pages of figures §2, Haynes' 25 and
   Turney's 14 on theirs, no figure in the five others: `uv run pytest
   -m whole_book tests/test_figures.py tests/test_owner_figures.py -k
   analyze --collect-only -q` lists at least 3 (the files do not exist
   at 2ec7143); they pass, with the owner's PDFs present. The report
   gives, for every group of 100 squares or more on the eight books'
   text pages, its squares and known words beside figures §3's
   "Measured" table, and analyze's time on Haynes beside the 6.8 s
   there.

**Stands on:** WP 1.

**Decision point.** If deliverable 3 does not hold, the orchestrator
finds the cause on the pages' renders. When the spec's rule is right
and the code wrong, it is fixed. When the rule itself misses a figure
or takes something else, `figure-blocks` does not start: the
orchestrator writes the finding into figures §11 as an open point,
with the pages, the options and what each costs, and goes on with the
other streams.

**What could go wrong.** The thresholds of figures §3 have a margin of
12 squares and 5 known words; the growth of a box into the outer band
was checked on Haynes and Turney only.

- [x] 2.1 `figure_boxes` in analyze, on the 36 dpi render the plate
  rule already makes, with the excluded regions; the boxes in
  pages.json, empty on other kinds; the INFO log per page; with the
  unit tests. Spec: figures §3; §6, `figure_boxes`; §9; §10, its first
  bullet. Stream `figures`. Deliverable 1.
- [x] 2.2 extract's cut at 300 dpi in the PDFium thread, the file
  names, `Figure.kind` on every figure; with the unit tests and the
  excerpt test of the boxes. Spec: figures §4; §5, "Which figures are
  in-page"; §9. Needs 2.1. Stream `figures`. Deliverable 2.
- [x] 2.3 The whole-book tests of deliverable 3 and the measurements in
  the report. Spec: figures §2, §3 "Measured", §10 "Whole-book tests".
  Needs 2.2. Stream `figures`. Deliverable 3.
- [x] Review of work package 2.

## 3. Figures through layout and structure

**What it gives.** The EPUB shows each in-page figure as an image with
its caption, after the paragraph printed before it; the paragraph the
figure cut is one block; the words the OCR read in the picture are
`figure_text` removals.

**Deliverables.**

1. layout's figure regions: unit tests (the words inside a box made a
   region whose box is the figure's; a word of the first row kept with
   the page's words; a figure with no word inside has no region): `uv
   run pytest tests/test_figures.py -k "figure_region" --collect-only
   -q` lists at least 3 (as above).
2. structure's caption label and caption: `uv run pytest
   tests/test_figures.py -k "caption_label" --collect-only -q` lists at
   least 17, the cases of figures §10's `is_caption_label` bullet; and
   `-k "caption_rows or figure_place or figure_text"` lists at least 3,
   figures §10's structure bullet (as above).
3. The excerpt: `uv run pytest tests/test_figures.py -k
   "kadesh_29_38 and not boxes" --collect-only -q` lists at least 6
   (as above), the rows of figures §10's table, and they pass; one of
   them, marked `epubcheck`, builds the excerpt's EPUB with its
   figures' images and epubcheck passes it.
4. On the eight books (figures §10, "Whole-book tests", the rest):
   Kadesh's 17 figure blocks and its 6 maps' captions' first two words;
   Haynes' 25 figure blocks, each caption starting "figure" and its
   number; Turney's 14, 11 with a caption, no heading on page 174; no
   figure block in the five others; the fidelity check passing on each:
   `uv run pytest -m whole_book tests/test_figures.py
   tests/test_owner_figures.py -k "blocks or caption" --collect-only
   -q` lists at least 4 (the files do not exist at 2ec7143), and with
   the PDFs present they pass.

**Stands on:** WP 2 and its decision point; for 3.2 to 3.4, `lists`
merged.

**What could go wrong.** The caption rules were measured on the
prototype's rows of `runs/owner-books/`; the rows structure makes once
layout takes the figure's words out may differ (figures §5,
"Measured"). The head-line case of Turney 174 depends on structure §3
not making that row a running head.

- [x] 3.1 layout's step before its step 1 on a page with in-page
  figures: the words inside each box made the figure's region, never
  re-read; `kind` copied through; with the unit tests. Spec: figures
  §5, "layout: the figure's words kept apart". Needs 2.2. Stream
  `figures`. Deliverable 1.
- [x] 3.2 structure's figure regions out of the survey and of the
  column and margin finding; the plate rules on a page whose figure is
  of kind `plate` only; the figure's lines and a head line inside a box
  removed as `figure_text`. Spec: figures §5, "Which figures are
  in-page" and "structure: removing the figure text"; structure §2,
  steps 1, 2.1 and 2.2; §18, its first line. Stream `figure-blocks`.
  Deliverable 2.
- [x] 3.3 `is_caption_label` and the caption rows (label row below,
  above or beside; the words of the label row; the rows after it), the
  caption taken out of the body stream in step 2.2; the figure block,
  its text, origin and place, after the paragraph, or after the whole
  list or contents run; the list's gap not tested across a figure; with
  the unit tests. Spec: figures §1, "Numeral" and "Caption label"; §5,
  "structure: the caption" and "structure: where the figure block
  goes"; §6, `is_caption_label`; structure §2, steps 2.2 and 3.7; §29,
  rule 5. Needs 3.2. Stream `figure-blocks`. Deliverable 2.
- [x] 3.4 The excerpt tests of `kadesh_29-38` and the whole-book tests
  of deliverable 4; the report gives each book's figure blocks and
  captions beside figures §5's "Measured" counts. Spec: figures §10.
  Needs 3.3. Stream `figure-blocks`. Deliverables 3, 4.
- [ ] Review of work package 3.

## 4. List items

**What it gives.** structure writes each item of a printed list as a
`list_item` block with its marker in `label`; Haynes' two lists and
Domesday's tables of pages 156 to 159 come out as lists, and numbered
paragraphs, notes and dashes inside sentences stay as they were.

**Deliverables.**

1. The unit tests of structure §32's first three bullets: `uv run
   pytest tests/test_structure_lists.py --collect-only -q` lists at
   least 12 (the file does not exist at 2ec7143): the dash list in
   Haynes' geometry, over a page break; the numbered list; each "not
   lists" case.
2. The excerpts: `domesday_lists` as task 1.1's expected output, and
   `kadesh_8-17`'s numbered paragraphs of pages 11 to 13 still
   paragraphs: `uv run pytest tests/test_structure_lists.py -k
   "domesday_lists or numbered_paragraphs" --collect-only -q` lists at
   least 2 (as above), and they pass.
3. On the books (structure §32, "Whole-book tests", the list rows):
   Haynes 11 `list_item` blocks, 6 with label "—" and 6 `list_marker`
   changes; Turney none; Domesday at least 36; Haskins, Stubbs, Gierke,
   Mariéjol and Kadesh none: `uv run pytest -m whole_book
   tests/test_structure_lists.py tests/test_owner_lists.py -k list
   --collect-only -q` lists at least 3 (the files do not exist at
   2ec7143), and with the PDFs present they pass. The report gives the
   lists and items per book beside structure §29, "What the rules
   give", which a prototype measured; a difference is found on the
   pages and explained before the task is ticked.

**Stands on:** WP 1.

**What could go wrong.** The hang of 5 to 20 pt and the gap of 1.5
pitches come from a prototype on the body streams of `page_parts`; the
code's body stream may differ at page breaks.

- [x] 4.1 The list rules as a function of the body stream across pages:
  the marker, its kind, form and value; rules 1 to 6; with the unit
  tests on lines written in the test. Spec: structure §29, "Terms" and
  "The rules". Stream `lists`. Deliverable 1.
- [x] 4.2 The rules wired into step 3.1: the pages and runs they skip;
  the `list_item` blocks, their labels, the `list_marker` change, the
  origins over a page break; a list item as a paragraph for notes,
  margin notes and the word rules, never a quote; with the excerpt
  tests. Spec: structure §2, step 3.1; §29, "Blocks". Needs 4.1. Stream
  `lists`. Deliverable 2.
- [x] 4.3 The whole-book tests of deliverable 3 and the counts in the
  report. Spec: structure §29, "What the rules give"; §32,
  "Whole-book tests". Needs 4.2. Stream `lists`. Deliverable 3.
- [x] Review of work package 4.

## 5. Contents entries

**What it gives.** On the pages of `contents_pages`, structure makes
the run's title a level-1 heading and each entry a `contents_entry`
block with its label, title, page number and depth, the leader dots
removed, and links each entry to the heading of its chapter.

**Deliverables.**

1. The unit tests of structure §32's contents and links bullets: `uv
   run pytest tests/test_structure_contents.py --collect-only -q` lists
   at least 10 (the file does not exist at 2ec7143).
2. The excerpt tests of structure §32's table for `haskins_front`,
   `stubbs_summaries_index`, `domesday_headings_quotes` and
   `gierke_front_flow`: `uv run pytest tests/test_structure_contents.py
   -k "haskins_front or stubbs_summaries or domesday_headings or
   gierke_front" --collect-only -q` lists at least 4 (as above), and
   they pass.
3. On the books (structure §32, "Whole-book tests", the contents
   rows): Turney 16 entries, all with a page number and a link, Haynes
   22, 21 with a page number and 22 linked, one level-1 heading on each
   contents page; links at least 9 in Haskins, 13 in Stubbs, 23 in
   Domesday, 13 in Gierke and 9 in Mariéjol, each naming a heading: `uv
   run pytest -m whole_book tests/test_structure_contents.py
   tests/test_owner_lists.py -k contents --collect-only -q` lists at
   least 3 (as above), and with the PDFs present they pass.
4. **The re-check of the prototype's measurements.** The ratio of 0.7
   and the analytical summary's threshold (2 inline page references,
   one for every two lines) were measured with a prototype only
   (structure §30, "The thresholds"). With the code, on the seven books
   with contents pages, the report gives structure §30's table again,
   entries, topics entries, entries with a page number, candidates, and
   links at 0.6, 0.7 and 0.8, and the analytical summaries per book,
   and has a subagent read every link at 0.7 against its heading. It
   holds when each row equals the spec's and the only wrong link is
   Gierke's "NOTE". The check is a script outside git whose output goes
   into the report; it cannot fail at 2ec7143 because nothing makes
   entries there.

**Stands on:** WP 1; WP 4 for the shared step 3.1.

**Decision point.** If deliverable 4 does not hold, the orchestrator
finds whether the code or the prototype differs from the spec. When the
code does, it is fixed. When the rule as written gives other counts, or
a wrong link, the orchestrator writes the measurement into structure
§30 and, when a threshold should change, an open point into §33 with
the options; meanwhile the rule stays as written, and the plan goes
on.

- [x] 5.1 The contents rules 1 to 8 on a run's body stream: the title,
  the pieces, analytical summaries, entries, lone labels, page numbers
  and leader dots, labels, depth; with the unit tests. Spec: structure
  §30, "Terms" and "The rules", rules 1 to 8. Stream `lists`.
  Deliverable 1.
- [x] 5.2 The links of rule 9 in step 3.4, the blocks of rule 10, the
  title as a heading in step 2.3, the `stray_mark` and `leader_dots`
  removals; with the unit tests of links. Spec: structure §2, steps
  2.3, 3.1 and 3.4; §30, rules 9 and 10. Needs 5.1 and 4.2. Stream
  `lists`. Deliverable 1.
- [x] 5.3 The excerpt tests of deliverable 2, with the reference pages
  they change checked on the renders; the whole-book tests of
  deliverable 3. Spec: structure §32. Needs 5.2. Stream `lists`.
  Deliverables 2, 3.
- [x] 5.4 The re-check of deliverable 4. Spec: structure §30, "The
  thresholds" and "What the rules give, and where they fail". Needs
  5.3. Stream `lists`. Deliverable 4.
- [x] Review of work package 5.

## 6. Lists and contents in Markdown and the EPUB

**What it gives.** `book.md` writes list items as Pandoc lists and a
contents as a nested list of links in a div of class `contents`; the
style sheet sets them; the fidelity check reads both at the markdown
boundary; the EPUB passes epubcheck with a link into another chapter
file.

**Deliverables.**

1. The markdown tests of structure §32's markdown bullet and the
   forms of §31 (the dash list as a `BulletList` of 6 items, the
   numbered list as an `OrderedList` from 1, "(iv)" and "A." items read
   as list items, two lists kept apart by a `list-break` div, a list
   ended by a margin note, a contents with depths 1 and 2 read as a
   nested `BulletList` in a `Div` of class `contents`): `uv run pytest
   tests/test_markdown_lists.py --collect-only -q` lists at least 7
   (the file does not exist at 2ec7143); one of them, marked
   `epubcheck`, builds an EPUB with a contents link into another
   chapter file, which epubcheck passes.
2. The fidelity check at the markdown boundary (structure §31, "The
   fidelity check at the markdown boundary"): it passes on each case of
   deliverable 1 and fails on a list item holding two divs, a written
   `page_number`, a link to anything but a heading, and a count of
   links unequal to the entries with a `heading_ref`: `uv run pytest
   tests/test_fidelity_markdown_lists.py --collect-only -q` lists at
   least 6 (as above).
3. `grep -c "contents-entry\|list-style" src/galley/epub/style.css`
   prints at least 2 (0 at 2ec7143).

**Stands on:** WP 1. It needs no structure code: its tests write
blocks.json values.

- [x] 6.1 markdown's lists and contents, the `list-break` div, the
  indents Pandoc needs, and the style sheet's rules; with the tests.
  Spec: structure §31, "A list" and "A contents"; §33, points 1 and 2
  (settled). Stream `markdown`. Deliverables 1, 3.
- [x] 6.2 The fidelity check at the markdown boundary for lists,
  contents and their links; with the tests. Spec: structure §31, "The
  fidelity check at the markdown boundary"; architecture §13. Needs
  6.1. Stream `markdown`. Deliverable 2.
- [x] Review of work package 6.

## 7. The measurement and the EPUBs

**What it gives.** The scores of the four evaluation books against the
baseline, the whole-book tests, the EPUBs of the eight books, each
passing epubcheck, and the default run's time.

**Deliverables.**

1. `uv run galley-eval run`, copied to `runs/lists-figures-final/` of
   the main checkout; the report puts each score at blocks beside
   `runs/owner-books-final/`'s, with the tolerances of the plan
   owner-books (its WP 7, deliverable 1). It fails if, against the
   baseline: the reference headings in heading blocks or the notes
   whose reference is right fall on any book; paragraph precision or
   recall falls by more than 0.005 on any book but Domesday, or below
   structure §9's targets; a body token error rate rises by more than
   0.002; margin notes found as margin notes fall on Stubbs or Domesday;
   a target of reocr §9 is no longer met. Domesday's paragraph scores
   change by design, its tables' rows becoming list items, each a
   block (structure §32, "Measured by `galley-eval run`"): the report
   gives the change and its pages, and a fall outside pages 156 to 159
   is a failure as above. A fall is not a stop: it is reported with its
   cause found in `differences.jsonl`, and fixed when a rule of this
   plan made it against its spec.
2. `uv run pytest -m whole_book` passes, with the owner's PDFs present,
   and its time.
3. The eight EPUBs in `runs/lists-figures/` of the main checkout, built
   with `galley2epub run`, the six public-domain books with
   `WHOLE_BOOK_CONFIGS` and the owner's two with the configs of
   `tests/test_owner_books.py`: epubcheck prints 0 errors and 0
   warnings for each; each book's time in the report.
4. `uv run --locked pytest -q`, its count and time in the report; it
   fails above 70 s on the machine of "What must be in place".
5. Checked by eye, by a subagent on 300-dpi renders, with counts in the
   report and no text of the owner's books: in the owner's `book.md`,
   each in-page figure (picture whole, caption, place) and the lists and
   contents; in Kadesh's, the 17 figures; the reference pages this plan
   changed, each change. What is wrong is fixed in a task of this work
   package or reported.

**Stands on:** WPs 1 to 6.

- [ ] 7.1 The measurement: deliverables 1 to 4. Spec: structure §32,
  "Measured by `galley-eval run`"; figures §10; `docs/specs/evaluation.md`
  §9.
- [ ] 7.2 The checks by eye, and the fixes they call for. Spec:
  figures §10, "Reference pages"; structure §32, "Excerpt tests", the
  owner's check done as "Changed reference pages" says. Needs 7.1.
  Deliverable 5.

## How the whole plan is checked at the end

- The checks of the `coding` skill on the plan's branch, pytest once
  normally and once with 8 threads, and `uv run pytest -m whole_book`.
- WP 7's deliverables 1 to 4 run again after the last fix.
- For the owner on the Kindle, in `runs/lists-figures/`: Haynes' list
  of six stereotypes (pages 16 and 17) and its printed contents, each
  entry opening its chapter; two of Haynes' figures, one with its
  caption below and one with it beside; Turney's insert, pages 164 to
  179; Kadesh's maps and a quotation in hieroglyphs as an image; whether
  the Kindle shows a contents list without bullets (`list-style: none`
  was never tried on one, structure §31).
