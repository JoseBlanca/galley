# Plan: stray text in the body

This plan removes four kinds of stray text that a reader of the EPUB
finds in the middle of the book's text:

- **junk words of inkless pages**: a page that prints nothing, or only
  show-through or a patterned endpaper, whose text layer still holds
  words the scan's OCR invented (Haynes page 9, "SP I fiyj. £ v", a
  heading after the contents);
- **running heads left in a paragraph**: a head whose page number the
  text layer boxed apart from it (Kadesh 38, Domesday 200 and 428), or
  whose words the OCR damaged (Gierke 16 and 84);
- **footnotes left in the body, and references left unlinked**:
  Gierke's introduction (pages 15 to 49) has all its footnotes glued
  into paragraphs; 8 Domesday pages keep a one-line footnote as a
  paragraph; 20 Domesday references are a sign followed by punctuation
  ("servus*.", page 55) and are not linked;
- **Stubbs' cut-in margin notes** whose lines sit on the body's
  baselines: 169 of the book's notes stay in the body, on 134 pages.

The owner asked for it on 18 November 2026, after reading the EPUBs of
the lists-figures plan, and said to write it and go on without waiting.
Dated 18 November 2026. State: approved; under way.

It is built from the measurements of two investigations made on 18
November 2026 on the runs of the eight books at main a0a1675
(`runs/lists-figures/` of the main checkout), which work package 1
turns into amendments of `docs/specs/layout.md` ("layout §n"),
`docs/specs/structure.md` ("structure §n"), the analyze rules of
`docs/specs/plates.md` and `docs/specs/figures.md`, and
`docs/architecture.md` ("architecture §n"). Their reports are in the
session's scratch folder; what the tasks need of them is below.

Page means page index of the whole PDF, from 0.

## In and out

In:

1. An inkless page: analyze measures the ink under each text-layer
   word on the 36 dpi render it already makes, and marks the page when
   at least half its words have no ink; extract turns the words of such
   a page into removals with a new reason. Measured: ink is the largest
   gap in gray level between the local background and any pixel of the
   word's box grown by 3 pt, either way (so white print on a dark cover
   counts). Real words: of 1.1 million, 339 fall below 20; junk words:
   41 of 43 below 20. Junk pages have 0.88 to 1.00 of their words below
   20; the highest real page, Domesday 481 (a rotated table), 0.10. It
   catches Haynes 9 and 421 and Haskins 277 and 278. A rule per word was
   measured and dropped: 7 of 12 inkless words checked by eye on
   ordinary pages were real words whose text-layer box sits 5 to 20 pt
   off the print. Such a page is not `blank`, which stops the run when
   it lacks a text layer.
2. Running heads, two rules:
   - layout, `running_head_row_count`: when the head row is only a page
     number, the next row with letters joins the head when it is itself
     at least 1.3 pitches from the row below it (Kadesh 38: 2.8 pitches,
     Domesday 200: 2.0, 428: 4.1);
   - structure's survey: the limit on the difference in letters between
     two heads it compares rises from 8 to 14. On the eight books it
     takes Gierke 16, Gierke 84 and Mariéjol 158, all real heads, and
     no other line.
3. Footnotes, three rules:
   - layout's footnote band: a row is small at 0.85 of the larger of the
     book's body word height and the page's median row height. Measured:
     the band appears on 30 Gierke pages, all footnotes, and 4 Mariéjol
     pages; no other book changes and no page loses its band;
   - layout, one-line notes: a foot row opening with a marker that reads
     1 and no full stop, then a capital, is small when its width per
     character is at most 0.85 of the page body's (measured 0.66 to 0.83
     on 12 such pages). It catches 8 Domesday pages (163, 174, 278, 303,
     308, 315, 347, 485); page 157, "2. The Church", a table, is the one
     false hit the "reads 1, no full stop" condition removes;
   - structure's reference candidates: a sign followed by punctuation
     ("servus*.") is a candidate. 49 new candidates in Domesday, of which
     20 are unlinked references; also 27 in Kadesh and 16 in Gierke.
4. Stubbs' cut-in notes: layout's cut-in zones (layout §9) also count a
   cut row as shortened when its words in the strip beside the note, of
   two letters or more, have a median height at most 0.9 and a width per
   character at most 0.9 of the page body's. Simulated with layout's own
   code on the whole book: 590 more words move, on 120 pages, of which
   365 are note words by the evaluation, 143 have at most 2 letters, 82
   are other (mostly garbled note words, perhaps 10 body words); 71 of
   the 169 notes are recovered whole, 41 mostly, 9 in part, 48 not.
   Without the size test 30 clear body words move.
5. Four new excerpts (work package 1) and the EPUBs of the eight books.

Out:

- **Mariéjol**: no effort on its scans (owner, earlier). Its page 459 is
  not caught by the rule of item 1; it gets no config exclusion here.
- **Domesday's other unlinked references**: 39 glued to a number
  ("£16,0002"), 35 not matched on pages whose notes were cut wrongly,
  24 taken by another note, 17 read as a letter, 15 a word of their own.
  Each is a rule of its own; a later plan.
- **Unreferenced endnotes** of Gierke (91), Haynes (50) and Turney (83):
  a separate matching rule, a later plan.
- **The 48 Stubbs notes item 4 does not recover**: the body line's edge
  is more than 3 pt from the inset (about 18), the text layer mixes rows
  (about 15), and smaller causes.
- Gierke 167's head (a speck reaching 2.007 pt into it), Kadesh's damaged
  OCR, tables.
- Already fixed on main and only checked here: the Haskins head in a
  paragraph (page 23) and the Haskins footnote of page 28, both reported
  by the owner on 17 November.

**Changed by work package 1**, measured with layout's own code on the
eight books; the specs hold the rules and these numbers win over items
1 to 4 above: the footnote band is 0.82 of the page's median row height
(at 0.85 of the larger height, the last rows of two contents pages,
Haskins 14 and Turney 10, became footnotes); one-line notes take a
limit of 0.9 (10 Domesday pages and Gierke 61; 0.85 missed Domesday
185); the head row joins only after a head row that is one word of 2 or
3 digits (any page-number form changed six Stubbs pages with specks);
an inkless page before the end of the front matter stays front matter
(Haskins' endpapers 1 and 2); `domesday_notes` gains page 430 and
`gierke_notes_heads` takes page 78 for 83, a title page with no head;
the rule of item 4 moves nothing on Stubbs 34 and 143, whose tests
check only that no body word moves. Gierke's introduction notes are
already notes in the excerpt, whose body height is the introduction's,
so only the whole-book count shows that fix.

Decided without the owner, who said not to wait, each to be said in the
report: pages.json gains the mark of item 1, so its format version
rises by one, and the removal reasons gain one value
(`inkless_page_text` or the name architecture §8 gives it). Books run
before the merge must run again from analyze.

**The owner's books are copyrighted.** No page of Turney or Haynes is
cut into an excerpt, and no committed file quotes their text beyond a
few words naming a case. Their tests count and compare page indices, are
found in `samples/` of the main checkout, and skip with the reason when
absent, as `tests/test_owner_books.py` does.

## What must be in place

- `which pandoc tesseract epubcheck` lists all three (checked on the
  starting commit a0a1675).
- The public-domain books in `samples/public_domain/` of the main
  checkout and the owner's two PDFs in `samples/` (checked).
- `uv run pytest -m whole_book` passes on a0a1675 (144 passed on 18
  November 2026 at the lists-figures merge).

## The order of the work, and the streams

Work package 1 is done first and alone: it changes the specs, the
formats in `model.py` and `docs/architecture.md`, and adds the
excerpts. Then three streams run side by side, each in a worktree of its
own made from `plan/stray-text`:

| stream | work packages | may change |
|---|---|---|
| `analyze` | 2 | `src/galley/analyze/`, `src/galley/extract/`, their tests |
| `layout` | 3 (tasks 3.1, 3.3, 3.4) | `src/galley/layout/`, its tests |
| `structure` | 3 (task 3.2), 4 | `src/galley/structure/`, its tests |

The `layout` stream holds the layout half of work packages 3 and 4,
which change the same files (`_column.py`, `_page.py`); the
`structure` stream holds their structure half. A test file shared by
two streams (`tests/conftest.py`, an excerpt's expected files) is
changed by one of them, named in its task; another stream that needs it
stops and asks. Work package 5 runs after the three are merged.

## 1. The specs, the formats and the excerpts

What it gives: the amendments that items 1 to 4 of "In" need, the
formats in `model.py`, and four excerpts whose expected files say what
the later work packages must make of them.

Deliverables:

1. The spec amendments, each a section or a paragraph where its rule
   belongs, with its thresholds and the measurements above: the
   inkless page in the analyze spec (`docs/specs/plates.md`, where the
   36 dpi render is specified) and architecture §8; layout §3 and §9
   for the head row, the footnote band, one-line notes and cut-in
   zones; structure §3 and §11 for the survey's limit and the reference
   candidates. Check: the `first-reader` and `spec-reviewer` subagents
   on the amended parts; their findings handled in the report.
2. pages.json's version raised, the page's mark and the new removal
   reason in `model.py` and `docs/architecture.md`, and `docs/glossary.md`
   for "inkless page". Check: `uv run pytest tests/test_model.py` with
   a new test that a pages.json of the old version is refused.
3. The excerpts, added to `scripts/fetch_samples.py` with what each
   covers, cut, and committed with their configs:
   - `haskins_endpapers`: Haskins 275 to 278 (275 a real colophon, 276
     excluded by the book's config, 277 and 278 junk);
   - `domesday_notes`: Domesday 24, 35, 55, 89, 163, 174, 278, 428, 481
     (one-line notes, references with punctuation, a head boxed apart,
     481 a rotated table that must stay);
   - `gierke_notes_heads`: Gierke 14 to 18, 40, 63, 83, 84, 146
     (footnotes of the introduction, damaged heads, 63 a page whose
     text-layer boxes sit off the print);
   - `stubbs_cut_in`: Stubbs 19, 34, 37, 120, 125, 143 (cut-in notes on
     the body's baselines; 120 and 125 hold body words a looser rule
     would move).
   Check: `ls tests/fixtures/pdf/` lists the four; the expected files of
   each, transcribed from the page images (memory: the assistant checks
   by eye itself), fail on a0a1675 where the defect is.

Tasks:

- [x] 1.1 The spec amendments of deliverable 1, in a commit of their
  own, then the `first-reader` and `spec-reviewer` subagents.
- [x] 1.2 The formats of deliverable 2. Spec: architecture §8 as 1.1
  amends it.
- [x] 1.3 The excerpts of deliverable 3 and their expected files under
  `tests/fixtures/expected/stray_text/`, each with how it was read, as
  `tests/fixtures/expected/lists_figures/` does. The expected files
  are tests marked to fail (`xfail` with `strict = true`) until their
  work package lands; the task that makes one pass removes its mark.
- [ ] Review of work package 1.

## 2. Inkless pages

What it gives: `galley2epub` on Haynes leaves nothing of pages 9 and
421 in the EPUB, and each word of those pages is a removal with the new
reason.

Deliverables:

1. The `haskins_endpapers` tests pass: pages 277 and 278 marked, every
   word removed with the reason; 275 not marked and its words in the
   output. The `domesday_notes` test of page 481 and the
   `gierke_notes_heads` test of page 63: not marked.
2. A whole-book test over the eight books: the marked pages are exactly
   Haynes 9 and 421 and Haskins 277 and 278 (Haynes' only when its PDF
   is present). Check: `uv run pytest -m whole_book -k inkless`.

Tasks (stream `analyze`):

- [x] 2.1 The ink measure and the page's mark in analyze, where the
  36 dpi render and the text layer's words are already at hand. Spec:
  the analyze amendment of 1.1.
- [x] 2.2 extract's removals for a marked page, as it does for an
  excluded page, and the tests of deliverables 1 and 2.
- [ ] Review of work package 2.

## 3. Running heads and footnotes

What it gives: the heads of Kadesh 38, Domesday 200 and 428, Gierke 16
and 84 removed as running heads; Gierke's introduction footnotes and
Domesday's eight one-line footnotes as notes; Domesday's references
with punctuation linked.

Deliverables:

1. The excerpt tests of the five heads pass (`kadesh_29-38` page 38,
   `domesday_front_flow` page 200, `domesday_notes` 428,
   `gierke_notes_heads` 16 and 84).
2. The excerpt tests of the footnotes pass: Gierke 15 to 18, 40 and 146
   have their notes as notes (already so in the excerpt, see "Changed
   by work package 1"); Domesday 163, 174 and 278 their one-line note; Domesday 55 links "servus*." to its note.
3. Whole-book counts, in the report and as tolerances in the whole-book
   tests: Gierke's notes left in the body on pages 15 to 49 at 0
   (today all); Domesday's one-line notes in the body at 0 of the 10,
   and Gierke 61's;
   Domesday's unlinked references fall by at least 15 of the 20; no
   page of the eight books loses its footnote band; the running-head
   lines left in the body of Kadesh, Domesday and Gierke fall from 5
   to 0 apart from Gierke 167.

Tasks:

- [ ] 3.1 (stream `layout`) The head row of item 2 in
  `running_head_row_count`, and the tests of Kadesh 38 and Domesday 200
  and 428. Spec: layout §3 as 1.1 amends it.
- [x] 3.2 (stream `structure`) The survey's limit of item 2, and the
  tests of Gierke 16 and 84; then the reference candidates of item 3
  and the test of Domesday 55. Spec: structure §3 and §11 as amended.
- [ ] 3.3 (stream `layout`) The footnote band and the one-line notes of
  item 3, and the tests of Gierke 15 to 18, 40, 146 and Domesday 163,
  174, 278. Spec: layout §3 as amended.
- [ ] 3.4 (stream `layout`, after 3.3) The whole-book counts of
  deliverable 3, with the counts of the starting commit beside them.
- [ ] Review of work package 3.

## 4. Stubbs' cut-in notes

What it gives: the Stubbs notes whose lines sit on the body's baselines
come out as margin notes.

Deliverables:

1. The `stubbs_cut_in` tests pass: pages 19 and 37 have their notes as
   margin notes; on pages 34, 120, 125 and 143 no body word moves.
2. Whole-book, in the report and as a tolerance: Stubbs' margin notes
   left in the body fall from 169 to at most 110; the words moved out
   of the body that are body words by the evaluation's reference stay
   at most 20.
3. The Stubbs tests of `stubbs_heads` and `stubbs_51_56-64` still pass.

Tasks (stream `layout`, after 3.4):

- [ ] 4.1 The shortened-row test of item 4 in the cut-in zones, and the
  tests of deliverables 1 and 3. Spec: layout §9 as amended.
- [ ] 4.2 The whole-book counts of deliverable 2.
- [ ] Review of work packages 4 with 3's layout half, when they are
  reviewed together.

## 5. The measurement and the EPUBs

What it gives: the eight books run again, measured against the
lists-figures runs, and checked by eye.

Deliverables:

1. `uv run pytest -m whole_book` passes.
2. The evaluation (`galley-eval`) of the four evaluation books against
   `runs/lists-figures-final/`: no score falls beyond its tolerance;
   the notes and margin notes scores of Domesday, Gierke and Stubbs
   given with both sides.
3. The EPUBs of the eight books in `runs/stray-text/` of the main
   checkout, each clean under epubcheck.
4. The pages of items 1 to 4 checked by eye against their images by a
   subagent, with each that is still wrong in the report.

Tasks:

- [ ] 5.1 The runs, the evaluation and epubcheck: deliverables 1 to 3.
- [ ] 5.2 The checks by eye of deliverable 4, and the fixes they call
  for, each with a test.
- [ ] 5.3 The quick tests back to about a minute: the four excerpts add
  to a run of 71 s on a0a1675. Find where the time goes
  (`--durations`) and cut it without dropping a check.

## How the whole plan is checked at the end

The checks of the `coding` skill on the plan's branch, the whole-book
tests, the evaluation and the EPUBs of work package 5. The owner looks
on the Kindle at Haynes after the contents (page 9 gone), Gierke's
introduction (its notes), and a few Stubbs pages with margin notes
(pages 19 and 37).
