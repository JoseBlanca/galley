# Plan: reading a badly OCRed book again, and Stubbs' letter fragments

This plan builds three things the owner asked for on 19 November 2026,
after reading the EPUBs of the stray-text plan:

- **`ocr = "redo"`**: for a book whose own OCR text layer is bad,
  galley reads every text page again with Tesseract and uses its words
  instead of the layer's. The case is Kadesh
  (`battleofkadeshst00breauoft`), whose layer reads "Me^iddo. already in
  tli.- sixti-fiith century ln-forr Christ" on page 9 where Tesseract
  reads "At Megiddo, already in the sixteenth century before Christ".
  The config key exists, but galley refuses it today.
- **Stubbs' letter fragments** (`earlyplantagenet01stub`): the layer
  splits off a descender or the dot of an "i" and gives it as a word of
  its own, so the text reads "Swabia, . and" and "only -' to call".
- **Housekeeping**: real titles and authors in the configs of the
  public-domain books (the EPUBs were titled with the Internet Archive
  identifier, "An Author"), and Mariéjol (`catherinedemedic00mariuoft`)
  dropped from the whole-book tests, the evaluation and the runs, as
  the owner asked ("drop it"), because neither its layer nor Tesseract
  reads its worn print.

The owner said to write the plan and go on without waiting. Dated 19
November 2026. State: approved; under way.

It is built from two investigations of 19 November 2026 at main 9292b17
(their notes are in `tmp/investigation/` of the plan's worktree, not
committed) and from amendments that work package 1 makes to
`docs/architecture.md` §6, §7b and §16 ("architecture §n"),
`docs/specs/extract.md` ("extract §n"), `docs/specs/reocr.md` and
`docs/specs/structure.md` ("structure §n").

Page means page index of the whole PDF, from 0. Each book is named by
its short name and, the first time, its folder.

## In and out

In:

1. **Redo in analyze and extract.** analyze no longer refuses
   `ocr = "redo"`: every page that would be a text page gets the text
   source `ocr`; the layer still decides what a page is (the plate,
   inkless, front-matter and figure rules use its word boxes), and a
   plate keeps its layer (Tesseract reads 38 to 140 junk words on a
   Kadesh plate, the layer 3 to 13). extract renders an OCR page at
   300 dpi in the PDFium thread and reads it with Tesseract (`ocr.read_image`
   and `words_of_tsv`, which already give words.json's `Word`) in the
   workers. Excluded and front-matter pages keep the layer's words as
   their removal records. Layout re-reads nothing under redo. No file
   format changes. Measured: Tesseract takes 0.95 s a text page; all 54
   pages of Kadesh in about 11 s with 6 threads.
2. **Note markers under redo.** In a trial on all of Kadesh, linked
   notes fell from 31 (layer) to 2 (Tesseract): Tesseract reads a raised
   digit as `*`, `'`, `"` or "S" ("⁵In" as "Sin"). The rule, settled in
   work package 1's spec from the pages: a note marker the layer reads
   where Tesseract's word holds none is taken from the layer word under
   it, by position. Target: Kadesh's linked notes at least 31.
3. **Junk headings under redo.** Tesseract makes 13 junk headings from
   the hieroglyph rows of pages 21, 32, 39 and others. The words of an
   in-page figure must be removed as figure text under redo as with the
   layer, and a line of low Tesseract confidence must not become a
   heading. Target: Kadesh's headings as with the layer, 3, plus any
   real heading the layer missed.
4. **Stubbs' letter fragments**, in structure, with a new removal
   reason: a token of at most 2 characters and at most 1 letter, at
   least half its width inside a word of 3 letters or more on the same
   line, overlapping it in height and at most 1.15 times its height.
   On Stubbs it takes 261 tokens on 127 pages, all of 24 sampled were
   fragments; run on every line it also takes real text in Domesday
   (61, "D." in footnotes), Gierke (44) and Mariéjol (81), so it runs
   only where the fragments are: work package 1 measures the narrowest
   condition that takes Stubbs' and nothing else (lines shortened by a
   cut-in note hold 244 of the 261).
5. **Titles and Mariéjol.** `title` and `authors` go into each entry of
   the whole-book configs in `tests/conftest.py`, and the test that
   compares them with `evaluation/books.toml` compares these too.
   Mariéjol leaves the whole-book tests, `evaluation/books.toml` and the
   evaluation's tests; its two committed excerpts stay as structure
   tests, and `scripts/fetch_samples.py` must keep cutting them (move
   the book into `BOOKS`).

Out: Mariéjol's text; italics and small caps under redo (Tesseract
misreads small caps, "Breastep"; the layer too); Stubbs' garble the
fragment rule does not fix (page 37 "j-j^ too anc j", a misreading;
page 97, two rows merged by the layer; pages 102 and 120, notes cut by
the column; page 236's "r Air ttt");  a test of which books
want redo (only Kadesh does: on 10 pages each of the other books the
layer is as good as Tesseract, within 0.02 of the share of known
words).

Decided without the owner, who said not to wait: Mariéjol's excerpts
stay (they cover rules no other excerpt does); the owner's two books
keep their placeholder titles in the tests (their real configs are the
owner's); Kadesh's runs and whole-book tests use redo.

**The owner's books are copyrighted**: no page of Turney or Haynes is
cut into an excerpt or quoted in a committed file.

## What must be in place

- `which tesseract pandoc epubcheck` lists all three (checked on 9292b17).
- The public-domain books in `samples/public_domain/` of the main
  checkout (checked).

## The order of the work, and the streams

Work package 1 first and alone. Then two streams, each in a worktree
made from `plan/ocr-redo`:

| stream | work packages | may change |
|---|---|---|
| `redo` | 2, then 3 | `src/galley/analyze/`, `src/galley/extract/`, `src/galley/ocr.py`, `src/galley/structure/` only for task 3.2, their tests, `tests/test_stray_text_*.py` and Kadesh's expected files |
| `fragments` | 4 | `src/galley/structure/` except what 3.2 changes, structure's tests |

Work package 3 and work package 4 both touch structure (3.1 moves the
glued-reference test out of `structure/_markers.py` into extract), so
work package 3 starts after work package 4 is merged. Work package 4 may
change the expected files of `stubbs_summaries_index` and `stubbs_heads`
where fragments leave them.

**Changed by work package 1** (the specs hold the rules): the note
references are taken from the layer in extract (structure §34 and
extract §9); a line of Tesseract's words with a median confidence below
60 is never a heading (structure §35; the 12 junk headings have medians
0 to 50.5, real ones 85 to 96); a letter fragment is a layer word of at
most 2 characters and 1 letter inside a word of 3 letters or more,
alone in its row, not on an index page, and the rule runs only in a
book where at least 0.15 of the pages have one (Stubbs 0.410, 251
words; the others at most 0.030). Kadesh's page 74, the library's card
pocket, goes into Kadesh's `exclude_pages` in task 2.2.
`docs/specs/evaluation.md` drops Mariéjol in task 5.1.
Work package 5 runs after both.

## 1. The specs, the excerpt, the titles and Mariéjol

What it gives: the rules of items 1 to 4 in the specs, an excerpt of
Kadesh run with redo, real titles, and Mariéjol out of the whole-book
tests and the evaluation.

Deliverables:

1. The amendments: architecture §6 (the `ocr` key), §7b, §16
   (Tesseract required by analyze and extract under redo); extract's
   rules for an OCR page; the note-marker rule of item 2 and the heading
   rule of item 3 where they belong (extract or structure); structure's
   fragment rule with its reason and the condition of item 4, measured.
   Check: the `first-reader` and `spec-reviewer` subagents; their
   findings handled.
2. The excerpt `kadesh_redo` (Kadesh pages 8 to 17 or the pages the
   investigation names: page 9's body and footnotes, running heads,
   note markers, a plate) in `scripts/fetch_samples.py`, with a config
   that sets `ocr = "redo"`, and expected files read from the page
   images. The tests are strict expected failures naming their task.
   Check: they fail on 9292b17, where analyze refuses redo.
3. Titles and authors in the whole-book configs; the comparison test
   extended. Check: it fails on 9292b17 for the four evaluation books.
4. Mariéjol out of the whole-book tests and the evaluation, its
   excerpts still cut. Check: `uv run pytest -m whole_book
   --collect-only -q | grep -c catherinedemedic` gives 0;
   `uv run python scripts/fetch_samples.py --cut-only` still lists both
   excerpts.

Tasks:

- [x] 1.1 The spec amendments of deliverable 1, in commits of their own,
  then the two subagents.
- [x] 1.2 The excerpt and its expected files (deliverable 2).
- [x] 1.3 Titles and Mariéjol (deliverables 3 and 4).
- [x] Review of work package 1 (with work package 2).

## 2. Redo in analyze and extract

What it gives: `galley2epub run` on Kadesh with `ocr = "redo"` makes an
EPUB from Tesseract's words.

Deliverables:

1. The `kadesh_redo` tests of the words pass: page 9 reads "At Megiddo,
   already in the sixteenth century before Christ"; its footnotes are
   Tesseract's; the plate keeps its layer; excluded pages keep the
   layer's words as removals.
2. A unit test that analyze marks text pages `ocr` under redo, and one
   that layout makes no re-reading records under redo.
3. The whole book: `uv run pytest -m whole_book -k kadesh` passes with
   redo, and Kadesh's share of unknown words in its body falls (measured
   against the layer's, with both numbers in the report).
4. The quick tests stay about a minute.

Tasks (stream `redo`):

- [x] 2.1 analyze: redo accepted, text pages marked `ocr`, Tesseract
  required. Spec: architecture §7b as amended.
- [x] 2.2 extract: Tesseract's words on OCR pages, the layer's words as
  removal records where the spec says; the tests of deliverables 1, 2
  and 4; the whole-book config of Kadesh with redo and deliverable 3.
- [x] Review of work package 2.

## 3. Note markers and headings under redo

What it gives: Kadesh with redo keeps its note links and gains no junk
headings.

Deliverables:

1. The `kadesh_redo` tests of note links and headings pass.
2. Whole book with redo: linked notes at least 31; headings the layer's
   3 and no junk from the hieroglyph rows. Check: whole-book tests with
   these counts.

Tasks (stream `redo`, after 2.2):

- [x] 3.1 The note-marker rule of item 2. Spec: as 1.1 places it.
- [x] 3.2 The heading rule of item 3, and figure text under redo.
- [x] 3.3 (added after work package 2) The notes' own markers under
  redo: Tesseract misreads them ("Sin" for "⁵In"), so Kadesh pages 9,
  25, 27, 33, 41 and 50 lose their footnotes; take them from the layer as
  3.1 does the references, and keep two note columns apart (pages 9,
  25). The map captions "MAP III." and "MAP V" (`test_figures.py`).
- [x] 3.4 The whole-book counts of deliverable 2.
- [ ] Review of work package 3.

## 4. Stubbs' letter fragments

What it gives: Stubbs' lines without the split-off pieces of letters.

Deliverables:

1. Excerpt tests on Stubbs pages already committed (`stubbs_cut_in`,
   `stubbs_51_56-64`, `stubbs_heads`, or a page added in 1.2 if none has
   a fragment): the fragments removed with the new reason, the words
   whole.
2. Whole book: the fragments removed on Stubbs, at least 240 of the 261
   measured; on every other book none, or each one checked on its page
   image.

Tasks (stream `fragments`):

- [x] 4.1 The rule and the tests of deliverable 1. Spec: structure as
  1.1 amends it.
- [x] 4.2 The whole-book counts of deliverable 2.
- [x] Review of work package 4.

## 5. The measurement and the EPUBs

Deliverables:

1. `uv run pytest -m whole_book` passes.
2. The evaluation of the three evaluation books left against
   `runs/stray-text-final/`: no score falls beyond the tolerances of the
   lists-figures plan.
3. The EPUBs of the seven books in `runs/ocr-redo/` of the main
   checkout, each clean under epubcheck, with real titles.
4. The pages of items 1 to 4 checked by eye against their images.

Tasks:

- [ ] 5.1 The runs, the evaluation and epubcheck.
- [ ] 5.2 The checks by eye, and the fixes they call for.

## How the whole plan is checked at the end

The checks of the `coding` skill, the whole-book tests, the evaluation
and the EPUBs of work package 5. The owner looks on the Kindle at Kadesh
(`battleofkadeshst00breauoft`), its first pages and its notes, and at
Stubbs (`earlyplantagenet01stub`).
