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
