# Plan: the owner's books

This plan makes galley read the owner's two modern books, Turney (312
pages, 1998) and Haynes (436 pages, 1994), both Internet Archive scans
with an OCR text layer like the six public-domain books, and fixes the
failures of the public-domain books that the same rules touch. After it,
on the owner's books:

- running heads are removed with their page numbers, also where the
  number is printed outside the column beside the head, and a page
  number at the foot of a chapter's first page is removed by its value;
- chapter headings set flush left or in large type are found, with
  their chapter label, which is never taken for a running head;
- the notes printed at the back, numbered from 1 again under a heading
  per chapter (a **note group**), are cut, kept with their group's
  heading, and linked to the references of their own chapter;
- the quotation set at the head of a chapter with its source (an
  **epigraph**) is a block of its own;
- a paragraph ends at a page break when the page's last line is short
  and ends a sentence.

And on every book: a "?", ";", ":" or "!" set apart by a space is
attached to its word (in French, preceded by a no-break space); a word
glued at a case change ("theAvre") is split; running heads that layout
missed on Haskins, Stubbs and Gierke are removed; notes set close under
the text are found; a word of a margin note is read once by re-reading,
not twice.

It is built from `docs/specs/structure.md` §1 to §8, §12, §14 and §21
to §27 (the parts the plan owner-books revised), `docs/specs/layout.md`
§3, steps 2 to 4, and §8, `docs/specs/reocr.md` §4, and the changes
they made to `docs/architecture.md` (`blocks.json` at version 4) and
`docs/glossary.md`, on branch `plan/owner-books` (commits 18f1e86 to
6b8c54d). Dated 17 November 2026. State: under way since 17 November
2026; approved by the owner on 17 November 2026 (scope in chat; plan
not reviewed by them).

"Structure §22" below is section 22 of `docs/specs/structure.md`,
"layout §3" of `docs/specs/layout.md`, "reocr §4" of
`docs/specs/reocr.md`, "architecture §8" of `docs/architecture.md`.
Page means page index of the whole PDF, from 0.

## In and out

In: everything structure §21 to §26 describes and the parts of §2, §3,
§4, §6, §7, §8, §12 and §14 that name the plan owner-books; layout §3,
steps 2 to 4; reocr §4's pairing by letters; four new excerpts; tests on
the owner's books that count; the EPUBs of the eight books.

Out (structure §28): the bibliographies' entries, which stay quotes;
Stubbs' cut-in note lines left in the body; merging the text layer's and
Tesseract's readings of an index word by word; tables; words glued
without a case change; Mariéjol's references read "(i)"; Kadesh's notes;
the correct stage. galley-eval is not changed beyond reading version 4
(see "Left open by the specs").

**The owner's books are copyrighted.** No page of them is cut into an
excerpt, and no committed file (test, report, commit message) quotes
their text: the tests count, and the report gives counts and page
indices. The tests find each PDF in `samples/` of the main checkout by
the patterns `*Turney*.pdf` and `*Haynes*.pdf`, and skip with the
reason when it is absent.

**Structure §27's open points**, settled by the orchestrator on 17
November 2026 (commit 6b8c54d writes them into the spec):

| point | settled | built in |
|---|---|---|
| 1. how the source and the group heading are stored | as the meanwhile: `Block.source` and `Note.group`, strings counted by the fidelity check | 2.1 |
| 2. group headings in the table of contents | as the meanwhile: not; a styled div before the group's first note | 6.1 |
| 3. how the source's dash is drawn | differs from the meanwhile: markdown writes "—" and a no-break space before the source as text, not CSS `::before`, because generated content was never tried on a Kindle and the text must not depend on it; the fidelity check at the markdown boundary takes that word out (structure §25, changed) | 2.1, 6.1 |
| 4. costs on the public-domain books | accepted on Mariéjol (36 splits of garbled words) and on Turney's two roman foot numbers; Stubbs' publisher's lists, pages 322 to 337, go into its `exclude_pages`; Domesday's 4 text lines taken as headings (pages 136 and 419) are looked at, and fixed if a rule can tell them apart, or else reported | 1.4, 1.6 |

## What must be in place

Checked on 17 November 2026 in this worktree, whose code is that of
9715a93 (the branch has changed only `docs/`), and checked again by the
orchestrator before task 1.1:

- `which pandoc tesseract epubcheck combine_tessdata dawg2wordlist`
  prints five paths; Pandoc 3.14, Tesseract 5.5.4, EPUBCheck 5.4.0.
- `uv run --locked pytest -q`: 2111 passed, 61 deselected, 8 xfailed,
  in 46.4 s (48.5 s wall).
- The six whole books in `samples/public_domain/` of the main checkout,
  their Gutenberg HTML under `gutenberg/`, and the owner's two PDFs in
  `samples/`.
- The plan's worktree and branch: `.claude/worktrees/owner-books`,
  branch `plan/owner-books`, made from `main` at 9715a93. No other
  session works in the repository (`git worktree list`, 17 November
  2026).
- **The baseline**: `uv run galley-eval run` at the plan's start (its
  code is that of `main`, 9715a93, and of 7533d23), copied to
  `runs/owner-books-baseline/` of the main checkout. Its scores must
  equal those of `docs/reports/clean-text.md`, "Review 3" and, for the
  scores Review 3 left unchanged, "Task 6.3"; if they do not, the
  orchestrator stops and tells the owner.

## The order of the work, and the streams

Task 1.1 runs first on the plan's branch. Then streams run side by
side, each in a worktree of its own (the `following-plans` skill,
"Parallel streams"), no more than three at once, and the plan's branch
counts as one while a task runs there:

| stream | tasks | starts | may change |
|---|---|---|---|
| plan's branch | 2.1 | after 1.1 | `src/galley/model.py`; `src/galley/fidelity.py`; `tests/test_model.py`; `tests/test_fidelity.py`; `tests/fixtures/evaluation/`; `tools/galley-eval/tests/` |
| `edges` | 1.2 to 1.6 | after 1.1 | `src/galley/layout/` but `_reread.py` and `_rereading.py`; `src/galley/structure/` but the new modules of other streams; `tests/test_layout.py`; `tests/test_structure.py`; `tests/test_structure_heads.py` (new); `tests/test_owner_books.py` (new); `tests/conftest.py`, only Stubbs' `WHOLE_BOOK_CONFIGS` entry and a fixture giving the `samples/` folder (as `books_dir` finds it, without `public_domain`); `evaluation/books.toml`, only Stubbs' `exclude_pages`; `tests/test_excerpts.py`, its new tests of the four excerpts; in `tests/test_excerpts.py`, `tests/test_end_to_end.py`, `tests/test_markdown.py`, `tests/test_text_layer.py`, `tests/test_analyze.py` and `tests/fixtures/expected/`, otherwise only literals its rules change; in task 1.6, `docs/specs/structure.md` §14 |
| `words` | 5.1 | after 1.1 | `src/galley/structure/_spaced.py` and `_case_split.py` (new); `tests/test_structure_words.py` (new) |
| `markdown` | 6.1 | after 2.1, when fewer than three run | `src/galley/markdown/`; `src/galley/epub/style.css`; `tests/test_markdown_epigraphs.py` (new) |
| `notes` | 3.1 to 3.3 | after `edges` is merged and 2.2 is done | `src/galley/structure/` but the new modules of other streams; `tests/test_structure_notes.py` (new); `tests/test_owner_books.py`; `tests/test_structure.py`, and the reference literals as for `edges` |
| `epigraphs` | 4.1 | after `edges` is merged and 2.1 is done | `src/galley/structure/_epigraphs.py` (new); `tests/test_structure_epigraphs.py` (new) |

`edges` and `notes` change the shared reference literals, so they never
run at once, and nothing else that changes outputs runs beside them:
task 2.2 (re-reading's pairing, which changes Domesday's and Gierke's
margin notes) waits on the plan's branch until `edges` is merged.

After the streams, the rest runs on the plan's branch in this order:
when `edges` is merged, WP 1's review and its decision point (below),
then 2.2 and WP 2's review; when `notes` is merged, WP 3's review; 4.2,
4.3 and WP 4's review; 5.2 and WP 5's review; WP 6's review once
`markdown` is merged (at any point before 7.1); 7.1, 7.2.

`model.py`, `config.py`, `fidelity.py`, `pyproject.toml`,
`docs/architecture.md` and `docs/glossary.md` are changed in task 2.1
and 2.2 only (the architecture and the glossary are already as the
specs want them). A task that finds it needs one of them stops and asks
the orchestrator, who changes it on the plan's branch and merges it into
the streams.

**New tests go into new files**, one per stream, as the table says, so
that streams do not change the same test file. An existing test file
changes only where a rule changes a literal.

**Changed reference pages.** A reference page is an excerpt page whose
expected output was checked against the page image; its literals are in
`tests/fixtures/expected/` and in tests. A task whose change alters one
updates it in the same commit, names each change and the spec part that
causes it in the commit message and the report, and the orchestrator
checks each against the page image before ticking the task. The owner
asked on 17 November 2026 (`docs/reports/clean-text.md`, "Task 6.4")
that the assistant do such checks itself: a subagent reads the page
rendered at 300 dpi, and its reading is recorded as such. This holds
also for the expected output of the four new excerpts, which structure
§26 gives to the owner.

**The default run.** `uv run --locked pytest` stays near a minute: 46.4
s at the start. Each task's report gives its time, and a task that takes
it past 60 s says which tests grew.

Each task keeps every check of the `coding` skill passing. Every command
check of the deliverables below was run once on 17 November 2026 on
this branch before the plan's commit (code of 9715a93; "at 6b8c54d"
below) and failed as each says. The whole-book tests on the
owner's books were not run (their files do not exist); the evaluation
run of 7.1 was not, since at 6b8c54d it equals the baseline.

## 1. Running heads, page numbers and headings

**What it gives.** On Turney and Haynes, `blocks.json` has each
chapter's heading, with its label, and no running head or page number
in the text; on Haskins, Stubbs and Gierke, the running heads layout
missed are removed; notes set close under the text are a band. This
work package comes first because note groups (WP 3) find their chapter
by its heading and epigraphs (WP 4) are looked for under one: if the
headings are not found, those two work packages' targets on the owner's
books do not hold.

**Deliverables.**

1. The four excerpts of structure §26, `haskins_heads_notes`,
   `stubbs_heads`, `gierke_intro_heads` and `domesday_rereads`, cut by
   `scripts/fetch_samples.py` with what each covers and in
   `EXCERPT_CONFIGS`: `for e in haskins_heads_notes stubbs_heads
   gierke_intro_heads domesday_rereads; do test -f
   tests/fixtures/pdf/$e.pdf && grep -q "\"$e\"" tests/conftest.py &&
   grep -q "\"$e\"" scripts/fetch_samples.py || echo "missing $e";
   done` prints nothing (4 lines at 6b8c54d).
2. Layout's three steps, with the unit tests of layout §8's bullets
   for them (head row by median tops, an em dash boxed tall below it, a
   skewed head of two rows, a row of marks passed over; a hanging "12"
   at 9 pt, 16 pt and on the head row; the gapless band start and the
   row of numbers that does not start it): `uv run pytest
   tests/test_layout.py -k "median_top or skewed_head or marks_row or
   hanging_number or gapless_band" --collect-only -q` lists at least 8
   (0 at 6b8c54d).
3. structure's head line, chapter label and foot number, with the unit
   tests of structure §26's first three bullets: `uv run pytest
   tests/test_structure_heads.py -k "beside_head or chapter_label or
   by_value" --collect-only -q` lists at least 6; the headings' two
   branches, with §26's headings bullet: `-k "flush_left or tall_line"`
   lists at least 5 (the file does not exist at 6b8c54d).
4. The excerpt tests of structure §26's table for this work package's
   rules: the running heads of Haskins' pages 23, 30, 66 and 235,
   Stubbs' 20, 100, 152, 158, 186, 202 and 210 and Gierke's 68 to 79
   are `running_head` removals with their page numbers recorded
   (Gierke's roman); Haskins' page 23 speck a `stray_mark`; the notes
   of Haskins' 28, 55 and 195 and Domesday's 97 and 138 are notes, not
   body; Gierke's list of authorities' section headings are heading
   blocks; Domesday's page 136 as task 1.6 leaves it. `uv run pytest
   tests/test_excerpts.py -k "heads_notes or stubbs_heads or
   gierke_intro_heads or domesday_rereads" --collect-only -q` lists at
   least 4 (0 at 6b8c54d), and they pass.
5. On the owner's books, the rows of structure §26's whole-book table
   that this work package answers: level-1 headings whose label starts
   with "chapter" (Turney 10, Haynes 16), level-1 headings without a
   label (at least 5 each), `running_head` removals whose first word is
   a chapter label word (0), Turney's `page_number` removals at the
   foot (at least 14 of its 15 opening pages), `margin_note` blocks
   that are a number of 1 to 3 digits (0): `uv run pytest -m whole_book
   tests/test_owner_books.py --collect-only -q` lists at least 5 (the
   file does not exist at 6b8c54d); with the PDFs present they pass.
6. On the six public-domain books: no `running_head` removal starts
   with a chapter label word, and the running heads of deliverable 4's
   pages are removed on the whole books: `uv run pytest -m whole_book
   tests/test_structure_heads.py --collect-only -q` lists at least 2;
   `uv run pytest -m whole_book` passes. The report gives each book's
   heading blocks before and after beside structure §14's table, and
   the lines layout's hanging-number step keeps in their line (layout
   §3, step 2: Gierke 26, Domesday 1).

**Decision point.** If deliverable 5's heading rows miss on either
book, the orchestrator finds the cause on that book's pages. When no
rule of the spec fixes it, WP 3 and WP 4 do not start; WP 2, 5 and 6
go on, and the orchestrator writes to the owner what failed, with the
pages, and what changing the spec would take.

**Stands on:** what must be in place.

**What could go wrong.** The headings' branches were measured with a
prototype on the survey's `lines.json`, made before layout's step 3
changed (structure §14, "The flush-left and tall branches"); the counts
may move once heads are removed. The foot-number rule was not measured
on the public-domain books (structure §4); the whole-book tests show
any change. Excluding Stubbs' pages 322 to 337 changes whole-book
literals that count Stubbs' words or removals (`tests/test_text_layer.py`,
`tests/test_analyze.py`); each changed literal is named with this
reason. The four excerpts add four runs to the excerpt fixture,
`domesday_rereads` with re-reading; if the default run passes 60 s,
the orchestrator cuts the excerpt with the fewest tested pages
shorter.

- [x] 1.1 The four excerpts and their configs, each excerpt's body
  measures and marker form checked against its whole book's (pages of
  the same book added where they differ), and the expected output of
  each page read from its 300-dpi render by a subagent. Spec: structure
  §26, "Excerpt tests", and the paragraph after its table; layout §8,
  the paragraph naming them. Plan's branch. Deliverable 1.
- [x] 1.2 layout §3, step 2 (a hanging number stays in its line), step
  3 (the head row by its words' median top, with the rows of a skewed
  head, passing rows of marks) and step 4 (the band's gapless start),
  with the unit tests; the changed reference pages. Spec: layout §3,
  steps 2 to 4, and §8, "Unit tests". Stream `edges`. Deliverable 2.
- [x] 1.3 The head line with the short regions beside it; a chapter
  label never a running head; a page number at the foot by its value
  and the local offset (`BookSurvey.head_numbers`); with the unit
  tests. Spec: structure §2, "What each region is"; §3, "A short region
  beside the head" and "A chapter label is never a running head"; §4,
  "A page number by its value"; §8; §26, "Unit tests", its first three
  bullets. Needs 1.2. Stream `edges`. Deliverable 3.
- [x] 1.4 The flush-left and tall branches of the heading rule, with
  the unit tests; Stubbs' pages 322 to 337 added to its `exclude_pages`
  in `WHOLE_BOOK_CONFIGS` and `evaluation/books.toml` (structure §27,
  point 4, settled). The levels' sentence on endnote sections is WP 3's.
  Spec: structure §1, "Line height"; §14, "The rule" and "The
  flush-left and tall branches"; §26, the headings bullet. Needs 1.3.
  Stream `edges`. Deliverable 3.
- [x] 1.5 The excerpt tests of this work package; `tests/test_owner_books.py`
  with its fixture (each book found in `samples/` by its pattern, run
  to `blocks.json` once per session with the configs of structure §21,
  `ocr = "trust"`, and a placeholder title and author, so that no title
  of the owner's is committed) and the rows of deliverable 5; the public-domain
  whole-book tests of deliverable 6, with any literal that changes
  named. Spec: structure §26, "Excerpt tests" and "Whole-book tests".
  Needs 1.4. Stream `edges`. Deliverables 4 to 6.
- [x] 1.6 Domesday's 4 text lines taken as tall headings (pages 136
  and 419): read on the renders why the tall branch takes them, and
  look for a condition that keeps them out and changes nothing else on
  the eight books (measured on all eight). If one is found, it goes
  into structure §14 first, in a commit of its own, then into the code
  with a unit test, and the `domesday_rereads` test of page 136 changes
  with it; if none is, the report says what was tried and the lines
  stay a known failure. Spec: structure §14, "Where it fails"; §27,
  point 4. Needs 1.5. Stream `edges`. Deliverable 4.
- [ ] Review of work package 1 (the `reviewing-code` skill), after
  `edges` is merged.

## 2. The format, the fidelity check and re-reading's pairing

**What it gives.** `blocks.json` at version 4 is read and written, with
the block kind `epigraph`, `Block.source`, `Note.group` and the three
word-change reasons; the fidelity check counts the new strings and
verifies the new changes, at structure's boundary and at markdown's.
Nothing structure writes uses them yet. Re-reading pairs a Tesseract
word with a layer word of its letters over a word under it whose letters
are unlike, so a margin-note word is read once.

**Deliverables.**

1. `uv run python -c "from galley.model import BLOCKS_FORMAT_VERSION as
   B, BlockKind, ChangeReason, Block, Note; assert B == 4;
   BlockKind('epigraph'); [ChangeReason(r) for r in ('source_dash',
   'punctuation_attached', 'case_split')]; assert 'source' in
   Block.__dataclass_fields__ and 'group' in Note.__dataclass_fields__"`
   passes (fails at 6b8c54d: version 3). `uv run pytest
   tests/test_model.py -k "epigraph or note_group" --collect-only -q`
   lists at least 4 (0 at 6b8c54d): a round trip of each new field, a
   source on a block that is not an epigraph refused naming the file
   and block, a file of version 3 refused naming structure.
2. The fidelity check's cases of structure §26's last unit-test bullet,
   and at the markdown boundary: the dash before a source taken out, the
   words of an `epigraph-source` div counted to its epigraph, those of a
   `note-group` div to the note after it, another div inside an
   epigraph an error: `uv run pytest tests/test_fidelity.py -k
   "source_dash or punctuation_attached or case_split or epigraph or
   note_group" --collect-only -q` lists at least 10 (0 at 6b8c54d).
3. Re-reading's pairing: unit tests of reocr §4's exception (the junk
   word under a Tesseract word and its letters' word beside it; the
   alike case by (c)'s ratio; a word under it alike too, which stays
   as now): `uv run pytest tests/test_model.py -k "unlike"
   --collect-only -q` lists at least 3 (0 at 6b8c54d); on
   `domesday_rereads`, the margin-note word of pages 26, 36, 139, 150
   and 160 read once: `uv run pytest tests/test_layout.py -k
   "read_once" --collect-only -q` lists at least 1 (0 at 6b8c54d), and
   it passes. The report gives, per book, the layer words left within 4
   pt of a kept record that a Tesseract word within 16 pt reads,
   beside reocr §4's 55 (47 to be fixed).
4. Kept true, so it passes at 6b8c54d too: `uv run pytest
   tools/galley-eval/tests` passes with its fixtures at version 4.

**Stands on:** task 1.1 for 2.2's excerpt; for 2.2, `edges` merged.

**What could go wrong.** The pairing changes the margin notes of
Domesday's and Gierke's excerpt reference pages; each change is
checked on the render.

- [x] 2.1 The format of architecture §8 in `model.py` (the new kind,
  fields and reasons, version 4, the readers' errors); the fidelity
  check of architecture §13 for the new strings and reasons at
  structure's and markdown's boundaries; the evaluation fixtures at
  version 4. Spec: architecture §8 and §13; structure §7, the plan
  owner-books' part; §22, "The dash is look, not text"; §23 and §24,
  the records; §25, its last paragraph. Plan's branch. Deliverables 1,
  2, 4. A commit of its own.
- [ ] 2.2 The pairing exception in `model.py`'s pairing, which layout
  and the fidelity check share, with the unit tests and the excerpt
  test; the changed reference pages. Spec: reocr §4, the exception in
  (a) and "A pairing by letters wins over a word under it whose letters
  are unlike". Plan's branch, after `edges` is merged. Deliverable 3.
- [ ] Review of work package 2.

## 3. Notes collected at the back

**What it gives.** On Turney, whose notes hang their number in the
margin, each note starts a paragraph and is cut; on both books the
endnote section is cut into note groups, each group's heading kept on
its first note, and each group's notes linked to the references of its
own chapter.

**Deliverables.**

1. Unit tests of structure §26's hanging-number and note-group bullets:
   `uv run pytest tests/test_structure_notes.py -k "hanging_number"
   --collect-only -q` lists at least 3, and `-k "note_group or
   group_heading or chapter_of_group or bare_number"` lists at least 5
   (the file does not exist at 6b8c54d).
2. On the owner's books, structure §26's rows: endnotes and note groups
   (Turney at least 580 and 11, Haynes at least 620 and 18), endnotes
   linked (at least 450 and 550), links to a note of another group's
   chapter (0): `uv run pytest -m whole_book tests/test_owner_books.py
   -k "endnote or group or linked" --collect-only -q` lists at least 4
   (0 at 6b8c54d), and with the PDFs present they pass. A miss of
   Turney's link target, which was not prototyped, does not stop the
   plan: the report gives its cause and what fixing it would take.
3. On the public-domain books nothing of their notes falls: `uv run
   pytest -m whole_book` passes, Gierke's endnotes one group without a
   group heading; the report lists the lines the hanging-number rule
   starts there beside structure §6's count (59: Domesday's tables 42,
   Gierke's contents 13, Mariéjol 3, Stubbs 1).

**Stands on:** WP 1 (the headings a group's chapter is found by) and
task 2.1 (`Note.group`).

**What could go wrong.** Turney's notes could not be prototyped before
they are cut (structure §12); its two columns per page and group
headings at the top of a column are the case to watch.

- [ ] 3.1 A hanging number starts a paragraph (rule 3), also at a page
  break; a bare number as an endnote marker in a run from 1 outside
  `contents_pages`; the section's reach back stopping at the first
  heading block that is not a group heading; with the unit tests.
  Spec: structure §6, rule 3 and "At a page break"; §12, its first
  changed paragraph. Stream `notes`. Deliverable 1.
- [ ] 3.2 Note groups, their headings as `Note.group` and the other
  heading blocks of the section made paragraphs; the chapter of a
  group; references matched per group; with the unit tests. Spec:
  structure §12, "Note groups", "References", "The chapter of a
  group"; §14, "Levels", its sentence on the endnote section. Needs
  3.1. Stream `notes`. Deliverable 1.
- [ ] 3.3 The whole-book tests of deliverables 2 and 3, and the counts
  in the report. Spec: structure §26, "Whole-book tests". Needs 3.2.
  Stream `notes`. Deliverables 2, 3.
- [ ] Review of work package 3.

## 4. Epigraphs, and a paragraph ended at a page break

**What it gives.** The quotation under a chapter's heading, with its
source, is an `epigraph` block, its source in `Block.source` without
its dash, a verse quotation keeping its line breaks; a page that holds
only an epigraph is one too. A page whose last line ends short with a
sentence's end ends its paragraph.

**Deliverables.**

1. Unit tests of structure §26's epigraphs bullet, on lines written in
   the test: `uv run pytest tests/test_structure_epigraphs.py
   --collect-only -q` lists at least 7 (the file does not exist at
   6b8c54d).
2. Unit tests of §26's page-break bullet through `make_blocks`: `uv run
   pytest tests/test_structure_epigraphs.py -k "page_break"
   --collect-only -q` lists at least 3 (0 at 6b8c54d).
3. On the owner's books, structure §26's rows: `epigraph` blocks and
   those with line feeds (Turney 11 and 0, Haynes 21 and 8),
   `source_dash` changes (0 and 21), and Turney's page 13 the origin of
   an epigraph block and of no other block: `uv run pytest -m whole_book
   tests/test_owner_books.py -k "epigraph or source_dash"
   --collect-only -q` lists at least 3 (0 at 6b8c54d), and with the PDFs
   present they pass.
4. On the six public-domain books, at most 2 `epigraph` blocks each:
   `uv run pytest -m whole_book tests/test_structure_epigraphs.py
   --collect-only -q` lists at least 1 (the file does not exist at
   6b8c54d); `uv run pytest -m whole_book` passes. The
   report lists any epigraph found there, and the page breaks the rule
   cuts per book beside structure §6's table.

**Stands on:** WP 1 and WP 2; for 4.2, WP 3 merged.

**What could go wrong.** Rule 5, a page of its own, was not measured on
the public-domain books; deliverable 4 shows what it takes.

- [ ] 4.1 The epigraph rule as a function of a page's body lines after
  its heading lines (rules 1 to 5, the source line, verse), giving the
  epigraph runs, their sources and the dash to remove; with the unit
  tests. Spec: structure §22, "The rule", "Verse". Stream `epigraphs`.
  Deliverable 1.
- [ ] 4.2 The rule wired into structure: the step after the heading
  lines, the speck between title and epigraph as a `stray_mark`, the
  block with its `source` and its `source_dash` change; and a short
  last line at a page break, with its unit tests. Spec: structure §2,
  steps 2.3 and 2.4; §6, "A short last line at a page break"; §22,
  "The block" and "The dash is look, not text". Needs 4.1 and WP 3.
  Plan's branch. Deliverable 2.
- [ ] 4.3 The whole-book tests of deliverables 3 and 4, and the counts
  in the report. Spec: structure §22, "What the rule gives"; §26,
  "Whole-book tests". Needs 4.2. Plan's branch. Deliverables 3, 4.
- [ ] Review of work package 4.

## 5. Spaced punctuation and words glued at a case change

**What it gives.** In a book not in French, a spaced "?", ";", ":" or
"!" is attached to its word, recorded; in Mariéjol a no-break space
stands before it. A word the OCR glued at a lower-to-upper case change
is split, recorded, when the book's own words support it.

**Deliverables.**

1. `uv run python -c "from galley.structure import attach_spaced_sign,
   split_at_case"` passes (fails at 6b8c54d), and the unit tests of
   structure §26's spaced-signs and case-split bullets: `uv run pytest
   tests/test_structure_words.py --collect-only -q` lists at least 9
   (the file does not exist at 6b8c54d).
2. The excerpt tests: `haskins_heads_notes` page 22's glued words
   split and page 28's sign glued to its reference linked to its note;
   `stubbs_heads`' spaced ";" attached; a page of `mariejol_210-219`
   with a no-break space and no `punctuation_attached` change: `uv run
   pytest tests/test_excerpts.py -k "spaced or case_split"
   --collect-only -q` lists at least 3 (0 at 6b8c54d), and they pass.
   The strict xfail of Domesday's "Can the villein be pursued?"
   (`tests/test_layout.py`, the owner-checked margin notes) passes and
   is no longer marked.
3. On the whole books: no `punctuation_attached` change in Mariéjol,
   and some in each English book: `uv run pytest -m whole_book
   tests/test_structure_words.py --collect-only -q` lists at least 1
   (the file does not exist at 6b8c54d); `uv run pytest -m whole_book` passes. The report gives
   each book's attachments and splits beside structure §23's and §24's
   tables, which the spec says the plan measures again.

**Stands on:** task 2.1; for 5.2, WP 4 merged.

**What could go wrong.** An edit written against a block's text before
this change no longer applies (structure §23); none exists for these
books.

- [x] 5.1 `attach_spaced_sign`, `split_at_case`, and the passes over a
  block's words that make the changes and the no-break spaces, as pure
  functions of their own modules, with the unit tests. Spec: structure
  §23, "The rule" and "After a note reference"; §24; §8, the two
  functions. Stream `words`. Deliverable 1.
- [ ] 5.2 The passes wired into structure: `make_blocks` takes the
  config's `language`; the case split after hyphens in each block; the
  spaced signs at step 3.2, before references are looked for; the
  exports; the excerpt and whole-book tests; the changed reference
  pages. Spec: structure §2, steps 2.4 and 3.2; §8; §23; §24. Needs 5.1
  and WP 4. Plan's branch. Deliverables 1 to 3.
- [ ] Review of work package 5.

## 6. Markdown and the EPUB

**What it gives.** `book.md` holds each epigraph as a div with its
quotation (hard line breaks when verse) and a source div starting with
"—" and a no-break space; each group heading as a div before its note,
outside the table of contents; no-break spaces as the character. The
style sheet sets the epigraph in and its source to the right.

**Deliverables.**

1. On blocks written in the test: `uv run pytest
   tests/test_markdown_epigraphs.py --collect-only -q` lists at least 5
   (the file does not exist at 6b8c54d): a prose and a verse epigraph,
   the source div with the dash, a group heading before its note and
   not a Pandoc heading, a no-break space kept, and the fidelity check
   at the markdown boundary passing on each; one of them, marked
   `epubcheck`, builds an EPUB that epubcheck passes.
2. `grep -c "\.epigraph\b\|\.epigraph-source\|\.note-group"
   src/galley/epub/style.css` prints at least 3 (0 at 6b8c54d).

**Stands on:** task 2.1.

- [x] 6.1 The epigraph, the note group heading and the no-break space
  in markdown, and their rules in the style sheet, with the tests.
  Spec: structure §25; architecture §9, the markdown and epub stages.
  Stream `markdown`. Deliverables 1, 2.
- [ ] Review of work package 6.

## 7. The measurement and the EPUBs

**What it gives.** The scores of the four evaluation books against the
baseline, the whole-book tests, and the EPUBs of the eight books, each
passing epubcheck.

**Deliverables.**

1. `uv run galley-eval run`, copied to `runs/owner-books-final/` of the
   main checkout; the report puts each score at blocks beside the
   baseline's. It fails if, against the baseline:
   - the reference headings in heading blocks, or the notes whose
     reference is right, fall on any book (structure §26);
   - paragraph precision or recall falls by more than 0.005 on any
     book, or below structure §9's targets;
   - a body token error rate rises by more than 0.002;
   - margin notes found as margin notes fall on Stubbs or Domesday;
   - a target of reocr §9 is no longer met (Stubbs' index at least
     0.97 / 0.94; margin notes at least 285 on Stubbs and 560 on
     Domesday; body error rate at most 0.062 on Stubbs and 0.080 on
     Domesday; Domesday's notes whose reference is right at least
     1,275; Haskins' index error rate at most 0.13).
   Stubbs' scores change with its excluded publisher's lists, which are
   outside its scored body (pages 18 to 321); the report says by how
   much. A fall is not a stop: it is reported with its cause found in
   `differences.jsonl`, and fixed when a rule of this plan made it
   against its spec.
2. `uv run pytest -m whole_book` passes, with the owner's PDFs present,
   and its time.
3. The eight EPUBs in `runs/owner-books/` of the main checkout, built
   with `galley2epub run`, the six public-domain books with
   `WHOLE_BOOK_CONFIGS` and the owner's two with the configs of
   structure §21 and `ocr = "trust"`: epubcheck prints 0 errors and 0
   warnings for each; each book's time in the report.
4. Checked by eye, by a subagent on 300-dpi renders, with the counts in
   the report and no text of the owner's books: on the owner's EPUBs'
   `book.md`, every chapter opening (heading, label, epigraphs) and the
   first page of each note group; the reference pages this plan
   changed, each change. What is wrong is fixed in a task of this work
   package or reported.

**Stands on:** WPs 1 to 6.

- [ ] 7.1 The measurement: deliverables 1 to 3. Spec: structure §26,
  "Measured by `galley-eval run`"; `docs/specs/evaluation.md` §9.
- [ ] 7.2 The checks by eye, and the fixes they call for. Spec:
  structure §26, "Excerpt tests", its owner's check, done as "Changed
  reference pages" above says. Needs 7.1. Deliverable 4.

## How the whole plan is checked at the end

- The checks of the `coding` skill on the plan's branch, pytest once
  normally and once with 8 threads, and `uv run pytest -m whole_book`;
  the default run's time against the minute.
- Work package 7's deliverables 1 to 3 run again after the last fix.
- For the owner on the Kindle, in `runs/owner-books/`: Turney's and
  Haynes' tables of contents (each chapter once, with its label, no
  group heading); a chapter opening of each with its epigraph, the
  source on its own line with its dash; Haynes' notes, a group heading
  and a note's link back and forth; Turney's first pages, the
  acknowledgements ending before the book's epigraph; Stubbs' text
  with no ";" at a line's start.

## Left open by the specs

- galley-eval counts a heading's label but not an epigraph's `source`
  or a note's `group` (`docs/specs/evaluation.md` was not changed). On
  the four evaluation books there is no note group and at most two
  epigraphs (work package 4, deliverable 4), so the plan leaves the tool as it is; a
  score that moves for it is named in 7.1.
- Structure §26 gives no whole-book target for spaced punctuation or
  case splits; the plan asserts only Mariéjol's zero attachments and
  the fidelity check, and reports the counts.
- Structure §26 gives the expected output of the new excerpts to the
  owner's eye; the plan has a subagent read the renders, as the owner
  asked on 17 November 2026, and lists them in the report.
