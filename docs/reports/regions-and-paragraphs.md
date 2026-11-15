# Report: regions and paragraphs

The work report of `docs/plans/regions-and-paragraphs.md`, written as
the work goes, for the owner. Started 15 November 2026. State: under
way.

## Before the first task

The plan's branch, `plan/regions-and-paragraphs`, was made from
`spec/structure` (commit 2f50468), not from `main`, because the specs
and the plan it is built from are on that branch and the owner has not
ordered it merged. Merging the plan's branch into `main` brings them in.

Checked on 15 November 2026: `which pandoc tesseract combine_tessdata
dawg2wordlist epubcheck` printed five paths; `tesseract --list-langs`
lists `eng` and `fra`; the six whole books and the four Gutenberg HTML
files are in `samples/public_domain/`; `uv run galley-eval --help`
works; the baseline runs are in `runs/evaluation/` of the main checkout;
`uv run --locked pytest` gave 781 passed, 8 deselected.

## 1. Three new excerpts

Done as planned, commit f8f3c50. `stubbs_51_56-64` (465 KB),
`domesday_74-83` (653 KB) and `mariejol_210-219` (745 KB) are committed,
ten pages each, every page with a text layer; `uv run pytest
tests/test_excerpts.py -q` gives 7 passed. `galley2epub run` on each
wrote an EPUB that epubcheck passes with no error or warning (galley as
it was before this plan, one block per page).

Change to the plan: work package 5 may change `tests/conftest.py`,
where the excerpts' book configs are (`EXCERPT_CONFIGS`); the new
excerpts have none yet, so the end-to-end tests do not run them.

The work package is reviewed together with work package 4, which runs in
the same stream next: its change is a list of page indices in
`scripts/fetch_samples.py`, with no code a review of its own would test.

## 4. Markdown writes margin notes and unreferenced notes

Done, commit 7de81a0 and the review's fixes up to 202d7ba, merged into
the plan's branch. `src/galley/markdown/` writes a margin note as a
fenced div with the class `margin-note` where it is in `blocks`, and a
note with `referenced` false as a div with the class `note` around its
blocks' divs. Deliverables:

1. The new tests pass: `uv run pytest tests/test_markdown.py -q` gives
   all passed; 11 new test functions, the refusal test with 11 cases.
2. The fidelity check at markdown's boundary passes on these blocks and
   fails on a word lost from a note, its marker or a margin note.
3. `test_the_epub_of_margin_notes_and_notes_passes_epubcheck` builds an
   EPUB from a hand-made `blocks.json` with both kinds; epubcheck gives
   no error or warning.

Checks on the plan's branch after the merge: ruff and ty pass; `uv run
pytest -q` gives 808 passed, 8 deselected in 20.1 s.

**Review** (work packages 1 and 4 together, four reviewers). No reviewer
found a word lost or invented. What was fixed:

- The spec's placement rule for notes reversed page order when a
  paragraph runs onto the next page: a note of page 4 went after the
  paragraph from page 3, before page 3's margin note and notes. The
  orchestrator corrected structure §6 and §10 (b) (commit 1e23f45): a
  note goes after the last block, in the order of `blocks`, whose first
  origin is on the note's page or an earlier one. This keeps the spec's
  aim, side text after the paragraph in which the page ends, and page
  order. The owner was told and can revert it.
- Two placement cases and two refusals inside a note had no test that
  could fail; now they do.
- Markdown refuses an id given twice, which would give an EPUB with
  duplicate ids.
- The refusal message listed what markdown writes, so it read as the
  opposite; a malformed `blocks.json` is now named apart from what is
  not written yet.
- Docstrings, a parameter name, a comment's unit (page indices).
- The excerpt test checked a text layer on page 0 only; it now checks
  every page. Kadesh's page 9 and Haskins' page 8 are blank by design
  and listed.

Not taken:

- Where a non-empty marker goes (at the start of the note's first
  block): every marker is empty in this plan; the second plan, which
  splits markers off, settles it with the edits tool, which would read
  the marker as an inserted word.
- The fidelity check does not see a note moved to the wrong place: order
  is not part of it, by architecture §13; the placement tests guard it.

**For whoever next writes a plan or revises a skill.** The excerpt test
that reads every page costs 14 s in the 8-thread run (27 s to 41 s),
because pdfplumber reads 60 pages in each of 8 threads; the default run
is unaffected (20 s, under the 30 s budget). The coding skill's budget
names only the default run.

## 2. Layout cuts pages into regions

Done, commits 647d5f4 to c990d84 on `plan/regions-and-paragraphs-layout`,
merged into the plan's branch. Layout measures the book (column width,
body word height, line pitch), then on each page takes out the outer
margin notes, the running-head line and the footnote band, cuts columns
in the body and the band, and puts drop capitals in their line.

Deliverables:

1. The unit tests of layout §8: `uv run pytest tests/test_layout.py -k
   "measure_book or margin or band or head or column or drop_capital"
   --collect-only -q` lists 35 or more, at least 8 required; all pass.
2. 1 worker and 3 give the same bytes on 8 hand-made pages.
3. `uv run pytest -m whole_book -k layout`: 6 passed in 46.6 s, the
   fidelity check and a new per-page check of every word's text and box
   on the six whole books.
4. The reference pages look as the spec says, apart from the cases the
   spec now lists (below); the owner checks them in work package 5.
5. Default `uv run pytest` on the layout branch: 843 passed in 17.2 s;
   on the plan's branch after the merge, 873 passed in 22.6 s.

Changes to the plan: the reference pages of layout §8 are 15, not 14
(Domesday page 75 added for a left margin note; page 74's is on the
right). The stream changed `tests/test_end_to_end.py`, outside its
files, by the orchestrator's leave: five assertions of the walking
skeleton's one region per page were replaced by checks that follow from
the layout spec.

Spec changes made during the work and the review, each in its own
commit: the band is cut into columns only when the gutter lies within
10 pt of the column's middle (f126f0b; on Kadesh the gutter is within 8
pt, on Domesday's short notes side by side 13 to 46 pt away); in the
body a column run starts and ends at a row open at the gutter (cf560fd,
f00b675); each page's column edges come from its own wide rows (f3ccf0d);
cases for margin words that reach into the column and for the page
number below a column cut (e04467b).

**Review** (four reviewers). No word lost or invented on the six books.
Two findings changed the reading order of body text and were fixed by
changing the spec, on the orchestrator's decision, which the owner was
told:

- Full prose lines beside a column cut were read as left halves, then
  right halves (Kadesh page 28; Domesday 43, 388, 477), because a
  justified line with one word across the gutter joined the run. Now a
  body run starts and ends at an open row.
- Column edges measured once per book put about 470 of Gierke's body
  words into margin regions (its introduction is set 296 pt wide; on its
  endnote pages the margin notes join the rows). Now each page with 3 or
  more wide rows takes its own edges. Gierke's margin words went from
  3,487 to 2,235, its body words from 109,014 to 110,261; page 13 has 1
  margin word, down from 32.

Also fixed: a word with an inverted box could be counted twice; a drop
capital could go to the other column; a per-page check of words and
boxes in the tests; boundary tests for thresholds that could move with
no test failing (small type 0.85, band gap 1.1 pitches, 2 band rows, 8
body rows, the gutter search, the drop capital's height); names,
docstrings, enums, the sources of constants.

Not taken or not fully fixed:

- The run rule of the body is not applied in the band: there the first
  note row of Kadesh page 8 has "Ori-" across the gutter and would be
  read across both columns.
- Domesday 43 and 388: two prose rows with a wide space at the gutter
  still count as open and are cut in halves. No rule tried tells them
  from real columns. The owner's page check or the evaluation will show
  whether it matters.
- The band's 10 pt threshold has little room (Kadesh at most 7.5 pt, a
  Domesday table 10.8 pt): left to the reference-page tests.

**What the owner should know.** Layout of Domesday's 558 pages takes
3.2 s. Mariéjol's 9-pt OCR notes stay in the body (layout §6), and its
table of contents (page 450) is cut into titles and page numbers.
